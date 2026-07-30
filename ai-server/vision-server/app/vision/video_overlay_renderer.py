"""Development-only video overlay rendering for Face-Fit landmark detection."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.vision.overlay_renderer import normalized_to_clamped_pixel
from app.vision.video_landmark_constants import (
    POSE_LEFT_EAR_INDEX,
    POSE_LEFT_SHOULDER_INDEX,
    POSE_NOSE_INDEX,
    POSE_RIGHT_EAR_INDEX,
    POSE_RIGHT_SHOULDER_INDEX,
)


FACE_COLOR = (255, 180, 0)
POSE_COLOR = (80, 220, 120)
BOX_COLOR = (220, 120, 220)
TEXT_COLOR = (245, 245, 245)
DISPLAY_POSE_INDICES = frozenset(
    {
        POSE_NOSE_INDEX,
        POSE_LEFT_EAR_INDEX,
        POSE_RIGHT_EAR_INDEX,
        POSE_LEFT_SHOULDER_INDEX,
        POSE_RIGHT_SHOULDER_INDEX,
    }
)


class VideoOverlayError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "VIDEO_OVERLAY_FAILED"


def render_video_overlay_frame(
    bgr_frame: np.ndarray,
    frame_result: dict[str, Any],
) -> np.ndarray:
    output = bgr_frame.copy()
    height, width = output.shape[:2]
    face_bbox = frame_result.get("face_bounding_box")
    if face_bbox:
        box = face_bbox["clamped"]
        cv2.rectangle(
            output,
            (box["min_x"], box["min_y"]),
            (box["max_x"], box["max_y"]),
            BOX_COLOR,
            2,
            cv2.LINE_AA,
        )
    for landmark in frame_result.get("face_landmarks", [])[::16]:
        if landmark.get("x") is not None and landmark.get("y") is not None:
            cv2.circle(
                output,
                normalized_to_clamped_pixel(
                    landmark["x"], landmark["y"], width, height
                ),
                1,
                FACE_COLOR,
                -1,
                cv2.LINE_AA,
            )

    points: dict[int, tuple[int, int]] = {}
    for landmark in frame_result.get("pose_landmarks", []):
        index = landmark.get("index")
        if (
            index not in DISPLAY_POSE_INDICES
            or landmark.get("x") is None
            or landmark.get("y") is None
        ):
            continue
        points[index] = normalized_to_clamped_pixel(
            landmark["x"], landmark["y"], width, height
        )
    if (
        POSE_LEFT_SHOULDER_INDEX in points
        and POSE_RIGHT_SHOULDER_INDEX in points
    ):
        cv2.line(
            output,
            points[POSE_LEFT_SHOULDER_INDEX],
            points[POSE_RIGHT_SHOULDER_INDEX],
            POSE_COLOR,
            2,
            cv2.LINE_AA,
        )
    for point in points.values():
        cv2.circle(output, point, 5, POSE_COLOR, -1, cv2.LINE_AA)

    lines = (
        f"{frame_result.get('timestamp_ms', 0)} ms | "
        f"frame {frame_result.get('source_frame_index', 0)}",
        f"face: {frame_result.get('face_detection_status', 'unknown')}",
        "shoulders: "
        + (
            "available"
            if frame_result.get("required_pose_landmarks_available")
            else "unavailable"
        ),
    )
    for index, text in enumerate(lines):
        cv2.putText(
            output,
            text,
            (12, 26 + index * 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )
    return output


class VideoOverlayWriter:
    """Write mp4v overlay video through a same-directory temporary MP4."""

    def __init__(
        self,
        destination: Path,
        fps: float,
        width: int,
        height: int,
    ) -> None:
        self.destination = Path(destination)
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self.codec = "mp4v"
        self.frame_count = 0
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.destination.stem}.",
            suffix=".mp4",
            dir=self.destination.parent,
        )
        os.close(descriptor)
        self._temporary_path = Path(temporary_name)
        self._writer = cv2.VideoWriter(
            str(self._temporary_path),
            cv2.VideoWriter_fourcc(*self.codec),
            float(fps),
            (int(width), int(height)),
        )
        self.available = bool(self._writer.isOpened())
        if not self.available:
            self._writer.release()
            self._temporary_path.unlink(missing_ok=True)

    def write(self, frame: np.ndarray) -> None:
        if not self.available:
            raise VideoOverlayError("OpenCV VideoWriter is unavailable.")
        try:
            self._writer.write(frame)
        except cv2.error as exc:
            raise VideoOverlayError(f"Could not write overlay frame: {exc}") from exc
        self.frame_count += 1

    def close(self, commit: bool = True) -> None:
        self._writer.release()
        if not self.available:
            return
        if commit and self.frame_count > 0 and self._temporary_path.is_file():
            os.replace(self._temporary_path, self.destination)
        else:
            self._temporary_path.unlink(missing_ok=True)
        self.available = False


def save_sampled_frame_png(frame: np.ndarray, destination: Path) -> None:
    success, encoded = cv2.imencode(".png", frame)
    if not success:
        raise VideoOverlayError("OpenCV could not encode sampled frame PNG.")
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
