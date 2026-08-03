"""Bounded, signature-checked temporary upload storage."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.settings import AnalysisApiSettings
from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerPayloadTooLarge,
)


_MIME_SUFFIX = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
_CHUNK_SIZE = 1024 * 1024


@dataclass
class ManagedMedia:
    path: Path
    size_bytes: int
    mime_type: str
    _cleaned: bool = False

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        try:
            self.path.unlink(missing_ok=True)
        finally:
            parent = self.path.parent
            try:
                parent.rmdir()
            except OSError:
                pass


def _safe_original_name(name: str | None) -> bool:
    if not name:
        return True
    return (
        ".." not in name
        and "/" not in name
        and "\\" not in name
        and "\x00" not in name
    )


def _valid_signature(mime_type: str, prefix: bytes) -> bool:
    if mime_type == "video/mp4":
        return len(prefix) >= 12 and prefix[4:8] == b"ftyp"
    if mime_type == "video/webm":
        return prefix.startswith(b"\x1a\x45\xdf\xa3")
    return False


async def persist_upload(
    upload: UploadFile,
    settings: AnalysisApiSettings,
) -> ManagedMedia:
    mime_type = (upload.content_type or "").lower()
    if mime_type not in _MIME_SUFFIX or not _safe_original_name(upload.filename):
        raise AnalyzerMediaFailure

    settings.temp_directory.mkdir(parents=True, exist_ok=True)
    request_directory = settings.temp_directory / f"request-{uuid4()}"
    request_directory.mkdir(mode=0o700)
    path = request_directory / f"media{_MIME_SUFFIX[mime_type]}"
    total = 0
    prefix = bytearray()

    try:
        with path.open("xb") as destination:
            while True:
                chunk = await upload.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise AnalyzerPayloadTooLarge
                if len(prefix) < 32:
                    prefix.extend(chunk[: 32 - len(prefix)])
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if total == 0 or not _valid_signature(mime_type, bytes(prefix)):
            raise AnalyzerMediaFailure
        return ManagedMedia(path=path, size_bytes=total, mime_type=mime_type)
    except Exception:
        try:
            path.unlink(missing_ok=True)
            request_directory.rmdir()
        except OSError:
            pass
        raise
    finally:
        await upload.close()
