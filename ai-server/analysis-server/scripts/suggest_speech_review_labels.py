"""Generate conservative heuristic labels for isolated speech-review clips.

The output is a machine suggestion, not human ground truth.  It must not be
copied into reviewer_label or used for scoring, penalties, or interview
evaluation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import wave
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.whisper_service import WhisperService  # noqa: E402


DEFAULT_MANIFEST = (
    ANALYSIS_SERVER_ROOT
    / "data"
    / "output"
    / "review"
    / "speech_review_manifest_reviewed.csv"
)
DEFAULT_JSON_OUTPUT = DEFAULT_MANIFEST.with_name("speech_review_suggestions.json")
DEFAULT_CSV_OUTPUT = DEFAULT_MANIFEST.with_name("speech_review_suggestions.csv")

ALLOWED_LABELS = {
    "filler",
    "normal_speech",
    "breath",
    "noise",
    "silence",
    "whisper_hallucination",
    "unknown",
}
FILLER_TOKENS = {"음", "어", "아", "저", "으", "엄", "응"}
MIN_CONFIDENCE = 0.55
HUMAN_ONLY_LABEL_CONFIDENCE_CAP = 0.75
FRAME_DURATION_SEC = 0.02
REQUIRED_COLUMNS = {
    "review_id",
    "clip_file",
    "event_type",
    "reviewer_label",
    "reviewer_note",
}
OUTPUT_FIELDS = [
    "review_id",
    "clip_file",
    "original_event_type",
    "suggested_label",
    "suggested_confidence",
    "suggested_reasons",
    "requires_human_review",
    "acoustic_features",
    "isolated_stt",
    "warnings",
    "error",
]
STT_CONFIGURATION = {
    "model": "turbo",
    "language": "ko",
    "task": "transcribe",
    "word_timestamps": True,
    "vad_filter": False,
    "condition_on_previous_text": False,
}

SttRunner = Callable[[Path], dict[str, Any]]


class SuggestionError(Exception):
    """A classified fatal suggestion error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _dbfs(amplitude: float) -> float:
    return 20.0 * math.log10(amplitude) if amplitude > 0 else -100.0


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def _frame_dbfs(samples: np.ndarray, sample_rate: int) -> list[float]:
    frame_size = max(1, round(sample_rate * FRAME_DURATION_SEC))
    return [
        _dbfs(_rms(samples[offset : offset + frame_size]))
        for offset in range(0, samples.size, frame_size)
    ]


