"""Batch existing speech metrics over SESSION001 standard WAV/STT pairs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Callable

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from app.speech.speech_metrics import analyze_speech_metrics  # noqa: E402


MANIFEST_FIELDS = (
    "sample_id",
    "speaker_code",
    "session_id",
    "script_id",
    "recording_condition",
    "repetition_index",
    "device_code",
    "capture_pair_key",
    "audio_file",
    "audio_sha256",
    "stt_json_file",
    "output_json",
    "speech_duration_sec",
    "speaking_ratio",
    "speech_rate_wpm",
    "speech_rate_eojeol_per_min",
    "pause_count",
    "long_pause_count",
    "probable_omitted_vocalization_count",
    "uncertain_gap_vocalization_count",
    "hallucination_candidate_count",
    "background_noise_warning",
    "clipping_warning",
    "error_code",
)
ERROR_CODES = {
    "STANDARD_WAV_NOT_FOUND",
    "STT_JSON_NOT_FOUND",
    "STT_JSON_INVALID",
    "WORD_TIMESTAMP_MISSING",
    "SPEECH_METRICS_ANALYSIS_FAILED",
    "DEVICE_PAIR_INCOMPLETE",
    "HUMAN_ANNOTATION_INVALID",
    "SPEECH_METRICS_WRITE_FAILED",
    "SESSION_SPEECH_METRICS_FAILED",
}


class SessionMetricsError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def strict_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(path: Path | str, root: Path | str) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def _load_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file():
        raise SessionMetricsError(code, str(path))
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionMetricsError(
            "STT_JSON_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(result, dict):
        raise SessionMetricsError("STT_JSON_INVALID", str(path))
    return result


def _pause_events(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    probable_keys = {
        (
            item["stt_gap_start_sec"],
            item["stt_gap_end_sec"],
        )
        for item in metrics["probable_omitted_vocalizations"]
    }
    uncertain_keys = {
        (
            item["stt_gap_start_sec"],
            item["stt_gap_end_sec"],
        )
        for item in metrics["uncertain_gap_vocalizations"]
    }
    events = []
    for pause in metrics["pauses"]:
        key = (pause["stt_gap_start_sec"], pause["stt_gap_end_sec"])
        previous = str(pause["previous_word"])
        event_types = ["inter_word_gap"]
        if previous.endswith((".", "?", "!", "다", "요")):
            event_types.append("sentence_boundary_pause_candidate")
        if pause["classification"] == "long_silence":
            event_types.append("long_silence_candidate")
        if key in probable_keys or key in uncertain_keys:
            event_types.append("non_word_acoustic_event_candidate")
        events.append({**pause, "event_types": event_types})
    return events


def build_file_result(
    stt: dict[str, Any],
    audio_path: Path,
    stt_path: Path,
    raw: dict[str, Any],
    relative_root: Path,
) -> dict[str, Any]:
    words = stt.get("words")
    if not isinstance(words, list) or any(
        word.get("start") is None or word.get("end") is None for word in words
    ):
        raise SessionMetricsError(
            "WORD_TIMESTAMP_MISSING", stt["sample_id"]
        )
    gaps = [float(item["stt_gap_duration_sec"]) for item in raw["pauses"]]
    speech_duration = float(raw["acoustic_voiced_time_sec"])
    audio_duration = float(raw["audio_duration_sec"])
    word_count = int(stt["word_count"])
    eojeol_count = int(stt["eojeol_count"])
    quality = raw["audio_quality"]
    warnings = list(raw["warnings"])
    if not words:
        warnings.append("EMPTY_WORD_TIMESTAMPS")
    return {
        "schema_version": "1.0",
        "sample_id": stt["sample_id"],
        "speaker_code": stt["speaker_code"],
        "session_id": stt["session_id"],
        "script_id": stt["script_id"],
        "recording_condition": stt["recording_condition"],
        "repetition_index": stt["repetition_index"],
        "device_code": stt["device_code"],
        "capture_pair_key": stt["capture_pair_key"],
        "audio_file": relative_path(audio_path, relative_root),
        "audio_sha256": sha256_file(audio_path),
        "audio_duration_sec": audio_duration,
        "transcription_text": stt["transcription_text_raw"],
        "transcription_word_count": word_count,
        "transcription_eojeol_count": eojeol_count,
        "word_timestamps": words,
        "speech_duration_sec": speech_duration,
        "speech_duration_definition": (
            "Existing speech_metrics acoustic_voiced_time_sec: sum of 20 ms "
            "frames at or above the existing voiced threshold."
        ),
        "speaking_ratio": raw["speech_ratio"],
        "speech_rate_wpm": raw["words_per_minute_voiced"],
        "speech_rate_eojeol_per_min": (
            eojeol_count * 60.0 / speech_duration
            if speech_duration > 0
            else 0.0
        ),
        "speech_rate_word_per_min_audio_duration": (
            word_count * 60.0 / audio_duration if audio_duration > 0 else 0.0
        ),
        "speech_rate_eojeol_per_min_audio_duration": (
            eojeol_count * 60.0 / audio_duration
            if audio_duration > 0
            else 0.0
        ),
        "speech_rate_word_per_min_speech_duration": (
            word_count * 60.0 / speech_duration
            if speech_duration > 0
            else 0.0
        ),
        "speech_rate_eojeol_per_min_speech_duration": (
            eojeol_count * 60.0 / speech_duration
            if speech_duration > 0
            else 0.0
        ),
        "rate_denominator_notes": {
            "audio_duration": "Complete standard WAV duration, including silence.",
            "speech_duration": "Existing acoustic voiced-frame duration.",
        },
        "pause_count": raw["pause_count"],
        "total_pause_duration_sec": sum(gaps),
        "mean_pause_duration_sec": statistics.mean(gaps) if gaps else 0.0,
        "median_pause_duration_sec": statistics.median(gaps) if gaps else 0.0,
        "max_pause_duration_sec": max(gaps, default=0.0),
        "long_pause_count": raw["long_silence_count"],
        "long_pauses": raw["long_silences"],
        "pause_events": _pause_events(raw),
        "probable_omitted_vocalization_count": raw[
            "probable_omitted_vocalization_count"
        ],
        "probable_omitted_vocalizations": raw[
            "probable_omitted_vocalizations"
        ],
        "uncertain_gap_vocalization_count": raw[
            "uncertain_gap_vocalization_count"
        ],
        "uncertain_gap_vocalizations": raw[
            "uncertain_gap_vocalizations"
        ],
        "hallucination_candidate_count": len(
            raw["hallucination_candidates"]
        ),
        "hallucination_candidates": raw["hallucination_candidates"],
        "clipping_ratio": quality["clipping_frame_ratio"],
        "noise_floor_dbfs": quality["estimated_noise_floor_dbfs"],
        "background_noise_warning": quality["background_noise_suspected"],
        "low_signal_warning": None,
        "quality_warnings": quality["reliability_warnings"],
        "analysis_warnings": warnings
        + [
            "No low-signal threshold exists in the reused algorithm; low_signal_warning is null."
        ],
        "existing_speech_metrics": raw,
        "error": None,
    }


def _atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(strict_json_text(payload))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError) as exc:
        temporary.unlink(missing_ok=True)
        raise SessionMetricsError(
            "SPEECH_METRICS_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(
                {field: row.get(field, "") for field in MANIFEST_FIELDS}
                for row in rows
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        temporary.unlink(missing_ok=True)
        raise SessionMetricsError(
            "SPEECH_METRICS_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def analyze_session(
    conversion_manifest_path: Path | str,
    stt_pc_directory: Path | str,
    stt_phone_directory: Path | str,
    output_pc_directory: Path | str,
    output_phone_directory: Path | str,
    manifest_json_path: Path | str,
    manifest_csv_path: Path | str,
    relative_root: Path | str,
    *,
    analyzer: Callable[[Path, Path], dict[str, Any]] = analyze_speech_metrics,
) -> dict[str, Any]:
    root = Path(relative_root)
    manifest = _load_json(
        Path(conversion_manifest_path), "SESSION_SPEECH_METRICS_FAILED"
    )
    conversions = manifest.get("conversions")
    if not isinstance(conversions, list) or len(conversions) != 24:
        raise SessionMetricsError(
            "SESSION_SPEECH_METRICS_FAILED",
            "Conversion manifest must contain 24 rows.",
        )
    rows: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for conversion in conversions:
        sample_id = conversion["sample_id"]
        device = conversion["device_code"]
        audio = root / Path(conversion["destination_path"])
        stt_dir = (
            Path(stt_pc_directory)
            if device == "DEV_PC_MIC_01"
            else Path(stt_phone_directory)
        )
        output_dir = (
            Path(output_pc_directory)
            if device == "DEV_PC_MIC_01"
            else Path(output_phone_directory)
        )
        stt_path = stt_dir / f"{sample_id}.json"
        output = output_dir / f"{sample_id}.json"
        error: dict[str, str] | None = None
        result: dict[str, Any] | None = None
        if not audio.is_file():
            error = {"code": "STANDARD_WAV_NOT_FOUND", "detail": str(audio)}
        elif not stt_path.is_file():
            error = {"code": "STT_JSON_NOT_FOUND", "detail": str(stt_path)}
        else:
            try:
                stt = _load_json(stt_path, "STT_JSON_NOT_FOUND")
                if stt.get("error") is not None:
                    raise SessionMetricsError(
                        "STT_JSON_INVALID", sample_id
                    )
                raw = analyzer(audio, stt_path)
                result = build_file_result(stt, audio, stt_path, raw, root)
                _atomic_json(output, result)
                results.append(result)
            except SessionMetricsError as exc:
                error = {"code": exc.code, "detail": exc.detail}
            except Exception as exc:
                error = {
                    "code": "SPEECH_METRICS_ANALYSIS_FAILED",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
        base = result or {
            "sample_id": sample_id,
            "device_code": device,
            "error": error,
        }
        rows.append(
            {
                **base,
                "stt_json_file": relative_path(stt_path, root),
                "output_json": relative_path(output, root),
                "clipping_warning": (
                    bool(result)
                    and "clipping_suspected"
                    in result["existing_speech_metrics"]["audio_quality"][
                        "reliability_flags"
                    ]
                ),
                "error_code": error["code"] if error else "",
            }
        )
    summary = {
        "total_files": len(rows),
        "successful_files": len(results),
        "failed_files": len(rows) - len(results),
        "pc_files": sum(row["device_code"] == "DEV_PC_MIC_01" for row in rows),
        "phone_files": sum(
            row["device_code"] == "DEV_PHONE_01" for row in rows
        ),
        "clean_files": sum(
            row.get("recording_condition") == "clean" for row in results
        ),
        "natural_files": sum(
            row.get("recording_condition") == "natural" for row in results
        ),
    }
    payload = {
        "schema_version": "1.0",
        "session_id": "SESSION001",
        "summary": summary,
        "files": rows,
        "limitations": [
            "Existing speech_metrics thresholds are reused without modification.",
            "Pause candidates are not filler labels and no interview score is produced.",
            "Prosody v2.1 and pitch analysis were not run.",
        ],
        "error": (
            {
                "code": "SESSION_SPEECH_METRICS_FAILED",
                "detail": f"{summary['failed_files']} files failed.",
            }
            if summary["failed_files"]
            else None
        ),
    }
    _atomic_json(Path(manifest_json_path), payload)
    _atomic_csv(Path(manifest_csv_path), rows)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversion-manifest", type=Path, required=True)
    parser.add_argument("--stt-pc-dir", type=Path, required=True)
    parser.add_argument("--stt-phone-dir", type=Path, required=True)
    parser.add_argument("--output-pc-dir", type=Path, required=True)
    parser.add_argument("--output-phone-dir", type=Path, required=True)
    parser.add_argument("--manifest-json-output", type=Path, required=True)
    parser.add_argument("--manifest-csv-output", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = analyze_session(
            args.conversion_manifest,
            args.stt_pc_dir,
            args.stt_phone_dir,
            args.output_pc_dir,
            args.output_phone_dir,
            args.manifest_json_output,
            args.manifest_csv_output,
            args.relative_root,
        )
    except SessionMetricsError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "SESSION_SPEECH_METRICS_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(strict_json_text({"summary": result["summary"], "error": result["error"]}))
    return 1 if result["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
