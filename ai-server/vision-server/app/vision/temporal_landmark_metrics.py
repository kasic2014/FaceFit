"""Pure temporal metrics for normalized landmark coordinates."""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable


def sanitize_metric_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _xy(point: Any) -> tuple[float, float] | None:
    if not isinstance(point, dict):
        return None
    x = sanitize_metric_number(point.get("x"))
    y = sanitize_metric_number(point.get("y"))
    return (x, y) if x is not None and y is not None else None


def calculate_point_displacement(previous: Any, current: Any) -> float | None:
    left, right = _xy(previous), _xy(current)
    return math.hypot(right[0] - left[0], right[1] - left[1]) if left and right else None


def calculate_center_point(left: Any, right: Any) -> dict[str, float] | None:
    a, b = _xy(left), _xy(right)
    return {"x": (a[0] + b[0]) / 2, "y": (a[1] + b[1]) / 2} if a and b else None


def calculate_shoulder_width(left: Any, right: Any) -> float | None:
    return calculate_point_displacement(left, right)


def calculate_frame_to_frame_displacement(points: Iterable[Any]) -> list[float | None]:
    values = list(points)
    return [None] + [
        calculate_point_displacement(values[index - 1], values[index])
        for index in range(1, len(values))
    ]


def calculate_series_median(values: Iterable[Any]) -> float | None:
    valid = [number for value in values if (number := sanitize_metric_number(value)) is not None]
    return statistics.median(valid) if valid else None


def calculate_series_mad(values: Iterable[Any], median: float | None = None) -> float | None:
    valid = [number for value in values if (number := sanitize_metric_number(value)) is not None]
    if not valid:
        return None
    center = calculate_series_median(valid) if median is None else median
    return statistics.median(abs(value - center) for value in valid)


def detect_coordinate_jump_candidates(
    values: list[Any],
    timestamps_ms: list[int],
    landmark_name: str,
    *,
    multiplier: float = 6.0,
    minimum_displacements: int = 4,
) -> dict[str, Any]:
    displacements = calculate_frame_to_frame_displacement(values)
    valid = [value for value in displacements if value is not None]
    median = calculate_series_median(valid)
    mad = calculate_series_mad(valid, median)
    if len(valid) < minimum_displacements:
        return {"method": "insufficient_data", "median": median, "mad": mad, "threshold": None, "events": []}
    if mad and mad > 0:
        threshold = median + multiplier * mad
        reason = "median_plus_k_mad"
    elif median and median > 0:
        threshold = median * 3.0
        reason = "zero_mad_relative_fallback"
    else:
        positive = [value for value in valid if value > 0]
        if not positive:
            return {"method": "zero_motion_insufficient_variation", "median": median, "mad": mad, "threshold": None, "events": []}
        threshold = calculate_series_median(positive) * 3.0
        reason = "zero_mad_positive_median_fallback"
    events = []
    for index, displacement in enumerate(displacements):
        if displacement is None or displacement <= threshold:
            continue
        events.append({
            "timestamp_ms": timestamps_ms[index],
            "landmark_name": landmark_name,
            "previous": values[index - 1],
            "current": values[index],
            "displacement": displacement,
            "median": median,
            "mad": mad,
            "threshold": threshold,
            "reason": reason,
            "status": "candidate",
        })
    return {"method": reason, "median": median, "mad": mad, "threshold": threshold, "events": events}


def _segments(states: list[bool], timestamps_ms: list[int], target: bool) -> list[dict[str, Any]]:
    if len(states) != len(timestamps_ms):
        raise ValueError("states and timestamps_ms must have equal lengths")
    if any(b <= a for a, b in zip(timestamps_ms, timestamps_ms[1:])):
        raise ValueError("timestamps_ms must be strictly increasing")
    interval = statistics.median(
        b - a for a, b in zip(timestamps_ms, timestamps_ms[1:])
    ) if len(timestamps_ms) > 1 else 0
    result, start = [], None
    for index, state in enumerate(states + [not target]):
        if index < len(states) and state is target and start is None:
            start = index
        if start is not None and (index == len(states) or state is not target):
            end = index - 1
            result.append({
                "start_sample_index": start,
                "end_sample_index": end,
                "start_timestamp_ms": timestamps_ms[start],
                "end_timestamp_ms": timestamps_ms[end],
                "frame_count": end - start + 1,
                "duration_sec": ((timestamps_ms[end] - timestamps_ms[start]) + interval) / 1000,
            })
            start = None
    return result


def build_detection_segments(states: list[bool], timestamps_ms: list[int]) -> list[dict[str, Any]]:
    return _segments(states, timestamps_ms, True)


def build_missing_segments(states: list[bool], timestamps_ms: list[int]) -> list[dict[str, Any]]:
    return _segments(states, timestamps_ms, False)


def calculate_longest_missing_duration(states: list[bool], timestamps_ms: list[int]) -> float:
    return max((segment["duration_sec"] for segment in build_missing_segments(states, timestamps_ms)), default=0.0)


def calculate_detection_ratio(states: Iterable[bool]) -> float | None:
    values = list(states)
    return sum(bool(value) for value in values) / len(values) if values else None
