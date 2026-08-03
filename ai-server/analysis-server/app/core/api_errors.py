"""Stable public errors for the internal analysis API."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AnalysisApiError(Exception):
    status_code: int
    code: str
    public_message: str
    retryable: bool
    request_id: UUID | None = None

    def with_request_id(self, request_id: UUID) -> "AnalysisApiError":
        return AnalysisApiError(
            status_code=self.status_code,
            code=self.code,
            public_message=self.public_message,
            retryable=self.retryable,
            request_id=request_id,
        )


def invalid_request(
    request_id: UUID | None = None,
    message: str = "The analysis request is invalid.",
) -> AnalysisApiError:
    return AnalysisApiError(400, "INVALID_REQUEST", message, False, request_id)


def unauthorized(request_id: UUID | None = None) -> AnalysisApiError:
    return AnalysisApiError(
        401,
        "UNAUTHORIZED",
        "Service authentication failed.",
        False,
        request_id,
    )


def payload_too_large(request_id: UUID | None = None) -> AnalysisApiError:
    return AnalysisApiError(
        413,
        "PAYLOAD_TOO_LARGE",
        "The analysis media exceeds the allowed limit.",
        False,
        request_id,
    )


def unsupported_media(request_id: UUID | None = None) -> AnalysisApiError:
    return AnalysisApiError(
        415,
        "UNSUPPORTED_MEDIA_TYPE",
        "The analysis media type is not supported.",
        False,
        request_id,
    )


def media_analysis_failed(request_id: UUID | None = None) -> AnalysisApiError:
    return AnalysisApiError(
        422,
        "MEDIA_ANALYSIS_FAILED",
        "The supplied media could not be analyzed.",
        False,
        request_id,
    )


def model_error(request_id: UUID | None = None) -> AnalysisApiError:
    return AnalysisApiError(
        500,
        "MODEL_ERROR",
        "The analysis model failed.",
        False,
        request_id,
    )


def analysis_unavailable(request_id: UUID | None = None) -> AnalysisApiError:
    return AnalysisApiError(
        503,
        "ANALYSIS_UNAVAILABLE",
        "The requested analysis is not available.",
        False,
        request_id,
    )


def model_timeout(request_id: UUID | None = None) -> AnalysisApiError:
    return AnalysisApiError(
        504,
        "MODEL_TIMEOUT",
        "The analysis model timed out.",
        True,
        request_id,
    )
