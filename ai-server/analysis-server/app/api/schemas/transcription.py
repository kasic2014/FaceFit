"""Sanitized Stage 25 transcription response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import ApiModel, ApiWarning


class TranscriptionAnswer(ApiModel):
    answer_id: str = Field(alias="answerId")
    status: str
    language: dict[str, Any]
    text_exposed: bool = Field(alias="textExposed")
    text: str | None
    segment_count: int = Field(alias="segmentCount")
    word_count: int = Field(alias="wordCount")
    segments: list[dict[str, Any]]
    words: list[dict[str, Any]]
    warnings: list[ApiWarning]


class TranscriptionResponse(ApiModel):
    session_id: str = Field(alias="sessionId")
    status: str
    engine: dict[str, Any]
    options: dict[str, Any]
    answers: list[TranscriptionAnswer]
    warnings: list[ApiWarning]
    errors: list[dict[str, Any]]
