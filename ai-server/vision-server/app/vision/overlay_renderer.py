"""OpenCV development overlays with no scoring or semantic judgment."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np


FACE_COLOR = (255, 180, 0)
POSE_COLOR = (80, 220, 120)
BOX_COLOR = (220, 120, 220)
TEXT_COLOR = (240, 240, 240)
POSE_VISIBILITY_THRESHOLD = 0.25

POSE_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),
    (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),
    (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),
)


class OverlayRenderError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "OVERLAY_RENDER_FAILED"


def normalized_to_clamped_pixel(
    x: float,
    y: float,
    width: int,
    height: int,
) -> tuple[int, int]:
    return (
        min(max(int(round(x * width)), 0), max(width - 1, 0)),
        min(max(int(round(y * height)), 0), max(height - 1, 0)),
    )


def _draw_bbox(image: np.ndarray, item: dict[str, Any], label: str) -> None:
    bbox = item.get("pixel_bounding_box")
    if not bbox:
        return
    clamped = bbox["clamped"]
    start = (clamped["min_x"], clamped["min_y"])
    end = (clamped["max_x"], clamped["max_y"])
    cv2.rectangle(image, start, end, BOX_COLOR, 1, cv2.LINE_AA)
    cv2.putText(
        image,
        label,
        (start[0], max(12, start[1] - 4)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        TEXT_COLOR,
        1,
        cv2.LINE_AA,
    )


def _draw_face(image: np.ndarray, face_result: dict[str, Any]) -> None:
    height, width = image.shape[:2]
    for face in face_result.get("faces", []):
        for landmark in face.get("landmarks", []):
            if landmark.get("x") is None or landmark.get("y") is None:
                continue
            point = normalized_to_clamped_pixel(
                landmark["x"],
                landmark["y"],
                width,
                height,
            )
            cv2.circle(image, point, 1, FACE_COLOR, -1, cv2.LINE_AA)
        _draw_bbox(image, face, f"FACE {face['face_index']}")


def _visible_pose_landmark(landmark: dict[str, Any]) -> bool:
    visibility = landmark.get("visibility")
    return visibility is None or visibility >= POSE_VISIBILITY_THRESHOLD


def _draw_pose(
    image: np.ndarray,
    pose_result: dict[str, Any],
    warnings: list[str],
) -> None:
    height, width = image.shape[:2]
    for pose in pose_result.get("poses", []):
        landmarks = pose.get("landmarks", [])
        points: dict[int, tuple[int, int]] = {}
        for landmark in landmarks:
            if (
                landmark.get("x") is None
                or landmark.get("y") is None
                or not _visible_pose_landmark(landmark)
            ):
                continue
            points[landmark["index"]] = normalized_to_clamped_pixel(
                landmark["x"],
                landmark["y"],
                width,
                height,
            )
        for start_index, end_index in POSE_CONNECTIONS:
            if start_index >= len(landmarks) or end_index >= len(landmarks):
                warnings.append(
                    f"Pose connection index out of range: {start_index}-{end_index}."
                )
                continue
            if start_index in points and end_index in points:
                cv2.line(
                    image,
                    points[start_index],
                    points[end_index],
                    POSE_COLOR,
                    1,
                    cv2.LINE_AA,
                )
        for point in points.values():
            cv2.circle(image, point, 3, POSE_COLOR, -1, cv2.LINE_AA)
        _draw_bbox(image, pose, f"POSE {pose['pose_index']}")


def _technical_message(image: np.ndarray, text: str, line: int) -> None:
    cv2.putText(
        image,
        text,
        (10, 24 + line * 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        TEXT_COLOR,
        1,
        cv2.LINE_AA,
    )


def render_face_overlay(
    bgr_image: np.ndarray,
    face_result: dict[str, Any],
) -> tuple[np.ndarray, list[str]]:
    output = bgr_image.copy()
    warnings: list[str] = []
    _draw_face(output, face_result)
    if face_result.get("face_count", 0) == 0:
        _technical_message(output, "NO FACE DETECTED", 0)
    return output, warnings


def render_pose_overlay(
    bgr_image: np.ndarray,
    pose_result: dict[str, Any],
) -> tuple[np.ndarray, list[str]]:
    output = bgr_image.copy()
    warnings: list[str] = []
    _draw_pose(output, pose_result, warnings)
    if pose_result.get("pose_count", 0) == 0:
        _technical_message(output, "NO POSE DETECTED", 0)
    return output, warnings


def render_combined_overlay(
    bgr_image: np.ndarray,
    face_result: dict[str, Any],
    pose_result: dict[str, Any],
) -> tuple[np.ndarray, list[str]]:
    output = bgr_image.copy()
    warnings: list[str] = []
    _draw_face(output, face_result)
    _draw_pose(output, pose_result, warnings)
    line = 0
    if face_result.get("face_count", 0) == 0:
        _technical_message(output, "NO FACE DETECTED", line)
        line += 1
    if pose_result.get("pose_count", 0) == 0:
        _technical_message(output, "NO POSE DETECTED", line)
    return output, warnings


def save_png_atomic(image: np.ndarray, destination: Path) -> None:
    try:
        success, encoded = cv2.imencode(".png", image)
        if not success:
            raise OverlayRenderError("OpenCV could not encode the overlay as PNG.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(encoded.tobytes())
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    except OverlayRenderError:
        raise
    except (OSError, cv2.error) as exc:
        raise OverlayRenderError(f"Could not save overlay {destination.name}: {exc}") from exc
