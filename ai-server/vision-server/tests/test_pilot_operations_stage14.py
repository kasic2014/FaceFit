from __future__ import annotations

import unittest

from app.vision.collection_quality_validator import validate_quality_checks
from app.vision.consent_models import ConsentReference
from app.vision.manual_review_models import ManualReviewDecision
from app.vision.pilot_collection_models import (
    CollectionQualityCheck,
    PilotAnswerRecord,
    PilotSessionRun,
    QualityCheckType,
    RecordingFileRecord,
)
from app.vision.pilot_session_state_machine import validate_session_transition
from app.vision.recording_checklist import RecordingChecklist, recording_ready
from app.vision.recording_file_validator import validate_recording_file_record


def granted_consent(**changes):
    values = {
        "consent_reference_id": "CNS_PILOT_000001",
        "participant_id": "PTC_000001",
        "status": "GRANTED",
        "document_version": "1.0",
        "video_collection_allowed": True,
        "automated_analysis_allowed": True,
        "research_use_allowed": True,
        "model_development_use_allowed": False,
    }
    values.update(changes)
    return ConsentReference(**values)


def checklist(**changes):
    values = {
        "checklist_id": "CHK_000001",
        "consent_status_granted": True,
        "video_collection_allowed": True,
        "automated_analysis_allowed": True,
        "research_use_allowed": True,
        "single_person_confirmed": True,
        "face_in_frame": True,
        "both_shoulders_in_frame": True,
        "camera_fixed": True,
        "lighting_checked": True,
        "microphone_checked": True,
        "storage_space_checked": True,
        "baseline_ready": True,
    }
    values.update(changes)
    return RecordingChecklist(**values)


def file_record(**changes):
    values = {
        "file_reference": (
            "data/pilot/incoming/"
            "PTC_000001_SES_000001_ANS_000001.mp4"
        ),
        "sha256": "1" * 64,
        "size_bytes": 1234,
        "created_at": "2026-01-01T10:00:00Z",
        "participant_id": "PTC_000001",
        "session_id": "SES_000001",
        "answer_id": "ANS_000001",
        "consent_reference_id": "CNS_PILOT_000001",
        "storage_status": "INCOMING",
    }
    values.update(changes)
    return RecordingFileRecord(**values)


