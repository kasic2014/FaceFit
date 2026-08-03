"""Stage 19.3 approval gate for the Annotation Agreement tie-breaker.

Only the deterministic tie-breaker is approved here. Temporal thresholds and
all official matching/agreement execution remain explicitly ineligible.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.vision.annotation_policy_revision import (
    AWAITING_STATUS,
    MATCHING_POLICY_ID,
    MATCHING_POLICY_VERSION,
    SCOPE,
    TIE_BREAKER_POLICY_ID,
    TIE_BREAKER_POLICY_VERSION,
    V2_ORDER,
    decision_template,
    validate_decision,
)
from app.vision.pilot_video_intake import (
    ensure_finite,
    load_strict_json,
    sha256_file,
    write_strict_json,
)


SCHEMA_VERSION = "1.0.0"
STAGE = "19.3"
APPROVED_STRATEGY = "DETERMINISTIC_MULTI_CRITERIA_V2"
TIE_BREAKER_STATUS = "tie_breaker_policy_approved"
AGREEMENT_POLICY_STATUS = "agreement_threshold_evidence_required"
VALIDATION_FAILED_STATUS = "agreement_policy_validation_failed"
SNAPSHOT_CONFLICT = "POLICY_SNAPSHOT_VERSION_CONFLICT"
BLOCKING_REASONS = (
    "AGREEMENT_THRESHOLDS_NOT_APPROVED",
    "INSUFFICIENT_THRESHOLD_EVIDENCE",
    "OFFICIAL_MATCHING_NOT_ELIGIBLE",
)
REQUIRED_STAGE192_INPUTS = (
    "agreement_policy_candidate_0_2_0.json",
    "agreement_policy_revision_decision.template.json",
    "agreement_policy_revision_status.json",
    "stage13_tie_breaker_analysis.json",
    "tie_breaker_strategy_comparison.json",
    "compatibility_fixture_results.json",
)
NEW_OUTPUTS = (
    "agreement_policy_revision_decision.json",
    "approved_tie_breaker_policy_snapshot.json",
    "agreement_policy_governance_status.json",
    "validation_report_stage193.json",
    "validation_report_stage193.md",
)
SNAPSHOT_FIELDS = frozenset(
    {
        "policy_id",
        "policy_version",
        "policy_status",
        "scope",
        "operational",
        "tie_breaker_policy_id",
        "tie_breaker_policy_version",
        "tie_breaker_strategy",
        "ordering_rules",
        "one_to_one_matching",
        "positive_overlap_requirement",
        "matching_keys",
        "threshold_status",
        "minimum_temporal_iou",
        "maximum_onset_difference_ms",
        "maximum_offset_difference_ms",
        "approved_by",
        "approved_at",
        "approval_rationale",
        "source_candidate_sha256",
        "source_decision_sha256",
    }
)


class PolicyApprovalError(ValueError):
    """Raised when the Stage 19.3 approval contract is violated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _timezone_aware_iso8601(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, f"{field} must be a timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, f"{field} must be ISO 8601"
        ) from exc
    if parsed.utcoffset() is None:
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, f"{field} must include timezone"
        )
    return value.strip()


def validate_approved_decision(value: dict[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_decision(value)
    except ValueError as exc:
        raise PolicyApprovalError(VALIDATION_FAILED_STATUS, str(exc)) from exc
    if validated["decision"] != "APPROVE_DETERMINISTIC_MULTI_CRITERIA_V2":
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, "decision must approve deterministic V2"
        )
    if validated["selected_tie_breaker_strategy"] != APPROVED_STRATEGY:
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, "decision and strategy do not match"
        )
    if validated["threshold_decision"] != "DEFERRED":
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, "threshold_decision must remain DEFERRED"
        )
    if not isinstance(validated["reviewer_id"], str) or not validated[
        "reviewer_id"
    ].strip():
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, "reviewer_id is required"
        )
    _timezone_aware_iso8601(validated["reviewed_at"], "reviewed_at")
    if not isinstance(validated["rationale"], str) or not validated[
        "rationale"
    ].strip():
        raise PolicyApprovalError(
            VALIDATION_FAILED_STATUS, "rationale is required"
        )
    return validated


def load_approved_decision(path: str | Path) -> dict[str, Any]:
    try:
        value = load_strict_json(path)
    except ValueError as exc:
        raise PolicyApprovalError(VALIDATION_FAILED_STATUS, str(exc)) from exc
    return validate_approved_decision(value)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyApprovalError(VALIDATION_FAILED_STATUS, message)


