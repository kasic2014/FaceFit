"""Experimental numpy-only speech prosody measurements.

This module reports objective pitch, loudness, and change measurements without
subjective interpretation. Pitch uses normalized autocorrelation and is
intentionally conservative when evidence is weak.
"""

from __future__ import annotations

import json
import math
import os
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from app.speech.speech_metrics import analyze_interval, load_pcm16_mono_wav


@dataclass(frozen=True)
class ProsodyConfiguration:
    pitch_frame_ms: int = 40
    hop_ms: int = 10
    min_f0_hz: float = 60.0
    max_f0_hz: float = 400.0
    min_pitch_confidence: float = 0.35
    fallback_voiced_threshold_dbfs: float = -45.0
    fallback_silence_threshold_dbfs: float = -55.0
    clipping_amplitude_ratio: float = 0.99
    exclude_clipped_pitch_frames: bool = True
    median_smoothing_frames: int = 3
    max_interpolation_gap_ms: int = 50
    octave_ratio_tolerance: float = 0.12
    large_pitch_jump_semitones: float = 3.0
    direction_change_epsilon: float = 0.05
    ending_window_ms: int = 500
    ending_pattern_threshold_semitones: float = 1.0
    minimum_segment_pitch_frames: int = 3
    low_pitch_coverage_threshold: float = 0.40
    clipping_warning_ratio: float = 0.01
    low_snr_proxy_db: float = 15.0
    high_octave_error_ratio: float = 0.10

    def validate(self) -> None:
        if self.pitch_frame_ms <= 0 or self.hop_ms <= 0:
            raise ValueError("Frame and hop durations must be positive.")
        if self.min_f0_hz <= 0 or self.max_f0_hz <= self.min_f0_hz:
            raise ValueError("F0 bounds are invalid.")
        if not 0.0 <= self.min_pitch_confidence <= 1.0:
            raise ValueError("min_pitch_confidence must be in [0, 1].")
        if self.median_smoothing_frames <= 0:
            raise ValueError("median_smoothing_frames must be positive.")
        if self.max_interpolation_gap_ms < 0:
            raise ValueError("max_interpolation_gap_ms must be non-negative.")


