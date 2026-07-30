"""Validated, read-only static image loading helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

from app.core import config


SUPPORTED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})
LARGE_IMAGE_BYTES = 25 * 1024 * 1024
LARGE_IMAGE_PIXELS = 25_000_000


class ImageInputError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_image_path(image_path: str | Path) -> Path:
    path = Path(image_path).expanduser().resolve(strict=False)
    if not path.exists():
        raise ImageInputError("IMAGE_NOT_FOUND", f"Image file not found: {path.name}")
    if not path.is_file():
        raise ImageInputError(
            "IMAGE_NOT_REGULAR_FILE",
            f"Image path is not a regular file: {path.name}",
        )
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ImageInputError(
            "IMAGE_EXTENSION_UNSUPPORTED",
            f"Unsupported image extension: {path.suffix.lower() or '(none)'}",
        )
    if path.stat().st_size == 0:
        raise ImageInputError("IMAGE_FILE_EMPTY", f"Image file is empty: {path.name}")
    return path


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_bgr_image(image_path: str | Path) -> tuple[Path, np.ndarray]:
    """Decode without modifying the source file, including Unicode paths."""

    path = validate_image_path(image_path)
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    except (OSError, ValueError, cv2.error) as exc:
        raise ImageInputError(
            "IMAGE_DECODE_FAILED",
            f"OpenCV could not decode image {path.name}: {exc}",
        ) from exc
    if image is None:
        raise ImageInputError(
            "IMAGE_DECODE_FAILED",
            f"OpenCV could not decode image: {path.name}",
        )
    if image.ndim not in (2, 3) or image.shape[0] <= 0 or image.shape[1] <= 0:
        raise ImageInputError(
            "IMAGE_DIMENSION_INVALID",
            f"Decoded image has invalid dimensions: {path.name}",
        )
    if image.ndim == 3 and image.shape[2] not in (1, 3, 4):
        raise ImageInputError(
            "IMAGE_DIMENSION_INVALID",
            f"Decoded image has an unsupported channel count: {image.shape[2]}",
        )
    return path, image


def convert_bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        converted = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 1:
        converted = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 3:
        converted = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    elif image.shape[2] == 4:
        converted = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
    else:
        raise ImageInputError(
            "IMAGE_DIMENSION_INVALID",
            "Cannot convert image with unsupported channels to RGB.",
        )
    return np.ascontiguousarray(converted)


def create_mediapipe_image(rgb_image: np.ndarray) -> mp.Image:
    try:
        return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
    except Exception as exc:
        raise ImageInputError(
            "IMAGE_DECODE_FAILED",
            f"Could not create MediaPipe image: {exc}",
        ) from exc


def _relative_source_path(path: Path) -> str:
    try:
        return path.relative_to(config.VISION_SERVER_ROOT).as_posix()
    except ValueError:
        return path.name


def inspect_image_metadata(path: Path, image: np.ndarray) -> dict[str, Any]:
    height, width = image.shape[:2]
    channels = 1 if image.ndim == 2 else int(image.shape[2])
    size = path.stat().st_size
    warnings: list[str] = []
    if size > LARGE_IMAGE_BYTES or width * height > LARGE_IMAGE_PIXELS:
        warnings.append(
            "Image is unusually large and may require significant memory or time."
        )
    return {
        "source_filename": path.name,
        "source_relative_path": _relative_source_path(path),
        "source_extension": path.suffix.lower(),
        "file_size_bytes": size,
        "sha256": calculate_sha256(path),
        "width": int(width),
        "height": int(height),
        "channels": channels,
        "dtype": str(image.dtype),
        "decoded": True,
        "warnings": warnings,
    }


def create_safe_image_id(filename: str, sha256: str) -> str:
    """Create a traversal-free, collision-resistant output identifier."""

    basename = filename.replace("\\", "/").split("/")[-1]
    stem = Path(basename).stem.replace("..", "")
    ascii_stem = (
        unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    )
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("._-") or "image"
    safe_hash = re.sub(r"[^0-9a-fA-F]", "", sha256)[:8].lower() or "unknown"
    return f"{safe_stem[:80]}_{safe_hash}"
