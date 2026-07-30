"""Reject fixture scoring when interval data quality is insufficient."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.vision.metric_registry import MetricValueResolution
from app.vision.threshold_models import MetricThresholdRule


@dataclass(frozen=True)
class DataQualityGateResult:
    passed: bool
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_data_quality_gate(
    resolution: MetricValueResolution,
    rule: MetricThresholdRule,
) -> DataQualityGateResult:
    failures: list[str] = []
    if (
        rule.minimum_availability_ratio is not None
        and resolution.availability_ratio
        < rule.minimum_availability_ratio
    ):
        failures.append("MINIMUM_AVAILABILITY_RATIO_NOT_MET")
    if (
        rule.minimum_sample_count is not None
        and resolution.sample_count < rule.minimum_sample_count
    ):
        failures.append("MINIMUM_SAMPLE_COUNT_NOT_MET")
    if (
        rule.maximum_longest_missing_duration_ms is not None
        and resolution.longest_missing_duration_ms
        > rule.maximum_longest_missing_duration_ms
    ):
        failures.append("MAXIMUM_LONGEST_MISSING_DURATION_EXCEEDED")
    if (
        rule.minimum_data_quality is not None
        and resolution.interval_quality_score
        < rule.minimum_data_quality
    ):
        failures.append("MINIMUM_INTERVAL_QUALITY_NOT_MET")
    if (
        rule.required_target_continuity is not None
        and resolution.target_continuity_ratio
        < rule.required_target_continuity
    ):
        failures.append("REQUIRED_TARGET_CONTINUITY_NOT_MET")
    return DataQualityGateResult(
        passed=not failures,
        failure_reasons=tuple(failures),
    )
