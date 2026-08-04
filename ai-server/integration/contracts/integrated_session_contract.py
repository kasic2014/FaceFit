"""Build the sanitized Stage 28 integrated Session result."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .common_contracts import (
    deduplicate_warnings,
    map_component_status,
    normalize_warning,
    utc_timestamp,
    validate_public_payload,
    validate_session_id,
)


SCORING_UNAVAILABLE_REASONS = [
    "SCORING_NOT_AVAILABLE_SINGLE_SESSION_MVP",
    "THRESHOLD_EVIDENCE_NOT_APPROVED",
]
GPU_LIMITATION = {
    "source": "INTEGRATION",
    "code": "ANALYSIS_DOCKER_GPU_FORCE_REBUILD_NOT_VERIFIED",
    "message": "GPU forceRebuild transcription remains unverified; existing results are reused.",
}


def _status(source: str, result: dict[str, Any] | None, job: dict[str, Any] | None) -> dict[str, str]:
    if result is None:
        source_status = str(job.get("status", "UNAVAILABLE")) if job is not None else "UNAVAILABLE"
        return {
            "status": "FAILED" if source_status == "FAILED" else "UNAVAILABLE",
            "sourceStatus": source_status,
        }
    if job is not None:
        source_status = str(job.get("status", ""))
    else:
        source_status = str(result.get("status", ""))
    return {
        "status": map_component_status(source, source_status),
        "sourceStatus": source_status,
    }


def _warnings(source: str, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    result: list[dict[str, Any]] = []
    rows = payload.get("warnings", [])
    if isinstance(rows, list):
        for warning in rows:
            result.append(normalize_warning(source, warning))
    answers = payload.get("answers", [])
    if isinstance(answers, list):
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            answer_id = answer.get("answerId")
            answer_warnings = answer.get("warnings", [])
            if isinstance(answer_warnings, list):
                for warning in answer_warnings:
                    result.append(normalize_warning(source, warning, answer_id=answer_id))
            if source == "VISION":
                head = answer.get("headPoseMeasurement", {})
                if isinstance(head, dict) and head.get("status") == "PARTIAL":
                    result.append(
                        normalize_warning(
                            "VISION",
                            {
                                "code": "HEAD_POSE_PARTIAL_AVAILABILITY",
                                "message": "Head Pose measurement is partially available for this answer.",
                            },
                            answer_id=answer_id,
                        )
                    )
    return result


def _answer_map(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if payload is None or not isinstance(payload.get("answers"), list):
        return {}
    return {
        str(row.get("answerId")): row
        for row in payload["answers"]
        if isinstance(row, dict) and isinstance(row.get("answerId"), str)
    }


def _language(answer: dict[str, Any]) -> str | None:
    language = answer.get("language")
    if isinstance(language, str):
        return language
    if isinstance(language, dict):
        value = language.get("detected", language.get("requested"))
        return value if isinstance(value, str) else None
    return None


def _answer_component_status(source: str, row: dict[str, Any] | None) -> str:
    if row is None:
        return "UNAVAILABLE"
    status = map_component_status(source, row.get("status"))
    warnings = row.get("warnings", [])
    if status == "READY" and isinstance(warnings, list) and warnings:
        return "READY_WITH_WARNINGS"
    return status


def _vision_answer(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {"status": "UNAVAILABLE", "measurementSummary": {}}
    summary_keys = (
        "sampleCount",
        "faceDetection",
        "bothShouldersDetection",
        "headPoseMeasurement",
        "postureMeasurement",
        "relativeMetricSummary",
    )
    return {
        "status": _answer_component_status("VISION", row),
        "measurementSummary": {
            key: deepcopy(row[key]) for key in summary_keys if key in row
        },
    }


def _transcription_answer(row: dict[str, Any] | None, expose_text: bool) -> dict[str, Any]:
    if row is None:
        return {
            "status": "UNAVAILABLE",
            "language": None,
            "segmentCount": 0,
            "wordCount": 0,
        }
    result: dict[str, Any] = {
        "status": _answer_component_status("TRANSCRIPTION", row),
        "language": _language(row),
        "segmentCount": int(row.get("segmentCount", 0)),
        "wordCount": int(row.get("wordCount", 0)),
    }
    if expose_text:
        result["text"] = row.get("text")
        result["segments"] = deepcopy(row.get("segments", []))
        result["words"] = deepcopy(row.get("words", []))
    return result


def _speech_answer(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "status": "UNAVAILABLE",
            "speakingRate": {},
            "timestampPauses": {},
            "volume": {},
            "pitch": {},
            "fillerCandidateCount": 0,
        }
    fillers = row.get("fillerCandidates", [])
    return {
        "status": _answer_component_status("SPEECH", row),
        "speakingRate": deepcopy(row.get("speakingRate", {})),
        "timestampPauses": deepcopy(row.get("timestampPauses", {})),
        "volume": deepcopy(row.get("volume", {})),
        "pitch": deepcopy(row.get("pitch", {})),
        "fillerCandidateCount": len(fillers) if isinstance(fillers, list) else 0,
    }


def _final_status(
    component_statuses: list[str], warnings: list[Any], limitations: list[Any], errors: list[Any]
) -> str:
    if errors:
        mandatory = {
            "SESSION_ID_MISMATCH",
            "ANSWER_SET_MISMATCH",
            "ANSWER_INTERVAL_MISMATCH",
            "TIMESTAMP_OUT_OF_RANGE",
            "COMPONENT_RESPONSE_INVALID",
        }
        if any(error.get("code") in mandatory for error in errors if isinstance(error, dict)):
            return "INTEGRATED_FAILED"
    usable = sum(status in {"READY", "READY_WITH_WARNINGS"} for status in component_statuses)
    unavailable = sum(status in {"NOT_READY", "FAILED", "UNAVAILABLE"} for status in component_statuses)
    if usable == len(component_statuses):
        if warnings or limitations or "READY_WITH_WARNINGS" in component_statuses:
            return "INTEGRATED_READY_WITH_WARNINGS"
        return "INTEGRATED_READY"
    if usable and unavailable:
        return "INTEGRATED_PARTIAL"
    return "INTEGRATED_FAILED"


def build_integrated_session(
    *,
    session_id: str,
    vision: dict[str, Any] | None,
    transcription: dict[str, Any] | None,
    speech: dict[str, Any] | None,
    validation: dict[str, Any],
    jobs: dict[str, dict[str, Any] | None] | None = None,
    component_errors: list[dict[str, Any]] | None = None,
    expose_transcript_text: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Create the Backend-facing, privacy-minimized integrated contract."""

    validate_session_id(session_id)
    jobs = jobs or {}
    vision_status = _status("VISION", vision, jobs.get("vision"))
    transcription_status = _status("TRANSCRIPTION", transcription, jobs.get("analysis"))
    speech_status = _status("SPEECH", speech, jobs.get("analysis"))

    vision_answers = _answer_map(vision)
    transcription_answers = _answer_map(transcription)
    speech_answers = _answer_map(speech)
    answer_ids = validation.get("answerIds", [])
    intervals = validation.get("intervals", {})

    warnings = deduplicate_warnings(
        _warnings("VISION", vision)
        + _warnings("TRANSCRIPTION", transcription)
        + _warnings("SPEECH", speech)
    )
    limitations: list[dict[str, Any]] = [deepcopy(GPU_LIMITATION)]
    if vision is not None and isinstance(vision.get("limitations"), list):
        for index, message in enumerate(vision["limitations"], start=1):
            if isinstance(message, str):
                limitations.append(
                    {
                        "source": "VISION",
                        "code": f"VISION_MEASUREMENT_LIMITATION_{index}",
                        "message": message,
                    }
                )
    errors = deepcopy(validation.get("errors", [])) + deepcopy(component_errors or [])

    answers: list[dict[str, Any]] = []
    for answer_id in answer_ids:
        answer_warnings = [
            deepcopy(item) for item in warnings if item.get("answerId") == answer_id
        ]
        interval = intervals.get(answer_id, {"startMs": 0, "endMs": 0, "durationMs": 0})
        answers.append(
            {
                "answerId": answer_id,
                "interval": deepcopy(interval),
                "vision": _vision_answer(vision_answers.get(answer_id)),
                "transcription": _transcription_answer(
                    transcription_answers.get(answer_id), expose_transcript_text
                ),
                "speechCharacteristics": _speech_answer(speech_answers.get(answer_id)),
                "warnings": answer_warnings,
            }
        )

    vision_summary = {
        **vision_status,
        "answerCount": len(vision_answers),
        "measurementSummary": deepcopy(vision.get("measurementSummary", {})) if vision else {},
    }
    transcript_rows = list(transcription_answers.values())
    transcription_summary = {
        **transcription_status,
        "answerCount": len(transcript_rows),
        "language": _language(transcript_rows[0]) if transcript_rows else None,
        "segmentCount": sum(int(row.get("segmentCount", 0)) for row in transcript_rows),
        "wordCount": sum(int(row.get("wordCount", 0)) for row in transcript_rows),
        "textExposed": bool(expose_transcript_text),
    }
    speech_rows = list(speech_answers.values())
    speech_summary = {
        **speech_status,
        "answerCount": len(speech_rows),
        "fillerCandidateCount": sum(
            len(row.get("fillerCandidates", []))
            for row in speech_rows
            if isinstance(row.get("fillerCandidates", []), list)
        ),
        "pitchAvailableAnswerCount": sum(bool(row.get("pitch")) for row in speech_rows),
        "aggregate": deepcopy(speech.get("aggregate", {})) if speech else {},
    }
    component_statuses = [
        vision_status["status"],
        transcription_status["status"],
        speech_status["status"],
    ]
    result = {
        "sessionId": session_id,
        "status": _final_status(component_statuses, warnings, limitations, errors),
        "generatedAt": generated_at or utc_timestamp(),
        "scoringAvailable": False,
        "scoringUnavailableReasons": list(SCORING_UNAVAILABLE_REASONS),
        "components": {
            "vision": vision_summary,
            "transcription": transcription_summary,
            "speechCharacteristics": speech_summary,
        },
        "answers": answers,
        "warnings": warnings,
        "limitations": limitations,
        "errors": errors,
    }
    validate_public_payload(result)
    return result
