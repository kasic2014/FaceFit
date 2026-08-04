"""Orchestrate independent Vision and Analysis Jobs into one Session result."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import os
from pathlib import Path
from typing import Any

from integration.contracts.common_contracts import (
    IntegrationContractError,
    atomic_write_json,
    atomic_write_text,
    map_job_status,
    normalize_error,
    validate_session_id,
)
from integration.contracts.integrated_session_contract import build_integrated_session
from integration.services.integration_validator import validate_integration_inputs


class IntegratedSessionService:
    """Service-layer orchestration with an injectable HTTP client."""

    def __init__(self, client: Any, *, expose_transcript_text: bool | None = None) -> None:
        self.client = client
        if expose_transcript_text is None:
            expose_transcript_text = os.environ.get(
                "FACEFIT_INTEGRATION_EXPOSE_TRANSCRIPT_TEXT", "false"
            ).strip().lower() in {"1", "true", "yes", "on"}
        self.expose_transcript_text = bool(expose_transcript_text)

    @staticmethod
    def _capture_error(error: IntegrationContractError) -> dict[str, Any]:
        return normalize_error(
            error.source if error.source in {"VISION", "ANALYSIS", "INTEGRATION"} else "INTEGRATION",
            error.code,
            error.message,
            retryable=error.retryable,
        )

    def _poll(self, source: str, job: dict[str, Any]) -> dict[str, Any]:
        return self.client.poll_job(source, job)

    def run(self, session_id: str) -> dict[str, Any]:
        validate_session_id(session_id)
        component_errors: list[dict[str, Any]] = []
        service_checks: dict[str, dict[str, Any]] = {}
        for source in ("VISION", "ANALYSIS"):
            try:
                health = self.client.health(source)
                ready = self.client.ready(source)
                service_checks[source.lower()] = {
                    "health": str(health.get("status", "UNKNOWN")),
                    "ready": str(ready.get("status", "UNKNOWN")),
                }
            except IntegrationContractError as exc:
                service_checks[source.lower()] = {"health": "UNAVAILABLE", "ready": "UNAVAILABLE"}
                component_errors.append(self._capture_error(exc))

        initial_jobs: dict[str, dict[str, Any]] = {}
        creators = {
            "VISION": self.client.create_vision_job,
            "ANALYSIS": self.client.create_analysis_job,
        }
        for source, creator in creators.items():
            try:
                initial_jobs[source] = creator(session_id)
            except IntegrationContractError as exc:
                component_errors.append(self._capture_error(exc))

        terminal_jobs: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="facefit-integration") as executor:
            futures = {
                executor.submit(self._poll, source, job): source
                for source, job in initial_jobs.items()
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    terminal_jobs[source] = future.result()
                except IntegrationContractError as exc:
                    component_errors.append(self._capture_error(exc))

        vision: dict[str, Any] | None = None
        transcription: dict[str, Any] | None = None
        speech: dict[str, Any] | None = None
        vision_job = terminal_jobs.get("VISION")
        analysis_job = terminal_jobs.get("ANALYSIS")
        if vision_job is not None:
            try:
                normalized = map_job_status("VISION", vision_job.get("status"))
                if normalized in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}:
                    vision = self.client.vision_feedback(session_id)
                else:
                    component_errors.append(
                        normalize_error(
                            "VISION",
                            "COMPONENT_JOB_FAILED",
                            "Vision job failed before an integrated result was available.",
                        )
                    )
            except IntegrationContractError as exc:
                component_errors.append(self._capture_error(exc))
        if analysis_job is not None:
            try:
                normalized = map_job_status("ANALYSIS", analysis_job.get("status"))
                if normalized in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}:
                    try:
                        transcription = self.client.transcription(session_id)
                    except IntegrationContractError as exc:
                        component_errors.append(self._capture_error(exc))
                    try:
                        speech = self.client.speech_characteristics(session_id)
                    except IntegrationContractError as exc:
                        component_errors.append(self._capture_error(exc))
                else:
                    component_errors.append(
                        normalize_error(
                            "ANALYSIS",
                            "COMPONENT_JOB_FAILED",
                            "Analysis job failed before an integrated result was available.",
                        )
                    )
            except IntegrationContractError as exc:
                component_errors.append(self._capture_error(exc))

        validation = validate_integration_inputs(session_id, vision, transcription, speech)
        integrated = build_integrated_session(
            session_id=session_id,
            vision=vision,
            transcription=transcription,
            speech=speech,
            validation=validation,
            jobs={"vision": vision_job, "analysis": analysis_job},
            component_errors=component_errors,
            expose_transcript_text=self.expose_transcript_text,
        )
        component_status = {
            "sessionId": session_id,
            "services": service_checks,
            "vision": self._job_status(vision_job),
            "analysis": self._job_status(analysis_job),
            "errorCount": len(component_errors),
            "errors": deepcopy(component_errors),
        }
        return {
            "integratedSession": integrated,
            "integrationValidation": validation,
            "componentStatus": component_status,
            "runtimeMetadata": {
                "visionJobId": vision_job.get("jobId") if vision_job else None,
                "analysisJobId": analysis_job.get("jobId") if analysis_job else None,
            },
        }

    @staticmethod
    def _job_status(job: dict[str, Any] | None) -> dict[str, Any]:
        if job is None:
            return {"status": "UNAVAILABLE", "sourceStatus": "UNAVAILABLE"}
        source = "VISION" if job.get("analysisMode") is not None else "ANALYSIS"
        source_status = str(job.get("status", "UNAVAILABLE"))
        return {"status": map_job_status(source, source_status), "sourceStatus": source_status}

    @staticmethod
    def write_outputs(output_root: str | Path, package: dict[str, Any]) -> Path:
        session_id = package["integratedSession"]["sessionId"]
        root = Path(output_root) / session_id
        atomic_write_json(root / "integrated_session.json", package["integratedSession"])
        atomic_write_json(root / "integration_validation.json", package["integrationValidation"])
        atomic_write_json(root / "component_status.json", package["componentStatus"])
        integrated = package["integratedSession"]
        validation = package["integrationValidation"]
        report = "\n".join(
            [
                f"# Face-Fit integrated Session report: {session_id}",
                "",
                f"- Status: `{integrated['status']}`",
                f"- Answers: {len(integrated['answers'])}",
                f"- Warnings: {len(integrated['warnings'])}",
                f"- Limitations: {len(integrated['limitations'])}",
                f"- Validation errors: {validation['errorCount']}",
                f"- Transcript text exposed: {integrated['components']['transcription']['textExposed']}",
                "- Scoring available: false",
                "",
                "This report contains no participant identifier, source filename, internal path, or score.",
                "",
            ]
        )
        atomic_write_text(root / "integration_report.md", report)
        return root
