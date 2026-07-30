"""Build the Stage 15 real-pilot intake and manual-review packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.collection_quality_validator import validate_quality_checks
from app.vision.consent_models import ConsentReference
from app.vision.dataset_release_gate import evaluate_dataset_release_gate
from app.vision.pilot_collection_models import (
    CollectionQualityCheck,
    DatasetReleaseCandidate,
    QualityCheckStatus,
    QualityCheckType,
)
from app.vision.pilot_video_intake import (
    assert_no_forbidden_semantics,
    load_strict_json,
    parse_ffprobe_json,
    sha256_file,
    validate_consent,
    validate_metadata,
    write_strict_json,
)


EXPECTED_VIDEO_SHA256 = (
    "a54511b0802641845dd92866124a5a74be90877e39c0e0880f6e45142cef87bc"
)
SAFE_ID = "PTC_000001_SES_000001_a54511b0"


def _load_stage_report(root: Path, stage: str) -> dict[str, Any]:
    return load_strict_json(root / stage / SAFE_ID / "validation_report.json")


def _probe_with_existing_pyav(video: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    helper = Path(__file__).with_name("probe_video_with_pyav.py").resolve()
    analysis_python = (
        Path(__file__).resolve().parents[2]
        / "analysis-server" / ".venv" / "Scripts" / "python.exe"
    )
    result = subprocess.run(
        [str(analysis_python), str(helper), str(video)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    raw = json.loads(result.stdout)
    return parse_ffprobe_json(raw), {
        "requested_backend": "ffprobe",
        "ffprobe_executable_available": False,
        "effective_backend": "PYAV_EXISTING_FFMPEG_LIBRARIES",
        "dependency_changed": False,
        "warning": (
            "ffprobe executable was unavailable; the existing PyAV FFmpeg "
            "bindings supplied equivalent container/stream metadata."
        ),
    }


def _full_decode(video: Path) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video))
    opened = capture.isOpened()
    count = 0
    invalid = 0
    while opened:
        ok, frame = capture.read()
        if not ok:
            break
        count += 1
        if frame is None or frame.size == 0:
            invalid += 1
    capture.release()
    return {
        "capture_opened": opened,
        "decoded_frame_count": count,
        "invalid_frame_count": invalid,
        "full_decode_succeeded": opened and count > 0 and invalid == 0,
    }


def _check(
    index: int, session_id: str, check_type: QualityCheckType, passed: bool,
    reason: str | None = None,
) -> CollectionQualityCheck:
    return CollectionQualityCheck(
        f"QC_{index:03d}",
        session_id,
        check_type.value,
        QualityCheckStatus.PASSED.value if passed else QualityCheckStatus.FAILED.value,
        None if passed else reason,
    )


def _markdown(report: dict[str, Any]) -> str:
    metadata = report["video_metadata"]
    lines = [
        "# Face-Fit Stage 15 Pilot Video Intake Validation",
        "",
        f"- Final decision: `{report['final_decision']}`",
        f"- Video SHA-256: `{metadata['sha256']}`",
        f"- Video: {metadata['codec']}, {metadata['width']}x{metadata['height']}, "
        f"{metadata['source_fps']:.6f} FPS, {metadata['frame_count']} frames, "
        f"{metadata['duration_sec']:.6f} seconds",
        f"- Audio stream: {metadata['audio_stream_present']}",
        f"- Consent valid: {report['consent_validation']['valid']}",
        f"- Metadata and intervals valid: {report['interval_validation']['valid']}",
        f"- Face availability: {report['vision_summary']['face_availability_ratio']:.6f}",
        f"- Both shoulders availability: "
        f"{report['vision_summary']['both_shoulders_availability_ratio']:.6f}",
        f"- Single target valid: {report['vision_summary']['single_target_valid']}",
        f"- Baseline available: {report['baseline_summary']['available']}",
        f"- Answer intervals aggregated: {report['answer_summary']['aggregated_count']}/4",
        "",
        "The result contains raw/relative technical features only. No Stage 11 "
        "scoring, evaluative posture/interview score, or evaluation threshold was produced.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    incoming = args.input_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    video = incoming / "PTC_000001_SES_000001.mp4"
    consent_path = incoming / "PTC_000001_SES_000001.consent.json"
    metadata_path = incoming / "PTC_000001_SES_000001.metadata.json"
    consent = load_strict_json(consent_path)
    metadata = load_strict_json(metadata_path)
    consent_result = validate_consent(consent)
    actual_hash = sha256_file(video)
    probe, backend = _probe_with_existing_pyav(video)
    decode = _full_decode(video)
    duration_ms = int(probe["duration_sec"] * 1000)
    interval_result = validate_metadata(
        metadata,
        consent,
        expected_video_filename=video.name,
        duration_ms=duration_ms,
    )
    hash_valid = (
        actual_hash == EXPECTED_VIDEO_SHA256 == metadata["expected_sha256"]
    )
    temporal = _load_stage_report(output, "stage5_temporal")
    target = _load_stage_report(output, "stage6_target")
    head = _load_stage_report(output, "stage7_head_pose")
    posture = _load_stage_report(output, "stage8_posture_raw")
    baseline = _load_stage_report(output, "stage9_baseline_relative")
    intervals = _load_stage_report(output, "stage10_intervals")
    availability = temporal["detection_availability"]
    tracking = target["tracking_summary"]
    single_target = (
        tracking["target_id"] == "TARGET_001"
        and tracking["target_id_change_count"] == 0
        and tracking["ambiguous_frame_count"] == 0
        and tracking["target_lost_frame_count"] == 0
    )
    baseline_available = baseline["baseline_summary"]["available"] is True
    interval_summaries = intervals["interval_summaries"]
    answer_valid = (
        interval_result["valid"]
        and len(interval_summaries) == 4
        and all(item["failure_reason"] is None for item in interval_summaries)
    )
    checks = [
        _check(1, metadata["session_id"], QualityCheckType.VIDEO_FILE_EXISTS, video.is_file(), "FILE_MISSING"),
        _check(2, metadata["session_id"], QualityCheckType.VIDEO_HASH_VALID, hash_valid, "HASH_MISMATCH"),
        _check(3, metadata["session_id"], QualityCheckType.VIDEO_DECODABLE, decode["full_decode_succeeded"], "VIDEO_DECODE_FAILED"),
        _check(4, metadata["session_id"], QualityCheckType.DURATION_VALID, probe["duration_sec"] > 0 and interval_result["valid"], "INVALID_DURATION"),
        _check(5, metadata["session_id"], QualityCheckType.RESOLUTION_VALID, probe["width"] > 0 and probe["height"] > 0, "INVALID_RESOLUTION"),
        _check(6, metadata["session_id"], QualityCheckType.SOURCE_FPS_VALID, probe["source_fps"] > 0, "INVALID_FPS"),
        _check(7, metadata["session_id"], QualityCheckType.FACE_AVAILABLE, availability["face"]["detection_ratio"] > 0, "FACE_NOT_VISIBLE"),
        _check(8, metadata["session_id"], QualityCheckType.BOTH_SHOULDERS_AVAILABLE, availability["required_shoulders"]["detection_ratio"] > 0, "BOTH_SHOULDERS_NOT_VISIBLE"),
        _check(9, metadata["session_id"], QualityCheckType.SINGLE_TARGET_VALID, single_target, "MULTIPLE_PERSON_DETECTED"),
        _check(10, metadata["session_id"], QualityCheckType.BASELINE_AVAILABLE, baseline_available, "BASELINE_FAILED"),
        _check(11, metadata["session_id"], QualityCheckType.ANSWER_INTERVALS_VALID, answer_valid, "ANSWER_INTERVAL_INVALID"),
    ]
    quality = validate_quality_checks(checks, pilot_session_id=metadata["session_id"])
    consent_model = ConsentReference(
        consent["consent_reference_id"], consent["participant_id"],
        consent["consent_status"], consent["schema_version"],
        consent["video_collection_allowed"], consent["automated_analysis_allowed"],
        consent["research_use_allowed"], consent["model_development_use_allowed"],
        consent["withdrawn_at"],
    )
    candidate = DatasetReleaseCandidate(
        "RELEASE_CANDIDATE_SES_000001",
        "MANIFEST_NOT_CREATED_STAGE_15",
        metadata["participant_id"], metadata["session_id"],
        tuple(item["answer_id"] for item in metadata["answers"]),
        "REVIEW_REQUIRED",
    )
    gate = evaluate_dataset_release_gate(
        candidate,
        consent=consent_model,
        withdrawn=metadata["withdrawn"],
        file_hash_valid=hash_valid,
        video_checks_passed=bool(quality["automatic_validation_passed"]),
        baseline_available=baseline_available,
        answer_intervals_valid=answer_valid,
        manual_review=None,
        split_assignment=None,
        split_leakage_detected=False,
    )
    review_reasons = [
        "MANUAL_REVIEW_NOT_APPROVED",
        "PARTICIPANT_SPLIT_MISSING",
        "HEAD_POSE_AND_POSTURE_JUMP_CANDIDATES_REQUIRE_VISUAL_REVIEW",
        "MULTI_PERSON_AMBIGUITY_NOT_OBSERVED_IN_THIS_SINGLE_PERSON_VIDEO",
    ]
    final_decision = (
        "pilot_video_excluded"
        if not consent_result["valid"] or metadata["withdrawn"]
        else "pilot_video_intake_validation_failed"
        if not hash_valid or not decode["full_decode_succeeded"]
        else "pilot_video_recording_required"
        if not quality["automatic_validation_passed"]
        else "pilot_video_annotation_ready"
        if gate.eligible
        else "pilot_video_manual_review_required"
    )
    video_metadata = {
        "file_exists": video.is_file(),
        "file_size_bytes": video.stat().st_size,
        "sha256": actual_hash,
        "expected_sha256": metadata["expected_sha256"],
        "hash_valid": hash_valid,
        **probe,
        "probe": backend,
        "decode": decode,
    }
    consent_output = {
        **consent_result,
        "participant_id": consent["participant_id"],
        "consent_reference_id": consent["consent_reference_id"],
        "consent_status": consent["consent_status"],
        "withdrawn_at": consent["withdrawn_at"],
        "source_sha256": sha256_file(consent_path),
    }
    interval_output = {
        **interval_result,
        "participant_id": metadata["participant_id"],
        "session_id": metadata["session_id"],
        "source_sha256": sha256_file(metadata_path),
    }
    quality_output = {
        "checks": [item.to_dict() for item in checks],
        "summary": quality,
    }
    vision_summary = {
        "sampled_frame_count": temporal["sampling"]["sampled_frame_count"],
        "timestamps_strictly_increasing": temporal["sampling"]["timestamps_strictly_increasing"],
        "face_availability_ratio": availability["face"]["detection_ratio"],
        "left_shoulder_availability_ratio": availability["left_shoulder"]["detection_ratio"],
        "right_shoulder_availability_ratio": availability["right_shoulder"]["detection_ratio"],
        "both_shoulders_availability_ratio": availability["required_shoulders"]["detection_ratio"],
        "face_and_shoulders_availability_ratio": availability["face_and_shoulders"]["detection_ratio"],
        "missing_segments": {
            "face": availability["face"]["missing_segments"],
            "left_shoulder": availability["left_shoulder"]["missing_segments"],
            "right_shoulder": availability["right_shoulder"]["missing_segments"],
        },
        "single_target_valid": single_target,
        "tracking_summary": tracking,
        "head_pose_raw_availability": {
            key: head["head_pose_summary"][key]
            for key in (
                "total_frame_count", "available_frame_count",
                "unavailable_frame_count", "availability_ratio",
                "longest_unavailable_duration_sec", "unavailable_segments",
            )
        },
        "posture_raw_availability": {
            key: posture["posture_summary"][key]
            for key in ("total_frame_count", "shoulders", "nose_alignment", "face_alignment")
        },
    }
    answer_summary = {
        "requested_count": 4,
        "aggregated_count": len(interval_summaries),
        "all_valid": answer_valid,
        "intervals": interval_summaries,
    }
    manual_packet = {
        "video_metadata": video_metadata,
        "consent_validation": consent_output,
        "quality_checks": quality_output,
        "vision_availability": vision_summary,
        "target_tracking_warnings": target["warnings"],
        "missing_intervals": vision_summary["missing_segments"],
        "baseline_interval": metadata["baseline_interval"],
        "answer_intervals": metadata["answers"],
        "review_reasons": review_reasons,
        "recording_required_reasons": [],
    }
    readiness = {
        "final_decision": final_decision,
        "automatic_annotation_ready_candidate": bool(
            consent_result["valid"]
            and quality["automatic_validation_passed"]
            and baseline_available and answer_valid
        ),
        "annotation_ready": gate.eligible,
        "stage14_dataset_release_gate": gate.to_dict(),
        "manual_review_required": not gate.eligible,
        "dataset_frozen": False,
    }
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "validation_type": "pilot_video_intake_annotation_readiness",
        "final_decision": final_decision,
        "video_metadata": video_metadata,
        "consent_validation": consent_output,
        "interval_validation": interval_output,
        "vision_summary": vision_summary,
        "baseline_summary": {
            key: baseline["baseline_summary"][key]
            for key in (
                "available", "status", "collection_start_ms",
                "collection_end_ms", "candidate_counts",
                "rejection_reason_counts", "failure_reason", "warnings",
            )
        },
        "answer_summary": answer_summary,
        "quality_check_results": quality_output,
        "annotation_readiness": readiness,
        "pipeline_stages": {
            "stage5": temporal["status"],
            "stage6": target["status"],
            "stage7": head["status"],
            "stage8": posture["status"],
            "stage9": baseline["status"],
            "stage10": intervals["status"],
            "stage11_scoring_executed": False,
        },
        "prohibited_operations": {
            "evaluative_score_produced": False,
            "evaluation_boundary_produced": False,
            "psychological_inference_produced": False,
            "ml_training_performed": False,
            "dataset_frozen": False,
            "dependency_changed": False,
        },
    }
    outputs = {
        "video_metadata.json": video_metadata,
        "consent_validation.json": consent_output,
        "interval_validation.json": interval_output,
        "quality_check_results.json": quality_output,
        "manual_review_packet.json": manual_packet,
        "annotation_readiness.json": readiness,
        "validation_report.json": report,
    }
    for name, payload in outputs.items():
        assert_no_forbidden_semantics(payload)
        write_strict_json(output / name, payload)
    (output / "validation_report.md").write_text(_markdown(report), encoding="utf-8")
    artifact_hashes = {
        name: sha256_file(output / name)
        for name in (*outputs.keys(), "validation_report.md")
    }
    print(json.dumps({
        "final_decision": final_decision,
        "artifact_hashes": artifact_hashes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
