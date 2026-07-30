"""Compare SESSION001 speech metrics by device, repetition, and human notes."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analyze_prosody_session_speech_metrics import (
    SessionMetricsError,
    relative_path,
    strict_json_text,
)


PAIR_METRICS = (
    "audio_duration_sec",
    "speech_duration_sec",
    "speaking_ratio",
    "speech_rate_wpm",
    "pause_count",
    "total_pause_duration_sec",
    "max_pause_duration_sec",
    "long_pause_count",
    "probable_omitted_vocalization_count",
    "uncertain_gap_vocalization_count",
    "clipping_ratio",
    "noise_floor_dbfs",
)
REPEATABILITY_METRICS = (
    "speech_rate_wpm",
    "speaking_ratio",
    "total_pause_duration_sec",
    "max_pause_duration_sec",
    "long_pause_count",
    "probable_omitted_vocalization_count",
)
PAIR_FIELDS = (
    "capture_pair_key",
    "script_id",
    "recording_condition",
    "repetition_index",
    "metric",
    "pc_value",
    "phone_value",
    "absolute_difference",
    "relative_difference",
    "comparison_available",
    "warning",
)
SUMMARY_FIELDS = ("record_type", "group", "device_code", "metric", "value", "mad")
HUMAN_FIELDS = (
    "annotation_type",
    "capture_key",
    "script_id",
    "repetition_index",
    "target",
    "classification",
    "pc_value",
    "phone_value",
    "comparison_value",
    "validation_status",
    "experimental",
    "details",
)
ELONGATION_OUTLIER_RATIO = 1.5


def _load_json(path: Path | str) -> dict[str, Any]:
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionMetricsError(
            "SESSION_SPEECH_METRICS_FAILED",
            f"{type(exc).__name__}: {exc}",
        ) from exc
    if not isinstance(result, dict):
        raise SessionMetricsError("SESSION_SPEECH_METRICS_FAILED", str(path))
    return result


def load_metric_results(
    manifest_path: Path | str, relative_root: Path | str
) -> list[dict[str, Any]]:
    manifest = _load_json(manifest_path)
    root = Path(relative_root)
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != 24:
        raise SessionMetricsError(
            "SESSION_SPEECH_METRICS_FAILED", "Expected 24 manifest rows."
        )
    results = []
    for row in rows:
        if row.get("error_code"):
            continue
        results.append(_load_json(root / Path(row["output_json"])))
    return results


def metric_difference(
    pc_value: Any, phone_value: Any
) -> dict[str, Any]:
    if not isinstance(pc_value, (int, float)) or not isinstance(
        phone_value, (int, float)
    ):
        return {
            "pc_value": pc_value,
            "phone_value": phone_value,
            "absolute_difference": None,
            "relative_difference": None,
            "comparison_available": False,
            "warning": "comparison_unavailable",
        }
    absolute = abs(float(pc_value) - float(phone_value))
    denominator = max(abs(float(pc_value)), abs(float(phone_value)))
    return {
        "pc_value": pc_value,
        "phone_value": phone_value,
        "absolute_difference": absolute,
        "relative_difference": absolute / denominator if denominator else 0.0,
        "comparison_available": True,
        "warning": "",
    }


def build_pair_comparisons(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[result["capture_pair_key"]].append(result)
    rows: list[dict[str, Any]] = []
    valid_pairs = 0
    for key, pair in sorted(groups.items()):
        by_device = {row["device_code"]: row for row in pair}
        pc = by_device.get("DEV_PC_MIC_01")
        phone = by_device.get("DEV_PHONE_01")
        if len(pair) != 2 or pc is None or phone is None:
            continue
        valid_pairs += 1
        for metric in PAIR_METRICS:
            rows.append(
                {
                    "capture_pair_key": key,
                    "script_id": pc["script_id"],
                    "recording_condition": pc["recording_condition"],
                    "repetition_index": pc["repetition_index"],
                    "metric": metric,
                    **metric_difference(pc.get(metric), phone.get(metric)),
                }
            )
    return rows, valid_pairs


def median_mad(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    median = statistics.median(values)
    return median, statistics.median(abs(value - median) for value in values)


def build_repeatability(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[
            (
                result["script_id"],
                result["recording_condition"],
                result["device_code"],
            )
        ].append(result)
    output = []
    for key, rows in sorted(groups.items()):
        for metric in REPEATABILITY_METRICS:
            values = [
                float(row[metric])
                for row in rows
                if isinstance(row.get(metric), (int, float))
            ]
            median, mad = median_mad(values)
            output.append(
                {
                    "script_id": key[0],
                    "recording_condition": key[1],
                    "device_code": key[2],
                    "metric": metric,
                    "repetition_count": len(values),
                    "median": median,
                    "mad": mad,
                }
            )
    return output


def load_human_annotations(path: Path | str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error, UnicodeError) as exc:
        raise SessionMetricsError(
            "HUMAN_ANNOTATION_INVALID", f"{type(exc).__name__}: {exc}"
        ) from exc
    if len(rows) != 6:
        raise SessionMetricsError(
            "HUMAN_ANNOTATION_INVALID", f"Expected 6 rows, found {len(rows)}."
        )
    annotations = []
    for row in rows:
        note = row["human_transcript_note"]
        if "생략" in note:
            target = "문제의" if row["script_id"] == "SCRIPT001" else "프로"
            annotations.append(
                {
                    "annotation_type": "omission",
                    "capture_key": row["capture_key"],
                    "script_id": row["script_id"],
                    "repetition_index": row["repetition_index"],
                    "target": target,
                    "classification": "script_to_spoken_content_difference",
                }
            )
        if "침묵" in note:
            annotations.append(
                {
                    "annotation_type": "silence",
                    "capture_key": row["capture_key"],
                    "script_id": row["script_id"],
                    "repetition_index": row["repetition_index"],
                    "target": "공유한 뒤 -> 우선순위에 따라",
                    "classification": "human_pause_annotation",
                }
            )
        if "늘어짐" in note:
            target = "저장" if "'저장'" in note else "데이터가"
            annotations.append(
                {
                    "annotation_type": "elongation",
                    "capture_key": row["capture_key"],
                    "script_id": row["script_id"],
                    "repetition_index": row["repetition_index"],
                    "target": target,
                    "classification": "human_elongation_annotation",
                }
            )
    counts = Counter(item["annotation_type"] for item in annotations)
    return annotations, {
        "omission": counts["omission"],
        "silence": counts["silence"],
        "elongation": counts["elongation"],
        "filler": 0,
    }


def _clean_word(text: str) -> str:
    normalized = unicodedata.normalize("NFC", str(text)).strip()
    return "".join(
        char
        for char in normalized
        if not unicodedata.category(char).startswith("P")
    )


def _find_word(result: dict[str, Any], target: str) -> dict[str, Any] | None:
    for word in result["word_timestamps"]:
        if _clean_word(word.get("word", "")) == target:
            return word
    return None


def validate_silence_annotation(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = [
        row
        for row in results
        if row["script_id"] == "SCRIPT001"
        and row["recording_condition"] == "natural"
        and int(row["repetition_index"]) == 2
    ]
    device_results: dict[str, Any] = {}
    detected: dict[str, bool] = {}
    for result in selected:
        previous = _find_word(result, "뒤")
        following = _find_word(result, "우선순위에")
        if previous is None or following is None:
            device_results[result["device_code"]] = {
                "annotation_exists": True,
                "word_boundary": "뒤 -> 우선순위에",
                "previous_word_end": None,
                "next_word_start": None,
                "word_timestamp_gap": None,
                "acoustic_pause_candidate_exists": False,
                "pause_start": None,
                "pause_end": None,
                "pause_duration": None,
            }
            detected[result["device_code"]] = False
            continue
        gap = float(following["start"]) - float(previous["end"])
        candidate = next(
            (
                pause
                for pause in result["pause_events"]
                if pause["previous_word"] == "뒤"
                and pause["next_word"] == "우선순위에"
            ),
            None,
        )
        detected[result["device_code"]] = candidate is not None
        device_results[result["device_code"]] = {
            "annotation_exists": True,
            "word_boundary": "뒤 -> 우선순위에",
            "previous_word_end": previous["end"],
            "next_word_start": following["start"],
            "word_timestamp_gap": gap,
            "acoustic_pause_candidate_exists": candidate is not None,
            "pause_start": candidate["acoustic_silence_start_sec"]
            if candidate
            else None,
            "pause_end": candidate["acoustic_silence_end_sec"]
            if candidate
            else None,
            "pause_duration": candidate["acoustic_silence_duration_sec"]
            if candidate
            else None,
        }
    pc = detected.get("DEV_PC_MIC_01", False)
    phone = detected.get("DEV_PHONE_01", False)
    status = (
        "detected_by_both_devices"
        if pc and phone
        else "detected_pc_only"
        if pc
        else "detected_phone_only"
        if phone
        else "not_detected"
        if len(selected) == 2
        else "comparison_unavailable"
    )
    pc_duration = device_results.get("DEV_PC_MIC_01", {}).get("pause_duration")
    phone_duration = device_results.get("DEV_PHONE_01", {}).get("pause_duration")
    return {
        "annotation_type": "silence",
        "capture_key": "SPK001|SESSION001|SCRIPT001|natural|2",
        "target": "뒤 -> 우선순위에",
        "devices": device_results,
        "pc_phone_pause_duration_difference": (
            abs(pc_duration - phone_duration)
            if isinstance(pc_duration, (int, float))
            and isinstance(phone_duration, (int, float))
            else None
        ),
        "validation_status": status,
        "accuracy_or_recall_computed": False,
    }


def elongation_diagnostics(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    annotations = [
        ("SCRIPT002", 1, "저장"),
        ("SCRIPT002", 3, "데이터가"),
    ]
    output = []
    for script, annotated_rep, target in annotations:
        by_device: dict[str, Any] = {}
        all_found = True
        for device in ("DEV_PC_MIC_01", "DEV_PHONE_01"):
            durations: dict[str, float | None] = {}
            for repetition in (1, 2, 3):
                result = next(
                    (
                        row
                        for row in results
                        if row["script_id"] == script
                        and row["recording_condition"] == "natural"
                        and int(row["repetition_index"]) == repetition
                        and row["device_code"] == device
                    ),
                    None,
                )
                word = _find_word(result, target) if result else None
                durations[f"R{repetition:02d}"] = (
                    float(word["end"]) - float(word["start"])
                    if word
                    else None
                )
            values = [value for value in durations.values() if value is not None]
            median = statistics.median(values) if values else None
            annotated = durations[f"R{annotated_rep:02d}"]
            ratio = (
                annotated / median
                if isinstance(annotated, (int, float))
                and isinstance(median, (int, float))
                and median > 0
                else None
            )
            if annotated is None:
                all_found = False
            by_device[device] = {
                "word_durations_sec": durations,
                "three_repetition_median_sec": median,
                "annotated_to_median_ratio": ratio,
            }
        ratios = [
            data["annotated_to_median_ratio"]
            for data in by_device.values()
            if data["annotated_to_median_ratio"] is not None
        ]
        if not all_found:
            status = "timestamp_word_not_found"
        elif len(ratios) != 2:
            status = "comparison_unavailable"
        elif any(ratio >= ELONGATION_OUTLIER_RATIO for ratio in ratios):
            status = "duration_outlier_candidate"
        else:
            status = "duration_not_outlier"
        output.append(
            {
                "annotation_type": "elongation",
                "capture_key": f"SPK001|SESSION001|{script}|natural|{annotated_rep}",
                "target": target,
                "annotated_repetition": annotated_rep,
                "devices": by_device,
                "validation_status": status,
                "experimental": True,
                "experimental_threshold": (
                    "annotated word duration / three-repetition median >= 1.5"
                ),
                "interview_score_use": False,
            }
        )
    return output


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
        raise SessionMetricsError(
            "SPEECH_METRICS_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
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
                writer.writerow(formatted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, csv.Error) as exc:
        temporary.unlink(missing_ok=True)
        raise SessionMetricsError(
            "SPEECH_METRICS_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def compare_session(
    metrics_manifest_path: Path | str,
    human_review_path: Path | str,
    relative_root: Path | str,
    summary_json_path: Path | str,
    summary_csv_path: Path | str,
    pair_csv_path: Path | str,
    human_json_path: Path | str,
    human_csv_path: Path | str,
) -> dict[str, Any]:
    results = load_metric_results(metrics_manifest_path, relative_root)
    pair_rows, valid_pairs = build_pair_comparisons(results)
    repeatability = build_repeatability(results)
    annotations, annotation_counts = load_human_annotations(human_review_path)
    silence = validate_silence_annotation(results)
    elongations = elongation_diagnostics(results)
    summary = {
        "total_files": len(results),
        "successful_files": len(results),
        "failed_files": 24 - len(results),
        "pc_files": sum(row["device_code"] == "DEV_PC_MIC_01" for row in results),
        "phone_files": sum(
            row["device_code"] == "DEV_PHONE_01" for row in results
        ),
        "clean_files": sum(row["recording_condition"] == "clean" for row in results),
        "natural_files": sum(
            row["recording_condition"] == "natural" for row in results
        ),
        "total_pairs": 12,
        "valid_pairs": valid_pairs,
        "files_with_long_pause": sum(row["long_pause_count"] > 0 for row in results),
        "files_with_probable_vocalization": sum(
            row["probable_omitted_vocalization_count"] > 0 for row in results
        ),
        "files_with_uncertain_candidate": sum(
            row["uncertain_gap_vocalization_count"] > 0 for row in results
        ),
        "files_with_background_noise_warning": sum(
            row["background_noise_warning"] for row in results
        ),
        "files_with_clipping_warning": sum(
            "clipping_suspected"
            in row["existing_speech_metrics"]["audio_quality"]["reliability_flags"]
            for row in results
        ),
        "speech_rate_median_by_device": {
            device: statistics.median(
                row["speech_rate_wpm"]
                for row in results
                if row["device_code"] == device
            )
            for device in ("DEV_PC_MIC_01", "DEV_PHONE_01")
        },
        "pause_duration_median_by_device": {
            device: statistics.median(
                row["total_pause_duration_sec"]
                for row in results
                if row["device_code"] == device
            )
            for device in ("DEV_PC_MIC_01", "DEV_PHONE_01")
        },
        "pair_difference_median": {
            metric: median_mad(
                [
                    row["absolute_difference"]
                    for row in pair_rows
                    if row["metric"] == metric
                    and row["comparison_available"]
                ]
            )[0]
            for metric in PAIR_METRICS
        },
        "annotation_counts": annotation_counts,
        "silence_detection_status": silence["validation_status"],
        "elongation_diagnostic_status": {
            row["target"]: row["validation_status"] for row in elongations
        },
    }
    summary_rows = []
    for device, value in summary["speech_rate_median_by_device"].items():
        summary_rows.append(
            {
                "record_type": "device_summary",
                "group": "all",
                "device_code": device,
                "metric": "speech_rate_wpm_median",
                "value": value,
                "mad": "",
            }
        )
    for row in repeatability:
        summary_rows.append(
            {
                "record_type": "repeatability",
                "group": f"{row['script_id']}|{row['recording_condition']}",
                "device_code": row["device_code"],
                "metric": row["metric"],
                "value": row["median"],
                "mad": row["mad"],
            }
        )
    human_rows = [
        {
            **annotation,
            "pc_value": "",
            "phone_value": "",
            "comparison_value": "",
            "validation_status": (
                "content_difference_not_acoustic_event"
                if annotation["annotation_type"] == "omission"
                else silence["validation_status"]
                if annotation["annotation_type"] == "silence"
                else next(
                    row["validation_status"]
                    for row in elongations
                    if row["target"] == annotation["target"]
                )
            ),
            "experimental": annotation["annotation_type"] == "elongation",
            "details": "",
        }
        for annotation in annotations
    ]
    payload = {
        "schema_version": "1.0",
        "session_id": "SESSION001",
        "summary": summary,
        "repeatability": repeatability,
        "limitations": [
            "SPK001 한 명, 두 대본, 두 장치의 내부 파일럿이다.",
            "장치 차이와 세 번의 발화 반복 차이가 섞일 수 있다.",
            "Pause 후보는 filler를 의미하지 않는다.",
            "Speech rate에 보편적 정상 범위를 적용하지 않는다.",
            "통계적 유의성 검정, 면접 점수, 감점 기준을 생성하지 않는다.",
        ],
        "error": None,
    }
    human_payload = {
        "schema_version": "1.0",
        "annotation_counts": annotation_counts,
        "annotations": annotations,
        "silence_validation": silence,
        "elongation_diagnostics": elongations,
        "interpretation": {
            "omission": "대본 대비 실제 발화 내용 차이이며 음향 이벤트가 아니다.",
            "silence": "사람이 정확한 시간을 기록하지 않았으므로 timestamp accuracy나 recall을 계산하지 않는다.",
            "elongation": "Whisper word duration 기반 experimental 진단이며 자동 정답이나 점수가 아니다.",
            "filler": "사람 annotation 0건만으로 자동 후보 전체를 오탐으로 단정하지 않는다.",
        },
        "error": None,
    }
    _atomic_json(Path(summary_json_path), payload)
    _atomic_csv(Path(summary_csv_path), summary_rows, SUMMARY_FIELDS)
    _atomic_csv(Path(pair_csv_path), pair_rows, PAIR_FIELDS)
    _atomic_json(Path(human_json_path), human_payload)
    _atomic_csv(Path(human_csv_path), human_rows, HUMAN_FIELDS)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-manifest", type=Path, required=True)
    parser.add_argument("--human-review", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    parser.add_argument("--summary-json-output", type=Path, required=True)
    parser.add_argument("--summary-csv-output", type=Path, required=True)
    parser.add_argument("--pair-csv-output", type=Path, required=True)
    parser.add_argument("--human-json-output", type=Path, required=True)
    parser.add_argument("--human-csv-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = compare_session(
            args.metrics_manifest,
            args.human_review,
            args.relative_root,
            args.summary_json_output,
            args.summary_csv_output,
            args.pair_csv_output,
            args.human_json_output,
            args.human_csv_output,
        )
    except SessionMetricsError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "SESSION_SPEECH_METRICS_FAILED",
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
