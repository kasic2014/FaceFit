"""Sequential MediaPipe VIDEO-mode Face/Pose landmark analysis."""

from __future__ import annotations

import os
import platform
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import cv2
import mediapipe
import numpy

from app.core import config
from app.vision.frame_sampler import (
    DEFAULT_ANALYSIS_FPS,
    FrameSampler,
    FrameSamplingError,
)
from app.vision.image_loader import create_mediapipe_image, convert_bgr_to_rgb
from app.vision.landmark_serializer import (
    serialize_face_result,
    serialize_pose_result,
)
from app.vision.landmarker_factory import (
    LandmarkerFactoryError,
    create_face_landmarker_video_mode,
    create_pose_landmarker_video_mode,
)
from app.vision.model_registry import (
    get_model_descriptor,
    manifest_local_path,
    require_model_ready,
)
from app.vision.video_landmark_constants import (
    extract_optional_pose_landmarks,
    extract_required_pose_landmarks,
    get_optional_pose_landmark_indices,
    get_required_pose_landmark_indices,
    validate_required_pose_landmarks,
)
from app.vision.video_loader import (
    VideoInputError,
    calculate_video_sha256,
    create_safe_video_id,
    inspect_video_metadata,
    open_video_capture,
    release_video_capture,
)
from app.vision.video_overlay_renderer import (
    VideoOverlayError,
    VideoOverlayWriter,
    render_video_overlay_frame,
    save_sampled_frame_png,
)
from app.vision.video_result_writer import (
    AtomicJsonlWriter,
    VideoResultWriteError,
    write_video_analysis_json,
)


DEFAULT_OUTPUT_ROOT = config.OUTPUT_DIR / "videos"


class VideoAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _relative(path: Path, fallback_root: Path | None = None) -> str:
    try:
        return path.resolve(strict=False).relative_to(
            config.VISION_SERVER_ROOT
        ).as_posix()
    except ValueError:
        if fallback_root is not None:
            try:
                return path.resolve(strict=False).relative_to(
                    fallback_root.resolve(strict=False)
                ).as_posix()
            except ValueError:
                pass
        return path.name


def _failed_result(kind: str, code: str, message: str) -> dict[str, Any]:
    count_key = "face_count" if kind == "face" else "pose_count"
    items_key = "faces" if kind == "face" else "poses"
    return {
        "detection_status": "failed",
        count_key: 0,
        items_key: [],
        "warnings": [],
        "error": {"code": code, "message": message},
    }


def _frame_status(
    face_status: str,
    pose_status: str,
) -> str:
    face_failed = face_status == "face_inference_failed"
    pose_failed = pose_status == "pose_inference_failed"
    if face_failed and pose_failed:
        return "failed"
    if face_failed or pose_failed:
        return "partial_failure"
    face_detected = face_status == "detected"
    shoulders = pose_status == "detected_required_landmarks_available"
    if face_detected and shoulders:
        return "face_and_shoulders_detected"
    if face_detected:
        return "face_detected_shoulders_unavailable"
    if shoulders:
        return "shoulders_detected_face_unavailable"
    return "no_detections"


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator > 0 else None


