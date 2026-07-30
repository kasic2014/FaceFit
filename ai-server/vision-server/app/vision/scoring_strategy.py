"""Scoring protocol and synthetic TEST_FIXTURE-only band strategy."""

from __future__ import annotations

from typing import Protocol

from app.vision.data_quality_gate import evaluate_data_quality_gate
from app.vision.evidence_models import (
    EvidenceStatus,
    SYNTHETIC_FIXTURE_NOTICE,
)
from app.vision.evidence_profile_models import EvidenceProfile
from app.vision.metric_registry import (
    MetricDefinition,
    MetricValueResolution,
)
from app.vision.scoring_models import (
    MetricScoreResult,
    MetricScoreStatus,
    ScoreProvenance,
)
from app.vision.threshold_models import (
    MetricThresholdRule,
    ThresholdProfile,
)


SCORING_POLICY_ID = "FIXTURE_BAND_SCORING_CONTRACT"
SCORING_POLICY_VERSION = "1.0.0"


class MetricScoringStrategy(Protocol):
    def score(
        self,
        resolution: MetricValueResolution,
        metric_definition: MetricDefinition,
        threshold_rule: MetricThresholdRule,
        threshold_profile: ThresholdProfile,
        evidence_profile: EvidenceProfile,
        provenance: ScoreProvenance | None,
    ) -> MetricScoreResult:
        ...


class TestFixtureBandScoringStrategy:
    """Exercise contracts only; this strategy must never run as production."""

    def _result(
        self,
        *,
        resolution: MetricValueResolution,
        threshold_rule: MetricThresholdRule,
        threshold_profile: ThresholdProfile,
        status: str,
        failure_reason: str | None,
        matched_band_id: str | None = None,
        test_fixture_score: float | None = None,
        provenance: ScoreProvenance | None = None,
    ) -> MetricScoreResult:
        available = status == MetricScoreStatus.SCORED_TEST_FIXTURE.value
        return MetricScoreResult(
            available=available,
            metric_id=resolution.metric_id,
            input_value=resolution.value,
            input_unit=resolution.unit,
            threshold_profile_id=threshold_profile.threshold_profile_id,
            threshold_profile_version=threshold_profile.version,
            scoring_policy_id=SCORING_POLICY_ID,
            scoring_policy_version=SCORING_POLICY_VERSION,
            rule_id=threshold_rule.rule_id,
            matched_band_id=matched_band_id,
            test_fixture_score=test_fixture_score if available else None,
            status=status,
            warnings=(SYNTHETIC_FIXTURE_NOTICE,),
            failure_reason=failure_reason,
            provenance=provenance if available else None,
        )

    def score(
        self,
        resolution: MetricValueResolution,
        metric_definition: MetricDefinition,
        threshold_rule: MetricThresholdRule,
        threshold_profile: ThresholdProfile,
        evidence_profile: EvidenceProfile,
        provenance: ScoreProvenance | None,
    ) -> MetricScoreResult:
        if evidence_profile.status != EvidenceStatus.TEST_FIXTURE.value:
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.EVIDENCE_NOT_APPROVED.value,
                failure_reason="FIXTURE_STRATEGY_REQUIRES_TEST_FIXTURE_EVIDENCE",
            )
        if (
            threshold_profile.status != EvidenceStatus.TEST_FIXTURE.value
            or threshold_rule.status != EvidenceStatus.TEST_FIXTURE.value
        ):
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.THRESHOLD_NOT_APPROVED.value,
                failure_reason="FIXTURE_STRATEGY_REQUIRES_TEST_FIXTURE_THRESHOLD",
            )
        if (
            threshold_profile.evidence_profile_id
            != evidence_profile.profile_id
            or threshold_profile.evidence_profile_version
            != evidence_profile.version
            or threshold_rule.evidence_profile_id
            != evidence_profile.profile_id
            or threshold_rule.evidence_profile_version
            != evidence_profile.version
        ):
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.PROFILE_VERSION_MISMATCH.value,
                failure_reason="EVIDENCE_PROFILE_VERSION_MISMATCH",
            )
        if (
            metric_definition.metric_id != threshold_rule.metric_id
            or resolution.metric_id != metric_definition.metric_id
        ):
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.INVALID_RULE.value,
                failure_reason="METRIC_RULE_ID_MISMATCH",
            )
        if (
            resolution.unit != metric_definition.unit
            or threshold_rule.unit != metric_definition.unit
        ):
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.UNIT_MISMATCH.value,
                failure_reason="METRIC_THRESHOLD_UNIT_MISMATCH",
            )
        if not resolution.available or resolution.value is None:
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.METRIC_UNAVAILABLE.value,
                failure_reason=resolution.failure_reason,
            )
        gate = evaluate_data_quality_gate(resolution, threshold_rule)
        if not gate.passed:
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.INSUFFICIENT_DATA.value,
                failure_reason=";".join(gate.failure_reasons),
            )
        matched = [
            band
            for band in threshold_rule.bands
            if band.contains(resolution.value)
        ]
        if len(matched) != 1 or matched[0].output_value is None:
            return self._result(
                resolution=resolution,
                threshold_rule=threshold_rule,
                threshold_profile=threshold_profile,
                status=MetricScoreStatus.NO_MATCHING_BAND.value,
                failure_reason="NO_UNIQUE_MATCHING_FIXTURE_BAND",
            )
        return self._result(
            resolution=resolution,
            threshold_rule=threshold_rule,
            threshold_profile=threshold_profile,
            status=MetricScoreStatus.SCORED_TEST_FIXTURE.value,
            failure_reason=None,
            matched_band_id=matched[0].band_id,
            test_fixture_score=matched[0].output_value,
            provenance=provenance,
        )
