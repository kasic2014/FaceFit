"""Word-timestamp gap and technical pause-view measurements."""

from __future__ import annotations

import math
import statistics
from typing import Any


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    interpolated = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return _round_half_up(interpolated)


def analyze_timestamp_pauses(
    words: list[dict[str, Any]],
    duration_ms: int,
    thresholds_ms: tuple[int, ...],
) -> tuple[dict[str, Any], list[str]]:
    if not words:
        return (
            {
                "leadingGapMs": None,
                "trailingGapMs": None,
                "wordPairCount": 0,
                "interWordGapCount": 0,
                "totalInterWordGapMs": 0,
                "meanInterWordGapMs": None,
                "medianInterWordGapMs": None,
                "maxInterWordGapMs": None,
                "p90InterWordGapMs": None,
                "overlappingWordPairCount": 0,
                "pauseCandidateViews": [
                    {"minimumGapMs": threshold, "count": 0,
                     "totalDurationMs": 0, "maximumDurationMs": 0}
                    for threshold in thresholds_ms
                ],
                "thresholdPurpose": "TECHNICAL_VIEW_ONLY",
                "scoringApproved": False,
            },
            ["WORD_TIMESTAMPS_UNAVAILABLE"],
        )
    gaps = [
        int(following["startMsRelative"]) - int(previous["endMsRelative"])
        for previous, following in zip(words, words[1:])
    ]
    positive = [gap for gap in gaps if gap > 0]
    overlaps = sum(gap < 0 for gap in gaps)
    views = [
        {
            "minimumGapMs": threshold,
            "count": sum(gap >= threshold for gap in positive),
            "totalDurationMs": sum(gap for gap in positive if gap >= threshold),
            "maximumDurationMs": max(
                (gap for gap in positive if gap >= threshold), default=0
            ),
        }
        for threshold in thresholds_ms
    ]
    return (
        {
            "leadingGapMs": int(words[0]["startMsRelative"]),
            "trailingGapMs": duration_ms - int(words[-1]["endMsRelative"]),
            "wordPairCount": len(gaps),
            "interWordGapCount": len(positive),
            "totalInterWordGapMs": sum(positive),
            "meanInterWordGapMs": (
                _round_half_up(statistics.mean(positive)) if positive else None
            ),
            "medianInterWordGapMs": (
                _round_half_up(statistics.median(positive)) if positive else None
            ),
            "maxInterWordGapMs": max(positive) if positive else None,
            "p90InterWordGapMs": _percentile(positive, 90) if positive else None,
            "overlappingWordPairCount": overlaps,
            "pauseCandidateViews": views,
            "thresholdPurpose": "TECHNICAL_VIEW_ONLY",
            "scoringApproved": False,
        },
        ["OVERLAPPING_WORD_TIMESTAMPS"] if overlaps else [],
    )
