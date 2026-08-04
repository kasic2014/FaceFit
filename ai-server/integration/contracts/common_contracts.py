"""Shared, dependency-free Stage 28 contract primitives."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable


SESSION_PATTERN = re.compile(r"^SES_\d{6}$")
ANSWER_PATTERN = re.compile(r"^ANS_\d{6}$")
PARTICIPANT_REFERENCE_PATTERN = re.compile(r"\bPTC_\d{6}\b")
WINDOWS_PATH_PATTERN = re.compile(r"(?:^|\s)[A-Za-z]:[\\/]")

COMPONENT_STATUSES = frozenset(
    {"READY", "READY_WITH_WARNINGS", "NOT_READY", "FAILED", "UNAVAILABLE"}
)
INTEGRATED_STATUSES = frozenset(
    {
        "INTEGRATED_READY",
        "INTEGRATED_READY_WITH_WARNINGS",
        "INTEGRATED_PARTIAL",
        "INTEGRATED_FAILED",
    }
)
TERMINAL_JOB_STATUSES = frozenset(
    {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "SUCCEEDED_WITH_LIMITATIONS", "FAILED"}
)
WARNING_SOURCES = frozenset({"VISION", "TRANSCRIPTION", "SPEECH", "INTEGRATION"})
ERROR_SOURCES = frozenset({"VISION", "ANALYSIS", "INTEGRATION"})

FORBIDDEN_KEYS = frozenset(
    {
        "participantid",
        "participant_id",
        "consent",
        "consentreference",
        "consent_reference",
        "raterid",
        "rater_id",
        "absolutepath",
        "absolute_path",
        "videofilename",
        "video_filename",
        "videopath",
        "video_path",
        "modelcachepath",
        "model_cache_path",
        "score",
        "scores",
        "grade",
        "passprobability",
        "pass_probability",
        "confidence",
        "anxiety",
        "personality",
        "emotion",
    }
)


class IntegrationContractError(ValueError):
    """Sanitized contract error safe for persistence and API handoff."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        source: str = "INTEGRATION",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_session_id(value: Any) -> str:
    if not isinstance(value, str) or SESSION_PATTERN.fullmatch(value) is None:
        raise IntegrationContractError(
            "SESSION_ID_MISMATCH", "sessionId must match SES_ followed by six digits."
        )
    return value


def validate_answer_id(value: Any) -> str:
    if not isinstance(value, str) or ANSWER_PATTERN.fullmatch(value) is None:
        raise IntegrationContractError(
            "ANSWER_SET_MISMATCH", "answerId must match ANS_ followed by six digits."
        )
    return value


def map_job_status(source: str, source_status: Any) -> str:
    status = str(source_status or "")
    if status == "SUCCEEDED_WITH_LIMITATIONS" and source == "VISION":
        return "SUCCEEDED_WITH_WARNINGS"
    if status in {"QUEUED", "RUNNING", "SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"}:
        return status
    raise IntegrationContractError(
        "COMPONENT_RESPONSE_INVALID",
        f"{source} returned an unsupported job status.",
        source=source if source in ERROR_SOURCES else "INTEGRATION",
    )


def map_component_status(source: str, source_status: Any) -> str:
    status = str(source_status or "")
    if status in {"SUCCEEDED", "READY", "COMPLETE"}:
        return "READY"
    if status in {
        "SUCCEEDED_WITH_WARNINGS",
        "SUCCEEDED_WITH_LIMITATIONS",
        "READY_WITH_WARNINGS",
        "COMPLETE_WITH_WARNINGS",
    }:
        return "READY_WITH_WARNINGS"
    if status in {"QUEUED", "RUNNING", "NOT_READY"}:
        return "NOT_READY"
    if status == "FAILED":
        return "FAILED"
    if status in {"UNAVAILABLE", ""}:
        return "UNAVAILABLE"
    lowered = status.lower()
    if "ready_with" in lowered or "limitation" in lowered or "warning" in lowered:
        return "READY_WITH_WARNINGS"
    if "ready" in lowered or "complete" in lowered:
        return "READY"
    if "fail" in lowered or "input_failed" in lowered:
        return "FAILED"
    if "unavailable" in lowered:
        return "UNAVAILABLE"
    raise IntegrationContractError(
        "COMPONENT_RESPONSE_INVALID",
        f"{source} returned an unsupported component status.",
        source=source if source in ERROR_SOURCES else "INTEGRATION",
    )


