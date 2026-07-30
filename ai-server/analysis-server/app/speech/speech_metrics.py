"""Acoustic speech metrics derived from PCM WAV frames and STT word timestamps."""

from __future__ import annotations

import json
import math
import re
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FRAME_DURATION_MS = 20
LONG_SILENCE_MIN_SEC = 3.0
NOTICEABLE_PAUSE_MIN_SEC = 2.0
SILENT_PAUSE_MIN_SEC = 0.75
MIN_GAP_SEC = 0.25
MAX_BRIDGE_MS = 100
HALLUCINATION_END_WINDOW_SEC = 1.0
HALLUCINATION_MAX_WORD_DURATION_SEC = 0.15
HALLUCINATION_MAX_PROBABILITY = 0.70
LOW_VOICED_RATIO = 0.35
UNREALISTIC_SYLLABLES_PER_SEC = 15.0
LOW_CONFIDENCE_PROBABILITY = 0.70
BACKGROUND_NON_WORD_VOICED_RATIO = 0.40
BACKGROUND_PERSISTENCE_DB = 6.0
PROBABLE_LOCAL_CONTRAST_DB = 3.0
PROBABLE_ABOVE_NOISE_FLOOR_DB = 8.0
LOCAL_CONTEXT_SEC = 0.3
CLIPPING_AMPLITUDE_RATIO = 0.99
CLIPPING_FRAME_WARNING_RATIO = 0.01


@dataclass(frozen=True)
class AudioData:
    samples: array
    sample_rate: int
    channels: int
    sample_width: int

    @property
    def duration_sec(self) -> float:
        return len(self.samples) / self.sample_rate


def load_pcm16_mono_wav(path: Path) -> AudioData:
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        compression = stream.getcomptype()
        frames = stream.readframes(stream.getnframes())
    if channels != 1 or sample_width != 2 or compression != "NONE":
        raise ValueError("INPUT_AUDIO_INVALID: expected mono 16-bit PCM WAV")
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    return AudioData(samples, sample_rate, channels, sample_width)


def serialize_json(payload: Any) -> str:
    """Serialize a payload as strict, readable UTF-8-compatible JSON text."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )


def write_json_file(output_path: Path, payload: Any) -> None:
    """Write strict JSON as UTF-8 with LF newlines and a trailing newline."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Validate before opening so NaN or Infinity cannot leave a truncated file.
    serialize_json(payload)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        file.write("\n")


def _rms(samples: array) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def _dbfs(rms: float) -> float:
    return 20.0 * math.log10(rms / 32768.0) if rms > 0 else -100.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return -100.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def _frame_dbfs(samples: array, frame_samples: int) -> list[float]:
    return [
        _dbfs(_rms(samples[offset : offset + frame_samples]))
        for offset in range(0, len(samples), frame_samples)
    ]


