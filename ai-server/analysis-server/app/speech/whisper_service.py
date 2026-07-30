"""Reusable, thread-safe faster-whisper model service."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.cuda_runtime import register_cuda_runtime


DEFAULT_MODEL_NAME = "turbo"
DEFAULT_DEVICE = "cuda"
DEFAULT_COMPUTE_TYPE = "int8_float16"
DEFAULT_LANGUAGE = "ko"
DEFAULT_BEAM_SIZE = 5

ModelFactory = Callable[..., Any]


def default_model_factory(model_name: str, *, device: str, compute_type: str) -> Any:
    """Register NVIDIA DLL paths before importing the CUDA-backed packages."""
    register_cuda_runtime()
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device=device, compute_type=compute_type)


class WhisperService:
    """Own one lazily initialized WhisperModel for one immutable configuration."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
        *,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model_factory = model_factory or default_model_factory
        self._model: Any | None = None
        self._load_time_sec: float | None = None
        self._initialization_count = 0
        self._initialization_lock = threading.Lock()

    @property
    def initialized(self) -> bool:
        return self._model is not None

    @property
    def load_time_sec(self) -> float | None:
        return self._load_time_sec

    @property
    def initialization_count(self) -> int:
        return self._initialization_count

    def status(self) -> dict[str, Any]:
        return {
            "initialized": self.initialized,
            "model_name": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "load_time_sec": self.load_time_sec,
            "initialization_count": self.initialization_count,
        }

    def initialize(self) -> Any:
        """Initialize once, with double-checked locking for concurrent callers."""
        if self._model is not None:
            return self._model
        with self._initialization_lock:
            if self._model is not None:
                return self._model
            started = time.perf_counter()
            try:
                model = self._model_factory(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            except Exception:
                self._load_time_sec = round(time.perf_counter() - started, 6)
                raise
            self._model = model
            self._load_time_sec = round(time.perf_counter() - started, 6)
            self._initialization_count += 1
            return model

    def transcribe(
        self,
        audio_file: str | Path,
        *,
        language: str = DEFAULT_LANGUAGE,
        task: str = "transcribe",
        beam_size: int = DEFAULT_BEAM_SIZE,
        word_timestamps: bool = True,
        vad_filter: bool = False,
    ) -> tuple[list[Any], Any]:
        """Transcribe one file and fully consume the returned segment generator."""
        model = self.initialize()
        segment_generator, info = model.transcribe(
            str(audio_file),
            language=language,
            task=task,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
        )
        return list(segment_generator), info
