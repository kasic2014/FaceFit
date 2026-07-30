"""Deterministic common statistics for interval feature values."""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable

from app.vision.interval_models import (
    IntervalAggregationConfig,
    IntervalAggregationFailureReason,
    NumericMetricSummary,
)


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def linear_percentile(values: Iterable[float], percentile: float) -> float:
    """NumPy-compatible linear interpolation: rank=(n-1)*percentile/100."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("percentile must be within 0..100")
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def aggregate_numeric_metric(
    values: Iterable[Any],
    config: IntervalAggregationConfig = IntervalAggregationConfig(),
) -> NumericMetricSummary:
    supplied = list(values)
    finite = [
        number
        for value in supplied
        if (number := _finite_number(value)) is not None
    ]
    if not finite:
        had_non_finite = any(value is not None for value in supplied)
        return NumericMetricSummary(
            available=False,
            count=0,
            minimum=None,
            maximum=None,
            mean=None,
            median=None,
            mad=None,
            standard_deviation=None,
            p05=None,
            p25=None,
            p75=None,
            p95=None,
            absolute_mean=None,
            absolute_median=None,
            absolute_p95=None,
            failure_reason=(
                IntervalAggregationFailureReason.NON_FINITE_VALUE.value
                if had_non_finite
                else IntervalAggregationFailureReason.NO_VALID_VALUES.value
            ),
        )
    median = float(statistics.median(finite))
    absolute = [abs(value) for value in finite]
    sufficient = len(finite) >= config.minimum_valid_sample_count
    percentiles = (
        {
            value: linear_percentile(finite, value)
            for value in config.percentile_values
        }
        if config.calculate_percentiles
        else {}
    )
    absolute_p95 = (
        linear_percentile(absolute, 95.0)
        if config.calculate_percentiles
        and config.include_absolute_statistics
        else None
    )
    return NumericMetricSummary(
        available=sufficient,
        count=len(finite),
        minimum=min(finite),
        maximum=max(finite),
        mean=float(statistics.fmean(finite)),
        median=median,
        mad=float(statistics.median(abs(value - median) for value in finite)),
        standard_deviation=float(statistics.pstdev(finite)),
        p05=percentiles.get(5.0),
        p25=percentiles.get(25.0),
        p75=percentiles.get(75.0),
        p95=percentiles.get(95.0),
        absolute_mean=(
            float(statistics.fmean(absolute))
            if config.include_absolute_statistics
            else None
        ),
        absolute_median=(
            float(statistics.median(absolute))
            if config.include_absolute_statistics
            else None
        ),
        absolute_p95=absolute_p95,
        failure_reason=(
            None
            if sufficient
            else IntervalAggregationFailureReason
            .INSUFFICIENT_VALID_SAMPLES.value
        ),
    )
