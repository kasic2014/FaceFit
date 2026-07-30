"""Tests for experimental numpy-only speech prosody metrics."""

from __future__ import annotations

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from app.speech import prosody_metrics as prosody  # noqa: E402
import analyze_speech_prosody as cli  # noqa: E402


class ProsodyMetricsTests(unittest.TestCase):
    SAMPLE_RATE = 16000

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.wav = self.directory / "audio.wav"
        self.stt = self.directory / "stt.json"
        self.metrics = self.directory / "metrics.json"
        self.output = self.directory / "prosody.json"

    def write_wav(
        self,
        samples: np.ndarray,
        *,
        sample_rate: int = SAMPLE_RATE,
    ) -> Path:
        pcm = np.rint(np.clip(samples, -1.0, 32767 / 32768) * 32768).astype("<i2")
        with wave.open(str(self.wav), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(pcm.tobytes())
        return self.wav

    def write_inputs(
        self,
        duration: float,
        *,
        segments: list[dict] | None = None,
        quality: dict | None = None,
    ) -> None:
        if segments is None:
            segments = [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": duration,
                    "text": "테스트.",
                    "words": [
                        {
                            "start": 0.0,
                            "end": duration,
                            "word": "테스트",
                            "probability": 0.95,
                        }
                    ],
                }
            ]
        self.stt.write_text(
            json.dumps({"segments": segments, "error": None}, ensure_ascii=False),
            encoding="utf-8",
        )
        audio_quality = {
            "voiced_threshold_dbfs": -50.0,
            "silence_threshold_dbfs": -60.0,
            "snr_proxy_db": 30.0,
            "background_noise_suspected": False,
            "reliability_flags": [],
        }
        if quality:
            audio_quality.update(quality)
        self.metrics.write_text(
            json.dumps({"audio_quality": audio_quality, "error": None}),
            encoding="utf-8",
        )

    def analyze(
        self,
        samples: np.ndarray,
        *,
        include_frames: bool = True,
        segments: list[dict] | None = None,
        quality: dict | None = None,
    ) -> dict:
        self.write_wav(samples)
        duration = len(samples) / self.SAMPLE_RATE
        self.write_inputs(duration, segments=segments, quality=quality)
        result = prosody.analyze_speech_prosody(
            self.wav,
            self.stt,
            self.metrics,
            include_frames=include_frames,
        )
        self.assertIsNone(result["error"], result["error"])
        return result

    def sine(self, frequency: float, duration: float = 1.0, amplitude: float = 0.2) -> np.ndarray:
        time = np.arange(round(duration * self.SAMPLE_RATE)) / self.SAMPLE_RATE
        return amplitude * np.sin(2.0 * math.pi * frequency * time)

    def chirp(
        self, start_hz: float, end_hz: float, duration: float = 1.2
    ) -> np.ndarray:
        count = round(duration * self.SAMPLE_RATE)
        frequencies = np.linspace(start_hz, end_hz, count)
        phase = 2.0 * math.pi * np.cumsum(frequencies) / self.SAMPLE_RATE
        return 0.2 * np.sin(phase)

    def test_detects_100_hz_sine(self) -> None:
        result = self.analyze(self.sine(100.0))
        self.assertAlmostEqual(
            result["pitch_summary"]["pitch_median_hz"], 100.0, delta=4.0
        )

    def test_detects_200_hz_sine(self) -> None:
        result = self.analyze(self.sine(200.0))
        self.assertAlmostEqual(
            result["pitch_summary"]["pitch_median_hz"], 200.0, delta=4.0
        )

    def test_out_of_range_f0_is_rejected(self) -> None:
        frame = self.sine(500.0, duration=0.04)
        f0, _ = prosody.estimate_frame_f0(frame, self.SAMPLE_RATE)
        self.assertIsNone(f0)

    def test_silence_has_no_pitch(self) -> None:
        result = self.analyze(np.zeros(self.SAMPLE_RATE))
        self.assertEqual(result["pitch_summary"]["pitch_valid_frame_count"], 0)
        self.assertIsNone(result["pitch_summary"]["pitch_median_hz"])

    def test_white_noise_has_low_pitch_confidence(self) -> None:
        rng = np.random.default_rng(17)
        frame = rng.normal(0.0, 0.1, round(0.04 * self.SAMPLE_RATE))
        f0, confidence = prosody.estimate_frame_f0(frame, self.SAMPLE_RATE)
        self.assertIsNone(f0)
        self.assertLess(confidence, 0.35)

    def test_rising_chirp_has_rising_ending(self) -> None:
        result = self.analyze(self.chirp(110.0, 190.0))
        ending = result["segment_prosody"][0]["ending_intonation"]
        self.assertEqual(ending["ending_pattern"], "rising")
        self.assertGreater(ending["ending_pitch_change_semitones"], 1.0)

    def test_falling_chirp_has_falling_ending(self) -> None:
        result = self.analyze(self.chirp(190.0, 110.0))
        ending = result["segment_prosody"][0]["ending_intonation"]
        self.assertEqual(ending["ending_pattern"], "falling")
        self.assertLess(ending["ending_pitch_change_semitones"], -1.0)

    def test_constant_frequency_has_level_ending(self) -> None:
        result = self.analyze(self.sine(150.0, duration=1.2))
        self.assertEqual(
            result["segment_prosody"][0]["ending_intonation"]["ending_pattern"],
            "level",
        )

    def test_two_times_frequency_is_octave_error_candidate(self) -> None:
        flags = prosody.detect_octave_error_candidates(
            [100.0, 101.0, 200.0, 200.0]
        )
        self.assertTrue(flags[1])
        self.assertTrue(flags[2])

    def test_three_frame_median_smoothing(self) -> None:
        smoothed = prosody.median_smooth_f0([100.0, 200.0, 101.0], 3)
        self.assertEqual(smoothed[1], 101.0)

    def test_short_gap_interpolation(self) -> None:
        values, flags = prosody.interpolate_short_f0_gaps(
            [100.0, None, None, 130.0], 2
        )
        self.assertEqual(values, [100.0, 110.0, 120.0, 130.0])
        self.assertEqual(flags, [False, True, True, False])

    def test_frame_rms_and_dbfs_are_recorded(self) -> None:
        result = self.analyze(self.sine(200.0, amplitude=0.1))
        frame = result["frames"][0]
        self.assertGreater(frame["rms"], 0)
        self.assertAlmostEqual(frame["dbfs"], -23.01, delta=0.5)

    def test_increasing_loudness_signal(self) -> None:
        time = np.arange(self.SAMPLE_RATE) / self.SAMPLE_RATE
        samples = np.linspace(0.02, 0.3, self.SAMPLE_RATE) * np.sin(
            2 * math.pi * 150 * time
        )
        result = self.analyze(samples)
        self.assertGreater(result["frames"][-1]["dbfs"], result["frames"][0]["dbfs"])
        self.assertGreater(result["loudness_summary"]["voiced_loudness_range_db"], 5)

    def test_decreasing_loudness_signal(self) -> None:
        time = np.arange(self.SAMPLE_RATE) / self.SAMPLE_RATE
        samples = np.linspace(0.3, 0.02, self.SAMPLE_RATE) * np.sin(
            2 * math.pi * 150 * time
        )
        result = self.analyze(samples)
        self.assertLess(result["frames"][-1]["dbfs"], result["frames"][0]["dbfs"])

    def test_clipping_frame_ratio(self) -> None:
        result = self.analyze(2.0 * self.sine(120.0, amplitude=1.0))
        self.assertGreater(result["loudness_summary"]["clipping_frame_ratio"], 0.5)

    def test_pitch_coverage_ratio(self) -> None:
        result = self.analyze(self.sine(120.0))
        self.assertGreater(result["pitch_summary"]["pitch_coverage_ratio"], 0.9)
        self.assertLessEqual(result["pitch_summary"]["pitch_coverage_ratio"], 1.0)

    def test_semitone_conversion(self) -> None:
        values = prosody.semitones_from_reference([100.0, 200.0], 100.0)
        self.assertAlmostEqual(values[0], 0.0)
        self.assertAlmostEqual(values[1], 12.0)

    def test_pitch_range_semitones(self) -> None:
        frames = [
            {"voiced": True, "smoothed_f0_hz": 100.0},
            {"voiced": True, "smoothed_f0_hz": 200.0},
        ]
        summary, _ = prosody.summarize_pitch(frames)
        self.assertAlmostEqual(summary["pitch_range_semitones"], 9.6, delta=0.1)

    def test_pitch_change_metrics(self) -> None:
        frames = [
            {"center_sec": 0.00, "voiced": True, "dbfs": -20.0, "smoothed_f0_hz": 100.0},
            {"center_sec": 0.01, "voiced": True, "dbfs": -19.0, "smoothed_f0_hz": 120.0},
            {"center_sec": 0.02, "voiced": True, "dbfs": -18.0, "smoothed_f0_hz": 100.0},
        ]
        pitch, _ = prosody.summarize_pitch(frames)
        summary = prosody.summarize_intonation(
            frames, pitch, prosody.ProsodyConfiguration()
        )
        self.assertGreater(summary["mean_absolute_pitch_change_semitones"], 3.0)
        self.assertEqual(summary["large_pitch_jump_count"], 2)
        self.assertEqual(summary["pitch_direction_change_count"], 1)

    def test_segment_prosody_is_created(self) -> None:
        segments = [
            {
                "id": 7,
                "start": 0.1,
                "end": 0.9,
                "text": "구간.",
                "words": [{"start": 0.1, "end": 0.9, "word": "구간"}],
            }
        ]
        result = self.analyze(self.sine(140.0), segments=segments)
        segment = result["segment_prosody"][0]
        self.assertEqual(segment["segment_id"], 7)
        self.assertEqual(segment["text"], "구간.")
        self.assertGreater(segment["valid_pitch_frame_count"], 3)

    def test_ending_uses_last_500_ms(self) -> None:
        result = self.analyze(self.chirp(100.0, 220.0, duration=1.5))
        ending = result["segment_prosody"][0]["ending_intonation"]
        self.assertGreater(ending["ending_pitch_start_hz"], 150.0)
        self.assertEqual(ending["ending_pattern"], "rising")

    def test_segment_with_insufficient_pitch_has_null_metrics(self) -> None:
        result = self.analyze(np.zeros(self.SAMPLE_RATE))
        segment = result["segment_prosody"][0]
        self.assertIsNone(segment["pitch_median_hz"])
        self.assertEqual(
            segment["ending_intonation"]["ending_pattern"], "insufficient_data"
        )
        self.assertEqual(segment["warnings"][0]["code"], "SEGMENT_PITCH_INSUFFICIENT")

    def test_background_noise_flag_is_forwarded(self) -> None:
        result = self.analyze(
            self.sine(120.0),
            quality={
                "background_noise_suspected": True,
                "reliability_flags": ["background_noise_suspected"],
            },
        )
        reliability = result["prosody_reliability"]
        self.assertTrue(reliability["background_noise_suspected"])
        self.assertIn("background_noise_suspected", reliability["reliability_flags"])

    def test_clipping_flag_is_forwarded(self) -> None:
        result = self.analyze(
            self.sine(120.0),
            quality={"reliability_flags": ["clipping_suspected"]},
        )
        self.assertTrue(result["prosody_reliability"]["clipping_suspected"])

    def test_low_snr_proxy_flag(self) -> None:
        result = self.analyze(
            self.sine(120.0), quality={"snr_proxy_db": 10.0}
        )
        reliability = result["prosody_reliability"]
        self.assertTrue(reliability["low_snr_proxy"])
        self.assertIn("low_snr_proxy", reliability["reliability_flags"])

    def test_missing_audio_quality_uses_explicit_reliability_flag(self) -> None:
        self.write_wav(self.sine(120.0))
        self.write_inputs(1.0)
        self.metrics.write_text(json.dumps({"error": None}), encoding="utf-8")
        result = prosody.analyze_speech_prosody(
            self.wav, self.stt, self.metrics
        )
        self.assertIsNone(result["error"])
        self.assertEqual(result["warnings"][0]["code"], "AUDIO_QUALITY_NOT_FOUND")
        self.assertIn(
            "audio_quality_unavailable",
            result["prosody_reliability"]["reliability_flags"],
        )

    def test_strict_json_atomic_save(self) -> None:
        payload = {"text": "한국어", "value": 1.0}
        prosody.write_json_atomic(self.output, payload)
        loaded = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(loaded, payload)
        self.assertFalse((self.directory / ".prosody.json.tmp").exists())

    def test_nan_and_infinity_become_null(self) -> None:
        text = prosody.strict_json_text(
            {"nan": float("nan"), "positive": float("inf"), "negative": -float("inf")}
        )
        loaded = json.loads(text)
        self.assertEqual(
            loaded, {"nan": None, "positive": None, "negative": None}
        )
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)

    def test_include_frames_option(self) -> None:
        samples = self.sine(120.0)
        omitted = self.analyze(samples, include_frames=False)
        included = self.analyze(samples, include_frames=True)
        self.assertEqual(omitted["frames"], [])
        self.assertGreater(len(included["frames"]), 0)

    def test_input_sha256_is_preserved(self) -> None:
        self.write_wav(self.sine(120.0))
        self.write_inputs(1.0)
        paths = [self.wav, self.stt, self.metrics]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        }
        prosody.analyze_speech_prosody(self.wav, self.stt, self.metrics)
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        }
        self.assertEqual(before, after)

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        self.write_wav(self.sine(120.0))
        self.write_inputs(1.0)
        args = [
            str(self.wav),
            str(self.stt),
            str(self.metrics),
            "--output",
            str(self.output),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = cli.main(args)
            failure = cli.main(
                [
                    str(self.directory / "missing.wav"),
                    str(self.stt),
                    str(self.metrics),
                    "--output",
                    str(self.output),
                ]
            )
            with self.assertRaises(SystemExit) as raised:
                cli.main([])
        self.assertEqual(success, 0)
        self.assertEqual(failure, 1)
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
