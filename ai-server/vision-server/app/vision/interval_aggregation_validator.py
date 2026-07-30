"""Strict file adapter and protected real-video smoke for interval aggregation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.core import config
from app.vision.interval_feature_aggregator import (
    IntervalAggregationError,
    aggregate_intervals,
)
from app.vision.interval_models import (
    AnalysisInterval,
    IntervalAggregationConfig,
    IntervalAggregationResult,
    IntervalType,
)
from app.vision.neutral_baseline_serializer import dumps_strict
from app.vision.video_loader import (
    calculate_video_sha256,
    create_safe_video_id,
    inspect_video_metadata,
)


EXPECTED_SOURCE_SHA256 = (
    "6cd4d7ac9d6dc546692d66c8c324dc7f09e1e20f5af846713bd1e119527bea32"
)
DEFAULT_INTERVAL_AGGREGATION_OUTPUT_ROOT = (
    config.OUTPUT_DIR / "interval_aggregation_validation"
)
PROTECTED_STAGE_ROOTS = (
    config.OUTPUT_DIR / "motion_validation",
    config.OUTPUT_DIR / "target_tracking_validation",
    config.OUTPUT_DIR / "head_pose_validation",
    config.OUTPUT_DIR / "posture_raw_validation",
    config.OUTPUT_DIR / "neutral_baseline_smoke",
)


class IntervalAggregationValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _protected_hashes(safe_id: str) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for root in PROTECTED_STAGE_ROOTS:
        directory = root / safe_id
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    result[path.resolve()] = _sha(path)
    return result


def load_strict_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(value)
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise IntervalAggregationValidationError(
            "INVALID_STRICT_JSON",
            f"{path.name}: {exc}",
        ) from exc


def load_strict_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise IntervalAggregationValidationError(
            "REQUIRED_INPUT_NOT_FOUND",
            f"Required input not found: {path}",
        )
    rows: list[dict[str, Any]] = []
    try:
        for line_number, text in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not text.strip():
                raise ValueError(f"blank line at {line_number}")
            value = json.loads(
                text,
                parse_constant=lambda constant: (_ for _ in ()).throw(
                    ValueError(constant)
                ),
            )
            if not isinstance(value, dict):
                raise ValueError(f"non-object line at {line_number}")
            rows.append(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise IntervalAggregationValidationError(
            "INVALID_STRICT_JSONL",
            f"{path.name}: {exc}",
        ) from exc
    if not rows:
        raise IntervalAggregationValidationError(
            "EMPTY_STRICT_JSONL",
            f"No rows in {path.name}",
        )
    return rows


def default_smoke_intervals(end_timestamp_ms: int) -> tuple[AnalysisInterval, ...]:
    if end_timestamp_ms <= 30_000:
        raise IntervalAggregationValidationError(
            "VIDEO_TOO_SHORT_FOR_SMOKE_INTERVALS",
            "The protected movement video must exceed 30 seconds",
        )
    boundaries = (0, 10_000, 20_000, 30_000, end_timestamp_ms)
    return tuple(
        AnalysisInterval(
            interval_id=f"INTERVAL_SMOKE_{index:03d}",
            start_timestamp_ms=start,
            end_timestamp_ms=end,
            interval_type=IntervalType.OTHER.value,
        )
        for index, (start, end) in enumerate(
            zip(boundaries, boundaries[1:]),
            start=1,
        )
    )


def parse_interval_definitions(path: str | Path) -> tuple[AnalysisInterval, ...]:
    payload = load_strict_json(Path(path).resolve())
    values = payload.get("intervals") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise IntervalAggregationValidationError(
            "INVALID_INTERVAL_DEFINITIONS",
            "Interval definitions must be a list or an object with intervals",
        )
    try:
        return tuple(AnalysisInterval(**value) for value in values)
    except (TypeError, ValueError) as exc:
        raise IntervalAggregationValidationError(
            "INVALID_INTERVAL_DEFINITIONS",
            str(exc),
        ) from exc


def _write_jsonl(
    path: Path,
    rows: Iterable[IntervalAggregationResult],
) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(dumps_strict(row))
            stream.write("\n")


def _annotate_frame_indices(
    relative_rows: list[dict[str, Any]],
    posture_rows: list[dict[str, Any]],
) -> None:
    posture_by_key = {
        (row.get("timestamp_ms"), row.get("target_id")): row
        for row in posture_rows
    }
    for relative in relative_rows:
        key = (relative.get("timestamp_ms"), relative.get("target_id"))
        posture = posture_by_key.get(key)
        if posture is None:
            raise IntervalAggregationValidationError(
                "STAGE_OUTPUT_ALIGNMENT_MISMATCH",
                f"No Stage 8 frame for Stage 9 key {key}",
            )
        relative["frame_index"] = posture.get(
            "frame_index",
            posture.get("sample_index"),
        )


def _distribution(
    intervals: tuple[AnalysisInterval, ...],
    frames: list[dict[str, Any]],
) -> dict[str, Any]:
    assignments = {
        interval.interval_id: sum(
            interval.contains(frame["timestamp_ms"]) for frame in frames
        )
        for interval in intervals
    }
    per_frame_counts = [
        sum(interval.contains(frame["timestamp_ms"]) for interval in intervals)
        for frame in frames
    ]
    return {
        "source_frame_count": len(frames),
        "interval_frame_counts": assignments,
        "assigned_frame_count": sum(count > 0 for count in per_frame_counts),
        "duplicate_assignment_frame_count": sum(
            count > 1 for count in per_frame_counts
        ),
        "unassigned_frame_count": sum(count == 0 for count in per_frame_counts),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Stage 10 interval aggregation smoke report",
        "",
        f"- Technical judgment: `{report['technical_judgment']}`",
        (
            "- Interval rule: "
            "`start_timestamp_ms <= timestamp_ms < end_timestamp_ms`"
        ),
        (
            f"- Source frames: "
            f"{report['frame_distribution']['source_frame_count']}"
        ),
        (
            f"- Assigned / duplicate / unassigned: "
            f"{report['frame_distribution']['assigned_frame_count']} / "
            f"{report['frame_distribution']['duplicate_assignment_frame_count']} / "
            f"{report['frame_distribution']['unassigned_frame_count']}"
        ),
        "",
        "## Temporary intervals",
        "",
    ]
    for item in report["interval_summaries"]:
        lines.append(
            "- "
            f"`{item['interval_id']}`: {item['frame_count']} frames; "
            f"Head {item['head_pose_availability_ratio']:.6f}, "
            f"shoulder {item['posture_availability_ratio']:.6f}, "
            f"nose {item['nose_alignment_availability_ratio']:.6f}, "
            f"face {item['face_alignment_availability_ratio']:.6f}; "
            f"events {item['event_count']}"
        )
    lines.extend(
        (
            "",
            "These intervals are technical smoke windows, not interview answers.",
            "Aggregates and collection quality are not posture or interview evaluations.",
            "No evidence threshold, grade, feedback, or behavioral inference is applied.",
            "",
        )
    )
    return "\n".join(lines)


class IntervalAggregationValidator:
    def validate(
        self,
        video_path: str | Path,
        *,
        intervals: Iterable[AnalysisInterval] | None = None,
        output_root: str | Path = DEFAULT_INTERVAL_AGGREGATION_OUTPUT_ROOT,
        overwrite: bool = False,
        aggregation_config: IntervalAggregationConfig = (
            IntervalAggregationConfig()
        ),
        expected_source_sha256: str = EXPECTED_SOURCE_SHA256,
        stage9_output_root: str | Path = config.OUTPUT_DIR / "neutral_baseline_smoke",
        stage8_output_root: str | Path = config.OUTPUT_DIR / "posture_raw_validation",
        stage7_output_root: str | Path = config.OUTPUT_DIR / "head_pose_validation",
        protected_stage_roots: tuple[str | Path, ...] | None = None,
    ) -> dict[str, Any]:
        source = Path(video_path).resolve()
        metadata = inspect_video_metadata(source)
        if metadata["sha256"] != expected_source_sha256:
            raise IntervalAggregationValidationError(
                "SOURCE_SHA256_MISMATCH",
                "Stage 10 smoke only accepts the protected movement video",
            )
        safe_id = create_safe_video_id(source.name, metadata["sha256"])
        destination = Path(output_root).resolve() / safe_id
        if destination.exists() and not overwrite:
            raise IntervalAggregationValidationError(
                "OUTPUT_ALREADY_EXISTS",
                f"Output exists: {destination}",
            )
        roots_to_protect = (
            PROTECTED_STAGE_ROOTS
            if protected_stage_roots is None
            else tuple(Path(item) for item in protected_stage_roots)
        )
        protected = {}
        for root in roots_to_protect:
            directory = Path(root) / safe_id
            if directory.is_dir():
                for path in sorted(directory.rglob("*")):
                    if path.is_file():
                        protected[path.resolve()] = _sha(path)
        stage9 = (
            Path(stage9_output_root)
            / safe_id
            / "relative_features.jsonl"
        )
        stage8_root = Path(stage8_output_root) / safe_id
        stage7_root = Path(stage7_output_root) / safe_id
        relative_rows = load_strict_jsonl(stage9)
        posture_rows = load_strict_jsonl(
            stage8_root / "frame_posture_metrics.jsonl"
        )
        head_events = load_strict_jsonl(
            stage7_root / "head_pose_events.jsonl"
        )
        posture_events = load_strict_jsonl(
            stage8_root / "posture_events.jsonl"
        )
        _annotate_frame_indices(relative_rows, posture_rows)
        for row in relative_rows:
            if "timestamp_ms" not in row or "target_id" not in row:
                raise IntervalAggregationValidationError(
                    "STAGE_9_SCHEMA_MISMATCH",
                    "Stage 9 frame lacks timestamp_ms or target_id",
                )
            if not {"head_pose", "posture"} <= row.keys():
                raise IntervalAggregationValidationError(
                    "STAGE_9_SCHEMA_MISMATCH",
                    "Stage 9 frame lacks relative feature groups",
                )
        video_end_ms = max(
            int(round(float(metadata["estimated_duration_sec"]) * 1000)),
            max(int(row["timestamp_ms"]) for row in relative_rows) + 1,
        )
        interval_values = (
            tuple(intervals)
            if intervals is not None
            else default_smoke_intervals(video_end_ms)
        )
        try:
            aggregates = aggregate_intervals(
                interval_values,
                relative_rows,
                temporal_frames=posture_rows,
                head_pose_events=head_events,
                posture_events=posture_events,
                config=aggregation_config,
            )
        except IntervalAggregationError as exc:
            raise IntervalAggregationValidationError(
                exc.code,
                str(exc),
            ) from exc
        distribution = _distribution(interval_values, relative_rows)
        interval_summaries = [
            {
                "interval_id": result.interval_id,
                "frame_count": result.data_quality.total_frame_count,
                "head_pose_availability_ratio": (
                    result.data_quality.head_pose_availability_ratio
                ),
                "posture_availability_ratio": (
                    result.data_quality.posture_availability_ratio
                ),
                "nose_alignment_availability_ratio": (
                    result.data_quality.nose_alignment_availability_ratio
                ),
                "face_alignment_availability_ratio": (
                    result.data_quality.face_alignment_availability_ratio
                ),
                "head_pose_jump_candidate_count": (
                    result.events.head_pose_jump_candidate_count
                ),
                "posture_jump_candidate_count": (
                    result.events.posture_jump_candidate_count
                ),
                "event_count": (
                    result.events.head_pose_jump_candidate_count
                    + result.events.posture_jump_candidate_count
                ),
                "data_quality_value": result.data_quality.quality_score,
                "failure_reason": result.failure_reason,
            }
            for result in aggregates
        ]
        report = {
            "schema_version": "1.0",
            "validation_type": "relative_feature_interval_aggregation_smoke",
            "status": "completed",
            "generated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source": metadata,
            "configuration": {
                **aggregation_config.__dict__,
                "percentile_method": (
                    "LINEAR_RANK_EQUALS_N_MINUS_1_TIMES_PERCENTILE"
                ),
                "standard_deviation_method": "POPULATION",
                "mad_method": "MEDIAN_ABSOLUTE_DEVIATION_FROM_MEDIAN",
                "velocity_policy": (
                    "REUSE_EXISTING_TEMPORAL_VALUES_NO_REESTIMATION"
                ),
                "target_id": "TARGET_001",
            },
            "interval_rule": {
                "start_inclusive": True,
                "end_exclusive": True,
                "overlap_rejected_by_default": True,
            },
            "frame_distribution": distribution,
            "interval_summaries": interval_summaries,
            "technical_judgment": (
                "interval_aggregation_smoke_completed_non_answer_intervals"
                if not any(result.failure_reason for result in aggregates)
                and distribution["duplicate_assignment_frame_count"] == 0
                and distribution["unassigned_frame_count"] == 0
                else "interval_aggregation_smoke_completed_with_data_limitations"
            ),
            "limitations": [
                "Temporary smoke intervals are not recorded interview answers.",
                "Interval aggregates are not posture or interview evaluations.",
                "No evidence-based threshold is applied.",
                "Low-availability intervals may limit later evaluation layers.",
                "Very short intervals may contain too few sampled frames.",
                "The 5 FPS analysis cadence limits temporal resolution.",
                "Head angular velocity is absent upstream and is not re-estimated.",
            ],
            "outputs": {
                "validation_report_json": "validation_report.json",
                "validation_report_markdown": "validation_report.md",
                "interval_definitions_json": "interval_definitions.json",
                "interval_aggregates_jsonl": "interval_aggregates.jsonl",
            },
        }
        definitions = {
            "schema_version": "1.0",
            "timestamp_unit": "millisecond",
            "inclusion_rule": (
                "start_timestamp_ms <= timestamp_ms < end_timestamp_ms"
            ),
            "intervals": [item.to_dict() for item in interval_values],
        }
        output_root_path = Path(output_root).resolve()
        output_root_path.mkdir(parents=True, exist_ok=True)
        staged: Path | None = Path(
            tempfile.mkdtemp(prefix=f".{safe_id}.", dir=output_root_path)
        )
        try:
            (staged / "interval_definitions.json").write_text(
                dumps_strict(definitions, indent=2) + "\n",
                encoding="utf-8",
            )
            _write_jsonl(staged / "interval_aggregates.jsonl", aggregates)
            (staged / "validation_report.json").write_text(
                dumps_strict(report, indent=2) + "\n",
                encoding="utf-8",
            )
            (staged / "validation_report.md").write_text(
                _markdown(report),
                encoding="utf-8",
            )
            if calculate_video_sha256(source) != expected_source_sha256:
                raise IntervalAggregationValidationError(
                    "PROTECTED_INPUT_CHANGED",
                    "Input video changed during validation",
                )
            if any(
                not path.is_file() or _sha(path) != digest
                for path, digest in protected.items()
            ):
                raise IntervalAggregationValidationError(
                    "PROTECTED_OUTPUT_CHANGED",
                    "A protected Stage 5-9 output changed during validation",
                )
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.old")
                if backup.exists():
                    raise IntervalAggregationValidationError(
                        "STALE_OUTPUT_BACKUP",
                        f"Refusing replacement while backup exists: {backup}",
                    )
                os.replace(destination, backup)
                try:
                    os.replace(staged, destination)
                except OSError:
                    os.replace(backup, destination)
                    raise
                shutil.rmtree(backup)
            else:
                os.replace(staged, destination)
            staged = None
            return report
        finally:
            if staged is not None:
                shutil.rmtree(staged, ignore_errors=True)
