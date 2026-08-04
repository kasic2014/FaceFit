"""Adapt registered Stage 26 physical/timing measurements, excluding transcript text."""

from __future__ import annotations

from typing import Any


def _get(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            return None
        value = value[component]
    return value


def adapt_speech_answer(session_id: str, answer: dict[str, Any], inventory: dict[str, Any], artifact_hash: str | None = None) -> list[dict[str, Any]]:
    answer_id = str(answer.get("answerId", ""))
    duration = int(_get(answer, "input.durationMs") or _get(answer, "speakingRate.answerDurationMs") or 0)
    words = int(_get(answer, "speakingRate.wordCount") or 0)
    total_frames = int(_get(answer, "pitch.totalFrameCount") or 0)
    voiced_frames = int(_get(answer, "pitch.voicedFrameCount") or 0)
    voiced_ratio = _get(answer, "pitch.voicedFrameRatio")
    rows: list[dict[str, Any]] = []
    for metric in inventory.get("metrics", []):
        if metric.get("sourceService") != "ANALYSIS" or metric.get("scope") != "ANSWER":
            continue
        rows.append({
            "sessionId": session_id,
            "answerId": answer_id,
            "metricId": metric["metricId"],
            "axis": metric["axis"],
            "value": _get(answer, metric["sourcePath"]),
            "unit": metric["unit"],
            "scope": "ANSWER",
            "quality": {
                "sampleCount": int(_get(answer, "input.sampleCount") or total_frames),
                "availabilityRatio": 1 if answer.get("status") in {"COMPLETE", "COMPLETE_WITH_WARNINGS"} else 0,
                "missingRatio": 0 if answer.get("status") in {"COMPLETE", "COMPLETE_WITH_WARNINGS"} else 1,
                "answerDurationMs": duration,
                "wordCount": words,
                "voicedFrameRatio": voiced_ratio,
                "timestampValid": "OVERLAPPING_WORD_TIMESTAMPS" not in answer.get("warnings", []),
                "validSampleCount": voiced_frames if metric["metricId"].startswith("SPEECH_F0") else int(_get(answer, "input.sampleCount") or 0),
            },
            "source": {"service": "ANALYSIS", "artifactHash": artifact_hash},
        })
    return rows
