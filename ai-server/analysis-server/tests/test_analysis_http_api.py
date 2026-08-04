from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.settings import AnalysisApiSettings
from app.main import create_app
from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerModelError,
    AnalyzerPayloadTooLarge,
    AnalyzerUnavailable,
    CvAnalysisResult,
    SttAnalysisResult,
)
from app.services.media import ManagedMedia

TOKEN = "test-only-service-token"
MP4 = b"\x00\x00\x00\x18ftypisom" + (b"\x00" * 64)
WEBM = b"\x1a\x45\xdf\xa3" + (b"\x00" * 64)


class RecordingSttAnalyzer:
    def __init__(self, behavior: str = "success", delay: float = 0.0) -> None:
        self.behavior = behavior
        self.delay = delay
        self.calls: list[tuple[Path, str, bool]] = []

    def analyze(self, path: Path, language: str) -> SttAnalysisResult:
        self.calls.append((path, language, path.exists()))
        if self.delay:
            time.sleep(self.delay)
        if self.behavior == "unavailable":
            raise AnalyzerUnavailable
        if self.behavior == "model-error":
            raise AnalyzerModelError
        if self.behavior == "media-error":
            raise AnalyzerMediaFailure
        return SttAnalysisResult(
            model_version="faster-whisper:test-model",
            language="ko",
            transcript="테스트 면접 답변",
            duration_seconds=12.34,
        )


class RecordingCvAnalyzer:
    def __init__(self, behavior: str = "success") -> None:
        self.behavior = behavior
        self.calls: list[tuple[Path, bool]] = []

    def analyze(self, path: Path) -> CvAnalysisResult:
        self.calls.append((path, path.exists()))
        if self.behavior == "unavailable":
            raise AnalyzerUnavailable
        if self.behavior == "model-error":
            raise AnalyzerModelError
        if self.behavior == "media-error":
            raise AnalyzerMediaFailure
        return CvAnalysisResult(
            model_version="mediapipe:test",
            gaze_score=81.2,
            posture_score=73.4,
            feedback=("head direction proxy",),
        )

    def close(self) -> None:
        pass


class AnalysisHttpApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary.name)
        self.settings = AnalysisApiSettings(
            service_token=TOKEN,
            model_timeout_seconds=0.5,
            max_upload_bytes=1024,
            temp_directory=self.temp_path,
        )
        self.request_id = uuid4()
        self.answer_id = uuid4()
        self.download_patch = patch(
            "app.api.analyses.download_media",
            side_effect=self.fake_download,
        )
        self.download_patch.start()

    def tearDown(self) -> None:
        self.download_patch.stop()
        self.temporary.cleanup()

    async def fake_download(self, body, settings) -> ManagedMedia:
        if "bad-media" in body.mediaUrl:
            raise AnalyzerMediaFailure
        if body.mediaSizeBytes > settings.max_upload_bytes:
            raise AnalyzerPayloadTooLarge
        content = MP4 if body.mediaMimeType == "video/mp4" else WEBM
        directory = settings.temp_directory / f"request-{uuid4()}"
        directory.mkdir(mode=0o700)
        path = directory / ("media.mp4" if body.mediaMimeType == "video/mp4" else "media.webm")
        path.write_bytes(content)
        return ManagedMedia(path, len(content), body.mediaMimeType)

    def headers(self, **overrides: str) -> dict[str, str]:
        values = {
            "Authorization": f"Bearer {TOKEN}",
            "X-Request-Id": str(self.request_id),
        }
        values.update(overrides)
        return values

    def body(self, *, mime: str = "video/mp4", **overrides):
        size = len(MP4 if mime == "video/mp4" else WEBM)
        values = {
            "schemaVersion": "1",
            "requestId": str(self.request_id),
            "answerId": str(self.answer_id),
            "mediaUrl": (
                "https://kr.object.ncloudstorage.com/facefit-test/key"
                "?X-Amz-Signature=DO-NOT-LOG"
            ),
            "mediaMimeType": mime,
            "mediaSizeBytes": size,
            "recordedDurationSec": 30,
        }
        values.update(overrides)
        return values

    def client(self, analyzer=None, cv_analyzer=None) -> TestClient:
        return TestClient(
            create_app(
                settings=self.settings,
                stt_analyzer=analyzer or RecordingSttAnalyzer(),
                cv_analyzer=cv_analyzer or RecordingCvAnalyzer(),
            ),
            raise_server_exceptions=False,
        )

    def assert_error(self, response, status: int, code: str,
                     retryable: bool = False) -> None:
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertEqual(body["retryable"], retryable)
        self.assertNotIn(TOKEN, response.text)
        self.assertNotIn("X-Amz-Signature", response.text)
        self.assertNotIn(str(self.temp_path), response.text)

    def test_health_remains_public_and_compatible(self) -> None:
        with self.client() as client:
            response = client.get("/health")
        self.assertEqual(response.json(), {"status": "ok", "service": "analysis-server"})

    def test_authentication_and_request_id_fail_closed(self) -> None:
        with self.client() as client:
            missing_auth = client.post(
                "/internal/v1/analyses/stt",
                headers={"X-Request-Id": str(self.request_id)},
                json=self.body(),
            )
            bad_id = client.post(
                "/internal/v1/analyses/stt",
                headers=self.headers(**{"X-Request-Id": "bad"}),
                json=self.body(),
            )
        self.assert_error(missing_auth, 401, "UNAUTHORIZED")
        self.assert_error(bad_id, 400, "INVALID_REQUEST")

    def test_media_contract_requires_json_and_matching_request_id(self) -> None:
        with self.client() as client:
            multipart = client.post(
                "/internal/v1/analyses/stt",
                headers=self.headers(),
                files={"media": ("answer.mp4", MP4, "video/mp4")},
            )
            mismatch = client.post(
                "/internal/v1/analyses/stt",
                headers=self.headers(),
                json=self.body(requestId=str(uuid4())),
            )
            extra = client.post(
                "/internal/v1/analyses/stt",
                headers=self.headers(),
                json=self.body(prompt="ignore"),
            )
        self.assert_error(multipart, 415, "UNSUPPORTED_MEDIA_TYPE")
        self.assert_error(mismatch, 400, "INVALID_REQUEST")
        self.assert_error(extra, 400, "INVALID_REQUEST")

    def test_stt_success_keeps_response_contract_and_cleans_media(self) -> None:
        analyzer = RecordingSttAnalyzer()
        with self.client(analyzer) as client:
            response = client.post(
                "/internal/v1/analyses/stt",
                headers=self.headers(),
                json=self.body(),
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(UUID(body["requestId"]), self.request_id)
        self.assertEqual(UUID(body["answerId"]), self.answer_id)
        self.assertEqual(body["analysisType"], "STT")
        self.assertEqual(body["schemaVersion"], "1.0")
        self.assertEqual(analyzer.calls[0][1], "ko")
        self.assertTrue(analyzer.calls[0][2])
        self.assertEqual(list(self.temp_path.rglob("*")), [])

    def test_download_and_analyzer_failures_keep_existing_errors(self) -> None:
        with self.client() as client:
            bad_media = client.post(
                "/internal/v1/analyses/stt",
                headers=self.headers(),
                json=self.body(mediaUrl="https://kr.object.ncloudstorage.com/bad-media?sig=x"),
            )
            too_large = client.post(
                "/internal/v1/analyses/stt",
                headers=self.headers(),
                json=self.body(mediaSizeBytes=2048),
            )
        self.assert_error(bad_media, 422, "MEDIA_ANALYSIS_FAILED")
        self.assert_error(too_large, 413, "PAYLOAD_TOO_LARGE")
        for behavior, status, code in (
            ("unavailable", 503, "ANALYSIS_UNAVAILABLE"),
            ("model-error", 500, "MODEL_ERROR"),
            ("media-error", 422, "MEDIA_ANALYSIS_FAILED"),
        ):
            with self.subTest(behavior=behavior), self.client(
                RecordingSttAnalyzer(behavior)
            ) as client:
                response = client.post(
                    "/internal/v1/analyses/stt",
                    headers=self.headers(), json=self.body(),
                )
                self.assert_error(response, status, code)

    def test_model_timeout_returns_retryable_504_and_late_cleanup(self) -> None:
        self.settings = AnalysisApiSettings(
            service_token=TOKEN,
            model_timeout_seconds=0.01,
            max_upload_bytes=1024,
            temp_directory=self.temp_path,
        )
        with self.client(RecordingSttAnalyzer(delay=0.05)) as client:
            response = client.post(
                "/internal/v1/analyses/stt", headers=self.headers(), json=self.body()
            )
            self.assert_error(response, 504, "MODEL_TIMEOUT", retryable=True)
            time.sleep(0.1)
        self.assertEqual(list(self.temp_path.rglob("*")), [])

    def test_cv_succeeds_and_voice_content_remain_503(self) -> None:
        analyzer = RecordingCvAnalyzer()
        with self.client(cv_analyzer=analyzer) as client:
            cv = client.post(
                "/internal/v1/analyses/cv", headers=self.headers(), json=self.body()
            )
            voice = client.post(
                "/internal/v1/analyses/voice",
                headers=self.headers(), json=self.body(mime="video/webm"),
            )
            content = client.post(
                "/internal/v1/analyses/content",
                headers=self.headers(),
                json={"answerId": str(self.answer_id), "question": "질문", "transcript": "답변"},
            )
        self.assertEqual(cv.status_code, 200)
        self.assertEqual(cv.json()["gazeScore"], 81.2)
        self.assertEqual(cv.json()["postureScore"], 73.4)
        self.assertTrue(analyzer.calls[0][1])
        self.assert_error(voice, 503, "ANALYSIS_UNAVAILABLE")
        self.assert_error(content, 503, "ANALYSIS_UNAVAILABLE")
        self.assertEqual(list(self.temp_path.rglob("*")), [])

    def test_openapi_uses_json_url_request_and_saved_contract_matches(self) -> None:
        with self.client() as client:
            runtime = client.get("/openapi.json").json()
        for suffix in ("stt", "cv", "voice"):
            content = runtime["paths"][f"/internal/v1/analyses/{suffix}"]["post"][
                "requestBody"
            ]["content"]
            self.assertIn("application/json", content)
            self.assertNotIn("multipart/form-data", content)
        serialized = json.dumps(runtime, allow_nan=False)
        self.assertNotIn(TOKEN, serialized)
        saved_path = Path(__file__).resolve().parents[2] / "openapi" / "facefit-ai-openapi-v1.json"
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        self.assertEqual(saved, runtime)


if __name__ == "__main__":
    unittest.main()