def _audio_quality(
    audio: AudioData,
    words: list[dict[str, Any]],
    frame_samples: int,
    frame_values: list[float],
) -> dict[str, Any]:
    word_intervals = [
        (float(word["start"]), float(word["end"]))
        for word in words
    ]
    word_flags: list[bool] = []
    clipping_flags: list[bool] = []
    frame_durations: list[float] = []
    clipping_level = 32767 * CLIPPING_AMPLITUDE_RATIO
    for index, _ in enumerate(frame_values):
        offset = index * frame_samples
        frame = audio.samples[offset : offset + frame_samples]
        midpoint_sec = (offset + len(frame) / 2) / audio.sample_rate
        word_flags.append(any(start <= midpoint_sec <= end for start, end in word_intervals))
        clipping_flags.append(max((abs(sample) for sample in frame), default=0) >= clipping_level)
        frame_durations.append(len(frame) / audio.sample_rate)

    word_frame_dbfs = [value for value, is_word in zip(frame_values, word_flags) if is_word]
    non_word_frame_dbfs = [value for value, is_word in zip(frame_values, word_flags) if not is_word]
    speech_reference_dbfs = _percentile(word_frame_dbfs or frame_values, 0.75)
    estimated_noise_floor_dbfs = _percentile(non_word_frame_dbfs or frame_values, 0.20)
    non_word_median_dbfs = _percentile(non_word_frame_dbfs or frame_values, 0.50)
    voiced_threshold_dbfs = speech_reference_dbfs - 8.0
    silence_threshold_dbfs = speech_reference_dbfs - 10.0

    word_region_time = 0.0
    word_voiced_time = 0.0
    non_word_time = 0.0
    non_word_voiced_time = 0.0
    silence_time = 0.0
    ambiguous_time = 0.0
    for value, is_word, duration in zip(frame_values, word_flags, frame_durations):
        if is_word:
            word_region_time += duration
        else:
            non_word_time += duration
        if value < silence_threshold_dbfs:
            silence_time += duration
        elif value >= voiced_threshold_dbfs:
            if is_word:
                word_voiced_time += duration
            else:
                non_word_voiced_time += duration
        else:
            ambiguous_time += duration

    duration = audio.duration_sec
    non_word_voiced_ratio = (
        non_word_voiced_time / non_word_time if non_word_time > 0 else 0.0
    )
    word_region_voiced_ratio = (
        word_voiced_time / word_region_time if word_region_time > 0 else 0.0
    )
    word_coverage_ratio = word_region_time / duration if duration > 0 else 0.0
    snr_proxy_db = speech_reference_dbfs - estimated_noise_floor_dbfs
    dynamic_range_db = _percentile(frame_values, 0.95) - _percentile(frame_values, 0.05)
    clipping_frame_ratio = (
        sum(clipping_flags) / len(clipping_flags) if clipping_flags else 0.0
    )
    non_word_energy_persistence_db = non_word_median_dbfs - estimated_noise_floor_dbfs
    background_noise_suspected = (
        non_word_voiced_ratio >= BACKGROUND_NON_WORD_VOICED_RATIO
        and (
            non_word_energy_persistence_db >= BACKGROUND_PERSISTENCE_DB
            or snr_proxy_db <= 20.0
        )
    )

    flags: list[str] = []
    warnings: list[str] = []
    if background_noise_suspected:
        flags.append("background_noise_suspected")
        warnings.append(
            "Persistent energy in non-word regions can cause omitted-vocalization false positives."
        )
    if non_word_voiced_ratio >= BACKGROUND_NON_WORD_VOICED_RATIO:
        flags.append("high_non_word_voiced_ratio")
    if clipping_frame_ratio >= CLIPPING_FRAME_WARNING_RATIO:
        flags.append("clipping_suspected")
        warnings.append("More than 1% of frames contain near-clipping samples.")
    if non_word_time < 0.5:
        flags.append("insufficient_non_word_audio")
        warnings.append("Noise-floor estimation has less than 0.5 seconds of non-word audio.")

    return {
        "estimated_noise_floor_dbfs": round(estimated_noise_floor_dbfs, 3),
        "speech_reference_dbfs": round(speech_reference_dbfs, 3),
        "snr_proxy_db": round(snr_proxy_db, 3),
        "snr_proxy_definition": (
            "speech_reference_dbfs - estimated_noise_floor_dbfs; "
            "this is a proxy, not a calibrated SNR measurement"
        ),
        "dynamic_range_db": round(dynamic_range_db, 3),
        "clipping_frame_ratio": round(clipping_frame_ratio, 6),
        "word_region_time_sec": round(word_region_time, 6),
        "word_region_voiced_time_sec": round(word_voiced_time, 6),
        "word_region_voiced_ratio": round(word_region_voiced_ratio, 6),
        "non_word_time_sec": round(non_word_time, 6),
        "non_word_voiced_time_sec": round(non_word_voiced_time, 6),
        "non_word_voiced_ratio": round(non_word_voiced_ratio, 6),
        "non_word_median_dbfs": round(non_word_median_dbfs, 3),
        "non_word_energy_persistence_db": round(non_word_energy_persistence_db, 3),
        "word_coverage_ratio": round(word_coverage_ratio, 6),
        "silence_frame_time_sec": round(silence_time, 6),
        "ambiguous_frame_time_sec": round(ambiguous_time, 6),
        "voiced_threshold_dbfs": round(voiced_threshold_dbfs, 3),
        "silence_threshold_dbfs": round(silence_threshold_dbfs, 3),
        "background_noise_suspected": background_noise_suspected,
        "reliability_flags": flags,
        "reliability_warnings": warnings,
    }


