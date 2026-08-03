"""Stage 20 multi-session pilot Annotation batch governance.

The batch registry references existing, validated artifacts read-only. It does
not create participants, videos, Annotation Events, thresholds, agreement
values, scores, or frozen datasets.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.vision.annotation_policy_approval import (
    AGREEMENT_POLICY_STATUS,
    APPROVED_STRATEGY,
    TIE_BREAKER_STATUS,
)
from app.vision.annotation_policy_revision import (
    MATCHING_POLICY_ID,
    MATCHING_POLICY_VERSION,
    SCOPE,
)
from app.vision.pilot_video_intake import (
    ensure_finite,
    load_strict_json,
    sha256_file,
    write_strict_json,
)


SCHEMA_VERSION = "1.0.0"
STAGE = 20
BATCH_ID = "PILOT_ANNOTATION_BATCH_001"
BATCH_VERSION = "0.1.0"
BATCH_PURPOSE = "THRESHOLD_EVIDENCE"
BATCH_STATUS = "EVIDENCE_INSUFFICIENT"
THRESHOLD_READINESS = "EVIDENCE_INSUFFICIENT"
FINAL_STATUS = "threshold_evidence_batch_insufficient"
COLLECTION_STATUS = "awaiting_additional_pilot_sessions"

PURPOSES = frozenset(
    {"PILOT_COLLECTION", "ANNOTATION_AGREEMENT", "THRESHOLD_EVIDENCE"}
)
BATCH_STATUSES = frozenset(
    {
        "DRAFT",
        "COLLECTING",
        "ANNOTATING",
        "AGREEMENT_PENDING",
        "EVIDENCE_INSUFFICIENT",
        "EVIDENCE_READY_FOR_REVIEW",
        "FROZEN",
        "RETIRED",
    }
)
SPLITS = frozenset(
    {"DEVELOPMENT", "CALIBRATION", "VALIDATION", "HOLDOUT", "EXCLUDED"}
)
RATER_ROLES = frozenset({"RATER_A", "RATER_B", "ADJUDICATOR"})
IDENTITY_CONTEXTS = frozenset(
    {"INTER_RATER", "INTRA_RATER_REPEAT", "RATER_IDENTITY_UNVERIFIED"}
)
ASSIGNMENT_STATUSES = frozenset(
    {"NOT_ASSIGNED", "ASSIGNED", "IN_PROGRESS", "COMPLETED"}
)
DATA_CONTEXTS = frozenset({"REAL_PILOT", "FIXTURE_ONLY"})
BLOCKING_REASONS = (
    "MINIMUM_PARTICIPANT_COUNT_NOT_APPROVED",
    "MINIMUM_SESSION_COUNT_NOT_APPROVED",
    "MINIMUM_EVENT_COUNT_NOT_APPROVED",
    "AGREEMENT_THRESHOLDS_NOT_APPROVED",
    "RATER_IDENTITY_UNVERIFIED",
)
PARTICIPANT_RE = re.compile(r"^PTC_\d{6}$")
SESSION_RE = re.compile(r"^SES_\d{6}$")
ANSWER_RE = re.compile(r"^ANS_\d{6}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
ASSIGNMENT_FIELDS = frozenset(
    {
        "assignment_id",
        "participant_id",
        "session_id",
        "rater_role",
        "rater_identity_context",
        "assignment_status",
        "assigned_at",
        "completed_at",
        "annotation_file_reference",
        "annotation_sha256",
        "blind_flags_valid",
    }
)
SESSION_FIELDS = frozenset(
    {
        "participant_id",
        "session_id",
        "split_name",
        "consent_reference_id",
        "video_sha256",
        "annotation_ready_manifest_reference",
        "answer_ids",
        "rater_a_assignment",
        "rater_b_assignment",
        "rater_a_status",
        "rater_b_status",
        "agreement_status",
        "adjudication_status",
        "eligible_for_threshold_evidence",
        "exclusion_reasons",
        "data_context",
    }
)
BATCH_FIELDS = frozenset(
    {
        "batch_id",
        "batch_version",
        "batch_status",
        "purpose",
        "scope",
        "operational",
        "created_at",
        "participant_count",
        "session_count",
        "answer_count",
        "split_summary",
        "sessions",
        "rater_assignment_summary",
        "annotation_completion_summary",
        "agreement_readiness_summary",
        "threshold_evidence_readiness",
        "blocking_reasons",
    }
)
OUTPUT_NAMES = (
    "pilot_batch_registry.json",
    "pilot_batch_sessions.json",
    "participant_split_validation.json",
    "rater_assignment_registry.json",
    "threshold_evidence_readiness.json",
    "pilot_batch_session.template.json",
    "batch_status.json",
    "validation_report.json",
    "validation_report.md",
)


class PilotBatchError(ValueError):
    """Raised when a Stage 20 batch contract is violated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _fail(message: str) -> None:
    raise PilotBatchError("pilot_batch_validation_failed", message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _exact_fields(
    value: dict[str, Any], expected: frozenset[str], context: str
) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        _fail(f"{context} fields must be exact; missing={missing}, extra={extra}")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be non-empty text")
    return value.strip()


def _optional_time(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_time(value, field)


def _required_time(value: Any, field: str) -> str:
    result = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PilotBatchError(
            "pilot_batch_validation_failed", f"{field} must be ISO 8601"
        ) from exc
    if parsed.utcoffset() is None:
        _fail(f"{field} must include timezone")
    return result


def _required_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail(f"{field} must be lowercase SHA-256")
    return value


@dataclass(frozen=True)
class RaterAssignment:
    assignment_id: str
    participant_id: str
    session_id: str
    rater_role: str
    rater_identity_context: str
    assignment_status: str
    assigned_at: str | None
    completed_at: str | None
    annotation_file_reference: str | None
    annotation_sha256: str | None
    blind_flags_valid: bool | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RaterAssignment":
        if not isinstance(value, dict):
            _fail("rater assignment must be an object")
        _exact_fields(value, ASSIGNMENT_FIELDS, "rater assignment")
        ensure_finite(value)
        assignment_id = _required_text(value["assignment_id"], "assignment_id")
        participant_id = _required_text(value["participant_id"], "participant_id")
        session_id = _required_text(value["session_id"], "session_id")
        _require(bool(PARTICIPANT_RE.fullmatch(participant_id)), "invalid participant_id")
        _require(bool(SESSION_RE.fullmatch(session_id)), "invalid session_id")
        _require(value["rater_role"] in RATER_ROLES, "invalid rater_role")
        _require(
            value["rater_identity_context"] in IDENTITY_CONTEXTS,
            "invalid rater_identity_context",
        )
        _require(
            value["assignment_status"] in ASSIGNMENT_STATUSES,
            "invalid assignment_status",
        )
        assigned_at = _optional_time(value["assigned_at"], "assigned_at")
        completed_at = _optional_time(value["completed_at"], "completed_at")
        annotation_reference = value["annotation_file_reference"]
        annotation_sha = value["annotation_sha256"]
        blind_valid = value["blind_flags_valid"]
        if value["assignment_status"] == "COMPLETED":
            _require(completed_at is not None, "completed assignment needs completed_at")
            annotation_reference = _required_text(
                annotation_reference, "annotation_file_reference"
            )
            annotation_sha = _required_sha(annotation_sha, "annotation_sha256")
            _require(blind_valid is True, "completed assignment needs valid blind flags")
        else:
            _require(
                annotation_reference is None and annotation_sha is None,
                "incomplete assignment cannot reference submitted Annotation",
            )
            _require(
                blind_valid in {None, False},
                "incomplete assignment cannot claim valid blind flags",
            )
        return cls(
            assignment_id,
            participant_id,
            session_id,
            value["rater_role"],
            value["rater_identity_context"],
            value["assignment_status"],
            assigned_at,
            completed_at,
            annotation_reference,
            annotation_sha,
            blind_valid,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchSession:
    participant_id: str
    session_id: str
    split_name: str
    consent_reference_id: str
    video_sha256: str
    annotation_ready_manifest_reference: str
    answer_ids: tuple[str, ...]
    rater_a_assignment: str
    rater_b_assignment: str
    rater_a_status: str
    rater_b_status: str
    agreement_status: str
    adjudication_status: str
    eligible_for_threshold_evidence: bool
    exclusion_reasons: tuple[str, ...]
    data_context: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BatchSession":
        if not isinstance(value, dict):
            _fail("batch session must be an object")
        _exact_fields(value, SESSION_FIELDS, "batch session")
        ensure_finite(value)
        participant_id = _required_text(value["participant_id"], "participant_id")
        session_id = _required_text(value["session_id"], "session_id")
        _require(bool(PARTICIPANT_RE.fullmatch(participant_id)), "invalid participant_id")
        _require(bool(SESSION_RE.fullmatch(session_id)), "invalid session_id")
        _require(value["split_name"] in SPLITS, "invalid split_name")
        _required_text(value["consent_reference_id"], "consent_reference_id")
        _required_sha(value["video_sha256"], "video_sha256")
        _required_text(
            value["annotation_ready_manifest_reference"],
            "annotation_ready_manifest_reference",
        )
        answer_ids = value["answer_ids"]
        _require(
            isinstance(answer_ids, list)
            and answer_ids
            and all(
                isinstance(answer_id, str) and ANSWER_RE.fullmatch(answer_id)
                for answer_id in answer_ids
            ),
            "answer_ids must contain pseudonymous Answer IDs",
        )
        _require(len(answer_ids) == len(set(answer_ids)), "answer_ids must be unique")
        for field in (
            "rater_a_assignment",
            "rater_b_assignment",
            "rater_a_status",
            "rater_b_status",
            "agreement_status",
            "adjudication_status",
        ):
            _required_text(value[field], field)
        _require(
            value["rater_a_assignment"] != value["rater_b_assignment"],
            "Rater assignments must be isolated",
        )
        _require(
            isinstance(value["eligible_for_threshold_evidence"], bool),
            "eligible_for_threshold_evidence must be boolean",
        )
        reasons = value["exclusion_reasons"]
        _require(
            isinstance(reasons, list)
            and all(isinstance(reason, str) and reason for reason in reasons),
            "exclusion_reasons must be a text array",
        )
        _require(
            not value["eligible_for_threshold_evidence"] or not reasons,
            "eligible session cannot have exclusion reasons",
        )
        _require(value["data_context"] in DATA_CONTEXTS, "invalid data_context")
        return cls(
            participant_id,
            session_id,
            value["split_name"],
            value["consent_reference_id"],
            value["video_sha256"],
            value["annotation_ready_manifest_reference"],
            tuple(answer_ids),
            value["rater_a_assignment"],
            value["rater_b_assignment"],
            value["rater_a_status"],
            value["rater_b_status"],
            value["agreement_status"],
            value["adjudication_status"],
            value["eligible_for_threshold_evidence"],
            tuple(reasons),
            value["data_context"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["answer_ids"] = list(self.answer_ids)
        value["exclusion_reasons"] = list(self.exclusion_reasons)
        return value


@dataclass(frozen=True)
class BatchRegistry:
    batch_id: str
    batch_version: str
    batch_status: str
    purpose: str
    scope: str
    operational: bool
    created_at: str
    participant_count: int
    session_count: int
    answer_count: int
    split_summary: dict[str, int]
    sessions: tuple[dict[str, str], ...]
    rater_assignment_summary: dict[str, Any]
    annotation_completion_summary: dict[str, Any]
    agreement_readiness_summary: dict[str, Any]
    threshold_evidence_readiness: str
    blocking_reasons: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BatchRegistry":
        if not isinstance(value, dict):
            _fail("batch registry must be an object")
        _exact_fields(value, BATCH_FIELDS, "batch registry")
        ensure_finite(value)
        batch_id = _required_text(value["batch_id"], "batch_id")
        version = _required_text(value["batch_version"], "batch_version")
        _require(bool(SEMVER_RE.fullmatch(version)), "batch_version must be SemVer")
        _require(value["batch_status"] in BATCH_STATUSES, "invalid batch_status")
        _require(value["purpose"] in PURPOSES, "invalid purpose")
        _require(value["scope"] == SCOPE, "invalid scope")
        _require(isinstance(value["operational"], bool), "operational must be boolean")
        created_at = _required_time(value["created_at"], "created_at")
        for field in ("participant_count", "session_count", "answer_count"):
            _require(
                isinstance(value[field], int)
                and not isinstance(value[field], bool)
                and value[field] >= 0,
                f"{field} must be a non-negative integer",
            )
        split_summary = value["split_summary"]
        _require(
            isinstance(split_summary, dict)
            and set(split_summary) == SPLITS
            and all(
                isinstance(count, int) and not isinstance(count, bool) and count >= 0
                for count in split_summary.values()
            ),
            "split_summary must contain every supported split",
        )
        _require(
            sum(split_summary.values()) == value["session_count"],
            "split summary must equal session_count",
        )
        sessions = value["sessions"]
        _require(
            isinstance(sessions, list)
            and len(sessions) == value["session_count"]
            and all(
                isinstance(item, dict)
                and set(item) == {"participant_id", "session_id"}
                for item in sessions
            ),
            "sessions summary is invalid",
        )
        for field in (
            "rater_assignment_summary",
            "annotation_completion_summary",
            "agreement_readiness_summary",
        ):
            _require(isinstance(value[field], dict), f"{field} must be an object")
        _require(
            value["threshold_evidence_readiness"]
            in {"EVIDENCE_INSUFFICIENT", "EVIDENCE_READY_FOR_REVIEW"},
            "invalid threshold evidence readiness",
        )
        reasons = value["blocking_reasons"]
        _require(
            isinstance(reasons, list)
            and all(isinstance(reason, str) and reason for reason in reasons),
            "blocking_reasons must be a text array",
        )
        if value["threshold_evidence_readiness"] == "EVIDENCE_INSUFFICIENT":
            _require(bool(reasons), "insufficient evidence needs blocking reasons")
        return cls(
            batch_id,
            version,
            value["batch_status"],
            value["purpose"],
            value["scope"],
            value["operational"],
            created_at,
            value["participant_count"],
            value["session_count"],
            value["answer_count"],
            dict(split_summary),
            tuple(dict(item) for item in sessions),
            dict(value["rater_assignment_summary"]),
            dict(value["annotation_completion_summary"]),
            dict(value["agreement_readiness_summary"]),
            value["threshold_evidence_readiness"],
            tuple(reasons),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sessions"] = [dict(item) for item in self.sessions]
        value["blocking_reasons"] = list(self.blocking_reasons)
        return value


@dataclass(frozen=True)
class CurrentSessionSources:
    consent: Path
    metadata: Path
    consent_validation: Path
    video_metadata: Path
    interval_validation: Path
    annotation_ready_manifest: Path
    split_assignment: Path
    annotation_package_manifest: Path
    stage19_input_validation: Path
    stage19_agreement_summary: Path
    governance_status: Path
    approved_snapshot: Path
    rater_a_annotation: Path
    rater_b_annotation: Path

    @classmethod
    def from_vision_root(cls, vision_root: str | Path) -> "CurrentSessionSources":
        root = Path(vision_root)
        intake = root / "data" / "output" / "pilot_video_intake_validation" / "SES_000001"
        stage17 = root / "data" / "output" / "pilot_manual_review" / "SES_000001"
        annotation = root / "data" / "output" / "pilot_annotation" / "SES_000001"
        agreement = (
            root / "data" / "output" / "pilot_annotation_agreement" / "SES_000001"
        )
        policy = (
            root
            / "data"
            / "output"
            / "pilot_annotation_agreement_policy"
            / "SES_000001"
            / "revision_0_2_0"
        )
        incoming = root / "data" / "pilot" / "incoming"
        return cls(
            incoming / "PTC_000001_SES_000001.consent.json",
            incoming / "PTC_000001_SES_000001.metadata.json",
            intake / "consent_validation.json",
            intake / "video_metadata.json",
            intake / "interval_validation.json",
            stage17 / "annotation_ready_manifest.json",
            stage17 / "development_split_assignment.json",
            annotation / "annotation_package_manifest.json",
            agreement / "input_validation.json",
            agreement / "agreement_summary.json",
            policy / "agreement_policy_governance_status.json",
            policy / "approved_tie_breaker_policy_snapshot.json",
            annotation / "rater_a" / "annotation_events.json",
            annotation / "rater_b" / "annotation_events.json",
        )

    def named_paths(self) -> dict[str, Path]:
        return {field: Path(value) for field, value in asdict(self).items()}


def validate_split_integrity(
    sessions: Iterable[BatchSession],
) -> dict[str, Any]:
    session_values = tuple(sessions)
    operational = tuple(
        item for item in session_values if item.data_context == "REAL_PILOT"
    )
    fixture = tuple(
        item for item in session_values if item.data_context == "FIXTURE_ONLY"
    )
    participant_splits: dict[str, set[str]] = {}
    session_splits: dict[str, str] = {}
    answer_splits: dict[str, str] = {}
    for item in operational:
        participant_splits.setdefault(item.participant_id, set()).add(item.split_name)
        existing_session = session_splits.get(item.session_id)
        _require(
            existing_session in {None, item.split_name},
            f"session split leakage: {item.session_id}",
        )
        session_splits[item.session_id] = item.split_name
        for answer_id in item.answer_ids:
            existing_answer = answer_splits.get(answer_id)
            _require(
                existing_answer in {None, item.split_name},
                f"answer split leakage: {answer_id}",
            )
            answer_splits[answer_id] = item.split_name
    leaked = {
        participant_id: sorted(splits)
        for participant_id, splits in participant_splits.items()
        if len(splits) != 1
    }
    _require(not leaked, f"participant split leakage: {leaked}")
    result = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "valid": True,
        "supported_splits": sorted(SPLITS),
        "operational_participant_count": len(participant_splits),
        "operational_session_count": len(session_splits),
        "operational_answer_count": len(answer_splits),
        "participant_split_assignments": {
            participant_id: next(iter(splits))
            for participant_id, splits in sorted(participant_splits.items())
        },
        "session_split_assignments": dict(sorted(session_splits.items())),
        "answer_split_assignments": dict(sorted(answer_splits.items())),
        "leakage_detected": False,
        "fixture_session_count_excluded": len(fixture),
        "fixture_assignments_are_not_operational": True,
        "split_movement_performed": False,
    }
    ensure_finite(result)
    return result


def intake_template() -> dict[str, Any]:
    return {
        "participant_id": None,
        "session_id": None,
        "consent_reference_id": None,
        "video_reference": None,
        "video_sha256": None,
        "metadata_reference": None,
        "annotation_ready_manifest_reference": None,
        "split_name": None,
        "answer_ids": [],
        "rater_assignments": [],
        "notes": None,
    }


def _load_sources(
    sources: CurrentSessionSources,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    documents: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for name, path in sources.named_paths().items():
        _require(path.is_file(), f"required source missing: {name}")
        try:
            documents[name] = load_strict_json(path)
        except ValueError as exc:
            raise PilotBatchError(
                "pilot_batch_validation_failed", f"invalid source {name}: {exc}"
            ) from exc
        hashes[name] = sha256_file(path)
    return documents, hashes


def _validate_current_sources(documents: dict[str, dict[str, Any]]) -> None:
    consent = documents["consent"]
    metadata = documents["metadata"]
    consent_validation = documents["consent_validation"]
    video = documents["video_metadata"]
    intervals = documents["interval_validation"]
    annotation_ready = documents["annotation_ready_manifest"]
    split = documents["split_assignment"]
    package = documents["annotation_package_manifest"]
    stage19 = documents["stage19_input_validation"]
    agreement = documents["stage19_agreement_summary"]
    governance = documents["governance_status"]
    snapshot = documents["approved_snapshot"]
    expected_participant = "PTC_000001"
    expected_session = "SES_000001"
    expected_split = "DEVELOPMENT"
    expected_answers = [
        "ANS_000001",
        "ANS_000002",
        "ANS_000003",
        "ANS_000004",
    ]

    _require(
        consent.get("participant_id") == expected_participant,
        "consent participant mismatch",
    )
    _require(consent.get("consent_status") == "GRANTED", "consent not granted")
    _require(consent.get("withdrawn_at") is None, "consent has withdrawal")
    _require(metadata.get("withdrawn") is False, "metadata has withdrawal")
    _require(
        metadata.get("participant_id") == expected_participant
        and metadata.get("session_id") == expected_session,
        "metadata Session reference mismatch",
    )
    _require(
        metadata.get("consent_reference_id") == consent.get("consent_reference_id"),
        "consent reference mismatch",
    )
    _require(consent_validation.get("valid") is True, "consent validation failed")
    _require(
        consent_validation.get("checks", {}).get("not_withdrawn") is True,
        "withdrawal check failed",
    )
    _require(video.get("hash_valid") is True, "video hash validation failed")
    _require(
        video.get("sha256") == metadata.get("expected_sha256"),
        "video SHA does not match metadata",
    )
    _require(intervals.get("valid") is True, "interval validation failed")
    _require(
        intervals.get("participant_id") == expected_participant
        and intervals.get("session_id") == expected_session,
        "interval Session reference mismatch",
    )
    metadata_answers = [
        item.get("answer_id") for item in metadata.get("answers", [])
        if isinstance(item, dict)
    ]
    interval_answers = [
        item.get("answer_id") for item in intervals.get("answers", [])
        if isinstance(item, dict)
    ]
    _require(
        metadata_answers == expected_answers and interval_answers == expected_answers,
        "Answer references do not match the registered Session",
    )
    _require(
        annotation_ready.get("final_status") == "pilot_video_annotation_ready",
        "Session is not Annotation Ready",
    )
    _require(
        annotation_ready.get("participant_id") == expected_participant
        and annotation_ready.get("session_id") == expected_session,
        "Annotation Ready Session reference mismatch",
    )
    _require(annotation_ready.get("split_name") == expected_split, "split changed")
    ready_answers = [
        item.get("answer_id")
        for item in annotation_ready.get("answer_intervals", [])
        if isinstance(item, dict)
    ]
    _require(ready_answers == expected_answers, "Annotation Ready Answer mismatch")
    split_linkage = split.get("linkage", {})
    _require(
        split_linkage.get("leakage_detected") is False,
        "Stage 17 split leakage detected",
    )
    _require(
        split.get("assignment", {}).get("participant_id") == expected_participant
        and split.get("assignment", {}).get("split_name") == expected_split,
        "participant Split reference mismatch",
    )
    _require(
        split_linkage.get("participant")
        == {"participant_id": expected_participant, "split_name": expected_split},
        "participant Split linkage mismatch",
    )
    _require(
        split_linkage.get("sessions")
        == [{"session_id": expected_session, "split_name": expected_split}],
        "Session Split linkage mismatch",
    )
    _require(
        split_linkage.get("answers")
        == [
            {"answer_id": answer_id, "split_name": expected_split}
            for answer_id in expected_answers
        ],
        "Answer Split linkage mismatch",
    )
    _require(
        split.get("existing_assignment_scan", {}).get(
            "fixture_assignments_are_not_operational"
        )
        is True,
        "fixture assignment isolation missing",
    )
    _require(
        package.get("participant_id") == expected_participant
        and package.get("session_id") == expected_session,
        "Annotation package Session reference mismatch",
    )
    _require(package.get("split_name") == expected_split, "package split mismatch")
    _require(package.get("answer_count") == len(expected_answers), "package Answer mismatch")
    _require(stage19.get("all_inputs_valid") is True, "Rater inputs are invalid")
    _require(
        stage19.get("participant_id") == expected_participant
        and stage19.get("session_id") == expected_session,
        "Stage 19 Session reference mismatch",
    )
    _require(
        stage19.get("context_checks", {}).get("answer_ids") is True,
        "Stage 19 Answer references invalid",
    )
    _require(
        agreement.get("agreement_context") == "RATER_IDENTITY_UNVERIFIED",
        "Rater identity provenance changed",
    )
    _require(
        agreement.get("calculation_status")
        == "NOT_CALCULATED_POLICY_REVIEW_REQUIRED",
        "unexpected official Agreement calculation",
    )
    _require(
        governance.get("tie_breaker_policy_status") == TIE_BREAKER_STATUS,
        "tie-breaker is not approved",
    )
    _require(
        governance.get("agreement_policy_status") == AGREEMENT_POLICY_STATUS,
        "Agreement policy status mismatch",
    )
    _require(
        governance.get("approved_tie_breaker_strategy") == APPROVED_STRATEGY,
        "approved strategy mismatch",
    )
    eligibility = governance.get("execution_eligibility", {})
    _require(eligibility.get("tie_breaker_approved") is True, "tie-breaker gate failed")
    _require(eligibility.get("thresholds_approved") is False, "thresholds were approved")
    _require(
        eligibility.get("official_matching_eligible") is False,
        "official matching unexpectedly eligible",
    )
    _require(
        snapshot.get("policy_id") == MATCHING_POLICY_ID,
        "policy snapshot ID mismatch",
    )
    _require(
        snapshot.get("policy_version") == MATCHING_POLICY_VERSION,
        "policy snapshot version mismatch",
    )
    _require(snapshot.get("operational") is False, "policy became operational")
    _require(snapshot.get("threshold_status") == "DEFERRED", "threshold status changed")
    _require(
        all(
            snapshot.get(name) is None
            for name in (
                "minimum_temporal_iou",
                "maximum_onset_difference_ms",
                "maximum_offset_difference_ms",
            )
        ),
        "thresholds must remain null",
    )


def _assignment_from_source(
    role: str,
    annotation: dict[str, Any],
    stage19_input: dict[str, Any],
    annotation_path: Path,
) -> RaterAssignment:
    source = stage19_input["rater_inputs"][role]
    _require(source.get("valid") is True, f"{role} validation failed")
    _require(source.get("rater_id") == role, f"{role} role mismatch")
    _require(annotation.get("rater_id") == role, f"{role} Annotation mismatch")
    _require(
        annotation.get("participant_id") == "PTC_000001"
        and annotation.get("session_id") == "SES_000001",
        f"{role} Session reference mismatch",
    )
    actual_sha = sha256_file(annotation_path)
    _require(source.get("sha256") == actual_sha, f"{role} SHA mismatch")
    value = {
        "assignment_id": f"ASG_SES_000001_{role}",
        "participant_id": "PTC_000001",
        "session_id": "SES_000001",
        "rater_role": role,
        "rater_identity_context": "RATER_IDENTITY_UNVERIFIED",
        "assignment_status": "COMPLETED",
        "assigned_at": None,
        "completed_at": annotation.get("completed_at"),
        "annotation_file_reference": str(annotation_path),
        "annotation_sha256": actual_sha,
        "blind_flags_valid": source.get("blind_flags_valid"),
    }
    return RaterAssignment.from_dict(value)


def _build_current_records(
    documents: dict[str, dict[str, Any]],
    sources: CurrentSessionSources,
) -> tuple[BatchSession, tuple[RaterAssignment, RaterAssignment], int]:
    stage19 = documents["stage19_input_validation"]
    rater_a = _assignment_from_source(
        "RATER_A", documents["rater_a_annotation"], stage19, sources.rater_a_annotation
    )
    rater_b = _assignment_from_source(
        "RATER_B", documents["rater_b_annotation"], stage19, sources.rater_b_annotation
    )
    answers = tuple(
        item["answer_id"] for item in documents["interval_validation"]["answers"]
    )
    annotation_ready_path = str(sources.annotation_ready_manifest)
    session = BatchSession.from_dict(
        {
            "participant_id": "PTC_000001",
            "session_id": "SES_000001",
            "split_name": "DEVELOPMENT",
            "consent_reference_id": documents["consent"]["consent_reference_id"],
            "video_sha256": documents["video_metadata"]["sha256"],
            "annotation_ready_manifest_reference": annotation_ready_path,
            "answer_ids": list(answers),
            "rater_a_assignment": rater_a.assignment_id,
            "rater_b_assignment": rater_b.assignment_id,
            "rater_a_status": rater_a.assignment_status,
            "rater_b_status": rater_b.assignment_status,
            "agreement_status": "NOT_CALCULATED_THRESHOLDS_UNAPPROVED",
            "adjudication_status": "NOT_STARTED",
            "eligible_for_threshold_evidence": False,
            "exclusion_reasons": list(BLOCKING_REASONS),
            "data_context": "REAL_PILOT",
        }
    )
    observed_event_count = sum(
        len(documents[name].get("events", []))
        for name in ("rater_a_annotation", "rater_b_annotation")
    )
    return session, (rater_a, rater_b), observed_event_count


def _registry(
    created_at: str,
    session: BatchSession,
    assignments: tuple[RaterAssignment, RaterAssignment],
    observed_event_count: int,
) -> BatchRegistry:
    value = {
        "batch_id": BATCH_ID,
        "batch_version": BATCH_VERSION,
        "batch_status": BATCH_STATUS,
        "purpose": BATCH_PURPOSE,
        "scope": SCOPE,
        "operational": False,
        "created_at": created_at,
        "participant_count": 1,
        "session_count": 1,
        "answer_count": len(session.answer_ids),
        "split_summary": {
            "DEVELOPMENT": 1,
            "CALIBRATION": 0,
            "VALIDATION": 0,
            "HOLDOUT": 0,
            "EXCLUDED": 0,
        },
        "sessions": [
            {
                "participant_id": session.participant_id,
                "session_id": session.session_id,
            }
        ],
        "rater_assignment_summary": {
            "assignment_count": len(assignments),
            "completed_count": sum(
                item.assignment_status == "COMPLETED" for item in assignments
            ),
            "identity_context": "RATER_IDENTITY_UNVERIFIED",
        },
        "annotation_completion_summary": {
            "session_count": 1,
            "completed_session_count": 1,
            "observed_annotation_event_count": observed_event_count,
        },
        "agreement_readiness_summary": {
            "policy_reference_available": True,
            "tie_breaker_approved": True,
            "thresholds_approved": False,
            "official_matching_eligible": False,
            "official_agreement_calculated": False,
        },
        "threshold_evidence_readiness": THRESHOLD_READINESS,
        "blocking_reasons": list(BLOCKING_REASONS),
    }
    return BatchRegistry.from_dict(value)


def build_pilot_annotation_batch(
    sources: CurrentSessionSources,
    output_dir: str | Path,
    *,
    created_at: str,
) -> dict[str, Any]:
    destination = Path(output_dir)
    if destination.exists():
        _fail("refusing to overwrite Stage 20 batch output")
    created = _required_time(created_at, "created_at")
    documents, hashes_before = _load_sources(sources)
    _validate_current_sources(documents)
    session, assignments, observed_event_count = _build_current_records(
        documents, sources
    )
    split_validation = validate_split_integrity([session])
    registry = _registry(created, session, assignments, observed_event_count)
    _require(registry.batch_status != "FROZEN", "Stage 20 cannot freeze a batch")
    _require(
        registry.threshold_evidence_readiness == "EVIDENCE_INSUFFICIENT",
        "one-participant batch cannot be marked Evidence Ready",
    )

    sessions_document = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "batch_id": BATCH_ID,
        "session_count": 1,
        "actual_participant_created": False,
        "actual_session_created": False,
        "sessions": [session.to_dict()],
    }
    assignments_document = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "batch_id": BATCH_ID,
        "assignment_count": len(assignments),
        "rater_identity_context": "RATER_IDENTITY_UNVERIFIED",
        "independent_raters_asserted": False,
        "assignments": [item.to_dict() for item in assignments],
    }
    readiness = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "batch_id": BATCH_ID,
        "structural_conditions": {
            "consent_valid": True,
            "withdrawal_absent": True,
            "video_validation_passed": True,
            "annotation_ready": True,
            "participant_split_valid": True,
            "rater_a_input_valid": True,
            "rater_b_input_valid": True,
            "agreement_policy_reference_available": True,
            "tie_breaker_approved": True,
            "thresholds_unapproved_explicit": True,
            "real_and_fixture_data_separated": True,
            "participant_leakage_absent": True,
        },
        "approved_minimum_criteria": {
            "minimum_participant_count": None,
            "minimum_session_count": None,
            "minimum_event_count": None,
        },
        "observed_counts": {
            "participant_count": 1,
            "session_count": 1,
            "answer_count": len(session.answer_ids),
            "annotation_event_count": observed_event_count,
        },
        "threshold_policy": {
            "minimum_temporal_iou": None,
            "maximum_onset_difference_ms": None,
            "maximum_offset_difference_ms": None,
        },
        "threshold_evidence_readiness": THRESHOLD_READINESS,
        "ready_for_review": False,
        "blocking_reasons": list(BLOCKING_REASONS),
        "threshold_created": False,
        "threshold_approved": False,
        "agreement_calculated": False,
        "kappa_calculated": False,
    }
    batch_status = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "batch_id": BATCH_ID,
        "batch_status": BATCH_STATUS,
        "current_status": FINAL_STATUS,
        "current_status_meaning": (
            "The registered Session is structurally valid, but approved sufficiency "
            "criteria and sufficient multi-participant evidence do not exist."
        ),
        "collection_status": COLLECTION_STATUS,
        "collection_status_meaning": (
            "Additional independently governed pilot Sessions are required before "
            "threshold evidence can be reviewed."
        ),
        "threshold_evidence_readiness": THRESHOLD_READINESS,
        "dataset_frozen": False,
    }
    template = intake_template()
    hashes_after = {
        name: sha256_file(path) for name, path in sources.named_paths().items()
    }
    _require(hashes_before == hashes_after, "protected source hash changed")
    validation = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "valid": True,
        "current_status": FINAL_STATUS,
        "checks": {
            "batch_schema_valid": True,
            "session_references_valid": True,
            "split_validation_passed": True,
            "fixture_and_real_data_separated": True,
            "rater_assignments_isolated": True,
            "rater_identity_unverified_preserved": True,
            "actual_participant_created": False,
            "actual_session_created": False,
            "actual_video_created": False,
            "actual_annotation_event_created": False,
            "minimum_quantity_criteria_invented": False,
            "one_participant_marked_evidence_ready": False,
            "thresholds_remain_null": True,
            "batch_frozen": False,
            "agreement_calculated": False,
            "kappa_calculated": False,
            "protected_source_hashes_unchanged": True,
        },
        "protected_sources": [
            {
                "name": name,
                "path": str(sources.named_paths()[name]),
                "sha256_before": hashes_before[name],
                "sha256_after": hashes_after[name],
            }
            for name in sorted(hashes_before)
        ],
    }
    documents_to_write = {
        "pilot_batch_registry.json": registry.to_dict(),
        "pilot_batch_sessions.json": sessions_document,
        "participant_split_validation.json": split_validation,
        "rater_assignment_registry.json": assignments_document,
        "threshold_evidence_readiness.json": readiness,
        "pilot_batch_session.template.json": template,
        "batch_status.json": batch_status,
        "validation_report.json": validation,
    }
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in documents_to_write.items():
        write_strict_json(destination / name, value)
    markdown = (
        "# Stage 20 pilot Annotation batch validation\n\n"
        f"- Batch: `{BATCH_ID}` v`{BATCH_VERSION}`\n"
        f"- Current status: `{FINAL_STATUS}`\n"
        f"- Collection status: `{COLLECTION_STATUS}`\n"
        "- Registered real participants / Sessions / Answers: `1 / 1 / 4`\n"
        "- Split: `DEVELOPMENT`\n"
        "- Rater identity context: `RATER_IDENTITY_UNVERIFIED`\n"
        "- Threshold evidence readiness: `EVIDENCE_INSUFFICIENT`\n"
        "- Thresholds: all `null`\n"
        "- Agreement/Kappa calculated: `false` / `false`\n"
        "- Dataset frozen: `false`\n"
    )
    (destination / "validation_report.md").write_text(markdown, encoding="utf-8")
    missing = [name for name in OUTPUT_NAMES if not (destination / name).is_file()]
    _require(not missing, f"missing Stage 20 outputs: {missing}")
    ensure_finite(validation)
    return validation


def load_batch_registry(path: str | Path) -> BatchRegistry:
    try:
        return BatchRegistry.from_dict(load_strict_json(path))
    except ValueError as exc:
        if isinstance(exc, PilotBatchError):
            raise
        raise PilotBatchError("pilot_batch_validation_failed", str(exc)) from exc
