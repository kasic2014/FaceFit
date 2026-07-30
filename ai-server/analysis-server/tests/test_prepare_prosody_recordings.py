"""Tests for safe prosody recording mapping and standard WAV preparation."""

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
from fractions import Fraction
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import prepare_prosody_recordings as prepare  # noqa: E402


def _write_wav(
    path: Path,
    marker: int = 1,
    *,
    rate: int = 48000,
    channels: int = 2,
    width: int = 2,
    duration: float = 0.05,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = max(1, int(rate * duration))
    if width == 2:
        samples = bytearray()
        for index in range(count):
            value = int(500 * math.sin(2 * math.pi * (200 + marker) * index / rate))
            encoded = value.to_bytes(2, "little", signed=True)
            samples.extend(encoded * channels)
        samples.extend((marker % 100).to_bytes(2, "little", signed=True) * channels)
        data = bytes(samples)
    else:
        data = bytes([128 + marker % 30]) * count * channels
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(width)
        stream.setframerate(rate)
        stream.writeframes(data)


def _write_real_m4a(path: Path, duration: float = 0.12) -> None:
    import av

    path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(path), mode="w")
    stream = container.add_stream("aac", rate=48000)
    stream.layout = "stereo"
    remaining = int(48000 * duration)
    pts = 0
    while remaining > 0:
        samples = min(1024, remaining)
        frame = av.AudioFrame(format="s16", layout="stereo", samples=samples)
        frame.sample_rate = 48000
        frame.pts = pts
        frame.time_base = Fraction(1, 48000)
        frame.planes[0].update(b"\x00\x00" * samples * 2)
        for packet in stream.encode(frame):
            container.mux(packet)
        pts += samples
        remaining -= samples
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()


def _plan_rows() -> list[dict[str, str]]:
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
                    original = stem + (
                        ".wav" if device == "DEV_PC_MIC_01" else ".m4a"
                    )
                    rows.append(
                        {
                            "plan_id": f"PLAN{number:03d}",
                            "sample_id": f"SAMPLE{number:03d}",
                            "speaker_code": "SPK001",
                            "session_id": "SESSION001",
                            "script_id": script,
                            "repetition_index": str(repetition),
                            "device_code": device,
                            "environment_code": "QUIET_ROOM",
                            "recording_condition": condition,
                            "recording_order": str(number),
                            "expected_original_filename": original,
                            "expected_analysis_wav_filename": stem + ".wav",
                            "recording_status": "pending",
                            "transfer_status": "pending",
                            "analysis_status": "pending",
                            "notes": "",
                        }
                    )
    return rows


class PrepareProsodyRecordingsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pc = self.root / "original" / "pc"
        self.phone = self.root / "original" / "phone"
        self.standard_pc = self.root / "standard" / "pc"
        self.standard_phone = self.root / "standard" / "phone"
        self.pc.mkdir(parents=True)
        self.phone.mkdir(parents=True)
        self.plan_path = self.root / "plan.csv"
        self.mapping_path = self.root / "mapping.csv"
        self.resolved_path = self.root / "resolved.csv"
        self.json_path = self.root / "manifest.json"
        self.csv_path = self.root / "manifest.csv"
        self.rows = _plan_rows()

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def _write_inputs(self, *, recordings: bool = True) -> None:
        self._write_csv(self.plan_path, self.rows)
        mappings = [
            {
                "plan_id": row["plan_id"],
                "sample_id": row["sample_id"],
                "device_code": row["device_code"],
                "script_id": row["script_id"],
                "recording_condition": row["recording_condition"],
                "repetition_index": row["repetition_index"],
                "expected_original_filename": row["expected_original_filename"],
                "source_filename": "",
                "source_relative_path": "",
                "mapping_status": "needs_manual_mapping",
                "mapping_note": "",
                "source_sha256": "",
            }
            for row in self.rows
        ]
        self._write_csv(self.mapping_path, mappings)
        if recordings:
            for marker, row in enumerate(self.rows, 1):
                if row["device_code"] == "DEV_PC_MIC_01":
                    path = self.pc / (
                        Path(row["expected_original_filename"]).stem + ".m4a"
                    )
                else:
                    path = self.phone / row["expected_original_filename"]
                _write_wav(path, marker)

    @staticmethod
    def _fake_converter(
        source: Path, destination: Path, duration: float = 0.05
    ) -> list[str]:
        _write_wav(
            destination,
            7,
            rate=16000,
            channels=1,
            width=2,
            duration=duration,
        )
        return []

    def _resolve(self) -> tuple[list[dict], dict]:
        return prepare.resolve_source_mappings(
            self.rows, self.pc, self.phone, self.root
        )

    def _prepare(self, **kwargs):
        return prepare.prepare_recordings(
            self.plan_path,
            self.mapping_path,
            self.pc,
            self.phone,
            self.standard_pc,
            self.standard_phone,
            self.root,
            converter=self._fake_converter,
            **kwargs,
        )

    def test_exact_filename_match(self) -> None:
        self._write_inputs()
        mappings, _ = self._resolve()
        phone = next(row for row in mappings if row["device_code"] == "DEV_PHONE_01")
        self.assertEqual(phone["mapping_status"], "exact_filename_match")

    def test_exact_stem_m4a_match(self) -> None:
        self._write_inputs()
        mappings, _ = self._resolve()
        pc = next(row for row in mappings if row["device_code"] == "DEV_PC_MIC_01")
        self.assertEqual(
            pc["mapping_status"], "exact_stem_supported_extension_match"
        )

    def test_stem_candidate_zero_is_unmatched(self) -> None:
        self._write_inputs()
        first_pc = next(row for row in self.rows if row["device_code"] == "DEV_PC_MIC_01")
        (self.pc / (Path(first_pc["expected_original_filename"]).stem + ".m4a")).unlink()
        mappings, _ = self._resolve()
        result = next(row for row in mappings if row["plan_id"] == first_pc["plan_id"])
        self.assertEqual(result["mapping_status"], "unmatched")

    def test_multiple_stem_candidates_are_ambiguous(self) -> None:
        self._write_inputs()
        first_pc = next(row for row in self.rows if row["device_code"] == "DEV_PC_MIC_01")
        stem = Path(first_pc["expected_original_filename"]).stem
        _write_wav(self.pc / f"{stem}.aac", 99)
        mappings, _ = self._resolve()
        result = next(row for row in mappings if row["plan_id"] == first_pc["plan_id"])
        self.assertEqual(result["mapping_status"], "ambiguous")

    def test_other_device_folder_candidate_is_excluded(self) -> None:
        self._write_inputs()
        first_pc = next(row for row in self.rows if row["device_code"] == "DEV_PC_MIC_01")
        stem = Path(first_pc["expected_original_filename"]).stem
        (self.pc / f"{stem}.m4a").unlink()
        _write_wav(self.phone / f"{stem}.m4a", 88)
        mappings, _ = self._resolve()
        result = next(row for row in mappings if row["plan_id"] == first_pc["plan_id"])
        self.assertEqual(result["mapping_status"], "unmatched")

    def test_source_cannot_be_mapped_twice(self) -> None:
        self._write_inputs()
        duplicate_plan = dict(self.rows[0])
        duplicate_plan["plan_id"] = "DUPLICATE"
        mappings, _ = prepare.resolve_source_mappings(
            [self.rows[0], duplicate_plan], self.pc, self.phone, self.root
        )
        self.assertEqual(mappings[1]["mapping_status"], "ambiguous")

    def test_all_24_sources_are_mapped(self) -> None:
        self._write_inputs()
        _, summary = self._resolve()
        self.assertEqual(summary["mapped_total"], 24)

    def test_pc_12_are_stem_matches(self) -> None:
        self._write_inputs()
        _, summary = self._resolve()
        self.assertEqual(summary["exact_stem_supported_extension_match"], 12)

    def test_phone_12_are_exact_matches(self) -> None:
        self._write_inputs()
        _, summary = self._resolve()
        self.assertEqual(summary["exact_filename_match"], 12)

    def test_real_m4a_converts_to_wav(self) -> None:
        source = self.pc / "real.m4a"
        destination = self.root / "converted.wav"
        _write_real_m4a(source)
        warnings = prepare.convert_to_temporary(source, destination)
        inspected = prepare.inspect_standard_wav(destination)
        self.assertTrue(inspected["valid"])
        self.assertIsInstance(warnings, list)

    def test_stereo_is_converted_to_mono(self) -> None:
        source = self.pc / "real.m4a"
        destination = self.root / "converted.wav"
        _write_real_m4a(source)
        prepare.convert_to_temporary(source, destination)
        self.assertEqual(prepare.inspect_standard_wav(destination)["channels"], 1)

    def test_48khz_is_converted_to_16khz(self) -> None:
        source = self.pc / "real.m4a"
        destination = self.root / "converted.wav"
        _write_real_m4a(source)
        prepare.convert_to_temporary(source, destination)
        self.assertEqual(prepare.inspect_standard_wav(destination)["sample_rate"], 16000)

    def test_output_is_signed_16_bit_pcm(self) -> None:
        path = self.root / "standard.wav"
        self._fake_converter(path, path)
        inspected = prepare.inspect_standard_wav(path)
        self.assertEqual(inspected["format"], "WAV/PCM_S16LE")
        self.assertEqual(inspected["bit_depth"], 16)

    def test_output_duration_is_positive(self) -> None:
        path = self.root / "standard.wav"
        self._fake_converter(path, path)
        self.assertGreater(prepare.inspect_standard_wav(path)["duration_sec"], 0)

    def _one_plan_mapping(self) -> tuple[dict, dict]:
        self._write_inputs()
        mappings, _ = self._resolve()
        return self.rows[0], mappings[0]

    def test_duration_over_warning_threshold_is_warning(self) -> None:
        plan, mapping = self._one_plan_mapping()

        def converter(source: Path, destination: Path) -> list[str]:
            return self._fake_converter(source, destination, duration=0.25)

        row = prepare.prepare_one_recording(
            plan,
            mapping,
            self.root,
            self.standard_pc,
            self.standard_phone,
            duration_warning_sec=0.10,
            duration_failure_sec=1.0,
            converter=converter,
        )
        self.assertEqual(row["conversion_status"], "converted")
        self.assertTrue(any("DURATION_DIFFERENCE_WARNING" in item for item in row["warnings"]))

    def test_duration_at_least_one_second_fails(self) -> None:
        plan, mapping = self._one_plan_mapping()

        def converter(source: Path, destination: Path) -> list[str]:
            return self._fake_converter(source, destination, duration=1.2)

        row = prepare.prepare_one_recording(
            plan,
            mapping,
            self.root,
            self.standard_pc,
            self.standard_phone,
            converter=converter,
        )
        self.assertEqual(row["conversion_status"], "validation_failed")
        self.assertIn("DURATION_MISMATCH", row["error"])

    def test_atomic_replace_uses_temporary_wav(self) -> None:
        plan, mapping = self._one_plan_mapping()
        observed: list[Path] = []

        def converter(source: Path, destination: Path) -> list[str]:
            observed.append(destination)
            self._fake_converter(source, destination)
            self.assertNotEqual(destination.name, plan["expected_analysis_wav_filename"])
            return []

        with mock.patch.object(prepare.os, "replace", wraps=prepare.os.replace) as replaced:
            row = prepare.prepare_one_recording(
                plan,
                mapping,
                self.root,
                self.standard_pc,
                self.standard_phone,
                converter=converter,
            )
        self.assertEqual(row["conversion_status"], "converted")
        replaced.assert_called_once()
        self.assertIn(".tmp.wav", observed[0].name)

    def test_existing_valid_wav_is_skipped(self) -> None:
        plan, mapping = self._one_plan_mapping()
        destination = self.standard_pc / plan["expected_analysis_wav_filename"]
        self._fake_converter(destination, destination)
        converter = mock.Mock(side_effect=AssertionError("must not convert"))
        row = prepare.prepare_one_recording(
            plan,
            mapping,
            self.root,
            self.standard_pc,
            self.standard_phone,
            converter=converter,
        )
        self.assertEqual(row["conversion_status"], "skipped_existing_valid")
        converter.assert_not_called()

    def test_existing_invalid_wav_is_error(self) -> None:
        plan, mapping = self._one_plan_mapping()
        destination = self.standard_pc / plan["expected_analysis_wav_filename"]
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"bad")
        row = prepare.prepare_one_recording(
            plan,
            mapping,
            self.root,
            self.standard_pc,
            self.standard_phone,
            converter=self._fake_converter,
        )
        self.assertEqual(row["conversion_status"], "validation_failed")
        self.assertIn("DESTINATION_ALREADY_INVALID", row["error"])

    def test_overwrite_replaces_existing_wav(self) -> None:
        plan, mapping = self._one_plan_mapping()
        destination = self.standard_pc / plan["expected_analysis_wav_filename"]
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"bad")
        row = prepare.prepare_one_recording(
            plan,
            mapping,
            self.root,
            self.standard_pc,
            self.standard_phone,
            overwrite=True,
            converter=self._fake_converter,
        )
        self.assertEqual(row["conversion_status"], "converted")
        self.assertTrue(prepare.inspect_standard_wav(destination)["valid"])

    def test_original_sha256_is_preserved(self) -> None:
        self._write_inputs()
        sources = list(self.pc.iterdir()) + list(self.phone.iterdir())
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        self._prepare()
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        self.assertEqual(before, after)

    def test_existing_inventory_sha256_is_preserved(self) -> None:
        self._write_inputs()
        inventory_path = self.root / "inventory.json"
        inventory_path.write_text('{"immutable": true}', encoding="utf-8")
        before = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
        self._prepare()
        self.assertEqual(before, hashlib.sha256(inventory_path.read_bytes()).hexdigest())

    def test_existing_mapping_sha256_is_preserved(self) -> None:
        self._write_inputs()
        before = hashlib.sha256(self.mapping_path.read_bytes()).hexdigest()
        self._prepare()
        self.assertEqual(before, hashlib.sha256(self.mapping_path.read_bytes()).hexdigest())

    def test_standard_wav_total_is_24(self) -> None:
        self._write_inputs()
        manifest, _, _ = self._prepare()
        self.assertEqual(
            manifest["conversion_summary"]["pc_standard_wav_count"]
            + manifest["conversion_summary"]["phone_standard_wav_count"],
            24,
        )

    def test_standard_pc_count_is_12(self) -> None:
        self._write_inputs()
        manifest, _, _ = self._prepare()
        self.assertEqual(manifest["conversion_summary"]["pc_standard_wav_count"], 12)

    def test_standard_phone_count_is_12(self) -> None:
        self._write_inputs()
        manifest, _, _ = self._prepare()
        self.assertEqual(manifest["conversion_summary"]["phone_standard_wav_count"], 12)

    def test_device_pair_count_is_12(self) -> None:
        self._write_inputs()
        manifest, _, _ = self._prepare()
        self.assertEqual(manifest["device_pair_summary"]["pair_count"], 12)

    def test_each_pair_has_two_devices(self) -> None:
        groups: dict[tuple, set[str]] = defaultdict(set)
        for row in self.rows:
            key = (
                row["speaker_code"],
                row["session_id"],
                row["script_id"],
                row["recording_condition"],
                row["repetition_index"],
            )
            groups[key].add(row["device_code"])
        self.assertTrue(
            all(devices == {"DEV_PC_MIC_01", "DEV_PHONE_01"} for devices in groups.values())
        )

    def test_pair_destination_names_differ_only_by_device(self) -> None:
        self._write_inputs()
        manifest, _, _ = self._prepare()
        self.assertEqual(manifest["device_pair_summary"]["invalid_pair_count"], 0)

    def test_json_is_strict(self) -> None:
        self._write_inputs()
        manifest, mappings, conversions = self._prepare()
        prepare.write_preparation_outputs(
            self.resolved_path,
            self.json_path,
            self.csv_path,
            manifest,
            mappings,
            conversions,
        )
        parsed = json.loads(
            self.json_path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
        self.assertEqual(parsed["schema_version"], "1.0")

    def test_csv_outputs_have_utf8_bom(self) -> None:
        self._write_inputs()
        manifest, mappings, conversions = self._prepare()
        prepare.write_preparation_outputs(
            self.resolved_path,
            self.json_path,
            self.csv_path,
            manifest,
            mappings,
            conversions,
        )
        self.assertTrue(self.resolved_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_atomic_manifest_outputs_leave_no_temp_files(self) -> None:
        self._write_inputs()
        manifest, mappings, conversions = self._prepare()
        prepare.write_preparation_outputs(
            self.resolved_path,
            self.json_path,
            self.csv_path,
            manifest,
            mappings,
            conversions,
        )
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.iterdir()))

    def test_cli_exit_codes_zero_one_two(self) -> None:
        self._write_inputs()
        args = [
            "--plan",
            str(self.plan_path),
            "--mapping",
            str(self.mapping_path),
            "--pc-dir",
            str(self.pc),
            "--phone-dir",
            str(self.phone),
            "--standard-pc-dir",
            str(self.standard_pc),
            "--standard-phone-dir",
            str(self.standard_phone),
            "--relative-root",
            str(self.root),
            "--resolved-mapping-output",
            str(self.resolved_path),
            "--manifest-json-output",
            str(self.json_path),
            "--manifest-csv-output",
            str(self.csv_path),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = prepare.main(args)
            bad_args = list(args)
            bad_args[1] = str(self.root / "missing-plan.csv")
            failure = prepare.main(bad_args)
            with self.assertRaises(SystemExit) as raised:
                prepare.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))

    def test_required_error_codes_are_declared(self) -> None:
        expected = {
            "COLLECTION_PLAN_NOT_FOUND",
            "COLLECTION_PLAN_INVALID",
            "SOURCE_RECORDING_NOT_FOUND",
            "SOURCE_MAPPING_AMBIGUOUS",
            "SOURCE_MAPPING_FAILED",
            "FFMPEG_NOT_FOUND",
            "AUDIO_CONVERSION_FAILED",
            "STANDARD_WAV_INVALID",
            "DURATION_MISMATCH",
            "DESTINATION_ALREADY_INVALID",
            "CONVERSION_MANIFEST_WRITE_FAILED",
            "RECORDING_PREPARATION_FAILED",
        }
        self.assertTrue(expected.issubset(prepare.REQUIRED_ERROR_CODES))


if __name__ == "__main__":
    unittest.main()