class ProsodyAnalysisError(Exception):
    """A classified prosody-analysis failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _empty_result(
    audio_file: Path | str,
    stt_json_file: Path | str,
    speech_metrics_file: Path | str,
    configuration: ProsodyConfiguration,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "description": (
            "Experimental numpy normalized-autocorrelation prosody metrics. "
            "Objective measurements without subjective interpretation."
        ),
        "audio_file": str(audio_file),
        "stt_json_file": str(stt_json_file),
        "speech_metrics_file": str(speech_metrics_file),
        "audio_duration_sec": 0.0,
        "configuration": asdict(configuration),
        "pitch_summary": {},
        "loudness_summary": {},
        "intonation_summary": {},
        "segment_prosody": [],
        "prosody_reliability": {},
        "frames": [],
        "warnings": [],
        "error": None,
    }


def _error(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _warning(code: str, detail: str, **values: Any) -> dict[str, Any]:
    return {"code": code, "detail": detail, **values}


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rounded(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        return None
    return float(np.percentile(array, percentile))


def _mean(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return float(np.mean(array)) if array.size else None


def _median(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return float(np.median(array)) if array.size else None


def _std(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return float(np.std(array)) if array.size else None


def semitones_from_reference(
    f0_values: Iterable[float], reference_f0: float | None
) -> list[float]:
    """Convert positive F0 values to semitones around one reference F0."""
    if reference_f0 is None or reference_f0 <= 0 or not math.isfinite(reference_f0):
        return []
    return [
        12.0 * math.log2(float(value) / reference_f0)
        for value in f0_values
        if float(value) > 0 and math.isfinite(float(value))
    ]


def _normalized_correlations(
    windowed: np.ndarray, start_lag: int, end_lag: int
) -> tuple[np.ndarray, np.ndarray]:
    lags: list[int] = []
    correlations: list[float] = []
    for lag in range(start_lag, end_lag + 1):
        first = windowed[:-lag]
        second = windowed[lag:]
        if first.size < 2:
            continue
        denominator = math.sqrt(
            float(np.dot(first, first)) * float(np.dot(second, second))
        )
        correlation = (
            float(np.dot(first, second)) / denominator
            if denominator > 1e-12
            else 0.0
        )
        lags.append(lag)
        correlations.append(max(-1.0, min(1.0, correlation)))
    return np.asarray(lags, dtype=np.int32), np.asarray(
        correlations, dtype=np.float64
    )


def _local_peak_indices(values: np.ndarray) -> list[int]:
    if values.size < 3:
        return []
    return [
        index
        for index in range(1, values.size - 1)
        if values[index] >= values[index - 1]
        and values[index] > values[index + 1]
    ]


def estimate_frame_f0(
    samples: np.ndarray,
    sample_rate: int,
    configuration: ProsodyConfiguration | None = None,
) -> tuple[float | None, float]:
    """Estimate one frame's F0 and normalized autocorrelation confidence."""
    config = configuration or ProsodyConfiguration()
    config.validate()
    values = np.asarray(samples, dtype=np.float64)
    if values.size < 3 or not np.any(values):
        return None, 0.0
    values = values - float(np.mean(values))
    windowed = values * np.hanning(values.size)
    if float(np.dot(windowed, windowed)) <= 1e-12:
        return None, 0.0

    minimum_lag = max(1, math.ceil(sample_rate / config.max_f0_hz))
    maximum_lag = min(values.size - 2, math.floor(sample_rate / config.min_f0_hz))
    if maximum_lag <= minimum_lag:
        return None, 0.0

    extended_maximum_lag = min(
        values.size - 2, math.ceil(maximum_lag * 1.15)
    )
    lags, correlations = _normalized_correlations(
        windowed, 2, extended_maximum_lag
    )
    all_peaks = _local_peak_indices(correlations)
    strong_peaks = [
        index
        for index in all_peaks
        if correlations[index] >= config.min_pitch_confidence
    ]
    if strong_peaks:
        first_strong_lag = int(lags[strong_peaks[0]])
        if first_strong_lag < minimum_lag - 1 or first_strong_lag > maximum_lag:
            return None, float(correlations[strong_peaks[0]])
    peaks = [
        index
        for index in all_peaks
        if minimum_lag - 1 <= int(lags[index]) <= maximum_lag
    ]
    if not peaks:
        in_range = correlations[lags <= maximum_lag]
        return None, float(np.max(in_range)) if in_range.size else 0.0
    peak_index = max(peaks, key=lambda index: correlations[index])
    confidence = float(correlations[peak_index])
    if confidence < config.min_pitch_confidence:
        return None, confidence

    interpolated_lag = float(lags[peak_index])
    if 0 < peak_index < correlations.size - 1:
        left = float(correlations[peak_index - 1])
        center = float(correlations[peak_index])
        right = float(correlations[peak_index + 1])
        denominator = left - 2.0 * center + right
        if abs(denominator) > 1e-12:
            offset = 0.5 * (left - right) / denominator
            if abs(offset) <= 1.0:
                interpolated_lag += offset
    if int(lags[peak_index]) <= minimum_lag:
        interpolated_lag = max(float(minimum_lag), interpolated_lag)
    if interpolated_lag <= 0:
        return None, confidence
    f0 = sample_rate / interpolated_lag
    if not config.min_f0_hz <= f0 <= config.max_f0_hz:
        return None, confidence
    return float(f0), confidence


def detect_octave_error_candidates(
    raw_f0: list[float | None],
    tolerance: float = 0.12,
) -> list[bool]:
    flags = [False] * len(raw_f0)
    previous_index: int | None = None
    for index, value in enumerate(raw_f0):
        if value is None:
            continue
        if previous_index is not None:
            previous = raw_f0[previous_index]
            assert previous is not None
            ratio = value / previous
            if abs(ratio - 2.0) <= 2.0 * tolerance or abs(ratio - 0.5) <= 0.5 * tolerance:
                flags[previous_index] = True
                flags[index] = True
        previous_index = index
    return flags


def median_smooth_f0(
    raw_f0: list[float | None], window_frames: int = 3
) -> list[float | None]:
    if window_frames <= 1:
        return list(raw_f0)
    radius = window_frames // 2
    smoothed: list[float | None] = []
    for index, value in enumerate(raw_f0):
        if value is None:
            smoothed.append(None)
            continue
        neighbors = [
            candidate
            for candidate in raw_f0[
                max(0, index - radius) : min(len(raw_f0), index + radius + 1)
            ]
            if candidate is not None
        ]
        smoothed.append(float(np.median(neighbors)) if neighbors else value)
    return smoothed


