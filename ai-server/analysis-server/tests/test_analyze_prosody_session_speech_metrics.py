"""Tests for SESSION001 batch reuse of existing speech metrics."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import analyze_prosody_session_speech_metrics as session  # noqa: E402


def _stt(number: int, device: str, condition: str) -> dict:
    script = "SCRIPT001" if number <= 12 else "SCRIPT002"
    repetition = ((number - 1) % 3) + 1
    words = [
        {"start": 0.0, "end": 1.0, "word": "안녕", "probability": 0.9},
        {"start": 2.0, "end": 3.0, "word": "하세요", "probability": 0.9},
    ]
    return {
        "sample_id": f"SAMPLE{number:03d}",
        "speaker_code": "SPK001",
        "session_id": "SESSION001",
        "script_id": script,
        "recording_condition": condition,
        "repetition_index": repetition,
        "device_code": device,
        "capture_pair_key": f"PAIR{(number + 1) // 2:02d}",
        "transcription_text_raw": "안녕 하세요",
        "word_count": 2,
        "eojeol_count": 2,
        "words": words,
        "segments": [{"id": 1, "words": words}],
        "error": None,
    }


def _raw() -> dict:
    pause = {
        "previous_word": "안녕",
        "next_word": "하세요",
        "stt_gap_start_sec": 1.0,
        "stt_gap_end_sec": 2.0,
        "stt_gap_duration_sec": 1.0,
        "classification": "long_silence",
        "acoustic_silence_confirmed": True,
        "acoustic_silence_start_sec": 1.0,
        "acoustic_silence_end_sec": 2.0,
        "acoustic_silence_duration_sec": 1.0,
        "acoustic": {},
    }
    return {
        "audio_duration_sec": 4.0,
        "acoustic_voiced_time_sec": 2.0,
        "speech_ratio": 0.5,
        "words_per_minute_total": 30.0,
        "words_per_minute_voiced": 60.0,
        "audio_quality": {
            "clipping_frame_ratio": 0.0,
            "estimated_noise_floor_dbfs": -50.0,
            "background_noise_suspected": False,
            "reliability_warnings": [],
            "reliability_flags": [],
        },
        "pauses": [pause],
        "pause_count": 1,
        "long_silences": [pause],
        "long_silence_count": 1,
        "probable_omitted_vocalization_count": 1,
        "probable_omitted_vocalizations": [{**pause}],
        "uncertain_gap_vocalization_count": 1,
        "uncertain_gap_vocalizations": [{**pause}],
        "hallucination_candidates": [],
        "warnings": [],
    }


class AnalyzeProsodySessionSpeechMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pc_stt = self.root / "stt/pc"
        self.phone_stt = self.root / "stt/phone"
        self.pc_out = self.root / "metrics/pc"
        self.phone_out = self.root / "metrics/phone"
        self.manifest_json = self.root / "manifest.json"
        self.manifest_csv = self.root / "manifest.csv"
        conversions = []
        for pair in range(1, 13):
            condition = "clean" if pair % 2 else "natural"
            for offset, device in enumerate(("DEV_PC_MIC_01", "DEV_PHONE_01")):
                number = (pair - 1) * 2 + offset + 1
                group = "pc" if offset == 0 else "phone"
                audio = self.root / f"standard/{group}/SAMPLE{number:03d}.wav"
                audio.parent.mkdir(parents=True, exist_ok=True)
                audio.write_bytes(f"audio{number}".encode())
                stt_dir = self.pc_stt if offset == 0 else self.phone_stt
                stt_dir.mkdir(parents=True, exist_ok=True)
                (stt_dir / f"SAMPLE{number:03d}.json").write_text(
                    json.dumps(_stt(number, device, condition), ensure_ascii=False),
                    encoding="utf-8",
                )
                conversions.append(
                    {
                        "sample_id": f"SAMPLE{number:03d}",
                        "device_code": device,
                        "destination_path": audio.relative_to(self.root).as_posix(),
                    }
                )
        self.conversion = self.root / "conversion.json"
        self.conversion.write_text(
            json.dumps({"conversions": conversions}), encoding="utf-8"
        )

    def _run(self):
        return session.analyze_session(
            self.conversion,
            self.pc_stt,
            self.phone_stt,
            self.pc_out,
            self.phone_out,
            self.manifest_json,
            self.manifest_csv,
            self.root,
            analyzer=lambda _audio, _stt_path: _raw(),
        )

    def test_standard_wav_and_stt_count_24(self) -> None:
        result = self._run()
        self.assertEqual(result["summary"]["total_files"], 24)
        self.assertEqual(result["summary"]["successful_files"], 24)

    def test_pc_phone_counts(self) -> None:
        result = self._run()
        self.assertEqual((result["summary"]["pc_files"], result["summary"]["phone_files"]), (12, 12))

    def test_clean_natural_counts(self) -> None:
        result = self._run()
        self.assertEqual((result["summary"]["clean_files"], result["summary"]["natural_files"]), (12, 12))

    def test_file_metrics_are_generated(self) -> None:
        self._run()
        self.assertEqual(len(list(self.pc_out.glob("*.json"))), 12)
        self.assertEqual(len(list(self.phone_out.glob("*.json"))), 12)

    def test_audio_duration_rate(self) -> None:
        audio = self.root / "a"; audio.write_bytes(b"x")
        result = session.build_file_result(_stt(1, "DEV_PC_MIC_01", "clean"), audio, self.root / "s", _raw(), self.root)
        self.assertEqual(result["speech_rate_word_per_min_audio_duration"], 30)

    def test_speech_duration_rate(self) -> None:
        audio = self.root / "a"; audio.write_bytes(b"x")
        result = session.build_file_result(_stt(1, "DEV_PC_MIC_01", "clean"), audio, self.root / "s", _raw(), self.root)
        self.assertEqual(result["speech_rate_word_per_min_speech_duration"], 60)

    def test_word_gap_pause_and_long_pause(self) -> None:
        audio = self.root / "a"; audio.write_bytes(b"x")
        result = session.build_file_result(_stt(1, "DEV_PC_MIC_01", "clean"), audio, self.root / "s", _raw(), self.root)
        self.assertEqual(result["pause_count"], 1)
        self.assertEqual(result["long_pause_count"], 1)
        self.assertIn("inter_word_gap", result["pause_events"][0]["event_types"])

    def test_probable_and_uncertain_candidates(self) -> None:
        audio = self.root / "a"; audio.write_bytes(b"x")
        result = session.build_file_result(_stt(1, "DEV_PC_MIC_01", "clean"), audio, self.root / "s", _raw(), self.root)
        self.assertEqual(result["probable_omitted_vocalization_count"], 1)
        self.assertEqual(result["uncertain_gap_vocalization_count"], 1)

    def test_strict_json_csv_bom_atomic(self) -> None:
        self._run()
        json.loads(self.manifest_json.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        self.assertTrue(self.manifest_csv.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.rglob("*")))

    def test_input_hashes_preserved(self) -> None:
        inputs = list((self.root / "standard").rglob("*.wav")) + list((self.root / "stt").rglob("*.json"))
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        self._run()
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs})

    def test_no_whisper_model_symbol(self) -> None:
        source = (ROOT / "scripts/analyze_prosody_session_speech_metrics.py").read_text(encoding="utf-8")
        self.assertNotIn("WhisperModel", source)
        self.assertNotIn("WhisperService", source)

    def test_missing_stt_is_failure(self) -> None:
        next(self.pc_stt.glob("*.json")).unlink()
        result = self._run()
        self.assertEqual(result["summary"]["failed_files"], 1)

    def test_cli_exit_codes_zero_one_two(self) -> None:
        args = ["--conversion-manifest", "a", "--stt-pc-dir", "b", "--stt-phone-dir", "c", "--output-pc-dir", "d", "--output-phone-dir", "e", "--manifest-json-output", "f", "--manifest-csv-output", "g", "--relative-root", "h"]
        with mock.patch.object(session, "analyze_session", return_value={"summary": {}, "error": None}), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = session.main(args)
            with mock.patch.object(session, "analyze_session", side_effect=session.SessionMetricsError("SESSION_SPEECH_METRICS_FAILED", "x")):
                failure = session.main(args)
            with self.assertRaises(SystemExit) as raised:
                session.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
