"""Export deterministic Backend handoff schemas and synthetic examples.

The FastAPI applications are imported only to verify public paths and status
enums. No server is started and no real Session result is exported.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Sequence


HANDOFF_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
SESSION_PATTERN = r"^SES_\d{6}$"
ANSWER_PATTERN = r"^ANS_\d{6}$"
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
DATE_TIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"

VISION_PATHS = {
    "/health",
    "/ready",
    "/api/v1/vision/jobs",
    "/api/v1/vision/jobs/{job_id}",
    "/api/v1/vision/sessions/{session_id}/feedback",
}
ANALYSIS_PATHS = {
    "/health",
    "/ready",
    "/api/v1/analysis/jobs",
    "/api/v1/analysis/jobs/{job_id}",
    "/api/v1/analysis/sessions/{session_id}/transcription",
    "/api/v1/analysis/sessions/{session_id}/speech-characteristics",
}
VISION_STATUSES = [
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "SUCCEEDED_WITH_LIMITATIONS",
    "FAILED",
]
ANALYSIS_STATUSES = [
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "SUCCEEDED_WITH_WARNINGS",
    "FAILED",
]


def _ensure_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON value")
    if isinstance(value, dict):
        for item in value.values():
            _ensure_finite(item)
    elif isinstance(value, list):
        for item in value:
            _ensure_finite(item)


def _write_json(path: Path, value: Any) -> None:
    _ensure_finite(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _default_python(server_root: Path) -> Path:
    candidates = (
        server_root / ".venv" / "Scripts" / "python.exe",
        server_root / ".venv" / "bin" / "python",
    )
    return next((path for path in candidates if path.is_file()), Path(sys.executable))


def _load_openapi(server_root: Path, python_executable: Path) -> dict[str, Any]:
    code = (
        "import json; from app.main import create_app; "
        "print(json.dumps(create_app().openapi(), allow_nan=False, separators=(',', ':')))"
    )
    completed = subprocess.run(
        [str(python_executable), "-c", code],
        cwd=server_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"OpenAPI export failed for {server_root.name} with exit {completed.returncode}."
        )
    try:
        schema = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAPI output is invalid for {server_root.name}.") from exc
    if not isinstance(schema, dict):
        raise RuntimeError("OpenAPI root is invalid")
    return schema


def _object(
    title: str,
    properties: dict[str, Any],
    required: list[str],
    *,
    additional: bool = False,
    description: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "$schema": SCHEMA_URI,
        "title": title,
        "type": "object",
        "additionalProperties": additional,
        "properties": properties,
        "required": required,
    }
    if description:
        result["description"] = description
    return result


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _timestamp(nullable: bool = False) -> dict[str, Any]:
    value = {"type": "string", "pattern": DATE_TIME_PATTERN, "description": "ISO-8601 UTC"}
    return _nullable(value) if nullable else value


def _warning() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["source", "code", "message", "answerId", "reviewRequired"],
        "properties": {
            "source": {"type": "string", "enum": ["VISION", "TRANSCRIPTION", "SPEECH", "INTEGRATION"]},
            "code": {"type": "string", "minLength": 1},
            "message": {"type": "string", "minLength": 1},
            "answerId": _nullable({"type": "string", "pattern": ANSWER_PATTERN}),
            "reviewRequired": {"type": "boolean"},
        },
    }


def _source_warning() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "message", "answerId", "reviewRequired"],
        "properties": {
            "code": {"type": "string", "minLength": 1},
            "message": {"type": "string", "minLength": 1},
            "answerId": _nullable({"type": "string", "pattern": ANSWER_PATTERN}),
            "reviewRequired": {"type": "boolean"},
        },
    }


def _job_error() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "message"],
        "properties": {
            "code": {"type": "string", "minLength": 1},
            "message": {"type": "string", "minLength": 1},
        },
    }


def schemas() -> dict[str, dict[str, Any]]:
    session_id = {"type": "string", "pattern": SESSION_PATTERN}
    answer_id = {"type": "string", "pattern": ANSWER_PATTERN}
    job_id = {"type": "string", "pattern": UUID_PATTERN}
    common_job = _object(
        "Common AI Job Contract",
        {
            "jobId": job_id,
            "sessionId": session_id,
            "status": {"type": "string", "enum": sorted(set(VISION_STATUSES + ANALYSIS_STATUSES))},
            "createdAt": _timestamp(),
            "startedAt": _timestamp(True),
            "completedAt": _timestamp(True),
            "resultAvailable": {"type": "boolean"},
            "warnings": {"type": "array", "items": _source_warning()},
            "error": _nullable(_job_error()),
        },
        [
            "jobId", "sessionId", "status", "createdAt", "startedAt",
            "completedAt", "resultAvailable", "warnings", "error",
        ],
        additional=True,
        description="Shared fields only; service-specific Job fields are permitted.",
    )
    vision_request = _object(
        "Vision Job Request",
        {
            "sessionId": session_id,
            "analysisMode": {"type": "string", "const": "SINGLE_SESSION_BASELINE_RELATIVE_MVP"},
            "forceRebuild": {"type": "boolean", "default": False},
        },
        ["sessionId", "analysisMode", "forceRebuild"],
    )
    vision_response = _object(
        "Vision Job Response",
        {
            "jobId": job_id,
            "sessionId": session_id,
            "analysisMode": {"type": "string", "const": "SINGLE_SESSION_BASELINE_RELATIVE_MVP"},
            "status": {"type": "string", "enum": VISION_STATUSES},
            "createdAt": _timestamp(),
            "startedAt": _timestamp(True),
            "completedAt": _timestamp(True),
            "resultAvailable": {"type": "boolean"},
            "warnings": {"type": "array", "items": _source_warning()},
            "error": _nullable(_job_error()),
        },
        [
            "jobId", "sessionId", "analysisMode", "status", "createdAt",
            "startedAt", "completedAt", "resultAvailable", "warnings", "error",
        ],
    )
    analysis_request = _object(
        "Analysis Job Request",
        {
            "sessionId": session_id,
            "pipeline": {
                "type": "string",
                "enum": ["STT_TRANSCRIPTION", "SPEECH_CHARACTERISTICS", "STT_AND_SPEECH"],
            },
            "forceRebuild": {"type": "boolean", "default": False},
        },
        ["sessionId", "pipeline", "forceRebuild"],
    )
    analysis_response = _object(
        "Analysis Job Response",
        {
            "jobId": job_id,
            "sessionId": session_id,
            "pipeline": {
                "type": "string",
                "enum": ["STT_TRANSCRIPTION", "SPEECH_CHARACTERISTICS", "STT_AND_SPEECH"],
            },
            "status": {"type": "string", "enum": ANALYSIS_STATUSES},
            "createdAt": _timestamp(),
            "queuedAt": _timestamp(),
            "startedAt": _timestamp(True),
            "completedAt": _timestamp(True),
            "updatedAt": _timestamp(),
            "queueWaitMs": _nullable({"type": "integer", "minimum": 0}),
            "executionDurationMs": _nullable({"type": "integer", "minimum": 0}),
            "totalDurationMs": _nullable({"type": "integer", "minimum": 0}),
            "resultAvailable": {"type": "boolean"},
            "warnings": {"type": "array", "items": _source_warning()},
            "error": _nullable(_job_error()),
        },
        [
            "jobId", "sessionId", "pipeline", "status", "createdAt", "queuedAt",
            "startedAt", "completedAt", "updatedAt", "queueWaitMs",
            "executionDurationMs", "totalDurationMs", "resultAvailable", "warnings", "error",
        ],
    )
    interval = {
        "type": "object",
        "additionalProperties": True,
        "required": ["startTimestampMs", "endTimestampMs"],
        "properties": {
            "startTimestampMs": {"type": "integer", "minimum": 0},
            "endTimestampMs": {"type": "integer", "minimum": 1},
            "rule": {"type": "string", "const": "[start, end)"},
        },
    }
    vision_feedback = _object(
        "Vision Feedback Response",
        {
            "sessionId": session_id,
            "status": {"type": "string", "minLength": 1},
            "analysisMode": {"type": "string", "const": "SINGLE_SESSION_BASELINE_RELATIVE_MVP"},
            "scores": {"type": "null", "description": "Scoring is unavailable."},
            "scoringUnavailableReasons": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
            },
            "measurementSummary": {"type": "object", "additionalProperties": True},
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["answerId", "interval"],
                    "properties": {"answerId": answer_id, "interval": interval},
                },
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
            "limitations": {"type": "array", "items": {"type": "string"}},
            "disclaimer": {"type": "string"},
        },
        [
            "sessionId", "status", "analysisMode", "scores",
            "scoringUnavailableReasons", "measurementSummary", "answers",
            "warnings", "limitations", "disclaimer",
        ],
        additional=True,
        description="Runtime permits measurement-specific fields while forbidding scores other than null.",
    )
    timestamp_item = {
        "type": "object",
        "additionalProperties": True,
        "required": ["startMsSession", "endMsSession", "text"],
        "properties": {
            "startMsSession": {"type": "integer", "minimum": 0},
            "endMsSession": {"type": "integer", "minimum": 1},
            "text": _nullable({"type": "string"}),
        },
    }
    transcription = _object(
        "Transcription Response",
        {
            "sessionId": session_id,
            "status": {"type": "string", "minLength": 1},
            "engine": {"type": "object", "additionalProperties": True},
            "options": {"type": "object", "additionalProperties": True},
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "answerId", "status", "language", "textExposed", "text",
                        "segmentCount", "wordCount", "segments", "words", "warnings",
                    ],
                    "properties": {
                        "answerId": answer_id,
                        "status": {"type": "string"},
                        "language": {"type": "object", "additionalProperties": True},
                        "textExposed": {"type": "boolean"},
                        "text": _nullable({"type": "string"}),
                        "segmentCount": {"type": "integer", "minimum": 0},
                        "wordCount": {"type": "integer", "minimum": 0},
                        "segments": {"type": "array", "items": timestamp_item},
                        "words": {"type": "array", "items": timestamp_item},
                        "warnings": {"type": "array", "items": _source_warning()},
                    },
                },
            },
            "warnings": {"type": "array", "items": _source_warning()},
            "errors": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        },
        ["sessionId", "status", "engine", "options", "answers", "warnings", "errors"],
    )
    speech_answer = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "answerId", "status", "speakingRate", "timestampPauses", "acousticSilence",
            "fillerCandidates", "volume", "pitch", "warnings",
        ],
        "properties": {
            "answerId": answer_id,
            "status": {"type": "string"},
            "speakingRate": {"type": "object", "additionalProperties": True},
            "timestampPauses": {"type": "object", "additionalProperties": True},
            "acousticSilence": {"type": "object", "additionalProperties": True},
            "fillerCandidates": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "volume": {"type": "object", "additionalProperties": True},
            "pitch": {"type": "object", "additionalProperties": True},
            "warnings": {"type": "array", "items": _source_warning()},
        },
    }
    speech = _object(
        "Speech Characteristics Response",
        {
            "sessionId": session_id,
            "status": {"type": "string"},
            "analysisMode": {"type": "string", "const": "MEASUREMENT_ONLY"},
            "scoringAvailable": {"type": "boolean", "const": False},
            "thresholdApproval": {"type": "boolean", "const": False},
            "answers": {"type": "array", "items": speech_answer},
            "aggregate": {"type": "object", "additionalProperties": True},
            "warnings": {"type": "array", "items": _source_warning()},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        [
            "sessionId", "status", "analysisMode", "scoringAvailable",
            "thresholdApproval", "answers", "aggregate", "warnings", "limitations",
        ],
    )
    component = {
        "type": "object",
        "additionalProperties": True,
        "required": ["status", "sourceStatus", "answerCount"],
        "properties": {
            "status": {
                "type": "string",
                "enum": ["READY", "READY_WITH_WARNINGS", "NOT_READY", "FAILED", "UNAVAILABLE"],
            },
            "sourceStatus": {"type": "string"},
            "answerCount": {"type": "integer", "minimum": 0},
        },
    }
    integrated_answer = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "answerId", "interval", "vision", "transcription",
            "speechCharacteristics", "warnings",
        ],
        "properties": {
            "answerId": answer_id,
            "interval": {
                "type": "object",
                "additionalProperties": False,
                "required": ["startMs", "endMs", "durationMs"],
                "properties": {
                    "startMs": {"type": "integer", "minimum": 0},
                    "endMs": {"type": "integer", "minimum": 1},
                    "durationMs": {"type": "integer", "minimum": 1},
                },
            },
            "vision": {"type": "object", "additionalProperties": True},
            "transcription": {"type": "object", "additionalProperties": True},
            "speechCharacteristics": {"type": "object", "additionalProperties": True},
            "warnings": {"type": "array", "items": _warning()},
        },
    }
    integrated = _object(
        "Integrated Session Response",
        {
            "sessionId": session_id,
            "status": {
                "type": "string",
                "enum": [
                    "INTEGRATED_READY", "INTEGRATED_READY_WITH_WARNINGS",
                    "INTEGRATED_PARTIAL", "INTEGRATED_FAILED",
                ],
            },
            "generatedAt": _timestamp(),
            "scoringAvailable": {"type": "boolean", "const": False},
            "scoringUnavailableReasons": {"type": "array", "items": {"type": "string"}, "minItems": 2},
            "components": {
                "type": "object",
                "additionalProperties": False,
                "required": ["vision", "transcription", "speechCharacteristics"],
                "properties": {
                    "vision": component,
                    "transcription": component,
                    "speechCharacteristics": component,
                },
            },
            "answers": {"type": "array", "items": integrated_answer},
            "warnings": {"type": "array", "items": _warning()},
            "limitations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["source", "code", "message"], "properties": {"source": {"type": "string"}, "code": {"type": "string"}, "message": {"type": "string"}}}},
            "errors": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["source", "code", "message", "retryable"], "properties": {"source": {"type": "string"}, "code": {"type": "string"}, "message": {"type": "string"}, "retryable": {"type": "boolean"}}}},
        },
        [
            "sessionId", "status", "generatedAt", "scoringAvailable",
            "scoringUnavailableReasons", "components", "answers", "warnings",
            "limitations", "errors",
        ],
    )
    return {
        "common-job-contract.schema.json": common_job,
        "vision-job-request.schema.json": vision_request,
        "vision-job-response.schema.json": vision_response,
        "analysis-job-request.schema.json": analysis_request,
        "analysis-job-response.schema.json": analysis_response,
        "vision-feedback.schema.json": vision_feedback,
        "transcription-response.schema.json": transcription,
        "speech-characteristics-response.schema.json": speech,
        "integrated-session.schema.json": integrated,
    }


def _source_warning_example(code: str, message: str, answer_id: str | None = None, review: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message, "answerId": answer_id, "reviewRequired": review}


def examples() -> dict[str, dict[str, Any]]:
    timestamp = "2026-08-03T00:00:00Z"
    vision_job_id = "00000000-0000-4000-8000-000000000001"
    analysis_job_id = "00000000-0000-4000-8000-000000000002"
    warning = _source_warning_example(
        "HEAD_POSE_PARTIAL_AVAILABILITY",
        "Head Pose measurements are partially available.",
    )
    intervals = [(11000, 50000), (51000, 107000), (108000, 160000), (161000, 192000)]
    integrated_answers = []
    for index, (start, end) in enumerate(intervals, start=1):
        integrated_answers.append(
            {
                "answerId": f"ANS_{index:06d}",
                "interval": {"startMs": start, "endMs": end, "durationMs": end - start},
                "vision": {"status": "READY_WITH_WARNINGS", "measurementSummary": {"sampleCount": 100}},
                "transcription": {"status": "READY_WITH_WARNINGS", "language": "ko", "segmentCount": [6, 8, 9, 4][index - 1], "wordCount": [68, 91, 94, 54][index - 1]},
                "speechCharacteristics": {"status": "READY_WITH_WARNINGS", "speakingRate": {"wordsPerMinute": 100.0}, "timestampPauses": {}, "volume": {"rmsDbfs": -30.0}, "pitch": {"medianF0Hz": 110.0}, "fillerCandidateCount": 1 if index == 4 else 0},
                "warnings": [],
            }
        )
    return {
        "vision-job-request.json": {
            "sessionId": "SES_000001",
            "analysisMode": "SINGLE_SESSION_BASELINE_RELATIVE_MVP",
            "forceRebuild": False,
        },
        "vision-job-response.json": {
            "jobId": vision_job_id,
            "sessionId": "SES_000001",
            "analysisMode": "SINGLE_SESSION_BASELINE_RELATIVE_MVP",
            "status": "SUCCEEDED_WITH_LIMITATIONS",
            "createdAt": timestamp,
            "startedAt": timestamp,
            "completedAt": timestamp,
            "resultAvailable": True,
            "warnings": [warning],
            "error": None,
        },
        "analysis-job-request.json": {
            "sessionId": "SES_000001",
            "pipeline": "STT_AND_SPEECH",
            "forceRebuild": False,
        },
        "analysis-job-response.json": {
            "jobId": analysis_job_id,
            "sessionId": "SES_000001",
            "pipeline": "STT_AND_SPEECH",
            "status": "SUCCEEDED_WITH_WARNINGS",
            "createdAt": timestamp,
            "queuedAt": timestamp,
            "startedAt": timestamp,
            "completedAt": timestamp,
            "updatedAt": timestamp,
            "queueWaitMs": 0,
            "executionDurationMs": 0,
            "totalDurationMs": 0,
            "resultAvailable": True,
            "warnings": [_source_warning_example("UPSTREAM_TRANSCRIPTION_WARNING", "Existing transcription warnings are retained.")],
            "error": None,
        },
        "vision-feedback.json": {
            "sessionId": "SES_000001",
            "status": "single_session_mvp_feedback_ready_with_measurement_limitations",
            "analysisMode": "SINGLE_SESSION_BASELINE_RELATIVE_MVP",
            "scores": None,
            "scoringUnavailableReasons": ["SCORING_NOT_AVAILABLE_SINGLE_SESSION_MVP", "THRESHOLD_EVIDENCE_NOT_APPROVED"],
            "measurementSummary": {"answerCount": 4, "thresholdsUsed": False, "scoringPerformed": False},
            "answers": [
                {"answerId": f"ANS_{i:06d}", "interval": {"startTimestampMs": start, "endTimestampMs": end, "rule": "[start, end)"}, "sampleCount": 100}
                for i, (start, end) in enumerate(intervals, start=1)
            ],
            "warnings": ["Head Pose measurements are partially available."],
            "limitations": ["Single-Session baseline-relative measurement only."],
            "disclaimer": "Measurements are not interview scores or hiring decisions.",
        },
        "transcription-response-redacted.json": {
            "sessionId": "SES_000001",
            "status": "stt_session_transcription_ready_with_warnings",
            "engine": {"name": "faster-whisper", "model": "large-v3-turbo"},
            "options": {"language": "ko", "wordTimestamps": True, "timestampToleranceMs": 1},
            "answers": [
                {
                    "answerId": "ANS_000001",
                    "status": "COMPLETE_WITH_WARNINGS",
                    "language": {"detected": "ko"},
                    "textExposed": False,
                    "text": None,
                    "segmentCount": 6,
                    "wordCount": 68,
                    "segments": [{"startMsSession": 11000, "endMsSession": 11500, "text": None}],
                    "words": [{"startMsSession": 11000, "endMsSession": 11500, "text": None}],
                    "warnings": [_source_warning_example("SEGMENT_BOUNDARY_EXPANDED_TO_WORDS", "Segment boundary follows word timestamps.", "ANS_000001")],
                }
            ],
            "warnings": [],
            "errors": [],
        },
        "speech-characteristics-response.json": {
            "sessionId": "SES_000001",
            "status": "speech_characteristics_ready_with_warnings",
            "analysisMode": "MEASUREMENT_ONLY",
            "scoringAvailable": False,
            "thresholdApproval": False,
            "answers": [
                {
                    "answerId": "ANS_000004",
                    "status": "COMPLETE_WITH_WARNINGS",
                    "speakingRate": {"wordsPerMinute": 100.0},
                    "timestampPauses": {},
                    "acousticSilence": {},
                    "fillerCandidates": [{"startMsSession": 161100, "endMsSession": 161200}],
                    "volume": {"rmsDbfs": -30.0},
                    "pitch": {"medianF0Hz": 110.0},
                    "warnings": [_source_warning_example("FILLER_CANDIDATE_REVIEW_REQUIRED", "Filler candidates require human review.", "ANS_000004", True)],
                }
            ],
            "aggregate": {"answerCount": 4, "totalWordCount": 307, "totalFillerCandidateCount": 1},
            "warnings": [],
            "limitations": ["Measurements are technical observations, not scores."],
        },
        "integrated-session-response.json": {
            "sessionId": "SES_000001",
            "status": "INTEGRATED_READY_WITH_WARNINGS",
            "generatedAt": timestamp,
            "scoringAvailable": False,
            "scoringUnavailableReasons": ["SCORING_NOT_AVAILABLE_SINGLE_SESSION_MVP", "THRESHOLD_EVIDENCE_NOT_APPROVED"],
            "components": {
                "vision": {"status": "READY_WITH_WARNINGS", "sourceStatus": "SUCCEEDED_WITH_LIMITATIONS", "answerCount": 4},
                "transcription": {"status": "READY_WITH_WARNINGS", "sourceStatus": "SUCCEEDED_WITH_WARNINGS", "answerCount": 4, "language": "ko", "segmentCount": 27, "wordCount": 307, "textExposed": False},
                "speechCharacteristics": {"status": "READY_WITH_WARNINGS", "sourceStatus": "SUCCEEDED_WITH_WARNINGS", "answerCount": 4, "fillerCandidateCount": 1, "pitchAvailableAnswerCount": 4},
            },
            "answers": integrated_answers,
            "warnings": [{"source": "VISION", "code": "HEAD_POSE_PARTIAL_AVAILABILITY", "message": "Head Pose measurements are partially available.", "answerId": None, "reviewRequired": False}],
            "limitations": [{"source": "INTEGRATION", "code": "ANALYSIS_DOCKER_GPU_FORCE_REBUILD_NOT_VERIFIED", "message": "GPU forceRebuild transcription remains unverified."}],
            "errors": [],
        },
        "common-error-response.json": {
            "code": "RESULT_NOT_READY",
            "message": "The requested component result is not ready.",
            "requestId": "00000000-0000-4000-8000-000000000003",
            "details": [],
        },
        "common-warning.json": {
            "source": "SPEECH",
            "code": "FILLER_CANDIDATE_REVIEW_REQUIRED",
            "message": "Filler candidates require human review.",
            "answerId": "ANS_000004",
            "reviewRequired": True,
        },
    }


def _openapi_enum(schema: dict[str, Any], name: str) -> list[str]:
    value = schema.get("components", {}).get("schemas", {}).get(name, {}).get("enum")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"OpenAPI enum {name} is missing")
    return value


def validate_openapi(vision: dict[str, Any], analysis: dict[str, Any]) -> None:
    if not VISION_PATHS.issubset(set(vision.get("paths", {}))):
        raise RuntimeError("Vision OpenAPI is missing required public paths")
    if not ANALYSIS_PATHS.issubset(set(analysis.get("paths", {}))):
        raise RuntimeError("Analysis OpenAPI is missing required public paths")
    if _openapi_enum(vision, "JobStatus") != VISION_STATUSES:
        raise RuntimeError("Vision JobStatus no longer matches the handoff contract")
    if _openapi_enum(analysis, "JobStatus") != ANALYSIS_STATUSES:
        raise RuntimeError("Analysis JobStatus no longer matches the handoff contract")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Export Stage 29 Backend handoff contracts.")
    result.add_argument(
        "--repo-root",
        type=Path,
        default=HANDOFF_ROOT.parents[2],
        help="Repository root containing ai-server.",
    )
    result.add_argument("--output-root", type=Path, default=HANDOFF_ROOT)
    result.add_argument("--vision-python", type=Path)
    result.add_argument("--analysis-python", type=Path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    vision_root = repo_root / "ai-server" / "vision-server"
    analysis_root = repo_root / "ai-server" / "analysis-server"
    vision = _load_openapi(
        vision_root, args.vision_python or _default_python(vision_root)
    )
    analysis = _load_openapi(
        analysis_root, args.analysis_python or _default_python(analysis_root)
    )
    validate_openapi(vision, analysis)
    for name, value in schemas().items():
        _write_json(args.output_root / "contracts" / name, value)
    for name, value in examples().items():
        _write_json(args.output_root / "examples" / name, value)
    print(
        json.dumps(
            {
                "status": "exported",
                "schemaCount": len(schemas()),
                "exampleCount": len(examples()),
                "visionRequiredPathCount": len(VISION_PATHS),
                "analysisRequiredPathCount": len(ANALYSIS_PATHS),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
