"""Compare SESSION001 frozen prosody v2.1 results without scoring devices."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
for import_root in (ANALYSIS_ROOT, SCRIPTS_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from analyze_prosody_session_v21 import (  # noqa: E402
    PC_DEVICE,
    PHONE_DEVICE,
    SessionProsodyV21Error,
    atomic_csv,
    atomic_json,
    load_json,
    strict_json_text,
)


RELIABILITY_STATUSES = (
    "sufficient_for_experimental_summary",
    "limited",
    "unreliable",
    "analysis_failed",
)
REPEATABILITY_METRICS = (
    "pitch_median_hz",
    "pitch_median_semitone",
    "pitch_range_semitones",
    "pitch_std_semitones",
    "validated_overall_coverage",
    "validated_over_voiced_coverage",
    "conditioned_estimator_agreement",
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
    "pc_pitch_median_hz",
    "phone_pitch_median_hz",
    "pitch_median_absolute_difference_hz",
    "pitch_median_difference_semitones",
    "pc_pitch_range_semitones",
    "phone_pitch_range_semitones",
    "pitch_range_absolute_difference_semitones",
    "pc_validated_overall_coverage",
    "phone_validated_overall_coverage",
    "coverage_absolute_difference",
    "pc_conditioned_estimator_agreement",
    "phone_conditioned_estimator_agreement",
    "pc_reliability_status",
    "phone_reliability_status",
    "pair_comparison_status",
    "warnings",
)
REPEATABILITY_FIELDS = (
    "script_id",
    "recording_condition",
    "device_code",
    "repetition_count",
    "reliable_repetition_count",
) + tuple(
    f"{metric}_{suffix}"
    for metric in REPEATABILITY_METRICS
    for suffix in (
        "all_median",
        "all_mad",
        "reliable_only_median",
        "reliable_only_mad",
    )
)
QUALITY_FIELDS = (
    "sample_id",
    "script_id",
    "recording_condition",
    "repetition_index",
    "device_code",
    "reliability_status",
    "internal_use_status",
    "low_coverage",
    "clipping",
    "background_noise",
    "shared_octave_harmonic_ambiguity",
    "estimator_disagreement",
    "insufficient_voiced_frames",
    "speech_rate_voiced_duration_wpm",
    "speaking_ratio",
    "total_pause_duration_sec",
    "probable_omitted_vocalization_count",
    "noise_floor_dbfs",
    "human_annotation_reference",
    "warnings",
)
SUMMARY_FIELDS = (
    "record_type",
    "group",
    "device_code",
    "recording_condition",
    "metric",
    "value",
    "mad",
    "count",
)
LIMITATIONS = [
    "SPK001 한 명에 대한 내부 파일럿이다.",
    "두 스크립트와 두 장치만 포함한다.",
    "같은 사람이 반복했지만 발화가 완전히 동일하지는 않다.",
    "Prosody v2.1은 experimental baseline이다.",
    "Estimator agreement는 정확도 보증이 아니며 같은 octave 오류가 남을 수 있다.",
    "Octave 및 harmonic ambiguity가 남을 수 있다.",
    "Pitch 수치를 성별, 감정, 자신감 또는 합격 가능성과 연결하지 않는다.",
    "보편적인 정상 pitch 범위를 적용하지 않는다.",
    "면접 점수나 감점 기준을 생성하지 않는다.",
    "이 SESSION001 데이터에 맞춰 임계값을 변경하지 않았다.",
    "반복은 그룹당 3개뿐이므로 유의성 검정을 수행하지 않는다.",
]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def median_mad(values: list[Any]) -> tuple[float | None, float | None]:
    finite = [
        number
        for value in values
        for number in [_number(value)]
        if number is not None
    ]
    if not finite:
        return None, None
    median = statistics.median(finite)
    mad = statistics.median(abs(value - median) for value in finite)
    return round(median, 6), round(mad, 6)


def pitch_hz_to_semitone(value: Any) -> float | None:
    frequency = _number(value)
    if frequency is None or frequency <= 0:
        return None
    # MIDI-like absolute coordinate; this is a unit conversion, not correction.
    return 69.0 + 12.0 * math.log2(frequency / 440.0)


def absolute_difference(first: Any, second: Any) -> float | None:
    left = _number(first)
    right = _number(second)
    if left is None or right is None:
        return None
    return abs(left - right)


def semitone_difference(first_hz: Any, second_hz: Any) -> float | None:
    left = _number(first_hz)
    right = _number(second_hz)
    if left is None or right is None or left <= 0 or right <= 0:
        return None
    return abs(12.0 * math.log2(right / left))


def pair_comparison_status(
    pc_reliability: str | None,
    phone_reliability: str | None,
    *,
    comparison_available: bool,
) -> str:
    if not comparison_available:
        return "comparison_unavailable"
    reliable = "sufficient_for_experimental_summary"
    pc_ok = pc_reliability == reliable
    phone_ok = phone_reliability == reliable
    if pc_ok and phone_ok:
        return "both_reliable"
    if pc_ok:
        return "pc_reliable_phone_limited"
    if phone_ok:
        return "phone_reliable_pc_limited"
    return "both_limited"


def build_pair_comparisons(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["capture_pair_key"])].append(row)
    if len(groups) != 12:
        raise SessionProsodyV21Error(
            "DEVICE_PAIR_INCOMPLETE",
            f"Expected 12 pair keys, found {len(groups)}.",
        )
    output: list[dict[str, Any]] = []
    for capture_key, members in sorted(groups.items()):
        pc = next(
            (item for item in members if item["device_code"] == PC_DEVICE),
            None,
        )
        phone = next(
            (item for item in members if item["device_code"] == PHONE_DEVICE),
            None,
        )
        if pc is None or phone is None or len(members) != 2:
            raise SessionProsodyV21Error(
                "DEVICE_PAIR_INCOMPLETE", capture_key
            )
        available = all(
            _number(value) is not None
            for value in (
                pc.get("pitch_median_hz"),
                phone.get("pitch_median_hz"),
                pc.get("pitch_range_semitones"),
                phone.get("pitch_range_semitones"),
                pc.get("validated_overall_coverage"),
                phone.get("validated_overall_coverage"),
                pc.get("conditioned_estimator_agreement"),
                phone.get("conditioned_estimator_agreement"),
            )
        )
        status = pair_comparison_status(
            pc.get("reliability_status"),
            phone.get("reliability_status"),
            comparison_available=available,
        )
        warnings: list[str] = []
        if status != "both_reliable":
            warnings.append(
                "LOW_RELIABILITY_DO_NOT_INTERPRET_AS_DEVICE_PERFORMANCE"
            )
        if not available:
            warnings.append("PAIR_NUMERIC_COMPARISON_UNAVAILABLE")
        output.append(
            {
                "capture_pair_key": capture_key,
                "speaker_code": pc["speaker_code"],
                "session_id": pc["session_id"],
                "script_id": pc["script_id"],
                "recording_condition": pc["recording_condition"],
                "repetition_index": pc["repetition_index"],
                "pc_sample_id": pc["sample_id"],
                "phone_sample_id": phone["sample_id"],
                "pc_pitch_median_hz": pc.get("pitch_median_hz"),
                "phone_pitch_median_hz": phone.get("pitch_median_hz"),
                "pitch_median_absolute_difference_hz": absolute_difference(
                    pc.get("pitch_median_hz"),
                    phone.get("pitch_median_hz"),
                ),
                "pitch_median_difference_semitones": semitone_difference(
                    pc.get("pitch_median_hz"),
                    phone.get("pitch_median_hz"),
                ),
                "pc_pitch_range_semitones": pc.get(
                    "pitch_range_semitones"
                ),
                "phone_pitch_range_semitones": phone.get(
                    "pitch_range_semitones"
                ),
                "pitch_range_absolute_difference_semitones": absolute_difference(
                    pc.get("pitch_range_semitones"),
                    phone.get("pitch_range_semitones"),
                ),
                "pc_validated_overall_coverage": pc.get(
                    "validated_overall_coverage"
                ),
                "phone_validated_overall_coverage": phone.get(
                    "validated_overall_coverage"
                ),
                "coverage_absolute_difference": absolute_difference(
                    pc.get("validated_overall_coverage"),
                    phone.get("validated_overall_coverage"),
                ),
                "pc_conditioned_estimator_agreement": pc.get(
                    "conditioned_estimator_agreement"
                ),
                "phone_conditioned_estimator_agreement": phone.get(
                    "conditioned_estimator_agreement"
                ),
                "pc_reliability_status": pc.get("reliability_status"),
                "phone_reliability_status": phone.get("reliability_status"),
                "pair_comparison_status": status,
                "warnings": warnings,
            }
        )
    return output


def build_repeatability(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[
            (
                str(row["script_id"]),
                str(row["recording_condition"]),
                str(row["device_code"]),
            )
        ].append(row)
    if len(groups) != 8:
        raise SessionProsodyV21Error(
            "REPEATABILITY_GROUP_INVALID",
            f"Expected 8 groups, found {len(groups)}.",
        )
    output = []
    for (script, condition, device), members in sorted(groups.items()):
        repetitions = sorted(int(item["repetition_index"]) for item in members)
        if repetitions != [1, 2, 3]:
            raise SessionProsodyV21Error(
                "REPEATABILITY_GROUP_INVALID",
                f"{script}|{condition}|{device}: {repetitions}",
            )
        reliable = [
            item
            for item in members
            if item.get("reliability_status")
            == "sufficient_for_experimental_summary"
        ]
        result: dict[str, Any] = {
            "script_id": script,
            "recording_condition": condition,
            "device_code": device,
            "repetition_count": len(members),
            "reliable_repetition_count": len(reliable),
        }
        for metric in REPEATABILITY_METRICS:
            if metric == "pitch_median_semitone":
                all_values = [
                    pitch_hz_to_semitone(item.get("pitch_median_hz"))
                    for item in members
                ]
                reliable_values = [
                    pitch_hz_to_semitone(item.get("pitch_median_hz"))
                    for item in reliable
                ]
            else:
                all_values = [item.get(metric) for item in members]
                reliable_values = [item.get(metric) for item in reliable]
            all_median, all_mad = median_mad(all_values)
            reliable_median, reliable_mad = median_mad(reliable_values)
            result[f"{metric}_all_median"] = all_median
            result[f"{metric}_all_mad"] = all_mad
            result[f"{metric}_reliable_only_median"] = reliable_median
            result[f"{metric}_reliable_only_mad"] = reliable_mad
        output.append(result)
    return output


def _status_distribution(
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    counts = Counter(
        str(row.get("reliability_status") or "analysis_failed")
        for row in rows
    )
    return {status: counts[status] for status in RELIABILITY_STATUSES}


def build_reliability_distribution(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "overall": _status_distribution(rows),
        "by_device": {
            device: _status_distribution(
                [row for row in rows if row["device_code"] == device]
            )
            for device in (PC_DEVICE, PHONE_DEVICE)
        },
        "by_condition": {
            condition: _status_distribution(
                [
                    row
                    for row in rows
                    if row["recording_condition"] == condition
                ]
            )
            for condition in ("clean", "natural")
        },
        "by_device_and_condition": {
            f"{device}|{condition}": _status_distribution(
                [
                    row
                    for row in rows
                    if row["device_code"] == device
                    and row["recording_condition"] == condition
                ]
            )
            for device in (PC_DEVICE, PHONE_DEVICE)
            for condition in ("clean", "natural")
        },
    }


def load_human_annotation_context(
    review_path: Path | str,
    comparison_path: Path | str,
) -> dict[str, Any]:
    try:
        with Path(review_path).open(
            "r", encoding="utf-8-sig", newline=""
        ) as stream:
            review_rows = list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise SessionProsodyV21Error(
            "SESSION_PROSODY_V21_FAILED",
            f"Natural review invalid: {type(exc).__name__}: {exc}",
        ) from exc
    if len(review_rows) != 6:
        raise SessionProsodyV21Error(
            "SESSION_PROSODY_V21_FAILED",
            f"Expected 6 Natural review rows, found {len(review_rows)}.",
        )
    counts = Counter()
    capture_annotations: dict[str, list[str]] = defaultdict(list)
    for row in review_rows:
        note = str(row.get("human_transcript_note") or "")
        capture = str(row.get("capture_key") or "")
        if "생략" in note:
            counts["omission"] += 1
            capture_annotations[capture].append("omission")
        if "침묵" in note:
            counts["silence"] += 1
            capture_annotations[capture].append("silence")
        if "늘어짐" in note:
            counts["elongation"] += 1
            capture_annotations[capture].append("elongation")
    counts["filler"] = 0
    comparison = load_json(
        comparison_path, "SESSION_PROSODY_V21_FAILED"
    )
    elongation_references = []
    for item in comparison.get("elongation_diagnostics") or []:
        if isinstance(item, dict):
            elongation_references.append(
                {
                    "capture_key": item.get("capture_key"),
                    "target": item.get("target"),
                    "validation_status": item.get("validation_status"),
                    "use": "word_duration_experimental_reference_only",
                    "pitch_linked": False,
                }
            )
    return {
        "counts": {
            "omission": counts["omission"],
            "silence": counts["silence"],
            "elongation": counts["elongation"],
            "filler": 0,
        },
        "capture_annotations": dict(capture_annotations),
        "elongation_references": elongation_references,
        "interpretation_rules": {
            "omission": "Not a pitch-analysis target.",
            "silence": "Linked only to existing pause analysis.",
            "elongation": "Linked only to existing experimental word duration; prosody does not confirm elongation.",
            "filler": "Zero annotations are not used for prosody quality evaluation.",
        },
    }


def _speech_metric_value(payload: dict[str, Any], key: str) -> Any:
    return payload.get(key)


def build_quality_diagnostics(
    rows: list[dict[str, Any]],
    relative_root: Path | str,
    annotation_context: dict[str, Any],
) -> list[dict[str, Any]]:
    root = Path(relative_root)
    output = []
    annotations = annotation_context["capture_annotations"]
    for row in rows:
        metrics_path = root / Path(str(row["speech_metrics_json_file"]))
        metrics = load_json(metrics_path, "SPEECH_METRICS_NOT_FOUND")
        warnings = list(row.get("warnings") or [])
        output.append(
            {
                "sample_id": row["sample_id"],
                "script_id": row["script_id"],
                "recording_condition": row["recording_condition"],
                "repetition_index": row["repetition_index"],
                "device_code": row["device_code"],
                "reliability_status": row.get("reliability_status"),
                "internal_use_status": row.get("internal_use_status"),
                "low_coverage": bool(row.get("low_pitch_coverage_warning")),
                "clipping": "clipping_suspected" in warnings,
                "background_noise": bool(row.get("background_noise_warning")),
                "shared_octave_harmonic_ambiguity": bool(
                    row.get("shared_octave_harmonic_risk")
                ),
                "estimator_disagreement": bool(
                    int(row.get("disagree_frame_count") or 0)
                ),
                "insufficient_voiced_frames": (
                    "agreement_based_on_small_sample" in warnings
                    or int(row.get("voiced_frame_count") or 0) == 0
                ),
                "speech_rate_voiced_duration_wpm": _speech_metric_value(
                    metrics, "speech_rate_wpm"
                ),
                "speaking_ratio": _speech_metric_value(
                    metrics, "speaking_ratio"
                ),
                "total_pause_duration_sec": _speech_metric_value(
                    metrics, "total_pause_duration_sec"
                ),
                "probable_omitted_vocalization_count": _speech_metric_value(
                    metrics, "probable_omitted_vocalization_count"
                ),
                "noise_floor_dbfs": _speech_metric_value(
                    metrics, "noise_floor_dbfs"
                ),
                "human_annotation_reference": annotations.get(
                    row["capture_pair_key"], []
                ),
                "warnings": warnings,
            }
        )
    return output


def _count_causes(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "low_coverage": sum(bool(row["low_coverage"]) for row in rows),
        "clipping": sum(bool(row["clipping"]) for row in rows),
        "background_noise": sum(bool(row["background_noise"]) for row in rows),
        "shared_octave_harmonic_ambiguity": sum(
            bool(row["shared_octave_harmonic_ambiguity"]) for row in rows
        ),
        "estimator_disagreement": sum(
            bool(row["estimator_disagreement"]) for row in rows
        ),
        "insufficient_voiced_frames": sum(
            bool(row["insufficient_voiced_frames"]) for row in rows
        ),
    }


def _device_median(
    rows: list[dict[str, Any]], field: str
) -> dict[str, dict[str, float | None]]:
    output = {}
    for device in (PC_DEVICE, PHONE_DEVICE):
        median, mad = median_mad(
            [
                row.get(field)
                for row in rows
                if row["device_code"] == device
            ]
        )
        output[device] = {"median": median, "mad": mad}
    return output


def _estimator_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    fields = (
        "agree_frame_count",
        "disagree_frame_count",
        "acf_only_frame_count",
        "yin_only_frame_count",
        "both_invalid_frame_count",
        "octave_correction_count",
        "unresolved_ambiguity_count",
    )
    return {
        field: sum(int(row.get(field) or 0) for row in rows)
        for field in fields
    }


def _summary_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for field in (
        "total_files",
        "successful_files",
        "failed_files",
        "total_pairs",
        "valid_pairs",
        "files_with_shared_octave_harmonic_risk",
        "files_with_low_coverage",
        "files_with_clipping",
        "files_with_background_noise",
    ):
        rows.append(
            {
                "record_type": "count",
                "group": "overall",
                "metric": field,
                "value": summary[field],
                "count": summary[field],
            }
        )
    for metric, device_values in (
        ("pitch_median_hz", summary["median_pitch_by_device"]),
        (
            "pitch_range_semitones",
            summary["median_pitch_range_by_device"],
        ),
        ("validated_overall_coverage", summary["median_coverage_by_device"]),
    ):
        for device, values in device_values.items():
            rows.append(
                {
                    "record_type": "device_median",
                    "group": "all",
                    "device_code": device,
                    "metric": metric,
                    "value": values["median"],
                    "mad": values["mad"],
                }
            )
    for status, count in summary["reliability_distribution"][
        "overall"
    ].items():
        rows.append(
            {
                "record_type": "reliability",
                "group": "overall",
                "metric": status,
                "value": count,
                "count": count,
            }
        )
    return rows


def compare_session(
    manifest_path: Path | str,
    speech_metrics_summary_path: Path | str,
    human_review_path: Path | str,
    human_annotation_comparison_path: Path | str,
    relative_root: Path | str,
    summary_json_path: Path | str,
    summary_csv_path: Path | str,
    pair_csv_path: Path | str,
    repeatability_csv_path: Path | str,
    quality_json_path: Path | str,
    quality_csv_path: Path | str,
) -> dict[str, Any]:
    manifest = load_json(manifest_path, "SESSION_PROSODY_V21_FAILED")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != 24:
        raise SessionProsodyV21Error(
            "SESSION_PROSODY_V21_FAILED", "Expected 24 manifest rows."
        )
    successful = [row for row in rows if row.get("error") is None]
    metrics_summary = load_json(
        speech_metrics_summary_path, "SPEECH_METRICS_NOT_FOUND"
    )
    if metrics_summary.get("summary", {}).get("successful_files") != 24:
        raise SessionProsodyV21Error(
            "SPEECH_METRICS_NOT_FOUND",
            "Existing speech metrics summary is not complete for 24 files.",
        )
    annotations = load_human_annotation_context(
        human_review_path, human_annotation_comparison_path
    )
    quality_rows = build_quality_diagnostics(
        successful, relative_root, annotations
    )
    pair_rows = build_pair_comparisons(rows)
    repeatability = build_repeatability(rows)
    valid_pairs = sum(
        row["pair_comparison_status"] != "comparison_unavailable"
        for row in pair_rows
    )
    reliability = build_reliability_distribution(rows)
    pair_hz_median, pair_hz_mad = median_mad(
        [row["pitch_median_absolute_difference_hz"] for row in pair_rows]
    )
    pair_st_median, pair_st_mad = median_mad(
        [row["pitch_median_difference_semitones"] for row in pair_rows]
    )
    pair_range_median, pair_range_mad = median_mad(
        [
            row["pitch_range_absolute_difference_semitones"]
            for row in pair_rows
        ]
    )
    internal_distribution = dict(
        Counter(str(row.get("internal_use_status")) for row in rows)
    )
    summary = {
        "total_files": len(rows),
        "successful_files": len(successful),
        "failed_files": len(rows) - len(successful),
        "pc_files": sum(row["device_code"] == PC_DEVICE for row in rows),
        "phone_files": sum(row["device_code"] == PHONE_DEVICE for row in rows),
        "clean_files": sum(
            row["recording_condition"] == "clean" for row in rows
        ),
        "natural_files": sum(
            row["recording_condition"] == "natural" for row in rows
        ),
        "total_pairs": len(pair_rows),
        "valid_pairs": valid_pairs,
        "reliability_distribution": reliability,
        "internal_use_status_distribution": internal_distribution,
        "median_pitch_by_device": _device_median(
            successful, "pitch_median_hz"
        ),
        "median_pitch_range_by_device": _device_median(
            successful, "pitch_range_semitones"
        ),
        "median_coverage_by_device": _device_median(
            successful, "validated_overall_coverage"
        ),
        "median_pair_pitch_difference_hz": {
            "median": pair_hz_median,
            "mad": pair_hz_mad,
        },
        "median_pair_pitch_difference_semitones": {
            "median": pair_st_median,
            "mad": pair_st_mad,
        },
        "median_pair_pitch_range_difference": {
            "median": pair_range_median,
            "mad": pair_range_mad,
        },
        "repeatability_median_and_mad": repeatability,
        "estimator_status_totals": _estimator_totals(successful),
        "files_with_shared_octave_harmonic_risk": sum(
            bool(row["shared_octave_harmonic_ambiguity"])
            for row in quality_rows
        ),
        "files_with_low_coverage": sum(
            bool(row["low_coverage"]) for row in quality_rows
        ),
        "files_with_clipping": sum(
            bool(row["clipping"]) for row in quality_rows
        ),
        "files_with_background_noise": sum(
            bool(row["background_noise"]) for row in quality_rows
        ),
        "quality_cause_counts": _count_causes(quality_rows),
        "human_annotation_counts": annotations["counts"],
    }
    payload = {
        "schema_version": "1.0",
        "prosody_schema_version": "2.1",
        "session_id": manifest.get("session_id", "SESSION001"),
        "summary": summary,
        "unit_notes": {
            "pitch_median_difference_semitones": (
                "Absolute symmetric PC/PHONE ratio in semitones; neither "
                "device is treated as reference."
            ),
            "pitch_median_semitone": (
                "MIDI-like Hz-to-semitone coordinate used only for repeatability."
            ),
        },
        "interpretation": {
            "device_pair": (
                "Low-reliability pair differences are not device performance conclusions."
            ),
            "speech_metrics": (
                "Read-only descriptive columns are joined without correlations, causality, or significance tests."
            ),
            "human_annotations": annotations["interpretation_rules"],
        },
        "limitations": LIMITATIONS,
        "error": None,
    }
    quality_payload = {
        "schema_version": "1.0",
        "session_id": manifest.get("session_id", "SESSION001"),
        "cause_counts": summary["quality_cause_counts"],
        "files": quality_rows,
        "human_annotation_context": annotations,
        "interpretation": (
            "Quality and annotation links are diagnostic references only. "
            "They do not confirm pitch correctness or produce a score."
        ),
        "limitations": LIMITATIONS,
        "error": None,
    }
    atomic_json(summary_json_path, payload)
    atomic_csv(summary_csv_path, _summary_rows(summary), SUMMARY_FIELDS)
    atomic_csv(pair_csv_path, pair_rows, PAIR_FIELDS)
    atomic_csv(
        repeatability_csv_path, repeatability, REPEATABILITY_FIELDS
    )
    atomic_json(quality_json_path, quality_payload)
    atomic_csv(quality_csv_path, quality_rows, QUALITY_FIELDS)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--speech-metrics-summary", type=Path, required=True)
    parser.add_argument("--human-review", type=Path, required=True)
    parser.add_argument(
        "--human-annotation-comparison", type=Path, required=True
    )
    parser.add_argument("--relative-root", type=Path, required=True)
    parser.add_argument("--summary-json-output", type=Path, required=True)
    parser.add_argument("--summary-csv-output", type=Path, required=True)
    parser.add_argument("--pair-csv-output", type=Path, required=True)
    parser.add_argument("--repeatability-csv-output", type=Path, required=True)
    parser.add_argument("--quality-json-output", type=Path, required=True)
    parser.add_argument("--quality-csv-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = compare_session(
            args.manifest,
            args.speech_metrics_summary,
            args.human_review,
            args.human_annotation_comparison,
            args.relative_root,
            args.summary_json_output,
            args.summary_csv_output,
            args.pair_csv_output,
            args.repeatability_csv_output,
            args.quality_json_output,
            args.quality_csv_output,
        )
    except SessionProsodyV21Error as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "SESSION_PROSODY_V21_FAILED",
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
