"""Run multi-candidate inference and validate session-scoped target continuity."""

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

import cv2

from app.core import config
from app.vision.image_loader import convert_bgr_to_rgb, create_mediapipe_image
from app.vision.landmark_serializer import serialize_face_result, serialize_pose_result
from app.vision.landmarker_factory import (
    LandmarkerFactoryError,
    create_face_landmarker_video_mode_multi_person,
    create_pose_landmarker_video_mode_multi_person,
)
from app.vision.single_target_tracker import SingleTargetTracker
from app.vision.target_candidate_matcher import (
    DEFAULT_MATCH_WEIGHTS,
    calculate_face_pose_consistency,
)
from app.vision.target_tracking_models import (
    TargetCandidate,
    TargetStatus,
    TrackingConfiguration,
)
from app.vision.temporal_landmark_metrics import calculate_center_point, calculate_shoulder_width
from app.vision.temporal_landmark_validator import load_strict_frames
from app.vision.video_analyzer import DEFAULT_OUTPUT_ROOT
from app.vision.video_landmark_constants import extract_required_pose_landmarks
from app.vision.video_loader import calculate_video_sha256, create_safe_video_id, inspect_video_metadata


DEFAULT_TARGET_TRACKING_OUTPUT_ROOT = config.OUTPUT_DIR / "target_tracking_validation"
DEFAULT_TEMPORAL_OUTPUT_ROOT = config.OUTPUT_DIR / "motion_validation"
TRACKING_CSV_FIELDS = [
    "target_status", "target_id", "target_confidence", "candidate_count",
    "selected_candidate_index", "target_switch_risk", "reacquired",
    "best_candidate_score", "second_candidate_score", "score_margin", "ambiguity_reason",
]


class TargetTrackingValidationError(RuntimeError):
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
        raise TargetTrackingValidationError("INVALID_PROTECTED_ANALYSIS", f"{path.name}: {exc}") from exc


