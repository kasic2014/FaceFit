"""Aggregate human labels from a Face-Fit speech review manifest.

This tool reports descriptive counts and ratios only. It does not change audio
analysis thresholds, assign missing labels, calculate a score, or make a
deployment decision.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable


ALLOWED_LABELS = [
    "filler",
    "normal_speech",
    "breath",
    "noise",
    "silence",
    "whisper_hallucination",
    "unknown",
]

EVENT_TYPES = [
    "probable_omitted_vocalization",
    "uncertain_gap_vocalization",
    "pause",
    "long_silence",
    "hallucination_candidate",
]

REVIEW_ITEM_FIELDS = [
    "review_id",
    "event_type",
    "source_event_types",
    "original_start_sec",
    "original_end_sec",
    "reviewer_label",
    "reviewer_note",
    "classification",
    "candidate_reasons",
    "audio_quality_flags",
]

RESULT_CSV_FIELDS = ["section", "metric", "event_type", "reviewer_label", "value"]


class ReviewEvaluationError(Exception):
    """A classified review-label evaluation failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _empty_result(source_manifest: Path | str) -> dict[str, Any]:
    empty_by_label = {
        event_type: {
            **{label: 0 for label in ALLOWED_LABELS},
            "unreviewed": 0,
            "invalid_label": 0,
        }
        for event_type in EVENT_TYPES
    }
    return {
        "source_manifest": str(source_manifest),
        "schema_notes": {
            "primary_event": (
                "The representative event recorded in review item event_type."
            ),
            "source_event_membership": (
                "Original event memberships listed in source_event_types before merging; "
                "each review item is counted at most once per event type."
            ),
            "event_type_counts": (
                "Legacy alias using source event membership, retained for compatibility. "
                "Use primary_event_type_counts or source_event_membership_counts explicitly."
            ),
            "event_type_by_reviewer_label": (
                "Legacy alias using source event membership, retained for compatibility. "
                "Use primary_event_by_reviewer_label or "
                "source_event_membership_by_reviewer_label explicitly."
            ),
            "pause_evaluation": (
                "Legacy source-membership pause aggregation. "
                "pause_correct_silence_ratio must not be interpreted as correctness "
                "of primary pause classification."
            ),
        },
        "total_items": 0,
        "reviewed_items": 0,
        "unreviewed_items": 0,
        "invalid_label_items": 0,
        "review_completion_ratio": None,
        "label_counts": {label: 0 for label in ALLOWED_LABELS},
        "primary_event_type_counts": {
            event_type: 0 for event_type in EVENT_TYPES
        },
        "source_event_membership_counts": {
            event_type: 0 for event_type in EVENT_TYPES
        },
        "primary_event_by_reviewer_label": {
            event_type: dict(labels) for event_type, labels in empty_by_label.items()
        },
        "source_event_membership_by_reviewer_label": {
            event_type: dict(labels) for event_type, labels in empty_by_label.items()
        },
        "event_type_counts": {event_type: 0 for event_type in EVENT_TYPES},
        "event_type_by_reviewer_label": {
            event_type: dict(labels) for event_type, labels in empty_by_label.items()
        },
        "probable_evaluation": {},
        "uncertain_evaluation": {},
        "pause_evaluation": {},
        "primary_pause_evaluation": {},
        "pause_source_membership_evaluation": {},
        "deprecated_metrics": {
            "pause_correct_silence_ratio": {
                "deprecated": True,
                "reason": (
                    "Primary pause와 source pause membership이 혼합되어 해석이 모호함"
                ),
                "deprecation_reason": (
                    "Primary pause와 source pause membership이 혼합되어 해석이 모호함"
                ),
                "replacement_metrics": [
                    "primary_pause_evaluation.silence_ratio",
                    "pause_source_membership_evaluation.silence_ratio",
                ],
            }
        },
        "experiment_summary": {},
        "review_items": [],
        "experimental_interpretation": [],
        "warnings": [],
        "error": None,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _source_event_types_for_row(row: dict[str, str]) -> set[str]:
    values = {
        value.strip()
        for value in row.get("source_event_types", "").split(";")
        if value.strip()
    }
    if not values:
        event_type = row.get("event_type", "").strip()
        if event_type:
            values.add(event_type)
    return values


def _membership_evaluation_counts(
    items: list[dict[str, str]],
    membership: list[set[str]],
    event_type: str,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    selected = [item for item, types in zip(items, membership) if event_type in types]
    return selected, _label_counts(selected)


def _primary_evaluation_counts(
    items: list[dict[str, str]], event_type: str
) -> tuple[list[dict[str, str]], dict[str, int]]:
    selected = [
        item for item in items if item.get("event_type", "").strip() == event_type
    ]
    return selected, _label_counts(selected)


def _label_counts(selected: list[dict[str, str]]) -> dict[str, int]:
    valid = [item for item in selected if item["reviewer_label"] in ALLOWED_LABELS]
    counts = {
        label: sum(item["reviewer_label"] == label for item in valid)
        for label in ALLOWED_LABELS
    }
    counts["total"] = len(selected)
    counts["reviewed"] = len(valid)
    return counts


def _probable_evaluation(
    items: list[dict[str, str]],
) -> dict[str, Any]:
    _, counts = _primary_evaluation_counts(
        items, "probable_omitted_vocalization"
    )
    human_count = counts["filler"] + counts["normal_speech"] + counts["breath"]
    return {
        "probable_total": counts["total"],
        "probable_reviewed": counts["reviewed"],
        "probable_filler_count": counts["filler"],
        "probable_normal_speech_count": counts["normal_speech"],
        "probable_breath_count": counts["breath"],
        "probable_noise_count": counts["noise"],
        "probable_silence_count": counts["silence"],
        "probable_unknown_count": counts["unknown"],
        "probable_filler_ratio": _ratio(counts["filler"], counts["reviewed"]),
        "probable_human_vocalization_ratio": _ratio(human_count, counts["reviewed"]),
        "probable_silence_ratio": _ratio(counts["silence"], counts["reviewed"]),
        "probable_noise_false_positive_ratio": _ratio(counts["noise"], counts["reviewed"]),
        "evaluation_basis": "Primary event_type only.",
        "human_vocalization_definition": (
            "Experimental initial grouping: filler, normal_speech, and breath. "
            "It is not a finalized production definition."
        ),
    }


def _uncertain_evaluation(
    items: list[dict[str, str]],
) -> dict[str, Any]:
    _, counts = _primary_evaluation_counts(
        items, "uncertain_gap_vocalization"
    )
    human_count = counts["filler"] + counts["normal_speech"] + counts["breath"]
    return {
        "uncertain_total": counts["total"],
        "uncertain_reviewed": counts["reviewed"],
        "uncertain_filler_count": counts["filler"],
        "uncertain_normal_speech_count": counts["normal_speech"],
        "uncertain_breath_count": counts["breath"],
        "uncertain_noise_count": counts["noise"],
        "uncertain_unknown_count": counts["unknown"],
        "uncertain_noise_ratio": _ratio(counts["noise"], counts["reviewed"]),
        "uncertain_human_vocalization_ratio": _ratio(human_count, counts["reviewed"]),
        "evaluation_basis": (
            "Primary event_type and human reviewer labels only; "
            "source filenames are not used."
        ),
    }


def _pause_evaluation(
    items: list[dict[str, str]], membership: list[set[str]]
) -> dict[str, Any]:
    _, counts = _membership_evaluation_counts(items, membership, "pause")
    return {
        "pause_total": counts["total"],
        "pause_reviewed": counts["reviewed"],
        "pause_silence_count": counts["silence"],
        "pause_breath_count": counts["breath"],
        "pause_normal_speech_count": counts["normal_speech"],
        "pause_noise_count": counts["noise"],
        "pause_correct_silence_ratio": _ratio(counts["silence"], counts["reviewed"]),
    }


def _primary_pause_evaluation(items: list[dict[str, str]]) -> dict[str, Any]:
    _, counts = _primary_evaluation_counts(items, "pause")
    return {
        "total": counts["total"],
        "reviewed": counts["reviewed"],
        "silence_count": counts["silence"],
        "breath_count": counts["breath"],
        "noise_count": counts["noise"],
        "normal_speech_count": counts["normal_speech"],
        "filler_count": counts["filler"],
        "unknown_count": counts["unknown"],
        "silence_ratio": _ratio(counts["silence"], counts["reviewed"]),
        "breath_ratio": _ratio(counts["breath"], counts["reviewed"]),
    }


def _pause_source_membership_evaluation(
    items: list[dict[str, str]], membership: list[set[str]]
) -> dict[str, Any]:
    _, counts = _membership_evaluation_counts(items, membership, "pause")
    label_counts = {label: counts[label] for label in ALLOWED_LABELS}
    return {
        "item_count": counts["total"],
        "reviewed_item_count": counts["reviewed"],
        "label_counts": label_counts,
        "silence_ratio": _ratio(counts["silence"], counts["reviewed"]),
        "breath_ratio": _ratio(counts["breath"], counts["reviewed"]),
        "noise_ratio": _ratio(counts["noise"], counts["reviewed"]),
    }


def _experiment_summary(result: dict[str, Any]) -> dict[str, Any]:
    probable = result["probable_evaluation"]
    uncertain = result["uncertain_evaluation"]
    primary_pause = result["primary_pause_evaluation"]
    all_human_reviewed = (
        result["total_items"] > 0
        and result["total_items"] == result["reviewed_items"]
        and result["invalid_label_items"] == 0
    )
    if all_human_reviewed:
        ground_truth_status = "human_reviewed"
    elif result["reviewed_items"]:
        ground_truth_status = "partially_human_reviewed"
    else:
        ground_truth_status = "unreviewed"
    if (
        uncertain["uncertain_total"] > 0
        and uncertain["uncertain_noise_count"] == uncertain["uncertain_total"]
    ):
        uncertain_finding = (
            f"uncertain {uncertain['uncertain_total']}개는 모두 noise"
        )
    else:
        uncertain_finding = (
            f"uncertain {uncertain['uncertain_total']}개 중 noise "
            f"{uncertain['uncertain_noise_count']}개"
        )
    filler_finding = (
        "filler로 확인된 항목은 없음"
        if result["label_counts"]["filler"] == 0
        else f"filler로 확인된 항목은 {result['label_counts']['filler']}개"
    )
    return {
        "sample_size": result["total_items"],
        "ground_truth_status": ground_truth_status,
        "generalization_allowed": False,
        "findings": [
            (
                f"probable {probable['probable_total']}개 중 breath "
                f"{probable['probable_breath_count']}개, silence "
                f"{probable['probable_silence_count']}개"
            ),
            uncertain_finding,
            (
                f"독립 pause {primary_pause['total']}개 중 breath "
                f"{primary_pause['breath_count']}개"
            ),
            filler_finding,
        ],
        "limitations": [
            "단일 화자",
            "소수 표본",
            "제한된 녹음 장치",
            "환경 종류가 적음",
            "filler 정답 샘플이 검수 데이터에 없음",
        ],
    }


def _interpretation(result: dict[str, Any]) -> list[str]:
    probable = result["probable_evaluation"]
    uncertain = result["uncertain_evaluation"]
    statements = [
        (
            f"probable 후보 {probable['probable_total']}개 중 사람 발성으로 확인된 "
            f"항목은 {probable['probable_filler_count'] + probable['probable_normal_speech_count'] + probable['probable_breath_count']}개입니다."
        ),
        (
            f"probable 후보에서 filler로 확인된 항목은 "
            f"{probable['probable_filler_count']}개입니다."
        ),
        "probable이라는 명칭을 filler 확정으로 해석하면 안 됩니다.",
        (
            "현재 표본에서는 probable 후보가 주로 breath로 확인됐습니다."
        ),
    ]
    if uncertain["uncertain_noise_ratio"] is None:
        statements.append(
            "검수된 uncertain 후보가 없어 사람의 noise 라벨과 비교할 수 없습니다."
        )
    else:
        statements.append(
            f"이번 {uncertain['uncertain_reviewed']}개 표본에서는 uncertain 분류와 "
            "사람의 noise 라벨이 일치했습니다."
        )
    statements.append("표본이 너무 작아 일반적인 정확도로 확정할 수 없습니다.")
    if result["unreviewed_items"] or result["invalid_label_items"]:
        statements.append(
            "미검수 또는 잘못된 라벨 항목이 있어 사람 검수 집계가 불완전합니다."
        )
    return statements


def evaluate_speech_review_labels(manifest_path: Path | str) -> dict[str, Any]:
    """Read a reviewed CSV manifest and calculate descriptive aggregates."""
    path = Path(manifest_path)
    result = _empty_result(path)
    if not path.is_file():
        result["error"] = {
            "code": "REVIEW_MANIFEST_NOT_FOUND",
            "detail": str(path),
        }
        return result

    try:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames is None:
                    raise ReviewEvaluationError(
                        "REVIEW_MANIFEST_CSV_INVALID", "CSV header is missing."
                    )
                required = {"review_id", "event_type", "reviewer_label"}
                missing = sorted(required - set(reader.fieldnames))
                if missing:
                    raise ReviewEvaluationError(
                        "REVIEW_MANIFEST_CSV_INVALID",
                        "Missing required columns: " + ", ".join(missing),
                    )
                raw_rows = list(reader)
        except ReviewEvaluationError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ReviewEvaluationError(
                "REVIEW_MANIFEST_CSV_INVALID", f"{type(exc).__name__}: {exc}"
            ) from exc

        items: list[dict[str, str]] = []
        membership: list[set[str]] = []
        for row_index, row in enumerate(raw_rows, start=2):
            item = {field: (row.get(field) or "") for field in REVIEW_ITEM_FIELDS}
            item["reviewer_label"] = item["reviewer_label"].strip()
            primary_event_type = item["event_type"].strip()
            source_types = _source_event_types_for_row(item)
            all_types = set(source_types)
            if primary_event_type:
                all_types.add(primary_event_type)
            unknown_types = sorted(all_types - set(EVENT_TYPES))
            if unknown_types:
                result["warnings"].append(
                    {
                        "code": "UNKNOWN_EVENT_TYPE",
                        "row": row_index,
                        "review_id": item["review_id"],
                        "values": unknown_types,
                    }
                )
            valid_source_types = source_types & set(EVENT_TYPES)
            items.append(item)
            membership.append(valid_source_types)

            label = item["reviewer_label"]
            if not label:
                result["unreviewed_items"] += 1
                label_bucket = "unreviewed"
            elif label not in ALLOWED_LABELS:
                result["invalid_label_items"] += 1
                label_bucket = "invalid_label"
                result["warnings"].append(
                    {
                        "code": "INVALID_REVIEWER_LABEL",
                        "row": row_index,
                        "review_id": item["review_id"],
                        "value": label,
                    }
                )
            else:
                result["reviewed_items"] += 1
                result["label_counts"][label] += 1
                label_bucket = label

            if primary_event_type in EVENT_TYPES:
                result["primary_event_type_counts"][primary_event_type] += 1
                result["primary_event_by_reviewer_label"][primary_event_type][
                    label_bucket
                ] += 1
            for event_type in valid_source_types:
                result["source_event_membership_counts"][event_type] += 1
                result["source_event_membership_by_reviewer_label"][event_type][
                    label_bucket
                ] += 1

        result["review_items"] = items
        result["total_items"] = len(items)
        result["review_completion_ratio"] = _ratio(result["reviewed_items"], len(items))
        result["event_type_counts"] = dict(result["source_event_membership_counts"])
        result["event_type_by_reviewer_label"] = {
            event_type: dict(labels)
            for event_type, labels in result[
                "source_event_membership_by_reviewer_label"
            ].items()
        }
        result["probable_evaluation"] = _probable_evaluation(items)
        result["uncertain_evaluation"] = _uncertain_evaluation(items)
        result["pause_evaluation"] = _pause_evaluation(items, membership)
        result["primary_pause_evaluation"] = _primary_pause_evaluation(items)
        result["pause_source_membership_evaluation"] = (
            _pause_source_membership_evaluation(items, membership)
        )
        result["experiment_summary"] = _experiment_summary(result)
        result["experimental_interpretation"] = _interpretation(result)
    except ReviewEvaluationError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
    except Exception as exc:  # defensive CLI boundary
        result["error"] = {
            "code": "REVIEW_EVALUATION_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return result


def _validate_json_numbers(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NaN and Infinity are not allowed in evaluation output.")
    if isinstance(value, dict):
        for nested in value.values():
            _validate_json_numbers(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _validate_json_numbers(nested)


def write_json_result(path: Path | str, result: dict[str, Any]) -> None:
    output_path = Path(path)
    try:
        _validate_json_numbers(result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewEvaluationError(
            "EVALUATION_OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _result_csv_rows(result: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for metric, value in result["schema_notes"].items():
        yield {"section": "schema_notes", "metric": metric, "value": value}
    for metric in [
        "total_items",
        "reviewed_items",
        "unreviewed_items",
        "invalid_label_items",
        "review_completion_ratio",
    ]:
        yield {"section": "summary", "metric": metric, "value": result[metric]}
    for label, count in result["label_counts"].items():
        yield {
            "section": "label_counts",
            "metric": "count",
            "reviewer_label": label,
            "value": count,
        }
    for section in [
        "primary_event_type_counts",
        "source_event_membership_counts",
        "event_type_counts",
    ]:
        for event_type, count in result[section].items():
            yield {
                "section": section,
                "metric": "count",
                "event_type": event_type,
                "value": count,
            }
    for section in [
        "primary_event_by_reviewer_label",
        "source_event_membership_by_reviewer_label",
        "event_type_by_reviewer_label",
    ]:
        for event_type, labels in result[section].items():
            for label, count in labels.items():
                yield {
                    "section": section,
                    "metric": "count",
                    "event_type": event_type,
                    "reviewer_label": label,
                    "value": count,
                }
    for section in [
        "probable_evaluation",
        "uncertain_evaluation",
        "pause_evaluation",
        "primary_pause_evaluation",
        "pause_source_membership_evaluation",
    ]:
        for metric, value in result[section].items():
            yield {
                "section": section,
                "metric": metric,
                "value": (
                    json.dumps(value, ensure_ascii=False, allow_nan=False)
                    if isinstance(value, (dict, list))
                    else value
                ),
            }
    for metric_name, details in result["deprecated_metrics"].items():
        for detail_name, value in details.items():
            yield {
                "section": "deprecated_metrics",
                "metric": f"{metric_name}.{detail_name}",
                "value": (
                    json.dumps(value, ensure_ascii=False, allow_nan=False)
                    if isinstance(value, (dict, list))
                    else value
                ),
            }
    for metric, value in result["experiment_summary"].items():
        yield {
            "section": "experiment_summary",
            "metric": metric,
            "value": (
                json.dumps(value, ensure_ascii=False, allow_nan=False)
                if isinstance(value, (dict, list))
                else value
            ),
        }
    for index, statement in enumerate(result["experimental_interpretation"], start=1):
        yield {
            "section": "experimental_interpretation",
            "metric": f"statement_{index}",
            "value": statement,
        }


def write_csv_result(path: Path | str, result: dict[str, Any]) -> None:
    output_path = Path(path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=RESULT_CSV_FIELDS)
            writer.writeheader()
            for row in _result_csv_rows(result):
                writer.writerow(row)
    except (OSError, csv.Error) as exc:
        raise ReviewEvaluationError(
            "EVALUATION_OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewed_manifest_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    return parser


def _print_json(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = evaluate_speech_review_labels(args.reviewed_manifest_csv)
    if result["error"] is not None:
        _print_json(result)
        return 1
    try:
        write_json_result(args.output, result)
        write_csv_result(args.csv_output, result)
    except ReviewEvaluationError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
        _print_json(result)
        return 1
    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
