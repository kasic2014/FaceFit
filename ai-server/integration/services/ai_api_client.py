"""Bounded standard-library HTTP client for the two AI services."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from integration.contracts.common_contracts import (
    IntegrationContractError,
    TERMINAL_JOB_STATUSES,
    ensure_finite,
    validate_session_id,
)


@dataclass(frozen=True)
class AiApiClientConfig:
    vision_base_url: str = "http://127.0.0.1:8000"
    analysis_base_url: str = "http://127.0.0.1:8002"
    poll_interval_ms: int = 250
    timeout_seconds: float = 120.0
    request_timeout_seconds: float = 10.0
    retry_count: int = 2

    @classmethod
    def from_env(cls, values: dict[str, str] | None = None) -> "AiApiClientConfig":
        env = os.environ if values is None else values
        return cls(
            vision_base_url=env.get(
                "FACEFIT_VISION_API_BASE_URL", "http://127.0.0.1:8000"
            ),
            analysis_base_url=env.get(
                "FACEFIT_ANALYSIS_API_BASE_URL", "http://127.0.0.1:8002"
            ),
            poll_interval_ms=int(env.get("FACEFIT_INTEGRATION_POLL_INTERVAL_MS", "250")),
            timeout_seconds=float(env.get("FACEFIT_INTEGRATION_TIMEOUT_SECONDS", "120")),
        )

    def validated(self) -> "AiApiClientConfig":
        for name, value in (
            ("Vision", self.vision_base_url),
            ("Analysis", self.analysis_base_url),
        ):
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
                raise IntegrationContractError(
                    "COMPONENT_RESPONSE_INVALID", f"{name} base URL is invalid."
                )
        if not 1 <= self.poll_interval_ms <= 60_000:
            raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "Polling interval is invalid.")
        if not 0 < self.timeout_seconds <= 600:
            raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "Integration timeout is invalid.")
        if not 0 < self.request_timeout_seconds <= 120 or not 0 <= self.retry_count <= 5:
            raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "HTTP retry policy is invalid.")
        return self


class AiApiClient:
    """HTTP transport with finite retries, polling, and sanitized failures."""

    def __init__(
        self,
        config: AiApiClientConfig | None = None,
        *,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = (config or AiApiClientConfig.from_env()).validated()
        self._opener = opener
        self._clock = clock
        self._sleeper = sleeper

    def _base(self, source: str) -> str:
        if source == "VISION":
            return self.config.vision_base_url.rstrip("/")
        if source == "ANALYSIS":
            return self.config.analysis_base_url.rstrip("/")
        raise IntegrationContractError("COMPONENT_RESPONSE_INVALID", "Component source is invalid.")

    def _request(
        self,
        source: str,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encoded = None
        headers = {"Accept": "application/json"}
        if body is not None:
            encoded = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._base(source) + path, data=encoded, headers=headers, method=method)
        last_error: Exception | None = None
        for attempt in range(self.config.retry_count + 1):
            try:
                with self._opener(request, timeout=self.config.request_timeout_seconds) as response:
                    raw = response.read()
                    if not 200 <= int(response.status) < 300:
                        raise HTTPError(request.full_url, response.status, "HTTP error", {}, None)
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("response root is not an object")
                ensure_finite(value)
                return value
            except HTTPError as exc:
                retryable = exc.code >= 500
                last_error = exc
                if not retryable or attempt >= self.config.retry_count:
                    raise IntegrationContractError(
                        "COMPONENT_HTTP_ERROR",
                        f"{source} request failed with HTTP {exc.code}.",
                        source=source,
                        retryable=retryable,
                    ) from exc
            except (URLError, socket.timeout, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= self.config.retry_count:
                    raise IntegrationContractError(
                        "COMPONENT_HTTP_ERROR",
                        f"{source} request could not reach the service.",
                        source=source,
                        retryable=True,
                    ) from exc
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise IntegrationContractError(
                    "COMPONENT_RESPONSE_INVALID",
                    f"{source} returned invalid JSON.",
                    source=source,
                ) from exc
            if last_error is not None:
                self._sleeper(min(0.1 * (attempt + 1), 0.5))
        raise AssertionError("bounded retry loop did not terminate")

    def health(self, source: str) -> dict[str, Any]:
        return self._request(source, "/health")

    def ready(self, source: str) -> dict[str, Any]:
        return self._request(source, "/ready")

    def create_vision_job(self, session_id: str) -> dict[str, Any]:
        validate_session_id(session_id)
        return self._request(
            "VISION",
            "/api/v1/vision/jobs",
            method="POST",
            body={
                "sessionId": session_id,
                "analysisMode": "SINGLE_SESSION_BASELINE_RELATIVE_MVP",
                "forceRebuild": False,
            },
        )

    def create_analysis_job(self, session_id: str) -> dict[str, Any]:
        validate_session_id(session_id)
        return self._request(
            "ANALYSIS",
            "/api/v1/analysis/jobs",
            method="POST",
            body={"sessionId": session_id, "pipeline": "STT_AND_SPEECH", "forceRebuild": False},
        )

    def get_job(self, source: str, job_id: str) -> dict[str, Any]:
        prefix = "/api/v1/vision/jobs/" if source == "VISION" else "/api/v1/analysis/jobs/"
        return self._request(source, prefix + job_id)

    def poll_job(self, source: str, initial_job: dict[str, Any]) -> dict[str, Any]:
        job_id = initial_job.get("jobId")
        if not isinstance(job_id, str) or not job_id:
            raise IntegrationContractError(
                "COMPONENT_RESPONSE_INVALID", f"{source} jobId is invalid.", source=source
            )
        deadline = self._clock() + self.config.timeout_seconds
        current = initial_job
        while True:
            status = current.get("status")
            if status in TERMINAL_JOB_STATUSES:
                return current
            if self._clock() >= deadline:
                raise IntegrationContractError(
                    "INTEGRATION_TIMEOUT",
                    f"{source} job did not finish before the integration timeout.",
                    source="INTEGRATION",
                    retryable=True,
                )
            self._sleeper(self.config.poll_interval_ms / 1000)
            current = self.get_job(source, job_id)

    def vision_feedback(self, session_id: str) -> dict[str, Any]:
        return self._request("VISION", f"/api/v1/vision/sessions/{validate_session_id(session_id)}/feedback")

    def transcription(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "ANALYSIS", f"/api/v1/analysis/sessions/{validate_session_id(session_id)}/transcription"
        )

    def speech_characteristics(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "ANALYSIS",
            f"/api/v1/analysis/sessions/{validate_session_id(session_id)}/speech-characteristics",
        )
