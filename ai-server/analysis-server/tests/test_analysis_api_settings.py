from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.settings import AnalysisApiSettings


class AnalysisApiSettingsTest(unittest.TestCase):
    def test_environment_binding_uses_explicit_values(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "FACEFIT_AI_SERVICE_TOKEN": "test-secret",
                "FACEFIT_AI_MODEL_TIMEOUT_SECONDS": "42",
                "FACEFIT_AI_MAX_UPLOAD_BYTES": "2048",
                "FACEFIT_AI_MAX_DURATION_SECONDS": "120",
                "FACEFIT_AI_TRANSCRIPT_MAX_CHARS": "3000",
                "WHISPER_MODEL_SIZE": "small",
                "WHISPER_DEVICE": "cpu",
                "WHISPER_COMPUTE_TYPE": "int8",
                "FACEFIT_CV_SAMPLE_FPS": "3",
                "FACEFIT_CV_MAX_SAMPLE_FRAMES": "60",
                "FACEFIT_CV_MIN_USABLE_FRAMES": "6",
            },
            clear=True,
        ):
            settings = AnalysisApiSettings.from_environment()
        self.assertEqual(settings.service_token, "test-secret")
        self.assertEqual(settings.model_timeout_seconds, 42)
        self.assertEqual(settings.max_upload_bytes, 2048)
        self.assertEqual(settings.max_duration_seconds, 120)
        self.assertEqual(settings.transcript_max_chars, 3000)
        self.assertEqual(settings.whisper_model_name, "small")
        self.assertEqual(settings.whisper_device, "cpu")
        self.assertEqual(settings.whisper_compute_type, "int8")
        self.assertEqual(settings.cv_sample_fps, 3)
        self.assertEqual(settings.cv_max_sample_frames, 60)
        self.assertEqual(settings.cv_min_usable_frames, 6)

    def test_secret_is_not_in_settings_representation(self) -> None:
        settings = AnalysisApiSettings(
            service_token="DO-NOT-RENDER",
            temp_directory=Path(tempfile.gettempdir()),
        )
        self.assertNotIn("DO-NOT-RENDER", repr(settings))

    def test_timeout_must_be_below_worker_timeout(self) -> None:
        with patch.dict(
            "os.environ",
            {"FACEFIT_AI_MODEL_TIMEOUT_SECONDS": "60"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                AnalysisApiSettings.from_environment()

    def test_numeric_limits_must_be_positive(self) -> None:
        with patch.dict(
            "os.environ",
            {"FACEFIT_AI_MAX_UPLOAD_BYTES": "0"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                AnalysisApiSettings.from_environment()

    def test_cv_limits_fail_before_unbounded_work_can_start(self) -> None:
        for environment in (
            {"FACEFIT_CV_SAMPLE_FPS": "11"},
            {"FACEFIT_CV_MAX_SAMPLE_FRAMES": "121"},
            {
                "FACEFIT_CV_MAX_SAMPLE_FRAMES": "5",
                "FACEFIT_CV_MIN_USABLE_FRAMES": "6",
            },
        ):
            with self.subTest(environment=environment):
                with patch.dict("os.environ", environment, clear=True):
                    with self.assertRaises(ValueError):
                        AnalysisApiSettings.from_environment()


if __name__ == "__main__":
    unittest.main()
