"""Timestamp-based longest consecutive missing duration calculation."""

from __future__ import annotations

from typing import Iterable

from app.vision.interval_models import AnalysisInterval


def calculate_longest_missing_duration_ms(
    interval: AnalysisInterval,
    timestamps_ms: Iterable[int],
    availability: Iterable[bool],
) -> int:
    """Return the longest missing run using real timestamps and boundaries.

    A leading missing run begins at the interval start. A trailing missing run
    ends at the exclusive interval end. A middle run starts at its first
    unavailable timestamp and ends at the next available timestamp.
    """

    pairs = sorted(
        zip(timestamps_ms, availability),
        key=lambda item: item[0],
    )
    if not pairs:
        return interval.duration_ms
    longest = 0
    missing_start: int | None = None
    for index, (timestamp, available) in enumerate(pairs):
        if not available and missing_start is None:
            missing_start = (
                interval.start_timestamp_ms if index == 0 else timestamp
            )
        elif available and missing_start is not None:
            longest = max(longest, timestamp - missing_start)
            missing_start = None
    if missing_start is not None:
        longest = max(
            longest,
            interval.end_timestamp_ms - missing_start,
        )
    return max(0, int(longest))
