"""Build a read-only SESSION001 validation and metric-readiness report.

The script only parses existing artifacts and hashes immutable inputs. It does
not invoke STT, speech metrics, prosody analysis, audio conversion, or models.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"
SESSION_ID = "SESSION001"
INPUT_PATHS = {
    "recording_inventory": (
        "data/prosody_validation/recording_inventory_SESSION001.json"
    ),
    "conversion_manifest": (
        "data/prosody_validation/recording_conversion_manifest_SESSION001.json"
    ),
    "stt_batch_manifest": (
        "data/output/prosody_validation/stt_evaluation/"
        "SESSION001_stt_batch_manifest.json"
    ),
    "stt_evaluation": (
        "data/output/prosody_validation/stt_evaluation/"
        "SESSION001_stt_evaluation.json"
    ),
    "natural_stt_evaluation": (
        "data/output/prosody_validation/stt_evaluation/"
        "SESSION001_natural_stt_evaluation.json"
    ),
    "stt_device_pair_comparison": (
        "data/output/prosody_validation/stt_evaluation/"
        "SESSION001_device_pair_comparison.csv"
    ),
    "speech_metrics_summary": (
        "data/output/prosody_validation/speech_metrics_evaluation/"
        "SESSION001_speech_metrics_summary.json"
    ),
    "speech_metrics_pair_comparison": (
        "data/output/prosody_validation/speech_metrics_evaluation/"
        "SESSION001_speech_metrics_pair_comparison.csv"
    ),
    "human_annotation_comparison": (
        "data/output/prosody_validation/speech_metrics_evaluation/"
        "SESSION001_human_annotation_comparison.json"
    ),
    "prosody_v21_summary": (
        "data/output/prosody_validation/prosody_v21_evaluation/"
        "SESSION001_prosody_v21_summary.json"
    ),
    "prosody_v21_pair_comparison": (
        "data/output/prosody_validation/prosody_v21_evaluation/"
        "SESSION001_prosody_v21_pair_comparison.csv"
    ),
    "prosody_v21_repeatability": (
        "data/output/prosody_validation/prosody_v21_evaluation/"
        "SESSION001_prosody_v21_repeatability.csv"
    ),
    "prosody_v21_quality_diagnostics": (
        "data/output/prosody_validation/prosody_v21_evaluation/"
        "SESSION001_prosody_v21_quality_diagnostics.json"
    ),
}
CORE_PATHS = (
    "app/speech/prosody_metrics.py",
    "app/speech/prosody_validation.py",
    "app/speech/prosody_validation_v21.py",
    "scripts/analyze_speech_prosody_v21.py",
)
READINESS_FIELDS = (
    "metric_id",
    "metric_name",
    "source_module",
    "implementation_status",
    "validation_status",
    "evidence",
    "known_risks",
    "user_feedback_eligible",
    "scoring_eligible",
    "recommended_usage",
    "next_validation_requirement",
)
VALIDATION_LEVELS = {
    "engineering_ready",
    "experimental",
    "insufficient_evidence",
    "prohibited_for_feedback",
}
PIPELINE_STATES = {
    "completed",
    "completed_with_limitations",
    "incomplete",
    "failed",
}
DECISION_RULES = [
    "분석 코드 실행 성공과 서비스 지표의 타당성은 서로 다르다.",
    "장치 간 수치 일치는 절대 정확도의 증명이 아니다.",
    "Estimator agreement는 ground truth가 아니다.",
    "Shared octave/harmonic risk가 있으면 pitch 사용자 피드백을 금지한다.",
    "Both-reliable pair가 0이면 장치 비교를 서비스 품질 근거로 사용하지 않는다.",
    "사람 annotation 하나의 미검출을 recall 값으로 표현하지 않는다.",
    "반복 3개는 통계적 일반화를 지원하지 않는다.",
]


class ValidationReportError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _reject_constant(token: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {token}")


def strict_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def load_json(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationReportError("REQUIRED_INPUT_NOT_FOUND", str(source))
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8-sig"),
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationReportError(
            "INPUT_INVALID", f"{source}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationReportError(
            "INPUT_INVALID", f"JSON object required: {source}"
        )
    return payload


def load_csv(path: Path | str) -> list[dict[str, str]]:
    source = Path(path)
    if not source.is_file():
        raise ValidationReportError("REQUIRED_INPUT_NOT_FOUND", str(source))
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValidationReportError(
            "INPUT_INVALID", f"{source}: {type(exc).__name__}: {exc}"
        ) from exc


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def aggregate_sha256(
    paths: Iterable[Path], relative_root: Path
) -> dict[str, Any]:
    files = sorted((Path(path) for path in paths), key=lambda item: str(item.resolve()))
    if not files:
        raise ValidationReportError(
            "BASELINE_INPUT_NOT_FOUND", "Checksum collection is empty."
        )
    entries = [
        {
            "path": path.resolve().relative_to(
                relative_root.resolve()
            ).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in files
    ]
    # Preserve the aggregate convention already used for SESSION001:
    # PowerShell-style relative keys such as ``.\data\...``.
    serialized = "\n".join(
        f".\\{entry['path'].replace('/', chr(92))}|{entry['sha256']}"
        for entry in entries
    ).encode("utf-8")
    return {
        "file_count": len(entries),
        "aggregate_sha256": hashlib.sha256(serialized).hexdigest(),
        "files": entries,
    }


def atomic_json(path: Path | str, payload: Any) -> None:
    target = Path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(strict_json_text(payload))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except (OSError, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise ValidationReportError(
            "REPORT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def atomic_csv(
    path: Path | str,
    rows: list[dict[str, Any]],
    fields: tuple[str, ...] = READINESS_FIELDS,
) -> None:
    target = Path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        field: (
                            json.dumps(
                                row.get(field),
                                ensure_ascii=False,
                                allow_nan=False,
                            )
                            if isinstance(row.get(field), (dict, list))
                            else str(row.get(field)).lower()
                            if isinstance(row.get(field), bool)
                            else ""
                            if row.get(field) is None
                            else row.get(field)
                        )
                        for field in fields
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except (OSError, csv.Error, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise ValidationReportError(
            "REPORT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def atomic_text(path: Path | str, text: str) -> None:
    target = Path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text.rstrip() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ValidationReportError(
            "REPORT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _median(values: Iterable[Any]) -> float | None:
    finite = [
        number
        for value in values
        for number in [_number(value)]
        if number is not None
    ]
    return statistics.median(finite) if finite else None


def _sum(values: Iterable[Any]) -> float:
    return sum(
        number
        for value in values
        for number in [_number(value)]
        if number is not None
    )


def _metric_rows(
    rows: list[dict[str, str]], metric: str
) -> list[dict[str, str]]:
    return [row for row in rows if row.get("metric") == metric]


def _metric_device_median(
    rows: list[dict[str, str]], metric: str
) -> dict[str, float | None]:
    selected = _metric_rows(rows, metric)
    return {
        "DEV_PC_MIC_01": _median(row.get("pc_value") for row in selected),
        "DEV_PHONE_01": _median(
            row.get("phone_value") for row in selected
        ),
    }


def _metric_device_total(
    rows: list[dict[str, str]], metric: str
) -> dict[str, float]:
    selected = _metric_rows(rows, metric)
    return {
        "DEV_PC_MIC_01": _sum(row.get("pc_value") for row in selected),
        "DEV_PHONE_01": _sum(
            row.get("phone_value") for row in selected
        ),
    }


def resolve_inputs(root: Path | str) -> dict[str, Path]:
    base = Path(root)
    resolved = {
        name: base / relative for name, relative in INPUT_PATHS.items()
    }
    missing = [str(path) for path in resolved.values() if not path.is_file()]
    if missing:
        raise ValidationReportError(
            "REQUIRED_INPUT_NOT_FOUND", "; ".join(missing)
        )
    return resolved


def load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "recording_inventory": load_json(paths["recording_inventory"]),
        "conversion_manifest": load_json(paths["conversion_manifest"]),
        "stt_batch_manifest": load_json(paths["stt_batch_manifest"]),
        "stt_evaluation": load_json(paths["stt_evaluation"]),
        "natural_stt_evaluation": load_json(
            paths["natural_stt_evaluation"]
        ),
        "stt_device_pair_comparison": load_csv(
            paths["stt_device_pair_comparison"]
        ),
        "speech_metrics_summary": load_json(
            paths["speech_metrics_summary"]
        ),
        "speech_metrics_pair_comparison": load_csv(
            paths["speech_metrics_pair_comparison"]
        ),
        "human_annotation_comparison": load_json(
            paths["human_annotation_comparison"]
        ),
        "prosody_v21_summary": load_json(paths["prosody_v21_summary"]),
        "prosody_v21_pair_comparison": load_csv(
            paths["prosody_v21_pair_comparison"]
        ),
        "prosody_v21_repeatability": load_csv(
            paths["prosody_v21_repeatability"]
        ),
        "prosody_v21_quality_diagnostics": load_json(
            paths["prosody_v21_quality_diagnostics"]
        ),
    }


def build_stt_results(data: dict[str, Any]) -> dict[str, Any]:
    batch = data["stt_batch_manifest"]["summary"]
    clean = data["stt_evaluation"]["summary"]
    natural = data["natural_stt_evaluation"]["summary"]
    pairs = data["stt_device_pair_comparison"]
    return {
        "total_files": batch.get("total_files"),
        "successful_files": batch.get("successful_files"),
        "failed_files": batch.get("failed_files"),
        "clean": {
            "evaluated_audio_file_count": clean.get("evaluated_clean_files"),
            "cer_median": clean.get("clean_cer_median"),
            "cer_mad": clean.get("clean_cer_mad"),
            "eojeol_error_rate_median": clean.get(
                "clean_eojeol_error_rate_median"
            ),
            "eojeol_error_rate_mad": clean.get(
                "clean_eojeol_error_rate_mad"
            ),
            "exact_match_audio_file_count": clean.get(
                "clean_exact_match_count"
            ),
            "by_device": clean.get("clean_by_device"),
        },
        "natural": {
            "evaluated_capture_count": natural.get(
                "evaluated_capture_count"
            ),
            "evaluated_audio_file_count": natural.get(
                "evaluated_audio_file_count"
            ),
            "cer_by_device": {
                "DEV_PC_MIC_01": {
                    "median": natural.get("pc_cer_median"),
                    "mad": natural.get("pc_cer_mad"),
                },
                "DEV_PHONE_01": {
                    "median": natural.get("phone_cer_median"),
                    "mad": natural.get("phone_cer_mad"),
                },
            },
            "eojeol_error_rate_by_device": {
                "DEV_PC_MIC_01": {
                    "median": natural.get(
                        "pc_eojeol_error_rate_median"
                    ),
                    "mad": natural.get("pc_eojeol_error_rate_mad"),
                },
                "DEV_PHONE_01": {
                    "median": natural.get(
                        "phone_eojeol_error_rate_median"
                    ),
                    "mad": natural.get(
                        "phone_eojeol_error_rate_mad"
                    ),
                },
            },
            "exact_match_audio_file_count": natural.get(
                "exact_match_audio_file_count"
            ),
            "incomplete_transcript_count": natural.get(
                "incomplete_transcript_count"
            ),
        },
        "device_pairs": {
            "total_pairs": clean.get("total_pairs"),
            "valid_pairs": clean.get("valid_pairs"),
            "exact_normalized_match_pairs": clean.get(
                "exact_normalized_match_pairs"
            ),
            "csv_pair_count": len(pairs),
        },
        "performance": {
            "median_real_time_factor": batch.get(
                "median_real_time_factor"
            ),
            "max_real_time_factor": batch.get("max_real_time_factor"),
            "timestamp_warning_count": batch.get(
                "timestamp_warning_count"
            ),
            "duration_validation_warning_count": batch.get(
                "duration_validation_warning_count"
            ),
        },
    }


def build_speech_metrics_results(data: dict[str, Any]) -> dict[str, Any]:
    summary = data["speech_metrics_summary"]["summary"]
    pairs = data["speech_metrics_pair_comparison"]
    return {
        "total_files": summary.get("total_files"),
        "successful_files": summary.get("successful_files"),
        "failed_files": summary.get("failed_files"),
        "speech_rate_voiced_duration_wpm_median_by_device": summary.get(
            "speech_rate_median_by_device"
        ),
        "speaking_ratio_median_by_device": _metric_device_median(
            pairs, "speaking_ratio"
        ),
        "answer_duration_sec_median_by_device": _metric_device_median(
            pairs, "audio_duration_sec"
        ),
        "speech_duration_sec_median_by_device": _metric_device_median(
            pairs, "speech_duration_sec"
        ),
        "pause_count_median_by_device": _metric_device_median(
            pairs, "pause_count"
        ),
        "total_pause_duration_sec_median_by_device": summary.get(
            "pause_duration_median_by_device"
        ),
        "max_pause_duration_sec_median_by_device": _metric_device_median(
            pairs, "max_pause_duration_sec"
        ),
        "long_silence_count_total_by_device": _metric_device_total(
            pairs, "long_pause_count"
        ),
        "probable_non_word_event_count_total_by_device": _metric_device_total(
            pairs, "probable_omitted_vocalization_count"
        ),
        "uncertain_event_count_total_by_device": _metric_device_total(
            pairs, "uncertain_gap_vocalization_count"
        ),
        "hallucination_candidate_count": None,
        "hallucination_candidate_count_status": (
            "not_available_in_selected_aggregate_inputs"
        ),
        "files_with_long_pause": summary.get("files_with_long_pause"),
        "files_with_probable_vocalization": summary.get(
            "files_with_probable_vocalization"
        ),
        "files_with_uncertain_candidate": summary.get(
            "files_with_uncertain_candidate"
        ),
        "quality_warnings": {
            "background_noise": summary.get(
                "files_with_background_noise_warning"
            ),
            "clipping": summary.get("files_with_clipping_warning"),
        },
        "pair_difference_median": summary.get("pair_difference_median"),
        "repeatability": data["speech_metrics_summary"].get(
            "repeatability", []
        ),
    }


def build_prosody_results(data: dict[str, Any]) -> dict[str, Any]:
    summary = data["prosody_v21_summary"]["summary"]
    pairs = data["prosody_v21_pair_comparison"]
    pair_status = Counter(
        row.get("pair_comparison_status") or "unknown" for row in pairs
    )
    return {
        "total_files": summary.get("total_files"),
        "successful_files": summary.get("successful_files"),
        "failed_files": summary.get("failed_files"),
        "pitch_median_by_device": summary.get("median_pitch_by_device"),
        "pitch_range_by_device": summary.get(
            "median_pitch_range_by_device"
        ),
        "coverage_by_device": summary.get("median_coverage_by_device"),
        "reliability_distribution": summary.get(
            "reliability_distribution"
        ),
        "estimator_status_matrix": summary.get("estimator_status_totals"),
        "pair_differences": {
            "pitch_hz": summary.get("median_pair_pitch_difference_hz"),
            "pitch_semitones": summary.get(
                "median_pair_pitch_difference_semitones"
            ),
            "pitch_range": summary.get(
                "median_pair_pitch_range_difference"
            ),
        },
        "pair_status_distribution": dict(pair_status),
        "both_reliable_pair_count": pair_status.get("both_reliable", 0),
        "shared_octave_harmonic_risk_file_count": summary.get(
            "files_with_shared_octave_harmonic_risk"
        ),
        "low_coverage_file_count": summary.get("files_with_low_coverage"),
        "clipping_file_count": summary.get("files_with_clipping"),
        "background_noise_file_count": summary.get(
            "files_with_background_noise"
        ),
        "repeatability": data["prosody_v21_repeatability"],
    }


def build_annotation_results(data: dict[str, Any]) -> dict[str, Any]:
    human = data["human_annotation_comparison"]
    elongation = {
        str(item.get("target")): item.get("validation_status")
        for item in human.get("elongation_diagnostics", [])
        if isinstance(item, dict)
    }
    silence = human.get("silence_validation") or {}
    return {
        "counts": human.get("annotation_counts"),
        "silence_detection_status": silence.get("validation_status"),
        "silence_recall_calculated": bool(
            silence.get("accuracy_or_recall_computed")
        ),
        "elongation_diagnostics": elongation,
        "interpretation": human.get("interpretation"),
    }


def build_pipeline_status(
    data: dict[str, Any],
    stt: dict[str, Any],
    speech: dict[str, Any],
    prosody: dict[str, Any],
    annotations: dict[str, Any],
) -> list[dict[str, Any]]:
    inventory = data["recording_inventory"]
    conversion = data["conversion_manifest"]
    stages = [
        {
            "stage": "recording_collection",
            "status": "completed_with_limitations",
            "evidence_file": INPUT_PATHS["recording_inventory"],
            "key_metrics": {
                "total_files": inventory.get("total_files"),
                "pc_files": inventory.get("pc_files"),
                "phone_files": inventory.get("phone_files"),
            },
            "limitations": ["One speaker, two scripts, two devices."],
        },
        {
            "stage": "inventory",
            "status": (
                "completed"
                if not inventory.get("error")
                and inventory.get("total_files") == 24
                else "failed"
            ),
            "evidence_file": INPUT_PATHS["recording_inventory"],
            "key_metrics": inventory.get("validation_summary"),
            "limitations": [],
        },
        {
            "stage": "source_mapping",
            "status": (
                "completed"
                if conversion.get("mapping_summary", {}).get("mapped_total")
                == 24
                and conversion.get("mapping_summary", {}).get("unmatched")
                == 0
                else "incomplete"
            ),
            "evidence_file": INPUT_PATHS["conversion_manifest"],
            "key_metrics": conversion.get("mapping_summary"),
            "limitations": [],
        },
        {
            "stage": "standardization",
            "status": (
                "completed_with_limitations"
                if conversion.get("conversion_summary", {}).get(
                    "failed_total"
                )
                == 0
                else "failed"
            ),
            "evidence_file": INPUT_PATHS["conversion_manifest"],
            "key_metrics": conversion.get("conversion_summary"),
            "limitations": [
                "Conversion warnings remain recorded in the source manifest."
            ],
        },
        {
            "stage": "stt_execution",
            "status": (
                "completed_with_limitations"
                if stt["successful_files"] == 24
                else "failed"
            ),
            "evidence_file": INPUT_PATHS["stt_batch_manifest"],
            "key_metrics": {
                "successful_files": stt["successful_files"],
                **stt["performance"],
            },
            "limitations": [
                "Duration validation warnings exist."
                if stt["performance"]["duration_validation_warning_count"]
                else "Single-speaker pilot only."
            ],
        },
        {
            "stage": "clean_stt_evaluation",
            "status": "completed_with_limitations",
            "evidence_file": INPUT_PATHS["stt_evaluation"],
            "key_metrics": stt["clean"],
            "limitations": ["Twelve clean audio files only."],
        },
        {
            "stage": "natural_stt_evaluation",
            "status": (
                "completed_with_limitations"
                if stt["natural"]["incomplete_transcript_count"] == 0
                else "incomplete"
            ),
            "evidence_file": INPUT_PATHS["natural_stt_evaluation"],
            "key_metrics": stt["natural"],
            "limitations": ["Six utterances and twelve audio files only."],
        },
        {
            "stage": "speech_metrics",
            "status": (
                "completed_with_limitations"
                if speech["successful_files"] == 24
                else "failed"
            ),
            "evidence_file": INPUT_PATHS["speech_metrics_summary"],
            "key_metrics": {
                "successful_files": speech["successful_files"],
                "quality_warnings": speech["quality_warnings"],
            },
            "limitations": [
                "Several event metrics remain experimental.",
                "Human silence annotation was not detected.",
            ],
        },
        {
            "stage": "prosody_v21",
            "status": (
                "completed_with_limitations"
                if prosody["successful_files"] == 24
                else "failed"
            ),
            "evidence_file": INPUT_PATHS["prosody_v21_summary"],
            "key_metrics": {
                "successful_files": prosody["successful_files"],
                "reliability": prosody["reliability_distribution"],
                "shared_risk_files": prosody[
                    "shared_octave_harmonic_risk_file_count"
                ],
            },
            "limitations": [
                "Only two files are sufficient for experimental summary.",
                "Shared octave/harmonic risk is present in 22 files.",
            ],
        },
        {
            "stage": "device_pair_comparison",
            "status": "completed_with_limitations",
            "evidence_file": INPUT_PATHS["prosody_v21_pair_comparison"],
            "key_metrics": {
                "stt_exact_pairs": stt["device_pairs"][
                    "exact_normalized_match_pairs"
                ],
                "prosody_pair_status": prosody[
                    "pair_status_distribution"
                ],
                "both_reliable_pairs": prosody[
                    "both_reliable_pair_count"
                ],
            },
            "limitations": [
                "No both-reliable prosody device pair exists.",
                "Neither device is an absolute reference.",
            ],
        },
        {
            "stage": "repeatability_analysis",
            "status": "completed_with_limitations",
            "evidence_file": INPUT_PATHS["prosody_v21_repeatability"],
            "key_metrics": {
                "prosody_group_count": len(prosody["repeatability"]),
                "repetitions_per_group": 3,
            },
            "limitations": [
                "Three repetitions do not support statistical generalization."
            ],
        },
        {
            "stage": "human_annotation_review",
            "status": "completed_with_limitations",
            "evidence_file": INPUT_PATHS["human_annotation_comparison"],
            "key_metrics": annotations,
            "limitations": [
                "Few event annotations; the missed silence is not a recall estimate."
            ],
        },
    ]
    if any(stage["status"] not in PIPELINE_STATES for stage in stages):
        raise ValidationReportError(
            "REPORT_BUILD_FAILED", "Unknown pipeline status."
        )
    return stages


def _readiness(
    metric_id: str,
    metric_name: str,
    source: str,
    implementation: str,
    validation: str,
    evidence: str,
    risks: str,
    feedback: bool,
    usage: str,
    next_requirement: str,
) -> dict[str, Any]:
    if validation not in VALIDATION_LEVELS:
        raise ValidationReportError(
            "REPORT_BUILD_FAILED", f"Unknown readiness level: {validation}"
        )
    return {
        "metric_id": metric_id,
        "metric_name": metric_name,
        "source_module": source,
        "implementation_status": implementation,
        "validation_status": validation,
        "evidence": evidence,
        "known_risks": risks,
        "user_feedback_eligible": feedback,
        "scoring_eligible": False,
        "recommended_usage": usage,
        "next_validation_requirement": next_requirement,
    }


def build_metric_readiness(
    stt: dict[str, Any],
    speech: dict[str, Any],
    prosody: dict[str, Any],
    annotations: dict[str, Any],
) -> list[dict[str, Any]]:
    clean_cer = stt["clean"]["cer_median"]
    natural_pc = stt["natural"]["cer_by_device"]["DEV_PC_MIC_01"]["median"]
    natural_phone = stt["natural"]["cer_by_device"]["DEV_PHONE_01"]["median"]
    shared_risk = prosody["shared_octave_harmonic_risk_file_count"]
    both_reliable = prosody["both_reliable_pair_count"]
    common_next = "Stage 2 multi-speaker and Stage 3 free-form validation."
    rows = [
        _readiness(
            "stt_text",
            "STT text",
            "faster-whisper/STT evaluation",
            "implemented",
            "engineering_ready",
            f"24/24 succeeded; clean CER median {clean_cer:.6f}; Natural PC/PHONE CER medians {natural_pc:.6f}/{natural_phone:.6f}.",
            "One speaker, two scripts; STT errors remain.",
            True,
            "Display transcript with correction or confirmation workflow.",
            common_next,
        ),
        _readiness(
            "answer_duration",
            "Answer duration",
            "standard WAV metadata",
            "implemented",
            "engineering_ready",
            "Duration available for all 24 standard WAV files.",
            "Conversion duration warnings must remain visible.",
            True,
            "Descriptive elapsed-time display only.",
            "Verify capture boundaries in Stage 2.",
        ),
        _readiness(
            "speech_duration",
            "Speech duration",
            "speech_metrics",
            "implemented",
            "experimental",
            "Computed for 24 files using existing voiced-frame thresholds.",
            "Threshold-based proxy without manual frame truth.",
            True,
            "Label explicitly as estimated voiced duration.",
            "Manual speech/non-speech intervals for representative files.",
        ),
        _readiness(
            "speaking_ratio",
            "Speaking ratio",
            "speech_metrics",
            "implemented",
            "experimental",
            "Device medians are available for 12 PC/PHONE pairs.",
            "Depends on estimated speech duration and capture boundaries.",
            True,
            "Descriptive experimental metric with definition shown.",
            common_next,
        ),
        _readiness(
            "speech_rate_overall_duration",
            "Overall-duration speech rate",
            "speech_metrics + STT",
            "implemented",
            "experimental",
            "Word/eojeol counts and complete WAV duration are available.",
            "STT word errors and leading/trailing silence affect the value.",
            True,
            "Descriptive rate with denominator disclosed.",
            "Validate against human transcript word counts.",
        ),
        _readiness(
            "speech_rate_voiced_duration",
            "Voiced-duration speech rate",
            "speech_metrics + STT",
            "implemented",
            "experimental",
            f"PC/PHONE medians {speech['speech_rate_voiced_duration_wpm_median_by_device']}.",
            "Combines STT counts with threshold-based voiced duration.",
            True,
            "Experimental display; never a performance score.",
            common_next,
        ),
        _readiness(
            "pause_count",
            "Pause count",
            "speech_metrics",
            "implemented",
            "experimental",
            f"Device medians {speech['pause_count_median_by_device']}.",
            "STT gaps and acoustic thresholds are not manually validated.",
            True,
            "Descriptive experimental count with event review.",
            "Manual pause boundary annotations.",
        ),
        _readiness(
            "total_pause_duration",
            "Total pause duration",
            "speech_metrics",
            "implemented",
            "experimental",
            f"Device medians {speech['total_pause_duration_sec_median_by_device']}.",
            "Human silence annotation was not detected.",
            False,
            "Internal diagnostics only until pause validation improves.",
            "Multiple manually timed pauses across speakers.",
        ),
        _readiness(
            "max_pause_duration",
            "Maximum pause duration",
            "speech_metrics",
            "implemented",
            "experimental",
            f"Device medians {speech['max_pause_duration_sec_median_by_device']}.",
            "Single missed human silence; no recall estimate.",
            False,
            "Internal diagnostics only.",
            "Manual pause boundary ground truth.",
        ),
        _readiness(
            "long_silence",
            "Long silence",
            "speech_metrics",
            "implemented",
            "insufficient_evidence",
            f"Files with long pause: {speech['files_with_long_pause']}; human silence status: {annotations['silence_detection_status']}.",
            "Only one human silence annotation and it was not detected.",
            False,
            "Do not provide user feedback.",
            "Larger manually timed silence set.",
        ),
        _readiness(
            "probable_non_word_event",
            "Probable non-word acoustic event",
            "speech_metrics",
            "implemented",
            "experimental",
            f"Files with candidates: {speech['files_with_probable_vocalization']}.",
            "Candidate is not a filler label and has limited human truth.",
            False,
            "Human-review queue only.",
            "Multi-speaker human labels for breath, filler, and noise.",
        ),
        _readiness(
            "uncertain_acoustic_event",
            "Uncertain acoustic event",
            "speech_metrics",
            "implemented",
            "experimental",
            f"Files with candidates: {speech['files_with_uncertain_candidate']}.",
            "Uncertainty is intentional; no automatic class confirmation.",
            False,
            "Human-review queue only.",
            "Larger human-labeled event dataset.",
        ),
        _readiness(
            "hallucination_candidate",
            "Hallucination candidate",
            "speech_metrics",
            "implemented",
            "insufficient_evidence",
            speech["hallucination_candidate_count_status"],
            "Aggregate count is absent from the selected summary inputs.",
            False,
            "Internal diagnostics only.",
            "Expose aggregate plus manual hallucination labels.",
        ),
        _readiness(
            "word_duration_outlier",
            "Word duration outlier",
            "speech_metrics/Whisper word timestamps",
            "implemented_experimental",
            "experimental",
            f"저장={annotations['elongation_diagnostics'].get('저장')}; 데이터가={annotations['elongation_diagnostics'].get('데이터가')}.",
            "Based on Whisper word duration, not manual word boundaries.",
            False,
            "Reference-only diagnostic; do not confirm elongation.",
            "Manual word timestamps and more annotated elongations.",
        ),
        _readiness(
            "pitch_median",
            "Pitch median",
            "prosody v2.1",
            "implemented_experimental",
            "insufficient_evidence",
            f"Shared risk in {shared_risk} files; both-reliable pairs {both_reliable}.",
            "No external F0 truth; octave/harmonic ambiguity.",
            False,
            "Internal diagnostics only; no user feedback.",
            "External pitch reference or manual expert validation.",
        ),
        _readiness(
            "pitch_range",
            "Pitch range",
            "prosody v2.1",
            "implemented_experimental",
            "insufficient_evidence",
            f"Reliability distribution: {prosody['reliability_distribution']['overall']}.",
            "Range depends on potentially ambiguous F0 frames.",
            False,
            "Internal diagnostics only.",
            "External pitch reference across multiple speakers.",
        ),
        _readiness(
            "intonation_variability",
            "Intonation variability",
            "prosody v2.1",
            "implemented_experimental",
            "insufficient_evidence",
            f"Only {prosody['reliability_distribution']['overall']['sufficient_for_experimental_summary']} files are sufficient.",
            "No validated relationship to communication quality.",
            False,
            "Internal research only.",
            "External F0 truth and construct-validity study.",
        ),
        _readiness(
            "ending_pattern",
            "Ending pattern",
            "prosody v2.1",
            "implemented_experimental",
            "insufficient_evidence",
            "Ending pattern is produced by the existing v2.1 baseline.",
            "No manual ending-intonation ground truth.",
            False,
            "Internal research only.",
            "Manual expert labels for ending contours.",
        ),
        _readiness(
            "confidence",
            "Confidence",
            "none",
            "not_implemented",
            "prohibited_for_feedback",
            "No validated confidence construct or labels.",
            "High risk of unsupported personal inference.",
            False,
            "Do not infer or display.",
            "Out of current scope; requires a separate ethical validity study.",
        ),
        _readiness(
            "emotion",
            "Emotion",
            "none",
            "not_implemented",
            "prohibited_for_feedback",
            "No emotion labels or validated model.",
            "Sensitive and unsupported inference.",
            False,
            "Do not infer or display.",
            "Out of current scope.",
        ),
        _readiness(
            "interview_speech_score",
            "Interview speech score",
            "none",
            "prohibited",
            "prohibited_for_feedback",
            "No score-validity or outcome study.",
            "Could create unjustified ranking or adverse impact.",
            False,
            "Do not create scores, deductions, or pass predictions.",
            "Independent validity, fairness, and governance study.",
        ),
    ]
    if len(rows) < 21:
        raise ValidationReportError(
            "REPORT_BUILD_FAILED", "At least 21 readiness rows are required."
        )
    return rows


def build_known_limitations(prosody: dict[str, Any]) -> dict[str, Any]:
    items = [
        ("one_speaker_only", "dataset", "Only SPK001 is included."),
        ("two_scripts_only", "dataset", "Only SCRIPT001 and SCRIPT002 are included."),
        ("two_recording_devices", "dataset", "Only PC and phone devices are included."),
        ("repeated_scripted_speech", "dataset", "The pilot uses repeated scripted speech."),
        ("no_free_form_interview_answer", "dataset", "No free-form interview answer is included."),
        ("no_multi_speaker_validation", "validation", "No multi-speaker validation exists."),
        ("no_external_pitch_ground_truth", "prosody", "No external F0 reference exists."),
        ("no_manual_word_timestamp_ground_truth", "stt", "No manually annotated word timestamp ground truth exists."),
        ("no_concurrent_user_load_test", "operations", "No concurrent user load test was run."),
        ("no_score_validity_study", "governance", "No interview-score validity study exists."),
        (
            "shared_octave_harmonic_risk",
            "prosody",
            f"Shared octave/harmonic risk occurs in {prosody['shared_octave_harmonic_risk_file_count']} files.",
        ),
        (
            "only_two_sufficient_prosody_files",
            "prosody",
            "Only two files are sufficient for experimental prosody summary.",
        ),
        (
            "no_both_reliable_device_pairs",
            "device_comparison",
            f"Both-reliable prosody pair count is {prosody['both_reliable_pair_count']}.",
        ),
        (
            "human_silence_not_detected",
            "speech_metrics",
            "The single human silence annotation was not detected; recall is not calculated.",
        ),
        (
            "elongation_uses_whisper_duration",
            "speech_metrics",
            "Elongation diagnostics rely on Whisper word duration rather than manual word boundaries.",
        ),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": SESSION_ID,
        "limitation_count": len(items),
        "limitations": [
            {
                "limitation_id": item_id,
                "category": category,
                "detail": detail,
                "service_impact": (
                    "Restricts generalization or user-facing interpretation."
                ),
                "resolved": False,
            }
            for item_id, category, detail in items
        ],
        "error": None,
    }


def build_collection_plan() -> dict[str, Any]:
    return {
        "stage_2": {
            "speakers": ["SPK001", "SPK002", "SPK003", "SPK004", "SPK005"],
            "scripts": ["SCRIPT001", "SCRIPT002"],
            "devices": ["PC", "PHONE"],
            "conditions": ["clean", "natural"],
            "repetitions": ["R01", "R02", "R03"],
            "recording_method": "simultaneous PC and PHONE recording",
            "actual_utterances": 60,
            "audio_files": 120,
        },
        "stage_3": {
            "minimum_speakers": 5,
            "minimum_free_form_questions": 5,
            "answer_length_sec": {"minimum": 30, "maximum": 90},
            "human_reference_transcripts": True,
            "manual_word_timestamp_review_for_representative_files": True,
            "stt_metrics": [
                "CER",
                "eojeol_error_rate",
                "failure_rate",
                "real_time_factor",
            ],
            "speech_metrics_repeatability": True,
            "prosody_validation": (
                "Review external reference or manual expert validation."
            ),
        },
        "plan_file_created": False,
    }


def build_checksums(
    root: Path,
    input_paths: dict[str, Path],
    generated_at: str,
) -> dict[str, Any]:
    collections = {
        "original_m4a": aggregate_sha256(
            root.glob(
                "data/prosody_validation/recordings/SESSION001/"
                "original/**/*.m4a"
            ),
            root,
        ),
        "standard_wav": aggregate_sha256(
            root.glob(
                "data/prosody_validation/recordings/SESSION001/"
                "standard/**/*.wav"
            ),
            root,
        ),
        "stt_json": aggregate_sha256(
            root.glob(
                "data/output/prosody_validation/stt/SESSION001/**/*.json"
            ),
            root,
        ),
        "speech_metrics_json": aggregate_sha256(
            root.glob(
                "data/output/prosody_validation/speech_metrics/"
                "SESSION001/**/*.json"
            ),
            root,
        ),
        "prosody_v21_core": aggregate_sha256(
            (root / relative for relative in CORE_PATHS), root
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": SESSION_ID,
        "generated_at": generated_at,
        "algorithm": "SHA-256",
        "aggregate_definition": (
            "SHA-256 of sorted UTF-8 lines: "
            ".\\windows_relative_path|file_sha256"
        ),
        "collections": collections,
        "major_artifacts": {
            name: {
                "path": path.resolve().relative_to(root.resolve()).as_posix(),
                "sha256": sha256_file(path),
            }
            for name, path in input_paths.items()
        },
        "regression_baseline": True,
        "error": None,
    }


def _format_number(value: Any, digits: int = 6) -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def build_markdown(report: dict[str, Any]) -> str:
    stt = report["results"]["stt"]
    speech = report["results"]["speech_metrics"]
    prosody = report["results"]["prosody_v21"]
    annotations = report["results"]["human_annotations"]
    readiness = report["metric_readiness"]
    stages = report["pipeline_status"]
    stage_rows = "\n".join(
        f"| {item['stage']} | {item['status']} | {item['evidence_file']} |"
        for item in stages
    )
    readiness_rows = "\n".join(
        "| {metric_name} | {validation_status} | {feedback} | {scoring} | "
        "{usage} |".format(
            metric_name=item["metric_name"],
            validation_status=item["validation_status"],
            feedback="yes" if item["user_feedback_eligible"] else "no",
            scoring="yes" if item["scoring_eligible"] else "no",
            usage=item["recommended_usage"].replace("|", "/"),
        )
        for item in readiness
    )
    repeat_rows = "\n".join(
        "| {script_id} | {recording_condition} | {device_code} | "
        "{pitch_median_hz_all_median} | {pitch_median_hz_all_mad} | "
        "{reliable_repetition_count} |".format(**row)
        for row in prosody["repeatability"]
    )
    limitations = "\n".join(
        f"- {item['detail']}"
        for item in report["known_limitations"]["limitations"]
    )
    rules = "\n".join(f"- {rule}" for rule in report["decision_rules"])
    return f"""# SESSION001 통합 검증 보고서

