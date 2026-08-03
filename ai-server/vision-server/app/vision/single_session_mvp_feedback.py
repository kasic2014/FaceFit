"""Stage 22 single-Session, baseline-relative Vision MVP feedback.

The service reuses validated Stage 7-10 and Stage 15-17 artifacts. It produces
measurement observations and within-Session numeric comparisons only. It does
not interpolate missing values, create thresholds or scores, infer psychology,
call an LLM, train a model, or freeze a dataset.
"""

from __future__ import annotations

import copy
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.vision.data_collection_validator import load_strict_jsonl
from app.vision.metric_registry import (
    FaceFitMetricRegistry,
    MetricDefinition,
    build_stage10_metric_registry,
)
from app.vision.pilot_video_intake import (
    ensure_finite,
    load_strict_json,
    sha256_file,
    write_strict_json,
)


SCHEMA_VERSION = "1.0.0"
STAGE = 22
ANALYSIS_MODE = "SINGLE_SESSION_BASELINE_RELATIVE_MVP"
ANALYSIS_SCOPE = "FACE_AND_BOTH_SHOULDERS"
EXPECTED_PARTICIPANT_ID = "PTC_000001"
EXPECTED_SESSION_ID = "SES_000001"
EXPECTED_ANSWER_IDS = (
    "ANS_000001",
    "ANS_000002",
    "ANS_000003",
    "ANS_000004",
)
AVAILABILITY_STATES = frozenset(
    {"COMPLETE", "PARTIAL", "UNAVAILABLE", "NOT_APPLICABLE"}
)
RESULT_READY = "single_session_mvp_feedback_ready"
RESULT_LIMITED = "single_session_mvp_feedback_ready_with_measurement_limitations"
RESULT_UNAVAILABLE = "single_session_mvp_feedback_unavailable"
RESULT_INPUT_FAILED = "single_session_mvp_input_validation_failed"
RESULT_STATUSES = frozenset(
    {RESULT_READY, RESULT_LIMITED, RESULT_UNAVAILABLE, RESULT_INPUT_FAILED}
)
SCORING_REASONS = (
    "SCORING_NOT_AVAILABLE_SINGLE_SESSION_MVP",
    "THRESHOLD_EVIDENCE_NOT_APPROVED",
)
DISCLAIMER = (
    "본 결과는 단일 파일럿 세션에서 측정한 값과 해당 세션의\n"
    "Baseline 대비 상대 변화에 기반한 개발용 참고 정보입니다.\n\n"
    "채용 평가, 합격 가능성, 성격, 자신감, 불안감, 집중력 또는\n"
    "심리 상태를 판단하지 않습니다.\n\n"
    "일부 프레임에서 측정값을 계산하지 못한 경우 해당 값은\n"
    "보간하거나 임의 값으로 대체하지 않았습니다."
)
HEAD_PARTIAL_WARNINGS = (
    "일부 프레임에서 고개 방향 측정값을 계산하지 못해 결과가 제한적입니다.",
    "측정되지 않은 구간은 보간하거나 임의 값으로 대체하지 않았습니다.",
)
LIMITATIONS = (
    "단일 세션 내부 Baseline 대비 상대 변화만 제공합니다.",
    "절대적인 정상·비정상 또는 면접 품질을 판정하지 않습니다.",
    "Head Pose 값은 카메라 설정에 의존하는 근사 측정값입니다.",
    "얼굴·코·귀·양쪽 어깨 범위만 사용하며 전신 자세를 측정하지 않습니다.",
)
OUTPUT_NAMES = (
    "single_session_mvp_feedback.json",
    "answer_feedback.json",
    "measurement_availability.json",
    "within_session_comparison.json",
    "mvp_feedback_api_contract.json",
    "feedback_status.json",
    "validation_report.json",
    "validation_report.md",
)
ALLOWED_STATISTICS = (
    "count",
    "minimum",
    "maximum",
    "mean",
    "median",
    "standard_deviation",
    "absolute_mean",
    "absolute_median",
    "absolute_p95",
)
PERCENTILE_KEYS = ("p05", "p25", "p75", "p95")


