"""2D geometry for shoulder and head-to-shoulder alignment raw metrics."""

from __future__ import annotations

import math
from typing import Any

from app.vision.posture_raw_models import (
    COORDINATE_SPACE,
    HORIZONTAL_SIGN_CONVENTION,
    SHOULDER_SIGN_CONVENTION,
    PostureFailureReason,
    PostureRawConfiguration,
    ShoulderPostureRawResult,
)


def _finite_point(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        x, y = float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    point = {"x": x, "y": y}
    for key in ("visibility", "presence"):
        candidate = value.get(key)
        if candidate is not None:
            try:
                number = float(candidate)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                point[key] = number
    return point


def _point_non_finite(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for key in ("x", "y"):
        candidate = value.get(key)
        if candidate is None:
            continue
        try:
            if not math.isfinite(float(candidate)):
                return True
        except (TypeError, ValueError):
            return True
    return False


def _point_quality(point: dict[str, float] | None) -> float:
    if point is None:
        return 0.0
    values = [
        max(0.0, min(1.0, float(point[key])))
        for key in ("visibility", "presence")
        if key in point
    ]
    return sum(values) / len(values) if values else 0.75


def _range_quality(
    points: list[dict[str, float] | None],
    configuration: PostureRawConfiguration,
) -> float:
    valid = [point for point in points if point is not None]
    if not valid:
        return 0.0
    inside = 0
    lower, upper = -configuration.coordinate_margin, 1.0 + configuration.coordinate_margin
    for point in valid:
        if lower <= point["x"] <= upper and lower <= point["y"] <= upper:
            inside += 1
    return inside / len(valid)


def _unavailable(
    reason: PostureFailureReason,
    *,
    status_codes: tuple[str, ...] | None = None,
) -> ShoulderPostureRawResult:
    return ShoulderPostureRawResult(
        available=False,
        shoulders_available=False,
        nose_alignment_available=False,
        face_alignment_available=False,
        shoulder_tilt_deg=None,
        shoulder_height_difference_norm=None,
        shoulder_center_x=None,
        shoulder_center_y=None,
        shoulder_width_norm=None,
        nose_shoulder_offset_x_norm=None,
        nose_shoulder_offset_y_norm=None,
        face_shoulder_offset_x_norm=None,
        face_shoulder_offset_y_norm=None,
        confidence=0.0,
        coordinate_space=COORDINATE_SPACE,
        horizontal_sign_convention=HORIZONTAL_SIGN_CONVENTION,
        shoulder_sign_convention=SHOULDER_SIGN_CONVENTION,
        failure_reason=reason.value,
        status_codes=status_codes or (reason.value,),
    )


def estimate_shoulder_posture(
    left_shoulder: Any,
    right_shoulder: Any,
    nose: Any,
    face_center: Any,
    *,
    target_id: str | None,
    target_confidence: float = 0.0,
    candidate_count: int = 1,
    previous_available: bool = False,
    configuration: PostureRawConfiguration = PostureRawConfiguration(),
) -> ShoulderPostureRawResult:
    """Calculate raw metrics using only the selected target's 2D points."""

    if candidate_count >= 2:
        return _unavailable(PostureFailureReason.MULTIPLE_PERSON_DETECTED)
    if target_id != "TARGET_001":
        return _unavailable(PostureFailureReason.TARGET_NOT_AVAILABLE)
    non_finite = any(
        _point_non_finite(value)
        for value in (left_shoulder, right_shoulder, nose, face_center)
    )
    left, right = _finite_point(left_shoulder), _finite_point(right_shoulder)
    nose_point, face_point = _finite_point(nose), _finite_point(face_center)
    if left is None and right is None:
        reason = (
            PostureFailureReason.NON_FINITE_COORDINATE
            if non_finite
            else PostureFailureReason.BOTH_SHOULDERS_MISSING
        )
        return _unavailable(reason)
    if left is None:
        reason = (
            PostureFailureReason.NON_FINITE_COORDINATE
            if _point_non_finite(left_shoulder)
            else PostureFailureReason.LEFT_SHOULDER_MISSING
        )
        return _unavailable(reason)
    if right is None:
        reason = (
            PostureFailureReason.NON_FINITE_COORDINATE
            if _point_non_finite(right_shoulder)
            else PostureFailureReason.RIGHT_SHOULDER_MISSING
        )
        return _unavailable(reason)

    dx, dy = right["x"] - left["x"], right["y"] - left["y"]
    width = math.hypot(dx, dy)
    if not math.isfinite(width) or width < configuration.minimum_shoulder_width_norm:
        return _unavailable(PostureFailureReason.INVALID_SHOULDER_WIDTH)
    center_x = (left["x"] + right["x"]) / 2.0
    center_y = (left["y"] + right["y"]) / 2.0
    horizontal_distance = abs(dx)
    tilt = math.degrees(math.atan2(dy, horizontal_distance))
    height_difference = dy / width

    nose_available = nose_point is not None
    face_available = face_point is not None
    status_codes = [PostureFailureReason.SHOULDERS_AVAILABLE.value]
    if not nose_available:
        status_codes.append(
            PostureFailureReason.NON_FINITE_COORDINATE.value
            if _point_non_finite(nose)
            else PostureFailureReason.NOSE_MISSING.value
        )
    if not face_available:
        status_codes.append(
            PostureFailureReason.NON_FINITE_COORDINATE.value
            if _point_non_finite(face_center)
            else PostureFailureReason.FACE_NOT_DETECTED.value
        )
    failure_reason = status_codes[1] if len(status_codes) > 1 else None

    target_quality = max(0.0, min(1.0, float(target_confidence)))
    shoulder_quality = (_point_quality(left) + _point_quality(right)) / 2.0
    nose_quality = _point_quality(nose_point)
    face_quality = 1.0 if face_available else 0.0
    coordinate_quality = _range_quality(
        [left, right, nose_point, face_point], configuration
    )
    width_quality = max(
        0.0,
        min(
            1.0,
            (width - configuration.minimum_shoulder_width_norm)
            / (
                configuration.expected_shoulder_width_norm
                - configuration.minimum_shoulder_width_norm
            ),
        ),
    )
    temporal_quality = 1.0 if previous_available else 0.5
    confidence = (
        configuration.target_quality_weight * target_quality
        + configuration.shoulder_quality_weight * shoulder_quality
        + configuration.nose_quality_weight * nose_quality
        + configuration.face_quality_weight * face_quality
        + configuration.coordinate_quality_weight * coordinate_quality
        + configuration.width_quality_weight * width_quality
        + configuration.temporal_quality_weight * temporal_quality
    )

    def offset(point: dict[str, float] | None) -> tuple[float | None, float | None]:
        if point is None:
            return None, None
        return (
            (point["x"] - center_x) / width,
            (point["y"] - center_y) / width,
        )

    nose_x, nose_y = offset(nose_point)
    face_x, face_y = offset(face_point)
    values = (
        tilt,
        height_difference,
        center_x,
        center_y,
        width,
        nose_x,
        nose_y,
        face_x,
        face_y,
        confidence,
    )
    if any(value is not None and not math.isfinite(value) for value in values):
        return _unavailable(PostureFailureReason.NON_FINITE_COORDINATE)
    return ShoulderPostureRawResult(
        available=True,
        shoulders_available=True,
        nose_alignment_available=nose_available,
        face_alignment_available=face_available,
        shoulder_tilt_deg=tilt,
        shoulder_height_difference_norm=height_difference,
        shoulder_center_x=center_x,
        shoulder_center_y=center_y,
        shoulder_width_norm=width,
        nose_shoulder_offset_x_norm=nose_x,
        nose_shoulder_offset_y_norm=nose_y,
        face_shoulder_offset_x_norm=face_x,
        face_shoulder_offset_y_norm=face_y,
        confidence=max(0.0, min(1.0, confidence)),
        coordinate_space=COORDINATE_SPACE,
        horizontal_sign_convention=HORIZONTAL_SIGN_CONVENTION,
        shoulder_sign_convention=SHOULDER_SIGN_CONVENTION,
        failure_reason=failure_reason,
        status_codes=tuple(status_codes),
    )
