"""Tests for clean-reference STT evaluation and device-pair consistency."""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_prosody_session_stt as evaluate  # noqa: E402
from transcribe_prosody_session import normalize_korean_text  # noqa: E402


REFERENCES = {
    "SCRIPT001": "안녕하세요 저는 지원자입니다",
    "SCRIPT002": "프로젝트 문제를 해결했습니다",
}


def _results(*, phone_difference: bool = False) -> list[dict]:
    rows = []
    number = 0
    for script in ("SCRIPT001", "SCRIPT002"):
        for condition in ("clean", "natural"):
            for repetition in (1, 2, 3):
                pair_key = f"SPK001|SESSION001|{script}|{condition}|{repetition}"
                for device in ("DEV_PC_MIC_01", "DEV_PHONE_01"):
                    number += 1
                    text = REFERENCES[script]
                    if phone_difference and device == "DEV_PHONE_01":
                        text += " 추가"
                    normalized = normalize_korean_text(text)
                    rows.append(
                        {
                            "sample_id": f"SAMPLE{number:03d}",
                            "speaker_code": "SPK001",
                            "session_id": "SESSION001",
                            "script_id": script,
                            "recording_condition": condition,
                            "repetition_index": repetition,
                            "device_code": device,
                            "capture_pair_key": pair_key,
                            "transcription_text_raw": text,
                            "transcription_text_normalized": normalized,
                            "word_count": len(normalized.split()),
                            "audio_duration_sec": 10.0,
                            "processing_time_sec": 1.0,
                            "real_time_factor": 0.1,
                            "warnings": [],
                            "error": None,
                        }
                    )
    return rows


class EvaluateProsodySessionSttTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.references = self.root / "references.json"
        self.references.write_text(
            json.dumps({"scripts": REFERENCES}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.batch = self.root / "batch.json"
        self.evaluation_json = self.root / "evaluation.json"
        self.evaluation_csv = self.root / "evaluation.csv"
        self.pair_csv = self.root / "pairs.csv"

    def _write_batch(self, results: list[dict] | None = None) -> None:
        results = results or _results()
        rows = []
        for result in results:
            output = self.root / "individual" / f"{result['sample_id']}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False), encoding="utf-8"
            )
            rows.append(
                {
                    "sample_id": result["sample_id"],
                    "output_json": output.relative_to(self.root).as_posix(),
                }
            )
        self.batch.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_files": 24,
                        "successful_files": 24,
                        "failed_files": 0,
                    },
                    "files": rows,
                }
            ),
            encoding="utf-8",
        )

    def _evaluate(self, results: list[dict] | None = None):
        self._write_batch(results)
        return evaluate.evaluate_session(
            self.batch,
            self.references,
            self.root,
            self.evaluation_json,
            self.evaluation_csv,
            self.pair_csv,
        )

    def test_nfc_normalization(self) -> None:
        decomposed = unicodedata.normalize("NFD", "안녕")
        self.assertEqual(normalize_korean_text(decomposed), "안녕")

    def test_punctuation_removal_and_lowercase(self) -> None:
        self.assertEqual(normalize_korean_text(" Hello, 안녕! "), "hello 안녕")

    def test_cer_exact_match(self) -> None:
        metrics = evaluate.evaluate_text("안녕하세요", "안녕하세요")
        self.assertEqual(metrics["cer"], 0)

    def test_cer_substitution(self) -> None:
        metrics = evaluate.evaluate_text("가나", "가다")
        self.assertEqual(metrics["character_substitutions"], 1)
        self.assertAlmostEqual(metrics["cer"], 1 / 2)

    def test_cer_deletion(self) -> None:
        metrics = evaluate.evaluate_text("가나다", "가나")
        self.assertEqual(metrics["character_deletions"], 1)

    def test_cer_insertion(self) -> None:
        metrics = evaluate.evaluate_text("가나", "가나다")
        self.assertEqual(metrics["character_insertions"], 1)

    def test_eojeol_error_rate(self) -> None:
        metrics = evaluate.evaluate_text("나는 학교에 간다", "나는 회사에 간다")
        self.assertEqual(metrics["eojeol_substitutions"], 1)
        self.assertAlmostEqual(metrics["eojeol_error_rate"], 1 / 3)

    def test_clean_reference_is_applied(self) -> None:
        rows = evaluate.build_evaluation_rows(_results(), REFERENCES)
        clean = next(row for row in rows if row["recording_condition"] == "clean")
        self.assertEqual(clean["reference_status"], "fixed_script_reference")
        self.assertEqual(clean["cer"], 0)

    def test_natural_reference_is_not_applied(self) -> None:
        rows = evaluate.build_evaluation_rows(_results(), REFERENCES)
        natural = next(row for row in rows if row["recording_condition"] == "natural")
        self.assertEqual(natural["reference_status"], "requires_manual_transcript")
        self.assertIsNone(natural["cer"])
        self.assertIsNone(natural["eojeol_error_rate"])

    def test_pair_count_is_12(self) -> None:
        self.assertEqual(len(evaluate.build_pair_rows(_results())), 12)

    def test_pair_exact_match(self) -> None:
        rows = evaluate.build_pair_rows(_results())
        self.assertTrue(all(row["exact_normalized_match"] for row in rows))
        self.assertTrue(all(row["pair_character_error_rate"] == 0 for row in rows))

    def test_pair_text_difference(self) -> None:
        rows = evaluate.build_pair_rows(_results(phone_difference=True))
        self.assertTrue(all(not row["exact_normalized_match"] for row in rows))
        self.assertTrue(all(row["pair_character_error_rate"] > 0 for row in rows))

    def test_pair_is_symmetric(self) -> None:
        first = evaluate._symmetric_error_rate("가나다", "가나")
        second = evaluate._symmetric_error_rate("가나", "가나다")
        self.assertEqual(first, second)

    def test_incomplete_pair_is_rejected(self) -> None:
        rows = _results()[:-1]
        with self.assertRaises(evaluate.SttEvaluationError) as raised:
            evaluate.build_pair_rows(rows)
        self.assertEqual(raised.exception.code, "DEVICE_PAIR_INCOMPLETE")

    def test_full_evaluation_counts_clean_and_natural(self) -> None:
        payload = self._evaluate()
        self.assertEqual(payload["summary"]["evaluated_clean_files"], 12)
        self.assertEqual(
            payload["summary"]["natural_requires_manual_transcript_count"], 12
        )

    def test_device_clean_summary(self) -> None:
        payload = self._evaluate()
        summary = payload["summary"]["clean_by_device"]
        self.assertEqual(summary["DEV_PC_MIC_01"]["file_count"], 6)
        self.assertEqual(summary["DEV_PHONE_01"]["file_count"], 6)

    def test_strict_json(self) -> None:
        self._evaluate()
        payload = json.loads(
            self.evaluation_json.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
        self.assertIsNone(payload["error"])

    def test_csv_outputs_use_utf8_bom(self) -> None:
        self._evaluate()
        self.assertTrue(self.evaluation_csv.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.pair_csv.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_csv_row_counts(self) -> None:
        self._evaluate()
        with self.evaluation_csv.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(sum(1 for _ in csv.DictReader(stream)), 24)
        with self.pair_csv.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(sum(1 for _ in csv.DictReader(stream)), 12)

    def test_atomic_outputs_leave_no_temp_files(self) -> None:
        self._evaluate()
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.rglob("*")))

    def test_interpretation_limits_are_recorded(self) -> None:
        payload = self._evaluate()
        self.assertIn("내부 파일럿", payload["interpretation"]["pilot_scope"])
        self.assertIn("대칭적", payload["interpretation"]["pair_metric"])

    def test_cli_exit_codes_zero_one_two(self) -> None:
        args = [
            "--batch-manifest", "a", "--references", "b", "--relative-root", "c",
            "--evaluation-json-output", "d", "--evaluation-csv-output", "e",
            "--pair-csv-output", "f",
        ]
        with mock.patch.object(
            evaluate,
            "evaluate_session",
            return_value={"summary": {}, "error": None},
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = evaluate.main(args)
            with mock.patch.object(
                evaluate,
                "evaluate_session",
                side_effect=evaluate.SttEvaluationError("STT_EVALUATION_FAILED", "x"),
            ):
                failure = evaluate.main(args)
            with self.assertRaises(SystemExit) as raised:
                evaluate.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
