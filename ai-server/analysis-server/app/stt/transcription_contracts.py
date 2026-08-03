"""Strict answer, segment, word, and timestamp contracts for Stage 25."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
from pathlib import Path
import re
from typing import Any

from app.audio.audio_manifest_writer import ensure_finite


ANSWER_PATTERN = re.compile(r"^ANS_\d{6}$")
TIMESTAMP_TOLERANCE_MS = 1
MANUAL_REVIEW_WARNINGS = {
    "EMPTY_TRANSCRIPT",
    "NO_SEGMENTS",
    "NO_WORD_TIMESTAMPS",
    "REPETITIVE_OUTPUT_CANDIDATE",
}


class TranscriptionContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AnswerAudio:
    session_id: str
    answer_id: str
    path: Path
    sha256: str
    start_ms: int
    end_ms: int
    duration_ms: int
    sample_count: int

    def __post_init__(self) -> None:
        if ANSWER_PATTERN.fullmatch(self.answer_id) is None:
            raise TranscriptionContractError("INVALID_ANSWER_ID", "Invalid answer ID")
        if self.start_ms < 0 or self.start_ms >= self.end_ms:
            raise TranscriptionContractError("INVALID_ANSWER_INTERVAL", "Invalid answer interval")
        if self.duration_ms != self.end_ms - self.start_ms:
            raise TranscriptionContractError("INVALID_ANSWER_INTERVAL", "Answer duration mismatch")


def seconds_to_milliseconds(value: Any) -> int:
    """Round non-negative model seconds to nearest millisecond, halves up."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TranscriptionContractError("TIMESTAMP_OUT_OF_RANGE", "Timestamp is not numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise TranscriptionContractError("TIMESTAMP_OUT_OF_RANGE", "Timestamp is invalid")
    try:
        return int((Decimal(str(number)) * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError) as exc:
        raise TranscriptionContractError("TIMESTAMP_OUT_OF_RANGE", "Timestamp is invalid") from exc


def _value(source: Any, name: str, default: Any = None) -> Any:
    return source.get(name, default) if isinstance(source, dict) else getattr(source, name, default)


def _finite_optional(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise TranscriptionContractError("NON_FINITE_VALUE", f"Invalid diagnostic value: {name}")
    return float(value)


def _bounded(
    value: int,
    lower: int,
    upper: int,
    warnings: list[str],
) -> int:
    if lower <= value <= upper:
        return value
    if lower - TIMESTAMP_TOLERANCE_MS <= value < lower:
        warnings.append("TIMESTAMP_ROUNDING_ADJUSTED")
        return lower
    if upper < value <= upper + TIMESTAMP_TOLERANCE_MS:
        warnings.append("TIMESTAMP_ROUNDING_ADJUSTED")
        return upper
    raise TranscriptionContractError(
        "TIMESTAMP_OUT_OF_RANGE",
        f"Timestamp {value} ms exceeds [{lower}, {upper}] ms boundary",
    )


def _interval(
    raw_start: Any,
    raw_end: Any,
    *,
    lower: int,
    upper: int,
    warnings: list[str],
) -> tuple[int, int]:
    start = _bounded(seconds_to_milliseconds(raw_start), lower, upper, warnings)
    end = _bounded(seconds_to_milliseconds(raw_end), lower, upper, warnings)
    if end <= start:
        if float(raw_end) > float(raw_start) and start + 1 <= upper:
            warnings.append("TIMESTAMP_ROUNDING_ADJUSTED")
            end = start + 1
        else:
            raise TranscriptionContractError("TIMESTAMP_OUT_OF_RANGE", "Timestamp interval is empty")
    return start, end


def _repetitive_candidate(texts: list[str]) -> bool:
    normalized = [" ".join(text.split()) for text in texts if text.strip()]
    return any(
        normalized[index] == normalized[index - 1] == normalized[index - 2]
        for index in range(2, len(normalized))
    )


def build_answer_contract(
    answer: AnswerAudio,
    *,
    segments_raw: list[Any],
    info: Any,
    processing_time_seconds: float,
) -> dict[str, Any]:
    warnings: list[str] = []
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    previous_segment_start = -1
    previous_segment_end = -1
    previous_word_start = -1
    previous_word_end = -1
    segment_texts: list[str] = []

    for segment_index, raw_segment in enumerate(segments_raw, start=1):
        try:
            model_start, model_end = _interval(
                _value(raw_segment, "start"),
                _value(raw_segment, "end"),
                lower=0,
                upper=answer.duration_ms,
                warnings=warnings,
            )
        except TranscriptionContractError as exc:
            raise TranscriptionContractError(
                exc.code, f"Segment {segment_index}: {exc}"
            ) from exc
        text = str(_value(raw_segment, "text", ""))
        if not text.strip():
            warnings.append("EMPTY_SEGMENT_TEXT")
        segment_texts.append(text)
        raw_words = _value(raw_segment, "words", None) or []
        converted_words: list[tuple[Any, int, int]] = []
        for word_index, raw_word in enumerate(raw_words, start=1):
            try:
                word_start, word_end = _interval(
                    _value(raw_word, "start"),
                    _value(raw_word, "end"),
                    lower=0,
                    upper=answer.duration_ms,
                    warnings=warnings,
                )
            except TranscriptionContractError as exc:
                raise TranscriptionContractError(
                    exc.code, f"Segment {segment_index}, word {word_index}: {exc}"
                ) from exc
            converted_words.append((raw_word, word_start, word_end))
        start = min([model_start, *(row[1] for row in converted_words)])
        end = max([model_end, *(row[2] for row in converted_words)])
        if start != model_start or end != model_end:
            warnings.append("SEGMENT_BOUNDARY_EXPANDED_TO_WORDS")
        if start < previous_segment_start or end < previous_segment_end:
            raise TranscriptionContractError(
                "NON_MONOTONIC_TIMESTAMP", "Segment timestamps are not monotonic"
            )
        overlaps = previous_segment_end >= 0 and start < previous_segment_end
        if overlaps:
            warnings.append("OVERLAPPING_SEGMENTS")
        word_start_index = len(words)
        for raw_word, word_start, word_end in converted_words:
            if word_start < previous_word_start or word_end < previous_word_end:
                raise TranscriptionContractError(
                    "NON_MONOTONIC_TIMESTAMP", "Word timestamps are not monotonic"
                )
            word_text = str(_value(raw_word, "word", ""))
            if not word_text:
                warnings.append("EMPTY_WORD_TEXT")
            words.append(
                {
                    "wordId": f"WRD_{len(words) + 1:06d}",
                    "segmentId": f"SEG_{segment_index:06d}",
                    "startMsRelative": word_start,
                    "endMsRelative": word_end,
                    "startMsSession": answer.start_ms + word_start,
                    "endMsSession": answer.start_ms + word_end,
                    "text": word_text,
                    "probability": _finite_optional(
                        _value(raw_word, "probability"), "probability"
                    ),
                }
            )
            previous_word_start, previous_word_end = word_start, word_end
        segments.append(
            {
                "segmentId": f"SEG_{segment_index:06d}",
                "startMsRelative": start,
                "endMsRelative": end,
                "startMsSession": answer.start_ms + start,
                "endMsSession": answer.start_ms + end,
                "modelStartMsRelative": model_start,
                "modelEndMsRelative": model_end,
                "text": text,
                "avgLogProbability": _finite_optional(
                    _value(raw_segment, "avg_logprob"), "avg_logprob"
                ),
                "noSpeechProbability": _finite_optional(
                    _value(raw_segment, "no_speech_prob"), "no_speech_prob"
                ),
                "compressionRatio": _finite_optional(
                    _value(raw_segment, "compression_ratio"), "compression_ratio"
                ),
                "temperature": _finite_optional(
                    _value(raw_segment, "temperature"), "temperature"
                ),
                "wordCount": len(words) - word_start_index,
                "overlapsPrevious": overlaps,
            }
        )
        previous_segment_start, previous_segment_end = start, end

    text = "".join(segment_texts)
    if not text.strip():
        warnings.append("EMPTY_TRANSCRIPT")
    if not segments:
        warnings.append("NO_SEGMENTS")
    if not words:
        warnings.extend(["NO_WORD_TIMESTAMPS", "WORD_TIMESTAMPS_UNAVAILABLE"])
    detected_language = _value(info, "language")
    if detected_language != "ko":
        warnings.append("LANGUAGE_MISMATCH")
    if _repetitive_candidate(segment_texts):
        warnings.append("REPETITIVE_OUTPUT_CANDIDATE")
    warnings = list(dict.fromkeys(warnings))
    processing = _finite_optional(processing_time_seconds, "processing_time_seconds")
    if processing is None or processing < 0:
        raise TranscriptionContractError("NON_FINITE_VALUE", "Invalid processing time")
    status = (
        "MANUAL_REVIEW_REQUIRED"
        if MANUAL_REVIEW_WARNINGS.intersection(warnings)
        else "COMPLETE_WITH_WARNINGS"
        if warnings
        else "COMPLETE"
    )
    result = {
        "sessionId": answer.session_id,
        "answerId": answer.answer_id,
        "status": status,
        "audio": {
            "durationMs": answer.duration_ms,
            "sampleCount": answer.sample_count,
            "sha256": answer.sha256,
        },
        "answerInterval": {"startMs": answer.start_ms, "endMs": answer.end_ms},
        "language": {
            "requested": "ko",
            "detected": detected_language,
            "probability": _finite_optional(
                _value(info, "language_probability"), "language_probability"
            ),
        },
        "text": text,
        "segments": segments,
        "words": words,
        "processingTimeSeconds": processing,
        "realTimeFactor": processing / (answer.duration_ms / 1000),
        "warnings": warnings,
        "errors": [],
    }
    ensure_finite(result)
    return result