def _bridge_short_active_runs(flags: list[bool], max_frames: int) -> list[bool]:
    """Bridge short non-silent bursts surrounded by low-energy frames."""
    bridged = flags[:]
    index = 0
    while index < len(flags):
        if flags[index]:
            index += 1
            continue
        start = index
        while index < len(flags) and not flags[index]:
            index += 1
        if start > 0 and index < len(flags) and index - start <= max_frames:
            bridged[start:index] = [True] * (index - start)
    return bridged


def _longest_true_run(flags: list[bool]) -> tuple[int, int]:
    best_start = best_end = current_start = 0
    in_run = False
    for index, value in enumerate(flags):
        if value and not in_run:
            current_start = index
            in_run = True
        if in_run and (not value or index == len(flags) - 1):
            current_end = index + 1 if value and index == len(flags) - 1 else index
            if current_end - current_start > best_end - best_start:
                best_start, best_end = current_start, current_end
            in_run = False
    return best_start, best_end


def analyze_interval(
    audio: AudioData,
    start_sec: float,
    end_sec: float,
    *,
    voiced_threshold_dbfs: float,
    silence_threshold_dbfs: float,
    frame_duration_ms: int = FRAME_DURATION_MS,
) -> dict[str, Any]:
    start_sec = max(0.0, min(start_sec, audio.duration_sec))
    end_sec = max(start_sec, min(end_sec, audio.duration_sec))
    start_sample = round(start_sec * audio.sample_rate)
    end_sample = round(end_sec * audio.sample_rate)
    samples = audio.samples[start_sample:end_sample]
    frame_samples = max(1, round(audio.sample_rate * frame_duration_ms / 1000))
    frame_values = _frame_dbfs(samples, frame_samples)
    voiced_flags = [value >= voiced_threshold_dbfs for value in frame_values]
    low_energy_flags = [value < silence_threshold_dbfs for value in frame_values]
    max_bridge_frames = max(1, round(MAX_BRIDGE_MS / frame_duration_ms))
    bridged = _bridge_short_active_runs(low_energy_flags, max_bridge_frames)
    run_start, run_end = _longest_true_run(bridged)
    low_energy_indices = [index for index, value in enumerate(low_energy_flags) if value]
    frame_sec = frame_samples / audio.sample_rate
    interval_rms = _rms(samples)
    frame_count = len(frame_values)
    voiced_ratio = sum(voiced_flags) / frame_count if frame_count else 0.0
    low_energy_ratio = sum(low_energy_flags) / frame_count if frame_count else 0.0
    if low_energy_indices and low_energy_ratio >= 0.85 and voiced_ratio <= 0.15:
        effective_start = low_energy_indices[0]
        effective_end = low_energy_indices[-1] + 1
        effective_basis = "high_low_energy_ratio_span"
    else:
        effective_start, effective_end = run_start, run_end
        effective_basis = "longest_bridged_low_energy_run"
    return {
        "start_sec": round(start_sec, 6),
        "end_sec": round(end_sec, 6),
        "duration_sec": round(end_sec - start_sec, 6),
        "rms": round(interval_rms, 3),
        "dbfs": round(_dbfs(interval_rms), 3),
        "voiced_frame_ratio": round(voiced_ratio, 6),
        "low_energy_frame_ratio": round(low_energy_ratio, 6),
        "frame_count": frame_count,
        "longest_low_energy_start_sec": round(start_sec + run_start * frame_sec, 6),
        "longest_low_energy_end_sec": round(
            min(end_sec, start_sec + run_end * frame_sec), 6
        ),
        "longest_low_energy_duration_sec": round((run_end - run_start) * frame_sec, 6),
        "effective_low_energy_start_sec": round(start_sec + effective_start * frame_sec, 6),
        "effective_low_energy_end_sec": round(
            min(end_sec, start_sec + effective_end * frame_sec), 6
        ),
        "effective_low_energy_duration_sec": round(
            (effective_end - effective_start) * frame_sec, 6
        ),
        "effective_low_energy_basis": effective_basis,
    }


