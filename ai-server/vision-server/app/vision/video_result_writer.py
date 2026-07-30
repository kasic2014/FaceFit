"""Strict, atomic JSON and JSONL writers for video analysis."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.vision.model_registry import write_json_atomic


class VideoResultWriteError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AtomicJsonlWriter:
    """Write one strict JSON object per line and expose only a complete file."""

    def __init__(self, destination: Path) -> None:
        self.destination = Path(destination)
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self._temporary_path: Path | None = None
        self._stream = None
        self.line_count = 0
        self._last_timestamp_ms: int | None = None

    def __enter__(self) -> "AtomicJsonlWriter":
        temporary = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=self.destination.parent,
            prefix=f".{self.destination.name}.",
            suffix=".tmp",
            delete=False,
        )
        self._stream = temporary
        self._temporary_path = Path(temporary.name)
        return self

    def write(self, payload: dict[str, Any]) -> None:
        if self._stream is None:
            raise VideoResultWriteError(
                "FRAMES_JSONL_WRITE_FAILED",
                "JSONL writer is not open.",
            )
        timestamp = payload.get("timestamp_ms")
        if not isinstance(timestamp, int):
            raise VideoResultWriteError(
                "FRAME_TIMESTAMP_INVALID",
                "Frame timestamp_ms must be an integer.",
            )
        if self._last_timestamp_ms is not None and timestamp <= self._last_timestamp_ms:
            raise VideoResultWriteError(
                "FRAME_TIMESTAMP_NOT_INCREASING",
                "Frame timestamps must be strictly increasing.",
            )
        try:
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            self._stream.write(serialized)
            self._stream.write("\n")
        except (OSError, TypeError, ValueError) as exc:
            raise VideoResultWriteError(
                "FRAMES_JSONL_WRITE_FAILED",
                f"Could not write frame JSONL: {exc}",
            ) from exc
        self._last_timestamp_ms = timestamp
        self.line_count += 1

    def commit(self) -> None:
        if self._stream is None or self._temporary_path is None:
            raise VideoResultWriteError(
                "FRAMES_JSONL_WRITE_FAILED",
                "JSONL writer is not open.",
            )
        try:
            self._stream.flush()
            os.fsync(self._stream.fileno())
            self._stream.close()
            self._stream = None
            os.replace(self._temporary_path, self.destination)
            self._temporary_path = None
        except OSError as exc:
            raise VideoResultWriteError(
                "FRAMES_JSONL_WRITE_FAILED",
                f"Could not commit frame JSONL: {exc}",
            ) from exc

    def abort(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if self._temporary_path is not None:
            self._temporary_path.unlink(missing_ok=True)
            self._temporary_path = None

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.abort()


def write_video_analysis_json(payload: dict[str, Any], destination: Path) -> None:
    try:
        write_json_atomic(payload, destination)
    except (OSError, TypeError, ValueError) as exc:
        raise VideoResultWriteError(
            "ANALYSIS_JSON_WRITE_FAILED",
            f"Could not write video analysis JSON: {exc}",
        ) from exc
