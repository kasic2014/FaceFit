"""Draft annotation-to-existing-metric hypothesis contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from app.vision.annotation_registry import AnnotationRegistry
from app.vision.data_collection_models import _required_id
from app.vision.metric_registry import FaceFitMetricRegistry


@dataclass(frozen=True)
class AnnotationMetricHypothesis:
    hypothesis_id: str
    label_id: str
    metric_id: str
    mapping_type: str
    expected_relationship: str
    status: str
    rationale: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_id(self.hypothesis_id, "hypothesis_id")
        _required_id(self.label_id, "label_id")
        _required_id(self.metric_id, "metric_id")
        if self.mapping_type != "PROXY":
            raise ValueError("Stage 13 supports only non-approved PROXY mappings")
        if self.status not in {"DRAFT", "REVIEW_REQUIRED", "TEST_FIXTURE"}:
            raise ValueError("hypothesis status must not be APPROVED")
        if not self.rationale.strip() or not self.limitations:
            raise ValueError("rationale and limitations are required")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["limitations"] = list(self.limitations)
        return value


def validate_metric_hypotheses(
    hypotheses: Iterable[AnnotationMetricHypothesis],
    *,
    annotation_registry: AnnotationRegistry,
    metric_registry: FaceFitMetricRegistry,
) -> None:
    ids: set[str] = set()
    for item in hypotheses:
        if item.hypothesis_id in ids:
            raise ValueError(f"Duplicate hypothesis_id: {item.hypothesis_id}")
        ids.add(item.hypothesis_id)
        annotation_registry.get_label(item.label_id)
        metric_registry.get(item.metric_id)
