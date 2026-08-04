"""Stage 28 contract, validator, client, and orchestration tests."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


AI_SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(AI_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVER_ROOT))

from integration.contracts.common_contracts import (
    IntegrationContractError,
    atomic_write_json,
    deduplicate_warnings,
    map_component_status,
    map_job_status,
    normalize_error,
    normalize_warning,
    strict_json_bytes,
    validate_answer_id,
    validate_public_payload,
    validate_session_id,
)
from integration.contracts.integrated_session_contract import build_integrated_session
from integration.scripts.run_integrated_session import parser as cli_parser
from integration.services.ai_api_client import AiApiClient, AiApiClientConfig
from integration.services.integrated_session_service import IntegratedSessionService
from integration.services.integration_validator import validate_integration_inputs


ANSWER_IDS = [f"ANS_{index:06d}" for index in range(1, 5)]
INTERVALS = [(11000, 50000), (51000, 107000), (108000, 160000), (161000, 192000)]
SEGMENTS = [6, 8, 9, 4]
WORDS = [68, 91, 94, 54]


def fixtures() -> tuple[dict, dict, dict, dict]:
    vision_answers = []
    transcript_answers = []
    speech_answers = []
    for index, answer_id in enumerate(ANSWER_IDS):
        start, end = INTERVALS[index]
        vision_answers.append(
            {
                "answerId": answer_id,
                "status": "COMPLETE_WITH_WARNINGS",
                "interval": {
                    "startTimestampMs": start,
                    "endTimestampMs": end,
                    "rule": "[start, end)",
                },
                "sampleCount": 100,
                "headPoseMeasurement": {"status": "PARTIAL"},
                "postureMeasurement": {"status": "COMPLETE"},
                "warnings": [],
            }
        )
        transcript_answers.append(
            {
                "answerId": answer_id,
                "status": "COMPLETE_WITH_WARNINGS",
                "language": {"detected": "ko"},
                "textExposed": True,
                "text": "private transcript",
                "segmentCount": SEGMENTS[index],
                "wordCount": WORDS[index],
                "segments": [
                    {"startMsSession": start, "endMsSession": start + 10, "text": "private"}
                ],
                "words": [
                    {"startMsSession": end - 10, "endMsSession": end, "text": "private"}
                ],
                "warnings": [
                    {
                        "code": "SEGMENT_BOUNDARY_EXPANDED_TO_WORDS",
                        "message": "Segment boundary was expanded.",
                        "answerId": answer_id,
                    }
                ],
            }
        )
        fillers = []
        if index == 3:
            fillers = [{"startMsSession": start + 20, "endMsSession": start + 30}]
        speech_answers.append(
            {
                "answerId": answer_id,
                "status": "COMPLETE_WITH_WARNINGS",
                "speakingRate": {"wordsPerMinute": 100.0},
                "timestampPauses": {},
                "acousticSilence": {},
                "fillerCandidates": fillers,
                "volume": {"rmsDbfs": -30.0},
                "pitch": {"medianF0Hz": 110.0},
                "warnings": [
                    {"code": "UPSTREAM_TRANSCRIPTION_WARNING", "message": "Upstream warning."}
                ],
            }
        )
    vision = {
        "sessionId": "SES_000001",
        "status": "single_session_mvp_feedback_ready_with_measurement_limitations",
        "measurementSummary": {"answerCount": 4},
        "answers": vision_answers,
        "warnings": [],
        "limitations": ["Head Pose is partially available."],
    }
    transcription = {
        "sessionId": "SES_000001",
        "status": "stt_session_transcription_ready_with_warnings",
        "options": {"timestampToleranceMs": 1},
        "answers": transcript_answers,
        "warnings": [],
        "errors": [],
    }
    speech = {
        "sessionId": "SES_000001",
        "status": "speech_characteristics_ready_with_warnings",
        "answers": speech_answers,
        "aggregate": {"totalFillerCandidateCount": 1},
        "warnings": [],
        "limitations": [],
    }
    jobs = {
        "vision": {
            "jobId": "vision-job",
            "analysisMode": "SINGLE_SESSION_BASELINE_RELATIVE_MVP",
            "status": "SUCCEEDED_WITH_LIMITATIONS",
        },
        "analysis": {"jobId": "analysis-job", "status": "SUCCEEDED_WITH_WARNINGS"},
    }
    return vision, transcription, speech, jobs


class FakeClient:
    def __init__(self, *, fail_analysis: bool = False):
        self.vision, self.transcription_result, self.speech_result, self.jobs = fixtures()
        self.fail_analysis = fail_analysis
        self.created = []

    def health(self, source):
        return {"status": "ok"}

    def ready(self, source):
        return {"status": "ready"}

    def create_vision_job(self, session_id):
        self.created.append(("VISION", session_id, False))
        return deepcopy(self.jobs["vision"])

    def create_analysis_job(self, session_id):
        self.created.append(("ANALYSIS", session_id, False))
        if self.fail_analysis:
            raise IntegrationContractError(
                "COMPONENT_HTTP_ERROR", "Analysis unavailable.", source="ANALYSIS", retryable=True
            )
        return deepcopy(self.jobs["analysis"])

    def poll_job(self, source, job):
        return deepcopy(job)

    def vision_feedback(self, session_id):
        return deepcopy(self.vision)

    def transcription(self, session_id):
        return deepcopy(self.transcription_result)

    def speech_characteristics(self, session_id):
        return deepcopy(self.speech_result)


class IdentifierContractTests(unittest.TestCase):
    def test_session_id_accepts_canonical_value(self):
        self.assertEqual(validate_session_id("SES_000001"), "SES_000001")

    def test_session_id_rejects_bad_value(self):
        with self.assertRaises(IntegrationContractError):
            validate_session_id("SESSION1")

    def test_answer_id_accepts_canonical_value(self):
        self.assertEqual(validate_answer_id("ANS_000004"), "ANS_000004")

    def test_answer_id_rejects_bad_value(self):
        with self.assertRaises(IntegrationContractError):
            validate_answer_id("ANS_4")


class StatusAndWarningTests(unittest.TestCase):
    def test_vision_job_limitation_maps_to_warning(self):
        self.assertEqual(
            map_job_status("VISION", "SUCCEEDED_WITH_LIMITATIONS"),
            "SUCCEEDED_WITH_WARNINGS",
        )

    def test_analysis_success_maps_ready(self):
        self.assertEqual(map_component_status("ANALYSIS", "SUCCEEDED"), "READY")

    def test_source_status_is_not_destroyed_by_mapping(self):
        vision, transcription, speech, jobs = fixtures()
        validation = validate_integration_inputs("SES_000001", vision, transcription, speech)
        result = build_integrated_session(
            session_id="SES_000001",
            vision=vision,
            transcription=transcription,
            speech=speech,
            validation=validation,
            jobs=jobs,
        )
        self.assertEqual(
            result["components"]["vision"]["sourceStatus"], "SUCCEEDED_WITH_LIMITATIONS"
        )

    def test_warning_normalization(self):
        warning = normalize_warning(
            "SPEECH", "FILLER_CANDIDATE_REVIEW_REQUIRED", answer_id="ANS_000004"
        )
        self.assertTrue(warning["reviewRequired"])
        self.assertEqual(warning["source"], "SPEECH")

    def test_warning_deduplication_keeps_different_sources(self):
        first = normalize_warning("VISION", {"code": "SHARED", "message": "a"})
        second = normalize_warning("SPEECH", {"code": "SHARED", "message": "b"})
        duplicate = normalize_warning("VISION", {"code": "SHARED", "message": "c"})
        self.assertEqual(len(deduplicate_warnings([first, second, duplicate])), 2)

    def test_error_normalization_drops_exception_details(self):
        error = normalize_error("ANALYSIS", "DEPENDENCY_UNAVAILABLE", "Dependency unavailable.")
        self.assertEqual(set(error), {"source", "code", "message", "retryable"})


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.vision, self.transcription, self.speech, _ = fixtures()

    def test_valid_fixture_has_four_answers(self):
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["answerIds"], ANSWER_IDS)

    def test_session_mismatch_is_detected(self):
        self.speech["sessionId"] = "SES_000002"
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertIn("SESSION_ID_MISMATCH", {item["code"] for item in result["errors"]})

    def test_missing_answer_is_detected(self):
        self.transcription["answers"].pop()
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertIn("ANSWER_SET_MISMATCH", {item["code"] for item in result["errors"]})

    def test_extra_answer_is_detected(self):
        extra = deepcopy(self.speech["answers"][0])
        extra["answerId"] = "ANS_000005"
        self.speech["answers"].append(extra)
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertFalse(result["valid"])

    def test_duplicate_answer_is_detected(self):
        self.vision["answers"].append(deepcopy(self.vision["answers"][0]))
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertFalse(result["valid"])

    def test_invalid_interval_is_detected(self):
        self.vision["answers"][0]["interval"]["endTimestampMs"] = 10000
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertIn("ANSWER_INTERVAL_MISMATCH", {item["code"] for item in result["errors"]})

    def test_valid_but_unapproved_interval_is_detected(self):
        self.vision["answers"][0]["interval"]["startTimestampMs"] = 11001
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertIn("ANSWER_INTERVAL_MISMATCH", {item["code"] for item in result["errors"]})

    def test_timestamp_outside_answer_is_detected(self):
        self.transcription["answers"][0]["words"][0]["endMsSession"] = 50002
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertEqual(result["timestampValidation"]["errorCount"], 1)

    def test_one_millisecond_tolerance_is_honored(self):
        self.transcription["answers"][0]["words"][0]["endMsSession"] = 50001
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertEqual(result["timestampValidation"]["errorCount"], 0)

    def test_tolerance_is_zero_without_upstream_contract(self):
        self.transcription["options"] = {}
        self.transcription["answers"][0]["words"][0]["endMsSession"] = 50001
        result = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )
        self.assertEqual(result["timestampValidation"]["errorCount"], 1)


class IntegratedContractTests(unittest.TestCase):
    def setUp(self):
        self.vision, self.transcription, self.speech, self.jobs = fixtures()
        self.validation = validate_integration_inputs(
            "SES_000001", self.vision, self.transcription, self.speech
        )

    def build(self, **kwargs):
        return build_integrated_session(
            session_id="SES_000001",
            vision=self.vision,
            transcription=self.transcription,
            speech=self.speech,
            validation=self.validation,
            jobs=self.jobs,
            generated_at="2026-08-03T00:00:00Z",
            **kwargs,
        )

    def test_expected_ready_with_warnings_status(self):
        self.assertEqual(self.build()["status"], "INTEGRATED_READY_WITH_WARNINGS")

    def test_counts_match_ses_000001(self):
        result = self.build()
        self.assertEqual(len(result["answers"]), 4)
        self.assertEqual(result["components"]["transcription"]["segmentCount"], 27)
        self.assertEqual(result["components"]["transcription"]["wordCount"], 307)
        self.assertEqual(result["components"]["speechCharacteristics"]["fillerCandidateCount"], 1)
        self.assertEqual(result["components"]["speechCharacteristics"]["pitchAvailableAnswerCount"], 4)

    def test_transcript_text_is_hidden_by_default(self):
        result = self.build()
        serialized = json.dumps(result)
        self.assertNotIn("private transcript", serialized)
        self.assertNotIn('"segments"', serialized)
        self.assertFalse(result["components"]["transcription"]["textExposed"])

    def test_transcript_text_can_be_explicitly_exposed(self):
        result = self.build(expose_transcript_text=True)
        self.assertEqual(result["answers"][0]["transcription"]["text"], "private transcript")

    def test_scoring_is_unavailable_and_score_fields_absent(self):
        result = self.build()
        self.assertFalse(result["scoringAvailable"])
        self.assertNotIn('"score"', json.dumps(result))

    def test_gpu_limitation_is_recorded(self):
        codes = {item["code"] for item in self.build()["limitations"]}
        self.assertIn("ANALYSIS_DOCKER_GPU_FORCE_REBUILD_NOT_VERIFIED", codes)

    def test_partial_when_analysis_is_unavailable(self):
        validation = validate_integration_inputs("SES_000001", self.vision, None, None)
        result = build_integrated_session(
            session_id="SES_000001",
            vision=self.vision,
            transcription=None,
            speech=None,
            validation=validation,
            jobs={"vision": self.jobs["vision"], "analysis": None},
        )
        self.assertEqual(result["status"], "INTEGRATED_PARTIAL")

    def test_successful_job_without_transcription_result_is_not_ready(self):
        validation = validate_integration_inputs(
            "SES_000001", self.vision, None, self.speech
        )
        result = build_integrated_session(
            session_id="SES_000001",
            vision=self.vision,
            transcription=None,
            speech=self.speech,
            validation=validation,
            jobs=self.jobs,
        )
        self.assertEqual(result["components"]["transcription"]["status"], "UNAVAILABLE")
        self.assertEqual(result["status"], "INTEGRATED_PARTIAL")

    def test_mandatory_validation_error_fails_integration(self):
        broken = deepcopy(self.validation)
        broken["errors"] = [
            {"source": "INTEGRATION", "code": "ANSWER_SET_MISMATCH", "message": "bad", "retryable": False}
        ]
        result = build_integrated_session(
            session_id="SES_000001",
            vision=self.vision,
            transcription=self.transcription,
            speech=self.speech,
            validation=broken,
            jobs=self.jobs,
        )
        self.assertEqual(result["status"], "INTEGRATED_FAILED")


class PrivacyAndStorageTests(unittest.TestCase):
    def test_participant_id_is_rejected(self):
        with self.assertRaises(IntegrationContractError):
            validate_public_payload({"message": "PTC_999999"})

    def test_absolute_path_is_rejected(self):
        with self.assertRaises(IntegrationContractError):
            validate_public_payload({"message": "C:\\private\\file.wav"})

    def test_forbidden_score_key_is_rejected(self):
        with self.assertRaises(IntegrationContractError):
            validate_public_payload({"score": 1})

    def test_nan_and_infinity_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(IntegrationContractError):
                strict_json_bytes({"value": value})

    def test_atomic_write_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "result.json"
            atomic_write_json(destination, {"status": "ok"})
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["status"], "ok")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


class ClientAndServiceTests(unittest.TestCase):
    def test_environment_configuration(self):
        config = AiApiClientConfig.from_env(
            {
                "FACEFIT_VISION_API_BASE_URL": "http://vision-server:8000",
                "FACEFIT_ANALYSIS_API_BASE_URL": "http://analysis-server:8002",
                "FACEFIT_INTEGRATION_POLL_INTERVAL_MS": "500",
                "FACEFIT_INTEGRATION_TIMEOUT_SECONDS": "10",
            }
        ).validated()
        self.assertEqual(config.poll_interval_ms, 500)
        self.assertEqual(config.timeout_seconds, 10)

    def test_invalid_base_url_is_rejected(self):
        with self.assertRaises(IntegrationContractError):
            AiApiClientConfig(vision_base_url="file:///private").validated()

    def test_polling_returns_immediately_for_terminal_job(self):
        client = AiApiClient(AiApiClientConfig(retry_count=0))
        job = {"jobId": "job", "status": "SUCCEEDED"}
        self.assertIs(client.poll_job("VISION", job), job)

    def test_polling_timeout_is_bounded(self):
        times = iter([0.0, 2.0])
        client = AiApiClient(
            AiApiClientConfig(timeout_seconds=1, retry_count=0),
            clock=lambda: next(times),
            sleeper=lambda _: None,
        )
        with self.assertRaises(IntegrationContractError) as context:
            client.poll_job("VISION", {"jobId": "job", "status": "RUNNING"})
        self.assertEqual(context.exception.code, "INTEGRATION_TIMEOUT")

    def test_service_uses_force_rebuild_false_and_integrates(self):
        fake = FakeClient()
        package = IntegratedSessionService(fake).run("SES_000001")
        self.assertEqual(package["integratedSession"]["status"], "INTEGRATED_READY_WITH_WARNINGS")
        self.assertEqual(fake.created, [("VISION", "SES_000001", False), ("ANALYSIS", "SES_000001", False)])
        self.assertEqual(package["runtimeMetadata"]["visionJobId"], "vision-job")
        self.assertEqual(package["runtimeMetadata"]["analysisJobId"], "analysis-job")

    def test_service_preserves_vision_when_analysis_fails(self):
        package = IntegratedSessionService(FakeClient(fail_analysis=True)).run("SES_000001")
        self.assertEqual(package["integratedSession"]["status"], "INTEGRATED_PARTIAL")
        self.assertEqual(package["integratedSession"]["components"]["vision"]["answerCount"], 4)

    def test_output_package_has_four_atomic_artifacts(self):
        package = IntegratedSessionService(FakeClient()).run("SES_000001")
        with tempfile.TemporaryDirectory() as directory:
            root = IntegratedSessionService.write_outputs(directory, package)
            self.assertEqual(
                {path.name for path in root.iterdir()},
                {
                    "integrated_session.json",
                    "integration_validation.json",
                    "component_status.json",
                    "integration_report.md",
                },
            )

    def test_cli_does_not_accept_media_or_identity_options(self):
        option_strings = {
            option
            for action in cli_parser()._actions
            for option in action.option_strings
        }
        for forbidden in ("--video-path", "--audio-path", "--participant-id", "--transcript-path"):
            self.assertNotIn(forbidden, option_strings)


if __name__ == "__main__":
    unittest.main()
