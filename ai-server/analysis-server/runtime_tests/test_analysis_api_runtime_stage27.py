from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import unittest
import uuid

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.analysis_api_config import AnalysisApiConfig
from app.main import create_app


def all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key).replace("_", "").lower() for key in value} | set().union(
            *(all_keys(item) for item in value.values())
        )
    if isinstance(value, list):
        return set().union(*(all_keys(item) for item in value)) if value else set()
    return set()


class AnalysisApiRuntimeStage27Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = AnalysisApiConfig(
            environment="runtime-test",
            host="127.0.0.1",
            port=8002,
            allowed_origins=(),
            enable_docs=True,
            output_root=ROOT / "data" / "output",
            log_level="INFO",
            expose_transcript_text=True,
        )
        cls.client = TestClient(create_app(config), raise_server_exceptions=False)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_health_ready_and_openapi(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)
        ready = self.client.get("/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["pipelines"], [
            "STT_TRANSCRIPTION", "SPEECH_CHARACTERISTICS", "STT_AND_SPEECH"
        ])
        document = self.client.get("/openapi.json")
        self.assertEqual(document.status_code, 200)
        self.assertIn("ApiError", document.json()["components"]["schemas"])

    def test_real_transcription_contract(self) -> None:
        response = self.client.get("/api/v1/analysis/sessions/SES_000001/transcription")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["answers"]), 4)
        self.assertEqual(sum(row["segmentCount"] for row in body["answers"]), 27)
        self.assertEqual(sum(row["wordCount"] for row in body["answers"]), 307)
        self.assertEqual(body["warnings"][0]["code"], "SEGMENT_BOUNDARY_EXPANDED_TO_WORDS")
        serialized = json.dumps(body).lower()
        self.assertNotIn("participantid", serialized)
        self.assertNotIn("cache", serialized)

    def test_real_speech_contract(self) -> None:
        response = self.client.get("/api/v1/analysis/sessions/SES_000001/speech-characteristics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["answers"]), 4)
        self.assertEqual(sum(len(row["fillerCandidates"]) for row in body["answers"]), 1)
        self.assertTrue(all(row["pitch"].get("medianF0Hz") is not None for row in body["answers"]))
        self.assertFalse(body["scoringAvailable"])
        keys = all_keys(body)
        for forbidden in ("score", "grade", "confidence", "anxiety", "personality", "emotion", "passprobability"):
            self.assertNotIn(forbidden, keys)

    def test_real_job_create_read_and_reuse(self) -> None:
        response = self.client.post("/api/v1/analysis/jobs", json={
            "sessionId": "SES_000001",
            "pipeline": "SPEECH_CHARACTERISTICS",
            "forceRebuild": False,
        })
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        deadline = time.monotonic() + 60
        while body["status"] not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"}:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.1)
            body = self.client.get(f"/api/v1/analysis/jobs/{body['jobId']}").json()
        self.assertEqual(body["status"], "SUCCEEDED_WITH_WARNINGS")
        self.assertTrue(body["resultAvailable"])
        self.assertGreaterEqual(len(body["warnings"]), 2)
        fetched = self.client.get(f"/api/v1/analysis/jobs/{body['jobId']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), body)

    def test_invalid_and_unknown_resources(self) -> None:
        invalid = self.client.get("/api/v1/analysis/sessions/not-valid/transcription")
        unknown = self.client.get("/api/v1/analysis/sessions/SES_999999/transcription")
        job = self.client.get(f"/api/v1/analysis/jobs/{uuid.uuid4()}")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(job.status_code, 404)


if __name__ == "__main__":
    unittest.main()
