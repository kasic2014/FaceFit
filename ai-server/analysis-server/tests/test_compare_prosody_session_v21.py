from __future__ import annotations

import csv
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

import analyze_prosody_session_v21 as analyzer  # noqa: E402
import compare_prosody_session_v21 as compare  # noqa: E402


class CompareProsodySessionV21Tests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = self.root / "manifest.json"
        self.metrics_summary = self.root / "speech_summary.json"
        self.review = self.root / "review.csv"
        self.human_comparison = self.root / "human_comparison.json"
        self.summary_json = self.root / "out" / "summary.json"
        self.summary_csv = self.root / "out" / "summary.csv"
        self.pair_csv = self.root / "out" / "pairs.csv"
        self.repeat_csv = self.root / "out" / "repeat.csv"
        self.quality_json = self.root / "out" / "quality.json"
        self.quality_csv = self.root / "out" / "quality.csv"
        rows = []
        for script_index, script in enumerate(("SCRIPT001", "SCRIPT002")):
            for condition_index, condition in enumerate(("clean", "natural")):
                for repetition in (1, 2, 3):
                    for device in (analyzer.PC_DEVICE, analyzer.PHONE_DEVICE):
                        sample_id = (
                            f"SPK001_SESSION001_{script}_{device}_"
                            f"{condition}_R{repetition:02d}"
                        )
                        metadata = analyzer.parse_sample_id(sample_id)
                        device_offset = (
                            0.0 if device == analyzer.PC_DEVICE else 2.0
                        )
                        pitch = (
                            100.0
                            + script_index * 10
                            + condition_index * 5
                            + repetition
                            + device_offset
                        )
                        metrics = (
                            self.root / "metrics" / f"{sample_id}.json"
                        )
                        metrics.parent.mkdir(parents=True, exist_ok=True)
                        metrics.write_text(
                            json.dumps(
                                {
                                    "speech_rate_wpm": 120.0 + repetition,
                                    "speaking_ratio": 0.7,
                                    "total_pause_duration_sec": 1.0,
                                    "probable_omitted_vocalization_count": 0,
                                    "noise_floor_dbfs": -60.0,
                                }
                            ),
                            encoding="utf-8",
                        )
                        rows.append(
                            {
                                **metadata,
                                "speech_metrics_json_file": metrics.relative_to(
                                    self.root
                                ).as_posix(),
                                "pitch_median_hz": pitch,
                                "pitch_range_semitones": 3.0 + device_offset,
                                "pitch_std_semitones": 1.0 + repetition / 10,
                                "validated_overall_coverage": 0.6,
                                "validated_over_voiced_coverage": 0.8,
                                "conditioned_estimator_agreement": 0.9,
                                "agree_frame_count": 90,
                                "disagree_frame_count": 10,
                                "acf_only_frame_count": 5,
                                "yin_only_frame_count": 2,
                                "both_invalid_frame_count": 3,
                                "octave_correction_count": 1,
                                "unresolved_ambiguity_count": 0,
                                "low_pitch_coverage_warning": False,
                                "background_noise_warning": False,
                                "shared_octave_harmonic_risk": False,
                                "reliability_status": (
                                    "sufficient_for_experimental_summary"
                                ),
                                "internal_use_status": (
                                    "experimental_summary_eligible"
                                ),
                                "warnings": [],
                                "error": None,
                            }
                        )
        self.rows = rows
        self.write_manifest()
        self.metrics_summary.write_text(
            json.dumps({"summary": {"successful_files": 24}}),
            encoding="utf-8",
        )
        review_fields = (
            "capture_key",
            "script_id",
            "repetition_index",
            "human_transcript_note",
        )
        notes = {
            ("SCRIPT001", 1): "원래 대본 단어를 실제 발화에서 생략함.",
            ("SCRIPT001", 2): "두 표현 사이에 침묵 구간이 있음.",
            ("SCRIPT001", 3): "특이사항 없음.",
            ("SCRIPT002", 1): "앞부분을 생략함. '저장'의 발음이 길게 늘어짐.",
            ("SCRIPT002", 2): "특이사항 없음.",
            ("SCRIPT002", 3): "'데이터가'의 발음이 길게 늘어짐.",
        }
        with self.review.open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=review_fields)
            writer.writeheader()
            for script in ("SCRIPT001", "SCRIPT002"):
                for repetition in (1, 2, 3):
                    writer.writerow(
                        {
                            "capture_key": (
                                f"SPK001|SESSION001|{script}|natural|"
                                f"{repetition}"
                            ),
                            "script_id": script,
                            "repetition_index": repetition,
                            "human_transcript_note": notes[
                                (script, repetition)
                            ],
                        }
                    )
        self.human_comparison.write_text(
            json.dumps(
                {
                    "elongation_diagnostics": [
                        {
                            "capture_key": (
                                "SPK001|SESSION001|SCRIPT002|natural|1"
                            ),
                            "target": "저장",
                            "validation_status": "duration_outlier_candidate",
                        },
                        {
                            "capture_key": (
                                "SPK001|SESSION001|SCRIPT002|natural|3"
                            ),
                            "target": "데이터가",
                            "validation_status": "duration_not_outlier",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def write_manifest(self) -> None:
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "session_id": "SESSION001",
                    "files": self.rows,
                }
            ),
            encoding="utf-8",
        )

    def run_compare(self) -> dict:
        self.write_manifest()
        return compare.compare_session(
            self.manifest,
            self.metrics_summary,
            self.review,
            self.human_comparison,
            self.root,
            self.summary_json,
            self.summary_csv,
            self.pair_csv,
            self.repeat_csv,
            self.quality_json,
            self.quality_csv,
        )

    def test_builds_12_device_pairs(self) -> None:
        self.assertEqual(len(compare.build_pair_comparisons(self.rows)), 12)

    def test_pair_pitch_hz_difference(self) -> None:
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertEqual(pair["pitch_median_absolute_difference_hz"], 2.0)

    def test_pair_pitch_semitone_difference(self) -> None:
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertGreater(pair["pitch_median_difference_semitones"], 0)

    def test_pair_coverage_difference(self) -> None:
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertEqual(pair["coverage_absolute_difference"], 0.0)

    def test_pair_both_reliable_status(self) -> None:
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertEqual(pair["pair_comparison_status"], "both_reliable")

    def test_pair_pc_reliable_status(self) -> None:
        self.rows[1]["reliability_status"] = "limited"
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertEqual(
            pair["pair_comparison_status"], "pc_reliable_phone_limited"
        )

    def test_pair_phone_reliable_status(self) -> None:
        self.rows[0]["reliability_status"] = "unreliable"
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertEqual(
            pair["pair_comparison_status"], "phone_reliable_pc_limited"
        )

    def test_pair_both_limited_status(self) -> None:
        self.rows[0]["reliability_status"] = "limited"
        self.rows[1]["reliability_status"] = "unreliable"
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertEqual(pair["pair_comparison_status"], "both_limited")

    def test_pair_comparison_unavailable(self) -> None:
        self.rows[0]["pitch_median_hz"] = None
        pair = compare.build_pair_comparisons(self.rows)[0]
        self.assertEqual(
            pair["pair_comparison_status"], "comparison_unavailable"
        )

    def test_builds_8_repeatability_groups(self) -> None:
        self.assertEqual(len(compare.build_repeatability(self.rows)), 8)

    def test_repeatability_median(self) -> None:
        repeat = compare.build_repeatability(self.rows)[0]
        self.assertIsNotNone(repeat["pitch_median_hz_all_median"])

    def test_repeatability_mad(self) -> None:
        repeat = compare.build_repeatability(self.rows)[0]
        self.assertEqual(repeat["pitch_median_hz_all_mad"], 1.0)

    def test_repeatability_excludes_unreliable_from_reliable_stats(self) -> None:
        target = [
            row
            for row in self.rows
            if row["script_id"] == "SCRIPT001"
            and row["recording_condition"] == "clean"
            and row["device_code"] == analyzer.PC_DEVICE
        ]
        target[0]["reliability_status"] = "unreliable"
        repeat = next(
            row
            for row in compare.build_repeatability(self.rows)
            if row["script_id"] == "SCRIPT001"
            and row["recording_condition"] == "clean"
            and row["device_code"] == analyzer.PC_DEVICE
        )
        self.assertEqual(repeat["reliable_repetition_count"], 2)

    def test_shared_octave_harmonic_risk_is_counted(self) -> None:
        self.rows[0]["shared_octave_harmonic_risk"] = True
        result = self.run_compare()
        self.assertEqual(
            result["summary"]["files_with_shared_octave_harmonic_risk"], 1
        )

    def test_low_coverage_is_counted(self) -> None:
        self.rows[0]["low_pitch_coverage_warning"] = True
        result = self.run_compare()
        self.assertEqual(result["summary"]["files_with_low_coverage"], 1)

    def test_speech_metrics_are_joined_read_only(self) -> None:
        before = {
            path: path.read_bytes()
            for path in (self.root / "metrics").glob("*.json")
        }
        self.run_compare()
        quality = json.loads(self.quality_json.read_text(encoding="utf-8"))
        self.assertEqual(
            quality["files"][0]["speech_rate_voiced_duration_wpm"], 121.0
        )
        self.assertEqual(
            before,
            {
                path: path.read_bytes()
                for path in (self.root / "metrics").glob("*.json")
            },
        )

    def test_omission_is_not_linked_to_pitch(self) -> None:
        self.run_compare()
        quality = json.loads(self.quality_json.read_text(encoding="utf-8"))
        self.assertEqual(
            quality["human_annotation_context"]["interpretation_rules"][
                "omission"
            ],
            "Not a pitch-analysis target.",
        )

    def test_elongation_is_not_confirmed_by_pitch(self) -> None:
        self.run_compare()
        quality = json.loads(self.quality_json.read_text(encoding="utf-8"))
        references = quality["human_annotation_context"][
            "elongation_references"
        ]
        self.assertEqual(len(references), 2)
        self.assertTrue(all(not row["pitch_linked"] for row in references))

    def test_human_annotation_counts(self) -> None:
        result = self.run_compare()
        self.assertEqual(
            result["summary"]["human_annotation_counts"],
            {"omission": 2, "silence": 1, "elongation": 2, "filler": 0},
        )

    def test_summary_json_is_strict(self) -> None:
        self.run_compare()
        parsed = json.loads(
            self.summary_json.read_text(encoding="utf-8"),
            parse_constant=lambda token: self.fail(token),
        )
        self.assertEqual(parsed["prosody_schema_version"], "2.1")

    def test_all_csv_outputs_have_utf8_bom(self) -> None:
        self.run_compare()
        for path in (
            self.summary_csv,
            self.pair_csv,
            self.repeat_csv,
            self.quality_csv,
        ):
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"), path)

    def test_atomic_writes_leave_no_temporary_files(self) -> None:
        self.run_compare()
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_incomplete_device_pair_has_named_error(self) -> None:
        with self.assertRaises(
            analyzer.SessionProsodyV21Error
        ) as raised:
            compare.build_pair_comparisons(self.rows[:-1])
        self.assertEqual(raised.exception.code, "DEVICE_PAIR_INCOMPLETE")

    def test_summary_warns_estimator_agreement_is_not_accuracy(self) -> None:
        result = self.run_compare()
        self.assertTrue(
            any("Estimator agreement" in item for item in result["limitations"])
        )

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        arguments = [
            "--manifest",
            "a",
            "--speech-metrics-summary",
            "b",
            "--human-review",
            "c",
            "--human-annotation-comparison",
            "d",
            "--relative-root",
            "e",
            "--summary-json-output",
            "f",
            "--summary-csv-output",
            "g",
            "--pair-csv-output",
            "h",
            "--repeatability-csv-output",
            "i",
            "--quality-json-output",
            "j",
            "--quality-csv-output",
            "k",
        ]
        with redirect_stdout(io.StringIO()), mock.patch.object(
            compare,
            "compare_session",
            return_value={"summary": {}, "error": None},
        ):
            success = compare.main(arguments)
        with redirect_stdout(io.StringIO()), mock.patch.object(
            compare,
            "compare_session",
            side_effect=analyzer.SessionProsodyV21Error(
                "SESSION_PROSODY_V21_FAILED", "failed"
            ),
        ):
            failure = compare.main(arguments)
        with redirect_stderr(io.StringIO()), self.assertRaises(
            SystemExit
        ) as raised:
            compare.main([])
        self.assertEqual(success, 0)
        self.assertEqual(failure, 1)
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
