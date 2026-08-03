"""Stage 19 independent-rater validation and policy-gated agreement package.

The module treats submitted rater events as immutable evidence.  It reuses the
Stage 13 temporal-IoU and presence-agreement contracts, but it never selects
event matches or calculates agreement unless an approved matching policy is
available.  The current Stage 13 implementation explicitly has no approved
cutoff, so Stage 19 emits pairwise comparison material and stops at policy
review.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.vision.annotation_agreement import temporal_iou
from app.vision.annotation_registry import AnnotationRegistry
from app.vision.pilot_annotation_package import (
    BLIND_FLAG_NAMES,
    PARTICIPANT_ID,
    RATER_IDS,
    RUBRIC_ID,
    RUBRIC_VERSION,
    registry_from_dict,
    validate_rater_submission,
)
from app.vision.pilot_video_intake import (
    ensure_finite,
    load_strict_json,
    sha256_file,
)


STAGE = 19
SCHEMA_VERSION = "1.0.0"
SESSION_ID = "SES_000001"
EXPECTED_SPLIT = "DEVELOPMENT"
AGREEMENT_CONTEXT = "RATER_IDENTITY_UNVERIFIED"
POLICY_REVIEW_STATUS = "agreement_policy_review_required"
VALIDATION_FAILED_STATUS = "rater_annotation_validation_failed"
READY_FOR_ADJUDICATION_STATUS = "awaiting_adjudication_decision"

OUTPUT_NAMES = (
    "input_validation.json",
    "agreement_policy_snapshot.json",
    "agreement_summary.json",
    "event_match_results.jsonl",
    "disagreement_candidates.json",
    "adjudication_packet.json",
    "adjudication_decision.template.json",
    "validation_report.json",
    "validation_report.md",
)

DISAGREEMENT_TYPES = (
    "EXACT_MATCH",
    "PARTIAL_MATCH",
    "TEMPORAL_BOUNDARY_MISMATCH",
    "LABEL_MISMATCH",
    "DIRECTION_MISMATCH",
    "ZERO_OVERLAP",
    "RATER_A_ONLY",
    "RATER_B_ONLY",
)

FORBIDDEN_RESULT_KEYS = frozenset(
    {
        "score",
        "scores",
        "threshold",
        "thresholds",
        "anxiety",
        "attention",
        "personality",
        "hirability",
        "pass_probability",
        "fail_probability",
        "psychological_profile",
    }
)


class Stage19ValidationError(ValueError):
    """Strict input validation failure carrying a stable terminal status."""


def _require_fields(
    value: dict[str, Any],
    required: Iterable[str],
    context: str,
) -> None:
    missing = sorted(set(required) - set(value))
    if missing:
        raise Stage19ValidationError(
            f"{context} missing fields: {', '.join(missing)}"
        )


def _require_iso8601(value: Any, context: str) -> None:
    if not isinstance(value, str):
        raise Stage19ValidationError(f"{context} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage19ValidationError(
            f"{context} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        raise Stage19ValidationError(f"{context} must include timezone")


def _assert_no_forbidden_result_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_RESULT_KEYS:
                raise Stage19ValidationError(
                    f"forbidden Stage 19 result field at {path}.{key}"
                )
            _assert_no_forbidden_result_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_result_keys(item, f"{path}[{index}]")


def validate_package_context(
    manifest: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    _require_fields(
        manifest,
        (
            "participant_id",
            "session_id",
            "split_name",
            "rubric_id",
            "rubric_version",
            "answer_count",
        ),
        "annotation package manifest",
    )
    _require_fields(
        metadata,
        ("participant_id", "session_id", "answers"),
        "session metadata",
    )
    checks = {
        "participant_id": (
            manifest["participant_id"] == PARTICIPANT_ID
            and metadata["participant_id"] == PARTICIPANT_ID
        ),
        "session_id": (
            manifest["session_id"] == SESSION_ID
            and metadata["session_id"] == SESSION_ID
        ),
        "split": manifest["split_name"] == EXPECTED_SPLIT,
        "rubric": (
            manifest["rubric_id"] == RUBRIC_ID
            and manifest["rubric_version"] == RUBRIC_VERSION
        ),
        "answer_count": (
            isinstance(metadata["answers"], list)
            and manifest["answer_count"] == len(metadata["answers"]) == 4
        ),
    }
    answer_ids = (
        [item.get("answer_id") for item in metadata["answers"]]
        if isinstance(metadata["answers"], list)
        else []
    )
    checks["answer_ids"] = answer_ids == [
        "ANS_000001",
        "ANS_000002",
        "ANS_000003",
        "ANS_000004",
    ]
    if not all(checks.values()):
        failed = ", ".join(key for key, passed in checks.items() if not passed)
        raise Stage19ValidationError(
            f"annotation package context mismatch: {failed}"
        )
    return checks


def validate_submission(
    value: dict[str, Any],
    *,
    expected_rater_id: str,
    answers: list[dict[str, Any]],
    registry: AnnotationRegistry,
) -> dict[str, Any]:
    try:
        details = validate_rater_submission(
            value,
            expected_rater_id=expected_rater_id,
            answers=answers,
            registry=registry,
            require_completed=True,
        )
    except ValueError as exc:
        raise Stage19ValidationError(str(exc)) from exc

    _require_iso8601(value["completed_at"], "completed_at")
    if not all(value.get(flag) is True for flag in BLIND_FLAG_NAMES):
        raise Stage19ValidationError("all eight blind flags must be true")

    rubric = registry.get_rubric(RUBRIC_ID, RUBRIC_VERSION)
    rubric_labels = set(rubric.label_ids)
    for event in value["events"]:
        if event["label_id"] not in rubric_labels:
            raise Stage19ValidationError(
                "event label is not included in the submitted rubric"
            )
    ensure_finite(value)
    return {
        **details,
        "completed_at_valid": True,
        "blind_flag_count": len(BLIND_FLAG_NAMES),
        "rubric_membership_valid": True,
        "finite_values_valid": True,
    }


def _event_sort_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["answer_id"],
        event["label_id"],
        event["direction"] or "",
        event["start_timestamp_ms"],
        event["end_timestamp_ms"],
        event["annotation_event_id"],
    )


def build_pairwise_candidates(
    rater_a_events: Iterable[dict[str, Any]],
    rater_b_events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create raw candidates without selecting or declaring any match."""

    a_events = sorted(rater_a_events, key=_event_sort_key)
    b_events = sorted(rater_b_events, key=_event_sort_key)
    candidates: list[dict[str, Any]] = []
    candidate_index = 0
    for a_event in a_events:
        for b_event in b_events:
            if (
                a_event["answer_id"],
                a_event["label_id"],
                a_event["direction"],
            ) != (
                b_event["answer_id"],
                b_event["label_id"],
                b_event["direction"],
            ):
                continue
            candidate_index += 1
            start_a = a_event["start_timestamp_ms"]
            end_a = a_event["end_timestamp_ms"]
            start_b = b_event["start_timestamp_ms"]
            end_b = b_event["end_timestamp_ms"]
            overlap = max(0, min(end_a, end_b) - max(start_a, start_b))
            union = max(end_a, end_b) - min(start_a, start_b)
            iou = temporal_iou(start_a, end_a, start_b, end_b)
            if start_a == start_b and end_a == end_b:
                raw_relation = "EXACT_MATCH"
            elif overlap > 0:
                raw_relation = "PARTIAL_MATCH"
            else:
                raw_relation = "ZERO_OVERLAP"
            candidates.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "candidate_id": f"PAIR_{candidate_index:06d}",
                    "answer_id": a_event["answer_id"],
                    "label_id": a_event["label_id"],
                    "direction": a_event["direction"],
                    "rater_a_event_id": a_event["annotation_event_id"],
                    "rater_b_event_id": b_event["annotation_event_id"],
                    "rater_a_interval": {
                        "start_timestamp_ms": start_a,
                        "end_timestamp_ms": end_a,
                    },
                    "rater_b_interval": {
                        "start_timestamp_ms": start_b,
                        "end_timestamp_ms": end_b,
                    },
                    "overlap_duration_ms": overlap,
                    "union_duration_ms": union,
                    "temporal_iou": iou,
                    "onset_difference_ms": abs(start_a - start_b),
                    "offset_difference_ms": abs(end_a - end_b),
                    "raw_temporal_relation": raw_relation,
                    "selected_as_match": False,
                    "selection_status": (
                        "NOT_SELECTED_AGREEMENT_POLICY_REVIEW_REQUIRED"
                    ),
                }
            )
    ensure_finite(candidates)
    return candidates


