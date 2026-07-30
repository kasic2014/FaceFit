"""Evaluate clean scripted STT and compare paired PC/phone transcriptions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

from transcribe_prosody_session import normalize_korean_text, strict_json_text


EVALUATION_FIELDS = (
    "sample_id",
    "device_code",
    "script_id",
    "recording_condition",
    "reference_status",
    "reference_text_raw",
    "reference_text_normalized",
    "hypothesis_text_raw",
    "hypothesis_text_normalized",
    "reference_character_count",
    "hypothesis_character_count",
    "character_substitutions",
    "character_deletions",
    "character_insertions",
    "cer",
    "reference_eojeol_count",
    "hypothesis_eojeol_count",
    "eojeol_substitutions",
    "eojeol_deletions",
    "eojeol_insertions",
    "eojeol_error_rate",
    "warnings",
    "error",
)
PAIR_FIELDS = (
    "capture_pair_key",
    "speaker_code",
    "session_id",
    "script_id",
    "recording_condition",
    "repetition_index",
    "pc_sample_id",
    "phone_sample_id",
    "pc_text_raw",
    "phone_text_raw",
    "pc_text_normalized",
    "phone_text_normalized",
    "exact_normalized_match",
    "pair_character_error_rate",
    "pair_eojeol_error_rate",
    "pc_word_count",
    "phone_word_count",
    "word_count_difference",
    "pc_audio_duration_sec",
    "phone_audio_duration_sec",
    "audio_duration_difference_sec",
    "pc_processing_time_sec",
    "phone_processing_time_sec",
    "pc_real_time_factor",
    "phone_real_time_factor",
    "warnings",
)


class SttEvaluationError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def edit_operations(
    reference: Sequence[Any], hypothesis: Sequence[Any]
) -> dict[str, int]:
    rows = len(reference) + 1
    columns = len(hypothesis) + 1
    matrix: list[list[tuple[int, int, int, int]]] = [
        [(0, 0, 0, 0) for _ in range(columns)] for _ in range(rows)
    ]
    for row in range(1, rows):
        matrix[row][0] = (row, 0, row, 0)
    for column in range(1, columns):
        matrix[0][column] = (column, 0, 0, column)
    for row in range(1, rows):
        for column in range(1, columns):
            if reference[row - 1] == hypothesis[column - 1]:
                matrix[row][column] = matrix[row - 1][column - 1]
                continue
            substitution = matrix[row - 1][column - 1]
            deletion = matrix[row - 1][column]
            insertion = matrix[row][column - 1]
            candidates = [
                (
                    substitution[0] + 1,
                    substitution[1] + 1,
                    substitution[2],
                    substitution[3],
                ),
                (
                    deletion[0] + 1,
                    deletion[1],
                    deletion[2] + 1,
                    deletion[3],
                ),
                (
                    insertion[0] + 1,
                    insertion[1],
                    insertion[2],
                    insertion[3] + 1,
                ),
            ]
            matrix[row][column] = min(
                candidates,
                key=lambda item: (item[0], item[1], item[2], item[3]),
            )
    distance, substitutions, deletions, insertions = matrix[-1][-1]
    return {
        "distance": distance,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
    }


def evaluate_text(reference_raw: str, hypothesis_raw: str) -> dict[str, Any]:
    reference_normalized = normalize_korean_text(reference_raw)
    hypothesis_normalized = normalize_korean_text(hypothesis_raw)
    reference_characters = reference_normalized.replace(" ", "")
    hypothesis_characters = hypothesis_normalized.replace(" ", "")
    character_ops = edit_operations(reference_characters, hypothesis_characters)
    reference_eojeol = reference_normalized.split()
    hypothesis_eojeol = hypothesis_normalized.split()
    eojeol_ops = edit_operations(reference_eojeol, hypothesis_eojeol)
    return {
        "reference_text_raw": reference_raw,
        "reference_text_normalized": reference_normalized,
        "hypothesis_text_raw": hypothesis_raw,
        "hypothesis_text_normalized": hypothesis_normalized,
        "reference_character_count": len(reference_characters),
        "hypothesis_character_count": len(hypothesis_characters),
        "character_substitutions": character_ops["substitutions"],
        "character_deletions": character_ops["deletions"],
        "character_insertions": character_ops["insertions"],
        "cer": (
            character_ops["distance"] / len(reference_characters)
            if reference_characters
            else (0.0 if not hypothesis_characters else 1.0)
        ),
        "reference_eojeol_count": len(reference_eojeol),
        "hypothesis_eojeol_count": len(hypothesis_eojeol),
        "eojeol_substitutions": eojeol_ops["substitutions"],
        "eojeol_deletions": eojeol_ops["deletions"],
        "eojeol_insertions": eojeol_ops["insertions"],
        "eojeol_error_rate": (
            eojeol_ops["distance"] / len(reference_eojeol)
            if reference_eojeol
            else (0.0 if not hypothesis_eojeol else 1.0)
        ),
    }


def load_references(path: Path | str) -> dict[str, str]:
    source = Path(path)
    if not source.is_file():
        raise SttEvaluationError(
            "SCRIPT_REFERENCE_NOT_FOUND", str(source)
        )
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SttEvaluationError(
            "SCRIPT_REFERENCE_NOT_FOUND", f"{type(exc).__name__}: {exc}"
        ) from exc
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict) or set(scripts) != {"SCRIPT001", "SCRIPT002"}:
        raise SttEvaluationError(
            "SCRIPT_REFERENCE_NOT_FOUND",
            "References must contain SCRIPT001 and SCRIPT002.",
        )
    return {key: str(value) for key, value in scripts.items()}


def _median_mad(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    median = statistics.median(values)
    return median, statistics.median(abs(value - median) for value in values)


def _load_batch_results(
    batch_manifest_path: Path | str, relative_root: Path | str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        batch = json.loads(Path(batch_manifest_path).read_text(encoding="utf-8"))
        rows = batch["files"]
        if len(rows) != 24:
            raise ValueError("Expected 24 batch rows.")
        results = [
            json.loads(
                (Path(relative_root) / Path(row["output_json"])).read_text(
                    encoding="utf-8"
                )
            )
            for row in rows
        ]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SttEvaluationError(
            "STT_EVALUATION_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    return batch, results


def build_evaluation_rows(
    results: list[dict[str, Any]], references: dict[str, str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    null_metrics = {
        "reference_text_raw": "",
        "reference_text_normalized": "",
        "hypothesis_text_raw": "",
        "hypothesis_text_normalized": "",
        "reference_character_count": None,
        "hypothesis_character_count": None,
        "character_substitutions": None,
        "character_deletions": None,
        "character_insertions": None,
        "cer": None,
        "reference_eojeol_count": None,
        "hypothesis_eojeol_count": None,
        "eojeol_substitutions": None,
        "eojeol_deletions": None,
        "eojeol_insertions": None,
        "eojeol_error_rate": None,
    }
    for result in results:
        row = {
            "sample_id": result["sample_id"],
            "device_code": result["device_code"],
            "script_id": result["script_id"],
            "recording_condition": result["recording_condition"],
            "warnings": list(result.get("warnings", [])),
            "error": result.get("error"),
        }
        if result.get("error") is not None:
            row.update(null_metrics)
            row["reference_status"] = "stt_failed"
        elif result["recording_condition"] == "natural":
            row.update(null_metrics)
            row["hypothesis_text_raw"] = result["transcription_text_raw"]
            row["hypothesis_text_normalized"] = result[
                "transcription_text_normalized"
            ]
            row["hypothesis_character_count"] = len(
                row["hypothesis_text_normalized"].replace(" ", "")
            )
            row["hypothesis_eojeol_count"] = len(
                row["hypothesis_text_normalized"].split()
            )
            row["reference_status"] = "requires_manual_transcript"
        else:
            row.update(
                evaluate_text(
                    references[result["script_id"]],
                    result["transcription_text_raw"],
                )
            )
            row["reference_status"] = "fixed_script_reference"
        rows.append(row)
    return rows


def _symmetric_error_rate(first: Sequence[Any], second: Sequence[Any]) -> float:
    denominator = max(len(first), len(second))
    if denominator == 0:
        return 0.0
    return edit_operations(first, second)["distance"] / denominator


def build_pair_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[result["capture_pair_key"]].append(result)
    rows: list[dict[str, Any]] = []
    for key, pair in sorted(groups.items()):
        by_device = {item["device_code"]: item for item in pair}
        pc = by_device.get("DEV_PC_MIC_01")
        phone = by_device.get("DEV_PHONE_01")
        if len(pair) != 2 or pc is None or phone is None:
            raise SttEvaluationError(
                "DEVICE_PAIR_INCOMPLETE", key
            )
        pc_normalized = pc["transcription_text_normalized"]
        phone_normalized = phone["transcription_text_normalized"]
        warnings = list(pc.get("warnings", [])) + list(
            phone.get("warnings", [])
        )
        if pc.get("error") or phone.get("error"):
            warnings.append("PAIR_CONTAINS_FAILED_STT")
        rows.append(
            {
                "capture_pair_key": key,
                "speaker_code": pc["speaker_code"],
                "session_id": pc["session_id"],
                "script_id": pc["script_id"],
                "recording_condition": pc["recording_condition"],
                "repetition_index": pc["repetition_index"],
                "pc_sample_id": pc["sample_id"],
                "phone_sample_id": phone["sample_id"],
                "pc_text_raw": pc["transcription_text_raw"],
                "phone_text_raw": phone["transcription_text_raw"],
                "pc_text_normalized": pc_normalized,
                "phone_text_normalized": phone_normalized,
                "exact_normalized_match": pc_normalized == phone_normalized,
                "pair_character_error_rate": _symmetric_error_rate(
                    pc_normalized.replace(" ", ""),
                    phone_normalized.replace(" ", ""),
                ),
                "pair_eojeol_error_rate": _symmetric_error_rate(
                    pc_normalized.split(), phone_normalized.split()
                ),
                "pc_word_count": pc["word_count"],
                "phone_word_count": phone["word_count"],
                "word_count_difference": abs(
                    pc["word_count"] - phone["word_count"]
                ),
                "pc_audio_duration_sec": pc["audio_duration_sec"],
                "phone_audio_duration_sec": phone["audio_duration_sec"],
                "audio_duration_difference_sec": abs(
                    pc["audio_duration_sec"] - phone["audio_duration_sec"]
                ),
                "pc_processing_time_sec": pc["processing_time_sec"],
                "phone_processing_time_sec": phone["processing_time_sec"],
                "pc_real_time_factor": pc["real_time_factor"],
                "phone_real_time_factor": phone["real_time_factor"],
                "warnings": warnings,
            }
        )
    if len(rows) != 12:
        raise SttEvaluationError(
            "DEVICE_PAIR_INCOMPLETE", f"Expected 12 pairs, found {len(rows)}."
        )
    return rows


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
    except (OSError, ValueError, TypeError) as exc:
        temporary.unlink(missing_ok=True)
        raise SttEvaluationError(
            "STT_RESULT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _atomic_csv(
    path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]
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
                if isinstance(formatted.get("error"), dict):
                    formatted["error"] = json.dumps(
                        formatted["error"], ensure_ascii=False
                    )
                writer.writerow(formatted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        temporary.unlink(missing_ok=True)
        raise SttEvaluationError(
            "STT_RESULT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def evaluate_session(
    batch_manifest_path: Path | str,
    references_path: Path | str,
    relative_root: Path | str,
    evaluation_json_path: Path | str,
    evaluation_csv_path: Path | str,
    pair_csv_path: Path | str,
) -> dict[str, Any]:
    batch, results = _load_batch_results(batch_manifest_path, relative_root)
    references = load_references(references_path)
    evaluation_rows = build_evaluation_rows(results, references)
    pair_rows = build_pair_rows(results)
    clean = [
        row
        for row in evaluation_rows
        if row["reference_status"] == "fixed_script_reference"
    ]
    cer_values = [float(row["cer"]) for row in clean]
    eojeol_values = [float(row["eojeol_error_rate"]) for row in clean]
    cer_median, cer_mad = _median_mad(cer_values)
    eojeol_median, eojeol_mad = _median_mad(eojeol_values)
    device_clean: dict[str, Any] = {}
    for device in ("DEV_PC_MIC_01", "DEV_PHONE_01"):
        device_rows = [row for row in clean if row["device_code"] == device]
        device_clean[device] = {
            "file_count": len(device_rows),
            "cer_median": statistics.median(
                float(row["cer"]) for row in device_rows
            ),
            "eojeol_error_rate_median": statistics.median(
                float(row["eojeol_error_rate"]) for row in device_rows
            ),
        }
    pair_cer = [float(row["pair_character_error_rate"]) for row in pair_rows]
    pair_eojeol = [
        float(row["pair_eojeol_error_rate"]) for row in pair_rows
    ]
    summary = {
        **batch["summary"],
        "evaluated_clean_files": len(clean),
        "clean_cer_median": cer_median,
        "clean_cer_mad": cer_mad,
        "clean_eojeol_error_rate_median": eojeol_median,
        "clean_eojeol_error_rate_mad": eojeol_mad,
        "clean_exact_match_count": sum(
            row["cer"] == 0 and row["eojeol_error_rate"] == 0 for row in clean
        ),
        "clean_by_device": device_clean,
        "natural_requires_manual_transcript_count": sum(
            row["reference_status"] == "requires_manual_transcript"
            for row in evaluation_rows
        ),
        "total_pairs": len(pair_rows),
        "valid_pairs": sum(
            "PAIR_CONTAINS_FAILED_STT" not in row["warnings"]
            for row in pair_rows
        ),
        "exact_normalized_match_pairs": sum(
            row["exact_normalized_match"] for row in pair_rows
        ),
        "pair_cer_median": statistics.median(pair_cer),
        "pair_eojeol_error_rate_median": statistics.median(pair_eojeol),
        "device_pair_warning_count": sum(bool(row["warnings"]) for row in pair_rows),
    }
    payload = {
        "schema_version": "1.0",
        "session_id": "SESSION001",
        "summary": summary,
        "evaluations": evaluation_rows,
        "device_pairs": pair_rows,
        "interpretation": {
            "pilot_scope": "SPK001 한 명과 두 스크립트에 대한 내부 파일럿이다.",
            "clean_ground_truth": "clean 조건만 고정 스크립트 기반 정답 평가를 한다.",
            "natural_ground_truth": "natural 조건은 사람 전사 전까지 정확도 평가 대상이 아니다.",
            "pair_metric": "PC와 휴대폰 pair 오류율은 어느 장치가 정답인지 나타내지 않는 대칭적 장치 출력 일관성 지표다.",
            "generalization": "전체 사용자 또는 모든 한국어 음성에 일반화하지 않는다.",
        },
        "error": None,
    }
    _atomic_json(Path(evaluation_json_path), payload)
    _atomic_csv(Path(evaluation_csv_path), evaluation_rows, EVALUATION_FIELDS)
    _atomic_csv(Path(pair_csv_path), pair_rows, PAIR_FIELDS)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-manifest", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    parser.add_argument("--evaluation-json-output", type=Path, required=True)
    parser.add_argument("--evaluation-csv-output", type=Path, required=True)
    parser.add_argument("--pair-csv-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_session(
            args.batch_manifest,
            args.references,
            args.relative_root,
            args.evaluation_json_output,
            args.evaluation_csv_output,
            args.pair_csv_output,
        )
    except SttEvaluationError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "STT_EVALUATION_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(strict_json_text({"summary": result["summary"], "error": None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
