from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import uuid

from fastapi.testclient import TestClient

from app.audio.audio_manifest_writer import write_json_atomic
from app.core.analysis_api_config import AnalysisApiConfig, AnalysisApiConfigError
from app.main import create_app
from app.services.analysis_job_service import AnalysisJobService
from app.services.analysis_job_storage import AnalysisJobStorage, JobStorageError


def all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key).replace("_", "").lower() for key in value} | set().union(
            *(all_keys(item) for item in value.values())
        )
    if isinstance(value, list):
        return set().union(*(all_keys(item) for item in value)) if value else set()
    return set()


def config(root: Path, *, expose_text: bool = True) -> AnalysisApiConfig:
    return AnalysisApiConfig(
        environment="test",
        host="127.0.0.1",
        port=8002,
        allowed_origins=(),
        enable_docs=True,
        output_root=root,
        log_level="INFO",
        expose_transcript_text=expose_text,
    )


def seed_results(root: Path, session_id: str = "SES_000001") -> None:
    (root / "stt_preprocessing" / session_id).mkdir(parents=True)
    transcript_root = root / "stt_transcription" / session_id
    speech_root = root / "speech_characteristics" / session_id
    answer_ids = [f"ANS_{index:06d}" for index in range(1, 5)]
    transcript_summaries = []
    speech_summaries = []
    for index, answer_id in enumerate(answer_ids, start=1):
        transcript = {
            "sessionId": session_id,
            "answerId": answer_id,
            "status": "COMPLETE_WITH_WARNINGS",
            "language": {"requested": "ko", "detected": "ko", "probability": 1.0},
            "text": f"answer {index}",
            "segments": [{
                "segmentId": "SEG_000001", "startMsRelative": 0, "endMsRelative": 500,
                "startMsSession": index * 1000, "endMsSession": index * 1000 + 500,
                "wordCount": 1, "text": f"answer {index}",
            }],
            "words": [{
                "wordId": "WRD_000001", "segmentId": "SEG_000001",
                "startMsRelative": 0, "endMsRelative": 500,
                "startMsSession": index * 1000, "endMsSession": index * 1000 + 500,
                "probability": 0.9, "text": f"answer {index}",
            }],
            "warnings": ["SEGMENT_BOUNDARY_EXPANDED_TO_WORDS"],
            "errors": [],
        }
        write_json_atomic(transcript_root / "answers" / f"{answer_id}.json", transcript)
        transcript_summaries.append({"answerId": answer_id})
        speech = {
            "sessionId": session_id,
            "answerId": answer_id,
            "status": "COMPLETE_WITH_WARNINGS",
            "speakingRate": {"wordCount": 1, "wordsPerMinute": 60.0},
            "timestampPauses": {"totalInterWordGapMs": 0, "scoringApproved": False},
            "acousticSilence": {"candidateSilentDurationMs": 0, "scoringApproved": False},
            "fillerCandidates": ([{"candidateText": "그", "reviewRequired": True}] if index == 4 else []),
            "volume": {"rmsDbfs": -30.0},
            "pitch": {"medianF0Hz": 120.0},
            "score": 99,
            "confidence": 0.9,
            "warnings": ["UPSTREAM_TRANSCRIPTION_WARNING"] + (
                ["FILLER_CANDIDATE_REVIEW_REQUIRED"] if index == 4 else []
            ),
            "errors": [],
        }
        write_json_atomic(speech_root / "answers" / f"{answer_id}.json", speech)
        speech_summaries.append({"answerId": answer_id})
    write_json_atomic(transcript_root / "session_transcription_manifest.json", {
        "sessionId": session_id,
        "status": "stt_session_transcription_ready_with_warnings",
        "engine": {"name": "faster-whisper", "version": "1.2.1", "cache": {"path": "secret"}},
        "options": {"language": "ko", "wordTimestamps": True},
        "answers": transcript_summaries,
        "warnings": ["SEGMENT_BOUNDARY_EXPANDED_TO_WORDS"],
        "errors": [],
    })
    write_json_atomic(speech_root / "session_speech_manifest.json", {
        "sessionId": session_id,
        "status": "speech_characteristics_ready_with_warnings",
        "answers": speech_summaries,
        "aggregate": {"answerCount": 4, "totalWordCount": 4, "score": 100},
        "warnings": ["UPSTREAM_TRANSCRIPTION_WARNING", "FILLER_CANDIDATE_REVIEW_REQUIRED"],
        "errors": [],
    })


