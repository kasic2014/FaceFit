from __future__ import annotations

import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from app.vision.pilot_session_intake_queue import (
    OUTPUT_NAMES,
    STAGE_TRANSITION_CONTRACT,
    ExistingBatchIndex,
    IntakeQueue,
    PilotSessionIntakeError,
    build_pilot_session_intake_queue,
    discover_session_candidates,
    intake_template,
    load_intake_queue,
)
from app.vision.pilot_video_intake import (
    load_strict_json,
    sha256_file,
    write_strict_json,
)


GENERATED_AT = "2026-07-30T23:00:00+09:00"
EXISTING_PARTICIPANT = "PTC_900001"
EXISTING_SESSION = "SES_900001"
FIXTURE_PARTICIPANT = "PTC_990001"
FIXTURE_SESSION = "SES_990001"
EXISTING_VIDEO_BYTES = b"stage21-existing-video-fixture"
EXISTING_VIDEO_SHA = hashlib.sha256(EXISTING_VIDEO_BYTES).hexdigest()


class PilotSessionIntakeQueueStage21Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.incoming = self.root / "incoming"
        self.incoming.mkdir()
        self.batch_sessions = self.root / "pilot_batch_sessions.json"
        self.split_validation = self.root / "participant_split_validation.json"
        self.fixture_registry = self.root / "pilot_registry.fixture.json"
        write_strict_json(
            self.batch_sessions,
            {
                "batch_id": "PILOT_ANNOTATION_BATCH_001",
                "actual_participant_created": False,
                "actual_session_created": False,
                "sessions": [
                    {
                        "participant_id": EXISTING_PARTICIPANT,
                        "session_id": EXISTING_SESSION,
                        "split_name": "DEVELOPMENT",
                        "video_sha256": EXISTING_VIDEO_SHA,
                    }
                ],
            },
        )
        write_strict_json(
            self.split_validation,
            {
                "participant_split_assignments": {
                    EXISTING_PARTICIPANT: "DEVELOPMENT"
                },
                "leakage_detected": False,
            },
        )
        write_strict_json(
            self.fixture_registry,
            {
                "enrollments": [{"participant_id": FIXTURE_PARTICIPANT}],
                "sessions": [{"pilot_session_id": FIXTURE_SESSION}],
            },
        )
        self.index = ExistingBatchIndex.from_files(
            self.batch_sessions,
            self.split_validation,
            self.fixture_registry,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _create_set(
        self,
        participant_id="PTC_900100",
        session_id="SES_900100",
        *,
        include=("mp4", "consent", "metadata"),
        video_bytes=b"stage21-new-video-fixture",
        consent_updates=None,
        metadata_updates=None,
    ):
        stem = f"{participant_id}_{session_id}"
        video_path = self.incoming / f"{stem}.mp4"
        consent_path = self.incoming / f"{stem}.consent.json"
        metadata_path = self.incoming / f"{stem}.metadata.json"
        video_sha = hashlib.sha256(video_bytes).hexdigest()
        consent = {
            "schema_version": "1.0.0",
            "consent_reference_id": f"CONSENT_{participant_id}_FIXTURE",
            "participant_id": participant_id,
            "consent_status": "GRANTED",
            "video_collection_allowed": True,
            "automated_analysis_allowed": True,
            "research_use_allowed": True,
            "model_development_use_allowed": False,
            "consented_at": GENERATED_AT,
            "withdrawn_at": None,
        }
        metadata = {
            "participant_id": participant_id,
            "session_id": session_id,
            "consent_reference_id": consent["consent_reference_id"],
            "video_file": video_path.name,
            "expected_sha256": video_sha,
            "baseline_interval": {
                "interval_id": "BASELINE_FIXTURE",
                "start_timestamp_ms": 0,
                "end_timestamp_ms": 1000,
            },
            "answers": [
                {
                    "answer_id": "ANS_900001",
                    "interval_id": "INT_FIXTURE_001",
                    "start_timestamp_ms": 1000,
                    "end_timestamp_ms": 2000,
                },
                {
                    "answer_id": "ANS_900002",
                    "interval_id": "INT_FIXTURE_002",
                    "start_timestamp_ms": 2000,
                    "end_timestamp_ms": 3000,
                },
            ],
            "withdrawn": False,
        }
        if consent_updates:
            consent.update(consent_updates)
        if metadata_updates:
            metadata.update(metadata_updates)
        if "mp4" in include:
            video_path.write_bytes(video_bytes)
        if "consent" in include:
            write_strict_json(consent_path, consent)
        if "metadata" in include:
            write_strict_json(metadata_path, metadata)
        return video_path, consent_path, metadata_path

    def _discover_one(self):
        candidates, discovery = discover_session_candidates(
            self.incoming, self.index
        )
        self.assertEqual(1, len(candidates))
        return candidates[0], discovery

    def _build(self, name="output"):
        output = self.root / name
        report = build_pilot_session_intake_queue(
            incoming_dir=self.incoming,
            batch_sessions_path=self.batch_sessions,
            split_validation_path=self.split_validation,
            fixture_registry_path=self.fixture_registry,
            output_dir=output,
            generated_at=GENERATED_AT,
        )
        return output, report

    def test_no_new_inputs_is_valid_awaiting_state(self):
        output, report = self._build()
        queue = load_intake_queue(output / "pilot_session_intake_queue.json")
        self.assertTrue(report["valid"])
        self.assertEqual("awaiting_additional_pilot_sessions", queue.final_status)
        self.assertEqual(0, len(queue.session_candidates))
        self.assertEqual(set(OUTPUT_NAMES), {item.name for item in output.iterdir()})

    def test_complete_input_set_is_ready_for_stage15_only(self):
        self._create_set()
        candidate, _ = self._discover_one()
        self.assertEqual("READY_FOR_INTAKE_VALIDATION", candidate.input_set_status)
        self.assertEqual("STAGE_15", candidate.next_required_stage)
        self.assertFalse(candidate.batch_registration_eligible)
        self.assertIn("STAGE_15_NOT_COMPLETED", candidate.blocking_reasons)

    def test_stage_transition_contract_is_declared_but_not_executed(self):
        self.assertEqual(
            {
                "READY_FOR_INTAKE_VALIDATION": "STAGE_15",
                "STAGE_15_PASSED": "STAGE_16",
                "MANUAL_REVIEW_PASSED": "STAGE_17",
                "ANNOTATION_READY": "STAGE_18",
            },
            STAGE_TRANSITION_CONTRACT,
        )
        output, _ = self._build()
        validation = load_strict_json(output / "input_set_validation.json")
        self.assertEqual(
            STAGE_TRANSITION_CONTRACT,
            validation["stage_transition_contract"],
        )
        self.assertFalse(validation["stage_transition_executed"])

    def test_missing_video_is_recorded(self):
        self._create_set(include=("consent", "metadata"))
        candidate, _ = self._discover_one()
        self.assertEqual("MISSING_VIDEO", candidate.input_set_status)
        self.assertIn("VIDEO_FILE_MISSING", candidate.blocking_reasons)

    def test_missing_consent_is_recorded(self):
        self._create_set(include=("mp4", "metadata"))
        candidate, _ = self._discover_one()
        self.assertEqual("MISSING_CONSENT", candidate.input_set_status)
        self.assertIn("CONSENT_FILE_MISSING", candidate.blocking_reasons)

    def test_missing_metadata_is_recorded(self):
        self._create_set(include=("mp4", "consent"))
        candidate, _ = self._discover_one()
        self.assertEqual("MISSING_METADATA", candidate.input_set_status)
        self.assertIn("METADATA_FILE_MISSING", candidate.blocking_reasons)

    def test_filename_and_internal_id_mismatch_is_blocked(self):
        self._create_set(metadata_updates={"session_id": "SES_900999"})
        candidate, _ = self._discover_one()
        self.assertEqual("REFERENCE_MISMATCH", candidate.input_set_status)
        self.assertIn(
            "METADATA_SESSION_FILENAME_MISMATCH", candidate.blocking_reasons
        )

    def test_consent_withdrawal_is_blocked(self):
        self._create_set(
            consent_updates={
                "consent_status": "WITHDRAWN",
                "withdrawn_at": GENERATED_AT,
            }
        )
        candidate, _ = self._discover_one()
        self.assertEqual("WITHDRAWN", candidate.input_set_status)
        self.assertEqual("WITHDRAWN", candidate.consent_status)

    def test_video_sha_mismatch_is_blocked(self):
        self._create_set(metadata_updates={"expected_sha256": "0" * 64})
        candidate, _ = self._discover_one()
        self.assertEqual("HASH_MISMATCH", candidate.input_set_status)
        self.assertIn("VIDEO_SHA256_MISMATCH", candidate.blocking_reasons)

    def test_duplicate_session_id_is_blocked(self):
        self._create_set(
            participant_id="PTC_900200",
            session_id=EXISTING_SESSION,
        )
        candidate, _ = self._discover_one()
        self.assertEqual("DUPLICATE_SESSION", candidate.input_set_status)
        self.assertIn("DUPLICATE_SESSION_ID", candidate.blocking_reasons)

    def test_duplicate_video_sha_is_blocked(self):
        self._create_set(video_bytes=EXISTING_VIDEO_BYTES)
        candidate, _ = self._discover_one()
        self.assertEqual("DUPLICATE_SESSION", candidate.input_set_status)
        self.assertIn("DUPLICATE_VIDEO_SHA256", candidate.blocking_reasons)

    def test_fixture_identity_is_blocked_from_real_intake(self):
        self._create_set(
            participant_id=FIXTURE_PARTICIPANT,
            session_id=FIXTURE_SESSION,
        )
        candidate, _ = self._discover_one()
        self.assertEqual("REFERENCE_MISMATCH", candidate.input_set_status)
        self.assertIn(
            "FIXTURE_ID_NOT_ALLOWED_FOR_REAL_SESSION",
            candidate.blocking_reasons,
        )

    def test_existing_participant_split_is_preserved(self):
        self._create_set(
            participant_id=EXISTING_PARTICIPANT,
            session_id="SES_900002",
        )
        candidate, _ = self._discover_one()
        self.assertEqual("EXISTING_SPLIT_PRESERVED", candidate.split_status)
        self.assertEqual("DEVELOPMENT", candidate.proposed_split)

    def test_new_participant_split_requires_review(self):
        self._create_set()
        candidate, _ = self._discover_one()
        self.assertEqual("REVIEW_REQUIRED", candidate.split_status)
        self.assertEqual("DEVELOPMENT", candidate.proposed_split)
        self.assertIn("SPLIT_APPROVAL_REQUIRED", candidate.blocking_reasons)

    def test_existing_registered_input_set_is_not_requeued(self):
        self._create_set(
            participant_id=EXISTING_PARTICIPANT,
            session_id=EXISTING_SESSION,
            video_bytes=EXISTING_VIDEO_BYTES,
        )
        candidates, discovery = discover_session_candidates(
            self.incoming, self.index
        )
        self.assertEqual([], candidates)
        self.assertEqual(1, discovery["existing_registered_input_set_count"])

    def test_existing_batch_is_not_modified_and_no_stage_runs(self):
        self._create_set()
        before = {
            path: sha256_file(path)
            for path in (self.batch_sessions, self.split_validation)
        }
        output, _ = self._build()
        after = {
            path: sha256_file(path)
            for path in (self.batch_sessions, self.split_validation)
        }
        self.assertEqual(before, after)
        status = load_strict_json(output / "intake_status.json")
        registration = load_strict_json(
            output / "batch_registration_candidates.json"
        )
        self.assertFalse(status["stages_15_to_18_executed"])
        self.assertFalse(registration["existing_batch_modified"])
        self.assertFalse(registration["registration_executed"])
        self.assertEqual(0, registration["eligible_count"])

    def test_overlapping_answer_intervals_are_blocked(self):
        answers = [
            {
                "answer_id": "ANS_900001",
                "interval_id": "INT_FIXTURE_001",
                "start_timestamp_ms": 1000,
                "end_timestamp_ms": 2200,
            },
            {
                "answer_id": "ANS_900002",
                "interval_id": "INT_FIXTURE_002",
                "start_timestamp_ms": 2000,
                "end_timestamp_ms": 3000,
            },
        ]
        self._create_set(metadata_updates={"answers": answers})
        candidate, _ = self._discover_one()
        self.assertEqual("REFERENCE_MISMATCH", candidate.input_set_status)
        self.assertIn("ANSWER_INTERVAL_OVERLAP", candidate.blocking_reasons)

    def test_invalid_filename_is_recorded_without_entity_creation(self):
        (self.incoming / "participant-name_SES_900100.mp4").write_bytes(b"fixture")
        candidate, _ = self._discover_one()
        self.assertEqual("INVALID_FILENAME", candidate.input_set_status)
        self.assertIsNone(candidate.participant_id)
        self.assertIsNone(candidate.session_id)

    def test_strict_queue_rejects_extra_fields_and_non_finite_values(self):
        output, _ = self._build()
        value = load_strict_json(output / "pilot_session_intake_queue.json")
        extra = copy.deepcopy(value)
        extra["unexpected"] = True
        with self.assertRaises(PilotSessionIntakeError):
            IntakeQueue.from_dict(extra)
        for invalid in (math.nan, math.inf, -math.inf):
            broken = copy.deepcopy(value)
            broken["generated_metric"] = invalid
            with self.assertRaises(ValueError):
                IntakeQueue.from_dict(broken)

    def test_strict_json_outputs_and_protected_hashes(self):
        self._create_set()
        protected = [
            *self.incoming.iterdir(),
            self.batch_sessions,
            self.split_validation,
            self.fixture_registry,
        ]
        before = {path: sha256_file(path) for path in protected}
        output, report = self._build()
        for name in OUTPUT_NAMES:
            if name.endswith(".json"):
                load_strict_json(output / name)
        after = {path: sha256_file(path) for path in protected}
        self.assertEqual(before, after)
        self.assertTrue(report["checks"]["protected_source_hashes_unchanged"])

    def test_empty_template_contains_no_real_values(self):
        template = intake_template()
        self.assertIsNone(template["participant_id"])
        self.assertIsNone(template["session_id"])
        self.assertIsNone(template["video_reference"])
        self.assertIsNone(template["consent_reference"])
        self.assertIsNone(template["metadata_reference"])
        self.assertNotIn("events", template)


if __name__ == "__main__":
    unittest.main()
