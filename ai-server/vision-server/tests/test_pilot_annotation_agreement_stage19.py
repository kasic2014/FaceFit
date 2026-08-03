from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


VISION_ROOT = Path(__file__).resolve().parents[1]
PATCH_MODULE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "vision"
    / "pilot_annotation_agreement.py"
)
if str(VISION_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_ROOT))

spec = importlib.util.spec_from_file_location(
    "stage19_patch_module",
    PATCH_MODULE,
)
assert spec is not None and spec.loader is not None
stage19 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage19)

from app.vision.pilot_annotation_package import (  # noqa: E402
    build_empty_template,
    registry_from_dict,
)
from app.vision.pilot_video_intake import load_strict_json  # noqa: E402


REGISTRY_PATH = (
    VISION_ROOT
    / "config"
    / "data_collection"
    / "fixtures"
    / "annotation_registry.json"
)
METADATA_PATH = (
    VISION_ROOT
    / "data"
    / "pilot"
    / "incoming"
    / "PTC_000001_SES_000001.metadata.json"
)
PACKAGE_DIR = (
    VISION_ROOT
    / "data"
    / "output"
    / "pilot_annotation"
    / "SES_000001"
)


def event(
    rater_id: str,
    number: int,
    *,
    answer_id: str = "ANS_000001",
    interval_id: str = "INT_ANSWER_001",
    label_id: str = "HEAD_TURN_LEFT",
    direction: str | None = "LEFT",
    start: int = 12000,
    end: int = 13000,
) -> dict:
    return {
        "annotation_event_id": f"{rater_id}_EVT_{number:06d}",
        "answer_id": answer_id,
        "interval_id": interval_id,
        "label_id": label_id,
        "direction": direction,
        "start_timestamp_ms": start,
        "end_timestamp_ms": end,
        "rater_confidence": None,
        "note": None,
    }


def submission(rater_id: str, events: list[dict]) -> dict:
    value = build_empty_template(rater_id)
    value["completed_at"] = "2026-07-30T00:00:00+00:00"
    value["events"] = events
    return value


class Stage19ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = registry_from_dict(load_strict_json(REGISTRY_PATH))
        cls.metadata = load_strict_json(METADATA_PATH)

    def validate(self, value: dict, rater_id: str = "RATER_A") -> dict:
        return stage19.validate_submission(
            value,
            expected_rater_id=rater_id,
            answers=self.metadata["answers"],
            registry=self.registry,
        )

    def test_normal_rater_a_and_b_inputs(self) -> None:
        a = submission("RATER_A", [event("RATER_A", 1)])
        b = submission("RATER_B", [event("RATER_B", 1)])
        self.assertEqual(self.validate(a)["event_count"], 1)
        self.assertEqual(self.validate(b, "RATER_B")["event_count"], 1)

    def test_empty_event_input_is_valid(self) -> None:
        self.assertEqual(
            self.validate(submission("RATER_A", []))["event_count"],
            0,
        )

    def test_bad_answer_reference_is_blocked(self) -> None:
        value = submission(
            "RATER_A",
            [event("RATER_A", 1, answer_id="ANS_BAD")],
        )
        with self.assertRaises(stage19.Stage19ValidationError):
            self.validate(value)

    def test_bad_label_is_blocked(self) -> None:
        value = submission(
            "RATER_A",
            [event("RATER_A", 1, label_id="UNKNOWN_LABEL")],
        )
        with self.assertRaises(stage19.Stage19ValidationError):
            self.validate(value)

    def test_bad_direction_is_blocked(self) -> None:
        value = submission(
            "RATER_A",
            [event("RATER_A", 1, direction="RIGHT")],
        )
        with self.assertRaises(stage19.Stage19ValidationError):
            self.validate(value)

    def test_bad_time_is_blocked(self) -> None:
        value = submission(
            "RATER_A",
            [event("RATER_A", 1, start=13000, end=13000)],
        )
        with self.assertRaises(stage19.Stage19ValidationError):
            self.validate(value)

    def test_duplicate_event_is_blocked(self) -> None:
        first = event("RATER_A", 1)
        duplicate = deepcopy(first)
        duplicate["annotation_event_id"] = "RATER_A_EVT_000002"
        with self.assertRaises(stage19.Stage19ValidationError):
            self.validate(submission("RATER_A", [first, duplicate]))


class PairwiseCandidateTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        values = stage19.build_pairwise_candidates(
            [event("RATER_A", 1)],
            [event("RATER_B", 1)],
        )
        self.assertEqual(values[0]["raw_temporal_relation"], "EXACT_MATCH")
        self.assertEqual(values[0]["temporal_iou"], 1.0)

    def test_partial_overlap(self) -> None:
        values = stage19.build_pairwise_candidates(
            [event("RATER_A", 1, start=12000, end=13000)],
            [event("RATER_B", 1, start=12500, end=13500)],
        )
        self.assertEqual(values[0]["raw_temporal_relation"], "PARTIAL_MATCH")
        self.assertAlmostEqual(values[0]["temporal_iou"], 1 / 3)
        self.assertEqual(values[0]["overlap_duration_ms"], 500)
        self.assertEqual(values[0]["union_duration_ms"], 1500)

    def test_zero_overlap(self) -> None:
        values = stage19.build_pairwise_candidates(
            [event("RATER_A", 1, start=12000, end=13000)],
            [event("RATER_B", 1, start=14000, end=15000)],
        )
        self.assertEqual(values[0]["raw_temporal_relation"], "ZERO_OVERLAP")
        self.assertEqual(values[0]["temporal_iou"], 0.0)

    def test_one_sided_event_has_no_candidate(self) -> None:
        self.assertEqual(
            stage19.build_pairwise_candidates([event("RATER_A", 1)], []),
            [],
        )

    def test_policy_review_prevents_any_match_selection(self) -> None:
        values = stage19.build_pairwise_candidates(
            [event("RATER_A", 1)],
            [
                event("RATER_B", 1),
                event("RATER_B", 2, start=12050, end=12950),
            ],
        )
        self.assertEqual(len(values), 2)
        self.assertFalse(any(item["selected_as_match"] for item in values))

    def test_outputs_are_finite_or_null(self) -> None:
        values = stage19.build_pairwise_candidates(
            [event("RATER_A", 1)],
            [event("RATER_B", 1)],
        )
        encoded = json.dumps(values, allow_nan=False)
        self.assertNotIn("NaN", encoded)
        self.assertNotIn("Infinity", encoded)

    def test_provenance_is_unverified(self) -> None:
        self.assertEqual(
            stage19.AGREEMENT_CONTEXT,
            "RATER_IDENTITY_UNVERIFIED",
        )


class PackageTests(unittest.TestCase):
    def test_empty_adjudication_template(self) -> None:
        self.assertEqual(
            stage19.adjudication_decision_template(),
            {
                "participant_id": "PTC_000001",
                "session_id": "SES_000001",
                "adjudicator_id": None,
                "decision": "REVIEW_PENDING",
                "completed_at": None,
                "resolved_events": [],
                "notes": None,
            },
        )

    def test_actual_input_hashes_remain_unchanged(self) -> None:
        paths = (
            PACKAGE_DIR / "rater_a" / "annotation_events.json",
            PACKAGE_DIR / "rater_b" / "annotation_events.json",
        )
        before = [
            hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        ]
        for path in paths:
            load_strict_json(path)
        after = [
            hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        ]
        self.assertEqual(before, after)

    def test_strict_json_and_jsonl_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "SES_000001"
            report = stage19.build_stage19_package(
                package_dir=PACKAGE_DIR,
                metadata_path=METADATA_PATH,
                registry_path=REGISTRY_PATH,
                output_dir=output,
            )
            self.assertEqual(
                report["current_status"],
                "agreement_policy_review_required",
            )
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(stage19.OUTPUT_NAMES),
            )
            for path in output.glob("*.json"):
                json.loads(
                    path.read_text("utf-8"),
                    parse_constant=lambda value: self.fail(value),
                )
            validation = load_strict_json(
                output / "input_validation.json"
            )
            self.assertEqual(
                validation["package_directory"],
                "data/output/pilot_annotation/SES_000001",
            )
            self.assertEqual(
                validation["rater_inputs"]["RATER_A"]["path"],
                "rater_a/annotation_events.json",
            )
            self.assertNotIn(
                str(VISION_ROOT),
                json.dumps(validation, ensure_ascii=False),
            )
            jsonl = output / "event_match_results.jsonl"
            for line in jsonl.read_text("utf-8").splitlines():
                json.loads(
                    line,
                    parse_constant=lambda value: self.fail(value),
                )

    def test_invalid_input_stops_with_validation_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            package.mkdir()
            manifest = load_strict_json(
                PACKAGE_DIR / "annotation_package_manifest.json"
            )
            (package / "annotation_package_manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            for subdir, rater_id in (
                ("rater_a", "RATER_A"),
                ("rater_b", "RATER_B"),
            ):
                target = package / subdir
                target.mkdir()
                value = submission(rater_id, [])
                if rater_id == "RATER_B":
                    value["session_id"] = "SES_BAD"
                (target / "annotation_events.json").write_text(
                    json.dumps(value),
                    encoding="utf-8",
                )
            output = root / "out"
            report = stage19.build_stage19_package(
                package_dir=package,
                metadata_path=METADATA_PATH,
                registry_path=REGISTRY_PATH,
                output_dir=output,
            )
            self.assertEqual(
                report["current_status"],
                "rater_annotation_validation_failed",
            )


if __name__ == "__main__":
    unittest.main()