def interpolate_short_f0_gaps(
    f0_values: list[float | None], max_gap_frames: int
) -> tuple[list[float | None], list[bool]]:
    interpolated = list(f0_values)
    flags = [False] * len(f0_values)
    index = 0
    while index < len(f0_values):
        if f0_values[index] is not None:
            index += 1
            continue
        start = index
        while index < len(f0_values) and f0_values[index] is None:
            index += 1
        gap = index - start
        if (
            gap <= max_gap_frames
            and start > 0
            and index < len(f0_values)
            and f0_values[start - 1] is not None
            and f0_values[index] is not None
        ):
            left = float(f0_values[start - 1])
            right = float(f0_values[index])
            for offset in range(gap):
                fraction = (offset + 1) / (gap + 1)
                interpolated[start + offset] = left + (right - left) * fraction
                flags[start + offset] = True
    return interpolated, flags


def _slope(values: list[float], times: list[float]) -> float | None:
    if len(values) < 2 or len(values) != len(times):
        return None
    x = np.asarray(times, dtype=np.float64)
    y = np.asarray(values, dtype=np.float64)
    centered = x - float(np.mean(x))
    denominator = float(np.dot(centered, centered))
    if denominator <= 1e-12:
        return None
    return float(np.dot(centered, y - float(np.mean(y))) / denominator)


def _direction_change_count(changes: list[float], epsilon: float) -> int:
    signs = [
        1 if change > epsilon else -1
        for change in changes
        if abs(change) > epsilon
    ]
    return sum(first != second for first, second in zip(signs, signs[1:]))


def summarize_pitch(
    frames: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[float | None]]:
    f0_by_frame = [
        _finite_float(frame.get("smoothed_f0_hz")) for frame in frames
    ]
    valid = [value for value in f0_by_frame if value is not None]
    voiced_count = sum(bool(frame.get("voiced")) for frame in frames)
    coverage = len(valid) / voiced_count if voiced_count else 0.0
    median_hz = _median(valid)
    semitones = semitones_from_reference(valid, median_hz)
    p10_hz = _percentile(valid, 10)
    p90_hz = _percentile(valid, 90)
    p10_st = _percentile(semitones, 10)
    p90_st = _percentile(semitones, 90)
    p25_st = _percentile(semitones, 25)
    p75_st = _percentile(semitones, 75)
    return (
        {
            "pitch_valid_frame_count": len(valid),
            "pitch_voiced_frame_count": voiced_count,
            "pitch_coverage_ratio": round(coverage, 6),
            "pitch_mean_hz": _rounded(_mean(valid), 3),
            "pitch_median_hz": _rounded(median_hz, 3),
            "pitch_std_hz": _rounded(_std(valid), 3),
            "pitch_p10_hz": _rounded(p10_hz, 3),
            "pitch_p90_hz": _rounded(p90_hz, 3),
            "pitch_range_hz": (
                _rounded(p90_hz - p10_hz, 3)
                if p10_hz is not None and p90_hz is not None
                else None
            ),
            "pitch_min_hz": _rounded(min(valid), 3) if valid else None,
            "pitch_max_hz": _rounded(max(valid), 3) if valid else None,
            "pitch_reference_median_hz": _rounded(median_hz, 3),
            "pitch_std_semitones": _rounded(_std(semitones), 6),
            "pitch_p10_semitones": _rounded(p10_st, 6),
            "pitch_p90_semitones": _rounded(p90_st, 6),
            "pitch_range_semitones": (
                _rounded(p90_st - p10_st, 6)
                if p10_st is not None and p90_st is not None
                else None
            ),
            "pitch_iqr_semitones": (
                _rounded(p75_st - p25_st, 6)
                if p25_st is not None and p75_st is not None
                else None
            ),
        },
        f0_by_frame,
    )