def _normalized_point(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        point = {"x": float(value["x"]), "y": float(value["y"])}
        for key in ("visibility", "presence"):
            if value.get(key) is not None:
                point[key] = float(value[key])
        return point
    except (KeyError, TypeError, ValueError):
        return None


def build_target_candidates(
    face_result: dict[str, Any],
    pose_result: dict[str, Any],
) -> list[TargetCandidate]:
    faces = face_result.get("faces") or []
    poses = pose_result.get("poses") or []
    candidates: list[TargetCandidate] = []
    used_faces: set[int] = set()
    for pose in poses:
        required = extract_required_pose_landmarks(pose.get("landmarks") or [])
        nose = _normalized_point(required.get("nose"))
        left = _normalized_point(required.get("left_shoulder"))
        right = _normalized_point(required.get("right_shoulder"))
        center = calculate_center_point(left, right)
        width = calculate_shoulder_width(left, right)
        best_face, best_consistency = None, None
        if nose and center and width:
            for face in faces:
                face_index = int(face.get("face_index", 0))
                if face_index in used_faces:
                    continue
                box = face.get("normalized_bounding_box")
                if not isinstance(box, dict):
                    continue
                face_center = {
                    "x": (box["min_x"] + box["max_x"]) / 2,
                    "y": (box["min_y"] + box["max_y"]) / 2,
                }
                consistency = calculate_face_pose_consistency(face_center, box, nose, center, width)
                if consistency is not None and (best_consistency is None or consistency < best_consistency):
                    best_face, best_consistency = face, consistency
        face_index, box, face_center = None, None, None
        if best_face is not None:
            face_index = int(best_face.get("face_index", 0))
            used_faces.add(face_index)
            box = {key: float(best_face["normalized_bounding_box"][key]) for key in ("min_x", "min_y", "max_x", "max_y")}
            face_center = {"x": (box["min_x"] + box["max_x"]) / 2, "y": (box["min_y"] + box["max_y"]) / 2}
        confidence_values = [
            point.get(key)
            for point in (nose, left, right)
            if point
            for key in ("visibility", "presence")
            if point.get(key) is not None
        ]
        pose_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else .5
        confidence = min(1.0, pose_confidence * (.85 if best_face else .65) + (.15 if best_face else 0.0))
        candidates.append(TargetCandidate(
            candidate_index=len(candidates),
            face_index=face_index,
            pose_index=int(pose.get("pose_index", 0)),
            face_bounding_box=box,
            face_center=face_center,
            nose=nose,
            left_shoulder=left,
            right_shoulder=right,
            shoulder_center=center,
            shoulder_width=width,
            detection_confidence=confidence,
            face_pose_consistency=best_consistency,
        ))
    return candidates


class MultiCandidateVideoExtractor:
    """One-pass multi-face/multi-pose inference at existing sampled timestamps."""

    def __init__(self, maximum_candidates: int = 4) -> None:
        self.maximum_candidates = maximum_candidates

    def extract(self, source: Path, sampled_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            face = create_face_landmarker_video_mode_multi_person(self.maximum_candidates)
            pose = create_pose_landmarker_video_mode_multi_person(self.maximum_candidates)
        except LandmarkerFactoryError as exc:
            raise TargetTrackingValidationError(exc.code, str(exc)) from exc
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            face.close(); pose.close()
            raise TargetTrackingValidationError("VIDEO_OPEN_FAILED", "Could not open target tracking input")
        outputs, current_index = [], 0
        try:
            for row in sampled_rows:
                wanted = int(row["source_frame_index"])
                frame = None
                while current_index <= wanted:
                    ok, decoded = capture.read()
                    if not ok:
                        raise TargetTrackingValidationError("VIDEO_DECODE_FAILED", f"Could not decode source frame {wanted}")
                    if current_index == wanted:
                        frame = decoded
                    current_index += 1
                image = create_mediapipe_image(convert_bgr_to_rgb(frame))
                timestamp = int(row["timestamp_ms"])
                faces = serialize_face_result(face.detect_for_video(image, timestamp), frame.shape[1], frame.shape[0])
                poses = serialize_pose_result(pose.detect_for_video(image, timestamp), frame.shape[1], frame.shape[0])
                candidates = build_target_candidates(faces, poses)
                outputs.append({
                    "sample_index": row["sample_index"],
                    "source_frame_index": wanted,
                    "timestamp_ms": timestamp,
                    "timestamp_sec": row["timestamp_sec"],
                    "face_candidate_count": faces["face_count"],
                    "pose_candidate_count": poses["pose_count"],
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                })
        except TargetTrackingValidationError:
            raise
        except Exception as exc:
            raise TargetTrackingValidationError("MULTI_CANDIDATE_INFERENCE_FAILED", str(exc)) from exc
        finally:
            capture.release()
            face.close()
            pose.close()
        return outputs


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
            stream.write("\n")


def _write_csv(path: Path, temporal_csv: Path, rows: list[dict[str, Any]]) -> None:
    with temporal_csv.open("r", encoding="utf-8-sig", newline="") as source:
        base_rows = list(csv.DictReader(source))
        base_fields = list(source.seek(0) or csv.reader(source).__next__())
    if len(base_rows) != len(rows):
        raise TargetTrackingValidationError("TEMPORAL_ROW_COUNT_MISMATCH", "Temporal CSV and tracking rows differ")
    with path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=[*base_fields, *TRACKING_CSV_FIELDS])
        writer.writeheader()
        for base, tracking in zip(base_rows, rows):
            writer.writerow({**base, **{field: tracking.get(field) for field in TRACKING_CSV_FIELDS}})


def _write_overlay(source: Path, path: Path, rows: list[dict[str, Any]], fps: float) -> None:
    capture = cv2.VideoCapture(str(source))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not capture.isOpened() or not writer.isOpened():
        capture.release(); writer.release()
        raise TargetTrackingValidationError("OVERLAY_FAILED", "Could not initialize tracking overlay")
    current_index = 0
    try:
        for row in rows:
            wanted = int(row["source_frame_index"])
            frame = None
            while current_index <= wanted:
                ok, decoded = capture.read()
                if not ok:
                    raise TargetTrackingValidationError("OVERLAY_FAILED", "Could not decode overlay frame")
                if current_index == wanted:
                    frame = decoded
                current_index += 1
            selected = row["selected_candidate_index"]
            for candidate in row["candidates"]:
                index, box = candidate["candidate_index"], candidate["face_bounding_box"]
                color = (0, 255, 0) if index == selected else (0, 165, 255)
                if box:
                    first = (round(box["min_x"] * width), round(box["min_y"] * height))
                    second = (round(box["max_x"] * width), round(box["max_y"] * height))
                    cv2.rectangle(frame, first, second, color, 3 if index == selected else 2)
                    cv2.putText(frame, f"C{index}", (first[0], max(20, first[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
                left, right = candidate["left_shoulder"], candidate["right_shoulder"]
                if left and right:
                    cv2.line(frame, (round(left["x"]*width), round(left["y"]*height)), (round(right["x"]*width), round(right["y"]*height)), color, 2)
            lines = [
                f'{row["timestamp_ms"]/1000:.1f}s {row["target_id"] or "NO_TARGET"} {row["target_status"]}',
                f'confidence={row["target_confidence"]:.3f} candidates={row["candidate_count"]} selected={selected}',
                f'switch_risk={row["target_switch_risk"]} ambiguous={row["target_status"] == TargetStatus.MULTIPLE_PERSON_AMBIGUOUS.value} reacquired={row["reacquired"]}',
            ]
            for index, text in enumerate(lines):
                cv2.putText(frame, text, (20, 32 + index * 28), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 4)
                cv2.putText(frame, text, (20, 32 + index * 28), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 2)
            writer.write(frame)
    finally:
        capture.release(); writer.release()


def _markdown(report: dict[str, Any]) -> str:
    summary = report["tracking_summary"]
    section = report["background_person_interval"]
    return (
        "# Single-target Tracking Validation\n\n"
        f"- Judgment: `{report['quality_assessment']['technical_judgment']}`\n"
        f"- Target ID: `{summary['target_id']}`\n"
        f"- Frames: {summary['total_frame_count']}\n"
        f"- Target ID changes: {summary['target_id_change_count']}\n"
        f"- Tracked: {summary['tracked_frame_count']}\n"
        f"- Temporarily lost: {summary['temporarily_lost_frame_count']}\n"
        f"- Ambiguous: {summary['ambiguous_frame_count']}\n"
        f"- Reacquired: {summary['reacquired_count']}\n"
        f"- Switch risks: {summary['target_switch_risk_count']}\n\n"
        "## Background-person interval (30–34 seconds)\n\n"
        f"- Maximum candidate count: {section['maximum_candidate_count']}\n"
        f"- Ambiguous frames: {section['ambiguous_frame_count']}\n"
        f"- Target ID changes: {section['target_id_change_count']}\n"
        f"- Assessment: {section['assessment']}\n\n"
        "## Limitations\n\n"
        "- MediaPipe Face and Pose candidates are independent and are joined using normalized geometry.\n"
        "- TARGET_001 is a session-local track label, not biometric identity.\n"
        "- This validates one scripted video and is not calibrated population-level scoring.\n"
        "- No head pose, iris, gaze, shoulder tilt, posture score, or identity recognition is produced.\n"
    )


class TargetTrackingValidator:
    def __init__(self, configuration: TrackingConfiguration = TrackingConfiguration()) -> None:
        self.configuration = configuration

    def validate(
        self, video_path: str | Path, *, analysis_fps: float = 5.0,
        output_root: str | Path = DEFAULT_TARGET_TRACKING_OUTPUT_ROOT,
        overwrite: bool = False, generate_overlay: bool = True,
        expected_source_sha256: str = "6cd4d7ac9d6dc546692d66c8c324dc7f09e1e20f5af846713bd1e119527bea32",
        video_analysis_root: str | Path = DEFAULT_OUTPUT_ROOT,
        temporal_output_root: str | Path = DEFAULT_TEMPORAL_OUTPUT_ROOT,
    ) -> dict[str, Any]:
        metadata = inspect_video_metadata(video_path)
        source = Path(video_path).expanduser().resolve()
        if metadata["sha256"] != expected_source_sha256:
            raise TargetTrackingValidationError("SOURCE_SHA256_MISMATCH", "Input SHA-256 does not match the stage-6 validation video")
        safe_id = create_safe_video_id(source.name, metadata["sha256"])
        analysis_dir = Path(video_analysis_root) / safe_id
        temporal_dir = Path(temporal_output_root) / safe_id
        analysis_path, frames_path = analysis_dir / "analysis.json", analysis_dir / "frames.jsonl"
        temporal_csv = temporal_dir / "landmark_timeseries.csv"
        protected_paths = [source, analysis_path, frames_path, *(path for path in temporal_dir.iterdir() if path.is_file())]
        if not all(path.is_file() for path in protected_paths) or not temporal_csv.is_file():
            raise TargetTrackingValidationError("PROTECTED_INPUT_MISSING", "Required stage-5 input or output is missing")
        protected_hashes = {path: _sha(path) for path in protected_paths}
        analysis = _strict_json(analysis_path)
        if abs(float(analysis["configuration"]["effective_analysis_fps"]) - analysis_fps) > 1e-9:
            raise TargetTrackingValidationError("ANALYSIS_FPS_MISMATCH", "Existing analysis is not 5 FPS")
        sampled_rows = load_strict_frames(frames_path)
        extracted = MultiCandidateVideoExtractor(self.configuration.maximum_candidates).extract(source, sampled_rows)
        tracker = SingleTargetTracker(self.configuration)
        initialization_frames = [
            (row["timestamp_ms"], row["candidates"])
            for row in extracted
            if row["timestamp_ms"] <= self.configuration.initialization_window_ms
        ]
        initial = tracker.select_initial_target(initialization_frames)
        output_rows, events = [], []
        for index, row in enumerate(extracted):
            if index == 0 and initial is not None:
                tracking, new_events = tracker.initialize(initial, row["timestamp_ms"])
            else:
                tracking, new_events = tracker.update(row["timestamp_ms"], row["candidates"])
            output_rows.append({
                **{key: row[key] for key in ("sample_index", "source_frame_index", "timestamp_ms", "timestamp_sec", "face_candidate_count", "pose_candidate_count")},
                **tracking,
                "candidates": [candidate.to_dict() for candidate in row["candidates"]],
            })
            events.extend(new_events)
        counts = Counter(row["target_status"] for row in output_rows)
        ids = [row["target_id"] for row in output_rows if row["target_id"]]
        id_changes = sum(current != previous for previous, current in zip(ids, ids[1:]))
        interval = [row for row in output_rows if 30_000 <= row["timestamp_ms"] <= 34_000]
        interval_ids = [row["target_id"] for row in interval if row["target_id"]]
        interval_changes = sum(current != previous for previous, current in zip(interval_ids, interval_ids[1:]))
        summary = {
            "target_id": ids[0] if ids else None,
            "total_frame_count": len(output_rows),
            "target_id_change_count": id_changes,
            "tracked_frame_count": counts[TargetStatus.TARGET_TRACKED.value] + counts[TargetStatus.TARGET_INITIALIZED.value],
            "temporarily_lost_frame_count": counts[TargetStatus.TARGET_TEMPORARILY_LOST.value],
            "ambiguous_frame_count": counts[TargetStatus.MULTIPLE_PERSON_AMBIGUOUS.value],
            "reacquired_frame_count": counts[TargetStatus.TARGET_REACQUIRED.value],
            "reacquired_count": sum(event["event_type"] == "TARGET_REACQUIRED" for event in events),
            "target_switch_risk_count": sum(event["event_type"] == "TARGET_SWITCH_RISK" for event in events),
            "target_lost_frame_count": counts[TargetStatus.TARGET_LOST.value],
            "maximum_candidate_count": max((row["candidate_count"] for row in output_rows), default=0),
        }
        background = {
            "start_timestamp_ms": 30_000, "end_timestamp_ms": 34_000,
            "frame_count": len(interval),
            "maximum_candidate_count": max((row["candidate_count"] for row in interval), default=0),
            "ambiguous_frame_count": sum(row["target_status"] == TargetStatus.MULTIPLE_PERSON_AMBIGUOUS.value for row in interval),
            "target_switch_risk_count": sum(row["target_switch_risk"] for row in interval),
            "target_id_change_count": interval_changes,
            "assessment": "TARGET_ID_RETAINED" if interval_changes == 0 else "TARGET_ID_CHANGED",
        }
        maximum_observed_candidates = summary["maximum_candidate_count"]
        judgment = (
            "target_tracking_validation_failed"
            if not initial or id_changes or summary["target_lost_frame_count"]
            else "target_tracking_passed_with_detection_limitations"
            if maximum_observed_candidates <= 1
            else "target_tracking_passed_with_warnings"
            if summary["ambiguous_frame_count"] or summary["target_switch_risk_count"]
            else "target_tracking_passed"
        )
        output_root_path, destination = Path(output_root).resolve(), Path(output_root).resolve() / safe_id
        if destination.exists() and not overwrite:
            raise TargetTrackingValidationError("OUTPUT_ALREADY_EXISTS", f"Output exists: {destination}")
        output_root_path.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=f".{safe_id}.", dir=output_root_path))
        try:
            _write_jsonl(staged / "frame_target_metrics.jsonl", output_rows)
            _write_jsonl(staged / "target_events.jsonl", events)
            _write_csv(staged / "target_timeseries.csv", temporal_csv, output_rows)
            if generate_overlay:
                _write_overlay(source, staged / "diagnostic_overlay.mp4", output_rows, analysis_fps)
            report = {
                "schema_version": "1.0", "validation_type": "single_target_tracking", "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": metadata,
                "configuration": {
                    **self.configuration.__dict__,
                    "analysis_fps": analysis_fps,
                    "match_weights": DEFAULT_MATCH_WEIGHTS.__dict__,
                    "head_pose_enabled": False, "iris_enabled": False, "gaze_enabled": False,
                    "shoulder_tilt_enabled": False, "posture_scoring_enabled": False,
                    "biometric_identity_enabled": False,
                },
                "tracking_summary": summary,
                "state_counts": dict(counts),
                "background_person_interval": background,
                "events": {"count": len(events), "types": dict(Counter(event["event_type"] for event in events))},
                "quality_assessment": {"technical_judgment": judgment, "target_switch_detected": bool(id_changes)},
                "limitations": [
                    "Face and Pose candidates are independent and joined by normalized geometry.",
                    "TARGET_001 is session-local and is not biometric identity.",
                    "Multiple candidates depend on MediaPipe detection availability.",
                ],
                "outputs": {
                    "validation_report_json": "validation_report.json",
                    "validation_report_markdown": "validation_report.md",
                    "frame_target_metrics_jsonl": "frame_target_metrics.jsonl",
                    "target_events_jsonl": "target_events.jsonl",
                    "target_timeseries_csv": "target_timeseries.csv",
                    "diagnostic_overlay_video": "diagnostic_overlay.mp4" if generate_overlay else None,
                },
                "warnings": (
                    ["No frame exposed more than one joined Face/Pose candidate; real multi-candidate ambiguity was not observable in this video."]
                    if maximum_observed_candidates <= 1 else []
                ),
                "errors": [],
            }
            (staged / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            (staged / "validation_report.md").write_text(_markdown(report), encoding="utf-8")
            if any(_sha(path) != digest for path, digest in protected_hashes.items()) or calculate_video_sha256(source) != metadata["sha256"]:
                raise TargetTrackingValidationError("PROTECTED_INPUT_CHANGED", "A protected stage-5 artifact changed")
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
