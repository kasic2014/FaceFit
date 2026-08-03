"""Synchronous Vision MVP Job orchestration and strict file storage.

This module deliberately has no FastAPI dependency so its storage, validation,
idempotency, and Stage 22 reuse contracts remain testable independently.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable
import uuid

from app.vision.pilot_video_intake import (
    PilotVideoIntakeError,
    ensure_finite,
    load_strict_json,
)
from app.vision.single_session_mvp_feedback import (
    ANALYSIS_MODE,
    RESULT_INPUT_FAILED,
    RESULT_LIMITED,
    RESULT_READY,
    RESULT_UNAVAILABLE,
    SCORING_REASONS,
    SingleSessionMvpError,
    build_single_session_mvp_feedback,
    load_single_session_inputs,
)


SESSION_PATTERN = re.compile(r"^SES_\d{6}$")
PARTICIPANT_PATTERN = re.compile(r"^PTC_\d{6}$")
PARTICIPANT_REFERENCE_PATTERN = re.compile(r"PTC_\d{6}")
WINDOWS_PATH_PATTERN = re.compile(r"[A-Za-z]:[\\/]")
JOB_STATUSES = frozenset(
    {
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "SUCCEEDED_WITH_LIMITATIONS",
        "FAILED",
    }
)
SUCCESS_JOB_STATUSES = frozenset(
    {"SUCCEEDED", "SUCCEEDED_WITH_LIMITATIONS"}
)
STAGE22_STATUS_TO_JOB_STATUS = {
    RESULT_READY: "SUCCEEDED",
    RESULT_LIMITED: "SUCCEEDED_WITH_LIMITATIONS",
    RESULT_UNAVAILABLE: "FAILED",
    RESULT_INPUT_FAILED: "FAILED",
}
FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "participantid",
        "participant_id",
        "videopath",
        "video_path",
        "outputpath",
        "output_path",
        "consentreference",
        "consent_reference",
        "metadatareference",
        "metadata_reference",
        "raterid",
        "rater_id",
        "gazescore",
        "gaze_score",
        "posturescore",
        "posture_score",
        "totalscore",
        "total_score",
        "interviewscore",
        "interview_score",
        "passprobability",
        "pass_probability",
        "confidencescore",
        "confidence_score",
        "anxiety",
        "concentration",
        "personality",
        "emotion",
    }
)


class VisionApiServiceError(RuntimeError):
    """A sanitized API-facing service error."""

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.details = details or []


def validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not SESSION_PATTERN.fullmatch(
        session_id
    ):
        raise VisionApiServiceError(
            "VALIDATION_ERROR",
            422,
            "sessionId는 SES_ 다음 6자리 숫자 형식이어야 합니다.",
        )
    return session_id


def validate_job_id(job_id: str) -> str:
    try:
        parsed = uuid.UUID(job_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise VisionApiServiceError(
            "VALIDATION_ERROR",
            422,
            "jobId는 UUID 형식이어야 합니다.",
        ) from exc
    canonical = str(parsed)
    if canonical != job_id.lower():
        raise VisionApiServiceError(
            "VALIDATION_ERROR",
            422,
            "jobId는 표준 UUID 형식이어야 합니다.",
        )
    return canonical


def _strict_json_bytes(value: dict[str, Any]) -> bytes:
    ensure_finite(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def atomic_write_json(path: str | Path, value: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _strict_json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


class FileJobStorage:
    """Restart-safe strict JSON storage for non-identifying Job records."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def ensure_accessible(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".readiness.",
            suffix=".tmp",
            dir=self.root,
        )
        os.close(descriptor)
        Path(temporary_name).unlink()

    def _path(self, job_id: str) -> Path:
        return self.root / f"{validate_job_id(job_id)}.json"

    def save_new(self, record: dict[str, Any]) -> None:
        path = self._path(record["jobId"])
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(".lock")
        try:
            lock_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as exc:
            raise VisionApiServiceError(
                "JOB_STORAGE_ERROR",
                500,
                "Job ID 충돌로 요청을 저장하지 못했습니다.",
            ) from exc
        os.close(lock_descriptor)
        try:
            if path.exists():
                raise VisionApiServiceError(
                    "JOB_STORAGE_ERROR",
                    500,
                    "Job ID 충돌로 요청을 저장하지 못했습니다.",
                )
            atomic_write_json(path, record)
        finally:
            lock_path.unlink(missing_ok=True)

    def save(self, record: dict[str, Any]) -> None:
        path = self._path(record["jobId"])
        if not path.is_file():
            raise VisionApiServiceError(
                "JOB_STORAGE_ERROR",
                500,
                "Job 상태 저장소가 일관되지 않습니다.",
            )
        atomic_write_json(path, record)

    def load(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.is_file():
            raise VisionApiServiceError(
                "JOB_NOT_FOUND",
                404,
                "요청한 Vision Job을 찾을 수 없습니다.",
            )
        try:
            value = load_strict_json(path)
            self._validate_record(value)
        except (
            KeyError,
            PilotVideoIntakeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VisionApiServiceError(
                "JOB_STORAGE_ERROR",
                500,
                "Vision Job 저장 파일이 손상되었습니다.",
            ) from exc
        return value

    def list_records(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        records = [
            self.load(path.stem)
            for path in sorted(self.root.glob("*.json"))
        ]
        return records

    @staticmethod
    def _validate_record(record: dict[str, Any]) -> None:
        required = {
            "jobId",
            "sessionId",
            "analysisMode",
            "forceRebuild",
            "status",
            "createdAt",
            "startedAt",
            "completedAt",
            "resultAvailable",
            "warnings",
            "error",
        }
        if set(record) != required:
            raise ValueError("Job record fields are invalid")
        validate_job_id(record["jobId"])
        validate_session_id(record["sessionId"])
        if record["analysisMode"] != ANALYSIS_MODE:
            raise ValueError("Job analysis mode is invalid")
        if record["status"] not in JOB_STATUSES:
            raise ValueError("Job status is invalid")
        if not isinstance(record["forceRebuild"], bool):
            raise ValueError("forceRebuild must be boolean")
        if not isinstance(record["resultAvailable"], bool):
            raise ValueError("resultAvailable must be boolean")
        if not isinstance(record["warnings"], list):
            raise ValueError("warnings must be a list")
        if record["error"] is not None and not isinstance(
            record["error"], dict
        ):
            raise ValueError("error must be null or an object")
        _validate_iso_timestamp(record["createdAt"], nullable=False)
        _validate_iso_timestamp(record["startedAt"], nullable=True)
        _validate_iso_timestamp(record["completedAt"], nullable=True)
        ensure_finite(record)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_iso_timestamp(value: Any, *, nullable: bool) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise ValueError("Job timestamp must be an ISO 8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Job timestamp requires a timezone")


def _walk_response(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).replace("-", "_").lower()
            if normalized_key in FORBIDDEN_RESPONSE_KEYS:
                raise VisionApiServiceError(
                    "FEEDBACK_BUILD_FAILED",
                    500,
                    "피드백 응답에 허용되지 않은 필드가 포함되었습니다.",
                )
            _walk_response(item)
    elif isinstance(value, list):
        for item in value:
            _walk_response(item)
    elif isinstance(value, str):
        lower = value.lower()
        if (
            PARTICIPANT_REFERENCE_PATTERN.search(value)
            or WINDOWS_PATH_PATTERN.search(value)
            or "/data/" in lower
            or "\\data\\" in lower
        ):
            raise VisionApiServiceError(
                "FEEDBACK_BUILD_FAILED",
                500,
                "피드백 응답에 내부 식별자 또는 경로가 포함되었습니다.",
            )


def validate_feedback_contract(
    payload: dict[str, Any],
    *,
    expected_session_id: str,
) -> dict[str, Any]:
    """Validate and canonicalize the Stage 22 public feedback contract."""

    validate_session_id(expected_session_id)
    ensure_finite(payload)
    result = deepcopy(payload)
    if result.get("sessionId") != expected_session_id:
        raise VisionApiServiceError(
            "FEEDBACK_BUILD_FAILED",
            500,
            "피드백 Session 참조가 일치하지 않습니다.",
        )
    if result.get("analysisMode") != ANALYSIS_MODE:
        raise VisionApiServiceError(
            "FEEDBACK_BUILD_FAILED",
            500,
            "피드백 분석 모드가 일치하지 않습니다.",
        )
    status = result.get("status")
    if status not in STAGE22_STATUS_TO_JOB_STATUS:
        raise VisionApiServiceError(
            "FEEDBACK_BUILD_FAILED",
            500,
            "피드백 상태가 지원되지 않습니다.",
        )
    if result.get("scores", object()) is not None:
        raise VisionApiServiceError(
            "FEEDBACK_BUILD_FAILED",
            500,
            "단일 세션 MVP에서는 점수를 제공할 수 없습니다.",
        )
    reasons = result.pop(
        "scoreUnavailableReasons",
        result.get("scoringUnavailableReasons"),
    )
    if reasons != list(SCORING_REASONS):
        raise VisionApiServiceError(
            "FEEDBACK_BUILD_FAILED",
            500,
            "점수 미지원 사유 계약이 일치하지 않습니다.",
        )
    result["scoringUnavailableReasons"] = list(SCORING_REASONS)
    _walk_response(result)
    ensure_finite(result)
    return result


def _warning_contract(warnings: Any) -> list[dict[str, str]]:
    if not isinstance(warnings, list):
        return []
    normalized: list[dict[str, str]] = []
    for warning in warnings:
        if isinstance(warning, dict):
            code = warning.get("code")
            message = warning.get("message")
            if isinstance(code, str) and isinstance(message, str):
                normalized.append({"code": code, "message": message})
        elif isinstance(warning, str):
            code = (
                "HEAD_POSE_PARTIAL_AVAILABILITY"
                if "고개 방향" in warning
                else "MEASUREMENT_LIMITATION"
            )
            normalized.append({"code": code, "message": warning})
    return normalized


class VisionJobService:
    """Execute Stage 22 feedback-only Jobs without invoking pipeline CLIs."""

    def __init__(
        self,
        *,
        vision_server_root: str | Path,
        output_root: str | Path,
        storage: FileJobStorage | None = None,
        job_id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.vision_server_root = Path(vision_server_root)
        self.output_root = Path(output_root)
        self.storage = storage or FileJobStorage(
            self.output_root / "vision_api" / "jobs"
        )
        self.job_id_generator = job_id_generator or (
            lambda: str(uuid.uuid4())
        )
        self.clock = clock or _utc_now

    def _session_root(self, session_id: str) -> Path:
        return (
            self.output_root
            / "pilot_video_intake_validation"
            / session_id
        )

    def _feedback_path(self, session_id: str) -> Path:
        return (
            self.output_root
            / "single_session_mvp_feedback"
            / session_id
            / "mvp_feedback_api_contract.json"
        )

    def _require_registered_session(self, session_id: str) -> None:
        validate_session_id(session_id)
        if not self._session_root(session_id).is_dir():
            raise VisionApiServiceError(
                "SESSION_NOT_FOUND",
                404,
                "요청한 분석 세션을 찾을 수 없습니다.",
            )

    def load_feedback(self, session_id: str) -> dict[str, Any]:
        self._require_registered_session(session_id)
        path = self._feedback_path(session_id)
        if not path.is_file():
            raise VisionApiServiceError(
                "RESULT_NOT_READY",
                409,
                "요청한 세션의 Vision MVP 결과가 아직 준비되지 않았습니다.",
            )
        try:
            payload = load_strict_json(path)
        except PilotVideoIntakeError as exc:
            raise VisionApiServiceError(
                "FEEDBACK_BUILD_FAILED",
                500,
                "Vision MVP 피드백 결과를 읽지 못했습니다.",
            ) from exc
        return validate_feedback_contract(
            payload,
            expected_session_id=session_id,
        )

    def _participant_id(self, session_id: str) -> str:
        manifest_path = (
            self.output_root
            / "pilot_manual_review"
            / session_id
            / "annotation_ready_manifest.json"
        )
        try:
            manifest = load_strict_json(manifest_path)
        except PilotVideoIntakeError as exc:
            raise VisionApiServiceError(
                "INPUT_ARTIFACTS_MISSING",
                503,
                "Stage 22 입력 산출물을 사용할 수 없습니다.",
            ) from exc
        participant_id = manifest.get("participant_id")
        if not isinstance(participant_id, str) or not PARTICIPANT_PATTERN.fullmatch(
            participant_id
        ):
            raise VisionApiServiceError(
                "INPUT_ARTIFACTS_MISSING",
                503,
                "Stage 22 입력 참조가 유효하지 않습니다.",
            )
        return participant_id

    def rebuild_feedback(self, session_id: str) -> dict[str, Any]:
        self._require_registered_session(session_id)
        participant_id = self._participant_id(session_id)
        try:
            inputs = load_single_session_inputs(
                self.vision_server_root,
                participant_id=participant_id,
                session_id=session_id,
            )
            package = build_single_session_mvp_feedback(inputs)
            contract = validate_feedback_contract(
                package["api_contract"],
                expected_session_id=session_id,
            )
            atomic_write_json(self._feedback_path(session_id), contract)
        except VisionApiServiceError:
            raise
        except (KeyError, PilotVideoIntakeError, SingleSessionMvpError) as exc:
            raise VisionApiServiceError(
                "FEEDBACK_BUILD_FAILED",
                500,
                "Stage 22 Vision MVP 피드백을 재생성하지 못했습니다.",
            ) from exc
        return contract

    def check_readiness(self) -> None:
        try:
            self.output_root.mkdir(parents=True, exist_ok=True)
            self.storage.ensure_accessible()
            if not callable(load_single_session_inputs):
                raise RuntimeError("Stage 22 resolver unavailable")
            json.dumps(
                {"analysisMode": ANALYSIS_MODE, "scoringAvailable": False},
                allow_nan=False,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise VisionApiServiceError(
                "DEPENDENCY_UNAVAILABLE",
                503,
                "Vision API 저장소 또는 Stage 22 resolver를 사용할 수 없습니다.",
            ) from exc

    def _find_reusable(
        self,
        session_id: str,
        analysis_mode: str,
        force_rebuild: bool,
    ) -> dict[str, Any] | None:
        candidates = [
            record
            for record in self.storage.list_records()
            if record["sessionId"] == session_id
            and record["analysisMode"] == analysis_mode
            and record["forceRebuild"] is force_rebuild
        ]
        candidates.sort(key=lambda item: (item["createdAt"], item["jobId"]))
        running = [
            item for item in candidates if item["status"] == "RUNNING"
        ]
        if running:
            return running[-1]
        if not force_rebuild:
            succeeded = [
                item
                for item in candidates
                if item["status"] in SUCCESS_JOB_STATUSES
            ]
            if succeeded:
                return succeeded[-1]
        return None

    def create_job(
        self,
        *,
        session_id: str,
        analysis_mode: str,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        self._require_registered_session(session_id)
        if analysis_mode != ANALYSIS_MODE:
            raise VisionApiServiceError(
                "UNSUPPORTED_ANALYSIS_MODE",
                422,
                "요청한 Vision 분석 모드는 지원되지 않습니다.",
            )
        reusable = self._find_reusable(
            session_id,
            analysis_mode,
            force_rebuild,
        )
        if reusable is not None:
            return self.public_job(reusable)
        job_id = validate_job_id(self.job_id_generator())
        record = {
            "jobId": job_id,
            "sessionId": session_id,
            "analysisMode": analysis_mode,
            "forceRebuild": force_rebuild,
            "status": "QUEUED",
            "createdAt": _iso_timestamp(self.clock),
            "startedAt": None,
            "completedAt": None,
            "resultAvailable": False,
            "warnings": [],
            "error": None,
        }
        self.storage.save_new(record)
        record["status"] = "RUNNING"
        record["startedAt"] = _iso_timestamp(self.clock)
        self.storage.save(record)
        try:
            feedback = (
                self.rebuild_feedback(session_id)
                if force_rebuild
                else self.load_feedback(session_id)
            )
            record["status"] = STAGE22_STATUS_TO_JOB_STATUS[
                feedback["status"]
            ]
            record["resultAvailable"] = (
                record["status"] in SUCCESS_JOB_STATUSES
            )
            record["warnings"] = _warning_contract(
                feedback.get("warnings")
            )
            if record["status"] == "FAILED":
                record["error"] = {
                    "code": "FEEDBACK_BUILD_FAILED",
                    "message": "Vision MVP 결과를 제공할 수 없습니다.",
                }
        except VisionApiServiceError as exc:
            record["status"] = "FAILED"
            record["error"] = {
                "code": exc.code,
                "message": exc.message,
            }
            record["completedAt"] = _iso_timestamp(self.clock)
            self.storage.save(record)
            raise
        except Exception as exc:
            record["status"] = "FAILED"
            record["error"] = {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Vision Job 처리 중 오류가 발생했습니다.",
            }
            record["completedAt"] = _iso_timestamp(self.clock)
            self.storage.save(record)
            raise VisionApiServiceError(
                "INTERNAL_SERVER_ERROR",
                500,
                "Vision Job 처리 중 오류가 발생했습니다.",
            ) from exc
        record["completedAt"] = _iso_timestamp(self.clock)
        self.storage.save(record)
        return self.public_job(record)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.public_job(self.storage.load(job_id))

    @staticmethod
    def public_job(record: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: deepcopy(record[key])
            for key in (
                "jobId",
                "sessionId",
                "analysisMode",
                "status",
                "createdAt",
                "startedAt",
                "completedAt",
                "resultAvailable",
                "warnings",
                "error",
            )
        }
        _walk_response(public)
        ensure_finite(public)
        return public
