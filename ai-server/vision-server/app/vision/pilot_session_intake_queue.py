"""Stage 21 read-only discovery for additional pilot Session inputs.

This module inventories incoming files and prepares governance candidates. It
does not move inputs, run Stages 15-18, mutate the Stage 20 batch, approve a
Split, create Annotation Events, calculate Agreement, or freeze a dataset.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.vision.pilot_video_intake import (
    PARTICIPANT_RE,
    SESSION_RE,
    SHA256_RE,
    ensure_finite,
    load_strict_json,
    sha256_file,
    write_strict_json,
)


SCHEMA_VERSION = "1.0.0"
STAGE = 21
QUEUE_ID = "PILOT_SESSION_INTAKE_QUEUE_001"
QUEUE_VERSION = "0.1.0"
BATCH_ID = "PILOT_ANNOTATION_BATCH_001"
DEFAULT_SPLIT = "DEVELOPMENT"

INPUT_SET_STATUSES = frozenset(
    {
        "COMPLETE_INPUT_SET",
        "MISSING_VIDEO",
        "MISSING_CONSENT",
        "MISSING_METADATA",
        "INVALID_FILENAME",
        "REFERENCE_MISMATCH",
        "HASH_MISMATCH",
        "DUPLICATE_SESSION",
        "WITHDRAWN",
        "READY_FOR_INTAKE_VALIDATION",
    }
)
CONSENT_STATUSES = frozenset(
    {"NOT_AVAILABLE", "VALID", "INVALID", "WITHDRAWN"}
)
SPLIT_STATUSES = frozenset(
    {
        "NOT_EVALUATED",
        "REVIEW_REQUIRED",
        "EXISTING_SPLIT_PRESERVED",
        "BLOCKED",
    }
)
FINAL_STATUSES = frozenset(
    {
        "awaiting_additional_pilot_sessions",
        "incomplete_pilot_session_inputs",
        "pilot_session_intake_validation_failed",
        "pilot_sessions_ready_for_stage15",
        "duplicate_pilot_sessions_detected",
    }
)
NEXT_STAGES = frozenset({"STAGE_15", "STAGE_16", "STAGE_17", "STAGE_18"})
STAGE_TRANSITION_CONTRACT = {
    "READY_FOR_INTAKE_VALIDATION": "STAGE_15",
    "STAGE_15_PASSED": "STAGE_16",
    "MANUAL_REVIEW_PASSED": "STAGE_17",
    "ANNOTATION_READY": "STAGE_18",
}
SPLITS = frozenset(
    {"DEVELOPMENT", "CALIBRATION", "VALIDATION", "HOLDOUT", "EXCLUDED"}
)
FILE_PATTERN = re.compile(
    r"^(?P<participant>PTC_\d{6})_(?P<session>SES_\d{6})"
    r"\.(?P<kind>mp4|consent\.json|metadata\.json)$"
)
CANDIDATE_FIELDS = frozenset(
    {
        "participant_id",
        "session_id",
        "video_reference",
        "consent_reference",
        "metadata_reference",
        "video_sha256",
        "input_set_status",
        "consent_status",
        "split_status",
        "proposed_split",
        "batch_registration_eligible",
        "next_required_stage",
        "blocking_reasons",
    }
)
QUEUE_FIELDS = frozenset(
    {
        "queue_id",
        "queue_version",
        "generated_at",
        "session_candidates",
        "complete_input_count",
        "incomplete_input_count",
        "duplicate_count",
        "withdrawn_count",
        "ready_count",
        "blocking_reasons",
        "final_status",
    }
)
OUTPUT_NAMES = (
    "pilot_session_intake_queue.json",
    "input_set_validation.json",
    "duplicate_session_validation.json",
    "split_assignment_candidates.json",
    "batch_registration_candidates.json",
    "intake_status.json",
    "pilot_session_intake.template.json",
    "validation_report.json",
    "validation_report.md",
)


class PilotSessionIntakeError(ValueError):
    """Raised when the Stage 21 intake contract cannot be validated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _fail(message: str) -> None:
    raise PilotSessionIntakeError("pilot_session_intake_validation_failed", message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _required_time(value: Any, field: str) -> str:
    result = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PilotSessionIntakeError(
            "pilot_session_intake_validation_failed",
            f"{field} must be ISO 8601",
        ) from exc
    if parsed.utcoffset() is None:
        _fail(f"{field} must include timezone")
    return result


def _exact_fields(
    value: dict[str, Any], expected: frozenset[str], context: str
) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        _fail(f"{context} fields must be exact; missing={missing}, extra={extra}")


@dataclass(frozen=True)
class SessionCandidate:
    participant_id: str | None
    session_id: str | None
    video_reference: str | None
    consent_reference: str | None
    metadata_reference: str | None
    video_sha256: str | None
    input_set_status: str
    consent_status: str
    split_status: str
    proposed_split: str | None
    batch_registration_eligible: bool
    next_required_stage: str | None
    blocking_reasons: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SessionCandidate":
        if not isinstance(value, dict):
            _fail("Session candidate must be an object")
        _exact_fields(value, CANDIDATE_FIELDS, "Session candidate")
        ensure_finite(value)
        participant_id = _optional_text(value["participant_id"], "participant_id")
        session_id = _optional_text(value["session_id"], "session_id")
        if participant_id is not None:
            _require(
                bool(PARTICIPANT_RE.fullmatch(participant_id)),
                "invalid participant_id",
            )
        if session_id is not None:
            _require(bool(SESSION_RE.fullmatch(session_id)), "invalid session_id")
        for field in (
            "video_reference",
            "consent_reference",
            "metadata_reference",
        ):
            _optional_text(value[field], field)
        video_sha = value["video_sha256"]
        if video_sha is not None:
            _require(
                isinstance(video_sha, str) and bool(SHA256_RE.fullmatch(video_sha)),
                "video_sha256 must be lowercase SHA-256",
            )
        _require(
            value["input_set_status"] in INPUT_SET_STATUSES,
            "invalid input_set_status",
        )
        _require(value["consent_status"] in CONSENT_STATUSES, "invalid consent_status")
        _require(value["split_status"] in SPLIT_STATUSES, "invalid split_status")
        proposed_split = value["proposed_split"]
        _require(
            proposed_split is None or proposed_split in SPLITS,
            "invalid proposed_split",
        )
        _require(
            isinstance(value["batch_registration_eligible"], bool),
            "batch_registration_eligible must be boolean",
        )
        next_stage = value["next_required_stage"]
        _require(
            next_stage is None or next_stage in NEXT_STAGES,
            "invalid next_required_stage",
        )
        reasons = value["blocking_reasons"]
        _require(
            isinstance(reasons, list)
            and len(reasons) == len(set(reasons))
            and all(isinstance(reason, str) and reason for reason in reasons),
            "blocking_reasons must be a unique text array",
        )
        if value["input_set_status"] == "READY_FOR_INTAKE_VALIDATION":
            _require(next_stage == "STAGE_15", "ready input must wait for STAGE_15")
            _require(
                value["batch_registration_eligible"] is False,
                "Stage 21 cannot register a Session before Stages 15-18",
            )
        return cls(
            participant_id,
            session_id,
            value["video_reference"],
            value["consent_reference"],
            value["metadata_reference"],
            video_sha,
            value["input_set_status"],
            value["consent_status"],
            value["split_status"],
            proposed_split,
            value["batch_registration_eligible"],
            next_stage,
            tuple(reasons),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["blocking_reasons"] = list(self.blocking_reasons)
        return value


@dataclass(frozen=True)
class IntakeQueue:
    queue_id: str
    queue_version: str
    generated_at: str
    session_candidates: tuple[SessionCandidate, ...]
    complete_input_count: int
    incomplete_input_count: int
    duplicate_count: int
    withdrawn_count: int
    ready_count: int
    blocking_reasons: tuple[str, ...]
    final_status: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "IntakeQueue":
        if not isinstance(value, dict):
            _fail("Intake Queue must be an object")
        _exact_fields(value, QUEUE_FIELDS, "Intake Queue")
        ensure_finite(value)
        _required_text(value["queue_id"], "queue_id")
        _required_text(value["queue_version"], "queue_version")
        generated_at = _required_time(value["generated_at"], "generated_at")
        candidates = value["session_candidates"]
        _require(isinstance(candidates, list), "session_candidates must be an array")
        parsed_candidates = tuple(
            SessionCandidate.from_dict(candidate) for candidate in candidates
        )
        counts: dict[str, int] = {}
        for field in (
            "complete_input_count",
            "incomplete_input_count",
            "duplicate_count",
            "withdrawn_count",
            "ready_count",
        ):
            count = value[field]
            _require(
                isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0,
                f"{field} must be a non-negative integer",
            )
            counts[field] = count
        _require(
            counts["ready_count"]
            == sum(
                candidate.input_set_status == "READY_FOR_INTAKE_VALIDATION"
                for candidate in parsed_candidates
            ),
            "ready_count mismatch",
        )
        _require(
            counts["duplicate_count"]
            == sum(
                candidate.input_set_status == "DUPLICATE_SESSION"
                or "DUPLICATE_VIDEO_SHA256" in candidate.blocking_reasons
                for candidate in parsed_candidates
            ),
            "duplicate_count mismatch",
        )
        reasons = value["blocking_reasons"]
        _require(
            isinstance(reasons, list)
            and len(reasons) == len(set(reasons))
            and all(isinstance(reason, str) and reason for reason in reasons),
            "Queue blocking_reasons must be a unique text array",
        )
        _require(value["final_status"] in FINAL_STATUSES, "invalid final_status")
        return cls(
            value["queue_id"],
            value["queue_version"],
            generated_at,
            parsed_candidates,
            counts["complete_input_count"],
            counts["incomplete_input_count"],
            counts["duplicate_count"],
            counts["withdrawn_count"],
            counts["ready_count"],
            tuple(reasons),
            value["final_status"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["session_candidates"] = [
            candidate.to_dict() for candidate in self.session_candidates
        ]
        value["blocking_reasons"] = list(self.blocking_reasons)
        return value


@dataclass(frozen=True)
class ExistingBatchIndex:
    sessions: dict[str, dict[str, str]]
    participant_splits: dict[str, str]
    video_sessions: dict[str, str]
    fixture_participant_ids: frozenset[str]
    fixture_session_ids: frozenset[str]

    @classmethod
    def from_files(
        cls,
        batch_sessions_path: str | Path,
        split_validation_path: str | Path,
        fixture_registry_path: str | Path,
    ) -> "ExistingBatchIndex":
        batch = load_strict_json(batch_sessions_path)
        split = load_strict_json(split_validation_path)
        fixture = load_strict_json(fixture_registry_path)
        _require(
            batch.get("batch_id") == BATCH_ID
            and batch.get("actual_participant_created") is False
            and batch.get("actual_session_created") is False,
            "Stage 20 Session registry is invalid",
        )
        sessions: dict[str, dict[str, str]] = {}
        video_sessions: dict[str, str] = {}
        for item in batch.get("sessions", []):
            _require(isinstance(item, dict), "Stage 20 Session must be an object")
            participant_id = item.get("participant_id")
            session_id = item.get("session_id")
            split_name = item.get("split_name")
            video_sha = item.get("video_sha256")
            _require(
                isinstance(participant_id, str)
                and PARTICIPANT_RE.fullmatch(participant_id)
                and isinstance(session_id, str)
                and SESSION_RE.fullmatch(session_id)
                and split_name in SPLITS
                and isinstance(video_sha, str)
                and SHA256_RE.fullmatch(video_sha),
                "Stage 20 Session reference is invalid",
            )
            _require(session_id not in sessions, "duplicate Stage 20 Session ID")
            _require(video_sha not in video_sessions, "duplicate Stage 20 video SHA")
            sessions[session_id] = {
                "participant_id": participant_id,
                "split_name": split_name,
                "video_sha256": video_sha,
            }
            video_sessions[video_sha] = session_id
        participant_splits = split.get("participant_split_assignments")
        _require(
            isinstance(participant_splits, dict)
            and split.get("leakage_detected") is False
            and all(
                isinstance(participant_id, str)
                and PARTICIPANT_RE.fullmatch(participant_id)
                and split_name in SPLITS
                for participant_id, split_name in participant_splits.items()
            ),
            "Stage 20 participant Split registry is invalid",
        )
        fixture_participants = {
            item.get("participant_id")
            for item in fixture.get("enrollments", [])
            if isinstance(item, dict) and isinstance(item.get("participant_id"), str)
        }
        fixture_sessions = {
            item.get("pilot_session_id")
            for item in fixture.get("sessions", [])
            if isinstance(item, dict) and isinstance(item.get("pilot_session_id"), str)
        }
        return cls(
            sessions,
            dict(participant_splits),
            video_sessions,
            frozenset(fixture_participants),
            frozenset(fixture_sessions),
        )


def _empty_candidate(
    *,
    participant_id: str | None,
    session_id: str | None,
    paths: dict[str, Path],
    status: str,
    reasons: list[str],
) -> SessionCandidate:
    return SessionCandidate.from_dict(
        {
            "participant_id": participant_id,
            "session_id": session_id,
            "video_reference": (
                str(paths["mp4"]) if "mp4" in paths else None
            ),
            "consent_reference": (
                str(paths["consent.json"]) if "consent.json" in paths else None
            ),
            "metadata_reference": (
                str(paths["metadata.json"]) if "metadata.json" in paths else None
            ),
            "video_sha256": None,
            "input_set_status": status,
            "consent_status": "NOT_AVAILABLE",
            "split_status": "NOT_EVALUATED",
            "proposed_split": None,
            "batch_registration_eligible": False,
            "next_required_stage": None,
            "blocking_reasons": reasons,
        }
    )


def _validate_intervals(metadata: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    baseline = metadata.get("baseline_interval")
    if not isinstance(baseline, dict):
        reasons.append("BASELINE_INTERVAL_MISSING")
    else:
        start = baseline.get("start_timestamp_ms")
        end = baseline.get("end_timestamp_ms")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or start >= end
        ):
            reasons.append("BASELINE_INTERVAL_INVALID")
    answers = metadata.get("answers")
    if not isinstance(answers, list) or not answers:
        return reasons + ["ANSWER_INTERVAL_REQUIRED"]
    normalized: list[tuple[int, int, str]] = []
    answer_ids: set[str] = set()
    interval_ids: set[str] = set()
    for answer in answers:
        if not isinstance(answer, dict):
            reasons.append("ANSWER_INTERVAL_INVALID")
            continue
        answer_id = answer.get("answer_id")
        interval_id = answer.get("interval_id")
        start = answer.get("start_timestamp_ms")
        end = answer.get("end_timestamp_ms")
        if not isinstance(answer_id, str) or not answer_id:
            reasons.append("ANSWER_ID_INVALID")
        elif answer_id in answer_ids:
            reasons.append("DUPLICATE_ANSWER_ID")
        else:
            answer_ids.add(answer_id)
        if not isinstance(interval_id, str) or not interval_id:
            reasons.append("ANSWER_INTERVAL_ID_INVALID")
        elif interval_id in interval_ids:
            reasons.append("DUPLICATE_ANSWER_INTERVAL_ID")
        else:
            interval_ids.add(interval_id)
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or start >= end
        ):
            reasons.append("ANSWER_INTERVAL_BOUNDARY_INVALID")
        else:
            normalized.append((start, end, str(interval_id)))
    normalized.sort()
    for left, right in zip(normalized, normalized[1:]):
        if right[0] < left[1]:
            reasons.append("ANSWER_INTERVAL_OVERLAP")
            break
    return list(dict.fromkeys(reasons))


def _split_candidate(
    participant_id: str, index: ExistingBatchIndex
) -> tuple[str, str]:
    existing = index.participant_splits.get(participant_id)
    if existing is not None:
        return "EXISTING_SPLIT_PRESERVED", existing
    return "REVIEW_REQUIRED", DEFAULT_SPLIT


def _validate_complete_set(
    participant_id: str,
    session_id: str,
    paths: dict[str, Path],
    index: ExistingBatchIndex,
) -> SessionCandidate:
    try:
        consent = load_strict_json(paths["consent.json"])
        metadata = load_strict_json(paths["metadata.json"])
    except ValueError as exc:
        return _empty_candidate(
            participant_id=participant_id,
            session_id=session_id,
            paths=paths,
            status="REFERENCE_MISMATCH",
            reasons=["STRICT_JSON_VALIDATION_FAILED", type(exc).__name__],
        )

    actual_sha = sha256_file(paths["mp4"])
    reasons: list[str] = []
    if consent.get("participant_id") != participant_id:
        reasons.append("CONSENT_PARTICIPANT_FILENAME_MISMATCH")
    if metadata.get("participant_id") != participant_id:
        reasons.append("METADATA_PARTICIPANT_FILENAME_MISMATCH")
    if metadata.get("session_id") != session_id:
        reasons.append("METADATA_SESSION_FILENAME_MISMATCH")
    if metadata.get("video_file") != paths["mp4"].name:
        reasons.append("METADATA_VIDEO_FILENAME_MISMATCH")
    if metadata.get("consent_reference_id") != consent.get("consent_reference_id"):
        reasons.append("CONSENT_REFERENCE_MISMATCH")

    withdrawn = (
        consent.get("consent_status") == "WITHDRAWN"
        or consent.get("withdrawn_at") is not None
        or metadata.get("withdrawn") is True
    )
    if withdrawn:
        status = "WITHDRAWN"
        consent_status = "WITHDRAWN"
        reasons.append("CONSENT_WITHDRAWN")
    else:
        permission_checks = {
            "CONSENT_NOT_GRANTED": consent.get("consent_status") != "GRANTED",
            "VIDEO_COLLECTION_NOT_ALLOWED": (
                consent.get("video_collection_allowed") is not True
            ),
            "AUTOMATED_ANALYSIS_NOT_ALLOWED": (
                consent.get("automated_analysis_allowed") is not True
            ),
            "METADATA_WITHDRAWAL_STATE_INVALID": (
                metadata.get("withdrawn") is not False
            ),
        }
        reasons.extend(
            reason for reason, failed in permission_checks.items() if failed
        )
        consent_status = "VALID" if not any(permission_checks.values()) else "INVALID"
        status = "REFERENCE_MISMATCH" if reasons else "COMPLETE_INPUT_SET"

    expected_sha = metadata.get("expected_sha256")
    if (
        not isinstance(expected_sha, str)
        or not SHA256_RE.fullmatch(expected_sha)
        or expected_sha != actual_sha
    ):
        reasons.append("VIDEO_SHA256_MISMATCH")
        if status != "WITHDRAWN":
            status = "HASH_MISMATCH"

    interval_reasons = _validate_intervals(metadata)
    reasons.extend(interval_reasons)
    if interval_reasons and status not in {"WITHDRAWN", "HASH_MISMATCH"}:
        status = "REFERENCE_MISMATCH"

    real_participants = {
        value["participant_id"] for value in index.sessions.values()
    }
    if (
        participant_id in index.fixture_participant_ids
        and participant_id not in real_participants
    ) or (
        session_id in index.fixture_session_ids
        and session_id not in index.sessions
    ):
        reasons.append("FIXTURE_ID_NOT_ALLOWED_FOR_REAL_SESSION")
        if status not in {"WITHDRAWN", "HASH_MISMATCH"}:
            status = "REFERENCE_MISMATCH"

    duplicate_session = session_id in index.sessions
    duplicate_video_session = index.video_sessions.get(actual_sha)
    if duplicate_session:
        reasons.append("DUPLICATE_SESSION_ID")
        status = "DUPLICATE_SESSION"
    if duplicate_video_session is not None:
        reasons.append("DUPLICATE_VIDEO_SHA256")
        if not duplicate_session:
            status = "DUPLICATE_SESSION"

    split_status, proposed_split = _split_candidate(participant_id, index)
    if status == "COMPLETE_INPUT_SET":
        status = "READY_FOR_INTAKE_VALIDATION"
        reasons.append("STAGE_15_NOT_COMPLETED")
        if split_status == "REVIEW_REQUIRED":
            reasons.append("SPLIT_APPROVAL_REQUIRED")
        next_stage = "STAGE_15"
    else:
        split_status = "BLOCKED"
        proposed_split = None
        next_stage = None

    return SessionCandidate.from_dict(
        {
            "participant_id": participant_id,
            "session_id": session_id,
            "video_reference": str(paths["mp4"]),
            "consent_reference": str(paths["consent.json"]),
            "metadata_reference": str(paths["metadata.json"]),
            "video_sha256": actual_sha,
            "input_set_status": status,
            "consent_status": consent_status,
            "split_status": split_status,
            "proposed_split": proposed_split,
            "batch_registration_eligible": False,
            "next_required_stage": next_stage,
            "blocking_reasons": list(dict.fromkeys(reasons)),
        }
    )


def discover_session_candidates(
    incoming_dir: str | Path,
    index: ExistingBatchIndex,
) -> tuple[list[SessionCandidate], dict[str, Any]]:
    incoming = Path(incoming_dir)
    _require(incoming.is_dir(), "incoming directory is missing")
    groups: dict[tuple[str, str], dict[str, Path]] = {}
    invalid_files: list[Path] = []
    ignored_files: list[Path] = []
    for path in sorted(incoming.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        match = FILE_PATTERN.fullmatch(path.name)
        if match is None:
            if path.name.startswith("."):
                ignored_files.append(path)
            elif path.suffix.lower() in {".mp4", ".json"}:
                invalid_files.append(path)
            else:
                ignored_files.append(path)
            continue
        key = (match.group("participant"), match.group("session"))
        groups.setdefault(key, {})[match.group("kind")] = path

    candidates: list[SessionCandidate] = []
    existing_sets: list[dict[str, Any]] = []
    for (participant_id, session_id), paths in sorted(groups.items()):
        existing = index.sessions.get(session_id)
        if existing is not None and existing["participant_id"] == participant_id:
            existing_sets.append(
                {
                    "participant_id": participant_id,
                    "session_id": session_id,
                    "files_present": sorted(paths),
                    "excluded_from_new_candidates": True,
                    "reason": "ALREADY_REGISTERED_STAGE20_SESSION",
                }
            )
            continue
        missing = [
            kind
            for kind in ("mp4", "consent.json", "metadata.json")
            if kind not in paths
        ]
        if missing:
            status = {
                "mp4": "MISSING_VIDEO",
                "consent.json": "MISSING_CONSENT",
                "metadata.json": "MISSING_METADATA",
            }[missing[0]]
            candidates.append(
                _empty_candidate(
                    participant_id=participant_id,
                    session_id=session_id,
                    paths=paths,
                    status=status,
                    reasons=[
                        {
                            "mp4": "VIDEO_FILE_MISSING",
                            "consent.json": "CONSENT_FILE_MISSING",
                            "metadata.json": "METADATA_FILE_MISSING",
                        }[kind]
                        for kind in missing
                    ],
                )
            )
            continue
        candidates.append(
            _validate_complete_set(participant_id, session_id, paths, index)
        )

    for path in invalid_files:
        candidates.append(
            _empty_candidate(
                participant_id=None,
                session_id=None,
                paths={},
                status="INVALID_FILENAME",
                reasons=[f"INVALID_INCOMING_FILENAME:{path.name}"],
            )
        )
    candidates.sort(
        key=lambda item: (
            item.participant_id or "",
            item.session_id or "",
            item.input_set_status,
        )
    )
    discovery = {
        "scanned_file_count": sum(
            1 for path in incoming.iterdir() if path.is_file()
        ),
        "recognized_input_group_count": len(groups),
        "new_session_candidate_count": len(candidates),
        "existing_registered_input_set_count": len(existing_sets),
        "existing_registered_input_sets": existing_sets,
        "invalid_filename_count": len(invalid_files),
        "invalid_filenames": [str(path) for path in invalid_files],
        "ignored_file_count": len(ignored_files),
        "ignored_files": [str(path) for path in ignored_files],
    }
    ensure_finite(discovery)
    return candidates, discovery


def _final_status(
    candidates: list[SessionCandidate], discovery: dict[str, Any]
) -> str:
    if not candidates:
        return "awaiting_additional_pilot_sessions"
    if any(
        item.input_set_status == "READY_FOR_INTAKE_VALIDATION"
        for item in candidates
    ):
        return "pilot_sessions_ready_for_stage15"
    duplicates = [
        item for item in candidates if item.input_set_status == "DUPLICATE_SESSION"
    ]
    if len(duplicates) == len(candidates):
        return "duplicate_pilot_sessions_detected"
    incomplete = [
        item
        for item in candidates
        if item.input_set_status
        in {"MISSING_VIDEO", "MISSING_CONSENT", "MISSING_METADATA"}
    ]
    if len(incomplete) == len(candidates):
        return "incomplete_pilot_session_inputs"
    return "pilot_session_intake_validation_failed"


def intake_template() -> dict[str, Any]:
    return {
        "participant_id": None,
        "session_id": None,
        "video_reference": None,
        "consent_reference": None,
        "metadata_reference": None,
        "video_sha256": None,
        "split_status": "REVIEW_REQUIRED",
        "proposed_split": DEFAULT_SPLIT,
        "notes": None,
    }


def _source_hashes(paths: list[Path]) -> dict[str, str]:
    return {
        str(path): sha256_file(path)
        for path in sorted(paths, key=lambda item: str(item))
        if path.is_file()
    }


def build_pilot_session_intake_queue(
    *,
    incoming_dir: str | Path,
    batch_sessions_path: str | Path,
    split_validation_path: str | Path,
    fixture_registry_path: str | Path,
    output_dir: str | Path,
    generated_at: str,
) -> dict[str, Any]:
    destination = Path(output_dir)
    if destination.exists():
        _fail("refusing to overwrite Stage 21 intake output")
    generated = _required_time(generated_at, "generated_at")
    protected_paths = [
        path
        for path in Path(incoming_dir).iterdir()
        if path.is_file()
    ] + [
        Path(batch_sessions_path),
        Path(split_validation_path),
        Path(fixture_registry_path),
    ]
    hashes_before = _source_hashes(protected_paths)
    index = ExistingBatchIndex.from_files(
        batch_sessions_path,
        split_validation_path,
        fixture_registry_path,
    )
    candidates, discovery = discover_session_candidates(incoming_dir, index)
    final_status = _final_status(candidates, discovery)
    complete_statuses = INPUT_SET_STATUSES - {
        "MISSING_VIDEO",
        "MISSING_CONSENT",
        "MISSING_METADATA",
        "INVALID_FILENAME",
    }
    queue_reasons = sorted(
        {
            reason
            for candidate in candidates
            for reason in candidate.blocking_reasons
        }
    )
    if not candidates:
        queue_reasons = ["NO_NEW_SESSION_INPUTS"]
    queue = IntakeQueue.from_dict(
        {
            "queue_id": QUEUE_ID,
            "queue_version": QUEUE_VERSION,
            "generated_at": generated,
            "session_candidates": [candidate.to_dict() for candidate in candidates],
            "complete_input_count": sum(
                candidate.input_set_status in complete_statuses
                for candidate in candidates
            ),
            "incomplete_input_count": sum(
                candidate.input_set_status
                in {
                    "MISSING_VIDEO",
                    "MISSING_CONSENT",
                    "MISSING_METADATA",
                    "INVALID_FILENAME",
                }
                for candidate in candidates
            ),
            "duplicate_count": sum(
                candidate.input_set_status == "DUPLICATE_SESSION"
                or "DUPLICATE_VIDEO_SHA256" in candidate.blocking_reasons
                for candidate in candidates
            ),
            "withdrawn_count": sum(
                candidate.input_set_status == "WITHDRAWN"
                for candidate in candidates
            ),
            "ready_count": sum(
                candidate.input_set_status == "READY_FOR_INTAKE_VALIDATION"
                for candidate in candidates
            ),
            "blocking_reasons": queue_reasons,
            "final_status": final_status,
        }
    )
    input_validation = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "queue_id": QUEUE_ID,
        "incoming_directory": str(incoming_dir),
        "files_moved": False,
        "files_renamed": False,
        "files_deleted": False,
        "stage_transition_contract": dict(STAGE_TRANSITION_CONTRACT),
        "stage_transition_executed": False,
        "discovery": discovery,
        "session_results": [candidate.to_dict() for candidate in candidates],
    }
    duplicate_validation = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "queue_id": QUEUE_ID,
        "existing_session_ids": sorted(index.sessions),
        "existing_video_sha256_count": len(index.video_sessions),
        "duplicate_count": queue.duplicate_count,
        "duplicates": [
            candidate.to_dict()
            for candidate in candidates
            if candidate.input_set_status == "DUPLICATE_SESSION"
        ],
        "existing_batch_modified": False,
    }
    split_candidates = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "queue_id": QUEUE_ID,
        "split_auto_approved": False,
        "split_movement_performed": False,
        "candidates": [
            {
                "participant_id": candidate.participant_id,
                "session_id": candidate.session_id,
                "split_status": candidate.split_status,
                "proposed_split": candidate.proposed_split,
            }
            for candidate in candidates
            if candidate.participant_id is not None
        ],
    }
    registration_candidates = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "queue_id": QUEUE_ID,
        "target_batch_id": BATCH_ID,
        "existing_batch_modified": False,
        "registration_executed": False,
        "eligible_count": sum(
            candidate.batch_registration_eligible for candidate in candidates
        ),
        "candidates": [
            candidate.to_dict()
            for candidate in candidates
            if candidate.input_set_status == "READY_FOR_INTAKE_VALIDATION"
        ],
    }
    status_document = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "queue_id": QUEUE_ID,
        "final_status": final_status,
        "new_session_candidate_count": len(candidates),
        "ready_for_stage15_count": queue.ready_count,
        "batch_registration_eligible_count": 0,
        "stages_15_to_18_executed": False,
        "annotation_generated": False,
        "agreement_calculated": False,
        "kappa_calculated": False,
        "threshold_created": False,
        "dataset_frozen": False,
    }
    hashes_after = _source_hashes(protected_paths)
    _require(hashes_before == hashes_after, "protected input hash changed")
    validation = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "valid": True,
        "final_status": final_status,
        "checks": {
            "queue_schema_valid": True,
            "incoming_files_read_only": True,
            "existing_batch_read_only": True,
            "duplicate_checks_applied": True,
            "fixture_ids_blocked": True,
            "participant_split_preserved": True,
            "new_participant_split_requires_review": True,
            "split_auto_approved": False,
            "stages_15_to_18_executed": False,
            "actual_entity_created": False,
            "annotation_generated": False,
            "agreement_or_kappa_calculated": False,
            "threshold_created": False,
            "dataset_frozen": False,
            "protected_source_hashes_unchanged": True,
        },
        "protected_sources": [
            {
                "path": path,
                "sha256_before": hashes_before[path],
                "sha256_after": hashes_after[path],
            }
            for path in sorted(hashes_before)
        ],
    }
    documents = {
        "pilot_session_intake_queue.json": queue.to_dict(),
        "input_set_validation.json": input_validation,
        "duplicate_session_validation.json": duplicate_validation,
        "split_assignment_candidates.json": split_candidates,
        "batch_registration_candidates.json": registration_candidates,
        "intake_status.json": status_document,
        "pilot_session_intake.template.json": intake_template(),
        "validation_report.json": validation,
    }
    for value in documents.values():
        ensure_finite(value)
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in documents.items():
        write_strict_json(destination / name, value)
    markdown = (
        "# Stage 21 pilot Session intake validation\n\n"
        f"- Queue: `{QUEUE_ID}` v`{QUEUE_VERSION}`\n"
        f"- Final status: `{final_status}`\n"
        f"- New Session candidates: `{len(candidates)}`\n"
        f"- Ready for Stage 15: `{queue.ready_count}`\n"
        "- Batch registrations executed: `0`\n"
        "- Stages 15-18 executed: `false`\n"
        "- Split auto-approved: `false`\n"
        "- Agreement/Kappa/Threshold calculated: `false / false / false`\n"
        "- Dataset frozen: `false`\n"
    )
    (destination / "validation_report.md").write_text(markdown, encoding="utf-8")
    missing = [name for name in OUTPUT_NAMES if not (destination / name).is_file()]
    _require(not missing, f"missing Stage 21 outputs: {missing}")
    return validation


def load_intake_queue(path: str | Path) -> IntakeQueue:
    try:
        return IntakeQueue.from_dict(load_strict_json(path))
    except ValueError as exc:
        if isinstance(exc, PilotSessionIntakeError):
            raise
        raise PilotSessionIntakeError(
            "pilot_session_intake_validation_failed", str(exc)
        ) from exc
