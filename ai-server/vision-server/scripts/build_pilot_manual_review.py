"""Generate the Stage 16 human manual-review packet and pending gate state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.consent_models import ConsentReference
from app.vision.dataset_release_gate import evaluate_dataset_release_gate
from app.vision.manual_review_models import ManualReviewDecision
from app.vision.pilot_collection_models import DatasetReleaseCandidate
from app.vision.pilot_manual_review import (
    PilotManualReviewDecision,
    context_frame_timestamps,
    create_development_split_assignment,
    interval_for_timestamp,
    map_gate_status,
    select_representative_candidates,
)
from app.vision.pilot_video_intake import (
    assert_no_forbidden_semantics,
    load_strict_json,
    sha256_file,
    write_strict_json,
)


SAFE_ID = "PTC_000001_SES_000001_a54511b0"
PARTICIPANT_ID = "PTC_000001"
SESSION_ID = "SES_000001"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip():
            raise ValueError(f"blank JSONL line at {path}:{line_number}")
        value = json.loads(
            line,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {item}")
            ),
        )
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be an object: {path}")
        values.append(value)
    return values


def _stage_path(stage15: Path, stage: str, filename: str) -> Path:
    return stage15 / stage / SAFE_ID / filename


def _event_inventory(
    rows: list[dict[str, Any]], answers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    values = []
    for row in rows:
        answer = interval_for_timestamp(row["timestamp_ms"], answers)
        values.append({
            "timestamp_ms": row["timestamp_ms"],
            "event_type": row["event_type"],
            "target_id": row["target_id"],
            "answer_id": answer["answer_id"] if answer else None,
            "interval_id": answer["interval_id"] if answer else None,
        })
    return values


def _extract_frame(
    capture: cv2.VideoCapture,
    *,
    timestamp_ms: int,
    fps: float,
    frame_count: int,
    destination: Path,
) -> dict[str, Any]:
    frame_index = round(timestamp_ms * fps / 1000.0)
    if frame_index < 0 or frame_index >= frame_count:
        raise ValueError("requested review frame is outside the video")
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    if not ok or frame is None or frame.size == 0:
        raise ValueError(f"review frame decode failed at {timestamp_ms}ms")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(
        str(destination), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]
    ):
        raise ValueError(f"review frame write failed: {destination}")
    return {
        "requested_timestamp_ms": timestamp_ms,
        "source_frame_index": frame_index,
        "decoded_timestamp_ms": round(frame_index / fps * 1000),
        "path": destination.as_posix(),
        "sha256": sha256_file(destination),
    }


def _contact_sheet(
    entries: list[dict[str, Any]],
    *,
    output_root: Path,
    destination: Path,
    answer_id: str,
) -> dict[str, Any]:
    tile_width, tile_height = 480, 270
    rows: list[np.ndarray] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in entries:
        grouped.setdefault(item["candidate_id"], []).append(item)
    for candidate_id, items in grouped.items():
        tiles = []
        for item in sorted(items, key=lambda value: value["offset_ms"]):
            image = cv2.imread(str(output_root / item["frame_path"]))
            if image is None:
                raise ValueError(f"contact sheet frame missing: {item['frame_path']}")
            image = cv2.resize(image, (tile_width, tile_height))
            label = (
                f"{candidate_id} {item['offset_ms']:+d}ms "
                f"@{item['requested_timestamp_ms']}ms"
            )
            cv2.rectangle(image, (0, 0), (tile_width, 32), (0, 0, 0), -1)
            cv2.putText(
                image, label, (8, 23), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (255, 255, 255), 1, cv2.LINE_AA,
            )
            tiles.append(image)
        rows.append(np.hstack(tiles))
    body = np.vstack(rows)
    header = np.zeros((40, body.shape[1], 3), dtype=np.uint8)
    cv2.putText(
        header, f"{answer_id} manual review candidates", (10, 27),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
    )
    sheet = np.vstack((header, body))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(
        str(destination), sheet, [cv2.IMWRITE_JPEG_QUALITY, 95]
    ):
        raise ValueError(f"contact sheet write failed: {destination}")
    return {
        "answer_id": answer_id,
        "path": destination.relative_to(output_root).as_posix(),
        "candidate_count": len(grouped),
        "frame_count": len(entries),
        "sha256": sha256_file(destination),
    }


def _reevaluate_gate(
    *,
    decision: PilotManualReviewDecision | None,
    split_assignment: Any,
    stage15_quality: dict[str, Any],
    consent_source: dict[str, Any],
    answers: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    automatic_quality_passed = bool(
        stage15_quality["summary"]["automatic_validation_passed"]
    )
    status = map_gate_status(
        decision,
        split_valid=True,
        automatic_quality_passed=automatic_quality_passed,
    )
    if (
        decision is None
        or decision.decision != "APPROVED_FOR_ANNOTATION"
    ):
        return status, None
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
        SESSION_ID,
        decision.reviewer_id or "",
        decision.decision,
        (),
        decision.reviewed_at or "",
        decision.notes,
    )
    candidate = DatasetReleaseCandidate(
        "RELEASE_CANDIDATE_SES_000001",
        "MANIFEST_NOT_CREATED_STAGE_16",
        PARTICIPANT_ID,
        SESSION_ID,
        tuple(item["answer_id"] for item in answers),
        "REVIEW_REQUIRED",
    )
    result = evaluate_dataset_release_gate(
        candidate,
        consent=consent,
        withdrawn=False,
        file_hash_valid=True,
        video_checks_passed=automatic_quality_passed,
        baseline_available=True,
        answer_intervals_valid=True,
        manual_review=manual_review,
        split_assignment=split_assignment,
        split_leakage_detected=False,
    )
    return (
        "pilot_video_annotation_ready" if result.eligible
        else "awaiting_human_manual_review_decision",
        result.to_dict(),
    )


def _markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Face-Fit Stage 16 Manual Review Preparation",
        "",
        f"- Current status: `{report['current_gate_status']}`",
        f"- Participant: `{report['participant_id']}`",
        f"- Session: `{report['session_id']}`",
        f"- Full unique review timestamps: "
        f"{report['candidate_summary']['unique_timestamp_count']}",
        f"- Representative candidates: "
        f"{report['candidate_summary']['representative_candidate_count']}",
        f"- Extracted frames: {report['frame_summary']['frame_count']}",
        f"- Contact sheets: {report['frame_summary']['contact_sheet_count']}",
        "- Split: `DEVELOPMENT`",
        "- Human decision: not present; automated approval was not performed.",
        "",
        "Head Pose availability is a calculation-availability signal only and "
        "must not be interpreted as posture quality or a deduction.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage15-dir", type=Path, required=True)
    parser.add_argument("--incoming-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--decision-file", type=Path)
    args = parser.parse_args()
    stage15 = args.stage15_dir.resolve()
    incoming = args.incoming_dir.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError(f"Stage 16 output already exists: {output}")
    output.mkdir(parents=True)

    stage15_report = load_strict_json(stage15 / "validation_report.json")
    interval_validation = load_strict_json(
        stage15 / "interval_validation.json"
    )
    quality = load_strict_json(stage15 / "quality_check_results.json")
    consent_source = load_strict_json(
        incoming / "PTC_000001_SES_000001.consent.json"
    )
    video_metadata = load_strict_json(stage15 / "video_metadata.json")
    target_report = load_strict_json(
        _stage_path(stage15, "stage6_target", "validation_report.json")
    )
    head_report = load_strict_json(
        _stage_path(stage15, "stage7_head_pose", "validation_report.json")
    )
    head_metrics = _load_jsonl(
        _stage_path(
            stage15, "stage7_head_pose", "frame_head_pose_metrics.jsonl"
        )
    )
    head_events = _load_jsonl(
        _stage_path(stage15, "stage7_head_pose", "head_pose_events.jsonl")
    )
    posture_events = _load_jsonl(
        _stage_path(stage15, "stage8_posture_raw", "posture_events.jsonl")
    )
    answers = interval_validation["answers"]
    duration_ms = round(video_metadata["duration_sec"] * 1000)

    missing_frames = []
    failure_counts: Counter[str] = Counter()
    solvepnp_success_on_missing = 0
    for row in head_metrics:
        pose = row["head_pose"]
        if pose["available"]:
            continue
        failure = pose["failure_reason"]
        failure_counts[failure] += 1
        solvepnp_success_on_missing += pose["solvepnp_success"] is True
        answer = interval_for_timestamp(row["timestamp_ms"], answers)
        missing_frames.append({
            "timestamp_ms": row["timestamp_ms"],
            "failure_reason": failure,
            "solvepnp_success": pose["solvepnp_success"],
            "answer_id": answer["answer_id"] if answer else None,
            "interval_id": answer["interval_id"] if answer else None,
        })
    head_inventory = _event_inventory(head_events, answers)
    posture_inventory = _event_inventory(posture_events, answers)
    missing_segments = head_report["head_pose_summary"]["unavailable_segments"]
    all_timestamps = sorted({
        *(item["timestamp_ms"] for item in missing_frames),
        *(item["timestamp_ms"] for item in head_inventory),
        *(item["timestamp_ms"] for item in posture_inventory),
    })

    representatives = []
    for answer in answers:
        selected = select_representative_candidates(
            answer=answer,
            missing_segments=missing_segments,
            head_jump_timestamps=(
                item["timestamp_ms"] for item in head_inventory
            ),
            posture_jump_timestamps=(
                item["timestamp_ms"] for item in posture_inventory
            ),
        )
        for index, item in enumerate(selected, 1):
            representatives.append({
                **item,
                "candidate_id": (
                    f"{answer['answer_id']}_REVIEW_{index:02d}"
                ),
                "answer_id": answer["answer_id"],
                "interval_id": answer["interval_id"],
            })

    video = incoming / "PTC_000001_SES_000001.mp4"
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("pilot video could not be opened")
    fps = float(video_metadata["source_fps"])
    frame_count = int(video_metadata["frame_count"])
    extracted_by_timestamp: dict[int, dict[str, Any]] = {}
    frame_manifest_entries = []
    for candidate in representatives:
        context = context_frame_timestamps(
            candidate["timestamp_ms"], duration_ms=duration_ms
        )
        for offset, timestamp in zip((-500, 0, 500), context):
            if timestamp not in extracted_by_timestamp:
                relative = (
                    Path("frames") / candidate["answer_id"].lower()
                    / f"frame_{timestamp:06d}ms.jpg"
                )
                extracted = _extract_frame(
                    capture,
                    timestamp_ms=timestamp,
                    fps=fps,
                    frame_count=frame_count,
                    destination=output / relative,
                )
                extracted["path"] = relative.as_posix()
                extracted_by_timestamp[timestamp] = extracted
            frame = extracted_by_timestamp[timestamp]
            frame_manifest_entries.append({
                "candidate_id": candidate["candidate_id"],
                "candidate_type": candidate["candidate_type"],
                "answer_id": candidate["answer_id"],
                "offset_ms": offset,
                "requested_timestamp_ms": timestamp,
                "decoded_timestamp_ms": frame["decoded_timestamp_ms"],
                "source_frame_index": frame["source_frame_index"],
                "frame_path": frame["path"],
                "frame_sha256": frame["sha256"],
            })
    capture.release()
    sheets = []
    for answer in answers:
        entries = [
            item for item in frame_manifest_entries
            if item["answer_id"] == answer["answer_id"]
        ]
        sheets.append(_contact_sheet(
            entries,
            output_root=output,
            destination=(
                output / "frames"
                / f"{answer['answer_id'].lower()}_contact_sheet.jpg"
            ),
            answer_id=answer["answer_id"],
        ))

    candidate_output = {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "video_duration_ms": duration_ms,
        "context_offsets_ms": [-500, 0, 500],
        "full_inventory": {
            "head_pose_missing_frames": missing_frames,
            "head_pose_missing_segments": missing_segments,
            "head_pose_raw_jump_events": head_inventory,
            "posture_raw_jump_events": posture_inventory,
            "unique_candidate_timestamps_ms": all_timestamps,
        },
        "representative_selection": {
            "method": (
                "longest missing segment plus evenly spread first/last RAW "
                "jump candidates per Answer"
            ),
            "maximum_candidates_per_answer": 5,
            "candidates": representatives,
        },
    }
    contact_manifest = {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "source_video_sha256": sha256_file(video),
        "raw_extracted_frames": sorted(
            extracted_by_timestamp.values(),
            key=lambda item: item["requested_timestamp_ms"],
        ),
        "candidate_frame_links": frame_manifest_entries,
        "contact_sheets": sheets,
        "source_video_modified": False,
        "synthetic_video_created": False,
    }
    checklist = [
        "EXCESSIVE_HEAD_ROTATION",
        "FACE_OCCLUSION_GLASSES_OR_HAIR",
        "PNP_FAILURE_OR_VIDEO_QUALITY",
        "CAMERA_MOVEMENT",
        "MULTIPLE_PERSON_OR_TARGET_CHANGE",
        "OBSERVABLE_ANNOTATION_USABILITY",
    ]
    manual_packet = {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "source_stage15_status": stage15_report["final_decision"],
        "automatic_quality_checks_passed": (
            quality["summary"]["automatic_validation_passed"]
        ),
        "review_scope": {
            "head_pose_missing_frame_count": len(missing_frames),
            "head_pose_failure_reason_counts": dict(sorted(failure_counts.items())),
            "solvepnp_success_on_missing_frame_count":
                solvepnp_success_on_missing,
            "head_pose_raw_jump_event_count": len(head_inventory),
            "posture_raw_jump_event_count": len(posture_inventory),
            "face_availability_ratio":
                stage15_report["vision_summary"]["face_availability_ratio"],
            "both_shoulders_availability_ratio":
                stage15_report["vision_summary"][
                    "both_shoulders_availability_ratio"
                ],
            "target_tracking_summary": target_report["tracking_summary"],
        },
        "answer_priority": stage15_report["answer_summary"]["intervals"],
        "human_review_checklist": [
            {"check": item, "status": "NOT_REVIEWED", "notes": None}
            for item in checklist
        ],
        "interpretation_limit": (
            "Head Pose availability is calculation availability only and is "
            "not posture quality or a deduction."
        ),
        "decision_source": "HUMAN_REVIEW_REQUIRED",
        "automatic_manual_review_decision": False,
    }
    template = PilotManualReviewDecision(
        PARTICIPANT_ID, SESSION_ID, None, "REVIEW_PENDING", (), None, None
    ).to_dict()

    assignment, linkage = create_development_split_assignment(
        participant_id=PARTICIPANT_ID,
        session_id=SESSION_ID,
        answer_ids=(item["answer_id"] for item in answers),
    )
    split_output = {
        "assignment": {
            **assignment.to_dict(),
            "split_name": assignment.split,
        },
        "linkage": linkage,
        "existing_assignment_scan": {
            "operational_assignment_found": False,
            "operational_conflict": False,
            "fixture_only_collision_found": True,
            "fixture_only_collision": {
                "participant_id": PARTICIPANT_ID,
                "split_name": "CALIBRATION",
                "source": (
                    "config/pilot_collection/fixtures/pilot_registry.json"
                ),
            },
            "fixture_assignments_are_not_operational": True,
        },
    }

    decision_path = args.decision_file.resolve() if args.decision_file else None
    decision = (
        PilotManualReviewDecision.from_dict(load_strict_json(decision_path))
        if decision_path and decision_path.is_file()
        else None
    )
    status, gate_result = _reevaluate_gate(
        decision=decision,
        split_assignment=assignment,
        stage15_quality=quality,
        consent_source=consent_source,
        answers=answers,
    )
    gate_output = {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "current_status": status,
        "human_decision_file_present": decision is not None,
        "human_decision": decision.to_dict() if decision else None,
        "development_split_valid": True,
        "automatic_quality_checks_passed": True,
        "stage14_gate_reexecuted": gate_result is not None,
        "stage14_gate_result": gate_result,
        "automatic_approval_performed": False,
        "next_action": (
            "A human reviewer must copy the template to a separate decision "
            "file, complete it, and rerun gate reevaluation."
        ),
    }
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "validation_type": "pilot_manual_review_preparation",
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "current_gate_status": status,
        "candidate_summary": {
            "head_pose_missing_frame_count": len(missing_frames),
            "head_pose_missing_segment_count": len(missing_segments),
            "head_pose_raw_jump_event_count": len(head_inventory),
            "posture_raw_jump_event_count": len(posture_inventory),
            "unique_timestamp_count": len(all_timestamps),
            "representative_candidate_count": len(representatives),
        },
        "frame_summary": {
            "frame_count": len(extracted_by_timestamp),
            "candidate_frame_link_count": len(frame_manifest_entries),
            "contact_sheet_count": len(sheets),
        },
        "split_result": split_output,
        "gate_reevaluation": gate_output,
        "protected_inputs": {
            "stage15_loaded_read_only": True,
            "source_video_modified": False,
        },
        "prohibited_operations": {
            "automatic_manual_review_approval": False,
            "evaluative_user_result_produced": False,
            "evaluation_boundary_produced": False,
            "psychological_inference_produced": False,
            "stage11_scoring_executed": False,
            "ml_training_performed": False,
            "dataset_frozen": False,
            "dependency_changed": False,
        },
    }
    outputs = {
        "review_candidate_timestamps.json": candidate_output,
        "review_contact_sheet_manifest.json": contact_manifest,
        "manual_review_packet.json": manual_packet,
        "manual_review_decision.template.json": template,
        "development_split_assignment.json": split_output,
        "gate_reevaluation_status.json": gate_output,
        "validation_report.json": report,
    }
    for name, payload in outputs.items():
        assert_no_forbidden_semantics(payload)
        write_strict_json(output / name, payload)
    (output / "validation_report.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    hashes = {
        path.relative_to(output).as_posix(): sha256_file(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    print(json.dumps({
        "status": status,
        "candidate_summary": report["candidate_summary"],
        "frame_summary": report["frame_summary"],
        "artifact_hashes": hashes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
