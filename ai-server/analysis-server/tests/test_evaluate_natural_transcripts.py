"""Tests for reviewer-confirmed natural transcript evaluation."""

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
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_natural_transcripts as natural  # noqa: E402
from create_natural_transcript_review import REVIEW_FIELDS  # noqa: E402


def _review_rows(*, completed: bool = False) -> list[dict]:
    rows = []
    number = 0
    for script in ("SCRIPT001", "SCRIPT002"):
        for repetition in (1, 2, 3):
            number += 1
            rows.append(
                {
                    "capture_key": f"SPK001|SESSION001|{script}|natural|{repetition}",
                    "speaker_code": "SPK001",
                    "session_id": "SESSION001",
                    "script_id": script,
                    "repetition_index": str(repetition),
                    "pc_sample_id": f"PC{number}",
                    "phone_sample_id": f"PHONE{number}",
                    "pc_audio_file": f"pc{number}.wav",
                    "phone_audio_file": f"phone{number}.wav",
                    "pc_stt_raw": "사람 전사",
                    "phone_stt_raw": "사람 전사",
                    "pc_stt_normalized": "사람 전사",
                    "phone_stt_normalized": "사람 전사",
                    "pair_exact_match": "true",
                    "pair_character_error_rate": "0",
                    "pair_eojeol_error_rate": "0",
                    "human_transcript": "사람 전사" if completed else "",
                    "human_transcript_note": "",
                    "review_status": "completed" if completed else "pending",
                    "reviewer_confirmed": completed,
                }
            )
    return rows


def _individual() -> dict[str, dict]:
    results = {}
    number = 0
    for script in ("SCRIPT001", "SCRIPT002"):
        for repetition in (1, 2, 3):
            number += 1
            for device, prefix, text in (
                ("DEV_PC_MIC_01", "PC", "사람 전사"),
                ("DEV_PHONE_01", "PHONE", "사람 검사"),
            ):
                sample_id = f"{prefix}{number}"
                results[sample_id] = {
                    "sample_id": sample_id,
                    "session_id": "SESSION001",
                    "script_id": script,
                    "repetition_index": repetition,
                    "device_code": device,
                    "transcription_text_raw": text,
                }
    return results


class EvaluateNaturalTranscriptsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.review = self.root / "review.csv"
        self.batch = self.root / "batch.json"
        self.output_json = self.root / "natural.json"
        self.output_csv = self.root / "natural.csv"

    def test_empty_transcript_is_excluded(self) -> None:
        rows = _review_rows()
        evaluations, exclusions = natural.build_natural_evaluations(rows, _individual())
        self.assertEqual(len(evaluations), 0)
        self.assertIn("HUMAN_TRANSCRIPT_EMPTY", exclusions[0]["reasons"])

    def test_unconfirmed_transcript_is_excluded(self) -> None:
        rows = _review_rows(completed=True)
        rows[0]["reviewer_confirmed"] = False
        evaluations, exclusions = natural.build_natural_evaluations(rows, _individual())
        self.assertEqual(len(evaluations), 10)
        self.assertIn("REVIEWER_NOT_CONFIRMED", exclusions[0]["reasons"])

    def test_completed_transcript_is_evaluated(self) -> None:
        evaluations, exclusions = natural.build_natural_evaluations(
            _review_rows(completed=True), _individual()
        )
        self.assertEqual(len(evaluations), 12)
        self.assertEqual(exclusions, [])

    def test_same_reference_is_applied_to_both_devices(self) -> None:
        evaluations, _ = natural.build_natural_evaluations(
            _review_rows(completed=True), _individual()
        )
        by_capture = {}
        for row in evaluations:
            by_capture.setdefault(row["capture_key"], []).append(row)
        self.assertTrue(
            all(
                pair[0]["reference_text_normalized"]
                == pair[1]["reference_text_normalized"]
                for pair in by_capture.values()
            )
        )

    def test_cer_is_calculated(self) -> None:
        evaluations, _ = natural.build_natural_evaluations(
            _review_rows(completed=True), _individual()
        )
        pc = next(row for row in evaluations if row["device_code"] == "DEV_PC_MIC_01")
        phone = next(row for row in evaluations if row["device_code"] == "DEV_PHONE_01")
        self.assertEqual(pc["cer"], 0)
        self.assertGreater(phone["cer"], 0)

    def test_eojeol_error_rate_is_calculated(self) -> None:
        evaluations, _ = natural.build_natural_evaluations(
            _review_rows(completed=True), _individual()
        )
        phone = next(row for row in evaluations if row["device_code"] == "DEV_PHONE_01")
        self.assertGreater(phone["eojeol_error_rate"], 0)

    def test_pc_aggregation(self) -> None:
        evaluations, exclusions = natural.build_natural_evaluations(
            _review_rows(completed=True), _individual()
        )
        summary = natural.summarize_natural_evaluations(evaluations, exclusions)
        self.assertEqual(summary["pc_cer_median"], 0)

    def test_phone_aggregation(self) -> None:
        evaluations, exclusions = natural.build_natural_evaluations(
            _review_rows(completed=True), _individual()
        )
        summary = natural.summarize_natural_evaluations(evaluations, exclusions)
        self.assertGreater(summary["phone_cer_median"], 0)

    def test_duplicate_capture_is_excluded(self) -> None:
        rows = _review_rows(completed=True)
        rows[1]["capture_key"] = rows[0]["capture_key"]
        evaluations, exclusions = natural.build_natural_evaluations(rows, _individual())
        self.assertEqual(len(evaluations), 8)
        self.assertEqual(len(exclusions), 2)

    def test_unclear_marker_requires_policy(self) -> None:
        rows = _review_rows(completed=True)
        rows[0]["human_transcript"] = "여기는 [불명확] 입니다"
        _, exclusions = natural.build_natural_evaluations(rows, _individual())
        self.assertIn("UNCLEAR_MARKER_REQUIRES_POLICY", exclusions[0]["reasons"])

    def _write_files(self, *, completed: bool = True) -> None:
        rows = _review_rows(completed=completed)
        with self.review.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        batch_rows = []
        for result in _individual().values():
            output = self.root / "stt" / f"{result['sample_id']}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result), encoding="utf-8")
            batch_rows.append(
                {
                    "sample_id": result["sample_id"],
                    "output_json": output.relative_to(self.root).as_posix(),
                }
            )
        self.batch.write_text(json.dumps({"files": batch_rows}), encoding="utf-8")

    def test_strict_json_csv_bom_and_atomic_output(self) -> None:
        self._write_files()
        natural.evaluate_natural_review(
            self.review,
            self.batch,
            self.root,
            self.output_json,
            self.output_csv,
        )
        json.loads(
            self.output_json.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
        self.assertTrue(self.output_csv.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.rglob("*")))

    def test_summary_scope_is_six_captures_twelve_files(self) -> None:
        self._write_files()
        payload = natural.evaluate_natural_review(
            self.review,
            self.batch,
            self.root,
            self.output_json,
            self.output_csv,
        )
        self.assertEqual(payload["summary"]["evaluated_capture_count"], 6)
        self.assertEqual(payload["summary"]["evaluated_audio_file_count"], 12)

    def test_cli_exit_codes_zero_one_two(self) -> None:
        args = [
            "--review-csv", "a", "--batch-manifest", "b", "--relative-root", "c",
            "--output-json", "d", "--output-csv", "e",
        ]
        with mock.patch.object(
            natural,
            "evaluate_natural_review",
            return_value={"summary": {}, "error": None},
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = natural.main(args)
            with mock.patch.object(
                natural,
                "evaluate_natural_review",
                side_effect=natural.NaturalEvaluationError("NATURAL_REVIEW_INVALID", "x"),
            ):
                failure = natural.main(args)
            with self.assertRaises(SystemExit) as raised:
                natural.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
