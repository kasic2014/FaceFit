"""Liveness and readiness endpoints."""

from fastapi import APIRouter, Request, Response

from app.api.schemas.common import HealthResponse, ReadyResponse


router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse, summary="Process liveness")
def health() -> dict[str, str]:
    """Return liveness without initializing an STT or pitch model."""
    return {"status": "UP", "service": "face-fit-analysis-api", "version": "0.1.0"}


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Analysis dependency readiness without model loading",
    responses={503: {"description": "A required dependency or writable store is unavailable"}},
)
def ready(request: Request, response: Response) -> dict:
    payload, status_code = request.app.state.analysis_job_service.readiness()
    response.status_code = status_code
    return payload
