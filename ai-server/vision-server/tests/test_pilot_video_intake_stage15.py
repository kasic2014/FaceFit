from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.vision.dataset_release_gate import evaluate_dataset_release_gate
from app.vision.pilot_collection_models import DatasetReleaseCandidate
from app.vision.pilot_video_intake import (
    PilotVideoIntakeError,
    assert_no_forbidden_semantics,
    load_strict_json,
    parse_ffprobe_json,
    sha256_file,
    validate_consent,
    validate_metadata,
    write_strict_json,
)


class PilotVideoIntakeStage15Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.consent = {
            "schema_version": "1.0.0",
            "consent_reference_id": "CONSENT_PTC_000001_V1",
            "participant_id": "PTC_000001",
            "consent_status": "GRANTED",
            "video_collection_allowed": True,
            "automated_analysis_allowed": True,
            "research_use_allowed": True,
            "model_development_use_allowed": False,
            "consented_at": "2026-07-29T19:31:57+09:00",
            "withdrawn_at": None,
        }
        self.metadata = {
            "participant_id": "PTC_000001",
            "session_id": "SES_000001",
            "consent_reference_id": "CONSENT_PTC_000001_V1",
            "video_file": "PTC_000001_SES_000001.mp4",
            "expected_sha256": "a" * 64,
            "baseline_interval": {
                "interval_id": "BASELINE_001",
                "start_timestamp_ms": 0,
                "end_timestamp_ms": 10_000,
            },
            "answers": [
                {
                    "answer_id": "ANS_000001",
                    "interval_id": "INT_ANSWER_001",
                    "start_timestamp_ms": 11_000,
                    "end_timestamp_ms": 50_000,
                },
                {
                    "answer_id": "ANS_000002",
                    "interval_id": "INT_ANSWER_002",
                    "start_timestamp_ms": 51_000,
                    "end_timestamp_ms": 107_000,
                },
            ],
            "withdrawn": False,
        }

    def test_strict_loader_rejects_duplicate_key_and_non_finite(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(PilotVideoIntakeError, "Duplicate"):
                load_strict_json(path)
            path.write_text('{"a":NaN}', encoding="utf-8")
            with self.assertRaises(PilotVideoIntakeError):
                load_strict_json(path)

    def test_strict_writer_rejects_non_finite(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(PilotVideoIntakeError):
                write_strict_json(Path(folder) / "bad.json", {"value": float("inf")})

    def test_consent_contract(self) -> None:
        self.assertTrue(validate_consent(self.consent)["valid"])
        denied = dict(self.consent, research_use_allowed=False)
        self.assertFalse(validate_consent(denied)["valid"])

    def test_metadata_reference_integrity_and_half_open_intervals(self) -> None:
        result = validate_metadata(
            self.metadata,
            self.consent,
            expected_video_filename=self.metadata["video_file"],
            duration_ms=120_000,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["interval_rule"], "[start, end)")

    def test_metadata_rejects_duplicate_overlap_and_duration_overrun(self) -> None:
        broken = json.loads(json.dumps(self.metadata))
        broken["answers"][1].update({
            "answer_id": "ANS_000001",
            "interval_id": "INT_ANSWER_001",
            "start_timestamp_ms": 49_000,
            "end_timestamp_ms": 121_000,
        })
        result = validate_metadata(
            broken,
            self.consent,
            expected_video_filename=broken["video_file"],
            duration_ms=120_000,
        )
        self.assertFalse(result["valid"])
        codes = {
            code
            for item in result["interval_errors"]
            for code in item["errors"]
        }
        self.assertIn("DUPLICATE_ANSWER_ID", codes)
        self.assertIn("DUPLICATE_INTERVAL_ID", codes)
        self.assertIn("INTERVAL_EXCEEDS_VIDEO_DURATION", codes)

    def test_sha256_match_and_mismatch_are_comparable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "value.bin"
            path.write_bytes(b"face-fit")
            actual = sha256_file(path)
            self.assertEqual(
                actual,
                "f04346e8cc2f7adbc953aaff9b8593355e6ca093e1874e128e639a7124fb880b",
            )
            self.assertNotEqual(actual, "0" * 64)

    def test_ffprobe_parser(self) -> None:
        parsed = parse_ffprobe_json({
            "streams": [
                {
                    "codec_type": "video", "codec_name": "hevc",
                    "width": 1920, "height": 1080,
                    "avg_frame_rate": "30000/1001",
                    "nb_frames": "5775", "duration": "192.735",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"duration": "192.735"},
        })
        self.assertEqual(parsed["codec"], "hevc")
        self.assertEqual(parsed["frame_count"], 5775)
        self.assertTrue(parsed["audio_stream_present"])

    def test_stage14_gate_requires_manual_review_and_split(self) -> None:
        candidate = DatasetReleaseCandidate(
            "RELEASE_001", "MANIFEST_001", "PTC_000001", "SES_000001",
            ("ANS_000001",), "REVIEW_REQUIRED",
        )
        result = evaluate_dataset_release_gate(
            candidate,
            consent=None,
            withdrawn=False,
            file_hash_valid=True,
            video_checks_passed=True,
            baseline_available=True,
            answer_intervals_valid=True,
            manual_review=None,
            split_assignment=None,
            split_leakage_detected=False,
        )
        self.assertFalse(result.eligible)
        self.assertIn("MANUAL_REVIEW_NOT_APPROVED", result.failed_conditions)
        self.assertIn("PARTICIPANT_SPLIT_MISSING", result.failed_conditions)
        self.assertFalse(result.dataset_frozen)

    def test_forbidden_semantic_fields(self) -> None:
        assert_no_forbidden_semantics({"availability": 1.0})
        with self.assertRaises(PilotVideoIntakeError):
            assert_no_forbidden_semantics({"personality": "x"})


if __name__ == "__main__":
    unittest.main()
