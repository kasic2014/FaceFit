from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def read(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def inventory():
    return read("registries/metric-inventory-v1.json")


def profile():
    return read("fixtures/profiles/experimental-scoring-profile-v1.json")


def payload():
    return read("fixtures/inputs/synthetic-scoring-input-v1.json")


def metric_input(metric_id: str, value=10, **quality):
    rule = next(row for row in profile()["metricRules"] if row["metricId"] == metric_id)
    base_quality = {"sampleCount": 100, "availabilityRatio": 1, "missingRatio": 0, "answerDurationMs": 30000, "wordCount": 50, "voicedFrameRatio": 0.8, "timestampValid": True}
    base_quality.update(quality)
    return {
        "sessionId": "SES_900001", "answerId": "ANS_900001", "metricId": metric_id,
        "axis": rule["axis"], "value": value, "unit": rule["unit"], "scope": "ANSWER",
        "quality": base_quality, "source": {"service": "VISION", "artifactHash": None},
    }, deepcopy(rule)
