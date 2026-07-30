from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.vision.evidence_loaders import (
    EvidenceLoadError,
    EvidenceRegistryLoader,
    load_strict_json,
)
from app.vision.evidence_registry import (
    EvidenceExecutionMode,
    EvidenceRegistry,
)
from app.vision.metric_registry import build_stage10_metric_registry


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "evidence"
    / "fixtures"
)


def loaded():
    return EvidenceRegistryLoader.load_directory(
        FIXTURE_ROOT,
        metric_registry=build_stage10_metric_registry(),
        execution_mode=EvidenceExecutionMode.TEST_FIXTURE_MODE.value,
    )


class EvidenceRegistryLoaderTests(unittest.TestCase):
    def test_fixture_directory_loads_all_contract_components(self):
        registry = loaded()
        self.assertEqual(len(registry.sources), 2)
        self.assertEqual(len(registry.records), 3)
        self.assertEqual(len(registry.mappings), 3)
        self.assertEqual(len(registry.profiles), 2)
        self.assertEqual(len(registry.threshold_profiles), 2)
        self.assertEqual(registry.conflicts, ())

    def test_registry_serialization_is_deterministic(self):
        first = json.dumps(
            loaded().to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        second = json.dumps(
            loaded().to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        self.assertEqual(first, second)

    def test_production_mode_rejects_fixture_data(self):
        with self.assertRaises(EvidenceLoadError) as context:
            EvidenceRegistryLoader.load_directory(
                FIXTURE_ROOT,
                metric_registry=build_stage10_metric_registry(),
                execution_mode=EvidenceExecutionMode.PRODUCTION_MODE.value,
            )
        self.assertEqual(
            context.exception.code,
            "EVIDENCE_REFERENCE_VALIDATION_FAILED",
        )

    def test_missing_component_file_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvidenceLoadError) as context:
                EvidenceRegistryLoader.load_directory(
                    directory,
                    metric_registry=build_stage10_metric_registry(),
                    execution_mode=(
                        EvidenceExecutionMode.TEST_FIXTURE_MODE.value
                    ),
                )
        self.assertEqual(context.exception.code, "EVIDENCE_FIXTURE_FILE_MISSING")

    def test_strict_json_rejects_nan_and_malformed_json(self):
        for text in ('{"value": NaN}', "{"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "fixture.json"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(EvidenceLoadError) as context:
                    load_strict_json(path)
                self.assertEqual(
                    context.exception.code,
                    "INVALID_STRICT_EVIDENCE_JSON",
                )

    def test_duplicate_ids_and_missing_references_are_rejected(self):
        registry = loaded()
        source = next(iter(registry.sources.values()))
        with self.assertRaises(ValueError):
            EvidenceRegistry(
                sources=(*registry.sources.values(), source),
                records=registry.records.values(),
                mappings=registry.mappings.values(),
                profiles=registry.profiles.values(),
                threshold_profiles=registry.threshold_profiles.values(),
                metric_registry=registry.metric_registry,
                execution_mode=registry.execution_mode,
            )
        missing = replace(
            next(iter(registry.records.values())),
            source_id="MISSING",
        )
        records = [
            missing if item.evidence_id == missing.evidence_id else item
            for item in registry.records.values()
        ]
        with self.assertRaises(ValueError):
            EvidenceRegistry(
                sources=registry.sources.values(),
                records=records,
                mappings=registry.mappings.values(),
                profiles=registry.profiles.values(),
                threshold_profiles=registry.threshold_profiles.values(),
                metric_registry=registry.metric_registry,
                execution_mode=registry.execution_mode,
            )

    def test_mapping_metric_unit_mismatch_is_rejected(self):
        registry = loaded()
        target = next(iter(registry.mappings.values()))
        changed = replace(
            target,
            target_unit="RATIO",
            source_unit="RATIO",
        )
        mappings = [
            changed if item.mapping_id == changed.mapping_id else item
            for item in registry.mappings.values()
        ]
        with self.assertRaises(ValueError):
            EvidenceRegistry(
                sources=registry.sources.values(),
                records=registry.records.values(),
                mappings=mappings,
                profiles=registry.profiles.values(),
                threshold_profiles=registry.threshold_profiles.values(),
                metric_registry=registry.metric_registry,
                execution_mode=registry.execution_mode,
            )

    def test_provenance_references_exact_profile_versions(self):
        registry = loaded()
        profile = registry.profiles[("EVIDENCE_FIX_HEAD", "1.0.0")]
        threshold = registry.threshold_profiles[
            ("THRESHOLD_FIX_HEAD", "1.0.0")
        ]
        result = registry.build_provenance(
            evidence_profile=profile,
            threshold_profile=threshold,
            rule_id="RULE_FIX_HEAD_YAW_001",
            metric_id="HEAD_RELATIVE_YAW_ABS_P95_DEG",
        )
        self.assertEqual(result.evidence_profile_version, "1.0.0")
        self.assertEqual(result.threshold_profile_version, "1.0.0")
        self.assertEqual(result.mapping_ids, ("MAP_FIX_HEAD_YAW_001",))

    def test_conflict_is_detected_but_never_auto_resolved(self):
        registry = loaded()
        head_profile = registry.profiles[("EVIDENCE_FIX_HEAD", "1.0.0")]
        posture_record = registry.records["EVID_FIX_POSTURE_TILT_001"]
        posture_mapping = registry.mappings["MAP_FIX_POSTURE_TILT_001"]
        conflicting_mapping = replace(
            posture_mapping,
            mapping_id="MAP_FIX_CONFLICTING_PROXY_001",
            facefit_metric_id="HEAD_RELATIVE_YAW_ABS_P95_DEG",
            mapping_type="PROXY",
            target_unit="DEGREE",
            source_unit="DEGREE",
        )
        expanded_head_profile = replace(
            head_profile,
            source_ids=tuple(
                sorted(
                    {
                        *head_profile.source_ids,
                        posture_record.source_id,
                    }
                )
            ),
            evidence_ids=tuple(
                sorted(
                    {
                        *head_profile.evidence_ids,
                        posture_record.evidence_id,
                    }
                )
            ),
            mapping_ids=tuple(
                sorted(
                    {
                        *head_profile.mapping_ids,
                        conflicting_mapping.mapping_id,
                    }
                )
            ),
        )
        profiles = [
            expanded_head_profile
            if item.profile_id == head_profile.profile_id
            else item
            for item in registry.profiles.values()
        ]
        conflicted = EvidenceRegistry(
            sources=registry.sources.values(),
            records=registry.records.values(),
            mappings=(
                *registry.mappings.values(),
                conflicting_mapping,
            ),
            profiles=profiles,
            threshold_profiles=registry.threshold_profiles.values(),
            metric_registry=registry.metric_registry,
            execution_mode=registry.execution_mode,
        )
        self.assertTrue(conflicted.conflicts)
        self.assertEqual(
            conflicted.conflicts[0].conflict_type,
            "APPLICABILITY_CONFLICT",
        )
        self.assertEqual(conflicted.conflicts[0].resolution_status, "OPEN")


if __name__ == "__main__":
    unittest.main()
