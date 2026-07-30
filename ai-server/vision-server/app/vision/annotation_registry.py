"""Observable annotation registry with semantic inference guards."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.vision.annotation_models import (
    AnnotationLabelDefinition,
    AnnotationRubric,
)


FORBIDDEN_ANNOTATION_CONCEPTS = frozenset(
    {
        "CONFIDENCE",
        "ANXIETY",
        "ATTENTION",
        "PERSONALITY",
        "HIRABILITY",
        "PASS",
        "FAIL",
        "MENTAL_HEALTH",
        "DIAGNOSIS",
        "TURTLE_NECK",
        "SCOLIOSIS",
    }
)


def _normalized_text(value: str) -> str:
    return value.upper().replace("-", "_").replace(" ", "_")


class AnnotationRegistry:
    def __init__(
        self,
        labels: Iterable[AnnotationLabelDefinition],
        rubrics: Iterable[AnnotationRubric],
    ) -> None:
        self._labels: dict[str, AnnotationLabelDefinition] = {}
        self._rubrics: dict[tuple[str, str], AnnotationRubric] = {}
        for label in labels:
            if label.label_id in self._labels:
                raise ValueError(f"Duplicate label_id: {label.label_id}")
            text = _normalized_text(
                " ".join((label.label_id, label.display_name, label.description))
            )
            forbidden = sorted(
                concept for concept in FORBIDDEN_ANNOTATION_CONCEPTS
                if concept in text
            )
            if forbidden:
                raise ValueError(
                    f"Forbidden inferred concept in {label.label_id}: "
                    f"{', '.join(forbidden)}"
                )
            self._labels[label.label_id] = label
        for rubric in rubrics:
            key = (rubric.rubric_id, rubric.version)
            if key in self._rubrics:
                raise ValueError(f"Duplicate rubric: {key}")
            unknown = sorted(set(rubric.label_ids) - set(self._labels))
            if unknown:
                raise ValueError(
                    f"Rubric references unknown labels: {', '.join(unknown)}"
                )
            self._rubrics[key] = rubric

    @property
    def labels(self) -> tuple[AnnotationLabelDefinition, ...]:
        return tuple(self._labels[key] for key in sorted(self._labels))

    @property
    def rubrics(self) -> tuple[AnnotationRubric, ...]:
        return tuple(self._rubrics[key] for key in sorted(self._rubrics))

    def get_label(self, label_id: str) -> AnnotationLabelDefinition:
        try:
            return self._labels[label_id]
        except KeyError as exc:
            raise KeyError(f"Unknown label_id: {label_id}") from exc

    def get_rubric(self, rubric_id: str, version: str) -> AnnotationRubric:
        try:
            return self._rubrics[(rubric_id, version)]
        except KeyError as exc:
            raise KeyError(f"Unknown rubric: {rubric_id}@{version}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "observable_only": True,
            "prohibited_inference_concepts": sorted(
                FORBIDDEN_ANNOTATION_CONCEPTS
            ),
            "labels": [item.to_dict() for item in self.labels],
            "rubrics": [item.to_dict() for item in self.rubrics],
        }
