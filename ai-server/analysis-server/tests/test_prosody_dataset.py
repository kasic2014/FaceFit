"""Tests for anonymous prosody dataset registration and benchmarking."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from app.speech import prosody_dataset as dataset  # noqa: E402
import create_prosody_dataset_manifest as create_cli  # noqa: E402
import register_prosody_sample as register_cli  # noqa: E402
import run_prosody_dataset_benchmark as benchmark_cli  # noqa: E402


class ProsodyDatasetTests(unittest.TestCase):
    IMMUTABLE_HASHES = {
        "app/speech/prosody_metrics.py": (
            "b66a0539e53e64dbfe94328bbcd5ac7f6f20b6b7e30eace8f09a664c9144eff8"
        ),
        "app/speech/prosody_validation.py": (
            "422d7c224d2ee80265ab3aa542229c8ac314abd74600acacb3ba200119caf48c"
        ),
        "app/speech/prosody_validation_v21.py": (
            "c95e22a0d1e77f4ba1a994ce74650d5481e675e1db632a05f1735a1f4e0e5663"
        ),
        "data/output/prosody_v21/speech_01_clean_prosody_v21.json": (
            "7a8f044320aa3fa482b5404cae9ee431f958c1c67b21ecb0fc42641eae53e10d"
        ),
        "data/output/prosody_v21/speech_03_silence_long_prosody_v21.json": (
            "7498d0d5037af6e100fba721bbef18b6d4f3cb9e366bd203fb9dc21b6e55d251"
        ),
        "data/output/prosody_v21/speech_04_fast_prosody_v21.json": (
            "10f108f8f7c3cb54b0a94629c63ecc334579ca8ec2a34107b0f02cc49182dc4d"
        ),
        "data/output/prosody_v21/speech_05_slow_prosody_v21.json": (
            "11eab266ec698673297acaa9ab98eaaa51d5f798b34bbca265c6a667d9df77c1"
        ),
        "data/output/prosody_v21/speech_06_noise_prosody_v21.json": (
            "327ba4e04f540a402f3375616cd3b7221a3561e20b6a8e731ac60e95a0a7592e"
        ),
        "data/output/prosody_v21/prosody_v2_v21_comparison.json": (
            "c985602b30e3f24527654b7181925782509a64b5c5710dc16150339abc6eb6cb"
        ),
        "data/output/prosody_v21/prosody_v2_v21_comparison.csv": (
            "3f41bdfd6fcc58e834a70cf2b98fbc6c2af87a67a4e1674184404a829b06f72f"
        ),
    }

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.manifest = self.directory / "manifest.csv"
        self.wav = self.directory / "audio.wav"
        self.stt = self.directory / "stt.json"
        self.metrics = self.directory / "metrics.json"
        self.prosody = self.directory / "prosody.json"
        dataset.create_empty_manifest(self.manifest)
        self.write_artifacts()

    def write_artifacts(
        self,
        *,
        schema: str = "2.1",
        prosody_error: object = None,
        reliability: str = "limited",
        pitch: float = 120.0,
        coverage: float = 0.6,
        harmonic: float = 0.1,
    ) -> None:
        self.wav.write_bytes(b"RIFF-test-wave")
        self.stt.write_text(
            json.dumps({"segments": [], "error": None}), encoding="utf-8"
        )
        self.metrics.write_text(
            json.dumps(
                {
                    "audio_quality": {
                        "estimated_noise_floor_dbfs": -45.0,
                        "speech_reference_dbfs": -20.0,
                        "snr_proxy_db": 25.0,
                        "clipping_frame_ratio": 0.0,
                        "non_word_voiced_ratio": 0.1,
                        "background_noise_suspected": False,
                        "reliability_flags": [],
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        self.prosody.write_text(
            json.dumps(
                {
                    "schema_version": schema,
                    "validated_pitch_summary": {
                        "pitch_median_hz": pitch,
                        "pitch_range_semitones": 4.0,
                    },
                    "coverage_summary": {
                        "validated_pitch_overall_coverage_ratio": 0.4,
                        "validated_pitch_voiced_coverage_ratio": coverage,
                        "dual_estimator_joint_valid_voiced_ratio": coverage + 0.05,
                    },
                    "agreement_summary": {
                        "estimator_agreement_ratio_conditioned_on_joint_valid": 1.0,
                        "estimator_agreement_ratio_over_acoustic_voiced": coverage,
                    },
                    "harmonic_support_summary": {
                        "harmonic_ambiguity_ratio": harmonic,
                        "agreement_harmonic_ambiguity_ratio": harmonic / 2,
                    },
                    "shared_failure_diagnostics": {
                        "shared_octave_error_risk": False,
                        "harmonic_ambiguity_risk": False,
                    },
                    "analysis_reliability_level": reliability,
                    "prosody_reliability": {
                        "clipping_suspected": False,
                        "reliability_flags": [],
                    },
                    "error": prosody_error,
                }
            ),
            encoding="utf-8",
        )

    def sample(
        self,
        sample_id: str = "SAMPLE001",
        *,
        repetition: int = 1,
        device: str = "DEV_PC_MIC_01",
        condition: str = "clean",
        consent: bool = True,
        script: str = "SCRIPT001",
        session: str = "SESSION001",
    ) -> dict:
        return {
            "sample_id": sample_id,
            "speaker_code": "SPK001",
            "session_id": session,
            "script_id": script,
            "repetition_index": repetition,
            "device_code": device,
            "environment_code": "QUIET_ROOM",
            "recording_condition": condition,
            "wav_path": self.wav,
            "stt_json_path": self.stt,
            "speech_metrics_json_path": self.metrics,
            "prosody_v21_json_path": self.prosody,
            "consent_confirmed": consent,
            "notes": "distance=30cm; auto_gain=off",
        }

    def register(self, **kwargs: object) -> dict:
        return dataset.register_sample(
            self.manifest,
            self.sample(**kwargs),
            workspace_root=self.directory,
        )

    @staticmethod
    def result_sample(
        sample_id: str,
        *,
        repetition: int = 1,
        device: str = "DEV1",
        condition: str = "clean",
        pitch: float | None = 100.0,
        coverage: float | None = 0.6,
        harmonic: float | None = 0.1,
        reliability: str = "limited",
        status: str = "ready_for_benchmark",
    ) -> dict:
        return {
            "sample_id": sample_id,
            "speaker_code": "SPK001",
            "session_id": "SESSION001",
            "script_id": "SCRIPT001",
            "repetition_index": repetition,
            "device_code": device,
            "environment_code": "QUIET_ROOM",
            "recording_condition": condition,
            "processing_status": status,
            "exclusion_reasons": [],
            "pitch_median_hz": pitch,
            "pitch_range_semitones": 4.0,
            "validated_pitch_voiced_coverage_ratio": coverage,
            "dual_estimator_joint_valid_voiced_ratio": coverage,
            "harmonic_ambiguity_ratio": harmonic,
            "clipping_frame_ratio": 0.0,
            "snr_proxy_db": 25.0,
            "reliability_status": reliability,
        }

    def test_empty_manifest_creation(self) -> None:
        self.assertEqual(dataset.read_manifest(self.manifest), [])
        payload = json.loads(self.manifest.with_suffix(".json").read_text())
        self.assertEqual(payload["samples"], [])

    def test_csv_has_utf8_bom(self) -> None:
        self.assertTrue(self.manifest.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_json_uses_strict_parsing(self) -> None:
        bad = self.directory / "bad.json"
        bad.write_text('{"samples":[NaN]}', encoding="utf-8")
        with self.assertRaises(dataset.ProsodyDatasetError):
            dataset.read_manifest(bad)

    def test_normal_sample_registration(self) -> None:
        record = self.register()
        self.assertEqual(record["sample_id"], "SAMPLE001")
        self.assertEqual(len(dataset.read_manifest(self.manifest)), 1)
        self.assertEqual(
            len(dataset.read_manifest(self.manifest.with_suffix(".json"))), 1
        )

    def test_duplicate_sample_id_is_rejected(self) -> None:
        self.register()
        with self.assertRaisesRegex(dataset.ProsodyDatasetError, "SAMPLE001"):
            self.register(device="DEV2")

    def test_duplicate_composite_key_is_rejected(self) -> None:
        self.register()
        with self.assertRaises(dataset.ProsodyDatasetError) as raised:
            self.register(sample_id="SAMPLE002")
        self.assertEqual(raised.exception.code, "DUPLICATE_COMPOSITE_KEY")

    def test_invalid_condition_is_rejected(self) -> None:
        with self.assertRaises(dataset.ProsodyDatasetError) as raised:
            self.register(condition="invalid")
        self.assertEqual(raised.exception.code, "INVALID_RECORDING_CONDITION")

    def test_unconfirmed_consent_is_excluded(self) -> None:
        record = self.register(consent=False)
        self.assertEqual(record["processing_status"], "excluded")
        self.assertIn("consent_not_confirmed", record["exclusion_reasons"])

    def test_missing_wav(self) -> None:
        self.wav.unlink()
        record = self.register()
        self.assertEqual(record["processing_status"], "artifacts_missing")
        self.assertIn("wav_missing", record["exclusion_reasons"])

    def test_missing_stt_json(self) -> None:
        self.stt.unlink()
        record = self.register()
        self.assertIn("stt_missing", record["exclusion_reasons"])

    def test_missing_metrics_json(self) -> None:
        self.metrics.unlink()
        record = self.register()
        self.assertIn("quality_metrics_missing", record["exclusion_reasons"])

    def test_missing_prosody_json(self) -> None:
        self.prosody.unlink()
        record = self.register()
        self.assertIn("prosody_missing", record["exclusion_reasons"])

    def test_prosody_schema_must_be_v21(self) -> None:
        self.write_artifacts(schema="2.0")
        record = self.register()
        self.assertEqual(record["processing_status"], "analysis_failed")
        self.assertIn("unsupported_schema", record["exclusion_reasons"])

    def test_prosody_error_is_detected(self) -> None:
        self.write_artifacts(prosody_error={"code": "FAILED"})
        record = self.register()
        self.assertIn("prosody_error", record["exclusion_reasons"])

    def test_sha256_values_are_saved(self) -> None:
        record = self.register()
        self.assertEqual(record["wav_sha256"], dataset.sha256_file(self.wav))
        self.assertEqual(
            record["prosody_v21_json_sha256"],
            dataset.sha256_file(self.prosody),
        )

    def test_hash_mismatch_excludes_benchmark_sample(self) -> None:
        self.register()
        self.wav.write_bytes(b"changed")
        result = dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        sample = result["sample_results"][0]
        self.assertEqual(sample["processing_status"], "excluded")
        self.assertIn("hash_mismatch", sample["exclusion_reasons"])

    def test_ready_status(self) -> None:
        record = self.register()
        self.assertEqual(record["processing_status"], "ready_for_benchmark")

    def test_excluded_status_in_benchmark(self) -> None:
        self.register(consent=False)
        result = dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        self.assertEqual(result["dataset_summary"]["excluded_samples"], 1)

    def test_missing_prosody_field_remains_null(self) -> None:
        payload = json.loads(self.prosody.read_text())
        del payload["validated_pitch_summary"]["pitch_median_hz"]
        self.prosody.write_text(json.dumps(payload), encoding="utf-8")
        self.register()
        result = dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        self.assertIsNone(result["sample_results"][0]["pitch_median_hz"])

    def test_repeatability_group_is_created(self) -> None:
        samples = [
            self.result_sample("S1", repetition=1),
            self.result_sample("S2", repetition=2, pitch=102.0),
        ]
        groups = dataset.build_repeatability_groups(samples)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["sample_count"], 2)

    def test_one_repetition_has_no_group(self) -> None:
        self.assertEqual(
            dataset.build_repeatability_groups([self.result_sample("S1")]),
            [],
        )

    def test_median(self) -> None:
        center, _ = dataset.median_mad([100, 101, 200])
        self.assertEqual(center, 101.0)

    def test_mad(self) -> None:
        _, deviation = dataset.median_mad([100, 101, 200])
        self.assertEqual(deviation, 1.0)

    def test_relative_mad(self) -> None:
        samples = [
            self.result_sample("S1", repetition=1, pitch=100),
            self.result_sample("S2", repetition=2, pitch=102),
            self.result_sample("S3", repetition=3, pitch=101),
        ]
        group = dataset.build_repeatability_groups(samples)[0]
        self.assertEqual(group["pitch_median_relative_mad"], 0.009901)

    def test_device_comparison_group(self) -> None:
        samples = [
            self.result_sample("S1", device="DEV1", pitch=100),
            self.result_sample("S2", device="DEV2", pitch=110),
        ]
        group = dataset.build_device_comparison_groups(samples)[0]
        self.assertEqual(group["device_count"], 2)
        self.assertEqual(group["pitch_median_max_difference_hz"], 10.0)

    def test_one_device_has_no_comparison(self) -> None:
        self.assertEqual(
            dataset.build_device_comparison_groups(
                [self.result_sample("S1")]
            ),
            [],
        )

    def test_condition_aggregation(self) -> None:
        samples = [
            self.result_sample("S1", condition="clean", coverage=0.5),
            self.result_sample("S2", condition="clean", coverage=0.7),
            self.result_sample("S3", condition="slow", coverage=0.4),
        ]
        summary = dataset.build_condition_summary(samples)
        self.assertEqual(summary["clean"]["sample_count"], 2)
        self.assertEqual(summary["clean"]["pitch_voiced_coverage_median"], 0.6)

    def test_reliability_status_aggregation(self) -> None:
        samples = [
            self.result_sample("S1", reliability="limited"),
            self.result_sample("S2", reliability="unreliable"),
        ]
        summary = dataset.build_condition_summary(samples)["clean"]
        self.assertEqual(summary["reliability_status_counts"]["limited"], 1)
        self.assertEqual(summary["reliability_status_counts"]["unreliable"], 1)

    def test_prohibited_personal_field_is_rejected(self) -> None:
        sample = self.sample()
        sample["email"] = "not-allowed@example.invalid"
        with self.assertRaises(dataset.ProsodyDatasetError) as raised:
            dataset.register_sample(
                self.manifest, sample, workspace_root=self.directory
            )
        self.assertEqual(raised.exception.code, "PROHIBITED_PERSONAL_FIELD")

    def test_original_artifact_sha256_is_preserved(self) -> None:
        paths = [self.wav, self.stt, self.metrics, self.prosody]
        before = {path: dataset.sha256_file(path) for path in paths}
        self.register()
        dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        after = {path: dataset.sha256_file(path) for path in paths}
        self.assertEqual(before, after)

    def test_manifest_save_is_atomic(self) -> None:
        self.register()
        self.assertFalse((self.directory / ".manifest.csv.tmp").exists())
        self.assertFalse((self.directory / ".manifest.json.tmp").exists())

    def test_benchmark_json_is_strict(self) -> None:
        self.register()
        result = dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        text = dataset.strict_json_text(result)
        loaded = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(token)
            ),
        )
        self.assertIsNone(loaded["error"])

    def test_benchmark_csv_column_order(self) -> None:
        self.register()
        result = dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        output_json = self.directory / "benchmark.json"
        output_csv = self.directory / "benchmark.csv"
        sample_csv = self.directory / "samples.csv"
        dataset.write_benchmark_outputs(
            result, output_json, output_csv, sample_csv
        )
        with output_csv.open(encoding="utf-8", newline="") as stream:
            self.assertEqual(
                tuple(next(csv.reader(stream))),
                dataset.BENCHMARK_CSV_FIELDS,
            )

    def test_sample_csv_column_order(self) -> None:
        self.register()
        result = dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        output_json = self.directory / "benchmark.json"
        output_csv = self.directory / "benchmark.csv"
        sample_csv = self.directory / "samples.csv"
        dataset.write_benchmark_outputs(
            result, output_json, output_csv, sample_csv
        )
        with sample_csv.open(encoding="utf-8", newline="") as stream:
            self.assertEqual(
                tuple(next(csv.reader(stream))),
                dataset.SAMPLE_RESULT_FIELDS,
            )

    def test_create_cli_exit_codes_zero_one_two(self) -> None:
        output = self.directory / "created.csv"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = create_cli.main(["--output", str(output)])
            failure = create_cli.main(
                ["--output", str(self.directory / "bad.txt")]
            )
            with self.assertRaises(SystemExit) as raised:
                create_cli.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))

    def test_register_cli_exit_codes_zero_one_two(self) -> None:
        args = [
            str(self.manifest),
            "--sample-id",
            "CLI001",
            "--speaker-code",
            "SPK001",
            "--session-id",
            "SESSION001",
            "--script-id",
            "SCRIPT001",
            "--repetition-index",
            "1",
            "--device-code",
            "DEV1",
            "--environment-code",
            "QUIET_ROOM",
            "--recording-condition",
            "clean",
            "--wav",
            str(self.wav),
            "--stt-json",
            str(self.stt),
            "--speech-metrics-json",
            str(self.metrics),
            "--prosody-v21-json",
            str(self.prosody),
            "--consent-confirmed",
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = register_cli.main(args)
            failure = register_cli.main(args)
            with self.assertRaises(SystemExit) as raised:
                register_cli.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))

    def test_benchmark_cli_exit_codes_zero_one_two(self) -> None:
        self.register()
        args = [
            str(self.manifest),
            "--output-json",
            str(self.directory / "out.json"),
            "--output-csv",
            str(self.directory / "out.csv"),
            "--sample-output-csv",
            str(self.directory / "samples.csv"),
        ]
        bad = list(args)
        bad[0] = str(self.directory / "missing.csv")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = benchmark_cli.main(args)
            failure = benchmark_cli.main(bad)
            with self.assertRaises(SystemExit) as raised:
                benchmark_cli.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))

    def test_paths_are_stored_relative_to_workspace(self) -> None:
        record = self.register()
        self.assertFalse(Path(record["wav_path"]).is_absolute())

    def test_json_manifest_can_be_benchmarked(self) -> None:
        self.register()
        result = dataset.benchmark_dataset(
            self.manifest.with_suffix(".json"),
            workspace_root=self.directory,
        )
        self.assertEqual(result["dataset_summary"]["ready_samples"], 1)

    def test_limitations_are_included(self) -> None:
        result = dataset.benchmark_dataset(
            self.manifest, workspace_root=self.directory
        )
        self.assertEqual(result["limitations"], dataset.LIMITATIONS)

    def test_existing_prosody_versions_remain_unchanged(self) -> None:
        for relative, expected in self.IMMUTABLE_HASHES.items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
