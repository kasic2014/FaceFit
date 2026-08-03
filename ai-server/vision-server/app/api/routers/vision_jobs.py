"""HTTP-only routes for Vision Jobs and Stage 22 feedback."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request, status

from app.api.schemas.common import ErrorResponse
from app.api.schemas.feedback import FeedbackResponse
from app.api.schemas.vision_job import (
    VisionJobCreateRequest,
    VisionJobResponse,
)
from app.services.vision_job_service import VisionJobService


router = APIRouter(prefix="/api/v1/vision", tags=["vision-mvp"])
ERROR_RESPONSES = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _service(request: Request) -> VisionJobService:
    return request.app.state.vision_job_service


@router.post(
    "/jobs",
    response_model=VisionJobResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Create or reuse a Vision MVP feedback Job",
)
def create_job(
    payload: VisionJobCreateRequest,
    request: Request,
) -> dict[str, object]:
    return _service(request).create_job(
        session_id=payload.sessionId,
        analysis_mode=payload.analysisMode.value,
        force_rebuild=payload.forceRebuild,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=VisionJobResponse,
    responses=ERROR_RESPONSES,
    summary="Read a persisted Vision Job by UUID",
)
def get_job(
    job_id: Annotated[
        str,
        Path(description="Non-identifying canonical UUID Job ID"),
    ],
    request: Request,
) -> dict[str, object]:
    return _service(request).get_job(job_id)


@router.get(
    "/sessions/{session_id}/feedback",
    response_model=FeedbackResponse,
    responses=ERROR_RESPONSES,
    summary="Read strict Stage 22 single-Session feedback",
)
def get_feedback(
    session_id: Annotated[
        str,
        Path(
            pattern=r"^SES_\d{6}$",
            description="Session ID in SES_ plus six digits format",
        ),
    ],
    request: Request,
) -> dict[str, object]:
    return _service(request).load_feedback(session_id)
