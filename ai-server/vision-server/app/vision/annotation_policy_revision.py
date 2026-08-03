"""Stage 19.2 governance review for Annotation Agreement tie-breakers.

This module compares strategies with synthetic fixtures only. It deliberately
does not load or match real rater events and does not calculate agreement.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.vision.annotation_agreement import temporal_iou
from app.vision.pilot_video_intake import (
    ensure_finite,
    load_strict_json,
    sha256_file,
    write_strict_json,
)


SCHEMA_VERSION = "1.0.0"
STAGE = "19.2"
PARTICIPANT_ID = "PTC_000001"
SESSION_ID = "SES_000001"
MATCHING_POLICY_ID = "ANNOTATION_AGREEMENT_MATCHING_001"
MATCHING_POLICY_VERSION = "0.2.0"
TIE_BREAKER_POLICY_ID = "ANNOTATION_AGREEMENT_TIE_BREAKER_001"
TIE_BREAKER_POLICY_VERSION = "0.2.0"
SCOPE = "PILOT_DEVELOPMENT_ONLY"

STRATEGIES = frozenset(
    {"LEGACY_STAGE13", "DETERMINISTIC_MULTI_CRITERIA_V2", "UNRESOLVED"}
)
POLICY_STATUSES = frozenset(
    {"DRAFT", "REVIEW_REQUIRED", "APPROVED", "REJECTED", "RETIRED"}
)
DECISIONS = frozenset(
    {
        "REVIEW_PENDING",
        "APPROVE_LEGACY_STAGE13",
        "APPROVE_DETERMINISTIC_MULTI_CRITERIA_V2",
        "REVISION_REQUIRED",
        "REJECTED",
    }
)
THRESHOLD_DECISIONS = frozenset({"DEFERRED", "REVISION_REQUIRED", "REJECTED"})
LEGACY_ORDER = ("TEMPORAL_IOU_DESC", "SORTED_RATER_B_INDEX_ASC")
V2_ORDER = (
    "TEMPORAL_IOU_DESC",
    "OVERLAP_DURATION_MS_DESC",
    "ONSET_DIFFERENCE_MS_ASC",
    "OFFSET_DIFFERENCE_MS_ASC",
    "EVENT_ID_LEXICAL_ASC",
)
AWAITING_STATUS = "awaiting_agreement_policy_governance_decision"
APPROVED_STATUS = "tie_breaker_policy_approved"
REVISION_STATUS = "agreement_policy_revision_required"
REJECTED_STATUS = "agreement_policy_rejected"
VALIDATION_FAILED_STATUS = "agreement_policy_validation_failed"

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
TIE_POLICY_FIELDS = frozenset(
    {
        "tie_breaker_policy_id",
        "tie_breaker_policy_version",
        "status",
        "scope",
        "strategy",
        "ordering_rules",
        "legacy_compatibility",
        "operational",
        "approved_by",
        "approved_at",
        "rationale",
    }
)
DECISION_FIELDS = frozenset(
    {
        "policy_id",
        "candidate_version",
        "reviewer_id",
        "decision",
        "selected_tie_breaker_strategy",
        "threshold_decision",
        "scope",
        "reviewed_at",
        "rationale",
    }
)
OUTPUT_NAMES = (
    "stage13_tie_breaker_analysis.json",
    "tie_breaker_strategy_comparison.json",
    "agreement_policy_candidate_0_2_0.json",
    "agreement_policy_revision_review_packet.json",
    "agreement_policy_revision_decision.template.json",
    "compatibility_fixture_results.json",
    "agreement_policy_revision_status.json",
    "validation_report.json",
    "validation_report.md",
)


class PolicyRevisionError(ValueError):
    """Raised when the Stage 19.2 governance contract is violated."""


def _exact_fields(value: dict[str, Any], expected: frozenset[str], name: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise PolicyRevisionError(
            f"{name} fields must be exact; missing={missing}, extra={extra}"
        )


def _text(value: Any, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise PolicyRevisionError(f"{name} must be non-empty text")
    return value.strip()


def _semver(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
        raise PolicyRevisionError(f"{name} must be valid Semantic Version")
    return value


def _iso8601(value: Any, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    result = _text(value, name)
    assert result is not None
    try:
        datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PolicyRevisionError(f"{name} must be ISO 8601") from exc
    return result


@dataclass(frozen=True)
class TieBreakerPolicy:
    tie_breaker_policy_id: str
    tie_breaker_policy_version: str
    status: str
    scope: str
    strategy: str
    ordering_rules: tuple[str, ...]
    legacy_compatibility: str
    operational: bool
    approved_by: str | None
    approved_at: str | None
    rationale: str | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TieBreakerPolicy":
        if not isinstance(value, dict):
            raise PolicyRevisionError("tie-breaker policy must be an object")
        _exact_fields(value, TIE_POLICY_FIELDS, "tie-breaker policy")
        ensure_finite(value)
        policy_id = _text(value["tie_breaker_policy_id"], "tie_breaker_policy_id")
        version = _semver(
            value["tie_breaker_policy_version"], "tie_breaker_policy_version"
        )
        if policy_id != TIE_BREAKER_POLICY_ID:
            raise PolicyRevisionError("tie_breaker_policy_id does not match")
        if version != TIE_BREAKER_POLICY_VERSION:
            raise PolicyRevisionError("tie_breaker_policy_version does not match")
        status = value["status"]
        strategy = value["strategy"]
        if status not in POLICY_STATUSES:
            raise PolicyRevisionError("status is not allowed")
        if strategy not in STRATEGIES:
            raise PolicyRevisionError("strategy is not allowed")
        if value["scope"] != SCOPE:
            raise PolicyRevisionError("scope is not allowed")
        if not isinstance(value["ordering_rules"], list) or not all(
            isinstance(item, str) and item for item in value["ordering_rules"]
        ):
            raise PolicyRevisionError("ordering_rules must be a text array")
        expected_order = {
            "LEGACY_STAGE13": LEGACY_ORDER,
            "DETERMINISTIC_MULTI_CRITERIA_V2": V2_ORDER,
            "UNRESOLVED": (),
        }[strategy]
        if tuple(value["ordering_rules"]) != expected_order:
            raise PolicyRevisionError("ordering_rules do not match strategy")
        if not isinstance(value["operational"], bool):
            raise PolicyRevisionError("operational must be boolean")
        approved_by = _text(value["approved_by"], "approved_by", optional=True)
        approved_at = _iso8601(value["approved_at"], "approved_at", optional=True)
        if status == "APPROVED":
            if strategy == "UNRESOLVED" or not value["operational"]:
                raise PolicyRevisionError("approved policy must be operational and resolved")
            if approved_by is None or approved_at is None:
                raise PolicyRevisionError("approved policy requires approval metadata")
        elif value["operational"]:
            raise PolicyRevisionError("non-approved policy cannot be operational")
        return cls(
            policy_id or "",
            version,
            status,
            SCOPE,
            strategy,
            expected_order,
            _text(value["legacy_compatibility"], "legacy_compatibility") or "",
            value["operational"],
            approved_by,
            approved_at,
            _text(value["rationale"], "rationale", optional=True),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["ordering_rules"] = list(self.ordering_rules)
        return value


def unresolved_tie_breaker_policy() -> TieBreakerPolicy:
    return TieBreakerPolicy.from_dict(
        {
            "tie_breaker_policy_id": TIE_BREAKER_POLICY_ID,
            "tie_breaker_policy_version": TIE_BREAKER_POLICY_VERSION,
            "status": "REVIEW_REQUIRED",
            "scope": SCOPE,
            "strategy": "UNRESOLVED",
            "ordering_rules": [],
            "legacy_compatibility": (
                "Unresolved. LEGACY_STAGE13 preserves prior tie results; V2 can "
                "change equal-IoU selections."
            ),
            "operational": False,
            "approved_by": None,
            "approved_at": None,
            "rationale": (
                "Stage 13 and Stage 19.1 define different equal-IoU behavior. "
                "Independent human governance review is required."
            ),
        }
    )


def decision_template() -> dict[str, Any]:
    return {
        "policy_id": MATCHING_POLICY_ID,
        "candidate_version": MATCHING_POLICY_VERSION,
        "reviewer_id": None,
        "decision": "REVIEW_PENDING",
        "selected_tie_breaker_strategy": None,
        "threshold_decision": "DEFERRED",
        "scope": SCOPE,
        "reviewed_at": None,
        "rationale": None,
    }


def validate_decision(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyRevisionError("decision must be an object")
    _exact_fields(value, DECISION_FIELDS, "decision")
    ensure_finite(value)
    if value["policy_id"] != MATCHING_POLICY_ID:
        raise PolicyRevisionError("policy_id does not match")
    if _semver(value["candidate_version"], "candidate_version") != MATCHING_POLICY_VERSION:
        raise PolicyRevisionError("candidate_version does not match")
    if value["scope"] != SCOPE:
        raise PolicyRevisionError("scope does not match")
    decision = value["decision"]
    if decision not in DECISIONS:
        raise PolicyRevisionError("decision is not allowed")
    if value["threshold_decision"] not in THRESHOLD_DECISIONS:
        raise PolicyRevisionError("threshold_decision is not allowed")
    if value["threshold_decision"] != "DEFERRED" and decision.startswith("APPROVE_"):
        raise PolicyRevisionError("tie-breaker approval cannot approve thresholds")
    expected_strategy = {
        "APPROVE_LEGACY_STAGE13": "LEGACY_STAGE13",
        "APPROVE_DETERMINISTIC_MULTI_CRITERIA_V2": (
            "DETERMINISTIC_MULTI_CRITERIA_V2"
        ),
    }.get(decision)
    selected = value["selected_tie_breaker_strategy"]
    if decision == "REVIEW_PENDING":
        if selected is not None:
            raise PolicyRevisionError("pending decision cannot select a strategy")
    elif expected_strategy is not None:
        if selected != expected_strategy:
            raise PolicyRevisionError("selected strategy does not match approval")
    elif selected is not None:
        raise PolicyRevisionError("non-approval decision cannot select a strategy")
    if decision != "REVIEW_PENDING":
        _text(value["reviewer_id"], "reviewer_id")
        _iso8601(value["reviewed_at"], "reviewed_at")
        _text(value["rationale"], "rationale")
    else:
        if value["reviewer_id"] is not None or value["reviewed_at"] is not None:
            raise PolicyRevisionError("pending decision cannot contain review metadata")
    return dict(value)


def load_decision(path: str | Path) -> dict[str, Any]:
    return validate_decision(load_strict_json(path))


def _event_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["answer_id"],
        event["label_id"],
        event["start_timestamp_ms"],
        event["event_id"],
    )


def _pair_metrics(a_event: dict[str, Any], b_event: dict[str, Any]) -> dict[str, Any]:
    start_a = a_event["start_timestamp_ms"]
    end_a = a_event["end_timestamp_ms"]
    start_b = b_event["start_timestamp_ms"]
    end_b = b_event["end_timestamp_ms"]
    overlap = max(0, min(end_a, end_b) - max(start_a, start_b))
    union = max(end_a, end_b) - min(start_a, start_b)
    return {
        "temporal_iou": temporal_iou(start_a, end_a, start_b, end_b),
        "overlap_duration_ms": overlap,
        "onset_difference_ms": abs(start_a - start_b),
        "offset_difference_ms": abs(end_a - end_b),
    }


def _same_candidate_group(a_event: dict[str, Any], b_event: dict[str, Any]) -> bool:
    return (
        a_event["answer_id"],
        a_event["label_id"],
        a_event.get("direction"),
    ) == (
        b_event["answer_id"],
        b_event["label_id"],
        b_event.get("direction"),
    )


def match_fixture_events(
    rater_a_events: Iterable[dict[str, Any]],
    rater_b_events: Iterable[dict[str, Any]],
    strategy: str,
) -> list[dict[str, Any]]:
    """Greedy one-to-one fixture matcher; never accepts real annotation files."""
    if strategy not in STRATEGIES - {"UNRESOLVED"}:
        raise PolicyRevisionError("a resolved fixture strategy is required")
    a_events = sorted((dict(item) for item in rater_a_events), key=_event_key)
    b_events = sorted((dict(item) for item in rater_b_events), key=_event_key)
    for event in (*a_events, *b_events):
        if not str(event.get("answer_id", "")).startswith("ANS_FIXTURE"):
            raise PolicyRevisionError("fixture matcher rejects non-fixture answer_id")
        if not str(event.get("label_id", "")).startswith("LBL_FIXTURE"):
            raise PolicyRevisionError("fixture matcher rejects non-fixture label_id")
    unused_b = set(range(len(b_events)))
    matches: list[dict[str, Any]] = []
    for a_event in a_events:
        candidates: list[tuple[int, dict[str, Any]]] = []
        for index in sorted(unused_b):
            b_event = b_events[index]
            if _same_candidate_group(a_event, b_event):
                candidates.append((index, _pair_metrics(a_event, b_event)))
        if not candidates:
            matches.append(
                {
                    "rater_a_event_id": a_event["event_id"],
                    "rater_b_event_id": None,
                    "status": "MISSING_RATER_B",
                    "metrics": None,
                }
            )
            continue
        if strategy == "LEGACY_STAGE13":
            best_index, metrics = max(
                candidates, key=lambda item: (item[1]["temporal_iou"], -item[0])
            )
        else:
            best_index, metrics = min(
                candidates,
                key=lambda item: (
                    -item[1]["temporal_iou"],
                    -item[1]["overlap_duration_ms"],
                    item[1]["onset_difference_ms"],
                    item[1]["offset_difference_ms"],
                    b_events[item[0]]["event_id"],
                ),
            )
        unused_b.remove(best_index)
        matches.append(
            {
                "rater_a_event_id": a_event["event_id"],
                "rater_b_event_id": b_events[best_index]["event_id"],
                "status": "MATCHED" if metrics["temporal_iou"] > 0 else "NO_OVERLAP",
                "metrics": metrics,
            }
        )
    for index in sorted(unused_b):
        matches.append(
            {
                "rater_a_event_id": None,
                "rater_b_event_id": b_events[index]["event_id"],
                "status": "MISSING_RATER_A",
                "metrics": None,
            }
        )
    ensure_finite(matches)
    return matches


def _rank_metric_candidates(
    candidates: list[dict[str, Any]], strategy: str
) -> str:
    indexed = list(enumerate(sorted(candidates, key=lambda item: item["event_id"])))
    if strategy == "LEGACY_STAGE13":
        _, best = max(
            indexed, key=lambda item: (item[1]["temporal_iou"], -item[0])
        )
    else:
        _, best = min(
            indexed,
            key=lambda item: (
                -item[1]["temporal_iou"],
                -item[1]["overlap_duration_ms"],
                item[1]["onset_difference_ms"],
                item[1]["offset_difference_ms"],
                item[1]["event_id"],
            ),
        )
    return best["event_id"]


def compatibility_fixture_results() -> dict[str, Any]:
    metric_fixtures = [
        (
            "different_iou",
            [
                {
                    "event_id": "EVT_B_001",
                    "temporal_iou": 0.5,
                    "overlap_duration_ms": 80,
                    "onset_difference_ms": 10,
                    "offset_difference_ms": 10,
                },
                {
                    "event_id": "EVT_B_002",
                    "temporal_iou": 0.75,
                    "overlap_duration_ms": 70,
                    "onset_difference_ms": 20,
                    "offset_difference_ms": 20,
                },
            ],
        ),
        (
            "same_iou_different_overlap",
            [
                {
                    "event_id": "EVT_B_001",
                    "temporal_iou": 0.5,
                    "overlap_duration_ms": 50,
                    "onset_difference_ms": 0,
                    "offset_difference_ms": 50,
                },
                {
                    "event_id": "EVT_B_002",
                    "temporal_iou": 0.5,
                    "overlap_duration_ms": 100,
                    "onset_difference_ms": 0,
                    "offset_difference_ms": 100,
                },
            ],
        ),
        (
            "same_iou_overlap_different_onset",
            [
                {
                    "event_id": "EVT_B_001",
                    "temporal_iou": 0.6,
                    "overlap_duration_ms": 60,
                    "onset_difference_ms": 20,
                    "offset_difference_ms": 5,
                },
                {
                    "event_id": "EVT_B_002",
                    "temporal_iou": 0.6,
                    "overlap_duration_ms": 60,
                    "onset_difference_ms": 10,
                    "offset_difference_ms": 30,
                },
            ],
        ),
        (
            "all_metrics_same_event_id_only",
            [
                {
                    "event_id": "EVT_B_002",
                    "temporal_iou": 0.8,
                    "overlap_duration_ms": 80,
                    "onset_difference_ms": 10,
                    "offset_difference_ms": 10,
                },
                {
                    "event_id": "EVT_B_001",
                    "temporal_iou": 0.8,
                    "overlap_duration_ms": 80,
                    "onset_difference_ms": 10,
                    "offset_difference_ms": 10,
                },
            ],
        ),
    ]
    comparisons = []
    for name, candidates in metric_fixtures:
        legacy = _rank_metric_candidates(candidates, "LEGACY_STAGE13")
        v2 = _rank_metric_candidates(candidates, "DETERMINISTIC_MULTI_CRITERIA_V2")
        comparisons.append(
            {
                "fixture_id": name,
                "legacy_selected_event_id": legacy,
                "v2_selected_event_id": v2,
                "strategies_differ": legacy != v2,
            }
        )

    a_events = [
        {
            "event_id": "EVT_A_001",
            "answer_id": "ANS_FIXTURE",
            "label_id": "LBL_FIXTURE",
            "direction": None,
            "start_timestamp_ms": 0,
            "end_timestamp_ms": 100,
        },
        {
            "event_id": "EVT_A_002",
            "answer_id": "ANS_FIXTURE",
            "label_id": "LBL_FIXTURE",
            "direction": None,
            "start_timestamp_ms": 60,
            "end_timestamp_ms": 160,
        },
    ]
    b_events = [
        {
            "event_id": "EVT_B_001",
            "answer_id": "ANS_FIXTURE",
            "label_id": "LBL_FIXTURE",
            "direction": None,
            "start_timestamp_ms": 20,
            "end_timestamp_ms": 120,
        },
        {
            "event_id": "EVT_B_002",
            "answer_id": "ANS_FIXTURE",
            "label_id": "LBL_FIXTURE",
            "direction": None,
            "start_timestamp_ms": 80,
            "end_timestamp_ms": 180,
        },
    ]
    order_checks = {}
    one_to_one_checks = {}
    for strategy in ("LEGACY_STAGE13", "DETERMINISTIC_MULTI_CRITERIA_V2"):
        forward = match_fixture_events(a_events, b_events, strategy)
        reversed_result = match_fixture_events(
            list(reversed(a_events)), list(reversed(b_events)), strategy
        )
        order_checks[strategy] = forward == reversed_result
        selected = [
            item["rater_b_event_id"]
            for item in forward
            if item["rater_b_event_id"] is not None
            and item["rater_a_event_id"] is not None
        ]
        one_to_one_checks[strategy] = len(selected) == len(set(selected))
    result = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "fixture_only": True,
        "real_rater_annotation_loaded": False,
        "agreement_or_kappa_calculated": False,
        "metric_fixture_comparisons": comparisons,
        "input_order_invariant": order_checks,
        "one_to_one_duplicate_prevented": one_to_one_checks,
        "all_checks_passed": all(order_checks.values())
        and all(one_to_one_checks.values()),
    }
    ensure_finite(result)
    return result


def _analysis() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "evidence_basis": "ACTUAL_CODE_AND_TESTS",
        "legacy": {
            "implementation": "app/vision/annotation_agreement.py:94",
            "selection_expression": "app/vision/annotation_agreement.py:150",
            "test_evidence": "tests/test_annotation_contract_stage13.py:218",
            "ordering_rules": list(LEGACY_ORDER),
            "deterministic": True,
            "raw_input_array_order_dependent": False,
            "dependency_detail": (
                "Both arrays are canonically sorted first. Equal IoU is resolved "
                "by the resulting Rater B index, whose sort keys include start time "
                "and event_id."
            ),
            "existing_test_impact": (
                "The Stage 13 test verifies no-overlap and missing statuses; it does "
                "not pin an equal-IoU tie fixture."
            ),
        },
        "proposed_v2": {
            "definition": "app/vision/annotation_matching_policy.py:41",
            "ranking_implementation": "app/vision/annotation_matching_policy.py:512",
            "ordering_rules": list(V2_ORDER),
            "deterministic": True,
            "raw_input_array_order_dependent": False,
        },
        "same_iou_difference": (
            "Legacy selects the lowest canonical Rater B index. V2 next compares "
            "overlap duration, onset difference, offset difference, then event_id."
        ),
        "previous_result_reproducibility": (
            "LEGACY_STAGE13 reproduces prior selections. V2 may change only cases "
            "with multiple maximum-IoU candidates."
        ),
        "backward_compatibility_risk": {
            "level": "MEDIUM",
            "unaffected_cases": "Cases with a unique maximum-IoU candidate.",
            "affected_cases": "Equal maximum-IoU candidates resolved by later keys.",
        },
    }


def _comparison() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "threshold_policy_separate": True,
        "strategies": [
            {
                "strategy": "LEGACY_STAGE13",
                "ordering_rules": list(LEGACY_ORDER),
                "legacy_compatible": True,
                "deterministic_after_canonical_sort": True,
            },
            {
                "strategy": "DETERMINISTIC_MULTI_CRITERIA_V2",
                "ordering_rules": list(V2_ORDER),
                "legacy_compatible": False,
                "deterministic_after_canonical_sort": True,
            },
        ],
        "automatic_selection_performed": False,
        "selected_strategy": "UNRESOLVED",
    }


def _candidate(previous_sha256: str) -> dict[str, Any]:
    tie_policy = unresolved_tie_breaker_policy()
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policy_id": MATCHING_POLICY_ID,
        "policy_version": MATCHING_POLICY_VERSION,
        "status": "REVIEW_REQUIRED",
        "operational": False,
        "scope": SCOPE,
        "rubric_id": "RUBRIC_OBSERVABLE_001",
        "rubric_version": "1.0.0",
        "matching_keys": ["answer_id", "label_id", "direction"],
        "positive_overlap_requirement": True,
        "one_to_one_matching": True,
        "tie_breaker_strategy": tie_policy.to_dict(),
        "temporal_thresholds": {
            "minimum_temporal_iou": None,
            "maximum_onset_difference_ms": None,
            "maximum_offset_difference_ms": None,
        },
        "previous_candidate": {
            "policy_version": "0.1.0",
            "sha256": previous_sha256,
            "modified": False,
        },
        "thresholds_derived_from_current_raters": False,
    }


def _status_for(decision: dict[str, Any] | None) -> str:
    if decision is None or decision["decision"] == "REVIEW_PENDING":
        return AWAITING_STATUS
    if decision["decision"].startswith("APPROVE_"):
        return APPROVED_STATUS
    if decision["decision"] == "REVISION_REQUIRED":
        return REVISION_STATUS
    return REJECTED_STATUS


def _approved_snapshot(decision: dict[str, Any]) -> dict[str, Any]:
    strategy = decision["selected_tie_breaker_strategy"]
    order = LEGACY_ORDER if strategy == "LEGACY_STAGE13" else V2_ORDER
    return TieBreakerPolicy.from_dict(
        {
            "tie_breaker_policy_id": TIE_BREAKER_POLICY_ID,
            "tie_breaker_policy_version": TIE_BREAKER_POLICY_VERSION,
            "status": "APPROVED",
            "scope": SCOPE,
            "strategy": strategy,
            "ordering_rules": list(order),
            "legacy_compatibility": (
                "Preserves Stage 13 equal-IoU selection."
                if strategy == "LEGACY_STAGE13"
                else "May change Stage 13 equal-IoU selection."
            ),
            "operational": True,
            "approved_by": decision["reviewer_id"],
            "approved_at": decision["reviewed_at"],
            "rationale": decision["rationale"],
        }
    ).to_dict()


def build_policy_revision_package(
    stage191_dir: str | Path,
    output_dir: str | Path,
    *,
    decision_path: str | Path | None = None,
    rater_annotation_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Create a new immutable 0.2.0 review package.

    Rater paths are hashed before and after only; their JSON contents are never
    loaded. Existing output content is treated as a version-overwrite attempt.
    """
    source_dir = Path(stage191_dir)
    destination = Path(output_dir)
    previous_candidate = source_dir / "agreement_policy_candidates.json"
    if not previous_candidate.is_file():
        raise PolicyRevisionError("Stage 19.1 candidate is missing")
    if destination.exists():
        raise PolicyRevisionError("refusing to overwrite policy version 0.2.0")

    previous_before = sha256_file(previous_candidate)
    rater_paths = [Path(item) for item in rater_annotation_paths]
    rater_before = {str(path): sha256_file(path) for path in rater_paths}
    decision: dict[str, Any] | None = None
    decision_error: str | None = None
    if decision_path is not None and Path(decision_path).exists():
        try:
            decision = load_decision(decision_path)
        except (PolicyRevisionError, ValueError) as exc:
            decision_error = str(exc)

    fixtures = compatibility_fixture_results()
    current_status = (
        VALIDATION_FAILED_STATUS if decision_error else _status_for(decision)
    )
    candidate = _candidate(previous_before)
    analysis = _analysis()
    comparison = _comparison()
    review_packet = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "candidate_policy_id": MATCHING_POLICY_ID,
        "candidate_version": MATCHING_POLICY_VERSION,
        "review_question": (
            "Choose whether the Stage 13 legacy or deterministic V2 tie-breaker "
            "should govern pilot matching."
        ),
        "threshold_review_separate": True,
        "threshold_approval_option_provided": False,
        "real_rater_results_used_for_selection": False,
        "automatic_decision_performed": False,
        "compatibility_fixture_only": True,
    }
    status = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "current_status": current_status,
        "decision_file_present": decision is not None or decision_error is not None,
        "decision_valid": decision_error is None,
        "selected_tie_breaker_strategy": (
            decision["selected_tie_breaker_strategy"] if decision else None
        ),
        "agreement_rerun_performed": False,
        "kappa_rerun_performed": False,
    }

    destination.mkdir(parents=True, exist_ok=False)
    documents = {
        "stage13_tie_breaker_analysis.json": analysis,
        "tie_breaker_strategy_comparison.json": comparison,
        "agreement_policy_candidate_0_2_0.json": candidate,
        "agreement_policy_revision_review_packet.json": review_packet,
        "agreement_policy_revision_decision.template.json": decision_template(),
        "compatibility_fixture_results.json": fixtures,
        "agreement_policy_revision_status.json": status,
    }
    validation = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "valid": decision_error is None,
        "current_status": current_status,
        "checks": {
            "previous_candidate_present": True,
            "previous_candidate_hash_unchanged": False,
            "fixture_checks_passed": fixtures["all_checks_passed"],
            "thresholds_remain_null": all(
                value is None for value in candidate["temporal_thresholds"].values()
            ),
            "strategy_auto_selected": False,
            "real_rater_annotation_loaded": False,
            "agreement_or_kappa_calculated": False,
            "decision_valid": decision_error is None,
        },
        "decision_validation_error": decision_error,
        "protected_inputs": {
            "stage19_1_candidate": {
                "path": str(previous_candidate),
                "sha256_before": previous_before,
                "sha256_after": None,
            },
            "rater_annotations": [
                {
                    "path": str(path),
                    "sha256_before": rater_before[str(path)],
                    "sha256_after": None,
                }
                for path in rater_paths
            ],
        },
    }
    for name, document in documents.items():
        write_strict_json(destination / name, document)
    if decision is not None and current_status == APPROVED_STATUS:
        write_strict_json(
            destination / "approved_tie_breaker_policy_snapshot.json",
            _approved_snapshot(decision),
        )

    previous_after = sha256_file(previous_candidate)
    rater_after = {str(path): sha256_file(path) for path in rater_paths}
    validation["checks"]["previous_candidate_hash_unchanged"] = (
        previous_before == previous_after
    )
    validation["protected_inputs"]["stage19_1_candidate"]["sha256_after"] = (
        previous_after
    )
    for item in validation["protected_inputs"]["rater_annotations"]:
        item["sha256_after"] = rater_after[item["path"]]
        item["hash_unchanged"] = item["sha256_before"] == item["sha256_after"]
    write_strict_json(destination / "validation_report.json", validation)
    markdown = (
        "# Stage 19.2 validation report\n\n"
        f"- Current status: `{current_status}`\n"
        f"- Validation passed: `{str(validation['valid']).lower()}`\n"
        "- Compatibility comparison: fixture-only\n"
        "- Real rater Annotation loaded: `false`\n"
        "- Agreement/Kappa rerun: `false`\n"
        "- Thresholds: all `null`\n"
        "- Automatic tie-breaker approval: `false`\n"
    )
    (destination / "validation_report.md").write_text(markdown, encoding="utf-8")
    if tuple(name for name in OUTPUT_NAMES if not (destination / name).is_file()):
        raise PolicyRevisionError("required package output is missing")
    ensure_finite(validation)
    return validation
