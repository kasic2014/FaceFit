"""Orchestrate profile validation, metric scoring, and aggregation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import ENGINE_VERSION
from .answer_aggregator import aggregate_answer
from .axis_aggregator import aggregate_axis
from .metric_scorer import score_metric
from .profile_validator import profile_hash, require_production_approval, validate_profile
from .scoring_errors import EXPERIMENTAL_NOT_ENABLED, PROFILE_NOT_APPROVED, ScoringError
from .scoring_models import AXES, MetricInput
from .session_aggregator import aggregate_session_scores


def disabled_result(session_id: str, reason: str = "THRESHOLD_EVIDENCE_NOT_APPROVED") -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "scoringMode": "DISABLED",
        "scoringAvailable": False,
        "scoreStatus": "NOT_AVAILABLE",
        "score": None,
        "reason": reason,
    }


def score_payload(
    payload: dict[str, Any],
    profile: dict[str, Any],
    inventory: dict[str, Any],
    *,
    mode: str = "EXPERIMENTAL",
    allow_experimental: bool = False,
) -> dict[str, Any]:
    session_id = str(payload.get("sessionId", ""))
    if mode == "DISABLED":
        return disabled_result(session_id)
    validation = validate_profile(profile, inventory)
    if mode == "EXPERIMENTAL":
        if profile.get("status") != "EXPERIMENTAL" or profile.get("productionApproved") is not False or not allow_experimental:
            raise ScoringError(EXPERIMENTAL_NOT_ENABLED, "Experimental scoring requires an explicit opt-in and experimental profile")
    elif mode == "PRODUCTION":
        try:
            require_production_approval(profile, inventory)
        except Exception as exc:
            raise ScoringError(PROFILE_NOT_APPROVED, "Production scoring failed closed") from exc
    else:
        raise ScoringError("SCORING_MODE_INVALID", f"Unsupported scoring mode: {mode}")
    if mode == "EXPERIMENTAL" and session_id == "SES_000001":
        raise ScoringError(EXPERIMENTAL_NOT_ENABLED, "Synthetic thresholds must not be applied to SES_000001")
    rules = {row["metricId"]: row for row in profile["metricRules"]}
    axis_rules = {row["axis"]: row for row in profile["axisRules"]}
    input_rows = payload.get("metricInputs", [])
    if not isinstance(input_rows, list):
        raise ScoringError("SCORING_INPUT_INVALID", "metricInputs must be an array")
    grouped: dict[str, list[MetricInput]] = {}
    seen_inputs: set[tuple[str, str]] = set()
    for row in input_rows:
        metric = MetricInput.from_dict(row)
        if metric.session_id != session_id or not metric.answer_id:
            raise ScoringError("SCORING_INPUT_INVALID", "Metric input identifiers are inconsistent")
        key = (metric.answer_id, metric.metric_id)
        if key in seen_inputs:
            raise ScoringError("SCORING_INPUT_INVALID", f"Duplicate metric input: {metric.answer_id}/{metric.metric_id}")
        seen_inputs.add(key)
        grouped.setdefault(metric.answer_id, []).append(metric)
    metadata = {row.get("answerId"): row for row in payload.get("answers", []) if isinstance(row, dict)}
    answers: list[dict[str, Any]] = []
    all_metric_results: list[dict[str, Any]] = []
    for answer_id in sorted(grouped):
        metric_results: list[dict[str, Any]] = []
        for metric in grouped[answer_id]:
            rule = rules.get(metric.metric_id)
            if rule is None:
                metric_results.append({
                    "metricId": metric.metric_id, "axis": metric.axis,
                    "scoreStatus": "UNSUPPORTED", "rawValue": metric.value,
                    "unit": metric.unit, "score": None, "weight": None,
                    "qualityStatus": "NOT_EVALUATED", "scoringFunction": None,
                    "metricRuleId": None, "evidenceIds": [],
                    "warnings": ["UNSUPPORTED_METRIC"], "limitations": [],
                })
            else:
                metric_results.append(score_metric(metric, rule, profile["scoreScale"]))
        present = {row.metric_id for row in grouped[answer_id]}
        for metric_id, rule in rules.items():
            if metric_id not in present:
                metric_results.append({
                    "metricId": metric_id, "axis": rule["axis"], "scoreStatus": "NOT_SCORABLE",
                    "rawValue": None, "unit": rule["unit"], "score": None, "weight": rule["weight"],
                    "qualityStatus": "INSUFFICIENT_DATA", "scoringFunction": rule["scoringFunction"],
                    "metricRuleId": rule["metricRuleId"], "evidenceIds": list(rule["evidenceIds"]),
                    "warnings": ["METRIC_MISSING"], "limitations": list(rule.get("limitations", [])),
                })
        axis_results = [aggregate_axis(metric_results, axis_rules[axis], int(profile["scoreScale"]["decimalPlaces"])) for axis in AXES if axis in axis_rules]
        answer = aggregate_answer(answer_id, axis_results, profile)
        answer["metricScores"] = sorted(metric_results, key=lambda row: row["metricId"])
        meta = metadata.get(answer_id, {})
        answer["answerDurationMs"] = int(meta.get("answerDurationMs", 0))
        answer["validSampleCount"] = int(meta.get("validSampleCount", 0))
        answers.append(answer)
        all_metric_results.extend(metric_results)
    session_axes: dict[str, Any] = {}
    for axis in AXES:
        rows = []
        for answer in answers:
            axis_result = answer["axisScores"].get(axis)
            if axis_result:
                rows.append({**axis_result, "answerDurationMs": answer["answerDurationMs"], "validSampleCount": answer["validSampleCount"]})
        if rows:
            session_axes[axis] = aggregate_session_scores(rows, profile["sessionAggregation"], int(profile["scoreScale"]["decimalPlaces"]))
    overall_enabled = profile.get("overallRule", {}).get("enabled") is True
    overall_rows = [
        {"scoreStatus": answer["scoreStatus"], "score": answer["overallScore"], "answerDurationMs": answer["answerDurationMs"], "validSampleCount": answer["validSampleCount"]}
        for answer in answers
    ]
    overall = aggregate_session_scores(overall_rows, profile["sessionAggregation"], int(profile["scoreScale"]["decimalPlaces"])) if overall_enabled else None
    generated_at = payload.get("generatedAt") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = {
        "sessionId": session_id,
        "scoringMode": mode,
        "scoringAvailable": True,
        "scoreStatus": overall["scoreStatus"] if overall else ("PARTIAL" if any(value["score"] is not None for value in session_axes.values()) else "NOT_SCORABLE"),
        "profileId": profile["profileId"],
        "profileVersion": profile["version"],
        "profileHash": validation["profileHash"],
        "engineVersion": ENGINE_VERSION,
        "generatedAt": generated_at,
        "answers": answers,
        "sessionAxisScores": session_axes,
        "overallScoreAvailable": bool(overall and overall["score"] is not None),
        "overallScore": overall["score"] if overall else None,
        "evidenceIds": sorted({evidence for rule in profile["metricRules"] for evidence in rule["evidenceIds"]}),
        "warnings": [],
        "limitations": [
            "Experimental coaching feedback only; not a hiring, job-fit, personality, emotion, anxiety, confidence, deception, gender, or health inference.",
            "Implementation readiness does not approve real-user thresholds or weights.",
        ],
    }
    return result