def _warning_code(source: str, warning: Any) -> tuple[str, str]:
    if isinstance(warning, dict):
        code = warning.get("code")
        message = warning.get("message")
        if isinstance(code, str) and code and isinstance(message, str) and message:
            return code, message
    if isinstance(warning, str) and warning:
        if source == "VISION" and ("HEAD_POSE" in warning.upper() or "head pose" in warning.lower()):
            return "HEAD_POSE_PARTIAL_AVAILABILITY", warning
        if re.fullmatch(r"[A-Z][A-Z0-9_]+", warning):
            return warning, warning.replace("_", " ").capitalize() + "."
        return f"{source}_WARNING", warning
    raise IntegrationContractError(
        "COMPONENT_RESPONSE_INVALID",
        f"{source} returned an invalid warning.",
        source="INTEGRATION",
    )


def normalize_warning(
    source: str, warning: Any, *, answer_id: str | None = None
) -> dict[str, Any]:
    if source not in WARNING_SOURCES:
        raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "Warning source is invalid.")
    code, message = _warning_code(source, warning)
    candidate_answer = answer_id
    if isinstance(warning, dict) and warning.get("answerId") is not None:
        candidate_answer = validate_answer_id(warning["answerId"])
    if candidate_answer is not None:
        validate_answer_id(candidate_answer)
    review_required = bool(
        isinstance(warning, dict) and warning.get("reviewRequired", False)
    ) or code == "FILLER_CANDIDATE_REVIEW_REQUIRED"
    return {
        "source": source,
        "code": code,
        "message": message,
        "answerId": candidate_answer,
        "reviewRequired": review_required,
    }


def deduplicate_warnings(warnings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for warning in warnings:
        key = (warning.get("source"), warning.get("code"), warning.get("answerId"))
        if key not in seen:
            result.append(deepcopy(warning))
            seen.add(key)
    return result


def normalize_error(
    source: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    if source not in ERROR_SOURCES or not code or not message:
        raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "Error contract is invalid.")
    return {
        "source": source,
        "code": code,
        "message": message,
        "retryable": bool(retryable),
    }


def ensure_finite(value: Any) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "Non-finite number is forbidden.")
        return
    if isinstance(value, list):
        for item in value:
            ensure_finite(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "JSON object key is invalid.")
            ensure_finite(item)
        return
    raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "Value is not strict JSON compatible.")


def validate_public_payload(value: Any) -> None:
    ensure_finite(value)
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.replace("-", "_").lower()
            if normalized in FORBIDDEN_KEYS:
                raise IntegrationContractError(
                    "COMPONENT_RESPONSE_INVALID", f"Forbidden response field: {key}."
                )
            validate_public_payload(item)
    elif isinstance(value, list):
        for item in value:
            validate_public_payload(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if (
            PARTICIPANT_REFERENCE_PATTERN.search(value)
            or WINDOWS_PATH_PATTERN.search(value)
            or lowered.startswith("/app/")
            or lowered.startswith("/data/")
            or "\\models\\" in lowered
            or "/models/" in lowered
        ):
            raise IntegrationContractError(
                "COMPONENT_RESPONSE_INVALID", "Internal identifier or path is forbidden."
            )


def strict_json_bytes(value: Any) -> bytes:
    validate_public_payload(value)
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def atomic_write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = strict_json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: str | Path, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
