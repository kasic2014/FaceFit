"""End-to-end Stage 14 metadata fixture readiness validation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from app.vision.collection_quality_validator import validate_quality_checks
from app.vision.consent_models import ConsentReference
from app.vision.data_collection_validator import (
    DataCollectionValidationError,
    dumps_strict,
    load_strict_json,
    sha256_file,
)
from app.vision.dataset_manifest_models import DatasetSplitAssignment
from app.vision.dataset_release_gate import evaluate_dataset_release_gate
from app.vision.manual_review_models import ManualReviewDecision
from app.vision.pilot_collection_models import (
    CollectionQualityCheck,
    DatasetReleaseCandidate,
    PilotAnswerRecord,
    PilotParticipantEnrollment,
    PilotSessionRun,
    PilotStudyProtocol,
    QualityCheckType,
    RecordingFileRecord,
    WithdrawalRequest,
)
from app.vision.recording_checklist import RecordingChecklist, recording_ready
from app.vision.recording_file_validator import validate_recording_file_record
from app.vision.withdrawal_processor import process_withdrawal


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = (
    ROOT / "config" / "pilot_collection" / "fixtures" / "pilot_registry.json"
)
DEFAULT_OUTPUT = (
    ROOT / "data" / "output" / "pilot_collection_readiness_validation"
)
TECHNICAL_JUDGMENT = (
    "pilot_collection_readiness_contract_smoke_completed_with_metadata_fixtures"
)
FAILURE_REASON_BY_CHECK = {
    "VIDEO_HASH_VALID": "HASH_MISMATCH",
    "BASELINE_AVAILABLE": "BASELINE_FAILED",
}


class PilotCollectionValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _objects(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = payload.get(key)
    if not isinstance(values, list) or not all(
        isinstance(item, dict) for item in values
    ):
        raise PilotCollectionValidationError(
            "INVALID_FIXTURE_COLLECTION", key
        )
    return values


def _write_json(path: Path, value: Any) -> None:
    path.write_text(dumps_strict(value, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(dumps_strict(value) + "\n")


def _markdown(report: dict[str, Any]) -> str:
    counts = report["fixture_counts"]
    outcomes = report["outcomes"]
    return "\n".join(
        (
            "# Stage 14 pilot collection readiness validation",
            "",
            f"- Technical judgment: `{report['technical_judgment']}`",
            f"- Participants / sessions / answers / file records: "
            f"{counts['participant_count']} / {counts['session_count']} / "
            f"{counts['answer_count']} / {counts['file_record_count']}",
            f"- Quality checks: {counts['quality_check_count']}",
            f"- Release eligible / blocked: "
            f"{outcomes['release_eligible_count']} / "
            f"{outcomes['release_blocked_count']}",
            f"- Excluded / withdrawn / recording required sessions: "
            f"{outcomes['excluded_session_count']} / "
            f"{outcomes['withdrawn_session_count']} / "
            f"{outcomes['recording_required_count']}",
            "",
            "All values are synthetic metadata fixtures. No person was recruited, "
            "no video was created or inspected, no file was deleted, and no "
            "dataset was frozen or operationally approved.",
            "",
        )
    )


class PilotCollectionReadinessValidator:
    OUTPUT_NAMES = (
        "validation_report.json",
        "validation_report.md",
        "fixture_pilot_sessions.jsonl",
        "fixture_quality_checks.jsonl",
        "fixture_manual_reviews.json",
        "fixture_withdrawal_results.json",
        "fixture_dataset_release_results.json",
    )

    def validate(
        self,
        *,
        fixture_path: str | Path = DEFAULT_FIXTURE,
        output_root: str | Path = DEFAULT_OUTPUT,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        payload = load_strict_json(fixture_path)
        if not isinstance(payload, dict):
            raise PilotCollectionValidationError(
                "INVALID_FIXTURE_ROOT", "pilot fixture must be an object"
            )
        try:
            protocol = PilotStudyProtocol(**payload["protocol"])
            enrollments = tuple(
                PilotParticipantEnrollment(**item)
                for item in _objects(payload, "enrollments")
            )
            consents = tuple(
                ConsentReference(**item)
                for item in _objects(payload, "consents")
            )
            checklists = tuple(
                RecordingChecklist(**item)
                for item in _objects(payload, "checklists")
            )
            raw_sessions = _objects(payload, "sessions")
            sessions = tuple(
                PilotSessionRun(
                    **{
                        **{
                            key: value for key, value in item.items()
                            if key != "quality_failure"
                        },
                        "exclusion_reasons": tuple(
                            item.get("exclusion_reasons") or ()
                        ),
                    }
                )
                for item in raw_sessions
            )
            reviews = tuple(
                ManualReviewDecision(
                    **{
                        **item,
                        "reason_codes": tuple(item.get("reason_codes") or ()),
                    }
                )
                for item in _objects(payload, "manual_reviews")
            )
            withdrawals = tuple(
                WithdrawalRequest(**item)
                for item in _objects(payload, "withdrawals")
            )
            assignments = tuple(
                DatasetSplitAssignment(**item)
                for item in _objects(payload, "split_assignments")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PilotCollectionValidationError(
                "FIXTURE_MODEL_VALIDATION_FAILED", str(exc)
            ) from exc

        consent_map = {item.consent_reference_id: item for item in consents}
        checklist_map = {item.checklist_id: item for item in checklists}
        review_map = {item.pilot_session_id: item for item in reviews}
        split_map = {item.participant_id: item for item in assignments}
        enrollment_map = {
            item.participant_id: item for item in enrollments
        }
        if any(
            len(mapping) != len(values)
            for mapping, values in (
                (consent_map, consents),
                (checklist_map, checklists),
                (enrollment_map, enrollments),
                (split_map, assignments),
            )
        ):
            raise PilotCollectionValidationError(
                "DUPLICATE_FIXTURE_IDENTIFIER", "registry duplicate"
            )
        if protocol.actual_collection_authorized:
            raise PilotCollectionValidationError(
                "ACTUAL_COLLECTION_PROHIBITED", protocol.pilot_protocol_id
            )

        answers: list[PilotAnswerRecord] = []
        files: list[RecordingFileRecord] = []
        quality_checks: list[CollectionQualityCheck] = []
        quality_summaries: dict[str, dict[str, object]] = {}
        for session_index, (session, raw_session) in enumerate(
            zip(sessions, raw_sessions), 1
        ):
            enrollment = enrollment_map.get(session.participant_id)
            consent = consent_map.get(session.consent_reference_id)
            checklist = checklist_map.get(session.checklist_id)
            if enrollment is None or checklist is None:
                raise PilotCollectionValidationError(
                    "PILOT_REFERENCE_MISSING", session.pilot_session_id
                )
            ready = recording_ready(checklist, consent)
            if session.status in {
                "READY", "RECORDING", "RECORDED", "VALIDATING",
                "MANUAL_REVIEW", "ANNOTATION_READY",
            } and not ready:
                raise PilotCollectionValidationError(
                    "SESSION_READY_WITH_FAILED_CHECKLIST",
                    session.pilot_session_id,
                )
            session_answers = (
                PilotAnswerRecord(
                    f"ANS_{(session_index * 2 - 1):06d}",
                    session.pilot_session_id,
                    "QUE_01", 2000, 5000,
                    f"TGT_{session_index:03d}",
                ),
                PilotAnswerRecord(
                    f"ANS_{(session_index * 2):06d}",
                    session.pilot_session_id,
                    "QUE_02", 5000, 8000,
                    f"TGT_{session_index:03d}",
                ),
            )
            if any(
                item.end_timestamp_ms > session.duration_ms
                for item in session_answers
            ):
                raise PilotCollectionValidationError(
                    "ANSWER_OUTSIDE_SESSION", session.pilot_session_id
                )
            if (
                session_answers[0].end_timestamp_ms
                > session_answers[1].start_timestamp_ms
            ):
                raise PilotCollectionValidationError(
                    "ANSWER_INTERVAL_OVERLAP", session.pilot_session_id
                )
            answers.extend(session_answers)
            for answer_index, answer in enumerate(session_answers, 1):
                record = RecordingFileRecord(
                    (
                        "data/pilot/incoming/"
                        f"{session.participant_id}_{session.pilot_session_id}_"
                        f"{answer.answer_id}.mp4"
                    ),
                    f"{session_index:x}" * 64,
                    1000000 + session_index * 1000 + answer_index,
                    f"2026-01-{session_index:02d}T10:0{answer_index}:00Z",
                    session.participant_id,
                    session.pilot_session_id,
                    answer.answer_id,
                    session.consent_reference_id,
                    "WITHDRAWAL_HOLD"
                    if session.status == "WITHDRAWN" else "INCOMING",
                )
                validate_recording_file_record(record)
                files.append(record)
            failure = raw_session.get("quality_failure")
            session_checks: list[CollectionQualityCheck] = []
            for check_index, check_type in enumerate(QualityCheckType, 1):
                status = "PASSED"
                reason = None
                if failure == "NOT_CHECKED":
                    status = "NOT_CHECKED"
                elif failure == check_type.value:
                    status = "FAILED"
                    reason = FAILURE_REASON_BY_CHECK[check_type.value]
                item = CollectionQualityCheck(
                    f"QC_{session_index:02d}_{check_index:02d}",
                    session.pilot_session_id,
                    check_type.value,
                    status,
                    reason,
                )
                session_checks.append(item)
                quality_checks.append(item)
            quality_summaries[session.pilot_session_id] = (
                validate_quality_checks(
                    session_checks,
                    pilot_session_id=session.pilot_session_id,
                )
            )

        withdrawal_results = [
            process_withdrawal(item, sessions, answers, files)
            for item in withdrawals
        ]
        withdrawn_participants = {
            item.participant_id for item in withdrawal_results
        }
        release_results = []
        for session_index, session in enumerate(sessions, 1):
            session_answers = tuple(
                item.answer_id for item in answers
                if item.pilot_session_id == session.pilot_session_id
            )
            candidate = DatasetReleaseCandidate(
                f"REL_{session_index:06d}",
                "DSM_STAGE14_PILOT",
                session.participant_id,
                session.pilot_session_id,
                session_answers,
                "DRAFT",
            )
            summary = quality_summaries[session.pilot_session_id]
            checks = [
                item for item in quality_checks
                if item.pilot_session_id == session.pilot_session_id
            ]
            by_type = {item.check_type: item for item in checks}
            release_results.append(
                evaluate_dataset_release_gate(
                    candidate,
                    consent=consent_map.get(session.consent_reference_id),
                    withdrawn=session.participant_id in withdrawn_participants,
                    file_hash_valid=(
                        by_type["VIDEO_HASH_VALID"].status == "PASSED"
                    ),
                    video_checks_passed=bool(
                        summary["release_quality_passed"]
                    ),
                    baseline_available=(
                        by_type["BASELINE_AVAILABLE"].status == "PASSED"
                    ),
                    answer_intervals_valid=(
                        by_type["ANSWER_INTERVALS_VALID"].status == "PASSED"
                    ),
                    manual_review=review_map.get(session.pilot_session_id),
                    split_assignment=split_map.get(session.participant_id),
                    split_leakage_detected=False,
                )
            )

        report = {
            "schema_version": "1.0",
            "status": "completed",
            "technical_judgment": TECHNICAL_JUDGMENT,
            "metadata_fixtures_only": True,
            "actual_people_recruited": False,
            "actual_video_created": False,
            "actual_file_deleted": False,
            "dataset_frozen": False,
            "operationally_approved": False,
            "split_leakage_detected": False,
            "fixture_counts": {
                "participant_count": len(enrollments),
                "consent_granted_count": sum(
                    item.status == "GRANTED" for item in consents
                ),
                "consent_withdrawn_count": sum(
                    item.status == "WITHDRAWN" for item in consents
                ),
                "session_count": len(sessions),
                "answer_count": len(answers),
                "file_record_count": len(files),
                "quality_check_count": len(quality_checks),
                "manual_review_count": len(reviews),
                "withdrawal_count": len(withdrawals),
            },
            "outcomes": {
                "release_eligible_count": sum(
                    item.eligible for item in release_results
                ),
                "release_blocked_count": sum(
                    not item.eligible for item in release_results
                ),
                "excluded_session_count": sum(
                    item.status == "EXCLUDED" for item in sessions
                ),
                "withdrawn_session_count": sum(
                    item.status == "WITHDRAWN" for item in sessions
                ),
                "recording_required_count": sum(
                    item.decision == "RECORDING_REQUIRED"
                    for item in reviews
                ),
                "file_hash_failure_count": sum(
                    item.check_type == "VIDEO_HASH_VALID"
                    and item.status == "FAILED"
                    for item in quality_checks
                ),
                "baseline_failure_count": sum(
                    item.check_type == "BASELINE_AVAILABLE"
                    and item.status == "FAILED"
                    for item in quality_checks
                ),
            },
            "limitations": [
                "No filesystem video existence, decoding, or media property check was performed.",
                "All paths and hashes are synthetic metadata fixtures.",
                "No file deletion, dataset freeze, threshold, score, or model training occurred.",
                "The result is not research validity, evaluation performance, or operational approval.",
            ],
            "outputs": list(self.OUTPUT_NAMES),
        }
        destination = Path(output_root).resolve()
        if destination.exists() and not overwrite:
            raise PilotCollectionValidationError(
                "OUTPUT_ALREADY_EXISTS", str(destination)
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = Path(
            tempfile.mkdtemp(prefix=".stage14.", dir=destination.parent)
        )
        try:
            _write_jsonl(
                staged / "fixture_pilot_sessions.jsonl",
                (
                    {
                        **session.to_dict(),
                        "recording_ready": recording_ready(
                            checklist_map[session.checklist_id],
                            consent_map.get(session.consent_reference_id),
                        ),
                    }
                    for session in sessions
                ),
            )
            _write_jsonl(
                staged / "fixture_quality_checks.jsonl",
                (item.to_dict() for item in quality_checks),
            )
            _write_json(
                staged / "fixture_manual_reviews.json",
                {
                    "schema_version": "1.0",
                    "reviews": [item.to_dict() for item in reviews],
                },
            )
            _write_json(
                staged / "fixture_withdrawal_results.json",
                {
                    "schema_version": "1.0",
                    "results": [
                        item.to_dict() for item in withdrawal_results
                    ],
                },
            )
            _write_json(
                staged / "fixture_dataset_release_results.json",
                {
                    "schema_version": "1.0",
                    "results": [item.to_dict() for item in release_results],
                },
            )
            _write_json(staged / "validation_report.json", report)
            (staged / "validation_report.md").write_text(
                _markdown(report), encoding="utf-8"
            )
            if destination.exists():
                for source in staged.iterdir():
                    os.replace(source, destination / source.name)
                staged.rmdir()
            else:
                os.replace(staged, destination)
            result = dict(report)
            result["output_sha256"] = {
                name: sha256_file(destination / name)
                for name in sorted(self.OUTPUT_NAMES)
            }
            return result
        except DataCollectionValidationError as exc:
            raise PilotCollectionValidationError(exc.code, str(exc)) from exc
        finally:
            if staged.exists():
                for item in staged.iterdir():
                    item.unlink()
                staged.rmdir()
