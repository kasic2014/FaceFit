"""Reusable one-image-at-a-time Face/Pose landmark analysis service."""

from __future__ import annotations

import json
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
from app.vision.image_loader import (
    ImageInputError,
    create_mediapipe_image,
    create_safe_image_id,
    convert_bgr_to_rgb,
    inspect_image_metadata,
    load_bgr_image,
)
from app.vision.landmark_serializer import (
    serialize_face_result,
    serialize_pose_result,
)
from app.vision.landmarker_factory import (
    LandmarkerFactoryError,
    create_face_landmarker_image_mode,
    create_pose_landmarker_image_mode,
)
from app.vision.model_registry import (
    get_model_descriptor,
    manifest_local_path,
    require_model_ready,
    write_json_atomic,
)
from app.vision.overlay_renderer import (
    OverlayRenderError,
    render_combined_overlay,
    render_face_overlay,
    render_pose_overlay,
    save_png_atomic,
)


DEFAULT_OUTPUT_ROOT = config.OUTPUT_DIR / "static_images"


class StaticImageAnalysisError(RuntimeError):
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


def _failed_detection(code: str, message: str, kind: str) -> dict[str, Any]:
    count_name = "face_count" if kind == "face" else "pose_count"
    items_name = "faces" if kind == "face" else "poses"
    return {
        "detection_status": "failed",
        count_name: 0,
        items_name: [],
        "warnings": [],
        "error": {"code": code, "message": message},
    }


def _integrated_status(
    face_result: dict[str, Any],
    pose_result: dict[str, Any],
) -> str:
    face_failed = face_result["detection_status"] == "failed"
    pose_failed = pose_result["detection_status"] == "failed"
    if face_failed and pose_failed:
        return "failed"
    if face_failed or pose_failed:
        return "partial_completed"
    face_count = face_result["face_count"]
    pose_count = pose_result["pose_count"]
    if face_count == 0 and pose_count == 0:
        return "completed_with_no_detections"
    if face_count == 0:
        return "completed_with_no_face"
    if pose_count == 0:
        return "completed_with_no_pose"
    return "completed"


