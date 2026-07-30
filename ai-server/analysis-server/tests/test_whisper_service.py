"""Mock-only tests for the reusable WhisperService."""

from __future__ import annotations

import threading
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.speech import whisper_service
from app.speech.whisper_service import WhisperService


class WhisperServiceTests(unittest.TestCase):
    def make_service(self) -> tuple[WhisperService, MagicMock, MagicMock]:
        model = MagicMock()
        factory = MagicMock(return_value=model)
        return WhisperService(model_factory=factory), factory, model

    def test_first_initialize_loads_model(self) -> None:
        service, factory, model = self.make_service()
        self.assertIs(service.initialize(), model)
        self.assertTrue(service.initialized)
        factory.assert_called_once_with("turbo", device="cuda", compute_type="int8_float16")

    def test_same_service_creates_model_only_once(self) -> None:
        service, factory, _ = self.make_service()
        service.initialize()
        service.initialize()
        factory.assert_called_once()

    def test_initialization_count_is_one(self) -> None:
        service, _, _ = self.make_service()
        service.initialize()
        service.initialize()
        self.assertEqual(service.initialization_count, 1)

    def test_later_transcribe_reuses_model(self) -> None:
        service, factory, model = self.make_service()
        info = SimpleNamespace(language="ko")
        model.transcribe.return_value = (iter([]), info)
        service.transcribe("one.wav")
        service.transcribe("two.wav")
        factory.assert_called_once()
        self.assertEqual(model.transcribe.call_count, 2)

    def test_different_settings_use_separate_service_instances(self) -> None:
        factory = MagicMock(side_effect=[MagicMock(), MagicMock()])
        first = WhisperService(model_name="turbo", model_factory=factory)
        second = WhisperService(model_name="other", device="cpu", compute_type="int8", model_factory=factory)
        first.initialize()
        second.initialize()
        self.assertEqual(factory.call_count, 2)
        factory.assert_any_call("turbo", device="cuda", compute_type="int8_float16")
        factory.assert_any_call("other", device="cpu", compute_type="int8")

    def test_model_factory_can_be_injected(self) -> None:
        sentinel_model = object()
        factory = MagicMock(return_value=sentinel_model)
        service = WhisperService(model_factory=factory)
        self.assertIs(service.initialize(), sentinel_model)

    def test_default_factory_registers_dlls_before_model_creation(self) -> None:
        events: list[str] = []
        sentinel_model = object()

        def register() -> dict:
            events.append("register")
            return {}

        def model_factory(*args: object, **kwargs: object) -> object:
            events.append("model")
            return sentinel_model

        fake_module = SimpleNamespace(WhisperModel=model_factory)
        with patch.object(
            whisper_service, "register_cuda_runtime", side_effect=register
        ), patch.dict(sys.modules, {"faster_whisper": fake_module}):
            model = whisper_service.default_model_factory(
                "turbo", device="cuda", compute_type="int8_float16"
            )
        self.assertIs(model, sentinel_model)
        self.assertEqual(events, ["register", "model"])

    def test_initialization_failure_is_preserved(self) -> None:
        service = WhisperService(model_factory=MagicMock(side_effect=RuntimeError("load failed")))
        with self.assertRaisesRegex(RuntimeError, "load failed"):
            service.initialize()
        self.assertFalse(service.initialized)
        self.assertEqual(service.initialization_count, 0)
        self.assertIsNotNone(service.load_time_sec)

    def test_transcribe_options_are_forwarded(self) -> None:
        service, _, model = self.make_service()
        model.transcribe.return_value = (iter([]), SimpleNamespace())
        service.transcribe(Path("audio.wav"))
        self.assertEqual(
            model.transcribe.call_args.kwargs,
            {
                "language": "ko",
                "task": "transcribe",
                "beam_size": 5,
                "word_timestamps": True,
                "vad_filter": False,
            },
        )

    def test_segment_generator_is_consumed(self) -> None:
        service, _, model = self.make_service()
        state = {"finished": False}

        def segments():
            yield SimpleNamespace(text="hello")
            state["finished"] = True

        model.transcribe.return_value = (segments(), SimpleNamespace())
        returned_segments, _ = service.transcribe("audio.wav")
        self.assertTrue(state["finished"])
        self.assertEqual(len(returned_segments), 1)

    def test_status_contains_reuse_information(self) -> None:
        service, _, _ = self.make_service()
        service.initialize()
        status = service.status()
        self.assertEqual(status["model_name"], "turbo")
        self.assertEqual(status["device"], "cuda")
        self.assertEqual(status["compute_type"], "int8_float16")
        self.assertTrue(status["initialized"])
        self.assertEqual(status["initialization_count"], 1)
        self.assertIsNotNone(status["load_time_sec"])

    def test_concurrent_initialize_still_creates_one_model(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        model = MagicMock()

        def factory(*args: object, **kwargs: object) -> MagicMock:
            entered.set()
            release.wait(timeout=2)
            return model

        factory_mock = MagicMock(side_effect=factory)
        service = WhisperService(model_factory=factory_mock)
        threads = [threading.Thread(target=service.initialize) for _ in range(2)]
        threads[0].start()
        self.assertTrue(entered.wait(timeout=2))
        threads[1].start()
        release.set()
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        factory_mock.assert_called_once()
        self.assertEqual(service.initialization_count, 1)


if __name__ == "__main__":
    unittest.main()
