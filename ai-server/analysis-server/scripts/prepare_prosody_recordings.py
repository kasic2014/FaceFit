"""Resolve safe recording mappings and create validated standard analysis WAVs."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import uuid
import wave
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

import convert_audio
import inventory_prosody_recordings as recording_inventory


CONVERSION_FIELDS = (
    "sample_id",
    "device_code",
    "source_path",
    "source_filename",
    "source_format",
    "source_sample_rate",
    "source_channels",
    "source_duration_sec",
    "source_sha256",
    "mapping_status",
    "destination_path",
    "destination_filename",
    "destination_format",
    "destination_sample_rate",
    "destination_channels",
    "destination_bit_depth",
    "destination_duration_sec",
    "destination_sha256",
    "duration_difference_sec",
    "conversion_status",
    "warnings",
    "error",
)
RESOLVED_MAPPING_FIELDS = recording_inventory.MAPPING_FIELDS
VALID_CONVERSION_STATUSES = {
    "converted",
    "skipped_existing_valid",
    "mapping_failed",
    "conversion_failed",
    "validation_failed",
}
REQUIRED_ERROR_CODES = {
    "COLLECTION_PLAN_NOT_FOUND",
    "COLLECTION_PLAN_INVALID",
    "SOURCE_RECORDING_NOT_FOUND",
    "SOURCE_MAPPING_AMBIGUOUS",
    "SOURCE_MAPPING_FAILED",
    "FFMPEG_NOT_FOUND",
    "AUDIO_CONVERSION_FAILED",
    "STANDARD_WAV_INVALID",
    "DURATION_MISMATCH",
    "DESTINATION_ALREADY_INVALID",
    "CONVERSION_MANIFEST_WRITE_FAILED",
    "RECORDING_PREPARATION_FAILED",
}
VALID_MAPPING_STATUSES = {
    "exact_filename_match",
    "exact_stem_supported_extension_match",
    "unmatched",
    "ambiguous",
}
SUCCESS_STATUSES = {"converted", "skipped_existing_valid"}
DEFAULT_DURATION_WARNING_SEC = 0.10
DEFAULT_DURATION_FAILURE_SEC = 1.0
FFMPEG_TIMEOUT_SECONDS = 120


class RecordingPreparationError(Exception):
    """A classified mapping, conversion, validation, or write failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def strict_json_text(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_existing_mapping(path: Path | str) -> list[dict[str, str]]:
    source = Path(path)
    if not source.is_file():
        raise RecordingPreparationError(
            "SOURCE_MAPPING_FAILED", f"Existing mapping not found: {source}"
        )
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            rows = list(reader)
    except (OSError, csv.Error, UnicodeError) as exc:
        raise RecordingPreparationError(
            "SOURCE_MAPPING_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    required = {"plan_id", "sample_id", "device_code", "mapping_status"}
    if len(rows) != 24 or not required.issubset(fields):
        raise RecordingPreparationError(
            "SOURCE_MAPPING_FAILED",
            f"Expected 24 mapping rows and required fields; found {len(rows)}.",
        )
    return rows


def _source_candidates(
    pc_directory: Path | str,
    phone_directory: Path | str,
) -> dict[str, list[Path]]:
    return {
        "DEV_PC_MIC_01": recording_inventory.discover_recordings(
            pc_directory, "pc"
        ),
        "DEV_PHONE_01": recording_inventory.discover_recordings(
            phone_directory, "phone"
        ),
    }


def resolve_source_mappings(
    plan_rows: Iterable[dict[str, str]],
    pc_directory: Path | str,
    phone_directory: Path | str,
    relative_root: Path | str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Resolve exact filenames, then the explicitly allowed PC stem exception."""
    root = Path(relative_root)
    candidates_by_device = _source_candidates(pc_directory, phone_directory)
    used_paths: set[Path] = set()
    resolved: list[dict[str, Any]] = []
    counts = Counter()

    for plan in plan_rows:
        device = plan["device_code"]
        expected = plan["expected_original_filename"]
        device_candidates = candidates_by_device.get(device, [])
        exact = [path for path in device_candidates if path.name == expected]
        selected: Path | None = None
        note = ""

        if len(exact) == 1 and exact[0].resolve() not in used_paths:
            selected = exact[0]
            status = "exact_filename_match"
        elif len(exact) > 1:
            status = "ambiguous"
            note = "Multiple exact filename candidates in the expected device folder."
        elif len(exact) == 1:
            status = "ambiguous"
            note = "Exact source was already assigned to another plan row."
        elif device == "DEV_PC_MIC_01":
            expected_stem = Path(expected).stem
            stem_matches = [
                path
                for path in device_candidates
                if path.stem == expected_stem
                and path.suffix.lower()
                in recording_inventory.SUPPORTED_EXTENSIONS
            ]
            unused = [
                path for path in stem_matches if path.resolve() not in used_paths
            ]
            if len(stem_matches) > 1:
                status = "ambiguous"
                note = "Multiple supported PC files share the exact expected stem."
            elif len(stem_matches) == 1 and len(unused) == 1:
                selected = unused[0]
                status = "exact_stem_supported_extension_match"
                note = "PC source differs from the plan only by supported extension."
            elif len(stem_matches) == 1:
                status = "ambiguous"
                note = "Exact-stem PC source was already assigned to another plan row."
            else:
                status = "unmatched"
                note = "No exact filename or permitted PC exact-stem match."
        else:
            status = "unmatched"
            note = "No exact filename match; no stem inference is allowed for this device."

        if selected is not None:
            used_paths.add(selected.resolve())
        counts[status] += 1
        resolved.append(
            {
                "plan_id": plan["plan_id"],
                "sample_id": plan["sample_id"],
                "device_code": device,
                "script_id": plan["script_id"],
                "recording_condition": plan["recording_condition"],
                "repetition_index": plan["repetition_index"],
                "expected_original_filename": expected,
                "source_filename": selected.name if selected else "",
                "source_relative_path": (
                    _relative(selected, root) if selected else ""
                ),
                "mapping_status": status,
                "mapping_note": note,
                "source_sha256": (
                    recording_inventory.sha256_file(selected)
                    if selected
                    else ""
                ),
            }
        )

    return resolved, {
        "total_plan_rows": len(resolved),
        "exact_filename_match": counts["exact_filename_match"],
        "exact_stem_supported_extension_match": counts[
            "exact_stem_supported_extension_match"
        ],
        "unmatched": counts["unmatched"],
        "ambiguous": counts["ambiguous"],
        "mapped_total": counts["exact_filename_match"]
        + counts["exact_stem_supported_extension_match"],
    }


def inspect_standard_wav(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    result: dict[str, Any] = {
        "valid": False,
        "format": "",
        "sample_rate": None,
        "channels": None,
        "bit_depth": None,
        "duration_sec": None,
        "sha256": "",
        "errors": [],
    }
    if not source.is_file():
        result["errors"].append("STANDARD_WAV_INVALID:FILE_NOT_FOUND")
        return result
    try:
        header = source.read_bytes()[:12]
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            result["errors"].append("STANDARD_WAV_INVALID:RIFF_WAVE_REQUIRED")
            return result
        with wave.open(str(source), "rb") as audio:
            channels = audio.getnchannels()
            sample_rate = audio.getframerate()
            sample_width = audio.getsampwidth()
            compression = audio.getcomptype()
            frames = audio.getnframes()
        duration = frames / sample_rate if sample_rate > 0 else 0.0
        result.update(
            {
                "format": "WAV/PCM_S16LE",
                "sample_rate": sample_rate,
                "channels": channels,
                "bit_depth": sample_width * 8,
                "duration_sec": duration,
                "sha256": recording_inventory.sha256_file(source),
            }
        )
        if compression != "NONE":
            result["errors"].append("STANDARD_WAV_INVALID:PCM_REQUIRED")
        if sample_width != 2:
            result["errors"].append("STANDARD_WAV_INVALID:PCM_S16LE_REQUIRED")
        if sample_rate != 16000:
            result["errors"].append("STANDARD_WAV_INVALID:SAMPLE_RATE_16000_REQUIRED")
        if channels != 1:
            result["errors"].append("STANDARD_WAV_INVALID:MONO_REQUIRED")
        if duration <= 0:
            result["errors"].append("STANDARD_WAV_INVALID:NON_POSITIVE_DURATION")
        result["valid"] = not result["errors"]
        return result
    except (OSError, EOFError, wave.Error) as exc:
        result["errors"].append(
            f"STANDARD_WAV_INVALID:{type(exc).__name__}:{exc}"
        )
        return result


def _convert_with_ffmpeg(source: Path, temporary: Path, executable: Path) -> None:
    command = [
        str(executable),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(temporary),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecordingPreparationError(
            "AUDIO_CONVERSION_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    if completed.returncode != 0:
        raise RecordingPreparationError(
            "AUDIO_CONVERSION_FAILED",
            completed.stderr.strip() or f"ffmpeg exited {completed.returncode}.",
        )


def _convert_with_existing_pyav(source: Path, temporary: Path) -> None:
    """Use the already-installed FFmpeg libraries when no executable exists."""
    try:
        import av  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RecordingPreparationError(
            "FFMPEG_NOT_FOUND",
            "No FFmpeg executable and the existing PyAV fallback is unavailable.",
        ) from exc
    input_container = None
    output_container = None
    try:
        input_container = av.open(str(source), mode="r")
        audio_streams = [
            stream for stream in input_container.streams if stream.type == "audio"
        ]
        if not audio_streams:
            raise ValueError("No audio stream found.")
        output_container = av.open(str(temporary), mode="w", format="wav")
        output_stream = output_container.add_stream("pcm_s16le", rate=16000)
        output_stream.layout = "mono"
        resampler = av.AudioResampler(
            format="s16",
            layout="mono",
            rate=16000,
        )
        for frame in input_container.decode(audio_streams[0]):
            converted = resampler.resample(frame)
            frames = converted if isinstance(converted, list) else [converted]
            for converted_frame in frames:
                if converted_frame is None:
                    continue
                for packet in output_stream.encode(converted_frame):
                    output_container.mux(packet)
        flushed = resampler.resample(None)
        flush_frames = flushed if isinstance(flushed, list) else [flushed]
        for converted_frame in flush_frames:
            if converted_frame is None:
                continue
            for packet in output_stream.encode(converted_frame):
                output_container.mux(packet)
        for packet in output_stream.encode(None):
            output_container.mux(packet)
    except RecordingPreparationError:
        raise
    except Exception as exc:
        raise RecordingPreparationError(
            "AUDIO_CONVERSION_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if output_container is not None:
            output_container.close()
        if input_container is not None:
            input_container.close()


def convert_to_temporary(
    source: Path,
    temporary: Path,
) -> list[str]:
    ffmpeg_path, resolution_error = convert_audio.find_ffmpeg()
    if ffmpeg_path is not None:
        _convert_with_ffmpeg(source, temporary, ffmpeg_path)
        return []
    if resolution_error not in {"FFMPEG_NOT_FOUND", "FFMPEG_PATH_INVALID"}:
        raise RecordingPreparationError(
            "FFMPEG_NOT_FOUND", str(resolution_error)
        )
    _convert_with_existing_pyav(source, temporary)
    return [
        "FFMPEG_EXECUTABLE_NOT_FOUND_USED_EXISTING_PYAV_FFMPEG_LIBRARIES"
    ]


def _base_conversion_row(
    plan: dict[str, str],
    mapping: dict[str, Any],
    destination: Path,
    relative_root: Path,
) -> dict[str, Any]:
    return {
        "sample_id": plan["sample_id"],
        "device_code": plan["device_code"],
        "source_path": mapping["source_relative_path"],
        "source_filename": mapping["source_filename"],
        "source_format": "",
        "source_sample_rate": None,
        "source_channels": None,
        "source_duration_sec": None,
        "source_sha256": mapping["source_sha256"],
        "mapping_status": mapping["mapping_status"],
        "destination_path": _relative(destination, relative_root),
        "destination_filename": destination.name,
        "destination_format": "",
        "destination_sample_rate": None,
        "destination_channels": None,
        "destination_bit_depth": None,
        "destination_duration_sec": None,
        "destination_sha256": "",
        "duration_difference_sec": None,
        "conversion_status": "mapping_failed",
        "warnings": [],
        "error": "",
    }


def _apply_destination_metadata(
    row: dict[str, Any],
    inspection: dict[str, Any],
) -> None:
    row.update(
        {
            "destination_format": inspection["format"],
            "destination_sample_rate": inspection["sample_rate"],
            "destination_channels": inspection["channels"],
            "destination_bit_depth": inspection["bit_depth"],
            "destination_duration_sec": inspection["duration_sec"],
            "destination_sha256": inspection["sha256"],
        }
    )


def _duration_validation(
    row: dict[str, Any],
    warning_threshold_sec: float,
    failure_threshold_sec: float,
) -> bool:
    difference = abs(
        float(row["source_duration_sec"])
        - float(row["destination_duration_sec"])
    )
    row["duration_difference_sec"] = difference
    if difference >= failure_threshold_sec:
        row["error"] = (
            f"DURATION_MISMATCH: difference {difference:.6f}s is at least "
            f"{failure_threshold_sec:.6f}s."
        )
        return False
    if difference > warning_threshold_sec:
        row["warnings"].append(
            f"DURATION_DIFFERENCE_WARNING:{difference:.6f}s"
        )
    return True


def prepare_one_recording(
    plan: dict[str, str],
    mapping: dict[str, Any],
    relative_root: Path | str,
    standard_pc_directory: Path | str,
    standard_phone_directory: Path | str,
    *,
    overwrite: bool = False,
    duration_warning_sec: float = DEFAULT_DURATION_WARNING_SEC,
    duration_failure_sec: float = DEFAULT_DURATION_FAILURE_SEC,
    converter: Callable[[Path, Path], list[str]] = convert_to_temporary,
) -> dict[str, Any]:
    root = Path(relative_root)
    destination_root = (
        Path(standard_pc_directory)
        if plan["device_code"] == "DEV_PC_MIC_01"
        else Path(standard_phone_directory)
    )
    destination = destination_root / plan["expected_analysis_wav_filename"]
    row = _base_conversion_row(plan, mapping, destination, root)

    if mapping["mapping_status"] not in {
        "exact_filename_match",
        "exact_stem_supported_extension_match",
    }:
        row["error"] = (
            "SOURCE_MAPPING_AMBIGUOUS"
            if mapping["mapping_status"] == "ambiguous"
            else "SOURCE_RECORDING_NOT_FOUND"
        )
        return row
    source = root / Path(str(mapping["source_relative_path"]))
    if not source.is_file():
        row["error"] = "SOURCE_RECORDING_NOT_FOUND"
        return row
    if source.resolve() == destination.resolve():
        row["error"] = "SOURCE_MAPPING_FAILED: source and destination paths match."
        return row
    try:
        source_metadata = recording_inventory.inspect_audio_metadata(source)
    except Exception as exc:
        row["error"] = f"SOURCE_MAPPING_FAILED:{type(exc).__name__}:{exc}"
        return row
    row.update(
        {
            "source_format": source_metadata["detected_audio_format"],
            "source_sample_rate": source_metadata["sample_rate"],
            "source_channels": source_metadata["channels"],
            "source_duration_sec": source_metadata["duration_sec"],
            "source_sha256": recording_inventory.sha256_file(source),
        }
    )

    if destination.exists() and not overwrite:
        inspection = inspect_standard_wav(destination)
        _apply_destination_metadata(row, inspection)
        if not inspection["valid"]:
            row["conversion_status"] = "validation_failed"
            row["error"] = "DESTINATION_ALREADY_INVALID:" + ";".join(
                inspection["errors"]
            )
            return row
        if not _duration_validation(
            row, duration_warning_sec, duration_failure_sec
        ):
            row["conversion_status"] = "validation_failed"
            return row
        row["conversion_status"] = "skipped_existing_valid"
        return row

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.stem}.{uuid.uuid4().hex}.tmp.wav"
    )
    try:
        row["warnings"].extend(converter(source, temporary))
        inspection = inspect_standard_wav(temporary)
        _apply_destination_metadata(row, inspection)
        if not inspection["valid"]:
            row["conversion_status"] = "validation_failed"
            row["error"] = "STANDARD_WAV_INVALID:" + ";".join(
                inspection["errors"]
            )
            return row
        if not _duration_validation(
            row, duration_warning_sec, duration_failure_sec
        ):
            row["conversion_status"] = "validation_failed"
            return row
        os.replace(temporary, destination)
        row["conversion_status"] = "converted"
        return row
    except RecordingPreparationError as exc:
        row["conversion_status"] = "conversion_failed"
        row["error"] = f"{exc.code}:{exc.detail}"
        return row
    except OSError as exc:
        row["conversion_status"] = "conversion_failed"
        row["error"] = f"AUDIO_CONVERSION_FAILED:{type(exc).__name__}:{exc}"
        return row
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def validate_prepared_pairs(
    plan_rows: list[dict[str, str]],
    conversions: list[dict[str, Any]],
) -> dict[str, Any]:
    by_sample = {row["sample_id"]: row for row in conversions}
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for plan in plan_rows:
        key = (
            plan["speaker_code"],
            plan["session_id"],
            plan["script_id"],
            plan["recording_condition"],
            plan["repetition_index"],
        )
        groups[key].append(plan)
    invalid: list[dict[str, Any]] = []
    for key, pair in groups.items():
        devices = {row["device_code"] for row in pair}
        statuses = [
            by_sample.get(row["sample_id"], {}).get("conversion_status")
            for row in pair
        ]
        names = {
            row["device_code"]: by_sample.get(row["sample_id"], {}).get(
                "destination_filename", ""
            )
            for row in pair
        }
        pc_name = names.get("DEV_PC_MIC_01", "")
        phone_name = names.get("DEV_PHONE_01", "")
        device_only_difference = bool(
            pc_name
            and phone_name
            and pc_name.replace("DEV_PC_MIC_01", "DEV_PHONE_01")
            == phone_name
        )
        if (
            len(pair) != 2
            or devices
            != {"DEV_PC_MIC_01", "DEV_PHONE_01"}
            or any(status not in SUCCESS_STATUSES for status in statuses)
            or not device_only_difference
        ):
            invalid.append(
                {
                    "pair_key": list(key),
                    "devices": sorted(devices),
                    "statuses": statuses,
                    "destination_filenames": names,
                }
            )
    return {
        "pair_count": len(groups),
        "valid_pair_count": len(groups) - len(invalid),
        "invalid_pair_count": len(invalid),
        "invalid_pairs": invalid,
    }


def _atomic_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
    error_code: str = "CONVERSION_MANIFEST_WRITE_FAILED",
) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                formatted = {field: row.get(field, "") for field in fields}
                if isinstance(formatted.get("warnings"), list):
                    formatted["warnings"] = ";".join(formatted["warnings"])
                writer.writerow(formatted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RecordingPreparationError(
            error_code, f"{type(exc).__name__}: {exc}"
        ) from exc


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(strict_json_text(payload))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RecordingPreparationError(
            "CONVERSION_MANIFEST_WRITE_FAILED",
            f"{type(exc).__name__}: {exc}",
        ) from exc


def prepare_recordings(
    plan_path: Path | str,
    existing_mapping_path: Path | str,
    pc_directory: Path | str,
    phone_directory: Path | str,
    standard_pc_directory: Path | str,
    standard_phone_directory: Path | str,
    relative_root: Path | str,
    *,
    overwrite: bool = False,
    duration_warning_sec: float = DEFAULT_DURATION_WARNING_SEC,
    duration_failure_sec: float = DEFAULT_DURATION_FAILURE_SEC,
    converter: Callable[[Path, Path], list[str]] = convert_to_temporary,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if (
        duration_warning_sec < 0
        or duration_failure_sec <= duration_warning_sec
    ):
        raise RecordingPreparationError(
            "RECORDING_PREPARATION_FAILED",
            "Duration thresholds must satisfy 0 <= warning < failure.",
        )
    try:
        plan_rows = recording_inventory.load_collection_plan(plan_path)
    except recording_inventory.RecordingInventoryError as exc:
        code = (
            exc.code
            if exc.code
            in {"COLLECTION_PLAN_NOT_FOUND", "COLLECTION_PLAN_INVALID"}
            else "COLLECTION_PLAN_INVALID"
        )
        raise RecordingPreparationError(code, exc.detail) from exc
    existing_mapping = load_existing_mapping(existing_mapping_path)
    if {row["plan_id"] for row in existing_mapping} != {
        row["plan_id"] for row in plan_rows
    }:
        raise RecordingPreparationError(
            "SOURCE_MAPPING_FAILED",
            "Existing mapping plan_id set does not match the collection plan.",
        )
    resolved, mapping_summary = resolve_source_mappings(
        plan_rows, pc_directory, phone_directory, relative_root
    )
    resolved_by_plan = {row["plan_id"]: row for row in resolved}
    conversions = [
        prepare_one_recording(
            plan,
            resolved_by_plan[plan["plan_id"]],
            relative_root,
            standard_pc_directory,
            standard_phone_directory,
            overwrite=overwrite,
            duration_warning_sec=duration_warning_sec,
            duration_failure_sec=duration_failure_sec,
            converter=converter,
        )
        for plan in plan_rows
    ]
    status_counts = Counter(row["conversion_status"] for row in conversions)
    pair_summary = validate_prepared_pairs(plan_rows, conversions)
    failures = [
        {
            "sample_id": row["sample_id"],
            "conversion_status": row["conversion_status"],
            "error": row["error"],
        }
        for row in conversions
        if row["conversion_status"] not in SUCCESS_STATUSES
    ]
    warning_count = sum(len(row["warnings"]) for row in conversions)
    manifest = {
        "schema_version": "1.0",
        "description": (
            "Read-only source mapping and standard WAV conversion manifest. "
            "No STT, quality metrics, prosody analysis, trimming, normalization, "
            "denoising, or device alignment was performed."
        ),
        "session_id": "SESSION001",
        "configuration": {
            "destination_format": "WAV/PCM_S16LE",
            "destination_sample_rate": 16000,
            "destination_channels": 1,
            "destination_bit_depth": 16,
            "duration_warning_threshold_sec": duration_warning_sec,
            "duration_failure_threshold_sec": duration_failure_sec,
            "overwrite": overwrite,
        },
        "mapping_summary": mapping_summary,
        "conversion_summary": {
            "total": len(conversions),
            "converted": status_counts["converted"],
            "skipped_existing_valid": status_counts[
                "skipped_existing_valid"
            ],
            "mapping_failed": status_counts["mapping_failed"],
            "conversion_failed": status_counts["conversion_failed"],
            "validation_failed": status_counts["validation_failed"],
            "failed_total": len(failures),
            "warning_count": warning_count,
            "pc_standard_wav_count": sum(
                row["device_code"] == "DEV_PC_MIC_01"
                and row["conversion_status"] in SUCCESS_STATUSES
                for row in conversions
            ),
            "phone_standard_wav_count": sum(
                row["device_code"] == "DEV_PHONE_01"
                and row["conversion_status"] in SUCCESS_STATUSES
                for row in conversions
            ),
        },
        "device_pair_summary": pair_summary,
        "conversions": conversions,
        "failures": failures,
        "warnings": [
            "Original recordings remain immutable; standard WAV files are separate derivatives.",
            "Duration equality across devices is not required and no waveform alignment was performed.",
        ],
        "error": (
            {
                "code": "RECORDING_PREPARATION_FAILED",
                "detail": (
                    f"{len(failures)} conversion rows or "
                    f"{pair_summary['invalid_pair_count']} device pairs failed."
                ),
            }
            if failures or pair_summary["invalid_pair_count"]
            else None
        ),
    }
    return manifest, resolved, conversions


def write_preparation_outputs(
    resolved_mapping_path: Path | str,
    manifest_json_path: Path | str,
    manifest_csv_path: Path | str,
    manifest: dict[str, Any],
    resolved_mappings: list[dict[str, Any]],
    conversions: list[dict[str, Any]],
) -> None:
    destinations = [
        Path(resolved_mapping_path).resolve(),
        Path(manifest_json_path).resolve(),
        Path(manifest_csv_path).resolve(),
    ]
    if len(set(destinations)) != 3:
        raise RecordingPreparationError(
            "CONVERSION_MANIFEST_WRITE_FAILED",
            "Resolved mapping and manifest output paths must be distinct.",
        )
    _atomic_csv(
        Path(resolved_mapping_path),
        resolved_mappings,
        RESOLVED_MAPPING_FIELDS,
    )
    _atomic_json(Path(manifest_json_path), manifest)
    _atomic_csv(
        Path(manifest_csv_path), conversions, CONVERSION_FIELDS
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--pc-dir", type=Path, required=True)
    parser.add_argument("--phone-dir", type=Path, required=True)
    parser.add_argument("--standard-pc-dir", type=Path, required=True)
    parser.add_argument("--standard-phone-dir", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    parser.add_argument("--resolved-mapping-output", type=Path, required=True)
    parser.add_argument("--manifest-json-output", type=Path, required=True)
    parser.add_argument("--manifest-csv-output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--duration-warning-sec",
        type=float,
        default=DEFAULT_DURATION_WARNING_SEC,
    )
    parser.add_argument(
        "--duration-failure-sec",
        type=float,
        default=DEFAULT_DURATION_FAILURE_SEC,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        manifest, mappings, conversions = prepare_recordings(
            args.plan,
            args.mapping,
            args.pc_dir,
            args.phone_dir,
            args.standard_pc_dir,
            args.standard_phone_dir,
            args.relative_root,
            overwrite=args.overwrite,
            duration_warning_sec=args.duration_warning_sec,
            duration_failure_sec=args.duration_failure_sec,
        )
        write_preparation_outputs(
            args.resolved_mapping_output,
            args.manifest_json_output,
            args.manifest_csv_output,
            manifest,
            mappings,
            conversions,
        )
    except RecordingPreparationError as exc:
        print(
            strict_json_text(
                {"error": {"code": exc.code, "detail": exc.detail}}
            )
        )
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "RECORDING_PREPARATION_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(
        strict_json_text(
            {
                "mapping_summary": manifest["mapping_summary"],
                "conversion_summary": manifest["conversion_summary"],
                "device_pair_summary": manifest["device_pair_summary"],
                "error": manifest["error"],
            }
        )
    )
    return 1 if manifest["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
