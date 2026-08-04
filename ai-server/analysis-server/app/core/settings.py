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
    cv_face_model_path: Path = APP_PATHS.root_dir / "models" / "face_landmarker.task"
    cv_pose_model_path: Path = APP_PATHS.root_dir / "models" / "pose_landmarker_full.task"
    cv_sample_fps: float = 2.0
    cv_max_sample_frames: int = 48
    cv_min_usable_frames: int = 5
    temp_directory: Path = APP_PATHS.temp_dir
    media_allowed_hosts: tuple[str, ...] = ("kr.object.ncloudstorage.com",)
    media_connect_timeout_seconds: float = 5.0
    media_read_timeout_seconds: float = 120.0

    @classmethod
    def from_environment(cls) -> "AnalysisApiSettings":
        timeout = _positive_float("FACEFIT_AI_MODEL_TIMEOUT_SECONDS", 55.0)
        if timeout >= 60.0:
            raise ValueError(
                "FACEFIT_AI_MODEL_TIMEOUT_SECONDS must be below the 60 second Worker timeout"
            )
        cv_sample_fps = _positive_float("FACEFIT_CV_SAMPLE_FPS", 2.0)
        cv_max_sample_frames = _positive_int("FACEFIT_CV_MAX_SAMPLE_FRAMES", 48)
        cv_min_usable_frames = _positive_int("FACEFIT_CV_MIN_USABLE_FRAMES", 5)
        if cv_sample_fps > 10:
            raise ValueError("FACEFIT_CV_SAMPLE_FPS must be at most 10")
        if cv_max_sample_frames > 120:
            raise ValueError("FACEFIT_CV_MAX_SAMPLE_FRAMES must be at most 120")
        if cv_min_usable_frames > cv_max_sample_frames:
            raise ValueError(
                "FACEFIT_CV_MIN_USABLE_FRAMES cannot exceed the sample cap"
            )
        return cls(
            service_token=os.environ.get("FACEFIT_AI_SERVICE_TOKEN", ""),
            model_timeout_seconds=timeout,
            max_upload_bytes=_positive_int(
                "ANALYSIS_MEDIA_MAX_BYTES",
                _positive_int("FACEFIT_AI_MAX_UPLOAD_BYTES", 200 * 1024 * 1024),
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
            cv_face_model_path=Path(
                os.environ.get(
                    "FACEFIT_CV_FACE_MODEL_PATH",
                    str(APP_PATHS.root_dir / "models" / "face_landmarker.task"),
                )
            ),
            cv_pose_model_path=Path(
                os.environ.get(
                    "FACEFIT_CV_POSE_MODEL_PATH",
                    str(APP_PATHS.root_dir / "models" / "pose_landmarker_full.task"),
                )
            ),
            cv_sample_fps=cv_sample_fps,
            cv_max_sample_frames=cv_max_sample_frames,
            cv_min_usable_frames=cv_min_usable_frames,
            temp_directory=APP_PATHS.temp_dir,
            media_allowed_hosts=tuple(
                host.strip().lower()
                for host in os.environ.get(
                    "ANALYSIS_MEDIA_ALLOWED_HOSTS",
                    os.environ.get(
                        "ANALYSIS_MEDIA_ALLOWED_HOST",
                        "kr.object.ncloudstorage.com",
                    ),
                ).split(",")
                if host.strip()
            ),
            media_connect_timeout_seconds=_positive_float(
                "ANALYSIS_MEDIA_CONNECT_TIMEOUT_SECONDS", 5.0
            ),
            media_read_timeout_seconds=_positive_float(
                "ANALYSIS_MEDIA_READ_TIMEOUT_SECONDS", 120.0
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> AnalysisApiSettings:
    return AnalysisApiSettings.from_environment()
