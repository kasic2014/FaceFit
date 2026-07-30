"""Validate raw approximate PnP head pose for the selected TARGET_001 track."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import statistics
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from app.core import config
from app.vision.head_pose_estimator import estimate_head_pose
from app.vision.head_pose_metrics import (
    calculate_angular_deltas,
    calculate_axis_summary,
    calculate_reprojection_summary,
    detect_angular_jump_candidates,
)
from app.vision.head_pose_models import (
    HEAD_POSE_LANDMARK_INDICES,
    HEAD_POSE_MODEL_POINTS,
    HeadPoseConfiguration,
    HeadPoseFailureReason,
)
from app.vision.temporal_landmark_metrics import (
    build_missing_segments,
    calculate_detection_ratio,
    calculate_longest_missing_duration,
)
from app.vision.temporal_landmark_validator import load_strict_frames
from app.vision.video_analyzer import DEFAULT_OUTPUT_ROOT as DEFAULT_VIDEO_OUTPUT_ROOT
from app.vision.video_loader import calculate_video_sha256, create_safe_video_id, inspect_video_metadata


DEFAULT_HEAD_POSE_OUTPUT_ROOT = config.OUTPUT_DIR / "head_pose_validation"
DEFAULT_TARGET_OUTPUT_ROOT = config.OUTPUT_DIR / "target_tracking_validation"
DEFAULT_TEMPORAL_OUTPUT_ROOT = config.OUTPUT_DIR / "motion_validation"
HEAD_POSE_CSV_FIELDS = [
    "target_id", "head_pose_available", "raw_yaw_deg", "raw_pitch_deg",
    "raw_roll_deg", "smoothed_yaw_deg", "smoothed_pitch_deg", "smoothed_roll_deg",
    "head_pose_confidence", "estimation_method", "failure_reason",
    "solvepnp_success", "reprojection_error", "head_pose_landmark_count",
    "camera_matrix_source", "yaw_delta_deg", "pitch_delta_deg", "roll_delta_deg",
    "angular_jump_candidate", "angular_jump_axes",
]


class HeadPoseValidationError(RuntimeError):
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
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HeadPoseValidationError("INVALID_PROTECTED_JSON", f"{path.name}: {exc}") from exc


def _strict_jsonl(path: Path) -> list[dict[str, Any]]:
    return load_strict_frames(path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
            stream.write("\n")


def _write_csv(path: Path, temporal_csv: Path, rows: list[dict[str, Any]]) -> None:
    with temporal_csv.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        base_fields = list(reader.fieldnames or [])
        base_rows = list(reader)
    if len(base_rows) != len(rows):
        raise HeadPoseValidationError("TEMPORAL_ROW_COUNT_MISMATCH", "Temporal CSV and head pose rows differ")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*base_fields, *HEAD_POSE_CSV_FIELDS])
        writer.writeheader()
        for base, row in zip(base_rows, rows):
            pose = row["head_pose"]
            extra = {
                "target_id": row["target_id"],
                "head_pose_available": pose["available"],
                "raw_yaw_deg": pose["yaw_deg"] if pose["available"] else "",
                "raw_pitch_deg": pose["pitch_deg"] if pose["available"] else "",
                "raw_roll_deg": pose["roll_deg"] if pose["available"] else "",
                "smoothed_yaw_deg": "", "smoothed_pitch_deg": "", "smoothed_roll_deg": "",
                "head_pose_confidence": pose["confidence"],
                "estimation_method": pose["estimation_method"],
                "failure_reason": pose["failure_reason"] or "",
                "solvepnp_success": pose["solvepnp_success"],
                "reprojection_error": pose["reprojection_error"] if pose["reprojection_error"] is not None else "",
                "head_pose_landmark_count": pose["landmark_count"],
                "camera_matrix_source": pose["camera_matrix_source"],
                **row["angular_deltas"],
                "angular_jump_candidate": bool(row["angular_jump_axes"]),
                "angular_jump_axes": "|".join(row["angular_jump_axes"]),
            }
            writer.writerow({**base, **extra})


def _write_overlay(source: Path, path: Path, rows: list[dict[str, Any]], fps: float) -> None:
    capture = cv2.VideoCapture(str(source))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not capture.isOpened() or not writer.isOpened():
        capture.release(); writer.release()
        raise HeadPoseValidationError("OVERLAY_FAILED", "Could not initialize head pose overlay")
    current_index = 0
    try:
        for row in rows:
            wanted, frame = int(row["source_frame_index"]), None
            while current_index <= wanted:
                ok, decoded = capture.read()
                if not ok:
                    raise HeadPoseValidationError("OVERLAY_FAILED", "Could not decode overlay frame")
                if current_index == wanted:
                    frame = decoded
                current_index += 1
            pose = row["head_pose"]
            if pose["available"]:
                text = (
                    f'{row["target_id"]} yaw={pose["yaw_deg"]:.1f} '
                    f'pitch={pose["pitch_deg"]:.1f} roll={pose["roll_deg"]:.1f}'
                )
                second = f'available=True confidence={pose["confidence"]:.3f} reproj={pose["reprojection_error"]:.2f}px'
                nose = pose.get("nose_pixel")
                axes = pose.get("axis_points")
                if nose and axes:
                    origin = tuple(round(value) for value in nose)
                    for name, color in (("x", (0, 0, 255)), ("y", (0, 255, 0)), ("z", (255, 0, 0))):
                        cv2.line(frame, origin, tuple(round(value) for value in axes[name]), color, 3)
            else:
                text = f'{row["target_id"] or "NO_TARGET"} Head Pose unavailable'
                second = f'available=False reason={pose["failure_reason"]}'
            third = f'angular_jump_candidate={bool(row["angular_jump_axes"])} axes={"|".join(row["angular_jump_axes"]) or "-"}'
            for index, line in enumerate((text, second, third)):
                y = 32 + index * 28
                cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 4)
                cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 2)
            writer.write(frame)
    finally:
        capture.release(); writer.release()


def _representatives(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    valid = [row for row in rows if row["head_pose"]["available"]]
    if not valid:
        return {name: None for name in ("frontal", "yaw_negative", "yaw_positive", "pitch_positive", "pitch_negative", "roll_extreme", "face_missing")}
    def payload(row: dict[str, Any]) -> dict[str, Any]:
        pose = row["head_pose"]
        return {"timestamp_ms": row["timestamp_ms"], "yaw_deg": pose["yaw_deg"], "pitch_deg": pose["pitch_deg"], "roll_deg": pose["roll_deg"]}
    missing = next((row for row in rows if not row["head_pose"]["available"]), None)
    return {
        "frontal": payload(min(valid, key=lambda row: sum(abs(row["head_pose"][f"{axis}_deg"]) for axis in ("yaw", "pitch", "roll")))),
        "yaw_negative": payload(min(valid, key=lambda row: row["head_pose"]["yaw_deg"])),
        "yaw_positive": payload(max(valid, key=lambda row: row["head_pose"]["yaw_deg"])),
        "pitch_positive": payload(max(valid, key=lambda row: row["head_pose"]["pitch_deg"])),
        "pitch_negative": payload(min(valid, key=lambda row: row["head_pose"]["pitch_deg"])),
        "roll_extreme": payload(max(valid, key=lambda row: abs(row["head_pose"]["roll_deg"]))),
        "face_missing": (
            {"timestamp_ms": missing["timestamp_ms"], "failure_reason": missing["head_pose"]["failure_reason"]}
            if missing else None
        ),
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report["head_pose_summary"]
    lines = [
        "# Raw Approximate Head Pose Validation", "",
        f"- Judgment: `{report['quality_assessment']['technical_judgment']}`",
        f"- Available: {summary['available_frame_count']}/{summary['total_frame_count']} ({summary['availability_ratio']:.4f})",
        f"- Longest unavailable: {summary['longest_unavailable_duration_sec']:.3f}s",
        f"- Mean confidence: {summary['confidence']['mean']}",
        f"- Jump candidates: {report['angular_jump_candidates']['total_count']}", "",
        "## Axis summaries", "",
    ]
    for axis in ("yaw", "pitch", "roll"):
        lines.append(f"- {axis}: {json.dumps(summary[axis], ensure_ascii=False)}")
    lines += [
        "", "## Sign convention", "",
        "- yaw: left rotation negative, right rotation positive",
        "- pitch: down negative, up positive",
        "- roll: left tilt negative, right tilt positive", "",
        "## Camera limitation", "",
        "- No camera calibration was available.",
        "- focal length is approximated as frame width; principal point is frame center; distortion is zero.",
        "- Values are suitable for relative direction/change checks under the same camera setup, not guaranteed physical-angle accuracy.", "",
        "## Scope", "",
        "- Raw values are preserved; smoothing is not applied.",
        "- Missing frames remain null and are not filled with zero or a previous angle.",
        "- Angular jumps are diagnostic candidates, not automatic errors.",
        "- No gaze, iris, shoulder tilt, posture, attitude, or interview score is produced.",
    ]
    return "\n".join(lines) + "\n"


class HeadPoseValidator:
    def __init__(self, configuration: HeadPoseConfiguration = HeadPoseConfiguration()) -> None:
        self.configuration = configuration

    def validate(
        self, video_path: str | Path, *, analysis_fps: float = 5.0,
        output_root: str | Path = DEFAULT_HEAD_POSE_OUTPUT_ROOT,
        overwrite: bool = False, generate_overlay: bool = True,
        expected_source_sha256: str = "6cd4d7ac9d6dc546692d66c8c324dc7f09e1e20f5af846713bd1e119527bea32",
        video_analysis_root: str | Path = DEFAULT_VIDEO_OUTPUT_ROOT,
        temporal_output_root: str | Path = DEFAULT_TEMPORAL_OUTPUT_ROOT,
        target_output_root: str | Path = DEFAULT_TARGET_OUTPUT_ROOT,
    ) -> dict[str, Any]:
        metadata = inspect_video_metadata(video_path)
        source = Path(video_path).expanduser().resolve()
        expected_hash = expected_source_sha256
        if metadata["sha256"] != expected_hash:
            raise HeadPoseValidationError("SOURCE_SHA256_MISMATCH", "Input SHA-256 does not match the stage-7 validation video")
        safe_id = create_safe_video_id(source.name, metadata["sha256"])
        video_dir = Path(video_analysis_root) / safe_id
        temporal_dir = Path(temporal_output_root) / safe_id
        target_dir = Path(target_output_root) / safe_id
        analysis_path, frames_path = video_dir / "analysis.json", video_dir / "frames.jsonl"
        tracking_path = target_dir / "frame_target_metrics.jsonl"
        temporal_csv = temporal_dir / "landmark_timeseries.csv"
        protected_paths = [
            source, analysis_path, frames_path,
            *(path for path in temporal_dir.iterdir() if path.is_file()),
            *(path for path in target_dir.iterdir() if path.is_file()),
        ]
        if not all(path.is_file() for path in protected_paths) or not tracking_path.is_file() or not temporal_csv.is_file():
            raise HeadPoseValidationError("PROTECTED_INPUT_MISSING", "Required stage-5/6 input is missing")
        protected_hashes = {path: _sha(path) for path in protected_paths}
        analysis = _strict_json(analysis_path)
        if abs(float(analysis["configuration"]["effective_analysis_fps"]) - analysis_fps) > 1e-9:
            raise HeadPoseValidationError("ANALYSIS_FPS_MISMATCH", "Existing VIDEO analysis FPS does not match")
        frames, tracking = _strict_jsonl(frames_path), _strict_jsonl(tracking_path)
        if len(frames) != len(tracking) or any(left["timestamp_ms"] != right["timestamp_ms"] for left, right in zip(frames, tracking)):
            raise HeadPoseValidationError("TRACKING_ALIGNMENT_FAILED", "VIDEO and target tracking frames are not aligned")
        rows, previous_angles = [], None
        for frame, target in zip(frames, tracking):
            candidate_count = int(target["candidate_count"])
            selected = target.get("selected_candidate_index")
            target_id = target.get("target_id")
            if candidate_count >= 2:
                result = estimate_head_pose([], frame["frame_width"], frame["frame_height"], target_available=False, target_id=target_id)
                payload = result.to_dict()
                payload["failure_reason"] = HeadPoseFailureReason.MULTIPLE_PERSON_DETECTED.value
            else:
                result = estimate_head_pose(
                    frame.get("face_landmarks") or [],
                    frame["frame_width"], frame["frame_height"],
                    target_available=target_id == "TARGET_001" and selected is not None,
                    target_id=target_id,
                    target_confidence=float(target.get("target_confidence") or 0.0),
                    previous_angles=previous_angles,
                    configuration=self.configuration,
                )
                payload = result.to_dict()
            row = {
                "frame_index": frame["sample_index"],
                "sample_index": frame["sample_index"],
                "source_frame_index": frame["source_frame_index"],
                "timestamp_ms": frame["timestamp_ms"],
                "timestamp_sec": frame["timestamp_sec"],
                "target_id": target_id,
                "candidate_count": candidate_count,
                "selected_candidate_index": selected,
                "head_pose": payload,
                "raw_yaw_deg": payload["yaw_deg"],
                "raw_pitch_deg": payload["pitch_deg"],
                "raw_roll_deg": payload["roll_deg"],
                "smoothed_yaw_deg": None,
                "smoothed_pitch_deg": None,
                "smoothed_roll_deg": None,
                "angular_deltas": {"yaw_delta_deg": None, "pitch_delta_deg": None, "roll_delta_deg": None},
                "angular_jump_axes": [],
            }
            rows.append(row)
            previous_angles = (
                (payload["yaw_deg"], payload["pitch_deg"], payload["roll_deg"])
                if payload["available"] else None
            )
        deltas = calculate_angular_deltas(rows)
        for row, delta in zip(rows, deltas):
            row["angular_deltas"] = delta
        events, jump_diagnostics = detect_angular_jump_candidates(rows, self.configuration)
        event_axes: dict[int, list[str]] = {}
        for event in events:
            event_axes.setdefault(event["timestamp_ms"], []).append(event["details"]["axis"])
        for row in rows:
            row["angular_jump_axes"] = event_axes.get(row["timestamp_ms"], [])
        available_states = [row["head_pose"]["available"] for row in rows]
        timestamps = [row["timestamp_ms"] for row in rows]
        valid = [row["head_pose"] for row in rows if row["head_pose"]["available"]]
        failures = Counter(row["head_pose"]["failure_reason"] for row in rows if not row["head_pose"]["available"])
        summary = {
            "total_frame_count": len(rows),
            "available_frame_count": len(valid),
            "unavailable_frame_count": len(rows) - len(valid),
            "availability_ratio": calculate_detection_ratio(available_states),
            "longest_unavailable_duration_sec": calculate_longest_missing_duration(available_states, timestamps),
            "unavailable_segments": build_missing_segments(available_states, timestamps),
            "failure_reason_counts": dict(failures),
            "yaw": calculate_axis_summary([pose["yaw_deg"] for pose in valid]),
            "pitch": calculate_axis_summary([pose["pitch_deg"] for pose in valid]),
            "roll": calculate_axis_summary([pose["roll_deg"] for pose in valid]),
            "confidence": calculate_axis_summary([pose["confidence"] for pose in valid]),
            "reprojection_error": calculate_reprojection_summary([pose["reprojection_error"] for pose in valid]),
        }
        judgment = (
            "head_pose_analysis_failed"
            if not valid
            else "head_pose_raw_validation_passed_with_warnings"
            if len(valid) < len(rows) or events
            else "head_pose_raw_validation_passed"
        )
        destination = Path(output_root).resolve() / safe_id
        output_root_path = Path(output_root).resolve()
        if destination.exists() and not overwrite:
            raise HeadPoseValidationError("OUTPUT_ALREADY_EXISTS", f"Output exists: {destination}")
        output_root_path.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=f".{safe_id}.", dir=output_root_path))
        try:
            _write_jsonl(staged / "frame_head_pose_metrics.jsonl", rows)
            _write_jsonl(staged / "head_pose_events.jsonl", events)
            _write_csv(staged / "head_pose_timeseries.csv", temporal_csv, rows)
            if generate_overlay:
                _write_overlay(source, staged / "diagnostic_overlay.mp4", rows, analysis_fps)
            report = {
                "schema_version": "1.0", "validation_type": "raw_approximate_head_pose", "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": metadata,
                "configuration": {
                    **self.configuration.__dict__,
                    "analysis_fps": analysis_fps,
                    "landmark_indices": list(HEAD_POSE_LANDMARK_INDICES),
                    "model_points": [list(point) for point in HEAD_POSE_MODEL_POINTS],
                    "camera_matrix_source": "APPROX_FOCAL_LENGTH_EQUALS_FRAME_WIDTH",
                    "distortion_coefficients": [0.0, 0.0, 0.0, 0.0],
                    "smoothing_enabled": False,
                    "sign_convention": {
                        "yaw": "left_negative_right_positive",
                        "pitch": "down_negative_up_positive",
                        "roll": "left_tilt_negative_right_tilt_positive",
                    },
                    "gaze_enabled": False, "iris_enabled": False, "posture_scoring_enabled": False,
                    "interview_scoring_enabled": False,
                },
                "head_pose_summary": summary,
                "angular_jump_candidates": {"total_count": len(events), "by_axis": dict(Counter(event["details"]["axis"] for event in events)), "diagnostics": jump_diagnostics},
                "representative_frames": _representatives(rows),
                "quality_assessment": {
                    "technical_judgment": judgment,
                    "raw_values_only": True,
                    "evaluation_score_produced": False,
                },
                "limitations": [
                    "Camera calibration is unavailable; approximate intrinsics are used.",
                    "Absolute physical-angle accuracy is not guaranteed.",
                    "Results support relative direction/change checks under the same camera setup.",
                    "Face rotation can increase landmark loss.",
                    "No gaze, iris, posture, attitude, or interview score is produced.",
                ],
                "outputs": {
                    "validation_report_json": "validation_report.json",
                    "validation_report_markdown": "validation_report.md",
                    "frame_head_pose_metrics_jsonl": "frame_head_pose_metrics.jsonl",
                    "head_pose_events_jsonl": "head_pose_events.jsonl",
                    "head_pose_timeseries_csv": "head_pose_timeseries.csv",
                    "diagnostic_overlay_video": "diagnostic_overlay.mp4" if generate_overlay else None,
                },
                "warnings": ["Approximate camera intrinsics; raw values are not calibrated physical-angle measurements."],
                "errors": [],
            }
            (staged / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            (staged / "validation_report.md").write_text(_markdown(report), encoding="utf-8")
            if calculate_video_sha256(source) != expected_hash or any(_sha(path) != digest for path, digest in protected_hashes.items()):
                raise HeadPoseValidationError("PROTECTED_INPUT_CHANGED", "Input or stage-5/6 output changed")
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.old")
                os.replace(destination, backup)
                try:
                    os.replace(staged, destination)
                except OSError:
                    os.replace(backup, destination); raise
                shutil.rmtree(backup)
            else:
                os.replace(staged, destination)
            staged = None
            return report
        finally:
            if staged is not None:
                shutil.rmtree(staged, ignore_errors=True)