def summarize_loudness(frames: list[dict[str, Any]]) -> dict[str, Any]:
    voiced_dbfs = [
        float(frame["dbfs"])
        for frame in frames
        if frame.get("voiced") and _finite_float(frame.get("dbfs")) is not None
    ]
    all_peak = [
        float(frame["peak_dbfs"])
        for frame in frames
        if _finite_float(frame.get("peak_dbfs")) is not None
    ]
    p10 = _percentile(voiced_dbfs, 10)
    p90 = _percentile(voiced_dbfs, 90)
    clipping_ratio = (
        sum(bool(frame.get("clipping")) for frame in frames) / len(frames)
        if frames
        else 0.0
    )
    return {
        "voiced_loudness_mean_dbfs": _rounded(_mean(voiced_dbfs), 3),
        "voiced_loudness_median_dbfs": _rounded(_median(voiced_dbfs), 3),
        "voiced_loudness_std_db": _rounded(_std(voiced_dbfs), 3),
        "voiced_loudness_p10_dbfs": _rounded(p10, 3),
        "voiced_loudness_p90_dbfs": _rounded(p90, 3),
        "voiced_loudness_range_db": (
            _rounded(p90 - p10, 3)
            if p10 is not None and p90 is not None
            else None
        ),
        "peak_dbfs": _rounded(max(all_peak), 3) if all_peak else None,
        "clipping_frame_ratio": round(clipping_ratio, 6),
    }


def summarize_intonation(
    frames: list[dict[str, Any]],
    pitch_summary: dict[str, Any],
    configuration: ProsodyConfiguration,
) -> dict[str, Any]:
    reference = _finite_float(pitch_summary.get("pitch_median_hz"))
    pitch_changes: list[float] = []
    pitch_times: list[float] = []
    pitch_values: list[float] = []
    previous_pitch: float | None = None
    previous_index: int | None = None
    for index, frame in enumerate(frames):
        value = _finite_float(frame.get("smoothed_f0_hz"))
        if value is None or reference is None:
            previous_pitch = None
            previous_index = None
            continue
        semitone = 12.0 * math.log2(value / reference)
        pitch_times.append(float(frame["center_sec"]))
        pitch_values.append(semitone)
        if previous_pitch is not None and previous_index == index - 1:
            pitch_changes.append(semitone - previous_pitch)
        previous_pitch = semitone
        previous_index = index

    absolute_pitch_changes = [abs(value) for value in pitch_changes]
    loudness_changes: list[float] = []
    previous_dbfs: float | None = None
    previous_loudness_index: int | None = None
    for index, frame in enumerate(frames):
        dbfs = _finite_float(frame.get("dbfs")) if frame.get("voiced") else None
        if dbfs is None:
            previous_dbfs = None
            previous_loudness_index = None
            continue
        if previous_dbfs is not None and previous_loudness_index == index - 1:
            loudness_changes.append(dbfs - previous_dbfs)
        previous_dbfs = dbfs
        previous_loudness_index = index
    absolute_loudness_changes = [abs(value) for value in loudness_changes]
    return {
        "mean_absolute_pitch_change_semitones": _rounded(
            _mean(absolute_pitch_changes), 6
        ),
        "median_absolute_pitch_change_semitones": _rounded(
            _median(absolute_pitch_changes), 6
        ),
        "pitch_change_p90_semitones": _rounded(
            _percentile(absolute_pitch_changes, 90), 6
        ),
        "large_pitch_jump_count": sum(
            value >= configuration.large_pitch_jump_semitones
            for value in absolute_pitch_changes
        ),
        "pitch_direction_change_count": _direction_change_count(
            pitch_changes, configuration.direction_change_epsilon
        ),
        "pitch_slope_semitones_per_sec": _rounded(
            _slope(pitch_values, pitch_times), 6
        ),
        "loudness_change_mean_db": _rounded(
            _mean(absolute_loudness_changes), 6
        ),
        "loudness_change_p90_db": _rounded(
            _percentile(absolute_loudness_changes, 90), 6
        ),
        "loudness_direction_change_count": _direction_change_count(
            loudness_changes, configuration.direction_change_epsilon
        ),
    }


def _pitch_values_and_times(
    frames: list[dict[str, Any]],
) -> tuple[list[float], list[float]]:
    values: list[float] = []
    times: list[float] = []
    for frame in frames:
        f0 = _finite_float(frame.get("smoothed_f0_hz"))
        if f0 is not None:
            values.append(f0)
            times.append(float(frame["center_sec"]))
    return values, times


