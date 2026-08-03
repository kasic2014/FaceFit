"""PCM amplitude, frame energy, and technical silence-candidate measurements."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.speech.speech_metrics import AudioData

from .speech_contracts import SpeechAnalysisProfile


def _dbfs(amplitude: float) -> float | None:
    return 20.0 * math.log10(amplitude) if amplitude > 0 else None


def _rounded(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _frame_measurements(
    normalized: np.ndarray, sample_rate: int, frame_ms: int, hop_ms: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frame_length = max(1, round(sample_rate * frame_ms / 1000))
    hop_length = max(1, round(sample_rate * hop_ms / 1000))
    starts = np.arange(0, normalized.size, hop_length, dtype=np.int64)
    ends = np.minimum(starts + frame_length, normalized.size)
    squared = normalized * normalized
    cumulative = np.concatenate((np.zeros(1), np.cumsum(squared, dtype=np.float64)))
    sums = cumulative[ends] - cumulative[starts]
    lengths = np.maximum(1, ends - starts)
    rms = np.sqrt(sums / lengths)
    dbfs = np.full(rms.shape, np.nan, dtype=np.float64)
    positive = rms > 0
    dbfs[positive] = 20.0 * np.log10(rms[positive])
    return starts, ends, dbfs


def _silence_regions(
    silent: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    sample_rate: int,
) -> list[dict[str, int]]:
    regions: list[dict[str, int]] = []
    index = 0
    while index < silent.size:
        if not bool(silent[index]):
            index += 1
            continue
        start_index = index
        while index < silent.size and bool(silent[index]):
            index += 1
        start_ms = math.floor(int(starts[start_index]) * 1000 / sample_rate)
        end_ms = math.floor(int(ends[index - 1]) * 1000 / sample_rate)
        if regions and start_ms <= regions[-1]["endMsRelative"]:
            regions[-1]["endMsRelative"] = max(regions[-1]["endMsRelative"], end_ms)
            regions[-1]["durationMs"] = (
                regions[-1]["endMsRelative"] - regions[-1]["startMsRelative"]
            )
        else:
            regions.append(
                {"startMsRelative": start_ms, "endMsRelative": end_ms,
                 "durationMs": end_ms - start_ms}
            )
    return regions


def analyze_volume_and_silence(
    audio: AudioData, profile: SpeechAnalysisProfile
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    samples = np.asarray(audio.samples, dtype=np.float64)
    if samples.size == 0:
        empty_volume = {
            key: None
            for key in (
                "peakAmplitude", "peakDbfs", "rmsAmplitude", "rmsDbfs",
                "meanFrameRmsDbfs", "medianFrameRmsDbfs", "p10FrameRmsDbfs",
                "p90FrameRmsDbfs", "frameRmsDbfsRange",
            )
        }
        empty_volume.update({"clippingSampleCount": 0, "clippingSampleRatio": None,
                             "zeroSampleRatio": None})
        return empty_volume, {
            "frameLengthMs": profile.frame_length_ms,
            "hopLengthMs": profile.hop_length_ms,
            "silenceThresholdDbfs": None,
            "candidateSilentFrameRatio": None,
            "candidateSilentDurationMs": None,
            "candidateSilenceRegionCount": 0,
            "candidateSilenceRegions": [],
            "thresholdPurpose": "TECHNICAL_VIEW_ONLY",
            "scoringApproved": False,
        }, ["AUDIO_EMPTY", "VOLUME_METRICS_UNAVAILABLE"]
    normalized = samples / 32768.0
    absolute = np.abs(normalized)
    peak = float(np.max(absolute))
    rms = float(np.sqrt(np.mean(normalized * normalized)))
    starts, ends, frame_dbfs = _frame_measurements(
        normalized, audio.sample_rate, profile.frame_length_ms, profile.hop_length_ms
    )
    finite_frames = frame_dbfs[np.isfinite(frame_dbfs)]
    if finite_frames.size:
        reference = float(np.percentile(finite_frames, profile.silence_reference_percentile))
        threshold = min(
            profile.silence_max_dbfs,
            max(profile.silence_min_dbfs, reference + profile.silence_offset_db),
        )
    else:
        threshold = profile.silence_max_dbfs
    silent = np.isnan(frame_dbfs) | (frame_dbfs <= threshold)
    regions = _silence_regions(silent, starts, ends, audio.sample_rate)
    duration_ms = round(samples.size * 1000 / audio.sample_rate)
    silent_duration_ms = sum(item["durationMs"] for item in regions)
    clipping_count = int(np.count_nonzero(absolute >= profile.clipping_amplitude))
    if rms == 0:
        warnings.extend(["AUDIO_NEAR_SILENT_CANDIDATE", "VOLUME_METRICS_UNAVAILABLE"])
    elif _dbfs(rms) is not None and _dbfs(rms) <= profile.near_silent_rms_dbfs:
        warnings.append("AUDIO_NEAR_SILENT_CANDIDATE")
    if clipping_count:
        warnings.append("CLIPPING_CANDIDATE")
    percentiles = (
        np.percentile(finite_frames, [10, 50, 90])
        if finite_frames.size
        else np.array([np.nan, np.nan, np.nan])
    )
    volume = {
        "peakAmplitude": _rounded(peak),
        "peakDbfs": _rounded(_dbfs(peak), 3),
        "rmsAmplitude": _rounded(rms),
        "rmsDbfs": _rounded(_dbfs(rms), 3),
        "meanFrameRmsDbfs": _rounded(
            float(np.mean(finite_frames)) if finite_frames.size else None, 3
        ),
        "medianFrameRmsDbfs": _rounded(
            float(percentiles[1]) if finite_frames.size else None, 3
        ),
        "p10FrameRmsDbfs": _rounded(
            float(percentiles[0]) if finite_frames.size else None, 3
        ),
        "p90FrameRmsDbfs": _rounded(
            float(percentiles[2]) if finite_frames.size else None, 3
        ),
        "frameRmsDbfsRange": _rounded(
            float(percentiles[2] - percentiles[0]) if finite_frames.size else None, 3
        ),
        "clippingSampleCount": clipping_count,
        "clippingSampleRatio": round(clipping_count / samples.size, 9),
        "zeroSampleRatio": round(float(np.count_nonzero(samples == 0)) / samples.size, 9),
    }
    silence = {
        "frameLengthMs": profile.frame_length_ms,
        "hopLengthMs": profile.hop_length_ms,
        "totalFrameCount": int(frame_dbfs.size),
        "silenceThresholdDbfs": round(threshold, 3),
        "thresholdMode": "P90_FRAME_RMS_DBFS_PLUS_OFFSET",
        "candidateSilentFrameRatio": round(float(np.mean(silent)), 6),
        "candidateSilentDurationMs": silent_duration_ms,
        "candidateSilentDurationRatio": (
            round(silent_duration_ms / duration_ms, 6) if duration_ms else None
        ),
        "candidateSilenceRegionCount": len(regions),
        "candidateSilenceRegions": regions,
        "thresholdPurpose": "TECHNICAL_VIEW_ONLY",
        "scoringApproved": False,
    }
    return volume, silence, list(dict.fromkeys(warnings))
