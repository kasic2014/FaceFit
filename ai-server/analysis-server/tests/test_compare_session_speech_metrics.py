"""Tests for device, repeatability, and human annotation comparisons."""

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

import compare_session_speech_metrics as compare  # noqa: E402
from create_natural_transcript_review import REVIEW_FIELDS  # noqa: E402


def _results() -> list[dict]:
    rows = []
    for script in ("SCRIPT001", "SCRIPT002"):
        for condition in ("clean", "natural"):
            for repetition in (1, 2, 3):
                pair = f"SPK001|SESSION001|{script}|{condition}|{repetition}"
                for device in ("DEV_PC_MIC_01", "DEV_PHONE_01"):
                    value = repetition + (0.1 if device == "DEV_PHONE_01" else 0)
                    words = [
                        {"word": "뒤", "start": 1.0, "end": 1.2},
                        {"word": "우선순위에", "start": 2.0, "end": 2.5},
                    ]
                    if script == "SCRIPT002" and condition == "natural":
                        storage_duration = {1: 0.9, 2: 0.4, 3: 0.4}[repetition]
                        data_duration = {1: 0.8, 2: 0.9, 3: 1.0}[repetition]
                        words += [
                            {"word": "저장", "start": 3.0, "end": 3.0 + storage_duration},
                            {"word": "데이터가", "start": 5.0, "end": 5.0 + data_duration},
                        ]
                    pause = {
                        "previous_word": "뒤",
                        "next_word": "우선순위에",
                        "acoustic_silence_start_sec": 1.2,
                        "acoustic_silence_end_sec": 2.0,
                        "acoustic_silence_duration_sec": 0.8,
                    }
                    rows.append(
                        {
                            "sample_id": f"{script}_{condition}_{repetition}_{device}",
                            "script_id": script,
                            "recording_condition": condition,
                            "repetition_index": repetition,
                            "device_code": device,
                            "capture_pair_key": pair,
                            "audio_duration_sec": 20 + value,
                            "speech_duration_sec": 15 + value,
                            "speaking_ratio": 0.7,
                            "speech_rate_wpm": 100 + value,
                            "pause_count": 2,
                            "total_pause_duration_sec": value,
                            "max_pause_duration_sec": value / 2,
                            "long_pause_count": 0,
                            "probable_omitted_vocalization_count": 1,
                            "uncertain_gap_vocalization_count": 0,
                            "clipping_ratio": 0.0,
                            "noise_floor_dbfs": -50 + value,
                            "background_noise_warning": False,
                            "pause_events": [pause] if script == "SCRIPT001" and condition == "natural" and repetition == 2 else [],
                            "word_timestamps": words,
                            "existing_speech_metrics": {"audio_quality": {"reliability_flags": []}},
                        }
                    )
    return rows


def _review_rows() -> list[dict]:
    notes = {
        ("SCRIPT001", "1"): "원래 대본의 '문제의'를 실제 발화에서 생략함.",
        ("SCRIPT001", "2"): "'공유한 뒤'와 '우선순위에 따라' 사이에 침묵 구간이 있음.",
        ("SCRIPT001", "3"): "특이사항 없음.",
        ("SCRIPT002", "1"): "'프로'를 실제 발화에서 생략함.\n'저장'의 발음이 길게 늘어짐.",
        ("SCRIPT002", "2"): "특이사항 없음.",
        ("SCRIPT002", "3"): "'데이터가'의 발음이 길게 늘어짐.",
    }
    rows = []
    for script in ("SCRIPT001", "SCRIPT002"):
        for repetition in ("1", "2", "3"):
            base = {field: "" for field in REVIEW_FIELDS}
            base.update(
                {
                    "capture_key": f"SPK001|SESSION001|{script}|natural|{repetition}",
                    "speaker_code": "SPK001",
                    "session_id": "SESSION001",
                    "script_id": script,
                    "repetition_index": repetition,
                    "human_transcript": "전사",
                    "human_transcript_note": notes[(script, repetition)],
                    "review_status": "completed",
                    "reviewer_confirmed": "true",
                }
            )
            rows.append(base)
    return rows


class CompareSessionSpeechMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.results = _results()
        self.review = self.root / "review.csv"
        with self.review.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(_review_rows())

    def test_device_pair_count_12(self) -> None:
        rows, valid = compare.build_pair_comparisons(self.results)
        self.assertEqual(valid, 12)
        self.assertEqual(len(rows), 12 * len(compare.PAIR_METRICS))

    def test_pair_numeric_difference(self) -> None:
        difference = compare.metric_difference(10, 12)
        self.assertEqual(difference["absolute_difference"], 2)
        self.assertAlmostEqual(difference["relative_difference"], 1 / 6)

    def test_pair_comparison_is_symmetric(self) -> None:
        self.assertEqual(compare.metric_difference(10, 12)["relative_difference"], compare.metric_difference(12, 10)["relative_difference"])

    def test_repeatability_has_eight_groups(self) -> None:
        rows = compare.build_repeatability(self.results)
        groups = {(r["script_id"], r["recording_condition"], r["device_code"]) for r in rows}
        self.assertEqual(len(groups), 8)

    def test_repeatability_each_group_has_three(self) -> None:
        self.assertTrue(all(row["repetition_count"] == 3 for row in compare.build_repeatability(self.results)))

    def test_median(self) -> None:
        self.assertEqual(compare.median_mad([1, 2, 3])[0], 2)

    def test_mad(self) -> None:
        self.assertEqual(compare.median_mad([1, 2, 3])[1], 1)

    def test_omission_count_two(self) -> None:
        _, counts = compare.load_human_annotations(self.review)
        self.assertEqual(counts["omission"], 2)

    def test_silence_count_one(self) -> None:
        _, counts = compare.load_human_annotations(self.review)
        self.assertEqual(counts["silence"], 1)

    def test_elongation_count_two(self) -> None:
        _, counts = compare.load_human_annotations(self.review)
        self.assertEqual(counts["elongation"], 2)

    def test_filler_count_zero(self) -> None:
        _, counts = compare.load_human_annotations(self.review)
        self.assertEqual(counts["filler"], 0)

    def test_omission_is_content_difference(self) -> None:
        annotations, _ = compare.load_human_annotations(self.review)
        self.assertTrue(all(a["classification"] == "script_to_spoken_content_difference" for a in annotations if a["annotation_type"] == "omission"))

    def test_silence_detected_by_both_devices(self) -> None:
        result = compare.validate_silence_annotation(self.results)
        self.assertEqual(result["validation_status"], "detected_by_both_devices")

    def test_silence_device_values(self) -> None:
        result = compare.validate_silence_annotation(self.results)
        self.assertEqual(result["devices"]["DEV_PC_MIC_01"]["pause_duration"], 0.8)
        self.assertEqual(result["devices"]["DEV_PHONE_01"]["pause_duration"], 0.8)

    def test_elongation_is_experimental(self) -> None:
        rows = compare.elongation_diagnostics(self.results)
        self.assertTrue(all(row["experimental"] for row in rows))
        self.assertTrue(all(not row["interview_score_use"] for row in rows))

    def test_storage_is_outlier_candidate(self) -> None:
        row = next(r for r in compare.elongation_diagnostics(self.results) if r["target"] == "저장")
        self.assertEqual(row["validation_status"], "duration_outlier_candidate")

    def test_data_word_not_outlier(self) -> None:
        row = next(r for r in compare.elongation_diagnostics(self.results) if r["target"] == "데이터가")
        self.assertEqual(row["validation_status"], "duration_not_outlier")

    def test_missing_word_status(self) -> None:
        modified = [dict(row, word_timestamps=[]) for row in self.results]
        rows = compare.elongation_diagnostics(modified)
        self.assertTrue(all(row["validation_status"] == "timestamp_word_not_found" for row in rows))

    def _write_manifest(self) -> Path:
        files = []
        for index, result in enumerate(self.results):
            output = self.root / "metrics" / f"{index}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            files.append({"output_json": output.relative_to(self.root).as_posix(), "error_code": ""})
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"files": files}), encoding="utf-8")
        return manifest

    def _compare(self):
        return compare.compare_session(
            self._write_manifest(),
            self.review,
            self.root,
            self.root / "summary.json",
            self.root / "summary.csv",
            self.root / "pairs.csv",
            self.root / "human.json",
            self.root / "human.csv",
        )

    def test_summary_counts(self) -> None:
        result = self._compare()
        self.assertEqual(result["summary"]["total_files"], 24)
        self.assertEqual(result["summary"]["valid_pairs"], 12)

    def test_strict_json_and_csv_bom(self) -> None:
        self._compare()
        json.loads((self.root / "summary.json").read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        for name in ("summary.csv", "pairs.csv", "human.csv"):
            self.assertTrue((self.root / name).read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_atomic_outputs(self) -> None:
        self._compare()
        self.assertFalse(any(path.name.endswith(".tmp") for path in self.root.rglob("*")))

    def test_cli_exit_codes_zero_one_two(self) -> None:
        args = ["--metrics-manifest", "a", "--human-review", "b", "--relative-root", "c", "--summary-json-output", "d", "--summary-csv-output", "e", "--pair-csv-output", "f", "--human-json-output", "g", "--human-csv-output", "h"]
        with mock.patch.object(compare, "compare_session", return_value={"summary": {}, "error": None}), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            success = compare.main(args)
            with mock.patch.object(compare, "compare_session", side_effect=compare.SessionMetricsError("SESSION_SPEECH_METRICS_FAILED", "x")):
                failure = compare.main(args)
            with self.assertRaises(SystemExit) as raised:
                compare.main([])
        self.assertEqual((success, failure, raised.exception.code), (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
