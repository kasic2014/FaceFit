from __future__ import annotations

import copy
import unittest
from dataclasses import replace

from app.vision.data_quality_gate import evaluate_data_quality_gate
from app.vision.evidence_loaders import EvidenceRegistryLoader
from app.vision.evidence_registry import EvidenceExecutionMode
from app.vision.metric_registry import (
    FaceFitMetricRegistry,
    MetricDefinition,
    MetricResolutionFailureReason,
    MetricValueResolution,
    build_stage10_metric_registry,
)
from app.vision.scoring_models import MetricScoreStatus
from app.vision.scoring_strategy import TestFixtureBandScoringStrategy
from app.vision.threshold_models import ThresholdBand

from tests.test_evidence_models import rule


FIXTURE_ROOT = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "config"
    / "evidence"
    / "fixtures"
)


def aggregate():
    summary = {
        "available": True,
        "count": 50,
        "absolute_p95": 12.5,
    }
    availability = {
        "available": True,
        "availability_ratio": 0.9,
        "longest_missing_duration_ms": 200,
    }
    return {
        "head_pose": {
            "relative_yaw_deg": dict(summary),
            "relative_pitch_deg": dict(summary),
            "relative_roll_deg": dict(summary),
            "availability": dict(availability),
        },
        "posture": {
            "relative_shoulder_tilt_deg": dict(summary),
            "shoulder_center_velocity_norm_per_sec": {
                "available": True,
                "count": 50,
                "p95": 0.2,
            },
            "relative_nose_shoulder_offset_x_norm": dict(summary),
            "shoulder_availability": dict(availability),
            "nose_alignment_availability": dict(availability),
        },
        "data_quality": {
            "available": True,
            "total_frame_count": 50,
            "head_pose_availability_ratio": 0.9,
            "posture_availability_ratio": 0.9,
            "quality_score": 0.95,
            "target_continuity_ratio": 1.0,
        },
    }


def resolution(**overrides):
    values = {
        "available": True,
        "metric_id": "HEAD_RELATIVE_YAW_ABS_P95_DEG",
        "metric_path": "head_pose.relative_yaw_deg.absolute_p95",
        "value": 12.5,
        "unit": "DEGREE",
        "sample_count": 50,
        "availability_ratio": 0.9,
        "longest_missing_duration_ms": 200,
        "interval_quality_score": 0.95,
        "target_continuity_ratio": 1.0,
        "failure_reason": None,
    }
    values.update(overrides)
    return MetricValueResolution(**values)


class MetricRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_stage10_metric_registry()

    def test_stage10_registry_has_stable_unique_definitions(self):
        definitions = self.registry.definitions
        self.assertEqual(len(definitions), 8)
        self.assertEqual(
            [item.metric_id for item in definitions],
            sorted(item.metric_id for item in definitions),
        )
        self.registry.validate_paths(aggregate())

    def test_duplicate_metric_and_unknown_metric_are_rejected(self):
        definition = self.registry.definitions[0]
        with self.assertRaises(ValueError):
            FaceFitMetricRegistry((definition, definition))
        with self.assertRaises(KeyError):
            self.registry.get("UNKNOWN")

    def test_resolver_returns_value_unit_and_quality_inputs(self):
        result = self.registry.resolve(
            aggregate(),
            "HEAD_RELATIVE_YAW_ABS_P95_DEG",
        )
        self.assertTrue(result.available)
        self.assertEqual(result.value, 12.5)
        self.assertEqual(result.unit, "DEGREE")
        self.assertEqual(result.sample_count, 50)
        self.assertEqual(result.availability_ratio, 0.9)
        self.assertEqual(result.longest_missing_duration_ms, 200)

    def test_quality_metric_uses_total_frame_count_and_own_ratio(self):
        result = self.registry.resolve(
            aggregate(),
            "QUALITY_HEAD_AVAILABILITY_RATIO",
        )
        self.assertEqual(result.value, 0.9)
        self.assertEqual(result.sample_count, 50)
        self.assertEqual(result.availability_ratio, 0.9)

    def test_resolver_reports_explicit_failure_reasons(self):
        cases = []
        missing_path = aggregate()
        del missing_path["head_pose"]["relative_yaw_deg"]
        cases.append(
            (
                missing_path,
                MetricResolutionFailureReason.METRIC_PATH_NOT_FOUND.value,
            )
        )
        missing_availability = aggregate()
        del missing_availability["head_pose"]["availability"]
        cases.append(
            (
                missing_availability,
                MetricResolutionFailureReason
                .AVAILABILITY_PATH_NOT_FOUND.value,
            )
        )
        unavailable = aggregate()
        unavailable["head_pose"]["availability"]["available"] = False
        cases.append(
            (
                unavailable,
                MetricResolutionFailureReason.METRIC_UNAVAILABLE.value,
            )
        )
        for value, expected in ((None, "METRIC_VALUE_NULL"), (True, "METRIC_VALUE_TYPE_INVALID"), (float("nan"), "METRIC_VALUE_NON_FINITE")):
            payload = aggregate()
            payload["head_pose"]["relative_yaw_deg"]["absolute_p95"] = value
            cases.append((payload, expected))
        for payload, expected in cases:
            with self.subTest(expected=expected):
                result = self.registry.resolve(
                    payload,
                    "HEAD_RELATIVE_YAW_ABS_P95_DEG",
                )
                self.assertFalse(result.available)
                self.assertEqual(result.failure_reason, expected)

    def test_metric_definition_rejects_invalid_unit_and_empty_path_component(self):
        definition = self.registry.definitions[0]
        with self.assertRaises(ValueError):
            MetricDefinition(**{**definition.to_dict(), "unit": "PIXEL"})
        with self.assertRaises(ValueError):
            MetricDefinition(
                **{**definition.to_dict(), "metric_path": "head_pose..yaw"}
            )


class GateAndFixtureScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metric_registry = build_stage10_metric_registry()
        cls.evidence_registry = EvidenceRegistryLoader.load_directory(
            FIXTURE_ROOT,
            metric_registry=cls.metric_registry,
            execution_mode=EvidenceExecutionMode.TEST_FIXTURE_MODE.value,
        )
        cls.profile = cls.evidence_registry.profiles[
            ("EVIDENCE_FIX_HEAD", "1.0.0")
        ]
        cls.threshold_profile = cls.evidence_registry.threshold_profiles[
            ("THRESHOLD_FIX_HEAD", "1.0.0")
        ]
        cls.threshold_rule = next(
            item
            for item in cls.threshold_profile.rules
            if item.metric_id == "HEAD_RELATIVE_YAW_ABS_P95_DEG"
        )
        cls.metric = cls.metric_registry.get(
            "HEAD_RELATIVE_YAW_ABS_P95_DEG"
        )
        cls.provenance = cls.evidence_registry.build_provenance(
            evidence_profile=cls.profile,
            threshold_profile=cls.threshold_profile,
            rule_id=cls.threshold_rule.rule_id,
            metric_id=cls.metric.metric_id,
        )
        cls.strategy = TestFixtureBandScoringStrategy()

    def test_gate_reports_every_failed_constraint(self):
        result = evaluate_data_quality_gate(
            resolution(
                sample_count=1,
                availability_ratio=0.1,
                longest_missing_duration_ms=5000,
                interval_quality_score=0.1,
                target_continuity_ratio=0.1,
            ),
            self.threshold_rule,
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failure_reasons), 5)

    def test_fixture_score_has_explicit_fixture_field_and_provenance(self):
        result = self.strategy.score(
            resolution(),
            self.metric,
            self.threshold_rule,
            self.threshold_profile,
            self.profile,
            self.provenance,
        )
        payload = result.to_dict()
        self.assertEqual(result.status, MetricScoreStatus.SCORED_TEST_FIXTURE.value)
        self.assertEqual(result.matched_band_id, "BAND_FIX_YAW_B")
        self.assertEqual(payload["test_fixture_score"], 50.0)
        self.assertNotIn("score", {key for key in payload if key != "test_fixture_score"})
        self.assertEqual(
            payload["provenance"]["source_ids"],
            ("SRC_FIXTURE_HEAD_001",),
        )

    def test_fixture_score_rejects_unavailable_and_insufficient_data(self):
        unavailable = self.strategy.score(
            resolution(available=False, value=None, failure_reason="NO_VALUE"),
            self.metric,
            self.threshold_rule,
            self.threshold_profile,
            self.profile,
            self.provenance,
        )
        self.assertEqual(unavailable.status, "METRIC_UNAVAILABLE")
        insufficient = self.strategy.score(
            resolution(sample_count=0),
            self.metric,
            self.threshold_rule,
            self.threshold_profile,
            self.profile,
            self.provenance,
        )
        self.assertEqual(insufficient.status, "INSUFFICIENT_DATA")
        self.assertIsNone(insufficient.test_fixture_score)

    def test_fixture_score_rejects_unit_metric_and_profile_mismatch(self):
        unit = self.strategy.score(
            resolution(unit="RATIO"),
            self.metric,
            self.threshold_rule,
            self.threshold_profile,
            self.profile,
            self.provenance,
        )
        self.assertEqual(unit.status, "UNIT_MISMATCH")
        metric = self.strategy.score(
            replace(resolution(), metric_id="OTHER"),
            self.metric,
            self.threshold_rule,
            self.threshold_profile,
            self.profile,
            self.provenance,
        )
        self.assertEqual(metric.status, "INVALID_RULE")
        mismatch_profile = replace(self.profile, version="1.0.1")
        mismatch = self.strategy.score(
            resolution(),
            self.metric,
            self.threshold_rule,
            self.threshold_profile,
            mismatch_profile,
            self.provenance,
        )
        self.assertEqual(mismatch.status, "PROFILE_VERSION_MISMATCH")

    def test_fixture_strategy_rejects_non_fixture_statuses(self):
        evidence = self.strategy.score(
            resolution(),
            self.metric,
            self.threshold_rule,
            self.threshold_profile,
            replace(self.profile, status="DRAFT"),
            self.provenance,
        )
        self.assertEqual(evidence.status, "EVIDENCE_NOT_APPROVED")
        threshold = self.strategy.score(
            resolution(),
            self.metric,
            self.threshold_rule,
            replace(self.threshold_profile, status="DRAFT"),
            self.profile,
            self.provenance,
        )
        self.assertEqual(threshold.status, "THRESHOLD_NOT_APPROVED")

    def test_gap_produces_no_matching_band(self):
        gap_rule = rule(
            bands=(
                ThresholdBand("A", "a", None, 10, False, True, 1),
                ThresholdBand("B", "b", 20, None, True, False, 0),
            ),
            evidence_profile_id="EVIDENCE_FIX_HEAD",
            allow_band_gaps=True,
        )
        profile = replace(self.threshold_profile, rules=(gap_rule,))
        result = self.strategy.score(
            resolution(value=15),
            self.metric,
            gap_rule,
            profile,
            self.profile,
            self.provenance,
        )
        self.assertEqual(result.status, "NO_MATCHING_BAND")


if __name__ == "__main__":
    unittest.main()
