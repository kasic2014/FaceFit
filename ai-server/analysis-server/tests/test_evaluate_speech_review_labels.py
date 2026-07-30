"""Tests for descriptive aggregation of human speech-review labels."""

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
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_speech_review_labels as evaluation  # noqa: E402


class EvaluateSpeechReviewLabelsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.manifest = self.directory / "reviewed.csv"

    @staticmethod
    def row(
        review_id: str,
        event_type: str,
        label: str,
        *,
        source_event_types: str | None = None,
        note: str = "",
    ) -> dict[str, str]:
        return {
            "review_id": review_id,
            "event_type": event_type,
            "source_event_types": source_event_types or event_type,
            "original_start_sec": "1.0",
            "original_end_sec": "1.5",
            "reviewer_label": label,
            "reviewer_note": note,
            "classification": "word_gap",
            "candidate_reasons": "test_reason",
            "audio_quality_flags": "",
        }

    def write_manifest(
        self, rows: list[dict[str, str]], *, bom: bool = True, path: Path | None = None
    ) -> Path:
        destination = path or self.manifest
        encoding = "utf-8-sig" if bom else "utf-8"
        with destination.open("w", encoding=encoding, newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=evaluation.REVIEW_ITEM_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return destination

    def evaluate(self, rows: list[dict[str, str]], *, bom: bool = True) -> dict:
        self.write_manifest(rows, bom=bom)
        return evaluation.evaluate_speech_review_labels(self.manifest)

    def completed_nine_rows(self) -> list[dict[str, str]]:
        rows = [
            self.row(
                "speech_04_fast_001",
                "probable_omitted_vocalization",
                "breath",
                source_event_types="probable_omitted_vocalization; pause",
            ),
            self.row(
                "speech_04_fast_002",
                "probable_omitted_vocalization",
                "breath",
                source_event_types="probable_omitted_vocalization; pause",
            ),
            self.row(
                "speech_05_slow_001",
                "probable_omitted_vocalization",
                "silence",
                source_event_types="probable_omitted_vocalization; pause",
            ),
            self.row(
                "speech_05_slow_002",
                "probable_omitted_vocalization",
                "breath",
                source_event_types="probable_omitted_vocalization; pause",
            ),
        ]
        rows.extend(
            self.row(
                f"speech_06_noise_{index:03d}",
                "uncertain_gap_vocalization",
                "noise",
                source_event_types="uncertain_gap_vocalization; pause",
            )
            for index in range(1, 5)
        )
        rows.append(self.row("speech_05_slow_003", "pause", "breath"))
        return rows

    def test_reads_utf8_bom_csv(self) -> None:
        result = self.evaluate([self.row("r1", "pause", "silence")], bom=True)
        self.assertIsNone(result["error"])
        self.assertEqual(result["reviewed_items"], 1)

    def test_reads_utf8_csv_without_bom(self) -> None:
        result = self.evaluate([self.row("r1", "pause", "silence")], bom=False)
        self.assertIsNone(result["error"])
        self.assertEqual(result["reviewed_items"], 1)

    def test_all_labels_completed(self) -> None:
        result = self.evaluate(
            [
                self.row("r1", "pause", "silence"),
                self.row("r2", "probable_omitted_vocalization", "filler"),
            ]
        )
        self.assertEqual(result["reviewed_items"], 2)
        self.assertEqual(result["unreviewed_items"], 0)
        self.assertEqual(result["review_completion_ratio"], 1.0)

    def test_some_labels_are_unreviewed(self) -> None:
        result = self.evaluate(
            [self.row("r1", "pause", "silence"), self.row("r2", "pause", "")]
        )
        self.assertEqual(result["reviewed_items"], 1)
        self.assertEqual(result["unreviewed_items"], 1)
        self.assertEqual(result["review_completion_ratio"], 0.5)

    def test_invalid_label_is_not_auto_corrected(self) -> None:
        result = self.evaluate([self.row("r1", "pause", "speech")])
        self.assertEqual(result["invalid_label_items"], 1)
        self.assertEqual(result["reviewed_items"], 0)
        self.assertEqual(result["review_items"][0]["reviewer_label"], "speech")
        self.assertEqual(result["warnings"][0]["code"], "INVALID_REVIEWER_LABEL")

    def test_probable_evaluation(self) -> None:
        labels = ["filler", "normal_speech", "breath", "noise", "unknown"]
        result = self.evaluate(
            [self.row(f"r{i}", "probable_omitted_vocalization", label) for i, label in enumerate(labels)]
        )
        probable = result["probable_evaluation"]
        self.assertEqual(probable["probable_total"], 5)
        self.assertEqual(probable["probable_filler_count"], 1)
        self.assertEqual(probable["probable_human_vocalization_ratio"], 0.6)
        self.assertEqual(probable["probable_noise_false_positive_ratio"], 0.2)
        self.assertIn("Experimental", probable["human_vocalization_definition"])

    def test_uncertain_evaluation(self) -> None:
        labels = ["noise", "noise", "filler", "unknown"]
        result = self.evaluate(
            [self.row(f"r{i}", "uncertain_gap_vocalization", label) for i, label in enumerate(labels)]
        )
        uncertain = result["uncertain_evaluation"]
        self.assertEqual(uncertain["uncertain_total"], 4)
        self.assertEqual(uncertain["uncertain_noise_count"], 2)
        self.assertEqual(uncertain["uncertain_noise_ratio"], 0.5)
        self.assertEqual(uncertain["uncertain_human_vocalization_ratio"], 0.25)

    def test_pause_evaluation(self) -> None:
        labels = ["silence", "breath", "normal_speech", "noise"]
        result = self.evaluate(
            [self.row(f"r{i}", "pause", label) for i, label in enumerate(labels)]
        )
        pause = result["pause_evaluation"]
        self.assertEqual(pause["pause_total"], 4)
        self.assertEqual(pause["pause_silence_count"], 1)
        self.assertEqual(pause["pause_correct_silence_ratio"], 0.25)

    def test_merged_review_item_is_counted_once_globally(self) -> None:
        result = self.evaluate(
            [
                self.row(
                    "r1",
                    "probable_omitted_vocalization",
                    "filler",
                    source_event_types="probable_omitted_vocalization; pause",
                )
            ]
        )
        self.assertEqual(result["total_items"], 1)
        self.assertEqual(result["reviewed_items"], 1)
        self.assertEqual(result["label_counts"]["filler"], 1)

    def test_source_event_types_are_used_for_event_aggregates(self) -> None:
        result = self.evaluate(
            [
                self.row(
                    "r1",
                    "probable_omitted_vocalization",
                    "silence",
                    source_event_types="probable_omitted_vocalization; pause",
                )
            ]
        )
        self.assertEqual(result["event_type_counts"]["probable_omitted_vocalization"], 1)
        self.assertEqual(result["event_type_counts"]["pause"], 1)
        self.assertEqual(result["pause_evaluation"]["pause_silence_count"], 1)

    def test_primary_event_and_source_membership_are_separate(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        self.assertEqual(
            result["primary_event_type_counts"],
            {
                "probable_omitted_vocalization": 4,
                "uncertain_gap_vocalization": 4,
                "pause": 1,
                "long_silence": 0,
                "hallucination_candidate": 0,
            },
        )
        self.assertEqual(result["source_event_membership_counts"]["pause"], 9)
        self.assertEqual(sum(result["primary_event_type_counts"].values()), 9)
        self.assertEqual(result["total_items"], 9)

    def test_primary_and_source_label_tables_are_separate(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        primary = result["primary_event_by_reviewer_label"]
        source = result["source_event_membership_by_reviewer_label"]
        self.assertEqual(primary["pause"]["breath"], 1)
        self.assertEqual(primary["pause"]["noise"], 0)
        self.assertEqual(source["pause"]["breath"], 4)
        self.assertEqual(source["pause"]["noise"], 4)
        self.assertEqual(source["pause"]["silence"], 1)

    def test_primary_pause_evaluation_uses_only_primary_pause(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        pause = result["primary_pause_evaluation"]
        self.assertEqual(pause["total"], 1)
        self.assertEqual(pause["reviewed"], 1)
        self.assertEqual(pause["silence_count"], 0)
        self.assertEqual(pause["breath_count"], 1)
        self.assertEqual(pause["silence_ratio"], 0.0)
        self.assertEqual(pause["breath_ratio"], 1.0)

    def test_pause_source_membership_distribution(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        pause = result["pause_source_membership_evaluation"]
        self.assertEqual(pause["item_count"], 9)
        self.assertEqual(pause["reviewed_item_count"], 9)
        self.assertEqual(pause["label_counts"]["breath"], 4)
        self.assertEqual(pause["label_counts"]["silence"], 1)
        self.assertEqual(pause["label_counts"]["noise"], 4)
        self.assertEqual(pause["silence_ratio"], 0.111111)
        self.assertEqual(pause["breath_ratio"], 0.444444)
        self.assertEqual(pause["noise_ratio"], 0.444444)

    def test_legacy_pause_metric_is_deprecated_with_replacements(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        self.assertEqual(
            result["pause_evaluation"]["pause_correct_silence_ratio"], 0.111111
        )
        deprecated = result["deprecated_metrics"]["pause_correct_silence_ratio"]
        self.assertTrue(deprecated["deprecated"])
        self.assertIn("deprecation_reason", deprecated)
        self.assertEqual(
            deprecated["replacement_metrics"],
            [
                "primary_pause_evaluation.silence_ratio",
                "pause_source_membership_evaluation.silence_ratio",
            ],
        )
        self.assertIn("source event membership", result["schema_notes"]["event_type_counts"])

    def test_probable_silence_ratio_is_explicit(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        probable = result["probable_evaluation"]
        self.assertEqual(probable["probable_filler_ratio"], 0.0)
        self.assertEqual(probable["probable_human_vocalization_ratio"], 0.75)
        self.assertEqual(probable["probable_silence_count"], 1)
        self.assertEqual(probable["probable_silence_ratio"], 0.25)
        self.assertEqual(probable["probable_noise_false_positive_ratio"], 0.0)

    def test_experiment_summary_records_findings_and_limitations(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        summary = result["experiment_summary"]
        self.assertEqual(summary["sample_size"], 9)
        self.assertEqual(summary["ground_truth_status"], "human_reviewed")
        self.assertFalse(summary["generalization_allowed"])
        self.assertTrue(any("breath 3개" in item for item in summary["findings"]))
        self.assertTrue(any("모두 noise" in item for item in summary["findings"]))
        self.assertIn("filler로 확인된 항목은 없음", summary["findings"])
        self.assertIn("단일 화자", summary["limitations"])
        self.assertIn("filler 정답 샘플이 검수 데이터에 없음", summary["limitations"])

    def test_csv_contains_v2_sections_and_replacement_paths(self) -> None:
        result = self.evaluate(self.completed_nine_rows())
        output = self.directory / "v2.csv"
        evaluation.write_csv_result(output, result)
        with output.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        sections = {row["section"] for row in rows}
        self.assertTrue(
            {
                "primary_event_type_counts",
                "source_event_membership_counts",
                "primary_event_by_reviewer_label",
                "source_event_membership_by_reviewer_label",
                "primary_pause_evaluation",
                "pause_source_membership_evaluation",
                "deprecated_metrics",
                "experiment_summary",
            }.issubset(sections)
        )
        replacement = next(
            row
            for row in rows
            if row["metric"]
            == "pause_correct_silence_ratio.replacement_metrics"
        )
        self.assertIn("primary_pause_evaluation.silence_ratio", replacement["value"])

    def test_v1_output_files_are_not_modified_by_v2_cli(self) -> None:
        self.write_manifest(self.completed_nine_rows())
        v1_json = self.directory / "speech_review_evaluation.json"
        v1_csv = self.directory / "speech_review_evaluation.csv"
        v1_json.write_bytes(b"preserve-json-v1")
        v1_csv.write_bytes(b"preserve-csv-v1")
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (v1_json, v1_csv)
        }
        with redirect_stdout(io.StringIO()):
            code = evaluation.main(
                [
                    str(self.manifest),
                    "--output",
                    str(self.directory / "speech_review_evaluation_v2.json"),
                    "--csv-output",
                    str(self.directory / "speech_review_evaluation_v2.csv"),
                ]
            )
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (v1_json, v1_csv)
        }
        self.assertEqual(code, 0)
        self.assertEqual(before, after)

    def test_duplicate_type_in_sources_is_not_double_counted(self) -> None:
        result = self.evaluate(
            [
                self.row(
                    "r1",
                    "pause",
                    "silence",
                    source_event_types="pause; pause",
                )
            ]
        )
        self.assertEqual(result["event_type_counts"]["pause"], 1)

    def test_zero_denominators_are_null(self) -> None:
        result = self.evaluate([])
        self.assertIsNone(result["review_completion_ratio"])
        self.assertIsNone(result["probable_evaluation"]["probable_filler_ratio"])
        self.assertIsNone(result["probable_evaluation"]["probable_silence_ratio"])
        self.assertIsNone(result["uncertain_evaluation"]["uncertain_noise_ratio"])
        self.assertIsNone(result["pause_evaluation"]["pause_correct_silence_ratio"])
        self.assertIsNone(result["primary_pause_evaluation"]["silence_ratio"])
        self.assertIsNone(result["primary_pause_evaluation"]["breath_ratio"])
        self.assertIsNone(
            result["pause_source_membership_evaluation"]["silence_ratio"]
        )

    def test_json_output_can_be_reloaded(self) -> None:
        result = self.evaluate([self.row("r1", "pause", "silence")])
        output = self.directory / "result.json"
        evaluation.write_json_result(output, result)
        loaded = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(loaded["pause_evaluation"]["pause_silence_count"], 1)
        self.assertNotIn("NaN", output.read_text(encoding="utf-8"))

    def test_csv_output_contains_aggregate_rows(self) -> None:
        result = self.evaluate([self.row("r1", "pause", "silence")])
        output = self.directory / "result.csv"
        evaluation.write_csv_result(output, result)
        self.assertTrue(output.read_bytes().startswith(b"\xef\xbb\xbf"))
        with output.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertTrue(any(row["metric"] == "review_completion_ratio" for row in rows))

    def test_korean_reviewer_note_is_preserved(self) -> None:
        result = self.evaluate(
            [self.row("r1", "pause", "silence", note="짧은 숨소리 이후 침묵")]
        )
        self.assertEqual(result["review_items"][0]["reviewer_note"], "짧은 숨소리 이후 침묵")
        output = self.directory / "result.json"
        evaluation.write_json_result(output, result)
        self.assertIn("짧은 숨소리", output.read_text(encoding="utf-8"))

    def test_source_manifest_sha256_is_preserved(self) -> None:
        self.write_manifest([self.row("r1", "pause", "silence")])
        before = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        evaluation.evaluate_speech_review_labels(self.manifest)
        after = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_cli_success_exit_code_zero(self) -> None:
        self.write_manifest([self.row("r1", "pause", "silence")])
        with redirect_stdout(io.StringIO()):
            code = evaluation.main(
                [
                    str(self.manifest),
                    "--output",
                    str(self.directory / "result.json"),
                    "--csv-output",
                    str(self.directory / "result.csv"),
                ]
            )
        self.assertEqual(code, 0)

    def test_analysis_failure_exit_code_one(self) -> None:
        with redirect_stdout(io.StringIO()):
            code = evaluation.main(
                [
                    str(self.directory / "missing.csv"),
                    "--output",
                    str(self.directory / "result.json"),
                    "--csv-output",
                    str(self.directory / "result.csv"),
                ]
            )
        self.assertEqual(code, 1)

    def test_cli_usage_error_exit_code_two(self) -> None:
        with (
            self.assertRaises(SystemExit) as raised,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            evaluation.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_invalid_csv_header_is_classified(self) -> None:
        self.manifest.write_text("wrong,columns\n1,2\n", encoding="utf-8")
        result = evaluation.evaluate_speech_review_labels(self.manifest)
        self.assertEqual(result["error"]["code"], "REVIEW_MANIFEST_CSV_INVALID")

    def test_review_items_contain_only_contract_fields(self) -> None:
        result = self.evaluate([self.row("r1", "pause", "silence")])
        self.assertEqual(set(result["review_items"][0]), set(evaluation.REVIEW_ITEM_FIELDS))


if __name__ == "__main__":
    unittest.main()
