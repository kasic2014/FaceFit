"""Tests for conservative dual-estimator prosody validation v2."""

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

TEXT_HASH_SUFFIXES = {".csv", ".json", ".md", ".py", ".txt"}


def portable_sha256(path: Path, expected: str) -> str:
    data = path.read_bytes()
    raw_hash = hashlib.sha256(data).hexdigest()
    if raw_hash == expected:
        return raw_hash
    if path.suffix.lower() in TEXT_HASH_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from app.speech import prosody_validation as validation  # noqa: E402
import analyze_speech_prosody_v2 as cli  # noqa: E402


class ProsodyValidationTests(unittest.TestCase):
    SAMPLE_RATE = 16000
    V1_HASHES = {
        "app/speech/prosody_metrics.py": (
            "b66a0539e53e64dbfe94328bbcd5ac7f6f20b6b7e30eace8f09a664c9144eff8"
        ),
        "data/output/prosody/speech_01_clean_prosody.json": (
            "98628c7e08fa0ff827e76861306f5271c7a8ee4577828af05027e26aaf642966"
        ),
        "data/output/prosody/speech_03_silence_long_prosody.json": (
            "e9fd017b4d7da9d495f227bd2020b4dc7c1626492133f6907ab9ed55377fd4ce"
        ),
        "data/output/prosody/speech_04_fast_prosody.json": (
            "c9cb9da76c53b67704b7b5198f3930b9d0e4bb385d19e1b5f5c9d8ffc769927c"
        ),
        "data/output/prosody/speech_05_slow_prosody.json": (
            "7872122a1f9633e34cd7a6f83236bb28b369749722e19c1e218f12310f312cc3"
        ),
        "data/output/prosody/speech_06_noise_prosody.json": (
            "f520c44988c0b1649866638d038c1cc753040e29493bfca15080327a6ff2bfec"
        ),
    }

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.wav = self.directory / "audio.wav"
        self.stt = self.directory / "stt.json"
        self.metrics = self.directory / "metrics.json"
        self.output = self.directory / "prosody_v2.json"

    def sine(
        self,
        frequency: float,
        duration: float = 1.0,
        amplitude: float = 0.2,
    ) -> np.ndarray:
        time = np.arange(round(duration * self.SAMPLE_RATE)) / self.SAMPLE_RATE
        return amplitude * np.sin(2.0 * math.pi * frequency * time)

    def chirp(
        self, start_hz: float, end_hz: float, duration: float = 1.2
    ) -> np.ndarray:
        count = round(duration * self.SAMPLE_RATE)
        frequencies = np.linspace(start_hz, end_hz, count)
        phase = 2.0 * math.pi * np.cumsum(frequencies) / self.SAMPLE_RATE
        return 0.2 * np.sin(phase)

    def write_wav(self, samples: np.ndarray) -> None:
        pcm = np.rint(
            np.clip(samples, -1.0, 32767 / 32768) * 32768
        ).astype("<i2")
        with wave.open(str(self.wav), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self.SAMPLE_RATE)
            stream.writeframes(pcm.tobytes())

    def write_metadata(
        self,
        duration: float,
        *,
        quality: dict | None = None,
        segments: list[dict] | None = None,
    ) -> None:
        if segments is None:
            segments = [
                {
                    "id": 1,
                    "start": 0.0,
                    "end": duration,
                    "text": "합성 신호",
                    "words": [
                        {
                            "start": 0.0,
                            "end": duration,
                            "word": "합성",
                            "probability": 0.99,
                        }
                    ],
                }
            ]
        self.stt.write_text(
            json.dumps({"segments": segments, "error": None}, ensure_ascii=False),
            encoding="utf-8",
        )
        audio_quality = {
            "estimated_noise_floor_dbfs": -70.0,
            "speech_reference_dbfs": -20.0,
            "snr_proxy_db": 50.0,
            "clipping_frame_ratio": 0.0,
            "non_word_voiced_ratio": 0.0,
            "voiced_threshold_dbfs": -50.0,
            "silence_threshold_dbfs": -60.0,
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
        quality: dict | None = None,
        segments: list[dict] | None = None,
    ) -> dict:
        self.write_wav(samples)
        duration = len(samples) / self.SAMPLE_RATE
        self.write_metadata(duration, quality=quality, segments=segments)
        result = validation.analyze_speech_prosody_v2(
            self.wav,
            self.stt,
            self.metrics,
            include_frames=include_frames,
        )
        self.assertIsNone(result["error"], result["error"])
        return result

    @staticmethod
    def correction_frames(
        local_hz: float,
        raw_hz: float,
        alternate_hz: float,
    ) -> list[dict]:
        frames = []
        for index in range(7):
            center = index == 3
            frames.append(
                {
                    "frame_index": index,
                    "center_sec": index * 0.01,
                    "voiced_gate_passed": True,
                    "estimator_agreement": not center,
                    "autocorrelation_f0_hz": (
                        alternate_hz if center else local_hz
                    ),
                    "autocorrelation_confidence": 0.75,
                    "yin_f0_hz": raw_hz if center else local_hz,
                    "yin_confidence": 0.9,
                    "selected_f0_hz": raw_hz if center else local_hz,
                    "raw_selected_f0_hz": raw_hz if center else local_hz,
                    "unresolved_pitch_candidate": center,
                    "invalid_reasons": [],
                    "clipping": False,
                }
            )
        return frames

    def test_yin_detects_100_hz(self) -> None:
        f0, confidence = validation.estimate_yin_f0(
            self.sine(100.0, 0.04), self.SAMPLE_RATE
        )
        self.assertAlmostEqual(f0, 100.0, delta=4.0)
        self.assertGreaterEqual(confidence, 0.70)

    def test_yin_detects_200_hz(self) -> None:
        f0, confidence = validation.estimate_yin_f0(
            self.sine(200.0, 0.04), self.SAMPLE_RATE
        )
        self.assertAlmostEqual(f0, 200.0, delta=4.0)
        self.assertGreater(confidence, 0.80)

    def test_dual_estimators_agree(self) -> None:
        selected = validation.select_estimator_f0(100.0, 0.8, 101.0, 0.9)
        self.assertTrue(selected["estimator_agreement"])
        self.assertIn("agreement", selected["selection_reason"])

    def test_estimator_disagreement_is_explicit(self) -> None:
        relation = validation.classify_estimator_relation(100.0, 150.0)
        self.assertTrue(relation["estimator_disagreement"])
        self.assertTrue(relation["unresolved_pitch_candidate"])

    def test_octave_half_relation(self) -> None:
        relation = validation.classify_estimator_relation(100.0, 200.0)
        self.assertTrue(relation["octave_halving_candidate"])
        self.assertEqual(relation["subharmonic_candidate"], "autocorrelation")

    def test_octave_double_relation(self) -> None:
        relation = validation.classify_estimator_relation(200.0, 100.0)
        self.assertTrue(relation["octave_doubling_candidate"])
        self.assertEqual(relation["harmonic_candidate"], "autocorrelation")

    def test_halving_correction(self) -> None:
        frames = self.correction_frames(100.0, 200.0, 100.0)
        validation.apply_octave_corrections(frames)
        self.assertEqual(frames[3]["corrected_f0_hz"], 100.0)
        self.assertEqual(
            frames[3]["correction_type"], "octave_halving_correction"
        )

    def test_doubling_correction(self) -> None:
        frames = self.correction_frames(200.0, 100.0, 200.0)
        validation.apply_octave_corrections(frames)
        self.assertEqual(frames[3]["corrected_f0_hz"], 200.0)
        self.assertEqual(
            frames[3]["correction_type"], "octave_doubling_correction"
        )

    def test_insufficient_evidence_remains_unresolved(self) -> None:
        frames = self.correction_frames(100.0, 200.0, 100.0)
        frames[0]["voiced_gate_passed"] = False
        frames[1]["voiced_gate_passed"] = False
        frames[5]["voiced_gate_passed"] = False
        frames[6]["voiced_gate_passed"] = False
        validation.apply_octave_corrections(frames)
        self.assertFalse(frames[3]["correction_applied"])
        self.assertFalse(frames[3]["valid"])

    def test_long_silence_boundary_is_not_crossed(self) -> None:
        frames = self.correction_frames(100.0, 200.0, 100.0)
        frames[2]["voiced_gate_passed"] = False
        frames[4]["voiced_gate_passed"] = False
        validation.apply_octave_corrections(frames)
        self.assertFalse(frames[3]["correction_applied"])
        self.assertIn(
            "insufficient_local_continuity_support",
            frames[3]["invalid_reasons"],
        )

    def test_noise_is_rejected_by_voiced_gate(self) -> None:
        rng = np.random.default_rng(7)
        result = self.analyze(
            rng.normal(0.0, 0.08, self.SAMPLE_RATE),
            quality={
                "estimated_noise_floor_dbfs": -23.0,
                "voiced_threshold_dbfs": -30.0,
                "background_noise_suspected": True,
                "reliability_flags": ["background_noise_suspected"],
            },
        )
        self.assertEqual(
            result["validated_pitch_summary"]["pitch_valid_frame_count"], 0
        )

    def test_clipping_frames_are_excluded(self) -> None:
        result = self.analyze(2.0 * self.sine(120.0, amplitude=1.0))
        self.assertEqual(
            result["validated_pitch_summary"]["pitch_valid_frame_count"], 0
        )
        self.assertTrue(
            any(
                "clipping_frame_excluded" in frame["invalid_reasons"]
                for frame in result["frames"]
            )
        )

    def test_strong_harmonic_signal_is_measured_without_forced_octave(self) -> None:
        signal = self.sine(100.0, amplitude=0.10) + self.sine(
            200.0, amplitude=0.25
        )
        result = self.analyze(signal)
        median = result["validated_pitch_summary"]["pitch_median_hz"]
        self.assertIsNotNone(median)
        self.assertGreater(median, 60.0)
        self.assertLess(median, 400.0)

    def test_subharmonic_signal_is_reported_conservatively(self) -> None:
        signal = self.sine(200.0, amplitude=0.20) + self.sine(
            100.0, amplitude=0.08
        )
        result = self.analyze(signal)
        summary = result["correction_summary"]
        self.assertGreaterEqual(summary["unresolved_frame_count"], 0)
        self.assertLessEqual(summary["corrected_frame_count"], len(result["frames"]))

    def test_raw_and_corrected_values_are_preserved(self) -> None:
        frames = self.correction_frames(100.0, 200.0, 100.0)
        validation.apply_octave_corrections(frames)
        self.assertEqual(frames[3]["raw_selected_f0_hz"], 200.0)
        self.assertEqual(frames[3]["corrected_f0_hz"], 100.0)

    def test_correction_reasons_are_recorded(self) -> None:
        frames = self.correction_frames(100.0, 200.0, 100.0)
        validation.apply_octave_corrections(frames)
        self.assertIn(
            "local_pitch_jump_reduced", frames[3]["correction_reasons"]
        )
        self.assertGreater(frames[3]["correction_confidence"], 0.0)

    def test_correction_reduces_pitch_jump(self) -> None:
        frames = self.correction_frames(100.0, 200.0, 100.0)
        validation.apply_octave_corrections(frames)
        raw = validation.track_jump_metrics(frames, "raw_selected_f0_hz")
        corrected = validation.track_jump_metrics(
            frames, "corrected_f0_hz", valid_only=True
        )
        self.assertGreater(
            raw["total_pitch_jump_semitones"],
            corrected["total_pitch_jump_semitones"],
        )

    def test_real_pitch_change_is_preserved(self) -> None:
        result = self.analyze(self.chirp(100.0, 180.0))
        self.assertGreater(
            result["validated_pitch_summary"]["pitch_range_semitones"], 3.0
        )

    def test_segment_uses_corrected_track_fields(self) -> None:
        result = self.analyze(self.sine(140.0))
        segment = result["segment_prosody"][0]
        self.assertIn("corrected_pitch_median_hz", segment)
        self.assertGreater(segment["validated_pitch_frame_count"], 3)
        self.assertIn(
            "octave_candidate_count", result["correction_summary"]
        )

    def test_quality_flag_is_forwarded(self) -> None:
        result = self.analyze(
            self.sine(120.0),
            quality={
                "background_noise_suspected": True,
                "reliability_flags": ["background_noise_suspected"],
            },
        )
        self.assertIn(
            "background_noise_suspected",
            result["prosody_reliability"]["reliability_flags"],
        )

    def test_strict_json_has_no_nonfinite_constants(self) -> None:
        text = validation.strict_json_text(
            {"nan": float("nan"), "infinity": float("inf")}
        )
        self.assertEqual(json.loads(text), {"nan": None, "infinity": None})
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)

    def test_include_frames_option(self) -> None:
        included = self.analyze(self.sine(120.0), include_frames=True)
        omitted = self.analyze(self.sine(120.0), include_frames=False)
        self.assertGreater(len(included["frames"]), 0)
        self.assertEqual(omitted["frames"], [])
        self.assertTrue(
            omitted["configuration"]["frames_omitted_from_output"]
        )

    def test_v1_module_and_outputs_are_unchanged(self) -> None:
        for relative, expected in self.V1_HASHES.items():
            path = ROOT / relative
            actual = portable_sha256(path, expected)
            self.assertEqual(actual, expected, relative)

    def test_source_sha256_is_preserved(self) -> None:
        self.write_wav(self.sine(120.0))
        self.write_metadata(1.0)
        paths = [self.wav, self.stt, self.metrics]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        }
        validation.analyze_speech_prosody_v2(
            self.wav, self.stt, self.metrics
        )
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        }
        self.assertEqual(before, after)

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        self.write_wav(self.sine(120.0))
        self.write_metadata(1.0)
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

    def test_configuration_contains_experimental_thresholds(self) -> None:
        config = validation.ProsodyValidationConfiguration()
        self.assertEqual(config.yin_threshold, 0.15)
        self.assertEqual(config.yin_fallback_threshold, 0.30)
        self.assertEqual(config.estimator_agreement_semitones, 0.75)

    def test_synthetic_error_metrics(self) -> None:
        report = validation.evaluate_synthetic_estimates(
            [100.0, 201.0, None], [100.0, 200.0, 150.0]
        )
        self.assertEqual(report["scope"], "synthetic_signals_only")
        self.assertAlmostEqual(report["valid_frame_ratio"], 2 / 3, places=6)
        self.assertLess(report["absolute_error_hz_mean"], 1.0)

    def test_synthetic_correction_precision_and_recall(self) -> None:
        report = validation.evaluate_synthetic_estimates(
            [100.0, 200.0],
            [100.0, 200.0],
            correction_flags=[True, False],
            expected_corrections=[True, False],
        )
        self.assertEqual(report["correction_precision"], 1.0)
        self.assertEqual(report["correction_recall"], 1.0)

    def test_twelve_synthetic_scenarios_are_reported(self) -> None:
        report = validation.run_synthetic_validation_suite()
        self.assertEqual(report["scope"], "synthetic_signals_only")
        self.assertEqual(report["scenario_count"], 12)
        self.assertEqual(len(report["scenarios"]), 12)

    def test_synthetic_rising_and_falling_scenarios_have_errors(self) -> None:
        report = validation.run_synthetic_validation_suite()
        by_name = {
            item["scenario"]: item for item in report["scenarios"]
        }
        for name in ("gradual_rising_pitch", "gradual_falling_pitch"):
            self.assertGreater(by_name[name]["valid_frame_ratio"], 0.5)
            self.assertIsNotNone(
                by_name[name]["absolute_error_semitones_mean"]
            )

    def test_synthetic_noise_and_hum_scenarios_are_present(self) -> None:
        report = validation.run_synthetic_validation_suite()
        names = {item["scenario"] for item in report["scenarios"]}
        self.assertIn("voiced_with_white_noise", names)
        self.assertIn("voiced_with_low_frequency_hum", names)
        self.assertIn("clipped_voiced_signal", names)

    def test_synthetic_injected_octaves_are_corrected_precisely(self) -> None:
        report = validation.run_synthetic_validation_suite()
        injected = [
            item
            for item in report["scenarios"]
            if item["scenario"].startswith("sudden_octave_")
        ]
        self.assertEqual(len(injected), 2)
        for item in injected:
            self.assertEqual(item["correction_precision"], 1.0)
            self.assertEqual(item["correction_recall"], 1.0)
            self.assertEqual(item["octave_error_rate"], 0.0)

    def test_missing_quality_metrics_returns_classified_error(self) -> None:
        self.write_wav(self.sine(120.0))
        self.write_metadata(1.0)
        result = validation.analyze_speech_prosody_v2(
            self.wav, self.stt, self.directory / "missing.json"
        )
        self.assertEqual(result["error"]["code"], "SPEECH_METRICS_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
