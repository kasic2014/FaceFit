"""Strict Stage 15 pilot video intake contracts and low-level helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PARTICIPANT_RE = re.compile(r"^PTC_\d{6}$")
SESSION_RE = re.compile(r"^SES_\d{6}$")


class PilotVideoIntakeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _reject_constant(value: str) -> None:
    raise PilotVideoIntakeError("NON_FINITE_JSON", f"Non-finite JSON value: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PilotVideoIntakeError("DUPLICATE_JSON_KEY", f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def load_strict_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(
            source.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except PilotVideoIntakeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PilotVideoIntakeError("INVALID_JSON", f"Invalid JSON: {source}") from exc
    if not isinstance(value, dict):
        raise PilotVideoIntakeError("INVALID_JSON_ROOT", "JSON root must be an object")
    ensure_finite(value)
    return value


def ensure_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise PilotVideoIntakeError("NON_FINITE_VALUE", f"Non-finite value at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            ensure_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            ensure_finite(item, f"{path}[{index}]")


def write_strict_json(path: str | Path, value: dict[str, Any]) -> None:
    ensure_finite(value)
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_consent(consent: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version", "consent_reference_id", "participant_id",
        "consent_status", "video_collection_allowed",
        "automated_analysis_allowed", "research_use_allowed",
        "model_development_use_allowed", "consented_at", "withdrawn_at",
    }
    missing = sorted(required - set(consent))
    if missing:
        raise PilotVideoIntakeError("CONSENT_FIELD_MISSING", ", ".join(missing))
    checks = {
        "participant_id_valid": bool(PARTICIPANT_RE.fullmatch(consent["participant_id"])),
        "status_granted": consent["consent_status"] == "GRANTED",
        "video_collection_allowed": consent["video_collection_allowed"] is True,
        "automated_analysis_allowed": consent["automated_analysis_allowed"] is True,
        "research_use_allowed": consent["research_use_allowed"] is True,
        "not_withdrawn": consent["withdrawn_at"] is None,
    }
    return {"valid": all(checks.values()), "checks": checks}


def _validate_interval(
    interval_id: Any, start: Any, end: Any, duration_ms: int
) -> list[str]:
    errors: list[str] = []
    if not isinstance(interval_id, str) or not interval_id:
        errors.append("INVALID_INTERVAL_ID")
    if (
        isinstance(start, bool) or isinstance(end, bool)
        or not isinstance(start, int) or not isinstance(end, int)
    ):
        return errors + ["INVALID_INTERVAL_TIMESTAMP"]
    if start < 0 or start >= end:
        errors.append("INVALID_INTERVAL_BOUNDARY")
    if end > duration_ms:
        errors.append("INTERVAL_EXCEEDS_VIDEO_DURATION")
    return errors


def validate_metadata(
    metadata: dict[str, Any],
    consent: dict[str, Any],
    *,
    expected_video_filename: str,
    duration_ms: int,
) -> dict[str, Any]:
    required = {
        "participant_id", "session_id", "consent_reference_id",
        "video_file", "expected_sha256", "baseline_interval", "answers", "withdrawn",
    }
    missing = sorted(required - set(metadata))
    if missing:
        raise PilotVideoIntakeError("METADATA_FIELD_MISSING", ", ".join(missing))
    reference_checks = {
        "participant_matches_consent":
            metadata["participant_id"] == consent["participant_id"],
        "consent_reference_matches":
            metadata["consent_reference_id"] == consent["consent_reference_id"],
        "participant_id_valid":
            isinstance(metadata["participant_id"], str)
            and bool(PARTICIPANT_RE.fullmatch(metadata["participant_id"])),
        "session_id_valid":
            isinstance(metadata["session_id"], str)
            and bool(SESSION_RE.fullmatch(metadata["session_id"])),
        "video_filename_matches":
            metadata["video_file"] == expected_video_filename,
        "expected_sha256_valid":
            isinstance(metadata["expected_sha256"], str)
            and bool(SHA256_RE.fullmatch(metadata["expected_sha256"])),
        "not_withdrawn": metadata["withdrawn"] is False,
    }
    baseline = metadata["baseline_interval"]
    answers = metadata["answers"]
    if not isinstance(baseline, dict) or not isinstance(answers, list):
        raise PilotVideoIntakeError("INVALID_INTERVAL_CONTAINER", "Invalid interval container")
    interval_errors: list[dict[str, Any]] = []
    baseline_errors = _validate_interval(
        baseline.get("interval_id"),
        baseline.get("start_timestamp_ms"),
        baseline.get("end_timestamp_ms"),
        duration_ms,
    )
    if baseline_errors:
        interval_errors.append({"interval_id": baseline.get("baseline_id"), "errors": baseline_errors})
    seen_answer_ids: set[str] = set()
    seen_interval_ids: set[str] = set()
    normalized: list[tuple[int, int, str]] = []
    for answer in answers:
        if not isinstance(answer, dict):
            raise PilotVideoIntakeError("INVALID_ANSWER_INTERVAL", "Answer must be an object")
        answer_id = answer.get("answer_id")
        interval_id = answer.get("interval_id")
        errors = _validate_interval(
            interval_id,
            answer.get("start_timestamp_ms"),
            answer.get("end_timestamp_ms"),
            duration_ms,
        )
        if answer_id in seen_answer_ids:
            errors.append("DUPLICATE_ANSWER_ID")
        if interval_id in seen_interval_ids:
            errors.append("DUPLICATE_INTERVAL_ID")
        seen_answer_ids.add(answer_id)
        seen_interval_ids.add(interval_id)
        if not errors:
            normalized.append((
                answer["start_timestamp_ms"],
                answer["end_timestamp_ms"],
                interval_id,
            ))
        else:
            interval_errors.append({"interval_id": interval_id, "errors": sorted(set(errors))})
    normalized.sort()
    overlaps: list[dict[str, str]] = []
    for left, right in zip(normalized, normalized[1:]):
        if right[0] < left[1]:
            overlaps.append({"left": left[2], "right": right[2]})
    return {
        "valid": all(reference_checks.values()) and not interval_errors and not overlaps,
        "reference_checks": reference_checks,
        "interval_rule": "[start, end)",
        "duration_ms": duration_ms,
        "baseline": baseline,
        "answers": answers,
        "interval_errors": interval_errors,
        "answer_overlaps": overlaps,
    }


def parse_ffprobe_json(value: dict[str, Any]) -> dict[str, Any]:
    streams = value.get("streams")
    if not isinstance(streams, list):
        raise PilotVideoIntakeError("FFPROBE_SCHEMA_INVALID", "streams must be a list")
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if video is None:
        raise PilotVideoIntakeError("VIDEO_STREAM_MISSING", "No video stream")
    audio = [item for item in streams if item.get("codec_type") == "audio"]

    def ratio(raw: str) -> float:
        numerator, denominator = raw.split("/", 1)
        return float(numerator) / float(denominator)

    duration = video.get("duration") or value.get("format", {}).get("duration")
    return {
        "codec": video.get("codec_name"),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "source_fps": ratio(video.get("avg_frame_rate") or video["r_frame_rate"]),
        "frame_count": int(video["nb_frames"]) if video.get("nb_frames") else None,
        "duration_sec": float(duration),
        "audio_stream_present": bool(audio),
        "audio_stream_count": len(audio),
    }


FORBIDDEN_SEMANTIC_KEYS = {
    "personality", "confidence", "anxiety", "focus", "medical",
    "pass_probability", "hire_probability", "psychological_inference",
    "posture_score", "interview_score", "evaluation_threshold",
}


def assert_no_forbidden_semantics(value: Any) -> None:
    if isinstance(value, dict):
        found = FORBIDDEN_SEMANTIC_KEYS.intersection(
            str(key).lower() for key in value
        )
        if found:
            raise PilotVideoIntakeError(
                "FORBIDDEN_SEMANTIC_FIELD", ", ".join(sorted(found))
            )
        for item in value.values():
            assert_no_forbidden_semantics(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_forbidden_semantics(item)
