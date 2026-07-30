from __future__ import annotations

import unittest

from app.vision.annotation_agreement import (
    calculate_presence_agreement,
    compare_event_sets,
    temporal_iou,
)
from app.vision.annotation_models import (
    AnnotationEvent,
    AnnotationLabelDefinition,
    AnnotationRater,
    AnnotationRubric,
    AnnotationSession,
)
from app.vision.annotation_registry import AnnotationRegistry
from app.vision.annotation_validator import validate_annotation_contract
from app.vision.data_collection_models import AnswerSample


def label(**changes):
    values = {
        "label_id": "HEAD_TURN_LEFT",
        "display_name": "Head turn left",
        "description": "Visible head rotation toward image left.",
        "category": "HEAD",
        "requires_direction": True,
        "allowed_directions": ("LEFT",),
        "observable_only": True,
        "status": "DRAFT",
    }
    values.update(changes)
    return AnnotationLabelDefinition(**values)


def event(event_id, rater, session, layer, **changes):
    values = {
        "event_id": event_id,
        "annotation_session_id": session,
        "answer_id": "ANS_000001",
        "rater_id": rater,
        "label_id": "HEAD_TURN_LEFT",
        "start_timestamp_ms": 2200,
        "end_timestamp_ms": 3000,
        "direction": "LEFT",
        "rater_confidence": 0.8,
        "layer": layer,
    }
    values.update(changes)
    return AnnotationEvent(**values)


