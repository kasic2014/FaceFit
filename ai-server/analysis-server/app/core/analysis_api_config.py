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


def _integer(value: str, name: str, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AnalysisApiConfigError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise AnalysisApiConfigError(
            f"{name} must be between {minimum} and {maximum}"
        )
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
    job_max_workers: int = 1
    job_queue_capacity: int = 16
    job_lock_wait_seconds: int = 300
    stale_lock_seconds: int = 900
    shutdown_wait_seconds: int = 30
    job_retention_enabled: bool = False
    job_retention_days: int = 30
    job_max_records: int = 1000

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
            job_max_workers=_integer(
                env.get(f"{PREFIX}JOB_MAX_WORKERS", "1"),
                "ANALYSIS_API_JOB_MAX_WORKERS", minimum=1, maximum=16,
            ),
            job_queue_capacity=_integer(
                env.get(f"{PREFIX}JOB_QUEUE_CAPACITY", "16"),
                "ANALYSIS_API_JOB_QUEUE_CAPACITY", minimum=1, maximum=10_000,
            ),
            job_lock_wait_seconds=_integer(
                env.get(f"{PREFIX}JOB_LOCK_WAIT_SECONDS", "300"),
                "ANALYSIS_API_JOB_LOCK_WAIT_SECONDS", minimum=0, maximum=3_600,
            ),
            stale_lock_seconds=_integer(
                env.get(f"{PREFIX}STALE_LOCK_SECONDS", "900"),
                "ANALYSIS_API_STALE_LOCK_SECONDS", minimum=1, maximum=86_400,
            ),
            shutdown_wait_seconds=_integer(
                env.get(f"{PREFIX}SHUTDOWN_WAIT_SECONDS", "30"),
                "ANALYSIS_API_SHUTDOWN_WAIT_SECONDS", minimum=0, maximum=300,
            ),
            job_retention_enabled=_boolean(
                env.get(f"{PREFIX}JOB_RETENTION_ENABLED", "false"),
                "ANALYSIS_API_JOB_RETENTION_ENABLED",
            ),
            job_retention_days=_integer(
                env.get(f"{PREFIX}JOB_RETENTION_DAYS", "30"),
                "ANALYSIS_API_JOB_RETENTION_DAYS", minimum=1, maximum=3_650,
            ),
            job_max_records=_integer(
                env.get(f"{PREFIX}JOB_MAX_RECORDS", "1000"),
                "ANALYSIS_API_JOB_MAX_RECORDS", minimum=1, maximum=1_000_000,
            ),
        )