## 1. 목적

기존 SESSION001 산출물을 읽기 전용으로 통합하여 파이프라인 상태와 서비스 사용 가능성을 판정한다. 이 보고서는 분석 재실행, 임계값 변경, 면접 점수 또는 사람 특성 추론을 수행하지 않는다.

## 2. 데이터 구성

- 화자: SPK001 1명
- 스크립트: SCRIPT001, SCRIPT002
- 장치: PC, PHONE
- 조건: clean, natural
- 원본/표준 파일: 24/24
- 동시 발화 pair: 12
- 반복: 조건별 R01~R03

## 3. 파이프라인

| 단계 | 상태 | 근거 |
|---|---|---|
{stage_rows}

## 4. STT 결과

- 성공: {stt['successful_files']}/{stt['total_files']}
- Clean CER median/MAD: {_format_number(stt['clean']['cer_median'])}/{_format_number(stt['clean']['cer_mad'])}
- Clean exact match: {stt['clean']['exact_match_audio_file_count']}/12
- Natural PC CER median/MAD: {_format_number(stt['natural']['cer_by_device']['DEV_PC_MIC_01']['median'])}/{_format_number(stt['natural']['cer_by_device']['DEV_PC_MIC_01']['mad'])}
- Natural PHONE CER median/MAD: {_format_number(stt['natural']['cer_by_device']['DEV_PHONE_01']['median'])}/{_format_number(stt['natural']['cer_by_device']['DEV_PHONE_01']['mad'])}
- Natural exact match: {stt['natural']['exact_match_audio_file_count']}/12
- PC·PHONE normalized exact pair: {stt['device_pairs']['exact_normalized_match_pairs']}/12
- RTF median/max: {_format_number(stt['performance']['median_real_time_factor'])}/{_format_number(stt['performance']['max_real_time_factor'])}
- Timestamp warning: {stt['performance']['timestamp_warning_count']}

