from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.vision.metric_registry import build_stage10_metric_registry
from app.vision.pilot_video_intake import load_strict_json, sha256_file
from app.vision.single_session_mvp_feedback import (
    ANALYSIS_MODE,
    DISCLAIMER,
    OUTPUT_NAMES,
    RESULT_LIMITED,
    RESULT_READY,
    RESULT_UNAVAILABLE,
    SCORING_REASONS,
    SingleSessionInputs,
    SingleSessionMvpError,
    build_answer_feedback,
    build_session_comparison,
    build_single_session_mvp_feedback,
    classify_availability,
    validate_single_session_inputs,
    write_single_session_mvp_outputs,
)


PARTICIPANT_ID = "PTC_900001"
SESSION_ID = "SES_900001"
ANSWER_IDS = (
    "ANS_900001",
    "ANS_900002",
    "ANS_900003",
    "ANS_900004",
)


def _availability(available, total, longest=0, failure_code=None):
    missing = total - available
    return {
        "availability_ratio": available / total if total else 0.0,
        "available": available > 0,
        "failure_reason": None if available else "FIXTURE_UNAVAILABLE",
        "failure_reason_counts": (
            {} if not failure_code or missing == 0 else {failure_code: missing}
        ),
        "invalid_frame_count": missing,
        "longest_missing_duration_ms": longest,
        "total_frame_count": total,
        "valid_frame_count": available,
    }


def _summary(value, count):
    return {
        "absolute_mean": abs(value),
        "absolute_median": abs(value),
        "absolute_p95": abs(value),
        "available": count > 0,
        "count": count,
        "failure_reason": None if count else "FIXTURE_UNAVAILABLE",
        "mad": 0.1,
        "maximum": value + 1.0,
        "mean": value,
        "median": value,
        "minimum": value - 1.0,
        "p05": value - 0.8,
        "p25": value - 0.4,
        "p75": value + 0.4,
        "p95": value + 0.8,
        "standard_deviation": 0.5,
    }


def _aggregate(index, *, head_available=5, posture_available=10, value=None):
    total = 10
    metric_value = float(index if value is None else value)
    head_availability = _availability(
        head_available,
        total,
        longest=400 if head_available < total else 0,
        failure_code="FIXTURE_HEAD_VALUE_UNAVAILABLE",
    )
    posture_availability = _availability(
        posture_available,
        total,
        failure_code="FIXTURE_POSTURE_VALUE_UNAVAILABLE",
    )
    return {
        "data_quality": {
            "available": True,
            "face_alignment_availability_ratio": (
                posture_available / total
            ),
            "head_pose_availability_ratio": head_available / total,
            "posture_availability_ratio": posture_available / total,
            "quality_score": 1.0,
            "target_continuity_ratio": 1.0,
            "total_frame_count": total,
            "warnings": (
                [] if head_available == total else ["HEAD_POSE_PARTIAL"]
            ),
        },
        "duration_ms": 1000,
        "end_timestamp_ms": index * 1000 + 1000,
        "events": [],
        "failure_reason": None,
        "head_pose": {
            "availability": head_availability,
            "relative_pitch_deg": _summary(metric_value + 0.1, head_available),
            "relative_roll_deg": _summary(metric_value + 0.2, head_available),
            "relative_yaw_deg": _summary(metric_value, head_available),
        },
        "interval_id": f"INT_FIXTURE_{index:03d}",
        "interval_type": "ANSWER",
        "posture": {
            "face_alignment_availability": posture_availability,
            "nose_alignment_availability": posture_availability,
            "relative_nose_shoulder_offset_x_norm": _summary(
                metric_value / 10.0, posture_available
            ),
            "relative_shoulder_tilt_deg": _summary(
                metric_value + 0.3, posture_available
            ),
            "shoulder_availability": posture_availability,
            "shoulder_center_velocity_norm_per_sec": _summary(
                metric_value / 20.0, posture_available
            ),
        },
        "start_timestamp_ms": index * 1000,
        "target_id": "TARGET_FIXTURE",
        "warnings": (
            [] if head_available == total else ["HEAD_POSE_PARTIAL"]
        ),
    }


