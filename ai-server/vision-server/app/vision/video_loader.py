"""Validated, read-only local video loading helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core import config


SUPPORTED_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
)


class VideoInputError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_video_path(video_path: str | Path) -> Path:
    path = Path(video_path).expanduser().resolve(strict=False)
    if not path.exists():
        raise VideoInputError("VIDEO_NOT_FOUND", f"Video file not found: {path.name}")
    if not path.is_file():
        raise VideoInputError(
            "VIDEO_NOT_REGULAR_FILE",
            f"Video path is not a regular file: {path.name}",
        )
    if path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        raise VideoInputError(
            "VIDEO_EXTENSION_UNSUPPORTED",
            f"Unsupported video extension: {path.suffix.lower() or '(none)'}",
        )
    if path.stat().st_size <= 0:
        raise VideoInputError("VIDEO_FILE_EMPTY", f"Video file is empty: {path.name}")
    return path


def calculate_video_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_video_capture(video_path: str | Path) -> cv2.VideoCapture:
    path = validate_video_path(video_path)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise VideoInputError(
            "VIDEO_CAPTURE_OPEN_FAILED",
            f"OpenCV could not open video: {path.name}",
        )
    return capture


def decode_frame(capture: cv2.VideoCapture) -> tuple[bool, np.ndarray | None]:
    try:
        success, frame = capture.read()
    except cv2.error as exc:
        raise VideoInputError(
            "VIDEO_DECODE_FAILED",
            f"OpenCV frame decode failed: {exc}",
        ) from exc
    if not success or frame is None:
        return False, None
    if frame.ndim != 3 or frame.shape[0] <= 0 or frame.shape[1] <= 0:
        raise VideoInputError(
            "VIDEO_FRAME_INVALID",
            "Decoded video frame has invalid dimensions.",
        )
    return True, frame


def release_video_capture(capture: cv2.VideoCapture | None) -> None:
    if capture is not None:
        capture.release()


def _relative_source_path(path: Path) -> str:
    try:
        return path.relative_to(config.VISION_SERVER_ROOT).as_posix()
    except ValueError:
        return path.name


def _fourcc_text(value: float) -> str:
    integer = int(value)
    return "".join(chr((integer >> (8 * index)) & 0xFF) for index in range(4)).strip(
        "\x00"
    )


def inspect_video_metadata(video_path: str | Path) -> dict[str, Any]:
    path = validate_video_path(video_path)
    capture = open_video_capture(path)
    warnings: list[str] = []
    try:
        width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        declared_frame_count = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        codec = _fourcc_text(capture.get(cv2.CAP_PROP_FOURCC))
        if width <= 0:
            raise VideoInputError("VIDEO_WIDTH_INVALID", "Video width must be positive.")
        if height <= 0:
            raise VideoInputError("VIDEO_HEIGHT_INVALID", "Video height must be positive.")
        if not np.isfinite(fps) or fps <= 0:
            raise VideoInputError("VIDEO_FPS_INVALID", "Video FPS must be positive.")
        success, first_frame = decode_frame(capture)
        if not success or first_frame is None:
            raise VideoInputError(
                "VIDEO_DECODE_FAILED",
                "Video does not contain a decodable frame.",
            )
        actual_height, actual_width = first_frame.shape[:2]
        if (actual_width, actual_height) != (width, height):
            warnings.append(
                "Declared dimensions differ from the first decoded frame; "
                "decoded dimensions are used."
            )
            width, height = actual_width, actual_height
        estimated_duration = (
            declared_frame_count / fps if declared_frame_count > 0 else None
        )
        if declared_frame_count <= 0:
            warnings.append(
                "Declared frame count is unavailable; duration will be completed "
                "from sequential decoding."
            )
        if not codec:
            warnings.append("Video codec FOURCC is unavailable.")
        warnings.append(
            "Rotation metadata is not reliably available through OpenCV; no "
            "automatic rotation was applied."
        )
        return {
            "source_filename": path.name,
            "source_relative_path": _relative_source_path(path),
            "extension": path.suffix.lower(),
            "file_size_bytes": path.stat().st_size,
            "sha256": calculate_video_sha256(path),
            "width": int(width),
            "height": int(height),
            "original_fps": fps,
            "declared_frame_count": max(declared_frame_count, 0),
            "estimated_duration_sec": estimated_duration,
            "codec_fourcc": codec or None,
            "capture_opened": True,
            "first_frame_decoded": True,
            "rotation_status": "not_applied_opencv_metadata_unavailable",
            "warnings": warnings,
        }
    finally:
        release_video_capture(capture)


def create_safe_video_id(filename: str, sha256: str) -> str:
    basename = filename.replace("\\", "/").split("/")[-1]
    stem = Path(basename).stem.replace("..", "")
    ascii_stem = (
        unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    )
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("._-") or "video"
    safe_hash = re.sub(r"[^0-9a-fA-F]", "", sha256)[:8].lower() or "unknown"
    return f"{safe_stem[:80]}_{safe_hash}"
