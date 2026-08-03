"""Face-Fit Vision MVP FastAPI application."""

from __future__ import annotations

from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.exception_handlers import register_exception_handlers
from app.api.routers.health import router as health_router
from app.api.routers.vision_jobs import router as vision_jobs_router
from app.api.schemas.common import ErrorResponse
from app.core.vision_api_config import (
    SERVICE_NAME,
    SERVICE_VERSION,
    VisionApiSettings,
)
from app.services.vision_job_service import (
    VisionApiServiceError,
    VisionJobService,
)


OPENAPI_DESCRIPTION = (
    "단일 세션 Baseline 대비 상대 분석용 Vision MVP API. "
    "채용 평가, 합격 가능성, 성격 또는 심리 상태를 판단하지 않는다."
)


def create_app(
    *,
    settings: VisionApiSettings | None = None,
    job_service: VisionJobService | None = None,
) -> FastAPI:
    resolved_settings = settings or VisionApiSettings.from_env()
    docs_url = "/docs" if resolved_settings.enable_docs else None
    application = FastAPI(
        title="Face-Fit Vision MVP API",
        description=OPENAPI_DESCRIPTION,
        version=SERVICE_VERSION,
        docs_url=docs_url,
        redoc_url=None,
    )
    application.state.settings = resolved_settings
    application.state.vision_job_service = job_service or VisionJobService(
        vision_server_root=resolved_settings.vision_server_root,
        output_root=resolved_settings.output_root,
    )

    if resolved_settings.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next: Any) -> Any:
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(vision_jobs_router)

    @application.get("/", tags=["legacy"])
    def read_root() -> dict[str, str | None]:
        return {
            "message": "Face-Fit Vision MVP API is running",
            "docs": docs_url,
        }

    @application.get("/status", tags=["legacy"])
    def server_status(request: Request) -> dict[str, object]:
        request.app.state.vision_job_service.check_readiness()
        return {
            "status": "ready",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
        }

    @application.post(
        "/api/v1/analyze/image",
        response_model=ErrorResponse,
        status_code=400,
        deprecated=True,
        tags=["legacy"],
        summary="Disabled legacy path-based image endpoint",
    )
    def analyze_image_disabled() -> JSONResponse:
        raise VisionApiServiceError(
            "VALIDATION_ERROR",
            400,
            (
                "임의 파일 경로를 받는 분석 API는 비활성화되었습니다. "
                "Vision Job API를 사용하십시오."
            ),
        )

    return application


app = create_app()
