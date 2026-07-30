"""Central Face-Fit Stage 10 metric registry and strict path resolver."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable

from app.vision.evidence_models import _enum_value, _required


class MetricUnit(str, Enum):
    DEGREE = "DEGREE"
    DEGREE_PER_SECOND = "DEGREE_PER_SECOND"
    NORMALIZED_COORDINATE = "NORMALIZED_COORDINATE"
    NORMALIZED_PER_SECOND = "NORMALIZED_PER_SECOND"
    RATIO = "RATIO"
    MILLISECOND = "MILLISECOND"
    COUNT = "COUNT"
    UNITLESS = "UNITLESS"


class MetricValueType(str, Enum):
    FLOAT = "FLOAT"
    INTEGER = "INTEGER"


class MetricDirectionality(str, Enum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    DATA_QUALITY_ONLY = "DATA_QUALITY_ONLY"


class MetricResolutionFailureReason(str, Enum):
    METRIC_PATH_NOT_FOUND = "METRIC_PATH_NOT_FOUND"
    AVAILABILITY_PATH_NOT_FOUND = "AVAILABILITY_PATH_NOT_FOUND"
    METRIC_UNAVAILABLE = "METRIC_UNAVAILABLE"
    METRIC_VALUE_NULL = "METRIC_VALUE_NULL"
    METRIC_VALUE_NON_FINITE = "METRIC_VALUE_NON_FINITE"
    METRIC_VALUE_TYPE_INVALID = "METRIC_VALUE_TYPE_INVALID"


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    source_stage: str
    metric_path: str
    display_name: str
    unit: str
    value_type: str
    directionality: str
    supports_absolute_statistics: bool
    supports_relative_value: bool
    supports_interval_aggregation: bool
    required_availability_group: str
    description: str
    limitations: tuple[str, ...]
    data_quality_metric: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.metric_id, "metric_id"),
            (self.source_stage, "source_stage"),
            (self.metric_path, "metric_path"),
            (self.display_name, "display_name"),
            (self.required_availability_group, "required_availability_group"),
            (self.description, "description"),
        ):
            _required(value, name)
        _enum_value(self.unit, MetricUnit, "unit")
        _enum_value(self.value_type, MetricValueType, "value_type")
        _enum_value(
            self.directionality,
            MetricDirectionality,
            "directionality",
        )
        if any(not part for part in self.metric_path.split(".")):
            raise ValueError("metric_path contains an empty component")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetricValueResolution:
    available: bool
    metric_id: str
    metric_path: str
    value: float | None
    unit: str
    sample_count: int
    availability_ratio: float
    longest_missing_duration_ms: int
    interval_quality_score: float
    target_continuity_ratio: float
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        if isinstance(result, dict):
            return result
    raise TypeError("interval_aggregate must be a dict or to_dict model")


def _resolve_path(payload: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = payload
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            return False, None
        current = current[component]
    return True, current


class FaceFitMetricRegistry:
    def __init__(self, definitions: Iterable[MetricDefinition]) -> None:
        self._definitions: dict[str, MetricDefinition] = {}
        for definition in definitions:
            if definition.metric_id in self._definitions:
                raise ValueError(f"Duplicate metric_id: {definition.metric_id}")
            self._definitions[definition.metric_id] = definition

    @property
    def definitions(self) -> tuple[MetricDefinition, ...]:
        return tuple(
            self._definitions[key] for key in sorted(self._definitions)
        )

    def get(self, metric_id: str) -> MetricDefinition:
        try:
            return self._definitions[metric_id]
        except KeyError as exc:
            raise KeyError(f"Unknown metric_id: {metric_id}") from exc

    def resolve(
        self,
        interval_aggregate: Any,
        metric_id: str,
    ) -> MetricValueResolution:
        definition = self.get(metric_id)
        payload = _payload(interval_aggregate)
        quality = payload.get("data_quality") or {}
        path_exists, value = _resolve_path(payload, definition.metric_path)
        availability_exists, availability = _resolve_path(
            payload,
            definition.required_availability_group,
        )
        base = {
            "metric_id": definition.metric_id,
            "metric_path": definition.metric_path,
            "unit": definition.unit,
            "interval_quality_score": _finite_or_zero(
                quality.get("quality_score")
            ),
            "target_continuity_ratio": _finite_or_zero(
                quality.get("target_continuity_ratio")
            ),
        }
        if not path_exists:
            return MetricValueResolution(
                available=False,
                value=None,
                sample_count=0,
                availability_ratio=0.0,
                longest_missing_duration_ms=0,
                failure_reason=(
                    MetricResolutionFailureReason
                    .METRIC_PATH_NOT_FOUND.value
                ),
                **base,
            )
        if not availability_exists or not isinstance(availability, dict):
            return MetricValueResolution(
                available=False,
                value=None,
                sample_count=0,
                availability_ratio=0.0,
                longest_missing_duration_ms=0,
                failure_reason=(
                    MetricResolutionFailureReason
                    .AVAILABILITY_PATH_NOT_FOUND.value
                ),
                **base,
            )
        parent_path = definition.metric_path.rsplit(".", 1)[0]
        _, parent = _resolve_path(payload, parent_path)
        summary = parent if isinstance(parent, dict) else {}
        sample_count = _integer_or_zero(
            summary.get(
                "count",
                quality.get("total_frame_count", 0),
            )
        )
        availability_ratio = _finite_or_zero(
            availability.get(
                "availability_ratio",
                value if definition.data_quality_metric else 0.0,
            )
        )
        longest_missing = _integer_or_zero(
            availability.get("longest_missing_duration_ms", 0)
        )
        common = {
            **base,
            "sample_count": sample_count,
            "availability_ratio": availability_ratio,
            "longest_missing_duration_ms": longest_missing,
        }
        if availability.get("available") is False:
            return MetricValueResolution(
                available=False,
                value=None,
                failure_reason=(
                    MetricResolutionFailureReason.METRIC_UNAVAILABLE.value
                ),
                **common,
            )
        if value is None:
            return MetricValueResolution(
                available=False,
                value=None,
                failure_reason=(
                    MetricResolutionFailureReason.METRIC_VALUE_NULL.value
                ),
                **common,
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return MetricValueResolution(
                available=False,
                value=None,
                failure_reason=(
                    MetricResolutionFailureReason
                    .METRIC_VALUE_TYPE_INVALID.value
                ),
                **common,
            )
        if not math.isfinite(float(value)):
            return MetricValueResolution(
                available=False,
                value=None,
                failure_reason=(
                    MetricResolutionFailureReason
                    .METRIC_VALUE_NON_FINITE.value
                ),
                **common,
            )
        return MetricValueResolution(
            available=True,
            value=float(value),
            failure_reason=None,
            **common,
        )

    def validate_paths(self, interval_aggregate: Any) -> None:
        payload = _payload(interval_aggregate)
        for definition in self.definitions:
            if not _resolve_path(payload, definition.metric_path)[0]:
                raise ValueError(
                    f"Metric path does not exist: {definition.metric_path}"
                )
            if not _resolve_path(
                payload,
                definition.required_availability_group,
            )[0]:
                raise ValueError(
                    "Availability path does not exist: "
                    f"{definition.required_availability_group}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "definitions": [
                definition.to_dict() for definition in self.definitions
            ]
        }


def _finite_or_zero(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return 0.0
    return float(value)


def _integer_or_zero(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def build_stage10_metric_registry() -> FaceFitMetricRegistry:
    values = (
        MetricDefinition(
            "HEAD_RELATIVE_YAW_ABS_P95_DEG",
            "STAGE_10_INTERVAL_AGGREGATION",
            "head_pose.relative_yaw_deg.absolute_p95",
            "Head relative yaw absolute p95",
            MetricUnit.DEGREE.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.NOT_ESTABLISHED.value,
            True,
            True,
            True,
            "head_pose.availability",
            "Session-relative Head Pose yaw interval statistic.",
            (
                "Approximate PnP angles are camera-setup dependent.",
                "Not a gaze or behavioral measure.",
            ),
        ),
        MetricDefinition(
            "HEAD_RELATIVE_PITCH_ABS_P95_DEG",
            "STAGE_10_INTERVAL_AGGREGATION",
            "head_pose.relative_pitch_deg.absolute_p95",
            "Head relative pitch absolute p95",
            MetricUnit.DEGREE.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.NOT_ESTABLISHED.value,
            True,
            True,
            True,
            "head_pose.availability",
            "Session-relative Head Pose pitch interval statistic.",
            ("Approximate PnP angle; not calibrated physical truth.",),
        ),
        MetricDefinition(
            "HEAD_RELATIVE_ROLL_ABS_P95_DEG",
            "STAGE_10_INTERVAL_AGGREGATION",
            "head_pose.relative_roll_deg.absolute_p95",
            "Head relative roll absolute p95",
            MetricUnit.DEGREE.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.NOT_ESTABLISHED.value,
            True,
            True,
            True,
            "head_pose.availability",
            "Session-relative Head Pose roll interval statistic.",
            ("Not a medical neck or spine assessment.",),
        ),
        MetricDefinition(
            "POSTURE_RELATIVE_SHOULDER_TILT_ABS_P95_DEG",
            "STAGE_10_INTERVAL_AGGREGATION",
            "posture.relative_shoulder_tilt_deg.absolute_p95",
            "Relative shoulder tilt absolute p95",
            MetricUnit.DEGREE.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.NOT_ESTABLISHED.value,
            True,
            True,
            True,
            "posture.shoulder_availability",
            "2D relative shoulder-line tilt proxy.",
            (
                "Does not measure spine, pelvis, or full-body posture.",
            ),
        ),
        MetricDefinition(
            "POSTURE_SHOULDER_CENTER_VELOCITY_P95_NORM_PER_SEC",
            "STAGE_10_INTERVAL_AGGREGATION",
            "posture.shoulder_center_velocity_norm_per_sec.p95",
            "Shoulder center velocity p95",
            MetricUnit.NORMALIZED_PER_SECOND.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.NOT_ESTABLISHED.value,
            False,
            False,
            True,
            "posture.shoulder_availability",
            "Existing timestamp-based 2D shoulder-center velocity.",
            ("Image-normalized and dependent on camera framing.",),
        ),
        MetricDefinition(
            "POSTURE_RELATIVE_NOSE_OFFSET_X_ABS_P95_NORM",
            "STAGE_10_INTERVAL_AGGREGATION",
            "posture.relative_nose_shoulder_offset_x_norm.absolute_p95",
            "Relative nose-shoulder horizontal offset absolute p95",
            MetricUnit.RATIO.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.NOT_ESTABLISHED.value,
            True,
            True,
            True,
            "posture.nose_alignment_availability",
            "Nose offset normalized by shoulder width.",
            ("A head-to-shoulder alignment proxy, not torso diagnosis.",),
        ),
        MetricDefinition(
            "QUALITY_HEAD_AVAILABILITY_RATIO",
            "STAGE_10_INTERVAL_AGGREGATION",
            "data_quality.head_pose_availability_ratio",
            "Head Pose availability ratio",
            MetricUnit.RATIO.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.DATA_QUALITY_ONLY.value,
            False,
            False,
            True,
            "data_quality",
            "Data availability gate input only.",
            ("Never convert missing detection into a posture penalty.",),
            data_quality_metric=True,
        ),
        MetricDefinition(
            "QUALITY_POSTURE_AVAILABILITY_RATIO",
            "STAGE_10_INTERVAL_AGGREGATION",
            "data_quality.posture_availability_ratio",
            "Shoulder posture availability ratio",
            MetricUnit.RATIO.value,
            MetricValueType.FLOAT.value,
            MetricDirectionality.DATA_QUALITY_ONLY.value,
            False,
            False,
            True,
            "data_quality",
            "Data availability gate input only.",
            ("Not a posture-quality measure.",),
            data_quality_metric=True,
        ),
    )
    return FaceFitMetricRegistry(values)
