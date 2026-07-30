"""Attach diagnostic jump events to start-inclusive/end-exclusive intervals."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from app.vision.interval_models import (
    AnalysisInterval,
    IntervalEventSummary,
)


def aggregate_interval_events(
    interval: AnalysisInterval,
    *,
    head_pose_events: Iterable[dict[str, Any]] = (),
    posture_events: Iterable[dict[str, Any]] = (),
    target_id: str = "TARGET_001",
) -> IntervalEventSummary:
    selected: list[tuple[str, dict[str, Any]]] = []
    ignored_target = 0
    for source, events in (
        ("head", head_pose_events),
        ("posture", posture_events),
    ):
        for event in events:
            timestamp = event.get("timestamp_ms")
            if (
                isinstance(timestamp, bool)
                or not isinstance(timestamp, int)
                or not interval.contains(timestamp)
            ):
                continue
            if event.get("target_id") != target_id:
                ignored_target += 1
                continue
            selected.append((source, event))
    event_types = Counter(
        str(event.get("event_type") or "UNKNOWN_EVENT")
        for _, event in selected
    )
    return IntervalEventSummary(
        head_pose_jump_candidate_count=sum(
            source == "head" for source, _ in selected
        ),
        posture_jump_candidate_count=sum(
            source == "posture" for source, _ in selected
        ),
        event_type_counts=dict(sorted(event_types.items())),
        event_timestamps_ms=tuple(
            sorted(int(event["timestamp_ms"]) for _, event in selected)
        ),
        ignored_target_mismatch_count=ignored_target,
    )
