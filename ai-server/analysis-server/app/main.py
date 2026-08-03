"""Face-Fit Analysis FastAPI application."""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import install_exception_handlers
from app.api.routers import analysis_jobs, health
from app.core.analysis_api_config import AnalysisApiConfig
from app.services.analysis_job_service import AnalysisJobService


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def create_app(
    config: AnalysisApiConfig | None = None,
    job_service: AnalysisJobService | None = None,
) -> FastAPI:
    settings = config or AnalysisApiConfig.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level))
    docs_url = "/docs" if settings.enable_docs else None
    redoc_url = "/redoc" if settings.enable_docs else None
    app = FastAPI(
        title="Face-Fit Analysis API",
        version="0.1.0",
        description=(
            "Stage 25 Korean STT and Stage 26 measurement-only speech characteristics. "
            "The API accepts session identifiers only, never participant identifiers or file paths. "
            "Transcript exposure is configurable and interview scoring is unavailable."
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url="/openapi.json",
    )
    app.state.analysis_api_config = settings
    app.state.analysis_job_service = job_service or AnalysisJobService(settings)

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(analysis_jobs.router)
    return app


app = create_app()
