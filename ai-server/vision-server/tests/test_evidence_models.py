from __future__ import annotations

import math
import unittest

from app.vision.evidence_mapping_models import EvidenceMetricMapping
from app.vision.evidence_models import (
    ApplicabilityScope,
    EvidenceRecord,
    EvidenceSource,
    SYNTHETIC_FIXTURE_NOTICE,
)
from app.vision.evidence_profile_models import EvidenceProfile
from app.vision.threshold_models import (
    MetricThresholdRule,
    ThresholdBand,
    ThresholdProfile,
    validate_threshold_bands,
)


def source(**overrides):
    values = {
        "source_id": "SRC_FIX",
        "source_type": "TECHNICAL_REPORT",
        "title": "Synthetic source",
        "authors": ("Fixture Author",),
        "publication_year": 2026,
        "publisher": None,
        "journal_or_conference": None,
        "doi": "10.1234/fixture",
        "url": "https://example.invalid/fixture",
        "language": "en",
        "study_population": "Synthetic records",
        "sample_size": 0,
        "peer_reviewed": False,
        "access_date": "2026-07-28",
        "status": "TEST_FIXTURE",
        "notes": SYNTHETIC_FIXTURE_NOTICE,
    }
    values.update(overrides)
    return EvidenceSource(**values)


def record(**overrides):
    values = {
        "evidence_id": "EVIDENCE_FIX",
        "source_id": "SRC_FIX",
        "construct_name": "Synthetic construct",
        "measurement_name": "Synthetic metric",
        "statistic_type": "POINT_ESTIMATE",
        "value": 1.0,
        "lower_bound": None,
        "upper_bound": None,
        "unit": "DEGREE",
        "population_scope": "Synthetic",
        "context_scope": "Contract test",
        "extraction_location": "Fixture",
        "extraction_note": SYNTHETIC_FIXTURE_NOTICE,
        "evidence_strength": "NOT_ASSESSED",
        "applicability": "REVIEW_REQUIRED",
        "status": "TEST_FIXTURE",
        "applicability_scope": ApplicabilityScope(
            analysis_fps=5.0,
            measurement_method="Synthetic",
            body_region="Head",
        ),
    }
    values.update(overrides)
    return EvidenceRecord(**values)


def mapping(**overrides):
    values = {
        "mapping_id": "MAP_FIX",
        "evidence_id": "EVIDENCE_FIX",
        "facefit_metric_id": "HEAD_RELATIVE_YAW_ABS_P95_DEG",
        "mapping_type": "DIRECT",
        "applicability": "REVIEW_REQUIRED",
        "source_unit": "DEGREE",
        "target_unit": "DEGREE",
        "conversion_rule": None,
        "transformation": None,
        "rationale": SYNTHETIC_FIXTURE_NOTICE,
        "limitations": ("Synthetic only.",),
        "review_status": "TEST_FIXTURE",
    }
    values.update(overrides)
    return EvidenceMetricMapping(**values)


def bands():
    return (
        ThresholdBand("LOW", "fixture low", None, 1.0, False, True, 1.0),
        ThresholdBand("HIGH", "fixture high", 1.0, None, False, False, 0.0),
    )


def rule(**overrides):
    values = {
        "rule_id": "RULE_FIX",
        "metric_id": "HEAD_RELATIVE_YAW_ABS_P95_DEG",
        "evidence_profile_id": "PROFILE_FIX",
        "evidence_profile_version": "1.0.0",
        "comparison_mode": "LOWER_IS_BETTER",
        "bands": bands(),
        "unit": "DEGREE",
        "minimum_data_quality": 0.8,
        "minimum_availability_ratio": 0.8,
        "minimum_sample_count": 5,
        "maximum_longest_missing_duration_ms": 1000,
        "required_target_continuity": 1.0,
        "status": "TEST_FIXTURE",
        "rationale": SYNTHETIC_FIXTURE_NOTICE,
    }
    values.update(overrides)
    return MetricThresholdRule(**values)