## 5. Speech metrics 결과

- Voiced-duration speech rate median: PC {_format_number(speech['speech_rate_voiced_duration_wpm_median_by_device']['DEV_PC_MIC_01'])}, PHONE {_format_number(speech['speech_rate_voiced_duration_wpm_median_by_device']['DEV_PHONE_01'])}
- Pause count median: {speech['pause_count_median_by_device']}
- Total pause duration median: {speech['total_pause_duration_sec_median_by_device']}
- Long-silence totals: {speech['long_silence_count_total_by_device']}
- Probable non-word event totals: {speech['probable_non_word_event_count_total_by_device']}
- Uncertain event totals: {speech['uncertain_event_count_total_by_device']}
- Hallucination candidate aggregate: {speech['hallucination_candidate_count_status']}
- Quality warnings: {speech['quality_warnings']}

## 6. Prosody v2.1 결과

- Pitch median by device: {prosody['pitch_median_by_device']}
- Pitch range by device: {prosody['pitch_range_by_device']}
- Coverage by device: {prosody['coverage_by_device']}
- Reliability: {prosody['reliability_distribution']['overall']}
- Estimator matrix: {prosody['estimator_status_matrix']}
- Shared octave/harmonic risk: {prosody['shared_octave_harmonic_risk_file_count']} files
- Low coverage/clipping/background noise: {prosody['low_coverage_file_count']}/{prosody['clipping_file_count']}/{prosody['background_noise_file_count']}

