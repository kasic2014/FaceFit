"""FaceFit internal analysis HTTP application."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHttpException

from app.api.analyses import router as analyses_router
from app.core.api_errors import AnalysisApiError
from app.core.http_contract import AnalysisContentTypeMiddleware
from app.core.security import parse_request_id
from app.core.settings import AnalysisApiSettings, get_settings
from app.services.executor import AnalysisExecutor
from app.services.cv_analyzer import MediaPipeCvAnalyzer
from app.services.stt_analyzer import WhisperSttAnalyzer
from app.speech.whisper_service import WhisperService


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _create_stage27_app(config, job_service) -> FastAPI:
    """Preserve the session-job API used by Stage 27 and integration runtimes."""
    from app.api.exception_handlers import install_exception_handlers
    from app.api.routers import analysis_jobs, health
    from app.core.analysis_api_config import AnalysisApiConfig
    from app.services.analysis_job_service import AnalysisJobService

    effective_config = config or AnalysisApiConfig.from_env()
    logging.basicConfig(level=getattr(logging, effective_config.log_level))
    service = job_service or AnalysisJobService(effective_config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service.start()
        try:
            yield
        finally:
            service.shutdown()

    application = FastAPI(
        title="Face-Fit Analysis API",
        version="0.1.0",
        description=(
            "Stage 25 Korean STT and Stage 26 measurement-only speech characteristics. "
            "The API accepts session identifiers only, never participant identifiers or file paths. "
            "Transcript exposure is configurable and interview scoring is unavailable."
        ),
        docs_url="/docs" if effective_config.enable_docs else None,
        redoc_url="/redoc" if effective_config.enable_docs else None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.analysis_api_config = effective_config
    application.state.analysis_job_service = service
    if effective_config.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(effective_config.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied
            if REQUEST_ID_PATTERN.fullmatch(supplied)
            else str(uuid.uuid4())
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(analysis_jobs.router)
    return application


def _error_body(
    request_id,
    code: str,
    message: str,
    retryable: bool,
) -> dict[str, object]:
    return {
        "requestId": str(request_id) if request_id is not None else None,
        "code": code,
        "message": message,
        "retryable": retryable,
    }


def create_app(
    config=None,
    job_service=None,
    *,
    settings: AnalysisApiSettings | None = None,
    stt_analyzer=None,
    cv_analyzer=None,
    executor: AnalysisExecutor | None = None,
) -> FastAPI:
    if config is not None or job_service is not None:
        if any(value is not None for value in (settings, stt_analyzer, cv_analyzer, executor)):
            raise TypeError("Stage 27 and internal analysis factory arguments cannot be mixed")
        return _create_stage27_app(config, job_service)

    effective_settings = settings or get_settings()
    effective_executor = executor or AnalysisExecutor(max_workers=1)
    effective_stt_analyzer = stt_analyzer or WhisperSttAnalyzer(
        WhisperService(
            model_name=effective_settings.whisper_model_name,
            device=effective_settings.whisper_device,
            compute_type=effective_settings.whisper_compute_type,
        ),
        transcript_max_chars=effective_settings.transcript_max_chars,
        max_duration_seconds=effective_settings.max_duration_seconds,
    )
    effective_cv_analyzer = cv_analyzer or MediaPipeCvAnalyzer(
        face_model_path=effective_settings.cv_face_model_path,
        pose_model_path=effective_settings.cv_pose_model_path,
        sample_fps=effective_settings.cv_sample_fps,
        max_sample_frames=effective_settings.cv_max_sample_frames,
        min_usable_frames=effective_settings.cv_min_usable_frames,
        max_duration_seconds=effective_settings.max_duration_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        close = getattr(effective_cv_analyzer, "close", None)
        if callable(close):
            close()
        effective_executor.shutdown()

    application = FastAPI(
        title="Face-Fit Analysis Server",
        version="1.0.0",
        description=(
            "Internal service-to-service analysis contract. "
            "CV uses a bounded CPU landmark pipeline. VOICE and CONTENT return "
            "ANALYSIS_UNAVAILABLE until their operational contracts exist."
        ),
        lifespan=lifespan,
    )
    application.state.analysis_settings = effective_settings
    application.state.analysis_executor = effective_executor
    application.state.stt_analyzer = effective_stt_analyzer
    application.state.cv_analyzer = effective_cv_analyzer
    application.dependency_overrides[get_settings] = lambda: effective_settings
    application.add_middleware(AnalysisContentTypeMiddleware)

    @application.exception_handler(AnalysisApiError)
    async def handle_analysis_error(
        _request: Request,
        error: AnalysisApiError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=_error_body(
                error.request_id,
                error.code,
                error.public_message,
                error.retryable,
            ),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        request_id = parse_request_id(request.headers.get("X-Request-Id"))
        return JSONResponse(
            status_code=400,
            content=_error_body(
                request_id,
                "INVALID_REQUEST",
                "The analysis request is invalid.",
                False,
            ),
        )

    @application.exception_handler(StarletteHttpException)
    async def handle_http_error(
        request: Request,
        _error: StarletteHttpException,
    ) -> JSONResponse:
        request_id = parse_request_id(request.headers.get("X-Request-Id"))
        return JSONResponse(
            status_code=400,
            content=_error_body(
                request_id,
                "INVALID_REQUEST",
                "The analysis request is invalid.",
                False,
            ),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        _error: Exception,
    ) -> JSONResponse:
        request_id = parse_request_id(request.headers.get("X-Request-Id"))
        return JSONResponse(
            status_code=500,
            content=_error_body(
                request_id,
                "MODEL_ERROR",
                "The analysis model failed.",
                False,
            ),
        )

    @application.get("/health", tags=["health"])
    def health_check():
        return {"status": "ok", "service": "analysis-server"}

    application.include_router(analyses_router)
    return application


app = create_app()
