"""Answer aggregation with overall score disabled unless explicitly profiled."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from .scoring_models import decimal_value, json_number, quantize


def aggregate_answer(answer_id: str, axis_results: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    scale = profile["scoreScale"]
    axis_map = {row["axis"]: row for row in axis_results}
    statuses = [row["scoreStatus"] for row in axis_results]
    status = "SCORED" if statuses and all(value == "SCORED" for value in statuses) else "PARTIAL" if any(value in {"SCORED", "PARTIAL"} for value in statuses) else "NOT_SCORABLE"
    enabled = profile.get("answerAggregation", {}).get("overallEnabled") is True
    overall = None
    if enabled:
        rule = profile.get("overallRule", {})
        required = rule.get("requiredAxes", [])
        available = [axis_map[axis] for axis in required if axis_map.get(axis, {}).get("score") is not None]
        minimum = decimal_value(rule.get("minimumAxisCoverageRatio", 1))
        coverage = Decimal(len(available)) / Decimal(len(required)) if required else Decimal(0)
        weights = rule.get("axisWeights") or {axis: 1 for axis in required}
        if coverage >= minimum and available:
            denominator = sum((decimal_value(weights[row["axis"]]) for row in available), Decimal(0))
            with localcontext() as context:
                context.prec = 34
                value = sum((decimal_value(row["score"]) * decimal_value(weights[row["axis"]]) for row in available), Decimal(0)) / denominator
            overall = json_number(quantize(value, int(scale["decimalPlaces"])))
    return {
        "answerId": answer_id,
        "scoreStatus": status,
        "axisScores": axis_map,
        "overallScoreAvailable": overall is not None,
        "overallScore": overall,
        "warnings": [],
        "limitations": [],
    }
