"""Filesystem configuration for the vision server.

Model paths are configuration values only.  Importing this module never checks
that model files exist and never downloads them.
"""

from __future__ import annotations

import os
from pathlib import Path


VISION_SERVER_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = VISION_SERVER_ROOT / "models"
INPUT_IMAGES_DIR = VISION_SERVER_ROOT / "data" / "input" / "images"
INPUT_VIDEOS_DIR = VISION_SERVER_ROOT / "data" / "input" / "videos"
OUTPUT_DIR = VISION_SERVER_ROOT / "data" / "output"


def resolve_model_path(environment_name: str, default_name: str) -> Path:
    """Resolve an absolute or vision-server-relative model configuration."""

    configured = os.environ.get(environment_name, default_name)
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = VISION_SERVER_ROOT / path
    return path.resolve(strict=False)


FACE_LANDMARKER_MODEL_PATH = resolve_model_path(
    "FACE_LANDMARKER_MODEL_PATH",
    "models/face_landmarker.task",
)
POSE_LANDMARKER_MODEL_PATH = resolve_model_path(
    "POSE_LANDMARKER_MODEL_PATH",
    "models/pose_landmarker_full.task",
)
