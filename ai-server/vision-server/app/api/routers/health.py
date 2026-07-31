"""Process liveness and dependency readiness routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas.common import ErrorResponse, HealthResponse, ReadyResponse
from app.core.vision_api_config import SERVICE_NAME, SERVICE_VERSION
from app.services.vision_job_service import VisionJobService
from app.vision.single_session_mvp_feedback import ANALYSIS_MODE


router = APIRouter(tags=["service"])


def _service(request: Request) -> VisionJobService:
    return request.app.state.vision_job_service


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Process liveness",
)
def health() -> dict[str, str]:
    return {
        "status": "UP",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Vision MVP dependency readiness",
)
def ready(request: Request) -> dict[str, object]:
    _service(request).check_readiness()
    return {
        "status": "READY",
        "service": SERVICE_NAME,
        "analysisMode": ANALYSIS_MODE,
        "scoringAvailable": False,
    }
