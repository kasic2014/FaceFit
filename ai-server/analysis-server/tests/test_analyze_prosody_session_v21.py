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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import analyze_prosody_session_v21 as session  # noqa: E402


class AnalyzeProsodySessionV21Tests(unittest.TestCase):
    CORE_HASHES = {
        "app/speech/prosody_metrics.py": (
            "b66a0539e53e64dbfe94328bbcd5ac7f6f20b6b7e30eace8f09a664c9144eff8"
        ),
        "app/speech/prosody_validation.py": (
            "422d7c224d2ee80265ab3aa542229c8ac314abd74600acacb3ba200119caf48c"
        ),
        "app/speech/prosody_validation_v21.py": (
            "c95e22a0d1e77f4ba1a994ce74650d5481e675e1db632a05f1735a1f4e0e5663"
        ),
        "scripts/analyze_speech_prosody_v21.py": (
            "5aee0077d57c1cd6e3aa9e797f6b7db089a40e95dc0c5b86eddd85a5ecd2bfda"
        ),
    }

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stt_pc = self.root / "stt" / "pc"
        self.stt_phone = self.root / "stt" / "phone"
        self.metrics_pc = self.root / "metrics" / "pc"
        self.metrics_phone = self.root / "metrics" / "phone"
        self.output_pc = self.root / "output" / "pc"
        self.output_phone = self.root / "output" / "phone"
        self.manifest_json = self.root / "evaluation" / "manifest.json"
        self.manifest_csv = self.root / "evaluation" / "manifest.csv"
        self.conversion_manifest = self.root / "conversion.json"
        for directory in (
            self.stt_pc,
            self.stt_phone,
            self.metrics_pc,
            self.metrics_phone,
        ):
            directory.mkdir(parents=True)
        conversions = []
        for script in ("SCRIPT001", "SCRIPT002"):
            for condition in ("clean", "natural"):
                for repetition in (1, 2, 3):
                    for device in (session.PC_DEVICE, session.PHONE_DEVICE):
                        sample_id = (
                            f"SPK001_SESSION001_{script}_{device}_"
                            f"{condition}_R{repetition:02d}"
                        )
                        device_dir = (
                            "pc" if device == session.PC_DEVICE else "phone"
                        )
                        audio = (
                            self.root
                            / "standard"
                            / device_dir
                            / f"{sample_id}.wav"
                        )
                        audio.parent.mkdir(parents=True, exist_ok=True)
                        audio.write_bytes(f"audio:{sample_id}".encode())
                        metadata = session.parse_sample_id(sample_id)
                        stt_dir = (
                            self.stt_pc
                            if device == session.PC_DEVICE
                            else self.stt_phone
                        )
                        metrics_dir = (
                            self.metrics_pc
                            if device == session.PC_DEVICE
                            else self.metrics_phone
                        )
                        (stt_dir / f"{sample_id}.json").write_text(
                            json.dumps({**metadata, "error": None}),
                            encoding="utf-8",
                        )
                        (metrics_dir / f"{sample_id}.json").write_text(
                            json.dumps({"audio_quality": {}, "error": None}),
                            encoding="utf-8",
                        )
                        conversions.append(
                            {
                                "sample_id": sample_id,
                                "device_code": device,
                                "destination_path": audio.relative_to(
                                    self.root
                                ).as_posix(),
                                "destination_sha256": session.sha256_file(
                                    audio
                                ),
                            }
                        )
        self.conversion_manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "session_id": "SESSION001",
                    "conversions": conversions,
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def fake_result(*_args, **_kwargs) -> dict:
        return {
            "schema_version": "2.1",
            "audio_duration_sec": 10.0,
            "configuration": {},
            "coverage_summary": {
                "total_analysis_frame_count": 3,
                "acoustic_voiced_frame_count": 2,
                "both_estimators_valid_frame_count": 2,
                "validated_pitch_frame_count": 2,
                "validated_pitch_overall_coverage_ratio": 2 / 3,
                "validated_pitch_voiced_coverage_ratio": 1.0,
                "dual_estimator_joint_valid_voiced_ratio": 1.0,
            },
            "agreement_summary": {
                "estimator_agreement_ratio_conditioned_on_joint_valid": 1.0,
            },
            "dual_estimator_status": {
                "both_valid_agree": 2,
                "both_valid_disagree": 0,
                "autocorrelation_only": 0,
                "yin_only": 0,
                "both_invalid": 1,
            },
            "harmonic_support_summary": {
                "harmonic_ambiguity_ratio": 0.1
            },
            "shared_failure_diagnostics": {
                "background_noise_suspected": False,
                "low_joint_valid_coverage": False,
                "low_validated_voiced_coverage": False,
                "shared_octave_error_risk": False,
                "harmonic_ambiguity_risk": False,
                "risk_flags": [],
            },
            "analysis_reliability_level": (
                "sufficient_for_experimental_summary"
            ),
            "raw_pitch_summary": {},
            "validated_pitch_summary": {
                "pitch_median_hz": 105.0,
                "pitch_range_semitones": 2.0,
            },
            "correction_summary": {
                "octave_halving_corrections": 1,
                "octave_doubling_corrections": 0,
                "unresolved_frame_count": 0,
            },
            "loudness_summary": {"clipping_frame_ratio": 0.0},
            "segment_prosody": [
                {
                    "ending_intonation": {
                        "ending_pattern": "level",
                        "ending_pitch_change_semitones": 0.2,
                    }
                }
            ],
            "prosody_reliability": {},
            "frames": [
                {"valid": True, "corrected_f0_hz": 100.0},
                {"valid": True, "corrected_f0_hz": 110.0},
                {"valid": False, "corrected_f0_hz": None},
            ],
            "warnings": [],
            "error": None,
        }

    def run_session(self, analyzer=None) -> dict:
        return session.analyze_session(
            self.conversion_manifest,
            self.stt_pc,
            self.stt_phone,
            self.metrics_pc,
            self.metrics_phone,
            self.output_pc,
            self.output_phone,
            self.manifest_json,
            self.manifest_csv,
            self.root,
            analyzer=analyzer or self.fake_result,
        )

    def test_connects_24_standard_wavs(self) -> None:
        self.assertEqual(self.run_session()["summary"]["total_files"], 24)

    def test_counts_12_pc_files(self) -> None:
        self.assertEqual(self.run_session()["summary"]["pc_files"], 12)

    def test_counts_12_phone_files(self) -> None:
        self.assertEqual(self.run_session()["summary"]["phone_files"], 12)

    def test_counts_12_clean_files(self) -> None:
        self.assertEqual(self.run_session()["summary"]["clean_files"], 12)

    def test_counts_12_natural_files(self) -> None:
        self.assertEqual(self.run_session()["summary"]["natural_files"], 12)

    def test_creates_one_v21_result_per_file(self) -> None:
        self.run_session()
        self.assertEqual(
            len(list((self.root / "output").rglob("*.json"))), 24
        )

    def test_saved_results_retain_schema_21(self) -> None:
        self.run_session()
        saved = json.loads(next(self.output_pc.glob("*.json")).read_text())
        self.assertEqual(saved["schema_version"], "2.1")
        self.assertEqual(saved["frames"], [])

    def test_pitch_median_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(row["pitch_median_hz"], 105.0)

    def test_pitch_range_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(row["pitch_range_semitones"], 2.0)

    def test_validated_overall_coverage_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertAlmostEqual(row["validated_overall_coverage"], 2 / 3)

    def test_validated_over_voiced_coverage_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(row["validated_over_voiced_coverage"], 1.0)

    def test_joint_over_voiced_coverage_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(row["joint_over_voiced_coverage"], 1.0)

    def test_estimator_status_matrix_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(row["agree_frame_count"], 2)
        self.assertEqual(row["both_invalid_frame_count"], 1)

    def test_conditioned_agreement_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(row["conditioned_estimator_agreement"], 1.0)

    def test_reliability_status_is_manifested(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(
            row["reliability_status"],
            "sufficient_for_experimental_summary",
        )

    def test_internal_use_is_non_scoring_status(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(
            row["internal_use_status"], "experimental_summary_eligible"
        )

    def test_derived_pitch_extrema_and_std(self) -> None:
        row = self.run_session()["files"][0]
        self.assertEqual(row["pitch_min_hz"], 100.0)
        self.assertEqual(row["pitch_max_hz"], 110.0)
        self.assertGreater(row["pitch_std_semitones"], 0)
        self.assertEqual(
            row["intonation_variability"], row["pitch_std_semitones"]
        )

    def test_strict_json_rejects_nan(self) -> None:
        with self.assertRaises(ValueError):
            session.strict_json_text({"bad": float("nan")})

    def test_nested_session_quality_uses_temporary_read_only_view(self) -> None:
        source = self.root / "nested_metrics.json"
        source.write_text(
            json.dumps(
                {
                    "existing_speech_metrics": {
                        "audio_quality": {"voiced_threshold_dbfs": -40.0},
                        "error": None,
                    }
                }
            ),
            encoding="utf-8",
        )
        before = source.read_bytes()
        with session.core_quality_metrics_path(source) as compatibility:
            self.assertNotEqual(compatibility, source)
            payload = json.loads(compatibility.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["audio_quality"]["voiced_threshold_dbfs"], -40.0
            )
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse(compatibility.exists())

    def test_manifest_csv_has_utf8_bom(self) -> None:
        self.run_session()
        self.assertTrue(self.manifest_csv.read_bytes().startswith(b"\xef\xbb\xbf"))
        with self.manifest_csv.open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 24)

    def test_atomic_writes_leave_no_temporary_files(self) -> None:
        self.run_session()
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_standard_wav_stt_and_metrics_hashes_are_preserved(self) -> None:
        inputs = [
            *self.root.glob("standard/**/*.wav"),
            *self.root.glob("stt/**/*.json"),
            *self.root.glob("metrics/**/*.json"),
        ]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        self.run_session()
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        self.assertEqual(before, after)

    def test_frozen_core_sha256_is_preserved(self) -> None:
        for relative, expected in self.CORE_HASHES.items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_missing_standard_wav_returns_named_error(self) -> None:
        missing = next((self.root / "standard").rglob("*.wav"))
        missing.unlink()
        result = self.run_session()
        errors = [row["error"] for row in result["files"] if row["error"]]
        self.assertEqual(errors[0]["code"], "STANDARD_WAV_NOT_FOUND")
        self.assertEqual(result["summary"]["failed_files"], 1)

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        arguments = [
            "--conversion-manifest",
            "a",
            "--stt-pc-dir",
            "b",
            "--stt-phone-dir",
            "c",
            "--speech-metrics-pc-dir",
            "d",
            "--speech-metrics-phone-dir",
            "e",
            "--output-pc-dir",
            "f",
            "--output-phone-dir",
            "g",
            "--manifest-json-output",
            "h",
            "--manifest-csv-output",
            "i",
            "--relative-root",
            "j",
        ]
        with redirect_stdout(io.StringIO()), mock.patch.object(
            session,
            "analyze_session",
            return_value={
                "summary": {"failed_files": 0},
                "error": None,
            },
        ):
            success = session.main(arguments)
        with redirect_stdout(io.StringIO()), mock.patch.object(
            session,
            "analyze_session",
            side_effect=session.SessionProsodyV21Error(
                "SESSION_PROSODY_V21_FAILED", "failed"
            ),
        ):
            failure = session.main(arguments)
        with redirect_stderr(io.StringIO()), self.assertRaises(
            SystemExit
        ) as raised:
            session.main([])
        self.assertEqual(success, 0)
        self.assertEqual(failure, 1)
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
