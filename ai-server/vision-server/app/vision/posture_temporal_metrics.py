"""Timestamp-based temporal metrics and robust diagnostic change candidates."""

from __future__ import annotations

import math
import statistics
from typing import Any

from app.vision.posture_raw_models import (
    PostureJumpEvent,
    PostureRawConfiguration,
    ShoulderPostureTemporalResult,
)


SUMMARY_KEYS = (
    "count",
    "min",
    "max",
    "median",
    "mad",
    "mean",
    "standard_deviation",
)


def calculate_numeric_summary(
    values: list[float | None],
) -> dict[str, float | int | None]:
    valid = [
        float(value)
        for value in values
        if value is not None and math.isfinite(float(value))
    ]
    if not valid:
        return dict.fromkeys(SUMMARY_KEYS, None) | {"count": 0}
    median = statistics.median(valid)
    return {
        "count": len(valid),
        "min": min(valid),
        "max": max(valid),
        "median": median,
        "mad": statistics.median(abs(value - median) for value in valid),
        "mean": statistics.fmean(valid),
        "standard_deviation": statistics.pstdev(valid),
    }


def _empty_temporal() -> ShoulderPostureTemporalResult:
    return ShoulderPostureTemporalResult(
        delta_time_seconds=None,
        shoulder_center_displacement_norm=None,
        shoulder_center_velocity_norm_per_sec=None,
        shoulder_tilt_delta_deg=None,
        shoulder_tilt_velocity_deg_per_sec=None,
        shoulder_width_delta_norm=None,
        shoulder_width_change_rate_per_sec=None,
        nose_offset_x_delta_norm=None,
        nose_offset_y_delta_norm=None,
        face_offset_x_delta_norm=None,
        face_offset_y_delta_norm=None,
    )


def calculate_posture_temporal_results(
    rows: list[dict[str, Any]],
) -> list[ShoulderPostureTemporalResult]:
    """Use real timestamps and never bridge an unavailable frame."""

    output: list[ShoulderPostureTemporalResult] = []
    previous: dict[str, Any] | None = None
    for row in rows:
        raw = row["posture_raw"]
        if not raw["available"]:
            output.append(_empty_temporal())
            previous = None
            continue
        if previous is None:
            output.append(_empty_temporal())
            previous = row
            continue
        delta_ms = row["timestamp_ms"] - previous["timestamp_ms"]
        if delta_ms <= 0:
            output.append(_empty_temporal())
            previous = row
            continue
        dt = delta_ms / 1000.0
        old = previous["posture_raw"]
        center_displacement = math.hypot(
            raw["shoulder_center_x"] - old["shoulder_center_x"],
            raw["shoulder_center_y"] - old["shoulder_center_y"],
        )
        tilt_delta = raw["shoulder_tilt_deg"] - old["shoulder_tilt_deg"]
        width_delta = raw["shoulder_width_norm"] - old["shoulder_width_norm"]

        def delta(field: str, availability: str) -> float | None:
            if not raw[availability] or not old[availability]:
                return None
            return raw[field] - old[field]

        output.append(
            ShoulderPostureTemporalResult(
                delta_time_seconds=dt,
                shoulder_center_displacement_norm=center_displacement,
                shoulder_center_velocity_norm_per_sec=center_displacement / dt,
                shoulder_tilt_delta_deg=tilt_delta,
                shoulder_tilt_velocity_deg_per_sec=tilt_delta / dt,
                shoulder_width_delta_norm=width_delta,
                shoulder_width_change_rate_per_sec=width_delta / dt,
                nose_offset_x_delta_norm=delta(
                    "nose_shoulder_offset_x_norm", "nose_alignment_available"
                ),
                nose_offset_y_delta_norm=delta(
                    "nose_shoulder_offset_y_norm", "nose_alignment_available"
                ),
                face_offset_x_delta_norm=delta(
                    "face_shoulder_offset_x_norm", "face_alignment_available"
                ),
                face_offset_y_delta_norm=delta(
                    "face_shoulder_offset_y_norm", "face_alignment_available"
                ),
            )
        )
        previous = row
    return output


