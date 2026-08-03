"""Environment-backed settings for the internal analysis HTTP contract."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.config import APP_PATHS


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class AnalysisApiSettings:
    """Immutable process settings with no secret-bearing representation."""

    service_token: str = field(repr=False)
    model_timeout_seconds: float = 55.0
    max_upload_bytes: int = 200 * 1024 * 1024
    max_duration_seconds: int = 300
    transcript_max_chars: int = 50_000
    whisper_model_name: str = "base"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "int8_float16"
    temp_directory: Path = APP_PATHS.temp_dir

    @classmethod
    def from_environment(cls) -> "AnalysisApiSettings":
        timeout = _positive_float("FACEFIT_AI_MODEL_TIMEOUT_SECONDS", 55.0)
        if timeout >= 60.0:
            raise ValueError(
                "FACEFIT_AI_MODEL_TIMEOUT_SECONDS must be below the 60 second Worker timeout"
            )
        return cls(
            service_token=os.environ.get("FACEFIT_AI_SERVICE_TOKEN", ""),
            model_timeout_seconds=timeout,
            max_upload_bytes=_positive_int(
                "FACEFIT_AI_MAX_UPLOAD_BYTES",
                200 * 1024 * 1024,
            ),
            max_duration_seconds=_positive_int(
                "FACEFIT_AI_MAX_DURATION_SECONDS",
                300,
            ),
            transcript_max_chars=_positive_int(
                "FACEFIT_AI_TRANSCRIPT_MAX_CHARS",
                50_000,
            ),
            whisper_model_name=os.environ.get("WHISPER_MODEL_SIZE", "base").strip()
            or "base",
            whisper_device=os.environ.get("WHISPER_DEVICE", "cuda").strip() or "cuda",
            whisper_compute_type=os.environ.get(
                "WHISPER_COMPUTE_TYPE",
                "int8_float16",
            ).strip()
            or "int8_float16",
            temp_directory=APP_PATHS.temp_dir,
        )


@lru_cache(maxsize=1)
def get_settings() -> AnalysisApiSettings:
    return AnalysisApiSettings.from_environment()
