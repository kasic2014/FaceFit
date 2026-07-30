"""Tests for natural transcript review templates and pair diagnostics."""

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
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import create_natural_transcript_review as review  # noqa: E402


def _fixtures() -> tuple[dict, dict[str, dict]]:
    pairs = []
    evaluations = []
    individuals = {}
    number = 0
    for script in ("SCRIPT001", "SCRIPT002"):
        for condition in ("clean", "natural"):
            for repetition in (1, 2, 3):
                number += 1
                key = f"SPK001|SESSION001|{script}|{condition}|{repetition}"
                pc_id = f"PC{number:02d}"
                phone_id = f"PHONE{number:02d}"
                pc_text = "같은 전사"
                phone_text = (
                    "다른 전사"
                    if (script, condition, repetition)
                    in {
                        ("SCRIPT001", "clean", 2),
                        ("SCRIPT001", "natural", 3),
                        ("SCRIPT002", "natural", 1),
                    }
                    else pc_text
                )
                pairs.append(
                    {
                        "capture_pair_key": key,
                        "speaker_code": "SPK001",
                        "session_id": "SESSION001",
                        "script_id": script,
                        "recording_condition": condition,
                        "repetition_index": repetition,
                        "pc_sample_id": pc_id,
                        "phone_sample_id": phone_id,
                        "pc_text_raw": pc_text,
                        "phone_text_raw": phone_text,
                        "pc_text_normalized": pc_text,
                        "phone_text_normalized": phone_text,
                        "exact_normalized_match": pc_text == phone_text,
                        "pair_character_error_rate": 0 if pc_text == phone_text else 0.25,
                        "pair_eojeol_error_rate": 0 if pc_text == phone_text else 0.5,
                    }
                )
                for device, sample_id, text in (
                    ("DEV_PC_MIC_01", pc_id, pc_text),
                    ("DEV_PHONE_01", phone_id, phone_text),
                ):
                    individuals[sample_id] = {
                        "sample_id": sample_id,
                        "audio_file": f"standard/{sample_id}.wav",
                    }
                    evaluations.append(
                        {
                            "sample_id": sample_id,
                            "device_code": device,
                            "cer": 0.0 if device == "DEV_PC_MIC_01" else 0.2,
                            "character_substitutions": 0 if device == "DEV_PC_MIC_01" else 1,
                            "character_deletions": 0,
                            "character_insertions": 0,
                        }
                    )
    return {"device_pairs": pairs, "evaluations": evaluations}, individuals


class NaturalTranscriptReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.evaluation, self.individual = _fixtures()
        self.review_csv = self.root / "review.csv"
        self.review_json = self.root / "review.json"
        self.mismatch_json = self.root / "mismatch.json"
        self.mismatch_csv = self.root / "mismatch.csv"

    def _rows(self):
        return review.build_natural_review_rows(
            self.evaluation, self.individual
        )

    def test_natural_capture_count_is_six(self) -> None:
        self.assertEqual(len(self._rows()), 6)

    def test_each_capture_has_one_pc(self) -> None:
        self.assertTrue(all(row["pc_sample_id"].startswith("PC") for row in self._rows()))

    def test_each_capture_has_one_phone(self) -> None:
        self.assertTrue(all(row["phone_sample_id"].startswith("PHONE") for row in self._rows()))

    def test_stt_is_not_copied_to_human_transcript(self) -> None:
        self.assertTrue(all(row["human_transcript"] == "" for row in self._rows()))
        self.assertTrue(all(row["review_status"] == "pending" for row in self._rows()))
        self.assertTrue(all(row["reviewer_confirmed"] is False for row in self._rows()))

    def test_pair_mismatch_extracts_three(self) -> None:
        mismatches = review.build_mismatch_rows(self.evaluation, self._rows())
        self.assertEqual(len(mismatches), 3)

    def test_clean_reference_comparison(self) -> None:
        mismatches = review.build_mismatch_rows(self.evaluation, self._rows())
        clean = next(row for row in mismatches if row["condition"] == "clean")
        self.assertEqual(clean["reference_status"], "fixed_script_reference")
        self.assertEqual(clean["reference_closeness"], "pc_closer_to_reference")

    def test_all_six_clean_pairs_are_diagnosed(self) -> None:
        diagnostics = review.build_clean_pair_diagnostics(self.evaluation)
        self.assertEqual(len(diagnostics), 6)
        self.assertTrue(
            all(row["classification"] != "comparison_unavailable" for row in diagnostics)
        )

    def test_natural_untranscribed_status(self) -> None:
        mismatches = review.build_mismatch_rows(self.evaluation, self._rows())
        natural = next(row for row in mismatches if row["condition"] == "natural")
        self.assertEqual(natural["reference_status"], "requires_manual_transcript")
        self.assertIsNone(natural["pc_cer"])

    def test_both_exact_classification(self) -> None:
        metrics = {"cer": 0.0, "character_substitutions": 0, "character_deletions": 0, "character_insertions": 0}
        classification, _, _ = review.classify_clean_pair(metrics, metrics)
        self.assertEqual(classification, "both_exact")

    def test_pc_closer_classification(self) -> None:
        pc = {"cer": 0.1, "character_substitutions": 1, "character_deletions": 0, "character_insertions": 0}
        phone = {"cer": 0.2, "character_substitutions": 2, "character_deletions": 0, "character_insertions": 0}
        self.assertEqual(review.classify_clean_pair(pc, phone)[0], "pc_closer_to_reference")

    def test_phone_closer_classification(self) -> None:
        pc = {"cer": 0.2, "character_substitutions": 2, "character_deletions": 0, "character_insertions": 0}
        phone = {"cer": 0.1, "character_substitutions": 1, "character_deletions": 0, "character_insertions": 0}
        self.assertEqual(review.classify_clean_pair(pc, phone)[0], "phone_closer_to_reference")

    def test_equal_non_exact_classification(self) -> None:
        pc = {"cer": 0.2, "character_substitutions": 1, "character_deletions": 0, "character_insertions": 0}
        phone = dict(pc)
        self.assertEqual(review.classify_clean_pair(pc, phone)[0], "equal_non_exact")

    def _write_realistic_inputs(self) -> tuple[Path, Path]:
        evaluation_path = self.root / "evaluation.json"
        evaluation_path.write_text(json.dumps(self.evaluation), encoding="utf-8")
        batch_rows = []
        for sample_id, payload in self.individual.items():
            output = self.root / "stt" / f"{sample_id}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            payload = {**payload}
            output.write_text(json.dumps(payload), encoding="utf-8")
            batch_rows.append(
                {
                    "sample_id": sample_id,
                    "output_json": output.relative_to(self.root).as_posix(),
                }
            )
        batch = self.root / "batch.json"
        batch.write_text(json.dumps({"files": batch_rows}), encoding="utf-8")
        return evaluation_path, batch

    def test_strict_json_csv_bom_and_atomic_writes(self) -> None:
        evaluation_path, batch = self._write_realistic_inputs()
        review.create_review_and_report(
            evaluation_path,
            batch,
            self.root,
            self.review_csv,
            self.review_json,
            self.mismatch_json,
            self.mismatch_csv,
        )
        json.loads(
            self.review_json.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
        self.assertTrue(self.review_csv.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.mismatch_csv.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.rglob("*")))

    def test_stt_and_wav_hashes_are_preserved_without_model_call(self) -> None:
        evaluation_path, batch = self._write_realistic_inputs()
        wav = self.root / "audio.wav"
        wav.write_bytes(b"immutable audio")
        protected = [batch, wav] + list((self.root / "stt").glob("*.json"))
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
        with mock.patch.dict(sys.modules, {"faster_whisper": None}):
            review.create_review_and_report(
                evaluation_path,
                batch,
                self.root,
                self.review_csv,
                self.review_json,
                self.mismatch_json,
                self.mismatch_csv,
            )
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
        self.assertEqual(before, after)

    def test_cli_exit_codes_zero_one_two(self) -> None:
        args = [
            "--stt-evaluation", "a", "--batch-manifest", "b", "--relative-root", "c",
            "--review-csv-output", "d", "--review-json-output", "e",
            "--mismatch-json-output", "f", "--mismatch-csv-output", "g",
        ]
        with mock.patch.object(
            review,
            "create_review_and_report",
            return_value={"natural_capture_count": 6, "mismatch_count": 3, "error": None},
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = review.main(args)
            with mock.patch.object(
                review,
                "create_review_and_report",
                side_effect=review.NaturalReviewError("REVIEW_INPUT_INVALID", "x"),
            ):
                failure = review.main(args)
            with self.assertRaises(SystemExit) as raised:
                review.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
