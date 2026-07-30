"""Normalized geometry association and temporal matching costs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.vision.target_tracking_models import MatchResult, TargetCandidate


@dataclass(frozen=True)
class MatchWeights:
    face_center_distance: float = 0.20
    nose_distance: float = 0.18
    shoulder_center_distance: float = 0.22
    shoulder_width_change: float = 0.12
    bbox_size_change: float = 0.10
    bbox_iou_cost: float = 0.18


DEFAULT_MATCH_WEIGHTS = MatchWeights()


def _distance(left: Any, right: Any) -> float | None:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    try:
        return math.hypot(float(right["x"]) - float(left["x"]), float(right["y"]) - float(left["y"]))
    except (KeyError, TypeError, ValueError):
        return None


def calculate_bbox_iou(left: Any, right: Any) -> float | None:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    try:
        ix1, iy1 = max(left["min_x"], right["min_x"]), max(left["min_y"], right["min_y"])
        ix2, iy2 = min(left["max_x"], right["max_x"]), min(left["max_y"], right["max_y"])
        intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        left_area = max(0.0, left["max_x"] - left["min_x"]) * max(0.0, left["max_y"] - left["min_y"])
        right_area = max(0.0, right["max_x"] - right["min_x"]) * max(0.0, right["max_y"] - right["min_y"])
        union = left_area + right_area - intersection
        return intersection / union if union > 0 else None
    except (KeyError, TypeError, ValueError):
        return None


def _bbox_area(box: Any) -> float | None:
    if not isinstance(box, dict):
        return None
    try:
        return max(0.0, box["max_x"] - box["min_x"]) * max(0.0, box["max_y"] - box["min_y"])
    except (KeyError, TypeError, ValueError):
        return None


def _relative_change(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None or previous <= 0:
        return None
    return min(abs(current - previous) / previous, 1.0)


def calculate_tracking_match(
    reference: TargetCandidate,
    candidate: TargetCandidate,
    weights: MatchWeights = DEFAULT_MATCH_WEIGHTS,
) -> MatchResult:
    iou = calculate_bbox_iou(reference.face_bounding_box, candidate.face_bounding_box)
    components = {
        "face_center_distance": _distance(reference.face_center, candidate.face_center),
        "nose_distance": _distance(reference.nose, candidate.nose),
        "shoulder_center_distance": _distance(reference.shoulder_center, candidate.shoulder_center),
        "shoulder_width_change": _relative_change(reference.shoulder_width, candidate.shoulder_width),
        "bbox_size_change": _relative_change(_bbox_area(reference.face_bounding_box), _bbox_area(candidate.face_bounding_box)),
        "bbox_iou_cost": 1.0 - iou if iou is not None else None,
    }
    total, active = 0.0, 0.0
    for name, value in components.items():
        if value is None:
            continue
        weight = getattr(weights, name)
        total += weight * min(max(value, 0.0), 1.0)
        active += weight
    cost = total / active if active else 1.0
    confidence = max(0.0, min(1.0, (1.0 - cost) * candidate.detection_confidence))
    return MatchResult(candidate.candidate_index, cost, confidence, components)


def calculate_face_pose_consistency(
    face_center: dict[str, float],
    face_box: dict[str, float],
    nose: dict[str, float],
    shoulder_center: dict[str, float],
    shoulder_width: float,
) -> float | None:
    if shoulder_width <= 0:
        return None
    horizontal = abs(face_center["x"] - shoulder_center["x"]) / shoulder_width
    vertical = (shoulder_center["y"] - face_center["y"]) / shoulder_width
    nose_face = _distance(nose, face_center)
    if vertical <= 0 or horizontal > 1.0 or vertical > 2.2 or nose_face is None:
        return None
    inside_expanded = (
        face_box["min_x"] - .1 <= nose["x"] <= face_box["max_x"] + .1
        and face_box["min_y"] - .1 <= nose["y"] <= face_box["max_y"] + .1
    )
    if not inside_expanded:
        return None
    return horizontal * .45 + abs(vertical - .75) * .35 + min(nose_face, 1.0) * .20
