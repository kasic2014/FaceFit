"""Interactively review Face-Fit speech clips from a Windows terminal."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

LABEL_KEYS = {
    "1": "filler",
    "2": "normal_speech",
    "3": "breath",
    "4": "noise",
    "5": "silence",
    "6": "whisper_hallucination",
    "7": "unknown",
}
ALLOWED_COMMANDS = {"r", "s", "b", "q", "h"}
REQUIRED_COLUMNS = {"review_id", "clip_file", "reviewer_label", "reviewer_note"}
DISPLAY_FIELDS = [
    "review_id",
    "event_type",
    "source_event_types",
    "clip_file",
    "original_start_sec",
    "original_end_sec",
    "previous_word",
    "next_word",
    "classification",
    "candidate_reasons",
    "audio_quality_flags",
    "reviewer_label",
    "reviewer_note",
]

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]
OpenFunction = Callable[[str], Any]


class ClipReviewError(Exception):
    """A classified manifest review failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _base_result(manifest_path: Path | str) -> dict[str, Any]:
    return {
        "success": False,
        "manifest_path": str(manifest_path),
        "total_items": 0,
        "reviewed_items": 0,
        "unreviewed_items": 0,
        "newly_reviewed_items": 0,
        "modified_items": 0,
        "label_counts": {label: 0 for label in LABEL_KEYS.values()},
        "backup_path": None,
        "interrupted": False,
        "warnings": [],
        "error": None,
    }


def read_manifest(path: Path | str) -> tuple[list[str], list[dict[str, str]]]:
    """Read a BOM or non-BOM UTF-8 review manifest."""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ClipReviewError("MANIFEST_FILE_NOT_FOUND", str(manifest_path))
    try:
        with manifest_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ClipReviewError("MANIFEST_READ_FAILED", "CSV header is missing.")
            fieldnames = list(reader.fieldnames)
            missing = sorted(REQUIRED_COLUMNS - set(fieldnames))
            if missing:
                raise ClipReviewError(
                    "REQUIRED_COLUMNS_MISSING", "Missing columns: " + ", ".join(missing)
                )
            return fieldnames, [
                {name: row.get(name, "") or "" for name in fieldnames} for row in reader
            ]
    except ClipReviewError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ClipReviewError("MANIFEST_READ_FAILED", f"{type(exc).__name__}: {exc}") from exc


