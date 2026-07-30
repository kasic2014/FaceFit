"""Stage 18 independent-rater package and submission validation contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.vision.annotation_models import (
    AnnotationLabelDefinition,
    AnnotationRubric,
)
from app.vision.annotation_registry import (
    FORBIDDEN_ANNOTATION_CONCEPTS,
    AnnotationRegistry,
)


PARTICIPANT_ID = "PTC_000001"
SESSION_ID = "SES_000001"
RUBRIC_ID = "RUBRIC_OBSERVABLE_001"
RUBRIC_VERSION = "1.0.0"
RATER_IDS = ("RATER_A", "RATER_B")
BLIND_FLAG_NAMES = (
    "blinded_to_model_metrics",
    "blinded_to_stage7_10_metrics",
    "blinded_to_head_pose_availability",
    "blinded_to_jump_candidates",
    "blinded_to_stage11_fixture_scores",
    "blinded_to_other_raters",
    "blinded_to_manual_review_details",
    "blinded_to_direct_identifiers",
)
ROOT_FIELDS = frozenset({
    "schema_version",
    "participant_id",
    "session_id",
    "rater_id",
    "rubric_id",
    "rubric_version",
    *BLIND_FLAG_NAMES,
    "completed_at",
    "events",
})
EVENT_FIELDS = frozenset({
    "annotation_event_id",
    "answer_id",
    "interval_id",
    "label_id",
    "direction",
    "start_timestamp_ms",
    "end_timestamp_ms",
    "rater_confidence",
    "note",
})
FORBIDDEN_INPUT_FIELDS = frozenset({
    "angle",
    "confidence",
    "anxiety",
    "attention",
    "personality",
    "hirability",
    "pass",
    "fail",
    "mental_health",
    "diagnosis",
    "posture_score",
    "interview_score",
    "evaluation_threshold",
    "head_pose_value",
    "jump_candidate",
    "stage10_metric",
    "stage11_score",
})


def registry_from_dict(value: dict[str, Any]) -> AnnotationRegistry:
    labels = tuple(
        AnnotationLabelDefinition(
            item["label_id"],
            item["display_name"],
            item["description"],
            item["category"],
            item["requires_direction"],
            tuple(item["allowed_directions"]),
            item["observable_only"],
            item["status"],
        )
        for item in value["labels"]
    )
    rubrics = tuple(
        AnnotationRubric(
            item["rubric_id"],
            item["version"],
            item["status"],
            tuple(item["label_ids"]),
            item["interval_end_exclusive"],
            item["inference_prohibited"],
        )
        for item in value["rubrics"]
    )
    return AnnotationRegistry(labels, rubrics)


def _require_exact_fields(
    value: dict[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing={','.join(sorted(missing))}")
        if extra:
            details.append(f"extra={','.join(sorted(extra))}")
        raise ValueError(f"{context} fields invalid: {'; '.join(details)}")


def _assert_no_forbidden_fields(value: Any) -> None:
    if isinstance(value, dict):
        found = FORBIDDEN_INPUT_FIELDS.intersection(
            str(key).lower() for key in value
        )
        if found:
            raise ValueError(
                f"forbidden annotation fields: {', '.join(sorted(found))}"
            )
        for item in value.values():
            _assert_no_forbidden_fields(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_fields(item)


def build_empty_template(rater_id: str) -> dict[str, Any]:
    if rater_id not in RATER_IDS:
        raise ValueError("invalid independent rater_id")
    return {
        "schema_version": "1.0.0",
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "rater_id": rater_id,
        "rubric_id": RUBRIC_ID,
        "rubric_version": RUBRIC_VERSION,
        **{flag: True for flag in BLIND_FLAG_NAMES},
        "completed_at": None,
        "events": [],
    }


def _validate_completed_at(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError("submitted annotation requires completed_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("completed_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("completed_at must include a timezone")


def validate_rater_submission(
    value: dict[str, Any],
    *,
    expected_rater_id: str,
    answers: list[dict[str, Any]],
    registry: AnnotationRegistry,
    require_completed: bool = True,
) -> dict[str, Any]:
    """Validate one rater without inspecting another rater's submission."""
    if expected_rater_id not in RATER_IDS:
        raise ValueError("invalid independent rater_id")
    _require_exact_fields(value, ROOT_FIELDS, "annotation root")
    _assert_no_forbidden_fields(value)
    if value["schema_version"] != "1.0.0":
        raise ValueError("annotation schema_version mismatch")
    references = {
        "participant_id": value["participant_id"] == PARTICIPANT_ID,
        "session_id": value["session_id"] == SESSION_ID,
        "rater_id": value["rater_id"] == expected_rater_id,
        "rubric": (
            value["rubric_id"] == RUBRIC_ID
            and value["rubric_version"] == RUBRIC_VERSION
        ),
    }
    if not all(references.values()):
        raise ValueError("annotation reference mismatch")
    if not all(value[flag] is True for flag in BLIND_FLAG_NAMES):
        raise ValueError("all rater blind flags must be true")
    registry.get_rubric(value["rubric_id"], value["rubric_version"])
    if require_completed:
        _validate_completed_at(value["completed_at"])
    elif value["completed_at"] is not None:
        _validate_completed_at(value["completed_at"])
    events = value["events"]
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    answer_map = {item["answer_id"]: item for item in answers}
    if len(answer_map) != len(answers):
        raise ValueError("duplicate answer_id in interval contract")
    event_ids: set[str] = set()
    exact_events: set[tuple[Any, ...]] = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("annotation event must be an object")
        _require_exact_fields(event, EVENT_FIELDS, "annotation event")
        _assert_no_forbidden_fields(event)
        event_id = event["annotation_event_id"]
        if (
            not isinstance(event_id, str)
            or not event_id.startswith(f"{expected_rater_id}_EVT_")
            or event_id in event_ids
        ):
            raise ValueError("invalid or duplicate annotation_event_id")
        event_ids.add(event_id)
        answer = answer_map.get(event["answer_id"])
        if answer is None or event["interval_id"] != answer["interval_id"]:
            raise ValueError("event Answer/Interval reference mismatch")
        start = event["start_timestamp_ms"]
        end = event["end_timestamp_ms"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not answer["start_timestamp_ms"] <= start < end
            or end > answer["end_timestamp_ms"]
        ):
            raise ValueError("annotation event is outside its Answer interval")
        try:
            label = registry.get_label(event["label_id"])
        except KeyError as exc:
            raise ValueError("event references an unknown label") from exc
        direction = event["direction"]
        if label.requires_direction:
            if direction not in label.allowed_directions:
                raise ValueError("required event direction is missing or invalid")
        elif direction is not None:
            raise ValueError("directionless label requires direction=null")
        if event["rater_confidence"] is not None:
            raise ValueError("rater_confidence must remain null")
        if event["note"] is not None and not isinstance(event["note"], str):
            raise ValueError("event note must be text or null")
        exact_key = (
            event["answer_id"],
            event["interval_id"],
            event["label_id"],
            direction,
            start,
            end,
        )
        if exact_key in exact_events:
            raise ValueError("exact duplicate event for the same rater")
        exact_events.add(exact_key)
    return {
        "valid": True,
        "rater_id": expected_rater_id,
        "event_count": len(events),
        "references_valid": True,
        "blind_flags_valid": True,
        "registry_labels_valid": True,
        "answer_intervals_valid": True,
        "direction_rules_valid": True,
        "duplicate_events_absent": True,
        "forbidden_fields_absent": True,
    }


