"""Convert MediaPipe landmarks to strict-JSON-compatible Python values."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


def sanitize_number(
    value: Any,
    warnings: list[str],
    field_name: str,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    try:
        number = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{field_name} is not numeric and was stored as null.")
        return None
    if not math.isfinite(number):
        warnings.append(f"{field_name} is not finite and was stored as null.")
        return None
    return number


def _serialize_landmarks(
    landmarks: Iterable[Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for index, landmark in enumerate(landmarks):
        prefix = f"landmark[{index}]"
        serialized.append(
            {
                "index": index,
                "x": sanitize_number(getattr(landmark, "x", None), warnings, f"{prefix}.x"),
                "y": sanitize_number(getattr(landmark, "y", None), warnings, f"{prefix}.y"),
                "z": sanitize_number(getattr(landmark, "z", None), warnings, f"{prefix}.z"),
                "visibility": sanitize_number(
                    getattr(landmark, "visibility", None),
                    warnings,
                    f"{prefix}.visibility",
                ),
                "presence": sanitize_number(
                    getattr(landmark, "presence", None),
                    warnings,
                    f"{prefix}.presence",
                ),
            }
        )
    return serialized


def serialize_normalized_landmarks(
    landmarks: Iterable[Any],
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    target_warnings = [] if warnings is None else warnings
    return _serialize_landmarks(landmarks, target_warnings)


def serialize_world_landmarks(
    landmarks: Iterable[Any],
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    target_warnings = [] if warnings is None else warnings
    return _serialize_landmarks(landmarks, target_warnings)


def calculate_normalized_bbox(
    landmarks: list[dict[str, Any]],
) -> dict[str, float] | None:
    coordinates = [
        (landmark["x"], landmark["y"])
        for landmark in landmarks
        if landmark.get("x") is not None and landmark.get("y") is not None
    ]
    if not coordinates:
        return None
    xs, ys = zip(*coordinates)
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
    }


def calculate_pixel_bbox(
    normalized_bbox: dict[str, float] | None,
    width: int,
    height: int,
) -> dict[str, Any] | None:
    if normalized_bbox is None:
        return None
    raw = {
        "min_x": int(math.floor(normalized_bbox["min_x"] * width)),
        "min_y": int(math.floor(normalized_bbox["min_y"] * height)),
        "max_x": int(math.ceil(normalized_bbox["max_x"] * width)),
        "max_y": int(math.ceil(normalized_bbox["max_y"] * height)),
    }
    clamped = {
        "min_x": min(max(raw["min_x"], 0), max(width - 1, 0)),
        "min_y": min(max(raw["min_y"], 0), max(height - 1, 0)),
        "max_x": min(max(raw["max_x"], 0), max(width - 1, 0)),
        "max_y": min(max(raw["max_y"], 0), max(height - 1, 0)),
    }
    return {**raw, "clamped": clamped}


def serialize_face_result(result: Any, width: int, height: int) -> dict[str, Any]:
    warnings: list[str] = []
    face_landmarks = list(getattr(result, "face_landmarks", None) or [])
    faces: list[dict[str, Any]] = []
    for face_index, raw_landmarks in enumerate(face_landmarks):
        landmarks = serialize_normalized_landmarks(raw_landmarks, warnings)
        normalized_bbox = calculate_normalized_bbox(landmarks)
        faces.append(
            {
                "face_index": face_index,
                "landmark_count": len(landmarks),
                "landmarks": landmarks,
                "normalized_bounding_box": normalized_bbox,
                "pixel_bounding_box": calculate_pixel_bbox(
                    normalized_bbox,
                    width,
                    height,
                ),
            }
        )
    return {
        "detection_status": "detected" if faces else "no_face_detected",
        "face_count": len(faces),
        "faces": faces,
        "warnings": warnings,
        "error": None,
    }


def serialize_pose_result(result: Any, width: int, height: int) -> dict[str, Any]:
    warnings: list[str] = []
    pose_landmarks = list(getattr(result, "pose_landmarks", None) or [])
    world_landmarks = list(getattr(result, "pose_world_landmarks", None) or [])
    poses: list[dict[str, Any]] = []
    for pose_index, raw_landmarks in enumerate(pose_landmarks):
        landmarks = serialize_normalized_landmarks(raw_landmarks, warnings)
        raw_world = world_landmarks[pose_index] if pose_index < len(world_landmarks) else []
        serialized_world = serialize_world_landmarks(raw_world, warnings)
        normalized_bbox = calculate_normalized_bbox(landmarks)
        poses.append(
            {
                "pose_index": pose_index,
                "landmark_count": len(landmarks),
                "landmarks": landmarks,
                "world_landmark_count": len(serialized_world),
                "world_landmarks": serialized_world,
                "normalized_bounding_box": normalized_bbox,
                "pixel_bounding_box": calculate_pixel_bbox(
                    normalized_bbox,
                    width,
                    height,
                ),
            }
        )
    return {
        "detection_status": "detected" if poses else "no_pose_detected",
        "pose_count": len(poses),
        "poses": poses,
        "warnings": warnings,
        "error": None,
    }
