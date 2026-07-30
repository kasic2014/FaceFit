"""Cross-reference validation, provenance, and conflict detection."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Iterable, TypeVar

from app.vision.evidence_mapping_models import (
    EvidenceMappingType,
    EvidenceMetricMapping,
)
from app.vision.evidence_models import (
    EvidenceConflict,
    EvidenceConflictResolutionStatus,
    EvidenceConflictType,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    SYNTHETIC_FIXTURE_NOTICE,
)
from app.vision.evidence_profile_models import EvidenceProfile
from app.vision.metric_registry import FaceFitMetricRegistry
from app.vision.scoring_models import ScoreProvenance
from app.vision.scoring_strategy import (
    SCORING_POLICY_ID,
    SCORING_POLICY_VERSION,
)
from app.vision.threshold_models import ThresholdProfile


class EvidenceExecutionMode(str, Enum):
    TEST_FIXTURE_MODE = "TEST_FIXTURE_MODE"
    PRODUCTION_MODE = "PRODUCTION_MODE"


T = TypeVar("T")


def _unique_map(
    values: Iterable[T],
    key_getter,
    name: str,
) -> dict[Any, T]:
    result: dict[Any, T] = {}
    for value in values:
        key = key_getter(value)
        if key in result:
            raise ValueError(f"Duplicate {name}: {key}")
        result[key] = value
    return result


class EvidenceRegistry:
    def __init__(
        self,
        *,
        sources: Iterable[EvidenceSource],
        records: Iterable[EvidenceRecord],
        mappings: Iterable[EvidenceMetricMapping],
        profiles: Iterable[EvidenceProfile],
        threshold_profiles: Iterable[ThresholdProfile],
        metric_registry: FaceFitMetricRegistry,
        execution_mode: str,
    ) -> None:
        if execution_mode not in {item.value for item in EvidenceExecutionMode}:
            raise ValueError(f"Invalid execution mode: {execution_mode}")
        self.execution_mode = execution_mode
        self.metric_registry = metric_registry
        self.sources = _unique_map(
            sources,
            lambda item: item.source_id,
            "source_id",
        )
        self.records = _unique_map(
            records,
            lambda item: item.evidence_id,
            "evidence_id",
        )
        self.mappings = _unique_map(
            mappings,
            lambda item: item.mapping_id,
            "mapping_id",
        )
        self.profiles = _unique_map(
            profiles,
            lambda item: (item.profile_id, item.version),
            "evidence profile ID/version",
        )
        self.threshold_profiles = _unique_map(
            threshold_profiles,
            lambda item: (item.threshold_profile_id, item.version),
            "threshold profile ID/version",
        )
        self._validate()
        self.conflicts = self._detect_conflicts()

    def _validate_status(self, value: Any, description_field: str) -> None:
        status = value.status
        if self.execution_mode == EvidenceExecutionMode.PRODUCTION_MODE.value:
            if status != EvidenceStatus.APPROVED.value:
                raise ValueError(
                    f"PRODUCTION_MODE rejects non-approved {type(value).__name__}"
                )
        elif status not in {
            EvidenceStatus.TEST_FIXTURE.value,
            EvidenceStatus.DRAFT.value,
        }:
            raise ValueError(
                "TEST_FIXTURE_MODE accepts only TEST_FIXTURE or DRAFT data"
            )
        if status == EvidenceStatus.TEST_FIXTURE.value:
            text = getattr(value, description_field, None) or ""
            if SYNTHETIC_FIXTURE_NOTICE not in text:
                raise ValueError(
                    f"TEST_FIXTURE {type(value).__name__} lacks fixture notice"
                )

    def _validate(self) -> None:
        for source in self.sources.values():
            self._validate_status(source, "notes")
            if source.status == EvidenceStatus.APPROVED.value:
                if (
                    not source.authors
                    or source.publication_year is None
                    or (source.doi is None and source.url is None)
                    or not source.study_population
                    or source.sample_size is None
                    or source.peer_reviewed is None
                ):
                    raise ValueError(
                        "APPROVED source lacks required provenance metadata"
                    )
        for record in self.records.values():
            self._validate_status(record, "extraction_note")
            if record.source_id not in self.sources:
                raise ValueError(
                    f"Evidence source reference missing: {record.source_id}"
                )
            if record.status == EvidenceStatus.APPROVED.value:
                scope = record.applicability_scope
                if (
                    record.unit is None
                    or not record.extraction_location
                    or scope is None
                    or not scope.measurement_method
                    or not scope.body_region
                ):
                    raise ValueError(
                        "APPROVED evidence lacks extraction/scope metadata"
                    )
        for mapping in self.mappings.values():
            self._validate_mapping(mapping)
        for key, profile in self.profiles.items():
            self._validate_status(profile, "description")
            if profile.supersedes_version is not None and (
                profile.profile_id,
                profile.supersedes_version,
            ) not in self.profiles:
                raise ValueError(
                    f"Missing superseded evidence profile: {key}"
                )
            for source_id in profile.source_ids:
                if source_id not in self.sources:
                    raise ValueError(
                        f"Profile source reference missing: {source_id}"
                    )
            for evidence_id in profile.evidence_ids:
                if evidence_id not in self.records:
                    raise ValueError(
                        f"Profile evidence reference missing: {evidence_id}"
                    )
            for mapping_id in profile.mapping_ids:
                if mapping_id not in self.mappings:
                    raise ValueError(
                        f"Profile mapping reference missing: {mapping_id}"
                    )
                mapping = self.mappings[mapping_id]
                if mapping.evidence_id not in profile.evidence_ids:
                    raise ValueError(
                        "Profile mapping evidence is outside evidence_ids"
                    )
            if profile.status == EvidenceStatus.APPROVED.value:
                linked = (
                    *(self.sources[item] for item in profile.source_ids),
                    *(self.records[item] for item in profile.evidence_ids),
                )
                if any(
                    item.status != EvidenceStatus.APPROVED.value
                    for item in linked
                ) or any(
                    self.mappings[item].review_status
                    != EvidenceStatus.APPROVED.value
                    for item in profile.mapping_ids
                ):
                    raise ValueError(
                        "APPROVED profile contains non-approved references"
                    )
        for key, profile in self.threshold_profiles.items():
            if (
                self.execution_mode
                == EvidenceExecutionMode.PRODUCTION_MODE.value
                and profile.status != EvidenceStatus.APPROVED.value
            ):
                raise ValueError(
                    "PRODUCTION_MODE rejects non-approved ThresholdProfile"
                )
            if (
                self.execution_mode
                == EvidenceExecutionMode.TEST_FIXTURE_MODE.value
                and profile.status
                not in {
                    EvidenceStatus.TEST_FIXTURE.value,
                    EvidenceStatus.DRAFT.value,
                }
            ):
                raise ValueError(
                    "TEST_FIXTURE_MODE rejects operating ThresholdProfile"
                )
            if profile.status == EvidenceStatus.TEST_FIXTURE.value and (
                SYNTHETIC_FIXTURE_NOTICE not in " ".join(
                    rule.rationale for rule in profile.rules
                )
            ):
                raise ValueError(
                    "TEST_FIXTURE threshold profile lacks fixture notice"
                )
            if profile.supersedes_version is not None and (
                profile.threshold_profile_id,
                profile.supersedes_version,
            ) not in self.threshold_profiles:
                raise ValueError(
                    f"Missing superseded threshold profile: {key}"
                )
            evidence_key = (
                profile.evidence_profile_id,
                profile.evidence_profile_version,
            )
            if evidence_key not in self.profiles:
                raise ValueError(
                    f"Threshold evidence profile missing: {evidence_key}"
                )
            evidence_profile = self.profiles[evidence_key]
            if (
                profile.status == EvidenceStatus.APPROVED.value
                and evidence_profile.status != EvidenceStatus.APPROVED.value
            ):
                raise ValueError(
                    "APPROVED threshold requires APPROVED evidence profile"
                )
            for rule in profile.rules:
                try:
                    metric = self.metric_registry.get(rule.metric_id)
                except KeyError as exc:
                    raise ValueError(
                        f"Threshold metric missing: {rule.metric_id}"
                    ) from exc
                if rule.unit != metric.unit:
                    raise ValueError(
                        f"Threshold unit mismatch for {rule.metric_id}"
                    )
                if (
                    rule.evidence_profile_id != evidence_profile.profile_id
                    or rule.evidence_profile_version
                    != evidence_profile.version
                ):
                    raise ValueError(
                        "Threshold rule evidence profile version mismatch"
                    )

    def _validate_mapping(self, mapping: EvidenceMetricMapping) -> None:
        if mapping.evidence_id not in self.records:
            raise ValueError(
                f"Mapping evidence reference missing: {mapping.evidence_id}"
            )
        try:
            metric = self.metric_registry.get(mapping.facefit_metric_id)
        except KeyError as exc:
            raise ValueError(
                f"Mapping metric reference missing: {mapping.facefit_metric_id}"
            ) from exc
        if mapping.target_unit != metric.unit:
            raise ValueError(
                f"Mapping target unit mismatch: {mapping.mapping_id}"
            )
        evidence = self.records[mapping.evidence_id]
        if (
            evidence.unit is not None
            and mapping.source_unit is not None
            and evidence.unit != mapping.source_unit
        ):
            raise ValueError(
                f"Mapping source unit mismatch: {mapping.mapping_id}"
            )
        diagnostic_terms = (
            "diagnosis",
            "diagnostic",
            "scoliosis",
            "mental disorder",
            "척추측만",
            "거북목",
            "질환",
            "불안장애",
            "주의력 결핍",
            "정신건강",
        )
        concept = (
            evidence.construct_name + " " + evidence.measurement_name
        ).casefold()
        if (
            any(term.casefold() in concept for term in diagnostic_terms)
            and mapping.mapping_type
            != EvidenceMappingType.UNSUPPORTED.value
        ):
            raise ValueError(
                "Diagnostic evidence cannot directly map to Face-Fit"
            )
        if self.execution_mode == EvidenceExecutionMode.PRODUCTION_MODE.value:
            if mapping.review_status != EvidenceStatus.APPROVED.value:
                raise ValueError(
                    "PRODUCTION_MODE rejects non-approved mappings"
                )
        elif mapping.review_status not in {
            EvidenceStatus.TEST_FIXTURE.value,
            EvidenceStatus.DRAFT.value,
        }:
            raise ValueError(
                "TEST_FIXTURE_MODE rejects operating mappings"
            )
        if (
            mapping.review_status == EvidenceStatus.TEST_FIXTURE.value
            and SYNTHETIC_FIXTURE_NOTICE not in mapping.rationale
        ):
            raise ValueError("TEST_FIXTURE mapping lacks fixture notice")

    def build_provenance(
        self,
        *,
        evidence_profile: EvidenceProfile,
        threshold_profile: ThresholdProfile,
        rule_id: str,
        metric_id: str,
    ) -> ScoreProvenance:
        mapping_ids = tuple(
            sorted(
                mapping_id
                for mapping_id in evidence_profile.mapping_ids
                if self.mappings[mapping_id].facefit_metric_id == metric_id
            )
        )
        if not mapping_ids:
            raise ValueError(
                f"No provenance mapping for metric_id: {metric_id}"
            )
        evidence_ids = tuple(
            sorted(
                {
                    self.mappings[mapping_id].evidence_id
                    for mapping_id in mapping_ids
                }
            )
        )
        source_ids = tuple(
            sorted({self.records[item].source_id for item in evidence_ids})
        )
        if any(item not in self.sources for item in source_ids):
            raise ValueError("Provenance source reference is missing")
        return ScoreProvenance(
            source_ids=source_ids,
            evidence_ids=evidence_ids,
            mapping_ids=mapping_ids,
            evidence_profile_id=evidence_profile.profile_id,
            evidence_profile_version=evidence_profile.version,
            threshold_profile_id=threshold_profile.threshold_profile_id,
            threshold_profile_version=threshold_profile.version,
            scoring_policy_id=SCORING_POLICY_ID,
            scoring_policy_version=SCORING_POLICY_VERSION,
            rule_id=rule_id,
        )

    def _detect_conflicts(self) -> tuple[EvidenceConflict, ...]:
        candidates: list[tuple[str, tuple[str, ...], str, str]] = []
        mapping_by_metric: dict[str, list[EvidenceMetricMapping]] = {}
        for mapping in self.mappings.values():
            mapping_by_metric.setdefault(
                mapping.facefit_metric_id,
                [],
            ).append(mapping)
        for metric_id, mappings in sorted(mapping_by_metric.items()):
            types = {mapping.mapping_type for mapping in mappings}
            if (
                EvidenceMappingType.DIRECT.value in types
                and EvidenceMappingType.PROXY.value in types
            ):
                candidates.append(
                    (
                        metric_id,
                        tuple(
                            sorted(
                                mapping.evidence_id for mapping in mappings
                            )
                        ),
                        EvidenceConflictType
                        .APPLICABILITY_CONFLICT.value,
                        "DIRECT and PROXY mappings coexist; manual review required.",
                    )
                )
            units = {mapping.source_unit for mapping in mappings}
            if len(units) > 1:
                candidates.append(
                    (
                        metric_id,
                        tuple(
                            sorted(
                                mapping.evidence_id for mapping in mappings
                            )
                        ),
                        EvidenceConflictType.UNIT_CONFLICT.value,
                        "Evidence mappings use different source units.",
                    )
                )
        rules_by_metric: dict[str, list[tuple[str, Any]]] = {}
        for key, profile in self.threshold_profiles.items():
            for rule in profile.rules:
                rules_by_metric.setdefault(rule.metric_id, []).append(
                    (f"{key[0]}@{key[1]}", rule)
                )
        for metric_id, rules in sorted(rules_by_metric.items()):
            signatures = {
                json.dumps(
                    rule.to_dict()["bands"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                for _, rule in rules
            }
            if len(rules) > 1 and len(signatures) > 1:
                evidence_ids = tuple(
                    sorted(
                        {
                            self.mappings[mapping_id].evidence_id
                            for profile in self.profiles.values()
                            for mapping_id in profile.mapping_ids
                            if self.mappings[mapping_id].facefit_metric_id
                            == metric_id
                        }
                    )
                )
                if len(evidence_ids) >= 2:
                    candidates.append(
                        (
                            metric_id,
                            evidence_ids,
                            EvidenceConflictType
                            .THRESHOLD_CONFLICT.value,
                            "Different fixture threshold bands target the same metric.",
                        )
                    )
        return tuple(
            EvidenceConflict(
                conflict_id=f"CONFLICT_{index:03d}",
                metric_id=metric_id,
                evidence_ids=tuple(dict.fromkeys(evidence_ids)),
                conflict_type=conflict_type,
                description=description,
                resolution_status=(
                    EvidenceConflictResolutionStatus.OPEN.value
                ),
            )
            for index, (
                metric_id,
                evidence_ids,
                conflict_type,
                description,
            ) in enumerate(candidates, start=1)
            if len(set(evidence_ids)) >= 2
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode,
            "metric_registry": self.metric_registry.to_dict(),
            "sources": [
                self.sources[key].to_dict() for key in sorted(self.sources)
            ],
            "records": [
                self.records[key].to_dict() for key in sorted(self.records)
            ],
            "mappings": [
                self.mappings[key].to_dict() for key in sorted(self.mappings)
            ],
            "profiles": [
                self.profiles[key].to_dict() for key in sorted(self.profiles)
            ],
            "threshold_profiles": [
                self.threshold_profiles[key].to_dict()
                for key in sorted(self.threshold_profiles)
            ],
            "conflicts": [item.to_dict() for item in self.conflicts],
        }