class AnalysisApiConfigTests(unittest.TestCase):
    def test_development_defaults(self) -> None:
        value = AnalysisApiConfig.from_env({})
        self.assertEqual(value.port, 8002)
        self.assertTrue(value.enable_docs)
        self.assertTrue(value.expose_transcript_text)
        self.assertEqual(value.allowed_origins, ())

    def test_production_hides_docs_and_text(self) -> None:
        value = AnalysisApiConfig.from_env({"ANALYSIS_API_ENV": "production"})
        self.assertFalse(value.enable_docs)
        self.assertFalse(value.expose_transcript_text)

    def test_rejects_wildcard_cors_and_loose_boolean(self) -> None:
        with self.assertRaises(AnalysisApiConfigError):
            AnalysisApiConfig.from_env({"ANALYSIS_API_ALLOWED_ORIGINS": "*"})
        with self.assertRaises(AnalysisApiConfigError):
            AnalysisApiConfig.from_env({"ANALYSIS_API_ENABLE_DOCS": "yes"})

    def test_rejects_invalid_port_and_log_level(self) -> None:
        with self.assertRaises(AnalysisApiConfigError):
            AnalysisApiConfig.from_env({"ANALYSIS_API_PORT": "0"})
        with self.assertRaises(AnalysisApiConfigError):
            AnalysisApiConfig.from_env({"ANALYSIS_API_LOG_LEVEL": "TRACE"})
        with self.assertRaises(AnalysisApiConfigError):
            AnalysisApiConfig.from_env({"ANALYSIS_API_OUTPUT_ROOT": "  "})


class JobStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = AnalysisJobStorage(self.temp.name)
        self.record = {"jobId": str(uuid.uuid4()), "status": "QUEUED"}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_create_read_and_restart(self) -> None:
        self.storage.create(self.record)
        restarted = AnalysisJobStorage(self.temp.name)
        self.assertEqual(restarted.read(self.record["jobId"]), self.record)

    def test_collision_is_rejected(self) -> None:
        self.storage.create(self.record)
        with self.assertRaises(JobStorageError):
            self.storage.create(self.record)

    def test_traversal_and_non_uuid_are_not_found(self) -> None:
        for value in ("../secret", "not-a-uuid"):
            with self.assertRaises(JobStorageError) as raised:
                self.storage.read(value)
            self.assertEqual(raised.exception.code, "JOB_NOT_FOUND")

    def test_malformed_json_is_detected(self) -> None:
        self.storage.create(self.record)
        path = self.storage.root / f"{self.record['jobId']}.json"
        path.write_text('{"value": NaN}', encoding="utf-8")
        with self.assertRaises(JobStorageError) as raised:
            self.storage.read(self.record["jobId"])
        self.assertEqual(raised.exception.code, "JOB_STORAGE_ERROR")


class AnalysisJobServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        seed_results(self.root)
        self.calls: list[tuple[str, str, bool]] = []

        def stt(session_id: str, force: bool) -> dict:
            self.calls.append(("stt", session_id, force))
            return {"status": "ready"}

        def speech(session_id: str, force: bool) -> dict:
            self.calls.append(("speech", session_id, force))
            return {"status": "ready"}

        self.service = AnalysisJobService(config(self.root), stt_runner=stt, speech_runner=speech)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_combined_job_calls_services_in_order_and_persists_warning_status(self) -> None:
        job = self.service.create_job("SES_000001", "STT_AND_SPEECH", False)
        self.assertEqual([row[0] for row in self.calls], ["stt", "speech"])
        self.assertEqual(job["status"], "SUCCEEDED_WITH_WARNINGS")
        self.assertTrue(job["resultAvailable"])
        self.assertNotIn("forceRebuild", job)
        self.assertEqual(self.service.get_job(job["jobId"]), job)

    def test_successful_non_force_job_is_reused(self) -> None:
        first = self.service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", False)
        second = self.service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", False)
        self.assertEqual(first["jobId"], second["jobId"])
        self.assertEqual(len(self.calls), 1)

    def test_force_job_is_new_each_time(self) -> None:
        first = self.service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        second = self.service.create_job("SES_000001", "SPEECH_CHARACTERISTICS", True)
        self.assertNotEqual(first["jobId"], second["jobId"])

    def test_transcript_text_can_be_hidden_consistently(self) -> None:
        hidden = AnalysisJobService(config(self.root, expose_text=False)).transcription_result("SES_000001")
        for answer in hidden["answers"]:
            self.assertFalse(answer["textExposed"])
            self.assertIsNone(answer["text"])
            self.assertTrue(all(row["text"] is None for row in answer["segments"]))
            self.assertTrue(all(row["text"] is None for row in answer["words"]))

    def test_speech_result_excludes_evaluation_fields(self) -> None:
        result = self.service.speech_result("SES_000001")
        keys = all_keys(result)
        for forbidden in ("score", "grade", "confidence", "personality", "emotion", "passprobability"):
            self.assertNotIn(forbidden, keys)
        self.assertFalse(result["scoringAvailable"])
        self.assertEqual(len(result["answers"]), 4)


class AnalysisApiRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        seed_results(root)
        service = AnalysisJobService(
            config(root),
            stt_runner=lambda session_id, force: {"status": "ready"},
            speech_runner=lambda session_id, force: {"status": "ready"},
        )
        self.client = TestClient(create_app(config(root), service), raise_server_exceptions=False)

    def tearDown(self) -> None:
        self.client.close()
        self.temp.cleanup()

    def test_health_ready_and_request_id(self) -> None:
        health = self.client.get("/health", headers={"X-Request-ID": "stage27-test"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.headers["X-Request-ID"], "stage27-test")
        self.assertEqual(health.json()["service"], "face-fit-analysis-api")
        ready = self.client.get("/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertFalse(ready.json()["scoringAvailable"])

    def test_job_create_and_read(self) -> None:
        created = self.client.post("/api/v1/analysis/jobs", json={
            "sessionId": "SES_000001", "pipeline": "SPEECH_CHARACTERISTICS", "forceRebuild": False,
        })
        self.assertEqual(created.status_code, 201)
        fetched = self.client.get(f"/api/v1/analysis/jobs/{created.json()['jobId']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), created.json())

    def test_result_routes(self) -> None:
        transcript = self.client.get("/api/v1/analysis/sessions/SES_000001/transcription")
        speech = self.client.get("/api/v1/analysis/sessions/SES_000001/speech-characteristics")
        self.assertEqual(transcript.status_code, 200)
        self.assertEqual(speech.status_code, 200)
        self.assertEqual(len(transcript.json()["answers"]), 4)
        self.assertEqual(len(speech.json()["answers"]), 4)

    def test_validation_unknown_session_and_job_errors(self) -> None:
        invalid = self.client.get("/api/v1/analysis/sessions/bad/transcription")
        missing_session = self.client.get("/api/v1/analysis/sessions/SES_999999/transcription")
        missing_job = self.client.get(f"/api/v1/analysis/jobs/{uuid.uuid4()}")
        self.assertEqual((invalid.status_code, invalid.json()["code"]), (422, "VALIDATION_ERROR"))
        self.assertEqual((missing_session.status_code, missing_session.json()["code"]), (404, "SESSION_NOT_FOUND"))
        self.assertEqual((missing_job.status_code, missing_job.json()["code"]), (404, "JOB_NOT_FOUND"))

    def test_unsupported_pipeline_and_cors_request_id(self) -> None:
        unsupported = self.client.post("/api/v1/analysis/jobs", json={
            "sessionId": "SES_000001", "pipeline": "UNKNOWN", "forceRebuild": False,
        })
        self.assertEqual((unsupported.status_code, unsupported.json()["code"]), (422, "UNSUPPORTED_PIPELINE"))
        self.assertIn("X-Request-ID", unsupported.headers)

    def test_configured_cors_is_explicit_and_preflight_has_request_id(self) -> None:
        base = config(Path(self.temp.name))
        cors = AnalysisApiConfig(
            environment=base.environment, host=base.host, port=base.port,
            allowed_origins=("https://face-fit.example",), enable_docs=base.enable_docs,
            output_root=base.output_root, log_level=base.log_level,
            expose_transcript_text=base.expose_transcript_text,
        )
        client = TestClient(create_app(cors), raise_server_exceptions=False)
        try:
            response = client.options("/health", headers={
                "Origin": "https://face-fit.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Request-ID",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.headers["access-control-allow-origin"], "https://face-fit.example"
            )
            self.assertIn("X-Request-ID", response.headers)
        finally:
            client.close()

    def test_openapi_lists_contract_and_has_no_file_input(self) -> None:
        document = self.client.get("/openapi.json")
        self.assertEqual(document.status_code, 200)
        paths = document.json()["paths"]
        self.assertIn("/api/v1/analysis/jobs", paths)
        self.assertIn("/api/v1/analysis/sessions/{session_id}/transcription", paths)
        serialized = json.dumps(document.json()).lower()
        self.assertNotIn("participantid", serialized)
        self.assertNotIn('"filepath"', serialized)

    def test_production_disables_interactive_docs_but_keeps_openapi(self) -> None:
        production = config(Path(self.temp.name), expose_text=False)
        production = AnalysisApiConfig(
            environment="production", host=production.host, port=production.port,
            allowed_origins=(), enable_docs=False, output_root=production.output_root,
            log_level="INFO", expose_transcript_text=False,
        )
        client = TestClient(create_app(production), raise_server_exceptions=False)
        try:
            self.assertEqual(client.get("/docs").status_code, 404)
            self.assertEqual(client.get("/openapi.json").status_code, 200)
            answer = client.get(
                "/api/v1/analysis/sessions/SES_000001/transcription"
            ).json()["answers"][0]
            self.assertFalse(answer["textExposed"])
            self.assertIsNone(answer["text"])
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
