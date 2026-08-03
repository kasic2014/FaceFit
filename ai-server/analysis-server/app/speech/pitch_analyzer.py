"""Injectable numpy FFT-autocorrelation F0 adapter and objective summaries."""

from __future__ import annotations

import math
import statistics
from typing import Any, Protocol

import numpy as np

from app.speech.speech_metrics import AudioData

from .speech_contracts import SpeechAnalysisProfile


class PitchAdapter(Protocol):
    def estimate(
        self, audio: AudioData, profile: SpeechAnalysisProfile, silence_threshold_dbfs: float | None
    ) -> tuple[list[float | None], int]: ...


class NumpyAutocorrelationPitchAdapter:
    """Batch FFT autocorrelation with energy gating; unvoiced frames are None."""

    def estimate(
        self, audio: AudioData, profile: SpeechAnalysisProfile, silence_threshold_dbfs: float | None
    ) -> tuple[list[float | None], int]:
        samples = np.asarray(audio.samples, dtype=np.float64) / 32768.0
        frame_length = max(1, round(audio.sample_rate * profile.pitch_frame_length_ms / 1000))
        hop_length = max(1, round(audio.sample_rate * profile.pitch_hop_length_ms / 1000))
        if samples.size < frame_length:
            return [], 0
        total = 1 + (samples.size - frame_length) // hop_length
        minimum_lag = max(1, math.ceil(audio.sample_rate / profile.pitch_fmax_hz))
        maximum_lag = min(frame_length - 2, math.floor(audio.sample_rate / profile.pitch_fmin_hz))
        window = np.hanning(frame_length)
        output: list[float | None] = []
        for batch_start in range(0, total, 512):
            indices = np.arange(batch_start, min(total, batch_start + 512)) * hop_length
            frames = np.stack([samples[index : index + frame_length] for index in indices])
            rms = np.sqrt(np.mean(frames * frames, axis=1))
            dbfs = np.full(rms.shape, -math.inf)
            positive = rms > 0
            dbfs[positive] = 20.0 * np.log10(rms[positive])
            centered = frames - np.mean(frames, axis=1, keepdims=True)
            windowed = centered * window
            fft_length = 1 << (2 * frame_length - 1).bit_length()
            spectrum = np.fft.rfft(windowed, n=fft_length, axis=1)
            correlation = np.fft.irfft(spectrum * np.conjugate(spectrum), n=fft_length, axis=1)
            zero = correlation[:, :1]
            correlation = np.divide(
                correlation, zero, out=np.zeros_like(correlation), where=zero > 1e-12
            )
            region = correlation[:, minimum_lag : maximum_lag + 1]
            local = np.zeros(region.shape, dtype=bool)
            if region.shape[1] >= 3:
                local[:, 1:-1] = (
                    (region[:, 1:-1] >= region[:, :-2])
                    & (region[:, 1:-1] > region[:, 2:])
                )
            eligible = local & (region >= profile.pitch_min_correlation)
            for row_index in range(region.shape[0]):
                energy_ok = (
                    silence_threshold_dbfs is None
                    or float(dbfs[row_index]) > silence_threshold_dbfs
                )
                candidates = np.flatnonzero(eligible[row_index])
                if not energy_ok or candidates.size == 0:
                    output.append(None)
                    continue
                candidate = int(candidates[np.argmax(region[row_index, candidates])])
                lag = float(minimum_lag + candidate)
                if 0 < candidate < region.shape[1] - 1:
                    left, center, right = (
                        float(region[row_index, candidate - 1]),
                        float(region[row_index, candidate]),
                        float(region[row_index, candidate + 1]),
                    )
                    denominator = left - 2 * center + right
                    if abs(denominator) > 1e-12:
                        offset = 0.5 * (left - right) / denominator
                        if abs(offset) <= 1:
                            lag += offset
                f0 = audio.sample_rate / lag
                output.append(
                    float(f0)
                    if profile.pitch_fmin_hz <= f0 <= profile.pitch_fmax_hz
                    else None
                )
        return output, total


def _percentile(values: list[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentile))


def analyze_pitch(
    audio: AudioData,
    profile: SpeechAnalysisProfile,
    silence_threshold_dbfs: float | None,
    *,
    adapter: PitchAdapter | None = None,
) -> tuple[dict[str, Any], list[str]]:
    estimator = adapter or NumpyAutocorrelationPitchAdapter()
    values, total = estimator.estimate(audio, profile, silence_threshold_dbfs)
    voiced = [float(value) for value in values if value is not None and math.isfinite(value)]
    warnings: list[str] = []
    if not voiced:
        warnings.append("PITCH_UNAVAILABLE")
    if len(voiced) < profile.pitch_min_voiced_frames:
        warnings.append("INSUFFICIENT_VOICED_FRAMES")
    boundary_count = sum(
        value <= profile.pitch_fmin_hz + profile.pitch_boundary_margin_hz
        or value >= profile.pitch_fmax_hz - profile.pitch_boundary_margin_hz
        for value in voiced
    )
    if voiced and boundary_count / len(voiced) >= profile.pitch_boundary_candidate_ratio:
        warnings.append("PITCH_RANGE_CLIPPED_CANDIDATE")
    if voiced:
        mean = statistics.fmean(voiced)
        median = statistics.median(voiced)
        std = statistics.pstdev(voiced)
        p10 = _percentile(voiced, 10)
        p90 = _percentile(voiced, 90)
        mad = statistics.median(abs(value - median) for value in voiced)
    else:
        mean = median = std = p10 = p90 = mad = None
    result = {
        "method": "NUMPY_FFT_AUTOCORRELATION",
        "frameLengthMs": profile.pitch_frame_length_ms,
        "hopLengthMs": profile.pitch_hop_length_ms,
        "fminHz": profile.pitch_fmin_hz,
        "fmaxHz": profile.pitch_fmax_hz,
        "voicedFrameCount": len(voiced),
        "totalFrameCount": total,
        "voicedFrameRatio": round(len(voiced) / total, 6) if total else 0.0,
        "meanF0Hz": round(mean, 3) if mean is not None else None,
        "medianF0Hz": round(median, 3) if median is not None else None,
        "standardDeviationF0Hz": round(std, 3) if std is not None else None,
        "p10F0Hz": round(p10, 3) if p10 is not None else None,
        "p90F0Hz": round(p90, 3) if p90 is not None else None,
        "minimumF0Hz": round(min(voiced), 3) if voiced else None,
        "maximumF0Hz": round(max(voiced), 3) if voiced else None,
        "f0RangeHz": round(max(voiced) - min(voiced), 3) if voiced else None,
        "p10P90RangeHz": round(p90 - p10, 3) if p10 is not None and p90 is not None else None,
        "medianAbsoluteDeviationF0Hz": round(mad, 3) if mad is not None else None,
        "coefficientOfVariation": round(std / mean, 6) if mean not in (None, 0) else None,
        "unvoicedFrameRepresentation": "EXCLUDED_NOT_ZERO",
        "interpretation": "PHYSICAL_F0_MEASUREMENT_ONLY",
    }
    return result, warnings
