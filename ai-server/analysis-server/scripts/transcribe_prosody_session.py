"""Validate source decoding lengths and batch-transcribe standard prosody WAVs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
import unicodedata
import wave
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from app.speech.whisper_service import (  # noqa: E402
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_MODEL_NAME,
    WhisperService,
)
import inventory_prosody_recordings as inventory  # noqa: E402


MODEL_NAME = DEFAULT_MODEL_NAME
DEVICE = DEFAULT_DEVICE
COMPUTE_TYPE = DEFAULT_COMPUTE_TYPE
LANGUAGE = "ko"
TASK = "transcribe"
DURATION_PASS_SEC = 0.05
DURATION_WARNING_SEC = 0.20
TIMESTAMP_OVERAGE_WARNING_SEC = 0.5
ERROR_CODES = {
    "STANDARD_WAV_NOT_FOUND",
    "CONVERSION_MANIFEST_INVALID",
    "DURATION_VALIDATION_FAILED",
    "CUDA_RUNTIME_UNAVAILABLE",
    "WHISPER_MODEL_LOAD_FAILED",
    "WHISPER_TRANSCRIPTION_FAILED",
    "WORD_TIMESTAMP_INVALID",
    "SCRIPT_REFERENCE_NOT_FOUND",
    "STT_RESULT_WRITE_FAILED",
    "DEVICE_PAIR_INCOMPLETE",
    "STT_EVALUATION_FAILED",
}
BATCH_FIELDS = (
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
    "audio_duration_sec",
    "output_json",
    "word_count",
    "eojeol_count",
    "processing_time_sec",
    "real_time_factor",
    "warning_count",
    "error_code",
)


class SessionTranscriptionError(Exception):
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


def normalize_korean_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", str(text)).lower()
    characters = [
        character
        for character in normalized
        if not unicodedata.category(character).startswith("P")
    ]
    return " ".join("".join(characters).strip().split())


def wav_frame_duration(path: Path | str) -> dict[str, Any]:
    with wave.open(str(path), "rb") as audio:
        frames = audio.getnframes()
        sample_rate = audio.getframerate()
    if sample_rate <= 0:
        raise SessionTranscriptionError(
            "STANDARD_WAV_NOT_FOUND", f"Invalid WAV sample rate: {path}"
        )
    return {
        "destination_wav_frame_count": frames,
        "destination_wav_sample_rate": sample_rate,
        "destination_wav_duration_sec": frames / sample_rate,
    }


def decoded_source_duration(path: Path | str) -> dict[str, Any]:
    try:
        import av  # type: ignore[import-not-found]

        container = av.open(str(path), mode="r")
        try:
            stream = next(item for item in container.streams if item.type == "audio")
            sample_rate = int(stream.codec_context.sample_rate or stream.rate or 0)
            sample_count = sum(frame.samples for frame in container.decode(stream))
            container_duration = (
                float(container.duration) / 1_000_000.0
                if container.duration is not None
                else None
            )
        finally:
            container.close()
    except Exception as exc:
        raise SessionTranscriptionError(
            "DURATION_VALIDATION_FAILED",
            f"{type(exc).__name__}: {exc}",
        ) from exc
    if sample_rate <= 0:
        raise SessionTranscriptionError(
            "DURATION_VALIDATION_FAILED", f"Invalid decoded sample rate: {path}"
        )
    return {
        "source_container_duration_sec": container_duration,
        "source_decoded_sample_count": sample_count,
        "source_decoded_sample_rate": sample_rate,
        "source_decoded_duration_sec": sample_count / sample_rate,
    }


def validate_decoded_duration(
    sample_id: str,
    source: Path | str,
    destination: Path | str,
) -> dict[str, Any]:
    decoded = decoded_source_duration(source)
    wav = wav_frame_duration(destination)
    container_duration = decoded["source_container_duration_sec"]
    decoded_duration = decoded["source_decoded_duration_sec"]
    wav_duration = wav["destination_wav_duration_sec"]
    decoded_difference = abs(decoded_duration - wav_duration)
    container_difference = (
        abs(float(container_duration) - decoded_duration)
        if container_duration is not None
        else None
    )
    warnings: list[str] = []
    if decoded_difference <= DURATION_PASS_SEC:
        status = "metadata_duration_discrepancy"
        if container_difference is not None and container_difference > DURATION_PASS_SEC:
            warnings.append("CONTAINER_METADATA_DURATION_DIFFERS_FROM_DECODED_PCM")
    elif decoded_difference <= DURATION_WARNING_SEC:
        status = "duration_difference_warning"
        warnings.append("DECODED_TO_WAV_DURATION_DIFFERENCE_WARNING")
    else:
        status = "possible_audio_loss"
        warnings.append("POSSIBLE_AUDIO_LOSS_STT_BLOCKED")
    return {
        "sample_id": sample_id,
        "source_file": str(source),
        "destination_wav": str(destination),
        **decoded,
        **wav,
        "container_to_decoded_difference_sec": container_difference,
        "decoded_to_wav_difference_sec": decoded_difference,
        "validation_status": status,
        "stt_allowed": status != "possible_audio_loss",
        "warnings": warnings,
    }


def load_conversion_manifest(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise SessionTranscriptionError(
            "CONVERSION_MANIFEST_INVALID", f"Missing manifest: {source}"
        )
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionTranscriptionError(
            "CONVERSION_MANIFEST_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    rows = payload.get("conversions")
    if not isinstance(rows, list) or len(rows) != 24:
        raise SessionTranscriptionError(
            "CONVERSION_MANIFEST_INVALID", "Expected 24 conversion rows."
        )
    return payload


def load_plan(path: Path | str) -> list[dict[str, str]]:
    try:
        return inventory.load_collection_plan(path)
    except inventory.RecordingInventoryError as exc:
        raise SessionTranscriptionError(
            "CONVERSION_MANIFEST_INVALID", exc.detail
        ) from exc


def _capture_pair_key(plan: dict[str, str]) -> str:
    return "|".join(
        plan[field]
        for field in (
            "speaker_code",
            "session_id",
            "script_id",
            "recording_condition",
            "repetition_index",
        )
    )


def validate_word_timestamps(
    words: list[dict[str, Any]],
    audio_duration_sec: float,
) -> list[str]:
    warnings: list[str] = []
    previous_start = 0.0
    previous_end = 0.0
    for index, word in enumerate(words):
        start = word.get("start")
        end = word.get("end")
        text = str(word.get("word") or "").strip()
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not math.isfinite(float(start))
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
            or not math.isfinite(float(end))
        ):
            warnings.append(f"WORD_TIMESTAMP_INVALID:NON_NUMERIC:{index}")
            continue
        if start < 0 or end < start:
            warnings.append(f"WORD_TIMESTAMP_INVALID:RANGE:{index}")
        if index and (start < previous_start or end < previous_end):
            warnings.append(f"WORD_TIMESTAMP_INVALID:ORDER:{index}")
        if not text:
            warnings.append(f"WORD_TIMESTAMP_INVALID:EMPTY_WORD:{index}")
        previous_start = float(start)
        previous_end = float(end)
    if words:
        final_end = words[-1].get("end")
        if (
            isinstance(final_end, (int, float))
            and final_end > audio_duration_sec + TIMESTAMP_OVERAGE_WARNING_SEC
        ):
            warnings.append("WORD_TIMESTAMP_EXCEEDS_AUDIO_DURATION")
    return warnings


def _word_dict(word: Any) -> dict[str, Any]:
    return {
        "start": getattr(word, "start", None),
        "end": getattr(word, "end", None),
        "word": getattr(word, "word", ""),
        "probability": getattr(word, "probability", None),
    }


def _segment_dict(segment: Any) -> dict[str, Any]:
    return {
        "id": getattr(segment, "id", None),
        "start": getattr(segment, "start", None),
        "end": getattr(segment, "end", None),
        "text": getattr(segment, "text", ""),
        "avg_logprob": getattr(segment, "avg_logprob", None),
        "no_speech_prob": getattr(segment, "no_speech_prob", None),
        "words": [
            _word_dict(word)
            for word in (getattr(segment, "words", None) or [])
        ],
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
        raise SessionTranscriptionError(
            "STT_RESULT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=BATCH_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in BATCH_FIELDS})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        temporary.unlink(missing_ok=True)
        raise SessionTranscriptionError(
            "STT_RESULT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _new_result(
    plan: dict[str, str],
    audio: Path,
    relative_root: Path,
) -> dict[str, Any]:
    duration = wav_frame_duration(audio)["destination_wav_duration_sec"]
    return {
        "schema_version": "1.0",
        "sample_id": plan["sample_id"],
        "speaker_code": plan["speaker_code"],
        "session_id": plan["session_id"],
        "script_id": plan["script_id"],
        "recording_condition": plan["recording_condition"],
        "repetition_index": int(plan["repetition_index"]),
        "device_code": plan["device_code"],
        "capture_pair_key": _capture_pair_key(plan),
        "audio_file": relative_path(audio, relative_root),
        "audio_sha256": sha256_file(audio),
        "audio_duration_sec": duration,
        "model_name": MODEL_NAME,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "language": LANGUAGE,
        "task": TASK,
        "transcription_text_raw": "",
        "transcription_text_normalized": "",
        "segments": [],
        "words": [],
        "word_count": 0,
        "eojeol_count": 0,
        "transcription_duration_sec": None,
        "processing_time_sec": None,
        "real_time_factor": None,
        "warnings": [],
        "error": None,
    }


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0 and COMPUTE_TYPE in set(
            ctranslate2.get_supported_compute_types("cuda")
        )
    except Exception:
        return False


def transcribe_batch(
    conversion_manifest_path: Path | str,
    plan_path: Path | str,
    relative_root: Path | str,
    pc_output_directory: Path | str,
    phone_output_directory: Path | str,
    batch_json_path: Path | str,
    batch_csv_path: Path | str,
    duration_json_path: Path | str,
    *,
    service_factory: Callable[[], WhisperService] | None = None,
    require_cuda_check: bool = True,
) -> dict[str, Any]:
    root = Path(relative_root)
    manifest = load_conversion_manifest(conversion_manifest_path)
    plan_rows = load_plan(plan_path)
    plan_by_sample = {row["sample_id"]: row for row in plan_rows}
    conversion_by_sample = {
        row["sample_id"]: row for row in manifest["conversions"]
    }
    if set(plan_by_sample) != set(conversion_by_sample):
        raise SessionTranscriptionError(
            "CONVERSION_MANIFEST_INVALID",
            "Plan and conversion manifest sample_id sets differ.",
        )

    duration_targets = [
        row
        for row in manifest["conversions"]
        if any(
            str(warning).startswith("DURATION_DIFFERENCE_WARNING")
            for warning in row.get("warnings", [])
        )
    ]
    duration_rows: list[dict[str, Any]] = []
    blocked: set[str] = set()
    for conversion in duration_targets:
        source = root / Path(conversion["source_path"])
        destination = root / Path(conversion["destination_path"])
        validation = validate_decoded_duration(
            conversion["sample_id"], source, destination
        )
        duration_rows.append(validation)
        if not validation["stt_allowed"]:
            blocked.add(conversion["sample_id"])
    duration_payload = {
        "schema_version": "1.0",
        "thresholds_sec": {
            "pass": DURATION_PASS_SEC,
            "warning": DURATION_WARNING_SEC,
        },
        "validated_warning_files": len(duration_rows),
        "blocked_files": len(blocked),
        "files": duration_rows,
        "error": (
            {
                "code": "DURATION_VALIDATION_FAILED",
                "detail": f"{len(blocked)} files exceed 0.20 seconds.",
            }
            if blocked
            else None
        ),
    }
    _atomic_json(Path(duration_json_path), duration_payload)

    results: list[dict[str, Any]] = []
    for plan in plan_rows:
        conversion = conversion_by_sample[plan["sample_id"]]
        audio = root / Path(conversion["destination_path"])
        if not audio.is_file():
            raise SessionTranscriptionError(
                "STANDARD_WAV_NOT_FOUND", str(audio)
            )
        results.append(_new_result(plan, audio, root))

    if require_cuda_check and not _cuda_available():
        raise SessionTranscriptionError(
            "CUDA_RUNTIME_UNAVAILABLE",
            "CUDA device or int8_float16 compute type is unavailable.",
        )
    service = (
        service_factory()
        if service_factory is not None
        else WhisperService(
            model_name=MODEL_NAME,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
    )
    try:
        model = service.initialize()
    except Exception as exc:
        raise SessionTranscriptionError(
            "WHISPER_MODEL_LOAD_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc

    started_total = time.perf_counter()
    output_paths: dict[str, str] = {}
    for result in results:
        sample_id = result["sample_id"]
        output_directory = (
            Path(pc_output_directory)
            if result["device_code"] == "DEV_PC_MIC_01"
            else Path(phone_output_directory)
        )
        output = output_directory / f"{sample_id}.json"
        output_paths[sample_id] = relative_path(output, root)
        if sample_id in blocked:
            result["error"] = {
                "code": "DURATION_VALIDATION_FAILED",
                "detail": "Decoded source and standard WAV differ by more than 0.20 seconds.",
            }
            _atomic_json(output, result)
            continue
        audio = root / Path(result["audio_file"])
        started = time.perf_counter()
        try:
            segment_generator, _info = model.transcribe(
                str(audio),
                language=LANGUAGE,
                task=TASK,
                word_timestamps=True,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            segments = [_segment_dict(segment) for segment in segment_generator]
        except Exception as exc:
            result["processing_time_sec"] = time.perf_counter() - started
            result["error"] = {
                "code": "WHISPER_TRANSCRIPTION_FAILED",
                "detail": f"{type(exc).__name__}: {exc}",
            }
            _atomic_json(output, result)
            continue
        elapsed = time.perf_counter() - started
        words = [word for segment in segments for word in segment["words"]]
        raw = "".join(segment["text"] for segment in segments).strip()
        normalized = normalize_korean_text(raw)
        timestamp_warnings = validate_word_timestamps(
            words, result["audio_duration_sec"]
        )
        result.update(
            {
                "transcription_text_raw": raw,
                "transcription_text_normalized": normalized,
                "segments": segments,
                "words": words,
                "word_count": len(words),
                "eojeol_count": len(normalized.split()) if normalized else 0,
                "transcription_duration_sec": (
                    max(
                        (
                            float(segment["end"])
                            for segment in segments
                            if isinstance(segment["end"], (int, float))
                        ),
                        default=0.0,
                    )
                ),
                "processing_time_sec": elapsed,
                "real_time_factor": elapsed / result["audio_duration_sec"],
                "warnings": timestamp_warnings,
            }
        )
        _atomic_json(output, result)

    total_elapsed = time.perf_counter() - started_total
    successful = [row for row in results if row["error"] is None]
    rtf_values = [
        row["real_time_factor"]
        for row in successful
        if isinstance(row["real_time_factor"], (int, float))
    ]
    batch_rows = [
        {
            **{field: result.get(field, "") for field in BATCH_FIELDS},
            "output_json": output_paths[result["sample_id"]],
            "warning_count": len(result["warnings"]),
            "error_code": (
                result["error"]["code"] if result["error"] else ""
            ),
        }
        for result in results
    ]
    summary = {
        "total_files": len(results),
        "successful_files": len(successful),
        "failed_files": len(results) - len(successful),
        "pc_files": sum(row["device_code"] == "DEV_PC_MIC_01" for row in results),
        "phone_files": sum(
            row["device_code"] == "DEV_PHONE_01" for row in results
        ),
        "clean_files": sum(row["recording_condition"] == "clean" for row in results),
        "natural_files": sum(
            row["recording_condition"] == "natural" for row in results
        ),
        "total_processing_time_sec": total_elapsed,
        "median_real_time_factor": statistics.median(rtf_values)
        if rtf_values
        else None,
        "max_real_time_factor": max(rtf_values) if rtf_values else None,
        "empty_transcription_count": sum(
            not row["transcription_text_normalized"] for row in successful
        ),
        "timestamp_warning_count": sum(
            any(warning.startswith("WORD_TIMESTAMP") for warning in row["warnings"])
            for row in results
        ),
        "duration_validation_warning_count": sum(
            bool(row["warnings"]) for row in duration_rows
        ),
    }
    batch_payload = {
        "schema_version": "1.0",
        "session_id": "SESSION001",
        "model": {
            "model_name": MODEL_NAME,
            "device": DEVICE,
            "compute_type": COMPUTE_TYPE,
            "language": LANGUAGE,
            "task": TASK,
            "word_timestamps": True,
            "vad_filter": False,
            "condition_on_previous_text": False,
            "initialization_count": service.initialization_count,
            "load_time_sec": service.load_time_sec,
        },
        "summary": summary,
        "files": batch_rows,
        "limitations": [
            "SPK001 한 명과 두 스크립트에 대한 내부 파일럿이다.",
            "이 결과는 전체 사용자 또는 모든 한국어 음성에 일반화하지 않는다.",
        ],
        "error": (
            {
                "code": "WHISPER_TRANSCRIPTION_FAILED",
                "detail": f"{summary['failed_files']} files failed.",
            }
            if summary["failed_files"]
            else None
        ),
    }
    _atomic_json(Path(batch_json_path), batch_payload)
    _atomic_csv(Path(batch_csv_path), batch_rows)
    return batch_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversion-manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    parser.add_argument("--pc-output-dir", type=Path, required=True)
    parser.add_argument("--phone-output-dir", type=Path, required=True)
    parser.add_argument("--batch-json-output", type=Path, required=True)
    parser.add_argument("--batch-csv-output", type=Path, required=True)
    parser.add_argument("--duration-json-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = transcribe_batch(
            args.conversion_manifest,
            args.plan,
            args.relative_root,
            args.pc_output_dir,
            args.phone_output_dir,
            args.batch_json_output,
            args.batch_csv_output,
            args.duration_json_output,
        )
    except SessionTranscriptionError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "WHISPER_TRANSCRIPTION_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(
        strict_json_text(
            {
                "model": result["model"],
                "summary": result["summary"],
                "error": result["error"],
            }
        )
    )
    return 1 if result["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
