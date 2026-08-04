"""Dependency-free scoring models and Decimal helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

AXES = ("GAZE_HEAD", "POSTURE", "SPEECH_DELIVERY")
SCORE_STATUSES = ("SCORED", "PARTIAL", "NOT_SCORABLE", "UNSUPPORTED", "PROFILE_ERROR")


def decimal_value(value: Any, name: str = "value") -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a finite number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def quantize(value: Decimal, places: int) -> Decimal:
    quantum = Decimal(1).scaleb(-places)
    with localcontext() as context:
        context.prec = 34
        return value.quantize(quantum, rounding=ROUND_HALF_UP)


def json_number(value: Decimal, places: int | None = None) -> int | float:
    result = quantize(value, places) if places is not None else value
    return int(result) if result == result.to_integral() else float(result)


@dataclass(frozen=True)
class MetricInput:
    session_id: str
    answer_id: str
    metric_id: str
    axis: str
    value: int | float | None
    unit: str
    scope: str = "ANSWER"
    quality: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "MetricInput":
        return cls(
            session_id=str(row.get("sessionId", "")),
            answer_id=str(row.get("answerId", "")),
            metric_id=str(row.get("metricId", "")),
            axis=str(row.get("axis", "")),
            value=row.get("value"),
            unit=str(row.get("unit", "")),
            scope=str(row.get("scope", "ANSWER")),
            quality=dict(row.get("quality") or {}),
            source=dict(row.get("source") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {
            "sessionId": payload["session_id"],
            "answerId": payload["answer_id"],
            "metricId": payload["metric_id"],
            "axis": payload["axis"],
            "value": payload["value"],
            "unit": payload["unit"],
            "scope": payload["scope"],
            "quality": payload["quality"],
            "source": payload["source"],
        }
