"""Metric-level quality gate; missing data is never converted to zero."""

from __future__ import annotations

from typing import Any

from .scoring_models import decimal_value

GATE_FIELDS = (
    ("minimumSampleCount", "sampleCount", "INSUFFICIENT_DATA", "minimum"),
    ("minimumAvailabilityRatio", "availabilityRatio", "LOW_AVAILABILITY", "minimum"),
    ("maximumMissingRatio", "missingRatio", "HIGH_MISSING_RATIO", "maximum"),
    ("minimumAnswerDurationMs", "answerDurationMs", "ANSWER_TOO_SHORT", "minimum"),
    ("minimumWordCount", "wordCount", "INSUFFICIENT_WORDS", "minimum"),
    ("minimumVoicedFrameRatio", "voicedFrameRatio", "INSUFFICIENT_VOICED_FRAMES", "minimum"),
)


def evaluate_quality(quality: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for rule_key, value_key, code, comparison in GATE_FIELDS:
        if rule_key not in gate or gate[rule_key] is None:
            continue
        value = quality.get(value_key)
        if value is None:
            failures.append(code)
            continue
        try:
            actual = decimal_value(value, value_key)
            expected = decimal_value(gate[rule_key], rule_key)
        except ValueError:
            failures.append(code)
            continue
        if (comparison == "minimum" and actual < expected) or (comparison == "maximum" and actual > expected):
            failures.append(code)
    if gate.get("timestampValidityRequired") is True and quality.get("timestampValid") is not True:
        failures.append("INVALID_TIMESTAMP")
    failures = list(dict.fromkeys(failures))
    return {
        "passed": not failures,
        "qualityStatus": "PASSED" if not failures else failures[0],
        "failureReasons": failures,
    }
