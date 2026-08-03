"""Safe, uniform Analysis API exception responses."""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.analysis_job_service import AnalysisApiServiceError
from app.services.analysis_job_storage import JobStorageError


LOGGER = logging.getLogger(__name__)


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", uuid.uuid4()))


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "requestId": request_id(request),
            "details": details or [],
        },
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        pipeline_error = any(tuple(item.get("loc", ())) == ("body", "pipeline") for item in errors)
        details = [
            {
                "location": ".".join(str(part) for part in item.get("loc", ())),
                "message": str(item.get("msg", "Invalid value")),
                "type": str(item.get("type", "validation_error")),
            }
            for item in errors
        ]
        return error_response(
            request,
            status_code=422,
            code="UNSUPPORTED_PIPELINE" if pipeline_error else "VALIDATION_ERROR",
            message="Pipeline is not supported" if pipeline_error else "Request validation failed",
            details=details,
        )

    @app.exception_handler(AnalysisApiServiceError)
    async def service_handler(request: Request, exc: AnalysisApiServiceError) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=str(exc),
        )

    @app.exception_handler(JobStorageError)
    async def storage_handler(request: Request, exc: JobStorageError) -> JSONResponse:
        status = 404 if exc.code == "JOB_NOT_FOUND" else 500
        return error_response(
            request,
            status_code=status,
            code=exc.code,
            message="Analysis job was not found" if status == 404 else "Analysis job storage failed",
        )

    @app.exception_handler(Exception)
    async def internal_handler(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled Analysis API error", exc_info=exc)
        return error_response(
            request,
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="Internal server error",
        )
