"""Deterministic state machine that prevents opportunistic target switching."""

from __future__ import annotations

from typing import Any

from app.vision.target_candidate_matcher import calculate_tracking_match
from app.vision.target_tracking_models import (
    TargetCandidate,
    TargetStatus,
    TrackingConfiguration,
)


class SingleTargetTracker:
    def __init__(self, configuration: TrackingConfiguration = TrackingConfiguration()) -> None:
        self.configuration = configuration
        self.target_id = "TARGET_001"
        self.reference: TargetCandidate | None = None
        self.status = TargetStatus.UNINITIALIZED
        self.last_seen_timestamp_ms: int | None = None
        self.lost_since_timestamp_ms: int | None = None
        self._event_sequence = 0

    def select_initial_target(
        self,
        frames: list[tuple[int, list[TargetCandidate]]],
    ) -> TargetCandidate | None:
        if not frames:
            return None
        first_candidates = [candidate for candidate in frames[0][1] if candidate.initialization_ready]
        if not first_candidates:
            return None
        scored: list[tuple[float, TargetCandidate]] = []
        for initial in first_candidates:
            center_distance = (
                ((initial.face_center["x"] - .5) ** 2 + (initial.face_center["y"] - .5) ** 2) ** .5
                if initial.face_center else 1.0
            )
            persistence_costs = []
            for _, candidates in frames[1:]:
                matches = [calculate_tracking_match(initial, candidate).cost for candidate in candidates]
                persistence_costs.append(min(matches) if matches else 1.0)
            persistence = sum(persistence_costs) / len(persistence_costs) if persistence_costs else 0.0
            size_reward = min(initial.shoulder_width or 0.0, .6)
            score = persistence * .55 + center_distance * .30 - size_reward * .15 - initial.detection_confidence * .10
            scored.append((score, initial))
        return min(scored, key=lambda value: (value[0], value[1].candidate_index))[1]

    def initialize(self, candidate: TargetCandidate, timestamp_ms: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        self.reference = candidate
        self.status = TargetStatus.TARGET_INITIALIZED
        self.last_seen_timestamp_ms = timestamp_ms
        return self._result(timestamp_ms, [candidate], candidate.candidate_index, 1.0, False, True, None, None, None), [
            self._event(timestamp_ms, "TARGET_INITIALIZED", [candidate], candidate.candidate_index, 1.0, {})
        ]

    def update(self, timestamp_ms: int, candidates: list[TargetCandidate]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if self.reference is None:
            return self._result(timestamp_ms, candidates, None, 0.0, False, False, None, None, "NO_INITIAL_TARGET"), []
        matches = sorted(
            (calculate_tracking_match(self.reference, candidate) for candidate in candidates),
            key=lambda match: (match.cost, match.candidate_index),
        )
        acceptable = [match for match in matches if match.cost <= self.configuration.match_cost_threshold]
        best = acceptable[0] if acceptable else None
        second = acceptable[1] if len(acceptable) > 1 else None
        margin = second.cost - best.cost if best and second else None
        ambiguous = bool(best and second and margin < self.configuration.ambiguity_margin_threshold)
        events: list[dict[str, Any]] = []
        if ambiguous:
            previous = self.status
            self.status = TargetStatus.MULTIPLE_PERSON_AMBIGUOUS
            if previous != self.status:
                events.append(self._event(timestamp_ms, self.status.value, candidates, None, 0.0, {
                    "best_candidate_score": best.cost,
                    "second_candidate_score": second.cost,
                    "score_margin": margin,
                    "ambiguity_reason": "CANDIDATE_SCORE_MARGIN_TOO_SMALL",
                }))
            return self._result(timestamp_ms, candidates, None, 0.0, True, False, best.cost, second.cost, "CANDIDATE_SCORE_MARGIN_TOO_SMALL"), events
        if best is None:
            if self.lost_since_timestamp_ms is None:
                self.lost_since_timestamp_ms = timestamp_ms
            elapsed = timestamp_ms - self.lost_since_timestamp_ms
            next_status = (
                TargetStatus.TARGET_LOST
                if elapsed > self.configuration.maximum_lost_duration_ms
                else TargetStatus.TARGET_TEMPORARILY_LOST
            )
            if self.status != next_status:
                self.status = next_status
                events.append(self._event(timestamp_ms, next_status.value, candidates, None, 0.0, {
                    "lost_duration_ms": elapsed,
                    "ambiguity_reason": "NO_ACCEPTABLE_TARGET_MATCH",
                }))
            return self._result(timestamp_ms, candidates, None, 0.0, bool(candidates), False, matches[0].cost if matches else None, matches[1].cost if len(matches) > 1 else None, "NO_ACCEPTABLE_TARGET_MATCH"), events
        selected = candidates[best.candidate_index]
        reacquired = self.status in {
            TargetStatus.TARGET_TEMPORARILY_LOST,
            TargetStatus.MULTIPLE_PERSON_AMBIGUOUS,
        }
        next_status = TargetStatus.TARGET_REACQUIRED if reacquired else TargetStatus.TARGET_TRACKED
        if self.status != next_status or reacquired:
            events.append(self._event(timestamp_ms, next_status.value, candidates, selected.candidate_index, best.confidence, {
                "best_candidate_score": best.cost,
                "second_candidate_score": second.cost if second else None,
                "score_margin": margin,
            }))
        self.status = next_status
        self.reference = selected
        self.last_seen_timestamp_ms = timestamp_ms
        self.lost_since_timestamp_ms = None
        switch_risk = best.cost >= self.configuration.switch_risk_cost_threshold
        if switch_risk:
            events.append(self._event(timestamp_ms, "TARGET_SWITCH_RISK", candidates, selected.candidate_index, best.confidence, {
                "best_candidate_score": best.cost,
                "second_candidate_score": second.cost if second else None,
                "score_margin": margin,
                "ambiguity_reason": "MATCH_COST_ELEVATED",
            }))
        return self._result(timestamp_ms, candidates, selected.candidate_index, best.confidence, switch_risk, reacquired, best.cost, second.cost if second else None, None), events

    def _result(
        self, timestamp_ms: int, candidates: list[TargetCandidate],
        selected: int | None, confidence: float, risk: bool, reacquired: bool,
        best: float | None, second: float | None, reason: str | None,
    ) -> dict[str, Any]:
        return {
            "timestamp_ms": timestamp_ms,
            "target_status": self.status.value,
            "target_id": self.target_id if self.reference else None,
            "target_confidence": confidence,
            "candidate_count": len(candidates),
            "selected_candidate_index": selected,
            "target_switch_risk": risk,
            "reacquired": reacquired,
            "best_candidate_score": best,
            "second_candidate_score": second,
            "score_margin": second - best if best is not None and second is not None else None,
            "ambiguity_reason": reason,
        }

    def _event(
        self, timestamp_ms: int, event_type: str, candidates: list[TargetCandidate],
        selected: int | None, confidence: float, details: dict[str, Any],
    ) -> dict[str, Any]:
        self._event_sequence += 1
        return {
            "event_sequence": self._event_sequence,
            "timestamp_ms": timestamp_ms,
            "event_type": event_type,
            "target_id": self.target_id,
            "candidate_count": len(candidates),
            "selected_candidate_index": selected,
            "target_confidence": confidence,
            "details": details,
        }
