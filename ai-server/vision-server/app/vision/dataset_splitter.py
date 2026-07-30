"""Deterministic participant-level fixture splitting and leakage checks."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping

from app.vision.data_collection_models import AnswerSample, RecordingSession
from app.vision.dataset_manifest_models import (
    SPLIT_NAMES,
    DatasetSplitAssignment,
)


def assign_participant_splits(
    participant_ids: Iterable[str],
    *,
    seed: int,
) -> tuple[DatasetSplitAssignment, ...]:
    """Assign round-robin splits after a seeded shuffle.

    This fixture helper does not encode or endorse production split ratios.
    """
    participants = sorted(participant_ids)
    if not participants or len(participants) != len(set(participants)):
        raise ValueError("participant_ids must be unique and non-empty")
    shuffled = list(participants)
    random.Random(seed).shuffle(shuffled)
    split_order = ("DEVELOPMENT", "CALIBRATION", "VALIDATION", "HOLDOUT")
    assigned = {
        participant_id: split_order[index % len(split_order)]
        for index, participant_id in enumerate(shuffled)
    }
    return tuple(
        DatasetSplitAssignment(
            participant_id=participant_id,
            split=assigned[participant_id],
            seed=seed,
            assignment_method="PARTICIPANT_LEVEL_DETERMINISTIC",
        )
        for participant_id in participants
    )


def validate_split_leakage(
    assignments: Iterable[DatasetSplitAssignment],
    sessions: Iterable[RecordingSession],
    answers: Iterable[AnswerSample],
) -> dict[str, int | bool]:
    assignment_items = tuple(assignments)
    session_items = tuple(sessions)
    answer_items = tuple(answers)
    participant_split: dict[str, str] = {}
    for item in assignment_items:
        prior = participant_split.setdefault(item.participant_id, item.split)
        if prior != item.split:
            raise ValueError("participant leakage across splits")
    session_split: dict[str, str] = {}
    for session in session_items:
        split = participant_split.get(session.participant_id)
        if split is None:
            raise ValueError("session participant lacks split assignment")
        prior = session_split.setdefault(session.session_id, split)
        if prior != split:
            raise ValueError("session leakage across splits")
    answer_split: dict[str, str] = {}
    for answer in answer_items:
        split = session_split.get(answer.session_id)
        if split is None:
            raise ValueError("answer session lacks split assignment")
        prior = answer_split.setdefault(answer.answer_id, split)
        if prior != split:
            raise ValueError("answer leakage across splits")
    unknown = set(participant_split.values()) - SPLIT_NAMES
    if unknown:
        raise ValueError("unknown split assignment")
    return {
        "leakage_detected": False,
        "participant_count": len(participant_split),
        "session_count": len(session_split),
        "answer_count": len(answer_split),
    }
