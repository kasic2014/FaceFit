"""Internal HTTP routes for answer analysis."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.api_errors import (
    AnalysisApiError,
    analysis_unavailable,
    invalid_request,
    media_analysis_failed,
    model_error,
    model_timeout,
    payload_too_large,
)
from app.core.security import authorize_analysis_request
from app.schemas.analysis_api import (
    ContentAnalysisRequest,
    CvSuccessResponse,
    ErrorResponse,
    MediaAnalysisRequest,
    SttSuccessResponse,
)
from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerModelError,
    AnalyzerPayloadTooLarge,
    AnalyzerTimeout,
    AnalyzerUnavailable,
)
from app.services.media import download_media


ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid request"},
    401: {"model": ErrorResponse, "description": "Service authentication failed"},
    413: {"model": ErrorResponse, "description": "Media limit exceeded"},
    415: {"model": ErrorResponse, "description": "Unsupported Content-Type or media"},
    422: {"model": ErrorResponse, "description": "Media could not be analyzed"},
    500: {"model": ErrorResponse, "description": "Model execution failed"},
    503: {"model": ErrorResponse, "description": "Analysis is unavailable"},
    504: {"model": ErrorResponse, "description": "Model execution timed out"},
}

UNAVAILABLE_RESPONSES = {
    status: detail
    for status, detail in ERROR_RESPONSES.items()
    if status != 503
}

router = APIRouter(prefix="/internal/v1/analyses", tags=["internal-analyses"])


def _map_failure(error: Exception, request_id: UUID) -> AnalysisApiError:
    if isinstance(error, AnalyzerPayloadTooLarge):
        return payload_too_large(request_id)
    if isinstance(error, AnalyzerMediaFailure):
        return media_analysis_failed(request_id)
    if isinstance(error, AnalyzerUnavailable):
        return analysis_unavailable(request_id)
    if isinstance(error, AnalyzerTimeout):
        return model_timeout(request_id)
    if isinstance(error, AnalyzerModelError):
        return model_error(request_id)
    return model_error(request_id)


@router.post(
    "/stt",
    response_model=SttSuccessResponse,
    responses=ERROR_RESPONSES,
    summary="Transcribe one answer media file",
)
async def analyze_stt(
    request: Request,
    body: MediaAnalysisRequest,
    request_id: UUID = Depends(authorize_analysis_request),
) -> SttSuccessResponse:
    if body.requestId != request_id:
        raise invalid_request(request_id)
    try:
        managed = await download_media(body, request.app.state.analysis_settings)
    except Exception as error:
        raise _map_failure(error, request_id) from None

    try:
        result = await request.app.state.analysis_executor.run(
            lambda: request.app.state.stt_analyzer.analyze(managed.path, "ko"),
            timeout_seconds=request.app.state.analysis_settings.model_timeout_seconds,
            cleanup=managed.cleanup,
        )
    except Exception as error:
        raise _map_failure(error, request_id) from None

    return SttSuccessResponse(
        requestId=request_id,
        answerId=body.answerId,
        modelVersion=result.model_version,
        language=result.language,
        transcript=result.transcript,
        durationSec=result.duration_seconds,
    )


async def _validate_unavailable_media(request: Request, body: MediaAnalysisRequest,
                                      request_id: UUID) -> None:
    if body.requestId != request_id:
        raise invalid_request(request_id)
    try:
        managed = await download_media(body, request.app.state.analysis_settings)
    except Exception as error:
        raise _map_failure(error, request_id) from None
    managed.cleanup()
    raise analysis_unavailable(request_id)


@router.post(
    "/cv",
    response_model=CvSuccessResponse,
    responses=ERROR_RESPONSES,
    summary="Analyze one answer video with the CPU CV pipeline",
)
async def analyze_cv(
    request: Request,
    body: MediaAnalysisRequest,
    request_id: UUID = Depends(authorize_analysis_request),
) -> CvSuccessResponse:
    if body.requestId != request_id:
        raise invalid_request(request_id)
    try:
        managed = await download_media(body, request.app.state.analysis_settings)
    except Exception as error:
        raise _map_failure(error, request_id) from None

    try:
        result = await request.app.state.analysis_executor.run(
            lambda: request.app.state.cv_analyzer.analyze(managed.path),
            timeout_seconds=request.app.state.analysis_settings.model_timeout_seconds,
            cleanup=managed.cleanup,
        )
    except Exception as error:
        raise _map_failure(error, request_id) from None

    return CvSuccessResponse(
        requestId=request_id,
        answerId=body.answerId,
        modelVersion=result.model_version,
        gazeScore=result.gaze_score,
        postureScore=result.posture_score,
        feedback=list(result.feedback),
    )


@router.post(
    "/voice",
    status_code=503,
    response_model=ErrorResponse,
    responses=UNAVAILABLE_RESPONSES,
    summary="Voice contract endpoint (operational scoring unavailable)",
)
async def analyze_voice(
    request: Request,
    body: MediaAnalysisRequest,
    request_id: UUID = Depends(authorize_analysis_request),
) -> ErrorResponse:
    await _validate_unavailable_media(request, body, request_id)
    raise analysis_unavailable(request_id)


@router.post(
    "/content",
    status_code=503,
    response_model=ErrorResponse,
    responses=UNAVAILABLE_RESPONSES,
    summary="Content contract endpoint (model and rubric unavailable)",
)
async def analyze_content(
    request: Request,
    body: ContentAnalysisRequest,
    request_id: UUID = Depends(authorize_analysis_request),
) -> ErrorResponse:
    settings = request.app.state.analysis_settings
    if not body.question.strip() or not body.transcript.strip():
        raise invalid_request(request_id)
    if len(body.transcript) > settings.transcript_max_chars:
        raise invalid_request(request_id)
    raise analysis_unavailable(request_id)
