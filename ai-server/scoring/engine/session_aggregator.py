"""Equal, duration-weighted, and valid-sample-weighted session aggregation."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from .scoring_models import decimal_value, json_number, quantize


def aggregate_session_scores(rows: list[dict[str, Any]], rule: dict[str, Any], decimal_places: int) -> dict[str, Any]:
    valid = [row for row in rows if row.get("score") is not None and row.get("scoreStatus") in {"SCORED", "PARTIAL"}]
    total_count = len(rows)
    coverage = Decimal(len(valid)) / Decimal(total_count) if total_count else Decimal(0)
    method = rule.get("method")
    weight_key = {"DURATION_WEIGHTED": "answerDurationMs", "VALID_SAMPLE_WEIGHTED": "validSampleCount"}.get(method)
    weighted: list[tuple[Decimal, Decimal]] = []
    for row in valid:
        weight = Decimal(1) if method == "EQUAL" else decimal_value(row.get(weight_key), weight_key or "weight")
        if weight > 0:
            weighted.append((decimal_value(row["score"]), weight))
    enough = len(valid) >= int(rule.get("minimumScorableAnswerCount", 1)) and coverage >= decimal_value(rule.get("minimumAnswerCoverageRatio", 1))
    status = "SCORED" if enough and coverage == 1 else "PARTIAL" if enough and rule.get("allowPartialScore") else "NOT_SCORABLE"
    score = None
    if status in {"SCORED", "PARTIAL"} and weighted:
        with localcontext() as context:
            context.prec = 34
            value = sum((score_value * weight for score_value, weight in weighted), Decimal(0)) / sum((weight for _, weight in weighted), Decimal(0))
        score = json_number(quantize(value, decimal_places))
    scores = [decimal_value(row["score"]) for row in valid]
    variation = None
    if scores:
        mean = sum(scores, Decimal(0)) / Decimal(len(scores))
        variance = sum(((value - mean) ** 2 for value in scores), Decimal(0)) / Decimal(len(scores))
        variation = json_number(quantize(variance.sqrt(), decimal_places))
    return {
        "scoreStatus": status,
        "score": score,
        "aggregationMethod": method,
        "scorableAnswerCount": len(valid),
        "answerCount": total_count,
        "answerCoverageRatio": json_number(quantize(coverage, 6)),
        "minimumAnswerScore": json_number(min(scores)) if scores else None,
        "maximumAnswerScore": json_number(max(scores)) if scores else None,
        "scoreVariation": variation,
        "warnings": [],
        "limitations": ["scoreVariation is a numerical dispersion statistic, not a psychological or personality inference."],
    }