class PilotOperationsStage14Tests(unittest.TestCase):
    def test_complete_checklist_and_consent_are_ready(self):
        self.assertTrue(recording_ready(checklist(), granted_consent()))

    def test_every_required_checklist_failure_blocks_ready(self):
        fields = tuple(
            key for key in checklist().to_dict()
            if key not in {"checklist_id", "all_required_passed"}
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertFalse(
                    recording_ready(checklist(**{field: False}), granted_consent())
                )

    def test_consent_purpose_denial_blocks_ready(self):
        self.assertFalse(
            recording_ready(
                checklist(),
                granted_consent(automated_analysis_allowed=False),
            )
        )
        self.assertFalse(recording_ready(checklist(), None))

    def test_allowed_session_transition_path(self):
        path = (
            "PLANNED", "READY", "RECORDING", "RECORDED", "VALIDATING",
            "MANUAL_REVIEW", "ANNOTATION_READY",
        )
        for current, target in zip(path, path[1:]):
            validate_session_transition(current, target)

    def test_forbidden_state_shortcuts_and_terminal_revival(self):
        for current, target in (
            ("PLANNED", "ANNOTATION_READY"),
            ("WITHDRAWN", "RECORDED"),
            ("FAILED", "ANNOTATION_READY"),
            ("EXCLUDED", "READY"),
        ):
            with self.subTest(current=current, target=target), self.assertRaises(
                ValueError
            ):
                validate_session_transition(current, target)

    def test_manual_review_can_request_new_planned_recording(self):
        validate_session_transition("MANUAL_REVIEW", "PLANNED")

    def test_file_record_accepts_pseudonymous_filename(self):
        value = file_record()
        validate_recording_file_record(value)

    def test_filename_rejects_personal_tokens_and_wrong_shape(self):
        for name in (
            "PTC_000001_SES_000001_ANS_000001_EMAIL.mp4",
            "Alice_SES_000001_ANS_000001.mp4",
            "PTC_000001_SES_000001.mp4",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_recording_file_record(
                    file_record(
                        file_reference=f"data/pilot/incoming/{name}"
                    )
                )

    def test_file_reference_rejects_absolute_and_traversal(self):
        for path in (
            "C:/data/pilot/incoming/PTC_000001_SES_000001_ANS_000001.mp4",
            "data/pilot/incoming/../PTC_000001_SES_000001_ANS_000001.mp4",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_recording_file_record(file_record(file_reference=path))

    def test_hash_and_size_are_validated(self):
        with self.assertRaises(ValueError):
            file_record(sha256="bad")
        with self.assertRaises(ValueError):
            file_record(size_bytes=0)

    def test_filename_references_must_match_metadata(self):
        with self.assertRaises(ValueError):
            validate_recording_file_record(
                file_record(answer_id="ANS_000002")
            )

    def test_baseline_and_answer_use_exclusive_interval_contract(self):
        session = PilotSessionRun(
            "SES_000001", "PTC_000001", "CNS_PILOT_000001",
            "CHK_000001", "PLANNED", 9000, 0, 2000,
        )
        answer = PilotAnswerRecord(
            "ANS_000001", "SES_000001", "QUE_01",
            2000, 5000, "TGT_001",
        )
        self.assertFalse(session.baseline_interval().contains(2000))
        self.assertTrue(answer.answer_sample().as_analysis_interval().contains(4999))
        self.assertFalse(answer.answer_sample().as_analysis_interval().contains(5000))

    def test_invalid_baseline_and_answer_are_rejected(self):
        with self.assertRaises(ValueError):
            PilotSessionRun(
                "SES_000001", "PTC_000001", "CNS_PILOT_000001",
                "CHK_000001", "PLANNED", 9000, 2000, 2000,
            )
        with self.assertRaises(ValueError):
            PilotAnswerRecord(
                "ANS_000001", "SES_000001", "QUE_01",
                5000, 5000, "TGT_001",
            )

    def test_quality_requires_all_eleven_unique_checks(self):
        values = tuple(
            CollectionQualityCheck(
                f"QC_01_{index:02d}", "SES_000001",
                check.value, "PASSED", None,
            )
            for index, check in enumerate(QualityCheckType, 1)
        )
        result = validate_quality_checks(values, pilot_session_id="SES_000001")
        self.assertTrue(result["release_quality_passed"])
        with self.assertRaises(ValueError):
            validate_quality_checks(values[:-1], pilot_session_id="SES_000001")

    def test_failed_warning_and_not_checked_quality_are_safe(self):
        base = [
            CollectionQualityCheck(
                f"QC_01_{index:02d}", "SES_000001",
                check.value, "PASSED", None,
            )
            for index, check in enumerate(QualityCheckType, 1)
        ]
        base[0] = CollectionQualityCheck(
            "QC_01_01", "SES_000001", "VIDEO_FILE_EXISTS",
            "WARNING", None,
        )
        result = validate_quality_checks(base, pilot_session_id="SES_000001")
        self.assertFalse(result["release_quality_passed"])
        self.assertFalse(result["warning_is_user_posture_failure"])
        with self.assertRaises(ValueError):
            CollectionQualityCheck(
                "QC_01_01", "SES_000001", "VIDEO_FILE_EXISTS",
                "FAILED", None,
            )

    def test_manual_review_uses_only_operational_decisions(self):
        ManualReviewDecision(
            "REV_001", "SES_000001", "REVIEWER_001",
            "APPROVED_FOR_ANNOTATION", (),
            "2026-01-01T10:00:00Z", None,
        )
        with self.assertRaises(ValueError):
            ManualReviewDecision(
                "REV_001", "SES_000001", "REVIEWER_001",
                "PASS", (), "2026-01-01T10:00:00Z", None,
            )


if __name__ == "__main__":
    unittest.main()
