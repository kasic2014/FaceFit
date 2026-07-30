"""Prosody v2.1 aggregation and harmonic-support diagnostics.

This module preserves v2 behavior while making coverage and agreement
denominators explicit. Spectral harmonic support is diagnostic only and never
forces a pitch correction. Results are not human ground truth or an assessment.
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
from app.speech.prosody_validation import (
    ProsodyValidationConfiguration,
    analyze_speech_prosody_v2,
    estimate_yin_f0,
    select_estimator_f0,
)
from app.speech.speech_metrics import load_pcm16_mono_wav


@dataclass(frozen=True)
class ProsodyValidationV21Configuration:
    pitch_frame_ms: int = 40
    hop_ms: int = 10
    min_f0_hz: float = 60.0
    max_f0_hz: float = 400.0
    estimator_agreement_semitones: float = 0.75
    joint_valid_voiced_warning_ratio: float = 0.40
    validated_voiced_warning_ratio: float = 0.40
    very_low_coverage_ratio: float = 0.15
    minimum_agreement_frames: int = 20
    harmonic_count: int = 5
    spectral_bandwidth_hz: float = 15.0
    harmonic_ambiguity_margin: float = 0.10
    harmonic_ambiguity_ratio_warning: float = 0.20
    octave_support_dominance_margin: float = 0.05
    shared_octave_frame_ratio_warning: float = 0.10
    severe_clipping_frame_ratio: float = 0.05

    def validate(self) -> None:
        if self.pitch_frame_ms <= 0 or self.hop_ms <= 0:
            raise ValueError("Frame and hop durations must be positive.")
        if self.min_f0_hz <= 0 or self.max_f0_hz <= self.min_f0_hz:
            raise ValueError("F0 bounds are invalid.")
        if self.harmonic_count < 1:
            raise ValueError("harmonic_count must be positive.")
        if self.spectral_bandwidth_hz <= 0:
            raise ValueError("spectral_bandwidth_hz must be positive.")
        for name in (
            "joint_valid_voiced_warning_ratio",
            "validated_voiced_warning_ratio",
            "very_low_coverage_ratio",
            "harmonic_ambiguity_margin",
            "harmonic_ambiguity_ratio_warning",
            "shared_octave_frame_ratio_warning",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1].")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any, digits: int = 6) -> float | None:
    number = _finite(value)
    return None if number is None else round(number, digits)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _mean(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return float(np.mean(array)) if array.size else None


def dual_estimator_state(frame: dict[str, Any]) -> str:
    """Classify one frame into exactly one dual-estimator matrix cell."""
    acf_valid = _finite(frame.get("autocorrelation_f0_hz")) is not None
    yin_valid = _finite(frame.get("yin_f0_hz")) is not None
    if acf_valid and yin_valid:
        return (
            "both_valid_agree"
            if bool(frame.get("estimator_agreement"))
            else "both_valid_disagree"
        )
    if acf_valid:
        return "autocorrelation_only"
    if yin_valid:
        return "yin_only"
    return "both_invalid"


def summarize_dual_estimator_frames(
    frames: list[dict[str, Any]],
    voiced_threshold_dbfs: float,
) -> tuple[dict[str, Any], dict[str, int], dict[str, Any]]:
    """Return explicit coverage, status matrix, and agreement denominators."""
    statuses = {
        "both_valid_agree": 0,
        "both_valid_disagree": 0,
        "autocorrelation_only": 0,
        "yin_only": 0,
        "both_invalid": 0,
    }
    acoustic_voiced = 0
    acf_valid = 0
    yin_valid = 0
    validated = 0
    for frame in frames:
        state = dual_estimator_state(frame)
        frame["dual_estimator_state"] = state
        statuses[state] += 1
        dbfs = _finite(frame.get("dbfs"))
        acoustic_voiced += (
            dbfs is not None and dbfs >= voiced_threshold_dbfs
        )
        acf_valid += _finite(frame.get("autocorrelation_f0_hz")) is not None
        yin_valid += _finite(frame.get("yin_f0_hz")) is not None
        validated += bool(frame.get("valid")) and (
            _finite(frame.get("corrected_f0_hz")) is not None
        )

    total = len(frames)
    both_valid = statuses["both_valid_agree"] + statuses["both_valid_disagree"]
    counts = {
        "total_analysis_frame_count": total,
        "acoustic_voiced_frame_count": acoustic_voiced,
        "autocorrelation_valid_frame_count": acf_valid,
        "yin_valid_frame_count": yin_valid,
        "both_estimators_valid_frame_count": both_valid,
        "only_autocorrelation_valid_frame_count": statuses[
            "autocorrelation_only"
        ],
        "only_yin_valid_frame_count": statuses["yin_only"],
        "both_estimators_invalid_frame_count": statuses["both_invalid"],
        "validated_pitch_frame_count": validated,
    }
    coverage = {
        **counts,
        "acoustic_voiced_ratio": _ratio(acoustic_voiced, total),
        "autocorrelation_overall_coverage_ratio": _ratio(acf_valid, total),
        "yin_overall_coverage_ratio": _ratio(yin_valid, total),
        "dual_estimator_joint_valid_ratio": _ratio(both_valid, total),
        "dual_estimator_joint_valid_voiced_ratio": _ratio(
            both_valid, acoustic_voiced
        ),
        "validated_pitch_overall_coverage_ratio": _ratio(validated, total),
        "validated_pitch_voiced_coverage_ratio": _ratio(
            validated, acoustic_voiced
        ),
    }
    agreement_count = statuses["both_valid_agree"]
    disagreement_count = statuses["both_valid_disagree"]
    agreement = {
        "estimator_agreement_frame_count": agreement_count,
        "estimator_disagreement_frame_count": disagreement_count,
        "estimator_agreement_ratio": _ratio(agreement_count, both_valid),
        "estimator_agreement_ratio_conditioned_on_joint_valid": _ratio(
            agreement_count, both_valid
        ),
        "estimator_agreement_ratio_over_acoustic_voiced": _ratio(
            agreement_count, acoustic_voiced
        ),
        "estimator_agreement_ratio_over_total_frames": _ratio(
            agreement_count, total
        ),
    }
    return coverage, statuses, agreement


def _band_energy(
    frequencies: np.ndarray,
    power: np.ndarray,
    center_hz: float,
    bandwidth_hz: float,
) -> float:
    if center_hz <= 0 or center_hz > float(frequencies[-1]):
        return 0.0
    mask = np.abs(frequencies - center_hz) <= bandwidth_hz
    return float(np.sum(power[mask]))


def analyze_harmonic_support(
    samples: np.ndarray,
    sample_rate: int,
    candidate_f0_hz: float | None,
    configuration: ProsodyValidationV21Configuration | None = None,
) -> dict[str, Any]:
    """Measure spectral support around f and its harmonics as diagnostics."""
    config = configuration or ProsodyValidationV21Configuration()
    f0 = _finite(candidate_f0_hz)
    empty = {
        "fundamental_band_energy": None,
        "harmonic_band_energy": None,
        "harmonic_support_score": None,
        "half_frequency_support_score": None,
        "double_frequency_support_score": None,
        "harmonic_support_margin": None,
        "harmonic_support_ambiguous": False,
    }
    values = np.asarray(samples, dtype=np.float64)
    if f0 is None or f0 <= 0 or values.size < 4 or not np.any(values):
        return empty
    centered = values - float(np.mean(values))
    windowed = centered * np.hanning(values.size)
    spectrum = np.fft.rfft(windowed)
    power = np.abs(spectrum) ** 2
    frequencies = np.fft.rfftfreq(values.size, d=1.0 / sample_rate)
    total_power = float(np.sum(power))
    if total_power <= 1e-15:
        return empty

    def series_energy(base_hz: float) -> float:
        energy = 0.0
        for harmonic in range(1, config.harmonic_count + 1):
            center = harmonic * base_hz
            if center > sample_rate / 2:
                break
            energy += _band_energy(
                frequencies,
                power,
                center,
                config.spectral_bandwidth_hz,
            ) / harmonic
        return energy

    fundamental = _band_energy(
        frequencies, power, f0, config.spectral_bandwidth_hz
    )
    harmonics = sum(
        _band_energy(
            frequencies,
            power,
            harmonic * f0,
            config.spectral_bandwidth_hz,
        )
        for harmonic in range(2, config.harmonic_count + 1)
        if harmonic * f0 <= sample_rate / 2
    )
    current_raw = series_energy(f0)
    half_raw = series_energy(f0 / 2.0)
    double_raw = series_energy(f0 * 2.0)
    hypothesis_total = current_raw + half_raw + double_raw
    if hypothesis_total <= 1e-15:
        return empty
    current_score = current_raw / hypothesis_total
    half_score = half_raw / hypothesis_total
    double_score = double_raw / hypothesis_total
    margin = current_score - max(half_score, double_score)
    return {
        "fundamental_band_energy": round(fundamental / total_power, 9),
        "harmonic_band_energy": round(harmonics / total_power, 9),
        "harmonic_support_score": round(current_score, 6),
        "half_frequency_support_score": round(half_score, 6),
        "double_frequency_support_score": round(double_score, 6),
        "harmonic_support_margin": round(margin, 6),
        "harmonic_support_ambiguous": (
            margin < config.harmonic_ambiguity_margin
        ),
    }


def summarize_harmonic_support(
    frames: list[dict[str, Any]],
    configuration: ProsodyValidationV21Configuration | None = None,
) -> dict[str, Any]:
    config = configuration or ProsodyValidationV21Configuration()
    diagnosed = [
        frame
        for frame in frames
        if _finite(frame.get("harmonic_support_score")) is not None
    ]
    ambiguous = [
        frame for frame in diagnosed if frame["harmonic_support_ambiguous"]
    ]
    half_dominant = [
        frame
        for frame in diagnosed
        if (
            float(frame["half_frequency_support_score"])
            > float(frame["harmonic_support_score"])
            + config.octave_support_dominance_margin
        )
    ]
    double_dominant = [
        frame
        for frame in diagnosed
        if (
            float(frame["double_frequency_support_score"])
            > float(frame["harmonic_support_score"])
            + config.octave_support_dominance_margin
        )
    ]
    agreement_diagnosed = [
        frame
        for frame in diagnosed
        if frame.get("dual_estimator_state") == "both_valid_agree"
    ]
    agreement_ambiguous = [
        frame
        for frame in agreement_diagnosed
        if frame["harmonic_support_ambiguous"]
    ]
    agreement_alternative_dominant = [
        frame
        for frame in agreement_diagnosed
        if (
            float(frame["half_frequency_support_score"])
            > float(frame["harmonic_support_score"])
            + config.octave_support_dominance_margin
            or float(frame["double_frequency_support_score"])
            > float(frame["harmonic_support_score"])
            + config.octave_support_dominance_margin
        )
    ]
    return {
        "diagnosed_frame_count": len(diagnosed),
        "harmonic_ambiguous_frame_count": len(ambiguous),
        "harmonic_ambiguity_ratio": _ratio(len(ambiguous), len(diagnosed)),
        "half_frequency_dominant_frame_count": len(half_dominant),
        "double_frequency_dominant_frame_count": len(double_dominant),
        "octave_alternative_dominant_ratio": _ratio(
            len(half_dominant) + len(double_dominant), len(diagnosed)
        ),
        "agreement_diagnosed_frame_count": len(agreement_diagnosed),
        "agreement_harmonic_ambiguous_frame_count": len(
            agreement_ambiguous
        ),
        "agreement_harmonic_ambiguity_ratio": _ratio(
            len(agreement_ambiguous), len(agreement_diagnosed)
        ),
        "agreement_octave_alternative_dominant_ratio": _ratio(
            len(agreement_alternative_dominant), len(agreement_diagnosed)
        ),
        "mean_harmonic_support_score": _round(
            _mean(float(frame["harmonic_support_score"]) for frame in diagnosed)
        ),
        "mean_half_frequency_support_score": _round(
            _mean(
                float(frame["half_frequency_support_score"])
                for frame in diagnosed
            )
        ),
        "mean_double_frequency_support_score": _round(
            _mean(
                float(frame["double_frequency_support_score"])
                for frame in diagnosed
            )
        ),
        "mean_harmonic_support_margin": _round(
            _mean(float(frame["harmonic_support_margin"]) for frame in diagnosed)
        ),
    }


def build_shared_failure_diagnostics(
    coverage: dict[str, Any],
    agreement: dict[str, Any],
    harmonic: dict[str, Any],
    *,
    background_noise_suspected: bool,
    clipping_suspected: bool,
    configuration: ProsodyValidationV21Configuration | None = None,
) -> dict[str, Any]:
    config = configuration or ProsodyValidationV21Configuration()
    joint_voiced = _finite(
        coverage.get("dual_estimator_joint_valid_voiced_ratio")
    )
    validated_voiced = _finite(
        coverage.get("validated_pitch_voiced_coverage_ratio")
    )
    ambiguity = _finite(
        harmonic.get(
            "agreement_harmonic_ambiguity_ratio",
            harmonic.get("harmonic_ambiguity_ratio"),
        )
    )
    octave_alternative = _finite(
        harmonic.get(
            "agreement_octave_alternative_dominant_ratio",
            harmonic.get("octave_alternative_dominant_ratio"),
        )
    )
    low_joint = (
        joint_voiced is None
        or joint_voiced < config.joint_valid_voiced_warning_ratio
    )
    low_validated = (
        validated_voiced is None
        or validated_voiced < config.validated_voiced_warning_ratio
    )
    ambiguity_risk = (
        ambiguity is not None
        and ambiguity >= config.harmonic_ambiguity_ratio_warning
    )
    shared_octave = (
        agreement["estimator_agreement_frame_count"] > 0
        and ambiguity_risk
        and octave_alternative is not None
        and octave_alternative
        >= config.shared_octave_frame_ratio_warning
    )
    small_sample = (
        agreement["estimator_agreement_frame_count"]
        < config.minimum_agreement_frames
    )
    flags = []
    for enabled, name in (
        (shared_octave, "shared_octave_error_risk"),
        (ambiguity_risk, "harmonic_ambiguity_risk"),
        (low_joint, "low_joint_valid_coverage"),
        (low_validated, "low_validated_voiced_coverage"),
        (small_sample, "agreement_based_on_small_sample"),
        (background_noise_suspected, "background_noise_suspected"),
        (clipping_suspected, "clipping_suspected"),
    ):
        if enabled:
            flags.append(name)
    return {
        "shared_octave_error_risk": shared_octave,
        "harmonic_ambiguity_risk": ambiguity_risk,
        "low_joint_valid_coverage": low_joint,
        "low_validated_voiced_coverage": low_validated,
        "agreement_based_on_small_sample": small_sample,
        "background_noise_suspected": background_noise_suspected,
        "clipping_suspected": clipping_suspected,
        "risk_flags": flags,
        "interpretation": (
            "Risk flags are diagnostic warnings, not confirmed pitch errors."
        ),
    }


def classify_experimental_reliability(
    coverage: dict[str, Any],
    diagnostics: dict[str, Any],
    *,
    clipping_frame_ratio: float,
    configuration: ProsodyValidationV21Configuration | None = None,
) -> str:
    """Classify internal measurement usability without creating a score."""
    config = configuration or ProsodyValidationV21Configuration()
    joint = _finite(coverage.get("dual_estimator_joint_valid_voiced_ratio"))
    validated = _finite(
        coverage.get("validated_pitch_voiced_coverage_ratio")
    )
    severe_quality = bool(diagnostics["background_noise_suspected"]) or (
        clipping_frame_ratio >= config.severe_clipping_frame_ratio
    )
    very_low = (
        joint is None
        or validated is None
        or joint < config.very_low_coverage_ratio
        or validated < config.very_low_coverage_ratio
    )
    combined_shared_risk = (
        diagnostics["shared_octave_error_risk"]
        and diagnostics["harmonic_ambiguity_risk"]
    )
    if severe_quality or very_low or combined_shared_risk:
        return "unreliable"
    if diagnostics["risk_flags"]:
        return "limited"
    return "sufficient_for_experimental_summary"


def _load_quality(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProsodyAnalysisError("SPEECH_METRICS_NOT_FOUND", str(path))
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"Non-finite JSON constant: {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProsodyAnalysisError(
            "SPEECH_METRICS_JSON_INVALID",
            f"{type(exc).__name__}: {exc}",
        ) from exc
    quality = payload.get("audio_quality") if isinstance(payload, dict) else None
    if not isinstance(quality, dict):
        raise ProsodyAnalysisError(
            "AUDIO_QUALITY_NOT_FOUND",
            "Speech metrics JSON has no audio_quality object.",
        )
    return quality


def _empty_result(
    audio_file: Path | str,
    stt_json_file: Path | str,
    quality_metrics_file: Path | str,
    configuration: ProsodyValidationV21Configuration,
) -> dict[str, Any]:
    return {
        "schema_version": "2.1",
        "description": (
            "Experimental prosody aggregation with explicit denominators and "
            "diagnostic spectral support. Not human ground truth or an assessment."
        ),
        "audio_file": str(audio_file),
        "stt_json_file": str(stt_json_file),
        "quality_metrics_file": str(quality_metrics_file),
        "audio_duration_sec": 0.0,
        "configuration": asdict(configuration),
        "schema_notes": {
            "pitch_coverage_ratio": (
                "Retained from v2 for compatibility; its denominator is "
                "total_analysis_frame_count."
            ),
            "estimator_agreement_ratio": (
                "Retained from v2; its denominator is "
                "both_estimators_valid_frame_count."
            ),
            "agreement_limit": (
                "두 추정기의 일치는 두 알고리즘이 동일한 harmonic 또는 "
                "subharmonic 후보를 선택한 경우에도 발생할 수 있으므로 "
                "F0 정확도의 독립적인 증거가 아니다."
            ),
            "harmonic_support": (
                "Spectral support is diagnostic only and never forces pitch correction."
            ),
        },
        "coverage_summary": {},
        "agreement_summary": {},
        "dual_estimator_status": {},
        "harmonic_support_summary": {},
        "shared_failure_diagnostics": {},
        "analysis_reliability_level": None,
        "raw_pitch_summary": {},
        "validated_pitch_summary": {},
        "correction_summary": {},
        "loudness_summary": {},
        "segment_prosody": [],
        "prosody_reliability": {},
        "frames": [],
        "warnings": [],
        "error": None,
    }


def analyze_speech_prosody_v21(
    audio_file: Path | str,
    stt_json_file: Path | str,
    quality_metrics_file: Path | str,
    *,
    include_frames: bool = False,
    configuration: ProsodyValidationV21Configuration | None = None,
) -> dict[str, Any]:
    """Extend v2 in memory without writing or changing any v1/v2 input."""
    config = configuration or ProsodyValidationV21Configuration()
    result = _empty_result(
        audio_file, stt_json_file, quality_metrics_file, config
    )
    try:
        config.validate()
        v2 = analyze_speech_prosody_v2(
            audio_file,
            stt_json_file,
            quality_metrics_file,
            include_frames=True,
        )
        if v2.get("error"):
            result["error"] = v2["error"]
            return result
        frames = [dict(frame) for frame in v2["frames"]]
        quality = _load_quality(Path(quality_metrics_file))
        voiced_threshold = _finite(
            v2["configuration"].get("effective_voiced_threshold_dbfs")
        )
        if voiced_threshold is None:
            raise ProsodyAnalysisError(
                "PROSODY_V21_ANALYSIS_FAILED",
                "Effective voiced threshold is unavailable.",
            )
        coverage, statuses, agreement = summarize_dual_estimator_frames(
            frames, voiced_threshold
        )

        audio = load_pcm16_mono_wav(Path(audio_file))
        normalized = np.asarray(audio.samples, dtype=np.float64) / 32768.0
        for frame in frames:
            start = round(float(frame["start_sec"]) * audio.sample_rate)
            end = round(float(frame["end_sec"]) * audio.sample_rate)
            candidate = _finite(frame.get("corrected_f0_hz"))
            if candidate is None:
                candidate = _finite(frame.get("raw_selected_f0_hz"))
            support = analyze_harmonic_support(
                normalized[start:end],
                audio.sample_rate,
                candidate,
                config,
            )
            frame.update(support)
        harmonic = summarize_harmonic_support(frames, config)

        quality_flags = {
            str(value) for value in quality.get("reliability_flags", [])
        }
        background = bool(quality.get("background_noise_suspected")) or (
            "background_noise_suspected" in quality_flags
        )
        clipping_ratio = _finite(quality.get("clipping_frame_ratio")) or 0.0
        clipping = (
            clipping_ratio > 0.01 or "clipping_suspected" in quality_flags
        )
        diagnostics = build_shared_failure_diagnostics(
            coverage,
            agreement,
            harmonic,
            background_noise_suspected=background,
            clipping_suspected=clipping,
            configuration=config,
        )
        level = classify_experimental_reliability(
            coverage,
            diagnostics,
            clipping_frame_ratio=clipping_ratio,
            configuration=config,
        )

        result.update(
            {
                "audio_duration_sec": v2["audio_duration_sec"],
                "coverage_summary": coverage,
                "agreement_summary": agreement,
                "dual_estimator_status": statuses,
                "harmonic_support_summary": harmonic,
                "shared_failure_diagnostics": diagnostics,
                "analysis_reliability_level": level,
                "raw_pitch_summary": v2["raw_pitch_summary"],
                "validated_pitch_summary": v2["validated_pitch_summary"],
                "correction_summary": v2["correction_summary"],
                "loudness_summary": v2["loudness_summary"],
                "segment_prosody": v2["segment_prosody"],
                "prosody_reliability": v2["prosody_reliability"],
                "warnings": list(v2["warnings"]),
                "frames": frames if include_frames else [],
            }
        )
        result["validated_pitch_summary"]["pitch_coverage_ratio"] = coverage[
            "validated_pitch_overall_coverage_ratio"
        ]
        result["validated_pitch_summary"][
            "pitch_voiced_coverage_ratio"
        ] = coverage["validated_pitch_voiced_coverage_ratio"]
        result["correction_summary"]["estimator_agreement_ratio"] = agreement[
            "estimator_agreement_ratio"
        ]
        if not include_frames:
            result["configuration"]["frames_omitted_from_output"] = True
    except ProsodyAnalysisError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
    except (OSError, ValueError, wave.Error) as exc:
        result["error"] = {
            "code": "PROSODY_V21_ANALYSIS_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    except Exception as exc:
        result["error"] = {
            "code": "PROSODY_V21_ANALYSIS_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return _sanitize(result)


def evaluate_synthetic_signal_v21(
    name: str,
    description: str,
    samples: np.ndarray,
    sample_rate: int,
    *,
    expected_f0_hz: float | None,
    ground_truth_status: str = "defined",
    configuration: ProsodyValidationV21Configuration | None = None,
) -> dict[str, Any]:
    """Evaluate known synthetic periodicity; never use this for real audio."""
    config = configuration or ProsodyValidationV21Configuration()
    frame_samples = round(sample_rate * config.pitch_frame_ms / 1000)
    hop_samples = round(sample_rate * config.hop_ms / 1000)
    v2_config = ProsodyValidationConfiguration(
        pitch_frame_ms=config.pitch_frame_ms,
        hop_ms=config.hop_ms,
        min_f0_hz=config.min_f0_hz,
        max_f0_hz=config.max_f0_hz,
        estimator_agreement_semitones=config.estimator_agreement_semitones,
    )
    acf_config = ProsodyConfiguration(
        pitch_frame_ms=config.pitch_frame_ms,
        hop_ms=config.hop_ms,
        min_f0_hz=config.min_f0_hz,
        max_f0_hz=config.max_f0_hz,
    )
    estimates: list[float] = []
    joint_valid = 0
    agreement = 0
    total = 0
    octave_errors = 0
    supports: list[dict[str, Any]] = []
    for start in range(0, len(samples) - frame_samples + 1, hop_samples):
        frame = np.asarray(samples[start : start + frame_samples], dtype=np.float64)
        acf, acf_conf = estimate_frame_f0(frame, sample_rate, acf_config)
        yin, yin_conf = estimate_yin_f0(frame, sample_rate, v2_config)
        selected = select_estimator_f0(
            acf, acf_conf, yin, yin_conf, v2_config
        )
        total += 1
        both = acf is not None and yin is not None
        joint_valid += both
        agrees = both and bool(selected["estimator_agreement"])
        agreement += agrees
        detected = _finite(selected.get("selected_f0_hz"))
        if detected is not None:
            estimates.append(detected)
            supports.append(
                analyze_harmonic_support(
                    frame, sample_rate, detected, config
                )
            )
            if (
                ground_truth_status == "defined"
                and expected_f0_hz is not None
            ):
                difference = abs(
                    1200.0 * math.log2(detected / expected_f0_hz)
                )
                octave_errors += abs(difference - 1200.0) <= 75.0
    detected_median = (
        float(np.median(np.asarray(estimates))) if estimates else None
    )
    accuracy_allowed = (
        ground_truth_status == "defined"
        and expected_f0_hz is not None
        and detected_median is not None
    )
    error_hz = (
        abs(detected_median - expected_f0_hz)
        if accuracy_allowed
        else None
    )
    error_cents = (
        abs(1200.0 * math.log2(detected_median / expected_f0_hz))
        if accuracy_allowed
        else None
    )
    support_frames = [
        item for item in supports if item["harmonic_support_score"] is not None
    ]
    return {
        "scenario": name,
        "description": description,
        "scope": "synthetic_signal_only",
        "ground_truth_status": ground_truth_status,
        "expected_f0_hz": (
            expected_f0_hz if ground_truth_status == "defined" else None
        ),
        "detected_f0_hz": _round(detected_median, 3),
        "absolute_error_hz": _round(error_hz, 6),
        "absolute_error_cents": _round(error_cents, 6),
        "valid_frame_ratio": _ratio(len(estimates), total),
        "octave_error_rate": (
            _ratio(octave_errors, len(estimates))
            if ground_truth_status == "defined"
            else None
        ),
        "joint_estimator_valid_ratio": _ratio(joint_valid, total),
        "agreement_ratio_conditioned_on_joint_valid": _ratio(
            agreement, joint_valid
        ),
        "accuracy_metrics_calculated": accuracy_allowed,
        "harmonic_support_result": {
            "diagnosed_frame_count": len(support_frames),
            "mean_harmonic_support_score": _round(
                _mean(
                    float(item["harmonic_support_score"])
                    for item in support_frames
                )
            ),
            "mean_half_frequency_support_score": _round(
                _mean(
                    float(item["half_frequency_support_score"])
                    for item in support_frames
                )
            ),
            "mean_double_frequency_support_score": _round(
                _mean(
                    float(item["double_frequency_support_score"])
                    for item in support_frames
                )
            ),
            "harmonic_ambiguity_ratio": _ratio(
                sum(
                    bool(item["harmonic_support_ambiguous"])
                    for item in support_frames
                ),
                len(support_frames),
            ),
        },
    }


def run_synthetic_validation_v21_suite(
    configuration: ProsodyValidationV21Configuration | None = None,
    *,
    sample_rate: int = 16000,
) -> dict[str, Any]:
    """Run revised, explicitly justified synthetic ground-truth scenarios."""
    config = configuration or ProsodyValidationV21Configuration()
    duration = 1.0
    count = round(duration * sample_rate)
    time = np.arange(count) / sample_rate

    def tone(frequency: float, amplitude: float) -> np.ndarray:
        return amplitude * np.sin(2.0 * math.pi * frequency * time)

    rng = np.random.default_rng(20260723)
    low_noise = np.convolve(
        rng.normal(0.0, 1.0, count),
        np.ones(201) / 201,
        mode="same",
    )
    low_noise = 0.05 * low_noise / max(1e-12, float(np.std(low_noise)))
    definitions = [
        (
            "weak_100hz_fundamental_strong_harmonics",
            "A: 100 Hz is weak; strong 200/300/400 Hz harmonics share a 100 Hz period.",
            0.02 * np.sin(2 * np.pi * 100 * time)
            + tone(200, 0.18)
            + tone(300, 0.14)
            + tone(400, 0.10),
            100.0,
            "defined",
        ),
        (
            "missing_100hz_fundamental",
            "B: 200/300/400 Hz components have greatest common periodicity 100 Hz.",
            tone(200, 0.18) + tone(300, 0.14) + tone(400, 0.10),
            100.0,
            "defined",
        ),
        (
            "200hz_voiced_with_50hz_hum",
            "C50: a small 50 Hz electrical hum is interference; periodic source is 200 Hz.",
            tone(200, 0.20) + tone(50, 0.015),
            200.0,
            "defined",
        ),
        (
            "200hz_voiced_with_60hz_hum",
            "C60: a small 60 Hz electrical hum is interference; periodic source is 200 Hz.",
            tone(200, 0.20) + tone(60, 0.015),
            200.0,
            "defined",
        ),
        (
            "200hz_voiced_with_low_frequency_nonperiodic_noise",
            "D: low-frequency non-periodic noise is interference; periodic source is 200 Hz.",
            tone(200, 0.20) + low_noise,
            200.0,
            "defined",
        ),
        (
            "actual_100hz_plus_200hz_composite",
            "E: explicit 100/200 Hz components repeat at 100 Hz; this is not a 200 Hz octave-error truth case.",
            tone(100, 0.10) + tone(200, 0.20),
            100.0,
            "defined",
        ),
        (
            "ambiguous_independent_130hz_181hz_sources",
            "No single intended periodic source is defined; truth-based accuracy is prohibited.",
            tone(130, 0.12) + tone(181, 0.12),
            None,
            "ambiguous",
        ),
    ]
    scenarios = [
        evaluate_synthetic_signal_v21(
            name,
            description,
            samples,
            sample_rate,
            expected_f0_hz=expected,
            ground_truth_status=status,
            configuration=config,
        )
        for name, description, samples, expected, status in definitions
    ]
    return {
        "scope": "synthetic_signals_only",
        "scenario_count": len(scenarios),
        "ground_truth_note": (
            "Truth-based errors are calculated only for generated signals with "
            "an explicitly defined periodic source."
        ),
        "scenarios": scenarios,
    }


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


__all__ = [
    "ProsodyValidationV21Configuration",
    "analyze_harmonic_support",
    "analyze_speech_prosody_v21",
    "build_shared_failure_diagnostics",
    "classify_experimental_reliability",
    "dual_estimator_state",
    "evaluate_synthetic_signal_v21",
    "run_synthetic_validation_v21_suite",
    "strict_json_text",
    "summarize_dual_estimator_frames",
    "summarize_harmonic_support",
    "write_json_atomic",
]
