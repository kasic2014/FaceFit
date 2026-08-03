"""Strict environment configuration for the Analysis HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from app.core.config import APP_PATHS


PREFIX = "ANALYSIS_API_"
ALLOWED_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class AnalysisApiConfigError(ValueError):
    """Raised when an Analysis API environment value is invalid."""


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise AnalysisApiConfigError(f"{name} must be true or false")


def _port(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AnalysisApiConfigError("ANALYSIS_API_PORT must be an integer") from exc
    if not 1 <= parsed <= 65535:
        raise AnalysisApiConfigError("ANALYSIS_API_PORT must be between 1 and 65535")
    return parsed


def _origins(value: str) -> tuple[str, ...]:
    origins = tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())
    if "*" in origins:
        raise AnalysisApiConfigError("Wildcard CORS origins are forbidden")
    if any(not origin.startswith(("http://", "https://")) for origin in origins):
        raise AnalysisApiConfigError("CORS origins must use http or https")
    return tuple(dict.fromkeys(origins))


@dataclass(frozen=True)
class AnalysisApiConfig:
    environment: str
    host: str
    port: int
    allowed_origins: tuple[str, ...]
    enable_docs: bool
    output_root: Path
    log_level: str
    expose_transcript_text: bool

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "AnalysisApiConfig":
        env = os.environ if values is None else values
        environment = env.get(f"{PREFIX}ENV", "development").strip().lower()
        if not environment:
            raise AnalysisApiConfigError("ANALYSIS_API_ENV must not be empty")
        production = environment == "production"
        host = env.get(f"{PREFIX}HOST", "127.0.0.1").strip()
        if not host:
            raise AnalysisApiConfigError("ANALYSIS_API_HOST must not be empty")
        enable_docs = _boolean(
            env.get(f"{PREFIX}ENABLE_DOCS", "false" if production else "true"),
            "ANALYSIS_API_ENABLE_DOCS",
        )
        expose_text = _boolean(
            env.get(f"{PREFIX}EXPOSE_TRANSCRIPT_TEXT", "false" if production else "true"),
            "ANALYSIS_API_EXPOSE_TRANSCRIPT_TEXT",
        )
        raw_root_value = env.get(f"{PREFIX}OUTPUT_ROOT", "data/output").strip()
        if not raw_root_value:
            raise AnalysisApiConfigError("ANALYSIS_API_OUTPUT_ROOT must not be empty")
        raw_root = Path(raw_root_value)
        output_root = raw_root if raw_root.is_absolute() else APP_PATHS.root_dir / raw_root
        log_level = env.get(f"{PREFIX}LOG_LEVEL", "INFO").strip().upper()
        if log_level not in ALLOWED_LOG_LEVELS:
            raise AnalysisApiConfigError("ANALYSIS_API_LOG_LEVEL is invalid")
        return cls(
            environment=environment,
            host=host,
            port=_port(env.get(f"{PREFIX}PORT", "8002")),
            allowed_origins=_origins(env.get(f"{PREFIX}ALLOWED_ORIGINS", "")),
            enable_docs=enable_docs,
            output_root=output_root.resolve(),
            log_level=log_level,
            expose_transcript_text=expose_text,
        )
