"""Finalize Stage 17 after a supplied human manual-review approval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.pilot_annotation_ready import (
    evaluate_stage17_annotation_gate,
    validate_decision_file_pair,
)
from app.vision.pilot_manual_review import PilotManualReviewDecision
from app.vision.pilot_video_intake import (
    assert_no_forbidden_semantics,
    load_strict_json,
    write_strict_json,
)


def _load(root: Path, name: str) -> dict:
    return load_strict_json(root / name)


def _markdown(report: dict) -> str:
    gate = report["gate_reevaluation"]
    checks = gate["condition_checks"]
    rows = "\n".join(
        f"| {name} | {'PASSED' if passed else 'FAILED'} |"
        for name, passed in checks.items()
    )
    return (
        "# Face-Fit Stage 17 Validation Report\n\n"
        f"- Participant: `{report['participant_id']}`\n"
        f"- Session: `{report['session_id']}`\n"
        f"- Human decision: `{report['manual_review']['decision']}`\n"
        f"- Split: `{report['split_name']}`\n"
        f"- Final status: `{report['final_status']}`\n\n"
        "## Gate conditions\n\n"
        "| Condition | Result |\n"
        "|---|---|\n"
        f"{rows}\n\n"
        "The approval is limited to observable-behavior annotation. Head-pose "
        "failures remain missing with their original failure reason; no missing "
        "value was interpolated. No evaluative value or decision boundary was "
        "created, Stage 11 was not executed, and the dataset remains unfrozen.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage15-dir", type=Path, required=True)
    parser.add_argument("--stage16-dir", type=Path, required=True)
    parser.add_argument("--incoming-dir", type=Path, required=True)
    args = parser.parse_args()

    stage15 = args.stage15_dir.resolve()
    stage16 = args.stage16_dir.resolve()
    incoming = args.incoming_dir.resolve()
    decision_path = stage16 / "manual_review_decision.json"
    template_path = stage16 / "manual_review_decision.template.json"
    decision_value = load_strict_json(decision_path)
    template_value = load_strict_json(template_path)
    pair_checks = validate_decision_file_pair(
        template_value, decision_value
    )
    decision = PilotManualReviewDecision.from_dict(decision_value)
    split_value = _load(stage16, "development_split_assignment.json")
    consent = _load(
        incoming, "PTC_000001_SES_000001.consent.json"
    )
    metadata = _load(
        incoming, "PTC_000001_SES_000001.metadata.json"
    )
    video_metadata = _load(stage15, "video_metadata.json")
    quality = _load(stage15, "quality_check_results.json")
    intervals = _load(stage15, "interval_validation.json")
    stage15_report = _load(stage15, "validation_report.json")
    review_packet = _load(stage16, "manual_review_packet.json")
    evaluation = evaluate_stage17_annotation_gate(
        decision=decision,
        split_value=split_value,
        consent_source=consent,
        metadata_source=metadata,
        video_metadata=video_metadata,
        quality_results=quality,
        interval_validation=intervals,
        stage15_report=stage15_report,
    )
    if evaluation.final_status != "pilot_video_annotation_ready":
        raise ValueError(
            "Stage 17 gate conditions did not produce annotation readiness"
        )
    gate_value = evaluation.to_dict()
    gate_status = {
        "participant_id": decision.participant_id,
        "session_id": decision.session_id,
        "current_status": evaluation.final_status,
        "human_decision_file_present": True,
        "human_decision": decision.to_dict(),
        "decision_file_validation": pair_checks,
        "development_split_valid":
            evaluation.split_validation["valid"],
        "automatic_quality_checks_passed":
            evaluation.condition_checks[
                "automatic_quality_checks_11_passed"
            ],
        "stage14_gate_reexecuted": True,
        "stage14_gate_result":
            evaluation.stage14_gate_result.to_dict(),
        "automatic_approval_performed": False,
        "dataset_frozen": False,
    }
    review_scope = review_packet["review_scope"]
    total_frames = review_scope["target_tracking_summary"][
        "total_frame_count"
    ]
    missing_frames = review_scope["head_pose_missing_frame_count"]
    available_frames = total_frames - missing_frames
    manifest = {
        "manifest_id": "ANNOTATION_READY_MANIFEST_SES_000001",
        "participant_id": decision.participant_id,
        "session_id": decision.session_id,
        "split_name": "DEVELOPMENT",
        "video": {
            "filename": metadata["video_file"],
            "sha256": video_metadata["sha256"],
        },
        "consent_reference_id": consent["consent_reference_id"],
        "interval_rule": intervals["interval_rule"],
        "baseline_interval": intervals["baseline"],
        "answer_intervals": intervals["answers"],
        "manual_review": decision.to_dict(),
        "availability": {
            "face": {
                "availability_ratio":
                    review_scope["face_availability_ratio"],
            },
            "both_shoulders": {
                "availability_ratio":
                    review_scope["both_shoulders_availability_ratio"],
            },
            "single_target": {
                "valid": True,
                "target_id": review_scope[
                    "target_tracking_summary"
                ]["target_id"],
                "target_id_change_count": review_scope[
                    "target_tracking_summary"
                ]["target_id_change_count"],
            },
            "head_pose": {
                "total_frame_count": total_frames,
                "available_frame_count": available_frames,
                "unavailable_frame_count": missing_frames,
                "availability_ratio": available_frames / total_frames,
                "failure_reason_counts":
                    review_scope["head_pose_failure_reason_counts"],
                "limitations": [
                    "Head Pose availability is calculation availability only.",
                    "REPROJECTION_ERROR_TOO_HIGH frames remain unavailable.",
                    "Missing Head Pose values were not interpolated or converted to successes.",
                ],
            },
        },
        "annotation_rubric_reference": {
            "rubric_id": "RUBRIC_OBSERVABLE_001",
            "version": "1.0.0",
            "status": "DRAFT",
            "registry_path":
                "config/data_collection/fixtures/annotation_registry.json",
            "guideline_path":
                "research/data_collection_protocol/annotation_guideline.md",
            "observable_only": True,
        },
        "approval_scope": "OBSERVABLE_BEHAVIOR_ANNOTATION_ONLY",
        "final_status": evaluation.final_status,
        "dataset_frozen": False,
    }
    report = {
        "schema_version": "1.0",
        "stage": 17,
        "participant_id": decision.participant_id,
        "session_id": decision.session_id,
        "final_status": evaluation.final_status,
        "manual_review": decision.to_dict(),
        "manual_review_file_validation": pair_checks,
        "split_name": "DEVELOPMENT",
        "split_validation": evaluation.split_validation,
        "gate_reevaluation": gate_value,
        "annotation_ready_manifest_summary": {
            "manifest_id": manifest["manifest_id"],
            "video_sha256": manifest["video"]["sha256"],
            "consent_reference_id": manifest[
                "consent_reference_id"
            ],
            "baseline_available": evaluation.condition_checks[
                "baseline_available"
            ],
            "answer_interval_count": len(manifest["answer_intervals"]),
            "face_availability_ratio": manifest["availability"]["face"][
                "availability_ratio"
            ],
            "both_shoulders_availability_ratio":
                manifest["availability"]["both_shoulders"][
                    "availability_ratio"
                ],
            "head_pose_availability_ratio":
                manifest["availability"]["head_pose"][
                    "availability_ratio"
                ],
            "rubric_id": manifest[
                "annotation_rubric_reference"
            ]["rubric_id"],
            "rubric_version": manifest[
                "annotation_rubric_reference"
            ]["version"],
        },
        "preservation_contract": {
            "head_pose_failure_reason_preserved":
                "REPROJECTION_ERROR_TOO_HIGH",
            "head_pose_missing_values_interpolated": False,
            "stage11_executed": False,
            "evaluative_value_produced": False,
            "evaluation_boundary_produced": False,
            "psychological_inference_produced": False,
            "ml_training_performed": False,
            "dataset_frozen": False,
            "dependency_changed": False,
        },
    }
    for value in (gate_status, manifest, report):
        assert_no_forbidden_semantics(value)
    write_strict_json(stage16 / "gate_reevaluation_status.json", gate_status)
    write_strict_json(stage16 / "annotation_ready_manifest.json", manifest)
    write_strict_json(stage16 / "validation_report.json", report)
    (stage16 / "validation_report.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