def _spectral_features(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    if samples.size < 2 or not np.any(samples):
        return {
            "spectral_centroid_hz": 0.0,
            "spectral_flatness": 0.0,
            "dominant_frequency_hz": 0.0,
        }
    windowed = (samples - float(np.mean(samples))) * np.hanning(samples.size)
    magnitudes = np.abs(np.fft.rfft(windowed))
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    if magnitudes.size:
        magnitudes[0] = 0.0
    magnitude_sum = float(np.sum(magnitudes))
    if magnitude_sum <= 1e-12:
        return {
            "spectral_centroid_hz": 0.0,
            "spectral_flatness": 0.0,
            "dominant_frequency_hz": 0.0,
        }
    centroid = float(np.sum(frequencies * magnitudes) / magnitude_sum)
    positive = magnitudes[1:] if magnitudes.size > 1 else magnitudes
    epsilon = 1e-12
    geometric = float(np.exp(np.mean(np.log(positive + epsilon))))
    arithmetic = float(np.mean(positive + epsilon))
    flatness = min(1.0, geometric / arithmetic) if arithmetic else 0.0
    dominant = float(frequencies[int(np.argmax(magnitudes))])
    return {
        "spectral_centroid_hz": round(centroid, 3),
        "spectral_flatness": round(flatness, 6),
        "dominant_frequency_hz": round(dominant, 3),
    }


def _periodicity_proxy(samples: np.ndarray, sample_rate: int) -> float:
    """Return the best normalized autocorrelation in a speech-like pitch range."""
    centered = samples.astype(np.float64, copy=False) - float(np.mean(samples))
    if centered.size < 3 or _rms(centered) < 1e-8:
        return 0.0
    minimum_lag = max(1, round(sample_rate / 500.0))
    maximum_lag = min(centered.size - 2, round(sample_rate / 50.0))
    if maximum_lag < minimum_lag:
        return 0.0
    best = 0.0
    for lag in range(minimum_lag, maximum_lag + 1):
        first = centered[:-lag]
        second = centered[lag:]
        denominator = math.sqrt(
            float(np.dot(first, first)) * float(np.dot(second, second))
        )
        if denominator > 1e-12:
            best = max(best, float(np.dot(first, second)) / denominator)
    return round(max(0.0, min(1.0, best)), 6)


def _local_contrast_db(
    all_samples: np.ndarray,
    candidate_start: int,
    candidate_end: int,
    sample_rate: int,
) -> float | None:
    context_samples = round(0.3 * sample_rate)
    before = all_samples[max(0, candidate_start - context_samples) : candidate_start]
    after = all_samples[candidate_end : min(all_samples.size, candidate_end + context_samples)]
    values = [_dbfs(_rms(part)) for part in (before, after) if part.size]
    if not values:
        return None
    candidate_dbfs = _dbfs(_rms(all_samples[candidate_start:candidate_end]))
    return round(candidate_dbfs - sum(values) / len(values), 3)


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    """Load a mono PCM16 WAV into normalized float64 samples."""
    try:
        with wave.open(str(path), "rb") as stream:
            if (
                stream.getnchannels() != 1
                or stream.getsampwidth() != 2
                or stream.getcomptype() != "NONE"
            ):
                raise SuggestionError(
                    "UNSUPPORTED_WAV_FORMAT", "Expected mono 16-bit PCM WAV."
                )
            sample_rate = stream.getframerate()
            raw = stream.readframes(stream.getnframes())
    except SuggestionError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise SuggestionError(
            "WAV_READ_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return samples, sample_rate


def _candidate_interval(
    row: dict[str, str], clip_duration: float
) -> tuple[float, float, list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    clip_start = _finite_float(row.get("clip_start_sec"))
    original_start = _finite_float(row.get("original_start_sec"))
    original_end = _finite_float(row.get("original_end_sec"))
    if (
        clip_start is not None
        and original_start is not None
        and original_end is not None
        and original_end > original_start
    ):
        start = max(0.0, original_start - clip_start)
        end = min(clip_duration, original_end - clip_start)
        if end > start:
            return start, end, warnings
    warnings.append(
        {
            "code": "CANDIDATE_INTERVAL_FALLBACK",
            "detail": "Candidate timestamps were invalid or absent; the full clip was analyzed.",
        }
    )
    return 0.0, clip_duration, warnings


def compute_acoustic_features(
    path: Path,
    row: dict[str, str],
    existing_quality: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Calculate the requested acoustic features for the candidate clip interval."""
    all_samples, sample_rate = load_wav(path)
    clip_duration = all_samples.size / sample_rate if sample_rate else 0.0
    start_sec, end_sec, warnings = _candidate_interval(row, clip_duration)
    start_sample = max(0, min(all_samples.size, round(start_sec * sample_rate)))
    end_sample = max(start_sample, min(all_samples.size, round(end_sec * sample_rate)))
    samples = all_samples[start_sample:end_sample]
    if samples.size == 0:
        raise SuggestionError("EMPTY_CANDIDATE_AUDIO", "Candidate interval has no samples.")

    quality = existing_quality or {}
    source_quality = quality.get("source_audio_quality", {})
    frame_values = _frame_dbfs(samples, sample_rate)
    reference = (
        _finite_float(source_quality.get("speech_reference_dbfs"))
        if isinstance(source_quality, dict)
        else None
    )
    source_voiced_threshold = (
        _finite_float(source_quality.get("voiced_threshold_dbfs"))
        if isinstance(source_quality, dict)
        else None
    )
    source_silence_threshold = (
        _finite_float(source_quality.get("silence_threshold_dbfs"))
        if isinstance(source_quality, dict)
        else None
    )
    if source_voiced_threshold is None:
        source_voiced_threshold = max(-45.0, (reference or max(frame_values)) - 8.0)
    if source_silence_threshold is None:
        source_silence_threshold = max(-55.0, (reference or max(frame_values)) - 10.0)

    voiced_ratio = (
        sum(value >= source_voiced_threshold for value in frame_values) / len(frame_values)
        if frame_values
        else 0.0
    )
    low_energy_ratio = (
        sum(value < source_silence_threshold for value in frame_values) / len(frame_values)
        if frame_values
        else 0.0
    )
    rms = _rms(samples)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    nonzero_signs = np.signbit(samples)
    zcr = (
        float(np.mean(nonzero_signs[1:] != nonzero_signs[:-1]))
        if samples.size > 1
        else 0.0
    )
    spectral = _spectral_features(samples, sample_rate)
    computed_contrast = _local_contrast_db(
        all_samples, start_sample, end_sample, sample_rate
    )
    manifest_quality = quality.get("manifest", {})
    existing_contrast = (
        _finite_float(manifest_quality.get("local_energy_contrast_db"))
        if isinstance(manifest_quality, dict)
        else None
    )
    return (
        {
            "duration_sec": round(samples.size / sample_rate, 6),
            "clip_duration_sec": round(clip_duration, 6),
            "analysis_start_sec": round(start_sec, 6),
            "analysis_end_sec": round(end_sec, 6),
            "sample_rate_hz": sample_rate,
            "rms": round(rms, 8),
            "dbfs": round(_dbfs(rms), 3),
            "peak_dbfs": round(_dbfs(peak), 3),
            "zero_crossing_rate": round(zcr, 6),
            **spectral,
            "periodicity_proxy": _periodicity_proxy(samples, sample_rate),
            "voiced_frame_ratio": round(voiced_ratio, 6),
            "low_energy_frame_ratio": round(low_energy_ratio, 6),
            "local_energy_contrast_db": (
                computed_contrast if computed_contrast is not None else existing_contrast
            ),
            "computed_local_energy_contrast_db": computed_contrast,
            "existing_quality_metrics": quality,
        },
        warnings,
    )


def _resolve_existing_file(value: str, manifest_path: Path) -> Path | None:
    if not value.strip():
        return None
    candidate = Path(value.strip())
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.is_file() else None


def load_existing_quality(
    row: dict[str, str],
    manifest_path: Path,
    cache: dict[Path, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    flags = [
        value.strip()
        for field in ("audio_quality_flags", "candidate_reasons")
        for value in row.get(field, "").split(";")
        if value.strip()
    ]
    quality: dict[str, Any] = {
        "manifest": {
            "mean_dbfs": _finite_float(row.get("mean_dbfs")),
            "voiced_frame_ratio": _finite_float(row.get("voiced_frame_ratio")),
            "local_energy_contrast_db": _finite_float(
                row.get("local_energy_contrast_db")
            ),
            "flags": list(dict.fromkeys(flags)),
        },
        "source_audio_quality": {},
    }
    metrics_value = row.get("source_metrics", "")
    if not metrics_value.strip():
        return quality, warnings
    metrics_path = _resolve_existing_file(metrics_value, manifest_path)
    if metrics_path is None:
        warnings.append(
            {
                "code": "SOURCE_METRICS_NOT_FOUND",
                "detail": metrics_value,
            }
        )
        return quality, warnings
    if metrics_path not in cache:
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
            cache[metrics_path] = payload if isinstance(payload, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            warnings.append(
                {
                    "code": "SOURCE_METRICS_INVALID",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            return quality, warnings
    source = cache[metrics_path].get("audio_quality", {})
    if isinstance(source, dict):
        reusable = [
            "estimated_noise_floor_dbfs",
            "speech_reference_dbfs",
            "voiced_threshold_dbfs",
            "silence_threshold_dbfs",
            "snr_proxy_db",
            "dynamic_range_db",
            "non_word_voiced_ratio",
            "non_word_energy_persistence_db",
            "background_noise_suspected",
            "reliability_flags",
        ]
        quality["source_audio_quality"] = {
            key: source[key] for key in reusable if key in source
        }
    return quality, warnings


def resolve_clip_path(row: dict[str, str], manifest_path: Path) -> Path | None:
    clip_value = row.get("clip_file", "").strip()
    if not clip_value:
        return None
    clip = Path(clip_value)
    if clip.is_absolute():
        return clip.resolve() if clip.is_file() else None
    candidates = [manifest_path.parent / clip]
    source_audio = row.get("source_audio", "").strip()
    if source_audio:
        candidates.append(manifest_path.parent / Path(source_audio).stem / clip)
    candidates.append(ANALYSIS_SERVER_ROOT / clip)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _timestamp_validity(
    words: list[dict[str, Any]], duration_sec: float
) -> dict[str, Any]:
    violations: list[str] = []
    valid_words = 0
    maximum_end = 0.0
    total_word_duration = 0.0
    previous_start = -math.inf
    for word in words:
        start = _finite_float(word.get("start"))
        end = _finite_float(word.get("end"))
        if start is None or end is None:
            violations.append("missing_or_non_finite_timestamp")
            continue
        valid_words += 1
        maximum_end = max(maximum_end, end)
        total_word_duration += max(0.0, end - start)
        if start < -0.05 or end < start:
            violations.append("invalid_word_interval")
        if start + 0.05 < previous_start:
            violations.append("non_monotonic_timestamp")
        if end > duration_sec + 0.25:
            violations.append("timestamp_exceeds_clip_duration")
        previous_start = start
    if total_word_duration > duration_sec + 0.35:
        violations.append("word_duration_exceeds_clip_duration")
    return {
        "applicable": bool(words),
        "valid": not violations if words else None,
        "clip_duration_sec": round(duration_sec, 6),
        "max_word_end_sec": round(maximum_end, 6) if words else None,
        "max_end_to_duration_ratio": (
            round(maximum_end / duration_sec, 6)
            if words and duration_sec > 0
            else None
        ),
        "total_word_duration_sec": round(total_word_duration, 6),
        "valid_word_count": valid_words,
        "violations": list(dict.fromkeys(violations)),
    }


def normalize_stt_result(
    raw: dict[str, Any], duration_sec: float, candidate_start: float, candidate_end: float
) -> dict[str, Any]:
    words: list[dict[str, Any]] = []
    for word in raw.get("detected_words", []):
        if not isinstance(word, dict):
            continue
        start = _finite_float(word.get("start"))
        end = _finite_float(word.get("end"))
        midpoint = (
            (start + end) / 2.0 if start is not None and end is not None else None
        )
        words.append(
            {
                "word": str(word.get("word", "")),
                "start": start,
                "end": end,
                "probability": _finite_float(word.get("probability")),
                "in_candidate_interval": (
                    midpoint is not None and candidate_start <= midpoint <= candidate_end
                ),
            }
        )
    probabilities = [
        float(word["probability"])
        for word in words
        if word["probability"] is not None
    ]
    average_probability = _finite_float(raw.get("average_probability"))
    if average_probability is None and probabilities:
        average_probability = sum(probabilities) / len(probabilities)
    no_speech = _finite_float(raw.get("no_speech_probability"))
    return {
        "transcript": str(raw.get("transcript", "")).strip(),
        "detected_words": words,
        "average_probability": _round(average_probability),
        "no_speech_probability": _round(no_speech),
        "timestamp_validity": _timestamp_validity(words, duration_sec),
        "configuration": dict(STT_CONFIGURATION),
        "error": raw.get("error"),
    }


class IsolatedWhisperTranscriber:
    """Lazily reuse one existing WhisperService/model for all review clips."""

    def __init__(self, service: WhisperService | None = None) -> None:
        self.service = service or WhisperService(model_name="turbo")

    def __call__(self, path: Path) -> dict[str, Any]:
        model = self.service.initialize()
        segment_generator, _ = model.transcribe(
            str(path),
            language="ko",
            task="transcribe",
            word_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        segments = list(segment_generator)
        words: list[dict[str, Any]] = []
        no_speech_values: list[float] = []
        transcript_parts: list[str] = []
        for segment in segments:
            transcript_parts.append(str(getattr(segment, "text", "")))
            no_speech = _finite_float(getattr(segment, "no_speech_prob", None))
            if no_speech is not None:
                no_speech_values.append(no_speech)
            for word in getattr(segment, "words", None) or []:
                words.append(
                    {
                        "word": str(getattr(word, "word", "")),
                        "start": getattr(word, "start", None),
                        "end": getattr(word, "end", None),
                        "probability": getattr(word, "probability", None),
                    }
                )
        probabilities = [
            value
            for value in (_finite_float(word.get("probability")) for word in words)
            if value is not None
        ]
        return {
            "transcript": "".join(transcript_parts).strip(),
            "detected_words": words,
            "average_probability": (
                sum(probabilities) / len(probabilities) if probabilities else None
            ),
            "no_speech_probability": (
                sum(no_speech_values) / len(no_speech_values)
                if no_speech_values
                else None
            ),
            "error": None,
        }


def _normalized_token(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).strip()


def _stt_evidence(stt: dict[str, Any], row: dict[str, str]) -> dict[str, Any]:
    candidate_words = [
        word
        for word in stt.get("detected_words", [])
        if word.get("in_candidate_interval")
    ]
    word_tokens = [
        (word, _normalized_token(str(word.get("word", ""))))
        for word in candidate_words
    ]
    word_tokens = [(word, token) for word, token in word_tokens if token]
    tokens = [token for _, token in word_tokens]
    boundary_tokens = {
        token
        for token in (
            _normalized_token(row.get("previous_word", "")),
            _normalized_token(row.get("next_word", "")),
        )
        if token
    }
    boundary_matches = [token for token in tokens if token in boundary_tokens]
    filler_tokens = [
        token
        for token in tokens
        if token in FILLER_TOKENS and token not in boundary_tokens
    ]
    meaningful = [
        token
        for token in tokens
        if (
            re.search(r"[가-힣]", token)
            and token not in FILLER_TOKENS
            and token not in boundary_tokens
        )
    ]
    probabilities = [
        float(word["probability"])
        for word, token in word_tokens
        if (
            token in meaningful
            and _finite_float(word.get("probability")) is not None
        )
    ]
    return {
        "candidate_words": candidate_words,
        "tokens": tokens,
        "filler_tokens": filler_tokens,
        "meaningful_tokens": meaningful,
        "boundary_matches": boundary_matches,
        "candidate_average_probability": (
            sum(probabilities) / len(probabilities) if probabilities else None
        ),
    }


def apply_confidence_policy(
    label: str, confidence: float, reasons: Iterable[str]
) -> tuple[str, float, list[str]]:
    """Apply the experimental 0.55 threshold and human-only label cap."""
    if label not in ALLOWED_LABELS:
        label = "unknown"
    confidence = max(0.0, min(1.0, float(confidence)))
    output_reasons = list(reasons)
    if label in {"filler", "breath"} and confidence > HUMAN_ONLY_LABEL_CONFIDENCE_CAP:
        confidence = HUMAN_ONLY_LABEL_CONFIDENCE_CAP
        output_reasons.append(
            "filler/breath confidence capped at 0.75 without human listening"
        )
    if confidence < MIN_CONFIDENCE and label != "unknown":
        output_reasons.append(
            "confidence below experimental 0.55 threshold; changed to unknown"
        )
        label = "unknown"
    return label, round(confidence, 6), output_reasons


def suggest_label(
    features: dict[str, Any],
    stt: dict[str, Any],
    row: dict[str, str],
) -> tuple[str, float, list[str]]:
    """Apply conservative, auditable heuristic rules."""
    evidence = _stt_evidence(stt, row)
    meaningful = evidence["meaningful_tokens"]
    fillers = evidence["filler_tokens"]
    candidate_probability = evidence["candidate_average_probability"]
    timestamp_valid = stt.get("timestamp_validity", {}).get("valid")
    transcript_empty = not stt.get("transcript", "").strip()
    dbfs = float(features.get("dbfs", -100.0))
    periodicity = float(features.get("periodicity_proxy", 0.0))
    flatness = float(features.get("spectral_flatness", 0.0))
    centroid = float(features.get("spectral_centroid_hz", 0.0))
    zcr = float(features.get("zero_crossing_rate", 0.0))
    duration = float(features.get("duration_sec", 0.0))
    voiced = float(features.get("voiced_frame_ratio", 0.0))
    low_energy = float(features.get("low_energy_frame_ratio", 0.0))
    existing = features.get("existing_quality_metrics", {})
    manifest_quality = existing.get("manifest", {}) if isinstance(existing, dict) else {}
    source_quality = (
        existing.get("source_audio_quality", {}) if isinstance(existing, dict) else {}
    )
    existing_voiced = _finite_float(manifest_quality.get("voiced_frame_ratio"))
    flags = {
        str(flag)
        for flag in manifest_quality.get("flags", [])
        if isinstance(flag, str)
    }
    flags.update(
        str(flag)
        for flag in source_quality.get("reliability_flags", [])
        if isinstance(flag, str)
    )
    background = (
        "background_noise_suspected" in flags
        or bool(source_quality.get("background_noise_suspected"))
    )
    high_non_word = "high_non_word_voiced_ratio" in flags or (
        (_finite_float(source_quality.get("non_word_voiced_ratio")) or 0.0) >= 0.4
    )

    if (
        transcript_empty
        and (
            (dbfs <= -50.0 and voiced <= 0.15 and low_energy >= 0.8)
            or (
                row.get("event_type") in {"pause", "long_silence"}
                and existing_voiced is not None
                and existing_voiced <= 0.15
                and dbfs <= -20.0
                and low_energy >= 0.5
            )
        )
    ):
        return apply_confidence_policy(
            "silence",
            0.95 if dbfs <= -50.0 else 0.86,
            [
                "isolated STT is empty",
                "low energy and low voiced-frame evidence",
            ],
        )

    if background and high_non_word:
        reasons = [
            "background_noise_suspected flag is present",
            "high non-word voiced ratio is present",
        ]
        if flatness >= 0.35:
            reasons.append("spectral flatness supports broadband noise")
        if periodicity < 0.45:
            reasons.append("low periodicity supports noise")
        return apply_confidence_policy("noise", 0.84, reasons)

    sustained_noise = (
        not meaningful
        and not fillers
        and duration >= 0.6
        and dbfs > -50.0
        and flatness >= 0.45
        and periodicity < 0.4
    )
    if sustained_noise:
        return apply_confidence_policy(
            "noise",
            0.85,
            [
                "sustained non-word energy",
                "high spectral flatness",
                "low periodicity",
            ],
        )

    if (
        meaningful
        and candidate_probability is not None
        and candidate_probability >= 0.65
        and timestamp_valid is True
        and not background
        and (
            voiced >= 0.25
            or (existing_voiced is not None and existing_voiced >= 0.35)
        )
        and low_energy <= 0.8
    ):
        confidence = min(0.92, 0.76 + 0.18 * candidate_probability)
        return apply_confidence_policy(
            "normal_speech",
            confidence,
            [
                "meaningful Korean token recognized inside candidate interval",
                "word probability is sufficient",
                "timestamps are plausible for clip duration",
            ],
        )

    no_speech = _finite_float(stt.get("no_speech_probability"))
    if (
        stt.get("transcript", "").strip()
        and not meaningful
        and not fillers
        and (
            dbfs <= -48.0
            or (no_speech is not None and no_speech >= 0.75)
            or timestamp_valid is False
        )
    ):
        return apply_confidence_policy(
            "whisper_hallucination",
            0.68,
            [
                "STT text lacks supported candidate words",
                "low acoustic support, high no-speech probability, or implausible timestamps",
            ],
        )

    filler_candidate = (
        0.2 <= duration <= 1.5
        and voiced >= 0.45
        and periodicity >= 0.35
        and (
            (_finite_float(features.get("local_energy_contrast_db")) or 0.0) >= 2.0
            or dbfs >= -32.0
        )
    )
    if filler_candidate:
        confidence = 0.68 if fillers else 0.52
        reasons = [
            "short voiced periodic vocalization",
            "energy is locally or absolutely elevated",
        ]
        if fillers:
            reasons.append(
                "isolated STT returned a filler-like token, used only as supporting evidence"
            )
        else:
            reasons.append("no reliable filler token; candidate remains weak")
        if evidence["boundary_matches"]:
            reasons.append(
                "recognized text matches adjacent manifest words and is excluded as padding leakage"
            )
        return apply_confidence_policy("filler", confidence, reasons)

    breath_candidate = (
        duration <= 0.8
        and dbfs > -55.0
        and not meaningful
        and not fillers
        and periodicity < 0.35
        and flatness >= 0.25
        and (centroid >= 1600.0 or zcr >= 0.12)
    )
    if breath_candidate:
        return apply_confidence_policy(
            "breath",
            0.64,
            [
                "short aperiodic broadband energy",
                "high spectral centroid or zero-crossing rate",
                "no meaningful isolated STT",
            ],
        )

    conflicts: list[str] = []
    if meaningful:
        conflicts.append("meaningful STT exists but probability/timestamp support is insufficient")
    if fillers:
        conflicts.append("filler-like STT exists without enough combined acoustic support")
    if evidence["boundary_matches"]:
        conflicts.append(
            "recognized text matches adjacent manifest words and is excluded as padding leakage"
        )
    if duration < 0.2:
        conflicts.append("candidate is too short for a reliable distinction")
    if not conflicts:
        conflicts.append("filler, breath, speech, noise, and silence evidence is insufficient")
    return "unknown", 0.5, conflicts + [
        "conservative unknown fallback; experimental heuristic only"
    ]


def _empty_stt(error: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "transcript": "",
        "detected_words": [],
        "average_probability": None,
        "no_speech_probability": None,
        "timestamp_validity": {
            "applicable": False,
            "valid": None,
            "clip_duration_sec": None,
            "max_word_end_sec": None,
            "max_end_to_duration_ratio": None,
            "total_word_duration_sec": 0.0,
            "valid_word_count": 0,
            "violations": [],
        },
        "configuration": dict(STT_CONFIGURATION),
        "error": error,
    }


def _base_item(row: dict[str, str]) -> dict[str, Any]:
    return {
        "review_id": row.get("review_id", ""),
        "clip_file": row.get("clip_file", ""),
        "original_event_type": row.get("event_type", ""),
        "suggested_label": "unknown",
        "suggested_confidence": 0.0,
        "suggested_reasons": [],
        "requires_human_review": True,
        "acoustic_features": {},
        "isolated_stt": _empty_stt(),
        "warnings": [
            {
                "code": "HEURISTIC_SUGGESTION_NOT_GROUND_TRUTH",
                "detail": "Human listening is required before assigning reviewer_label.",
            },
            {
                "code": "DO_NOT_USE_FOR_SCORING",
                "detail": "Do not use this suggestion for scores, penalties, or interview evaluation.",
            },
        ],
        "error": None,
    }


def _result(manifest_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "description": (
            "Heuristic speech-review suggestions only; not human ground truth. "
            "Never copy automatically to reviewer_label and never use for scoring, "
            "penalties, or interview evaluation."
        ),
        "source_manifest": str(manifest_path),
        "stt_configuration": dict(STT_CONFIGURATION),
        "confidence_policy": {
            "experimental": True,
            "strong_recommendation_min": 0.80,
            "reference_recommendation_min": 0.55,
            "below_0_55_label": "unknown",
            "filler_breath_without_listening_cap": 0.75,
        },
        "items": [],
        "warnings": [],
        "error": None,
    }


def suggest_manifest(
    manifest_path: Path | str,
    *,
    stt_runner: SttRunner | None = None,
) -> dict[str, Any]:
    """Read a manifest without modifying it and suggest labels for its clips."""
    path = Path(manifest_path)
    result = _result(path)
    if not path.is_file():
        result["error"] = {"code": "MANIFEST_NOT_FOUND", "detail": str(path)}
        return result
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise SuggestionError("MANIFEST_INVALID", "CSV header is missing.")
            missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames))
            if missing:
                raise SuggestionError(
                    "MANIFEST_INVALID",
                    "Missing required columns: " + ", ".join(missing),
                )
            rows = list(reader)
    except SuggestionError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
        return result
    except (OSError, UnicodeError, csv.Error) as exc:
        result["error"] = {
            "code": "MANIFEST_INVALID",
            "detail": f"{type(exc).__name__}: {exc}",
        }
        return result

    transcriber = stt_runner or IsolatedWhisperTranscriber()
    metrics_cache: dict[Path, dict[str, Any]] = {}
    for row_index, row in enumerate(rows, start=2):
        item = _base_item(row)
        clip_path = resolve_clip_path(row, path)
        if clip_path is None:
            warning = {
                "code": "CLIP_FILE_NOT_FOUND",
                "detail": row.get("clip_file", ""),
            }
            item["warnings"].append(warning)
            item["error"] = warning
            item["suggested_reasons"] = ["missing clip; no automatic label attempted"]
            result["warnings"].append(
                {"row": row_index, "review_id": item["review_id"], **warning}
            )
            result["items"].append(item)
            continue

        existing, quality_warnings = load_existing_quality(row, path, metrics_cache)
        item["warnings"].extend(quality_warnings)
        try:
            features, acoustic_warnings = compute_acoustic_features(
                clip_path, row, existing
            )
            item["acoustic_features"] = features
            item["warnings"].extend(acoustic_warnings)
        except SuggestionError as exc:
            item["error"] = {"code": exc.code, "detail": exc.detail}
            item["warnings"].append(item["error"])
            item["suggested_reasons"] = ["audio feature extraction failed"]
            result["warnings"].append(
                {
                    "row": row_index,
                    "review_id": item["review_id"],
                    "code": exc.code,
                    "detail": exc.detail,
                }
            )
            result["items"].append(item)
            continue

        try:
            raw_stt = transcriber(clip_path)
            item["isolated_stt"] = normalize_stt_result(
                raw_stt,
                float(features["clip_duration_sec"]),
                float(features["analysis_start_sec"]),
                float(features["analysis_end_sec"]),
            )
        except Exception as exc:  # model/runtime failures remain per-item evidence gaps
            stt_error = {
                "code": "ISOLATED_STT_FAILED",
                "detail": f"{type(exc).__name__}: {exc}",
            }
            item["isolated_stt"] = _empty_stt(stt_error)
            item["isolated_stt"]["timestamp_validity"]["clip_duration_sec"] = features[
                "clip_duration_sec"
            ]
            item["warnings"].append(stt_error)
            result["warnings"].append(
                {"row": row_index, "review_id": item["review_id"], **stt_error}
            )

        label, confidence, reasons = suggest_label(
            features, item["isolated_stt"], row
        )
        item["suggested_label"] = label
        item["suggested_confidence"] = confidence
        item["suggested_reasons"] = reasons
        result["items"].append(item)
    return result


def _validate_json(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NaN and Infinity are not permitted.")
    if isinstance(value, dict):
        for nested in value.values():
            _validate_json(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _validate_json(nested)


def write_json(path: Path | str, result: dict[str, Any]) -> None:
    output = Path(path)
    try:
        _validate_json(result)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, TypeError, ValueError) as exc:
        raise SuggestionError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def write_csv(path: Path | str, items: Iterable[dict[str, Any]]) -> None:
    output = Path(path)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            for item in items:
                row = dict(item)
                for field in (
                    "suggested_reasons",
                    "acoustic_features",
                    "isolated_stt",
                    "warnings",
                    "error",
                ):
                    row[field] = json.dumps(
                        row[field], ensure_ascii=False, allow_nan=False
                    )
                writer.writerow(row)
    except (OSError, TypeError, ValueError, csv.Error) as exc:
        raise SuggestionError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stt_runner: SttRunner | None = None,
) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = suggest_manifest(args.manifest, stt_runner=stt_runner)
    if result["error"] is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    try:
        write_json(args.json_output, result)
        write_csv(args.csv_output, result["items"])
    except SuggestionError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    summary = {
        "success": True,
        "source_manifest": str(args.manifest),
        "json_output": str(args.json_output),
        "csv_output": str(args.csv_output),
        "item_count": len(result["items"]),
        "warning_count": len(result["warnings"]),
        "notice": result["description"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
