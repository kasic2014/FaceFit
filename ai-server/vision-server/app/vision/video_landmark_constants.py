"""Canonical service-scope MediaPipe Pose landmark indices for video."""

from __future__ import annotations

from typing import Any


POSE_NOSE_INDEX = 0
POSE_LEFT_EAR_INDEX = 7
POSE_RIGHT_EAR_INDEX = 8
POSE_LEFT_SHOULDER_INDEX = 11
POSE_RIGHT_SHOULDER_INDEX = 12

REQUIRED_POSE_LANDMARKS = {
    "nose": POSE_NOSE_INDEX,
    "left_shoulder": POSE_LEFT_SHOULDER_INDEX,
    "right_shoulder": POSE_RIGHT_SHOULDER_INDEX,
}
OPTIONAL_POSE_LANDMARKS = {
    "left_ear": POSE_LEFT_EAR_INDEX,
    "right_ear": POSE_RIGHT_EAR_INDEX,
}


def get_required_pose_landmark_indices() -> dict[str, int]:
    return dict(REQUIRED_POSE_LANDMARKS)


def get_optional_pose_landmark_indices() -> dict[str, int]:
    return dict(OPTIONAL_POSE_LANDMARKS)


def _extract(
    landmarks: list[dict[str, Any]],
    mapping: dict[str, int],
) -> dict[str, dict[str, Any] | None]:
    by_index = {
        landmark.get("index"): landmark
        for landmark in landmarks
        if isinstance(landmark, dict)
    }
    return {name: by_index.get(index) for name, index in mapping.items()}


def extract_required_pose_landmarks(
    landmarks: list[dict[str, Any]],
) -> dict[str, dict[str, Any] | None]:
    return _extract(landmarks, REQUIRED_POSE_LANDMARKS)


def extract_optional_pose_landmarks(
    landmarks: list[dict[str, Any]],
) -> dict[str, dict[str, Any] | None]:
    return _extract(landmarks, OPTIONAL_POSE_LANDMARKS)


def validate_required_pose_landmarks(
    extracted: dict[str, dict[str, Any] | None],
) -> bool:
    for name in REQUIRED_POSE_LANDMARKS:
        landmark = extracted.get(name)
        if not isinstance(landmark, dict):
            return False
        if any(landmark.get(axis) is None for axis in ("x", "y", "z")):
            return False
    return True