def _fixture_inputs(
    temp_root: Path,
    *,
    head_counts=(5, 6, 3, 4),
    posture_counts=(10, 10, 10, 10),
    values=(1.0, 2.0, 3.0, 4.0),
):
    video = temp_root / "fixture-video.bin"
    video.write_bytes(b"fixture-protected-input")
    video_sha = sha256_file(video)
    answers = [
        {
            "answer_id": answer_id,
            "interval_id": f"INT_FIXTURE_{index:03d}",
            "start_timestamp_ms": index * 1000,
            "end_timestamp_ms": index * 1000 + 1000,
        }
        for index, answer_id in enumerate(ANSWER_IDS, 1)
    ]
    definitions = [
        {
            "end_timestamp_ms": answer["end_timestamp_ms"],
            "interval_id": answer["interval_id"],
            "interval_type": "ANSWER",
            "start_timestamp_ms": answer["start_timestamp_ms"],
        }
        for answer in answers
    ]
    stage_report = {
        "status": "completed",
        "source": {"sha256": video_sha},
    }
    documents = {
        "metadata": {
            "participant_id": PARTICIPANT_ID,
            "session_id": SESSION_ID,
            "expected_sha256": video_sha,
        },
        "stage15_report": {"video_metadata": {"sha256": video_sha}},
        "manual_review": {
            "participant_id": PARTICIPANT_ID,
            "session_id": SESSION_ID,
            "decision": "APPROVED_FOR_ANNOTATION",
        },
        "annotation_ready": {
            "participant_id": PARTICIPANT_ID,
            "session_id": SESSION_ID,
            "split_name": "DEVELOPMENT",
            "video": {
                "filename": f"{PARTICIPANT_ID}_{SESSION_ID}.mp4",
                "sha256": video_sha,
            },
            "baseline_interval": {
                "interval_id": "BASELINE_FIXTURE",
                "start_timestamp_ms": 0,
                "end_timestamp_ms": 1000,
            },
            "answer_intervals": answers,
            "final_status": "pilot_video_annotation_ready",
        },
        "baseline": {
            "available": True,
            "status": "COMPLETED",
            "collection_start_ms": 0,
            "collection_end_ms": 1000,
        },
        "interval_definitions": {
            "inclusion_rule": (
                "start_timestamp_ms <= timestamp_ms < end_timestamp_ms"
            ),
            "intervals": definitions,
        },
    }
    for stage in (
        "stage7_head_pose_report",
        "stage8_posture_raw_report",
        "stage9_baseline_relative_report",
        "stage10_intervals_report",
    ):
        documents[stage] = copy.deepcopy(stage_report)
    rows = {
        "head_pose_raw": ({"fixture": True},),
        "posture_raw": ({"fixture": True},),
        "relative_features": ({"fixture": True},),
        "interval_aggregates": tuple(
            _aggregate(
                index,
                head_available=head_counts[index - 1],
                posture_available=posture_counts[index - 1],
                value=values[index - 1],
            )
            for index in range(1, 5)
        ),
    }
    return SingleSessionInputs(
        PARTICIPANT_ID,
        SESSION_ID,
        {"video": video},
        documents,
        rows,
        {"video": sha256_file(video)},
    )