def ending_intonation(
    frames: list[dict[str, Any]],
    configuration: ProsodyConfiguration,
) -> dict[str, Any]:
    valid_frames = [
        frame
        for frame in frames
        if _finite_float(frame.get("smoothed_f0_hz")) is not None
    ]
    if len(valid_frames) < 2:
        return {
            "ending_pitch_start_hz": None,
            "ending_pitch_end_hz": None,
            "ending_pitch_change_semitones": None,
            "ending_pitch_slope_semitones_per_sec": None,
            "ending_pattern": "insufficient_data",
        }
    last_time = float(valid_frames[-1]["center_sec"])
    window_start = last_time - configuration.ending_window_ms / 1000.0
    ending_frames = [
        frame for frame in valid_frames if float(frame["center_sec"]) >= window_start
    ]
    if len(ending_frames) < 2:
        return {
            "ending_pitch_start_hz": None,
            "ending_pitch_end_hz": None,
            "ending_pitch_change_semitones": None,
            "ending_pitch_slope_semitones_per_sec": None,
            "ending_pattern": "insufficient_data",
        }
    start_hz = float(ending_frames[0]["smoothed_f0_hz"])
    end_hz = float(ending_frames[-1]["smoothed_f0_hz"])
    change = 12.0 * math.log2(end_hz / start_hz)
    values = [
        12.0 * math.log2(float(frame["smoothed_f0_hz"]) / start_hz)
        for frame in ending_frames
    ]
    times = [float(frame["center_sec"]) for frame in ending_frames]
    threshold = configuration.ending_pattern_threshold_semitones
    if change >= threshold:
        pattern = "rising"
    elif change <= -threshold:
        pattern = "falling"
    else:
        pattern = "level"
    return {
        "ending_pitch_start_hz": round(start_hz, 3),
        "ending_pitch_end_hz": round(end_hz, 3),
        "ending_pitch_change_semitones": round(change, 6),
        "ending_pitch_slope_semitones_per_sec": _rounded(
            _slope(values, times), 6
        ),
        "ending_pattern": pattern,
    }


