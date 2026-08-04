from __future__ import annotations

import math
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerModelError,
    AnalyzerPayloadTooLarge,
    AnalyzerUnavailable,
)
from app.services.stt_analyzer import WhisperSttAnalyzer, probe_answer_media
from app.speech.whisper_service import WhisperService


class FakeModel:
    def __init__(
        self,
        *,
        text: str = " 테스트 전사",
        language: str = "ko",
        duration: float = 12.34,
        failure: Exception | None = None,
    ) -> None:
        self.text = text
        self.language = language
        self.duration = duration
        self.failure = failure
        self.calls = 0

    def transcribe(self, _path: str, **_options):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return (
            iter([SimpleNamespace(text=self.text)]),
            SimpleNamespace(language=self.language, duration=self.duration),
        )


class WhisperSttAnalyzerTest(unittest.TestCase):
    def test_media_probe_converts_pyav_microseconds_to_seconds(self) -> None:
        class Container:
            duration = 12_340_000
            streams = (SimpleNamespace(type="audio"), SimpleNamespace(type="video"))

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        fake_av = SimpleNamespace(time_base=1_000_000, open=lambda _path: Container())
        with patch.dict(sys.modules, {"av": fake_av}):
            self.assertEqual(probe_answer_media(Path("answer.mp4")), 12.34)

    def analyzer(
        self,
        model: FakeModel,
        *,
        transcript_max_chars: int = 100,
        max_duration_seconds: int = 300,
    ) -> tuple[WhisperSttAnalyzer, WhisperService]:
        service = WhisperService(
            model_name="contract-model",
            device="cpu",
            compute_type="int8",
            model_factory=lambda *_args, **_kwargs: model,
        )
        return (
            WhisperSttAnalyzer(
                service,
                transcript_max_chars=transcript_max_chars,
                max_duration_seconds=max_duration_seconds,
                media_probe=lambda _path: model.duration,
                runtime_version="test-runtime",
            ),
            service,
        )

    def test_maps_real_whisper_service_boundary_and_reuses_model(self) -> None:
        model = FakeModel()
        analyzer, service = self.analyzer(model)
        first = analyzer.analyze(Path("first.mp4"), "ko")
        second = analyzer.analyze(Path("second.mp4"), "ko")
        self.assertEqual(first.transcript, "테스트 전사")
        self.assertEqual(first.language, "ko")
        self.assertEqual(first.duration_seconds, 12.34)
        self.assertEqual(
            first.model_version,
            "faster-whisper:test-runtime:contract-model",
        )
        self.assertEqual(second.model_version, first.model_version)
        self.assertEqual(service.initialization_count, 1)
        self.assertEqual(model.calls, 2)

    def test_rejects_blank_oversized_or_wrong_language_transcript(self) -> None:
        cases = (
            (FakeModel(text=" "), 100),
            (FakeModel(text="x" * 11), 10),
            (FakeModel(language="en"), 100),
        )
        for model, limit in cases:
            with self.subTest(model=model, limit=limit):
                analyzer, _service = self.analyzer(
                    model,
                    transcript_max_chars=limit,
                )
                with self.assertRaises(AnalyzerMediaFailure):
                    analyzer.analyze(Path("answer.mp4"), "ko")

    def test_rejects_invalid_or_excessive_duration(self) -> None:
        for duration in (0.0, -1.0, math.nan, math.inf):
            with self.subTest(duration=duration):
                analyzer, _service = self.analyzer(FakeModel(duration=duration))
                with self.assertRaises(AnalyzerMediaFailure):
                    analyzer.analyze(Path("answer.mp4"), "ko")
        analyzer, _service = self.analyzer(
            FakeModel(duration=300.1),
            max_duration_seconds=300,
        )
        with self.assertRaises(AnalyzerPayloadTooLarge):
            analyzer.analyze(Path("answer.mp4"), "ko")

    def test_model_initialization_failure_is_unavailable(self) -> None:
        service = WhisperService(
            model_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ModuleNotFoundError("provider detail")
            )
        )
        analyzer = WhisperSttAnalyzer(
            service,
            transcript_max_chars=100,
            max_duration_seconds=300,
            media_probe=lambda _path: 12.34,
            runtime_version="test-runtime",
        )
        with self.assertRaises(AnalyzerUnavailable):
            analyzer.analyze(Path("answer.mp4"), "ko")

    def test_initialized_model_runtime_failure_is_model_error(self) -> None:
        model = FakeModel()
        analyzer, service = self.analyzer(model)
        service.initialize()
        model.failure = RuntimeError("provider detail")
        with self.assertRaises(AnalyzerModelError):
            analyzer.analyze(Path("answer.mp4"), "ko")


if __name__ == "__main__":
    unittest.main()