def validate_stage192_inputs(
    revision_dir: str | Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    root = Path(revision_dir)
    documents: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for name in REQUIRED_STAGE192_INPUTS:
        path = root / name
        _require(path.is_file(), f"required Stage 19.2 input missing: {name}")
        try:
            documents[name] = load_strict_json(path)
        except ValueError as exc:
            raise PolicyApprovalError(
                VALIDATION_FAILED_STATUS, f"invalid Stage 19.2 input {name}: {exc}"
            ) from exc
        hashes[name] = sha256_file(path)

    candidate = documents["agreement_policy_candidate_0_2_0.json"]
    _require(candidate.get("policy_id") == MATCHING_POLICY_ID, "policy_id mismatch")
    _require(
        candidate.get("policy_version") == MATCHING_POLICY_VERSION,
        "candidate version mismatch",
    )
    _require(candidate.get("status") == "REVIEW_REQUIRED", "candidate status mismatch")
    _require(candidate.get("scope") == SCOPE, "candidate scope mismatch")
    _require(candidate.get("operational") is False, "candidate must be nonoperational")
    tie_breaker = candidate.get("tie_breaker_strategy")
    _require(isinstance(tie_breaker, dict), "tie-breaker candidate missing")
    _require(tie_breaker.get("strategy") == "UNRESOLVED", "strategy must be unresolved")
    _require(
        tie_breaker.get("status") == "REVIEW_REQUIRED",
        "tie-breaker status mismatch",
    )
    _require(
        tie_breaker.get("operational") is False,
        "tie-breaker candidate must be nonoperational",
    )
    thresholds = candidate.get("temporal_thresholds")
    _require(isinstance(thresholds, dict), "temporal_thresholds missing")
    _require(
        set(thresholds)
        == {
            "minimum_temporal_iou",
            "maximum_onset_difference_ms",
            "maximum_offset_difference_ms",
        },
        "temporal threshold fields mismatch",
    )
    _require(all(value is None for value in thresholds.values()), "thresholds must be null")

    template = documents["agreement_policy_revision_decision.template.json"]
    _require(template == decision_template(), "REVIEW_PENDING template changed")
    status = documents["agreement_policy_revision_status.json"]
    _require(status.get("current_status") == AWAITING_STATUS, "Stage 19.2 status mismatch")
    analysis = documents["stage13_tie_breaker_analysis.json"]
    _require(analysis.get("legacy") is not None, "Stage 13 analysis missing")
    comparison = documents["tie_breaker_strategy_comparison.json"]
    strategies = comparison.get("strategies")
    _require(isinstance(strategies, list), "strategy comparison missing")
    v2 = next(
        (
            item
            for item in strategies
            if item.get("strategy") == APPROVED_STRATEGY
        ),
        None,
    )
    _require(v2 is not None, "V2 strategy comparison missing")
    _require(tuple(v2.get("ordering_rules", ())) == V2_ORDER, "V2 ordering changed")
    fixtures = documents["compatibility_fixture_results.json"]
    _require(fixtures.get("fixture_only") is True, "fixture-only evidence missing")
    _require(fixtures.get("all_checks_passed") is True, "V2 fixtures did not pass")
    _require(
        fixtures.get("real_rater_annotation_loaded") is False,
        "real rater data was loaded",
    )
    ensure_finite(documents)
    return documents, hashes


def _snapshot(
    candidate: dict[str, Any],
    decision: dict[str, Any],
    candidate_sha256: str,
    decision_sha256: str,
) -> dict[str, Any]:
    tie_breaker = candidate["tie_breaker_strategy"]
    thresholds = candidate["temporal_thresholds"]
    value = {
        "policy_id": MATCHING_POLICY_ID,
        "policy_version": MATCHING_POLICY_VERSION,
        "policy_status": "PARTIALLY_APPROVED",
        "scope": SCOPE,
        "operational": False,
        "tie_breaker_policy_id": tie_breaker["tie_breaker_policy_id"],
        "tie_breaker_policy_version": tie_breaker["tie_breaker_policy_version"],
        "tie_breaker_strategy": APPROVED_STRATEGY,
        "ordering_rules": list(V2_ORDER),
        "one_to_one_matching": candidate["one_to_one_matching"],
        "positive_overlap_requirement": candidate["positive_overlap_requirement"],
        "matching_keys": list(candidate["matching_keys"]),
        "threshold_status": "DEFERRED",
        "minimum_temporal_iou": thresholds["minimum_temporal_iou"],
        "maximum_onset_difference_ms": thresholds[
            "maximum_onset_difference_ms"
        ],
        "maximum_offset_difference_ms": thresholds[
            "maximum_offset_difference_ms"
        ],
        "approved_by": decision["reviewer_id"],
        "approved_at": decision["reviewed_at"],
        "approval_rationale": decision["rationale"],
        "source_candidate_sha256": candidate_sha256,
        "source_decision_sha256": decision_sha256,
    }
    validate_snapshot(value)
    return value


def validate_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(value, dict), "snapshot must be an object")
    _require(set(value) == SNAPSHOT_FIELDS, "snapshot fields must be exact")
    ensure_finite(value)
    _require(value["policy_id"] == MATCHING_POLICY_ID, "snapshot policy_id mismatch")
    _require(
        value["policy_version"] == MATCHING_POLICY_VERSION,
        "snapshot policy_version mismatch",
    )
    _require(
        value["policy_status"] == "PARTIALLY_APPROVED",
        "snapshot policy status mismatch",
    )
    _require(value["scope"] == SCOPE, "snapshot scope mismatch")
    _require(value["operational"] is False, "snapshot must be nonoperational")
    _require(
        value["tie_breaker_policy_id"] == TIE_BREAKER_POLICY_ID,
        "tie-breaker policy id mismatch",
    )
    _require(
        value["tie_breaker_policy_version"] == TIE_BREAKER_POLICY_VERSION,
        "tie-breaker policy version mismatch",
    )
    _require(
        value["tie_breaker_strategy"] == APPROVED_STRATEGY,
        "snapshot strategy mismatch",
    )
    _require(tuple(value["ordering_rules"]) == V2_ORDER, "V2 ordering changed")
    _require(value["one_to_one_matching"] is True, "one-to-one matching changed")
    _require(
        value["positive_overlap_requirement"] is True,
        "positive-overlap requirement changed",
    )
    _require(
        value["matching_keys"] == ["answer_id", "label_id", "direction"],
        "matching keys changed",
    )
    _require(value["threshold_status"] == "DEFERRED", "threshold status changed")
    _require(
        all(
            value[name] is None
            for name in (
                "minimum_temporal_iou",
                "maximum_onset_difference_ms",
                "maximum_offset_difference_ms",
            )
        ),
        "snapshot thresholds must remain null",
    )
    _require(bool(value["approved_by"]), "approved_by is required")
    _timezone_aware_iso8601(value["approved_at"], "approved_at")
    _require(bool(value["approval_rationale"]), "approval_rationale is required")
    for name in ("source_candidate_sha256", "source_decision_sha256"):
        _require(
            isinstance(value[name], str)
            and len(value[name]) == 64
            and all(char in "0123456789abcdef" for char in value[name]),
            f"{name} must be lowercase SHA-256",
        )
    return dict(value)


