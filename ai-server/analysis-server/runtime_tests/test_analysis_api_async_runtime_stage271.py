from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import unittest

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.analysis_api_config import AnalysisApiConfig
from app.main import create_app


class AnalysisApiAsyncRuntimeStage271Tests(unittest.TestCase):
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

    def _create(self) -> tuple[float, dict]:
        started = time.perf_counter()
        response = self.client.post("/api/v1/analysis/jobs", json={
            "sessionId": "SES_000001",
            "pipeline": "STT_AND_SPEECH",
            "forceRebuild": False,
        })
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, 201, response.text)
        return elapsed, response.json()

    def _poll(self, job: dict) -> tuple[dict, int]:
        deadline = time.monotonic() + 60
        polls = 0
        while job["status"] not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"}:
            self.assertLess(time.monotonic(), deadline, "bounded async polling timed out")
            time.sleep(0.1)
            response = self.client.get(f"/api/v1/analysis/jobs/{job['jobId']}")
            self.assertEqual(response.status_code, 200)
            job = response.json()
            polls += 1
        return job, polls

    def test_real_async_job_polling_and_idempotent_concurrent_post(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(self._create) for _ in range(2)]
            results = [future.result(timeout=10) for future in requests]
        elapsed = [row[0] for row in results]
        jobs = [row[1] for row in results]
        self.assertTrue(all(value < 2 for value in elapsed))
        self.assertEqual(len({job["jobId"] for job in jobs}), 1)
        self.assertIn(jobs[0]["status"], {
            "QUEUED", "RUNNING", "SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"
        })
        final, polls = self._poll(jobs[0])
        self.assertEqual(final["status"], "SUCCEEDED_WITH_WARNINGS")
        self.assertTrue(final["resultAvailable"])
        self.assertIsNotNone(final["completedAt"])
        self.assertIsNotNone(final["executionDurationMs"])
        self.assertGreaterEqual(polls, 0)

        again_elapsed, again = self._create()
        self.assertLess(again_elapsed, 2)
        self.assertEqual(again["jobId"], final["jobId"])

        transcript = self.client.get(
            "/api/v1/analysis/sessions/SES_000001/transcription"
        )
        speech = self.client.get(
            "/api/v1/analysis/sessions/SES_000001/speech-characteristics"
        )
        self.assertEqual(transcript.status_code, 200)
        self.assertEqual(speech.status_code, 200)
        transcript_body, speech_body = transcript.json(), speech.json()
        self.assertEqual(len(transcript_body["answers"]), 4)
        self.assertEqual(sum(row["segmentCount"] for row in transcript_body["answers"]), 27)
        self.assertEqual(sum(row["wordCount"] for row in transcript_body["answers"]), 307)
        self.assertEqual(sum(len(row["fillerCandidates"]) for row in speech_body["answers"]), 1)
        self.assertTrue(all(row["pitch"].get("medianF0Hz") for row in speech_body["answers"]))
        self.assertFalse(speech_body["scoringAvailable"])
        self.assertFalse(speech_body["thresholdApproval"])
        serialized = json.dumps({"job": final, "transcript": transcript_body, "speech": speech_body}).lower()
        self.assertNotIn("participantid", serialized)
        self.assertNotIn("cachepath", serialized)


if __name__ == "__main__":
    unittest.main()