class SingleSessionMvpFeedbackStage22Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_fixture_session_identity_and_intervals_validate(self):
        inputs = _fixture_inputs(self.root)
        report = validate_single_session_inputs(
            inputs,
            expected_participant_id=PARTICIPANT_ID,
            expected_session_id=SESSION_ID,
            expected_answer_ids=ANSWER_IDS,
        )
        self.assertTrue(report["valid"])
        self.assertEqual(4, report["answer_count"])
        self.assertEqual("[start, end)", report["interval_rule"])

    def test_session_id_mismatch_is_blocked(self):
        inputs = _fixture_inputs(self.root)
        with self.assertRaisesRegex(SingleSessionMvpError, "session_id mismatch"):
            validate_single_session_inputs(
                inputs,
                expected_participant_id=PARTICIPANT_ID,
                expected_session_id="SES_900999",
                expected_answer_ids=ANSWER_IDS,
            )

    def test_baseline_mismatch_is_blocked(self):
        inputs = _fixture_inputs(self.root)
        inputs.documents["baseline"]["collection_end_ms"] = 999
        with self.assertRaisesRegex(SingleSessionMvpError, "Baseline model"):
            validate_single_session_inputs(
                inputs,
                expected_participant_id=PARTICIPANT_ID,
                expected_session_id=SESSION_ID,
                expected_answer_ids=ANSWER_IDS,
            )

    def test_official_metric_resolver_is_reused(self):
        inputs = _fixture_inputs(self.root)
        real_builder = build_stage10_metric_registry
        with patch(
            "app.vision.single_session_mvp_feedback."
            "build_stage10_metric_registry",
            wraps=real_builder,
        ) as resolver_builder:
            answers = build_answer_feedback(inputs)
        self.assertTrue(resolver_builder.called)
        expected = {
            item.metric_id for item in real_builder().definitions
        }
        self.assertEqual(
            expected,
            set(answers[0]["relative_metric_summary"]),
        )

    def test_structural_availability_states(self):
        self.assertEqual("COMPLETE", classify_availability(10, 10))
        self.assertEqual("PARTIAL", classify_availability(1, 10))
        self.assertEqual("UNAVAILABLE", classify_availability(0, 10))
        self.assertEqual(
            "NOT_APPLICABLE", classify_availability(0, 0, applicable=False)
        )

    def test_partial_head_pose_is_not_interpolated(self):
        inputs = _fixture_inputs(self.root)
        answer = build_answer_feedback(inputs)[0]
        head = answer["head_pose_measurement"]
        self.assertEqual("PARTIAL", head["status"])
        self.assertFalse(head["imputation_performed"])
        self.assertEqual(5, head["availability"]["missing_sample_count"])
        self.assertFalse(head["availability"]["imputation_performed"])

    def test_partial_metrics_produce_limited_ready_status(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(self.root)
        )
        self.assertEqual(RESULT_LIMITED, package["feedback"]["result_status"])

    def test_all_complete_metrics_produce_ready_status(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(
                self.root,
                head_counts=(10, 10, 10, 10),
            )
        )
        self.assertEqual(RESULT_READY, package["feedback"]["result_status"])

    def test_all_core_metrics_unavailable_produce_unavailable_status(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(
                self.root,
                head_counts=(0, 0, 0, 0),
                posture_counts=(0, 0, 0, 0),
            )
        )
        self.assertEqual(
            RESULT_UNAVAILABLE, package["feedback"]["result_status"]
        )

    def test_api_scores_remain_null_with_reasons(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(self.root)
        )
        api = package["api_contract"]
        self.assertIsNone(api["scores"])
        self.assertEqual(list(SCORING_REASONS), api["scoreUnavailableReasons"])
        self.assertFalse(package["feedback_status"]["scoring_performed"])

    def test_no_numeric_threshold_is_created(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(self.root)
        )
        self.assertFalse(package["feedback_status"]["threshold_created"])
        self.assertFalse(
            package["feedback"]["measurement_summary"]["thresholds_used"]
        )
        self.assertFalse(
            package["within_session_comparison"]["thresholds_used"]
        )

    def test_within_session_rank_is_deterministic(self):
        answers = build_answer_feedback(_fixture_inputs(self.root))
        first = build_session_comparison(answers)
        second = build_session_comparison(copy.deepcopy(answers))
        self.assertEqual(first, second)
        metric = first["metric_comparisons"][
            "HEAD_RELATIVE_YAW_ABS_P95_DEG"
        ]
        self.assertEqual(1, metric["answer_values"][ANSWER_IDS[0]][
            "dense_rank_ascending"
        ])
        self.assertEqual(4, metric["answer_values"][ANSWER_IDS[3]][
            "dense_rank_ascending"
        ])

    def test_tied_values_share_dense_rank(self):
        answers = build_answer_feedback(
            _fixture_inputs(self.root, values=(1.0, 1.0, 2.0, 3.0))
        )
        metric = build_session_comparison(answers)["metric_comparisons"][
            "HEAD_RELATIVE_YAW_ABS_P95_DEG"
        ]
        self.assertEqual(
            metric["answer_values"][ANSWER_IDS[0]]["dense_rank_ascending"],
            metric["answer_values"][ANSWER_IDS[1]]["dense_rank_ascending"],
        )
        self.assertTrue(
            metric["answer_values"][ANSWER_IDS[0]]["is_session_minimum"]
        )
        self.assertTrue(
            metric["answer_values"][ANSWER_IDS[1]]["is_session_minimum"]
        )

    def test_comparison_is_omitted_when_fewer_than_two_values(self):
        answers = build_answer_feedback(
            _fixture_inputs(
                self.root,
                head_counts=(5, 0, 0, 0),
                posture_counts=(10, 0, 0, 0),
            )
        )
        comparison = build_session_comparison(answers)
        self.assertEqual({}, comparison["metric_comparisons"])

    def test_observation_types_are_contract_limited(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(self.root)
        )
        allowed = {
            "MEASUREMENT_OBSERVATION",
            "WITHIN_SESSION_COMPARISON",
            "MEASUREMENT_LIMITATION",
        }
        for answer in package["feedback"]["answer_feedback"]:
            self.assertTrue(answer["observations"])
            self.assertTrue(
                all(item["type"] in allowed for item in answer["observations"])
            )

    def test_prohibited_evaluative_claims_are_absent(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(self.root)
        )
        text = json.dumps(package, ensure_ascii=False)
        for phrase in (
            "자세가 나쁘",
            "시선 처리가 좋지",
            "자신감이 부족",
            "집중력이 부족",
            "면접 태도가 부적절",
            "합격 가능성이 낮",
        ):
            self.assertNotIn(phrase, text)

    def test_required_disclaimer_is_in_internal_and_api_contracts(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(self.root)
        )
        self.assertEqual(DISCLAIMER, package["feedback"]["disclaimer"])
        self.assertEqual(DISCLAIMER, package["api_contract"]["disclaimer"])

    def test_api_uses_camel_case_without_participant_or_paths(self):
        package = build_single_session_mvp_feedback(
            _fixture_inputs(self.root)
        )
        api = package["api_contract"]
        self.assertEqual(SESSION_ID, api["sessionId"])
        self.assertEqual(ANALYSIS_MODE, api["analysisMode"])
        self.assertIn("measurementSummary", api)
        self.assertNotIn("measurement_summary", api)
        text = json.dumps(api, ensure_ascii=False)
        self.assertNotIn(PARTICIPANT_ID, text)
        self.assertNotIn(str(self.root), text)

    def test_outputs_are_strict_finite_and_sources_unchanged(self):
        inputs = _fixture_inputs(self.root)
        before = sha256_file(inputs.paths["video"])
        package = build_single_session_mvp_feedback(inputs)
        output = self.root / "output"
        report = write_single_session_mvp_outputs(package, inputs, output)
        self.assertTrue(report["valid"])
        self.assertEqual(set(OUTPUT_NAMES), {item.name for item in output.iterdir()})
        for name in OUTPUT_NAMES:
            if name.endswith(".json"):
                load_strict_json(output / name)
        self.assertEqual(before, sha256_file(inputs.paths["video"]))

    def test_nan_and_infinity_are_rejected(self):
        inputs = _fixture_inputs(self.root)
        for invalid in (math.nan, math.inf, -math.inf):
            broken = copy.deepcopy(inputs)
            broken.rows["interval_aggregates"][0]["head_pose"][
                "relative_yaw_deg"
            ]["absolute_p95"] = invalid
            with self.assertRaises(ValueError):
                build_answer_feedback(broken)


if __name__ == "__main__":
    unittest.main()
