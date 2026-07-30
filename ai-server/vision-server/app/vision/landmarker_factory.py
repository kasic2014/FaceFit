"""Validated MediaPipe IMAGE- and VIDEO-mode landmarker factories."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_matplotlib_cache = Path(tempfile.gettempdir()) / "face-fit-matplotlib"
_matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))

from mediapipe.tasks import python as tasks_python
from mediapipe.tasks.python import vision

from app.vision.model_registry import (
    ModelRegistryError,
    get_model_descriptor,
    require_model_ready,
)


class LandmarkerFactoryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _verified_model_path(model_id: str) -> str:
    descriptor = get_model_descriptor(model_id)
    try:
        state = require_model_ready(descriptor)
    except ModelRegistryError as exc:
        raise LandmarkerFactoryError(exc.code, str(exc)) from exc
    return str(descriptor.local_path.resolve(strict=False))


def create_face_landmarker_image_mode():
    """Create one caller-owned FaceLandmarker; the caller must close it."""

    model_path = _verified_model_path("face_landmarker")
    options = vision.FaceLandmarkerOptions(
        base_options=tasks_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    try:
        return vision.FaceLandmarker.create_from_options(options)
    except Exception as exc:
        raise LandmarkerFactoryError(
            "FACE_MODEL_LOAD_FAILED",
            f"Face Landmarker creation failed: {exc}",
        ) from exc


def create_pose_landmarker_image_mode():
    """Create one caller-owned PoseLandmarker; the caller must close it."""

    model_path = _verified_model_path("pose_landmarker")
    options = vision.PoseLandmarkerOptions(
        base_options=tasks_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_segmentation_masks=False,
    )
    try:
        return vision.PoseLandmarker.create_from_options(options)
    except Exception as exc:
        raise LandmarkerFactoryError(
            "POSE_MODEL_LOAD_FAILED",
            f"Pose Landmarker creation failed: {exc}",
        ) from exc


def create_face_landmarker_video_mode():
    """Create one caller-owned VIDEO-mode FaceLandmarker."""

    model_path = _verified_model_path("face_landmarker")
    options = vision.FaceLandmarkerOptions(
        base_options=tasks_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    try:
        return vision.FaceLandmarker.create_from_options(options)
    except Exception as exc:
        raise LandmarkerFactoryError(
            "FACE_MODEL_LOAD_FAILED",
            f"Face VIDEO Landmarker creation failed: {exc}",
        ) from exc


def create_pose_landmarker_video_mode():
    """Create one caller-owned VIDEO-mode PoseLandmarker."""

    model_path = _verified_model_path("pose_landmarker")
    options = vision.PoseLandmarkerOptions(
        base_options=tasks_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_segmentation_masks=False,
    )
    try:
        return vision.PoseLandmarker.create_from_options(options)
    except Exception as exc:
        raise LandmarkerFactoryError(
            "POSE_MODEL_LOAD_FAILED",
            f"Pose VIDEO Landmarker creation failed: {exc}",
        ) from exc


def create_face_landmarker_video_mode_multi_person(max_faces: int = 4):
    """Create a VIDEO FaceLandmarker that exposes multiple candidates."""

    if not isinstance(max_faces, int) or isinstance(max_faces, bool) or max_faces < 2:
        raise LandmarkerFactoryError(
            "INVALID_MAX_FACES",
            "max_faces must be an integer greater than or equal to 2.",
        )
    model_path = _verified_model_path("face_landmarker")
    options = vision.FaceLandmarkerOptions(
        base_options=tasks_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=max_faces,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    try:
        return vision.FaceLandmarker.create_from_options(options)
    except Exception as exc:
        raise LandmarkerFactoryError(
            "FACE_MODEL_LOAD_FAILED",
            f"Multi-candidate Face VIDEO Landmarker creation failed: {exc}",
        ) from exc


def create_pose_landmarker_video_mode_multi_person(max_poses: int = 4):
    """Create a VIDEO PoseLandmarker that exposes multiple candidates."""

    if not isinstance(max_poses, int) or isinstance(max_poses, bool) or max_poses < 2:
        raise LandmarkerFactoryError(
            "INVALID_MAX_POSES",
            "max_poses must be an integer greater than or equal to 2.",
        )
    model_path = _verified_model_path("pose_landmarker")
    options = vision.PoseLandmarkerOptions(
        base_options=tasks_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=max_poses,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_segmentation_masks=False,
    )
    try:
        return vision.PoseLandmarker.create_from_options(options)
    except Exception as exc:
        raise LandmarkerFactoryError(
            "POSE_MODEL_LOAD_FAILED",
            f"Multi-candidate Pose VIDEO Landmarker creation failed: {exc}",
        ) from exc
