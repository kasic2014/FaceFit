"""Sample-exact WAV inspection and [start, end) interval extraction."""

from __future__ import annotations

from array import array
import hashlib
import math
from pathlib import Path
import wave
from typing import Any, Iterable

from .audio_contracts import (
    AudioContractError,
    AudioInterval,
    CHANNELS,
    DURATION_TOLERANCE_MS,
    SAMPLE_RATE_HZ,
    SAMPLE_WIDTH_BITS,
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_pcm_wav(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    result: dict[str, Any] = {
        "fileSizeBytes": source.stat().st_size if source.is_file() else 0,
        "sha256": sha256_file(source) if source.is_file() else None,
        "container": "WAV",
        "codec": "PCM_S16LE",
        "sampleRateHz": None,
        "channels": None,
        "sampleWidthBits": None,
        "sampleCount": 0,
        "durationMs": 0,
        "decodedDurationMs": 0,
        "readable": False,
        "decodable": False,
        "peakAmplitude": 0.0,
        "rmsAmplitude": 0.0,
        "zeroSampleRatio": 1.0,
        "silentFrameRatio": 1.0,
        "clippingSampleRatio": 0.0,
        "warnings": [],
        "errors": [],
    }
    if not source.is_file():
        result["errors"].append("AUDIO_DECODE_FAILED")
        return result
    result["readable"] = True
    sum_squares = 0
    zero_count = 0
    clip_count = 0
    peak = 0
    total = 0
    silent_frames = 0
    frame_windows = 0
    try:
        with wave.open(str(source), "rb") as stream:
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            rate = stream.getframerate()
            frames = stream.getnframes()
            result.update(
                sampleRateHz=rate,
                channels=channels,
                sampleWidthBits=sample_width * 8,
                sampleCount=frames,
                durationMs=frames * 1000 // rate if rate else 0,
                decodedDurationMs=frames * 1000 // rate if rate else 0,
            )
            if stream.getcomptype() != "NONE" or sample_width != 2:
                result["errors"].append("AUDIO_DECODE_FAILED")
                return result
            window_samples = max(1, rate // 100)
            while True:
                raw = stream.readframes(window_samples)
                if not raw:
                    break
                samples = array("h")
                samples.frombytes(raw)
                if not samples:
                    continue
                total += len(samples)
                local_square = 0
                for sample in samples:
                    magnitude = abs(sample)
                    peak = max(peak, magnitude)
                    sum_squares += sample * sample
                    local_square += sample * sample
                    zero_count += sample == 0
                    clip_count += magnitude >= 32767
                local_rms = math.sqrt(local_square / len(samples)) / 32768.0
                silent_frames += local_rms < 0.001
                frame_windows += 1
    except (OSError, EOFError, wave.Error):
        result["errors"].append("AUDIO_DECODE_FAILED")
        return result
    result["decodable"] = True
    if result["sampleRateHz"] != SAMPLE_RATE_HZ:
        result["errors"].append("UNEXPECTED_SAMPLE_RATE")
    if result["channels"] != CHANNELS:
        result["errors"].append("UNEXPECTED_CHANNEL_COUNT")
    if result["sampleWidthBits"] != SAMPLE_WIDTH_BITS:
        result["errors"].append("AUDIO_DECODE_FAILED")
    if result["sampleCount"] <= 0:
        result["errors"].append("EMPTY_AUDIO")
    if total:
        result["peakAmplitude"] = peak / 32768.0
        result["rmsAmplitude"] = math.sqrt(sum_squares / total) / 32768.0
        result["zeroSampleRatio"] = zero_count / total
        result["clippingSampleRatio"] = clip_count / total
    if frame_windows:
        result["silentFrameRatio"] = silent_frames / frame_windows
    if total and result["rmsAmplitude"] < 0.001:
        result["warnings"].append("NEAR_SILENT_AUDIO")
    if result["clippingSampleRatio"] > 0:
        result["warnings"].append("CLIPPING_DETECTED")
    return result


def validate_source_contract(source: str | Path) -> dict[str, Any]:
    result = inspect_pcm_wav(source)
    if result["errors"]:
        raise AudioContractError(result["errors"][0], "Source WAV violates the STT audio contract")
    return result


def extract_intervals(
    source_wav: str | Path,
    destination_dir: str | Path,
    intervals: Iterable[AudioInterval],
) -> list[dict[str, Any]]:
    source = Path(source_wav)
    destination = Path(destination_dir)
    destination.mkdir(parents=True, exist_ok=True)
    definitions = list(intervals)
    if not definitions:
        raise AudioContractError("EMPTY_AUDIO", "At least one interval is required")
    with wave.open(str(source), "rb") as stream:
        if (
            stream.getframerate() != SAMPLE_RATE_HZ
            or stream.getnchannels() != CHANNELS
            or stream.getsampwidth() * 8 != SAMPLE_WIDTH_BITS
            or stream.getcomptype() != "NONE"
        ):
            raise AudioContractError("AUDIO_DECODE_FAILED", "Source WAV violates the STT contract")
        source_samples = stream.getnframes()
        for interval in definitions:
            if interval.end_sample > source_samples:
                raise AudioContractError(
                    "INTERVAL_OUT_OF_RANGE",
                    f"{interval.output_id} ends after decoded audio",
                )
        results: list[dict[str, Any]] = []
        for interval in definitions:
            stream.setpos(interval.start_sample)
            frames = stream.readframes(interval.expected_sample_count)
            output = destination / f"{interval.output_id}.wav"
            with wave.open(str(output), "wb") as target:
                target.setnchannels(CHANNELS)
                target.setsampwidth(SAMPLE_WIDTH_BITS // 8)
                target.setframerate(SAMPLE_RATE_HZ)
                target.writeframes(frames)
            inspection = inspect_pcm_wav(output)
            actual_samples = inspection["sampleCount"]
            actual_duration = actual_samples * 1000 // SAMPLE_RATE_HZ
            errors = list(inspection["errors"])
            if actual_samples != interval.expected_sample_count:
                errors.append("DURATION_MISMATCH")
            if abs(actual_duration - interval.expected_duration_ms) > DURATION_TOLERANCE_MS:
                errors.append("DURATION_MISMATCH")
            if errors:
                raise AudioContractError(errors[0], f"Invalid interval output: {interval.output_id}")
            item = interval.contract_dict()
            item.update(
                actualDurationMs=actual_duration,
                sampleCount=actual_samples,
                status="COMPLETE_WITH_WARNINGS" if inspection["warnings"] else "COMPLETE",
                warnings=list(inspection["warnings"]),
                audio=inspection,
            )
            results.append(item)
    return results
