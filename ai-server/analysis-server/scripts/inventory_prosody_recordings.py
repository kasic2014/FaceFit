"""Inventory immutable prosody recordings and map exact plan filenames only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import wave
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


INVENTORY_FIELDS = (
    "source_device_group",
    "source_filename",
    "source_relative_path",
    "extension",
    "file_size_bytes",
    "created_time",
    "modified_time",
    "sha256",
    "detected_audio_format",
    "duration_sec",
    "sample_rate",
    "channels",
    "bit_depth",
    "readable",
    "inspection_warnings",
)
MAPPING_FIELDS = (
    "plan_id",
    "sample_id",
    "device_code",
    "script_id",
    "recording_condition",
    "repetition_index",
    "expected_original_filename",
    "source_filename",
    "source_relative_path",
    "mapping_status",
    "mapping_note",
    "source_sha256",
)
PLAN_REQUIRED_FIELDS = {
    "plan_id",
    "sample_id",
    "speaker_code",
    "session_id",
    "script_id",
    "recording_condition",
    "repetition_index",
    "device_code",
    "recording_order",
    "expected_original_filename",
    "expected_analysis_wav_filename",
}
SUPPORTED_EXTENSIONS = {
    ".wav",
    ".wave",
    ".m4a",
    ".mp4",
    ".3gp",
    ".3g2",
    ".aac",
    ".mp3",
    ".flac",
    ".ogg",
    ".opus",
}
TEMPORARY_SUFFIXES = {".tmp", ".temp", ".part", ".crdownload"}
DEVICE_CODES = {"pc": "DEV_PC_MIC_01", "phone": "DEV_PHONE_01"}
KNOWN_ERROR_CODES = {
    "PC_RECORDING_DIRECTORY_NOT_FOUND",
    "PHONE_RECORDING_DIRECTORY_NOT_FOUND",
    "RECORDING_COUNT_MISMATCH",
    "AUDIO_FILE_UNREADABLE",
    "UNSUPPORTED_AUDIO_FORMAT",
    "DUPLICATE_AUDIO_HASH",
    "COLLECTION_PLAN_NOT_FOUND",
    "COLLECTION_PLAN_INVALID",
    "MAPPING_AMBIGUOUS",
    "INVENTORY_WRITE_FAILED",
    "RECORDING_INVENTORY_FAILED",
}


class RecordingInventoryError(Exception):
    """A classified inventory failure."""

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


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _ignored_file(path: Path) -> bool:
    name = path.name
    lower = name.lower()
    return (
        name.startswith(".")
        or name.startswith("~$")
        or lower == "thumbs.db"
        or path.suffix.lower() in TEMPORARY_SUFFIXES
    )


def discover_recordings(directory: Path | str, device_group: str) -> list[Path]:
    root = Path(directory)
    if not root.is_dir():
        code = (
            "PC_RECORDING_DIRECTORY_NOT_FOUND"
            if device_group == "pc"
            else "PHONE_RECORDING_DIRECTORY_NOT_FOUND"
        )
        raise RecordingInventoryError(code, str(root))
    return sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file() and not _ignored_file(path)
        ),
        key=lambda path: path.name,
    )


def _wav_metadata(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as audio:
        sample_rate = audio.getframerate()
        frame_count = audio.getnframes()
        channels = audio.getnchannels()
        bit_depth = audio.getsampwidth() * 8
    if sample_rate <= 0 or channels <= 0:
        raise ValueError("Invalid WAV stream metadata.")
    return {
        "detected_audio_format": "WAV/PCM",
        "duration_sec": frame_count / sample_rate,
        "sample_rate": sample_rate,
        "channels": channels,
        "bit_depth": bit_depth,
    }


def _find_ffprobe() -> str | None:
    explicit = os.environ.get("FFPROBE_PATH")
    if explicit and Path(explicit).is_file():
        return explicit
    ffmpeg = os.environ.get("FFMPEG_PATH")
    if ffmpeg:
        sibling = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.is_file():
            return str(sibling)
    return shutil.which("ffprobe")


def _format_label(extension: str, codec: str, container_name: str) -> str:
    codec_upper = codec.upper() if codec else "UNKNOWN"
    if extension in {".m4a", ".mp4", ".3gp", ".3g2"}:
        return f"M4A/{codec_upper}" if codec else "M4A"
    if extension in {".wav", ".wave"}:
        return f"WAV/{codec_upper}"
    if extension:
        return f"{extension[1:].upper()}/{codec_upper}"
    return container_name or codec_upper


def _ffprobe_metadata(path: Path, executable: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "format=format_name,duration:stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample,duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or "ffprobe failed.")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise ValueError("No audio stream found.")
    stream = streams[0]
    format_data = payload.get("format") or {}
    duration = stream.get("duration") or format_data.get("duration")
    bit_depth = stream.get("bits_per_raw_sample") or stream.get("bits_per_sample")
    return {
        "detected_audio_format": _format_label(
            path.suffix.lower(),
            str(stream.get("codec_name") or ""),
            str(format_data.get("format_name") or ""),
        ),
        "duration_sec": float(duration),
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "bit_depth": int(bit_depth) if bit_depth not in (None, "", "0", 0) else None,
    }


def _pyav_metadata(path: Path) -> dict[str, Any]:
    try:
        import av  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError("Neither ffprobe nor the existing PyAV dependency is available.") from exc

    container = av.open(str(path), mode="r")
    try:
        streams = [stream for stream in container.streams if stream.type == "audio"]
        if not streams:
            raise ValueError("No audio stream found.")
        stream = streams[0]
        context = stream.codec_context
        duration: float | None = None
        if stream.duration is not None and stream.time_base is not None:
            duration = float(stream.duration * stream.time_base)
        elif container.duration is not None:
            duration = float(container.duration) / 1_000_000.0
        sample_rate = int(context.sample_rate or stream.rate or 0)
        channels = int(context.channels or 0)
        codec = str(context.name or "")
        bit_depth = getattr(context, "bits_per_raw_sample", None)
        if not bit_depth:
            bit_depth = getattr(context, "bits_per_coded_sample", None)
        if duration is None or sample_rate <= 0 or channels <= 0:
            raise ValueError("Incomplete audio stream metadata.")
        return {
            "detected_audio_format": _format_label(
                path.suffix.lower(), codec, str(container.format.name or "")
            ),
            "duration_sec": duration,
            "sample_rate": sample_rate,
            "channels": channels,
            "bit_depth": int(bit_depth) if bit_depth else None,
        }
    finally:
        container.close()


def inspect_audio_metadata(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    extension = source.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise RecordingInventoryError(
            "UNSUPPORTED_AUDIO_FORMAT",
            f"{source.name}: extension {extension or '<none>'}",
        )
    if extension in {".wav", ".wave"}:
        return _wav_metadata(source)
    ffprobe = _find_ffprobe()
    if ffprobe:
        return _ffprobe_metadata(source, ffprobe)
    return _pyav_metadata(source)


def inspect_recording(
    path: Path | str,
    device_group: str,
    relative_root: Path | str,
) -> dict[str, Any]:
    source = Path(path)
    stat = source.stat()
    try:
        relative = source.resolve().relative_to(Path(relative_root).resolve()).as_posix()
    except ValueError:
        relative = source.resolve().as_posix()
    warnings: list[str] = []
    metadata: dict[str, Any] = {
        "detected_audio_format": "",
        "duration_sec": None,
        "sample_rate": None,
        "channels": None,
        "bit_depth": None,
    }
    readable = False
    if stat.st_size == 0:
        warnings.append("EMPTY_AUDIO_FILE")
    else:
        try:
            metadata = inspect_audio_metadata(source)
            readable = bool(metadata["duration_sec"] > 0)
            if not readable:
                warnings.append("NON_POSITIVE_DURATION")
            if metadata.get("bit_depth") is None:
                warnings.append("BIT_DEPTH_UNAVAILABLE_FOR_COMPRESSED_AUDIO")
            if source.suffix.lower() not in {".wav", ".wave"}:
                warnings.append("ANALYSIS_WAV_CONVERSION_REQUIRED")
        except RecordingInventoryError as exc:
            warnings.append(exc.code)
        except Exception as exc:  # metadata readers expose several exception types
            warnings.append(f"AUDIO_FILE_UNREADABLE:{type(exc).__name__}")
    return {
        "source_device_group": device_group,
        "source_filename": source.name,
        "source_relative_path": relative,
        "extension": source.suffix.lower(),
        "file_size_bytes": stat.st_size,
        "created_time": _iso_time(stat.st_ctime),
        "modified_time": _iso_time(stat.st_mtime),
        "sha256": sha256_file(source),
        **metadata,
        "readable": readable,
        "inspection_warnings": warnings,
    }


def load_collection_plan(path: Path | str) -> list[dict[str, str]]:
    source = Path(path)
    if not source.is_file():
        raise RecordingInventoryError("COLLECTION_PLAN_NOT_FOUND", str(source))
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            rows = list(reader)
    except (OSError, csv.Error, UnicodeError) as exc:
        raise RecordingInventoryError(
            "COLLECTION_PLAN_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    if not PLAN_REQUIRED_FIELDS.issubset(fields) or len(rows) != 24:
        raise RecordingInventoryError(
            "COLLECTION_PLAN_INVALID",
            f"Expected 24 rows and required columns; found {len(rows)} rows.",
        )
    if len({row["plan_id"] for row in rows}) != 24:
        raise RecordingInventoryError(
            "COLLECTION_PLAN_INVALID", "plan_id values must be unique."
        )
    return rows


def validate_device_pairs(rows: Iterable[dict[str, str]]) -> dict[str, Any]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            row["speaker_code"],
            row["session_id"],
            row["script_id"],
            row["recording_condition"],
            row["repetition_index"],
        )
        groups[key].append(row)
    complete = 0
    invalid: list[dict[str, Any]] = []
    expected = set(DEVICE_CODES.values())
    for key, pair in groups.items():
        devices = [row["device_code"] for row in pair]
        if len(pair) == 2 and set(devices) == expected and len(set(devices)) == 2:
            complete += 1
        else:
            invalid.append({"pair_key": list(key), "devices": devices})
    if len(groups) != 12 or invalid:
        raise RecordingInventoryError(
            "COLLECTION_PLAN_INVALID",
            f"Expected 12 complete device pairs; found {complete}.",
        )
    return {
        "pair_count": len(groups),
        "complete_pair_count": complete,
        "invalid_pair_count": len(invalid),
        "pair_key_fields": [
            "speaker_code",
            "session_id",
            "script_id",
            "recording_condition",
            "repetition_index",
        ],
    }


def build_mapping_rows(
    plan_rows: Iterable[dict[str, str]],
    inventory_rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_filename: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recording in inventory_rows:
        by_filename[str(recording["source_filename"])].append(recording)

    mappings: list[dict[str, Any]] = []
    counts = Counter()
    for plan_row in plan_rows:
        candidates = by_filename[plan_row["expected_original_filename"]]
        source: dict[str, Any] | None = None
        if len(candidates) == 1:
            source = candidates[0]
            mapping_status = "exact_filename_match"
            mapping_note = ""
            counts["exact_filename_match"] += 1
        elif not candidates:
            mapping_status = "needs_manual_mapping"
            mapping_note = "No exact expected_original_filename match; not inferred by order or time."
            counts["unmatched"] += 1
        else:
            mapping_status = "ambiguous"
            mapping_note = "Multiple exact filename candidates; manual mapping required."
            counts["ambiguous"] += 1
        mappings.append(
            {
                "plan_id": plan_row["plan_id"],
                "sample_id": plan_row["sample_id"],
                "device_code": plan_row["device_code"],
                "script_id": plan_row["script_id"],
                "recording_condition": plan_row["recording_condition"],
                "repetition_index": plan_row["repetition_index"],
                "expected_original_filename": plan_row["expected_original_filename"],
                "source_filename": source["source_filename"] if source else "",
                "source_relative_path": source["source_relative_path"] if source else "",
                "mapping_status": mapping_status,
                "mapping_note": mapping_note,
                "source_sha256": source["sha256"] if source else "",
            }
        )
    counts["needs_manual_mapping"] = counts["unmatched"] + counts["ambiguous"]
    return mappings, {
        "exact_filename_match": counts["exact_filename_match"],
        "unmatched": counts["unmatched"],
        "ambiguous": counts["ambiguous"],
        "needs_manual_mapping": counts["needs_manual_mapping"],
    }


def _device_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durations = sorted(
        float(row["duration_sec"])
        for row in rows
        if row["readable"] and row["duration_sec"] is not None
    )
    formats = Counter(str(row["detected_audio_format"]) for row in rows if row["detected_audio_format"])
    rates = Counter(str(row["sample_rate"]) for row in rows if row["sample_rate"])
    channels = Counter(str(row["channels"]) for row in rows if row["channels"])
    return {
        "file_count": len(rows),
        "audio_format_counts": dict(formats),
        "sample_rate_counts": dict(rates),
        "channel_counts": dict(channels),
        "duration_sec": {
            "min": min(durations) if durations else None,
            "median": statistics.median(durations) if durations else None,
            "max": max(durations) if durations else None,
        },
        "read_failure_count": sum(not row["readable"] for row in rows),
        "conversion_required_count": sum(
            row["extension"] not in {".wav", ".wave"} for row in rows
        ),
    }


def validate_inventory(
    rows: list[dict[str, Any]],
    pc_count: int,
    phone_count: int,
    mapping_summary: dict[str, int],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    def add(code: str, detail: str) -> None:
        errors.append({"code": code, "detail": detail})

    if pc_count != 12 or phone_count != 12 or len(rows) != 24:
        add(
            "RECORDING_COUNT_MISMATCH",
            f"Expected pc=12, phone=12, total=24; found pc={pc_count}, phone={phone_count}, total={len(rows)}.",
        )
    unreadable = [row["source_filename"] for row in rows if not row["readable"]]
    if unreadable:
        add("AUDIO_FILE_UNREADABLE", ", ".join(unreadable))
    unsupported = [
        row["source_filename"]
        for row in rows
        if "UNSUPPORTED_AUDIO_FORMAT" in row["inspection_warnings"]
    ]
    if unsupported:
        add("UNSUPPORTED_AUDIO_FORMAT", ", ".join(unsupported))
    hashes: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        hashes[str(row["sha256"])].append(str(row["source_relative_path"]))
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    if duplicates:
        add("DUPLICATE_AUDIO_HASH", strict_json_text(duplicates))
    if mapping_summary.get("ambiguous", 0):
        add(
            "MAPPING_AMBIGUOUS",
            f"{mapping_summary['ambiguous']} plan rows have ambiguous exact matches.",
        )
    return errors


def create_inventory(
    pc_directory: Path | str,
    phone_directory: Path | str,
    plan_path: Path | str,
    relative_root: Path | str,
    *,
    session_id: str = "SESSION001",
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    pc_files = discover_recordings(pc_directory, "pc")
    phone_files = discover_recordings(phone_directory, "phone")
    plan_rows = load_collection_plan(plan_path)
    pair_summary = validate_device_pairs(plan_rows)
    rows = [
        inspect_recording(path, "pc", relative_root) for path in pc_files
    ] + [
        inspect_recording(path, "phone", relative_root) for path in phone_files
    ]
    mapping_rows, mapping_summary = build_mapping_rows(plan_rows, rows)
    errors = validate_inventory(rows, len(pc_files), len(phone_files), mapping_summary)
    report = {
        "schema_version": "1.0",
        "description": (
            "SHA-256 baseline and read-only metadata inventory. Mapping uses exact "
            "expected filenames only and never infers identity from order or time."
        ),
        "session_id": session_id,
        "total_files": len(rows),
        "pc_files": len(pc_files),
        "phone_files": len(phone_files),
        "files": rows,
        "validation_summary": {
            "empty_file_count": sum(row["file_size_bytes"] == 0 for row in rows),
            "unreadable_file_count": sum(not row["readable"] for row in rows),
            "unsupported_format_count": sum(
                "UNSUPPORTED_AUDIO_FORMAT" in row["inspection_warnings"] for row in rows
            ),
            "non_positive_duration_count": sum(
                row["duration_sec"] is None or row["duration_sec"] <= 0 for row in rows
            ),
            "duplicate_sha256_count": sum(
                count - 1 for count in Counter(row["sha256"] for row in rows).values() if count > 1
            ),
            "errors": errors,
        },
        "mapping_summary": mapping_summary,
        "device_pair_summary": pair_summary,
        "device_format_summary": {
            "pc": _device_summary([row for row in rows if row["source_device_group"] == "pc"]),
            "phone": _device_summary(
                [row for row in rows if row["source_device_group"] == "phone"]
            ),
        },
        "warnings": [
            "Inventory metadata and hashes only; no STT, conversion, quality metrics, or prosody analysis was run.",
            "Non-WAV files are marked as requiring a future separate analysis-WAV conversion; originals must remain unchanged.",
        ],
        "error": errors[0] if errors else None,
    }
    return report, rows, mapping_rows


def _atomic_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                formatted = {field: row.get(field, "") for field in fields}
                if isinstance(formatted.get("inspection_warnings"), list):
                    formatted["inspection_warnings"] = ";".join(
                        formatted["inspection_warnings"]
                    )
                writer.writerow(formatted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RecordingInventoryError(
            "INVENTORY_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
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
        raise RecordingInventoryError(
            "INVENTORY_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def write_inventory_outputs(
    json_path: Path | str,
    csv_path: Path | str,
    mapping_path: Path | str,
    report: dict[str, Any],
    inventory_rows: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
) -> None:
    destinations = [
        Path(json_path).resolve(),
        Path(csv_path).resolve(),
        Path(mapping_path).resolve(),
    ]
    if len(set(destinations)) != 3:
        raise RecordingInventoryError(
            "INVENTORY_WRITE_FAILED", "Output paths must be distinct."
        )
    _atomic_json(Path(json_path), report)
    _atomic_csv(Path(csv_path), inventory_rows, INVENTORY_FIELDS)
    _atomic_csv(Path(mapping_path), mapping_rows, MAPPING_FIELDS)


def run_inventory(
    pc_directory: Path | str,
    phone_directory: Path | str,
    plan_path: Path | str,
    relative_root: Path | str,
    json_path: Path | str,
    csv_path: Path | str,
    mapping_path: Path | str,
    *,
    session_id: str = "SESSION001",
) -> dict[str, Any]:
    report, rows, mapping_rows = create_inventory(
        pc_directory,
        phone_directory,
        plan_path,
        relative_root,
        session_id=session_id,
    )
    write_inventory_outputs(
        json_path, csv_path, mapping_path, report, rows, mapping_rows
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pc-dir", required=True, type=Path)
    parser.add_argument("--phone-dir", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--relative-root", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--mapping-output", required=True, type=Path)
    parser.add_argument("--session-id", default="SESSION001")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        report = run_inventory(
            args.pc_dir,
            args.phone_dir,
            args.plan,
            args.relative_root,
            args.output_json,
            args.output_csv,
            args.mapping_output,
            session_id=args.session_id,
        )
    except RecordingInventoryError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "RECORDING_INVENTORY_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(
        strict_json_text(
            {
                "total_files": report["total_files"],
                "pc_files": report["pc_files"],
                "phone_files": report["phone_files"],
                "mapping_summary": report["mapping_summary"],
                "device_pair_summary": report["device_pair_summary"],
                "error": report["error"],
            }
        )
    )
    return 1 if report["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
