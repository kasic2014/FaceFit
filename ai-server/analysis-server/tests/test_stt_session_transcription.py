from __future__ import annotations

from array import array
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock
import wave


ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))
SCRIPTS_ROOT = ANALYSIS_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from app.audio.interval_audio_extractor import sha256_file  # noqa: E402
from app.stt.faster_whisper_adapter import (  # noqa: E402
    AdapterError,
    FasterWhisperAdapter,
    ModelCacheInfo,
    TranscriptionRun,
    classify_adapter_error,
)
from app.stt.session_transcription_service import (  # noqa: E402
    OPTIONS,
    SessionTranscriptionError,
    SessionTranscriptionInput,
    SessionTranscriptionService,
    resolve_stage24_input,
)
from app.stt.transcription_contracts import (  # noqa: E402
    AnswerAudio,
    TranscriptionContractError,
    build_answer_contract,
    seconds_to_milliseconds,
)
from app.stt import transcription_profile as profiles  # noqa: E402
import transcribe_stt_session as cli  # noqa: E402


def write_wav(path: Path, duration_ms: int = 1000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = array("h", [0] * (16_000 * duration_ms // 1000))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(samples.tobytes())


def answer_audio(index: int = 1, *, duration_ms: int = 1000) -> AnswerAudio:
    start = index * 2000
    return AnswerAudio(
        session_id="SES_000001",
        answer_id=f"ANS_{index:06d}",
        path=Path(f"ANS_{index:06d}.wav"),
        sha256=f"{index:064x}",
        start_ms=start,
        end_ms=start + duration_ms,
        duration_ms=duration_ms,
        sample_count=duration_ms * 16,
    )


def segment(
    start: float = 0.1,
    end: float = 0.9,
    text: str = " 원문",
    *,
    words: list[object] | None = None,
    avg_logprob: float = -0.2,
) -> SimpleNamespace:
    return SimpleNamespace(
        start=start,
        end=end,
        text=text,
        avg_logprob=avg_logprob,
        no_speech_prob=0.01,
        compression_ratio=1.1,
        temperature=0.0,
        words=words,
    )


def word(start: float = 0.1, end: float = 0.5, text: str = " 원") -> SimpleNamespace:
    return SimpleNamespace(start=start, end=end, word=text, probability=0.9)


def info(language: str = "ko") -> SimpleNamespace:
    return SimpleNamespace(language=language, language_probability=0.99)


class ProfileTests(unittest.TestCase):
    def test_auto_prefers_supported_cuda_float16(self) -> None:
        capabilities = {
            "ctranslate2Available": True,
            "cudaDeviceCount": 1,
            "cudaComputeTypes": ["float16"],
            "cpuComputeTypes": ["int8"],
        }
        with mock.patch.object(profiles, "runtime_capabilities", return_value=capabilities):
            selected = profiles.resolve_profile("auto")
        self.assertEqual((selected.model, selected.device, selected.compute_type),
                         ("large-v3-turbo", "cuda", "float16"))
        self.assertFalse(selected.fallback_model)

    def test_auto_uses_cpu_int8_when_cuda_is_unavailable(self) -> None:
        capabilities = {
            "ctranslate2Available": True,
            "cudaDeviceCount": 0,
            "cudaComputeTypes": [],
            "cpuComputeTypes": ["int8"],
        }
        with mock.patch.object(profiles, "runtime_capabilities", return_value=capabilities):
            self.assertEqual(profiles.resolve_profile("auto").name, "cpu-int8")

    def test_explicit_unavailable_profile_is_rejected_without_fallback(self) -> None:
        capabilities = {
            "ctranslate2Available": True,
            "cudaDeviceCount": 0,
            "cudaComputeTypes": [],
            "cpuComputeTypes": ["int8"],
        }
        with mock.patch.object(profiles, "runtime_capabilities", return_value=capabilities):
            with self.assertRaises(profiles.ProfileError) as caught:
                profiles.resolve_profile("cuda-float16")
        self.assertEqual(caught.exception.code, "STT_RUNTIME_UNAVAILABLE")

    def test_missing_ctranslate2_is_a_dependency_block(self) -> None:
        capabilities = {
            "ctranslate2Available": False, "cudaDeviceCount": 0,
            "cudaComputeTypes": [], "cpuComputeTypes": [],
            "errorType": "ModuleNotFoundError",
        }
        with mock.patch.object(profiles, "runtime_capabilities", return_value=capabilities):
            with self.assertRaises(profiles.ProfileError) as caught:
                profiles.resolve_profile("auto")
        self.assertEqual(caught.exception.code, "STT_DEPENDENCY_BLOCKED")


class TimestampContractTests(unittest.TestCase):
    def test_nearest_millisecond_rounds_halves_up(self) -> None:
        self.assertEqual(seconds_to_milliseconds(0.0004), 0)
        self.assertEqual(seconds_to_milliseconds(0.0005), 1)
        self.assertEqual(seconds_to_milliseconds(1.2345), 1235)

    def test_relative_and_session_timestamps_are_consistent(self) -> None:
        result = build_answer_contract(
            answer_audio(), segments_raw=[segment(words=[word()])], info=info(),
            processing_time_seconds=0.25,
        )
        self.assertEqual(result["segments"][0]["startMsRelative"], 100)
        self.assertEqual(result["segments"][0]["startMsSession"], 2100)
        self.assertEqual(result["words"][0]["endMsSession"], 2500)

    def test_one_millisecond_boundary_overage_is_adjusted_and_recorded(self) -> None:
        result = build_answer_contract(
            answer_audio(), segments_raw=[segment(0.1, 1.001, words=[])], info=info(),
            processing_time_seconds=0.1,
        )
        self.assertEqual(result["segments"][0]["endMsRelative"], 1000)
        self.assertIn("TIMESTAMP_ROUNDING_ADJUSTED", result["warnings"])

    def test_larger_answer_boundary_overage_is_rejected(self) -> None:
        with self.assertRaises(TranscriptionContractError) as caught:
            build_answer_contract(
                answer_audio(), segments_raw=[segment(0.1, 1.002)], info=info(),
                processing_time_seconds=0.1,
            )
        self.assertEqual(caught.exception.code, "TIMESTAMP_OUT_OF_RANGE")

    def test_non_monotonic_segments_are_rejected(self) -> None:
        with self.assertRaises(TranscriptionContractError) as caught:
            build_answer_contract(
                answer_audio(),
                segments_raw=[segment(0.4, 0.7), segment(0.3, 0.8)],
                info=info(), processing_time_seconds=0.1,
            )
        self.assertEqual(caught.exception.code, "NON_MONOTONIC_TIMESTAMP")

    def test_segment_expands_to_preserve_model_word_timestamps(self) -> None:
        result = build_answer_contract(
            answer_audio(), segments_raw=[segment(0.2, 0.8, words=[word(0.1, 0.9)])],
            info=info(), processing_time_seconds=0.1,
        )
        segment_result = result["segments"][0]
        self.assertEqual((segment_result["startMsRelative"], segment_result["endMsRelative"]),
                         (100, 900))
        self.assertEqual((segment_result["modelStartMsRelative"],
                          segment_result["modelEndMsRelative"]), (200, 800))
        self.assertIn("SEGMENT_BOUNDARY_EXPANDED_TO_WORDS", result["warnings"])

    def test_word_outside_answer_boundary_is_rejected(self) -> None:
        with self.assertRaises(TranscriptionContractError) as caught:
            build_answer_contract(
                answer_audio(), segments_raw=[segment(0.2, 0.8, words=[word(0.5, 1.002)])],
                info=info(), processing_time_seconds=0.1,
            )
        self.assertEqual(caught.exception.code, "TIMESTAMP_OUT_OF_RANGE")

    def test_nan_diagnostic_is_rejected(self) -> None:
        with self.assertRaises(TranscriptionContractError) as caught:
            build_answer_contract(
                answer_audio(), segments_raw=[segment(avg_logprob=math.nan)], info=info(),
                processing_time_seconds=0.1,
            )
        self.assertEqual(caught.exception.code, "NON_FINITE_VALUE")

    def test_raw_model_text_and_word_spacing_are_preserved(self) -> None:
        result = build_answer_contract(
            answer_audio(),
            segments_raw=[segment(text="  원문 그대로 ", words=[word(text=" 원문")])],
            info=info(), processing_time_seconds=0.1,
        )
        self.assertEqual(result["text"], "  원문 그대로 ")
        self.assertEqual(result["words"][0]["text"], " 원문")

    def test_empty_transcript_and_missing_words_require_review(self) -> None:
        result = build_answer_contract(
            answer_audio(), segments_raw=[], info=info(), processing_time_seconds=0.1
        )
        self.assertEqual(result["status"], "MANUAL_REVIEW_REQUIRED")
        self.assertTrue({"EMPTY_TRANSCRIPT", "NO_SEGMENTS", "NO_WORD_TIMESTAMPS"}
                        .issubset(result["warnings"]))

    def test_language_mismatch_is_a_warning_not_content_evaluation(self) -> None:
        result = build_answer_contract(
            answer_audio(), segments_raw=[segment(words=[word()])], info=info("en"),
            processing_time_seconds=0.1,
        )
        self.assertEqual(result["status"], "COMPLETE_WITH_WARNINGS")
        self.assertIn("LANGUAGE_MISMATCH", result["warnings"])

    def test_three_repeated_segments_are_flagged_for_manual_review(self) -> None:
        rows = [segment(0.0, 0.2, " 반복"), segment(0.2, 0.4, " 반복"),
                segment(0.4, 0.6, " 반복")]
        result = build_answer_contract(
            answer_audio(), segments_raw=rows, info=info(), processing_time_seconds=0.1
        )
        self.assertIn("REPETITIVE_OUTPUT_CANDIDATE", result["warnings"])
        self.assertEqual(result["status"], "MANUAL_REVIEW_REQUIRED")


class Stage24ResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        session_root = self.root / "SES_000001"
        rows = []
        for index in range(1, 5):
            answer_id = f"ANS_{index:06d}"
            path = session_root / "intervals" / f"{answer_id}.wav"
            write_wav(path)
            rows.append({
                "intervalType": "ANSWER", "answerId": answer_id,
                "startMs": index * 2000, "endMs": index * 2000 + 1000,
                "actualDurationMs": 1000, "sampleCount": 16000,
                "audio": {"sha256": sha256_file(path)},
            })
        manifest = {
            "sessionId": "SES_000001", "status": "stt_audio_preprocessing_ready",
            "intervalContractSha256": "a" * 64, "intervals": rows,
        }
        (session_root / "interval_audio_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_resolves_exactly_four_ordered_answer_wavs(self) -> None:
        resolved = resolve_stage24_input("SES_000001", preprocessing_root=self.root)
        self.assertEqual([row.answer_id for row in resolved.answers],
                         [f"ANS_{index:06d}" for index in range(1, 5)])
        self.assertTrue(all(row.sample_count == 16000 for row in resolved.answers))

    def test_hash_mismatch_is_rejected(self) -> None:
        target = self.root / "SES_000001" / "intervals" / "ANS_000001.wav"
        target.write_bytes(b"corrupt")
        with self.assertRaises(SessionTranscriptionError) as caught:
            resolve_stage24_input("SES_000001", preprocessing_root=self.root)
        self.assertEqual(caught.exception.code, "STAGE24_AUDIO_INVALID")

    def test_invalid_session_id_is_rejected(self) -> None:
        with self.assertRaises(SessionTranscriptionError) as caught:
            resolve_stage24_input("../SES_000001", preprocessing_root=self.root)
        self.assertEqual(caught.exception.code, "INVALID_SESSION_ID")


class FakeAdapter:
    initialize_count = 0
    transcribe_count = 0
    fail = False

    def __init__(self, profile: profiles.TranscriptionProfile, *, local_files_only: bool) -> None:
        self.profile = profile
        self.local_files_only = local_files_only

    @classmethod
    def reset(cls) -> None:
        cls.initialize_count = 0
        cls.transcribe_count = 0
        cls.fail = False

    def initialize(self) -> None:
        type(self).initialize_count += 1

    def engine_metadata(self) -> dict[str, object]:
        return {
            "name": "faster-whisper", "version": "1.2.1",
            "ctranslate2Version": "4.8.1", "profile": self.profile.name,
            "model": self.profile.model, "modelId": self.profile.model_id,
            "revision": self.profile.revision, "device": self.profile.device,
            "computeType": self.profile.compute_type, "fallbackModel": False,
            "cache": {"status": "CACHED", "modelId": self.profile.model_id,
                      "revision": self.profile.revision, "sizeBytes": 100},
            "localFilesOnly": self.local_files_only,
            "localFilesOnlyValidated": self.local_files_only,
            "modelLoadTimeSeconds": 0.01, "pythonVersion": sys.version.split()[0],
        }

    def transcribe(self, path: Path) -> TranscriptionRun:
        type(self).transcribe_count += 1
        if type(self).fail:
            raise AdapterError("STT_TRANSCRIPTION_FAILED", "fake failure")
        row = segment(words=[word(), word(0.5, 0.9, " 그대로")])
        return TranscriptionRun([row], info(), 0.05)


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "output"
        self.source = SessionTranscriptionInput(
            session_id="SES_000001", stage24_manifest_sha256="1" * 64,
            stage24_interval_contract_sha256="2" * 64,
            answers=tuple(answer_audio(index) for index in range(1, 5)),
        )
        FakeAdapter.reset()
        self.service = SessionTranscriptionService(
            profile=profiles.CUDA_FLOAT16, local_files_only=True,
            output_root=self.output, resolver=lambda _session_id, **_kwargs: self.source,
            adapter_factory=FakeAdapter,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_pipeline_writes_required_tree_and_fixed_options(self) -> None:
        result = self.service.run("SES_000001")
        self.assertEqual(result["status"], "stt_session_transcription_ready")
        root = self.output / "SES_000001"
        expected = [*(f"answers/ANS_{index:06d}.json" for index in range(1, 5)),
                    "session_transcription_manifest.json", "transcription_validation.json",
                    "transcription_review.md", "transcription_report.md"]
        self.assertTrue(all((root / item).is_file() for item in expected))
        manifest = json.loads((root / expected[4]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["options"], OPTIONS)
        self.assertEqual(manifest["engine"]["model"], "large-v3-turbo")
        self.assertEqual(FakeAdapter.initialize_count, 1)
        self.assertEqual(FakeAdapter.transcribe_count, 4)

    def test_outputs_are_strict_and_exclude_paths_and_participant_ids(self) -> None:
        self.service.run("SES_000001")
        root = self.output / "SES_000001"
        for path in root.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            json.loads(text, parse_constant=lambda value: self.fail(value))
            self.assertNotIn("PTC_", text)
            self.assertNotIn(str(self.root), text)
        for path in (root / "answers").glob("*.json"):
            text = path.read_text(encoding="utf-8")
            json.loads(text, parse_constant=lambda value: self.fail(value))
            self.assertNotIn("PTC_", text)
            self.assertNotIn(str(self.root), text)

    def test_identical_input_is_reused_without_loading_model(self) -> None:
        self.assertFalse(self.service.run("SES_000001")["reused"])
        self.assertTrue(self.service.run("SES_000001")["reused"])
        self.assertEqual(FakeAdapter.initialize_count, 1)
        self.assertEqual(FakeAdapter.transcribe_count, 4)

    def test_corrupted_answer_json_is_rebuilt(self) -> None:
        self.service.run("SES_000001")
        answer = self.output / "SES_000001" / "answers" / "ANS_000001.json"
        answer.write_text("{}", encoding="utf-8")
        self.assertFalse(self.service.run("SES_000001")["reused"])
        self.assertEqual(FakeAdapter.transcribe_count, 8)

    def test_corrupted_validation_artifact_is_rebuilt(self) -> None:
        self.service.run("SES_000001")
        validation = self.output / "SES_000001" / "transcription_validation.json"
        validation.write_text("{}", encoding="utf-8")
        self.assertFalse(self.service.run("SES_000001")["reused"])
        self.assertEqual(FakeAdapter.transcribe_count, 8)

    def test_force_rebuild_transcribes_all_answers_again(self) -> None:
        self.service.run("SES_000001")
        self.assertFalse(self.service.run("SES_000001", force_rebuild=True)["reused"])
        self.assertEqual(FakeAdapter.transcribe_count, 8)

    def test_failed_force_rebuild_preserves_existing_complete_result(self) -> None:
        self.service.run("SES_000001")
        manifest = self.output / "SES_000001" / "session_transcription_manifest.json"
        before = hashlib.sha256(manifest.read_bytes()).hexdigest()
        FakeAdapter.fail = True
        with self.assertRaises(SessionTranscriptionError):
            self.service.run("SES_000001", force_rebuild=True)
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), before)
        self.assertEqual(list(self.output.glob("*.tmp")), [])


class AdapterAndCliTests(unittest.TestCase):
    def test_adapter_forwards_only_official_transcription_options(self) -> None:
        service = mock.MagicMock()
        service.load_time_sec = 0.01
        service.transcribe.return_value = ([], info())
        factory = mock.MagicMock(return_value=service)
        cached = ModelCacheInfo(True, profiles.MODEL_ID, profiles.MODEL_REVISION, 123)
        with mock.patch("app.stt.faster_whisper_adapter.inspect_model_cache", return_value=cached):
            adapter = FasterWhisperAdapter(profiles.CUDA_FLOAT16, service_factory=factory)
            adapter.transcribe(Path("answer.wav"))
        self.assertEqual(service.transcribe.call_args.kwargs, {
            "language": "ko", "task": "transcribe", "beam_size": 5,
            "word_timestamps": True, "vad_filter": False,
            "condition_on_previous_text": False, "temperature": 0.0,
        })
        self.assertTrue(factory.call_args.kwargs["local_files_only"])
        self.assertEqual(factory.call_args.kwargs["revision"], profiles.MODEL_REVISION)

    def test_cuda_failure_is_classified_as_runtime_unavailable(self) -> None:
        code = classify_adapter_error(RuntimeError("Could not load cublas64.dll"), loading=True)
        self.assertEqual(code, "STT_RUNTIME_UNAVAILABLE")

    def test_network_model_failure_is_classified_as_download_blocked(self) -> None:
        code = classify_adapter_error(RuntimeError("HuggingFace connection timed out"), loading=True)
        self.assertEqual(code, "STT_MODEL_DOWNLOAD_BLOCKED")

    def test_cli_rejects_arbitrary_media_and_participant_options(self) -> None:
        for option, value in (("--audio-path", "x.wav"), ("--video-path", "x.mp4"),
                              ("--participant-id", "PTC_000001")):
            with self.subTest(option=option), self.assertRaises(SystemExit):
                cli.build_parser().parse_args(["--session-id", "SES_000001", option, value])


if __name__ == "__main__":
    unittest.main()
