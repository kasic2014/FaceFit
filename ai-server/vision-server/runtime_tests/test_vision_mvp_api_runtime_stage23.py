from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.core.vision_api_config import VisionApiSettings
from app.main import create_app
from app.services.vision_job_service import (
    VisionJobService,
    atomic_write_json,
)
from app.vision.single_session_mvp_feedback import (
    ANALYSIS_MODE,
    RESULT_LIMITED,
    SCORING_REASONS,
)


SESSION_ID = "SES_900001"
EMPTY_SESSION_ID = "SES_900002"
JOB_ID = "20000000-0000-4000-8000-000000000001"


class SequenceClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 31, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        value = self.value
        self.value += timedelta(seconds=1)
        return value


class VisionMvpApiRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        output = root / "data" / "output"
        for session_id in (SESSION_ID, EMPTY_SESSION_ID):
            (
                output
                / "pilot_video_intake_validation"
                / session_id
            ).mkdir(parents=True)
        feedback = {
            "sessionId": SESSION_ID,
            "status": RESULT_LIMITED,
            "analysisMode": ANALYSIS_MODE,
            "analysisScope": "FACE_AND_BOTH_SHOULDERS",
            "operational": False,
            "scores": None,
            "scoreUnavailableReasons": list(SCORING_REASONS),
            "measurementSummary": {},
            "answers": [],
            "warnings": [],
            "limitations": [],
            "disclaimer": "fixture-only measurement disclaimer",
        }
        atomic_write_json(
            output
            / "single_session_mvp_feedback"
            / SESSION_ID
            / "mvp_feedback_api_contract.json",
            feedback,
        )
        settings = VisionApiSettings(
            environment="test",
            host="127.0.0.1",
            port=8001,
            allowed_origins=(),
            enable_docs=True,
            output_root=output,
            log_level="INFO",
            vision_server_root=root,
        )
        service = VisionJobService(
            vision_server_root=root,
            output_root=output,
            job_id_generator=lambda: JOB_ID,
            clock=SequenceClock(),
        )
        self.client = TestClient(
            create_app(settings=settings, job_service=service)
        )

    def tearDown(self):
        self.client.close()
        self.temporary.cleanup()

    def test_health_ready_and_openapi(self):
        health = self.client.get("/health")
        ready = self.client.get("/ready")
        openapi = self.client.get("/openapi.json")
        self.assertEqual(
            (health.status_code, ready.status_code, openapi.status_code),
            (200, 200, 200),
        )
        self.assertEqual(health.headers["content-type"], "application/json")
        self.assertEqual(health.json()["status"], "UP")
        self.assertFalse(ready.json()["scoringAvailable"])
        required = {
            "/health",
            "/ready",
            "/api/v1/vision/jobs",
            "/api/v1/vision/jobs/{job_id}",
            "/api/v1/vision/sessions/{session_id}/feedback",
        }
        self.assertTrue(required.issubset(openapi.json()["paths"]))
        self.assertEqual(len(openapi.json()["paths"]), len(set(
            openapi.json()["paths"]
        )))

    def test_job_create_read_and_feedback(self):
        created = self.client.post(
            "/api/v1/vision/jobs",
            json={
                "sessionId": SESSION_ID,
                "analysisMode": ANALYSIS_MODE,
                "forceRebuild": False,
            },
        )
        read = self.client.get(f"/api/v1/vision/jobs/{JOB_ID}")
        feedback = self.client.get(
            f"/api/v1/vision/sessions/{SESSION_ID}/feedback"
        )
        self.assertEqual(
            (created.status_code, read.status_code, feedback.status_code),
            (201, 200, 200),
        )
        self.assertEqual(
            created.json()["status"],
            "SUCCEEDED_WITH_LIMITATIONS",
        )
        self.assertEqual(created.json(), read.json())
        payload = feedback.json()
        self.assertIsNone(payload["scores"])
        self.assertEqual(
            payload["scoringUnavailableReasons"],
            list(SCORING_REASONS),
        )
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("PTC_", text)
        self.assertNotIn("\\data\\", text)

    def test_common_error_contracts(self):
        responses = (
            self.client.get(
                "/api/v1/vision/sessions/SES_999999/feedback"
            ),
            self.client.get(
                f"/api/v1/vision/sessions/{EMPTY_SESSION_ID}/feedback"
            ),
            self.client.get(
                "/api/v1/vision/jobs/"
                "30000000-0000-4000-8000-000000000001"
            ),
            self.client.post(
                "/api/v1/vision/jobs",
                json={
                    "sessionId": SESSION_ID,
                    "analysisMode": "FULL_PIPELINE",
                },
            ),
            self.client.post(
                "/api/v1/vision/jobs",
                json={"sessionId": "../SES_900001"},
            ),
        )
        self.assertEqual(
            [response.status_code for response in responses],
            [404, 409, 404, 422, 422],
        )
        for response in responses:
            self.assertEqual(
                set(response.json()),
                {"code", "message", "requestId", "details"},
            )

    def test_legacy_path_input_is_disabled(self):
        response = self.client.post(
            "/api/v1/analyze/image",
            json={"image_path": r"C:\private\image.png"},
        )
        self.assertEqual(response.status_code, 400)
        text = response.text
        self.assertNotIn("private", text)
        self.assertEqual(response.json()["code"], "VALIDATION_ERROR")
