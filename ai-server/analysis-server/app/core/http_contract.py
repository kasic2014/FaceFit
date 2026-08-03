"""Content-Type guard for the internal analysis endpoints."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.api_errors import (
    analysis_unavailable,
    invalid_request,
    unauthorized,
    unsupported_media,
)
from app.core.security import parse_request_id


class AnalysisContentTypeMiddleware(BaseHTTPMiddleware):
    _MULTIPART_PATHS = {
        "/internal/v1/analyses/stt",
        "/internal/v1/analyses/cv",
        "/internal/v1/analyses/voice",
    }
    _JSON_PATHS = {"/internal/v1/analyses/content"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "POST" and (
            request.url.path in self._MULTIPART_PATHS
            or request.url.path in self._JSON_PATHS
        ):
            request_id_header = request.headers.get("X-Request-Id")
            request_id = parse_request_id(request_id_header)
            settings = request.app.state.analysis_settings
            authorization = request.headers.get("Authorization", "")
            expected = f"Bearer {settings.service_token}"
            if not settings.service_token:
                return _error_response(analysis_unavailable(request_id))
            if not secrets.compare_digest(authorization, expected):
                return _error_response(unauthorized(request_id))
            if request_id_header is None:
                return _error_response(
                    invalid_request(None, "X-Request-Id is required.")
                )
            if request_id is None:
                return _error_response(
                    invalid_request(None, "X-Request-Id must be a UUID.")
                )
            media_type = (
                request.headers.get("content-type", "")
                .split(";", 1)[0]
                .lower()
            )
            if (
                request.url.path in self._MULTIPART_PATHS
                and media_type != "multipart/form-data"
            ):
                return _error_response(unsupported_media(request_id))
            if request.url.path in self._JSON_PATHS and media_type != "application/json":
                return _error_response(unsupported_media(request_id))
        return await call_next(request)


def _error_response(error: Exception) -> JSONResponse:
    analysis_error = error
    return JSONResponse(
        status_code=analysis_error.status_code,
        content={
            "requestId": (
                str(analysis_error.request_id)
                if analysis_error.request_id is not None
                else None
            ),
            "code": analysis_error.code,
            "message": analysis_error.public_message,
            "retryable": analysis_error.retryable,
        },
    )
