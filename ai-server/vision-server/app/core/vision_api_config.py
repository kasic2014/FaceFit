"""Non-secret configuration for the Face-Fit Vision MVP API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from app.core.config import VISION_SERVER_ROOT


SERVICE_NAME = "face-fit-vision-api"
SERVICE_VERSION = "0.1.0"


class VisionApiConfigError(ValueError):
    """Raised when a Vision API environment setting is invalid."""


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise VisionApiConfigError(f"{name} must be a boolean")


def _parse_port() -> int:
    raw = os.environ.get("VISION_API_PORT", "8000")
    try:
        port = int(raw)
    except ValueError as exc:
        raise VisionApiConfigError("VISION_API_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise VisionApiConfigError("VISION_API_PORT is outside the valid range")
    return port


def _parse_origins() -> tuple[str, ...]:
    raw = os.environ.get("VISION_API_ALLOWED_ORIGINS", "")
    origins = tuple(
        item.strip().rstrip("/")
        for item in raw.split(",")
        if item.strip()
    )
    if "*" in origins:
        raise VisionApiConfigError(
            "VISION_API_ALLOWED_ORIGINS cannot allow every origin"
        )
    return origins


@dataclass(frozen=True)
class VisionApiSettings:
    environment: str
    host: str
    port: int
    allowed_origins: tuple[str, ...]
    enable_docs: bool
    output_root: Path
    log_level: str
    vision_server_root: Path

    @property
    def job_root(self) -> Path:
        return self.output_root / "vision_api" / "jobs"

    @property
    def feedback_root(self) -> Path:
        return self.output_root / "single_session_mvp_feedback"

    @classmethod
    def from_env(
        cls,
        *,
        vision_server_root: str | Path = VISION_SERVER_ROOT,
    ) -> "VisionApiSettings":
        root = Path(vision_server_root).resolve(strict=False)
        environment = os.environ.get("VISION_API_ENV", "development").strip()
        if not environment:
            raise VisionApiConfigError("VISION_API_ENV cannot be empty")
        default_docs = environment.lower() not in {"production", "prod"}
        configured_output = os.environ.get("VISION_API_OUTPUT_ROOT")
        output_root = (
            Path(configured_output).expanduser()
            if configured_output
            else root / "data" / "output"
        )
        if not output_root.is_absolute():
            output_root = root / output_root
        log_level = os.environ.get("VISION_API_LOG_LEVEL", "INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise VisionApiConfigError("VISION_API_LOG_LEVEL is invalid")
        return cls(
            environment=environment,
            host=os.environ.get("VISION_API_HOST", "127.0.0.1"),
            port=_parse_port(),
            allowed_origins=_parse_origins(),
            enable_docs=_parse_bool("VISION_API_ENABLE_DOCS", default_docs),
            output_root=output_root.resolve(strict=False),
            log_level=log_level,
            vision_server_root=root,
        )
