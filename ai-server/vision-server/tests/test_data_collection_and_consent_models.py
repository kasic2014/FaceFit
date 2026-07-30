from __future__ import annotations

import unittest

from app.vision.consent_models import (
    ConsentPurpose,
    ConsentReference,
    evaluate_consent_gate,
)
from app.vision.data_collection_models import (
    AnswerSample,
    DataCollectionProtocol,
    RecordingEnvironment,
    RecordingSession,
    ResearchParticipant,
)


def consent(**changes):
    values = {
        "consent_reference_id": "CNS_000001",
        "participant_id": "PTC_000001",
        "status": "GRANTED",
        "document_version": "1.0",
        "video_collection_allowed": True,
        "automated_analysis_allowed": True,
        "research_use_allowed": True,
        "model_development_use_allowed": True,
    }
    values.update(changes)
    return ConsentReference(**values)


class DataCollectionAndConsentModelTests(unittest.TestCase):
    def test_participant_accepts_only_pseudonymous_id(self):
        ResearchParticipant("PTC_000001", "TEST_FIXTURE", "CNS_000001")
        with self.assertRaises(ValueError):
            ResearchParticipant("Alice", "TEST_FIXTURE", "CNS_000001")

    def test_protocol_accepts_exact_facefit_scope(self):
        value = DataCollectionProtocol(
            "DCP_FACE_FIT_001",
            "1.0.0",
            "DRAFT",
            True,
            True,
            True,
            True,
            ("FACE", "NOSE", "LEFT_SHOULDER", "RIGHT_SHOULDER"),
            ("HANDS", "PELVIS"),
            "Fixture validation",
        )
        self.assertTrue(value.single_person_only)

    def test_protocol_rejects_lower_body_scope(self):
        with self.assertRaises(ValueError):
            DataCollectionProtocol(
                "DCP_FACE_FIT_001", "1.0.0", "DRAFT",
                True, True, True, True,
                ("FACE", "LEFT_SHOULDER", "RIGHT_SHOULDER", "PELVIS"),
                (), "Fixture validation",
            )

    def test_protocol_requires_fixed_camera_and_baseline(self):
        with self.assertRaises(ValueError):
            DataCollectionProtocol(
                "DCP_FACE_FIT_001", "1.0.0", "DRAFT",
                True, False, True, True,
                ("FACE", "LEFT_SHOULDER", "RIGHT_SHOULDER"),
                (), "Fixture validation",
            )

    def test_environment_separates_source_and_analysis_fps(self):
        value = RecordingEnvironment(
            "ENV_FIXED_01", 1280, 720, 30.0, 5.0,
            True, True, False, True,
        )
        self.assertEqual(value.analysis_fps, 5.0)
        self.assertFalse(value.stored_video_mirrored)

    def test_environment_rejects_nonfinite_or_excess_analysis_fps(self):
        for value in (float("nan"), float("inf"), 31.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RecordingEnvironment(
                    "ENV_FIXED_01", 1280, 720, 30.0, value,
                    True, True, False, True,
                )

    def test_session_validates_baseline_and_hash(self):
        value = RecordingSession(
            "SES_000001", "PTC_000001", "DCP_FACE_FIT_001",
            "CNS_000001", "ENV_FIXED_01", "ANNOTATION_READY",
            9000, 0, 2000, "1" * 64,
        )
        self.assertEqual(value.baseline_end_timestamp_ms, 2000)
        with self.assertRaises(ValueError):
            RecordingSession(
                "SES_000001", "PTC_000001", "DCP_FACE_FIT_001",
                "CNS_000001", "ENV_FIXED_01", "ANNOTATION_READY",
                9000, 0, 2000, "bad",
            )

    def test_excluded_session_requires_coded_reason(self):
        with self.assertRaises(ValueError):
            RecordingSession(
                "SES_000001", "PTC_000001", "DCP_FACE_FIT_001",
                "CNS_000001", "ENV_FIXED_01", "EXCLUDED",
                9000, 0, 2000, "1" * 64,
            )

    def test_answer_reuses_stage10_exclusive_interval(self):
        value = AnswerSample(
            "ANS_000001", "SES_000001", "QUE_01",
            2000, 5000, "TGT_001",
        )
        interval = value.as_analysis_interval()
        self.assertTrue(interval.contains(4999))
        self.assertFalse(interval.contains(5000))
        self.assertEqual(interval.interval_type, "ANSWER")

    def test_answer_rejects_zero_duration(self):
        with self.assertRaises(ValueError):
            AnswerSample(
                "ANS_000001", "SES_000001", "QUE_01",
                2000, 2000, "TGT_001",
            )

    def test_all_four_consent_purposes_are_allowed(self):
        value = consent()
        self.assertTrue(
            all(
                evaluate_consent_gate(value, purpose.value).allowed
                for purpose in ConsentPurpose
            )
        )

    def test_missing_pending_withdrawn_and_expired_are_denied(self):
        self.assertFalse(
            evaluate_consent_gate(
                None, ConsentPurpose.RESEARCH_USE.value
            ).allowed
        )
        for status in ("PENDING", "EXPIRED", "INVALID"):
            with self.subTest(status=status):
                self.assertFalse(
                    evaluate_consent_gate(
                        consent(status=status),
                        ConsentPurpose.RESEARCH_USE.value,
                    ).allowed
                )
        self.assertFalse(
            evaluate_consent_gate(
                consent(status="WITHDRAWN", withdrawn_at="2026-01-01"),
                ConsentPurpose.RESEARCH_USE.value,
            ).allowed
        )

    def test_partial_consent_rejects_unauthorized_purpose(self):
        gate = evaluate_consent_gate(
            consent(
                status="PARTIALLY_GRANTED",
                model_development_use_allowed=False,
            ),
            ConsentPurpose.MODEL_DEVELOPMENT.value,
        )
        self.assertFalse(gate.allowed)
        self.assertEqual(gate.reason, "PURPOSE_NOT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
