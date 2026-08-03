"""Synchronous orchestration and sanitized result projection for Stage 27."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
from typing import Any, Callable
import uuid

from app.audio.audio_contracts import validate_session_id
from app.audio.session_audio_preprocessor import load_strict_json
from app.core.analysis_api_config import AnalysisApiConfig
from app.speech.speech_analysis_service import SpeechAnalysisError, SpeechAnalysisService
from app.speech.speech_contracts import resolve_profile as resolve_speech_profile
from app.stt.session_transcription_service import SessionTranscriptionError, SessionTranscriptionService
from app.stt.transcription_profile import ProfileError, resolve_profile as resolve_stt_profile

from .analysis_job_storage import AnalysisJobStorage, JobStorageError


PIPELINES = ("STT_TRANSCRIPTION", "SPEECH_CHARACTERISTICS", "STT_AND_SPEECH")
TERMINAL_SUCCESS = {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}
IN_PROGRESS = {"QUEUED", "RUNNING"}
WARNING_MESSAGES = {
    "SEGMENT_BOUNDARY_EXPANDED_TO_WORDS": "Model segment boundaries were expanded to include word timestamps.",
    "UPSTREAM_TRANSCRIPTION_WARNING": "Upstream transcription contains technical warnings.",
    "FILLER_CANDIDATE_REVIEW_REQUIRED": "Filler candidates require human review.",
}


class AnalysisApiServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _warning(code: str, answer_id: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "message": WARNING_MESSAGES.get(code, "A technical pipeline warning was reported."),
    }
    if answer_id:
        item["answerId"] = answer_id
    return item


def _warnings(codes: list[Any], answer_id: str | None = None) -> list[dict[str, Any]]:
    return [_warning(str(code), answer_id) for code in dict.fromkeys(codes)]


def _safe_load(path: Path, *, missing_code: str, missing_message: str) -> dict[str, Any]:
    if not path.is_file():
        status = 500 if missing_code == "INTERNAL_SERVER_ERROR" else 409
        raise AnalysisApiServiceError(missing_code, missing_message, status)
    try:
        return load_strict_json(path)
    except Exception as exc:
        raise AnalysisApiServiceError("INTERNAL_SERVER_ERROR", "Analysis result is invalid", 500) from exc


def _validate_session(session_id: str) -> None:
    try:
        validate_session_id(session_id)
    except ValueError as exc:
        raise AnalysisApiServiceError("VALIDATION_ERROR", "sessionId is invalid", 422) from exc


def _strip_evaluation_fields(value: Any) -> Any:
    forbidden = {
        "score", "grade", "confidence", "anxiety", "personality", "emotion",
        "passprobability", "toofast", "tooslow", "tooquiet", "tooloud", "monotone",
        "scoringapproved", "manualreviewrequired",
    }
    if isinstance(value, dict):
        return {
            key: _strip_evaluation_fields(item)
            for key, item in value.items()
            if key.replace("_", "").lower() not in forbidden
        }
    if isinstance(value, list):
        return [_strip_evaluation_fields(item) for item in value]
    return value


class AnalysisJobService:
    def __init__(
        self,
        config: AnalysisApiConfig,
        *,
        storage: AnalysisJobStorage | None = None,
        stt_runner: Callable[[str, bool], dict[str, Any]] | None = None,
        speech_runner: Callable[[str, bool], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.output_root = config.output_root
        self.storage = storage or AnalysisJobStorage(self.output_root)
        self._stt_runner = stt_runner or self._run_stt
        self._speech_runner = speech_runner or self._run_speech

    def _run_stt(self, session_id: str, force_rebuild: bool) -> dict[str, Any]:
        profile = resolve_stt_profile("auto")
        service = SessionTranscriptionService(
            profile=profile,
            local_files_only=True,
            output_root=self.output_root / "stt_transcription",
            preprocessing_root=self.output_root / "stt_preprocessing",
        )
        return service.run(session_id, force_rebuild=force_rebuild)

    def _run_speech(self, session_id: str, force_rebuild: bool) -> dict[str, Any]:
        service = SpeechAnalysisService(
            profile=resolve_speech_profile(),
            output_root=self.output_root / "speech_characteristics",
            preprocessing_root=self.output_root / "stt_preprocessing",
            transcription_root=self.output_root / "stt_transcription",
        )
        return service.run(session_id, force_rebuild=force_rebuild)

    def readiness(self) -> tuple[dict[str, Any], int]:
        checks = {
            "outputRootWritable": self._output_root_writable(),
            "jobStorageAvailable": self.storage.check_available(),
            "stage24ResolverAvailable": importlib.util.find_spec("app.audio.session_audio_preprocessor") is not None,
            "stage25ServiceAvailable": importlib.util.find_spec("app.stt.session_transcription_service") is not None,
            "stage26ServiceAvailable": importlib.util.find_spec("app.speech.speech_analysis_service") is not None,
            "requiredImportsAvailable": all(
                importlib.util.find_spec(name) is not None
                for name in ("fastapi", "pydantic", "uvicorn", "httpx")
            ),
        }
        ready = all(checks.values())
        return ({
            "status": "UP" if ready else "DOWN",
            "service": "face-fit-analysis-api",
            "pipelines": list(PIPELINES),
            "scoringAvailable": False,
            "checks": checks,
        }, 200 if ready else 503)

    def _output_root_writable(self) -> bool:
        descriptor: int | None = None
        probe: Path | None = None
        try:
            self.output_root.mkdir(parents=True, exist_ok=True)
            probe = self.output_root / f".analysis-api-probe-{uuid.uuid4()}.tmp"
            descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, b"ok")
            os.close(descriptor)
            descriptor = None
            return True
        except OSError:
            return False
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if probe is not None:
                try:
                    probe.unlink(missing_ok=True)
                except OSError:
                    pass

    def create_job(self, session_id: str, pipeline: str, force_rebuild: bool) -> dict[str, Any]:
        _validate_session(session_id)
        if pipeline not in PIPELINES:
            raise AnalysisApiServiceError("UNSUPPORTED_PIPELINE", "Pipeline is not supported", 422)
        if not force_rebuild:
            reusable = self._find_reusable(session_id, pipeline)
            if reusable is not None:
                return self.public_job(reusable)
        record = {
            "jobId": str(uuid.uuid4()),
            "sessionId": session_id,
            "pipeline": pipeline,
            "forceRebuild": force_rebuild,
            "status": "QUEUED",
            "createdAt": _now(),
            "startedAt": None,
            "completedAt": None,
            "resultAvailable": False,
            "warnings": [],
            "error": None,
        }
        self.storage.create(record)
        record["status"] = "RUNNING"
        record["startedAt"] = _now()
        self.storage.write(record)
        try:
            self._execute(session_id, pipeline, force_rebuild)
            warnings = self._pipeline_warnings(session_id, pipeline)
            record["warnings"] = warnings
            record["status"] = "SUCCEEDED_WITH_WARNINGS" if warnings else "SUCCEEDED"
            record["resultAvailable"] = True
            record["completedAt"] = _now()
            self.storage.write(record)
            return self.public_job(record)
        except AnalysisApiServiceError as exc:
            self._fail(record, exc.code, exc.status_code)
            raise
        except (ProfileError, SessionTranscriptionError) as exc:
            status = 503 if exc.code in {
                "STT_DEPENDENCY_BLOCKED", "STT_MODEL_DOWNLOAD_BLOCKED", "STT_RUNTIME_UNAVAILABLE"
            } else (404 if not self._session_exists(session_id) else 500)
            code = "DEPENDENCY_UNAVAILABLE" if status == 503 else (
                "SESSION_NOT_FOUND" if status == 404 else "STT_TRANSCRIPTION_FAILED"
            )
            self._fail(record, code, status)
            raise AnalysisApiServiceError(code, self._error_message(code), status) from exc
        except SpeechAnalysisError as exc:
            status = 404 if not self._session_exists(session_id) else 500
            code = "SESSION_NOT_FOUND" if status == 404 else "SPEECH_CHARACTERISTICS_FAILED"
            self._fail(record, code, status)
            raise AnalysisApiServiceError(code, self._error_message(code), status) from exc
        except JobStorageError:
            raise
        except Exception as exc:
            self._fail(record, "INTERNAL_SERVER_ERROR", 500)
            raise AnalysisApiServiceError("INTERNAL_SERVER_ERROR", "Internal server error", 500) from exc

    def _execute(self, session_id: str, pipeline: str, force_rebuild: bool) -> None:
        if pipeline in {"STT_TRANSCRIPTION", "STT_AND_SPEECH"}:
            self._stt_runner(session_id, force_rebuild)
        if pipeline in {"SPEECH_CHARACTERISTICS", "STT_AND_SPEECH"}:
            self._speech_runner(session_id, force_rebuild)

    def _fail(self, record: dict[str, Any], code: str, status_code: int) -> None:
        record["status"] = "FAILED"
        record["completedAt"] = _now()
        record["resultAvailable"] = False
        record["error"] = {"code": code, "message": self._error_message(code), "httpStatus": status_code}
        try:
            self.storage.write(record)
        except JobStorageError:
            pass

    @staticmethod
    def _error_message(code: str) -> str:
        return {
            "SESSION_NOT_FOUND": "Analysis session was not found",
            "DEPENDENCY_UNAVAILABLE": "Analysis dependency is unavailable",
            "STT_TRANSCRIPTION_FAILED": "Session transcription failed",
            "SPEECH_CHARACTERISTICS_FAILED": "Speech characteristics analysis failed",
        }.get(code, "Internal server error")

    def _find_reusable(self, session_id: str, pipeline: str) -> dict[str, Any] | None:
        candidates = [
            row for row in self.storage.list_records()
            if row.get("sessionId") == session_id
            and row.get("pipeline") == pipeline
            and row.get("forceRebuild") is False
            and row.get("status") in TERMINAL_SUCCESS | IN_PROGRESS
        ]
        return max(candidates, key=lambda row: str(row.get("createdAt", ""))) if candidates else None

    def get_job(self, job_id: str) -> dict[str, Any]:
        try:
            return self.public_job(self.storage.read(job_id))
        except JobStorageError as exc:
            status = 404 if exc.code == "JOB_NOT_FOUND" else 500
            raise AnalysisApiServiceError(exc.code, str(exc), status) from exc

    @staticmethod
    def public_job(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(record.get(key))
            for key in (
                "jobId", "sessionId", "pipeline", "status", "createdAt", "startedAt",
                "completedAt", "resultAvailable", "warnings", "error",
            )
        }

    def _pipeline_warnings(self, session_id: str, pipeline: str) -> list[dict[str, Any]]:
        codes: list[Any] = []
        if pipeline in {"STT_TRANSCRIPTION", "STT_AND_SPEECH"}:
            manifest = _safe_load(
                self.output_root / "stt_transcription" / session_id / "session_transcription_manifest.json",
                missing_code="RESULT_NOT_READY", missing_message="Transcription result is not ready",
            )
            codes.extend(manifest.get("warnings", []))
        if pipeline in {"SPEECH_CHARACTERISTICS", "STT_AND_SPEECH"}:
            manifest = _safe_load(
                self.output_root / "speech_characteristics" / session_id / "session_speech_manifest.json",
                missing_code="RESULT_NOT_READY", missing_message="Speech result is not ready",
            )
            codes.extend(manifest.get("warnings", []))
        return _warnings(codes)

    def _session_exists(self, session_id: str) -> bool:
        return (self.output_root / "stt_preprocessing" / session_id).is_dir()

    def _result_path(self, session_id: str, kind: str, filename: str) -> Path:
        _validate_session(session_id)
        root = self.output_root / kind / session_id
        path = root / filename
        if not path.is_file():
            if not self._session_exists(session_id):
                raise AnalysisApiServiceError("SESSION_NOT_FOUND", "Analysis session was not found", 404)
            raise AnalysisApiServiceError("RESULT_NOT_READY", "Analysis result is not ready", 409)
        return path

    def transcription_result(self, session_id: str) -> dict[str, Any]:
        manifest_path = self._result_path(
            session_id, "stt_transcription", "session_transcription_manifest.json"
        )
        manifest = _safe_load(manifest_path, missing_code="RESULT_NOT_READY", missing_message="Transcription result is not ready")
        engine_keys = (
            "name", "version", "ctranslate2Version", "model", "modelId", "revision",
            "device", "computeType", "profile", "localFilesOnly",
        )
        answers = []
        for summary in manifest.get("answers", []):
            answer_id = str(summary["answerId"])
            raw = _safe_load(
                manifest_path.parent / "answers" / f"{answer_id}.json",
                missing_code="INTERNAL_SERVER_ERROR", missing_message="Transcription answer is invalid",
            )
            segments = []
            for row in raw.get("segments", []):
                item = {key: deepcopy(value) for key, value in row.items() if key != "text"}
                item["text"] = row.get("text") if self.config.expose_transcript_text else None
                segments.append(item)
            words = []
            for row in raw.get("words", []):
                item = {key: deepcopy(value) for key, value in row.items() if key != "text"}
                item["text"] = row.get("text") if self.config.expose_transcript_text else None
                words.append(item)
            answers.append({
                "answerId": answer_id,
                "status": raw.get("status"),
                "language": deepcopy(raw.get("language", {})),
                "textExposed": self.config.expose_transcript_text,
                "text": raw.get("text") if self.config.expose_transcript_text else None,
                "segmentCount": len(segments),
                "wordCount": len(words),
                "segments": segments,
                "words": words,
                "warnings": _warnings(raw.get("warnings", []), answer_id),
            })
        return {
            "sessionId": session_id,
            "status": manifest.get("status"),
            "engine": {key: deepcopy(manifest.get("engine", {}).get(key)) for key in engine_keys if key in manifest.get("engine", {})},
            "options": deepcopy(manifest.get("options", {})),
            "answers": answers,
            "warnings": _warnings(manifest.get("warnings", [])),
            "errors": [],
        }

    def speech_result(self, session_id: str) -> dict[str, Any]:
        manifest_path = self._result_path(
            session_id, "speech_characteristics", "session_speech_manifest.json"
        )
        manifest = _safe_load(manifest_path, missing_code="RESULT_NOT_READY", missing_message="Speech result is not ready")
        answers = []
        for summary in manifest.get("answers", []):
            answer_id = str(summary["answerId"])
            raw = _safe_load(
                manifest_path.parent / "answers" / f"{answer_id}.json",
                missing_code="INTERNAL_SERVER_ERROR", missing_message="Speech answer is invalid",
            )
            answers.append(_strip_evaluation_fields({
                "answerId": answer_id,
                "status": raw.get("status"),
                "speakingRate": raw.get("speakingRate", {}),
                "timestampPauses": raw.get("timestampPauses", {}),
                "acousticSilence": raw.get("acousticSilence", {}),
                "fillerCandidates": raw.get("fillerCandidates", []),
                "volume": raw.get("volume", {}),
                "pitch": raw.get("pitch", {}),
                "warnings": _warnings(raw.get("warnings", []), answer_id),
            }))
        return {
            "sessionId": session_id,
            "status": manifest.get("status"),
            "analysisMode": "MEASUREMENT_ONLY",
            "scoringAvailable": False,
            "thresholdApproval": False,
            "answers": answers,
            "aggregate": _strip_evaluation_fields(deepcopy(manifest.get("aggregate", {}))),
            "warnings": _warnings(manifest.get("warnings", [])),
            "limitations": [
                "Measurements are technical observations and are not interview scores.",
                "Filler matches are candidates that require human review.",
                "Pitch values are physical F0 measurements, not emotion or personality inference.",
            ],
        }
