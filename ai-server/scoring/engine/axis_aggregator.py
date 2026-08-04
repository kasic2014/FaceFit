"""Coverage-aware weighted metric aggregation."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from .scoring_models import decimal_value, json_number, quantize


def aggregate_axis(metric_results: list[dict[str, Any]], axis_rule: dict[str, Any], decimal_places: int) -> dict[str, Any]:
    axis = axis_rule["axis"]
    rows = [row for row in metric_results if row.get("axis") == axis and row.get("weight") is not None]
    total_weight = sum((decimal_value(row.get("weight"), "weight") for row in rows), Decimal(0))
    scored = [row for row in rows if row.get("scoreStatus") == "SCORED" and row.get("score") is not None]
    scored_weight = sum((decimal_value(row["weight"]) for row in scored), Decimal(0))
    coverage = scored_weight / total_weight if total_weight else Decimal(0)
    required = set(axis_rule.get("requiredMetricIds", []))
    scored_ids = {row["metricId"] for row in scored}
    missing_required = sorted(required - scored_ids)
    minimum = decimal_value(axis_rule["minimumCoverageRatio"])
    can_partial = axis_rule["allowPartialScore"] and axis_rule["renormalizeAvailableWeights"]
    status = "SCORED" if coverage == 1 and not missing_required else "PARTIAL"
    if missing_required or coverage < minimum or (coverage < 1 and not can_partial) or not scored:
        status = "NOT_SCORABLE"
    score = None
    if status in {"SCORED", "PARTIAL"}:
        denominator = scored_weight if axis_rule["renormalizeAvailableWeights"] else total_weight
        with localcontext() as context:
            context.prec = 34
            value = sum((decimal_value(row["score"]) * decimal_value(row["weight"]) for row in scored), Decimal(0)) / denominator
        score = json_number(quantize(value, decimal_places))
    return {
        "axis": axis,
        "scoreStatus": status,
        "score": score,
        "coverageRatio": json_number(quantize(coverage, 6)),
        "scoredMetricCount": len(scored),
        "totalMetricCount": len(rows),
        "missingRequiredMetricIds": missing_required,
        "includedMetricIds": [row["metricId"] for row in scored],
        "warnings": ["REQUIRED_METRIC_MISSING"] if missing_required else [],
        "limitations": [],
    }
