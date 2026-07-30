"""Reference, interval, direction, duplicate, and layer validation."""

from __future__ import annotations

from collections.abc import Iterable

from app.vision.annotation_models import (
    AnnotationEvent,
    AnnotationLayer,
    AnnotationRater,
    AnnotationSession,
)
from app.vision.annotation_registry import AnnotationRegistry
from app.vision.data_collection_models import AnswerSample


def validate_annotation_contract(
    *,
    registry: AnnotationRegistry,
    answers: Iterable[AnswerSample],
    raters: Iterable[AnnotationRater],
    sessions: Iterable[AnnotationSession],
    events: Iterable[AnnotationEvent],
) -> None:
    answer_items = tuple(answers)
    rater_items = tuple(raters)
    session_items = tuple(sessions)
    answer_map = {item.answer_id: item for item in answer_items}
    rater_map = {item.rater_id: item for item in rater_items}
    session_map = {
        item.annotation_session_id: item for item in session_items
    }
    if len(answer_map) != len(answer_items):
        raise ValueError("Duplicate answer_id")
    if len(rater_map) != len(rater_items):
        raise ValueError("Duplicate rater_id")
    if len(session_map) != len(session_items):
        raise ValueError("Duplicate annotation_session_id")

    original_raters: set[str] = set()
    for session in session_map.values():
        if session.rater_id not in rater_map:
            raise ValueError("annotation session references unknown rater")
        registry.get_rubric(session.rubric_id, session.rubric_version)
        if session.layer != AnnotationLayer.ADJUDICATED_RESULT.value:
            if rater_map[session.rater_id].role != "INDEPENDENT_RATER":
                raise ValueError("original layer requires independent rater")
            original_raters.add(session.rater_id)
        elif rater_map[session.rater_id].role != "ADJUDICATOR":
            raise ValueError("adjudicated layer requires adjudicator")
    if len(original_raters) < 2:
        raise ValueError("at least two independent raters are required")

    event_ids: set[str] = set()
    exact_keys: set[tuple[object, ...]] = set()
    for event in events:
        if event.event_id in event_ids:
            raise ValueError(f"Duplicate event_id: {event.event_id}")
        event_ids.add(event.event_id)
        if event.answer_id not in answer_map:
            raise ValueError("event references unknown answer")
        if event.rater_id not in rater_map:
            raise ValueError("event references unknown rater")
        session = session_map.get(event.annotation_session_id)
        if session is None:
            raise ValueError("event references unknown annotation session")
        if session.rater_id != event.rater_id or session.layer != event.layer:
            raise ValueError("event rater/layer differs from annotation session")
        answer = answer_map[event.answer_id]
        if not (
            answer.start_timestamp_ms <= event.start_timestamp_ms
            < event.end_timestamp_ms <= answer.end_timestamp_ms
        ):
            raise ValueError("annotation event is outside AnswerSample")
        label = registry.get_label(event.label_id)
        if label.requires_direction:
            if event.direction not in label.allowed_directions:
                raise ValueError("required event direction is missing or invalid")
        elif event.direction is not None:
            raise ValueError("directionless label requires direction=null")
        key = (
            event.rater_id,
            event.answer_id,
            event.label_id,
            event.start_timestamp_ms,
            event.end_timestamp_ms,
            event.direction,
            event.layer,
        )
        if key in exact_keys:
            raise ValueError("exact duplicate event for the same rater")
        exact_keys.add(key)
