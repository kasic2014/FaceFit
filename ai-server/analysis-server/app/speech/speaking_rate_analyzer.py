"""Objective speaking-rate measurements from transcript timestamps."""

from __future__ import annotations

from typing import Any


def _interval_union_duration(words: list[dict[str, Any]]) -> int:
    intervals = sorted(
        (int(word["startMsRelative"]), int(word["endMsRelative"]))
        for word in words
    )
    if not intervals:
        return 0
    total = 0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    return total + current_end - current_start


def _per_minute(value: int, duration_ms: int) -> float | None:
    return round(value * 60_000 / duration_ms, 6) if duration_ms > 0 else None


def analyze_speaking_rate(
    transcript: dict[str, Any], duration_ms: int
) -> tuple[dict[str, Any], list[str]]:
    text = str(transcript.get("text", ""))
    words = list(transcript.get("words", []))
    segments = list(transcript.get("segments", []))
    detected_speech_ms = _interval_union_duration(words)
    voiced_span_ms = (
        int(words[-1]["endMsRelative"]) - int(words[0]["startMsRelative"])
        if words
        else None
    )
    warnings: list[str] = []
    if not text.strip():
        warnings.append("EMPTY_TRANSCRIPT")
    if not words:
        warnings.append("WORD_TIMESTAMPS_UNAVAILABLE")
    word_count = len(words)
    characters_without_spaces = sum(not char.isspace() for char in text)
    return (
        {
            "answerDurationMs": duration_ms,
            "transcriptCharacterCount": len(text),
            "transcriptCharacterCountWithoutSpaces": characters_without_spaces,
            "wordCount": word_count,
            "segmentCount": len(segments),
            "voicedWordSpanMs": voiced_span_ms,
            "detectedSpeechDurationMs": detected_speech_ms,
            "detectedSpeechDurationDefinition": "union of Stage 25 word timestamp intervals",
            "wordsPerMinute": _per_minute(word_count, duration_ms),
            "charactersPerMinute": _per_minute(len(text), duration_ms),
            "charactersWithoutSpacesPerMinute": _per_minute(
                characters_without_spaces, duration_ms
            ),
            "articulationWordsPerMinute": _per_minute(
                word_count, detected_speech_ms
            ),
        },
        warnings,
    )
