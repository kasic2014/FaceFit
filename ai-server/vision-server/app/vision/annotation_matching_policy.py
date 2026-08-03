"""Stage 19.1 governance contract for Annotation Agreement matching."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.vision.pilot_video_intake import (
    ensure_finite,
    load_strict_json,
    sha256_file,
)


SCHEMA_VERSION = "1.0.0"
STAGE = "19.1"
PARTICIPANT_ID = "PTC_000001"
SESSION_ID = "SES_000001"
DEFAULT_POLICY_ID = "ANNOTATION_AGREEMENT_MATCHING_001"
DEFAULT_POLICY_VERSION = "0.1.0"
DEFAULT_SCOPE = "PILOT_DEVELOPMENT_ONLY"
SOURCE_TYPE = "PROJECT_GOVERNANCE_CANDIDATE"

POLICY_STATUSES = frozenset(
    {"DRAFT", "REVIEW_REQUIRED", "APPROVED", "REJECTED", "RETIRED"}
)
POLICY_SCOPES = frozenset(
    {"PILOT_DEVELOPMENT_ONLY", "RESEARCH_VALIDATION", "PRODUCTION"}
)
DECISIONS = frozenset(
    {"REVIEW_PENDING", "APPROVED", "REJECTED", "REVISION_REQUIRED"}
)
MATCHING_KEYS = ("answer_id", "label_id", "direction")
CANDIDATE_TIE_BREAKER = (
    "TEMPORAL_IOU_DESC",
    "OVERLAP_DURATION_MS_DESC",
    "ONSET_DIFFERENCE_MS_ASC",
    "OFFSET_DIFFERENCE_MS_ASC",
    "EVENT_ID_LEXICAL_ASC",
)
STAGE13_TIE_BREAKER = (
    "TEMPORAL_IOU_DESC",
    "SORTED_RATER_B_INDEX_ASC",
)

AWAITING_STATUS = "awaiting_agreement_policy_decision"
REVISION_STATUS = "agreement_policy_revision_required"
REJECTED_STATUS = "agreement_policy_rejected"
APPROVED_STATUS = "agreement_policy_approved"
VALIDATION_FAILED_STATUS = "agreement_policy_validation_failed"

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
POLICY_FIELDS = frozenset(
    {
        "policy_id",
        "policy_version",
        "policy_status",
        "operational",
        "source_type",
        "scope",
        "rubric_id",
        "rubric_version",
        "matching_keys",
        "minimum_temporal_iou",
        "maximum_onset_difference_ms",
        "maximum_offset_difference_ms",
        "require_positive_overlap",
        "one_to_one_matching",
        "tie_breaker_order",
        "effective_from",
        "approved_by",
        "approved_at",
        "rationale",
    }
)
DECISION_FIELDS = frozenset(
    {
        "policy_id",
        "policy_version",
        "reviewer_id",
        "decision",
        "scope",
        "selected_minimum_temporal_iou",
        "selected_maximum_onset_difference_ms",
        "selected_maximum_offset_difference_ms",
        "reviewed_at",
        "rationale",
    }
)
OUTPUT_NAMES = (
    "agreement_policy_candidates.json",
    "agreement_policy_review_packet.json",
    "agreement_policy_decision.template.json",
    "agreement_policy_status.json",
    "validation_report.json",
    "validation_report.md",
)


class AgreementPolicyError(ValueError):
    """Raised when a policy or human decision violates the contract."""


def _require_exact_fields(
    value: dict[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise AgreementPolicyError(
            f"{context} fields must be exact; missing={missing}, extra={extra}"
        )


def _require_semver(value: Any, context: str) -> str:
    if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
        raise AgreementPolicyError(f"{context} must be valid Semantic Version")
    return value


def _require_iso8601(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgreementPolicyError(f"{context} must be an ISO 8601 timestamp")
    candidate = value.strip()
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgreementPolicyError(
            f"{context} must be an ISO 8601 timestamp"
        ) from exc
    return candidate


def _optional_iou(value: Any, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgreementPolicyError(f"{context} must be a finite number or null")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise AgreementPolicyError(f"{context} must be within [0, 1]")
    return result


def _optional_millisecond_limit(value: Any, context: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgreementPolicyError(
            f"{context} must be a non-negative integer millisecond or null"
        )
    if value < 0:
        raise AgreementPolicyError(f"{context} must not be negative")
    return value


def _optional_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AgreementPolicyError(f"{context} must be non-empty text or null")
    return value.strip()


@dataclass(frozen=True)
class MatchingPolicy:
    policy_id: str
    policy_version: str
    policy_status: str
    operational: bool
    source_type: str
    scope: str
    rubric_id: str
    rubric_version: str
    matching_keys: tuple[str, ...]
    minimum_temporal_iou: float | None
    maximum_onset_difference_ms: int | None
    maximum_offset_difference_ms: int | None
    require_positive_overlap: bool
    one_to_one_matching: bool
    tie_breaker_order: tuple[str, ...]
    effective_from: str | None
    approved_by: str | None
    approved_at: str | None
    rationale: str | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MatchingPolicy":
        if not isinstance(value, dict):
            raise AgreementPolicyError("policy must be an object")
        _require_exact_fields(value, POLICY_FIELDS, "policy")
        ensure_finite(value)

        policy_id = _optional_text(value["policy_id"], "policy_id")
        if policy_id is None:
            raise AgreementPolicyError("policy_id is required")
        policy_version = _require_semver(
            value["policy_version"], "policy_version"
        )
        policy_status = value["policy_status"]
        if policy_status not in POLICY_STATUSES:
            raise AgreementPolicyError("policy_status is not allowed")
        if not isinstance(value["operational"], bool):
            raise AgreementPolicyError("operational must be boolean")
        if value["source_type"] != SOURCE_TYPE:
            raise AgreementPolicyError("source_type is not allowed")
        if value["scope"] not in POLICY_SCOPES:
            raise AgreementPolicyError("scope is not allowed")
        if (
            not isinstance(value["rubric_id"], str)
            or not value["rubric_id"].strip()
        ):
            raise AgreementPolicyError("rubric_id is required")
        rubric_version = _require_semver(
            value["rubric_version"], "rubric_version"
        )

        matching_keys = value["matching_keys"]
        if (
            not isinstance(matching_keys, list)
            or tuple(matching_keys) != MATCHING_KEYS
        ):
            raise AgreementPolicyError(
                "matching_keys must be answer_id, label_id, direction"
            )
        tie_breaker = value["tie_breaker_order"]
        if (
            not isinstance(tie_breaker, list)
            or tuple(tie_breaker) != CANDIDATE_TIE_BREAKER
        ):
            raise AgreementPolicyError(
                "tie_breaker_order must match the deterministic candidate order"
            )
        if value["require_positive_overlap"] is not True:
            raise AgreementPolicyError("require_positive_overlap must be true")
        if value["one_to_one_matching"] is not True:
            raise AgreementPolicyError("one_to_one_matching must be true")

        minimum_iou = _optional_iou(
            value["minimum_temporal_iou"],
            "minimum_temporal_iou",
        )
        maximum_onset = _optional_millisecond_limit(
            value["maximum_onset_difference_ms"],
            "maximum_onset_difference_ms",
        )
        maximum_offset = _optional_millisecond_limit(
            value["maximum_offset_difference_ms"],
            "maximum_offset_difference_ms",
        )
        effective_from = value["effective_from"]
        if effective_from is not None:
            effective_from = _require_iso8601(
                effective_from, "effective_from"
            )
        approved_at = value["approved_at"]
        if approved_at is not None:
            approved_at = _require_iso8601(approved_at, "approved_at")
        approved_by = _optional_text(value["approved_by"], "approved_by")
        rationale = _optional_text(value["rationale"], "rationale")

        if policy_status == "REVIEW_REQUIRED":
            if value["operational"]:
                raise AgreementPolicyError(
                    "REVIEW_REQUIRED policy cannot be operational"
                )
            if any(
                item is not None
                for item in (minimum_iou, maximum_onset, maximum_offset)
            ):
                raise AgreementPolicyError(
                    "REVIEW_REQUIRED candidate thresholds must remain null"
                )
        if policy_status == "APPROVED":
            if not value["operational"]:
                raise AgreementPolicyError(
                    "APPROVED policy must be operational"
                )
            if any(
                item is None
                for item in (minimum_iou, maximum_onset, maximum_offset)
            ):
                raise AgreementPolicyError(
                    "APPROVED policy requires all matching thresholds"
                )
            if approved_by is None or approved_at is None:
                raise AgreementPolicyError(
                    "APPROVED policy requires approved_by and approved_at"
                )

        return cls(
            policy_id=policy_id,
            policy_version=policy_version,
            policy_status=policy_status,
            operational=value["operational"],
            source_type=value["source_type"],
            scope=value["scope"],
            rubric_id=value["rubric_id"].strip(),
            rubric_version=rubric_version,
            matching_keys=tuple(matching_keys),
            minimum_temporal_iou=minimum_iou,
            maximum_onset_difference_ms=maximum_onset,
            maximum_offset_difference_ms=maximum_offset,
            require_positive_overlap=True,
            one_to_one_matching=True,
            tie_breaker_order=tuple(tie_breaker),
            effective_from=effective_from,
            approved_by=approved_by,
            approved_at=approved_at,
            rationale=rationale,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["matching_keys"] = list(self.matching_keys)
        value["tie_breaker_order"] = list(self.tie_breaker_order)
        ensure_finite(value)
        return value

    def require_operational(self) -> None:
        if self.policy_status != "APPROVED" or not self.operational:
            raise AgreementPolicyError(
                "unapproved matching policy cannot be used operationally"
            )
        if any(
            item is None
            for item in (
                self.minimum_temporal_iou,
                self.maximum_onset_difference_ms,
                self.maximum_offset_difference_ms,
            )
        ):
            raise AgreementPolicyError(
                "operational matching policy requires all thresholds"
            )


def policy_candidate(
    *,
    rubric_id: str,
    rubric_version: str,
) -> MatchingPolicy:
    """Create one non-operational candidate without deriving thresholds."""

    return MatchingPolicy.from_dict(
        {
            "policy_id": DEFAULT_POLICY_ID,
            "policy_version": DEFAULT_POLICY_VERSION,
            "policy_status": "REVIEW_REQUIRED",
            "operational": False,
            "source_type": SOURCE_TYPE,
            "scope": DEFAULT_SCOPE,
            "rubric_id": rubric_id,
            "rubric_version": rubric_version,
            "matching_keys": list(MATCHING_KEYS),
            "minimum_temporal_iou": None,
            "maximum_onset_difference_ms": None,
            "maximum_offset_difference_ms": None,
            "require_positive_overlap": True,
            "one_to_one_matching": True,
            "tie_breaker_order": list(CANDIDATE_TIE_BREAKER),
            "effective_from": None,
            "approved_by": None,
            "approved_at": None,
            "rationale": (
                "No approved Stage 12/13 or project-governance source defines "
                "operational matching thresholds. Values remain null pending "
                "independent human policy review."
            ),
        }
    )


def decision_template() -> dict[str, Any]:
    return {
        "policy_id": None,
        "policy_version": None,
        "reviewer_id": None,
        "decision": "REVIEW_PENDING",
        "scope": DEFAULT_SCOPE,
        "selected_minimum_temporal_iou": None,
        "selected_maximum_onset_difference_ms": None,
        "selected_maximum_offset_difference_ms": None,
        "reviewed_at": None,
        "rationale": None,
    }


def validate_decision(
    value: dict[str, Any],
    candidate: MatchingPolicy,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgreementPolicyError("decision must be an object")
    _require_exact_fields(value, DECISION_FIELDS, "decision")
    ensure_finite(value)
    decision = value["decision"]
    if decision not in DECISIONS:
        raise AgreementPolicyError("decision is not allowed")
    if value["scope"] != candidate.scope:
        raise AgreementPolicyError("decision scope does not match policy scope")

    minimum_iou = _optional_iou(
        value["selected_minimum_temporal_iou"],
        "selected_minimum_temporal_iou",
    )
    maximum_onset = _optional_millisecond_limit(
        value["selected_maximum_onset_difference_ms"],
        "selected_maximum_onset_difference_ms",
    )
    maximum_offset = _optional_millisecond_limit(
        value["selected_maximum_offset_difference_ms"],
        "selected_maximum_offset_difference_ms",
    )

    if decision == "REVIEW_PENDING":
        if value["policy_id"] not in (None, candidate.policy_id):
            raise AgreementPolicyError("policy_id does not match candidate")
        if value["policy_version"] not in (None, candidate.policy_version):
            raise AgreementPolicyError("policy_version does not match candidate")
        if value["policy_version"] is not None:
            _require_semver(value["policy_version"], "policy_version")
        reviewer_id = _optional_text(value["reviewer_id"], "reviewer_id")
        reviewed_at = value["reviewed_at"]
        if reviewed_at is not None:
            reviewed_at = _require_iso8601(reviewed_at, "reviewed_at")
    else:
        if value["policy_id"] != candidate.policy_id:
            raise AgreementPolicyError("policy_id does not match candidate")
        policy_version = _require_semver(
            value["policy_version"], "policy_version"
        )
        if policy_version != candidate.policy_version:
            raise AgreementPolicyError("policy_version does not match candidate")
        reviewer_id = _optional_text(value["reviewer_id"], "reviewer_id")
        if reviewer_id is None:
            raise AgreementPolicyError("reviewer_id is required")
        reviewed_at = _require_iso8601(value["reviewed_at"], "reviewed_at")

    if decision == "APPROVED" and any(
        item is None
        for item in (minimum_iou, maximum_onset, maximum_offset)
    ):
        raise AgreementPolicyError(
            "APPROVED decision requires all selected matching thresholds"
        )

    return {
        **value,
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at,
        "selected_minimum_temporal_iou": minimum_iou,
        "selected_maximum_onset_difference_ms": maximum_onset,
        "selected_maximum_offset_difference_ms": maximum_offset,
        "rationale": _optional_text(value["rationale"], "rationale"),
    }


def decision_status(decision: str) -> str:
    return {
        "REVIEW_PENDING": AWAITING_STATUS,
        "REVISION_REQUIRED": REVISION_STATUS,
        "REJECTED": REJECTED_STATUS,
        "APPROVED": APPROVED_STATUS,
    }[decision]


def approved_snapshot(
    candidate: MatchingPolicy,
    decision: dict[str, Any],
) -> MatchingPolicy:
    if decision["decision"] != "APPROVED":
        raise AgreementPolicyError(
            "approved snapshot requires an APPROVED decision"
        )
    return MatchingPolicy.from_dict(
        {
            **candidate.to_dict(),
            "policy_status": "APPROVED",
            "operational": True,
            "minimum_temporal_iou": (
                decision["selected_minimum_temporal_iou"]
            ),
            "maximum_onset_difference_ms": (
                decision["selected_maximum_onset_difference_ms"]
            ),
            "maximum_offset_difference_ms": (
                decision["selected_maximum_offset_difference_ms"]
            ),
            "effective_from": decision["reviewed_at"],
            "approved_by": decision["reviewer_id"],
            "approved_at": decision["reviewed_at"],
            "rationale": decision["rationale"],
        }
    )


def rank_candidates_deterministically(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank hypothetical pairs only; this function never selects a match."""

    values = [dict(item) for item in candidates]
    for item in values:
        ensure_finite(item)
        for key in (
            "temporal_iou",
            "overlap_duration_ms",
            "onset_difference_ms",
            "offset_difference_ms",
            "rater_a_event_id",
            "rater_b_event_id",
        ):
            if key not in item:
                raise AgreementPolicyError(
                    f"tie-breaker candidate missing {key}"
                )
    return sorted(
        values,
        key=lambda item: (
            -float(item["temporal_iou"]),
            -int(item["overlap_duration_ms"]),
            int(item["onset_difference_ms"]),
            int(item["offset_difference_ms"]),
            str(item["rater_a_event_id"]),
            str(item["rater_b_event_id"]),
        ),
    )


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    ensure_finite(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        if load_strict_json(path) != value:
            raise AgreementPolicyError(
                f"immutable policy artifact differs: {path.name}"
            )
        return
    _write_json_atomic(path, value)


def _load_stage19_context(stage19_dir: Path) -> dict[str, Any]:
    required = (
        "input_validation.json",
        "agreement_policy_snapshot.json",
        "agreement_summary.json",
        "event_match_results.jsonl",
        "validation_report.json",
    )
    missing = [name for name in required if not (stage19_dir / name).is_file()]
    if missing:
        raise AgreementPolicyError(
            f"Stage 19 artifacts are missing: {missing}"
        )
    input_validation = load_strict_json(
        stage19_dir / "input_validation.json"
    )
    source_policy = load_strict_json(
        stage19_dir / "agreement_policy_snapshot.json"
    )
    summary = load_strict_json(stage19_dir / "agreement_summary.json")
    stage19_report = load_strict_json(
        stage19_dir / "validation_report.json"
    )
    pairwise: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        (stage19_dir / "event_match_results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines(),
        start=1,
    ):
        try:
            value = json.loads(
                line,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    AgreementPolicyError(
                        f"non-finite JSONL value at line {line_number}: {item}"
                    )
                ),
            )
        except json.JSONDecodeError as exc:
            raise AgreementPolicyError(
                f"invalid Stage 19 JSONL at line {line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise AgreementPolicyError(
                f"Stage 19 JSONL line {line_number} must be an object"
            )
        ensure_finite(value)
        pairwise.append(value)

    if not input_validation.get("all_inputs_valid"):
        raise AgreementPolicyError("Stage 19 input validation did not pass")
    if source_policy.get("approval_cutoff_defined") is not False:
        raise AgreementPolicyError(
            "Stage 19 policy snapshot does not record an undefined cutoff"
        )
    if source_policy.get("matching_policy_approved") is not False:
        raise AgreementPolicyError(
            "Stage 19 unexpectedly records an approved matching policy"
        )
    if summary.get("terminal_status") != "agreement_policy_review_required":
        raise AgreementPolicyError("Stage 19 is not awaiting policy review")
    if stage19_report.get("agreement_calculated") is not False:
        raise AgreementPolicyError("Stage 19 agreement was already calculated")
    if any(item.get("selected_as_match") is not False for item in pairwise):
        raise AgreementPolicyError(
            "Stage 19 pairwise input contains a selected match"
        )

    return {
        "input_validation": input_validation,
        "source_policy": source_policy,
        "summary": summary,
        "report": stage19_report,
        "pairwise": pairwise,
        "hashes": {
            name: sha256_file(stage19_dir / name) for name in required
        },
    }