## 7. 장치 비교

- STT exact normalized pair: {stt['device_pairs']['exact_normalized_match_pairs']}/12
- Prosody pair status: {prosody['pair_status_distribution']}
- Both-reliable prosody pair: {prosody['both_reliable_pair_count']}
- Pair pitch differences: {prosody['pair_differences']}

장치 간 수치가 가까워도 절대 정확도를 증명하지 않으며, 어느 장치도 정답 장치로 취급하지 않는다.

## 8. 반복 안정성

| Script | Condition | Device | Pitch median Hz | MAD | Reliable repetitions |
|---|---|---|---:|---:|---:|
{repeat_rows}

그룹당 반복이 3개뿐이므로 유의성 검정이나 통계적 일반화를 수행하지 않는다.

## 9. 사람 annotation 비교

- 집계: {annotations['counts']}
- Silence: {annotations['silence_detection_status']}
- 저장: {annotations['elongation_diagnostics'].get('저장')}
- 데이터가: {annotations['elongation_diagnostics'].get('데이터가')}

한 건의 silence 미검출을 recall 값으로 표현하지 않는다. Elongation은 Whisper word duration 기반 experimental 진단이며 pitch로 확정하지 않는다.

## 10. 서비스 적용 가능 지표

| 지표 | 판정 | 사용자 피드백 | 점수 사용 | 권장 용도 |
|---|---|---|---|---|
{readiness_rows}

