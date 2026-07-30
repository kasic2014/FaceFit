"""Create an empty human transcript review sheet and current pair diagnostics."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from evaluate_prosody_session_stt import edit_operations, evaluate_text
from transcribe_prosody_session import strict_json_text


REVIEW_FIELDS = (
    "capture_key",
    "speaker_code",
    "session_id",
    "script_id",
    "repetition_index",
    "pc_sample_id",
    "phone_sample_id",
    "pc_audio_file",
    "phone_audio_file",
    "pc_stt_raw",
    "phone_stt_raw",
    "pc_stt_normalized",
    "phone_stt_normalized",
    "pair_exact_match",
    "pair_character_error_rate",
    "pair_eojeol_error_rate",
    "human_transcript",
    "human_transcript_note",
    "review_status",
    "reviewer_confirmed",
)
MISMATCH_FIELDS = (
    "capture_key",
    "script_id",
    "condition",
    "repetition_index",
    "pc_sample_id",
    "phone_sample_id",
    "pc_stt",
    "phone_stt",
    "character_difference",
    "eojeol_difference",
    "reference_status",
    "pc_cer",
    "phone_cer",
    "reference_closeness",
    "clean_pair_classification",
    "same_reference_error_signature",
    "single_device_error",
    "warnings",
)
HUMAN_FIELDS = (
    "human_transcript",
    "human_transcript_note",
    "review_status",
    "reviewer_confirmed",
)


class NaturalReviewError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _load_json(path: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NaturalReviewError(
            "REVIEW_INPUT_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise NaturalReviewError("REVIEW_INPUT_INVALID", str(path))
    return payload


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _existing_human_values(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error, UnicodeError) as exc:
        raise NaturalReviewError(
            "REVIEW_INPUT_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    values: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("capture_key") or "")
        if not key or key in values:
            raise NaturalReviewError(
                "REVIEW_INPUT_INVALID", "Existing capture_key is empty or duplicated."
            )
        values[key] = {
            "human_transcript": row.get("human_transcript", ""),
            "human_transcript_note": row.get("human_transcript_note", ""),
            "review_status": row.get("review_status", "pending"),
            "reviewer_confirmed": _parse_bool(
                row.get("reviewer_confirmed", False)
            ),
        }
    return values


def _load_individual_results(
    batch_manifest_path: Path | str,
    relative_root: Path | str,
    allowed_counts: tuple[int, ...] = (24,),
) -> dict[str, dict[str, Any]]:
    batch = _load_json(batch_manifest_path)
    root = Path(relative_root)
    results: dict[str, dict[str, Any]] = {}
    try:
        for row in batch["files"]:
            result = _load_json(root / Path(row["output_json"]))
            results[result["sample_id"]] = result
    except (KeyError, TypeError) as exc:
        raise NaturalReviewError(
            "REVIEW_INPUT_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    if len(results) not in allowed_counts:
        raise NaturalReviewError(
            "REVIEW_INPUT_INVALID",
            f"Expected STT result count in {allowed_counts}, found {len(results)}.",
        )
    return results


def build_natural_review_rows(
    evaluation: dict[str, Any],
    individual_results: dict[str, dict[str, Any]],
    existing_values: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    existing_values = existing_values or {}
    natural_pairs = [
        row
        for row in evaluation.get("device_pairs", [])
        if row.get("recording_condition") == "natural"
    ]
    rows: list[dict[str, Any]] = []
    for pair in sorted(
        natural_pairs,
        key=lambda row: (row["script_id"], int(row["repetition_index"])),
    ):
        pc = individual_results[pair["pc_sample_id"]]
        phone = individual_results[pair["phone_sample_id"]]
        key = pair["capture_pair_key"]
        human = existing_values.get(
            key,
            {
                "human_transcript": "",
                "human_transcript_note": "",
                "review_status": "pending",
                "reviewer_confirmed": False,
            },
        )
        rows.append(
            {
                "capture_key": key,
                "speaker_code": pair["speaker_code"],
                "session_id": pair["session_id"],
                "script_id": pair["script_id"],
                "repetition_index": pair["repetition_index"],
                "pc_sample_id": pair["pc_sample_id"],
                "phone_sample_id": pair["phone_sample_id"],
                "pc_audio_file": pc["audio_file"],
                "phone_audio_file": phone["audio_file"],
                "pc_stt_raw": pair["pc_text_raw"],
                "phone_stt_raw": pair["phone_text_raw"],
                "pc_stt_normalized": pair["pc_text_normalized"],
                "phone_stt_normalized": pair["phone_text_normalized"],
                "pair_exact_match": pair["exact_normalized_match"],
                "pair_character_error_rate": pair[
                    "pair_character_error_rate"
                ],
                "pair_eojeol_error_rate": pair[
                    "pair_eojeol_error_rate"
                ],
                **human,
            }
        )
    if len(rows) != 6:
        raise NaturalReviewError(
            "NATURAL_CAPTURE_COUNT_INVALID",
            f"Expected 6 natural captures, found {len(rows)}.",
        )
    return rows


def _difference(first: list[Any] | str, second: list[Any] | str) -> dict[str, Any]:
    operations = edit_operations(first, second)
    denominator = max(len(first), len(second))
    return {
        **operations,
        "symmetric_rate": operations["distance"] / denominator
        if denominator
        else 0.0,
    }


def _operation_signature(metrics: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(metrics["character_substitutions"]),
        int(metrics["character_deletions"]),
        int(metrics["character_insertions"]),
    )


def classify_clean_pair(
    pc_metrics: dict[str, Any] | None,
    phone_metrics: dict[str, Any] | None,
) -> tuple[str, str, bool | None]:
    if pc_metrics is None or phone_metrics is None:
        return "comparison_unavailable", "comparison_unavailable", None
    pc_cer = float(pc_metrics["cer"])
    phone_cer = float(phone_metrics["cer"])
    if pc_cer == 0 and phone_cer == 0:
        classification = "both_exact"
    elif pc_cer < phone_cer:
        classification = "pc_closer_to_reference"
    elif phone_cer < pc_cer:
        classification = "phone_closer_to_reference"
    else:
        classification = "equal_non_exact"
    if pc_cer == 0 and phone_cer > 0:
        single = "phone_only"
    elif phone_cer == 0 and pc_cer > 0:
        single = "pc_only"
    elif pc_cer > 0 and phone_cer > 0:
        single = "both"
    else:
        single = "neither"
    return (
        classification,
        single,
        _operation_signature(pc_metrics) == _operation_signature(phone_metrics),
    )


def build_mismatch_rows(
    evaluation: dict[str, Any],
    review_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evaluations = {
        row["sample_id"]: row for row in evaluation.get("evaluations", [])
    }
    review_by_key = {row["capture_key"]: row for row in review_rows}
    mismatches: list[dict[str, Any]] = []
    for pair in evaluation.get("device_pairs", []):
        if pair["exact_normalized_match"]:
            continue
        pc_text = pair["pc_text_normalized"]
        phone_text = pair["phone_text_normalized"]
        character_difference = _difference(
            pc_text.replace(" ", ""), phone_text.replace(" ", "")
        )
        eojeol_difference = _difference(
            pc_text.split(), phone_text.split()
        )
        pc_metrics: dict[str, Any] | None = None
        phone_metrics: dict[str, Any] | None = None
        warnings: list[str] = []
        if pair["recording_condition"] == "clean":
            reference_status = "fixed_script_reference"
            pc_metrics = evaluations[pair["pc_sample_id"]]
            phone_metrics = evaluations[pair["phone_sample_id"]]
            classification, single, same_signature = classify_clean_pair(
                pc_metrics, phone_metrics
            )
            closeness = classification
        else:
            review = review_by_key[pair["capture_pair_key"]]
            completed = (
                str(review["human_transcript"]).strip()
                and review["review_status"] == "completed"
                and _parse_bool(review["reviewer_confirmed"])
            )
            if completed:
                reference_status = "human_transcript_completed"
                pc_metrics = evaluate_text(
                    review["human_transcript"], pair["pc_text_raw"]
                )
                phone_metrics = evaluate_text(
                    review["human_transcript"], pair["phone_text_raw"]
                )
                classification, single, same_signature = classify_clean_pair(
                    pc_metrics, phone_metrics
                )
                closeness = classification
            else:
                reference_status = "requires_manual_transcript"
                classification = "comparison_unavailable"
                single = "comparison_unavailable"
                same_signature = None
                closeness = "requires_manual_transcript"
                warnings.append(
                    "Natural accuracy and device closeness are unavailable until human transcription."
                )
        mismatches.append(
            {
                "capture_key": pair["capture_pair_key"],
                "script_id": pair["script_id"],
                "condition": pair["recording_condition"],
                "repetition_index": pair["repetition_index"],
                "pc_sample_id": pair["pc_sample_id"],
                "phone_sample_id": pair["phone_sample_id"],
                "pc_stt": pair["pc_text_raw"],
                "phone_stt": pair["phone_text_raw"],
                "character_difference": character_difference,
                "eojeol_difference": eojeol_difference,
                "reference_status": reference_status,
                "pc_cer": pc_metrics["cer"] if pc_metrics else None,
                "phone_cer": phone_metrics["cer"] if phone_metrics else None,
                "reference_closeness": closeness,
                "clean_pair_classification": classification,
                "same_reference_error_signature": same_signature,
                "single_device_error": single,
                "warnings": warnings,
            }
        )
    return mismatches


def build_clean_pair_diagnostics(
    evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    evaluations = {
        row["sample_id"]: row for row in evaluation.get("evaluations", [])
    }
    diagnostics: list[dict[str, Any]] = []
    for pair in evaluation.get("device_pairs", []):
        if pair["recording_condition"] != "clean":
            continue
        pc_metrics = evaluations.get(pair["pc_sample_id"])
        phone_metrics = evaluations.get(pair["phone_sample_id"])
        classification, single, same_signature = classify_clean_pair(
            pc_metrics, phone_metrics
        )
        diagnostics.append(
            {
                "capture_key": pair["capture_pair_key"],
                "script_id": pair["script_id"],
                "repetition_index": pair["repetition_index"],
                "pair_exact_normalized_match": pair[
                    "exact_normalized_match"
                ],
                "pc_cer": pc_metrics["cer"] if pc_metrics else None,
                "phone_cer": phone_metrics["cer"] if phone_metrics else None,
                "classification": classification,
                "same_reference_error_signature": same_signature,
                "single_device_error": single,
            }
        )
    return diagnostics


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
        raise NaturalReviewError(
            "REVIEW_OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
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
                for field, value in tuple(formatted.items()):
                    if isinstance(value, (dict, list)):
                        formatted[field] = json.dumps(
                            value, ensure_ascii=False, allow_nan=False
                        )
                    elif isinstance(value, bool):
                        formatted[field] = str(value).lower()
                writer.writerow(formatted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        temporary.unlink(missing_ok=True)
        raise NaturalReviewError(
            "REVIEW_OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def create_review_and_report(
    evaluation_path: Path | str,
    batch_manifest_path: Path | str,
    relative_root: Path | str,
    review_csv_path: Path | str,
    review_json_path: Path | str,
    mismatch_json_path: Path | str,
    mismatch_csv_path: Path | str,
) -> dict[str, Any]:
    evaluation = _load_json(evaluation_path)
    individual = _load_individual_results(batch_manifest_path, relative_root)
    existing = _existing_human_values(Path(review_csv_path))
    review_rows = build_natural_review_rows(evaluation, individual, existing)
    mismatch_rows = build_mismatch_rows(evaluation, review_rows)
    clean_diagnostics = build_clean_pair_diagnostics(evaluation)
    review_payload = {
        "schema_version": "1.0",
        "session_id": "SESSION001",
        "capture_count": len(review_rows),
        "instructions": [
            "오디오에서 실제로 들린 내용을 문법·어미·반복·수정·누락·오발음까지 그대로 기록한다.",
            "실제로 들리는 filler도 기록한다.",
            "[불명확] 표기가 있으면 평가 전 처리 기준을 별도로 확정한다.",
            "STT는 비교용이며 human_transcript로 자동 복사하거나 정답으로 확정하지 않는다.",
        ],
        "review_rows": review_rows,
        "error": None,
    }
    mismatch_payload = {
        "schema_version": "1.0",
        "session_id": "SESSION001",
        "total_pairs": len(evaluation.get("device_pairs", [])),
        "mismatch_count": len(mismatch_rows),
        "mismatches": mismatch_rows,
        "clean_pair_diagnostics": clean_diagnostics,
        "clean_pair_classification_counts": dict(
            Counter(row["classification"] for row in clean_diagnostics)
        ),
        "limitations": [
            "Natural 미전사 pair에서는 어느 장치가 더 정확한지 판단하지 않는다.",
            "Clean pair 분류는 해당 고정 reference에 대한 파일별 진단이며 장치 일반 우열이 아니다.",
        ],
        "error": None,
    }
    _atomic_csv(Path(review_csv_path), review_rows, REVIEW_FIELDS)
    _atomic_json(Path(review_json_path), review_payload)
    _atomic_json(Path(mismatch_json_path), mismatch_payload)
    _atomic_csv(Path(mismatch_csv_path), mismatch_rows, MISMATCH_FIELDS)
    return {
        "natural_capture_count": len(review_rows),
        "mismatch_count": len(mismatch_rows),
        "pending_review_count": sum(
            row["review_status"] != "completed"
            or not _parse_bool(row["reviewer_confirmed"])
            or not str(row["human_transcript"]).strip()
            for row in review_rows
        ),
        "error": None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stt-evaluation", type=Path, required=True)
    parser.add_argument("--batch-manifest", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    parser.add_argument("--review-csv-output", type=Path, required=True)
    parser.add_argument("--review-json-output", type=Path, required=True)
    parser.add_argument("--mismatch-json-output", type=Path, required=True)
    parser.add_argument("--mismatch-csv-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = create_review_and_report(
            args.stt_evaluation,
            args.batch_manifest,
            args.relative_root,
            args.review_csv_output,
            args.review_json_output,
            args.mismatch_json_output,
            args.mismatch_csv_output,
        )
    except NaturalReviewError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "NATURAL_REVIEW_CREATION_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(strict_json_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