class EvidenceModelsTests(unittest.TestCase):
    def test_source_round_trip_and_metadata_validation(self):
        self.assertEqual(source().to_dict()["source_id"], "SRC_FIX")
        for override in (
            {"source_id": ""},
            {"source_type": "INVALID"},
            {"publication_year": 1599},
            {"sample_size": -1},
            {"doi": "invalid"},
            {"url": "file:///fixture"},
            {"access_date": "2026/07/28"},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                source(**override)

    def test_scope_requires_positive_finite_fps(self):
        for value in (0, -1, math.inf, math.nan, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ApplicabilityScope(analysis_fps=value)

    def test_record_range_and_finite_values(self):
        ranged = record(
            statistic_type="RANGE",
            value=None,
            lower_bound=0.0,
            upper_bound=2.0,
        )
        self.assertEqual(ranged.to_dict()["upper_bound"], 2.0)
        for override in (
            {"statistic_type": "RANGE", "lower_bound": None},
            {"lower_bound": 2.0, "upper_bound": 1.0},
            {"value": math.nan},
            {"statistic_type": "INVALID"},
            {"evidence_strength": "INVALID"},
            {"applicability": "INVALID"},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                record(**override)

    def test_mapping_requires_explicit_conversion_and_proxy_limitations(self):
        with self.assertRaises(ValueError):
            mapping(source_unit="RADIAN")
        converted = mapping(
            mapping_type="UNIT_CONVERSION",
            source_unit="RADIAN",
            conversion_rule="degrees(value)",
        )
        self.assertEqual(converted.mapping_type, "UNIT_CONVERSION")
        with self.assertRaises(ValueError):
            mapping(mapping_type="UNIT_CONVERSION", conversion_rule=None)
        with self.assertRaises(ValueError):
            mapping(mapping_type="PROXY", limitations=())

    def test_profile_enforces_semver_unique_references_and_timestamps(self):
        values = {
            "profile_id": "PROFILE_FIX",
            "version": "1.0.0",
            "name": "Fixture",
            "description": SYNTHETIC_FIXTURE_NOTICE,
            "source_ids": ("SRC_FIX",),
            "evidence_ids": ("EVIDENCE_FIX",),
            "mapping_ids": ("MAP_FIX",),
            "domain": "HEAD_POSE",
            "status": "TEST_FIXTURE",
            "created_at": "2026-07-28T00:00:00Z",
            "updated_at": "2026-07-28T00:00:00Z",
            "supersedes_version": None,
            "notes": None,
        }
        profile = EvidenceProfile(**values)
        self.assertEqual(profile.version, "1.0.0")
        for key, value in (
            ("version", "v1"),
            ("source_ids", ()),
            ("evidence_ids", ("EVIDENCE_FIX", "EVIDENCE_FIX")),
            ("created_at", "yesterday"),
            ("domain", "INVALID"),
            ("supersedes_version", "1.0.0"),
        ):
            bad = dict(values)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                EvidenceProfile(**bad)

    def test_threshold_boundaries_are_unambiguous(self):
        current = bands()
        validate_threshold_bands(current)
        self.assertTrue(current[0].contains(1.0))
        self.assertFalse(current[1].contains(1.0))
        with self.assertRaises(ValueError):
            validate_threshold_bands(
                (
                    ThresholdBand("A", "a", None, 1, False, True, 1),
                    ThresholdBand("B", "b", 1, None, True, False, 0),
                )
            )

    def test_threshold_gap_overlap_and_invalid_bounds_are_rejected(self):
        cases = (
            (
                ThresholdBand("A", "a", None, 0, False, False, 1),
                ThresholdBand("B", "b", 1, None, True, False, 0),
            ),
            (
                ThresholdBand("A", "a", None, 2, False, True, 1),
                ThresholdBand("B", "b", 1, None, False, False, 0),
            ),
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_threshold_bands(value)
        with self.assertRaises(ValueError):
            ThresholdBand("A", "a", 2, 1, True, True, 0)
        with self.assertRaises(ValueError):
            ThresholdBand("A", "a", None, None, False, False, 0)

    def test_threshold_rule_quality_constraints_and_modes(self):
        for mode in (
            "LOWER_IS_BETTER",
            "HIGHER_IS_BETTER",
            "TARGET_RANGE",
            "SYMMETRIC_ABSOLUTE",
        ):
            self.assertEqual(rule(comparison_mode=mode).comparison_mode, mode)
        for override in (
            {"comparison_mode": "INVALID"},
            {"minimum_data_quality": 1.1},
            {"minimum_sample_count": -1},
            {"maximum_longest_missing_duration_ms": True},
            {"evidence_profile_version": "1"},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                rule(**override)

    def test_threshold_profile_rejects_rule_reference_mismatch_and_duplicates(self):
        values = {
            "threshold_profile_id": "THRESHOLD_FIX",
            "version": "1.0.0",
            "name": "Fixture",
            "domain": "HEAD_POSE",
            "evidence_profile_id": "PROFILE_FIX",
            "evidence_profile_version": "1.0.0",
            "rules": (rule(),),
            "status": "TEST_FIXTURE",
            "created_at": "2026-07-28T00:00:00Z",
            "supersedes_version": None,
        }
        self.assertEqual(ThresholdProfile(**values).rules[0].rule_id, "RULE_FIX")
        bad = dict(values)
        bad["rules"] = (rule(), rule())
        with self.assertRaises(ValueError):
            ThresholdProfile(**bad)
        bad = dict(values)
        bad["rules"] = (rule(evidence_profile_id="OTHER"),)
        with self.assertRaises(ValueError):
            ThresholdProfile(**bad)


if __name__ == "__main__":
    unittest.main()