def annotation_readiness_status(
    rater_a: dict[str, Any],
    rater_b: dict[str, Any],
) -> str:
    validations = (rater_a, rater_b)
    if any(
        item.get("result_file_exists") is True
        and item.get("valid") is not True
        for item in validations
    ):
        return "rater_annotation_validation_failed"
    submitted = [
        item.get("result_file_exists") is True
        and item.get("valid") is True
        for item in validations
    ]
    if all(submitted):
        return "rater_annotations_ready_for_agreement"
    if any(submitted):
        return "awaiting_second_rater_annotation"
    return "awaiting_rater_annotations"


def cross_rater_similarity_warnings(
    rater_a: dict[str, Any],
    rater_b: dict[str, Any],
) -> list[str]:
    """Flag copied or semantically identical results without judging them."""
    warnings: list[str] = []
    if rater_a == rater_b:
        warnings.append("IDENTICAL_RESULT_FILE_CONTENT")
    a_events = rater_a.get("events")
    b_events = rater_b.get("events")
    if not isinstance(a_events, list) or not isinstance(b_events, list):
        return warnings

    def signatures(events: list[Any]) -> list[tuple[Any, ...]] | None:
        values: list[tuple[Any, ...]] = []
        for event in events:
            if not isinstance(event, dict):
                return None
            values.append((
                event.get("answer_id"),
                event.get("interval_id"),
                event.get("label_id"),
                event.get("direction"),
                event.get("start_timestamp_ms"),
                event.get("end_timestamp_ms"),
                event.get("note"),
            ))
        return values

    a_signatures = signatures(a_events)
    b_signatures = signatures(b_events)
    if (
        a_signatures is not None
        and b_signatures is not None
        and a_signatures
        and a_signatures == b_signatures
    ):
        warnings.append("IDENTICAL_EVENT_CONTENT")
    return warnings


def forbidden_concept_names() -> list[str]:
    return sorted(FORBIDDEN_ANNOTATION_CONCEPTS)