## 11. 사용 금지 지표

- Confidence 추론
- Emotion 추론
- Interview speech score, 감점, 순위, 합격 가능성
- Shared octave/harmonic risk가 남은 pitch 기반 사용자 피드백

### 의사결정 규칙

{rules}

## 12. 알려진 한계

{limitations}

## 13. 다음 검증 계획

### Stage 2

- SPK001~SPK005
- SCRIPT001, SCRIPT002
- PC·PHONE 동시 녹음
- clean, natural 및 R01~R03
- 실제 발화 60개, 오디오 파일 120개

### Stage 3

- 화자 5명 이상, 자유 면접 질문 5개 이상
- 답변 길이 30~90초
- 사람 정답 전사와 대표 파일 word timestamp 검수
- CER, 어절 오류율, 실패율, RTF
- Speech metrics 반복성
- Prosody 외부 기준 또는 수동 검수 방법 검토

별도 녹음 계획 파일은 이번 단계에서 생성하지 않았다.

## 14. 결론

STT 실행과 기본 파일·시간 측정은 제한된 서비스 활용이 가능하다. Speech event와 word-duration 지표는 experimental이며 사람 검토가 필요하다. Prosody pitch 지표는 외부 기준 부재, shared octave/harmonic risk 22개, sufficient 파일 2개, both-reliable pair 0개 때문에 사용자 피드백이나 점수에 사용할 근거가 부족하다.
"""


def build_report(
    analysis_root: Path | str,
    output_directory: Path | str,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = Path(analysis_root)
    output = Path(output_directory)
    input_paths = resolve_inputs(root)
    before_hashes = {
        name: sha256_file(path) for name, path in input_paths.items()
    }
    data = load_inputs(input_paths)
    stt = build_stt_results(data)
    speech = build_speech_metrics_results(data)
    prosody = build_prosody_results(data)
    annotations = build_annotation_results(data)
    pipeline = build_pipeline_status(
        data, stt, speech, prosody, annotations
    )
    readiness = build_metric_readiness(stt, speech, prosody, annotations)
    limitations = build_known_limitations(prosody)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    checksums = build_checksums(root, input_paths, timestamp)
    report = {
        "schema_version": SCHEMA_VERSION,
        "session_id": SESSION_ID,
        "generated_at": timestamp,
        "purpose": (
            "Read-only integrated validation and service-readiness assessment."
        ),
        "analysis_rerun": {
            "stt": False,
            "speech_metrics": False,
            "prosody_v21": False,
            "audio_conversion": False,
        },
        "input_artifacts": [
            {
                "artifact_id": name,
                "path": INPUT_PATHS[name],
                "sha256": before_hashes[name],
            }
            for name in INPUT_PATHS
        ],
        "pipeline_status": pipeline,
        "results": {
            "stt": stt,
            "speech_metrics": speech,
            "prosody_v21": prosody,
            "human_annotations": annotations,
        },
        "metric_readiness": readiness,
        "decision_rules": DECISION_RULES,
        "known_limitations": limitations,
        "next_validation_plan": build_collection_plan(),
        "prohibited_inferences": [
            "gender",
            "emotion",
            "confidence",
            "interview_score",
            "selection_probability",
        ],
        "error": None,
    }
    markdown = build_markdown(report)
    atomic_json(output / f"{SESSION_ID}_validation_report.json", report)
    atomic_text(output / f"{SESSION_ID}_validation_report.md", markdown)
    atomic_csv(output / f"{SESSION_ID}_metric_readiness.csv", readiness)
    atomic_json(
        output / f"{SESSION_ID}_baseline_checksums.json", checksums
    )
    atomic_json(
        output / f"{SESSION_ID}_known_limitations.json", limitations
    )
    after_hashes = {
        name: sha256_file(path) for name, path in input_paths.items()
    }
    if before_hashes != after_hashes:
        raise ValidationReportError(
            "INPUT_MODIFIED",
            "A required input changed while the report was generated.",
        )
    after_checksums = build_checksums(root, input_paths, timestamp)
    if (
        checksums["collections"] != after_checksums["collections"]
        or checksums["major_artifacts"] != after_checksums["major_artifacts"]
    ):
        raise ValidationReportError(
            "INPUT_MODIFIED",
            "An audio, analysis, core, or report input changed while the "
            "report was generated.",
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = build_report(args.analysis_root, args.output_dir)
    except ValidationReportError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "SESSION_REPORT_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(
        strict_json_text(
            {
                "session_id": result["session_id"],
                "pipeline_stage_count": len(result["pipeline_status"]),
                "metric_readiness_count": len(result["metric_readiness"]),
                "error": None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
