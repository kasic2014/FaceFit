from __future__ import annotations

import unittest

from app.vision.annotation_metric_hypotheses import (
    AnnotationMetricHypothesis,
    validate_metric_hypotheses,
)
from app.vision.annotation_models import (
    AnnotationLabelDefinition,
    AnnotationRubric,
)
from app.vision.annotation_registry import AnnotationRegistry
from app.vision.data_collection_models import AnswerSample, RecordingSession
from app.vision.dataset_manifest_models import (
    DatasetManifest,
    DatasetSplitAssignment,
)
from app.vision.dataset_splitter import (
    assign_participant_splits,
    validate_split_leakage,
)
from app.vision.metric_registry import build_stage10_metric_registry


class DatasetAndHypothesisStage13Tests(unittest.TestCase):
    def setUp(self):
        label = AnnotationLabelDefinition(
            "HEAD_TURN_LEFT", "Head turn left",
            "Visible head rotation toward image left.",
            "HEAD", True, ("LEFT",), True, "DRAFT",
        )
        self.registry = AnnotationRegistry(
            (label,),
            (
                AnnotationRubric(
                    "RUBRIC_001", "1.0.0", "DRAFT",
                    ("HEAD_TURN_LEFT",), True, True,
                ),
            ),
        )

    def test_hypothesis_references_existing_stage11_metric(self):
        value = AnnotationMetricHypothesis(
            "HYP_001", "HEAD_TURN_LEFT",
            "HEAD_RELATIVE_YAW_ABS_P95_DEG", "PROXY",
            "POSITIVE_ASSOCIATION_EXPECTED", "TEST_FIXTURE",
            "Observable event may co-occur with the relative metric.",
            ("No evaluation meaning.",),
        )
        validate_metric_hypotheses(
            (value,),
            annotation_registry=self.registry,
            metric_registry=build_stage10_metric_registry(),
        )

    def test_unknown_metric_id_is_rejected(self):
        value = AnnotationMetricHypothesis(
            "HYP_001", "HEAD_TURN_LEFT",
            "POSTURE_RELATIVE_SHOULDER_CENTER_X", "PROXY",
            "ASSOCIATION_UNKNOWN", "DRAFT",
            "Candidate reference.", ("Metric is not registered.",),
        )
        with self.assertRaises(KeyError):
            validate_metric_hypotheses(
                (value,),
                annotation_registry=self.registry,
                metric_registry=build_stage10_metric_registry(),
            )

    def test_direct_and_approved_hypotheses_are_rejected(self):
        for mapping, status in (("DIRECT", "DRAFT"), ("PROXY", "APPROVED")):
            with self.subTest(mapping=mapping, status=status), self.assertRaises(
                ValueError
            ):
                AnnotationMetricHypothesis(
                    "HYP_001", "HEAD_TURN_LEFT",
                    "HEAD_RELATIVE_YAW_ABS_P95_DEG", mapping,
                    "ASSOCIATION_UNKNOWN", status,
                    "Candidate reference.", ("Not approved.",),
                )

    def test_manifest_is_metadata_only_draft(self):
        value = DatasetManifest(
            "DSM_FIXTURE", "1.0.0", "DRAFT", "DCP_001",
            ("PTC_000001",), ("SES_000001",), ("ANS_000001",),
            {"fixture": "1" * 64}, False, False, False,
        )
        self.assertFalse(value.contains_media)
        for changes in (
            {"status": "FROZEN"},
            {"contains_media": True},
            {"contains_direct_identifiers": True},
            {"frozen": True},
        ):
            values = {
                "manifest_id": "DSM_FIXTURE",
                "version": "1.0.0",
                "status": "DRAFT",
                "protocol_id": "DCP_001",
                "participant_ids": ("PTC_000001",),
                "session_ids": ("SES_000001",),
                "answer_ids": ("ANS_000001",),
                "artifact_sha256": {"fixture": "1" * 64},
                "contains_media": False,
                "contains_direct_identifiers": False,
                "frozen": False,
            }
            values.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                DatasetManifest(**values)

    def test_splitter_is_deterministic_and_participant_level(self):
        participants = tuple(f"PTC_{index:06d}" for index in range(1, 7))
        first = assign_participant_splits(participants, seed=13)
        second = assign_participant_splits(reversed(participants), seed=13)
        self.assertEqual(first, second)
        self.assertEqual(len({item.participant_id for item in first}), 6)

    def test_splitter_supports_all_four_named_splits(self):
        participants = tuple(f"PTC_{index:06d}" for index in range(1, 9))
        values = assign_participant_splits(participants, seed=13)
        self.assertEqual(
            {item.split for item in values},
            {"DEVELOPMENT", "CALIBRATION", "VALIDATION", "HOLDOUT"},
        )

    def test_duplicate_participant_assignment_is_rejected(self):
        with self.assertRaises(ValueError):
            assign_participant_splits(
                ("PTC_000001", "PTC_000001"), seed=13
            )

    def test_split_leakage_is_rejected(self):
        assignments = (
            DatasetSplitAssignment(
                "PTC_000001", "DEVELOPMENT", 13,
                "PARTICIPANT_LEVEL_DETERMINISTIC",
            ),
            DatasetSplitAssignment(
                "PTC_000001", "HOLDOUT", 13,
                "PARTICIPANT_LEVEL_DETERMINISTIC",
            ),
        )
        with self.assertRaises(ValueError):
            validate_split_leakage(assignments, (), ())

    def test_session_and_answer_inherit_participant_split(self):
        assignment = DatasetSplitAssignment(
            "PTC_000001", "VALIDATION", 13,
            "PARTICIPANT_LEVEL_DETERMINISTIC",
        )
        session = RecordingSession(
            "SES_000001", "PTC_000001", "DCP_001", "CNS_001",
            "ENV_001", "ANNOTATION_READY", 9000, 0, 2000, "1" * 64,
        )
        answer = AnswerSample(
            "ANS_000001", "SES_000001", "QUE_01",
            2000, 5000, "TGT_001",
        )
        result = validate_split_leakage(
            (assignment,), (session,), (answer,)
        )
        self.assertFalse(result["leakage_detected"])
        self.assertEqual(result["answer_count"], 1)


if __name__ == "__main__":
    unittest.main()