def _review_packet(
    candidate: MatchingPolicy,
    context: dict[str, Any],
) -> dict[str, Any]:
    summary = context["summary"]
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "agreement_context": summary["agreement_context"],
        "source_stage19_status": summary["terminal_status"],
        "source_artifact_sha256": context["hashes"],
        "stage13_contract_review": {
            "matching_keys_aligned": True,
            "positive_overlap_rule_aligned": True,
            "one_to_one_matching_aligned": True,
            "stage13_tie_breaker_order": list(STAGE13_TIE_BREAKER),
            "candidate_tie_breaker_order": list(CANDIDATE_TIE_BREAKER),
            "tie_breaker_contract_aligned": False,
            "conflict_code": "TIE_BREAKER_CONTRACT_REVIEW_REQUIRED",
            "candidate_rule_applied": False,
        },
        "raw_pairwise_context": {
            "rater_a_event_count": summary["rater_a_event_count"],
            "rater_b_event_count": summary["rater_b_event_count"],
            "pairwise_candidate_count": summary["pairwise_candidate_count"],
            "candidates": context["pairwise"],
        },
        "threshold_evidence": {
            "approved_source_found": False,
            "thresholds_derived_from_current_raters": False,
            "kappa_optimization_performed": False,
            "single_session_optimization_performed": False,
            "candidate_thresholds": {
                "minimum_temporal_iou": None,
                "maximum_onset_difference_ms": None,
                "maximum_offset_difference_ms": None,
            },
            "review_reason": (
                "No approved Stage 12/13 or project-governance threshold "
                "source was found."
            ),
        },
        "policy_candidate": candidate.to_dict(),
        "human_action_required": True,
        "agreement_recalculated": False,
        "kappa_recalculated": False,
        "automatic_approval_performed": False,
    }


