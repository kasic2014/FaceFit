"""Tests for standard-library-only speech review clip export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
import wave
from array import array
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import export_speech_review_clips as review_export  # noqa: E402


class ExportSpeechReviewClipsTests(unittest.TestCase):
    SAMPLE_RATE = 16000

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.wav_path = self.write_wav()
        self.metrics_path = self.directory / "metrics.json"
        self.output_dir = self.directory / "clips"

    def write_wav(
        self,
        *,
        duration_sec: float = 2.0,
        sample_rate: int = SAMPLE_RATE,
        channels: int = 1,
    ) -> Path:
        path = self.directory / "source.wav"
        frame_count = round(duration_sec * sample_rate)
        samples = array("h", [1200] * frame_count * channels)
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(channels)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(samples.tobytes())
        return path

    def write_metrics(self, **arrays: object) -> Path:
        payload = {
            "error": None,
            "audio_quality": {"reliability_flags": ["background_noise_suspected"]},
            **arrays,
        }
        self.metrics_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        return self.metrics_path

    @staticmethod
    def gap_event(start: object = 0.5, end: object = 1.0, **extra: object) -> dict:
        return {
            "stt_gap_start_sec": start,
            "stt_gap_end_sec": end,
            "classification": "word_gap",
            "previous_word": "이전",
            "next_word": "다음",
            "acoustic": {"dbfs": -28.5, "voiced_frame_ratio": 0.25},
            **extra,
        }

    def export(self, **arrays: object) -> dict:
        self.write_metrics(**arrays)
        return review_export.export_review_clips(
            self.wav_path, self.metrics_path, self.output_dir
        )

    def test_normal_wav_clip_extraction(self) -> None:
        result = self.export(pauses=[self.gap_event()])
        self.assertTrue(result["success"])
        self.assertEqual(result["clip_count"], 1)
        clip_path = self.output_dir / result["items"][0]["clip_file"]
        with wave.open(str(clip_path), "rb") as stream:
            self.assertEqual(stream.getnchannels(), 1)
            self.assertEqual(stream.getsampwidth(), 2)
            self.assertEqual(stream.getframerate(), self.SAMPLE_RATE)
            self.assertEqual(stream.getnframes(), round(1.1 * self.SAMPLE_RATE))

    def test_padding_is_clamped_at_audio_start(self) -> None:
        result = self.export(pauses=[self.gap_event(0.1, 0.3)])
        self.assertEqual(result["items"][0]["clip_start_sec"], 0.0)

    def test_padding_is_clamped_at_audio_end(self) -> None:
        result = self.export(pauses=[self.gap_event(1.7, 1.95)])
        self.assertEqual(result["items"][0]["clip_end_sec"], 2.0)

    def test_probable_candidate_is_exported(self) -> None:
        result = self.export(probable_omitted_vocalizations=[self.gap_event()])
        self.assertEqual(result["event_counts"]["probable_omitted_vocalization"], 1)

    def test_uncertain_candidate_is_exported(self) -> None:
        result = self.export(uncertain_gap_vocalizations=[self.gap_event()])
        self.assertEqual(result["event_counts"]["uncertain_gap_vocalization"], 1)

    def test_hallucination_candidate_is_exported(self) -> None:
        event = {"start_sec": 1.5, "end_sec": 1.6, "word": "감사합니다.", "probability": 0.6}
        result = self.export(hallucination_candidates=[event])
        self.assertEqual(result["event_counts"]["hallucination_candidate"], 1)
        self.assertEqual(result["items"][0]["confidence_or_probability"], 0.6)

    def test_pause_is_exported(self) -> None:
        result = self.export(pauses=[self.gap_event()])
        self.assertEqual(result["event_counts"]["pause"], 1)

    def test_long_silence_is_exported(self) -> None:
        result = self.export(long_silences=[self.gap_event(0.2, 1.8, classification="long_silence")])
        self.assertEqual(result["event_counts"]["long_silence"], 1)

    def test_duplicate_cross_type_events_are_merged(self) -> None:
        event = self.gap_event()
        result = self.export(probable_omitted_vocalizations=[event], pauses=[event])
        self.assertEqual(result["clip_count"], 1)
        self.assertEqual(result["merged_event_count"], 1)
        self.assertTrue(result["items"][0]["merged"])
        self.assertEqual(
            result["items"][0]["source_event_types"],
            "probable_omitted_vocalization; pause",
        )

    def test_different_events_are_not_merged(self) -> None:
        result = self.export(
            probable_omitted_vocalizations=[self.gap_event(0.2, 0.5)],
            pauses=[self.gap_event(1.2, 1.5)],
        )
        self.assertEqual(result["clip_count"], 2)
        self.assertEqual(result["merged_event_count"], 0)

    def test_long_silence_and_hallucination_are_never_auto_merged(self) -> None:
        result = self.export(
            long_silences=[self.gap_event(0.5, 1.0)],
            hallucination_candidates=[{"start_sec": 0.5, "end_sec": 1.0}],
        )
        self.assertEqual(result["clip_count"], 2)

    def test_invalid_timestamp_is_skipped_with_warning(self) -> None:
        result = self.export(pauses=[self.gap_event("invalid", 1.0), self.gap_event(0.4, 0.8)])
        self.assertTrue(result["success"])
        self.assertEqual(result["clip_count"], 1)
        self.assertEqual(result["warnings"][0]["code"], "EVENT_TIMESTAMP_INVALID")

    def test_csv_manifest_has_utf8_bom(self) -> None:
        result = self.export(pauses=[self.gap_event()])
        manifest = self.directory / "manifest.csv"
        review_export.write_csv_manifest(manifest, result["items"])
        self.assertTrue(manifest.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_korean_words_are_preserved_in_csv(self) -> None:
        result = self.export(pauses=[self.gap_event(previous_word="안녕하세요.", next_word="다음입니다.")])
        manifest = self.directory / "manifest.csv"
        review_export.write_csv_manifest(manifest, result["items"])
        with manifest.open("r", encoding="utf-8-sig", newline="") as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row["previous_word"], "안녕하세요.")
        self.assertEqual(row["next_word"], "다음입니다.")

    def test_json_manifest_can_be_reloaded(self) -> None:
        result = self.export(pauses=[self.gap_event()])
        manifest = self.directory / "manifest.json"
        review_export.write_json_manifest(manifest, result["items"], result["warnings"])
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["items"]), 1)
        self.assertIn("filler", payload["reviewer_label_values"])

    def test_source_wav_sha256_is_preserved(self) -> None:
        before = hashlib.sha256(self.wav_path.read_bytes()).hexdigest()
        self.export(pauses=[self.gap_event()])
        after = hashlib.sha256(self.wav_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_source_metrics_sha256_is_preserved(self) -> None:
        self.write_metrics(pauses=[self.gap_event()])
        before = hashlib.sha256(self.metrics_path.read_bytes()).hexdigest()
        review_export.export_review_clips(self.wav_path, self.metrics_path, self.output_dir)
        after = hashlib.sha256(self.metrics_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_output_filenames_do_not_collide(self) -> None:
        event = self.gap_event()
        result = self.export(pauses=[event, event])
        filenames = [item["clip_file"] for item in result["items"]]
        self.assertEqual(len(filenames), 2)
        self.assertEqual(len(set(filenames)), 2)
        self.assertTrue(filenames[0].startswith("001_"))
        self.assertTrue(filenames[1].startswith("002_"))

    def test_cli_success_and_failure_exit_codes(self) -> None:
        self.write_metrics(pauses=[self.gap_event()])
        manifest = self.directory / "manifest.csv"
        with redirect_stdout(io.StringIO()):
            success_code = review_export.main(
                [
                    str(self.wav_path),
                    str(self.metrics_path),
                    "--output-dir",
                    str(self.output_dir),
                    "--manifest",
                    str(manifest),
                ]
            )
            failure_code = review_export.main(
                [
                    str(self.directory / "missing.wav"),
                    str(self.metrics_path),
                    "--output-dir",
                    str(self.output_dir),
                    "--manifest",
                    str(manifest),
                ]
            )
        self.assertEqual(success_code, 0)
        self.assertEqual(failure_code, 1)

    def test_cli_usage_error_is_exit_code_two(self) -> None:
        with self.assertRaises(SystemExit) as raised, redirect_stdout(io.StringIO()):
            review_export.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_unsupported_wav_format_is_classified(self) -> None:
        self.wav_path = self.write_wav(sample_rate=8000)
        result = self.export(pauses=[self.gap_event()])
        self.assertFalse(result["success"])
        self.assertEqual(result["errors"][0]["code"], "UNSUPPORTED_WAV_FORMAT")


if __name__ == "__main__":
    unittest.main()
