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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import create_stage2_collection_plan as stage2  # noqa: E402


class CreateStage2CollectionPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.references = self.directory / "scripts.json"
        self.output = self.directory / "stage2"
        self.references.write_text(
            json.dumps(
                {
                    "scripts": {
                        "SCRIPT001": "첫 번째 고정 대본입니다.",
                        "SCRIPT002": "두 번째 고정 대본입니다.",
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.rows = stage2.generate_stage2_plan()

    def write_outputs(self) -> dict:
        return stage2.write_stage2_outputs(self.references, self.output)

    def test_four_new_speakers(self) -> None:
        self.assertEqual(
            {row["speaker_code"] for row in self.rows},
            {"SPK002", "SPK003", "SPK004", "SPK005"},
        )

    def test_plan_has_96_rows(self) -> None:
        self.assertEqual(len(self.rows), 96)

    def test_has_48_capture_groups(self) -> None:
        self.assertEqual(
            len({row["capture_group_id"] for row in self.rows}), 48
        )

    def test_each_speaker_has_24_rows(self) -> None:
        counts = Counter(row["speaker_code"] for row in self.rows)
        self.assertEqual(counts, Counter({speaker: 24 for speaker in stage2.SPEAKERS}))

    def test_each_speaker_has_12_captures(self) -> None:
        captures = {
            (row["speaker_code"], row["capture_group_id"])
            for row in self.rows
        }
        counts = Counter(speaker for speaker, _capture in captures)
        self.assertEqual(counts, Counter({speaker: 12 for speaker in stage2.SPEAKERS}))

    def test_pc_count_is_48(self) -> None:
        self.assertEqual(
            sum(row["device_code"] == "DEV_PC_MIC_01" for row in self.rows),
            48,
        )

    def test_phone_count_is_48(self) -> None:
        self.assertEqual(
            sum(row["device_code"] == "DEV_PHONE_01" for row in self.rows),
            48,
        )

    def test_clean_count_is_48(self) -> None:
        self.assertEqual(
            sum(row["recording_condition"] == "clean" for row in self.rows),
            48,
        )

    def test_natural_count_is_48(self) -> None:
        self.assertEqual(
            sum(row["recording_condition"] == "natural" for row in self.rows),
            48,
        )

    def test_every_capture_has_complete_device_pair(self) -> None:
        groups = defaultdict(list)
        for row in self.rows:
            groups[row["capture_group_id"]].append(row)
        for pair in groups.values():
            self.assertEqual(len(pair), 2)
            self.assertEqual(
                {row["device_code"] for row in pair}, set(stage2.DEVICES)
            )

    def test_paired_sample_links_are_reciprocal(self) -> None:
        by_sample = {row["sample_id"]: row for row in self.rows}
        for row in self.rows:
            paired = by_sample[row["paired_sample_id"]]
            self.assertEqual(paired["paired_sample_id"], row["sample_id"])
            self.assertEqual(
                paired["capture_group_id"], row["capture_group_id"]
            )

    def test_sample_ids_are_unique(self) -> None:
        values = [row["sample_id"] for row in self.rows]
        self.assertEqual(len(values), len(set(values)))

    def test_expected_filenames_are_unique(self) -> None:
        for field in (
            "expected_original_filename",
            "expected_analysis_wav_filename",
        ):
            values = [row[field] for row in self.rows]
            self.assertEqual(len(values), len(set(values)))

    def test_r01_is_pc_first(self) -> None:
        self.assertTrue(
            all(
                row["device_start_order"] == "PC_FIRST"
                for row in self.rows
                if row["repetition_index"] == 1
            )
        )

    def test_r02_is_phone_first(self) -> None:
        self.assertTrue(
            all(
                row["device_start_order"] == "PHONE_FIRST"
                for row in self.rows
                if row["repetition_index"] == 2
            )
        )

    def test_r03_is_pc_first(self) -> None:
        self.assertTrue(
            all(
                row["device_start_order"] == "PC_FIRST"
                for row in self.rows
                if row["repetition_index"] == 3
            )
        )

    def test_all_rows_are_simultaneous(self) -> None:
        self.assertTrue(all(row["simultaneous_capture"] is True for row in self.rows))

    def test_all_rows_are_held_out_validation(self) -> None:
        self.assertEqual(
            {row["dataset_role"] for row in self.rows},
            {"held_out_validation"},
        )

    def test_spk001_is_not_in_new_plan(self) -> None:
        self.assertNotIn("SPK001", {row["speaker_code"] for row in self.rows})

    def test_no_prohibited_personal_fields(self) -> None:
        self.assertFalse(set(stage2.PLAN_FIELDS) & stage2.PROHIBITED_PERSONAL_FIELDS)
        for row in self.rows:
            self.assertFalse(set(row) & stage2.PROHIBITED_PERSONAL_FIELDS)

    def test_consent_defaults_false(self) -> None:
        self.assertTrue(all(row["consent_confirmed"] is False for row in self.rows))

    def test_recording_status_defaults_planned(self) -> None:
        self.assertEqual(
            {row["recording_status"] for row in self.rows}, {"planned"}
        )

    def test_capture_group_id_structure(self) -> None:
        self.assertTrue(
            all(
                stage2.CAPTURE_PATTERN.fullmatch(row["capture_group_id"])
                for row in self.rows
            )
        )

    def test_speaker_specific_session_ids(self) -> None:
        self.assertTrue(
            all(
                row["session_id"] == f"{row['speaker_code']}_SESSION001"
                for row in self.rows
            )
        )

    def test_original_and_analysis_filename_extensions(self) -> None:
        self.assertTrue(
            all(
                row["expected_original_filename"].endswith(".m4a")
                and row["expected_analysis_wav_filename"].endswith(".wav")
                for row in self.rows
            )
        )

    def test_capture_checklist_has_48_rows(self) -> None:
        checklist = stage2.generate_capture_checklist(self.rows)
        self.assertEqual(len(checklist), 48)
        self.assertTrue(
            all(row["capture_status"] == "planned" for row in checklist)
        )

    def test_strict_json_output(self) -> None:
        self.write_outputs()
        with (self.output / "stage2_collection_plan.json").open(
            encoding="utf-8"
        ) as stream:
            payload = json.load(
                stream, parse_constant=lambda token: self.fail(token)
            )
        self.assertEqual(payload["validation_summary"]["plan_row_count"], 96)

    def test_csv_outputs_have_utf8_bom(self) -> None:
        self.write_outputs()
        for name in (
            "stage2_collection_plan.csv",
            "stage2_capture_checklist.csv",
        ):
            self.assertTrue(
                (self.output / name).read_bytes().startswith(b"\xef\xbb\xbf")
            )

    def test_atomic_writes_leave_no_temp_files(self) -> None:
        self.write_outputs()
        self.assertEqual(list(self.output.rglob("*.tmp")), [])

    def test_six_outputs_are_created(self) -> None:
        self.write_outputs()
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {
                "stage2_collection_plan.csv",
                "stage2_collection_plan.json",
                "stage2_capture_checklist.csv",
                "STAGE2_RECORDING_GUIDE.md",
                "STAGE2_DATASET_SPLIT.md",
                "STAGE2_CONSENT_AND_PRIVACY_CHECKLIST.md",
            },
        )

    def test_dataset_split_separates_spk001(self) -> None:
        self.write_outputs()
        text = (self.output / "STAGE2_DATASET_SPLIT.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("development_pilot", text)
        self.assertIn("held_out_validation", text)
        self.assertIn("독립 검증 표본이 아니다", text)

    def test_consent_document_is_internal_not_legal_document(self) -> None:
        self.write_outputs()
        text = (
            self.output / "STAGE2_CONSENT_AND_PRIVACY_CHECKLIST.md"
        ).read_text(encoding="utf-8")
        self.assertIn("법률 문서가 아니라", text)
        self.assertIn("음성 복제 학습에는 사용하지 않음", text)
        self.assertIn("동의하지 않은 파일은 분석 대상에서 제외", text)

    def test_script_reference_text_is_reused(self) -> None:
        self.write_outputs()
        text = (self.output / "STAGE2_RECORDING_GUIDE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("첫 번째 고정 대본입니다.", text)
        self.assertIn("두 번째 고정 대본입니다.", text)

    def test_session001_baseline_files_are_preserved(self) -> None:
        paths = [
            ROOT
            / "data/output/prosody_validation/session_reports/"
            "SESSION001_baseline_checksums.json",
            ROOT
            / "data/output/prosody_validation/session_reports/"
            "SESSION001_validation_report.json",
        ]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        self.write_outputs()
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        self.assertEqual(before, after)

    def test_existing_collection_plan_is_preserved(self) -> None:
        paths = [
            ROOT / "data/prosody_validation/prosody_collection_plan_01.csv",
            ROOT / "data/prosody_validation/prosody_collection_plan_01.json",
            ROOT / "data/prosody_validation/RECORDING_CHECKLIST.md",
        ]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        self.write_outputs()
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        self.assertEqual(before, after)

    def test_no_analysis_script_or_model_invocation(self) -> None:
        self.write_outputs()
        source = (
            SCRIPTS_ROOT / "create_stage2_collection_plan.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("WhisperModel", source)
        self.assertFalse(
            stage2.write_stage2_outputs(
                self.references, self.directory / "another"
            )["recording_or_analysis_executed"]
        )

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        args = [
            "--script-references",
            str(self.references),
            "--output-dir",
            str(self.output),
        ]
        with redirect_stdout(io.StringIO()), mock.patch.object(
            stage2,
            "write_stage2_outputs",
            return_value={"error": None},
        ):
            success = stage2.main(args)
        with redirect_stdout(io.StringIO()), mock.patch.object(
            stage2,
            "write_stage2_outputs",
            side_effect=stage2.Stage2PlanError("TEST", "failed"),
        ):
            failure = stage2.main(args)
        with redirect_stderr(io.StringIO()), self.assertRaises(
            SystemExit
        ) as raised:
            stage2.main([])
        self.assertEqual(success, 0)
        self.assertEqual(failure, 1)
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
