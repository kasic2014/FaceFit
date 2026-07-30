"""Stage 14 metadata-only pilot collection operations models."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.vision.data_collection_models import (
    PARTICIPANT_RE,
    SHA256_RE,
    AnswerSample,
    _required_id,
)
from app.vision.interval_models import AnalysisInterval, IntervalType


class PilotSessionStatus(str, Enum):
    PLANNED = "PLANNED"
    READY = "READY"
    RECORDING = "RECORDING"
    RECORDED = "RECORDED"
    VALIDATING = "VALIDATING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ANNOTATION_READY = "ANNOTATION_READY"
    EXCLUDED = "EXCLUDED"
    WITHDRAWN = "WITHDRAWN"
    FAILED = "FAILED"


class QualityCheckType(str, Enum):
    VIDEO_FILE_EXISTS = "VIDEO_FILE_EXISTS"
    VIDEO_HASH_VALID = "VIDEO_HASH_VALID"
    VIDEO_DECODABLE = "VIDEO_DECODABLE"
    DURATION_VALID = "DURATION_VALID"
    RESOLUTION_VALID = "RESOLUTION_VALID"
    SOURCE_FPS_VALID = "SOURCE_FPS_VALID"
    FACE_AVAILABLE = "FACE_AVAILABLE"
    BOTH_SHOULDERS_AVAILABLE = "BOTH_SHOULDERS_AVAILABLE"
    SINGLE_TARGET_VALID = "SINGLE_TARGET_VALID"
    BASELINE_AVAILABLE = "BASELINE_AVAILABLE"
    ANSWER_INTERVALS_VALID = "ANSWER_INTERVALS_VALID"


class QualityCheckStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    NOT_CHECKED = "NOT_CHECKED"


class PilotExclusionReason(str, Enum):
    CONSENT_NOT_GRANTED = "CONSENT_NOT_GRANTED"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    FILE_MISSING = "FILE_MISSING"
    HASH_MISMATCH = "HASH_MISMATCH"
    VIDEO_DECODE_FAILED = "VIDEO_DECODE_FAILED"
    INVALID_DURATION = "INVALID_DURATION"
    INVALID_RESOLUTION = "INVALID_RESOLUTION"
    INVALID_FPS = "INVALID_FPS"
    FACE_NOT_VISIBLE = "FACE_NOT_VISIBLE"
    BOTH_SHOULDERS_NOT_VISIBLE = "BOTH_SHOULDERS_NOT_VISIBLE"
    MULTIPLE_PERSON_DETECTED = "MULTIPLE_PERSON_DETECTED"
    BASELINE_FAILED = "BASELINE_FAILED"
    ANSWER_INTERVAL_INVALID = "ANSWER_INTERVAL_INVALID"
    CAMERA_MOVED = "CAMERA_MOVED"
    SEVERE_OCCLUSION = "SEVERE_OCCLUSION"
    MANUAL_REVIEW_REJECTED = "MANUAL_REVIEW_REJECTED"
    OTHER = "OTHER"


class WithdrawalDisposition(str, Enum):
    DELETION_PENDING = "DELETION_PENDING"
    QUARANTINED = "QUARANTINED"
    DELETED_CONFIRMED = "DELETED_CONFIRMED"


class ReleaseCandidateStatus(str, Enum):
    DRAFT = "DRAFT"
    PILOT_CANDIDATE = "PILOT_CANDIDATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


def _enum(value: str, kind: type[Enum], name: str) -> None:
    if value not in {item.value for item in kind}:
        raise ValueError(f"Invalid {name}: {value}")


def _timestamp(value: str, name: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ValueError(f"{name} must be fixture UTC ISO-8601")


@dataclass(frozen=True)
class PilotStudyProtocol:
    pilot_protocol_id: str
    data_collection_protocol_id: str
    version: str
    status: str
    actual_collection_authorized: bool

    def __post_init__(self) -> None:
        _required_id(self.pilot_protocol_id, "pilot_protocol_id")
        _required_id(
            self.data_collection_protocol_id, "data_collection_protocol_id"
        )
        if self.status not in {"DRAFT", "REVIEW_REQUIRED", "TEST_FIXTURE"}:
            raise ValueError("pilot protocol is not in a non-operational status")
        if self.actual_collection_authorized:
            raise ValueError("Stage 14 cannot authorize actual collection")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PilotParticipantEnrollment:
    enrollment_id: str
    participant_id: str
    consent_reference_id: str
    status: str

    def __post_init__(self) -> None:
        _required_id(self.enrollment_id, "enrollment_id")
        _required_id(self.consent_reference_id, "consent_reference_id")
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("participant_id must be pseudonymous")
        if self.status not in {
            "ENROLLED", "NOT_ELIGIBLE", "WITHDRAWN", "TEST_FIXTURE"
        }:
            raise ValueError("invalid enrollment status")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecordingFileRecord:
    file_reference: str
    sha256: str
    size_bytes: int
    created_at: str
    participant_id: str
    session_id: str
    answer_id: str
    consent_reference_id: str
    storage_status: str

    def __post_init__(self) -> None:
        if not isinstance(self.file_reference, str) or not self.file_reference:
            raise ValueError("file_reference is required")
        if not SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be lowercase SHA-256")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes <= 0
        ):
            raise ValueError("size_bytes must be positive")
        _timestamp(self.created_at, "created_at")
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("invalid participant_id")
        for value, name in (
            (self.session_id, "session_id"),
            (self.answer_id, "answer_id"),
            (self.consent_reference_id, "consent_reference_id"),
        ):
            _required_id(value, name)
        if self.storage_status not in {
            "INCOMING", "VALIDATED", "EXCLUDED", "WITHDRAWAL_HOLD"
        }:
            raise ValueError("invalid storage_status")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PilotSessionRun:
    pilot_session_id: str
    participant_id: str
    consent_reference_id: str
    checklist_id: str
    status: str
    duration_ms: int
    baseline_start_timestamp_ms: int
    baseline_end_timestamp_ms: int
    exclusion_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.pilot_session_id, "pilot_session_id"),
            (self.consent_reference_id, "consent_reference_id"),
            (self.checklist_id, "checklist_id"),
        ):
            _required_id(value, name)
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("invalid participant_id")
        _enum(self.status, PilotSessionStatus, "status")
        if (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or self.duration_ms <= 0
        ):
            raise ValueError("duration_ms must be positive")
        self.baseline_interval()
        if self.baseline_end_timestamp_ms > self.duration_ms:
            raise ValueError("baseline exceeds session duration")
        for reason in self.exclusion_reasons:
            _enum(reason, PilotExclusionReason, "exclusion_reason")
        if self.status in {"EXCLUDED", "FAILED"} and not self.exclusion_reasons:
            raise ValueError("excluded/failed session requires reason")

    def baseline_interval(self) -> AnalysisInterval:
        return AnalysisInterval(
            interval_id=f"{self.pilot_session_id}_BASELINE",
            start_timestamp_ms=self.baseline_start_timestamp_ms,
            end_timestamp_ms=self.baseline_end_timestamp_ms,
            interval_type=IntervalType.BASELINE.value,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["exclusion_reasons"] = list(self.exclusion_reasons)
        return value


@dataclass(frozen=True)
class PilotAnswerRecord:
    answer_id: str
    pilot_session_id: str
    question_id: str
    start_timestamp_ms: int
    end_timestamp_ms: int
    target_id: str

    def __post_init__(self) -> None:
        self.answer_sample()

    def answer_sample(self) -> AnswerSample:
        return AnswerSample(
            self.answer_id,
            self.pilot_session_id,
            self.question_id,
            self.start_timestamp_ms,
            self.end_timestamp_ms,
            self.target_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CollectionQualityCheck:
    check_id: str
    pilot_session_id: str
    check_type: str
    status: str
    reason_code: str | None

    def __post_init__(self) -> None:
        _required_id(self.check_id, "check_id")
        _required_id(self.pilot_session_id, "pilot_session_id")
        _enum(self.check_type, QualityCheckType, "check_type")
        _enum(self.status, QualityCheckStatus, "status")
        if self.reason_code is not None:
            _enum(self.reason_code, PilotExclusionReason, "reason_code")
        if self.status == "FAILED" and self.reason_code is None:
            raise ValueError("failed quality check requires reason_code")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WithdrawalRequest:
    withdrawal_request_id: str
    participant_id: str
    consent_reference_id: str
    requested_at: str
    disposition: str

    def __post_init__(self) -> None:
        _required_id(
            self.withdrawal_request_id, "withdrawal_request_id"
        )
        _required_id(self.consent_reference_id, "consent_reference_id")
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("invalid participant_id")
        _timestamp(self.requested_at, "requested_at")
        _enum(self.disposition, WithdrawalDisposition, "disposition")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DatasetReleaseCandidate:
    release_candidate_id: str
    manifest_id: str
    participant_id: str
    pilot_session_id: str
    answer_ids: tuple[str, ...]
    status: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.release_candidate_id, "release_candidate_id"),
            (self.manifest_id, "manifest_id"),
            (self.pilot_session_id, "pilot_session_id"),
        ):
            _required_id(value, name)
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("invalid participant_id")
        if not self.answer_ids or len(set(self.answer_ids)) != len(
            self.answer_ids
        ):
            raise ValueError("answer_ids must be unique and non-empty")
        _enum(self.status, ReleaseCandidateStatus, "status")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["answer_ids"] = list(self.answer_ids)
        return value