class SingleSessionMvpError(ValueError):
    """Raised when protected Stage inputs violate the MVP contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _fail(message: str) -> None:
    raise SingleSessionMvpError(RESULT_INPUT_FAILED, message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _finite_number(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        _fail(f"{field} must be finite")
    return float(value)


def _path_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            return None
        current = current[component]
    return current


def _resolve_stage_report(session_root: Path, stage_name: str) -> Path:
    stage_root = session_root / stage_name
    _require(stage_root.is_dir(), f"required Stage directory missing: {stage_name}")
    reports = sorted(
        path
        for path in stage_root.glob("*/validation_report.json")
        if not path.parent.name.startswith(".")
    )
    _require(
        len(reports) == 1,
        f"{stage_name} must resolve to exactly one official report",
    )
    return reports[0]


def _resolve_report_output(
    report_path: Path,
    report: dict[str, Any],
    output_key: str,
) -> Path:
    outputs = report.get("outputs")
    _require(isinstance(outputs, dict), f"{report_path.name} outputs missing")
    filename = outputs.get(output_key)
    _require(
        isinstance(filename, str)
        and filename
        and Path(filename).name == filename,
        f"invalid official output resolver key: {output_key}",
    )
    resolved = report_path.parent / filename
    _require(resolved.is_file(), f"resolved input missing: {output_key}")
    return resolved


@dataclass(frozen=True)
class SingleSessionInputs:
    participant_id: str
    session_id: str
    paths: dict[str, Path]
    documents: dict[str, dict[str, Any]]
    rows: dict[str, tuple[dict[str, Any], ...]]
    source_hashes: dict[str, str]


def load_single_session_inputs(
    vision_root: str | Path,
    *,
    participant_id: str = EXPECTED_PARTICIPANT_ID,
    session_id: str = EXPECTED_SESSION_ID,
) -> SingleSessionInputs:
    """Resolve and strictly load the existing official Stage artifacts."""

    root = Path(vision_root)
    session_root = (
        root
        / "data"
        / "output"
        / "pilot_video_intake_validation"
        / session_id
    )
    stage_reports = {
        stage: _resolve_stage_report(session_root, stage)
        for stage in (
            "stage7_head_pose",
            "stage8_posture_raw",
            "stage9_baseline_relative",
            "stage10_intervals",
        )
    }
    documents: dict[str, dict[str, Any]] = {
        "stage15_report": load_strict_json(session_root / "validation_report.json"),
        "manual_review": load_strict_json(
            root
            / "data"
            / "output"
            / "pilot_manual_review"
            / session_id
            / "manual_review_decision.json"
        ),
        "annotation_ready": load_strict_json(
            root
            / "data"
            / "output"
            / "pilot_manual_review"
            / session_id
            / "annotation_ready_manifest.json"
        ),
    }
    paths: dict[str, Path] = {
        "stage15_report": session_root / "validation_report.json",
        "manual_review": (
            root
            / "data"
            / "output"
            / "pilot_manual_review"
            / session_id
            / "manual_review_decision.json"
        ),
        "annotation_ready": (
            root
            / "data"
            / "output"
            / "pilot_manual_review"
            / session_id
            / "annotation_ready_manifest.json"
        ),
    }
    for stage, report_path in stage_reports.items():
        key = f"{stage}_report"
        paths[key] = report_path
        documents[key] = load_strict_json(report_path)

    annotation_ready = documents["annotation_ready"]
    video_info = annotation_ready.get("video")
    _require(isinstance(video_info, dict), "Annotation Ready video reference missing")
    video_filename = video_info.get("filename")
    _require(
        isinstance(video_filename, str)
        and Path(video_filename).name == video_filename,
        "Annotation Ready video filename invalid",
    )
    incoming = root / "data" / "pilot" / "incoming"
    video_path = incoming / video_filename
    metadata_path = incoming / f"{Path(video_filename).stem}.metadata.json"
    _require(video_path.is_file(), "source video missing")
    _require(metadata_path.is_file(), "source Metadata missing")
    paths["video"] = video_path
    paths["metadata"] = metadata_path
    documents["metadata"] = load_strict_json(metadata_path)

    stage7 = documents["stage7_head_pose_report"]
    stage8 = documents["stage8_posture_raw_report"]
    stage9 = documents["stage9_baseline_relative_report"]
    stage10 = documents["stage10_intervals_report"]
    resolved = {
        "head_pose_raw": _resolve_report_output(
            paths["stage7_head_pose_report"],
            stage7,
            "frame_head_pose_metrics_jsonl",
        ),
        "posture_raw": _resolve_report_output(
            paths["stage8_posture_raw_report"],
            stage8,
            "frame_posture_metrics_jsonl",
        ),
        "baseline": _resolve_report_output(
            paths["stage9_baseline_relative_report"],
            stage9,
            "baseline_json",
        ),
        "relative_features": _resolve_report_output(
            paths["stage9_baseline_relative_report"],
            stage9,
            "relative_features_jsonl",
        ),
        "interval_aggregates": _resolve_report_output(
            paths["stage10_intervals_report"],
            stage10,
            "interval_aggregates_jsonl",
        ),
        "interval_definitions": _resolve_report_output(
            paths["stage10_intervals_report"],
            stage10,
            "interval_definitions_json",
        ),
    }
    paths.update(resolved)
    documents["baseline"] = load_strict_json(paths["baseline"])
    documents["interval_definitions"] = load_strict_json(
        paths["interval_definitions"]
    )
    rows = {
        "head_pose_raw": load_strict_jsonl(paths["head_pose_raw"]),
        "posture_raw": load_strict_jsonl(paths["posture_raw"]),
        "relative_features": load_strict_jsonl(paths["relative_features"]),
        "interval_aggregates": load_strict_jsonl(paths["interval_aggregates"]),
    }
    for collection in rows.values():
        ensure_finite(list(collection))
    source_hashes = {
        name: sha256_file(path)
        for name, path in sorted(paths.items())
    }
    return SingleSessionInputs(
        participant_id,
        session_id,
        paths,
        documents,
        rows,
        source_hashes,
    )


def validate_single_session_inputs(
    inputs: SingleSessionInputs,
    *,
    expected_participant_id: str = EXPECTED_PARTICIPANT_ID,
    expected_session_id: str = EXPECTED_SESSION_ID,
    expected_answer_ids: tuple[str, ...] = EXPECTED_ANSWER_IDS,
) -> dict[str, Any]:
    """Validate cross-Stage identity, SHA, interval, and metric contracts."""

    _require(
        inputs.participant_id == expected_participant_id,
        "participant_id mismatch",
    )
    _require(inputs.session_id == expected_session_id, "session_id mismatch")
    docs = inputs.documents
    metadata = docs["metadata"]
    stage15 = docs["stage15_report"]
    ready = docs["annotation_ready"]
    manual = docs["manual_review"]
    baseline = docs["baseline"]
    definitions = docs["interval_definitions"]
    _require(
        metadata.get("participant_id") == expected_participant_id
        and metadata.get("session_id") == expected_session_id,
        "Metadata identity mismatch",
    )
    _require(
        ready.get("participant_id") == expected_participant_id
        and ready.get("session_id") == expected_session_id,
        "Annotation Ready identity mismatch",
    )
    _require(ready.get("split_name") == "DEVELOPMENT", "Split mismatch")
    _require(
        manual.get("participant_id") == expected_participant_id
        and manual.get("session_id") == expected_session_id
        and manual.get("decision") == "APPROVED_FOR_ANNOTATION",
        "Manual Review is not approved",
    )
    _require(
        ready.get("final_status") == "pilot_video_annotation_ready",
        "Session is not Annotation Ready",
    )
    video_sha = inputs.source_hashes["video"]
    expected_shas = {
        metadata.get("expected_sha256"),
        stage15.get("video_metadata", {}).get("sha256"),
        ready.get("video", {}).get("sha256"),
    }
    for stage in (
        "stage7_head_pose_report",
        "stage8_posture_raw_report",
        "stage9_baseline_relative_report",
        "stage10_intervals_report",
    ):
        report = docs[stage]
        _require(report.get("status") == "completed", f"{stage} is not completed")
        expected_shas.add(report.get("source", {}).get("sha256"))
    _require(expected_shas == {video_sha}, "video SHA mismatch across Stages")

    baseline_interval = ready.get("baseline_interval")
    _require(isinstance(baseline_interval, dict), "Baseline interval missing")
    _require(
        baseline_interval.get("start_timestamp_ms")
        < baseline_interval.get("end_timestamp_ms"),
        "Baseline interval invalid",
    )
    _require(
        baseline.get("available") is True
        and baseline.get("status") == "COMPLETED"
        and baseline.get("collection_start_ms")
        == baseline_interval.get("start_timestamp_ms")
        and baseline.get("collection_end_ms")
        == baseline_interval.get("end_timestamp_ms"),
        "Baseline model mismatch",
    )
    answers = ready.get("answer_intervals")
    _require(isinstance(answers, list) and len(answers) == 4, "four Answers required")
    answer_ids = tuple(item.get("answer_id") for item in answers)
    _require(answer_ids == expected_answer_ids, "Answer IDs mismatch")
    previous_end = -1
    interval_map: dict[str, dict[str, Any]] = {}
    for answer in answers:
        start = answer.get("start_timestamp_ms")
        end = answer.get("end_timestamp_ms")
        _require(
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and start < end,
            "Answer interval invalid",
        )
        _require(start >= previous_end, "Answer intervals overlap")
        previous_end = end
        interval_map[answer["interval_id"]] = answer
    _require(
        definitions.get("inclusion_rule")
        == "start_timestamp_ms <= timestamp_ms < end_timestamp_ms",
        "Stage 10 interval rule mismatch",
    )
    definition_rows = definitions.get("intervals")
    _require(
        isinstance(definition_rows, list)
        and len(definition_rows) == 4,
        "Stage 10 interval definitions missing",
    )
    for definition in definition_rows:
        answer = interval_map.get(definition.get("interval_id"))
        _require(answer is not None, "Stage 10 interval reference mismatch")
        _require(
            definition.get("interval_type") == "ANSWER"
            and definition.get("start_timestamp_ms")
            == answer.get("start_timestamp_ms")
            and definition.get("end_timestamp_ms")
            == answer.get("end_timestamp_ms"),
            "Stage 10 interval boundary mismatch",
        )
    aggregates = inputs.rows["interval_aggregates"]
    _require(len(aggregates) == 4, "Stage 10 Answer aggregates missing")
    _require(
        {row.get("interval_id") for row in aggregates} == set(interval_map),
        "Stage 10 aggregate references mismatch",
    )
    registry = build_stage10_metric_registry()
    for row in aggregates:
        registry.validate_paths(row)
    _require(bool(inputs.rows["head_pose_raw"]), "Head Pose RAW missing")
    _require(bool(inputs.rows["posture_raw"]), "Posture RAW missing")
    _require(bool(inputs.rows["relative_features"]), "relative features missing")
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "valid": True,
        "participant_id": expected_participant_id,
        "session_id": expected_session_id,
        "video_sha256": video_sha,
        "interval_rule": "[start, end)",
        "answer_count": 4,
        "head_pose_raw_row_count": len(inputs.rows["head_pose_raw"]),
        "posture_raw_row_count": len(inputs.rows["posture_raw"]),
        "relative_feature_row_count": len(inputs.rows["relative_features"]),
        "interval_aggregate_count": len(aggregates),
        "manual_review_decision": manual["decision"],
        "annotation_ready_status": ready["final_status"],
        "official_metric_ids": [
            definition.metric_id for definition in registry.definitions
        ],
    }
    ensure_finite(report)
    return report


def classify_availability(
    available_sample_count: int,
    total_sample_count: int,
    *,
    applicable: bool = True,
) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if (
        isinstance(available_sample_count, bool)
        or isinstance(total_sample_count, bool)
        or not isinstance(available_sample_count, int)
        or not isinstance(total_sample_count, int)
        or available_sample_count < 0
        or total_sample_count < 0
        or available_sample_count > total_sample_count
    ):
        raise ValueError("invalid structural availability counts")
    if total_sample_count == 0 or available_sample_count == 0:
        return "UNAVAILABLE"
    if available_sample_count == total_sample_count:
        return "COMPLETE"
    return "PARTIAL"


def _availability(value: dict[str, Any]) -> dict[str, Any]:
    total = value.get("total_frame_count")
    available = value.get("valid_frame_count")
    missing = value.get("invalid_frame_count")
    longest = value.get("longest_missing_duration_ms")
    _require(
        isinstance(total, int)
        and isinstance(available, int)
        and isinstance(missing, int)
        and isinstance(longest, int)
        and total == available + missing,
        "invalid Stage 10 availability counts",
    )
    ratio = _finite_number(value.get("availability_ratio"), "availability_ratio")
    expected_ratio = available / total if total else 0.0
    _require(
        math.isclose(ratio, expected_ratio, rel_tol=0.0, abs_tol=1e-12),
        "availability ratio mismatch",
    )
    reason_counts = value.get("failure_reason_counts")
    _require(isinstance(reason_counts, dict), "failure reason counts missing")
    result = {
        "status": classify_availability(available, total),
        "available_sample_count": available,
        "total_sample_count": total,
        "availability_ratio": ratio,
        "missing_sample_count": missing,
        "longest_missing_gap_ms": longest,
        "failure_codes": sorted(
            code
            for code, count in reason_counts.items()
            if isinstance(code, str) and isinstance(count, int) and count > 0
        ),
        "imputation_performed": False,
    }
    ensure_finite(result)
    return result


def _combined_status(values: list[str]) -> str:
    _require(
        bool(values) and all(value in AVAILABILITY_STATES for value in values),
        "invalid availability state",
    )
    applicable = [value for value in values if value != "NOT_APPLICABLE"]
    if not applicable:
        return "NOT_APPLICABLE"
    if all(value == "COMPLETE" for value in applicable):
        return "COMPLETE"
    if all(value == "UNAVAILABLE" for value in applicable):
        return "UNAVAILABLE"
    return "PARTIAL"


def _metric_statistics(
    row: dict[str, Any],
    definition: MetricDefinition,
    availability: dict[str, Any],
) -> dict[str, Any] | None:
    if definition.data_quality_metric:
        return None
    parent_path = definition.metric_path.rsplit(".", 1)[0]
    summary = _path_value(row, parent_path)
    if not isinstance(summary, dict):
        return None
    result: dict[str, Any] = {}
    for key in ALLOWED_STATISTICS:
        value = summary.get(key)
        if value is None:
            result[key] = None
        elif key == "count":
            _require(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0,
                f"{definition.metric_id} count invalid",
            )
            result[key] = value
        else:
            result[key] = _finite_number(value, f"{definition.metric_id}.{key}")
    percentiles: dict[str, float | None] = {}
    for key in PERCENTILE_KEYS:
        value = summary.get(key)
        percentiles[key] = (
            None
            if value is None
            else _finite_number(value, f"{definition.metric_id}.{key}")
        )
    result["percentiles"] = percentiles
    minimum = result.get("minimum")
    maximum = result.get("maximum")
    result["range"] = (
        None
        if minimum is None or maximum is None
        else float(maximum) - float(minimum)
    )
    result["availability"] = dict(availability)
    ensure_finite(result)
    return result


def _resolved_metrics(
    row: dict[str, Any],
    registry: FaceFitMetricRegistry,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for definition in registry.definitions:
        resolution = registry.resolve(row, definition.metric_id)
        availability_value = _path_value(
            row, definition.required_availability_group
        )
        availability = (
            _availability(availability_value)
            if isinstance(availability_value, dict)
            and all(
                key in availability_value
                for key in (
                    "total_frame_count",
                    "valid_frame_count",
                    "invalid_frame_count",
                    "longest_missing_duration_ms",
                    "failure_reason_counts",
                )
            )
            else {
                "status": (
                    "COMPLETE" if resolution.availability_ratio == 1.0
                    else "PARTIAL" if resolution.availability_ratio > 0.0
                    else "UNAVAILABLE"
                ),
                "available_sample_count": round(
                    row.get("data_quality", {}).get("total_frame_count", 0)
                    * resolution.availability_ratio
                ),
                "total_sample_count": (
                    row.get("data_quality", {}).get("total_frame_count", 0)
                ),
                "availability_ratio": resolution.availability_ratio,
                "missing_sample_count": max(
                    0,
                    row.get("data_quality", {}).get("total_frame_count", 0)
                    - round(
                        row.get("data_quality", {}).get(
                            "total_frame_count", 0
                        )
                        * resolution.availability_ratio
                    ),
                ),
                "longest_missing_gap_ms": resolution.longest_missing_duration_ms,
                "failure_codes": (
                    [] if resolution.failure_reason is None
                    else [resolution.failure_reason]
                ),
                "imputation_performed": False,
            }
        )
        item = {
            "metric_id": definition.metric_id,
            "source_stage": definition.source_stage,
            "unit": definition.unit,
            "description": definition.description,
            "baseline_relative": definition.supports_relative_value,
            "resolved_value": resolution.value,
            "resolved_statistic": definition.metric_path.rsplit(".", 1)[-1],
            "available": resolution.available,
            "failure_reason": resolution.failure_reason,
            "statistics": _metric_statistics(row, definition, availability),
            "availability": availability,
        }
        ensure_finite(item)
        result[definition.metric_id] = item
    return result


def build_answer_feedback(
    inputs: SingleSessionInputs,
) -> list[dict[str, Any]]:
    """Build deterministic per-Answer measurement feedback."""

    ready_answers = inputs.documents["annotation_ready"]["answer_intervals"]
    answer_by_interval = {
        answer["interval_id"]: answer for answer in ready_answers
    }
    registry = build_stage10_metric_registry()
    answers: list[dict[str, Any]] = []
    for row in sorted(
        inputs.rows["interval_aggregates"],
        key=lambda value: value["start_timestamp_ms"],
    ):
        answer = answer_by_interval[row["interval_id"]]
        face = _availability(row["posture"]["face_alignment_availability"])
        shoulders = _availability(row["posture"]["shoulder_availability"])
        head = _availability(row["head_pose"]["availability"])
        nose = _availability(row["posture"]["nose_alignment_availability"])
        posture_status = _combined_status(
            [shoulders["status"], nose["status"], face["status"]]
        )
        observations = [
            {
                "type": "MEASUREMENT_OBSERVATION",
                "code": "BASELINE_RELATIVE_VALUES",
                "message": (
                    "측정값은 현재 세션의 Baseline과 비교한 변화량으로 "
                    "제공됩니다."
                ),
            }
        ]
        if face["status"] == "COMPLETE" and shoulders["status"] == "COMPLETE":
            observations.append(
                {
                    "type": "MEASUREMENT_OBSERVATION",
                    "code": "FACE_AND_BOTH_SHOULDERS_COMPLETE",
                    "message": (
                        "얼굴과 양쪽 어깨가 전체 분석 프레임에서 "
                        "검출되었습니다."
                    ),
                }
            )
        warnings: list[str] = []
        if head["status"] == "PARTIAL":
            warnings.extend(HEAD_PARTIAL_WARNINGS)
            observations.append(
                {
                    "type": "MEASUREMENT_LIMITATION",
                    "code": "HEAD_POSE_PARTIAL",
                    "message": HEAD_PARTIAL_WARNINGS[0],
                }
            )
        result_status = (
            "MEASUREMENTS_AVAILABLE"
            if all(
                value == "COMPLETE"
                for value in (
                    face["status"],
                    shoulders["status"],
                    head["status"],
                    posture_status,
                )
            )
            else "MEASUREMENT_LIMITATIONS_PRESENT"
        )
        total_samples = row["data_quality"]["total_frame_count"]
        item = {
            "answer_id": answer["answer_id"],
            "interval": {
                "interval_id": answer["interval_id"],
                "start_timestamp_ms": answer["start_timestamp_ms"],
                "end_timestamp_ms": answer["end_timestamp_ms"],
                "rule": "[start, end)",
            },
            "sample_count": total_samples,
            "face_detection": face,
            "both_shoulders_detection": shoulders,
            "head_pose_measurement": {
                "status": head["status"],
                "availability": head,
                "metric_ids": [
                    definition.metric_id
                    for definition in registry.definitions
                    if definition.metric_id.startswith("HEAD_")
                ],
                "imputation_performed": False,
            },
            "posture_measurement": {
                "status": posture_status,
                "shoulder_availability": shoulders,
                "nose_alignment_availability": nose,
                "face_alignment_availability": face,
                "metric_ids": [
                    definition.metric_id
                    for definition in registry.definitions
                    if definition.metric_id.startswith("POSTURE_")
                ],
                "analysis_scope": ANALYSIS_SCOPE,
            },
            "relative_metric_summary": _resolved_metrics(row, registry),
            "within_session_comparison": {},
            "observations": observations,
            "warnings": warnings,
            "result_status": result_status,
        }
        ensure_finite(item)
        answers.append(item)
    return answers


def _dense_rank(values: dict[str, float]) -> dict[str, int]:
    unique = sorted(set(values.values()))
    rank_by_value = {value: index + 1 for index, value in enumerate(unique)}
    return {key: rank_by_value[value] for key, value in values.items()}


def build_session_comparison(
    answer_feedback: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare official metric values within one Session without thresholds."""

    metric_ids = sorted(
        {
            metric_id
            for answer in answer_feedback
            for metric_id, value in answer["relative_metric_summary"].items()
            if value.get("baseline_relative") is True
        }
    )
    comparisons: dict[str, Any] = {}
    by_answer: dict[str, dict[str, Any]] = {
        answer["answer_id"]: {} for answer in answer_feedback
    }
    for metric_id in metric_ids:
        values: dict[str, float] = {}
        unit = None
        for answer in answer_feedback:
            summary = answer["relative_metric_summary"].get(metric_id)
            value = summary.get("resolved_value") if summary else None
            if value is None:
                continue
            values[answer["answer_id"]] = _finite_number(value, metric_id)
            unit = summary["unit"]
        if len(values) < 2:
            continue
        session_median = float(statistics.median(values.values()))
        minimum = min(values.values())
        maximum = max(values.values())
        ranks = _dense_rank(values)
        answer_values: dict[str, Any] = {}
        for answer_id, value in sorted(values.items()):
            item = {
                "value": value,
                "unit": unit,
                "dense_rank_ascending": ranks[answer_id],
                "is_session_minimum": value == minimum,
                "is_session_maximum": value == maximum,
                "difference_from_session_median": value - session_median,
                "comparison_answer_count": len(values),
                "quality_interpretation": False,
            }
            answer_values[answer_id] = item
            by_answer[answer_id][metric_id] = item
        comparisons[metric_id] = {
            "metric_id": metric_id,
            "unit": unit,
            "rank_method": "DENSE_ASCENDING_NUMERIC_ONLY",
            "session_minimum": minimum,
            "session_maximum": maximum,
            "session_median": session_median,
            "comparable_answer_count": len(values),
            "answer_values": answer_values,
            "interpretation": (
                "동일 세션의 Answer 간 수치 비교이며 품질 평가가 아닙니다."
            ),
        }
    result = {
        "comparison_scope": "WITHIN_SESSION_ONLY",
        "thresholds_used": False,
        "quality_evaluation": False,
        "metric_comparisons": comparisons,
        "by_answer": by_answer,
    }
    ensure_finite(result)
    return result


