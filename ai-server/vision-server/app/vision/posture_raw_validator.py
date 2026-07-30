"""Validate limited raw 2D shoulder posture metrics for TARGET_001."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core import config
from app.vision.posture_overlay_renderer import (
    PostureOverlayError,
    write_posture_overlay,
)
from app.vision.posture_raw_models import (
    PostureRawConfiguration,
)
from app.vision.posture_temporal_metrics import (
    calculate_numeric_summary,
    calculate_posture_temporal_results,
    detect_posture_jump_candidates,
)
from app.vision.shoulder_posture_estimator import estimate_shoulder_posture
from app.vision.target_candidate_matcher import calculate_face_pose_consistency
from app.vision.temporal_landmark_metrics import (
    build_missing_segments,
    calculate_detection_ratio,
    calculate_longest_missing_duration,
)
from app.vision.temporal_landmark_validator import load_strict_frames
from app.vision.video_analyzer import DEFAULT_OUTPUT_ROOT as DEFAULT_VIDEO_OUTPUT_ROOT
from app.vision.video_loader import (
    calculate_video_sha256,
    create_safe_video_id,
    inspect_video_metadata,
)


EXPECTED_SOURCE_SHA256 = (
    "6cd4d7ac9d6dc546692d66c8c324dc7f09e1e20f5af846713bd1e119527bea32"
)
DEFAULT_POSTURE_RAW_OUTPUT_ROOT = config.OUTPUT_DIR / "posture_raw_validation"
DEFAULT_TEMPORAL_OUTPUT_ROOT = config.OUTPUT_DIR / "motion_validation"
DEFAULT_TARGET_OUTPUT_ROOT = config.OUTPUT_DIR / "target_tracking_validation"
DEFAULT_HEAD_POSE_OUTPUT_ROOT = config.OUTPUT_DIR / "head_pose_validation"

POSTURE_CSV_FIELDS = [
    "target_id",
    "candidate_count",
    "selected_candidate_index",
    "posture_available",
    "shoulders_available",
    "nose_alignment_available",
    "face_alignment_available",
    "shoulder_tilt_deg",
    "shoulder_height_difference_norm",
    "shoulder_center_x_raw",
    "shoulder_center_y_raw",
    "shoulder_width_norm",
    "nose_shoulder_offset_x_norm",
    "nose_shoulder_offset_y_norm",
    "face_shoulder_offset_x_norm",
    "face_shoulder_offset_y_norm",
    "posture_confidence",
    "coordinate_space",
    "horizontal_sign_convention",
    "shoulder_sign_convention",
    "posture_failure_reason",
    "posture_status_codes",
    "delta_time_seconds",
    "shoulder_center_displacement_norm",
    "shoulder_center_velocity_norm_per_sec",
    "shoulder_tilt_delta_deg",
    "shoulder_tilt_velocity_deg_per_sec",
    "shoulder_width_delta_norm",
    "shoulder_width_change_rate_per_sec",
    "nose_offset_x_delta_norm",
    "nose_offset_y_delta_norm",
    "face_offset_x_delta_norm",
    "face_offset_y_delta_norm",
    "posture_jump_candidate",
    "posture_jump_event_types",
    "head_pose_available_reference",
    "raw_yaw_deg_reference",
    "raw_pitch_deg_reference",
    "raw_roll_deg_reference",
]


class PostureRawValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PostureRawValidationError(
            "INVALID_PROTECTED_JSON",
            f"{path.name}: {exc}",
        ) from exc


def _strict_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return load_strict_frames(path)
    except Exception as exc:
        raise PostureRawValidationError(
            "INVALID_PROTECTED_JSONL",
            f"{path.name}: {exc}",
        ) from exc


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
            stream.write("\n")


def _selected_candidate(target: dict[str, Any]) -> dict[str, Any] | None:
    selected = target.get("selected_candidate_index")
    if selected is None:
        return None
    for candidate in target.get("candidates") or []:
        if candidate.get("candidate_index") == selected:
            return candidate
    return None


def _frame_face_geometry(
    frame: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> tuple[dict[str, float] | None, dict[str, float] | None]:
    """Accept the canonical face bbox only when it matches selected pose geometry."""

    if not candidate:
        return None, None
    source_box = frame.get("face_bounding_box")
    width, height = frame.get("frame_width"), frame.get("frame_height")
    if not isinstance(source_box, dict) or not width or not height:
        return None, None
    nose = candidate.get("nose")
    shoulder_center = candidate.get("shoulder_center")
    shoulder_width = candidate.get("shoulder_width")
    if not nose or not shoulder_center or not shoulder_width:
        return None, None
    try:
        box = {
            "min_x": float(source_box["min_x"]) / float(width),
            "min_y": float(source_box["min_y"]) / float(height),
            "max_x": float(source_box["max_x"]) / float(width),
            "max_y": float(source_box["max_y"]) / float(height),
        }
        face_center = {
            "x": (box["min_x"] + box["max_x"]) / 2.0,
            "y": (box["min_y"] + box["max_y"]) / 2.0,
        }
        consistency = calculate_face_pose_consistency(
            face_center,
            box,
            nose,
            shoulder_center,
            float(shoulder_width),
        )
    except (KeyError, TypeError, ValueError):
        return None, None
    if consistency is None:
        return None, None
    return box, face_center


def _write_csv(
    path: Path,
    temporal_csv: Path,
    rows: list[dict[str, Any]],
) -> None:
    with temporal_csv.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        prefix_fields = list(reader.fieldnames or [])
        prefix_rows = list(reader)
    if len(prefix_rows) != len(rows):
        raise PostureRawValidationError(
            "TEMPORAL_CSV_ALIGNMENT_FAILED",
            "Existing temporal CSV row count does not match posture rows",
        )
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=prefix_fields + POSTURE_CSV_FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        for prefix, row in zip(prefix_rows, rows):
            if int(prefix["timestamp_ms"]) != int(row["timestamp_ms"]):
                raise PostureRawValidationError(
                    "TEMPORAL_CSV_ALIGNMENT_FAILED",
                    "Existing temporal CSV timestamp does not match posture row",
                )
            raw = row["posture_raw"]
            temporal = row["posture_temporal"]
            head = row["head_pose_reference"]

            def csv_value(value: Any) -> Any:
                return "" if value is None else value

            extension = {
                "target_id": row["target_id"],
                "candidate_count": row["candidate_count"],
                "selected_candidate_index": csv_value(
                    row["selected_candidate_index"]
                ),
                "posture_available": raw["available"],
                "shoulders_available": raw["shoulders_available"],
                "nose_alignment_available": raw["nose_alignment_available"],
                "face_alignment_available": raw["face_alignment_available"],
                "shoulder_center_x_raw": csv_value(raw["shoulder_center_x"]),
                "shoulder_center_y_raw": csv_value(raw["shoulder_center_y"]),
                "posture_confidence": raw["confidence"],
                "posture_failure_reason": csv_value(raw["failure_reason"]),
                "posture_status_codes": "|".join(raw["status_codes"]),
                "posture_jump_candidate": bool(
                    row["posture_jump_candidates"]
                ),
                "posture_jump_event_types": "|".join(
                    row["posture_jump_candidates"]
                ),
                "head_pose_available_reference": head["available"],
                "raw_yaw_deg_reference": csv_value(head["yaw_deg"]),
                "raw_pitch_deg_reference": csv_value(head["pitch_deg"]),
                "raw_roll_deg_reference": csv_value(head["roll_deg"]),
            }
            for field in (
                "shoulder_tilt_deg",
                "shoulder_height_difference_norm",
                "shoulder_width_norm",
                "nose_shoulder_offset_x_norm",
                "nose_shoulder_offset_y_norm",
                "face_shoulder_offset_x_norm",
                "face_shoulder_offset_y_norm",
                "coordinate_space",
                "horizontal_sign_convention",
                "shoulder_sign_convention",
            ):
                extension[field] = csv_value(raw[field])
            for field, value in temporal.items():
                extension[field] = csv_value(value)
            writer.writerow(prefix | extension)


def _availability_summary(
    states: list[bool],
    timestamps: list[int],
) -> dict[str, Any]:
    available = sum(states)
    return {
        "available_frame_count": available,
        "unavailable_frame_count": len(states) - available,
        "availability_ratio": calculate_detection_ratio(states),
        "unavailable_segments": build_missing_segments(states, timestamps),
        "longest_unavailable_duration_sec": calculate_longest_missing_duration(
            states,
            timestamps,
        ),
    }


def _metric_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    return calculate_numeric_summary(
        [row["posture_raw"].get(field) for row in rows]
    )


def _temporal_summary(
    rows: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    return calculate_numeric_summary(
        [row["posture_temporal"].get(field) for row in rows]
    )


def _representative_payload(
    category: str,
    row: dict[str, Any] | None,
    *,
    limitation: str | None = None,
) -> dict[str, Any]:
    if row is None:
        return {
            "category": category,
            "observed": False,
            "limitation": limitation
            or "Movement was not clearly observed in this video.",
        }
    raw = row["posture_raw"]
    return {
        "category": category,
        "observed": True,
        "timestamp_ms": row["timestamp_ms"],
        "target_id": row["target_id"],
        "shoulder_tilt_deg": raw["shoulder_tilt_deg"],
        "shoulder_height_difference_norm": raw[
            "shoulder_height_difference_norm"
        ],
        "shoulder_center_x": raw["shoulder_center_x"],
        "shoulder_center_y": raw["shoulder_center_y"],
        "shoulder_width_norm": raw["shoulder_width_norm"],
        "nose_shoulder_offset_x_norm": raw[
            "nose_shoulder_offset_x_norm"
        ],
        "nose_shoulder_offset_y_norm": raw[
            "nose_shoulder_offset_y_norm"
        ],
        "face_shoulder_offset_x_norm": raw[
            "face_shoulder_offset_x_norm"
        ],
        "face_shoulder_offset_y_norm": raw[
            "face_shoulder_offset_y_norm"
        ],
        "confidence": raw["confidence"],
        "failure_reason": raw["failure_reason"],
    }


def _select_representatives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    available = [row for row in rows if row["posture_raw"]["available"]]
    nose = [
        row
        for row in rows
        if row["posture_raw"]["nose_alignment_available"]
    ]
    face_missing = [
        row
        for row in rows
        if row["posture_raw"]["available"]
        and not row["posture_raw"]["face_alignment_available"]
    ]
    temporal_center = [
        row
        for row in rows
        if row["posture_temporal"]["shoulder_center_displacement_norm"]
        is not None
    ]
    temporal_width = [
        row
        for row in rows
        if row["posture_temporal"]["shoulder_width_delta_norm"] is not None
    ]
    right_lower = [
        row for row in available if row["posture_raw"]["shoulder_tilt_deg"] > 1.0
    ]
    left_lower = [
        row
        for row in available
        if row["posture_raw"]["shoulder_tilt_deg"] < -1.0
    ]
    return [
        _representative_payload(
            "shoulders_near_horizontal",
            min(
                available,
                key=lambda row: abs(row["posture_raw"]["shoulder_tilt_deg"]),
                default=None,
            ),
        ),
        _representative_payload(
            "subject_right_shoulder_lower",
            max(
                right_lower,
                key=lambda row: row["posture_raw"]["shoulder_tilt_deg"],
                default=None,
            ),
            limitation=(
                "A clearly positive anatomical-right-lower shoulder frame "
                "was not observed; independent directional validation is limited."
            ),
        ),
        _representative_payload(
            "subject_left_shoulder_lower",
            min(
                left_lower,
                key=lambda row: row["posture_raw"]["shoulder_tilt_deg"],
                default=None,
            ),
            limitation=(
                "A clearly negative anatomical-left-lower shoulder frame "
                "was not observed; independent directional validation is limited."
            ),
        ),
        _representative_payload(
            "nose_screen_left",
            min(
                nose,
                key=lambda row: row["posture_raw"][
                    "nose_shoulder_offset_x_norm"
                ],
                default=None,
            ),
        ),
        _representative_payload(
            "nose_screen_right",
            max(
                nose,
                key=lambda row: row["posture_raw"][
                    "nose_shoulder_offset_x_norm"
                ],
                default=None,
            ),
        ),
        _representative_payload(
            "face_not_detected",
            face_missing[0] if face_missing else None,
        ),
        _representative_payload(
            "largest_shoulder_center_displacement",
            max(
                temporal_center,
                key=lambda row: row["posture_temporal"][
                    "shoulder_center_displacement_norm"
                ],
                default=None,
            ),
        ),
        _representative_payload(
            "largest_shoulder_width_change",
            max(
                temporal_width,
                key=lambda row: abs(
                    row["posture_temporal"]["shoulder_width_delta_norm"]
                ),
                default=None,
            ),
        ),
    ]


def _interval_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    intervals = {
        "face_missing_focus": (14_012, 16_633),
        "background_person_focus": (30_000, 34_000),
    }
    output: dict[str, Any] = {}
    for name, (start, end) in intervals.items():
        selected = [
            row for row in rows if start <= row["timestamp_ms"] <= end
        ]
        output[name] = {
            "start_timestamp_ms": start,
            "end_timestamp_ms": end,
            "frame_count": len(selected),
            "target_ids": sorted(
                {
                    row["target_id"]
                    for row in selected
                    if row["target_id"] is not None
                }
            ),
            "maximum_candidate_count": max(
                (row["candidate_count"] for row in selected),
                default=None,
            ),
            "shoulder_available_frame_count": sum(
                row["posture_raw"]["shoulders_available"]
                for row in selected
            ),
            "nose_alignment_available_frame_count": sum(
                row["posture_raw"]["nose_alignment_available"]
                for row in selected
            ),
            "face_alignment_available_frame_count": sum(
                row["posture_raw"]["face_alignment_available"]
                for row in selected
            ),
        }
    return output


def _markdown(report: dict[str, Any]) -> str:
    summary = report["posture_summary"]
    quality = report["quality_assessment"]
    lines = [
        "# TARGET_001 Raw Shoulder Posture Validation",
        "",
        f"- Judgment: `{quality['technical_judgment']}`",
        f"- Frames: {summary['total_frame_count']}",
        (
            f"- Shoulder metrics: "
            f"{summary['shoulders']['available_frame_count']}/"
            f"{summary['total_frame_count']}"
        ),
        (
            f"- Nose alignment: "
            f"{summary['nose_alignment']['available_frame_count']}/"
            f"{summary['total_frame_count']}"
        ),
        (
            f"- Face alignment: "
            f"{summary['face_alignment']['available_frame_count']}/"
            f"{summary['total_frame_count']}"
        ),
        (
            f"- Confidence mean/min/max: "
            f"{summary['confidence']['mean']}/"
            f"{summary['confidence']['min']}/"
            f"{summary['confidence']['max']}"
        ),
        "",
        "## Coordinate and sign conventions",
        "",
        "- Coordinates: IMAGE_NORMALIZED; x increases screen-right and y increases downward.",
        "- Offset x: screen-left negative, screen-right positive.",
        "- Shoulder tilt/height: anatomical right shoulder lower is positive; anatomical left shoulder lower is negative.",
        "- Source pixels were not horizontally flipped by this pipeline.",
        "",
        "## Raw metric summaries",
        "",
    ]
    for key, value in report["raw_metric_summaries"].items():
        lines.append(f"- {key}: `{json.dumps(value, ensure_ascii=False)}`")
    lines += [
        "",
        "## Temporal metric summaries",
        "",
    ]
    for key, value in report["temporal_metric_summaries"].items():
        lines.append(f"- {key}: `{json.dumps(value, ensure_ascii=False)}`")
    lines += [
        "",
        "## Diagnostic change candidates",
        "",
        (
            f"- Total: "
            f"{report['jump_candidates']['total_count']} "
            "(diagnostic only; not an error or score)"
        ),
        "",
        "## Scope and limitations",
        "",
        "- Only the selected target's face, nose, and two shoulder landmarks are used.",
        "- Elbows, wrists, hands, hips, pelvis, lower body, and full-body landmarks are not used.",
        "- These 2D proxies do not directly measure spine, pelvis, or full-body posture.",
        "- Camera tilt and user placement can create fixed offsets.",
        "- Nose/face alignment jointly reflects head motion, upper-body motion, and camera placement.",
        "- Normalized 2D coordinates contain no calibrated depth measurement.",
        "- Confidence is calculation quality, not posture quality.",
        "- Raw metrics are not converted to posture, attitude, confidence, focus, anxiety, or interview scores.",
        "- Smoothing and automatic baseline correction are disabled.",
        "",
        "## Outputs",
        "",
    ]
    for key, value in report["outputs"].items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


class PostureRawValidator:
    def __init__(
        self,
        configuration: PostureRawConfiguration = PostureRawConfiguration(),
    ) -> None:
        self.configuration = configuration

    def validate(
        self,
        video_path: str | Path,
        *,
        analysis_fps: float = 5.0,
        output_root: str | Path = DEFAULT_POSTURE_RAW_OUTPUT_ROOT,
        overwrite: bool = False,
        generate_overlay: bool = True,
        expected_source_sha256: str = EXPECTED_SOURCE_SHA256,
        video_analysis_root: str | Path = DEFAULT_VIDEO_OUTPUT_ROOT,
        temporal_output_root: str | Path = DEFAULT_TEMPORAL_OUTPUT_ROOT,
        target_output_root: str | Path = DEFAULT_TARGET_OUTPUT_ROOT,
        head_pose_output_root: str | Path = DEFAULT_HEAD_POSE_OUTPUT_ROOT,
    ) -> dict[str, Any]:
        if analysis_fps <= 0:
            raise PostureRawValidationError(
                "INVALID_ANALYSIS_FPS",
                "analysis_fps must be positive",
            )
        metadata = inspect_video_metadata(video_path)
        source = Path(video_path).expanduser().resolve()
        if metadata["sha256"] != expected_source_sha256:
            raise PostureRawValidationError(
                "SOURCE_SHA256_MISMATCH",
                "Input SHA-256 does not match the stage-8 validation video",
            )
        safe_id = create_safe_video_id(source.name, metadata["sha256"])
        video_dir = Path(video_analysis_root) / safe_id
        temporal_dir = Path(temporal_output_root) / safe_id
        target_dir = Path(target_output_root) / safe_id
        head_dir = Path(head_pose_output_root) / safe_id
        analysis_path = video_dir / "analysis.json"
        frames_path = video_dir / "frames.jsonl"
        temporal_csv = temporal_dir / "landmark_timeseries.csv"
        tracking_path = target_dir / "frame_target_metrics.jsonl"
        head_path = head_dir / "frame_head_pose_metrics.jsonl"
        required = (
            analysis_path,
            frames_path,
            temporal_csv,
            tracking_path,
            head_path,
        )
        if not all(path.is_file() for path in required):
            raise PostureRawValidationError(
                "PROTECTED_INPUT_MISSING",
                "Required stage-5/6/7 input is missing",
            )
        protected_paths = [
            source,
            analysis_path,
            frames_path,
            *sorted(path for path in temporal_dir.iterdir() if path.is_file()),
            *sorted(path for path in target_dir.iterdir() if path.is_file()),
            *sorted(path for path in head_dir.iterdir() if path.is_file()),
        ]
        protected_hashes = {path: _sha(path) for path in protected_paths}
        analysis = _strict_json(analysis_path)
        if (
            abs(
                float(analysis["configuration"]["effective_analysis_fps"])
                - analysis_fps
            )
            > 1e-9
        ):
            raise PostureRawValidationError(
                "ANALYSIS_FPS_MISMATCH",
                "Existing VIDEO analysis FPS does not match",
            )
        frames = _strict_jsonl(frames_path)
        tracking = _strict_jsonl(tracking_path)
        head_pose = _strict_jsonl(head_path)
        if not (len(frames) == len(tracking) == len(head_pose)):
            raise PostureRawValidationError(
                "TIMESTAMP_ALIGNMENT_FAILED",
                "Stage-5/6/7 row counts differ",
            )
        for frame, target, head in zip(frames, tracking, head_pose):
            if not (
                frame["timestamp_ms"]
                == target["timestamp_ms"]
                == head["timestamp_ms"]
            ):
                raise PostureRawValidationError(
                    "TIMESTAMP_ALIGNMENT_FAILED",
                    "Stage-5/6/7 timestamps are not aligned",
                )

        rows: list[dict[str, Any]] = []
        previous_available = False
        for frame, target, head in zip(frames, tracking, head_pose):
            candidate_count = int(target.get("candidate_count") or 0)
            candidate = _selected_candidate(target)
            face_box, face_center = _frame_face_geometry(frame, candidate)
            result = estimate_shoulder_posture(
                candidate.get("left_shoulder") if candidate else None,
                candidate.get("right_shoulder") if candidate else None,
                candidate.get("nose") if candidate else None,
                face_center,
                target_id=target.get("target_id"),
                target_confidence=float(target.get("target_confidence") or 0.0),
                candidate_count=candidate_count,
                previous_available=previous_available,
                configuration=self.configuration,
            )
            raw = result.to_dict()
            head_values = head["head_pose"]
            rows.append(
                {
                    "frame_index": frame["sample_index"],
                    "sample_index": frame["sample_index"],
                    "source_frame_index": frame["source_frame_index"],
                    "timestamp_ms": frame["timestamp_ms"],
                    "timestamp_sec": frame["timestamp_sec"],
                    "target_id": target.get("target_id"),
                    "candidate_count": candidate_count,
                    "selected_candidate_index": target.get(
                        "selected_candidate_index"
                    ),
                    "landmarks": {
                        "nose": candidate.get("nose") if candidate else None,
                        "left_shoulder": (
                            candidate.get("left_shoulder") if candidate else None
                        ),
                        "right_shoulder": (
                            candidate.get("right_shoulder")
                            if candidate
                            else None
                        ),
                        "face_center": face_center,
                        "face_bounding_box": face_box,
                    },
                    "posture_raw": raw,
                    "posture_temporal": {},
                    "posture_jump_candidates": [],
                    "head_pose_reference": {
                        "available": bool(head_values["available"]),
                        "yaw_deg": head_values["yaw_deg"],
                        "pitch_deg": head_values["pitch_deg"],
                        "roll_deg": head_values["roll_deg"],
                    },
                }
            )
            previous_available = raw["available"]

        temporal_results = calculate_posture_temporal_results(rows)
        for row, temporal in zip(rows, temporal_results):
            row["posture_temporal"] = temporal.to_dict()
        events, jump_diagnostics = detect_posture_jump_candidates(
            rows,
            self.configuration,
        )
        event_types: dict[int, list[str]] = {}
        for event in events:
            event_types.setdefault(event["timestamp_ms"], []).append(
                event["event_type"]
            )
        for row in rows:
            row["posture_jump_candidates"] = event_types.get(
                row["timestamp_ms"],
                [],
            )

        timestamps = [row["timestamp_ms"] for row in rows]
        shoulder_states = [
            row["posture_raw"]["shoulders_available"] for row in rows
        ]
        nose_states = [
            row["posture_raw"]["nose_alignment_available"] for row in rows
        ]
        face_states = [
            row["posture_raw"]["face_alignment_available"] for row in rows
        ]
        status_counts = Counter(
            status
            for row in rows
            for status in row["posture_raw"]["status_codes"]
        )
        failure_counts = Counter(
            row["posture_raw"]["failure_reason"]
            for row in rows
            if row["posture_raw"]["failure_reason"] is not None
        )
        confidence = calculate_numeric_summary(
            [row["posture_raw"]["confidence"] for row in rows]
        )
        posture_summary = {
            "total_frame_count": len(rows),
            "shoulders": _availability_summary(shoulder_states, timestamps),
            "nose_alignment": _availability_summary(nose_states, timestamps),
            "face_alignment": _availability_summary(face_states, timestamps),
            "confidence": confidence,
            "status_code_counts": dict(status_counts),
            "failure_reason_counts": dict(failure_counts),
        }
        raw_metric_summaries = {
            field: _metric_summary(rows, field)
            for field in (
                "shoulder_tilt_deg",
                "shoulder_height_difference_norm",
                "shoulder_center_x",
                "shoulder_center_y",
                "shoulder_width_norm",
                "nose_shoulder_offset_x_norm",
                "nose_shoulder_offset_y_norm",
                "face_shoulder_offset_x_norm",
                "face_shoulder_offset_y_norm",
            )
        }
        temporal_metric_summaries = {
            field: _temporal_summary(rows, field)
            for field in (
                "shoulder_center_displacement_norm",
                "shoulder_center_velocity_norm_per_sec",
                "shoulder_tilt_delta_deg",
                "shoulder_tilt_velocity_deg_per_sec",
                "shoulder_width_delta_norm",
                "shoulder_width_change_rate_per_sec",
                "nose_offset_x_delta_norm",
                "nose_offset_y_delta_norm",
                "face_offset_x_delta_norm",
                "face_offset_y_delta_norm",
            )
        }
        representatives = _select_representatives(rows)
        representative_timestamps = {
            item["timestamp_ms"] for item in representatives if item["observed"]
        }
        judgment = (
            "posture_raw_validation_failed"
            if not any(shoulder_states)
            else "posture_raw_validation_passed_with_warnings"
            if events or not all(face_states) or not all(nose_states)
            else "posture_raw_validation_passed"
        )

        destination = Path(output_root).resolve() / safe_id
        output_root_path = Path(output_root).resolve()
        if destination.exists() and not overwrite:
            raise PostureRawValidationError(
                "OUTPUT_ALREADY_EXISTS",
                f"Output exists: {destination}",
            )
        output_root_path.mkdir(parents=True, exist_ok=True)
        staged = Path(
            tempfile.mkdtemp(prefix=f".{safe_id}.", dir=output_root_path)
        )
        try:
            _write_jsonl(staged / "frame_posture_metrics.jsonl", rows)
            _write_jsonl(staged / "posture_events.jsonl", events)
            _write_csv(
                staged / "posture_timeseries.csv",
                temporal_csv,
                rows,
            )
            overlay_metadata = None
            if generate_overlay:
                try:
                    overlay_metadata = write_posture_overlay(
                        source,
                        staged / "diagnostic_overlay.mp4",
                        rows,
                        analysis_fps,
                        representative_timestamps=representative_timestamps,
                        representative_directory=staged / "representative_frames",
                        configuration=self.configuration,
                    )
                except PostureOverlayError as exc:
                    raise PostureRawValidationError(
                        "OVERLAY_FAILED",
                        str(exc),
                    ) from exc
            if overlay_metadata:
                files = overlay_metadata["representative_files"]
                for representative in representatives:
                    timestamp = representative.get("timestamp_ms")
                    representative["overlay_image"] = (
                        f"representative_frames/{files[str(timestamp)]}"
                        if timestamp is not None and str(timestamp) in files
                        else None
                    )
            report = {
                "schema_version": "1.0",
                "validation_type": "target_001_raw_2d_shoulder_posture",
                "status": "completed",
                "generated_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "source": metadata,
                "configuration": {
                    **self.configuration.__dict__,
                    "analysis_fps": analysis_fps,
                    "target_id": "TARGET_001",
                    "pose_landmark_indices": {
                        "nose": 0,
                        "left_shoulder": 11,
                        "right_shoulder": 12,
                    },
                    "coordinate_space": "IMAGE_NORMALIZED",
                    "horizontal_sign_convention": (
                        "SCREEN_LEFT_NEGATIVE_SCREEN_RIGHT_POSITIVE"
                    ),
                    "shoulder_sign_convention": (
                        "SUBJECT_RIGHT_SHOULDER_LOWER_POSITIVE_"
                        "SUBJECT_LEFT_SHOULDER_LOWER_NEGATIVE"
                    ),
                    "source_mirroring": (
                        "NOT_MIRRORED_VISUALLY_CONFIRMED_"
                        "NO_PIPELINE_HORIZONTAL_FLIP"
                    ),
                    "smoothing": "NONE",
                    "automatic_baseline_correction": False,
                    "head_pose_used_for_scoring": False,
                    "posture_scoring_enabled": False,
                    "interview_scoring_enabled": False,
                },
                "data_linkage": {
                    "target_tracking": (
                        "timestamp + TARGET_001 + selected_candidate_index"
                    ),
                    "temporal_prefix": str(temporal_csv),
                    "head_pose_reference": (
                        "same timestamp, diagnostic comparison only"
                    ),
                },
                "posture_summary": posture_summary,
                "raw_metric_summaries": raw_metric_summaries,
                "temporal_metric_summaries": temporal_metric_summaries,
                "jump_candidates": {
                    "total_count": len(events),
                    "by_event_type": dict(
                        Counter(event["event_type"] for event in events)
                    ),
                    "diagnostics": jump_diagnostics,
                    "interpretation": (
                        "diagnostic candidates only; not tracking errors, "
                        "posture judgments, or scores"
                    ),
                },
                "representative_frames": representatives,
                "focus_interval_diagnostics": _interval_diagnostics(rows),
                "overlay_validation": overlay_metadata,
                "quality_assessment": {
                    "technical_judgment": judgment,
                    "raw_values_only": True,
                    "confidence_is_calculation_quality_not_posture_quality": True,
                    "evaluation_score_produced": False,
                },
                "limitations": [
                    "Only face, nose, and both shoulder landmarks are used.",
                    "Spine, pelvis, and full-body posture are not directly measured.",
                    "Camera tilt and user placement can introduce fixed offsets.",
                    "Nose/face alignment jointly reflects head and upper-body motion.",
                    "2D normalized coordinates do not provide calibrated depth.",
                    "Raw metrics cannot directly serve as posture or interview scores.",
                ],
                "outputs": {
                    "validation_report_json": "validation_report.json",
                    "validation_report_markdown": "validation_report.md",
                    "frame_posture_metrics_jsonl": (
                        "frame_posture_metrics.jsonl"
                    ),
                    "posture_events_jsonl": "posture_events.jsonl",
                    "posture_timeseries_csv": "posture_timeseries.csv",
                    "diagnostic_overlay_video": (
                        "diagnostic_overlay.mp4" if generate_overlay else None
                    ),
                    "representative_frames_directory": (
                        "representative_frames" if generate_overlay else None
                    ),
                },
                "warnings": [
                    "Face alignment is null on face-missing frames while nose alignment remains independent.",
                    "Jump candidates require manual overlay review.",
                    "No posture or interview score is produced.",
                ],
                "errors": [],
            }
            (staged / "validation_report.json").write_text(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (staged / "validation_report.md").write_text(
                _markdown(report),
                encoding="utf-8",
            )
            if calculate_video_sha256(source) != expected_source_sha256:
                raise PostureRawValidationError(
                    "PROTECTED_INPUT_CHANGED",
                    "Input video changed during validation",
                )
            if any(
                _sha(path) != digest
                for path, digest in protected_hashes.items()
            ):
                raise PostureRawValidationError(
                    "PROTECTED_INPUT_CHANGED",
                    "Stage-5/6/7 protected output changed during validation",
                )
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.old")
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
