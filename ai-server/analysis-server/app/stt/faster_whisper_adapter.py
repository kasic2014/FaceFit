"""Injectable Faster-Whisper adapter with cache and runtime provenance."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
import time
from typing import Any

from app.speech.whisper_service import WhisperService

from .transcription_profile import TranscriptionProfile


class AdapterError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelCacheInfo:
    cached: bool
    model_id: str
    revision: str
    size_bytes: int | None

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": "CACHED" if self.cached else "NOT_CACHED",
            "modelId": self.model_id,
            "revision": self.revision,
            "sizeBytes": self.size_bytes,
        }


@dataclass(frozen=True)
class TranscriptionRun:
    segments: list[Any]
    info: Any
    elapsed_seconds: float


def inspect_model_cache(profile: TranscriptionProfile) -> ModelCacheInfo:
    try:
        from huggingface_hub import scan_cache_dir

        cache = scan_cache_dir()
        for repository in cache.repos:
            if repository.repo_id != profile.model_id:
                continue
            for revision in repository.revisions:
                if revision.commit_hash == profile.revision:
                    return ModelCacheInfo(
                        cached=True,
                        model_id=profile.model_id,
                        revision=revision.commit_hash,
                        size_bytes=int(revision.size_on_disk),
                    )
    except Exception:
        pass
    return ModelCacheInfo(
        cached=False,
        model_id=profile.model_id,
        revision=profile.revision,
        size_bytes=None,
    )


def classify_adapter_error(error: BaseException, *, loading: bool) -> str:
    message = f"{type(error).__name__}: {error}".lower()
    if loading and any(
        token in message
        for token in (
            "localentrynotfounderror",
            "cannot find the requested files",
            "download",
            "connection",
            "huggingface",
            "timed out",
        )
    ):
        return "STT_MODEL_DOWNLOAD_BLOCKED"
    if any(token in message for token in ("cuda", "cublas", "cudnn", "out of memory")):
        return "STT_RUNTIME_UNAVAILABLE"
    return "STT_MODEL_LOAD_FAILED" if loading else "STT_TRANSCRIPTION_FAILED"


def _distribution_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError as exc:
        raise AdapterError(
            "STT_DEPENDENCY_BLOCKED", f"Missing dependency: {distribution}"
        ) from exc


class FasterWhisperAdapter:
    def __init__(
        self,
        profile: TranscriptionProfile,
        *,
        local_files_only: bool = False,
        service_factory: Any | None = None,
    ) -> None:
        self.profile = profile
        self.cache_info = inspect_model_cache(profile)
        self.local_files_only = local_files_only or self.cache_info.cached
        factory = service_factory or WhisperService
        self.service = factory(
            model_name=profile.model,
            device=profile.device,
            compute_type=profile.compute_type,
            local_files_only=self.local_files_only,
            revision=profile.revision,
        )
        self.local_files_only_validated = False

    def initialize(self) -> None:
        try:
            self.service.initialize()
        except Exception as exc:
            raise AdapterError(
                classify_adapter_error(exc, loading=True),
                f"{type(exc).__name__}: {exc}",
            ) from exc
        self.cache_info = inspect_model_cache(self.profile)
        self.local_files_only_validated = self.local_files_only and self.cache_info.cached

    def transcribe(self, audio_path: str | Path) -> TranscriptionRun:
        started = time.perf_counter()
        try:
            segments, info = self.service.transcribe(
                audio_path,
                language="ko",
                task="transcribe",
                beam_size=5,
                word_timestamps=True,
                vad_filter=False,
                condition_on_previous_text=False,
                temperature=0.0,
            )
        except Exception as exc:
            raise AdapterError(
                classify_adapter_error(exc, loading=False),
                f"{type(exc).__name__}: {exc}",
            ) from exc
        return TranscriptionRun(
            segments=segments,
            info=info,
            elapsed_seconds=time.perf_counter() - started,
        )

    def engine_metadata(self) -> dict[str, Any]:
        return {
            **self.profile.public_dict(),
            "name": "faster-whisper",
            "version": _distribution_version("faster-whisper"),
            "ctranslate2Version": _distribution_version("ctranslate2"),
            "cache": self.cache_info.public_dict(),
            "localFilesOnly": self.local_files_only,
            "localFilesOnlyValidated": self.local_files_only_validated,
            "modelLoadTimeSeconds": self.service.load_time_sec,
            "pythonVersion": sys.version.split()[0],
        }
