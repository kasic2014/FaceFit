"""Create a deterministic static-image MP4 for video-pipeline smoke testing."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import cv2


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.core import config  # noqa: E402
from app.vision.image_loader import (  # noqa: E402
    ImageInputError,
    calculate_sha256,
    load_bgr_image,
)
from app.vision.model_registry import write_json_atomic  # noqa: E402
from app.vision.video_loader import (  # noqa: E402
    calculate_video_sha256,
    inspect_video_metadata,
)


DEFAULT_OUTPUT = (
    config.INPUT_VIDEOS_DIR
    / "generated"
    / "SPK001_FRONT_SHOULDERS_STATIC_SMOKE_01.mp4"
)
DEFAULT_DURATION_SEC = 3.0
DEFAULT_FPS = 10.0
DEFAULT_MAX_HEIGHT = 960


class SmokeVideoError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _relative(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(
            VISION_SERVER_ROOT
        ).as_posix()
    except ValueError:
        return path.name


def create_smoke_video(
    input_path: str | Path,
    *,
    output_path: str | Path = DEFAULT_OUTPUT,
    duration_sec: float = DEFAULT_DURATION_SEC,
    fps: float = DEFAULT_FPS,
    max_height: int = DEFAULT_MAX_HEIGHT,
    overwrite: bool = False,
) -> dict:
    if duration_sec <= 0 or fps <= 0 or max_height <= 0:
        raise SmokeVideoError(
            "SMOKE_VIDEO_CONFIGURATION_INVALID",
            "Duration, FPS, and maximum height must be positive.",
        )
    try:
        source_path, image = load_bgr_image(input_path)
    except ImageInputError as exc:
        raise SmokeVideoError(exc.code, str(exc)) from exc
    source_hash_before = calculate_sha256(source_path)
    destination = Path(output_path).expanduser().resolve(strict=False)
    manifest_path = destination.with_suffix(".manifest.json")
    if (destination.exists() or manifest_path.exists()) and not overwrite:
        raise SmokeVideoError(
            "SMOKE_VIDEO_OUTPUT_EXISTS",
            f"Smoke video output already exists: {destination.name}",
        )
    source_height, source_width = image.shape[:2]
    scale = min(1.0, max_height / source_height)
    width = max(2, int(round(source_width * scale)))
    height = max(2, int(round(source_height * scale)))
    width -= width % 2
    height -= height % 2
    frame = (
        cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        if (width, height) != (source_width, source_height)
        else image.copy()
    )
    frame_count = int(round(duration_sec * fps))
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=".mp4",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    writer = cv2.VideoWriter(
        str(temporary_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        writer.release()
        temporary_path.unlink(missing_ok=True)
        raise SmokeVideoError(
            "SMOKE_VIDEO_WRITER_UNAVAILABLE",
            "OpenCV mp4v VideoWriter is unavailable.",
        )
    try:
        for _ in range(frame_count):
            writer.write(frame)
    finally:
        writer.release()
    if not temporary_path.is_file() or temporary_path.stat().st_size <= 0:
        temporary_path.unlink(missing_ok=True)
        raise SmokeVideoError(
            "SMOKE_VIDEO_WRITE_FAILED",
            "Smoke video was not created.",
        )
    if destination.exists():
        destination.unlink()
    os.replace(temporary_path, destination)
    metadata = inspect_video_metadata(destination)
    if metadata["declared_frame_count"] != frame_count:
        raise SmokeVideoError(
            "SMOKE_VIDEO_VALIDATION_FAILED",
            "Generated smoke video frame count is incorrect.",
        )
    if calculate_sha256(source_path) != source_hash_before:
        raise SmokeVideoError(
            "SOURCE_IMAGE_CHANGED",
            "Source image changed while creating smoke video.",
        )
    manifest = {
        "schema_version": "1.0",
        "source_image_path": _relative(source_path),
        "source_image_sha256": source_hash_before,
        "generated_video_path": _relative(destination),
        "generated_video_sha256": calculate_video_sha256(destination),
        "width": metadata["width"],
        "height": metadata["height"],
        "fps": metadata["original_fps"],
        "frame_count": metadata["declared_frame_count"],
        "duration_sec": metadata["estimated_duration_sec"],
        "codec": metadata["codec_fourcc"],
        "synthetic_static_video": True,
        "purpose": "video_pipeline_smoke_test",
        "not_valid_for_temporal_motion_validation": True,
    }
    write_json_atomic(manifest, manifest_path)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a 3-second static-image video pipeline smoke input."
    )
    parser.add_argument("--input", required=True, help="Local source image path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        result = create_smoke_video(
            arguments.input,
            output_path=arguments.output,
            overwrite=arguments.overwrite,
        )
    except SmokeVideoError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
