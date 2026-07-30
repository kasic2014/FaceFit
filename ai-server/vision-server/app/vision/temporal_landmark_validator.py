"""Temporal validation of existing Face-Fit VIDEO landmark analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from app.core import config
from app.vision.temporal_landmark_metrics import (
    build_detection_segments,
    build_missing_segments,
    calculate_center_point,
    calculate_detection_ratio,
    calculate_frame_to_frame_displacement,
    calculate_longest_missing_duration,
    calculate_series_mad,
    calculate_series_median,
    calculate_shoulder_width,
    detect_coordinate_jump_candidates,
    sanitize_metric_number,
)
from app.vision.video_analyzer import DEFAULT_OUTPUT_ROOT, VideoAnalysisError, VideoAnalyzer
from app.vision.video_loader import calculate_video_sha256, create_safe_video_id, inspect_video_metadata
from app.vision.video_result_writer import AtomicJsonlWriter


DEFAULT_VALIDATION_OUTPUT_ROOT = config.OUTPUT_DIR / "motion_validation"
CSV_FIELDS = [
    "sample_index", "source_frame_index", "timestamp_ms", "timestamp_sec", "frame_status",
    "face_available", "nose_available", "left_ear_available", "right_ear_available",
    "left_shoulder_available", "right_shoulder_available", "required_shoulders_available",
    "face_and_shoulders_available", "face_bbox_center_x", "face_bbox_center_y",
    "nose_x", "nose_y", "nose_visibility", "nose_presence",
    "left_shoulder_x", "left_shoulder_y", "left_shoulder_visibility", "left_shoulder_presence",
    "right_shoulder_x", "right_shoulder_y", "right_shoulder_visibility", "right_shoulder_presence",
    "shoulder_center_x", "shoulder_center_y", "shoulder_width",
    "face_bbox_center_displacement", "nose_displacement", "left_shoulder_displacement",
    "right_shoulder_displacement", "shoulder_center_displacement", "shoulder_width_change", "warnings",
]


class TemporalValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TemporalValidationError("INVALID_VIDEO_ANALYSIS", f"Invalid JSON {path.name}: {exc}") from exc


def load_strict_frames(path: Path) -> list[dict[str, Any]]:
    rows, previous = [], None
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                raise ValueError(f"blank line {line_number}")
            row = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            timestamp = row.get("timestamp_ms")
            if not isinstance(row, dict) or not isinstance(timestamp, int):
                raise ValueError(f"invalid row/timestamp at line {line_number}")
            if previous is not None and timestamp <= previous:
                raise ValueError(f"non-increasing timestamp at line {line_number}")
            previous = timestamp
            rows.append(row)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TemporalValidationError("INVALID_FRAMES_JSONL", f"Invalid frames.jsonl: {exc}") from exc
    if not rows:
        raise TemporalValidationError("INVALID_FRAMES_JSONL", "frames.jsonl is empty")
    return rows


def _point(landmark: Any) -> dict[str, float | None] | None:
    if not isinstance(landmark, dict):
        return None
    x, y = sanitize_metric_number(landmark.get("x")), sanitize_metric_number(landmark.get("y"))
    if x is None or y is None:
        return None
    return {
        "x": x, "y": y,
        "visibility": sanitize_metric_number(landmark.get("visibility")),
        "presence": sanitize_metric_number(landmark.get("presence")),
    }


def _face_box(row: dict[str, Any]) -> dict[str, float] | None:
    box = row.get("face_bounding_box")
    width, height = row.get("frame_width"), row.get("frame_height")
    if not isinstance(box, dict) or not width or not height:
        return None
    values = [sanitize_metric_number(box.get(key)) for key in ("min_x", "max_x", "min_y", "max_y")]
    if any(value is None for value in values):
        return None
    return {
        "min_x": values[0] / width, "max_x": values[1] / width,
        "min_y": values[2] / height, "max_y": values[3] / height,
    }


def _face_center(row: dict[str, Any]) -> dict[str, float] | None:
    box = _face_box(row)
    if box is None:
        return None
    return {"x": (box["min_x"] + box["max_x"]) / 2, "y": (box["min_y"] + box["max_y"]) / 2}


def build_frame_metrics(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[Any]]]:
    metrics, series = [], {name: [] for name in (
        "face_bbox_center", "nose", "left_shoulder", "right_shoulder", "shoulder_center", "shoulder_width"
    )}
    for row in rows:
        required, optional = row.get("required_pose_landmarks") or {}, row.get("optional_pose_landmarks") or {}
        nose, left, right = _point(required.get("nose")), _point(required.get("left_shoulder")), _point(required.get("right_shoulder"))
        left_ear, right_ear = _point(optional.get("left_ear")), _point(optional.get("right_ear"))
        face_box, face_center = _face_box(row), _face_center(row)
        shoulder_center = calculate_center_point(left, right)
        shoulder_width = calculate_shoulder_width(left, right)
        points = {
            "face_bbox_center": face_center, "nose": nose, "left_shoulder": left,
            "right_shoulder": right, "shoulder_center": shoulder_center, "shoulder_width": shoulder_width,
        }
        for name, value in points.items():
            series[name].append(value)
        availability = {
            "face": face_center is not None, "nose": nose is not None,
            "left_ear": left_ear is not None, "right_ear": right_ear is not None,
            "left_shoulder": left is not None, "right_shoulder": right is not None,
        }
        availability["required_shoulders"] = availability["left_shoulder"] and availability["right_shoulder"]
        availability["optional_ears"] = availability["left_ear"] and availability["right_ear"]
        availability["face_and_shoulders"] = availability["face"] and availability["required_shoulders"]
        metrics.append({
            "sample_index": row.get("sample_index"), "source_frame_index": row.get("source_frame_index"),
            "timestamp_ms": row["timestamp_ms"], "timestamp_sec": row.get("timestamp_sec"),
            "frame_status": row.get("frame_status"), "availability": availability,
            "landmarks": {"nose": nose, "left_ear": left_ear, "right_ear": right_ear, "left_shoulder": left, "right_shoulder": right},
            "derived": {"face_bounding_box": face_box, "face_bbox_center": face_center, "shoulder_center": shoulder_center, "shoulder_width": shoulder_width},
            "displacements": {}, "jump_candidates": [], "warnings": list(row.get("warnings") or []),
        })
    for name in ("face_bbox_center", "nose", "left_shoulder", "right_shoulder", "shoulder_center"):
        for metric, value in zip(metrics, calculate_frame_to_frame_displacement(series[name])):
            metric["displacements"][name] = value
    previous_width = None
    for metric, width in zip(metrics, series["shoulder_width"]):
        metric["displacements"]["shoulder_width_change"] = (
            abs(width - previous_width) if width is not None and previous_width is not None else None
        )
        previous_width = width
    return metrics, series


def _availability_summary(metrics: list[dict[str, Any]], name: str) -> dict[str, Any]:
    states = [metric["availability"][name] for metric in metrics]
    timestamps = [metric["timestamp_ms"] for metric in metrics]
    detected = sum(states)
    detected_timestamps = [timestamp for state, timestamp in zip(states, timestamps) if state]
    return {
        "detected_frame_count": detected, "missing_frame_count": len(states) - detected,
        "detection_ratio": calculate_detection_ratio(states),
        "detected_segments": build_detection_segments(states, timestamps),
        "missing_segments": build_missing_segments(states, timestamps),
        "longest_missing_duration_sec": calculate_longest_missing_duration(states, timestamps),
        "first_detected_timestamp_ms": detected_timestamps[0] if detected_timestamps else None,
        "last_detected_timestamp_ms": detected_timestamps[-1] if detected_timestamps else None,
    }


def _write_csv(path: Path, metrics: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in metrics:
            a, l, d, disp = item["availability"], item["landmarks"], item["derived"], item["displacements"]
            def v(point: Any, key: str) -> Any:
                return point.get(key) if isinstance(point, dict) and point.get(key) is not None else ""
            row = {
                **{key: item.get(key, "") for key in CSV_FIELDS[:5]},
                "face_available": a["face"], "nose_available": a["nose"], "left_ear_available": a["left_ear"],
                "right_ear_available": a["right_ear"], "left_shoulder_available": a["left_shoulder"],
                "right_shoulder_available": a["right_shoulder"], "required_shoulders_available": a["required_shoulders"],
                "face_and_shoulders_available": a["face_and_shoulders"],
                "face_bbox_center_x": v(d["face_bbox_center"], "x"), "face_bbox_center_y": v(d["face_bbox_center"], "y"),
                "shoulder_center_x": v(d["shoulder_center"], "x"), "shoulder_center_y": v(d["shoulder_center"], "y"),
                "shoulder_width": d["shoulder_width"] if d["shoulder_width"] is not None else "",
                "warnings": " | ".join(item["warnings"]),
            }
            for name in ("nose", "left_shoulder", "right_shoulder"):
                for key in ("x", "y", "visibility", "presence"):
                    row[f"{name}_{key}"] = v(l[name], key)
            for name in ("face_bbox_center", "nose", "left_shoulder", "right_shoulder", "shoulder_center"):
                row[f"{name}_displacement"] = disp[name] if disp[name] is not None else ""
            row["shoulder_width_change"] = disp["shoulder_width_change"] if disp["shoulder_width_change"] is not None else ""
            writer.writerow(row)


def _write_overlay(source: Path, path: Path, metrics: list[dict[str, Any]], fps: float) -> None:
    capture = cv2.VideoCapture(str(source))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not capture.isOpened() or not writer.isOpened():
        capture.release(); writer.release()
        raise TemporalValidationError("DIAGNOSTIC_OVERLAY_FAILED", "Could not open diagnostic video")
    try:
        for metric in metrics:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(metric["source_frame_index"]))
            ok, frame = capture.read()
            if not ok:
                raise TemporalValidationError("DIAGNOSTIC_OVERLAY_FAILED", "Could not decode sampled frame")
            for name, color in (("nose", (0, 255, 255)), ("left_ear", (255, 255, 0)), ("right_ear", (255, 255, 0)), ("left_shoulder", (0, 255, 0)), ("right_shoulder", (0, 255, 0))):
                point = metric["landmarks"][name]
                if point:
                    cv2.circle(frame, (round(point["x"] * width), round(point["y"] * height)), 5, color, -1)
            left, right = metric["landmarks"]["left_shoulder"], metric["landmarks"]["right_shoulder"]
            box = metric["derived"]["face_bounding_box"]
            if box:
                cv2.rectangle(
                    frame,
                    (round(box["min_x"] * width), round(box["min_y"] * height)),
                    (round(box["max_x"] * width), round(box["max_y"] * height)),
                    (255, 128, 0), 2,
                )
            if left and right:
                cv2.line(frame, (round(left["x"]*width), round(left["y"]*height)), (round(right["x"]*width), round(right["y"]*height)), (0,255,0), 2)
            center = metric["derived"]["shoulder_center"]
            if center:
                cv2.circle(frame, (round(center["x"]*width), round(center["y"]*height)), 7, (255,0,255), 2)
            cv2.putText(frame, f'{metric["timestamp_ms"]/1000:.1f}s face={int(metric["availability"]["face"])} shoulders={int(metric["availability"]["required_shoulders"])} jumps={len(metric["jump_candidates"])}', (20,35), cv2.FONT_HERSHEY_SIMPLEX, .7, (255,255,255), 2)
            writer.write(frame)
    finally:
        capture.release(); writer.release()


def _markdown(report: dict[str, Any]) -> str:
    availability = report["detection_availability"]
    lines = [
        "# Real Motion Temporal Landmark Validation", "",
        f"- Judgment: `{report['quality_assessment']['technical_judgment']}`",
        f"- Source: `{report['source']['source_filename']}`",
        f"- SHA-256: `{report['source']['sha256']}`",
        f"- Analysis FPS: {report['configuration']['analysis_fps']}",
        f"- Sampled frames: {report['sampling']['sampled_frame_count']}", "",
        "## Detection availability", "",
    ]
    for name, value in availability.items():
        lines.append(f"- {name}: ratio={value['detection_ratio']:.4f}, longest missing={value['longest_missing_duration_sec']:.3f}s")
    lines += ["", "## Temporal stability", ""]
    for name, value in report["temporal_stability"].items():
        lines.append(f"- {name}: median={value['median']}, MAD={value['mad']}, method={value['method']}")
    lines += [
        "", "## Jump candidates", "",
        f"- Total diagnostic candidates: {report['jump_candidates']['total_count']}",
        "", "## Smoke criteria", "",
        "- Face availability >= 0.90",
        "- Required shoulders availability >= 0.90",
        "- Face + shoulders availability >= 0.85",
        "- Longest required landmark missing interval <= 1.0 s",
        "", "## Scope and limitations", "",
        "- This is a pipeline smoke criterion, not a calibrated product score.",
        "- One person, one scripted real-motion video; it does not establish population-level accuracy.",
        "- Coordinate jump candidates are diagnostics and do not automatically mean tracking failure.",
        "- No interpolation is applied to missing landmarks.",
        "- This report is not evidence for head pose, iris, gaze direction, shoulder tilt, or posture scoring.",
        "", "## Outputs", "",
    ]
    lines.extend(f"- {name}: `{path}`" for name, path in report["outputs"].items())
    return "\n".join(lines) + "\n"


class TemporalLandmarkValidator:
    def validate(
        self, video_path: str | Path, analysis_fps: float = 5.0, *,
        output_root: str | Path = DEFAULT_VALIDATION_OUTPUT_ROOT,
        video_analysis_root: str | Path = DEFAULT_OUTPUT_ROOT,
        overwrite: bool = False, reuse_video_analysis: bool = False,
        generate_diagnostic_overlay: bool = True,
    ) -> dict[str, Any]:
        if analysis_fps <= 0:
            raise TemporalValidationError("INVALID_ANALYSIS_FPS", "analysis_fps must be positive")
        try:
            metadata = inspect_video_metadata(video_path)
        except Exception as exc:
            raise TemporalValidationError(getattr(exc, "code", "INVALID_INPUT"), str(exc)) from exc
        source = Path(video_path).expanduser().resolve()
        source_hash = metadata["sha256"]
        safe_id = create_safe_video_id(source.name, source_hash)
        analysis_dir = Path(video_analysis_root).resolve() / safe_id
        analysis_json, frames_jsonl = analysis_dir / "analysis.json", analysis_dir / "frames.jsonl"
        if analysis_json.is_file() and frames_jsonl.is_file():
            analysis = _read_json(analysis_json)
            rows = load_strict_frames(frames_jsonl)
            matches = analysis.get("source", {}).get("sha256") == source_hash and abs(float(analysis.get("configuration", {}).get("requested_analysis_fps", -1)) - analysis_fps) < 1e-9
            if not matches:
                raise TemporalValidationError("VIDEO_ANALYSIS_MISMATCH", "Existing analysis SHA/FPS does not match the request")
            reused = True
        else:
            if reuse_video_analysis:
                raise TemporalValidationError("VIDEO_ANALYSIS_NOT_FOUND", "Matching reusable video analysis was not found")
            try:
                with VideoAnalyzer() as analyzer:
                    analysis = analyzer.analyze(source, analysis_fps, output_root=video_analysis_root, generate_overlay=True)
            except VideoAnalysisError as exc:
                raise TemporalValidationError(exc.code, str(exc)) from exc
            rows = load_strict_frames(frames_jsonl)
            reused = False
        protected = {path: _sha(path) for path in (analysis_json, frames_jsonl) if path.is_file()}
        metrics, series = build_frame_metrics(rows)
        timestamps = [item["timestamp_ms"] for item in metrics]
        stability, all_events = {}, []
        for name in ("face_bbox_center", "nose", "left_shoulder", "right_shoulder", "shoulder_center"):
            jump = detect_coordinate_jump_candidates(series[name], timestamps, name)
            stability[name] = {key: jump[key] for key in ("method", "median", "mad", "threshold")}
            all_events.extend(jump["events"])
        width_changes = [item["displacements"]["shoulder_width_change"] for item in metrics]
        stability["shoulder_width_change"] = {"method": "descriptive_only", "median": calculate_series_median(width_changes), "mad": calculate_series_mad(width_changes), "threshold": None}
        by_timestamp = {}
        for event in all_events:
            by_timestamp.setdefault(event["timestamp_ms"], []).append(event)
        for item in metrics:
            item["jump_candidates"] = by_timestamp.get(item["timestamp_ms"], [])
        availability = {name: _availability_summary(metrics, name) for name in (
            "face", "nose", "left_ear", "right_ear", "left_shoulder", "right_shoulder",
            "required_shoulders", "optional_ears", "face_and_shoulders"
        )}
        criteria = (
            availability["face"]["detection_ratio"] >= .90
            and availability["required_shoulders"]["detection_ratio"] >= .90
            and availability["face_and_shoulders"]["detection_ratio"] >= .85
            and all(availability[name]["longest_missing_duration_sec"] <= 1.0 for name in ("nose", "left_shoulder", "right_shoulder"))
        )
        if not criteria:
            judgment = "detection_availability_limited"
        elif all_events:
            judgment = "temporal_validation_passed_with_warnings"
        else:
            judgment = "temporal_validation_passed"
        output_root_path = Path(output_root).resolve()
        destination = output_root_path / safe_id
        if destination.exists() and not overwrite:
            raise TemporalValidationError("OUTPUT_ALREADY_EXISTS", f"Validation output already exists: {destination}")
        output_root_path.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=f".{safe_id}.", dir=output_root_path))
        try:
            with AtomicJsonlWriter(staged / "frame_metrics.jsonl") as writer:
                for item in metrics:
                    writer.write(item)
            _write_csv(staged / "landmark_timeseries.csv", metrics)
            if generate_diagnostic_overlay:
                _write_overlay(source, staged / "diagnostic_overlay.mp4", metrics, float(analysis["configuration"]["effective_analysis_fps"]))
            outputs = {
                "validation_report_json": "validation_report.json", "validation_report_markdown": "validation_report.md",
                "frame_metrics_jsonl": "frame_metrics.jsonl", "landmark_timeseries_csv": "landmark_timeseries.csv",
                "diagnostic_overlay_video": "diagnostic_overlay.mp4" if generate_diagnostic_overlay else None,
            }
            report = {
                "schema_version": "1.0", "validation_type": "real_motion_landmark_tracking", "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": metadata,
                "video_analysis_reference": {"directory": str(analysis_dir), "analysis_json_sha256": protected.get(analysis_json), "frames_jsonl_sha256": protected.get(frames_jsonl), "reused": reused},
                "configuration": {
                    "analysis_fps": analysis_fps, "required_landmarks": ["nose", "left_shoulder", "right_shoulder"],
                    "optional_landmarks": ["left_ear", "right_ear"], "head_pose_enabled": False,
                    "iris_enabled": False, "gaze_enabled": False, "shoulder_tilt_enabled": False,
                    "posture_scoring_enabled": False,
                },
                "sampling": analysis["sampling"], "detection_availability": availability,
                "temporal_stability": stability,
                "jump_candidates": {"total_count": len(all_events), "events": all_events},
                "quality_assessment": {
                    "technical_judgment": judgment, "smoke_criteria_passed": criteria,
                    "criteria": {"face_ratio_min": .90, "required_shoulders_ratio_min": .90, "face_and_shoulders_ratio_min": .85, "required_landmark_longest_missing_sec_max": 1.0},
                    "jump_candidates_auto_fail": False,
                },
                "limitations": [
                    "The models are configured for one target person; additional people can create target-selection ambiguity.",
                    "Not calibrated product scoring or population-level accuracy evidence.",
                    "No head pose, iris, gaze direction, shoulder tilt, or posture score.",
                    "Missing landmarks are not interpolated.",
                ],
                "outputs": outputs, "warnings": ["Jump candidates require visual review."] if all_events else [], "errors": [],
            }
            (staged / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            (staged / "validation_report.md").write_text(_markdown(report), encoding="utf-8")
            if calculate_video_sha256(source) != source_hash or any(_sha(path) != digest for path, digest in protected.items()):
                raise TemporalValidationError("PROTECTED_INPUT_CHANGED", "Input or reused video analysis changed during validation")
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