def _measurement_summary(answers: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "face_detection",
        "both_shoulders_detection",
        "head_pose_measurement",
        "posture_measurement",
    )
    status_counts: dict[str, dict[str, int]] = {}
    for field in fields:
        counts = {state: 0 for state in sorted(AVAILABILITY_STATES)}
        for answer in answers:
            counts[answer[field]["status"]] += 1
        status_counts[field] = counts
    metric_ids = sorted(
        {
            metric_id
            for answer in answers
            for metric_id in answer["relative_metric_summary"]
        }
    )
    return {
        "answer_count": len(answers),
        "sample_count": sum(answer["sample_count"] for answer in answers),
        "availability_status_counts": status_counts,
        "official_metric_ids": metric_ids,
        "baseline_relative_meaning": "현재 세션의 Baseline과 비교한 변화량",
        "thresholds_used": False,
        "scoring_performed": False,
    }


def _result_status(answers: list[dict[str, Any]]) -> str:
    core = [
        (
            answer["head_pose_measurement"]["status"],
            answer["posture_measurement"]["status"],
        )
        for answer in answers
    ]
    if all(
        head == "UNAVAILABLE" and posture == "UNAVAILABLE"
        for head, posture in core
    ):
        return RESULT_UNAVAILABLE
    required = [
        answer[field]["status"]
        for answer in answers
        for field in (
            "face_detection",
            "both_shoulders_detection",
            "head_pose_measurement",
            "posture_measurement",
        )
    ]
    if all(value == "COMPLETE" for value in required):
        return RESULT_READY
    return RESULT_LIMITED


