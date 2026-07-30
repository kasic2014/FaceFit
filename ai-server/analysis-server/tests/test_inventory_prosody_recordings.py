"""Tests for the read-only prosody recording inventory."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
import tempfile
import unittest
import wave
from collections import Counter, defaultdict
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import inventory_prosody_recordings as inventory  # noqa: E402


def _write_wav(path: Path, marker: int, duration: float = 0.02) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 8000
    frames = max(1, int(sample_rate * duration))
    data = bytes(
        128 + int(20 * math.sin(2 * math.pi * (200 + marker) * i / sample_rate))
        for i in range(frames)
    ) + bytes([marker % 256])
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(1)
        stream.setframerate(sample_rate)
        stream.writeframes(data)


def _plan_rows(*, extension: str = ".wav") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    number = 0
    for script in ("SCRIPT001", "SCRIPT002"):
        for condition in ("clean", "natural"):
            for repetition in (1, 2, 3):
                for device in ("DEV_PC_MIC_01", "DEV_PHONE_01"):
                    number += 1
                    stem = (
                        f"SPK001_{script}_SESSION001_{device}_"
                        f"{condition}_R{repetition:02d}"
                    )
                    rows.append(
                        {
                            "plan_id": f"PLAN{number:03d}",
                            "sample_id": f"SAMPLE{number:03d}",
                            "speaker_code": "SPK001",
                            "session_id": "SESSION001",
                            "script_id": script,
                            "recording_condition": condition,
                            "repetition_index": str(repetition),
                            "device_code": device,
                            "recording_order": str(number),
                            "expected_original_filename": stem + extension,
                            "expected_analysis_wav_filename": stem + ".wav",
                        }
                    )
    return rows


class RecordingInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pc = self.root / "recordings" / "pc"
        self.phone = self.root / "recordings" / "phone"
        self.pc.mkdir(parents=True)
        self.phone.mkdir(parents=True)
        self.plan_path = self.root / "plan.csv"
        self.json_path = self.root / "inventory.json"
        self.csv_path = self.root / "inventory.csv"
        self.mapping_path = self.root / "mapping.csv"

    def _write_plan(self, rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
        rows = rows or _plan_rows()
        with self.plan_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return rows

    def _write_complete_recordings(self) -> list[dict[str, str]]:
        rows = self._write_plan()
        for marker, row in enumerate(rows, 1):
            group = self.pc if row["device_code"] == "DEV_PC_MIC_01" else self.phone
            _write_wav(group / row["expected_original_filename"], marker)
        return rows

    def _create(self) -> tuple[dict, list[dict], list[dict]]:
        return inventory.create_inventory(
            self.pc, self.phone, self.plan_path, self.root
        )

    def test_pc_file_count_is_12(self) -> None:
        self._write_complete_recordings()
        report, _, _ = self._create()
        self.assertEqual(report["pc_files"], 12)

    def test_phone_file_count_is_12(self) -> None:
        self._write_complete_recordings()
        report, _, _ = self._create()
        self.assertEqual(report["phone_files"], 12)

    def test_total_file_count_is_24(self) -> None:
        self._write_complete_recordings()
        report, _, _ = self._create()
        self.assertEqual(report["total_files"], 24)

    def test_hidden_and_temporary_files_are_excluded(self) -> None:
        self._write_complete_recordings()
        for name in (".hidden.wav", "Thumbs.db", "~$open.wav", "partial.tmp"):
            (self.pc / name).write_bytes(b"not audio")
        self.assertEqual(len(inventory.discover_recordings(self.pc, "pc")), 12)

    def test_sha256_is_generated(self) -> None:
        path = self.pc / "one.wav"
        _write_wav(path, 1)
        row = inventory.inspect_recording(path, "pc", self.root)
        self.assertEqual(row["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_duplicate_hash_is_detected(self) -> None:
        rows = [
            {
                "source_filename": "a.wav",
                "source_relative_path": "pc/a.wav",
                "sha256": "same",
                "readable": True,
                "duration_sec": 1.0,
                "file_size_bytes": 1,
                "inspection_warnings": [],
            },
            {
                "source_filename": "b.wav",
                "source_relative_path": "phone/b.wav",
                "sha256": "same",
                "readable": True,
                "duration_sec": 1.0,
                "file_size_bytes": 1,
                "inspection_warnings": [],
            },
        ]
        errors = inventory.validate_inventory(rows, 12, 12, {})
        self.assertIn("DUPLICATE_AUDIO_HASH", {error["code"] for error in errors})

    def test_empty_file_is_unreadable(self) -> None:
        path = self.pc / "empty.wav"
        path.touch()
        row = inventory.inspect_recording(path, "pc", self.root)
        self.assertFalse(row["readable"])
        self.assertIn("EMPTY_AUDIO_FILE", row["inspection_warnings"])

    def test_unreadable_audio_is_detected(self) -> None:
        path = self.pc / "bad.wav"
        path.write_bytes(b"not a wave file")
        row = inventory.inspect_recording(path, "pc", self.root)
        self.assertFalse(row["readable"])
        self.assertTrue(
            any(item.startswith("AUDIO_FILE_UNREADABLE") for item in row["inspection_warnings"])
        )

    def test_wav_metadata(self) -> None:
        path = self.pc / "audio.wav"
        _write_wav(path, 2, duration=0.05)
        metadata = inventory.inspect_audio_metadata(path)
        self.assertEqual(metadata["detected_audio_format"], "WAV/PCM")
        self.assertEqual(metadata["sample_rate"], 8000)
        self.assertEqual(metadata["channels"], 1)
        self.assertEqual(metadata["bit_depth"], 8)
        self.assertGreater(metadata["duration_sec"], 0)

    def test_phone_format_metadata_processing(self) -> None:
        path = self.phone / "audio.m4a"
        path.write_bytes(b"placeholder")
        expected = {
            "detected_audio_format": "M4A/AAC",
            "duration_sec": 2.5,
            "sample_rate": 48000,
            "channels": 1,
            "bit_depth": None,
        }
        with mock.patch.object(inventory, "_find_ffprobe", return_value=None), mock.patch.object(
            inventory, "_pyav_metadata", return_value=expected
        ):
            self.assertEqual(inventory.inspect_audio_metadata(path), expected)

    def test_collection_plan_has_24_rows(self) -> None:
        self._write_plan()
        self.assertEqual(len(inventory.load_collection_plan(self.plan_path)), 24)

    def test_invalid_collection_plan_is_rejected(self) -> None:
        self._write_plan(_plan_rows()[:-1])
        with self.assertRaises(inventory.RecordingInventoryError) as raised:
            inventory.load_collection_plan(self.plan_path)
        self.assertEqual(raised.exception.code, "COLLECTION_PLAN_INVALID")

    def test_exact_filename_match(self) -> None:
        plan_rows = _plan_rows()
        recording = {
            "source_filename": plan_rows[0]["expected_original_filename"],
            "source_relative_path": "recordings/pc/exact.wav",
            "sha256": "abc",
        }
        mappings, counts = inventory.build_mapping_rows(plan_rows, [recording])
        self.assertEqual(mappings[0]["mapping_status"], "exact_filename_match")
        self.assertEqual(counts["exact_filename_match"], 1)

    def test_unmatched_file_needs_manual_mapping(self) -> None:
        mappings, counts = inventory.build_mapping_rows(_plan_rows(), [])
        self.assertEqual(mappings[0]["mapping_status"], "needs_manual_mapping")
        self.assertEqual(mappings[0]["source_filename"], "")
        self.assertEqual(counts["unmatched"], 24)

    def test_ambiguous_filename_is_not_selected(self) -> None:
        plan_rows = _plan_rows()
        name = plan_rows[0]["expected_original_filename"]
        recordings = [
            {"source_filename": name, "source_relative_path": "a", "sha256": "a"},
            {"source_filename": name, "source_relative_path": "b", "sha256": "b"},
        ]
        mappings, counts = inventory.build_mapping_rows(plan_rows, recordings)
        self.assertEqual(mappings[0]["mapping_status"], "ambiguous")
        self.assertEqual(mappings[0]["source_filename"], "")
        self.assertEqual(counts["ambiguous"], 1)

    def test_order_is_never_used_to_infer_mapping(self) -> None:
        recordings = [
            {
                "source_filename": f"recording_{index:02d}.wav",
                "source_relative_path": f"pc/recording_{index:02d}.wav",
                "sha256": str(index),
            }
            for index in range(24)
        ]
        mappings, counts = inventory.build_mapping_rows(_plan_rows(), recordings)
        self.assertEqual(counts["exact_filename_match"], 0)
        self.assertTrue(all(row["source_filename"] == "" for row in mappings))

    def test_manual_mapping_template_has_fixed_fields(self) -> None:
        mappings, _ = inventory.build_mapping_rows(_plan_rows(), [])
        self.assertEqual(len(mappings), 24)
        self.assertEqual(tuple(mappings[0]), inventory.MAPPING_FIELDS)

    def test_device_pair_count_is_12(self) -> None:
        summary = inventory.validate_device_pairs(_plan_rows())
        self.assertEqual(summary["pair_count"], 12)

    def test_each_pair_has_one_pc(self) -> None:
        groups: dict[tuple, list[str]] = defaultdict(list)
        for row in _plan_rows():
            key = (
                row["speaker_code"],
                row["session_id"],
                row["script_id"],
                row["recording_condition"],
                row["repetition_index"],
            )
            groups[key].append(row["device_code"])
        self.assertTrue(all(devices.count("DEV_PC_MIC_01") == 1 for devices in groups.values()))

    def test_each_pair_has_one_phone(self) -> None:
        groups: dict[tuple, list[str]] = defaultdict(list)
        for row in _plan_rows():
            key = (
                row["speaker_code"],
                row["session_id"],
                row["script_id"],
                row["recording_condition"],
                row["repetition_index"],
            )
            groups[key].append(row["device_code"])
        self.assertTrue(all(devices.count("DEV_PHONE_01") == 1 for devices in groups.values()))

    def test_incomplete_device_pair_is_rejected(self) -> None:
        rows = _plan_rows()
        rows[0]["device_code"] = "DEV_PHONE_01"
        with self.assertRaises(inventory.RecordingInventoryError):
            inventory.validate_device_pairs(rows)

    def test_source_sha256_is_preserved(self) -> None:
        self._write_complete_recordings()
        paths = inventory.discover_recordings(self.pc, "pc") + inventory.discover_recordings(
            self.phone, "phone"
        )
        before = {path: inventory.sha256_file(path) for path in paths}
        self._create()
        after = {path: inventory.sha256_file(path) for path in paths}
        self.assertEqual(before, after)

    def test_csv_is_utf8_bom(self) -> None:
        self._write_complete_recordings()
        report, rows, mappings = self._create()
        inventory.write_inventory_outputs(
            self.json_path, self.csv_path, self.mapping_path, report, rows, mappings
        )
        self.assertTrue(self.csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.mapping_path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_json_is_strict(self) -> None:
        self._write_complete_recordings()
        report, rows, mappings = self._create()
        inventory.write_inventory_outputs(
            self.json_path, self.csv_path, self.mapping_path, report, rows, mappings
        )
        parsed = json.loads(
            self.json_path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
        self.assertEqual(parsed["schema_version"], "1.0")
        self.assertEqual(len(parsed["files"]), 24)

    def test_atomic_writes_leave_no_temporary_files(self) -> None:
        self._write_complete_recordings()
        report, rows, mappings = self._create()
        inventory.write_inventory_outputs(
            self.json_path, self.csv_path, self.mapping_path, report, rows, mappings
        )
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.iterdir()))

    def test_inventory_csv_has_fixed_column_order(self) -> None:
        self._write_complete_recordings()
        report, rows, mappings = self._create()
        inventory.write_inventory_outputs(
            self.json_path, self.csv_path, self.mapping_path, report, rows, mappings
        )
        with self.csv_path.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(tuple(next(csv.reader(stream))), inventory.INVENTORY_FIELDS)

    def test_supported_format_failure_is_classified(self) -> None:
        path = self.pc / "audio.bin"
        path.write_bytes(b"content")
        with self.assertRaises(inventory.RecordingInventoryError) as raised:
            inventory.inspect_audio_metadata(path)
        self.assertEqual(raised.exception.code, "UNSUPPORTED_AUDIO_FORMAT")

    def test_missing_device_directories_are_classified(self) -> None:
        missing = self.root / "missing"
        with self.assertRaises(inventory.RecordingInventoryError) as raised:
            inventory.discover_recordings(missing, "pc")
        self.assertEqual(raised.exception.code, "PC_RECORDING_DIRECTORY_NOT_FOUND")

    def test_count_mismatch_report_can_be_written(self) -> None:
        rows = self._write_plan()
        for marker, row in enumerate(rows[:-1], 1):
            group = self.pc if row["device_code"] == "DEV_PC_MIC_01" else self.phone
            _write_wav(group / row["expected_original_filename"], marker)
        report, inventory_rows, mappings = self._create()
        inventory.write_inventory_outputs(
            self.json_path,
            self.csv_path,
            self.mapping_path,
            report,
            inventory_rows,
            mappings,
        )
        self.assertEqual(report["error"]["code"], "RECORDING_COUNT_MISMATCH")
        self.assertTrue(self.mapping_path.exists())

    def test_cli_exit_codes_zero_one_two(self) -> None:
        rows = self._write_complete_recordings()
        args = [
            "--pc-dir",
            str(self.pc),
            "--phone-dir",
            str(self.phone),
            "--plan",
            str(self.plan_path),
            "--relative-root",
            str(self.root),
            "--output-json",
            str(self.json_path),
            "--output-csv",
            str(self.csv_path),
            "--mapping-output",
            str(self.mapping_path),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = inventory.main(args)
            (self.phone / rows[-1]["expected_original_filename"]).unlink()
            failure = inventory.main(args)
            with self.assertRaises(SystemExit) as raised:
                inventory.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))

    def test_required_error_codes_are_declared(self) -> None:
        expected = {
            "PC_RECORDING_DIRECTORY_NOT_FOUND",
            "PHONE_RECORDING_DIRECTORY_NOT_FOUND",
            "RECORDING_COUNT_MISMATCH",
            "AUDIO_FILE_UNREADABLE",
            "UNSUPPORTED_AUDIO_FORMAT",
            "DUPLICATE_AUDIO_HASH",
            "COLLECTION_PLAN_NOT_FOUND",
            "COLLECTION_PLAN_INVALID",
            "MAPPING_AMBIGUOUS",
            "INVENTORY_WRITE_FAILED",
            "RECORDING_INVENTORY_FAILED",
        }
        self.assertTrue(expected.issubset(inventory.KNOWN_ERROR_CODES))


if __name__ == "__main__":
    unittest.main()
