"""Internal analysis results and stable service failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SttAnalysisResult:
    model_version: str
    language: str
    transcript: str
    duration_seconds: float


class AnalyzerFailure(Exception):
    """Base class deliberately carrying no provider error text."""


class AnalyzerUnavailable(AnalyzerFailure):
    pass


class AnalyzerModelError(AnalyzerFailure):
    pass


class AnalyzerMediaFailure(AnalyzerFailure):
    pass


class AnalyzerPayloadTooLarge(AnalyzerFailure):
    pass


class AnalyzerTimeout(AnalyzerFailure):
    pass
