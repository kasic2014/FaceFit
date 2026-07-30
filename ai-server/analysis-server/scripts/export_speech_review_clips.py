"""Export detected speech-metric events as WAV clips for human review.

The tool performs no scoring or automatic label assignment. Reviewers may use
these labels: filler, normal_speech, breath, noise, silence,
whisper_hallucination, and unknown.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import wave
from pathlib import Path
from typing import Any, Iterable


SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1
DEFAULT_PADDING_SEC = 0.30
MERGE_OVERLAP_RATIO = 0.90
MERGE_BOUNDARY_TOLERANCE_SEC = 0.05

REVIEWER_LABEL_VALUES = [
    "filler",
    "normal_speech",
    "breath",
    "noise",
    "silence",
    "whisper_hallucination",
    "unknown",
]

EVENT_SPECS = [
    ("probable_omitted_vocalizations", "probable_omitted_vocalization"),
    ("uncertain_gap_vocalizations", "uncertain_gap_vocalization"),
    ("hallucination_candidates", "hallucination_candidate"),
    ("pauses", "pause"),
    ("long_silences", "long_silence"),
]
EVENT_ORDER = {event_type: index for index, (_, event_type) in enumerate(EVENT_SPECS)}
MERGE_PROTECTED_TYPES = {"hallucination_candidate", "long_silence"}

CSV_FIELDS = [
    "review_id",
    "source_audio",
    "source_metrics",
    "clip_file",
    "event_type",
    "source_event_types",
    "merged",
    "original_start_sec",
    "original_end_sec",
    "original_duration_sec",
    "clip_start_sec",
    "clip_end_sec",
    "classification",
    "confidence_or_probability",
    "candidate_reasons",
    "previous_word",
    "next_word",
    "mean_dbfs",
    "voiced_frame_ratio",
    "local_energy_contrast_db",
    "audio_quality_flags",
    "reviewer_label",
    "reviewer_note",
]


class ReviewExportError(Exception):
    """A classified review-export failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _error(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _warning(code: str, detail: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "detail": detail, **context}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _event_times(event_type: str, event: dict[str, Any]) -> tuple[float, float] | None:
    if event_type == "hallucination_candidate":
        pairs = [("start_sec", "end_sec")]
    else:
        pairs = [
            ("stt_gap_start_sec", "stt_gap_end_sec"),
            ("start_sec", "end_sec"),
            ("original_start_sec", "original_end_sec"),
        ]
    for start_key, end_key in pairs:
        start = _finite_number(event.get(start_key))
        end = _finite_number(event.get(end_key))
        if start is not None and end is not None:
            return start, end
    return None


def _as_text_list(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return ""


def _event_row(
    event_type: str,
    event: dict[str, Any],
    start: float,
    end: float,
    source_audio: Path,
    source_metrics: Path,
    audio_quality_flags: str,
) -> dict[str, Any]:
    acoustic = event.get("acoustic") if isinstance(event.get("acoustic"), dict) else {}
    contrast = (
        event.get("local_energy_contrast")
        if isinstance(event.get("local_energy_contrast"), dict)
        else {}
    )
    candidate_acoustic = (
        contrast.get("candidate_acoustic")
        if isinstance(contrast.get("candidate_acoustic"), dict)
        else {}
    )
    reasons = _first_value(
        event.get("reasons"),
        event.get("matched_conditions"),
        event.get("exclusion_reasons"),
    )
    return {
        "review_id": "",
        "source_audio": str(source_audio),
        "source_metrics": str(source_metrics),
        "clip_file": "",
        "event_type": event_type,
        "source_event_types": event_type,
        "merged": False,
        "original_start_sec": round(start, 6),
        "original_end_sec": round(end, 6),
        "original_duration_sec": round(end - start, 6),
        "clip_start_sec": "",
        "clip_end_sec": "",
        "classification": _first_value(event.get("classification"), event.get("candidate_type")),
        "confidence_or_probability": _first_value(event.get("probability"), event.get("confidence")),
        "candidate_reasons": _as_text_list(reasons),
        "previous_word": str(event.get("previous_word", "")),
        "next_word": str(event.get("next_word", "")),
        "mean_dbfs": _first_value(
            candidate_acoustic.get("dbfs"),
            contrast.get("candidate_mean_dbfs"),
            acoustic.get("dbfs"),
        ),
        "voiced_frame_ratio": _first_value(
            candidate_acoustic.get("voiced_frame_ratio"),
            acoustic.get("voiced_frame_ratio"),
        ),
        "local_energy_contrast_db": _first_value(contrast.get("surrounding_energy_contrast_db")),
        "audio_quality_flags": audio_quality_flags,
        "reviewer_label": "",
        "reviewer_note": "",
    }


def collect_review_events(
    metrics: dict[str, Any], source_audio: Path, source_metrics: Path, audio_duration_sec: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize supported metrics arrays and skip only invalid events."""
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    quality = metrics.get("audio_quality") if isinstance(metrics.get("audio_quality"), dict) else {}
    flags = _as_text_list(quality.get("reliability_flags", []))

    for array_name, event_type in EVENT_SPECS:
        events = metrics.get(array_name, [])
        if events is None:
            events = []
        if not isinstance(events, list):
            warnings.append(
                _warning(
                    "EVENT_TIMESTAMP_INVALID",
                    f"{array_name} is not an array and was skipped.",
                    event_type=event_type,
                )
            )
            continue
        for event_index, event in enumerate(events):
            if not isinstance(event, dict):
                warnings.append(
                    _warning(
                        "EVENT_TIMESTAMP_INVALID",
                        "Event is not an object and was skipped.",
                        event_type=event_type,
                        event_index=event_index,
                    )
                )
                continue
            times = _event_times(event_type, event)
            if times is None:
                warnings.append(
                    _warning(
                        "EVENT_TIMESTAMP_INVALID",
                        "Event start/end timestamps are missing or non-finite.",
                        event_type=event_type,
                        event_index=event_index,
                    )
                )
                continue
            start, end = times
            if start < 0 or end <= start or start >= audio_duration_sec or end <= 0:
                warnings.append(
                    _warning(
                        "EVENT_TIMESTAMP_INVALID",
                        f"Invalid event interval: {start} to {end} seconds.",
                        event_type=event_type,
                        event_index=event_index,
                    )
                )
                continue
            rows.append(_event_row(event_type, event, start, end, source_audio, source_metrics, flags))

    rows.sort(
        key=lambda row: (
            float(row["original_start_sec"]),
            float(row["original_end_sec"]),
            EVENT_ORDER[row["event_type"]],
        )
    )
    return rows, warnings


def _overlap_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_start = float(first["original_start_sec"])
    first_end = float(first["original_end_sec"])
    second_start = float(second["original_start_sec"])
    second_end = float(second["original_end_sec"])
    overlap = max(0.0, min(first_end, second_end) - max(first_start, second_start))
    shorter_duration = min(first_end - first_start, second_end - second_start)
    return overlap / shorter_duration if shorter_duration > 0 else 0.0


def _can_merge(first: dict[str, Any], second: dict[str, Any]) -> bool:
    if first["event_type"] == second["event_type"]:
        return False
    if first["event_type"] in MERGE_PROTECTED_TYPES or second["event_type"] in MERGE_PROTECTED_TYPES:
        return False
    return (
        _overlap_ratio(first, second) >= MERGE_OVERLAP_RATIO
        and abs(float(first["original_start_sec"]) - float(second["original_start_sec"]))
        <= MERGE_BOUNDARY_TOLERANCE_SEC
        and abs(float(first["original_end_sec"]) - float(second["original_end_sec"]))
        <= MERGE_BOUNDARY_TOLERANCE_SEC
    )


def merge_review_events(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Merge duplicate cross-type events, excluding protected event kinds."""
    merged_rows: list[dict[str, Any]] = []
    merged_count = 0
    for row in rows:
        duplicate_index = next(
            (index for index, existing in enumerate(merged_rows) if _can_merge(existing, row)),
            None,
        )
        if duplicate_index is None:
            merged_rows.append(dict(row))
            continue

        existing = merged_rows[duplicate_index]
        preferred = min(
            (existing, row), key=lambda item: EVENT_ORDER[str(item["event_type"])]
        )
        combined = dict(preferred)
        source_types = {
            *str(existing["source_event_types"]).split("; "),
            *str(row["source_event_types"]).split("; "),
        }
        combined["source_event_types"] = "; ".join(
            sorted(source_types, key=lambda value: EVENT_ORDER[value])
        )
        combined["merged"] = True
        merged_rows[duplicate_index] = combined
        merged_count += 1
    return merged_rows, merged_count


def _read_wav(path: Path) -> tuple[wave._wave_params, bytes]:
    try:
        with wave.open(str(path), "rb") as stream:
            parameters = stream.getparams()
            if (
                parameters.nchannels != CHANNELS
                or parameters.sampwidth != SAMPLE_WIDTH
                or parameters.framerate != SAMPLE_RATE
                or parameters.comptype != "NONE"
            ):
                raise ReviewExportError(
                    "UNSUPPORTED_WAV_FORMAT",
                    "Expected PCM 16-bit, 16000 Hz, mono WAV.",
                )
            return parameters, stream.readframes(parameters.nframes)
    except ReviewExportError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise ReviewExportError("UNSUPPORTED_WAV_FORMAT", f"{type(exc).__name__}: {exc}") from exc


def _write_clip(path: Path, frames: bytes, start_frame: int, end_frame: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        byte_start = start_frame * SAMPLE_WIDTH * CHANNELS
        byte_end = end_frame * SAMPLE_WIDTH * CHANNELS
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(CHANNELS)
            stream.setsampwidth(SAMPLE_WIDTH)
            stream.setframerate(SAMPLE_RATE)
            stream.writeframes(frames[byte_start:byte_end])
    except (OSError, wave.Error) as exc:
        raise ReviewExportError("AUDIO_CLIP_WRITE_FAILED", f"{type(exc).__name__}: {exc}") from exc


def _clip_filename(sequence: int, event_type: str, start: float, end: float) -> str:
    return f"{sequence:03d}_{event_type}_{start:.3f}_{end:.3f}.wav"


def export_review_clips(
    wav_file: Path | str,
    metrics_json: Path | str,
    output_dir: Path | str,
    padding_sec: float = DEFAULT_PADDING_SEC,
) -> dict[str, Any]:
    """Export review clips and return manifest items without writing manifests."""
    wav_path = Path(wav_file)
    metrics_path = Path(metrics_json)
    clip_directory = Path(output_dir)
    result: dict[str, Any] = {
        "success": False,
        "source_audio": str(wav_path),
        "source_metrics": str(metrics_path),
        "output_dir": str(clip_directory),
        "padding_sec": padding_sec,
        "clip_count": 0,
        "event_counts": {event_type: 0 for _, event_type in EVENT_SPECS},
        "merged_event_count": 0,
        "items": [],
        "warnings": [],
        "errors": [],
    }
    if not wav_path.is_file():
        result["errors"].append(_error("AUDIO_FILE_NOT_FOUND", str(wav_path)))
        return result
    if not metrics_path.is_file():
        result["errors"].append(_error("METRICS_FILE_NOT_FOUND", str(metrics_path)))
        return result
    if not math.isfinite(padding_sec) or padding_sec < 0:
        result["errors"].append(_error("REVIEW_EXPORT_FAILED", "padding_sec must be finite and non-negative."))
        return result

    try:
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ReviewExportError("METRICS_JSON_INVALID", f"{type(exc).__name__}: {exc}") from exc
        if not isinstance(metrics, dict):
            raise ReviewExportError("METRICS_JSON_INVALID", "Metrics JSON root must be an object.")
        if metrics.get("error"):
            raise ReviewExportError("METRICS_RESULT_ERROR", str(metrics["error"]))

        parameters, frames = _read_wav(wav_path)
        audio_duration_sec = parameters.nframes / parameters.framerate
        rows, warnings = collect_review_events(metrics, wav_path, metrics_path, audio_duration_sec)
        rows, merged_count = merge_review_events(rows)
        result["warnings"].extend(warnings)
        result["merged_event_count"] = merged_count

        clip_directory.mkdir(parents=True, exist_ok=True)
        for sequence, row in enumerate(rows, start=1):
            original_start = float(row["original_start_sec"])
            original_end = float(row["original_end_sec"])
            start_frame = max(0, math.floor((original_start - padding_sec) * SAMPLE_RATE))
            end_frame = min(parameters.nframes, math.ceil((original_end + padding_sec) * SAMPLE_RATE))
            if end_frame <= start_frame:
                result["warnings"].append(
                    _warning(
                        "EVENT_TIMESTAMP_INVALID",
                        "Padded event interval contains no audio frames and was skipped.",
                        event_type=row["event_type"],
                    )
                )
                continue
            filename = _clip_filename(sequence, str(row["event_type"]), original_start, original_end)
            _write_clip(clip_directory / filename, frames, start_frame, end_frame)
            row["review_id"] = f"{wav_path.stem}_{sequence:03d}"
            row["clip_file"] = filename
            row["clip_start_sec"] = round(start_frame / SAMPLE_RATE, 6)
            row["clip_end_sec"] = round(end_frame / SAMPLE_RATE, 6)
            result["items"].append(row)
            result["event_counts"][row["event_type"]] += 1

        result["clip_count"] = len(result["items"])
        result["success"] = True
    except ReviewExportError as exc:
        result["errors"].append(_error(exc.code, exc.detail))
    except Exception as exc:  # defensive CLI boundary
        result["errors"].append(_error("REVIEW_EXPORT_FAILED", f"{type(exc).__name__}: {exc}"))
    return result


def write_csv_manifest(path: Path | str, items: Iterable[dict[str, Any]]) -> None:
    manifest_path = Path(path)
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(items)
    except (OSError, csv.Error) as exc:
        raise ReviewExportError("MANIFEST_WRITE_FAILED", f"{type(exc).__name__}: {exc}") from exc


def write_json_manifest(
    path: Path | str,
    items: Iterable[dict[str, Any]],
    warnings: Iterable[dict[str, Any]] = (),
) -> None:
    manifest_path = Path(path)
    payload = {
        "manifest_version": 1,
        "description": "Human review manifest. No score or automatic reviewer label is assigned.",
        "reviewer_label_values": REVIEWER_LABEL_VALUES,
        "items": list(items),
        "warnings": list(warnings),
    }
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError) as exc:
        raise ReviewExportError("MANIFEST_WRITE_FAILED", f"{type(exc).__name__}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="reviewer_label values: " + ", ".join(REVIEWER_LABEL_VALUES),
    )
    parser.add_argument("wav_file", type=Path)
    parser.add_argument("metrics_json", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json-manifest", type=Path)
    parser.add_argument("--padding-sec", type=float, default=DEFAULT_PADDING_SEC)
    return parser


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = export_review_clips(
        args.wav_file,
        args.metrics_json,
        args.output_dir,
        args.padding_sec,
    )
    if not result["success"]:
        _print_json(result)
        return 1
    try:
        write_csv_manifest(args.manifest, result["items"])
        if args.json_manifest is not None:
            write_json_manifest(args.json_manifest, result["items"], result["warnings"])
    except ReviewExportError as exc:
        result["success"] = False
        result["errors"].append(_error(exc.code, exc.detail))
        _print_json(result)
        return 1
    result["manifest"] = str(args.manifest)
    result["json_manifest"] = str(args.json_manifest) if args.json_manifest else None
    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
