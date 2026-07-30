"""Conservative dual-estimator validation for objective prosody metrics.

Version 2 keeps the version-1 normalized-autocorrelation implementation intact,
adds a numpy-only YIN-like CMNDF estimator, and only applies octave correction
when local voiced-region evidence is sufficient.  Results are measurements,
not human traits, scores, or interview assessments.
"""

from __future__ import annotations

import json
import math
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from app.speech.prosody_metrics import (
    ProsodyAnalysisError,
    ProsodyConfiguration,
    estimate_frame_f0,
    strict_json_text,
    write_json_atomic,
)
from app.speech.speech_metrics import analyze_interval, load_pcm16_mono_wav


@dataclass(frozen=True)
class ProsodyValidationConfiguration:
    pitch_frame_ms: int = 40
    hop_ms: int = 10
    min_f0_hz: float = 60.0
    max_f0_hz: float = 400.0
    autocorrelation_min_confidence: float = 0.35
    yin_threshold: float = 0.15
    yin_fallback_threshold: float = 0.30
    yin_min_confidence: float = 0.70
    estimator_agreement_semitones: float = 0.75
    octave_relation_semitones: float = 12.0
    octave_tolerance_semitones: float = 0.75
    local_continuity_window_ms: int = 200
    local_min_support_frames: int = 3
    correction_min_improvement_semitones: float = 1.5
    large_pitch_jump_semitones: float = 3.0
    minimum_noise_margin_db: float = 6.0
    background_minimum_noise_margin_db: float = 10.0
    maximum_zero_crossing_rate: float = 0.35
    clipping_amplitude_ratio: float = 0.99
    clipping_warning_ratio: float = 0.01
    low_pitch_coverage_threshold: float = 0.40
    low_agreement_ratio_threshold: float = 0.60
    fallback_voiced_threshold_dbfs: float = -45.0
    fallback_silence_threshold_dbfs: float = -55.0
    fallback_noise_floor_dbfs: float = -60.0
    word_boundary_margin_sec: float = 0.03
    minimum_segment_pitch_frames: int = 3
    ending_window_ms: int = 500
    ending_pattern_threshold_semitones: float = 1.0

    def validate(self) -> None:
        if self.pitch_frame_ms <= 0 or self.hop_ms <= 0:
            raise ValueError("Frame and hop durations must be positive.")
        if self.min_f0_hz <= 0 or self.max_f0_hz <= self.min_f0_hz:
            raise ValueError("F0 bounds are invalid.")
        for name in (
            "autocorrelation_min_confidence",
            "yin_threshold",
            "yin_fallback_threshold",
            "yin_min_confidence",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1].")
        if self.yin_threshold > self.yin_fallback_threshold:
            raise ValueError("yin_threshold must not exceed fallback threshold.")
        if self.local_continuity_window_ms <= 0:
            raise ValueError("local_continuity_window_ms must be positive.")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any, digits: int = 6) -> float | None:
    number = _finite(value)
    return None if number is None else round(number, digits)


