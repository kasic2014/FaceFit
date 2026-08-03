"""Shared public response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ApiWarning(ApiModel):
    code: str
    message: str
    answer_id: str | None = Field(default=None, alias="answerId")


class ApiError(ApiModel):
    code: str
    message: str
    request_id: str = Field(alias="requestId")
    details: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(ApiModel):
    status: str
    service: str
    version: str


class ReadyResponse(ApiModel):
    status: str
    service: str
    available_pipelines: list[str] = Field(alias="availablePipelines")
    pipelines: list[str]
    scoring_available: bool = Field(alias="scoringAvailable")
    job_execution: dict[str, Any] = Field(alias="jobExecution")
    recovery: dict[str, Any]
    configuration_warnings: list[dict[str, Any]] = Field(alias="configurationWarnings")
    checks: dict[str, bool]