class StaticImageAnalyzer:
    """Own one Face and one Pose landmarker for reuse across images."""

    def __init__(
        self,
        face_factory: Callable[[], Any] = create_face_landmarker_image_mode,
        pose_factory: Callable[[], Any] = create_pose_landmarker_image_mode,
    ) -> None:
        self._face_landmarker = None
        self._pose_landmarker = None
        self._closed = False
        try:
            self._face_landmarker = face_factory()
        except LandmarkerFactoryError as exc:
            raise StaticImageAnalysisError(
                "FACE_MODEL_NOT_READY",
                f"Face model is not ready: {exc}",
            ) from exc
        try:
            self._pose_landmarker = pose_factory()
        except LandmarkerFactoryError as exc:
            self.close()
            raise StaticImageAnalysisError(
                "POSE_MODEL_NOT_READY",
                f"Pose model is not ready: {exc}",
            ) from exc

        try:
            face_descriptor = get_model_descriptor("face_landmarker")
            pose_descriptor = get_model_descriptor("pose_landmarker")
            self._face_model_state = require_model_ready(face_descriptor)
            self._pose_model_state = require_model_ready(pose_descriptor)
            self._face_descriptor = face_descriptor
            self._pose_descriptor = pose_descriptor
        except Exception:
            self.close()
            raise

    def __enter__(self) -> "StaticImageAnalyzer":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for landmarker in (self._pose_landmarker, self._face_landmarker):
            if landmarker is not None:
                try:
                    landmarker.close()
                except Exception:
                    pass
        self._pose_landmarker = None
        self._face_landmarker = None

    def _ensure_open(self) -> None:
        if self._closed:
            raise StaticImageAnalysisError(
                "STATIC_IMAGE_ANALYSIS_FAILED",
                "StaticImageAnalyzer is already closed.",
            )

    def analyze(
        self,
        image_path: str | Path,
        *,
        output_root: str | Path = DEFAULT_OUTPUT_ROOT,
        overwrite: bool = False,
        generate_overlays: bool = True,
    ) -> dict[str, Any]:
        self._ensure_open()
        total_started = time.perf_counter()
        load_started = time.perf_counter()
        try:
            source_path, bgr_image = load_bgr_image(image_path)
        except ImageInputError as exc:
            raise StaticImageAnalysisError(exc.code, str(exc)) from exc
        metadata = inspect_image_metadata(source_path, bgr_image)
        source_hash_before = metadata["sha256"]
        rgb_image = convert_bgr_to_rgb(bgr_image)
        mp_image = create_mediapipe_image(rgb_image)
        image_load_sec = time.perf_counter() - load_started

        safe_image_id = create_safe_image_id(source_path.name, metadata["sha256"])
        output_root_path = Path(output_root).expanduser().resolve(strict=False)
        output_root_path.mkdir(parents=True, exist_ok=True)
        destination = output_root_path / safe_image_id
        if destination.exists() and not overwrite:
            raise StaticImageAnalysisError(
                "OUTPUT_ALREADY_EXISTS",
                f"Output already exists for image ID: {safe_image_id}",
            )

        face_started = time.perf_counter()
        try:
            raw_face_result = self._face_landmarker.detect(mp_image)
        except Exception as exc:
            face_result = _failed_detection(
                "FACE_INFERENCE_FAILED",
                f"Face inference failed: {exc}",
                "face",
            )
        else:
            try:
                face_result = serialize_face_result(
                    raw_face_result,
                    metadata["width"],
                    metadata["height"],
                )
            except Exception as exc:
                face_result = _failed_detection(
                    "LANDMARK_SERIALIZATION_FAILED",
                    f"Face landmark serialization failed: {exc}",
                    "face",
                )
        face_inference_sec = time.perf_counter() - face_started

        pose_started = time.perf_counter()
        try:
            raw_pose_result = self._pose_landmarker.detect(mp_image)
        except Exception as exc:
            pose_result = _failed_detection(
                "POSE_INFERENCE_FAILED",
                f"Pose inference failed: {exc}",
                "pose",
            )
        else:
            try:
                pose_result = serialize_pose_result(
                    raw_pose_result,
                    metadata["width"],
                    metadata["height"],
                )
            except Exception as exc:
                pose_result = _failed_detection(
                    "LANDMARK_SERIALIZATION_FAILED",
                    f"Pose landmark serialization failed: {exc}",
                    "pose",
                )
        pose_inference_sec = time.perf_counter() - pose_started

        status = _integrated_status(face_result, pose_result)
        errors = [
            result["error"]
            for result in (face_result, pose_result)
            if result["error"] is not None
        ]
        warnings = [
            *metadata["warnings"],
            *face_result["warnings"],
            *pose_result["warnings"],
        ]

        overlay_started = time.perf_counter()
        staged_root = Path(
            tempfile.mkdtemp(prefix=f".{safe_image_id}.", dir=output_root_path)
        )
        overlay_paths: dict[str, str | None] = {
            "face_overlay": None,
            "pose_overlay": None,
            "combined_overlay": None,
        }
        try:
            if generate_overlays:
                face_overlay, face_overlay_warnings = render_face_overlay(
                    bgr_image,
                    face_result,
                )
                pose_overlay, pose_overlay_warnings = render_pose_overlay(
                    bgr_image,
                    pose_result,
                )
                combined_overlay, combined_warnings = render_combined_overlay(
                    bgr_image,
                    face_result,
                    pose_result,
                )
                warnings.extend(
                    face_overlay_warnings
                    + pose_overlay_warnings
                    + combined_warnings
                )
                overlays = {
                    "face_overlay": ("face_overlay.png", face_overlay),
                    "pose_overlay": ("pose_overlay.png", pose_overlay),
                    "combined_overlay": ("combined_overlay.png", combined_overlay),
                }
                for key, (filename, image) in overlays.items():
                    save_png_atomic(image, staged_root / filename)
                    overlay_paths[key] = _relative(
                        destination / filename,
                        output_root_path,
                    )
            overlay_render_sec = time.perf_counter() - overlay_started

            analysis_path = destination / "analysis.json"
            source = {
                "filename": metadata["source_filename"],
                "relative_path": metadata["source_relative_path"],
                "extension": metadata["source_extension"],
                "file_size_bytes": metadata["file_size_bytes"],
                "sha256": metadata["sha256"],
                "width": metadata["width"],
                "height": metadata["height"],
                "channels": metadata["channels"],
                "dtype": metadata["dtype"],
            }
            result = {
                "schema_version": "1.0",
                "analysis_type": "static_image_landmark_detection",
                "status": status,
                "generated_at": _utc_now(),
                "source": source,
                "environment": {
                    "python_version": platform.python_version(),
                    "mediapipe_version": mediapipe.__version__,
                    "numpy_version": numpy.__version__,
                    "opencv_version": cv2.__version__,
                },
                "models": {
                    "face": {
                        "model_id": self._face_descriptor.model_id,
                        "variant": self._face_descriptor.variant,
                        "local_path": manifest_local_path(
                            self._face_descriptor.local_path
                        ),
                        "sha256": self._face_model_state["sha256"],
                    },
                    "pose": {
                        "model_id": self._pose_descriptor.model_id,
                        "variant": "full",
                        "local_path": manifest_local_path(
                            self._pose_descriptor.local_path
                        ),
                        "sha256": self._pose_model_state["sha256"],
                    },
                },
                "configuration": {
                    "running_mode": "IMAGE",
                    "num_faces": 1,
                    "num_poses": 1,
                    "blendshapes_enabled": False,
                    "transformation_matrixes_enabled": False,
                    "segmentation_masks_enabled": False,
                },
                "face_result": face_result,
                "pose_result": pose_result,
                "timing": {
                    "image_load_sec": image_load_sec,
                    "face_inference_sec": face_inference_sec,
                    "pose_inference_sec": pose_inference_sec,
                    "overlay_render_sec": overlay_render_sec if generate_overlays else 0.0,
                    "total_processing_sec": time.perf_counter() - total_started,
                },
                "outputs": {
                    "analysis_json": _relative(analysis_path, output_root_path),
                    **overlay_paths,
                },
                "warnings": warnings,
                "errors": errors,
            }
            try:
                write_json_atomic(result, staged_root / "analysis.json")
            except (OSError, TypeError, ValueError) as exc:
                raise StaticImageAnalysisError(
                    "STATIC_IMAGE_RESULT_WRITE_FAILED",
                    f"Could not write analysis JSON: {exc}",
                ) from exc

            if source_hash_before != inspect_image_metadata(source_path, bgr_image)["sha256"]:
                raise StaticImageAnalysisError(
                    "STATIC_IMAGE_ANALYSIS_FAILED",
                    "Input image changed during analysis.",
                )
            self._commit_staged_output(staged_root, destination, overwrite)
            staged_root = None
            return result
        except OverlayRenderError as exc:
            raise StaticImageAnalysisError(exc.code, str(exc)) from exc
        finally:
            if staged_root is not None:
                shutil.rmtree(staged_root, ignore_errors=True)

    @staticmethod
    def _commit_staged_output(
        staged_root: Path,
        destination: Path,
        overwrite: bool,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not destination.exists():
                os.replace(staged_root, destination)
                return
            if not overwrite:
                raise StaticImageAnalysisError(
                    "OUTPUT_ALREADY_EXISTS",
                    f"Output already exists: {destination.name}",
                )
            destination.mkdir(parents=True, exist_ok=True)
            staged_names = {path.name for path in staged_root.iterdir()}
            for old_name in (
                "analysis.json",
                "face_overlay.png",
                "pose_overlay.png",
                "combined_overlay.png",
            ):
                old_path = destination / old_name
                if old_path.exists() and old_name not in staged_names:
                    old_path.unlink()
            for staged_file in staged_root.iterdir():
                os.replace(staged_file, destination / staged_file.name)
            staged_root.rmdir()
        except StaticImageAnalysisError:
            raise
        except OSError as exc:
            raise StaticImageAnalysisError(
                "STATIC_IMAGE_RESULT_WRITE_FAILED",
                f"Could not commit static image output: {exc}",
            ) from exc
