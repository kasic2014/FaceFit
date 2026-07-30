"""Stage 13 metadata-only data collection contracts.

These models intentionally contain no direct identifiers, media payloads,
behavioral scores, or production decisions.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.vision.interval_models import AnalysisInterval, IntervalType


ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PARTICIPANT_RE = re.compile(r"^PTC_[0-9]{6}$")

ALLOWED_BODY_REGIONS = frozenset(
    {
        "FACE",
        "NOSE",
        "LEFT_EAR",
        "RIGHT_EAR",
        "LEFT_SHOULDER",
        "RIGHT_SHOULDER",
    }
)
REQUIRED_FRAME_REGIONS = frozenset(
    {"FACE", "LEFT_SHOULDER", "RIGHT_SHOULDER"}
)


class ProtocolStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    TEST_FIXTURE = "TEST_FIXTURE"


class ParticipantStatus(str, Enum):
    TEST_FIXTURE = "TEST_FIXTURE"
    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"
    WITHDRAWN = "WITHDRAWN"


class RecordingSessionStatus(str, Enum):
    PLANNED = "PLANNED"
    RECORDING = "RECORDING"
    RECORDED = "RECORDED"
    PROCESSING = "PROCESSING"
    ANNOTATION_READY = "ANNOTATION_READY"
    EXCLUDED = "EXCLUDED"
    WITHDRAWN = "WITHDRAWN"
    COMPLETED = "COMPLETED"


class ExclusionReason(str, Enum):
    CONSENT_NOT_GRANTED = "CONSENT_NOT_GRANTED"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    VIDEO_FILE_MISSING = "VIDEO_FILE_MISSING"
    VIDEO_HASH_MISMATCH = "VIDEO_HASH_MISMATCH"
    VIDEO_DECODE_FAILED = "VIDEO_DECODE_FAILED"
    FACE_NOT_VISIBLE = "FACE_NOT_VISIBLE"
    LEFT_SHOULDER_NOT_VISIBLE = "LEFT_SHOULDER_NOT_VISIBLE"
    RIGHT_SHOULDER_NOT_VISIBLE = "RIGHT_SHOULDER_NOT_VISIBLE"
    BOTH_SHOULDERS_NOT_VISIBLE = "BOTH_SHOULDERS_NOT_VISIBLE"
    MULTIPLE_PERSON_DETECTED = "MULTIPLE_PERSON_DETECTED"
    CAMERA_MOVED = "CAMERA_MOVED"
    CAMERA_ORIENTATION_CHANGED = "CAMERA_ORIENTATION_CHANGED"
    SEVERE_OCCLUSION = "SEVERE_OCCLUSION"
    ANSWER_INTERVAL_MISSING = "ANSWER_INTERVAL_MISSING"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    DUPLICATE_INTERVAL = "DUPLICATE_INTERVAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    TARGET_TRACKING_FAILED = "TARGET_TRACKING_FAILED"
    BASELINE_FAILED = "BASELINE_FAILED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    OTHER = "OTHER"


def _required_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{name} must be a coded identifier")


def _enum(value: str, enum_type: type[Enum], name: str) -> None:
    if value not in {item.value for item in enum_type}:
        raise ValueError(f"Invalid {name}: {value}")


def _positive_finite(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class DataCollectionProtocol:
    protocol_id: str
    version: str
    status: str
    single_person_only: bool
    fixed_camera_required: bool
    baseline_required: bool
    answer_timestamps_required: bool
    body_regions: tuple[str, ...]
    prohibited_body_regions: tuple[str, ...]
    purpose: str

    def __post_init__(self) -> None:
        _required_id(self.protocol_id, "protocol_id")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.version):
            raise ValueError("version must use semantic version format")
        _enum(self.status, ProtocolStatus, "status")
        if not all(
            (
                self.single_person_only,
                self.fixed_camera_required,
                self.baseline_required,
                self.answer_timestamps_required,
            )
        ):
            raise ValueError("protocol capture safety requirements must be true")
        regions = set(self.body_regions)
        if not REQUIRED_FRAME_REGIONS.issubset(regions):
            raise ValueError("face and both shoulders must be in frame")
        if not regions.issubset(ALLOWED_BODY_REGIONS):
            raise ValueError("body_regions exceeds the Face-Fit scope")
        if regions.intersection(self.prohibited_body_regions):
            raise ValueError("allowed and prohibited body regions overlap")
        if not self.purpose.strip():
            raise ValueError("purpose must not be empty")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["body_regions"] = list(self.body_regions)
        value["prohibited_body_regions"] = list(self.prohibited_body_regions)
        return value


@dataclass(frozen=True)
class ResearchParticipant:
    participant_id: str
    status: str
    consent_reference_id: str

    def __post_init__(self) -> None:
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("participant_id must be pseudonymous PTC_######")
        _enum(self.status, ParticipantStatus, "status")
        _required_id(self.consent_reference_id, "consent_reference_id")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecordingEnvironment:
    environment_id: str
    width_px: int
    height_px: int
    source_fps: float
    analysis_fps: float
    fixed_camera: bool
    mirror_preview: bool
    stored_video_mirrored: bool
    face_and_shoulders_in_frame: bool

    def __post_init__(self) -> None:
        _required_id(self.environment_id, "environment_id")
        for value, name in (
            (self.width_px, "width_px"),
            (self.height_px, "height_px"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        _positive_finite(self.source_fps, "source_fps")
        _positive_finite(self.analysis_fps, "analysis_fps")
        if self.analysis_fps > self.source_fps:
            raise ValueError("analysis_fps cannot exceed source_fps")
        if not self.fixed_camera or not self.face_and_shoulders_in_frame:
            raise ValueError("fixed camera and required framing are mandatory")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecordingSession:
    session_id: str
    participant_id: str
    protocol_id: str
    consent_reference_id: str
    environment_id: str
    status: str
    duration_ms: int
    baseline_start_timestamp_ms: int
    baseline_end_timestamp_ms: int
    video_sha256: str
    exclusion_reason: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.session_id, "session_id"),
            (self.protocol_id, "protocol_id"),
            (self.consent_reference_id, "consent_reference_id"),
            (self.environment_id, "environment_id"),
        ):
            _required_id(value, name)
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("invalid participant_id")
        _enum(self.status, RecordingSessionStatus, "status")
        if (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or self.duration_ms <= 0
        ):
            raise ValueError("duration_ms must be a positive integer")
        if not (
            0 <= self.baseline_start_timestamp_ms
            < self.baseline_end_timestamp_ms
            <= self.duration_ms
        ):
            raise ValueError("baseline interval is outside the session")
        if not SHA256_RE.fullmatch(self.video_sha256):
            raise ValueError("video_sha256 must be lowercase SHA-256")
        if self.exclusion_reason is not None:
            _enum(self.exclusion_reason, ExclusionReason, "exclusion_reason")
        if self.status in {
            RecordingSessionStatus.EXCLUDED.value,
            RecordingSessionStatus.WITHDRAWN.value,
        } and self.exclusion_reason is None:
            raise ValueError("excluded/withdrawn sessions require a reason")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnswerSample:
    answer_id: str
    session_id: str
    question_id: str
    start_timestamp_ms: int
    end_timestamp_ms: int
    target_id: str
    exclusion_reason: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.answer_id, "answer_id"),
            (self.session_id, "session_id"),
            (self.question_id, "question_id"),
            (self.target_id, "target_id"),
        ):
            _required_id(value, name)
        # Reuse the authoritative Stage 10 interval boundary validation.
        self.as_analysis_interval()
        if self.exclusion_reason is not None:
            _enum(self.exclusion_reason, ExclusionReason, "exclusion_reason")

    @property
    def duration_ms(self) -> int:
        return self.end_timestamp_ms - self.start_timestamp_ms

    def as_analysis_interval(self) -> AnalysisInterval:
        return AnalysisInterval(
            interval_id=self.answer_id,
            start_timestamp_ms=self.start_timestamp_ms,
            end_timestamp_ms=self.end_timestamp_ms,
            interval_type=IntervalType.ANSWER.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
