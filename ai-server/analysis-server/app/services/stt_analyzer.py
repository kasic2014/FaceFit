"""Production STT boundary backed by the reusable WhisperService."""

from __future__ import annotations

import math
from pathlib import Path
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerModelError,
    AnalyzerPayloadTooLarge,
    AnalyzerUnavailable,
    SttAnalysisResult,
)
from app.speech.whisper_service import WhisperService


MediaProbe = Callable[[Path], float]


def probe_answer_media(media_path: Path) -> float:
    """Verify the protected answer-media contract and return real duration."""
    try:
        import av
    except (ModuleNotFoundError, ImportError) as exc:
        raise AnalyzerUnavailable from exc

    try:
        with av.open(str(media_path)) as container:
            has_audio = any(stream.type == "audio" for stream in container.streams)
            has_video = any(stream.type == "video" for stream in container.streams)
            if not has_audio or not has_video or container.duration is None:
                raise AnalyzerMediaFailure
            duration_seconds = float(container.duration / av.time_base)
    except AnalyzerMediaFailure:
        raise
    except Exception as exc:
        raise AnalyzerMediaFailure from exc

    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise AnalyzerMediaFailure
    return duration_seconds


class WhisperSttAnalyzer:
    def __init__(
        self,
        whisper_service: WhisperService,
        *,
        transcript_max_chars: int,
        max_duration_seconds: int,
        media_probe: MediaProbe = probe_answer_media,
        runtime_version: str | None = None,
    ) -> None:
        self._whisper_service = whisper_service
        self._transcript_max_chars = transcript_max_chars
        self._max_duration_seconds = max_duration_seconds
        self._media_probe = media_probe
        self._runtime_version = runtime_version

    @property
    def model_version(self) -> str:
        runtime_version = self._runtime_version
        if runtime_version is None:
            try:
                runtime_version = version("faster-whisper")
            except PackageNotFoundError as exc:
                raise AnalyzerUnavailable from exc
        return (
            f"faster-whisper:{runtime_version}:"
            f"{self._whisper_service.model_name}"
        )

    def analyze(self, media_path: Path, language: str) -> SttAnalysisResult:
        duration_seconds = self._media_probe(media_path)
        if not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise AnalyzerMediaFailure
        if duration_seconds > self._max_duration_seconds:
            raise AnalyzerPayloadTooLarge

        initialized_before_call = self._whisper_service.initialized
        try:
            segments, info = self._whisper_service.transcribe(
                media_path,
                language=language,
                task="transcribe",
                word_timestamps=False,
                vad_filter=True,
            )
        except (ModuleNotFoundError, ImportError, FileNotFoundError, OSError) as exc:
            raise AnalyzerUnavailable from exc
        except Exception as exc:
            if not initialized_before_call and not self._whisper_service.initialized:
                raise AnalyzerUnavailable from exc
            raise AnalyzerModelError from exc

        transcript = "".join(
            str(getattr(segment, "text", "") or "") for segment in segments
        ).strip()
        detected_language = str(getattr(info, "language", language) or language)

        if detected_language != language:
            raise AnalyzerMediaFailure
        if not transcript or len(transcript) > self._transcript_max_chars:
            raise AnalyzerMediaFailure

        return SttAnalysisResult(
            model_version=self.model_version,
            language=detected_language,
            transcript=transcript,
            duration_seconds=round(duration_seconds, 3),
        )