def _validation_report_markdown(report: dict[str, Any]) -> str:
    return (
        "# Stage 19.1 Annotation Agreement Matching Policy\n\n"
        f"- Policy candidate count: `{report['policy_candidate_count']}`\n"
        f"- Threshold evidence found: "
        f"`{str(report['threshold_evidence_found']).lower()}`\n"
        f"- Decision file present: "
        f"`{str(report['decision_file_present']).lower()}`\n"
        f"- Policy operational: "
        f"`{str(report['policy_operational']).lower()}`\n"
        f"- Agreement recalculated: "
        f"`{str(report['agreement_recalculated']).lower()}`\n"
        f"- Current status: `{report['current_status']}`\n\n"
        "The Stage 13 tie-breaker differs from the proposed governance "
        "candidate order. The candidate is not operational and all matching "
        "thresholds remain null until a valid human decision is supplied.\n"
    )


def build_policy_review_package(
    *,
    stage19_dir: str | Path,
    output_dir: str | Path,
    decision_path: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(stage19_dir).resolve()
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    actual_decision = (
        Path(decision_path).resolve()
        if decision_path is not None
        else destination / "agreement_policy_decision.json"
    )
    context = _load_stage19_context(source)
    input_validation = context["input_validation"]
    candidate = policy_candidate(
        rubric_id=input_validation["rubric_id"],
        rubric_version=input_validation["rubric_version"],
    )
    candidates_payload = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "candidate_count": 1,
        "source_type": SOURCE_TYPE,
        "automatic_candidate_selection_performed": False,
        "thresholds_derived_from_current_raters": False,
        "candidates": [candidate.to_dict()],
    }
    review_packet = _review_packet(candidate, context)
    template = decision_template()

    _write_immutable_json(
        destination / "agreement_policy_candidates.json",
        candidates_payload,
    )
    _write_immutable_json(
        destination / "agreement_policy_review_packet.json",
        review_packet,
    )
    _write_immutable_json(
        destination / "agreement_policy_decision.template.json",
        template,
    )

    errors: list[str] = []
    decision_present = actual_decision.is_file()
    validated_decision: dict[str, Any] | None = None
    current_status = AWAITING_STATUS
    snapshot_created = False
    policy_operational = False
    if decision_present:
        try:
            validated_decision = validate_decision(
                load_strict_json(actual_decision),
                candidate,
            )
            current_status = decision_status(validated_decision["decision"])
            if current_status == APPROVED_STATUS:
                snapshot_path = (
                    destination / "approved_agreement_policy_snapshot.json"
                )
                if snapshot_path.exists():
                    raise AgreementPolicyError(
                        "approved policy snapshot already exists; refusing "
                        "same-version overwrite"
                    )
                snapshot = approved_snapshot(
                    candidate,
                    validated_decision,
                )
                _write_immutable_json(snapshot_path, snapshot.to_dict())
                snapshot_created = True
                policy_operational = True
        except (OSError, KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
            current_status = VALIDATION_FAILED_STATUS

    effective_policy_status = {
        APPROVED_STATUS: "APPROVED",
        REJECTED_STATUS: "REJECTED",
    }.get(current_status, candidate.policy_status)
    status_payload = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "policy_id": candidate.policy_id,
        "policy_version": candidate.policy_version,
        "policy_status": effective_policy_status,
        "scope": candidate.scope,
        "decision_file_present": decision_present,
        "decision": (
            validated_decision["decision"]
            if validated_decision is not None
            else None
        ),
        "policy_operational": policy_operational,
        "approved_snapshot_created": snapshot_created,
        "agreement_recalculated": False,
        "kappa_recalculated": False,
        "current_status": current_status,
    }
    report = {
        **status_payload,
        "policy_candidate_count": 1,
        "threshold_evidence_found": False,
        "candidate_thresholds": {
            "minimum_temporal_iou": None,
            "maximum_onset_difference_ms": None,
            "maximum_offset_difference_ms": None,
        },
        "stage13_tie_breaker_conflict": True,
        "automatic_threshold_selection_performed": False,
        "automatic_approval_performed": False,
        "rater_annotations_modified": False,
        "stage19_outputs_modified": False,
        "scoring_performed": False,
        "ml_training_performed": False,
        "dataset_frozen": False,
        "dependency_changed": False,
        "errors": errors,
        "outputs": list(OUTPUT_NAMES)
        + (
            ["approved_agreement_policy_snapshot.json"]
            if snapshot_created
            else []
        ),
    }
    _write_json_atomic(
        destination / "agreement_policy_status.json",
        status_payload,
    )
    _write_json_atomic(destination / "validation_report.json", report)
    _write_text_atomic(
        destination / "validation_report.md",
        _validation_report_markdown(report),
    )
    return report
