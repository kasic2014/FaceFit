"""Tests for prosody v2.1 denominator and harmonic diagnostics."""

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

from app.speech import prosody_validation_v21 as v21  # noqa: E402
import analyze_speech_prosody_v21 as cli  # noqa: E402


class ProsodyValidationV21Tests(unittest.TestCase):
    SAMPLE_RATE = 16000
    IMMUTABLE_PROSODY_HASHES = {
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
        "data/output/prosody_v2/speech_01_clean_prosody_v2.json": (
            "d0b4cf6ef30f5cc8cc2408c9d5d1b0990350ebd9282eaddba8f2ec668f53b8f4"
        ),
        "data/output/prosody_v2/speech_03_silence_long_prosody_v2.json": (
            "2f3e3f7a1a8f64cd1b4325911f81a18684ef8bac25e3708d84d5c6150ceaa46a"
        ),
        "data/output/prosody_v2/speech_04_fast_prosody_v2.json": (
            "41f746208db7b6f02ba3702283e2c0dbcffbbe9cbcf4a4e9d00c870b39702702"
        ),
        "data/output/prosody_v2/speech_05_slow_prosody_v2.json": (
            "0502c7cbd4565a3b004e3f99334c60cfc4a41bae98948a21ef01ac1d93cd7409"
        ),
        "data/output/prosody_v2/speech_06_noise_prosody_v2.json": (
            "179816e3d7fb618c801b8989cdafe74ebe7a8d1549fc3a292ead0e63a7c91d74"
        ),
        "data/output/prosody_v2/prosody_v1_v2_comparison.json": (
            "d2a871aff57c7f6615fd7420cc48781bb38a9b6263acb685c136b7a4fff0cf78"
        ),
        "data/output/prosody_v2/prosody_v1_v2_comparison.csv": (
            "4cb8f97dcdf0370f63786d4e434b44ea1f1114f311c787ab88c1c03040faad17"
        ),
    }
    IMMUTABLE_INPUT_HASHES = {
        "data/input/audio/standard/speech_01_clean.wav": (
            "6da99df5f1511575c237d861246fcdb5eaae7a8edc8794a0cd5fdaf5bb717aad"
        ),
        "data/input/audio/standard/speech_03_silence_long.wav": (
            "9d1c933138addcc72538da31bfb7be299741d112cb80021040f9c66d98d885c5"
        ),
        "data/input/audio/standard/speech_04_fast.wav": (
            "397b1abf66f7665e306bbe846af0bd518c9893ff16de2a2f9797eac4e9be4cfe"
        ),
        "data/input/audio/standard/speech_05_slow.wav": (
            "a11849d60c91ea7801874ec8884a9104807a478b1b9244375be35a580baee72d"
        ),
        "data/input/audio/standard/speech_06_noise.wav": (
            "937283dca0c133a8cc6985036ed5f82cfdb654864be45d9e2bc1969e485ead5d"
        ),
        "data/output/speech_01_clean_turbo_cuda_retry1.json": (
            "d85fadb5d090fd09d5cec560f90555d1fa229fcfec2f131ca4a74ebe6e4d028c"
        ),
        "data/output/speech_03_silence_long_turbo_cuda.json": (
            "025944f0a341702de0d16f5a563f550ec6fbb1606946f2dda5b6849b5cd67b75"
        ),
        "data/output/speech_04_fast_turbo_cuda.json": (
            "14c64d626160f0d84fa8a52543efb7e4deb44db33f6bd049d84ecfe0a35c63e3"
        ),
        "data/output/speech_05_slow_turbo_cuda.json": (
            "b9d3a3ca7457a8453d7d21282a46985f7f4671cb67d57ab16ce75b90b95480e7"
        ),
        "data/output/speech_06_noise_turbo_cuda.json": (
            "138ee0202bfb18bafbafd633023ccbcf0df306ff825687d6b89dd7836b0d7c5e"
        ),
        "data/output/speech_01_clean_metrics_quality.json": (
            "540d20267e5b52a621bb0cbf12bbb6176cd4760d624b5a92b26fc8852c51feef"
        ),
        "data/output/speech_03_silence_long_metrics_quality.json": (
            "142f9d9eb0d74b56a7fe56aafae2966a4aaf73374dc1305ffb1330594ceb3d93"
        ),
        "data/output/speech_04_fast_metrics_quality.json": (
            "805a4af98f61219d9d388006791a6dd46ae9869cc0c0a423c34e814a566a488a"
        ),
        "data/output/speech_05_slow_metrics_quality.json": (
            "a1b3d272d91c82a7132766cf2d1ea1f09fe3fdc8d3524a30430b842d1aae426f"
        ),
        "data/output/speech_06_noise_metrics_quality.json": (
            "f68873ab8716f7a20e3ad7b5b99ce37f282fb2f709f57a0ff57bfcd14125eb09"
        ),
    }

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.wav = self.directory / "audio.wav"
        self.stt = self.directory / "stt.json"
        self.metrics = self.directory / "metrics.json"
        self.output = self.directory / "v21.json"

    @staticmethod
    def frame(
        acf: float | None,
        yin: float | None,
        *,
        agree: bool = False,
        dbfs: float = -20.0,
        valid: bool = False,
    ) -> dict:
        return {
            "autocorrelation_f0_hz": acf,
            "yin_f0_hz": yin,
            "estimator_agreement": agree,
            "dbfs": dbfs,
            "valid": valid,
            "corrected_f0_hz": acf if valid else None,
        }

    def signal(self, components: list[tuple[float, float]], duration: float = 1.0) -> np.ndarray:
        time = np.arange(round(duration * self.SAMPLE_RATE)) / self.SAMPLE_RATE
        return sum(
            amplitude * np.sin(2 * math.pi * frequency * time)
            for frequency, amplitude in components
        )

    def write_inputs(self, samples: np.ndarray) -> None:
        pcm = np.rint(
            np.clip(samples, -1.0, 32767 / 32768) * 32768
        ).astype("<i2")
        with wave.open(str(self.wav), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self.SAMPLE_RATE)
            stream.writeframes(pcm.tobytes())
        duration = len(samples) / self.SAMPLE_RATE
        self.stt.write_text(
            json.dumps(
                {
                    "segments": [
                        {
                            "id": 1,
                            "start": 0.0,
                            "end": duration,
                            "text": "합성",
                            "words": [
                                {
                                    "start": 0.0,
                                    "end": duration,
                                    "word": "합성",
                                    "probability": 0.99,
                                }
                            ],
                        }
                    ],
                    "error": None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.metrics.write_text(
            json.dumps(
                {
                    "audio_quality": {
                        "estimated_noise_floor_dbfs": -70.0,
                        "speech_reference_dbfs": -20.0,
                        "snr_proxy_db": 50.0,
                        "clipping_frame_ratio": 0.0,
                        "non_word_voiced_ratio": 0.0,
                        "voiced_threshold_dbfs": -50.0,
                        "silence_threshold_dbfs": -60.0,
                        "background_noise_suspected": False,
                        "reliability_flags": [],
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )

    def suite_by_name(self) -> dict[str, dict]:
        result = v21.run_synthetic_validation_v21_suite()
        return {item["scenario"]: item for item in result["scenarios"]}

    def test_total_frame_count_is_preserved(self) -> None:
        frames = [self.frame(None, None) for _ in range(5)]
        coverage, _, _ = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(coverage["total_analysis_frame_count"], 5)

    def test_acoustic_voiced_frame_count(self) -> None:
        frames = [
            self.frame(None, None, dbfs=-20),
            self.frame(None, None, dbfs=-50),
        ]
        coverage, _, _ = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(coverage["acoustic_voiced_frame_count"], 1)

    def test_both_valid_agree_status(self) -> None:
        frame = self.frame(100, 101, agree=True)
        self.assertEqual(v21.dual_estimator_state(frame), "both_valid_agree")

    def test_both_valid_disagree_status(self) -> None:
        frame = self.frame(100, 150)
        self.assertEqual(v21.dual_estimator_state(frame), "both_valid_disagree")

    def test_autocorrelation_only_status(self) -> None:
        self.assertEqual(
            v21.dual_estimator_state(self.frame(100, None)),
            "autocorrelation_only",
        )

    def test_yin_only_status(self) -> None:
        self.assertEqual(
            v21.dual_estimator_state(self.frame(None, 100)), "yin_only"
        )

    def test_both_invalid_status(self) -> None:
        self.assertEqual(
            v21.dual_estimator_state(self.frame(None, None)), "both_invalid"
        )

    def test_status_matrix_sum_matches_total(self) -> None:
        frames = [
            self.frame(100, 100, agree=True),
            self.frame(100, 150),
            self.frame(100, None),
            self.frame(None, 100),
            self.frame(None, None),
        ]
        coverage, statuses, _ = v21.summarize_dual_estimator_frames(
            frames, -40
        )
        self.assertEqual(sum(statuses.values()), coverage["total_analysis_frame_count"])

    def test_joint_valid_coverage(self) -> None:
        frames = [
            self.frame(100, 100, agree=True),
            self.frame(100, None),
        ]
        coverage, _, _ = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(coverage["dual_estimator_joint_valid_ratio"], 0.5)

    def test_voiced_based_validated_coverage(self) -> None:
        frames = [
            self.frame(100, 100, agree=True, valid=True),
            self.frame(None, None, dbfs=-20),
            self.frame(None, None, dbfs=-80),
        ]
        coverage, _, _ = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(
            coverage["validated_pitch_voiced_coverage_ratio"], 0.5
        )

    def test_conditioned_agreement_ratio(self) -> None:
        frames = [
            self.frame(100, 100, agree=True),
            self.frame(100, 150),
        ]
        _, _, agreement = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(
            agreement["estimator_agreement_ratio_conditioned_on_joint_valid"],
            0.5,
        )

    def test_voiced_based_agreement_ratio(self) -> None:
        frames = [
            self.frame(100, 100, agree=True),
            self.frame(None, None, dbfs=-20),
        ]
        _, _, agreement = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(
            agreement["estimator_agreement_ratio_over_acoustic_voiced"], 0.5
        )

    def test_total_based_agreement_ratio(self) -> None:
        frames = [
            self.frame(100, 100, agree=True),
            self.frame(None, None, dbfs=-80),
        ]
        _, _, agreement = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(
            agreement["estimator_agreement_ratio_over_total_frames"], 0.5
        )

    def test_zero_agreement_frames(self) -> None:
        frames = [self.frame(100, 150), self.frame(None, None)]
        _, _, agreement = v21.summarize_dual_estimator_frames(frames, -40)
        self.assertEqual(agreement["estimator_agreement_frame_count"], 0)
        self.assertEqual(
            agreement["estimator_agreement_ratio_conditioned_on_joint_valid"],
            0.0,
        )

    def test_zero_denominators_are_null(self) -> None:
        coverage, _, agreement = v21.summarize_dual_estimator_frames([], -40)
        self.assertIsNone(coverage["acoustic_voiced_ratio"])
        self.assertIsNone(coverage["validated_pitch_voiced_coverage_ratio"])
        self.assertIsNone(
            agreement["estimator_agreement_ratio_conditioned_on_joint_valid"]
        )

    def test_perfect_conditioned_agreement_can_warn_low_joint_coverage(self) -> None:
        coverage = {
            "dual_estimator_joint_valid_voiced_ratio": 0.1,
            "validated_pitch_voiced_coverage_ratio": 0.1,
        }
        agreement = {"estimator_agreement_frame_count": 25}
        harmonic = {
            "harmonic_ambiguity_ratio": 0.0,
            "octave_alternative_dominant_ratio": 0.0,
        }
        diagnostic = v21.build_shared_failure_diagnostics(
            coverage,
            agreement,
            harmonic,
            background_noise_suspected=False,
            clipping_suspected=False,
        )
        self.assertTrue(diagnostic["low_joint_valid_coverage"])

    def test_shared_octave_risk(self) -> None:
        diagnostic = v21.build_shared_failure_diagnostics(
            {
                "dual_estimator_joint_valid_voiced_ratio": 1.0,
                "validated_pitch_voiced_coverage_ratio": 1.0,
            },
            {"estimator_agreement_frame_count": 30},
            {
                "harmonic_ambiguity_ratio": 0.5,
                "octave_alternative_dominant_ratio": 0.5,
            },
            background_noise_suspected=False,
            clipping_suspected=False,
        )
        self.assertTrue(diagnostic["shared_octave_error_risk"])

    def test_harmonic_support_score(self) -> None:
        frame = self.signal([(100, 0.2)], 0.04)
        support = v21.analyze_harmonic_support(
            frame, self.SAMPLE_RATE, 100
        )
        self.assertGreater(support["harmonic_support_score"], 0.5)

    def test_half_frequency_support(self) -> None:
        frame = self.signal([(100, 0.2)], 0.04)
        support = v21.analyze_harmonic_support(
            frame, self.SAMPLE_RATE, 200
        )
        self.assertGreater(
            support["half_frequency_support_score"],
            support["harmonic_support_score"],
        )

    def test_double_frequency_support(self) -> None:
        frame = self.signal([(200, 0.2)], 0.04)
        support = v21.analyze_harmonic_support(
            frame, self.SAMPLE_RATE, 100
        )
        self.assertGreater(
            support["double_frequency_support_score"],
            support["harmonic_support_score"],
        )

    def test_harmonic_ambiguity(self) -> None:
        frame = self.signal([(200, 0.18), (300, 0.14), (400, 0.10)], 0.04)
        support = v21.analyze_harmonic_support(
            frame, self.SAMPLE_RATE, 100
        )
        self.assertTrue(support["harmonic_support_ambiguous"])

    def test_weak_fundamental_strong_harmonics_ground_truth(self) -> None:
        item = self.suite_by_name()[
            "weak_100hz_fundamental_strong_harmonics"
        ]
        self.assertEqual(item["expected_f0_hz"], 100.0)
        self.assertLess(item["absolute_error_hz"], 5.0)

    def test_missing_fundamental_ground_truth(self) -> None:
        item = self.suite_by_name()["missing_100hz_fundamental"]
        self.assertIn("greatest common periodicity", item["description"])
        self.assertEqual(item["expected_f0_hz"], 100.0)

    def test_200hz_with_50hz_hum(self) -> None:
        item = self.suite_by_name()["200hz_voiced_with_50hz_hum"]
        self.assertEqual(item["expected_f0_hz"], 200.0)
        self.assertLess(item["absolute_error_hz"], 5.0)

    def test_200hz_with_60hz_hum(self) -> None:
        item = self.suite_by_name()["200hz_voiced_with_60hz_hum"]
        self.assertEqual(item["expected_f0_hz"], 200.0)
        self.assertLess(item["absolute_error_hz"], 5.0)

    def test_200hz_with_low_frequency_nonperiodic_noise(self) -> None:
        item = self.suite_by_name()[
            "200hz_voiced_with_low_frequency_nonperiodic_noise"
        ]
        self.assertEqual(item["expected_f0_hz"], 200.0)
        self.assertLess(item["absolute_error_hz"], 10.0)

    def test_actual_100hz_200hz_composite_truth_is_100hz(self) -> None:
        item = self.suite_by_name()["actual_100hz_plus_200hz_composite"]
        self.assertEqual(item["expected_f0_hz"], 100.0)
        self.assertEqual(item["octave_error_rate"], 0.0)

    def test_ambiguous_truth_prohibits_accuracy(self) -> None:
        item = self.suite_by_name()[
            "ambiguous_independent_130hz_181hz_sources"
        ]
        self.assertEqual(item["ground_truth_status"], "ambiguous")
        self.assertFalse(item["accuracy_metrics_calculated"])
        self.assertIsNone(item["absolute_error_hz"])
        self.assertIsNone(item["absolute_error_cents"])
        self.assertIsNone(item["octave_error_rate"])

    def test_strict_json(self) -> None:
        text = v21.strict_json_text(
            {"nan": float("nan"), "infinity": float("inf")}
        )
        self.assertEqual(json.loads(text), {"nan": None, "infinity": None})

    def test_v1_and_v2_output_sha256_preserved(self) -> None:
        for relative, expected in self.IMMUTABLE_PROSODY_HASHES.items():
            actual = portable_sha256(ROOT / relative, expected)
            self.assertEqual(actual, expected, relative)

    def test_wav_stt_metrics_sha256_preserved(self) -> None:
        for relative, expected in self.IMMUTABLE_INPUT_HASHES.items():
            actual = portable_sha256(ROOT / relative, expected)
            self.assertEqual(actual, expected, relative)

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        self.write_inputs(self.signal([(120, 0.2)]))
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

    def test_frames_only_with_include_frames(self) -> None:
        self.write_inputs(self.signal([(120, 0.2)]))
        omitted = v21.analyze_speech_prosody_v21(
            self.wav, self.stt, self.metrics
        )
        included = v21.analyze_speech_prosody_v21(
            self.wav, self.stt, self.metrics, include_frames=True
        )
        self.assertEqual(omitted["frames"], [])
        self.assertGreater(len(included["frames"]), 0)
        self.assertIn("dual_estimator_state", included["frames"][0])
        self.assertIn("harmonic_support_score", included["frames"][0])

    def test_status_matrix_in_real_schema_sums_to_total(self) -> None:
        self.write_inputs(self.signal([(120, 0.2)]))
        result = v21.analyze_speech_prosody_v21(
            self.wav, self.stt, self.metrics
        )
        self.assertIsNone(result["error"])
        self.assertEqual(
            sum(result["dual_estimator_status"].values()),
            result["coverage_summary"]["total_analysis_frame_count"],
        )

    def test_schema_notes_define_compatibility_denominators(self) -> None:
        self.write_inputs(self.signal([(120, 0.2)]))
        result = v21.analyze_speech_prosody_v21(
            self.wav, self.stt, self.metrics
        )
        self.assertIn(
            "total_analysis_frame_count",
            result["schema_notes"]["pitch_coverage_ratio"],
        )
        self.assertIn(
            "정확도의 독립적인 증거가 아니다",
            result["schema_notes"]["agreement_limit"],
        )

    def test_reliability_level_is_not_numeric(self) -> None:
        level = v21.classify_experimental_reliability(
            {
                "dual_estimator_joint_valid_voiced_ratio": 1.0,
                "validated_pitch_voiced_coverage_ratio": 1.0,
            },
            {
                "background_noise_suspected": False,
                "shared_octave_error_risk": False,
                "harmonic_ambiguity_risk": False,
                "risk_flags": [],
            },
            clipping_frame_ratio=0.0,
        )
        self.assertEqual(level, "sufficient_for_experimental_summary")

    def test_background_noise_is_unreliable(self) -> None:
        level = v21.classify_experimental_reliability(
            {
                "dual_estimator_joint_valid_voiced_ratio": 1.0,
                "validated_pitch_voiced_coverage_ratio": 1.0,
            },
            {
                "background_noise_suspected": True,
                "shared_octave_error_risk": False,
                "harmonic_ambiguity_risk": False,
                "risk_flags": ["background_noise_suspected"],
            },
            clipping_frame_ratio=0.0,
        )
        self.assertEqual(level, "unreliable")


if __name__ == "__main__":
    unittest.main()
