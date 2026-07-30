"""Safe, non-evaluative inter-rater agreement calculations."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from app.vision.annotation_models import AnnotationEvent, EventAgreementResult


def temporal_iou(
    start_a_ms: int,
    end_a_ms: int,
    start_b_ms: int,
    end_b_ms: int,
) -> float:
    if end_a_ms <= start_a_ms or end_b_ms <= start_b_ms:
        raise ValueError("IoU intervals must have positive duration")
    intersection = max(
        0, min(end_a_ms, end_b_ms) - max(start_a_ms, start_b_ms)
    )
    union = max(end_a_ms, end_b_ms) - min(start_a_ms, start_b_ms)
    value = intersection / union
    if not math.isfinite(value):
        raise ValueError("non-finite temporal IoU")
    return value


@dataclass(frozen=True)
class PresenceAgreementResult:
    item_count: int
    both_positive_count: int
    a_only_count: int
    b_only_count: int
    both_negative_count: int
    observed_agreement: float | None
    positive_agreement: float | None
    negative_agreement: float | None
    cohen_kappa: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_presence_agreement(
    rater_a: Iterable[bool],
    rater_b: Iterable[bool],
) -> PresenceAgreementResult:
    a_values = tuple(rater_a)
    b_values = tuple(rater_b)
    if len(a_values) != len(b_values):
        raise ValueError("presence vectors must have equal length")
    n = len(a_values)
    both_positive = sum(a and b for a, b in zip(a_values, b_values))
    a_only = sum(a and not b for a, b in zip(a_values, b_values))
    b_only = sum(not a and b for a, b in zip(a_values, b_values))
    both_negative = sum(not a and not b for a, b in zip(a_values, b_values))
    observed = (both_positive + both_negative) / n if n else None
    positive_denominator = 2 * both_positive + a_only + b_only
    negative_denominator = 2 * both_negative + a_only + b_only
    positive = (
        2 * both_positive / positive_denominator
        if positive_denominator else None
    )
    negative = (
        2 * both_negative / negative_denominator
        if negative_denominator else None
    )
    kappa: float | None = None
    if n:
        p_a = (both_positive + a_only) / n
        p_b = (both_positive + b_only) / n
        expected = p_a * p_b + (1 - p_a) * (1 - p_b)
        denominator = 1 - expected
        if denominator != 0:
            kappa = (observed - expected) / denominator
    for value in (observed, positive, negative, kappa):
        if value is not None and not math.isfinite(value):
            raise ValueError("non-finite agreement result")
    return PresenceAgreementResult(
        n,
        both_positive,
        a_only,
        b_only,
        both_negative,
        observed,
        positive,
        negative,
        kappa,
    )


def compare_event_sets(
    rater_a_events: Iterable[AnnotationEvent],
    rater_b_events: Iterable[AnnotationEvent],
) -> tuple[EventAgreementResult, ...]:
    """Greedily match same-answer/label/direction events by maximum IoU.

    There is deliberately no approval threshold. Positive overlap is a match;
    zero overlap and missing counterparts remain explicit.
    """
    a_events = sorted(
        rater_a_events,
        key=lambda e: (e.answer_id, e.label_id, e.start_timestamp_ms, e.event_id),
    )
    b_events = sorted(
        rater_b_events,
        key=lambda e: (e.answer_id, e.label_id, e.start_timestamp_ms, e.event_id),
    )
    unused_b = set(range(len(b_events)))
    results: list[EventAgreementResult] = []
    for a_event in a_events:
        candidates: list[tuple[float, int]] = []
        for index in sorted(unused_b):
            b_event = b_events[index]
            if (
                a_event.answer_id,
                a_event.label_id,
                a_event.direction,
            ) != (
                b_event.answer_id,
                b_event.label_id,
                b_event.direction,
            ):
                continue
            candidates.append(
                (
                    temporal_iou(
                        a_event.start_timestamp_ms,
                        a_event.end_timestamp_ms,
                        b_event.start_timestamp_ms,
                        b_event.end_timestamp_ms,
                    ),
                    index,
                )
            )
        if not candidates:
            results.append(
                EventAgreementResult(
                    a_event.answer_id,
                    a_event.label_id,
                    a_event.event_id,
                    None,
                    None,
                    "MISSING_RATER_B",
                )
            )
            continue
        best_iou, best_index = max(
            candidates, key=lambda item: (item[0], -item[1])
        )
        b_event = b_events[best_index]
        unused_b.remove(best_index)
        results.append(
            EventAgreementResult(
                a_event.answer_id,
                a_event.label_id,
                a_event.event_id,
                b_event.event_id,
                best_iou,
                "MATCHED" if best_iou > 0 else "NO_OVERLAP",
            )
        )
    for index in sorted(unused_b):
        event = b_events[index]
        results.append(
            EventAgreementResult(
                event.answer_id,
                event.label_id,
                None,
                event.event_id,
                None,
                "MISSING_RATER_A",
            )
        )
    return tuple(results)
