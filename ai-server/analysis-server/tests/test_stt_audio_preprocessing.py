from __future__ import annotations

from array import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock
import wave


ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))
SCRIPTS_ROOT = ANALYSIS_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from app.audio.audio_contracts import (  # noqa: E402
    AudioContractError,
    AudioInterval,
    SessionAudioInput,
    milliseconds_to_sample,
    validate_session_id,
)
from app.audio.audio_manifest_writer import (  # noqa: E402
    ManifestWriteError,
    strict_json_bytes,
    write_json_atomic,
)
from app.audio.interval_audio_extractor import (  # noqa: E402
    extract_intervals,
    inspect_pcm_wav,
    sha256_file,
)
from app.audio import session_audio_preprocessor as preprocessing  # noqa: E402
from app.audio.session_audio_preprocessor import (  # noqa: E402
    PreprocessingError,
    SessionAudioPreprocessor,
    extract_source_audio,
    resolve_session_input,
)
import build_stt_audio_preprocessing as cli  # noqa: E402


def write_wav(
    path: Path,
    *,
    rate: int = 16_000,
    channels: int = 1,
    duration_ms: int = 1000,
    amplitude: int = 5000,
) -> None:
    samples_per_channel = rate * duration_ms // 1000
    samples = array("h")
    for index in range(samples_per_channel):
        value = int(amplitude * math.sin(2 * math.pi * 220 * index / rate))
        samples.extend([value] * channels)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(samples.tobytes())


class ContractTests(unittest.TestCase):
    def test_session_id_validation(self) -> None:
        self.assertEqual(validate_session_id("SES_000001"), "SES_000001")
        for invalid in ("SES_1", "PTC_000001", "../SES_000001", "SES_000001/.."):
            with self.subTest(invalid=invalid), self.assertRaises(AudioContractError):
                validate_session_id(invalid)

    def test_floor_millisecond_sample_conversion(self) -> None:
        self.assertEqual(milliseconds_to_sample(0), 0)
        self.assertEqual(milliseconds_to_sample(1), 16)
        self.assertEqual(milliseconds_to_sample(10_999), 175_984)

    def test_start_inclusive_end_exclusive_counts(self) -> None:
        item = AudioInterval("ANSWER", "ANS_000001", 11_000, 50_000, "ANS_000001")
        self.assertEqual(item.start_sample, 176_000)
        self.assertEqual(item.end_sample, 800_000)
        self.assertEqual(item.expected_sample_count, 624_000)

    def test_empty_interval_is_rejected(self) -> None:
        with self.assertRaises(AudioContractError) as caught:
            AudioInterval("BASELINE", "BASELINE", 100, 100)
        self.assertEqual(caught.exception.code, "EMPTY_AUDIO")


class ManifestTests(unittest.TestCase):
    def test_strict_json_rejects_nan_and_infinity(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ManifestWriteError):
                strict_json_bytes({"value": value})

    def test_atomic_json_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "result.json"
            write_json_atomic(output, {"ok": True})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"ok": True})
            self.assertEqual(list(root.glob("*.tmp")), [])


class IntervalExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.wav"
        write_wav(self.source, duration_ms=2000)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_wav_contract_and_exact_samples(self) -> None:
        inspection = inspect_pcm_wav(self.source)
        self.assertEqual(inspection["sampleRateHz"], 16_000)
        self.assertEqual(inspection["channels"], 1)
        self.assertEqual(inspection["sampleWidthBits"], 16)
        self.assertEqual(inspection["sampleCount"], 32_000)
        self.assertTrue(inspection["decodable"])

    def test_interval_outputs_have_expected_samples(self) -> None:
        definitions = (
            AudioInterval("BASELINE", "BASELINE", 0, 1000),
            AudioInterval("ANSWER", "ANS_000001", 1000, 2000, "ANS_000001"),
        )
        result = extract_intervals(self.source, self.root / "intervals", definitions)
        self.assertEqual([item["sampleCount"] for item in result], [16_000, 16_000])
        self.assertEqual([item["actualDurationMs"] for item in result], [1000, 1000])

    def test_interval_out_of_range_is_rejected(self) -> None:
        definition = AudioInterval("ANSWER", "ANS_000001", 1000, 2001, "ANS_000001")
        with self.assertRaises(AudioContractError) as caught:
            extract_intervals(self.source, self.root / "intervals", (definition,))
        self.assertEqual(caught.exception.code, "INTERVAL_OUT_OF_RANGE")

    def test_near_silence_and_clipping_are_only_warnings(self) -> None:
        silent = self.root / "silent.wav"
        write_wav(silent, amplitude=0)
        self.assertIn("NEAR_SILENT_AUDIO", inspect_pcm_wav(silent)["warnings"])
        clipped = self.root / "clipped.wav"
        write_wav(clipped, amplitude=32767)
        # A sinusoid may not land exactly on the endpoint, so force PCM endpoints.
        with wave.open(str(clipped), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16_000)
            stream.writeframes(array("h", [32767, -32767] * 8000).tobytes())
        self.assertIn("CLIPPING_DETECTED", inspect_pcm_wav(clipped)["warnings"])

    def test_malformed_wav_is_not_decodable(self) -> None:
        malformed = self.root / "bad.wav"
        malformed.write_bytes(b"not a wave")
        inspection = inspect_pcm_wav(malformed)
        self.assertFalse(inspection["decodable"])
        self.assertIn("AUDIO_DECODE_FAILED", inspection["errors"])


class DecoderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_stereo_96khz_is_standardized_by_pyav(self) -> None:
        source = self.root / "stereo.wav"
        output = self.root / "standard.wav"
        write_wav(source, rate=96_000, channels=2, duration_ms=250)
        with mock.patch.object(preprocessing, "resolve_ffmpeg", return_value=None):
            method, warnings = extract_source_audio(source, output)
        inspection = inspect_pcm_wav(output)
        self.assertEqual(method, "PYAV")
        self.assertIn("FFMPEG_UNAVAILABLE_PYAV_FALLBACK", warnings)
        self.assertEqual(inspection["sampleRateHz"], 16_000)
        self.assertEqual(inspection["channels"], 1)
        self.assertEqual(inspection["sampleWidthBits"], 16)

    def test_ffmpeg_failure_is_reported(self) -> None:
        source = self.root / "source.wav"
        output = self.root / "output.wav"
        executable = self.root / "ffmpeg.exe"
        executable.write_bytes(b"")
        write_wav(source)
        failed = {"success": False, "errors": ["FFMPEG_NONZERO_EXIT"]}
        with mock.patch.object(preprocessing, "convert_audio_to_stt", return_value=failed):
            with self.assertRaises(PreprocessingError) as caught:
                extract_source_audio(source, output, ffmpeg_path=executable)
        self.assertEqual(caught.exception.code, "AUDIO_DECODE_FAILED")

    def test_media_without_audio_stream_is_rejected(self) -> None:
        class FakeContainer:
            streams = types.SimpleNamespace(audio=[], video=[object()])
            def __enter__(self): return self
            def __exit__(self, *args): return None
        fake_av = types.SimpleNamespace(open=lambda _: FakeContainer())
        with mock.patch.dict(sys.modules, {"av": fake_av}):
            with self.assertRaises(PreprocessingError) as caught:
                preprocessing.probe_media(self.root / "video.mp4")
        self.assertEqual(caught.exception.code, "AUDIO_STREAM_MISSING")


class CanonicalResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.incoming = self.root / "data" / "pilot" / "incoming"
        self.incoming.mkdir(parents=True)
        self.stem = "PTC_000001_SES_000001"
        self.video = self.incoming / f"{self.stem}.mp4"
        self.video.write_bytes(b"canonical media")
        metadata = {
            "participant_id": "PTC_000001",
            "session_id": "SES_000001",
            "consent_reference_id": "CNS_1",
            "video_file": self.video.name,
            "expected_sha256": sha256_file(self.video),
            "baseline_interval": {"start_timestamp_ms": 0, "end_timestamp_ms": 1000},
            "answers": [{
                "answer_id": "ANS_000001", "start_timestamp_ms": 1000,
                "end_timestamp_ms": 2000,
            }],
            "withdrawn": False,
        }
        consent = {
            "participant_id": "PTC_000001", "consent_reference_id": "CNS_1",
            "consent_status": "GRANTED", "video_collection_allowed": True,
            "automated_analysis_allowed": True, "withdrawn_at": None,
        }
        (self.incoming / f"{self.stem}.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (self.incoming / f"{self.stem}.consent.json").write_text(json.dumps(consent), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_resolves_video_and_intervals_from_session_only(self) -> None:
        resolved = resolve_session_input("SES_000001", vision_server_root=self.root)
        self.assertEqual(resolved.video_path, self.video)
        self.assertEqual([item.output_id for item in resolved.intervals], ["BASELINE", "ANS_000001"])

    def test_hash_mismatch_is_rejected(self) -> None:
        self.video.write_bytes(b"changed")
        with self.assertRaises(PreprocessingError) as caught:
            resolve_session_input("SES_000001", vision_server_root=self.root)
        self.assertEqual(caught.exception.code, "SOURCE_HASH_MISMATCH")

    def test_cli_has_no_arbitrary_video_or_participant_option(self) -> None:
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--session-id", "SES_000001", "--video-path", "x.mp4"])
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--session-id", "SES_000001", "--participant-id", "PTC_000001"])


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "fixture.wav"
        write_wav(self.source, duration_ms=2000)
        self.session = SessionAudioInput(
            session_id="SES_000001",
            video_path=self.source,
            metadata_path=self.root / "metadata.json",
            source_sha256=sha256_file(self.source),
            intervals=(
                AudioInterval("BASELINE", "BASELINE", 0, 1000),
                AudioInterval("ANSWER", "ANS_000001", 1000, 2000, "ANS_000001"),
            ),
        )
        self.output = self.root / "output"
        self.service = SessionAudioPreprocessor(output_root=self.output, resolver=lambda _: self.session)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def fake_extract(self, source: Path, output: Path, **_: object) -> tuple[str, list[str]]:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.source, output)
        return "TEST", []

    def run_service(self, *, force: bool = False) -> dict[str, object]:
        with mock.patch.object(preprocessing, "resolve_ffmpeg", return_value=None), mock.patch.object(
            preprocessing, "probe_media", return_value={"audioStreamCount": 1}
        ), mock.patch.object(preprocessing, "extract_source_audio", side_effect=self.fake_extract):
            return self.service.run("SES_000001", force_rebuild=force)

    def test_pipeline_writes_required_tree_and_public_manifest(self) -> None:
        result = self.run_service()
        self.assertEqual(result["status"], "stt_audio_preprocessing_ready")
        session_root = self.output / "SES_000001"
        expected = [
            "source_audio/SES_000001_source.wav", "intervals/BASELINE.wav",
            "intervals/ANS_000001.wav", "source_audio_metadata.json",
            "interval_audio_manifest.json", "preprocessing_validation.json",
            "preprocessing_report.md",
        ]
        self.assertTrue(all((session_root / item).is_file() for item in expected))
        manifest_text = (session_root / "interval_audio_manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("PTC_", manifest_text)
        self.assertNotIn(str(self.root), manifest_text)
        manifest = json.loads(manifest_text)
        self.assertEqual([item["sampleCount"] for item in manifest["intervals"]], [16_000, 16_000])

    def test_identical_input_is_reused_and_corruption_rebuilds(self) -> None:
        self.assertFalse(self.run_service()["reused"])
        self.assertTrue(self.run_service()["reused"])
        target = self.output / "SES_000001" / "intervals" / "BASELINE.wav"
        target.write_bytes(b"corrupt")
        self.assertFalse(self.run_service()["reused"])
        self.assertTrue(inspect_pcm_wav(target)["decodable"])

    def test_force_rebuild(self) -> None:
        self.run_service()
        self.assertFalse(self.run_service(force=True)["reused"])

    def test_source_duration_mismatch_is_a_technical_warning(self) -> None:
        with mock.patch.object(preprocessing, "resolve_ffmpeg", return_value=None), mock.patch.object(
            preprocessing, "probe_media", return_value={"audioStreamCount": 1, "durationMs": 1900}
        ), mock.patch.object(preprocessing, "extract_source_audio", side_effect=self.fake_extract):
            result = self.service.run("SES_000001")
        self.assertEqual(result["status"], "stt_audio_preprocessing_ready_with_warnings")
        validation = json.loads(
            (self.output / "SES_000001" / "preprocessing_validation.json").read_text(encoding="utf-8")
        )
        self.assertFalse(validation["checks"]["sourceDurationWithinTolerance"])
        self.assertIn("DURATION_MISMATCH", validation["warnings"])

    def test_failed_force_rebuild_preserves_complete_result(self) -> None:
        self.run_service()
        manifest = self.output / "SES_000001" / "interval_audio_manifest.json"
        before = hashlib.sha256(manifest.read_bytes()).hexdigest()
        with mock.patch.object(preprocessing, "resolve_ffmpeg", return_value=None), mock.patch.object(
            preprocessing, "probe_media", return_value={"audioStreamCount": 1}
        ), mock.patch.object(
            preprocessing, "extract_source_audio",
            side_effect=PreprocessingError("AUDIO_DECODE_FAILED", "failed"),
        ):
            with self.assertRaises(PreprocessingError):
                self.service.run("SES_000001", force_rebuild=True)
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), before)
        self.assertEqual(list(self.output.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