def _segment_prosody(
    stt: dict[str, Any],
    frames: list[dict[str, Any]],
    configuration: ProsodyConfiguration,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    results: list[dict[str, Any]] = []
    pattern_counts = {
        "rising": 0,
        "falling": 0,
        "level": 0,
        "insufficient_data": 0,
    }
    for segment_index, segment in enumerate(stt.get("segments", [])):
        start = _finite_float(segment.get("start"))
        end = _finite_float(segment.get("end"))
        if start is None or end is None or end <= start:
            continue
        selected = [
            frame
            for frame in frames
            if start <= float(frame["center_sec"]) <= end
        ]
        pitch_values, pitch_times = _pitch_values_and_times(selected)
        voiced_count = sum(bool(frame.get("voiced")) for frame in selected)
        pitch_coverage = (
            len(pitch_values) / voiced_count if voiced_count else 0.0
        )
        median_pitch = _median(pitch_values)
        semitones = semitones_from_reference(pitch_values, median_pitch)
        p10 = _percentile(semitones, 10)
        p90 = _percentile(semitones, 90)
        voiced_dbfs = [
            float(frame["dbfs"])
            for frame in selected
            if frame.get("voiced") and _finite_float(frame.get("dbfs")) is not None
        ]
        loudness_p10 = _percentile(voiced_dbfs, 10)
        loudness_p90 = _percentile(voiced_dbfs, 90)
        segment_warnings: list[dict[str, Any]] = []
        if len(pitch_values) < configuration.minimum_segment_pitch_frames:
            segment_warnings.append(
                _warning(
                    "SEGMENT_PITCH_INSUFFICIENT",
                    "Segment has too few valid pitch frames.",
                    valid_pitch_frame_count=len(pitch_values),
                )
            )
            pitch_range = None
            pitch_slope = None
        else:
            pitch_range = (
                p90 - p10 if p10 is not None and p90 is not None else None
            )
            pitch_slope = _slope(
                semitones,
                pitch_times,
            )
        ending = ending_intonation(selected, configuration)
        pattern_counts[ending["ending_pattern"]] += 1
        results.append(
            {
                "segment_id": segment.get("id", segment_index),
                "start_sec": round(start, 6),
                "end_sec": round(end, 6),
                "text": str(segment.get("text", "")),
                "duration_sec": round(end - start, 6),
                "pitch_median_hz": (
                    _rounded(median_pitch, 3)
                    if len(pitch_values)
                    >= configuration.minimum_segment_pitch_frames
                    else None
                ),
                "pitch_range_semitones": _rounded(pitch_range, 6),
                "pitch_slope_semitones_per_sec": _rounded(pitch_slope, 6),
                "loudness_mean_dbfs": _rounded(_mean(voiced_dbfs), 3),
                "loudness_range_db": (
                    _rounded(loudness_p90 - loudness_p10, 3)
                    if loudness_p10 is not None and loudness_p90 is not None
                    else None
                ),
                "valid_pitch_frame_count": len(pitch_values),
                "pitch_coverage_ratio": round(pitch_coverage, 6),
                "ending_intonation": ending,
                "warnings": segment_warnings,
            }
        )
    return results, pattern_counts


def _load_json(path: Path, missing_code: str, invalid_code: str) -> dict[str, Any]:
    if not path.is_file():
        raise ProsodyAnalysisError(missing_code, str(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProsodyAnalysisError(
            invalid_code, f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("error"):
        raise ProsodyAnalysisError(
            invalid_code, "JSON root is not a successful result object."
        )
    return payload


def _validate_word_timestamps(stt: dict[str, Any]) -> None:
    timestamped_words = 0
    for segment in stt.get("segments", []):
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words") or []:
            if (
                isinstance(word, dict)
                and _finite_float(word.get("start")) is not None
                and _finite_float(word.get("end")) is not None
            ):
                timestamped_words += 1
    if timestamped_words == 0:
        raise ProsodyAnalysisError(
            "WORD_TIMESTAMPS_NOT_FOUND",
            "STT result contains no words with start/end timestamps.",
        )


def _analyze_frames(
    audio: Any,
    configuration: ProsodyConfiguration,
    voiced_threshold_dbfs: float,
    silence_threshold_dbfs: float,
) -> list[dict[str, Any]]:
    sample_rate = audio.sample_rate
    frame_samples = max(
        1, round(sample_rate * configuration.pitch_frame_ms / 1000.0)
    )
    hop_samples = max(1, round(sample_rate * configuration.hop_ms / 1000.0))
    normalized = np.asarray(audio.samples, dtype=np.float64) / 32768.0
    frames: list[dict[str, Any]] = []
    offsets = (
        [0]
        if normalized.size <= frame_samples
        else range(0, normalized.size - frame_samples + 1, hop_samples)
    )
    for frame_index, start_sample in enumerate(offsets):
        end_sample = min(normalized.size, start_sample + frame_samples)
        start_sec = start_sample / sample_rate
        end_sec = end_sample / sample_rate
        acoustic = analyze_interval(
            audio,
            start_sec,
            end_sec,
            voiced_threshold_dbfs=voiced_threshold_dbfs,
            silence_threshold_dbfs=silence_threshold_dbfs,
        )
        frame_samples_normalized = normalized[start_sample:end_sample]
        peak = (
            float(np.max(np.abs(frame_samples_normalized)))
            if frame_samples_normalized.size
            else 0.0
        )
        peak_dbfs = 20.0 * math.log10(peak) if peak > 0 else -100.0
        clipping = peak >= configuration.clipping_amplitude_ratio
        voiced = bool(acoustic["dbfs"] >= voiced_threshold_dbfs)
        raw_f0: float | None = None
        confidence = 0.0
        if voiced and not (
            clipping and configuration.exclude_clipped_pitch_frames
        ):
            raw_f0, confidence = estimate_frame_f0(
                frame_samples_normalized,
                sample_rate,
                configuration,
            )
        frames.append(
            {
                "frame_index": frame_index,
                "start_sec": round(start_sec, 6),
                "end_sec": round(end_sec, 6),
                "center_sec": round((start_sec + end_sec) / 2.0, 6),
                "rms": acoustic["rms"],
                "dbfs": acoustic["dbfs"],
                "peak_dbfs": round(peak_dbfs, 3),
                "voiced": voiced,
                "clipping": clipping,
                "raw_f0_hz": _rounded(raw_f0, 3),
                "smoothed_f0_hz": None,
                "pitch_confidence": round(confidence, 6),
                "interpolated": False,
                "octave_error_candidate": False,
            }
        )

    raw_values = [_finite_float(frame["raw_f0_hz"]) for frame in frames]
    octave_flags = detect_octave_error_candidates(
        raw_values, configuration.octave_ratio_tolerance
    )
    smoothed = median_smooth_f0(
        raw_values, configuration.median_smoothing_frames
    )
    max_gap_frames = math.floor(
        configuration.max_interpolation_gap_ms / configuration.hop_ms
    )
    smoothed, interpolation_flags = interpolate_short_f0_gaps(
        smoothed, max_gap_frames
    )
    for frame, f0, interpolated, octave in zip(
        frames, smoothed, interpolation_flags, octave_flags
    ):
        if interpolated and not frame["voiced"]:
            f0 = None
            interpolated = False
        frame["smoothed_f0_hz"] = _rounded(f0, 3)
        frame["interpolated"] = interpolated
        frame["octave_error_candidate"] = octave
    return frames


def _prosody_reliability(
    pitch_summary: dict[str, Any],
    loudness_summary: dict[str, Any],
    frames: list[dict[str, Any]],
    quality: dict[str, Any],
    configuration: ProsodyConfiguration,
) -> dict[str, Any]:
    coverage = float(pitch_summary.get("pitch_coverage_ratio", 0.0))
    low_coverage = coverage < configuration.low_pitch_coverage_threshold
    clipping_ratio = float(loudness_summary.get("clipping_frame_ratio", 0.0))
    quality_flags = {
        str(value) for value in quality.get("reliability_flags", [])
    }
    background = bool(quality.get("background_noise_suspected")) or (
        "background_noise_suspected" in quality_flags
    )
    clipping = (
        clipping_ratio > configuration.clipping_warning_ratio
        or "clipping_suspected" in quality_flags
    )
    snr = _finite_float(quality.get("snr_proxy_db"))
    low_snr = snr is not None and snr < configuration.low_snr_proxy_db
    octave_count = sum(
        bool(frame.get("octave_error_candidate")) for frame in frames
    )
    raw_valid = sum(
        _finite_float(frame.get("raw_f0_hz")) is not None for frame in frames
    )
    octave_ratio = octave_count / raw_valid if raw_valid else 0.0
    high_octave_ratio = octave_ratio > configuration.high_octave_error_ratio
    invalid_ratio = 1.0 - coverage
    flags: list[str] = []
    warnings: list[str] = []
    if low_coverage:
        flags.append("low_pitch_coverage")
        warnings.append("Pitch coverage is below the experimental 0.40 threshold.")
    if background:
        flags.append("background_noise_suspected")
        warnings.append("Background noise can reduce autocorrelation pitch reliability.")
    if clipping:
        flags.append("clipping_suspected")
        warnings.append("Clipping can distort pitch and loudness measurements.")
    if low_snr:
        flags.append("low_snr_proxy")
        warnings.append("SNR proxy is below the experimental 15 dB threshold.")
    if high_octave_ratio:
        flags.append("high_octave_error_candidate_ratio")
        warnings.append("Octave-error candidates are frequent among valid raw pitch frames.")
    return {
        "pitch_coverage_ratio": round(coverage, 6),
        "low_pitch_coverage": low_coverage,
        "background_noise_suspected": background,
        "clipping_suspected": clipping,
        "low_snr_proxy": low_snr,
        "octave_error_candidate_count": octave_count,
        "octave_error_candidate_ratio": round(octave_ratio, 6),
        "invalid_pitch_frame_ratio": round(invalid_ratio, 6),
        "reliability_flags": flags,
        "reliability_warnings": warnings,
    }


def analyze_speech_prosody(
    audio_file: Path | str,
    stt_json_file: Path | str,
    speech_metrics_file: Path | str,
    *,
    include_frames: bool = False,
    configuration: ProsodyConfiguration | None = None,
) -> dict[str, Any]:
    """Analyze one WAV without changing any input file."""
    config = configuration or ProsodyConfiguration()
    result = _empty_result(
        audio_file, stt_json_file, speech_metrics_file, config
    )
    audio_path = Path(audio_file)
    stt_path = Path(stt_json_file)
    metrics_path = Path(speech_metrics_file)
    if not audio_path.is_file():
        result["error"] = _error("AUDIO_FILE_NOT_FOUND", str(audio_path))
        return result
    try:
        try:
            config.validate()
        except ValueError as exc:
            raise ProsodyAnalysisError("PROSODY_ANALYSIS_FAILED", str(exc)) from exc
        stt = _load_json(
            stt_path, "STT_RESULT_NOT_FOUND", "STT_JSON_INVALID"
        )
        _validate_word_timestamps(stt)
        metrics = _load_json(
            metrics_path,
            "SPEECH_METRICS_NOT_FOUND",
            "SPEECH_METRICS_JSON_INVALID",
        )
        try:
            audio = load_pcm16_mono_wav(audio_path)
        except ValueError as exc:
            raise ProsodyAnalysisError(
                "UNSUPPORTED_WAV_FORMAT", str(exc)
            ) from exc
        except (OSError, EOFError, wave.Error) as exc:
            raise ProsodyAnalysisError(
                "AUDIO_INVALID", f"{type(exc).__name__}: {exc}"
            ) from exc
        if audio.sample_rate != 16000:
            raise ProsodyAnalysisError(
                "UNSUPPORTED_WAV_FORMAT",
                f"Expected 16000 Hz, found {audio.sample_rate} Hz.",
            )
        result["audio_duration_sec"] = round(audio.duration_sec, 6)

        quality = metrics.get("audio_quality")
        quality_available = isinstance(quality, dict)
        if not quality_available:
            quality = {}
            result["warnings"].append(
                _warning(
                    "AUDIO_QUALITY_NOT_FOUND",
                    "Speech metrics JSON has no audio_quality object; "
                    "configured fallback energy thresholds are used.",
                )
            )
        voiced_threshold = _finite_float(quality.get("voiced_threshold_dbfs"))
        silence_threshold = _finite_float(quality.get("silence_threshold_dbfs"))
        if voiced_threshold is None:
            voiced_threshold = config.fallback_voiced_threshold_dbfs
        if silence_threshold is None:
            silence_threshold = config.fallback_silence_threshold_dbfs
        result["configuration"]["effective_voiced_threshold_dbfs"] = voiced_threshold
        result["configuration"]["effective_silence_threshold_dbfs"] = silence_threshold
        result["configuration"]["energy_threshold_source"] = (
            "speech_metrics.audio_quality"
            if metrics.get("audio_quality")
            else "configuration_fallback"
        )

        try:
            frames = _analyze_frames(
                audio,
                config,
                voiced_threshold,
                silence_threshold,
            )
        except Exception as exc:
            raise ProsodyAnalysisError(
                "PITCH_ANALYSIS_FAILED", f"{type(exc).__name__}: {exc}"
            ) from exc
        pitch_summary, _ = summarize_pitch(frames)
        loudness_summary = summarize_loudness(frames)
        intonation_summary = summarize_intonation(
            frames, pitch_summary, config
        )
        segments, pattern_counts = _segment_prosody(stt, frames, config)
        intonation_summary["ending_pattern_counts"] = pattern_counts
        result["pitch_summary"] = pitch_summary
        result["loudness_summary"] = loudness_summary
        result["intonation_summary"] = intonation_summary
        result["segment_prosody"] = segments
        reliability = _prosody_reliability(
            pitch_summary, loudness_summary, frames, quality, config
        )
        if not quality_available:
            reliability["reliability_flags"].append("audio_quality_unavailable")
            reliability["reliability_warnings"].append(
                "Source audio-quality metrics are unavailable; fallback energy "
                "thresholds reduce comparability."
            )
        result["prosody_reliability"] = reliability
        result["frames"] = frames if include_frames else []
        if not include_frames:
            result["configuration"]["frames_omitted_from_output"] = True
    except ProsodyAnalysisError as exc:
        result["error"] = _error(exc.code, exc.detail)
    except Exception as exc:
        result["error"] = _error(
            "PROSODY_ANALYSIS_FAILED", f"{type(exc).__name__}: {exc}"
        )
    return _sanitize_json(result)


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, dict):
        return {str(key): _sanitize_json(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json(nested) for nested in value]
    return value


def strict_json_text(payload: Any) -> str:
    sanitized = _sanitize_json(payload)
    return json.dumps(
        sanitized,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )


def write_json_atomic(output_file: Path | str, payload: Any) -> None:
    output_path = Path(output_file)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = strict_json_text(payload) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProsodyAnalysisError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
