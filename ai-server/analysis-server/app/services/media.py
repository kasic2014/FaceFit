"""Secure, bounded download of private answer media to an isolated temp file."""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.core.settings import AnalysisApiSettings
from app.schemas.analysis_api import MediaAnalysisRequest
from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerPayloadTooLarge,
    AnalyzerTimeout,
)

_MIME_SUFFIX = {"video/mp4": ".mp4", "video/webm": ".webm"}
_CHUNK_SIZE = 1024 * 1024
_MAX_URL_LENGTH = 4096


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
            try:
                self.path.parent.rmdir()
            except OSError:
                pass


def _valid_signature(mime_type: str, prefix: bytes) -> bool:
    if mime_type == "video/mp4":
        return len(prefix) >= 12 and prefix[4:8] == b"ftyp"
    if mime_type == "video/webm":
        return prefix.startswith(b"\x1a\x45\xdf\xa3")
    return False


def _validate_url(media_url: str, settings: AnalysisApiSettings) -> str:
    if len(media_url) > _MAX_URL_LENGTH:
        raise AnalyzerMediaFailure
    parsed = urlsplit(media_url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or host not in settings.media_allowed_hosts
        or parsed.fragment
    ):
        raise AnalyzerMediaFailure
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AnalyzerTimeout from exc
    if not addresses:
        raise AnalyzerMediaFailure
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise AnalyzerMediaFailure
    return host


async def download_media(
    request: MediaAnalysisRequest,
    settings: AnalysisApiSettings,
) -> ManagedMedia:
    _validate_url(request.mediaUrl, settings)
    mime_type = request.mediaMimeType.lower()
    if mime_type not in _MIME_SUFFIX:
        raise AnalyzerMediaFailure
    if request.mediaSizeBytes > settings.max_upload_bytes:
        raise AnalyzerPayloadTooLarge

    settings.temp_directory.mkdir(parents=True, exist_ok=True)
    request_directory = settings.temp_directory / f"request-{uuid4()}"
    request_directory.mkdir(mode=0o700)
    path = request_directory / f"media{_MIME_SUFFIX[mime_type]}"
    total = 0
    prefix = bytearray()
    timeout = httpx.Timeout(
        connect=settings.media_connect_timeout_seconds,
        read=settings.media_read_timeout_seconds,
        write=settings.media_connect_timeout_seconds,
        pool=settings.media_connect_timeout_seconds,
    )

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream("GET", request.mediaUrl) as response:
                if 300 <= response.status_code < 400:
                    raise AnalyzerMediaFailure
                if response.status_code >= 500:
                    raise AnalyzerTimeout
                if response.status_code in (401, 403, 404):
                    raise AnalyzerMediaFailure
                if response.status_code < 200 or response.status_code >= 300:
                    raise AnalyzerMediaFailure

                content_type = response.headers.get("content-type", "")
                actual_mime = content_type.split(";", 1)[0].strip().lower()
                if actual_mime != mime_type:
                    raise AnalyzerMediaFailure
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared = int(content_length)
                    except ValueError as exc:
                        raise AnalyzerMediaFailure from exc
                    if declared > settings.max_upload_bytes:
                        raise AnalyzerPayloadTooLarge
                    if declared != request.mediaSizeBytes:
                        raise AnalyzerMediaFailure

                with path.open("xb") as destination:
                    async for chunk in response.aiter_bytes(_CHUNK_SIZE):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > settings.max_upload_bytes:
                            raise AnalyzerPayloadTooLarge
                        if len(prefix) < 32:
                            prefix.extend(chunk[: 32 - len(prefix)])
                        destination.write(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
        if total == 0 or total != request.mediaSizeBytes:
            raise AnalyzerMediaFailure
        if not _valid_signature(mime_type, bytes(prefix)):
            raise AnalyzerMediaFailure
        return ManagedMedia(path=path, size_bytes=total, mime_type=mime_type)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        _cleanup_partial(path, request_directory)
        raise AnalyzerTimeout from exc
    except Exception:
        _cleanup_partial(path, request_directory)
        raise


def _cleanup_partial(path: Path, directory: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        directory.rmdir()
    except OSError:
        pass