class VideoAnalyzer:
    """Analyze exactly one video with one Face and one Pose VIDEO model."""

    def __init__(
        self,
        face_factory: Callable[[], Any] = create_face_landmarker_video_mode,
        pose_factory: Callable[[], Any] = create_pose_landmarker_video_mode,
    ) -> None:
        self._face_factory = face_factory
        self._pose_factory = pose_factory
        self._face_landmarker = None
        self._pose_landmarker = None
        self._closed = False
        self._used = False
        self.face_model_create_count = 0
        self.pose_model_create_count = 0
        self.face_model_close_count = 0
        self.pose_model_close_count = 0

    def __enter__(self) -> "VideoAnalyzer":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _release_models(self) -> None:
        if self._pose_landmarker is not None:
            try:
                self._pose_landmarker.close()
            finally:
                self.pose_model_close_count += 1
                self._pose_landmarker = None
        if self._face_landmarker is not None:
            try:
                self._face_landmarker.close()
            finally:
                self.face_model_close_count += 1
                self._face_landmarker = None

    def close(self) -> None:
        if self._closed:
            return
        self._release_models()
        self._closed = True

    def _load_models(self) -> tuple[float, float]:
        face_started = time.perf_counter()
        try:
            self._face_landmarker = self._face_factory()
            self.face_model_create_count += 1
        except LandmarkerFactoryError as exc:
            raise VideoAnalysisError(
                "FACE_MODEL_NOT_READY",
                f"Face VIDEO model is not ready: {exc}",
            ) from exc
        face_load_sec = time.perf_counter() - face_started
        pose_started = time.perf_counter()
        try:
            self._pose_landmarker = self._pose_factory()
            self.pose_model_create_count += 1
        except LandmarkerFactoryError as exc:
            self._release_models()
            raise VideoAnalysisError(
                "POSE_MODEL_NOT_READY",
                f"Pose VIDEO model is not ready: {exc}",
            ) from exc
        return face_load_sec, time.perf_counter() - pose_started

    def analyze(
        self,
        video_path: str | Path,
        analysis_fps: float = DEFAULT_ANALYSIS_FPS,
        *,
        output_root: str | Path = DEFAULT_OUTPUT_ROOT,
        overwrite: bool = False,
        generate_overlay: bool = True,
        require_overlay: bool = False,
        save_all_sampled_frames: bool = False,
    ) -> dict[str, Any]:
        if self._closed or self._used:
            raise VideoAnalysisError(
                "VIDEO_ANALYZER_UNAVAILABLE",
                "VideoAnalyzer is closed or has already analyzed a video.",
            )
        self._used = True
        total_started = time.perf_counter()
        try:
            metadata = inspect_video_metadata(video_path)
        except VideoInputError as exc:
            raise VideoAnalysisError(exc.code, str(exc)) from exc
        source_path = Path(video_path).expanduser().resolve(strict=False)
        source_hash_before = metadata["sha256"]
        safe_video_id = create_safe_video_id(source_path.name, source_hash_before)
        output_root_path = Path(output_root).expanduser().resolve(strict=False)
        output_root_path.mkdir(parents=True, exist_ok=True)
        destination = output_root_path / safe_video_id
        if destination.exists() and not overwrite:
            raise VideoAnalysisError(
                "OUTPUT_ALREADY_EXISTS",
                f"Output already exists for video ID: {safe_video_id}",
            )

        try:
            face_descriptor = get_model_descriptor("face_landmarker")
            pose_descriptor = get_model_descriptor("pose_landmarker")
            face_model_state = require_model_ready(face_descriptor)
            pose_model_state = require_model_ready(pose_descriptor)
        except Exception as exc:
            raise VideoAnalysisError(
                "MODEL_NOT_READY",
                f"VIDEO model integrity validation failed: {exc}",
            ) from exc

        staged_root = Path(
            tempfile.mkdtemp(prefix=f".{safe_video_id}.", dir=output_root_path)
        )
        capture = None
        overlay_writer: VideoOverlayWriter | None = None
        models_released = False
        try:
            open_started = time.perf_counter()
            capture = open_video_capture(source_path)
            video_open_sec = time.perf_counter() - open_started
            face_load_sec, pose_load_sec = self._load_models()
            sampler = FrameSampler(
                capture,
                metadata["original_fps"],
                analysis_fps,
            )
            overlay_path = staged_root / "combined_overlay.mp4"
            overlay_status = "disabled"
            warnings = list(metadata["warnings"])
            if generate_overlay:
                overlay_writer = VideoOverlayWriter(
                    overlay_path,
                    sampler.effective_analysis_fps,
                    metadata["width"],
                    metadata["height"],
                )
                if overlay_writer.available:
                    overlay_status = "available"
                else:
                    overlay_status = "unavailable"
                    warning = "Overlay VideoWriter mp4v is unavailable."
                    warnings.append(warning)
                    if require_overlay:
                        raise VideoAnalysisError("VIDEO_OVERLAY_FAILED", warning)

            face_inference_total = 0.0
            pose_inference_total = 0.0
            overlay_render_total = 0.0
            frame_processing_total = 0.0
            records: list[dict[str, Any]] = []
            status_counts: dict[str, int] = {
                "face_and_shoulders_detected": 0,
                "face_detected_shoulders_unavailable": 0,
                "shoulders_detected_face_unavailable": 0,
                "no_detections": 0,
                "partial_failure": 0,
                "failed": 0,
            }
            face_detected_count = 0
            pose_detected_count = 0
            shoulders_count = 0
            face_shoulders_count = 0
            face_detect_calls = 0
            pose_detect_calls = 0
            candidate_directory = staged_root / ".sampled_candidates"
            frames_path = staged_root / "frames.jsonl"

            loop_started = time.perf_counter()
            with AtomicJsonlWriter(frames_path) as jsonl_writer:
                for sample in sampler:
                    frame_started = time.perf_counter()
                    mp_image = create_mediapipe_image(
                        convert_bgr_to_rgb(sample.bgr_frame)
                    )
                    face_started = time.perf_counter()
                    try:
                        face_detect_calls += 1
                        raw_face = self._face_landmarker.detect_for_video(
                            mp_image,
                            sample.timestamp_ms,
                        )
                        face_result = serialize_face_result(
                            raw_face,
                            sample.width,
                            sample.height,
                        )
                    except Exception as exc:
                        face_result = _failed_result(
                            "face",
                            "FACE_INFERENCE_FAILED",
                            f"Face VIDEO inference failed: {exc}",
                        )
                    face_sec = time.perf_counter() - face_started
                    face_inference_total += face_sec

                    pose_started = time.perf_counter()
                    try:
                        pose_detect_calls += 1
                        raw_pose = self._pose_landmarker.detect_for_video(
                            mp_image,
                            sample.timestamp_ms,
                        )
                        pose_result = serialize_pose_result(
                            raw_pose,
                            sample.width,
                            sample.height,
                        )
                    except Exception as exc:
                        pose_result = _failed_result(
                            "pose",
                            "POSE_INFERENCE_FAILED",
                            f"Pose VIDEO inference failed: {exc}",
                        )
                    pose_sec = time.perf_counter() - pose_started
                    pose_inference_total += pose_sec

                    face = (
                        face_result["faces"][0]
                        if face_result.get("face_count", 0) > 0
                        else None
                    )
                    pose = (
                        pose_result["poses"][0]
                        if pose_result.get("pose_count", 0) > 0
                        else None
                    )
                    pose_landmarks = pose["landmarks"] if pose else []
                    required = extract_required_pose_landmarks(pose_landmarks)
                    optional = extract_optional_pose_landmarks(pose_landmarks)
                    required_available = validate_required_pose_landmarks(required)
                    face_status = (
                        "face_inference_failed"
                        if face_result["detection_status"] == "failed"
                        else face_result["detection_status"]
                    )
                    if pose_result["detection_status"] == "failed":
                        pose_status = "pose_inference_failed"
                    elif pose_result.get("pose_count", 0) == 0:
                        pose_status = "no_pose_detected"
                    elif required_available:
                        pose_status = "detected_required_landmarks_available"
                    else:
                        pose_status = "detected_required_landmarks_incomplete"
                    integrated = _frame_status(face_status, pose_status)
                    status_counts[integrated] += 1
                    face_detected_count += int(face_status == "detected")
                    pose_detected_count += int(pose_result.get("pose_count", 0) > 0)
                    shoulders_count += int(required_available)
                    face_shoulders_count += int(
                        integrated == "face_and_shoulders_detected"
                    )
                    frame_warnings = [
                        *face_result.get("warnings", []),
                        *pose_result.get("warnings", []),
                    ]
                    frame_errors = [
                        error
                        for error in (
                            face_result.get("error"),
                            pose_result.get("error"),
                        )
                        if error is not None
                    ]
                    row = {
                        "sample_index": sample.sample_index,
                        "source_frame_index": sample.source_frame_index,
                        "timestamp_ms": sample.timestamp_ms,
                        "timestamp_sec": sample.timestamp_sec,
                        "frame_width": sample.width,
                        "frame_height": sample.height,
                        "face_detection_status": face_status,
                        "face_count": face_result.get("face_count", 0),
                        "face_landmarks": face["landmarks"] if face else [],
                        "face_bounding_box": (
                            face["pixel_bounding_box"] if face else None
                        ),
                        "pose_detection_status": pose_status,
                        "pose_count": pose_result.get("pose_count", 0),
                        "pose_landmarks": pose_landmarks,
                        "pose_world_landmarks": (
                            pose["world_landmarks"] if pose else []
                        ),
                        "pose_bounding_box": (
                            pose["pixel_bounding_box"] if pose else None
                        ),
                        "required_pose_landmarks": required,
                        "required_pose_landmarks_available": required_available,
                        "optional_pose_landmarks": optional,
                        "frame_status": integrated,
                        "face_inference_sec": face_sec,
                        "pose_inference_sec": pose_sec,
                        "frame_processing_sec": 0.0,
                        "warnings": frame_warnings,
                        "errors": frame_errors,
                    }
                    overlay_started = time.perf_counter()
                    overlay_frame = render_video_overlay_frame(sample.bgr_frame, row)
                    if overlay_writer is not None and overlay_writer.available:
                        overlay_writer.write(overlay_frame)
                    candidate_name = (
                        f"frame_{sample.source_frame_index:06d}_"
                        f"{sample.timestamp_ms:06d}ms.png"
                    )
                    save_sampled_frame_png(
                        overlay_frame,
                        candidate_directory / candidate_name,
                    )
                    overlay_render_total += time.perf_counter() - overlay_started
                    row["frame_processing_sec"] = time.perf_counter() - frame_started
                    frame_processing_total += row["frame_processing_sec"]
                    jsonl_writer.write(row)
                    records.append(
                        {
                            "sample_index": sample.sample_index,
                            "frame_status": integrated,
                            "candidate_name": candidate_name,
                        }
                    )
            loop_total = time.perf_counter() - loop_started
            sampling = sampler.summary()
            if sampling["sampled_frame_count"] == 0:
                raise VideoAnalysisError(
                    "NO_SAMPLED_FRAMES",
                    "Video produced zero sampled frames.",
                )
            if not sampling["timestamps_strictly_increasing"]:
                raise VideoAnalysisError(
                    "FRAME_TIMESTAMP_NOT_INCREASING",
                    "Sampled timestamps are not strictly increasing.",
                )
            if status_counts["failed"] == sampling["sampled_frame_count"]:
                raise VideoAnalysisError(
                    "ALL_FRAME_INFERENCE_FAILED",
                    "Face and Pose inference failed for every sampled frame.",
                )

            if overlay_writer is not None:
                overlay_writer.close(commit=overlay_writer.available)
                if overlay_status == "available" and not overlay_path.is_file():
                    overlay_status = "unavailable"
                    warnings.append("Overlay video was not committed.")
                    if require_overlay:
                        raise VideoAnalysisError(
                            "VIDEO_OVERLAY_FAILED",
                            "Required overlay video was not committed.",
                        )

            sampled_directory = staged_root / "sampled_frames"
            sampled_directory.mkdir(parents=True, exist_ok=True)
            selected_indices: set[int]
            if save_all_sampled_frames:
                selected_indices = {record["sample_index"] for record in records}
            else:
                selected_indices = {
                    0,
                    len(records) // 2,
                    len(records) - 1,
                }
                previous_status = records[0]["frame_status"]
                for record in records[1:]:
                    if record["frame_status"] != previous_status:
                        selected_indices.add(record["sample_index"])
                    previous_status = record["frame_status"]
            for record in records:
                candidate = candidate_directory / record["candidate_name"]
                if record["sample_index"] in selected_indices:
                    os.replace(candidate, sampled_directory / candidate.name)
            shutil.rmtree(candidate_directory, ignore_errors=True)

            release_video_capture(capture)
            capture = None
            self._release_models()
            models_released = True
            sample_count = int(sampling["sampled_frame_count"])
            if metadata["estimated_duration_sec"] is None:
                metadata["estimated_duration_sec"] = (
                    int(sampling["decoded_frame_count"]) / metadata["original_fps"]
                )
            detection_summary = {
                "face_detected_frame_count": face_detected_count,
                "face_not_detected_frame_count": sample_count - face_detected_count,
                "pose_detected_frame_count": pose_detected_count,
                "required_shoulders_available_frame_count": shoulders_count,
                "face_and_shoulders_detected_frame_count": face_shoulders_count,
                "partial_failure_frame_count": status_counts["partial_failure"],
                "failed_frame_count": status_counts["failed"],
                "face_detected_ratio": _safe_ratio(face_detected_count, sample_count),
                "required_shoulders_available_ratio": _safe_ratio(
                    shoulders_count, sample_count
                ),
                "face_and_shoulders_detected_ratio": _safe_ratio(
                    face_shoulders_count, sample_count
                ),
                "frame_status_counts": status_counts,
            }
            if status_counts["failed"] or status_counts["partial_failure"]:
                status = "partial_completed"
            elif warnings:
                status = "completed_with_warnings"
            else:
                status = "completed"
            total_sec = time.perf_counter() - total_started
            duration = metadata["estimated_duration_sec"]
            result = {
                "schema_version": "1.0",
                "analysis_type": "video_landmark_detection",
                "status": status,
                "generated_at": _utc_now(),
                "source": metadata,
                "environment": {
                    "python_version": platform.python_version(),
                    "mediapipe_version": mediapipe.__version__,
                    "numpy_version": numpy.__version__,
                    "opencv_version": cv2.__version__,
                },
                "models": {
                    "face": {
                        "model_id": face_descriptor.model_id,
                        "variant": face_descriptor.variant,
                        "local_path": manifest_local_path(
                            face_descriptor.local_path
                        ),
                        "sha256": face_model_state["sha256"],
                    },
                    "pose": {
                        "model_id": pose_descriptor.model_id,
                        "variant": "full",
                        "local_path": manifest_local_path(
                            pose_descriptor.local_path
                        ),
                        "sha256": pose_model_state["sha256"],
                    },
                },
                "configuration": {
                    "running_mode": "VIDEO",
                    "requested_analysis_fps": float(analysis_fps),
                    "effective_analysis_fps": sampling["effective_analysis_fps"],
                    "num_faces": 1,
                    "num_poses": 1,
                    "required_pose_landmarks": list(
                        get_required_pose_landmark_indices()
                    ),
                    "optional_pose_landmarks": list(
                        get_optional_pose_landmark_indices()
                    ),
                    "head_pose_enabled": False,
                    "gaze_enabled": False,
                    "posture_scoring_enabled": False,
                },
                "sampling": sampling,
                "detection_summary": detection_summary,
                "timing": {
                    "video_open_sec": video_open_sec,
                    "face_model_load_sec": face_load_sec,
                    "pose_model_load_sec": pose_load_sec,
                    "decoding_sec": max(
                        0.0,
                        loop_total
                        - face_inference_total
                        - pose_inference_total
                        - overlay_render_total,
                    ),
                    "face_inference_total_sec": face_inference_total,
                    "pose_inference_total_sec": pose_inference_total,
                    "overlay_render_total_sec": overlay_render_total,
                    "frame_processing_total_sec": frame_processing_total,
                    "total_processing_sec": total_sec,
                    "processing_realtime_factor": (
                        total_sec / duration if duration and duration > 0 else None
                    ),
                },
                "resources": {
                    "face_model_create_count": self.face_model_create_count,
                    "pose_model_create_count": self.pose_model_create_count,
                    "face_detect_for_video_call_count": face_detect_calls,
                    "pose_detect_for_video_call_count": pose_detect_calls,
                    "face_model_close_count": self.face_model_close_count,
                    "pose_model_close_count": self.pose_model_close_count,
                    "capture_released": True,
                },
                "outputs": {
                    "analysis_json": _relative(
                        destination / "analysis.json", output_root_path
                    ),
                    "frames_jsonl": _relative(
                        destination / "frames.jsonl", output_root_path
                    ),
                    "combined_overlay_video": (
                        _relative(
                            destination / "combined_overlay.mp4",
                            output_root_path,
                        )
                        if overlay_status == "available"
                        else None
                    ),
                    "overlay_status": overlay_status,
                    "overlay_codec": (
                        overlay_writer.codec
                        if overlay_status == "available" and overlay_writer
                        else None
                    ),
                    "sampled_frames_directory": _relative(
                        destination / "sampled_frames", output_root_path
                    ),
                    "saved_sampled_frame_count": len(selected_indices),
                },
                "warnings": warnings,
                "errors": [],
            }
            write_video_analysis_json(result, staged_root / "analysis.json")
            if calculate_video_sha256(source_path) != source_hash_before:
                raise VideoAnalysisError(
                    "VIDEO_INPUT_CHANGED",
                    "Input video changed during analysis.",
                )
            self._commit_staged_output(staged_root, destination, overwrite)
            staged_root = None
            return result
        except (
            VideoInputError,
            FrameSamplingError,
            VideoOverlayError,
            VideoResultWriteError,
        ) as exc:
            raise VideoAnalysisError(getattr(exc, "code", "VIDEO_ANALYSIS_FAILED"), str(exc))
        finally:
            release_video_capture(capture)
            if overlay_writer is not None and overlay_writer.available:
                overlay_writer.close(commit=False)
            if not models_released:
                self._release_models()
            if staged_root is not None:
                shutil.rmtree(staged_root, ignore_errors=True)

    @staticmethod
    def _commit_staged_output(
        staged_root: Path,
        destination: Path,
        overwrite: bool,
    ) -> None:
        try:
            if not destination.exists():
                os.replace(staged_root, destination)
                return
            if not overwrite:
                raise VideoAnalysisError(
                    "OUTPUT_ALREADY_EXISTS",
                    f"Output already exists: {destination.name}",
                )
            backup = destination.with_name(f".{destination.name}.old")
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(destination, backup)
            try:
                os.replace(staged_root, destination)
            except OSError:
                os.replace(backup, destination)
                raise
            shutil.rmtree(backup)
        except VideoAnalysisError:
            raise
        except OSError as exc:
            raise VideoAnalysisError(
                "VIDEO_RESULT_WRITE_FAILED",
                f"Could not commit video output: {exc}",
            ) from exc
