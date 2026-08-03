"""Authentication and request-correlation dependencies."""

from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import Depends, Header, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.api_errors import analysis_unavailable, invalid_request, unauthorized
from app.core.settings import AnalysisApiSettings, get_settings


bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AIServiceBearer",
    description="Internal service token supplied through FACEFIT_AI_SERVICE_TOKEN.",
)


def parse_request_id(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


def authorize_analysis_request(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    request_id_header: str | None = Header(default=None, alias="X-Request-Id"),
    settings: AnalysisApiSettings = Depends(get_settings),
) -> UUID:
    candidate_request_id = parse_request_id(request_id_header)
    if not settings.service_token:
        raise analysis_unavailable(candidate_request_id)
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, settings.service_token)
    ):
        raise unauthorized(candidate_request_id)
    if request_id_header is None:
        raise invalid_request(None, "X-Request-Id is required.")
    if candidate_request_id is None:
        raise invalid_request(None, "X-Request-Id must be a UUID.")
    return candidate_request_id
