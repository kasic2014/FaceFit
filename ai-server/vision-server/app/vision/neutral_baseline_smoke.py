"""Read-only Stage 6-8 linkage smoke test for the Stage 9 baseline model."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core import config
from app.vision.neutral_baseline_collector import collect_baseline_candidates
from app.vision.neutral_baseline_estimator import (
    estimate_session_neutral_baseline,
)
from app.vision.neutral_baseline_models import (
    NeutralBaselineConfig,
    NeutralBaselineFrame,
)
from app.vision.neutral_baseline_serializer import dumps_strict
from app.vision.relative_feature_normalizer import (
    normalize_relative_feature_frame,
)
from app.vision.video_loader import (
    calculate_video_sha256,
    create_safe_video_id,
    inspect_video_metadata,
)


EXPECTED_SOURCE_SHA256 = (
    "6cd4d7ac9d6dc546692d66c8c324dc7f09e1e20f5af846713bd1e119527bea32"
)
DEFAULT_NEUTRAL_BASELINE_OUTPUT_ROOT = (
    config.OUTPUT_DIR / "neutral_baseline_smoke"
)
PROTECTED_STAGE_ROOTS = (
    config.OUTPUT_DIR / "motion_validation",
    config.OUTPUT_DIR / "target_tracking_validation",
    config.OUTPUT_DIR / "head_pose_validation",
    config.OUTPUT_DIR / "posture_raw_validation",
)


class NeutralBaselineSmokeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _protected_hashes(safe_id: str) -> dict[Path, str]:
    hashes: dict[Path, str] = {}
    for root in PROTECTED_STAGE_ROOTS:
        directory = root / safe_id
        if directory.exists():
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    hashes[path.resolve()] = _sha(path)
    return hashes


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise NeutralBaselineSmokeError(
            "PROTECTED_OUTPUT_NOT_FOUND",
            f"Required Stage 6-8 JSONL not found: {path}",
        )
    rows: list[dict[str, Any]] = []
    try:
        for line_number, text in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not text.strip():
                continue
            rows.append(
                json.loads(
                    text,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(value)
                    ),
                )
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise NeutralBaselineSmokeError(
            "INVALID_PROTECTED_JSONL",
            f"{path.name}:{line_number}: {exc}",
        ) from exc
    return rows


def _index_exact(
    rows: list[dict[str, Any]],
    *,
    name: str,
) -> dict[tuple[int, str], dict[str, Any]]:
    result: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        timestamp = row.get("timestamp_ms")
        target_id = row.get("target_id")
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, int)
            or not isinstance(target_id, str)
        ):
            raise NeutralBaselineSmokeError(
                "INVALID_LINKAGE_KEY",
                f"{name} contains an invalid timestamp/target key",
            )
        key = (timestamp, target_id)
        if key in result:
            raise NeutralBaselineSmokeError(
                "DUPLICATE_LINKAGE_KEY",
                f"{name} contains duplicate key {key}",
            )
        result[key] = row
    return result


def build_baseline_frames(
    target_rows: list[dict[str, Any]],
    head_rows: list[dict[str, Any]],
    posture_rows: list[dict[str, Any]],
) -> list[NeutralBaselineFrame]:
    """Join exact timestamps and derive unsmoothed Head Pose velocity."""

    target = _index_exact(target_rows, name="target tracking")
    head = _index_exact(head_rows, name="head pose")
    posture = _index_exact(posture_rows, name="posture")
    if not target or set(target) != set(head) or set(target) != set(posture):
        raise NeutralBaselineSmokeError(
            "STAGE_OUTPUT_ALIGNMENT_MISMATCH",
            "Stage 6, 7, and 8 timestamp + target keys must match exactly",
        )
    result: list[NeutralBaselineFrame] = []
    previous_timestamp: int | None = None
    previous_angles: tuple[float, float, float] | None = None
    for key in sorted(target):
        timestamp, target_id = key
        target_row = target[key]
        head_row = head[key]
        posture_row = posture[key]
        head_payload = head_row.get("head_pose") or {}
        angles: tuple[float, float, float] | None = None
        if head_payload.get("available"):
            raw_angles = (
                head_payload.get("yaw_deg"),
                head_payload.get("pitch_deg"),
                head_payload.get("roll_deg"),
            )
            if all(
                value is not None
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in raw_angles
            ):
                angles = tuple(float(value) for value in raw_angles)
        velocity = None
        if (
            angles is not None
            and previous_angles is not None
            and previous_timestamp is not None
            and timestamp > previous_timestamp
        ):
            elapsed_seconds = (timestamp - previous_timestamp) / 1000.0
            velocity = max(
                abs(current - previous) / elapsed_seconds
                for current, previous in zip(angles, previous_angles)
            )
        if angles is None:
            previous_angles = None
            previous_timestamp = None
        else:
            previous_angles = angles
            previous_timestamp = timestamp
        result.append(
            NeutralBaselineFrame(
                timestamp_ms=timestamp,
                target_id=target_id,
                target_status=target_row.get("target_status"),
                candidate_count=int(target_row.get("candidate_count") or 0),
                target_confidence=float(
                    target_row.get("target_confidence") or 0.0
                ),
                head_pose=dict(head_payload),
                head_angular_velocity_deg_per_sec=velocity,
                head_jump_candidate=bool(
                    head_row.get("angular_jump_axes")
                ),
                posture_raw=dict(posture_row.get("posture_raw") or {}),
                posture_temporal=dict(
                    posture_row.get("posture_temporal") or {}
                ),
                posture_jump_candidate=bool(
                    posture_row.get("posture_jump_candidates")
                ),
            )
        )
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(dumps_strict(row))
            stream.write("\n")


def _markdown(report: dict[str, Any]) -> str:
    baseline = report["baseline_summary"]
    counts = report["relative_feature_summary"]
    return "\n".join(
        (
            "# Stage 9 session neutral baseline smoke report",
            "",
            f"- Technical judgment: `{report['technical_judgment']}`",
            f"- Source SHA-256: `{report['source']['sha256']}`",
            f"- Linked frames: {report['data_linkage']['linked_frame_count']}",
            (
                "- Collection window: "
                f"{baseline['collection_start_ms']}–"
                f"{baseline['collection_end_ms']} ms"
            ),
            f"- Baseline available: {baseline['available']}",
            f"- Collection quality: {baseline['quality_score']:.6f}",
            (
                "- Head / shoulder / nose / face candidates: "
                f"{baseline['candidate_counts']['head_pose']} / "
                f"{baseline['candidate_counts']['shoulder']} / "
                f"{baseline['candidate_counts']['nose_alignment']} / "
                f"{baseline['candidate_counts']['face_alignment']}"
            ),
            (
                "- Relative available frames (head / shoulder / nose / face): "
                f"{counts['head_pose_available_frames']} / "
                f"{counts['shoulder_available_frames']} / "
                f"{counts['nose_alignment_available_frames']} / "
                f"{counts['face_alignment_available_frames']}"
            ),
            "",
            "This is a technical collection smoke test. The selected interval "
            "is not asserted to be true neutral posture.",
            "The quality value describes baseline collection quality only; it "
            "is not a posture, interview, confidence, focus, or anxiety score.",
            "",
        )
    )


class NeutralBaselineSmokeValidator:
    def validate(
        self,
        video_path: str | Path,
        *,
        collection_start_ms: int = 0,
        collection_end_ms: int | None = None,
        output_root: str | Path = DEFAULT_NEUTRAL_BASELINE_OUTPUT_ROOT,
        overwrite: bool = False,
        baseline_config: NeutralBaselineConfig = NeutralBaselineConfig(),
        expected_source_sha256: str = EXPECTED_SOURCE_SHA256,
        target_output_root: str | Path = config.OUTPUT_DIR / "target_tracking_validation",
        head_pose_output_root: str | Path = config.OUTPUT_DIR / "head_pose_validation",
        posture_output_root: str | Path = config.OUTPUT_DIR / "posture_raw_validation",
        protected_stage_roots: tuple[str | Path, ...] | None = None,
    ) -> dict[str, Any]:
        source = Path(video_path).resolve()
        metadata = inspect_video_metadata(source)
        if metadata["sha256"] != expected_source_sha256:
            raise NeutralBaselineSmokeError(
                "SOURCE_SHA256_MISMATCH",
                "Stage 9 smoke only accepts the protected movement video",
            )
        safe_id = create_safe_video_id(source.name, metadata["sha256"])
        roots_to_protect = (
            PROTECTED_STAGE_ROOTS
            if protected_stage_roots is None
            else tuple(Path(item) for item in protected_stage_roots)
        )
        protected = {}
        for root in roots_to_protect:
            directory = Path(root) / safe_id
            if directory.exists():
                for path in sorted(directory.rglob("*")):
                    if path.is_file():
                        protected[path.resolve()] = _sha(path)
        roots = {
            "target": Path(target_output_root) / safe_id,
            "head": Path(head_pose_output_root) / safe_id,
            "posture": Path(posture_output_root) / safe_id,
        }
        target_rows = _load_jsonl(
            roots["target"] / "frame_target_metrics.jsonl"
        )
        head_rows = _load_jsonl(
            roots["head"] / "frame_head_pose_metrics.jsonl"
        )
        posture_rows = _load_jsonl(
            roots["posture"] / "frame_posture_metrics.jsonl"
        )
        frames = build_baseline_frames(target_rows, head_rows, posture_rows)
        end = (
            collection_start_ms + baseline_config.collection_duration_ms
            if collection_end_ms is None
            else collection_end_ms
        )
        collection = collect_baseline_candidates(
            frames,
            collection_start_ms=collection_start_ms,
            collection_end_ms=end,
            config=baseline_config,
        )
        baseline = estimate_session_neutral_baseline(
            collection,
            baseline_config,
        )
        relative_frames = [
            normalize_relative_feature_frame(
                timestamp_ms=frame.timestamp_ms,
                target_id=frame.target_id,
                raw_head_pose=frame.head_pose,
                raw_posture=frame.posture_raw,
                baseline=baseline,
            )
            for frame in frames
        ]
        relative_payloads = [item.to_dict() for item in relative_frames]
        availability = {
            "head_pose_available_frames": sum(
                item.head_pose.available for item in relative_frames
            ),
            "shoulder_available_frames": sum(
                item.posture.shoulder.available for item in relative_frames
            ),
            "nose_alignment_available_frames": sum(
                item.posture.nose_alignment.available
                for item in relative_frames
            ),
            "face_alignment_available_frames": sum(
                item.posture.face_alignment.available
                for item in relative_frames
            ),
        }
        failure_counts = Counter(
            metric.failure_reason
            for item in relative_frames
            for metric in (
                item.head_pose.yaw,
                *item.posture.shoulder.metrics.values(),
                *item.posture.nose_alignment.metrics.values(),
                *item.posture.face_alignment.metrics.values(),
            )
            if metric.failure_reason
        )
        report = {
            "schema_version": "1.0",
            "validation_type": "session_neutral_baseline_relative_model_smoke",
            "status": "completed",
            "generated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source": metadata,
            "configuration": {
                **baseline_config.__dict__,
                "collection_start_ms": collection_start_ms,
                "collection_end_ms": end,
                "target_id": "TARGET_001",
                "raw_baseline_relative_separated": True,
                "smoothing": "NONE",
                "posture_scoring_enabled": False,
                "interview_scoring_enabled": False,
            },
            "data_linkage": {
                "key": "timestamp_ms + TARGET_001",
                "linked_frame_count": len(frames),
                "stage_6_target_frames": len(target_rows),
                "stage_7_head_pose_frames": len(head_rows),
                "stage_8_posture_frames": len(posture_rows),
            },
            "baseline_summary": {
                "available": baseline.available,
                "status": baseline.status,
                "failure_reason": baseline.failure_reason,
                "collection_start_ms": baseline.collection_start_ms,
                "collection_end_ms": baseline.collection_end_ms,
                "quality_score": baseline.quality_score,
                "quality_interpretation": (
                    "collection quality only; never posture/interview quality"
                ),
                "candidate_counts": {
                    "common": collection.common_frame_count,
                    "head_pose": len(collection.head_pose_frames),
                    "shoulder": len(collection.shoulder_frames),
                    "nose_alignment": len(collection.nose_alignment_frames),
                    "face_alignment": len(collection.face_alignment_frames),
                },
                "rejection_reason_counts": collection.rejection_reason_counts,
                "warnings": list(baseline.warnings),
            },
            "relative_feature_summary": {
                **availability,
                "failure_reason_counts": dict(failure_counts),
                "relative_definition": "raw_value - session_baseline_value",
                "unavailable_values": "null_with_explicit_failure_reason",
            },
            "technical_judgment": (
                "baseline_model_smoke_completed_non_ground_truth"
                if baseline.available
                else "baseline_collection_insufficient_for_neutral_validation"
            ),
            "limitations": [
                "The collection interval is not labeled neutral ground truth.",
                "Baseline values are session-local camera/user references.",
                "Quality score measures collection quality, not posture quality.",
                "No posture, interview, confidence, focus, or anxiety score is produced.",
                "No smoothing, calibration, or multi-person tracking is added.",
            ],
            "outputs": {
                "baseline_json": "baseline.json",
                "relative_features_jsonl": "relative_features.jsonl",
                "validation_report_json": "validation_report.json",
                "validation_report_markdown": "validation_report.md",
            },
        }
        destination = Path(output_root).resolve() / safe_id
        if destination.exists() and not overwrite:
            raise NeutralBaselineSmokeError(
                "OUTPUT_ALREADY_EXISTS",
                f"Output exists: {destination}",
            )
        output_root_path = Path(output_root).resolve()
        output_root_path.mkdir(parents=True, exist_ok=True)
        staged: Path | None = Path(
            tempfile.mkdtemp(prefix=f".{safe_id}.", dir=output_root_path)
        )
        try:
            (staged / "baseline.json").write_text(
                dumps_strict(baseline, indent=2) + "\n",
                encoding="utf-8",
            )
            _write_jsonl(staged / "relative_features.jsonl", relative_payloads)
            (staged / "validation_report.json").write_text(
                dumps_strict(report, indent=2) + "\n",
                encoding="utf-8",
            )
            (staged / "validation_report.md").write_text(
                _markdown(report),
                encoding="utf-8",
            )
            if calculate_video_sha256(source) != expected_source_sha256:
                raise NeutralBaselineSmokeError(
                    "PROTECTED_INPUT_CHANGED",
                    "Input video changed during smoke validation",
                )
            if any(
                not path.is_file() or _sha(path) != digest
                for path, digest in protected.items()
            ):
                raise NeutralBaselineSmokeError(
                    "PROTECTED_OUTPUT_CHANGED",
                    "A Stage 5-8 protected output changed during validation",
                )
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.old")
                if backup.exists():
                    raise NeutralBaselineSmokeError(
                        "STALE_OUTPUT_BACKUP",
                        f"Refusing to replace while backup exists: {backup}",
                    )
                os.replace(destination, backup)
                try:
                    os.replace(staged, destination)
                except OSError:
                    os.replace(backup, destination)
                    raise
                shutil.rmtree(backup)
            else:
                os.replace(staged, destination)
            staged = None
            return report
        finally:
            if staged is not None:
                shutil.rmtree(staged, ignore_errors=True)