def _apply_comparisons(
    answers: list[dict[str, Any]],
    comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    result = copy.deepcopy(answers)
    yaw_id = "HEAD_RELATIVE_YAW_ABS_P95_DEG"
    for answer in result:
        values = comparison["by_answer"].get(answer["answer_id"], {})
        answer["within_session_comparison"] = values
        yaw = values.get(yaw_id)
        if yaw and yaw["is_session_maximum"]:
            answer["observations"].append(
                {
                    "type": "WITHIN_SESSION_COMPARISON",
                    "code": "HEAD_RELATIVE_YAW_NUMERIC_MAXIMUM",
                    "message": (
                        "이 답변은 이번 세션의 다른 답변보다 yaw 상대 "
                        "변화 폭이 크게 관찰되었습니다."
                    ),
                }
            )
        elif yaw and yaw["is_session_minimum"]:
            answer["observations"].append(
                {
                    "type": "WITHIN_SESSION_COMPARISON",
                    "code": "HEAD_RELATIVE_YAW_NUMERIC_MINIMUM",
                    "message": (
                        "이 답변은 이번 세션의 다른 답변보다 yaw 상대 "
                        "변화 폭이 작게 관찰되었습니다."
                    ),
                }
            )
    return result


def _provenance(inputs: SingleSessionInputs) -> dict[str, Any]:
    registry = build_stage10_metric_registry()
    logical_hashes = {
        name: digest
        for name, digest in inputs.source_hashes.items()
        if name != "video"
    }
    return {
        "source_video_sha256": inputs.source_hashes["video"],
        "source_stages": ["STAGE_7", "STAGE_8", "STAGE_9", "STAGE_10",
                          "STAGE_15", "STAGE_16", "STAGE_17"],
        "official_metric_ids": [
            definition.metric_id for definition in registry.definitions
        ],
        "input_artifact_sha256": logical_hashes,
        "input_files_read_only": True,
        "missing_values_interpolated": False,
        "llm_used": False,
    }


def _snake_to_camel(key: str) -> str:
    if key.isupper() or "_" not in key:
        return key
    first, *rest = key.split("_")
    return first + "".join(part.capitalize() for part in rest)


def _camelize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            _snake_to_camel(str(key)): _camelize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def _api_contract(feedback: dict[str, Any]) -> dict[str, Any]:
    answers = [
        {
            key: value
            for key, value in answer.items()
            if key
            in {
                "answer_id",
                "interval",
                "sample_count",
                "face_detection",
                "both_shoulders_detection",
                "head_pose_measurement",
                "posture_measurement",
                "relative_metric_summary",
                "within_session_comparison",
                "observations",
                "warnings",
                "result_status",
            }
        }
        for answer in feedback["answer_feedback"]
    ]
    api = {
        "sessionId": feedback["session_id"],
        "status": feedback["result_status"],
        "analysisMode": feedback["analysis_mode"],
        "analysisScope": feedback["analysis_scope"],
        "operational": False,
        "scores": None,
        "scoreUnavailableReasons": list(SCORING_REASONS),
        "measurementSummary": _camelize(feedback["measurement_summary"]),
        "answers": _camelize(answers),
        "warnings": list(feedback["warnings"]),
        "limitations": list(feedback["limitations"]),
        "disclaimer": feedback["disclaimer"],
    }
    text = str(api)
    _require("participant_id" not in text, "API exposes participant_id")
    _require("\\data\\" not in text and "/data/" not in text, "API exposes paths")
    ensure_finite(api)
    return api


def build_single_session_mvp_feedback(
    inputs: SingleSessionInputs,
) -> dict[str, Any]:
    """Build the reusable internal and API response package."""

    validation = validate_single_session_inputs(
        inputs,
        expected_participant_id=inputs.participant_id,
        expected_session_id=inputs.session_id,
        expected_answer_ids=tuple(
            item["answer_id"]
            for item in inputs.documents["annotation_ready"]["answer_intervals"]
        ),
    )
    answers = build_answer_feedback(inputs)
    comparison = build_session_comparison(answers)
    answers = _apply_comparisons(answers, comparison)
    status = _result_status(answers)
    warnings = sorted(
        {
            warning
            for answer in answers
            for warning in answer["warnings"]
        }
    )
    feedback = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "session_id": inputs.session_id,
        "participant_id": inputs.participant_id,
        "analysis_mode": ANALYSIS_MODE,
        "analysis_scope": ANALYSIS_SCOPE,
        "operational": False,
        "result_status": status,
        "baseline_reference": {
            "interval_id": inputs.documents["annotation_ready"][
                "baseline_interval"
            ]["interval_id"],
            "start_timestamp_ms": inputs.documents["baseline"][
                "collection_start_ms"
            ],
            "end_timestamp_ms": inputs.documents["baseline"]["collection_end_ms"],
            "model_available": inputs.documents["baseline"]["available"],
            "meaning": "현재 세션의 Baseline과 비교한 변화량",
        },
        "measurement_summary": _measurement_summary(answers),
        "answer_feedback": answers,
        "session_comparison": comparison,
        "warnings": warnings,
        "limitations": list(LIMITATIONS),
        "disclaimer": DISCLAIMER,
        "provenance": _provenance(inputs),
    }
    api = _api_contract(feedback)
    package = {
        "feedback": feedback,
        "answer_feedback": {
            "session_id": inputs.session_id,
            "answers": answers,
        },
        "measurement_availability": {
            "session_id": inputs.session_id,
            "answers": [
                {
                    "answer_id": answer["answer_id"],
                    "face_detection": answer["face_detection"],
                    "both_shoulders_detection": answer[
                        "both_shoulders_detection"
                    ],
                    "head_pose_measurement": answer["head_pose_measurement"],
                    "posture_measurement": answer["posture_measurement"],
                }
                for answer in answers
            ],
        },
        "within_session_comparison": comparison,
        "api_contract": api,
        "feedback_status": {
            "session_id": inputs.session_id,
            "result_status": status,
            "operational": False,
            "scoring_performed": False,
            "scoring_unavailable_reasons": list(SCORING_REASONS),
            "threshold_created": False,
            "agreement_or_kappa_calculated": False,
            "missing_value_imputation_performed": False,
            "dataset_frozen": False,
        },
        "validation": validation,
    }
    ensure_finite(package)
    return package