def agreement_policy_snapshot() -> dict[str, Any]:
    """Describe the Stage 13 contract without promoting it to approval."""

    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "source_stage": 13,
        "source_implementation": {
            "module": "app.vision.annotation_agreement",
            "available_functions": [
                "temporal_iou",
                "calculate_presence_agreement",
                "compare_event_sets",
            ],
            "functions_applied": ["temporal_iou"],
            "functions_not_applied_without_approved_policy": [
                "calculate_presence_agreement",
                "compare_event_sets",
            ],
            "time_unit": "INTEGER_MILLISECOND",
            "interval_contract": "[start,end)",
            "candidate_key": [
                "answer_id",
                "label_id",
                "direction",
            ],
            "implemented_selection": (
                "greedy maximum Temporal IoU; positive overlap treated as match"
            ),
        },
        "policy_id": None,
        "policy_version": None,
        "matching_policy_approved": False,
        "matching_cutoff": None,
        "approval_cutoff_defined": False,
        "policy_application_status": "NOT_APPLIED",
        "review_reason": (
            "Stage 13 explicitly records approval_cutoff_defined=false; "
            "no approved policy ID/version or cutoff was found."
        ),
        "terminal_status": POLICY_REVIEW_STATUS,
    }


def _nullable_agreement_summary(
    rater_a_event_count: int,
    rater_b_event_count: int,
    pairwise_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_relations = {
        relation: sum(
            item["raw_temporal_relation"] == relation
            for item in pairwise_candidates
        )
        for relation in ("EXACT_MATCH", "PARTIAL_MATCH", "ZERO_OVERLAP")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "agreement_context": AGREEMENT_CONTEXT,
        "rater_a_event_count": rater_a_event_count,
        "rater_b_event_count": rater_b_event_count,
        "pairwise_candidate_count": len(pairwise_candidates),
        "pairwise_raw_temporal_relations": raw_relations,
        "calculation_status": "NOT_CALCULATED_POLICY_REVIEW_REQUIRED",
        "policy_id": None,
        "policy_version": None,
        "matched_event_count": None,
        "exact_match_count": None,
        "partial_match_count": None,
        "zero_overlap_count": None,
        "rater_a_only_count": None,
        "rater_b_only_count": None,
        "mean_temporal_iou": None,
        "median_temporal_iou": None,
        "mean_onset_difference_ms": None,
        "mean_offset_difference_ms": None,
        "observed_agreement": None,
        "positive_agreement": None,
        "negative_agreement": None,
        "cohen_kappa": None,
        "kappa_interpretation": None,
        "terminal_status": POLICY_REVIEW_STATUS,
    }


def _input_validation_payload(
    package_dir: Path,
    manifest: dict[str, Any],
    context_checks: dict[str, Any],
    rater_validations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "split": manifest["split_name"],
        "rubric_id": manifest["rubric_id"],
        "rubric_version": manifest["rubric_version"],
        "context_checks": context_checks,
        "rater_inputs": rater_validations,
        "all_inputs_valid": all(
            item["valid"] for item in rater_validations.values()
        ),
        "input_files_read_only": True,
        "annotation_events_generated": False,
        "annotation_events_modified": False,
        "annotation_events_deleted": False,
        "terminal_status": POLICY_REVIEW_STATUS,
        "package_directory": (
            f"data/output/pilot_annotation/{package_dir.name}"
        ),
    }


def _validation_failure_payload(
    package_dir: Path,
    input_paths: dict[str, Path],
    errors: list[str],
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for rater_id, path in input_paths.items():
        inputs[rater_id] = {
            "path": path.relative_to(package_dir).as_posix(),
            "exists": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
            "valid": False,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "rater_inputs": inputs,
        "all_inputs_valid": False,
        "errors": errors,
        "input_files_read_only": True,
        "annotation_events_generated": False,
        "annotation_events_modified": False,
        "annotation_events_deleted": False,
        "terminal_status": VALIDATION_FAILED_STATUS,
        "package_directory": (
            f"data/output/pilot_annotation/{package_dir.name}"
        ),
    }


def adjudication_decision_template() -> dict[str, Any]:
    return {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "adjudicator_id": None,
        "decision": "REVIEW_PENDING",
        "completed_at": None,
        "resolved_events": [],
        "notes": None,
    }


def _disagreement_payload(
    rater_a_events: list[dict[str, Any]],
    rater_b_events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "classification_status": (
            "NOT_CLASSIFIED_AGREEMENT_POLICY_REVIEW_REQUIRED"
        ),
        "allowed_disagreement_types": list(DISAGREEMENT_TYPES),
        "disagreement_candidate_count": None,
        "candidates": [],
        "unresolved_rater_a_event_ids": [
            item["annotation_event_id"]
            for item in sorted(rater_a_events, key=_event_sort_key)
        ],
        "unresolved_rater_b_event_ids": [
            item["annotation_event_id"]
            for item in sorted(rater_b_events, key=_event_sort_key)
        ],
        "automatic_resolution_performed": False,
        "terminal_status": POLICY_REVIEW_STATUS,
    }


def _adjudication_packet(
    input_validation: dict[str, Any],
    pairwise_candidates: list[dict[str, Any]],
    disagreement: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "agreement_context": AGREEMENT_CONTEXT,
        "rater_input_hashes": {
            key: value["sha256"]
            for key, value in input_validation["rater_inputs"].items()
        },
        "pairwise_candidate_ids": [
            item["candidate_id"] for item in pairwise_candidates
        ],
        "disagreement_classification_status": disagreement[
            "classification_status"
        ],
        "review_requirements": [
            "Approve and version an event matching policy.",
            "Define or explicitly reject a matching cutoff.",
            "Confirm whether RATER_A and RATER_B represent different people.",
        ],
        "automatic_adjudication_performed": False,
        "final_annotation_generated": False,
        "resolved_events": [],
        "terminal_status": POLICY_REVIEW_STATUS,
    }


def _validation_report(
    *,
    input_validation: dict[str, Any],
    agreement_summary: dict[str, Any],
    pairwise_candidates: list[dict[str, Any]],
    disagreement: dict[str, Any],
    terminal_status: str,
) -> dict[str, Any]:
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "agreement_context": AGREEMENT_CONTEXT,
        "input_validation_passed": input_validation["all_inputs_valid"],
        "rater_a_event_count": agreement_summary["rater_a_event_count"],
        "rater_b_event_count": agreement_summary["rater_b_event_count"],
        "pairwise_candidate_count": len(pairwise_candidates),
        "agreement_calculated": False,
        "matching_performed": False,
        "disagreement_classification_performed": False,
        "adjudication_performed": False,
        "final_annotation_generated": False,
        "annotation_events_generated": False,
        "annotation_events_modified": False,
        "annotation_events_deleted": False,
        "scoring_performed": False,
        "threshold_generated": False,
        "psychological_inference_performed": False,
        "ml_training_performed": False,
        "dataset_frozen": False,
        "dependency_changed": False,
        "disagreement_candidate_count": disagreement[
            "disagreement_candidate_count"
        ],
        "outputs": list(OUTPUT_NAMES),
        "current_status": terminal_status,
    }
    _assert_no_forbidden_result_keys(report)
    ensure_finite(report)
    return report


def _markdown_report(report: dict[str, Any]) -> str:
    return (
        "# Face-Fit Stage 19 Validation Report\n\n"
        f"- Participant: `{report['participant_id']}`\n"
        f"- Session: `{report['session_id']}`\n"
        f"- Agreement context: `{report['agreement_context']}`\n"
        f"- Rater A events: `{report['rater_a_event_count']}`\n"
        f"- Rater B events: `{report['rater_b_event_count']}`\n"
        f"- Pairwise candidates: `{report['pairwise_candidate_count']}`\n"
        f"- Agreement calculated: `{str(report['agreement_calculated']).lower()}`\n"
        f"- Current status: `{report['current_status']}`\n\n"
        "Stage 13 provides Temporal IoU and agreement arithmetic, but its "
        "approval cutoff is explicitly undefined. No event matches were "
        "selected, no agreement statistics were calculated, and no "
        "adjudication or final Annotation was generated.\n"
    )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _assert_no_forbidden_result_keys(value)
    ensure_finite(value)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    lines: list[str] = []
    for value in values:
        _assert_no_forbidden_result_keys(value)
        ensure_finite(value)
        lines.append(json.dumps(value, ensure_ascii=False, allow_nan=False))
    path.write_text(
        ("\n".join(lines) + "\n") if lines else "",
        encoding="utf-8",
    )


def _publish_staged_directory(staged: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Stage 19 output already exists: {destination}")
    os.replace(staged, destination)


def build_stage19_package(
    *,
    package_dir: str | Path,
    metadata_path: str | Path,
    registry_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    package = Path(package_dir).resolve()
    metadata_source = Path(metadata_path).resolve()
    registry_source = Path(registry_path).resolve()
    destination = Path(output_dir).resolve()
    input_paths = {
        "RATER_A": package / "rater_a" / "annotation_events.json",
        "RATER_B": package / "rater_b" / "annotation_events.json",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=".stage19.", dir=destination.parent)
    )
    try:
        try:
            manifest = load_strict_json(
                package / "annotation_package_manifest.json"
            )
            metadata = load_strict_json(metadata_source)
            registry = registry_from_dict(load_strict_json(registry_source))
            context_checks = validate_package_context(manifest, metadata)
            submissions: dict[str, dict[str, Any]] = {}
            validations: dict[str, dict[str, Any]] = {}
            for rater_id in RATER_IDS:
                path = input_paths[rater_id]
                value = load_strict_json(path)
                details = validate_submission(
                    value,
                    expected_rater_id=rater_id,
                    answers=metadata["answers"],
                    registry=registry,
                )
                submissions[rater_id] = value
                validations[rater_id] = {
                    "path": path.relative_to(package).as_posix(),
                    "sha256": sha256_file(path),
                    "valid": True,
                    **details,
                }
            input_validation = _input_validation_payload(
                package,
                manifest,
                context_checks,
                validations,
            )
        except (OSError, KeyError, TypeError, ValueError) as exc:
            input_validation = _validation_failure_payload(
                package,
                input_paths,
                [str(exc)],
            )
            failure_summary = {
                "schema_version": SCHEMA_VERSION,
                "stage": STAGE,
                "participant_id": PARTICIPANT_ID,
                "session_id": SESSION_ID,
                "agreement_context": AGREEMENT_CONTEXT,
                "rater_a_event_count": None,
                "rater_b_event_count": None,
                "calculation_status": "NOT_CALCULATED_INPUT_VALIDATION_FAILED",
                "terminal_status": VALIDATION_FAILED_STATUS,
            }
            empty_disagreement = {
                "schema_version": SCHEMA_VERSION,
                "participant_id": PARTICIPANT_ID,
                "session_id": SESSION_ID,
                "classification_status": "NOT_CLASSIFIED_INPUT_VALIDATION_FAILED",
                "allowed_disagreement_types": list(DISAGREEMENT_TYPES),
                "disagreement_candidate_count": None,
                "candidates": [],
                "automatic_resolution_performed": False,
                "terminal_status": VALIDATION_FAILED_STATUS,
            }
            empty_packet = {
                "schema_version": SCHEMA_VERSION,
                "stage": STAGE,
                "participant_id": PARTICIPANT_ID,
                "session_id": SESSION_ID,
                "agreement_context": AGREEMENT_CONTEXT,
                "automatic_adjudication_performed": False,
                "final_annotation_generated": False,
                "resolved_events": [],
                "terminal_status": VALIDATION_FAILED_STATUS,
            }
            failure_report = {
                "schema_version": SCHEMA_VERSION,
                "stage": STAGE,
                "participant_id": PARTICIPANT_ID,
                "session_id": SESSION_ID,
                "agreement_context": AGREEMENT_CONTEXT,
                "input_validation_passed": False,
                "rater_a_event_count": None,
                "rater_b_event_count": None,
                "pairwise_candidate_count": 0,
                "agreement_calculated": False,
                "matching_performed": False,
                "disagreement_classification_performed": False,
                "adjudication_performed": False,
                "final_annotation_generated": False,
                "annotation_events_generated": False,
                "annotation_events_modified": False,
                "annotation_events_deleted": False,
                "scoring_performed": False,
                "threshold_generated": False,
                "psychological_inference_performed": False,
                "ml_training_performed": False,
                "dataset_frozen": False,
                "dependency_changed": False,
                "disagreement_candidate_count": None,
                "outputs": list(OUTPUT_NAMES),
                "errors": input_validation["errors"],
                "current_status": VALIDATION_FAILED_STATUS,
            }
            _write_json(staged / OUTPUT_NAMES[0], input_validation)
            _write_json(staged / OUTPUT_NAMES[1], agreement_policy_snapshot())
            _write_json(staged / OUTPUT_NAMES[2], failure_summary)
            _write_jsonl(staged / OUTPUT_NAMES[3], [])
            _write_json(staged / OUTPUT_NAMES[4], empty_disagreement)
            _write_json(staged / OUTPUT_NAMES[5], empty_packet)
            _write_json(
                staged / OUTPUT_NAMES[6],
                adjudication_decision_template(),
            )
            _write_json(staged / OUTPUT_NAMES[7], failure_report)
            (staged / OUTPUT_NAMES[8]).write_text(
                _markdown_report(failure_report),
                encoding="utf-8",
            )
            _publish_staged_directory(staged, destination)
            return failure_report

        rater_a_events = submissions["RATER_A"]["events"]
        rater_b_events = submissions["RATER_B"]["events"]
        pairwise = build_pairwise_candidates(
            rater_a_events,
            rater_b_events,
        )
        policy = agreement_policy_snapshot()
        summary = _nullable_agreement_summary(
            len(rater_a_events),
            len(rater_b_events),
            pairwise,
        )
        disagreement = _disagreement_payload(
            rater_a_events,
            rater_b_events,
        )
        packet = _adjudication_packet(
            input_validation,
            pairwise,
            disagreement,
        )
        report = _validation_report(
            input_validation=input_validation,
            agreement_summary=summary,
            pairwise_candidates=pairwise,
            disagreement=disagreement,
            terminal_status=POLICY_REVIEW_STATUS,
        )
        _write_json(staged / OUTPUT_NAMES[0], input_validation)
        _write_json(staged / OUTPUT_NAMES[1], policy)
        _write_json(staged / OUTPUT_NAMES[2], summary)
        _write_jsonl(staged / OUTPUT_NAMES[3], pairwise)
        _write_json(staged / OUTPUT_NAMES[4], disagreement)
        _write_json(staged / OUTPUT_NAMES[5], packet)
        _write_json(
            staged / OUTPUT_NAMES[6],
            adjudication_decision_template(),
        )
        _write_json(staged / OUTPUT_NAMES[7], report)
        (staged / OUTPUT_NAMES[8]).write_text(
            _markdown_report(report),
            encoding="utf-8",
        )
        _publish_staged_directory(staged, destination)
        return report
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
