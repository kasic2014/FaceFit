"""Tests for acoustic speech metrics without model or GPU dependencies."""

from __future__ import annotations

import json
import hashlib
import math
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.speech.speech_metrics import (
    analyze_speech_metrics,
    serialize_json,
    write_json_file,
)


class SpeechMetricsTests(unittest.TestCase):
    SAMPLE_RATE = 16000

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)

    def write_wav(self, parts: list[tuple[float, int]]) -> Path:
        samples = array("h")
        sample_index = 0
        for duration, amplitude in parts:
            count = round(duration * self.SAMPLE_RATE)
            for _ in range(count):
                value = amplitude * math.sin(2 * math.pi * 220 * sample_index / self.SAMPLE_RATE)
                samples.append(round(value))
                sample_index += 1
        path = self.directory / "sample.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self.SAMPLE_RATE)
            stream.writeframes(samples.tobytes())
        return path

    def write_stt(self, words: list[dict]) -> Path:
        payload = {"segments": [{"id": 1, "words": words}], "error": None}
        path = self.directory / "stt.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def analyze(self, parts: list[tuple[float, int]], words: list[dict]) -> dict:
        return analyze_speech_metrics(self.write_wav(parts), self.write_stt(words))

    def background_noise_result(self) -> dict:
        return self.analyze(
            [(0.6, 4000), (0.8, 9000), (0.8, 4000), (0.8, 9000), (0.6, 4000)],
            [
                {"start": 0.6, "end": 1.4, "word": " 이전", "probability": 0.99},
                {"start": 2.2, "end": 3.0, "word": " 다음", "probability": 0.99},
            ],
        )

    def short_vocalization_result(self) -> dict:
        return self.analyze(
            [(1.0, 9000), (0.3, 40), (0.2, 6000), (0.3, 40), (1.0, 9000)],
            [
                {"start": 0.0, "end": 1.0, "word": " 이전", "probability": 0.99},
                {"start": 1.8, "end": 2.8, "word": " 다음", "probability": 0.99},
            ],
        )

    def test_long_silence_requires_acoustic_low_energy(self) -> None:
        result = self.analyze(
            [(1.0, 9000), (3.5, 40), (1.0, 9000)],
            [
                {"start": 0.0, "end": 1.0, "word": " 이전", "probability": 0.99},
                {"start": 4.5, "end": 5.5, "word": " 다음", "probability": 0.99},
            ],
        )
        self.assertEqual(result["long_silence_count"], 1)
        self.assertGreaterEqual(result["longest_silence_sec"], 3.4)

    def test_voiced_timestamp_gap_is_not_silence(self) -> None:
        result = self.analyze(
            [(3.0, 9000)],
            [
                {"start": 0.0, "end": 0.8, "word": " 이전", "probability": 0.99},
                {"start": 2.0, "end": 2.8, "word": " 다음", "probability": 0.99},
            ],
        )
        self.assertEqual(result["long_silence_count"], 0)
        self.assertFalse(result["pauses"][0]["acoustic_silence_confirmed"])

    def test_two_second_low_energy_gap_is_noticeable_pause(self) -> None:
        result = self.analyze(
            [(1.0, 9000), (2.3, 40), (1.0, 9000)],
            [
                {"start": 0.0, "end": 1.0, "word": " 이전", "probability": 0.99},
                {"start": 3.3, "end": 4.3, "word": " 다음", "probability": 0.99},
            ],
        )
        self.assertEqual(result["pauses"][0]["classification"], "noticeable_pause")

    def test_voiced_gap_becomes_omitted_filler_candidate(self) -> None:
        result = self.analyze(
            [(3.0, 9000)],
            [
                {"start": 0.0, "end": 0.8, "word": " 이전", "probability": 0.99},
                {"start": 2.0, "end": 2.8, "word": " 다음", "probability": 0.99},
            ],
        )
        self.assertEqual(len(result["omitted_filler_candidates"]), 1)

    def test_audio_quality_contains_required_fields(self) -> None:
        quality = self.background_noise_result()["audio_quality"]
        required = {
            "estimated_noise_floor_dbfs", "speech_reference_dbfs", "snr_proxy_db",
            "dynamic_range_db", "clipping_frame_ratio", "non_word_voiced_time_sec",
            "non_word_voiced_ratio", "word_coverage_ratio", "reliability_flags",
            "reliability_warnings",
        }
        self.assertTrue(required.issubset(quality))
        self.assertIn("not a calibrated SNR", quality["snr_proxy_definition"])

    def test_constant_background_noise_has_high_non_word_voiced_ratio(self) -> None:
        quality = self.background_noise_result()["audio_quality"]
        self.assertGreaterEqual(quality["non_word_voiced_ratio"], 0.40)
        self.assertGreater(quality["non_word_voiced_time_sec"], 0.0)

    def test_background_noise_suspected_flag(self) -> None:
        quality = self.background_noise_result()["audio_quality"]
        self.assertTrue(quality["background_noise_suspected"])
        self.assertIn("background_noise_suspected", quality["reliability_flags"])

    def test_background_noise_gap_is_uncertain_not_probable(self) -> None:
        result = self.background_noise_result()
        self.assertEqual(result["probable_omitted_vocalizations"], [])
        self.assertEqual(len(result["uncertain_gap_vocalizations"]), 1)
        self.assertIn(
            "background_noise_suspected",
            result["uncertain_gap_vocalizations"][0]["reasons"],
        )

    def test_clear_short_vocalization_is_probable(self) -> None:
        result = self.short_vocalization_result()
        self.assertEqual(len(result["probable_omitted_vocalizations"]), 1)
        self.assertEqual(result["uncertain_gap_vocalizations"], [])

    def test_local_energy_contrast_is_recorded(self) -> None:
        candidate = self.short_vocalization_result()["probable_omitted_vocalizations"][0]
        contrast = candidate["local_energy_contrast"]
        required = {
            "candidate_mean_dbfs", "before_300ms_mean_dbfs", "after_300ms_mean_dbfs",
            "estimated_noise_floor_dbfs", "above_noise_floor_db",
            "surrounding_energy_contrast_db",
        }
        self.assertTrue(required.issubset(contrast))
        self.assertGreaterEqual(
            contrast["surrounding_energy_contrast_db"], 3.0
        )

    def test_probable_candidate_uses_localized_voiced_run(self) -> None:
        candidate = self.short_vocalization_result()["probable_omitted_vocalizations"][0]
        contrast = candidate["local_energy_contrast"]
        self.assertAlmostEqual(contrast["candidate_start_sec"], 1.3, delta=0.04)
        self.assertAlmostEqual(contrast["candidate_end_sec"], 1.5, delta=0.04)

    def test_eojeol_per_minute_aliases_match_existing_fields(self) -> None:
        result = self.short_vocalization_result()
        self.assertEqual(result["eojeol_per_minute_total"], result["words_per_minute_total"])
        self.assertEqual(result["eojeol_per_minute_voiced"], result["words_per_minute_voiced"])

    def test_combined_omitted_candidate_field_remains_compatible(self) -> None:
        result = self.short_vocalization_result()
        self.assertEqual(
            result["omitted_filler_candidates"],
            result["probable_omitted_vocalizations"] + result["uncertain_gap_vocalizations"],
        )
        self.assertEqual(
            result["omitted_filler_candidate_count"],
            len(result["omitted_filler_candidates"]),
        )

    def hallucination_result(self) -> dict:
        return self.analyze(
            [(2.7, 9000), (0.3, 20)],
            [
                {"start": 0.0, "end": 2.5, "word": " 정상발화", "probability": 0.99},
                {"start": 2.9, "end": 2.98, "word": " 감사합니다.", "probability": 0.60},
            ],
        )

    def test_hallucination_candidate_uses_compound_evidence(self) -> None:
        candidate = self.hallucination_result()["hallucination_candidates"][0]
        self.assertEqual(candidate["word"], "감사합니다.")
        self.assertGreaterEqual(candidate["matched_condition_count"], 3)
        self.assertIn("low_acoustic_support", candidate["matched_conditions"])
        self.assertTrue(candidate["auxiliary_evidence"]["unrealistic_syllable_rate"])

    def test_hallucination_candidate_is_excluded_from_effective_count(self) -> None:
        result = self.hallucination_result()
        self.assertEqual(result["raw_word_count"], 2)
        self.assertEqual(result["effective_word_count"], 1)
        self.assertEqual(result["excluded_word_count"], 1)
        self.assertEqual(result["excluded_from_metrics"][0]["word"], "감사합니다.")
        self.assertTrue(result["exclusion_reasons"][0]["reasons"])

    def test_low_probability_alone_is_not_hallucination(self) -> None:
        result = self.analyze(
            [(3.0, 9000)],
            [{"start": 0.2, "end": 1.0, "word": " 정상", "probability": 0.40}],
        )
        self.assertEqual(result["hallucination_candidates"], [])

    def test_pause_contains_rms_dbfs_and_voiced_ratio(self) -> None:
        result = self.analyze(
            [(1.0, 9000), (2.3, 40), (1.0, 9000)],
            [
                {"start": 0.0, "end": 1.0, "word": " 이전", "probability": 0.99},
                {"start": 3.3, "end": 4.3, "word": " 다음", "probability": 0.99},
            ],
        )
        acoustic = result["pauses"][0]["acoustic"]
        self.assertIn("rms", acoustic)
        self.assertIn("dbfs", acoustic)
        self.assertIn("voiced_frame_ratio", acoustic)

    def test_analysis_preserves_source_sha256(self) -> None:
        audio = self.write_wav([(2.0, 9000)])
        stt = self.write_stt(
            [{"start": 0.0, "end": 1.0, "word": " 원본", "probability": 0.99}]
        )
        audio_before = hashlib.sha256(audio.read_bytes()).hexdigest()
        stt_before = hashlib.sha256(stt.read_bytes()).hexdigest()
        analyze_speech_metrics(audio, stt)
        self.assertEqual(hashlib.sha256(audio.read_bytes()).hexdigest(), audio_before)
        self.assertEqual(hashlib.sha256(stt.read_bytes()).hexdigest(), stt_before)

    def test_korean_pause_words_survive_json_write(self) -> None:
        payload = {"pauses": [{"previous_word": "분석했습니다.", "next_word": "그 결과"}]}
        output = self.directory / "korean.json"
        write_json_file(output, payload)
        decoded = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(decoded["pauses"][0]["previous_word"], "분석했습니다.")
        self.assertEqual(decoded["pauses"][0]["next_word"], "그 결과")

    def test_written_json_can_be_loaded_again(self) -> None:
        payload = {"value": [1, True, None, "한국어"]}
        output = self.directory / "roundtrip.json"
        write_json_file(output, payload)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)

    def test_quote_in_user_string_is_escaped(self) -> None:
        payload = {"word": '그는 "분석"이라고 말했다.'}
        output = self.directory / "quote.json"
        write_json_file(output, payload)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)

    def test_backslash_in_user_string_is_escaped(self) -> None:
        payload = {"word": "C:\\temp\\음성"}
        output = self.directory / "backslash.json"
        write_json_file(output, payload)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)

    def test_newline_in_user_string_is_escaped(self) -> None:
        payload = {"word": "첫 줄\n둘째 줄"}
        output = self.directory / "newline.json"
        write_json_file(output, payload)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)

    def test_ensure_ascii_false_preserves_korean_text(self) -> None:
        payload = {"word": "한국어"}
        output = self.directory / "utf8.json"
        write_json_file(output, payload)
        text = output.read_text(encoding="utf-8")
        self.assertIn("한국어", text)
        self.assertNotIn("\\ud55c", text.lower())
        self.assertIn("한국어", serialize_json(payload))

    def test_nan_and_infinity_are_rejected_before_file_creation(self) -> None:
        for index, value in enumerate((float("nan"), float("inf"), float("-inf"))):
            with self.subTest(value=value):
                output = self.directory / f"invalid-{index}.json"
                with self.assertRaises(ValueError):
                    write_json_file(output, {"value": value})
                self.assertFalse(output.exists())

    def test_result_contains_required_summary_schema(self) -> None:
        result = self.analyze(
            [(2.0, 9000)],
            [{"start": 0.0, "end": 1.0, "word": " 정상", "probability": 0.95}],
        )
        required = {
            "raw_word_count", "effective_word_count", "excluded_word_count",
            "acoustic_voiced_time_sec", "silence_time_sec", "speech_ratio",
            "words_per_minute_total", "words_per_minute_voiced",
            "average_word_probability", "low_confidence_words", "pause_count",
            "noticeable_pause_count", "long_silence_count", "longest_silence_sec",
            "omitted_filler_candidates", "hallucination_candidates", "warnings", "error",
        }
        self.assertTrue(required.issubset(result))

    def test_pause_counts_match_pause_array(self) -> None:
        result = self.analyze(
            [(1.0, 9000), (2.3, 40), (1.0, 9000)],
            [
                {"start": 0.0, "end": 1.0, "word": " 이전", "probability": 0.99},
                {"start": 3.3, "end": 4.3, "word": " 다음", "probability": 0.99},
            ],
        )
        self.assertEqual(result["pause_count"], len(result["pauses"]))
        self.assertEqual(
            result["noticeable_pause_count"],
            sum(pause["classification"] == "noticeable_pause" for pause in result["pauses"]),
        )
        self.assertEqual(
            result["omitted_filler_candidate_count"],
            len(result["omitted_filler_candidates"]),
        )

    def test_invalid_wav_contract_is_rejected(self) -> None:
        path = self.directory / "invalid.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(self.SAMPLE_RATE)
            stream.writeframes(array("h", [0, 0] * self.SAMPLE_RATE).tobytes())
        stt = self.write_stt([])
        with self.assertRaisesRegex(ValueError, "INPUT_AUDIO_INVALID"):
            analyze_speech_metrics(path, stt)


if __name__ == "__main__":
    unittest.main()
