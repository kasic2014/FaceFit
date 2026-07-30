"""Reevaluate the Stage 14 gate only after a human Stage 16 decision exists."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.consent_models import ConsentReference
from app.vision.dataset_manifest_models import DatasetSplitAssignment
from app.vision.dataset_release_gate import evaluate_dataset_release_gate
from app.vision.manual_review_models import ManualReviewDecision
from app.vision.pilot_collection_models import DatasetReleaseCandidate
from app.vision.pilot_manual_review import (
    PilotManualReviewDecision,
    map_gate_status,
)
from app.vision.pilot_video_intake import (
    assert_no_forbidden_semantics,
    load_strict_json,
    write_strict_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage15-dir", type=Path, required=True)
    parser.add_argument("--stage16-dir", type=Path, required=True)
    parser.add_argument("--incoming-dir", type=Path, required=True)
    parser.add_argument("--decision-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"gate reevaluation output already exists: {output}")
    decision = PilotManualReviewDecision.from_dict(
        load_strict_json(args.decision_file.resolve())
    )
    quality = load_strict_json(
        args.stage15_dir.resolve() / "quality_check_results.json"
    )
    intervals = load_strict_json(
        args.stage15_dir.resolve() / "interval_validation.json"
    )
    split = load_strict_json(
        args.stage16_dir.resolve() / "development_split_assignment.json"
    )
    consent_source = load_strict_json(
        args.incoming_dir.resolve()
        / "PTC_000001_SES_000001.consent.json"
    )
    assignment_value = split["assignment"]
    assignment = DatasetSplitAssignment(
        assignment_value["participant_id"],
        assignment_value["split"],
        assignment_value["seed"],
        assignment_value["assignment_method"],
    )
    automatic_quality_passed = bool(
        quality["summary"]["automatic_validation_passed"]
    )
    status = map_gate_status(
        decision,
        split_valid=(
            assignment.split == "DEVELOPMENT"
            and split["linkage"]["leakage_detected"] is False
        ),
        automatic_quality_passed=automatic_quality_passed,
    )
    gate_result = None
    if decision.decision == "APPROVED_FOR_ANNOTATION":
        consent = ConsentReference(
            consent_source["consent_reference_id"],
            consent_source["participant_id"],
            consent_source["consent_status"],
            consent_source["schema_version"],
            consent_source["video_collection_allowed"],
            consent_source["automated_analysis_allowed"],
            consent_source["research_use_allowed"],
            consent_source["model_development_use_allowed"],
            consent_source["withdrawn_at"],
        )
        manual_review = ManualReviewDecision(
            "REVIEW_SES_000001",
            "SES_000001",
            decision.reviewer_id or "",
            decision.decision,
            (),
            decision.reviewed_at or "",
            decision.notes,
        )
        candidate = DatasetReleaseCandidate(
            "RELEASE_CANDIDATE_SES_000001",
            "MANIFEST_NOT_CREATED_STAGE_16",
            "PTC_000001",
            "SES_000001",
            tuple(
                item["answer_id"] for item in intervals["answers"]
            ),
            "REVIEW_REQUIRED",
        )
        evaluated = evaluate_dataset_release_gate(
            candidate,
            consent=consent,
            withdrawn=False,
            file_hash_valid=True,
            video_checks_passed=automatic_quality_passed,
            baseline_available=True,
            answer_intervals_valid=intervals["valid"],
            manual_review=manual_review,
            split_assignment=assignment,
            split_leakage_detected=False,
        )
        gate_result = evaluated.to_dict()
        status = (
            "pilot_video_annotation_ready"
            if evaluated.eligible
            else "awaiting_human_manual_review_decision"
        )
    payload = {
        "participant_id": "PTC_000001",
        "session_id": "SES_000001",
        "current_status": status,
        "human_decision_file_present": True,
        "human_decision": decision.to_dict(),
        "development_split_valid": assignment.split == "DEVELOPMENT",
        "automatic_quality_checks_passed": automatic_quality_passed,
        "stage14_gate_reexecuted":
            decision.decision == "APPROVED_FOR_ANNOTATION",
        "stage14_gate_result": gate_result,
        "automatic_approval_performed": False,
        "dataset_frozen": False,
    }
    assert_no_forbidden_semantics(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_strict_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