def _verify_source_hashes(inputs: SingleSessionInputs) -> None:
    after = {
        name: sha256_file(path)
        for name, path in sorted(inputs.paths.items())
    }
    _require(after == inputs.source_hashes, "protected source hash changed")


def write_single_session_mvp_outputs(
    package: dict[str, Any],
    inputs: SingleSessionInputs,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write strict Stage 22 outputs without overwriting prior results."""

    destination = Path(output_dir)
    if destination.exists():
        _fail("refusing to overwrite Stage 22 MVP output")
    _verify_source_hashes(inputs)
    validation = {
        **package["validation"],
        "result_status": package["feedback"]["result_status"],
        "checks": {
            "existing_metric_resolver_reused": True,
            "baseline_and_answer_intervals_valid": True,
            "manual_review_approved": True,
            "annotation_ready": True,
            "availability_structural_only": True,
            "missing_values_interpolated": False,
            "threshold_created": False,
            "scoring_performed": False,
            "psychological_inference_performed": False,
            "llm_used": False,
            "api_contract_has_no_participant_or_internal_path": True,
            "strict_json_finite": True,
            "protected_source_hashes_unchanged": True,
            "dataset_frozen": False,
        },
        "protected_sources": [
            {
                "name": name,
                "sha256_before": digest,
                "sha256_after": digest,
            }
            for name, digest in sorted(inputs.source_hashes.items())
        ],
    }
    documents = {
        "single_session_mvp_feedback.json": package["feedback"],
        "answer_feedback.json": package["answer_feedback"],
        "measurement_availability.json": package["measurement_availability"],
        "within_session_comparison.json": package["within_session_comparison"],
        "mvp_feedback_api_contract.json": package["api_contract"],
        "feedback_status.json": package["feedback_status"],
        "validation_report.json": validation,
    }
    for value in documents.values():
        ensure_finite(value)
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in documents.items():
        write_strict_json(destination / name, value)
    feedback = package["feedback"]
    availability_lines = [
        (
            f"- {answer['answer_id']} Head Pose availability: "
            f"`{answer['head_pose_measurement']['availability']['availability_ratio']:.6f}` "
            f"({answer['head_pose_measurement']['status']})"
        )
        for answer in feedback["answer_feedback"]
    ]
    markdown = "\n".join(
        [
            "# Face-Fit Stage 22 Single-Session Vision MVP Feedback",
            "",
            f"- Session: `{feedback['session_id']}`",
            f"- Analysis mode: `{ANALYSIS_MODE}`",
            f"- Analysis scope: `{ANALYSIS_SCOPE}`",
            f"- Result: `{feedback['result_status']}`",
            "- Operational: `false`",
            "- Scores: `null`",
            "- Thresholds created: `false`",
            "- Missing values interpolated: `false`",
            "",
            "## Measurement availability",
            "",
            *availability_lines,
            "",
            "## 안내문",
            "",
            DISCLAIMER,
            "",
        ]
    )
    (destination / "validation_report.md").write_text(markdown, encoding="utf-8")
    _verify_source_hashes(inputs)
    missing = [name for name in OUTPUT_NAMES if not (destination / name).is_file()]
    _require(not missing, f"missing Stage 22 outputs: {missing}")
    return validation


def build_and_write_single_session_mvp_feedback(
    *,
    vision_root: str | Path,
    output_dir: str | Path,
    participant_id: str = EXPECTED_PARTICIPANT_ID,
    session_id: str = EXPECTED_SESSION_ID,
) -> dict[str, Any]:
    inputs = load_single_session_inputs(
        vision_root,
        participant_id=participant_id,
        session_id=session_id,
    )
    validate_single_session_inputs(
        inputs,
        expected_participant_id=participant_id,
        expected_session_id=session_id,
    )
    package = build_single_session_mvp_feedback(inputs)
    return write_single_session_mvp_outputs(package, inputs, output_dir)
