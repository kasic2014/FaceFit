"""Validate external scoring profiles without inferring thresholds or weights."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from .scoring_errors import PROFILE_INVALID, PROFILE_NOT_APPROVED, ScoringError
from .scoring_models import AXES, decimal_value

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def canonical_profile_bytes(profile: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in profile.items() if key != "profileHash"}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def profile_hash(profile: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_profile_bytes(profile)).hexdigest()


def _fail(message: str) -> None:
    raise ScoringError(PROFILE_INVALID, message)


def _unique(rows: list[dict[str, Any]], key: str, label: str) -> None:
    values = [row.get(key) for row in rows]
    if any(not isinstance(value, str) or not value for value in values):
        _fail(f"{label} requires {key}")
    if len(values) != len(set(values)):
        _fail(f"Duplicate {label} {key}")


def _score(value: Any, minimum: Any, maximum: Any, name: str) -> None:
    number = decimal_value(value, name)
    if number < decimal_value(minimum) or number > decimal_value(maximum):
        _fail(f"{name} is outside scoreScale")


def _validate_bands(rule: dict[str, Any], scale: dict[str, Any]) -> None:
    bands = rule.get("bands")
    if not isinstance(bands, list) or not bands:
        _fail("BAND_LOOKUP requires bands")
    normalized: list[tuple[Any, Any, bool, bool]] = []
    for band in bands:
        if not isinstance(band, dict):
            _fail("Band must be an object")
        if "minimumInclusive" not in band or "maximumInclusive" not in band:
            _fail("Band boundary inclusion must be explicit")
        low = decimal_value(band.get("minimum"), "band minimum")
        high = decimal_value(band.get("maximum"), "band maximum")
        if low > high or (low == high and not (band["minimumInclusive"] and band["maximumInclusive"])):
            _fail("Band minimum/maximum is invalid")
        _score(band.get("score"), scale["minimum"], scale["maximum"], "band score")
        normalized.append((low, high, bool(band["minimumInclusive"]), bool(band["maximumInclusive"])))
    normalized.sort(key=lambda item: item[0])
    for previous, current in zip(normalized, normalized[1:]):
        if previous[1] > current[0] or (previous[1] == current[0] and previous[3] and current[2]):
            _fail("Bands overlap")
    if rule.get("unmatchedPolicy") not in {"NOT_SCORABLE"}:
        _fail("Unsupported unmatchedPolicy")


def validate_profile(profile: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict):
        _fail("Profile must be an object")
    if not isinstance(profile.get("profileId"), str) or not profile["profileId"]:
        _fail("profileId is required")
    if not isinstance(profile.get("version"), str) or not SEMVER.fullmatch(profile["version"]):
        _fail("version must be semantic version")
    if profile.get("status") not in {"EXPERIMENTAL", "APPROVED", "DISABLED"}:
        _fail("Unknown profile status")
    scale = profile.get("scoreScale")
    if not isinstance(scale, dict):
        _fail("scoreScale is required")
    low = decimal_value(scale.get("minimum"), "score minimum")
    high = decimal_value(scale.get("maximum"), "score maximum")
    places = scale.get("decimalPlaces")
    if low != 0 or high != 100 or isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 6:
        _fail("Invalid scoreScale")
    metrics = {row.get("metricId"): row for row in inventory.get("metrics", []) if isinstance(row, dict)}
    rules = profile.get("metricRules")
    axes = profile.get("axisRules")
    if not isinstance(rules, list) or not isinstance(axes, list):
        _fail("metricRules and axisRules must be arrays")
    _unique(rules, "metricId", "metric rule")
    _unique(rules, "metricRuleId", "metric rule")
    _unique(axes, "axis", "axis rule")
    for rule in rules:
        metric = metrics.get(rule["metricId"])
        if metric is None:
            _fail(f"Unknown metric: {rule['metricId']}")
        if rule.get("axis") != metric.get("axis") or rule.get("axis") not in AXES:
            _fail(f"Invalid axis for {rule['metricId']}")
        if rule.get("unit") != metric.get("unit"):
            _fail(f"Unit mismatch for {rule['metricId']}")
        weight = decimal_value(rule.get("weight"), "metric weight")
        if weight <= 0 or weight > 1:
            _fail("Metric weight must be within (0, 1]")
        if not isinstance(rule.get("evidenceIds"), list) or not rule["evidenceIds"]:
            _fail("Metric rule requires evidenceIds")
        function = rule.get("scoringFunction")
        if function == "PIECEWISE_LINEAR":
            anchors = rule.get("anchors")
            if not isinstance(anchors, list) or len(anchors) < 2:
                _fail("PIECEWISE_LINEAR requires at least two anchors")
            values = [decimal_value(anchor.get("value"), "anchor value") for anchor in anchors]
            if values != sorted(values) or len(values) != len(set(values)):
                _fail("Anchors must be unique and ascending")
            for anchor in anchors:
                _score(anchor.get("score"), scale["minimum"], scale["maximum"], "anchor score")
            if not isinstance(rule.get("clampOutsideRange"), bool):
                _fail("clampOutsideRange must be boolean")
        elif function == "BAND_LOOKUP":
            _validate_bands(rule, scale)
        else:
            _fail(f"Unsupported scoringFunction: {function}")
    for rule in axes:
        if rule.get("axis") not in AXES:
            _fail(f"Unknown axis: {rule.get('axis')}")
        ratio = decimal_value(rule.get("minimumCoverageRatio"), "minimumCoverageRatio")
        if ratio < 0 or ratio > 1:
            _fail("minimumCoverageRatio must be within 0..1")
        if not isinstance(rule.get("renormalizeAvailableWeights"), bool) or not isinstance(rule.get("allowPartialScore"), bool):
            _fail("Axis partial-score flags must be boolean")
        known_axis_metrics = {item["metricId"] for item in rules if item["axis"] == rule["axis"]}
        if not set(rule.get("requiredMetricIds", [])).issubset(known_axis_metrics):
            _fail("Axis requiredMetricIds references an unknown axis metric")
    answer_aggregation = profile.get("answerAggregation")
    session_aggregation = profile.get("sessionAggregation")
    overall_rule = profile.get("overallRule")
    if not isinstance(answer_aggregation, dict) or not isinstance(answer_aggregation.get("overallEnabled"), bool):
        _fail("answerAggregation.overallEnabled must be boolean")
    if not isinstance(session_aggregation, dict) or session_aggregation.get("method") not in {"EQUAL", "DURATION_WEIGHTED", "VALID_SAMPLE_WEIGHTED"}:
        _fail("Unsupported session aggregation method")
    count = session_aggregation.get("minimumScorableAnswerCount")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        _fail("minimumScorableAnswerCount must be positive")
    answer_coverage = decimal_value(session_aggregation.get("minimumAnswerCoverageRatio"), "minimumAnswerCoverageRatio")
    if not 0 <= answer_coverage <= 1 or not isinstance(session_aggregation.get("allowPartialScore"), bool):
        _fail("Invalid session coverage policy")
    if not isinstance(overall_rule, dict) or not isinstance(overall_rule.get("enabled"), bool):
        _fail("overallRule.enabled must be boolean")
    if overall_rule.get("enabled") and not answer_aggregation.get("overallEnabled"):
        _fail("Session overall requires answer overall aggregation")
    if not isinstance(profile.get("evidenceIds"), list) or not profile["evidenceIds"]:
        _fail("Profile evidenceIds are required")
    declared_hash = profile.get("profileHash")
    computed_hash = profile_hash(profile)
    if declared_hash is not None and declared_hash != computed_hash:
        _fail("Profile hash verification failed")
    return {"valid": True, "profileHash": computed_hash, "warnings": []}


def require_production_approval(profile: dict[str, Any], inventory: dict[str, Any]) -> None:
    try:
        validation = validate_profile(profile, inventory)
        conditions = (
            profile.get("status") == "APPROVED",
            profile.get("productionApproved") is True,
            profile.get("evidenceApprovalStatus") == "APPROVED",
            profile.get("validationStatus") == "PASSED",
            bool(profile.get("approvedBy")),
            bool(profile.get("approvedAt")),
            bool(profile.get("profileHash")),
            profile.get("profileHash") == validation["profileHash"],
        )
        if profile.get("approvedAt"):
            datetime.fromisoformat(str(profile["approvedAt"]).replace("Z", "+00:00"))
        metric_map = {row["metricId"]: row for row in inventory.get("metrics", [])}
        evidence_ok = all(
            metric_map.get(rule["metricId"], {}).get("evidenceStatus") == "APPROVED"
            and metric_map.get(rule["metricId"], {}).get("evidenceRelation")
            for rule in profile.get("metricRules", [])
        )
        if not all(conditions) or not evidence_ok:
            raise ValueError("approval condition missing")
    except Exception as exc:
        if isinstance(exc, ScoringError) and exc.code == PROFILE_NOT_APPROVED:
            raise
        raise ScoringError(PROFILE_NOT_APPROVED, "Production profile approval is incomplete") from exc
