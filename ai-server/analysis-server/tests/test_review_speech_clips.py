"""Tests for the terminal-based speech clip review workflow."""

from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import review_speech_clips as review  # noqa: E402


class ReviewSpeechClipsTests(unittest.TestCase):
    FIELDNAMES = [
        "review_id",
        "source_audio",
        "source_metrics",
        "clip_file",
        "event_type",
        "source_event_types",
        "merged",
        "original_start_sec",
        "original_end_sec",
        "original_duration_sec",
        "clip_start_sec",
        "clip_end_sec",
        "classification",
        "confidence_or_probability",
        "candidate_reasons",
        "previous_word",
        "next_word",
        "mean_dbfs",
        "voiced_frame_ratio",
        "local_energy_contrast_db",
        "audio_quality_flags",
        "reviewer_label",
        "reviewer_note",
    ]

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.manifest = self.directory / "reviewed.csv"
        self.clip = self.directory / "clip.wav"
        self.clip.touch()

    def row(
        self,
        review_id: str,
        label: str = "",
        note: str = "",
        clip_file: str = "clip.wav",
    ) -> dict[str, str]:
        values = {field: "" for field in self.FIELDNAMES}
        values.update(
            {
                "review_id": review_id,
                "source_audio": str(self.directory / "source.wav"),
                "clip_file": clip_file,
                "event_type": "probable_omitted_vocalization",
                "source_event_types": "probable_omitted_vocalization; pause",
                "original_start_sec": "1.0",
                "original_end_sec": "1.5",
                "classification": "word_gap",
                "candidate_reasons": "localized_voiced_run",
                "previous_word": "이전",
                "next_word": "다음",
                "reviewer_label": label,
                "reviewer_note": note,
            }
        )
        return values

    def write_manifest(
        self, rows: list[dict[str, str]], fieldnames: list[str] | None = None
    ) -> Path:
        columns = fieldnames or self.FIELDNAMES
        with self.manifest.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return self.manifest

    def read_rows(self) -> list[dict[str, str]]:
        with self.manifest.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def run_review(
        self,
        rows: list[dict[str, str]],
        inputs: list[object],
        **options: object,
    ) -> tuple[dict, list[str]]:
        self.write_manifest(rows)
        input_mock = Mock(side_effect=inputs)
        output: list[str] = []
        result = review.review_speech_clips(
            self.manifest,
            no_open=True,
            input_function=input_mock,
            output_function=output.append,
            workspace_root=self.directory,
            **options,
        )
        return result, output

    def test_only_unreviewed_items_are_selected(self) -> None:
        result, output = self.run_review(
            [self.row("done", "filler"), self.row("todo")], ["1", ""]
        )
        rows = self.read_rows()
        self.assertEqual(rows[0]["reviewer_label"], "filler")
        self.assertEqual(rows[1]["reviewer_label"], "filler")
        self.assertTrue(any("현재 진행: 1/1" in line for line in output))
        self.assertEqual(result["newly_reviewed_items"], 1)

    def test_reviewed_items_are_skipped_by_default(self) -> None:
        result, output = self.run_review([self.row("done", "noise")], [])
        self.assertTrue(result["success"])
        self.assertTrue(any("검수할 항목이 없습니다" in line for line in output))

    def test_include_reviewed_can_modify_existing_value(self) -> None:
        result, _ = self.run_review(
            [self.row("done", "filler")],
            ["y", "4", "소음으로 수정"],
            include_reviewed=True,
        )
        row = self.read_rows()[0]
        self.assertEqual(row["reviewer_label"], "noise")
        self.assertEqual(result["modified_items"], 1)

    def test_numeric_keys_map_to_all_seven_labels(self) -> None:
        rows = [self.row(f"r{key}") for key in review.LABEL_KEYS]
        inputs = [value for key in review.LABEL_KEYS for value in (key, "")]
        self.run_review(rows, inputs)
        self.assertEqual(
            [row["reviewer_label"] for row in self.read_rows()],
            list(review.LABEL_KEYS.values()),
        )

    def test_invalid_input_is_requested_again(self) -> None:
        _, output = self.run_review([self.row("r1")], ["invalid", "1", ""])
        self.assertEqual(self.read_rows()[0]["reviewer_label"], "filler")
        self.assertTrue(any("잘못된 입력" in line for line in output))

    def test_replay_command_calls_startfile_again(self) -> None:
        self.write_manifest([self.row("r1")])
        opener = Mock()
        result = review.review_speech_clips(
            self.manifest,
            no_open=False,
            input_function=Mock(side_effect=["r", "s"]),
            output_function=Mock(),
            open_function=opener,
            workspace_root=self.directory,
        )
        self.assertTrue(result["success"])
        self.assertEqual(opener.call_count, 2)

    def test_skip_command_leaves_item_unreviewed(self) -> None:
        result, _ = self.run_review([self.row("r1")], ["s"])
        self.assertEqual(self.read_rows()[0]["reviewer_label"], "")
        self.assertEqual(result["unreviewed_items"], 1)

    def test_back_command_moves_to_previous_selected_item(self) -> None:
        self.run_review(
            [self.row("r1"), self.row("r2")],
            ["s", "b", "1", "", "q"],
        )
        rows = self.read_rows()
        self.assertEqual(rows[0]["reviewer_label"], "filler")
        self.assertEqual(rows[1]["reviewer_label"], "")

    def test_quit_command_saves_no_unfinished_value(self) -> None:
        before = self.write_manifest([self.row("r1")]).read_bytes()
        result = review.review_speech_clips(
            self.manifest,
            no_open=True,
            input_function=Mock(side_effect=["q"]),
            output_function=Mock(),
            workspace_root=self.directory,
        )
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(result["newly_reviewed_items"], 0)

    def test_reviewer_note_is_saved(self) -> None:
        self.run_review([self.row("r1")], ["3", "짧은 숨소리"])
        self.assertEqual(self.read_rows()[0]["reviewer_note"], "짧은 숨소리")

    def test_empty_note_preserves_existing_note(self) -> None:
        self.run_review(
            [self.row("r1", "filler", "기존 메모")],
            ["y", "2", ""],
            include_reviewed=True,
        )
        self.assertEqual(self.read_rows()[0]["reviewer_note"], "기존 메모")

    def test_each_completed_item_is_saved_immediately(self) -> None:
        self.write_manifest([self.row("r1"), self.row("r2")])
        with patch("review_speech_clips.write_manifest", wraps=review.write_manifest) as writer:
            review.review_speech_clips(
                self.manifest,
                no_open=True,
                input_function=Mock(side_effect=["1", "", "4", ""]),
                output_function=Mock(),
                workspace_root=self.directory,
            )
        self.assertEqual(writer.call_count, 2)

    def test_saved_csv_keeps_utf8_bom(self) -> None:
        self.run_review([self.row("r1")], ["1", ""])
        self.assertTrue(self.manifest.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_korean_note_is_preserved(self) -> None:
        self.run_review([self.row("r1")], ["1", "한국어 메모입니다."])
        self.assertEqual(self.read_rows()[0]["reviewer_note"], "한국어 메모입니다.")

    def test_original_column_order_is_preserved(self) -> None:
        self.run_review([self.row("r1")], ["1", ""])
        with self.manifest.open("r", encoding="utf-8-sig", newline="") as stream:
            fieldnames = csv.DictReader(stream).fieldnames
        self.assertEqual(fieldnames, self.FIELDNAMES)

    def test_backup_file_is_created_before_review(self) -> None:
        fixed = lambda: datetime(2026, 7, 22, 9, 10, 11)
        result, _ = self.run_review([self.row("r1")], ["q"], backup=True, now=fixed)
        backup = Path(result["backup_path"])
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.name, "reviewed.backup_20260722_091011.csv")

    def test_existing_backup_is_not_overwritten(self) -> None:
        fixed = lambda: datetime(2026, 7, 22, 9, 10, 11)
        existing = self.directory / "reviewed.backup_20260722_091011.csv"
        existing.write_text("keep", encoding="utf-8")
        result, _ = self.run_review([self.row("r1")], ["q"], backup=True, now=fixed)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
        self.assertTrue(Path(result["backup_path"]).name.endswith("_1.csv"))

    def test_missing_clip_is_a_warning_not_failure(self) -> None:
        result, _ = self.run_review([self.row("r1", clip_file="missing.wav")], ["s"])
        self.assertTrue(result["success"])
        self.assertEqual(result["warnings"][0]["code"], "CLIP_FILE_NOT_FOUND")

    def test_audio_open_failure_is_a_warning(self) -> None:
        self.write_manifest([self.row("r1")])
        opener = Mock(side_effect=OSError("cannot open"))
        result = review.review_speech_clips(
            self.manifest,
            no_open=False,
            input_function=Mock(side_effect=["s"]),
            output_function=Mock(),
            open_function=opener,
            workspace_root=self.directory,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["warnings"][0]["code"], "AUDIO_OPEN_FAILED")

    def test_missing_required_columns_is_classified(self) -> None:
        self.write_manifest([self.row("r1")], fieldnames=["review_id", "clip_file"])
        result = review.review_speech_clips(
            self.manifest, no_open=True, input_function=Mock(), output_function=Mock()
        )
        self.assertEqual(result["error"]["code"], "REQUIRED_COLUMNS_MISSING")

    def test_ctrl_c_preserves_previous_completed_item(self) -> None:
        self.write_manifest([self.row("r1"), self.row("r2")])
        result = review.review_speech_clips(
            self.manifest,
            no_open=True,
            input_function=Mock(side_effect=["1", "첫 항목", KeyboardInterrupt()]),
            output_function=Mock(),
            workspace_root=self.directory,
        )
        rows = self.read_rows()
        self.assertTrue(result["interrupted"])
        self.assertEqual(rows[0]["reviewer_label"], "filler")
        self.assertEqual(rows[1]["reviewer_label"], "")

    def test_all_completed_manifest_prints_summary(self) -> None:
        result, output = self.run_review(
            [self.row("r1", "filler"), self.row("r2", "noise")], []
        )
        self.assertEqual(result["reviewed_items"], 2)
        self.assertEqual(result["unreviewed_items"], 0)
        self.assertTrue(any("label_counts" in line for line in output))

    def test_start_from_uses_requested_review_id(self) -> None:
        self.run_review(
            [self.row("r1"), self.row("r2")],
            ["4", ""],
            start_from="r2",
        )
        rows = self.read_rows()
        self.assertEqual(rows[0]["reviewer_label"], "")
        self.assertEqual(rows[1]["reviewer_label"], "noise")

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        self.write_manifest([self.row("done", "filler")])
        with patch("builtins.print"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = review.main([str(self.manifest), "--no-open"])
            failure = review.main([str(self.directory / "missing.csv"), "--no-open"])
            with self.assertRaises(SystemExit) as raised:
                review.main([])
        self.assertEqual(success, 0)
        self.assertEqual(failure, 1)
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
