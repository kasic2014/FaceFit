"""Mock-only tests for the single-file faster-whisper Turbo runner."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import transcribe_turbo  # noqa: E402
from app.speech.whisper_service import WhisperService  # noqa: E402


class TranscribeTurboTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.audio = self.directory / "sample.wav"
        self.audio.touch()
        self.inspection = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "metadata": {"duration_sec": 30.0},
        }
        self.word = SimpleNamespace(start=0.1, end=0.5, word=" 안녕", probability=0.9)
        self.segment = SimpleNamespace(
            id=0,
            start=0.0,
            end=1.0,
            text=" 안녕하세요",
            avg_logprob=-0.2,
            no_speech_prob=0.01,
            words=[self.word],
        )
        self.info = SimpleNamespace(language="ko", language_probability=0.98)

    def run_success(self, segments: object | None = None) -> tuple[dict, MagicMock, MagicMock]:
        model = MagicMock()
        model.transcribe.return_value = (
            iter([self.segment]) if segments is None else segments,
            self.info,
        )
        model_factory = MagicMock(return_value=model)
        service = WhisperService(model_factory=model_factory)
        with patch("transcribe_turbo.inspect_audio", return_value=self.inspection):
            result = transcribe_turbo.transcribe_audio(self.audio, service=service)
        return result, model_factory, model

    def test_default_model_is_turbo(self) -> None:
        self.assertEqual(transcribe_turbo.DEFAULT_MODEL, "turbo")

    def test_default_device_is_cuda(self) -> None:
        self.assertEqual(transcribe_turbo.DEFAULT_DEVICE, "cuda")

    def test_default_compute_type_is_int8_float16(self) -> None:
        self.assertEqual(transcribe_turbo.DEFAULT_COMPUTE_TYPE, "int8_float16")

    def test_language_ko_is_forwarded(self) -> None:
        _, _, model = self.run_success()
        self.assertEqual(model.transcribe.call_args.kwargs["language"], "ko")

    def test_task_transcribe_is_forwarded(self) -> None:
        _, _, model = self.run_success()
        self.assertEqual(model.transcribe.call_args.kwargs["task"], "transcribe")

    def test_beam_size_five_is_forwarded(self) -> None:
        _, _, model = self.run_success()
        self.assertEqual(model.transcribe.call_args.kwargs["beam_size"], 5)

    def test_word_timestamps_true_is_forwarded(self) -> None:
        _, _, model = self.run_success()
        self.assertIs(model.transcribe.call_args.kwargs["word_timestamps"], True)

    def test_vad_filter_false_is_forwarded(self) -> None:
        _, _, model = self.run_success()
        self.assertIs(model.transcribe.call_args.kwargs["vad_filter"], False)

    def test_batch_inference_is_not_used(self) -> None:
        self.assertFalse(hasattr(transcribe_turbo, "BatchedInferencePipeline"))

    def test_segments_generator_is_consumed_completely(self) -> None:
        state = {"finished": False}

        def segments():
            yield self.segment
            state["finished"] = True

        self.run_success(segments())
        self.assertTrue(state["finished"])

    def test_segment_json_conversion(self) -> None:
        converted = transcribe_turbo.segment_to_dict(self.segment)
        self.assertEqual(converted["id"], 0)
        self.assertEqual(converted["avg_logprob"], -0.2)
        self.assertEqual(converted["no_speech_prob"], 0.01)

    def test_word_json_conversion(self) -> None:
        converted = transcribe_turbo.word_to_dict(self.word)
        self.assertEqual(converted, {"start": 0.1, "end": 0.5, "word": " 안녕", "probability": 0.9})

    def test_transcript_is_joined(self) -> None:
        second = SimpleNamespace(**{**self.segment.__dict__, "id": 1, "text": " 반갑습니다"})
        result, _, _ = self.run_success(iter([self.segment, second]))
        self.assertEqual(result["transcript"], "안녕하세요 반갑습니다")

    def test_realtime_factor_is_calculated(self) -> None:
        result, _, _ = self.run_success()
        self.assertEqual(
            result["realtime_factor"],
            round(result["transcription_time_sec"] / 30.0, 6),
        )

    def test_input_file_missing(self) -> None:
        result = transcribe_turbo.transcribe_audio(self.directory / "missing.wav")
        self.assertEqual(result["error"]["code"], "INPUT_FILE_NOT_FOUND")

    def test_input_audio_validation_failure(self) -> None:
        invalid = {"valid": False, "errors": ["INVALID_CODEC"], "warnings": [], "metadata": {}}
        with patch("transcribe_turbo.inspect_audio", return_value=invalid):
            result = transcribe_turbo.transcribe_audio(self.audio)
        self.assertEqual(result["error"]["code"], "INPUT_AUDIO_INVALID")

    def test_model_load_failure(self) -> None:
        service = WhisperService(
            model_factory=MagicMock(side_effect=RuntimeError("model is corrupt"))
        )
        with patch("transcribe_turbo.inspect_audio", return_value=self.inspection):
            result = transcribe_turbo.transcribe_audio(self.audio, service=service)
        self.assertEqual(result["error"]["code"], "MODEL_LOAD_FAILED")

    def test_cuda_device_missing_is_classified(self) -> None:
        error = RuntimeError("No CUDA device found")
        self.assertEqual(transcribe_turbo.classify_exception(error, "model_load"), "CUDA_DEVICE_NOT_FOUND")

    def test_cublas_error_is_classified(self) -> None:
        error = RuntimeError("Library cublas64_12.dll is not found")
        self.assertEqual(transcribe_turbo.classify_exception(error, "model_load"), "CUBLAS_NOT_FOUND")

    def test_cudnn_error_is_classified(self) -> None:
        error = RuntimeError("Could not load cudnn64_9.dll")
        self.assertEqual(transcribe_turbo.classify_exception(error, "model_load"), "CUDNN_NOT_FOUND")

    def test_cuda_oom_is_classified(self) -> None:
        error = RuntimeError("CUDA out of memory")
        self.assertEqual(transcribe_turbo.classify_exception(error, "transcription"), "CUDA_OUT_OF_MEMORY")

    def test_transcription_failure(self) -> None:
        model = MagicMock()
        model.transcribe.side_effect = RuntimeError("decoder failed")
        service = WhisperService(model_factory=MagicMock(return_value=model))
        with patch("transcribe_turbo.inspect_audio", return_value=self.inspection):
            result = transcribe_turbo.transcribe_audio(self.audio, service=service)
        self.assertEqual(result["error"]["code"], "TRANSCRIPTION_FAILED")

    def test_existing_json_result_contract_is_preserved(self) -> None:
        result = transcribe_turbo.new_result(self.audio)
        self.assertEqual(
            set(result),
            {
                "model", "model_description", "device", "compute_type", "language",
                "detected_language", "language_probability", "audio_file",
                "audio_duration_sec", "model_load_time_sec", "transcription_time_sec",
                "total_time_sec", "realtime_factor", "transcript", "segments",
                "warnings", "error",
            },
        )

    def test_json_output_success(self) -> None:
        result = transcribe_turbo.new_result(self.audio)
        output = self.directory / "result.json"
        self.assertTrue(transcribe_turbo.write_result_json(result, output))
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["model"], "turbo")

    def test_json_output_failure(self) -> None:
        result = transcribe_turbo.new_result(self.audio)
        with patch("transcribe_turbo.Path.write_text", side_effect=OSError("access denied")):
            success = transcribe_turbo.write_result_json(result, self.directory / "result.json")
        self.assertFalse(success)
        self.assertEqual(result["error"]["code"], "OUTPUT_WRITE_FAILED")

    def test_model_download_failure_is_classified(self) -> None:
        error = RuntimeError("snapshot_download connection timed out")
        self.assertEqual(transcribe_turbo.classify_exception(error, "model_load"), "MODEL_DOWNLOAD_FAILED")

    def test_unsupported_compute_type_is_classified(self) -> None:
        error = ValueError("Compute type int8_float16 is not supported")
        self.assertEqual(transcribe_turbo.classify_exception(error, "model_load"), "UNSUPPORTED_COMPUTE_TYPE")

    def test_cuda_runtime_error_is_classified(self) -> None:
        error = RuntimeError("CUDA runtime initialization failed")
        self.assertEqual(transcribe_turbo.classify_exception(error, "model_load"), "CUDA_RUNTIME_ERROR")


if __name__ == "__main__":
    unittest.main()