def write_manifest(path: Path | str, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Atomically rewrite the full CSV while preserving its original columns."""
    manifest_path = Path(path)
    temporary_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=fieldnames,
                extrasaction="ignore",
                lineterminator="\r\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(manifest_path)
    except (OSError, csv.Error) as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ClipReviewError("MANIFEST_WRITE_FAILED", f"{type(exc).__name__}: {exc}") from exc


def create_backup(
    path: Path | str, now: Callable[[], datetime] = datetime.now
) -> Path:
    """Create a timestamped backup without replacing an existing backup."""
    manifest_path = Path(path)
    timestamp = now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{manifest_path.stem}.backup_{timestamp}"
    candidate = manifest_path.with_name(base_name + manifest_path.suffix)
    sequence = 1
    while candidate.exists():
        candidate = manifest_path.with_name(f"{base_name}_{sequence}{manifest_path.suffix}")
        sequence += 1
    try:
        shutil.copy2(manifest_path, candidate)
    except OSError as exc:
        raise ClipReviewError("MANIFEST_WRITE_FAILED", f"{type(exc).__name__}: {exc}") from exc
    return candidate


def _inside(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def resolve_clip_path(
    row: dict[str, str], manifest_path: Path | str, workspace_root: Path = WORKSPACE_ROOT
) -> Path | None:
    """Resolve a clip only within the manifest directory or workspace."""
    clip_value = row.get("clip_file", "").strip()
    if not clip_value:
        return None
    manifest_directory = Path(manifest_path).resolve().parent
    workspace = workspace_root.resolve()
    clip_path = Path(clip_value)
    allowed_bases = [manifest_directory, workspace]

    if clip_path.is_absolute():
        resolved = clip_path.resolve()
        return resolved if any(_inside(resolved, base) for base in allowed_bases) else None

    candidates = [manifest_directory / clip_path, workspace / clip_path]
    source_audio = row.get("source_audio", "").strip()
    if source_audio:
        candidates.insert(1, manifest_directory / Path(source_audio).stem / clip_path)
    for candidate in candidates:
        resolved = candidate.resolve()
        if any(_inside(resolved, base) for base in allowed_bases) and resolved.is_file():
            return resolved
    return None


def open_clip(
    clip_path: Path | None,
    *,
    no_open: bool,
    open_function: OpenFunction | None = None,
) -> tuple[bool, dict[str, str] | None]:
    """Open a clip in the Windows default application or return a warning."""
    if clip_path is None or not clip_path.is_file():
        return False, {
            "code": "CLIP_FILE_NOT_FOUND",
            "detail": "The review clip could not be resolved or does not exist.",
        }
    if no_open:
        return False, None
    opener = open_function or getattr(os, "startfile", None)
    if opener is None:
        return False, {
            "code": "AUDIO_OPEN_FAILED",
            "detail": "os.startfile is unavailable on this platform.",
        }
    try:
        opener(str(clip_path))
    except OSError as exc:
        return False, {
            "code": "AUDIO_OPEN_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return True, None


def _display_item(
    row: dict[str, str], position: int, count: int, output: OutputFunction
) -> None:
    output("")
    output("=" * 72)
    output(f"현재 진행: {position}/{count}")
    for field in DISPLAY_FIELDS:
        output(f"{field}: {row.get(field, '')}")
    output("=" * 72)


def _display_help(output: OutputFunction) -> None:
    output("라벨: 1 filler | 2 normal_speech | 3 breath | 4 noise")
    output("      5 silence | 6 whisper_hallucination | 7 unknown")
    output("명령: r 다시 재생 | s 건너뛰기 | b 이전 | q 저장 후 종료 | h 도움말")


def _summary(rows: list[dict[str, str]], result: dict[str, Any]) -> None:
    labels = [row.get("reviewer_label", "").strip() for row in rows]
    counts = Counter(label for label in labels if label in LABEL_KEYS.values())
    result["total_items"] = len(rows)
    result["reviewed_items"] = sum(label in LABEL_KEYS.values() for label in labels)
    result["unreviewed_items"] = len(rows) - result["reviewed_items"]
    result["label_counts"] = {label: counts.get(label, 0) for label in LABEL_KEYS.values()}


def _print_summary(result: dict[str, Any], output: OutputFunction) -> None:
    output("")
    output("검수 요약")
    for key in [
        "total_items",
        "reviewed_items",
        "unreviewed_items",
        "newly_reviewed_items",
        "modified_items",
    ]:
        output(f"{key}: {result[key]}")
    output("label_counts: " + json.dumps(result["label_counts"], ensure_ascii=False))
    output(f"manifest_path: {result['manifest_path']}")


def review_speech_clips(
    manifest_path: Path | str,
    *,
    start_from: str | None = None,
    include_reviewed: bool = False,
    no_open: bool = False,
    backup: bool = False,
    input_function: InputFunction = input,
    output_function: OutputFunction = print,
    open_function: OpenFunction | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
    now: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    """Run the interactive review loop and save each completed item immediately."""
    path = Path(manifest_path)
    result = _base_result(path)
    try:
        fieldnames, rows = read_manifest(path)
        initial_labels = [row.get("reviewer_label", "").strip() for row in rows]
        if backup:
            result["backup_path"] = str(create_backup(path, now))

        start_index = 0
        if start_from is not None:
            matches = [index for index, row in enumerate(rows) if row.get("review_id") == start_from]
            if not matches:
                raise ClipReviewError("REVIEW_FAILED", f"Unknown review_id: {start_from}")
            start_index = matches[0]

        selected_indices = [
            index
            for index, row in enumerate(rows)
            if index >= start_index
            and (include_reviewed or not row.get("reviewer_label", "").strip())
        ]
        if not selected_indices:
            _summary(rows, result)
            result["success"] = True
            output_function("검수할 항목이 없습니다.")
            _print_summary(result, output_function)
            return result

        cursor = 0
        while cursor < len(selected_indices):
            row_index = selected_indices[cursor]
            row = rows[row_index]
            _display_item(row, cursor + 1, len(selected_indices), output_function)
            clip_path = resolve_clip_path(row, path, workspace_root)
            _, warning = open_clip(
                clip_path, no_open=no_open, open_function=open_function
            )
            if warning:
                warning = {**warning, "review_id": row.get("review_id", "")}
                result["warnings"].append(warning)
                output_function(f"WARNING {warning['code']}: {warning['detail']}")

            if include_reviewed and row.get("reviewer_label", "").strip():
                answer = input_function("기존 검수 값을 변경하시겠습니까? [y/N]: ").strip().lower()
                if answer not in {"y", "yes"}:
                    cursor += 1
                    continue

            while True:
                choice = input_function("라벨 번호 또는 명령(h 도움말): ").strip().lower()
                if choice in LABEL_KEYS:
                    old_label = row.get("reviewer_label", "").strip()
                    old_note = row.get("reviewer_note", "")
                    note = input_function(
                        "메모(빈 입력 시 기존 메모 유지): "
                    )
                    row["reviewer_label"] = LABEL_KEYS[choice]
                    row["reviewer_note"] = old_note if note == "" else note
                    write_manifest(path, fieldnames, rows)
                    if initial_labels[row_index]:
                        if row["reviewer_label"] != old_label or row["reviewer_note"] != old_note:
                            result["modified_items"] += 1
                    else:
                        result["newly_reviewed_items"] += 1
                        initial_labels[row_index] = row["reviewer_label"]
                    output_function("저장했습니다.")
                    cursor += 1
                    break
                if choice == "r":
                    _, replay_warning = open_clip(
                        clip_path, no_open=no_open, open_function=open_function
                    )
                    if replay_warning:
                        replay_warning = {
                            **replay_warning,
                            "review_id": row.get("review_id", ""),
                        }
                        result["warnings"].append(replay_warning)
                        output_function(
                            f"WARNING {replay_warning['code']}: {replay_warning['detail']}"
                        )
                    continue
                if choice == "s":
                    cursor += 1
                    break
                if choice == "b":
                    cursor = max(0, cursor - 1)
                    break
                if choice == "q":
                    cursor = len(selected_indices)
                    break
                if choice == "h":
                    _display_help(output_function)
                    continue
                output_function("잘못된 입력입니다. 1~7 또는 r/s/b/q/h를 입력하세요.")

        _summary(rows, result)
        result["success"] = True
        _print_summary(result, output_function)
    except KeyboardInterrupt:
        result["interrupted"] = True
        result["success"] = True
        try:
            _summary(rows, result)
        except UnboundLocalError:
            pass
        output_function("검수가 중단되었습니다. 이전에 완료된 항목은 저장되어 있습니다.")
        _print_summary(result, output_function)
    except ClipReviewError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
    except Exception as exc:  # defensive CLI boundary
        result["error"] = {
            "code": "REVIEW_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewed_manifest_csv", type=Path)
    parser.add_argument("--start-from")
    parser.add_argument("--include-reviewed", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--backup", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = review_speech_clips(
        args.reviewed_manifest_csv,
        start_from=args.start_from,
        include_reviewed=args.include_reviewed,
        no_open=args.no_open,
        backup=args.backup,
    )
    if result["error"] is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
