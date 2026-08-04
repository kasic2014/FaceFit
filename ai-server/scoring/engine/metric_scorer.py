"""Decimal-based PIECEWISE_LINEAR and BAND_LOOKUP scorers."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from .quality_gate import evaluate_quality
from .scoring_models import MetricInput, decimal_value, json_number, quantize


def _base(metric: MetricInput, rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "metricId": metric.metric_id,
        "axis": metric.axis,
        "rawValue": metric.value,
        "unit": metric.unit,
        "weight": rule.get("weight"),
        "scoringFunction": rule.get("scoringFunction"),
        "metricRuleId": rule.get("metricRuleId"),
        "evidenceIds": list(rule.get("evidenceIds", [])),
        "warnings": [],
        "limitations": list(rule.get("limitations", [])),
    }


def _not_scorable(metric: MetricInput, rule: dict[str, Any], quality_status: str, reasons: list[str]) -> dict[str, Any]:
    return {
        **_base(metric, rule),
        "scoreStatus": "NOT_SCORABLE",
        "score": None,
        "qualityStatus": quality_status,
        "warnings": reasons,
    }


def _piecewise(value: Decimal, rule: dict[str, Any]) -> Decimal | None:
    anchors = [(decimal_value(item["value"]), decimal_value(item["score"])) for item in rule["anchors"]]
    if value < anchors[0][0]:
        return anchors[0][1] if rule["clampOutsideRange"] else None
    if value > anchors[-1][0]:
        return anchors[-1][1] if rule["clampOutsideRange"] else None
    for anchor_value, anchor_score in anchors:
        if value == anchor_value:
            return anchor_score
    for (left_value, left_score), (right_value, right_score) in zip(anchors, anchors[1:]):
        if left_value < value < right_value:
            with localcontext() as context:
                context.prec = 34
                return left_score + (value - left_value) * (right_score - left_score) / (right_value - left_value)
    return None


def _band(value: Decimal, rule: dict[str, Any]) -> Decimal | None:
    for band in rule["bands"]:
        low = decimal_value(band["minimum"])
        high = decimal_value(band["maximum"])
        lower_ok = value > low or (value == low and band["minimumInclusive"])
        upper_ok = value < high or (value == high and band["maximumInclusive"])
        if lower_ok and upper_ok:
            return decimal_value(band["score"])
    return None


def score_metric(metric: MetricInput | dict[str, Any], rule: dict[str, Any], score_scale: dict[str, Any]) -> dict[str, Any]:
    metric = MetricInput.from_dict(metric) if isinstance(metric, dict) else metric
    if metric.value is None:
        return _not_scorable(metric, rule, "INSUFFICIENT_DATA", ["METRIC_VALUE_MISSING"])
    if metric.metric_id != rule.get("metricId") or metric.axis != rule.get("axis") or metric.unit != rule.get("unit"):
        result = _base(metric, rule)
        result.update(scoreStatus="PROFILE_ERROR", score=None, qualityStatus="NOT_EVALUATED", warnings=["METRIC_RULE_CONTRACT_MISMATCH"])
        return result
    try:
        value = decimal_value(metric.value)
    except ValueError:
        return _not_scorable(metric, rule, "INSUFFICIENT_DATA", ["METRIC_VALUE_NON_FINITE"])
    gate = evaluate_quality(metric.quality, rule.get("qualityGate", {}))
    if not gate["passed"]:
        return _not_scorable(metric, rule, gate["qualityStatus"], gate["failureReasons"])
    if rule["scoringFunction"] == "PIECEWISE_LINEAR":
        score = _piecewise(value, rule)
    elif rule["scoringFunction"] == "BAND_LOOKUP":
        score = _band(value, rule)
    else:
        score = None
    if score is None:
        return _not_scorable(metric, rule, "PASSED", ["VALUE_OUTSIDE_SCORABLE_RANGE"])
    minimum = decimal_value(score_scale["minimum"])
    maximum = decimal_value(score_scale["maximum"])
    if score < minimum or score > maximum:
        result = _base(metric, rule)
        result.update(scoreStatus="PROFILE_ERROR", score=None, qualityStatus="PASSED", warnings=["SCORE_OUTSIDE_PROFILE_SCALE"])
        return result
    places = int(score_scale["decimalPlaces"])
    result = _base(metric, rule)
    result.update(scoreStatus="SCORED", score=json_number(quantize(score, places)), qualityStatus="PASSED")
    return result
