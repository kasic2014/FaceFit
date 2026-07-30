"""Tests for the deterministic 24-row prosody recording plan."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import create_prosody_collection_plan as plan  # noqa: E402


class ProsodyCollectionPlanTests(unittest.TestCase):
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
        "app/speech/prosody_dataset.py": (
            "a4dc8dc5ab1d02c19681e9b44a3e99afec3a97a4a121da1d7198857f94e957a0"
        ),
        "scripts/run_prosody_dataset_benchmark.py": (
            "f3034ef4eb183cbecc3d226792e77265ea1da911bba5030bce07bc61d1adb47f"
        ),
        "data/prosody_validation/prosody_dataset_manifest.csv": (
            "757cd2d88d20507ea82161ef968bb61213332467509e23be60bc45ad8fdc3d6f"
        ),
        "data/prosody_validation/prosody_dataset_manifest.json": (
            "543767f3b0428f45b843bbfce59272d1cc58947d3c40a8a9052b3cfe8e709d21"
        ),
        "data/prosody_validation/prosody_dataset_pilot.csv": (
            "5c9c15ea0b5eefaeba93c7973a52d33d24442220428be5493d8c675b3e2c9da5"
        ),
        "data/prosody_validation/prosody_dataset_pilot.json": (
            "84d1a3416d631994793c3f8d7b8f3b51e33d732d66d79d3452034f130d90e5f4"
        ),
        "data/output/prosody_validation/prosody_dataset_pilot_benchmark.json": (
            "01b2bc31f9b831a3f31f0157bea0bdbfebcbe6359155065c1fd25ea3c2613aa3"
        ),
        "data/output/prosody_validation/prosody_dataset_pilot_benchmark.csv": (
            "9148491ec46d2d2695c710f8b9ae165f6a3ba25f2f61d6c8613942ff6b665034"
        ),
        "data/output/prosody_validation/prosody_dataset_pilot_samples.csv": (
            "a15952ae57844da91601ec0dda65ee5490eaa5e3f62f2b8e075285f254e113e6"
        ),
    }

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.csv_path = self.directory / "plan.csv"
        self.json_path = self.directory / "plan.json"
        self.checklist = self.directory / "CHECKLIST.md"
        self.rows = plan.generate_collection_plan()

    def test_generates_24_combinations(self) -> None:
        self.assertEqual(len(self.rows), 24)

    def test_pc_count_is_12(self) -> None:
        self.assertEqual(
            sum(row["device_code"] == "DEV_PC_MIC_01" for row in self.rows),
            12,
        )

    def test_phone_count_is_12(self) -> None:
        self.assertEqual(
            sum(row["device_code"] == "DEV_PHONE_01" for row in self.rows),
            12,
        )

    def test_clean_count_is_12(self) -> None:
        self.assertEqual(
            sum(row["recording_condition"] == "clean" for row in self.rows),
            12,
        )

    def test_natural_count_is_12(self) -> None:
        self.assertEqual(
            sum(row["recording_condition"] == "natural" for row in self.rows),
            12,
        )

    def test_each_script_count_is_12(self) -> None:
        counts = Counter(row["script_id"] for row in self.rows)
        self.assertEqual(counts, {"SCRIPT001": 12, "SCRIPT002": 12})

    def test_each_repetition_count_is_8(self) -> None:
        counts = Counter(row["repetition_index"] for row in self.rows)
        self.assertEqual(counts, {1: 8, 2: 8, 3: 8})

    def test_sample_ids_are_unique(self) -> None:
        values = [row["sample_id"] for row in self.rows]
        self.assertEqual(len(values), len(set(values)))

    def test_plan_ids_are_unique(self) -> None:
        values = [row["plan_id"] for row in self.rows]
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(values[0], "PLAN001")
        self.assertEqual(values[-1], "PLAN024")

    def test_expected_filenames_are_unique_per_field(self) -> None:
        originals = [row["expected_original_filename"] for row in self.rows]
        analysis = [
            row["expected_analysis_wav_filename"] for row in self.rows
        ]
        self.assertEqual(len(originals), len(set(originals)))
        self.assertEqual(len(analysis), len(set(analysis)))

    def test_device_comparison_pairs_are_complete(self) -> None:
        groups: dict[tuple, set[str]] = defaultdict(set)
        for row in self.rows:
            key = (
                row["speaker_code"],
                row["script_id"],
                row["session_id"],
                row["repetition_index"],
                row["recording_condition"],
            )
            groups[key].add(row["device_code"])
        self.assertEqual(len(groups), 12)
        self.assertTrue(
            all(
                devices == {"DEV_PC_MIC_01", "DEV_PHONE_01"}
                for devices in groups.values()
            )
        )

    def _pair_orders(self, repetition: int) -> list[tuple[str, str]]:
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for row in self.rows:
            if row["repetition_index"] != repetition:
                continue
            key = (row["script_id"], row["recording_condition"])
            groups[key].append(row)
        return [
            tuple(
                row["device_code"]
                for row in sorted(
                    group, key=lambda item: item["recording_order"]
                )
            )
            for group in groups.values()
        ]

    def test_repetition_one_device_order(self) -> None:
        self.assertTrue(
            all(
                order == ("DEV_PC_MIC_01", "DEV_PHONE_01")
                for order in self._pair_orders(1)
            )
        )

    def test_repetition_two_device_order(self) -> None:
        self.assertTrue(
            all(
                order == ("DEV_PHONE_01", "DEV_PC_MIC_01")
                for order in self._pair_orders(2)
            )
        )

    def test_repetition_three_device_order(self) -> None:
        self.assertTrue(
            all(
                order == ("DEV_PC_MIC_01", "DEV_PHONE_01")
                for order in self._pair_orders(3)
            )
        )

    def test_csv_is_utf8_bom(self) -> None:
        plan.write_csv_atomic(self.csv_path, self.rows)
        self.assertTrue(self.csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_json_is_strict(self) -> None:
        plan.write_json_atomic(self.json_path, self.rows)
        payload = json.loads(
            self.json_path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(token)
            ),
        )
        self.assertEqual(len(payload["plan_rows"]), 24)
        self.assertIsNone(payload["error"])

    def test_atomic_outputs_leave_no_temporary_files(self) -> None:
        plan.write_collection_plan(
            self.csv_path, self.json_path, self.checklist
        )
        self.assertFalse((self.directory / ".plan.csv.tmp").exists())
        self.assertFalse((self.directory / ".plan.json.tmp").exists())
        self.assertFalse((self.directory / ".CHECKLIST.md.tmp").exists())

    def test_no_prohibited_personal_fields(self) -> None:
        self.assertFalse(
            set(plan.PLAN_FIELDS).intersection(
                plan.PROHIBITED_PERSONAL_FIELDS
            )
        )
        self.assertTrue(
            all(
                not set(row).intersection(plan.PROHIBITED_PERSONAL_FIELDS)
                for row in self.rows
            )
        )

    def test_existing_file_sha256_is_preserved(self) -> None:
        for relative, expected in self.IMMUTABLE_HASHES.items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_cli_exit_codes_zero_one_two(self) -> None:
        args = [
            "--output-csv",
            str(self.csv_path),
            "--output-json",
            str(self.json_path),
            "--checklist-output",
            str(self.checklist),
        ]
        collision = [
            "--output-csv",
            str(self.csv_path),
            "--output-json",
            str(self.csv_path),
            "--checklist-output",
            str(self.checklist),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = plan.main(args)
            failure = plan.main(collision)
            with self.assertRaises(SystemExit) as raised:
                plan.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))

    def test_fixed_csv_column_order(self) -> None:
        plan.write_csv_atomic(self.csv_path, self.rows)
        with self.csv_path.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(tuple(next(csv.reader(stream))), plan.PLAN_FIELDS)

    def test_initial_statuses_are_pending(self) -> None:
        for row in self.rows:
            self.assertEqual(row["recording_status"], "pending")
            self.assertEqual(row["transfer_status"], "pending")
            self.assertEqual(row["analysis_status"], "pending")

    def test_pc_original_and_analysis_names_match(self) -> None:
        for row in self.rows:
            if row["device_code"] == "DEV_PC_MIC_01":
                self.assertEqual(
                    row["expected_original_filename"],
                    row["expected_analysis_wav_filename"],
                )

    def test_phone_original_and_analysis_extensions(self) -> None:
        for row in self.rows:
            if row["device_code"] == "DEV_PHONE_01":
                self.assertTrue(
                    row["expected_original_filename"].endswith(".m4a")
                )
                self.assertTrue(
                    row["expected_analysis_wav_filename"].endswith(".wav")
                )

    def test_checklist_contains_required_sections(self) -> None:
        plan.write_checklist_atomic(self.checklist)
        text = self.checklist.read_text(encoding="utf-8")
        for section in (
            "## 녹음 전",
            "## 녹음 중",
            "## 녹음 후",
            "## clean 조건",
            "## natural 조건",
        ):
            self.assertIn(section, text)

    def test_validation_summary(self) -> None:
        summary = plan.validate_collection_plan(self.rows)
        self.assertEqual(summary["total_rows"], 24)
        self.assertEqual(summary["device_comparison_pair_count"], 12)
        self.assertEqual(summary["prohibited_personal_field_count"], 0)


if __name__ == "__main__":
    unittest.main()