def _threshold(
    values: list[float],
    minimum: float,
    configuration: PostureRawConfiguration,
) -> dict[str, Any]:
    if len(values) < configuration.minimum_jump_samples:
        return {
            "method": "insufficient_data",
            "sample_count": len(values),
            "median": None,
            "mad": None,
            "threshold": None,
        }
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    threshold = max(minimum, median + configuration.jump_mad_multiplier * mad)
    return {
        "method": "median_plus_k_mad_with_configured_floor",
        "sample_count": len(values),
        "median": median,
        "mad": mad,
        "threshold": threshold,
    }


def detect_posture_jump_candidates(
    rows: list[dict[str, Any]],
    configuration: PostureRawConfiguration = PostureRawConfiguration(),
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return diagnostics only; candidates do not alter validation status."""

    specifications = {
        "shoulder_tilt_deg": (
            "SHOULDER_TILT_JUMP_CANDIDATE",
            "shoulder_tilt_delta_deg",
            configuration.minimum_jump_tilt_deg,
        ),
        "shoulder_center_displacement_norm": (
            "SHOULDER_CENTER_DISPLACEMENT_CANDIDATE",
            "shoulder_center_displacement_norm",
            configuration.minimum_jump_displacement_norm,
        ),
        "shoulder_width_norm": (
            "SHOULDER_WIDTH_JUMP_CANDIDATE",
            "shoulder_width_delta_norm",
            configuration.minimum_jump_width_norm,
        ),
        "nose_shoulder_offset_x_norm": (
            "NOSE_SHOULDER_OFFSET_X_JUMP_CANDIDATE",
            "nose_offset_x_delta_norm",
            configuration.minimum_jump_offset_norm,
        ),
        "nose_shoulder_offset_y_norm": (
            "NOSE_SHOULDER_OFFSET_Y_JUMP_CANDIDATE",
            "nose_offset_y_delta_norm",
            configuration.minimum_jump_offset_norm,
        ),
        "face_shoulder_offset_x_norm": (
            "FACE_SHOULDER_OFFSET_X_JUMP_CANDIDATE",
            "face_offset_x_delta_norm",
            configuration.minimum_jump_offset_norm,
        ),
        "face_shoulder_offset_y_norm": (
            "FACE_SHOULDER_OFFSET_Y_JUMP_CANDIDATE",
            "face_offset_y_delta_norm",
            configuration.minimum_jump_offset_norm,
        ),
    }
    diagnostics: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for metric, (event_type, temporal_key, minimum) in specifications.items():
        magnitudes = [
            abs(float(row["posture_temporal"][temporal_key]))
            for row in rows
            if row["posture_temporal"][temporal_key] is not None
        ]
        diagnostic = _threshold(magnitudes, minimum, configuration)
        diagnostics[metric] = diagnostic
        threshold = diagnostic["threshold"]
        if threshold is None:
            continue
        for index, row in enumerate(rows):
            delta = row["posture_temporal"][temporal_key]
            if delta is None or abs(delta) <= threshold:
                continue
            current = (
                row["posture_raw"].get(metric)
                if metric != "shoulder_center_displacement_norm"
                else delta
            )
            previous = None
            if index > 0 and metric != "shoulder_center_displacement_norm":
                previous = rows[index - 1]["posture_raw"].get(metric)
            details = {
                "metric": metric,
                "previous_value": previous,
                "current_value": current,
                "delta": delta,
                "absolute_delta": abs(delta),
                "threshold": threshold,
                "median": diagnostic["median"],
                "mad": diagnostic["mad"],
                "method": diagnostic["method"],
                "status": "candidate",
            }
            events.append(
                PostureJumpEvent(
                    timestamp_ms=row["timestamp_ms"],
                    event_type=event_type,
                    target_id=row["target_id"],
                    details=details,
                ).to_dict()
            )
    events.sort(key=lambda event: (event["timestamp_ms"], event["event_type"]))
    return events, diagnostics
