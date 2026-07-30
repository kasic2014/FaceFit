from __future__ import annotations

import unittest

from app.vision.consent_models import ConsentReference
from app.vision.dataset_manifest_models import DatasetSplitAssignment
from app.vision.dataset_release_gate import evaluate_dataset_release_gate
from app.vision.manual_review_models import ManualReviewDecision
from app.vision.pilot_collection_models import (
    DatasetReleaseCandidate,
    PilotAnswerRecord,
    PilotSessionRun,
    RecordingFileRecord,
    WithdrawalRequest,
)
from app.vision.withdrawal_processor import process_withdrawal


class WithdrawalReleaseStage14Tests(unittest.TestCase):
    def setUp(self):
        self.consent = ConsentReference(
            "CNS_PILOT_000001", "PTC_000001", "GRANTED", "1.0",
            True, True, True, False,
        )
        self.session = PilotSessionRun(
            "SES_000001", "PTC_000001", "CNS_PILOT_000001",
            "CHK_000001", "ANNOTATION_READY", 9000, 0, 2000,
        )
        self.answers = (
            PilotAnswerRecord(
                "ANS_000001", "SES_000001", "QUE_01",
                2000, 5000, "TGT_001",
            ),
        )
        self.file = RecordingFileRecord(
            "data/pilot/incoming/PTC_000001_SES_000001_ANS_000001.mp4",
            "1" * 64, 1000, "2026-01-01T10:00:00Z",
            "PTC_000001", "SES_000001", "ANS_000001",
            "CNS_PILOT_000001", "INCOMING",
        )
        self.review = ManualReviewDecision(
            "REV_001", "SES_000001", "REVIEWER_001",
            "APPROVED_FOR_ANNOTATION", (),
            "2026-01-01T10:00:00Z", None,
        )
        self.split = DatasetSplitAssignment(
            "PTC_000001", "VALIDATION", 13,
            "PARTICIPANT_LEVEL_DETERMINISTIC",
        )
        self.candidate = DatasetReleaseCandidate(
            "REL_000001", "DSM_PILOT", "PTC_000001",
            "SES_000001", ("ANS_000001",), "DRAFT",
        )

    def gate(self, **changes):
        values = {
            "consent": self.consent,
            "withdrawn": False,
            "file_hash_valid": True,
            "video_checks_passed": True,
            "baseline_available": True,
            "answer_intervals_valid": True,
            "manual_review": self.review,
            "split_assignment": self.split,
            "split_leakage_detected": False,
        }
        values.update(changes)
        return evaluate_dataset_release_gate(self.candidate, **values)

    def test_complete_release_candidate_is_eligible_but_not_frozen(self):
        result = self.gate()
        self.assertTrue(result.eligible)
        self.assertEqual(result.result_status, "PILOT_CANDIDATE")
        self.assertFalse(result.dataset_frozen)
        self.assertFalse(result.operationally_approved)

    def test_each_release_gate_failure_blocks_candidate(self):
        cases = {
            "consent": None,
            "withdrawn": True,
            "file_hash_valid": False,
            "video_checks_passed": False,
            "baseline_available": False,
            "answer_intervals_valid": False,
            "manual_review": None,
            "split_assignment": None,
            "split_leakage_detected": True,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                result = self.gate(**{field: value})
                self.assertFalse(result.eligible)
                self.assertEqual(result.result_status, "REVIEW_REQUIRED")

    def test_split_participant_mismatch_blocks_candidate(self):
        wrong = DatasetSplitAssignment(
            "PTC_000002", "VALIDATION", 13,
            "PARTICIPANT_LEVEL_DETERMINISTIC",
        )
        self.assertFalse(self.gate(split_assignment=wrong).eligible)

    def test_withdrawal_blocks_all_linked_uses_without_deletion(self):
        request = WithdrawalRequest(
            "WDR_000001", "PTC_000001", "CNS_PILOT_000001",
            "2026-01-02T10:00:00Z", "QUARANTINED",
        )
        result = process_withdrawal(
            request, (self.session,), self.answers, (self.file,)
        )
        self.assertEqual(result.participant_status, "WITHDRAWN")
        self.assertEqual(result.blocked_session_ids, ("SES_000001",))
        self.assertEqual(result.blocked_answer_ids, ("ANS_000001",))
        self.assertTrue(result.annotation_use_blocked)
        self.assertTrue(result.manifest_use_blocked)
        self.assertFalse(result.actual_file_deleted)

    def test_withdrawal_disposition_is_restricted(self):
        with self.assertRaises(ValueError):
            WithdrawalRequest(
                "WDR_000001", "PTC_000001", "CNS_PILOT_000001",
                "2026-01-02T10:00:00Z", "DELETE_NOW",
            )

    def test_release_status_cannot_be_frozen_or_approved(self):
        for status in ("FROZEN", "APPROVED"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                DatasetReleaseCandidate(
                    "REL_000001", "DSM_PILOT", "PTC_000001",
                    "SES_000001", ("ANS_000001",), status,
                )


if __name__ == "__main__":
    unittest.main()
