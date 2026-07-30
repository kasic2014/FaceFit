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

import build_session_validation_report as report  # noqa: E402


class BuildSessionValidationReportTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "reports"
        self._create_collections()
        self._create_inputs()

    def write_json(self, relative: str, payload: dict) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def write_csv(
        self, relative: str, rows: list[dict], fields: list[str]
    ) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def _create_collections(self) -> None:
        groups = (
            (
                "data/prosody_validation/recordings/SESSION001/original/pc",
                ".m4a",
            ),
            (
                "data/prosody_validation/recordings/SESSION001/standard/pc",
                ".wav",
            ),
            (
                "data/output/prosody_validation/stt/SESSION001/pc",
                ".json",
            ),
            (
                "data/output/prosody_validation/speech_metrics/SESSION001/pc",
                ".json",
            ),
        )
        for directory, extension in groups:
            target = self.root / directory
            target.mkdir(parents=True, exist_ok=True)
            for index in range(24):
                (target / f"sample_{index:02d}{extension}").write_bytes(
                    f"{directory}:{index}".encode()
                )
        for relative in report.CORE_PATHS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"frozen:{relative}\n", encoding="utf-8")

    def _create_inputs(self) -> None:
        p = report.INPUT_PATHS
        self.write_json(
            p["recording_inventory"],
            {
                "total_files": 24,
                "pc_files": 12,
                "phone_files": 12,
                "validation_summary": {"errors": []},
                "error": None,
            },
        )
        self.write_json(
            p["conversion_manifest"],
            {
                "mapping_summary": {
                    "mapped_total": 24,
                    "unmatched": 0,
                    "ambiguous": 0,
                },
                "conversion_summary": {
                    "total": 24,
                    "converted": 24,
                    "failed_total": 0,
                    "warning_count": 2,
                    "pc_standard_wav_count": 12,
                    "phone_standard_wav_count": 12,
                },
                "error": None,
            },
        )
        self.write_json(
            p["stt_batch_manifest"],
            {
                "summary": {
                    "total_files": 24,
                    "successful_files": 24,
                    "failed_files": 0,
                    "median_real_time_factor": 0.04,
                    "max_real_time_factor": 0.06,
                    "timestamp_warning_count": 0,
                    "duration_validation_warning_count": 2,
                },
                "error": None,
            },
        )
        self.write_json(
            p["stt_evaluation"],
            {
                "summary": {
                    "evaluated_clean_files": 12,
                    "clean_cer_median": 0.04,
                    "clean_cer_mad": 0.02,
                    "clean_eojeol_error_rate_median": 0.03,
                    "clean_eojeol_error_rate_mad": 0.01,
                    "clean_exact_match_count": 5,
                    "clean_by_device": {
                        "DEV_PC_MIC_01": {"cer_median": 0.04},
                        "DEV_PHONE_01": {"cer_median": 0.02},
                    },
                    "total_pairs": 12,
                    "valid_pairs": 12,
                    "exact_normalized_match_pairs": 9,
                },
                "error": None,
            },
        )
        self.write_json(
            p["natural_stt_evaluation"],
            {
                "summary": {
                    "evaluated_capture_count": 6,
                    "evaluated_audio_file_count": 12,
                    "pc_cer_median": 0.0,
                    "pc_cer_mad": 0.0,
                    "phone_cer_median": 0.005,
                    "phone_cer_mad": 0.005,
                    "pc_eojeol_error_rate_median": 0.0,
                    "pc_eojeol_error_rate_mad": 0.0,
                    "phone_eojeol_error_rate_median": 0.014,
                    "phone_eojeol_error_rate_mad": 0.014,
                    "exact_match_audio_file_count": 7,
                    "incomplete_transcript_count": 0,
                },
                "error": None,
            },
        )
        self.write_csv(
            p["stt_device_pair_comparison"],
            [{"capture_pair_key": f"pair-{index}"} for index in range(12)],
            ["capture_pair_key"],
        )
        self.write_json(
            p["speech_metrics_summary"],
            {
                "summary": {
                    "total_files": 24,
                    "successful_files": 24,
                    "failed_files": 0,
                    "files_with_long_pause": 0,
                    "files_with_probable_vocalization": 16,
                    "files_with_uncertain_candidate": 1,
                    "files_with_background_noise_warning": 0,
                    "files_with_clipping_warning": 0,
                    "speech_rate_median_by_device": {
                        "DEV_PC_MIC_01": 169.1,
                        "DEV_PHONE_01": 170.4,
                    },
                    "pause_duration_median_by_device": {
                        "DEV_PC_MIC_01": 1.03,
                        "DEV_PHONE_01": 1.16,
                    },
                    "pair_difference_median": {
                        "speech_rate_wpm": 3.68,
                        "pause_count": 0.0,
                    },
                },
                "repeatability": [],
                "error": None,
            },
        )
        metrics = [
            "audio_duration_sec",
            "speech_duration_sec",
            "speaking_ratio",
            "speech_rate_wpm",
            "pause_count",
            "total_pause_duration_sec",
            "max_pause_duration_sec",
            "long_pause_count",
            "probable_omitted_vocalization_count",
            "uncertain_gap_vocalization_count",
            "clipping_ratio",
            "noise_floor_dbfs",
        ]
        pair_rows = []
        for index in range(12):
            for metric in metrics:
                pair_rows.append(
                    {
                        "capture_pair_key": f"pair-{index}",
                        "metric": metric,
                        "pc_value": 1 + index / 10,
                        "phone_value": 2 + index / 10,
                    }
                )
        self.write_csv(
            p["speech_metrics_pair_comparison"],
            pair_rows,
            ["capture_pair_key", "metric", "pc_value", "phone_value"],
        )
        self.write_json(
            p["human_annotation_comparison"],
            {
                "annotation_counts": {
                    "omission": 2,
                    "silence": 1,
                    "elongation": 2,
                    "filler": 0,
                },
                "silence_validation": {
                    "validation_status": "not_detected",
                    "accuracy_or_recall_computed": False,
                },
                "elongation_diagnostics": [
                    {
                        "target": "저장",
                        "validation_status": "duration_outlier_candidate",
                    },
                    {
                        "target": "데이터가",
                        "validation_status": "duration_not_outlier",
                    },
                ],
                "interpretation": {},
                "error": None,
            },
        )
        self.write_json(
            p["prosody_v21_summary"],
            {
                "summary": {
                    "total_files": 24,
                    "successful_files": 24,
                    "failed_files": 0,
                    "median_pitch_by_device": {
                        "DEV_PC_MIC_01": {"median": 206.8, "mad": 3.6},
                        "DEV_PHONE_01": {"median": 204.7, "mad": 3.9},
                    },
                    "median_pitch_range_by_device": {
                        "DEV_PC_MIC_01": {"median": 7.3, "mad": 0.8},
                        "DEV_PHONE_01": {"median": 7.4, "mad": 0.8},
                    },
                    "median_coverage_by_device": {
                        "DEV_PC_MIC_01": {"median": 0.33, "mad": 0.02},
                        "DEV_PHONE_01": {"median": 0.31, "mad": 0.04},
                    },
                    "reliability_distribution": {
                        "overall": {
                            "sufficient_for_experimental_summary": 2,
                            "limited": 12,
                            "unreliable": 10,
                            "analysis_failed": 0,
                        }
                    },
                    "estimator_status_totals": {
                        "agree_frame_count": 100,
                        "disagree_frame_count": 2,
                    },
                    "median_pair_pitch_difference_hz": {
                        "median": 1.4,
                        "mad": 0.7,
                    },
                    "median_pair_pitch_difference_semitones": {
                        "median": 0.11,
                        "mad": 0.06,
                    },
                    "median_pair_pitch_range_difference": {
                        "median": 0.44,
                        "mad": 0.27,
                    },
                    "files_with_shared_octave_harmonic_risk": 22,
                    "files_with_low_coverage": 2,
                    "files_with_clipping": 0,
                    "files_with_background_noise": 0,
                },
                "error": None,
            },
        )
        self.write_csv(
            p["prosody_v21_pair_comparison"],
            [
                {
                    "capture_pair_key": f"pair-{index}",
                    "pair_comparison_status": (
                        "pc_reliable_phone_limited"
                        if index == 0
                        else "phone_reliable_pc_limited"
                        if index == 1
                        else "both_limited"
                    ),
                }
                for index in range(12)
            ],
            ["capture_pair_key", "pair_comparison_status"],
        )
        repeat_rows = []
        for script in ("SCRIPT001", "SCRIPT002"):
            for condition in ("clean", "natural"):
                for device in ("DEV_PC_MIC_01", "DEV_PHONE_01"):
                    repeat_rows.append(
                        {
                            "script_id": script,
                            "recording_condition": condition,
                            "device_code": device,
                            "pitch_median_hz_all_median": 200,
                            "pitch_median_hz_all_mad": 2,
                            "reliable_repetition_count": (
                                1
                                if script == "SCRIPT002"
                                and condition == "natural"
                                else 0
                            ),
                        }
                    )
        self.write_csv(
            p["prosody_v21_repeatability"],
            repeat_rows,
            [
                "script_id",
                "recording_condition",
                "device_code",
                "pitch_median_hz_all_median",
                "pitch_median_hz_all_mad",
                "reliable_repetition_count",
            ],
        )
        self.write_json(
            p["prosody_v21_quality_diagnostics"],
            {
                "cause_counts": {
                    "shared_octave_harmonic_ambiguity": 22
                },
                "files": [],
                "error": None,
            },
        )

    def build(self) -> dict:
        return report.build_report(
            self.root,
            self.output,
            generated_at="2026-07-24T00:00:00+00:00",
        )

    def test_all_required_inputs_are_connected(self) -> None:
        result = self.build()
        self.assertEqual(len(result["input_artifacts"]), 13)
        self.assertEqual(
            {row["artifact_id"] for row in result["input_artifacts"]},
            set(report.INPUT_PATHS),
        )

    def test_missing_input_has_named_error(self) -> None:
        (self.root / report.INPUT_PATHS["stt_evaluation"]).unlink()
        with self.assertRaises(report.ValidationReportError) as raised:
            self.build()
        self.assertEqual(raised.exception.code, "REQUIRED_INPUT_NOT_FOUND")

    def test_pipeline_has_all_12_stages(self) -> None:
        stages = self.build()["pipeline_status"]
        self.assertEqual(len(stages), 12)

    def test_pipeline_status_values_are_valid(self) -> None:
        stages = self.build()["pipeline_status"]
        self.assertTrue(
            all(row["status"] in report.PIPELINE_STATES for row in stages)
        )

    def test_stt_key_metrics(self) -> None:
        stt = self.build()["results"]["stt"]
        self.assertEqual(stt["successful_files"], 24)
        self.assertEqual(stt["clean"]["cer_median"], 0.04)
        self.assertEqual(stt["natural"]["exact_match_audio_file_count"], 7)

    def test_speech_metrics_key_metrics(self) -> None:
        speech = self.build()["results"]["speech_metrics"]
        self.assertEqual(speech["successful_files"], 24)
        self.assertEqual(
            speech["speech_rate_voiced_duration_wpm_median_by_device"][
                "DEV_PC_MIC_01"
            ],
            169.1,
        )

    def test_prosody_key_metrics(self) -> None:
        prosody = self.build()["results"]["prosody_v21"]
        self.assertEqual(prosody["successful_files"], 24)
        self.assertEqual(
            prosody["pitch_median_by_device"]["DEV_PC_MIC_01"]["median"],
            206.8,
        )

    def test_human_annotation_aggregation(self) -> None:
        annotations = self.build()["results"]["human_annotations"]
        self.assertEqual(
            annotations["counts"],
            {"omission": 2, "silence": 1, "elongation": 2, "filler": 0},
        )
        self.assertEqual(annotations["silence_detection_status"], "not_detected")

    def test_readiness_has_at_least_21_metrics(self) -> None:
        self.assertGreaterEqual(len(self.build()["metric_readiness"]), 21)

    def test_pitch_scoring_is_forbidden(self) -> None:
        rows = self.build()["metric_readiness"]
        pitch = [row for row in rows if row["metric_id"].startswith("pitch_")]
        self.assertTrue(all(not row["scoring_eligible"] for row in pitch))
        self.assertTrue(all(not row["user_feedback_eligible"] for row in pitch))

    def test_confidence_feedback_is_prohibited(self) -> None:
        row = next(
            item
            for item in self.build()["metric_readiness"]
            if item["metric_id"] == "confidence"
        )
        self.assertEqual(row["validation_status"], "prohibited_for_feedback")
        self.assertFalse(row["user_feedback_eligible"])

    def test_emotion_feedback_is_prohibited(self) -> None:
        row = next(
            item
            for item in self.build()["metric_readiness"]
            if item["metric_id"] == "emotion"
        )
        self.assertEqual(row["validation_status"], "prohibited_for_feedback")

    def test_interview_score_is_prohibited(self) -> None:
        row = next(
            item
            for item in self.build()["metric_readiness"]
            if item["metric_id"] == "interview_speech_score"
        )
        self.assertEqual(row["validation_status"], "prohibited_for_feedback")
        self.assertFalse(row["scoring_eligible"])

    def test_all_metrics_are_not_scoring_eligible(self) -> None:
        self.assertTrue(
            all(
                not row["scoring_eligible"]
                for row in self.build()["metric_readiness"]
            )
        )

    def test_shared_octave_risk_is_reflected(self) -> None:
        prosody = self.build()["results"]["prosody_v21"]
        self.assertEqual(prosody["shared_octave_harmonic_risk_file_count"], 22)

    def test_no_both_reliable_pair_is_reflected(self) -> None:
        prosody = self.build()["results"]["prosody_v21"]
        self.assertEqual(prosody["both_reliable_pair_count"], 0)

    def test_known_limitations_are_created(self) -> None:
        result = self.build()
        limitations = result["known_limitations"]
        self.assertGreaterEqual(limitations["limitation_count"], 15)
        ids = {row["limitation_id"] for row in limitations["limitations"]}
        self.assertIn("no_external_pitch_ground_truth", ids)
        self.assertIn("human_silence_not_detected", ids)

    def test_baseline_checksums_are_created(self) -> None:
        self.build()
        path = self.output / "SESSION001_baseline_checksums.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["collections"]["original_m4a"]["file_count"], 24)
        self.assertEqual(payload["collections"]["prosody_v21_core"]["file_count"], 4)

    def test_major_artifact_checksums_include_13_inputs(self) -> None:
        self.build()
        payload = json.loads(
            (self.output / "SESSION001_baseline_checksums.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(len(payload["major_artifacts"]), 13)

    def test_markdown_has_14_required_sections(self) -> None:
        self.build()
        text = (self.output / "SESSION001_validation_report.md").read_text(
            encoding="utf-8"
        )
        for number in range(1, 15):
            self.assertIn(f"## {number}.", text)

    def test_strict_json_outputs(self) -> None:
        self.build()
        for path in self.output.glob("*.json"):
            with path.open(encoding="utf-8") as stream:
                json.load(
                    stream,
                    parse_constant=lambda token: self.fail(token),
                )

    def test_readiness_csv_has_utf8_bom(self) -> None:
        self.build()
        path = self.output / "SESSION001_metric_readiness.csv"
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with path.open(encoding="utf-8-sig", newline="") as stream:
            self.assertGreaterEqual(len(list(csv.DictReader(stream))), 21)

    def test_atomic_outputs_leave_no_temporary_files(self) -> None:
        self.build()
        self.assertEqual(list(self.output.rglob("*.tmp")), [])

    def test_exactly_five_output_files_are_created(self) -> None:
        self.build()
        self.assertEqual(len(list(self.output.iterdir())), 5)

    def test_required_input_hashes_are_preserved(self) -> None:
        paths = report.resolve_inputs(self.root)
        before = {name: report.sha256_file(path) for name, path in paths.items()}
        self.build()
        after = {name: report.sha256_file(path) for name, path in paths.items()}
        self.assertEqual(before, after)

    def test_analysis_is_not_rerun(self) -> None:
        result = self.build()
        self.assertEqual(
            result["analysis_rerun"],
            {
                "stt": False,
                "speech_metrics": False,
                "prosody_v21": False,
                "audio_conversion": False,
            },
        )
        source = (SCRIPTS / "build_session_validation_report.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("subprocess", source)
        self.assertNotIn("WhisperModel", source)

    def test_hallucination_count_is_not_invented(self) -> None:
        speech = self.build()["results"]["speech_metrics"]
        self.assertIsNone(speech["hallucination_candidate_count"])
        self.assertEqual(
            speech["hallucination_candidate_count_status"],
            "not_available_in_selected_aggregate_inputs",
        )

    def test_stage_2_and_stage_3_are_reported_without_plan_file(self) -> None:
        plan = self.build()["next_validation_plan"]
        self.assertEqual(plan["stage_2"]["actual_utterances"], 60)
        self.assertEqual(plan["stage_2"]["audio_files"], 120)
        self.assertFalse(plan["plan_file_created"])

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        args = [str(self.root), "--output-dir", str(self.output)]
        with redirect_stdout(io.StringIO()), mock.patch.object(
            report,
            "build_report",
            return_value={
                "session_id": "SESSION001",
                "pipeline_status": [],
                "metric_readiness": [],
            },
        ):
            success = report.main(args)
        with redirect_stdout(io.StringIO()), mock.patch.object(
            report,
            "build_report",
            side_effect=report.ValidationReportError("TEST", "failed"),
        ):
            failure = report.main(args)
        with redirect_stderr(io.StringIO()), self.assertRaises(
            SystemExit
        ) as raised:
            report.main([])
        self.assertEqual(success, 0)
        self.assertEqual(failure, 1)
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
