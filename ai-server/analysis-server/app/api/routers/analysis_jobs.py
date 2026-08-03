"""Analysis job and result routes."""

from typing import Annotated

from fastapi import APIRouter, Path, Request, status

from app.api.schemas.analysis_job import AnalysisJobRequest, AnalysisJobResponse
from app.api.schemas.common import ApiError
from app.api.schemas.speech_characteristics import SpeechCharacteristicsResponse
from app.api.schemas.transcription import TranscriptionResponse


ERRORS = {
    404: {"model": ApiError, "description": "Session or job not found"},
    409: {"model": ApiError, "description": "Result not ready"},
    422: {"model": ApiError, "description": "Invalid session or unsupported pipeline"},
    500: {"model": ApiError, "description": "Analysis or storage failure"},
    503: {"model": ApiError, "description": "Runtime dependency unavailable"},
}

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post(
    "/jobs",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
    summary="Run or reuse a synchronous analysis job",
)
def create_job(body: AnalysisJobRequest, request: Request) -> dict:
    return request.app.state.analysis_job_service.create_job(
        body.session_id, body.pipeline.value, body.force_rebuild
    )


@router.get(
    "/jobs/{job_id}",
    response_model=AnalysisJobResponse,
    responses=ERRORS,
    summary="Read a restart-safe analysis job record",
)
def get_job(job_id: str, request: Request) -> dict:
    return request.app.state.analysis_job_service.get_job(job_id)


@router.get(
    "/sessions/{session_id}/transcription",
    response_model=TranscriptionResponse,
    responses=ERRORS,
    summary="Read sanitized Stage 25 transcription",
    description=(
        "Returns Korean STT timestamps and text. Text is replaced with null when "
        "ANALYSIS_API_EXPOSE_TRANSCRIPT_TEXT is false. Participant and filesystem metadata are never exposed."
    ),
)
def transcription(
    session_id: Annotated[str, Path(pattern=r"^SES_\d{6}$")], request: Request
) -> dict:
    return request.app.state.analysis_job_service.transcription_result(session_id)


@router.get(
    "/sessions/{session_id}/speech-characteristics",
    response_model=SpeechCharacteristicsResponse,
    responses=ERRORS,
    summary="Read sanitized Stage 26 speech measurements",
    description=(
        "Returns speaking-rate, pause, silence, filler-candidate, volume, and physical pitch measurements. "
        "No score, grade, confidence, emotion, personality, or pass inference is produced."
    ),
)
def speech_characteristics(
    session_id: Annotated[str, Path(pattern=r"^SES_\d{6}$")], request: Request
) -> dict:
    return request.app.state.analysis_job_service.speech_result(session_id)