class AnnotationContractStage13Tests(unittest.TestCase):
    def setUp(self):
        self.registry = AnnotationRegistry(
            (label(),),
            (
                AnnotationRubric(
                    "RUBRIC_001", "1.0.0", "DRAFT",
                    ("HEAD_TURN_LEFT",), True, True,
                ),
            ),
        )
        self.answer = AnswerSample(
            "ANS_000001", "SES_000001", "QUE_01",
            2000, 5000, "TGT_001",
        )
        self.raters = (
            AnnotationRater("RATER_A", "INDEPENDENT_RATER", "1.0.0", "ACTIVE"),
            AnnotationRater("RATER_B", "INDEPENDENT_RATER", "1.0.0", "ACTIVE"),
        )
        self.sessions = (
            AnnotationSession(
                "ANN_A", "RATER_A", "RUBRIC_001", "1.0.0",
                "RATER_A_ORIGINAL", True, True, True, True,
            ),
            AnnotationSession(
                "ANN_B", "RATER_B", "RUBRIC_001", "1.0.0",
                "RATER_B_ORIGINAL", True, True, True, True,
            ),
        )

    def test_registry_rejects_inferred_trait_label(self):
        with self.assertRaises(ValueError):
            AnnotationRegistry(
                (
                    label(
                        label_id="ANXIETY",
                        display_name="Anxiety",
                        description="Inferred internal state.",
                    ),
                ),
                (),
            )

    def test_registry_rejects_diagnostic_label(self):
        with self.assertRaises(ValueError):
            AnnotationRegistry(
                (
                    label(
                        label_id="SCOLIOSIS",
                        display_name="Clinical condition",
                        description="Diagnosis from video.",
                    ),
                ),
                (),
            )

    def test_direction_contract_is_enforced(self):
        with self.assertRaises(ValueError):
            label(allowed_directions=())
        with self.assertRaises(ValueError):
            AnnotationLabelDefinition(
                "CAMERA_MOVEMENT", "Camera movement", "Visible camera movement.",
                "DATA_QUALITY", False, ("LEFT",), True, "DRAFT",
            )

    def test_event_requires_positive_interval_and_finite_confidence(self):
        with self.assertRaises(ValueError):
            event(
                "EVT_001", "RATER_A", "ANN_A", "RATER_A_ORIGINAL",
                end_timestamp_ms=2200,
            )
        with self.assertRaises(ValueError):
            event(
                "EVT_001", "RATER_A", "ANN_A", "RATER_A_ORIGINAL",
                rater_confidence=float("nan"),
            )

    def test_event_must_be_inside_answer(self):
        value = event(
            "EVT_001", "RATER_A", "ANN_A", "RATER_A_ORIGINAL",
            start_timestamp_ms=1900,
        )
        with self.assertRaises(ValueError):
            validate_annotation_contract(
                registry=self.registry,
                answers=(self.answer,),
                raters=self.raters,
                sessions=self.sessions,
                events=(value,),
            )

    def test_event_direction_must_match_label(self):
        value = event(
            "EVT_001", "RATER_A", "ANN_A", "RATER_A_ORIGINAL",
            direction="RIGHT",
        )
        with self.assertRaises(ValueError):
            validate_annotation_contract(
                registry=self.registry,
                answers=(self.answer,),
                raters=self.raters,
                sessions=self.sessions,
                events=(value,),
            )

    def test_exact_duplicate_for_same_rater_is_rejected(self):
        first = event("EVT_001", "RATER_A", "ANN_A", "RATER_A_ORIGINAL")
        duplicate = event("EVT_002", "RATER_A", "ANN_A", "RATER_A_ORIGINAL")
        with self.assertRaises(ValueError):
            validate_annotation_contract(
                registry=self.registry,
                answers=(self.answer,),
                raters=self.raters,
                sessions=self.sessions,
                events=(first, duplicate),
            )

    def test_original_rater_blinding_is_required(self):
        with self.assertRaises(ValueError):
            AnnotationSession(
                "ANN_A", "RATER_A", "RUBRIC_001", "1.0.0",
                "RATER_A_ORIGINAL", True, True, False, True,
            )

    def test_valid_original_layers_remain_separate(self):
        values = (
            event("EVT_A", "RATER_A", "ANN_A", "RATER_A_ORIGINAL"),
            event("EVT_B", "RATER_B", "ANN_B", "RATER_B_ORIGINAL"),
        )
        validate_annotation_contract(
            registry=self.registry,
            answers=(self.answer,),
            raters=self.raters,
            sessions=self.sessions,
            events=values,
        )
        self.assertNotEqual(values[0].layer, values[1].layer)

    def test_temporal_iou_cases(self):
        self.assertEqual(temporal_iou(0, 10, 0, 10), 1.0)
        self.assertAlmostEqual(temporal_iou(0, 10, 5, 15), 1 / 3)
        self.assertEqual(temporal_iou(0, 10, 10, 20), 0.0)
        self.assertEqual(temporal_iou(0, 10, 20, 30), 0.0)
        with self.assertRaises(ValueError):
            temporal_iou(0, 0, 0, 10)

    def test_event_matching_preserves_no_overlap_and_missing(self):
        a = (
            event("EVT_A1", "RATER_A", "ANN_A", "RATER_A_ORIGINAL"),
            event(
                "EVT_A2", "RATER_A", "ANN_A", "RATER_A_ORIGINAL",
                answer_id="ANS_000002",
            ),
        )
        b = (
            event(
                "EVT_B1", "RATER_B", "ANN_B", "RATER_B_ORIGINAL",
                start_timestamp_ms=3000, end_timestamp_ms=3300,
            ),
            event(
                "EVT_B2", "RATER_B", "ANN_B", "RATER_B_ORIGINAL",
                answer_id="ANS_000003",
            ),
        )
        statuses = {item.match_status for item in compare_event_sets(a, b)}
        self.assertEqual(
            statuses,
            {"NO_OVERLAP", "MISSING_RATER_A", "MISSING_RATER_B"},
        )

    def test_presence_agreement_formulas(self):
        value = calculate_presence_agreement(
            (True, True, False, False),
            (True, False, True, False),
        )
        self.assertEqual(value.observed_agreement, 0.5)
        self.assertEqual(value.positive_agreement, 0.5)
        self.assertEqual(value.negative_agreement, 0.5)
        self.assertEqual(value.cohen_kappa, 0.0)

    def test_zero_kappa_denominator_becomes_null(self):
        value = calculate_presence_agreement(
            (True, True), (True, True)
        )
        self.assertIsNone(value.cohen_kappa)
        self.assertIsNone(value.negative_agreement)

    def test_empty_presence_vectors_are_safe_nulls(self):
        value = calculate_presence_agreement((), ())
        self.assertIsNone(value.observed_agreement)
        self.assertIsNone(value.cohen_kappa)


if __name__ == "__main__":
    unittest.main()
