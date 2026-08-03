"""Asynchronous job orchestration and sanitized Stage 25/26 result projection."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import threading
from typing import Any, Callable
import uuid

from app.audio.audio_contracts import validate_session_id
from app.audio.audio_manifest_writer import ensure_finite
from app.audio.session_audio_preprocessor import load_strict_json
from app.core.analysis_api_config import AnalysisApiConfig
from app.speech.speech_analysis_service import SpeechAnalysisError, SpeechAnalysisService
from app.speech.speech_contracts import resolve_profile as resolve_speech_profile
from app.stt.faster_whisper_adapter import FasterWhisperAdapter
from app.stt.session_transcription_service import SessionTranscriptionError, SessionTranscriptionService
from app.stt.transcription_profile import ProfileError, resolve_profile as resolve_stt_profile

from .analysis_job_executor import AnalysisJobExecutor, JobExecutorError
from .analysis_job_lock import AnalysisJobLockManager, JobLockError, LockAcquisition
from .analysis_job_retention import AnalysisJobRetention
from .analysis_job_storage import AnalysisJobStorage, JobStorageError


PIPELINES = ("STT_TRANSCRIPTION", "SPEECH_CHARACTERISTICS", "STT_AND_SPEECH")
TERMINAL_SUCCESS = {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}
TERMINAL = TERMINAL_SUCCESS | {"FAILED"}
IN_PROGRESS = {"QUEUED", "RUNNING"}
ALLOWED_TRANSITIONS = {
    "QUEUED": {"RUNNING", "FAILED"},
    "RUNNING": {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"},
}
WARNING_MESSAGES = {
    "SEGMENT_BOUNDARY_EXPANDED_TO_WORDS": "Model segment boundaries were expanded to include word timestamps.",
    "UPSTREAM_TRANSCRIPTION_WARNING": "Upstream transcription contains technical warnings.",
    "FILLER_CANDIDATE_REVIEW_REQUIRED": "Filler candidates require human review.",
    "STALE_JOB_LOCK_RECOVERED": "A stale analysis execution lock was safely recovered.",
}
ERROR_MESSAGES = {
    "SESSION_NOT_FOUND": "Analysis session was not found",
    "DEPENDENCY_UNAVAILABLE": "Analysis dependency is unavailable",
    "STT_TRANSCRIPTION_FAILED": "Session transcription failed",
    "SPEECH_CHARACTERISTICS_FAILED": "Speech characteristics analysis failed",
    "JOB_INTERRUPTED_BY_RESTART": "Analysis job was interrupted by process restart",
    "JOB_INTERRUPTED_BY_SHUTDOWN": "Analysis job was interrupted by service shutdown",
    "JOB_LOCK_TIMEOUT": "Analysis execution lock wait timed out",
    "JOB_LOCK_CORRUPTED": "Analysis execution lock is corrupted",
    "JOB_LOCK_ERROR": "Analysis execution lock failed",
    "INTERNAL_SERVER_ERROR": "Internal server error",
}


class AnalysisApiServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _duration_ms(start: Any, end: Any) -> int | None:
    left, right = _parse_utc(start), _parse_utc(end)
    if left is None or right is None:
        return None
    return max(0, round((right - left).total_seconds() * 1000))


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
        lock_manager: AnalysisJobLockManager | None = None,
        executor: Any | None = None,
        retention: AnalysisJobRetention | None = None,
        stt_runner: Callable[[str, bool], dict[str, Any]] | None = None,
        speech_runner: Callable[[str, bool], dict[str, Any]] | None = None,
        stt_adapter_factory: Callable[..., Any] = FasterWhisperAdapter,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.config = config
        self.output_root = config.output_root
        self.storage = storage or AnalysisJobStorage(self.output_root)
        self.lock_manager = lock_manager or AnalysisJobLockManager(
            self.output_root,
            wait_seconds=config.job_lock_wait_seconds,
            stale_seconds=config.stale_lock_seconds,
        )
        self._now = now
        self._stt_runner = stt_runner or self._run_stt
        self._speech_runner = speech_runner or self._run_speech
        self._stt_adapter_factory = stt_adapter_factory
        self._shared_stt_adapter: Any | None = None
        self._shared_stt_signature: tuple[str, str, str, str, bool] | None = None
        self._adapter_lock = threading.RLock()
        self._stt_execution_lock = threading.Lock()
        self._speech_locks_guard = threading.RLock()
        self._speech_locks: dict[str, threading.Lock] = {}
        self._state_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._started = False
        self._shutdown = False
        self.recovery_report: dict[str, Any] = {
            "interruptedQueued": 0,
            "interruptedRunning": 0,
            "staleLocksRecovered": 0,
            "corruptedLocks": 0,
        }
        self.retention_report: dict[str, Any] | None = None
        self.executor = executor or AnalysisJobExecutor(
            max_workers=config.job_max_workers,
            queue_capacity=config.job_queue_capacity,
            handler=self.run_job,
            interrupt_handler=self.interrupt_job,
        )
        self.retention = retention or AnalysisJobRetention(
            self.storage,
            retention_days=config.job_retention_days,
            max_records=config.job_max_records,
            lock_owner_ids=self.lock_manager.owner_job_ids,
        )

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._started:
                return
            if self._shutdown:
                raise AnalysisApiServiceError(
                    "JOB_EXECUTOR_SHUTTING_DOWN", "Analysis job executor is stopped", 503
                )
            interrupted = self.recover_interrupted_jobs()
            locks = self.lock_manager.recover_stale_locks(
                job_lookup=self._lookup_optional,
                active_job_ids=lambda: set(),
            )
            self.recovery_report = {
                **interrupted,
                "staleLocksRecovered": locks["recovered"],
                "corruptedLocks": locks["corrupted"],
            }
            if self.config.job_retention_enabled:
                self.retention_report = self.retention.cleanup(apply=True)
            self.executor.start()
            self._started = True

    def shutdown(self) -> dict[str, int]:
        with self._lifecycle_lock:
            if self._shutdown:
                return {"queuedInterrupted": 0, "runningInterrupted": 0}
            self._shutdown = True
        return self.executor.shutdown(self.config.shutdown_wait_seconds)

    def _shared_adapter_factory(self, profile: Any, *, local_files_only: bool) -> Any:
        signature = (
            profile.model_id,
            profile.revision,
            profile.device,
            profile.compute_type,
            local_files_only,
        )
        with self._adapter_lock:
            if self._shared_stt_adapter is None:
                self._shared_stt_adapter = self._stt_adapter_factory(
                    profile, local_files_only=local_files_only
                )
                self._shared_stt_signature = signature
            elif self._shared_stt_signature != signature:
                raise SessionTranscriptionError(
                    "STT_RUNTIME_UNAVAILABLE", "Shared STT adapter profile changed"
                )
            return self._shared_stt_adapter

    def _run_stt(self, session_id: str, force_rebuild: bool) -> dict[str, Any]:
        with self._stt_execution_lock:
            profile = resolve_stt_profile("auto")
            service = SessionTranscriptionService(
                profile=profile,
                local_files_only=True,
                output_root=self.output_root / "stt_transcription",
                preprocessing_root=self.output_root / "stt_preprocessing",
                adapter_factory=self._shared_adapter_factory,
            )
            return service.run(session_id, force_rebuild=force_rebuild)

    def _run_speech(self, session_id: str, force_rebuild: bool) -> dict[str, Any]:
        with self._speech_locks_guard:
            session_lock = self._speech_locks.setdefault(session_id, threading.Lock())
        with session_lock:
            service = SpeechAnalysisService(
                profile=resolve_speech_profile(),
                output_root=self.output_root / "speech_characteristics",
                preprocessing_root=self.output_root / "stt_preprocessing",
                transcription_root=self.output_root / "stt_transcription",
            )
            return service.run(session_id, force_rebuild=force_rebuild)

    def readiness(self) -> tuple[dict[str, Any], int]:
        execution = self.executor.metrics()
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
            "jobExecutorAccepting": bool(execution["acceptingJobs"]),
        }
        ready = all(checks.values())
        configuration_warnings = []
        if self.config.job_max_workers > 1:
            configuration_warnings.append({
                "code": "MULTIPLE_GPU_WORKERS_CONFIGURED",
                "message": "Multiple workers may increase GPU memory contention; STT execution remains serialized.",
            })
        return ({
            "status": "READY" if ready else "NOT_READY",
            "service": "face-fit-analysis-api",
            "availablePipelines": list(PIPELINES),
            "pipelines": list(PIPELINES),
            "scoringAvailable": False,
            "jobExecution": execution,
            "recovery": deepcopy(self.recovery_report),
            "configurationWarnings": configuration_warnings,
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
        if not self._started:
            self.start()
        with self.storage.creation_guard():
            if not force_rebuild:
                reusable = self._find_reusable(session_id, pipeline)
                if reusable is not None:
                    return self.public_job(reusable)
            if not self.executor.reserve():
                metrics = self.executor.metrics()
                code = "JOB_QUEUE_FULL" if metrics["acceptingJobs"] else "JOB_EXECUTOR_SHUTTING_DOWN"
                message = (
                    "현재 분석 요청이 많아 새 작업을 등록할 수 없습니다."
                    if code == "JOB_QUEUE_FULL"
                    else "Analysis job executor is shutting down"
                )
                raise AnalysisApiServiceError(code, message, 503)
            timestamp = _iso(self._now())
            record = {
                "jobId": str(uuid.uuid4()),
                "sessionId": session_id,
                "pipeline": pipeline,
                "forceRebuild": force_rebuild,
                "status": "QUEUED",
                "createdAt": timestamp,
                "queuedAt": timestamp,
                "startedAt": None,
                "completedAt": None,
                "updatedAt": timestamp,
                "queueWaitMs": None,
                "executionDurationMs": None,
                "totalDurationMs": None,
                "resultAvailable": False,
                "warnings": [],
                "error": None,
            }
            try:
                self.storage.create(record)
            except Exception:
                self.executor.cancel_reservation()
                raise
            try:
                self.executor.enqueue_reserved(record["jobId"])
            except JobExecutorError as exc:
                try:
                    self.storage.delete(record["jobId"])
                except JobStorageError:
                    pass
                raise AnalysisApiServiceError(exc.code, str(exc), 503) from exc
            return self.public_job(record)

    def run_job(self, job_id: str) -> None:
        acquisition: LockAcquisition | None = None
        lock_warning_codes: list[str] = []
        try:
            record = self._normalize_record(self.storage.read(job_id))
            if record.get("status") != "QUEUED":
                return
            acquisition = self.lock_manager.acquire(
                job_id=job_id,
                session_id=record["sessionId"],
                pipeline=record["pipeline"],
                job_lookup=self._lookup_optional,
                active_job_ids=self.executor.active_job_ids,
            )
            if acquisition.recovered_stale_lock:
                lock_warning_codes.append("STALE_JOB_LOCK_RECOVERED")
            record = self._transition(job_id, "RUNNING")
            self._execute(record["sessionId"], record["pipeline"], bool(record["forceRebuild"]))
            warnings = _warnings(lock_warning_codes) + self._pipeline_warnings(
                record["sessionId"], record["pipeline"]
            )
            target = "SUCCEEDED_WITH_WARNINGS" if warnings else "SUCCEEDED"
            self._transition(
                job_id, target, warnings=warnings, result_available=True
            )
        except Exception as exc:
            code, status = self._map_execution_error(exc, job_id)
            self._fail_if_active(job_id, code, status)
        finally:
            if acquisition is not None:
                self.lock_manager.release(acquisition, job_id=job_id)

    def _execute(self, session_id: str, pipeline: str, force_rebuild: bool) -> None:
        if pipeline in {"STT_TRANSCRIPTION", "STT_AND_SPEECH"}:
            self._stt_runner(session_id, force_rebuild)
        if pipeline in {"SPEECH_CHARACTERISTICS", "STT_AND_SPEECH"}:
            self._speech_runner(session_id, force_rebuild)

    def _map_execution_error(self, exc: Exception, job_id: str) -> tuple[str, int]:
        if isinstance(exc, AnalysisApiServiceError):
            return exc.code, exc.status_code
        if isinstance(exc, JobLockError):
            return exc.code, 500
        if isinstance(exc, (ProfileError, SessionTranscriptionError)):
            if exc.code in {"STT_DEPENDENCY_BLOCKED", "STT_MODEL_DOWNLOAD_BLOCKED", "STT_RUNTIME_UNAVAILABLE"}:
                return "DEPENDENCY_UNAVAILABLE", 503
            record = self._lookup_optional(job_id)
            if record is not None and not self._session_exists(record["sessionId"]):
                return "SESSION_NOT_FOUND", 404
            return "STT_TRANSCRIPTION_FAILED", 500
        if isinstance(exc, SpeechAnalysisError):
            record = self._lookup_optional(job_id)
            if record is not None and not self._session_exists(record["sessionId"]):
                return "SESSION_NOT_FOUND", 404
            return "SPEECH_CHARACTERISTICS_FAILED", 500
        if isinstance(exc, JobStorageError):
            return "JOB_STORAGE_ERROR", 500
        return "INTERNAL_SERVER_ERROR", 500

    def _fail_if_active(self, job_id: str, code: str, status_code: int) -> None:
        try:
            current = self.storage.read(job_id)
            if current.get("status") in IN_PROGRESS:
                self._transition(
                    job_id,
                    "FAILED",
                    error={
                        "code": code,
                        "message": ERROR_MESSAGES.get(code, "Analysis job failed"),
                        "httpStatus": status_code,
                    },
                    result_available=False,
                )
        except (JobStorageError, AnalysisApiServiceError):
            return

    def interrupt_job(self, job_id: str, code: str) -> None:
        self._fail_if_active(job_id, code, 500)

    def recover_interrupted_jobs(self) -> dict[str, int]:
        result = {"interruptedQueued": 0, "interruptedRunning": 0}
        for record in self.storage.list_records():
            status = record.get("status")
            if status not in IN_PROGRESS:
                continue
            normalized = self._normalize_record(record)
            self.storage.write(normalized)
            self._transition(
                normalized["jobId"],
                "FAILED",
                error={
                    "code": "JOB_INTERRUPTED_BY_RESTART",
                    "message": ERROR_MESSAGES["JOB_INTERRUPTED_BY_RESTART"],
                    "httpStatus": 500,
                },
                result_available=False,
            )
            result["interruptedQueued" if status == "QUEUED" else "interruptedRunning"] += 1
        return result

    def _transition(
        self,
        job_id: str,
        target: str,
        *,
        warnings: list[dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
        result_available: bool = False,
    ) -> dict[str, Any]:
        with self._state_lock:
            record = self._normalize_record(self.storage.read(job_id))
            current = str(record.get("status"))
            if target not in ALLOWED_TRANSITIONS.get(current, set()):
                raise AnalysisApiServiceError(
                    "INVALID_JOB_STATE_TRANSITION",
                    "Analysis job state transition is invalid",
                    409,
                )
            now = _iso(self._now())
            record["status"] = target
            record["updatedAt"] = now
            if target == "RUNNING":
                record["startedAt"] = now
                record["queueWaitMs"] = _duration_ms(record["queuedAt"], now)
                record["resultAvailable"] = False
                record["error"] = None
            elif target in TERMINAL:
                record["completedAt"] = now
                record["executionDurationMs"] = _duration_ms(record.get("startedAt"), now)
                record["totalDurationMs"] = _duration_ms(record["createdAt"], now)
                record["resultAvailable"] = bool(result_available and target in TERMINAL_SUCCESS)
                record["warnings"] = warnings or []
                record["error"] = error if target == "FAILED" else None
                if target == "FAILED" and record["error"] is None:
                    raise AnalysisApiServiceError(
                        "INVALID_JOB_STATE_TRANSITION", "Failed job requires an error", 409
                    )
            self._validate_record(record)
            self.storage.write(record)
            return record

    def _validate_record(self, record: dict[str, Any]) -> None:
        ordered = [
            _parse_utc(record.get("createdAt")),
            _parse_utc(record.get("queuedAt")),
            _parse_utc(record.get("startedAt")),
            _parse_utc(record.get("completedAt")),
        ]
        present = [value for value in ordered if value is not None]
        if len(present) < 2 or any(left > right for left, right in zip(present, present[1:])):
            raise AnalysisApiServiceError(
                "INVALID_JOB_STATE_TRANSITION", "Analysis job timestamps are invalid", 409
            )
        status = record.get("status")
        if status in TERMINAL and record.get("completedAt") is None:
            raise AnalysisApiServiceError(
                "INVALID_JOB_STATE_TRANSITION", "Terminal job requires completedAt", 409
            )
        if status == "FAILED" and record.get("resultAvailable"):
            raise AnalysisApiServiceError(
                "INVALID_JOB_STATE_TRANSITION", "Failed job cannot expose a result", 409
            )
        ensure_finite(record)

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(record)
        created = normalized.get("createdAt")
        normalized.setdefault("queuedAt", created)
        normalized.setdefault(
            "updatedAt",
            normalized.get("completedAt") or normalized.get("startedAt") or created,
        )
        normalized.setdefault(
            "queueWaitMs", _duration_ms(normalized.get("queuedAt"), normalized.get("startedAt"))
        )
        normalized.setdefault(
            "executionDurationMs",
            _duration_ms(normalized.get("startedAt"), normalized.get("completedAt")),
        )
        normalized.setdefault(
            "totalDurationMs", _duration_ms(created, normalized.get("completedAt"))
        )
        normalized.setdefault("warnings", [])
        normalized.setdefault("error", None)
        normalized.setdefault("resultAvailable", False)
        return normalized

    def _find_reusable(self, session_id: str, pipeline: str) -> dict[str, Any] | None:
        candidates = [
            self._normalize_record(row) for row in self.storage.list_records()
            if row.get("sessionId") == session_id
            and row.get("pipeline") == pipeline
            and row.get("forceRebuild") is False
            and row.get("status") in TERMINAL_SUCCESS | IN_PROGRESS
        ]
        return max(candidates, key=lambda row: str(row.get("createdAt", ""))) if candidates else None

    def _lookup_optional(self, job_id: str) -> dict[str, Any] | None:
        try:
            return self._normalize_record(self.storage.read(job_id))
        except JobStorageError as exc:
            if exc.code == "JOB_NOT_FOUND":
                return None
            raise

    def get_job(self, job_id: str) -> dict[str, Any]:
        try:
            return self.public_job(self._normalize_record(self.storage.read(job_id)))
        except JobStorageError as exc:
            status = 404 if exc.code == "JOB_NOT_FOUND" else 500
            raise AnalysisApiServiceError(exc.code, str(exc), status) from exc

    @staticmethod
    def public_job(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(record.get(key))
            for key in (
                "jobId", "sessionId", "pipeline", "status", "createdAt", "queuedAt",
                "startedAt", "completedAt", "updatedAt", "queueWaitMs",
                "executionDurationMs", "totalDurationMs", "resultAvailable", "warnings", "error",
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
