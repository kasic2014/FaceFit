"""Tests for duration validation and one-model prosody batch STT."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import transcribe_prosody_session as transcribe  # noqa: E402


def _write_wav(path: Path, duration: float = 0.05, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * max(1, int(duration * rate)))


def _plan_rows() -> list[dict[str, str]]:
    rows = []
    number = 0
    for script in ("SCRIPT001", "SCRIPT002"):
        for condition in ("clean", "natural"):
            for repetition in (1, 2, 3):
                for device in ("DEV_PC_MIC_01", "DEV_PHONE_01"):
                    number += 1
                    stem = (
                        f"SPK001_{script}_SESSION001_{device}_"
                        f"{condition}_R{repetition:02d}"
                    )
                    rows.append(
                        {
                            "plan_id": f"PLAN{number:03d}",
                            "sample_id": f"SAMPLE{number:03d}",
                            "speaker_code": "SPK001",
                            "session_id": "SESSION001",
                            "script_id": script,
                            "repetition_index": str(repetition),
                            "device_code": device,
                            "environment_code": "QUIET_ROOM",
                            "recording_condition": condition,
                            "recording_order": str(number),
                            "expected_original_filename": stem + ".m4a",
                            "expected_analysis_wav_filename": stem + ".wav",
                            "recording_status": "pending",
                            "transfer_status": "pending",
                            "analysis_status": "pending",
                            "notes": "",
                        }
                    )
    return rows


class FakeModel:
    def __init__(self, *, empty: bool = False) -> None:
        self.calls = 0
        self.empty = empty

    def transcribe(self, audio: str, **kwargs):
        self.calls += 1
        if self.empty:
            return iter([]), SimpleNamespace(language="ko")
        word = SimpleNamespace(
            start=0.0, end=0.04, word=" 안녕하세요", probability=0.99
        )
        segment = SimpleNamespace(
            id=1,
            start=0.0,
            end=0.04,
            text=" 안녕하세요",
            avg_logprob=-0.1,
            no_speech_prob=0.0,
            words=[word],
        )
        self.last_kwargs = kwargs
        return iter([segment]), SimpleNamespace(language="ko")


class FakeService:
    def __init__(self, model: FakeModel) -> None:
        self.model = model
        self.initialization_count = 0
        self.load_time_sec = 0.01

    def initialize(self):
        self.initialization_count += 1
        return self.model


class TranscribeProsodySessionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plan_path = self.root / "plan.csv"
        self.manifest_path = self.root / "conversion.json"
        self.pc_output = self.root / "stt" / "pc"
        self.phone_output = self.root / "stt" / "phone"
        self.batch_json = self.root / "batch.json"
        self.batch_csv = self.root / "batch.csv"
        self.duration_json = self.root / "duration.json"
        self.rows = _plan_rows()
        with self.plan_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=tuple(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        conversions = []
        for row in self.rows:
            group = "pc" if row["device_code"] == "DEV_PC_MIC_01" else "phone"
            standard = (
                self.root / "standard" / group / row["expected_analysis_wav_filename"]
            )
            original = (
                self.root / "original" / group / row["expected_original_filename"]
            )
            _write_wav(standard)
            _write_wav(original, rate=48000)
            conversions.append(
                {
                    "sample_id": row["sample_id"],
                    "source_path": transcribe.relative_path(original, self.root),
                    "destination_path": transcribe.relative_path(standard, self.root),
                    "warnings": [],
                }
            )
        self.manifest_path.write_text(
            json.dumps({"conversions": conversions}), encoding="utf-8"
        )

    def _batch(self, model: FakeModel | None = None):
        model = model or FakeModel()
        service = FakeService(model)
        result = transcribe.transcribe_batch(
            self.manifest_path,
            self.plan_path,
            self.root,
            self.pc_output,
            self.phone_output,
            self.batch_json,
            self.batch_csv,
            self.duration_json,
            service_factory=lambda: service,
            require_cuda_check=False,
        )
        return result, model, service

    def test_source_decoded_duration_calculation(self) -> None:
        source = next((self.root / "original").rglob("*.m4a"))
        result = transcribe.decoded_source_duration(source)
        self.assertGreater(result["source_decoded_sample_count"], 0)
        self.assertAlmostEqual(result["source_decoded_duration_sec"], 0.05, places=3)

    def test_wav_frame_duration_calculation(self) -> None:
        path = next((self.root / "standard").rglob("*.wav"))
        result = transcribe.wav_frame_duration(path)
        self.assertEqual(result["destination_wav_frame_count"], 800)
        self.assertEqual(result["destination_wav_duration_sec"], 0.05)

    def test_metadata_duration_discrepancy(self) -> None:
        with mock.patch.object(
            transcribe,
            "decoded_source_duration",
            return_value={
                "source_container_duration_sec": 1.6,
                "source_decoded_sample_count": 48000,
                "source_decoded_sample_rate": 48000,
                "source_decoded_duration_sec": 1.0,
            },
        ), mock.patch.object(
            transcribe,
            "wav_frame_duration",
            return_value={
                "destination_wav_frame_count": 16000,
                "destination_wav_sample_rate": 16000,
                "destination_wav_duration_sec": 1.0,
            },
        ):
            result = transcribe.validate_decoded_duration("x", "a", "b")
        self.assertEqual(result["validation_status"], "metadata_duration_discrepancy")

    def test_duration_difference_at_005_passes(self) -> None:
        with mock.patch.object(
            transcribe, "decoded_source_duration",
            return_value={"source_container_duration_sec": 1.0, "source_decoded_sample_count": 48000, "source_decoded_sample_rate": 48000, "source_decoded_duration_sec": 1.0},
        ), mock.patch.object(
            transcribe, "wav_frame_duration",
            return_value={"destination_wav_frame_count": 15200, "destination_wav_sample_rate": 16000, "destination_wav_duration_sec": 0.95},
        ):
            result = transcribe.validate_decoded_duration("x", "a", "b")
        self.assertTrue(result["stt_allowed"])

    def test_duration_005_to_020_warns(self) -> None:
        with mock.patch.object(
            transcribe, "decoded_source_duration",
            return_value={"source_container_duration_sec": 1.0, "source_decoded_sample_count": 48000, "source_decoded_sample_rate": 48000, "source_decoded_duration_sec": 1.0},
        ), mock.patch.object(
            transcribe, "wav_frame_duration",
            return_value={"destination_wav_frame_count": 14400, "destination_wav_sample_rate": 16000, "destination_wav_duration_sec": 0.9},
        ):
            result = transcribe.validate_decoded_duration("x", "a", "b")
        self.assertEqual(result["validation_status"], "duration_difference_warning")

    def test_duration_over_020_blocks(self) -> None:
        with mock.patch.object(
            transcribe, "decoded_source_duration",
            return_value={"source_container_duration_sec": 1.0, "source_decoded_sample_count": 48000, "source_decoded_sample_rate": 48000, "source_decoded_duration_sec": 1.0},
        ), mock.patch.object(
            transcribe, "wav_frame_duration",
            return_value={"destination_wav_frame_count": 11200, "destination_wav_sample_rate": 16000, "destination_wav_duration_sec": 0.7},
        ):
            result = transcribe.validate_decoded_duration("x", "a", "b")
        self.assertFalse(result["stt_allowed"])

    def test_model_loads_once(self) -> None:
        _, _, service = self._batch()
        self.assertEqual(service.initialization_count, 1)

    def test_batch_processes_24_files(self) -> None:
        result, model, _ = self._batch()
        self.assertEqual(result["summary"]["total_files"], 24)
        self.assertEqual(model.calls, 24)

    def test_pc_count_is_12(self) -> None:
        result, _, _ = self._batch()
        self.assertEqual(result["summary"]["pc_files"], 12)

    def test_phone_count_is_12(self) -> None:
        result, _, _ = self._batch()
        self.assertEqual(result["summary"]["phone_files"], 12)

    def test_clean_count_is_12(self) -> None:
        result, _, _ = self._batch()
        self.assertEqual(result["summary"]["clean_files"], 12)

    def test_natural_count_is_12(self) -> None:
        result, _, _ = self._batch()
        self.assertEqual(result["summary"]["natural_files"], 12)

    def test_sample_metadata_is_connected(self) -> None:
        self._batch()
        payload = json.loads(next(self.pc_output.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(payload["speaker_code"], "SPK001")
        self.assertIn(payload["script_id"], {"SCRIPT001", "SCRIPT002"})

    def test_condition_on_previous_text_is_false(self) -> None:
        _, model, _ = self._batch()
        self.assertFalse(model.last_kwargs["condition_on_previous_text"])

    def test_word_timestamp_order_is_valid(self) -> None:
        warnings = transcribe.validate_word_timestamps(
            [{"start": 0.0, "end": 0.1, "word": "안녕"}, {"start": 0.2, "end": 0.3, "word": "하세요"}],
            1.0,
        )
        self.assertEqual(warnings, [])

    def test_timestamp_duration_overage_warns(self) -> None:
        warnings = transcribe.validate_word_timestamps(
            [{"start": 0.0, "end": 2.0, "word": "안녕"}], 1.0
        )
        self.assertIn("WORD_TIMESTAMP_EXCEEDS_AUDIO_DURATION", warnings)

    def test_empty_transcription_is_counted(self) -> None:
        result, _, _ = self._batch(FakeModel(empty=True))
        self.assertEqual(result["summary"]["empty_transcription_count"], 24)

    def test_strict_json_and_csv_bom(self) -> None:
        self._batch()
        json.loads(
            self.batch_json.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
        self.assertTrue(self.batch_csv.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_atomic_outputs_leave_no_temp_files(self) -> None:
        self._batch()
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.rglob("*")))

    def test_standard_wav_and_original_hashes_are_preserved(self) -> None:
        inputs = list((self.root / "standard").rglob("*.wav")) + list(
            (self.root / "original").rglob("*.m4a")
        )
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        self._batch()
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        self.assertEqual(before, after)

    def test_conversion_manifest_is_preserved(self) -> None:
        before = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        self._batch()
        self.assertEqual(before, hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())

    def test_cli_exit_codes_zero_one_two(self) -> None:
        success_result = {"model": {}, "summary": {}, "error": None}
        with mock.patch.object(transcribe, "transcribe_batch", return_value=success_result), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            args = [
                "--conversion-manifest", "a", "--plan", "b", "--relative-root", "c",
                "--pc-output-dir", "d", "--phone-output-dir", "e",
                "--batch-json-output", "f", "--batch-csv-output", "g",
                "--duration-json-output", "h",
            ]
            success = transcribe.main(args)
            with mock.patch.object(
                transcribe,
                "transcribe_batch",
                side_effect=transcribe.SessionTranscriptionError("CUDA_RUNTIME_UNAVAILABLE", "x"),
            ):
                failure = transcribe.main(args)
            with self.assertRaises(SystemExit) as raised:
                transcribe.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
