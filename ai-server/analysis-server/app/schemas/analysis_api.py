"""Strict external HTTP DTOs for FaceFit analysis services."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"


class ErrorResponse(StrictModel):
    requestId: UUID | None
    code: Literal[
        "INVALID_REQUEST",
        "UNAUTHORIZED",
        "PAYLOAD_TOO_LARGE",
        "UNSUPPORTED_MEDIA_TYPE",
        "MEDIA_ANALYSIS_FAILED",
        "MODEL_ERROR",
        "ANALYSIS_UNAVAILABLE",
        "MODEL_TIMEOUT",
    ]
    message: str
    retryable: bool


class AnalysisSuccessResponse(StrictModel):
    requestId: UUID
    answerId: UUID
    analysisType: Literal["STT", "CV", "VOICE", "CONTENT"]
    schemaVersion: Literal["1.0"] = "1.0"
    modelVersion: str = Field(min_length=1, max_length=100)


class SttSuccessResponse(AnalysisSuccessResponse):
    analysisType: Literal["STT"] = "STT"
    language: Literal["ko"] = "ko"
    transcript: str = Field(min_length=1)
    durationSec: float = Field(gt=0)


class CvSuccessResponse(AnalysisSuccessResponse):
    analysisType: Literal["CV"] = "CV"
    gazeScore: float = Field(ge=0, le=100)
    postureScore: float = Field(ge=0, le=100)
    feedback: list[str]


class VoiceSuccessResponse(AnalysisSuccessResponse):
    analysisType: Literal["VOICE"] = "VOICE"
    speechScore: float = Field(ge=0, le=100)
    feedback: list[str]


class ContentSuccessResponse(AnalysisSuccessResponse):
    analysisType: Literal["CONTENT"] = "CONTENT"
    contentScore: float = Field(ge=0, le=100)
    feedback: list[str]


class ContentAnalysisRequest(StrictModel):
    answerId: UUID
    question: str = Field(min_length=1, max_length=5_000)
    transcript: str = Field(min_length=1, max_length=50_000)
    jobContext: str | None = Field(default=None, max_length=10_000)


class MediaAnalysisRequest(StrictModel):
    schemaVersion: Literal["1"]
    requestId: UUID
    answerId: UUID
    mediaUrl: str = Field(min_length=1, max_length=4096)
    mediaMimeType: Literal["video/mp4", "video/webm"]
    mediaSizeBytes: int = Field(gt=0, le=200 * 1024 * 1024)
    recordedDurationSec: float = Field(gt=0, le=300)