def execution_gate() -> dict[str, bool]:
    return {
        "tie_breaker_approved": True,
        "thresholds_approved": False,
        "official_matching_eligible": False,
        "agreement_calculation_eligible": False,
        "kappa_calculation_eligible": False,
    }


def _strict_bytes(value: dict[str, Any]) -> bytes:
    ensure_finite(value)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    return text.replace("\n", os.linesep).encode("utf-8")


def _write_immutable_json(path: Path, value: dict[str, Any], conflict_code: str) -> None:
    expected = _strict_bytes(value)
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise PolicyApprovalError(conflict_code, f"cannot read {path.name}") from exc
        if existing != expected:
            raise PolicyApprovalError(
                conflict_code, f"immutable output differs: {path.name}"
            )
        return
    write_strict_json(path, value)


def build_policy_approval_package(
    revision_dir: str | Path,
    *,
    decision_path: str | Path | None = None,
    rater_annotation_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
    root = Path(revision_dir)
    documents, hashes_before = validate_stage192_inputs(root)
    rater_paths = [Path(path) for path in rater_annotation_paths]
    rater_hashes_before = {str(path): sha256_file(path) for path in rater_paths}

    source_decision_path = (
        Path(decision_path)
        if decision_path is not None
        else root / "agreement_policy_revision_decision.json"
    )
    _require(source_decision_path.is_file(), "governance decision file is missing")
    loaded_decision = load_approved_decision(source_decision_path)
    decision_sha256 = sha256_file(source_decision_path)

    snapshot = _snapshot(
        documents["agreement_policy_candidate_0_2_0.json"],
        loaded_decision,
        hashes_before["agreement_policy_candidate_0_2_0.json"],
        decision_sha256,
    )
    snapshot_path = root / "approved_tie_breaker_policy_snapshot.json"
    _write_immutable_json(snapshot_path, snapshot, SNAPSHOT_CONFLICT)
    loaded_snapshot = validate_snapshot(load_strict_json(snapshot_path))
    _require(loaded_snapshot == snapshot, "approved snapshot validation failed")
    snapshot_sha256 = sha256_file(snapshot_path)

    gate = execution_gate()
    governance_status = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policy_id": MATCHING_POLICY_ID,
        "policy_version": MATCHING_POLICY_VERSION,
        "decision_file_valid": True,
        "approved_tie_breaker_strategy": APPROVED_STRATEGY,
        "threshold_status": "DEFERRED",
        "execution_eligibility": gate,
        "blocking_reasons": list(BLOCKING_REASONS),
        "tie_breaker_policy_status": TIE_BREAKER_STATUS,
        "agreement_policy_status": AGREEMENT_POLICY_STATUS,
        "official_matching_executed": False,
        "agreement_calculated": False,
        "kappa_calculated": False,
    }
    status_path = root / "agreement_policy_governance_status.json"
    _write_immutable_json(
        status_path, governance_status, "GOVERNANCE_STATUS_VERSION_CONFLICT"
    )
    status_sha256 = sha256_file(status_path)

    hashes_after = {
        name: sha256_file(root / name) for name in REQUIRED_STAGE192_INPUTS
    }
    rater_hashes_after = {str(path): sha256_file(path) for path in rater_paths}
    _require(hashes_before == hashes_after, "Stage 19.2 input hash changed")
    _require(rater_hashes_before == rater_hashes_after, "rater input hash changed")

    validation = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "valid": True,
        "tie_breaker_policy_status": TIE_BREAKER_STATUS,
        "agreement_policy_status": AGREEMENT_POLICY_STATUS,
        "checks": {
            "stage192_inputs_valid": True,
            "stage192_hashes_unchanged": True,
            "decision_strictly_valid": True,
            "review_pending_template_unchanged": True,
            "v2_ordering_fixed": True,
            "thresholds_remain_null": True,
            "threshold_decision_deferred": True,
            "snapshot_immutable": True,
            "tie_breaker_and_execution_separated": True,
            "official_matching_executed": False,
            "agreement_calculated": False,
            "kappa_calculated": False,
            "real_rater_annotation_loaded": False,
            "rater_hashes_unchanged": True,
        },
        "execution_eligibility": gate,
        "blocking_reasons": list(BLOCKING_REASONS),
        "protected_stage192_inputs": [
            {
                "name": name,
                "sha256_before": hashes_before[name],
                "sha256_after": hashes_after[name],
            }
            for name in REQUIRED_STAGE192_INPUTS
        ],
        "protected_rater_inputs": [
            {
                "path": path,
                "sha256_before": rater_hashes_before[path],
                "sha256_after": rater_hashes_after[path],
            }
            for path in sorted(rater_hashes_before)
        ],
        "generated_output_sha256": {
            "agreement_policy_revision_decision.json": decision_sha256,
            "approved_tie_breaker_policy_snapshot.json": snapshot_sha256,
            "agreement_policy_governance_status.json": status_sha256,
        },
    }
    report_path = root / "validation_report_stage193.json"
    _write_immutable_json(
        report_path, validation, "VALIDATION_REPORT_VERSION_CONFLICT"
    )
    markdown = (
        "# Stage 19.3 validation report\n\n"
        f"- Tie-breaker policy status: `{TIE_BREAKER_STATUS}`\n"
        f"- Agreement policy status: `{AGREEMENT_POLICY_STATUS}`\n"
        f"- Approved strategy: `{APPROVED_STRATEGY}`\n"
        "- Threshold status: `DEFERRED`\n"
        "- Official matching eligible/executed: `false` / `false`\n"
        "- Agreement calculated: `false`\n"
        "- Cohen's kappa calculated: `false`\n"
        "- Real Rater Annotation loaded: `false`\n"
    )
    markdown_path = root / "validation_report_stage193.md"
    if markdown_path.exists():
        if markdown_path.read_text(encoding="utf-8") != markdown:
            raise PolicyApprovalError(
                "VALIDATION_REPORT_VERSION_CONFLICT",
                "immutable output differs: validation_report_stage193.md",
            )
    else:
        markdown_path.write_text(markdown, encoding="utf-8")

    missing = [name for name in NEW_OUTPUTS if not (root / name).is_file()]
    _require(not missing, f"required Stage 19.3 outputs missing: {missing}")
    ensure_finite(validation)
    return validation
