"""Sanitized Stage 26 speech-characteristics response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import ApiModel, ApiWarning


class SpeechAnswer(ApiModel):
    answer_id: str = Field(alias="answerId")
    status: str
    speaking_rate: dict[str, Any] = Field(alias="speakingRate")
    timestamp_pauses: dict[str, Any] = Field(alias="timestampPauses")
    acoustic_silence: dict[str, Any] = Field(alias="acousticSilence")
    filler_candidates: list[dict[str, Any]] = Field(alias="fillerCandidates")
    volume: dict[str, Any]
    pitch: dict[str, Any]
    warnings: list[ApiWarning]


class SpeechCharacteristicsResponse(ApiModel):
    session_id: str = Field(alias="sessionId")
    status: str
    analysis_mode: str = Field(alias="analysisMode")
    scoring_available: bool = Field(alias="scoringAvailable")
    threshold_approval: bool = Field(alias="thresholdApproval")
    answers: list[SpeechAnswer]
    aggregate: dict[str, Any]
    warnings: list[ApiWarning]
    limitations: list[str]
