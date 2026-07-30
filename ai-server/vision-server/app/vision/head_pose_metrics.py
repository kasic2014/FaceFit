"""Temporal summaries and diagnostic jump candidates for raw head pose."""

from __future__ import annotations

import math
import statistics
from typing import Any

from app.vision.head_pose_models import HeadPoseConfiguration


def calculate_axis_summary(values: list[float | None]) -> dict[str, float | int | None]:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not valid:
        return {"count": 0, "min": None, "max": None, "median": None, "mad": None, "mean": None, "standard_deviation": None}
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


def calculate_reprojection_summary(values: list[float | None]) -> dict[str, float | int | None]:
    summary = calculate_axis_summary(values)
    return {
        "count": summary["count"],
        "min": summary["min"],
        "max": summary["max"],
        "median": summary["median"],
        "mean": summary["mean"],
        "standard_deviation": summary["standard_deviation"],
    }


def calculate_angular_deltas(
    rows: list[dict[str, Any]],
) -> list[dict[str, float | None]]:
    output, previous = [], None
    for row in rows:
        pose = row["head_pose"]
        if not pose["available"]:
            output.append({"yaw_delta_deg": None, "pitch_delta_deg": None, "roll_delta_deg": None})
            previous = None
            continue
        current = (pose["yaw_deg"], pose["pitch_deg"], pose["roll_deg"])
        if previous is None:
            output.append({"yaw_delta_deg": None, "pitch_delta_deg": None, "roll_delta_deg": None})
        else:
            output.append({
                "yaw_delta_deg": abs(current[0] - previous[0]),
                "pitch_delta_deg": abs(current[1] - previous[1]),
                "roll_delta_deg": abs(current[2] - previous[2]),
            })
        previous = current
    return output


def detect_angular_jump_candidates(
    rows: list[dict[str, Any]],
    configuration: HeadPoseConfiguration = HeadPoseConfiguration(),
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    deltas = calculate_angular_deltas(rows)
    events, diagnostics = [], {}
    for axis in ("yaw", "pitch", "roll"):
        key = f"{axis}_delta_deg"
        valid = [item[key] for item in deltas if item[key] is not None]
        median = statistics.median(valid) if valid else None
        mad = statistics.median(abs(value - median) for value in valid) if valid else None
        if len(valid) < configuration.minimum_jump_deltas:
            threshold, method = None, "insufficient_data"
        elif mad and mad > 0:
            threshold = median + configuration.jump_mad_multiplier * mad
            method = "median_plus_k_mad"
        else:
            threshold = max(configuration.jump_fallback_threshold_deg, (median or 0.0) * 3.0)
            method = "zero_mad_configured_fallback"
        diagnostics[axis] = {"median_delta_deg": median, "mad_delta_deg": mad, "threshold_deg": threshold, "method": method}
        if threshold is None:
            continue
        for index, (row, delta) in enumerate(zip(rows, deltas)):
            if delta[key] is None or delta[key] <= threshold:
                continue
            previous = rows[index - 1]["head_pose"]
            current = row["head_pose"]
            events.append({
                "timestamp_ms": row["timestamp_ms"],
                "event_type": "HEAD_POSE_ANGULAR_JUMP_CANDIDATE",
                "target_id": row["target_id"],
                "details": {
                    "axis": axis,
                    "previous_deg": previous[f"{axis}_deg"],
                    "current_deg": current[f"{axis}_deg"],
                    "delta_deg": delta[key],
                    "median_delta_deg": median,
                    "mad_delta_deg": mad,
                    "threshold_deg": threshold,
                    "method": method,
                    "status": "candidate",
                },
            })
    events.sort(key=lambda item: (item["timestamp_ms"], item["details"]["axis"]))
    return events, diagnostics