def _flatten_words(stt: dict[str, Any]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(stt.get("segments", [])):
        for segment_word_index, word in enumerate(segment.get("words") or []):
            if word.get("start") is None or word.get("end") is None:
                continue
            flattened.append(
                {
                    **word,
                    "segment_id": segment.get("id", segment_index),
                    "segment_word_index": segment_word_index,
                    "word_index": len(flattened),
                }
            )
    return flattened


def _hangul_syllable_count(word: str) -> int:
    return len(re.findall(r"[가-힣]", word))


def _hallucination_candidates(
    words: list[dict[str, Any]],
    audio: AudioData,
    speech_reference_dbfs: float,
    voiced_threshold_dbfs: float,
    silence_threshold_dbfs: float,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for word in words:
        start = float(word["start"])
        end = float(word["end"])
        duration = max(0.0, end - start)
        probability = word.get("probability")
        acoustic = analyze_interval(
            audio,
            start,
            end,
            voiced_threshold_dbfs=voiced_threshold_dbfs,
            silence_threshold_dbfs=silence_threshold_dbfs,
        )
        low_acoustic_support = (
            acoustic["dbfs"] < speech_reference_dbfs - 4.0
            or acoustic["voiced_frame_ratio"] < LOW_VOICED_RATIO
        )
        conditions = {
            "near_audio_end": end >= audio.duration_sec - HALLUCINATION_END_WINDOW_SEC,
            "timestamp_duration_below_0_15_sec": duration < HALLUCINATION_MAX_WORD_DURATION_SEC,
            "low_acoustic_support": low_acoustic_support,
            "probability_below_0_70": (
                isinstance(probability, (int, float))
                and probability < HALLUCINATION_MAX_PROBABILITY
            ),
        }
        matched = [name for name, value in conditions.items() if value]
        syllables = _hangul_syllable_count(str(word.get("word", "")))
        syllables_per_sec = syllables / duration if duration > 0 else None
        auxiliary = {
            "hangul_syllable_count": syllables,
            "syllables_per_sec": round(syllables_per_sec, 3) if syllables_per_sec is not None else None,
            "unrealistic_syllable_rate": (
                syllables_per_sec is not None
                and syllables_per_sec > UNREALISTIC_SYLLABLES_PER_SEC
            ),
        }
        if len(matched) < 3 or not low_acoustic_support:
            continue
        candidates.append(
            {
                "word_index": word["word_index"],
                "segment_id": word["segment_id"],
                "segment_word_index": word["segment_word_index"],
                "word": str(word.get("word", "")).strip(),
                "start_sec": round(start, 6),
                "end_sec": round(end, 6),
                "duration_sec": round(duration, 6),
                "probability": probability,
                "matched_condition_count": len(matched),
                "matched_conditions": matched,
                "conditions": conditions,
                "acoustic": acoustic,
                "auxiliary_evidence": auxiliary,
            }
        )
    return candidates


def _dominant_voiced_run(
    audio: AudioData,
    start_sec: float,
    end_sec: float,
    voiced_threshold_dbfs: float,
) -> tuple[float, float] | None:
    start_sec = max(0.0, min(start_sec, audio.duration_sec))
    end_sec = max(start_sec, min(end_sec, audio.duration_sec))
    frame_samples = max(1, round(audio.sample_rate * FRAME_DURATION_MS / 1000))
    start_sample = round(start_sec * audio.sample_rate)
    end_sample = round(end_sec * audio.sample_rate)
    values = _frame_dbfs(audio.samples[start_sample:end_sample], frame_samples)
    voiced_flags = [value >= voiced_threshold_dbfs for value in values]
    bridged = _bridge_short_active_runs(voiced_flags, max_frames=2)
    run_start, run_end = _longest_true_run(bridged)
    if run_end <= run_start:
        return None
    frame_sec = frame_samples / audio.sample_rate
    return (
        round(start_sec + run_start * frame_sec, 6),
        round(min(end_sec, start_sec + run_end * frame_sec), 6),
    )


def _local_energy_contrast(
    audio: AudioData,
    candidate_start_sec: float,
    candidate_end_sec: float,
    *,
    noise_floor_dbfs: float,
    voiced_threshold_dbfs: float,
    silence_threshold_dbfs: float,
) -> dict[str, Any]:
    candidate = analyze_interval(
        audio,
        candidate_start_sec,
        candidate_end_sec,
        voiced_threshold_dbfs=voiced_threshold_dbfs,
        silence_threshold_dbfs=silence_threshold_dbfs,
    )
    before = analyze_interval(
        audio,
        max(0.0, candidate_start_sec - LOCAL_CONTEXT_SEC),
        candidate_start_sec,
        voiced_threshold_dbfs=voiced_threshold_dbfs,
        silence_threshold_dbfs=silence_threshold_dbfs,
    )
    after = analyze_interval(
        audio,
        candidate_end_sec,
        min(audio.duration_sec, candidate_end_sec + LOCAL_CONTEXT_SEC),
        voiced_threshold_dbfs=voiced_threshold_dbfs,
        silence_threshold_dbfs=silence_threshold_dbfs,
    )
    context_values = [
        interval["dbfs"]
        for interval in (before, after)
        if interval["duration_sec"] > 0
    ]
    surrounding_mean_dbfs = (
        sum(context_values) / len(context_values) if context_values else noise_floor_dbfs
    )
    candidate_dbfs = candidate["dbfs"]
    return {
        "candidate_start_sec": round(candidate_start_sec, 6),
        "candidate_end_sec": round(candidate_end_sec, 6),
        "candidate_duration_sec": round(candidate_end_sec - candidate_start_sec, 6),
        "candidate_mean_dbfs": round(candidate_dbfs, 3),
        "before_300ms_mean_dbfs": before["dbfs"],
        "after_300ms_mean_dbfs": after["dbfs"],
        "estimated_noise_floor_dbfs": round(noise_floor_dbfs, 3),
        "above_noise_floor_db": round(candidate_dbfs - noise_floor_dbfs, 3),
        "surrounding_mean_dbfs": round(surrounding_mean_dbfs, 3),
        "surrounding_energy_contrast_db": round(candidate_dbfs - surrounding_mean_dbfs, 3),
        "similar_energy_persists": (
            abs(candidate_dbfs - before["dbfs"]) < PROBABLE_LOCAL_CONTRAST_DB
            and abs(candidate_dbfs - after["dbfs"]) < PROBABLE_LOCAL_CONTRAST_DB
        ),
        "candidate_acoustic": candidate,
    }


def _pause_metrics(
    words: list[dict[str, Any]],
    excluded_indices: set[int],
    audio: AudioData,
    voiced_threshold_dbfs: float,
    silence_threshold_dbfs: float,
    audio_quality: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    effective_words = [word for word in words if word["word_index"] not in excluded_indices]
    pauses: list[dict[str, Any]] = []
    omitted_filler_candidates: list[dict[str, Any]] = []
    probable_omitted_vocalizations: list[dict[str, Any]] = []
    uncertain_gap_vocalizations: list[dict[str, Any]] = []
    for previous, following in zip(effective_words, effective_words[1:]):
        gap_start = float(previous["end"])
        gap_end = float(following["start"])
        gap_duration = gap_end - gap_start
        if gap_duration < MIN_GAP_SEC:
            continue
        acoustic = analyze_interval(
            audio,
            gap_start,
            gap_end,
            voiced_threshold_dbfs=voiced_threshold_dbfs,
            silence_threshold_dbfs=silence_threshold_dbfs,
        )
        silence_duration = acoustic["effective_low_energy_duration_sec"]
        silence_confirmed = (
            acoustic["low_energy_frame_ratio"] >= 0.55
            and acoustic["dbfs"] <= silence_threshold_dbfs + 1.0
            and silence_duration >= 0.5
        )
        if silence_confirmed and silence_duration >= LONG_SILENCE_MIN_SEC:
            classification = "long_silence"
        elif silence_confirmed and silence_duration >= NOTICEABLE_PAUSE_MIN_SEC:
            classification = "noticeable_pause"
        elif silence_confirmed and silence_duration >= SILENT_PAUSE_MIN_SEC:
            classification = "silent_pause"
        else:
            classification = "word_gap"

        pause = {
            "previous_word": str(previous.get("word", "")).strip(),
            "next_word": str(following.get("word", "")).strip(),
            "stt_gap_start_sec": round(gap_start, 6),
            "stt_gap_end_sec": round(gap_end, 6),
            "stt_gap_duration_sec": round(gap_duration, 6),
            "classification": classification,
            "acoustic_silence_confirmed": silence_confirmed,
            "acoustic_silence_start_sec": acoustic["effective_low_energy_start_sec"],
            "acoustic_silence_end_sec": acoustic["effective_low_energy_end_sec"],
            "acoustic_silence_duration_sec": silence_duration,
            "acoustic": acoustic,
        }
        pauses.append(pause)

        contains_omitted_voice = (
            0.25 <= gap_duration <= 2.0
            and not silence_confirmed
            and acoustic["voiced_frame_ratio"] >= 0.10
        )
        if contains_omitted_voice:
            voiced_run = _dominant_voiced_run(
                audio, gap_start, gap_end, voiced_threshold_dbfs
            )
            if voiced_run is None:
                continue
            local_contrast = _local_energy_contrast(
                audio,
                voiced_run[0],
                voiced_run[1],
                noise_floor_dbfs=audio_quality["estimated_noise_floor_dbfs"],
                voiced_threshold_dbfs=voiced_threshold_dbfs,
                silence_threshold_dbfs=silence_threshold_dbfs,
            )
            uncertain_reasons: list[str] = []
            if audio_quality["background_noise_suspected"]:
                uncertain_reasons.append("background_noise_suspected")
            if audio_quality["non_word_voiced_ratio"] >= BACKGROUND_NON_WORD_VOICED_RATIO:
                uncertain_reasons.append("high_non_word_voiced_ratio")
            if local_contrast["similar_energy_persists"]:
                uncertain_reasons.append("similar_energy_persists_around_candidate")
            if local_contrast["surrounding_energy_contrast_db"] < PROBABLE_LOCAL_CONTRAST_DB:
                uncertain_reasons.append("low_local_energy_contrast")
            if local_contrast["above_noise_floor_db"] < PROBABLE_ABOVE_NOISE_FLOOR_DB:
                uncertain_reasons.append("insufficient_energy_above_noise_floor")

            probable = not uncertain_reasons
            candidate = {
                **pause,
                "candidate_type": (
                    "probable_omitted_vocalization"
                    if probable
                    else "uncertain_gap_vocalization"
                ),
                "local_energy_contrast": local_contrast,
                "reasons": (
                    [
                        "localized_voiced_run",
                        "energy_above_noise_floor",
                        "energy_contrast_above_surroundings",
                    ]
                    if probable
                    else uncertain_reasons
                ),
            }
            omitted_filler_candidates.append(candidate)
            if probable:
                probable_omitted_vocalizations.append(candidate)
            else:
                uncertain_gap_vocalizations.append(candidate)
    return (
        pauses,
        omitted_filler_candidates,
        probable_omitted_vocalizations,
        uncertain_gap_vocalizations,
    )


def analyze_speech_metrics(audio_file: Path, stt_json_file: Path) -> dict[str, Any]:
    audio_file = Path(audio_file)
    stt_json_file = Path(stt_json_file)
    audio = load_pcm16_mono_wav(audio_file)
    stt = json.loads(stt_json_file.read_text(encoding="utf-8"))
    if stt.get("error") is not None:
        raise ValueError("INPUT_STT_INVALID: STT result contains an error")

    frame_samples = max(1, round(audio.sample_rate * FRAME_DURATION_MS / 1000))
    global_frame_dbfs = _frame_dbfs(audio.samples, frame_samples)
    global_rms = _rms(audio.samples)
    words = _flatten_words(stt)
    audio_quality = _audio_quality(audio, words, frame_samples, global_frame_dbfs)
    speech_reference_dbfs = audio_quality["speech_reference_dbfs"]
    voiced_threshold_dbfs = audio_quality["voiced_threshold_dbfs"]
    silence_threshold_dbfs = audio_quality["silence_threshold_dbfs"]
    hallucinations = _hallucination_candidates(
        words,
        audio,
        speech_reference_dbfs,
        voiced_threshold_dbfs,
        silence_threshold_dbfs,
    )
    excluded_indices = {candidate["word_index"] for candidate in hallucinations}
    effective_words = [word for word in words if word["word_index"] not in excluded_indices]
    (
        pauses,
        omitted_fillers,
        probable_omitted_vocalizations,
        uncertain_gap_vocalizations,
    ) = _pause_metrics(
        words,
        excluded_indices,
        audio,
        voiced_threshold_dbfs,
        silence_threshold_dbfs,
        audio_quality,
    )
    long_silences = [pause for pause in pauses if pause["classification"] == "long_silence"]
    excluded = [
        {
            "word_index": candidate["word_index"],
            "word": candidate["word"],
            "start_sec": candidate["start_sec"],
            "end_sec": candidate["end_sec"],
        }
        for candidate in hallucinations
    ]
    exclusion_reasons = [
        {
            "word_index": candidate["word_index"],
            "word": candidate["word"],
            "reasons": candidate["matched_conditions"],
        }
        for candidate in hallucinations
    ]
    voiced_time_sec = 0.0
    silence_time_sec = 0.0
    for index, frame_value in enumerate(global_frame_dbfs):
        offset = index * frame_samples
        current_frame_sec = min(frame_samples, len(audio.samples) - offset) / audio.sample_rate
        if frame_value >= voiced_threshold_dbfs:
            voiced_time_sec += current_frame_sec
        if frame_value < silence_threshold_dbfs:
            silence_time_sec += current_frame_sec
    probabilities = [
        float(word["probability"])
        for word in effective_words
        if isinstance(word.get("probability"), (int, float))
        and math.isfinite(float(word["probability"]))
    ]
    low_confidence_words = [
        {
            "word_index": word["word_index"],
            "segment_id": word["segment_id"],
            "word": str(word.get("word", "")).strip(),
            "start_sec": round(float(word["start"]), 6),
            "end_sec": round(float(word["end"]), 6),
            "probability": word["probability"],
        }
        for word in effective_words
        if isinstance(word.get("probability"), (int, float))
        and math.isfinite(float(word["probability"]))
        and float(word["probability"]) < LOW_CONFIDENCE_PROBABILITY
    ]
    noticeable_pauses = [
        pause for pause in pauses if pause["classification"] == "noticeable_pause"
    ]
    effective_word_count = len(effective_words)
    words_per_minute_total = (
        effective_word_count * 60.0 / audio.duration_sec if audio.duration_sec > 0 else 0.0
    )
    words_per_minute_voiced = (
        effective_word_count * 60.0 / voiced_time_sec if voiced_time_sec > 0 else 0.0
    )
    return {
        "schema_version": "1.0",
        "audio_file": str(audio_file),
        "stt_json_file": str(stt_json_file),
        "audio_duration_sec": round(audio.duration_sec, 6),
        "acoustic_configuration": {
            "sample_rate": audio.sample_rate,
            "channels": audio.channels,
            "sample_width_bytes": audio.sample_width,
            "frame_duration_ms": FRAME_DURATION_MS,
            "speech_reference_dbfs": round(speech_reference_dbfs, 3),
            "voiced_threshold_dbfs": round(voiced_threshold_dbfs, 3),
            "silence_threshold_dbfs": round(silence_threshold_dbfs, 3),
            "global_rms": round(global_rms, 3),
            "global_dbfs": round(_dbfs(global_rms), 3),
        },
        "audio_quality": audio_quality,
        "acoustic_voiced_time_sec": round(voiced_time_sec, 6),
        "silence_time_sec": round(silence_time_sec, 6),
        "speech_ratio": round(voiced_time_sec / audio.duration_sec, 6) if audio.duration_sec > 0 else 0.0,
        "raw_word_count": len(words),
        "effective_word_count": effective_word_count,
        "excluded_word_count": len(excluded_indices),
        "words_per_minute_total": round(words_per_minute_total, 6),
        "words_per_minute_voiced": round(words_per_minute_voiced, 6),
        "eojeol_per_minute_total": round(words_per_minute_total, 6),
        "eojeol_per_minute_voiced": round(words_per_minute_voiced, 6),
        "average_word_probability": round(sum(probabilities) / len(probabilities), 6) if probabilities else None,
        "low_confidence_words": low_confidence_words,
        "excluded_from_metrics": excluded,
        "exclusion_reasons": exclusion_reasons,
        "hallucination_candidates": hallucinations,
        "pauses": pauses,
        "pause_count": len(pauses),
        "noticeable_pause_count": len(noticeable_pauses),
        "long_silences": long_silences,
        "long_silence_count": len(long_silences),
        "longest_silence_sec": round(
            max(
                (pause["acoustic_silence_duration_sec"] for pause in long_silences),
                default=0.0,
            ),
            6,
        ),
        "omitted_filler_candidates": omitted_fillers,
        "omitted_filler_candidate_count": len(omitted_fillers),
        "probable_omitted_vocalizations": probable_omitted_vocalizations,
        "probable_omitted_vocalization_count": len(probable_omitted_vocalizations),
        "uncertain_gap_vocalizations": uncertain_gap_vocalizations,
        "uncertain_gap_vocalization_count": len(uncertain_gap_vocalizations),
        "warnings": list(audio_quality["reliability_warnings"]),
        "error": None,
    }
