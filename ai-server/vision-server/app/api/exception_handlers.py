"""Sanitized common error handling for every Vision API route."""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHttpException

from app.services.vision_job_service import VisionApiServiceError


LOGGER = logging.getLogger("face_fit.vision_api")


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if not isinstance(request_id, str):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
    return request_id


def _payload(
    request: Request,
    *,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "requestId": _request_id(request),
        "details": details or [],
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VisionApiServiceError)
    async def handle_service_error(
        request: Request,
        exc: VisionApiServiceError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(
                request,
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = exc.errors()
        unsupported_mode = any(
            error.get("loc", ())[-1:] == ("analysisMode",)
            for error in errors
        )
        details = [
            {
                "field": ".".join(
                    str(part)
                    for part in error.get("loc", ())
                    if part not in {"body", "path", "query"}
                ),
                "type": str(error.get("type", "validation_error")),
            }
            for error in errors
        ]
        return JSONResponse(
            status_code=422,
            content=_payload(
                request,
                code=(
                    "UNSUPPORTED_ANALYSIS_MODE"
                    if unsupported_mode
                    else "VALIDATION_ERROR"
                ),
                message=(
                    "요청한 Vision 분석 모드는 지원되지 않습니다."
                    if unsupported_mode
                    else "요청 형식이 Vision API 계약과 일치하지 않습니다."
                ),
                details=details,
            ),
        )

    @app.exception_handler(StarletteHttpException)
    async def handle_http_error(
        request: Request,
        exc: StarletteHttpException,
    ) -> JSONResponse:
        code = "VALIDATION_ERROR"
        message = "요청을 처리할 수 없습니다."
        if exc.status_code == 404:
            code = "SESSION_NOT_FOUND"
            message = "요청한 API 리소스를 찾을 수 없습니다."
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, code=code, message=message),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        LOGGER.exception(
            "Unhandled Vision API error request_id=%s type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=_payload(
                request,
                code="INTERNAL_SERVER_ERROR",
                message="Vision API 처리 중 내부 오류가 발생했습니다.",
            ),
        )
