"""Approximate-camera solvePnP head pose from selected face landmarks."""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from app.vision.head_pose_models import (
    HEAD_POSE_LANDMARK_INDICES,
    HEAD_POSE_MODEL_POINTS,
    HeadPoseConfiguration,
    HeadPoseFailureReason,
    HeadPoseResult,
)


ESTIMATION_METHOD = "PNP_APPROX_CAMERA"
CAMERA_MATRIX_SOURCE = "APPROX_FOCAL_LENGTH_EQUALS_FRAME_WIDTH"


def create_approximate_camera_matrix(
    width: int | float,
    height: int | float,
    focal_length_width_multiplier: float = 1.0,
) -> np.ndarray:
    values = (width, height, focal_length_width_multiplier)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0 for value in values):
        raise ValueError("width, height, and focal multiplier must be positive finite numbers")
    focal = float(width) * float(focal_length_width_multiplier)
    return np.array(
        [[focal, 0.0, float(width) / 2], [0.0, focal, float(height) / 2], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def _unavailable(
    reason: HeadPoseFailureReason,
    *,
    target_id: str | None,
    landmark_count: int = 0,
    solvepnp_success: bool = False,
    reprojection_error: float | None = None,
) -> HeadPoseResult:
    return HeadPoseResult(
        available=False,
        yaw_deg=None,
        pitch_deg=None,
        roll_deg=None,
        confidence=0.0,
        estimation_method=ESTIMATION_METHOD,
        failure_reason=reason.value,
        solvepnp_success=solvepnp_success,
        reprojection_error=reprojection_error,
        landmark_count=landmark_count,
        camera_matrix_source=CAMERA_MATRIX_SOURCE,
        target_id=target_id,
    )


def _bbox_area(landmarks: list[dict[str, Any]]) -> float:
    valid = [
        (float(item["x"]), float(item["y"]))
        for item in landmarks
        if isinstance(item, dict)
        and isinstance(item.get("x"), (int, float))
        and isinstance(item.get("y"), (int, float))
        and math.isfinite(float(item["x"]))
        and math.isfinite(float(item["y"]))
    ]
    if not valid:
        return 0.0
    xs, ys = zip(*valid)
    return max(0.0, max(xs) - min(xs)) * max(0.0, max(ys) - min(ys))


def estimate_head_pose(
    face_landmarks: list[dict[str, Any]],
    frame_width: int,
    frame_height: int,
    *,
    target_available: bool,
    target_id: str | None,
    target_confidence: float = 0.0,
    previous_angles: tuple[float, float, float] | None = None,
    configuration: HeadPoseConfiguration = HeadPoseConfiguration(),
) -> HeadPoseResult:
    if not target_available or target_id is None:
        return _unavailable(HeadPoseFailureReason.TARGET_NOT_AVAILABLE, target_id=target_id)
    if not face_landmarks:
        return _unavailable(HeadPoseFailureReason.FACE_NOT_DETECTED, target_id=target_id)
    by_index = {item.get("index"): item for item in face_landmarks if isinstance(item, dict)}
    selected, image_points = [], []
    for index in HEAD_POSE_LANDMARK_INDICES:
        item = by_index.get(index)
        if not isinstance(item, dict):
            return _unavailable(HeadPoseFailureReason.REQUIRED_LANDMARK_MISSING, target_id=target_id, landmark_count=len(selected))
        try:
            x, y = float(item["x"]), float(item["y"])
        except (KeyError, TypeError, ValueError):
            return _unavailable(HeadPoseFailureReason.INVALID_LANDMARK_COORDINATE, target_id=target_id, landmark_count=len(selected))
        if not math.isfinite(x) or not math.isfinite(y) or not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            return _unavailable(HeadPoseFailureReason.INVALID_LANDMARK_COORDINATE, target_id=target_id, landmark_count=len(selected))
        selected.append(item)
        image_points.append((x * frame_width, y * frame_height))
    try:
        camera = create_approximate_camera_matrix(
            frame_width,
            frame_height,
            configuration.focal_length_width_multiplier,
        )
    except ValueError:
        return _unavailable(HeadPoseFailureReason.INVALID_LANDMARK_COORDINATE, target_id=target_id, landmark_count=len(selected))
    model = np.asarray(HEAD_POSE_MODEL_POINTS, dtype=np.float64)
    image = np.asarray(image_points, dtype=np.float64)
    distortion = np.zeros((4, 1), dtype=np.float64)
    try:
        # SQPnP avoids the mirrored negative-depth solution that an unguided
        # iterative solve can choose for this near-planar six-point template.
        success, rotation_vector, translation_vector = cv2.solvePnP(
            model, image, camera, distortion, flags=cv2.SOLVEPNP_SQPNP
        )
        if success and float(translation_vector[2, 0]) > 0:
            success, rotation_vector, translation_vector = cv2.solvePnP(
                model,
                image,
                camera,
                distortion,
                rotation_vector,
                translation_vector,
                True,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
    except cv2.error:
        success = False
    if not success or float(translation_vector[2, 0]) <= 0:
        return _unavailable(HeadPoseFailureReason.SOLVEPNP_FAILED, target_id=target_id, landmark_count=len(selected))
    try:
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        decomposed = cv2.RQDecomp3x3(rotation_matrix)
        euler = decomposed[0]
        # Convert OpenCV camera-axis signs to the public subject-relative rule:
        # yaw left -, right +; pitch down -, up +;
        # roll left tilt -, right tilt +.
        pitch, yaw, roll = float(euler[0]), -float(euler[1]), -float(euler[2])
    except (cv2.error, TypeError, ValueError, IndexError):
        return _unavailable(HeadPoseFailureReason.ROTATION_CONVERSION_FAILED, target_id=target_id, landmark_count=len(selected), solvepnp_success=True)
    projected, _ = cv2.projectPoints(model, rotation_vector, translation_vector, camera, distortion)
    residuals = projected.reshape(-1, 2) - image
    reprojection_error = float(np.sqrt(np.mean(np.sum(residuals * residuals, axis=1))))
    if not all(math.isfinite(value) for value in (yaw, pitch, roll, reprojection_error)):
        return _unavailable(HeadPoseFailureReason.NON_FINITE_RESULT, target_id=target_id, landmark_count=len(selected), solvepnp_success=True)
    if reprojection_error > configuration.max_reprojection_error_px:
        return _unavailable(
            HeadPoseFailureReason.REPROJECTION_ERROR_TOO_HIGH,
            target_id=target_id,
            landmark_count=len(selected),
            solvepnp_success=True,
            reprojection_error=reprojection_error,
        )
    reprojection_quality = max(0.0, 1.0 - reprojection_error / configuration.max_reprojection_error_px)
    area_quality = min(1.0, _bbox_area(face_landmarks) / 0.08)
    if previous_angles is None:
        continuity_quality = 0.5
    else:
        delta = max(abs(current - previous) for current, previous in zip((yaw, pitch, roll), previous_angles))
        continuity_quality = max(0.0, 1.0 - delta / 45.0)
    confidence = (
        configuration.target_confidence_weight * max(0.0, min(1.0, float(target_confidence)))
        + configuration.reprojection_weight * reprojection_quality
        + configuration.bbox_size_weight * area_quality
        + configuration.temporal_continuity_weight * continuity_quality
    )
    axes = np.asarray(((100.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 0.0, 100.0)), dtype=np.float64)
    projected_axes, _ = cv2.projectPoints(axes, rotation_vector, translation_vector, camera, distortion)
    axis_points = {
        name: (float(point[0]), float(point[1]))
        for name, point in zip(("x", "y", "z"), projected_axes.reshape(-1, 2))
    }
    return HeadPoseResult(
        available=True,
        yaw_deg=yaw,
        pitch_deg=pitch,
        roll_deg=roll,
        confidence=max(0.0, min(1.0, confidence)),
        estimation_method=ESTIMATION_METHOD,
        failure_reason=None,
        solvepnp_success=True,
        reprojection_error=reprojection_error,
        landmark_count=len(selected),
        camera_matrix_source=CAMERA_MATRIX_SOURCE,
        target_id=target_id,
        nose_pixel=image_points[0],
        axis_points=axis_points,
    )
