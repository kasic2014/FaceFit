"""Cross-component Session, Answer, and timestamp validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from integration.contracts.common_contracts import (
    IntegrationContractError,
    validate_answer_id,
    validate_session_id,
)


SES_000001_ANSWERS = (
    "ANS_000001",
    "ANS_000002",
    "ANS_000003",
    "ANS_000004",
)
SES_000001_INTERVALS = {
    "ANS_000001": {"startMs": 11000, "endMs": 50000, "durationMs": 39000},
    "ANS_000002": {"startMs": 51000, "endMs": 107000, "durationMs": 56000},
    "ANS_000003": {"startMs": 108000, "endMs": 160000, "durationMs": 52000},
    "ANS_000004": {"startMs": 161000, "endMs": 192000, "durationMs": 31000},
}


def _answer_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    rows = payload.get("answers", [])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise IntegrationContractError(
            "COMPONENT_RESPONSE_INVALID", "Component answers must be an array of objects."
        )
    return rows


def _answer_map(
    payload: dict[str, Any] | None, source: str
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    result: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for row in _answer_rows(payload):
        try:
            answer_id = validate_answer_id(row.get("answerId"))
        except IntegrationContractError:
            errors.append(
                {
                    "source": "INTEGRATION",
                    "code": "ANSWER_SET_MISMATCH",
                    "message": f"{source} returned an invalid answerId.",
                    "retryable": False,
                }
            )
            continue
        if answer_id in result:
            errors.append(
                {
                    "source": "INTEGRATION",
                    "code": "ANSWER_SET_MISMATCH",
                    "message": f"{source} returned a duplicate answerId.",
                    "retryable": False,
                }
            )
            continue
        result[answer_id] = row
    return result, errors


def _vision_interval(row: dict[str, Any]) -> dict[str, int] | None:
    interval = row.get("interval")
    if not isinstance(interval, dict):
        return None
    start = interval.get("startTimestampMs", interval.get("startMs"))
    end = interval.get("endTimestampMs", interval.get("endMs"))
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        return None
    return {"startMs": start, "endMs": end, "durationMs": end - start}


def _event_interval(event: dict[str, Any]) -> tuple[int, int] | None:
    pairs = (
        ("startMsSession", "endMsSession"),
        ("eventStartMs", "eventEndMs"),
        ("startTimestampMs", "endTimestampMs"),
        ("startMs", "endMs"),
    )
    for start_key, end_key in pairs:
        if start_key in event or end_key in event:
            start = event.get(start_key)
            end = event.get(end_key)
            if isinstance(start, bool) or isinstance(end, bool):
                return None
            if isinstance(start, int) and isinstance(end, int):
                return start, end
            return None
    return None


def _timestamp_events(
    transcription: dict[str, Any] | None,
    speech: dict[str, Any] | None,
) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for answer in _answer_rows(transcription):
        answer_id = str(answer.get("answerId", ""))
        for kind in ("segments", "words"):
            rows = answer.get(kind, [])
            if isinstance(rows, list):
                for event in rows:
                    if isinstance(event, dict):
                        yield answer_id, f"TRANSCRIPTION_{kind[:-1].upper()}", event
    for answer in _answer_rows(speech):
        answer_id = str(answer.get("answerId", ""))
        rows = answer.get("fillerCandidates", [])
        if isinstance(rows, list):
            for event in rows:
                if isinstance(event, dict):
                    yield answer_id, "SPEECH_FILLER", event


def validate_integration_inputs(
    session_id: str,
    vision: dict[str, Any] | None,
    transcription: dict[str, Any] | None,
    speech: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a strict validation report without silently repairing input."""

    validate_session_id(session_id)
    errors: list[dict[str, Any]] = []
    available = {
        "VISION": vision,
        "TRANSCRIPTION": transcription,
        "SPEECH": speech,
    }
    for source, payload in available.items():
        if payload is None:
            continue
        if payload.get("sessionId") != session_id:
            errors.append(
                {
                    "source": "INTEGRATION",
                    "code": "SESSION_ID_MISMATCH",
                    "message": f"{source} sessionId does not match the requested Session.",
                    "retryable": False,
                }
            )

    maps: dict[str, dict[str, dict[str, Any]]] = {}
    for source, payload in available.items():
        answer_map, answer_errors = _answer_map(payload, source)
        maps[source] = answer_map
        errors.extend(answer_errors)

    present_sets = [set(rows) for rows in maps.values() if rows]
    expected = set(SES_000001_ANSWERS) if session_id == "SES_000001" else (
        present_sets[0] if present_sets else set()
    )
    for source, rows in maps.items():
        if available[source] is not None and set(rows) != expected:
            errors.append(
                {
                    "source": "INTEGRATION",
                    "code": "ANSWER_SET_MISMATCH",
                    "message": f"{source} answer set does not match the approved Session answers.",
                    "retryable": False,
                }
            )

    intervals: dict[str, dict[str, int]] = (
        deepcopy(SES_000001_INTERVALS) if session_id == "SES_000001" else {}
    )
    for answer_id, row in maps["VISION"].items():
        interval = _vision_interval(row)
        if interval is None:
            errors.append(
                {
                    "source": "INTEGRATION",
                    "code": "ANSWER_INTERVAL_MISMATCH",
                    "message": f"{answer_id} has an invalid Vision answer interval.",
                    "retryable": False,
                }
            )
        elif session_id == "SES_000001" and interval != SES_000001_INTERVALS.get(answer_id):
            errors.append(
                {
                    "source": "INTEGRATION",
                    "code": "ANSWER_INTERVAL_MISMATCH",
                    "message": f"{answer_id} does not match the approved Session interval.",
                    "retryable": False,
                }
            )
        else:
            intervals[answer_id] = interval

    tolerance = 0
    if transcription is not None:
        options = transcription.get("options", {})
        if isinstance(options, dict) and options.get("timestampToleranceMs") == 1:
            tolerance = 1
    timestamp_checks = 0
    timestamp_errors = 0
    for answer_id, source, event in _timestamp_events(transcription, speech):
        event_interval = _event_interval(event)
        if event_interval is None:
            continue
        timestamp_checks += 1
        approved = intervals.get(answer_id)
        start, end = event_interval
        if (
            approved is None
            or start >= end
            or start < approved["startMs"] - tolerance
            or end > approved["endMs"] + tolerance
        ):
            timestamp_errors += 1
            errors.append(
                {
                    "source": "INTEGRATION",
                    "code": "TIMESTAMP_OUT_OF_RANGE",
                    "message": f"{source} timestamp is outside {answer_id}.",
                    "retryable": False,
                }
            )

    unique_errors: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for error in errors:
        key = (error["code"], error["message"])
        if key not in seen:
            unique_errors.append(error)
            seen.add(key)
    return {
        "sessionId": session_id,
        "valid": not unique_errors,
        "answerIds": sorted(expected),
        "answerSets": {source: sorted(rows) for source, rows in maps.items()},
        "intervals": deepcopy(intervals),
        "timestampValidation": {
            "rule": "answerStartMs <= eventStartMs < eventEndMs <= answerEndMs",
            "toleranceMs": tolerance,
            "checkedEventCount": timestamp_checks,
            "errorCount": timestamp_errors,
        },
        "errorCount": len(unique_errors),
        "errors": unique_errors,
    }