def _mean(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return float(np.mean(array)) if array.size else None


def _median(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return float(np.median(array)) if array.size else None


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return float(np.percentile(array, percentile)) if array.size else None


def semitone_difference(first_hz: Any, second_hz: Any) -> float | None:
    first = _finite(first_hz)
    second = _finite(second_hz)
    if first is None or second is None or first <= 0 or second <= 0:
        return None
    return abs(12.0 * math.log2(first / second))


def estimate_yin_f0(
    samples: np.ndarray,
    sample_rate: int,
    configuration: ProsodyValidationConfiguration | None = None,
) -> tuple[float | None, float]:
    """Estimate one frame using a YIN-like difference/CMNDF procedure."""
    config = configuration or ProsodyValidationConfiguration()
    config.validate()
    values = np.asarray(samples, dtype=np.float64)
    if values.size < 4 or not np.any(values):
        return None, 0.0
    values = values - float(np.mean(values))
    windowed = values * np.hanning(values.size)
    energy = float(np.dot(windowed, windowed))
    if energy <= 1e-12:
        return None, 0.0

    minimum_lag = max(2, math.ceil(sample_rate / config.max_f0_hz))
    maximum_lag = min(values.size - 2, math.floor(sample_rate / config.min_f0_hz))
    if maximum_lag <= minimum_lag:
        return None, 0.0

    # Wiener-Khinchin supplies all lagged dot products; cumulative squared
    # energies account for the shrinking overlap in the YIN difference.
    fft_size = 1
    while fft_size < 2 * windowed.size:
        fft_size *= 2
    spectrum = np.fft.rfft(windowed, n=fft_size)
    autocorrelation = np.fft.irfft(
        spectrum * np.conjugate(spectrum), n=fft_size
    ).real[: maximum_lag + 1]
    squares = windowed * windowed
    cumulative = np.concatenate(([0.0], np.cumsum(squares)))
    lags = np.arange(1, maximum_lag + 1, dtype=np.int32)
    first_energy = cumulative[windowed.size - lags]
    second_energy = cumulative[windowed.size] - cumulative[lags]
    difference = np.maximum(
        0.0,
        first_energy + second_energy - 2.0 * autocorrelation[lags],
    )

    cmndf = np.ones(maximum_lag + 1, dtype=np.float64)
    running = np.cumsum(difference)
    nonzero = running > 1e-12
    normalized = np.ones_like(difference)
    normalized[nonzero] = (
        difference[nonzero] * lags[nonzero] / running[nonzero]
    )
    cmndf[1:] = normalized

    candidate_lag: int | None = None
    lag = minimum_lag
    while lag <= maximum_lag:
        if cmndf[lag] < config.yin_threshold:
            while lag < maximum_lag and cmndf[lag + 1] <= cmndf[lag]:
                lag += 1
            candidate_lag = lag
            break
        lag += 1
    if candidate_lag is None:
        local = cmndf[minimum_lag : maximum_lag + 1]
        candidate_lag = minimum_lag + int(np.argmin(local))
        if cmndf[candidate_lag] > config.yin_fallback_threshold:
            confidence = max(0.0, min(1.0, 1.0 - float(cmndf[candidate_lag])))
            return None, confidence

    interpolated_lag = float(candidate_lag)
    if minimum_lag < candidate_lag < maximum_lag:
        left = float(cmndf[candidate_lag - 1])
        center = float(cmndf[candidate_lag])
        right = float(cmndf[candidate_lag + 1])
        denominator = left - 2.0 * center + right
        if abs(denominator) > 1e-12:
            offset = 0.5 * (left - right) / denominator
            if abs(offset) <= 1.0:
                interpolated_lag += offset
    confidence = max(0.0, min(1.0, 1.0 - float(cmndf[candidate_lag])))
    if interpolated_lag <= 0:
        return None, confidence
    f0 = sample_rate / interpolated_lag
    if not config.min_f0_hz <= f0 <= config.max_f0_hz:
        return None, confidence
    return float(f0), confidence


def classify_estimator_relation(
    autocorrelation_f0_hz: Any,
    yin_f0_hz: Any,
    configuration: ProsodyValidationConfiguration | None = None,
) -> dict[str, Any]:
    config = configuration or ProsodyValidationConfiguration()
    difference = semitone_difference(autocorrelation_f0_hz, yin_f0_hz)
    agreement = (
        difference is not None
        and difference <= config.estimator_agreement_semitones
    )
    octave = (
        difference is not None
        and abs(difference - config.octave_relation_semitones)
        <= config.octave_tolerance_semitones
    )
    first = _finite(autocorrelation_f0_hz)
    second = _finite(yin_f0_hz)
    lower_source = None
    higher_source = None
    if octave and first is not None and second is not None:
        lower_source = "autocorrelation" if first < second else "yin"
        higher_source = "yin" if first < second else "autocorrelation"
    return {
        "estimator_difference_semitones": _round(difference, 6),
        "estimator_agreement": bool(agreement),
        "estimator_disagreement": bool(
            first is not None and second is not None and not agreement
        ),
        "octave_halving_candidate": bool(octave),
        "octave_doubling_candidate": bool(octave),
        "subharmonic_candidate": lower_source,
        "harmonic_candidate": higher_source,
        "unresolved_pitch_candidate": bool(
            first is not None and second is not None and not agreement
        ),
    }


def select_estimator_f0(
    autocorrelation_f0_hz: Any,
    autocorrelation_confidence: Any,
    yin_f0_hz: Any,
    yin_confidence: Any,
    configuration: ProsodyValidationConfiguration | None = None,
) -> dict[str, Any]:
    config = configuration or ProsodyValidationConfiguration()
    acf = _finite(autocorrelation_f0_hz)
    yin = _finite(yin_f0_hz)
    acf_conf = _finite(autocorrelation_confidence) or 0.0
    yin_conf = _finite(yin_confidence) or 0.0
    relation = classify_estimator_relation(acf, yin, config)
    selected: float | None = None
    reason = "no_valid_estimator"
    if acf is not None and yin is not None and relation["estimator_agreement"]:
        total = max(1e-12, acf_conf + yin_conf)
        selected = (acf * acf_conf + yin * yin_conf) / total
        reason = "confidence_weighted_estimator_agreement"
    elif acf is not None and yin is not None:
        if acf_conf >= yin_conf:
            selected = acf
            reason = "autocorrelation_higher_confidence_disagreement"
        else:
            selected = yin
            reason = "yin_higher_confidence_disagreement"
    elif acf is not None and acf_conf >= config.autocorrelation_min_confidence:
        selected = acf
        reason = "autocorrelation_only"
    elif yin is not None and yin_conf >= config.yin_min_confidence:
        selected = yin
        reason = "yin_only"
    return {
        **relation,
        "selected_f0_hz": _round(selected, 3),
        "selection_reason": reason,
    }


def _load_json(path: Path, missing_code: str, invalid_code: str) -> dict[str, Any]:
    if not path.is_file():
        raise ProsodyAnalysisError(missing_code, str(path))
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"Non-finite JSON constant: {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProsodyAnalysisError(
            invalid_code, f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("error"):
        raise ProsodyAnalysisError(
            invalid_code, "JSON root is not a successful result object."
        )
    return payload


def _word_intervals(stt: dict[str, Any]) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for segment in stt.get("segments", []):
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words") or []:
            if not isinstance(word, dict):
                continue
            start = _finite(word.get("start"))
            end = _finite(word.get("end"))
            if start is not None and end is not None and end > start:
                intervals.append((start, end))
    if not intervals:
        raise ProsodyAnalysisError(
            "WORD_TIMESTAMPS_NOT_FOUND",
            "STT result contains no words with start/end timestamps.",
        )
    return intervals


def _in_word(
    center_sec: float,
    intervals: list[tuple[float, float]],
    margin_sec: float,
) -> bool:
    return any(
        start - margin_sec <= center_sec <= end + margin_sec
        for start, end in intervals
    )


def _zero_crossing_rate(values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    centered = values - float(np.mean(values))
    signs = np.signbit(centered)
    return float(np.count_nonzero(signs[1:] != signs[:-1]) / (values.size - 1))


def _voiced_gate(
    *,
    dbfs: float,
    noise_floor_dbfs: float,
    voiced_threshold_dbfs: float,
    autocorrelation_f0_hz: float | None,
    autocorrelation_confidence: float,
    yin_f0_hz: float | None,
    yin_confidence: float,
    estimator_agreement: bool,
    zero_crossing_rate: float,
    word_active: bool,
    clipping: bool,
    background_noise_suspected: bool,
    configuration: ProsodyValidationConfiguration,
) -> tuple[bool, list[str], list[str]]:
    reasons: list[str] = []
    invalid: list[str] = []
    energy_ok = dbfs >= voiced_threshold_dbfs
    noise_margin = dbfs - noise_floor_dbfs
    required_margin = (
        configuration.background_minimum_noise_margin_db
        if background_noise_suspected
        else configuration.minimum_noise_margin_db
    )
    margin_ok = noise_margin >= required_margin
    acf_ok = (
        autocorrelation_f0_hz is not None
        and autocorrelation_confidence
        >= configuration.autocorrelation_min_confidence
    )
    yin_ok = (
        yin_f0_hz is not None
        and yin_confidence >= configuration.yin_min_confidence
    )
    periodic_ok = estimator_agreement or (acf_ok and yin_ok)
    zcr_ok = zero_crossing_rate <= configuration.maximum_zero_crossing_rate

    if energy_ok:
        reasons.append("frame_energy_above_voiced_threshold")
    else:
        invalid.append("energy_below_voiced_threshold")
    if margin_ok:
        reasons.append("energy_above_noise_floor_margin")
    else:
        invalid.append("insufficient_noise_floor_margin")
    if acf_ok:
        reasons.append("autocorrelation_confident")
    if yin_ok:
        reasons.append("yin_confident")
    if estimator_agreement:
        reasons.append("estimators_agree")
    if not periodic_ok:
        invalid.append("insufficient_periodicity_evidence")
    if zcr_ok:
        reasons.append("zero_crossing_rate_compatible")
    else:
        invalid.append("zero_crossing_rate_too_high")
    if word_active:
        reasons.append("inside_stt_word_region")
    if clipping:
        invalid.append("clipping_frame_excluded")
    if background_noise_suspected:
        reasons.append("background_noise_strict_gate_applied")
        if not word_active:
            invalid.append("background_noise_outside_word_region")
        if not estimator_agreement:
            invalid.append("background_noise_requires_estimator_agreement")

    valid = (
        energy_ok
        and margin_ok
        and periodic_ok
        and zcr_ok
        and not clipping
        and (
            not background_noise_suspected
            or (word_active and estimator_agreement)
        )
    )
    return valid, reasons, invalid


def _assign_voiced_regions(frames: list[dict[str, Any]]) -> None:
    region_id = -1
    active = False
    for frame in frames:
        gate = bool(frame.get("voiced_gate_passed"))
        if gate and not active:
            region_id += 1
        frame["voiced_region_id"] = region_id if gate else None
        active = gate


def _continuity_neighbors(
    frames: list[dict[str, Any]],
    index: int,
    configuration: ProsodyValidationConfiguration,
) -> list[float]:
    region = frames[index].get("voiced_region_id")
    if region is None:
        return []
    radius = max(
        1,
        round(
            configuration.local_continuity_window_ms
            / configuration.hop_ms
        ),
    )
    values: list[float] = []
    for neighbor_index in range(
        max(0, index - radius),
        min(len(frames), index + radius + 1),
    ):
        if neighbor_index == index:
            continue
        neighbor = frames[neighbor_index]
        if neighbor.get("voiced_region_id") != region:
            continue
        if not neighbor.get("estimator_agreement"):
            continue
        value = _finite(neighbor.get("raw_selected_f0_hz"))
        if value is not None:
            values.append(value)
    return values


def apply_octave_corrections(
    frames: list[dict[str, Any]],
    configuration: ProsodyValidationConfiguration | None = None,
    *,
    background_noise_suspected: bool = False,
    clipping_excessive: bool = False,
) -> list[dict[str, Any]]:
    """Apply locally supported octave corrections without crossing regions."""
    config = configuration or ProsodyValidationConfiguration()
    _assign_voiced_regions(frames)
    for index, frame in enumerate(frames):
        raw = _finite(
            frame.get("raw_selected_f0_hz", frame.get("selected_f0_hz"))
        )
        frame["raw_selected_f0_hz"] = _round(raw, 3)
        frame["corrected_f0_hz"] = _round(raw, 3)
        frame["correction_applied"] = False
        frame["correction_type"] = None
        frame["correction_confidence"] = 0.0
        frame["correction_reasons"] = []

        if not frame.get("voiced_gate_passed") or raw is None:
            frame["valid"] = False
            continue
        if frame.get("estimator_agreement"):
            frame["valid"] = True
            frame["unresolved_pitch_candidate"] = False
            continue

        acf = _finite(frame.get("autocorrelation_f0_hz"))
        yin = _finite(frame.get("yin_f0_hz"))
        relation = classify_estimator_relation(acf, yin, config)
        if not relation["octave_halving_candidate"]:
            frame["valid"] = False
            if "non_octave_estimator_disagreement" not in frame["invalid_reasons"]:
                frame["invalid_reasons"].append(
                    "non_octave_estimator_disagreement"
                )
            continue
        if background_noise_suspected or clipping_excessive or frame.get("clipping"):
            frame["valid"] = False
            frame["invalid_reasons"].append(
                "octave_correction_blocked_by_quality_warning"
            )
            continue

        neighbors = _continuity_neighbors(frames, index, config)
        if len(neighbors) < config.local_min_support_frames:
            frame["valid"] = False
            frame["invalid_reasons"].append(
                "insufficient_local_continuity_support"
            )
            continue
        local_median = float(np.median(neighbors))
        candidates = [
            ("autocorrelation", acf),
            ("yin", yin),
        ]
        candidates = [
            (name, value) for name, value in candidates if value is not None
        ]
        if len(candidates) != 2:
            frame["valid"] = False
            frame["invalid_reasons"].append("octave_pair_incomplete")
            continue
        distances = [
            (semitone_difference(value, local_median) or 0.0, name, value)
            for name, value in candidates
        ]
        distances.sort()
        best_distance, best_name, best_value = distances[0]
        raw_distance = semitone_difference(raw, local_median)
        improvement = (
            (raw_distance or 0.0) - best_distance
            if raw_distance is not None
            else 0.0
        )
        if (
            math.isclose(best_value, raw, rel_tol=1e-6, abs_tol=1e-6)
            or improvement < config.correction_min_improvement_semitones
        ):
            frame["valid"] = False
            frame["invalid_reasons"].append(
                "correction_does_not_reduce_local_jump_enough"
            )
            continue

        frame["corrected_f0_hz"] = _round(best_value, 3)
        frame["correction_applied"] = True
        frame["correction_type"] = (
            "octave_halving_correction"
            if best_value < raw
            else "octave_doubling_correction"
        )
        estimator_confidence = _finite(
            frame.get(f"{best_name}_confidence")
        ) or 0.0
        support = min(1.0, len(neighbors) / max(1, 2 * config.local_min_support_frames))
        frame["correction_confidence"] = round(
            min(1.0, 0.6 * estimator_confidence + 0.4 * support), 6
        )
        frame["correction_reasons"] = [
            f"{best_name}_matches_local_voiced_region_median",
            "estimators_have_octave_relation",
            "local_pitch_jump_reduced",
            "quality_warnings_do_not_block_correction",
        ]
        frame["valid"] = True
        frame["unresolved_pitch_candidate"] = False
    return frames


def track_jump_metrics(
    frames: list[dict[str, Any]],
    field: str,
    configuration: ProsodyValidationConfiguration | None = None,
    *,
    valid_only: bool = False,
) -> dict[str, Any]:
    config = configuration or ProsodyValidationConfiguration()
    jumps: list[float] = []
    previous: float | None = None
    previous_region: Any = None
    previous_index: int | None = None
    for index, frame in enumerate(frames):
        value = _finite(frame.get(field))
        region = frame.get("voiced_region_id")
        if valid_only and not frame.get("valid"):
            value = None
        if (
            value is not None
            and previous is not None
            and region is not None
            and region == previous_region
            and previous_index == index - 1
        ):
            difference = semitone_difference(value, previous)
            if difference is not None:
                jumps.append(difference)
        if value is None or region is None:
            previous = None
            previous_region = None
            previous_index = None
        else:
            previous = value
            previous_region = region
            previous_index = index
    return {
        "total_pitch_jump_semitones": _round(sum(jumps), 6),
        "mean_pitch_jump_semitones": _round(_mean(jumps), 6),
        "large_pitch_jump_count": sum(
            value >= config.large_pitch_jump_semitones for value in jumps
        ),
        "adjacent_pitch_transition_count": len(jumps),
    }


def _pitch_summary(
    frames: list[dict[str, Any]],
    field: str,
    configuration: ProsodyValidationConfiguration,
    *,
    valid_only: bool,
) -> dict[str, Any]:
    values = [
        float(frame[field])
        for frame in frames
        if _finite(frame.get(field)) is not None
        and (not valid_only or frame.get("valid"))
        and frame.get("voiced_gate_passed")
    ]
    reference = _median(values)
    semitones = (
        [12.0 * math.log2(value / reference) for value in values]
        if reference is not None and reference > 0
        else []
    )
    p10_hz = _percentile(values, 10)
    p90_hz = _percentile(values, 90)
    p10_st = _percentile(semitones, 10)
    p90_st = _percentile(semitones, 90)
    total = len(frames)
    voiced = sum(bool(frame.get("voiced_gate_passed")) for frame in frames)
    summary = {
        "pitch_valid_frame_count": len(values),
        "pitch_voiced_frame_count": voiced,
        "pitch_total_frame_count": total,
        "pitch_coverage_ratio": round(len(values) / total, 6) if total else 0.0,
        "pitch_voiced_coverage_ratio": (
            round(len(values) / voiced, 6) if voiced else 0.0
        ),
        "pitch_mean_hz": _round(_mean(values), 3),
        "pitch_median_hz": _round(reference, 3),
        "pitch_p10_hz": _round(p10_hz, 3),
        "pitch_p90_hz": _round(p90_hz, 3),
        "pitch_range_hz": (
            _round(p90_hz - p10_hz, 3)
            if p10_hz is not None and p90_hz is not None
            else None
        ),
        "pitch_range_semitones": (
            _round(p90_st - p10_st, 6)
            if p10_st is not None and p90_st is not None
            else None
        ),
    }
    summary.update(
        track_jump_metrics(
            frames,
            field,
            configuration,
            valid_only=valid_only,
        )
    )
    return summary


def _loudness_summary(frames: list[dict[str, Any]]) -> dict[str, Any]:
    voiced = [
        float(frame["dbfs"])
        for frame in frames
        if frame.get("voiced_gate_passed")
        and _finite(frame.get("dbfs")) is not None
    ]
    peaks = [
        float(frame["peak_dbfs"])
        for frame in frames
        if _finite(frame.get("peak_dbfs")) is not None
    ]
    p10 = _percentile(voiced, 10)
    p90 = _percentile(voiced, 90)
    return {
        "voiced_loudness_mean_dbfs": _round(_mean(voiced), 3),
        "voiced_loudness_median_dbfs": _round(_median(voiced), 3),
        "voiced_loudness_p10_dbfs": _round(p10, 3),
        "voiced_loudness_p90_dbfs": _round(p90, 3),
        "voiced_loudness_range_db": (
            _round(p90 - p10, 3)
            if p10 is not None and p90 is not None
            else None
        ),
        "peak_dbfs": _round(max(peaks), 3) if peaks else None,
        "clipping_frame_ratio": (
            round(
                sum(bool(frame.get("clipping")) for frame in frames)
                / len(frames),
                6,
            )
            if frames
            else 0.0
        ),
    }


def _ending_summary(
    frames: list[dict[str, Any]],
    configuration: ProsodyValidationConfiguration,
) -> dict[str, Any]:
    valid = [
        frame
        for frame in frames
        if frame.get("valid")
        and _finite(frame.get("corrected_f0_hz")) is not None
    ]
    if len(valid) < 2:
        return {
            "ending_pitch_change_semitones": None,
            "ending_pattern": "insufficient_data",
        }
    cutoff = float(valid[-1]["center_sec"]) - configuration.ending_window_ms / 1000
    ending = [frame for frame in valid if float(frame["center_sec"]) >= cutoff]
    if len(ending) < 2:
        return {
            "ending_pitch_change_semitones": None,
            "ending_pattern": "insufficient_data",
        }
    start = float(ending[0]["corrected_f0_hz"])
    end = float(ending[-1]["corrected_f0_hz"])
    change = 12.0 * math.log2(end / start)
    if change >= configuration.ending_pattern_threshold_semitones:
        pattern = "rising"
    elif change <= -configuration.ending_pattern_threshold_semitones:
        pattern = "falling"
    else:
        pattern = "level"
    return {
        "ending_pitch_change_semitones": round(change, 6),
        "ending_pattern": pattern,
    }


def _segment_prosody(
    stt: dict[str, Any],
    frames: list[dict[str, Any]],
    configuration: ProsodyValidationConfiguration,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(stt.get("segments", [])):
        if not isinstance(segment, dict):
            continue
        start = _finite(segment.get("start"))
        end = _finite(segment.get("end"))
        if start is None or end is None or end <= start:
            continue
        selected = [
            frame
            for frame in frames
            if start <= float(frame["center_sec"]) <= end
        ]
        summary = _pitch_summary(
            selected,
            "corrected_f0_hz",
            configuration,
            valid_only=True,
        )
        warnings: list[dict[str, Any]] = []
        if (
            summary["pitch_valid_frame_count"]
            < configuration.minimum_segment_pitch_frames
        ):
            warnings.append(
                {
                    "code": "SEGMENT_PITCH_INSUFFICIENT",
                    "detail": "Segment has too few validated pitch frames.",
                }
            )
        results.append(
            {
                "segment_id": segment.get("id", segment_index),
                "start_sec": round(start, 6),
                "end_sec": round(end, 6),
                "text": str(segment.get("text", "")),
                "duration_sec": round(end - start, 6),
                "corrected_pitch_median_hz": summary["pitch_median_hz"],
                "corrected_pitch_range_semitones": summary[
                    "pitch_range_semitones"
                ],
                "validated_pitch_frame_count": summary[
                    "pitch_valid_frame_count"
                ],
                "validated_pitch_coverage_ratio": summary[
                    "pitch_coverage_ratio"
                ],
                "ending_intonation": _ending_summary(selected, configuration),
                "warnings": warnings,
            }
        )
    return results


def _sanitize(value: Any) -> Any:
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(nested) for nested in value]
    return value


def _empty_result(
    audio_file: Path | str,
    stt_json_file: Path | str,
    quality_metrics_file: Path | str,
    configuration: ProsodyValidationConfiguration,
) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "description": (
            "Experimental heuristic validation of objective prosody metrics "
            "using numpy autocorrelation and YIN-like CMNDF estimators. "
            "Not human ground truth and not for scoring or interview assessment."
        ),
        "audio_file": str(audio_file),
        "stt_json_file": str(stt_json_file),
        "quality_metrics_file": str(quality_metrics_file),
        "audio_duration_sec": 0.0,
        "configuration": asdict(configuration),
        "raw_pitch_summary": {},
        "validated_pitch_summary": {},
        "correction_summary": {
            "corrected_frame_count": 0,
            "octave_halving_corrections": 0,
            "octave_doubling_corrections": 0,
            "octave_candidate_count": 0,
            "estimator_disagreement_count": 0,
            "unresolved_frame_count": 0,
            "estimator_agreement_ratio": 0.0,
            "raw_large_jump_count": 0,
            "corrected_large_jump_count": 0,
        },
        "loudness_summary": {},
        "segment_prosody": [],
        "prosody_reliability": {},
        "frames": [],
        "warnings": [],
        "error": None,
    }


def analyze_speech_prosody_v2(
    audio_file: Path | str,
    stt_json_file: Path | str,
    quality_metrics_file: Path | str,
    *,
    include_frames: bool = False,
    configuration: ProsodyValidationConfiguration | None = None,
) -> dict[str, Any]:
    """Analyze one WAV without modifying the WAV, STT, metrics, or v1 output."""
    config = configuration or ProsodyValidationConfiguration()
    result = _empty_result(
        audio_file, stt_json_file, quality_metrics_file, config
    )
    audio_path = Path(audio_file)
    stt_path = Path(stt_json_file)
    quality_path = Path(quality_metrics_file)
    if not audio_path.is_file():
        result["error"] = {
            "code": "AUDIO_FILE_NOT_FOUND",
            "detail": str(audio_path),
        }
        return result
    try:
        try:
            config.validate()
        except ValueError as exc:
            raise ProsodyAnalysisError("PROSODY_V2_ANALYSIS_FAILED", str(exc))
        stt = _load_json(stt_path, "STT_RESULT_NOT_FOUND", "STT_JSON_INVALID")
        intervals = _word_intervals(stt)
        metrics = _load_json(
            quality_path,
            "SPEECH_METRICS_NOT_FOUND",
            "SPEECH_METRICS_JSON_INVALID",
        )
        quality = metrics.get("audio_quality")
        if not isinstance(quality, dict):
            raise ProsodyAnalysisError(
                "AUDIO_QUALITY_NOT_FOUND",
                "Speech metrics JSON has no audio_quality object.",
            )
        try:
            audio = load_pcm16_mono_wav(audio_path)
        except ValueError as exc:
            raise ProsodyAnalysisError("UNSUPPORTED_WAV_FORMAT", str(exc))
        except (OSError, EOFError, wave.Error) as exc:
            raise ProsodyAnalysisError(
                "AUDIO_INVALID", f"{type(exc).__name__}: {exc}"
            )
        if audio.sample_rate != 16000:
            raise ProsodyAnalysisError(
                "UNSUPPORTED_WAV_FORMAT",
                f"Expected 16000 Hz, found {audio.sample_rate} Hz.",
            )

        result["audio_duration_sec"] = round(audio.duration_sec, 6)
        noise_floor = (
            _finite(quality.get("estimated_noise_floor_dbfs"))
            or config.fallback_noise_floor_dbfs
        )
        voiced_threshold = (
            _finite(quality.get("voiced_threshold_dbfs"))
            or config.fallback_voiced_threshold_dbfs
        )
        silence_threshold = (
            _finite(quality.get("silence_threshold_dbfs"))
            or config.fallback_silence_threshold_dbfs
        )
        quality_flags = {
            str(value) for value in quality.get("reliability_flags", [])
        }
        background = bool(quality.get("background_noise_suspected")) or (
            "background_noise_suspected" in quality_flags
        )
        quality_clipping_ratio = (
            _finite(quality.get("clipping_frame_ratio")) or 0.0
        )
        clipping_excessive = (
            quality_clipping_ratio > config.clipping_warning_ratio
            or "clipping_suspected" in quality_flags
        )
        result["configuration"].update(
            {
                "effective_noise_floor_dbfs": noise_floor,
                "effective_voiced_threshold_dbfs": voiced_threshold,
                "effective_silence_threshold_dbfs": silence_threshold,
                "energy_threshold_source": "speech_metrics.audio_quality",
            }
        )

        sample_rate = audio.sample_rate
        frame_samples = max(
            1, round(sample_rate * config.pitch_frame_ms / 1000.0)
        )
        hop_samples = max(1, round(sample_rate * config.hop_ms / 1000.0))
        normalized = np.asarray(audio.samples, dtype=np.float64) / 32768.0
        offsets = (
            [0]
            if normalized.size <= frame_samples
            else range(0, normalized.size - frame_samples + 1, hop_samples)
        )
        acf_config = ProsodyConfiguration(
            pitch_frame_ms=config.pitch_frame_ms,
            hop_ms=config.hop_ms,
            min_f0_hz=config.min_f0_hz,
            max_f0_hz=config.max_f0_hz,
            min_pitch_confidence=config.autocorrelation_min_confidence,
        )
        frames: list[dict[str, Any]] = []
        for frame_index, start_sample in enumerate(offsets):
            end_sample = min(normalized.size, start_sample + frame_samples)
            start_sec = start_sample / sample_rate
            end_sec = end_sample / sample_rate
            center_sec = (start_sec + end_sec) / 2.0
            samples = normalized[start_sample:end_sample]
            acoustic = analyze_interval(
                audio,
                start_sec,
                end_sec,
                voiced_threshold_dbfs=voiced_threshold,
                silence_threshold_dbfs=silence_threshold,
            )
            peak = float(np.max(np.abs(samples))) if samples.size else 0.0
            peak_dbfs = 20.0 * math.log10(peak) if peak > 0 else -100.0
            clipping = peak >= config.clipping_amplitude_ratio
            acf_f0, acf_confidence = estimate_frame_f0(
                samples, sample_rate, acf_config
            )
            yin_f0, yin_confidence = estimate_yin_f0(
                samples, sample_rate, config
            )
            selection = select_estimator_f0(
                acf_f0,
                acf_confidence,
                yin_f0,
                yin_confidence,
                config,
            )
            word_active = _in_word(
                center_sec, intervals, config.word_boundary_margin_sec
            )
            zcr = _zero_crossing_rate(samples)
            gate, gate_reasons, invalid_reasons = _voiced_gate(
                dbfs=float(acoustic["dbfs"]),
                noise_floor_dbfs=noise_floor,
                voiced_threshold_dbfs=voiced_threshold,
                autocorrelation_f0_hz=acf_f0,
                autocorrelation_confidence=acf_confidence,
                yin_f0_hz=yin_f0,
                yin_confidence=yin_confidence,
                estimator_agreement=bool(selection["estimator_agreement"]),
                zero_crossing_rate=zcr,
                word_active=word_active,
                clipping=clipping,
                background_noise_suspected=background,
                configuration=config,
            )
            if (
                selection["estimator_disagreement"]
                and not selection["octave_halving_candidate"]
            ):
                invalid_reasons.append("estimator_disagreement")
            frame = {
                "frame_index": frame_index,
                "start_sec": round(start_sec, 6),
                "end_sec": round(end_sec, 6),
                "center_sec": round(center_sec, 6),
                "rms": acoustic["rms"],
                "dbfs": acoustic["dbfs"],
                "peak_dbfs": round(peak_dbfs, 3),
                "zero_crossing_rate": round(zcr, 6),
                "periodicity_proxy": round(
                    max(acf_confidence, yin_confidence), 6
                ),
                "word_active": word_active,
                "clipping": clipping,
                "autocorrelation_f0_hz": _round(acf_f0, 3),
                "autocorrelation_confidence": round(acf_confidence, 6),
                "yin_f0_hz": _round(yin_f0, 3),
                "yin_confidence": round(yin_confidence, 6),
                **selection,
                "raw_selected_f0_hz": selection["selected_f0_hz"],
                "corrected_f0_hz": selection["selected_f0_hz"],
                "voiced_gate_passed": gate,
                "voiced_gate_reasons": gate_reasons,
                "valid": False,
                "invalid_reasons": list(dict.fromkeys(invalid_reasons)),
            }
            frames.append(frame)

        apply_octave_corrections(
            frames,
            config,
            background_noise_suspected=background,
            clipping_excessive=clipping_excessive,
        )
        raw_summary = _pitch_summary(
            frames,
            "raw_selected_f0_hz",
            config,
            valid_only=False,
        )
        validated_summary = _pitch_summary(
            frames,
            "corrected_f0_hz",
            config,
            valid_only=True,
        )
        loudness = _loudness_summary(frames)
        dual_count = sum(
            _finite(frame.get("autocorrelation_f0_hz")) is not None
            and _finite(frame.get("yin_f0_hz")) is not None
            for frame in frames
        )
        agreement_count = sum(
            bool(frame.get("estimator_agreement")) for frame in frames
        )
        agreement_ratio = agreement_count / dual_count if dual_count else 0.0
        unresolved = sum(
            bool(frame.get("unresolved_pitch_candidate"))
            and not bool(frame.get("correction_applied"))
            for frame in frames
        )
        corrections = sum(
            bool(frame.get("correction_applied")) for frame in frames
        )
        result["raw_pitch_summary"] = raw_summary
        result["validated_pitch_summary"] = validated_summary
        result["correction_summary"] = {
            "corrected_frame_count": corrections,
            "octave_halving_corrections": sum(
                frame.get("correction_type") == "octave_halving_correction"
                for frame in frames
            ),
            "octave_doubling_corrections": sum(
                frame.get("correction_type") == "octave_doubling_correction"
                for frame in frames
            ),
            "octave_candidate_count": sum(
                bool(frame.get("octave_halving_candidate")) for frame in frames
            ),
            "estimator_disagreement_count": sum(
                bool(frame.get("estimator_disagreement")) for frame in frames
            ),
            "unresolved_frame_count": unresolved,
            "estimator_agreement_ratio": round(agreement_ratio, 6),
            "raw_total_pitch_jump_semitones": raw_summary[
                "total_pitch_jump_semitones"
            ],
            "corrected_total_pitch_jump_semitones": validated_summary[
                "total_pitch_jump_semitones"
            ],
            "raw_large_jump_count": raw_summary["large_pitch_jump_count"],
            "corrected_large_jump_count": validated_summary[
                "large_pitch_jump_count"
            ],
        }
        result["loudness_summary"] = loudness
        result["segment_prosody"] = _segment_prosody(stt, frames, config)
        coverage = float(validated_summary["pitch_coverage_ratio"])
        reliability_flags = list(sorted(quality_flags))
        reliability_warnings: list[str] = []
        warning_entries = [
            {
                "code": "SOURCE_AUDIO_QUALITY_WARNING",
                "detail": str(detail),
            }
            for detail in quality.get("reliability_warnings", [])
        ]
        if background and "background_noise_suspected" not in reliability_flags:
            reliability_flags.append("background_noise_suspected")
        if clipping_excessive and "clipping_suspected" not in reliability_flags:
            reliability_flags.append("clipping_suspected")
        if coverage < config.low_pitch_coverage_threshold:
            reliability_flags.append("low_validated_pitch_coverage")
            detail = (
                "Validated pitch coverage is below the experimental 0.40 threshold."
            )
            reliability_warnings.append(detail)
            warning_entries.append(
                {"code": "LOW_VALIDATED_PITCH_COVERAGE", "detail": detail}
            )
        if agreement_ratio < config.low_agreement_ratio_threshold:
            reliability_flags.append("low_estimator_agreement")
            detail = (
                "Dual-estimator agreement is below the experimental 0.60 threshold."
            )
            reliability_warnings.append(detail)
            warning_entries.append(
                {"code": "LOW_ESTIMATOR_AGREEMENT", "detail": detail}
            )
        if unresolved:
            reliability_flags.append("unresolved_pitch_candidates")
            detail = "Some estimator disagreements remain unresolved."
            reliability_warnings.append(detail)
            warning_entries.append(
                {"code": "UNRESOLVED_PITCH_CANDIDATES", "detail": detail}
            )
        result["prosody_reliability"] = {
            "quality_metrics_available": True,
            "background_noise_suspected": background,
            "clipping_suspected": clipping_excessive,
            "pitch_coverage_ratio": coverage,
            "estimator_agreement_ratio": round(agreement_ratio, 6),
            "unresolved_frame_count": unresolved,
            "reliability_flags": list(dict.fromkeys(reliability_flags)),
            "reliability_warnings": reliability_warnings,
        }
        result["warnings"] = warning_entries
        result["frames"] = frames if include_frames else []
        if not include_frames:
            result["configuration"]["frames_omitted_from_output"] = True
    except ProsodyAnalysisError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
    except Exception as exc:
        result["error"] = {
            "code": "PROSODY_V2_ANALYSIS_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return _sanitize(result)


def evaluate_synthetic_estimates(
    estimates_hz: Iterable[float | None],
    truth_hz: Iterable[float | None],
    *,
    correction_flags: Iterable[bool] | None = None,
    expected_corrections: Iterable[bool] | None = None,
    octave_tolerance_semitones: float = 0.75,
) -> dict[str, Any]:
    """Calculate truth-based errors for synthetic signals only."""
    estimates = list(estimates_hz)
    truth = list(truth_hz)
    if len(estimates) != len(truth):
        raise ValueError("Estimate and truth tracks must have equal length.")
    errors_hz: list[float] = []
    errors_semitones: list[float] = []
    octave_errors = 0
    truth_count = 0
    valid_count = 0
    for estimate, expected in zip(estimates, truth):
        expected_value = _finite(expected)
        if expected_value is None:
            continue
        truth_count += 1
        estimate_value = _finite(estimate)
        if estimate_value is None:
            continue
        valid_count += 1
        errors_hz.append(abs(estimate_value - expected_value))
        difference = semitone_difference(estimate_value, expected_value) or 0.0
        errors_semitones.append(difference)
        if abs(difference - 12.0) <= octave_tolerance_semitones:
            octave_errors += 1
    report = {
        "scope": "synthetic_signals_only",
        "absolute_error_hz_mean": _round(_mean(errors_hz), 6),
        "absolute_error_semitones_mean": _round(
            _mean(errors_semitones), 6
        ),
        "valid_frame_ratio": (
            round(valid_count / truth_count, 6) if truth_count else 0.0
        ),
        "octave_error_rate": (
            round(octave_errors / valid_count, 6) if valid_count else 0.0
        ),
        "correction_precision": None,
        "correction_recall": None,
    }
    if correction_flags is not None and expected_corrections is not None:
        actual = list(correction_flags)
        expected = list(expected_corrections)
        if len(actual) != len(expected):
            raise ValueError("Correction flag tracks must have equal length.")
        true_positive = sum(a and e for a, e in zip(actual, expected))
        predicted = sum(bool(value) for value in actual)
        positives = sum(bool(value) for value in expected)
        report["correction_precision"] = (
            round(true_positive / predicted, 6) if predicted else 0.0
        )
        report["correction_recall"] = (
            round(true_positive / positives, 6) if positives else 0.0
        )
    return report


def run_synthetic_validation_suite(
    configuration: ProsodyValidationConfiguration | None = None,
    *,
    sample_rate: int = 16000,
) -> dict[str, Any]:
    """Run the twelve specified synthetic scenarios with known pitch tracks."""
    config = configuration or ProsodyValidationConfiguration()
    rng = np.random.default_rng(20260723)

    def sine(frequency: float, duration: float, amplitude: float) -> np.ndarray:
        times = np.arange(round(duration * sample_rate)) / sample_rate
        return amplitude * np.sin(2.0 * math.pi * frequency * times)

    def chirp(
        start_hz: float, end_hz: float, duration: float, amplitude: float
    ) -> tuple[np.ndarray, np.ndarray]:
        count = round(duration * sample_rate)
        frequencies = np.linspace(start_hz, end_hz, count)
        phase = 2.0 * math.pi * np.cumsum(frequencies) / sample_rate
        return amplitude * np.sin(phase), frequencies

    def analyze_signal(
        name: str,
        signal: np.ndarray,
        truth_by_sample: np.ndarray,
    ) -> dict[str, Any]:
        frame_samples = round(sample_rate * config.pitch_frame_ms / 1000)
        hop_samples = round(sample_rate * config.hop_ms / 1000)
        acf_config = ProsodyConfiguration(
            pitch_frame_ms=config.pitch_frame_ms,
            hop_ms=config.hop_ms,
            min_f0_hz=config.min_f0_hz,
            max_f0_hz=config.max_f0_hz,
            min_pitch_confidence=config.autocorrelation_min_confidence,
        )
        estimates: list[float | None] = []
        truths: list[float | None] = []
        disagreement_count = 0
        frame_count = 0
        false_voiced = 0
        unvoiced_truth = 0
        for start in range(0, signal.size - frame_samples + 1, hop_samples):
            frame = signal[start : start + frame_samples]
            acf, acf_conf = estimate_frame_f0(frame, sample_rate, acf_config)
            yin, yin_conf = estimate_yin_f0(frame, sample_rate, config)
            selected = select_estimator_f0(
                acf, acf_conf, yin, yin_conf, config
            )
            estimate = (
                _finite(selected["selected_f0_hz"])
                if selected["estimator_agreement"]
                else None
            )
            truth_frame = truth_by_sample[start : start + frame_samples]
            positive_truth = truth_frame[
                np.isfinite(truth_frame) & (truth_frame > 0)
            ]
            truth = (
                float(np.median(positive_truth))
                if positive_truth.size >= 0.5 * truth_frame.size
                else None
            )
            estimates.append(estimate)
            truths.append(truth)
            frame_count += 1
            disagreement_count += bool(selected["estimator_disagreement"])
            if truth is None:
                unvoiced_truth += 1
                false_voiced += estimate is not None
        metrics = evaluate_synthetic_estimates(estimates, truths)
        metrics.update(
            {
                "scenario": name,
                "frame_count": frame_count,
                "estimator_disagreement_count": disagreement_count,
                "false_voiced_rate_in_unvoiced_truth": (
                    round(false_voiced / unvoiced_truth, 6)
                    if unvoiced_truth
                    else None
                ),
            }
        )
        return metrics

    duration = 1.0
    sample_count = round(duration * sample_rate)
    scenarios: list[dict[str, Any]] = []

    signal = sine(100.0, duration, 0.2)
    scenarios.append(
        analyze_signal("pure_sine_100_hz", signal, np.full(sample_count, 100.0))
    )
    signal = sine(200.0, duration, 0.2)
    scenarios.append(
        analyze_signal("pure_sine_200_hz", signal, np.full(sample_count, 200.0))
    )
    signal = sine(100.0, duration, 0.10) + sine(200.0, duration, 0.25)
    scenarios.append(
        analyze_signal(
            "100_hz_with_strong_200_hz_harmonic",
            signal,
            np.full(sample_count, 100.0),
        )
    )
    signal = sine(200.0, duration, 0.20) + sine(100.0, duration, 0.08)
    scenarios.append(
        analyze_signal(
            "200_hz_with_100_hz_subharmonic",
            signal,
            np.full(sample_count, 200.0),
        )
    )
    rising, rising_truth = chirp(100.0, 200.0, duration, 0.2)
    scenarios.append(
        analyze_signal("gradual_rising_pitch", rising, rising_truth)
    )
    falling, falling_truth = chirp(200.0, 100.0, duration, 0.2)
    scenarios.append(
        analyze_signal("gradual_falling_pitch", falling, falling_truth)
    )
    voiced_silence = np.concatenate(
        (
            sine(120.0, 0.35, 0.2),
            np.zeros(round(0.30 * sample_rate)),
            sine(120.0, 0.35, 0.2),
        )
    )
    voiced_silence_truth = np.concatenate(
        (
            np.full(round(0.35 * sample_rate), 120.0),
            np.full(round(0.30 * sample_rate), np.nan),
            np.full(round(0.35 * sample_rate), 120.0),
        )
    )
    scenarios.append(
        analyze_signal(
            "voiced_regions_separated_by_long_silence",
            voiced_silence,
            voiced_silence_truth,
        )
    )
    signal = sine(150.0, duration, 0.2) + rng.normal(
        0.0, 0.04, sample_count
    )
    scenarios.append(
        analyze_signal(
            "voiced_with_white_noise", signal, np.full(sample_count, 150.0)
        )
    )
    signal = sine(150.0, duration, 0.2) + sine(60.0, duration, 0.08)
    scenarios.append(
        analyze_signal(
            "voiced_with_low_frequency_hum",
            signal,
            np.full(sample_count, 150.0),
        )
    )
    signal = np.clip(sine(120.0, duration, 2.0), -1.0, 32767 / 32768)
    scenarios.append(
        analyze_signal(
            "clipped_voiced_signal", signal, np.full(sample_count, 120.0)
        )
    )

    def injected_error_scenario(
        name: str,
        local_hz: float,
        raw_hz: float,
        alternate_hz: float,
    ) -> dict[str, Any]:
        frames: list[dict[str, Any]] = []
        for index in range(7):
            error = index == 3
            frames.append(
                {
                    "frame_index": index,
                    "center_sec": index * config.hop_ms / 1000,
                    "voiced_gate_passed": True,
                    "estimator_agreement": not error,
                    "autocorrelation_f0_hz": (
                        alternate_hz if error else local_hz
                    ),
                    "autocorrelation_confidence": 0.8,
                    "yin_f0_hz": raw_hz if error else local_hz,
                    "yin_confidence": 0.9,
                    "selected_f0_hz": raw_hz if error else local_hz,
                    "raw_selected_f0_hz": raw_hz if error else local_hz,
                    "unresolved_pitch_candidate": error,
                    "invalid_reasons": [],
                    "clipping": False,
                }
            )
        apply_octave_corrections(frames, config)
        report = evaluate_synthetic_estimates(
            [frame["corrected_f0_hz"] for frame in frames],
            [local_hz] * len(frames),
            correction_flags=[
                bool(frame["correction_applied"]) for frame in frames
            ],
            expected_corrections=[index == 3 for index in range(len(frames))],
        )
        report.update(
            {
                "scenario": name,
                "frame_count": len(frames),
                "estimator_disagreement_count": 1,
                "false_voiced_rate_in_unvoiced_truth": None,
            }
        )
        return report

    scenarios.append(
        injected_error_scenario(
            "sudden_octave_doubling_error", 100.0, 200.0, 100.0
        )
    )
    scenarios.append(
        injected_error_scenario(
            "sudden_octave_halving_error", 200.0, 100.0, 200.0
        )
    )
    return {
        "scope": "synthetic_signals_only",
        "description": (
            "Known generated pitch tracks permit truth-based error metrics; "
            "these metrics do not apply to the real recordings."
        ),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


__all__ = [
    "ProsodyValidationConfiguration",
    "analyze_speech_prosody_v2",
    "apply_octave_corrections",
    "classify_estimator_relation",
    "estimate_yin_f0",
    "evaluate_synthetic_estimates",
    "run_synthetic_validation_suite",
    "select_estimator_f0",
    "semitone_difference",
    "strict_json_text",
    "track_jump_metrics",
    "write_json_atomic",
]
