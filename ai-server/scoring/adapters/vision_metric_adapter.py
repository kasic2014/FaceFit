"""Adapt registered Stage 10 Vision interval metrics without inventing values."""

from __future__ import annotations

from typing import Any


def _get(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            return None
        value = value[component]
    return value


def adapt_vision_answer(session_id: str, answer_id: str, aggregate: dict[str, Any], inventory: dict[str, Any], artifact_hash: str | None = None) -> list[dict[str, Any]]:
    quality = aggregate.get("data_quality", {})
    rows: list[dict[str, Any]] = []
    for metric in inventory.get("metrics", []):
        if metric.get("sourceService") != "VISION" or metric.get("scope") != "ANSWER" or metric.get("dataQualityOnly"):
            continue
        value = _get(aggregate, metric["sourcePath"])
        availability_group = "head_pose.availability" if metric["axis"] == "GAZE_HEAD" else "posture.shoulder_availability"
        availability = _get(aggregate, availability_group) or {}
        parent = _get(aggregate, metric["sourcePath"].rsplit(".", 1)[0]) or {}
        rows.append({
            "sessionId": session_id,
            "answerId": answer_id,
            "metricId": metric["metricId"],
            "axis": metric["axis"],
            "value": value,
            "unit": metric["unit"],
            "scope": "ANSWER",
            "quality": {
                "sampleCount": int(parent.get("count", quality.get("total_frame_count", 0)) or 0),
                "availabilityRatio": availability.get("availability_ratio", quality.get("head_pose_availability_ratio" if metric["axis"] == "GAZE_HEAD" else "posture_availability_ratio")),
                "missingRatio": None if availability.get("availability_ratio") is None else 1 - float(availability["availability_ratio"]),
                "answerDurationMs": int(aggregate.get("duration_ms", 0) or 0),
                "wordCount": None,
                "voicedFrameRatio": None,
                "timestampValid": not bool(aggregate.get("errors")),
            },
            "source": {"service": "VISION", "artifactHash": artifact_hash},
        })
    return rows
