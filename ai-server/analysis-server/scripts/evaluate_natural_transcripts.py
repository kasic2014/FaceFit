"""Evaluate only completed, reviewer-confirmed natural human transcripts."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from create_natural_transcript_review import (
    REVIEW_FIELDS,
    _load_individual_results,
    _parse_bool,
)
from evaluate_prosody_session_stt import evaluate_text
from transcribe_prosody_session import strict_json_text


NATURAL_EVALUATION_FIELDS = (
    "capture_key",
    "sample_id",
    "device_code",
    "script_id",
    "repetition_index",
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
    "exact_normalized_match",
)


class NaturalEvaluationError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def load_review_rows(path: Path | str) -> list[dict[str, Any]]:
    source = Path(path)
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            fields = set(reader.fieldnames or [])
    except (OSError, csv.Error, UnicodeError) as exc:
        raise NaturalEvaluationError(
            "NATURAL_REVIEW_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    if not set(REVIEW_FIELDS).issubset(fields) or len(rows) != 6:
        raise NaturalEvaluationError(
            "NATURAL_REVIEW_INVALID",
            f"Expected 6 rows and review fields; found {len(rows)} rows.",
        )
    for row in rows:
        row["reviewer_confirmed"] = _parse_bool(row["reviewer_confirmed"])
    return rows


def validate_completed_capture(
    review: dict[str, Any],
    individual: dict[str, dict[str, Any]],
    duplicate_keys: set[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    key = str(review.get("capture_key") or "")
    transcript = str(review.get("human_transcript") or "").strip()
    if not transcript:
        reasons.append("HUMAN_TRANSCRIPT_EMPTY")
    if not _parse_bool(review.get("reviewer_confirmed")):
        reasons.append("REVIEWER_NOT_CONFIRMED")
    if review.get("review_status") != "completed":
        reasons.append("REVIEW_STATUS_NOT_COMPLETED")
    if key in duplicate_keys:
        reasons.append("CAPTURE_KEY_DUPLICATED")
    if "[불명확]" in transcript:
        reasons.append("UNCLEAR_MARKER_REQUIRES_POLICY")
    pc = individual.get(str(review.get("pc_sample_id") or ""))
    phone = individual.get(str(review.get("phone_sample_id") or ""))
    if pc is None or phone is None:
        reasons.append("PAIRED_SAMPLE_NOT_FOUND")
    else:
        expected = (
            review.get("session_id"),
            review.get("script_id"),
            str(review.get("repetition_index")),
        )
        for sample in (pc, phone):
            actual = (
                sample.get("session_id"),
                sample.get("script_id"),
                str(sample.get("repetition_index")),
            )
            if actual != expected:
                reasons.append("PAIRED_SAMPLE_METADATA_MISMATCH")
                break
        if pc.get("device_code") != "DEV_PC_MIC_01":
            reasons.append("PC_SAMPLE_DEVICE_INVALID")
        if phone.get("device_code") != "DEV_PHONE_01":
            reasons.append("PHONE_SAMPLE_DEVICE_INVALID")
    return not reasons, reasons


def build_natural_evaluations(
    review_rows: list[dict[str, Any]],
    individual: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts = Counter(str(row.get("capture_key") or "") for row in review_rows)
    duplicates = {key for key, count in counts.items() if count > 1}
    evaluations: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for review in review_rows:
        eligible, reasons = validate_completed_capture(
            review, individual, duplicates
        )
        if not eligible:
            exclusions.append(
                {
                    "capture_key": review.get("capture_key"),
                    "reasons": reasons,
                }
            )
            continue
        reference = str(review["human_transcript"]).strip()
        for sample_id_field in ("pc_sample_id", "phone_sample_id"):
            result = individual[review[sample_id_field]]
            metrics = evaluate_text(
                reference, result["transcription_text_raw"]
            )
            evaluations.append(
                {
                    "capture_key": review["capture_key"],
                    "sample_id": result["sample_id"],
                    "device_code": result["device_code"],
                    "script_id": result["script_id"],
                    "repetition_index": result["repetition_index"],
                    **metrics,
                    "exact_normalized_match": (
                        metrics["reference_text_normalized"]
                        == metrics["hypothesis_text_normalized"]
                    ),
                }
            )
    return evaluations, exclusions


def _median_mad(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    median = statistics.median(values)
    return median, statistics.median(abs(value - median) for value in values)


def summarize_natural_evaluations(
    evaluations: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
) -> dict[str, Any]:
    captures = {row["capture_key"] for row in evaluations}
    pc = [
        row for row in evaluations if row["device_code"] == "DEV_PC_MIC_01"
    ]
    phone = [
        row for row in evaluations if row["device_code"] == "DEV_PHONE_01"
    ]
    all_cer = [float(row["cer"]) for row in evaluations]
    pc_cer = [float(row["cer"]) for row in pc]
    phone_cer = [float(row["cer"]) for row in phone]
    all_eojeol = [float(row["eojeol_error_rate"]) for row in evaluations]
    pc_eojeol = [float(row["eojeol_error_rate"]) for row in pc]
    phone_eojeol = [float(row["eojeol_error_rate"]) for row in phone]
    pc_cer_median, pc_cer_mad = _median_mad(pc_cer)
    phone_cer_median, phone_cer_mad = _median_mad(phone_cer)
    all_cer_median, all_cer_mad = _median_mad(all_cer)
    pc_eojeol_median, pc_eojeol_mad = _median_mad(pc_eojeol)
    phone_eojeol_median, phone_eojeol_mad = _median_mad(phone_eojeol)
    return {
        "evaluated_capture_count": len(captures),
        "evaluated_audio_file_count": len(evaluations),
        "pc_cer_median": pc_cer_median,
        "pc_cer_mad": pc_cer_mad,
        "phone_cer_median": phone_cer_median,
        "phone_cer_mad": phone_cer_mad,
        "overall_cer_median": all_cer_median,
        "overall_cer_mad": all_cer_mad,
        "pc_eojeol_error_rate_median": pc_eojeol_median,
        "pc_eojeol_error_rate_mad": pc_eojeol_mad,
        "phone_eojeol_error_rate_median": phone_eojeol_median,
        "phone_eojeol_error_rate_mad": phone_eojeol_mad,
        "overall_eojeol_error_rate_median": (
            statistics.median(all_eojeol) if all_eojeol else None
        ),
        "exact_match_audio_file_count": sum(
            row["exact_normalized_match"] for row in evaluations
        ),
        "incomplete_transcript_count": len(exclusions),
    }


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
        raise NaturalEvaluationError(
            "NATURAL_EVALUATION_WRITE_FAILED",
            f"{type(exc).__name__}: {exc}",
        ) from exc


def _atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=NATURAL_EVALUATION_FIELDS
            )
            writer.writeheader()
            writer.writerows(
                {
                    field: row.get(field, "")
                    for field in NATURAL_EVALUATION_FIELDS
                }
                for row in rows
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        temporary.unlink(missing_ok=True)
        raise NaturalEvaluationError(
            "NATURAL_EVALUATION_WRITE_FAILED",
            f"{type(exc).__name__}: {exc}",
        ) from exc


def evaluate_natural_review(
    review_csv_path: Path | str,
    batch_manifest_path: Path | str,
    relative_root: Path | str,
    output_json_path: Path | str,
    output_csv_path: Path | str,
) -> dict[str, Any]:
    review_rows = load_review_rows(review_csv_path)
    individual = _load_individual_results(
        batch_manifest_path, relative_root, allowed_counts=(12, 24)
    )
    evaluations, exclusions = build_natural_evaluations(
        review_rows, individual
    )
    summary = summarize_natural_evaluations(evaluations, exclusions)
    payload = {
        "schema_version": "1.0",
        "session_id": "SESSION001",
        "summary": summary,
        "evaluations": evaluations,
        "excluded_captures": exclusions,
        "limitations": [
            "이 평가는 최대 6개 natural 발화와 12개 장치 파일의 내부 파일럿이다.",
            "미완료·미확인·빈 전사와 [불명확] 처리 정책 미확정 전사는 평가에서 제외한다.",
            "전체 사용자 또는 모든 한국어 음성으로 일반화하지 않는다.",
        ],
        "error": None,
    }
    _atomic_json(Path(output_json_path), payload)
    _atomic_csv(Path(output_csv_path), evaluations)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-csv", type=Path, required=True)
    parser.add_argument("--batch-manifest", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_natural_review(
            args.review_csv,
            args.batch_manifest,
            args.relative_root,
            args.output_json,
            args.output_csv,
        )
    except (NaturalEvaluationError, Exception) as exc:
        if isinstance(exc, NaturalEvaluationError):
            code, detail = exc.code, exc.detail
        else:
            code, detail = (
                "NATURAL_STT_EVALUATION_FAILED",
                f"{type(exc).__name__}: {exc}",
            )
        print(strict_json_text({"error": {"code": code, "detail": detail}}))
        return 1
    print(strict_json_text({"summary": result["summary"], "error": None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
