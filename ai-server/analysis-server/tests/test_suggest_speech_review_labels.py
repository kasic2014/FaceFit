"""Tests for conservative speech-review label suggestions."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import suggest_speech_review_labels as suggest  # noqa: E402


class SuggestSpeechReviewLabelsTests(unittest.TestCase):
    FIELDS = [
        "review_id",
        "source_audio",
        "source_metrics",
        "clip_file",
        "event_type",
        "original_start_sec",
        "original_end_sec",
        "clip_start_sec",
        "mean_dbfs",
        "voiced_frame_ratio",
        "local_energy_contrast_db",
        "candidate_reasons",
        "audio_quality_flags",
        "previous_word",
        "next_word",
        "reviewer_label",
        "reviewer_note",
    ]

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.manifest = self.directory / "reviewed.csv"
        self.json_output = self.directory / "suggestions.json"
        self.csv_output = self.directory / "suggestions.csv"

    def write_wav(
        self, name: str, samples: np.ndarray, sample_rate: int = 16000
    ) -> Path:
        path = self.directory / name
        pcm = np.clip(samples, -1.0, 0.999969) * 32768.0
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(pcm.astype("<i2").tobytes())
        return path

    def row(
        self,
        clip: Path,
        *,
        review_id: str = "r1",
        event_type: str = "probable_omitted_vocalization",
        label: str = "keep-label",
        note: str = "기존 메모",
    ) -> dict[str, str]:
        values = {field: "" for field in self.FIELDS}
        values.update(
            {
                "review_id": review_id,
                "clip_file": clip.name,
                "event_type": event_type,
                "reviewer_label": label,
                "reviewer_note": note,
            }
        )
        return values

    def write_manifest(self, rows: list[dict[str, str]]) -> None:
        with self.manifest.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def empty_stt(_: Path) -> dict:
        return {
            "transcript": "",
            "detected_words": [],
            "average_probability": None,
            "no_speech_probability": 0.95,
            "error": None,
        }

    @staticmethod
    def meaningful_stt(_: Path) -> dict:
        return {
            "transcript": "안녕하세요",
            "detected_words": [
                {
                    "word": "안녕하세요",
                    "start": 0.05,
                    "end": 0.55,
                    "probability": 0.94,
                }
            ],
            "average_probability": 0.94,
            "no_speech_probability": 0.02,
            "error": None,
        }

    def analyze_one(self, row: dict[str, str], stt=None) -> dict:
        self.write_manifest([row])
        result = suggest.suggest_manifest(
            self.manifest, stt_runner=stt or self.empty_stt
        )
        self.assertIsNone(result["error"])
        return result["items"][0]

    def test_complete_silence_is_silence(self) -> None:
        clip = self.write_wav("silence.wav", np.zeros(16000))
        item = self.analyze_one(
            self.row(clip, event_type="pause", label=""), self.empty_stt
        )
        self.assertEqual(item["suggested_label"], "silence")
        self.assertGreaterEqual(item["suggested_confidence"], 0.8)

    def test_steady_white_noise_is_noise(self) -> None:
        rng = np.random.default_rng(7)
        clip = self.write_wav("noise.wav", rng.normal(0.0, 0.08, 16000))
        item = self.analyze_one(self.row(clip, label=""), self.empty_stt)
        self.assertEqual(item["suggested_label"], "noise")

    def test_short_periodic_tone_is_not_forced_to_filler(self) -> None:
        sample_rate = 16000
        time = np.arange(round(0.5 * sample_rate)) / sample_rate
        clip = self.write_wav("tone.wav", 0.12 * np.sin(2 * math.pi * 180 * time))
        item = self.analyze_one(self.row(clip, label=""), self.empty_stt)
        self.assertIn(item["suggested_label"], {"unknown", "filler"})
        if item["suggested_label"] == "filler":
            self.assertLessEqual(item["suggested_confidence"], 0.75)

    def test_short_broadband_noise_is_breath_or_unknown(self) -> None:
        rng = np.random.default_rng(11)
        clip = self.write_wav("burst.wav", rng.normal(0.0, 0.06, 4800))
        item = self.analyze_one(self.row(clip, label=""), self.empty_stt)
        self.assertIn(item["suggested_label"], {"breath", "unknown"})

    def test_meaningful_isolated_stt_is_normal_speech(self) -> None:
        sample_rate = 16000
        time = np.arange(sample_rate) / sample_rate
        clip = self.write_wav(
            "speech_like.wav", 0.1 * np.sin(2 * math.pi * 170 * time)
        )
        item = self.analyze_one(self.row(clip, label=""), self.meaningful_stt)
        self.assertEqual(item["suggested_label"], "normal_speech")
        self.assertEqual(
            item["isolated_stt"]["detected_words"][0]["word"], "안녕하세요"
        )

    def test_adjacent_manifest_word_is_not_normal_speech_evidence(self) -> None:
        sample_rate = 16000
        time = np.arange(sample_rate) / sample_rate
        clip = self.write_wav(
            "boundary.wav", 0.1 * np.sin(2 * math.pi * 170 * time)
        )
        row = self.row(clip, label="")
        row["next_word"] = "안녕하세요."
        item = self.analyze_one(row, self.meaningful_stt)
        self.assertEqual(item["suggested_label"], "unknown")
        self.assertTrue(
            any("padding leakage" in reason for reason in item["suggested_reasons"])
        )

    def test_low_energy_pause_is_not_normal_speech_from_stt_alone(self) -> None:
        rng = np.random.default_rng(31)
        clip = self.write_wav("low_pause.wav", rng.normal(0.0, 0.002, 16000))
        row = self.row(clip, event_type="pause", label="")
        row["voiced_frame_ratio"] = "0.05"
        item = self.analyze_one(row, self.meaningful_stt)
        self.assertNotEqual(item["suggested_label"], "normal_speech")

    def test_low_confidence_changes_label_to_unknown(self) -> None:
        label, confidence, reasons = suggest.apply_confidence_policy(
            "filler", 0.54, ["weak"]
        )
        self.assertEqual(label, "unknown")
        self.assertEqual(confidence, 0.54)
        self.assertTrue(any("0.55" in reason for reason in reasons))

    def test_filler_and_breath_confidence_caps(self) -> None:
        for label in ("filler", "breath"):
            output, confidence, _ = suggest.apply_confidence_policy(
                label, 0.99, ["strong candidate"]
            )
            self.assertEqual(output, label)
            self.assertEqual(confidence, 0.75)

    def test_existing_reviewer_fields_are_not_modified(self) -> None:
        clip = self.write_wav("silence.wav", np.zeros(8000))
        self.write_manifest([self.row(clip)])
        before = self.manifest.read_bytes()
        suggest.suggest_manifest(self.manifest, stt_runner=self.empty_stt)
        self.assertEqual(self.manifest.read_bytes(), before)
        with self.manifest.open("r", encoding="utf-8-sig", newline="") as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row["reviewer_label"], "keep-label")
        self.assertEqual(row["reviewer_note"], "기존 메모")

    def test_json_and_csv_are_utf8_and_keep_korean(self) -> None:
        clip = self.write_wav("speech.wav", np.zeros(8000))
        self.write_manifest([self.row(clip)])
        result = suggest.suggest_manifest(
            self.manifest, stt_runner=self.meaningful_stt
        )
        suggest.write_json(self.json_output, result)
        suggest.write_csv(self.csv_output, result["items"])
        json_text = self.json_output.read_text(encoding="utf-8")
        csv_text = self.csv_output.read_text(encoding="utf-8-sig")
        self.assertIn("안녕하세요", json_text)
        self.assertIn("안녕하세요", csv_text)
        json.loads(json_text)
        with self.csv_output.open("r", encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_manifest_and_wav_sha256_are_preserved(self) -> None:
        clip = self.write_wav("preserved.wav", np.zeros(8000))
        self.write_manifest([self.row(clip)])
        before = {
            self.manifest: hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            clip: hashlib.sha256(clip.read_bytes()).hexdigest(),
        }
        result = suggest.suggest_manifest(
            self.manifest, stt_runner=self.empty_stt
        )
        suggest.write_json(self.json_output, result)
        suggest.write_csv(self.csv_output, result["items"])
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before
        }
        self.assertEqual(after, before)

    def test_missing_one_clip_is_warning(self) -> None:
        present = self.write_wav("present.wav", np.zeros(8000))
        missing = self.directory / "missing.wav"
        self.write_manifest(
            [
                self.row(present, review_id="present", label=""),
                self.row(missing, review_id="missing", label=""),
            ]
        )
        result = suggest.suggest_manifest(
            self.manifest, stt_runner=self.empty_stt
        )
        self.assertIsNone(result["error"])
        missing_item = result["items"][1]
        self.assertEqual(missing_item["suggested_label"], "unknown")
        self.assertEqual(missing_item["error"]["code"], "CLIP_FILE_NOT_FOUND")
        self.assertTrue(
            any(warning["code"] == "CLIP_FILE_NOT_FOUND" for warning in result["warnings"])
        )

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        clip = self.write_wav("clip.wav", np.zeros(8000))
        self.write_manifest([self.row(clip, label="")])
        args = [
            str(self.manifest),
            "--json-output",
            str(self.json_output),
            "--csv-output",
            str(self.csv_output),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = suggest.main(args, stt_runner=self.empty_stt)
            failure = suggest.main(
                [str(self.directory / "missing.csv")],
                stt_runner=self.empty_stt,
            )
            with self.assertRaises(SystemExit) as raised:
                suggest.main(["--not-a-real-option"], stt_runner=self.empty_stt)
        self.assertEqual(success, 0)
        self.assertEqual(failure, 1)
        self.assertEqual(raised.exception.code, 2)

    def test_stt_configuration_disables_vad_and_previous_text(self) -> None:
        self.assertEqual(
            suggest.STT_CONFIGURATION,
            {
                "model": "turbo",
                "language": "ko",
                "task": "transcribe",
                "word_timestamps": True,
                "vad_filter": False,
                "condition_on_previous_text": False,
            },
        )

    def test_all_required_output_fields_are_present(self) -> None:
        clip = self.write_wav("clip.wav", np.zeros(8000))
        item = self.analyze_one(self.row(clip, label=""), self.empty_stt)
        self.assertEqual(set(item), set(suggest.OUTPUT_FIELDS))
        for feature in (
            "duration_sec",
            "rms",
            "dbfs",
            "peak_dbfs",
            "zero_crossing_rate",
            "spectral_centroid_hz",
            "spectral_flatness",
            "dominant_frequency_hz",
            "periodicity_proxy",
            "voiced_frame_ratio",
            "low_energy_frame_ratio",
            "local_energy_contrast_db",
        ):
            self.assertIn(feature, item["acoustic_features"])


if __name__ == "__main__":
    unittest.main()
