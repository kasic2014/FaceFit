"""Build isolated Stage 18 Rater A/B packages without annotation events."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.pilot_annotation_package import (
    BLIND_FLAG_NAMES,
    PARTICIPANT_ID,
    RATER_IDS,
    RUBRIC_ID,
    RUBRIC_VERSION,
    SESSION_ID,
    annotation_readiness_status,
    build_empty_template,
    forbidden_concept_names,
    registry_from_dict,
    validate_rater_submission,
)
from app.vision.pilot_video_intake import (
    assert_no_forbidden_semantics,
    load_strict_json,
    sha256_file,
    write_strict_json,
)


VIDEO_RELATIVE_PATH = (
    "../../../../pilot/incoming/PTC_000001_SES_000001.mp4"
)


def _instructions(rater_id: str) -> str:
    return f"""# Independent Annotation Instructions — {rater_id}

Annotate only directly visible behavior in the four Answer intervals. The
Baseline interval is excluded. Use the shared video through the relative path
in `answer_intervals.json`; do not alter or copy the source video.

Start from `annotation_events.template.json` and save the completed result as
`annotation_events.json` in this directory. Keep your work independent. Do not
open, request, or reproduce another rater's result.

Each event uses `[start, end)`: start is included and end is excluded. Both
timestamps must fall inside the referenced Answer interval. Use only labels
and directions defined in `annotation_labels.json`. Directionless labels must
use `null`. Keep `rater_confidence` as `null`; do not enter angles, ratings,
grades, model-derived values, inferred internal states, diagnoses, or hiring
outcomes.

Set `completed_at` to a timezone-aware ISO-8601 timestamp only after the
annotation is complete. The template intentionally contains an empty `events`
array and does not contain suggested observations.
"""


def _validation_for_missing_result(rater_id: str, result: Path) -> dict:
    return {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "rater_id": rater_id,
        "expected_result_file": str(result.name),
        "result_file_exists": False,
        "validation_status": "NOT_SUBMITTED",
        "valid": None,
        "event_count": None,
        "errors": [],
        "warnings": [],
    }


def _validate_or_missing(
    rater_id: str,
    result: Path,
    *,
    answers: list[dict],
    registry,
) -> dict:
    if not result.exists():
        return _validation_for_missing_result(rater_id, result)
    try:
        value = load_strict_json(result)
        detail = validate_rater_submission(
            value,
            expected_rater_id=rater_id,
            answers=answers,
            registry=registry,
        )
    except (ValueError, OSError) as exc:
        return {
            "participant_id": PARTICIPANT_ID,
            "session_id": SESSION_ID,
            "rater_id": rater_id,
            "expected_result_file": result.name,
            "result_file_exists": True,
            "validation_status": "FAILED",
            "valid": False,
            "event_count": None,
            "errors": [str(exc)],
            "warnings": [],
        }
    return {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "rater_id": rater_id,
        "expected_result_file": result.name,
        "result_file_exists": True,
        "result_sha256": sha256_file(result),
        "validation_status": "PASSED",
        "valid": True,
        "event_count": detail["event_count"],
        "errors": [],
        "warnings": [],
    }


def _markdown(report: dict) -> str:
    return (
        "# Face-Fit Stage 18 Validation Report\n\n"
        f"- Participant: `{report['participant_id']}`\n"
        f"- Session: `{report['session_id']}`\n"
        f"- Rubric: `{report['rubric_id']} {report['rubric_version']}`\n"
        f"- Included labels: `{report['label_count']}`\n"
        f"- Included Answer intervals: `{report['answer_count']}`\n"
        f"- Rater A result: `{report['rater_results']['RATER_A']}`\n"
        f"- Rater B result: `{report['rater_results']['RATER_B']}`\n"
        f"- Current status: `{report['current_status']}`\n\n"
        "The packages contain no suggested Annotation Events or model-derived "
        "measurements. Agreement and Kappa were not calculated. The dataset "
        "remains unfrozen.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage17-manifest", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"Stage 18 output already exists: {output}")

    stage17 = load_strict_json(args.stage17_manifest.resolve())
    metadata = load_strict_json(args.metadata.resolve())
    registry_source = load_strict_json(args.registry.resolve())
    if stage17["final_status"] != "pilot_video_annotation_ready":
        raise ValueError("Stage 17 annotation-ready status is required")
    if (
        stage17["participant_id"] != PARTICIPANT_ID
        or stage17["session_id"] != SESSION_ID
        or stage17["split_name"] != "DEVELOPMENT"
    ):
        raise ValueError("Stage 17 participant/session/split mismatch")
    registry = registry_from_dict(registry_source)
    rubric = registry.get_rubric(RUBRIC_ID, RUBRIC_VERSION)
    labels = [
        registry.get_label(label_id).to_dict()
        for label_id in rubric.label_ids
    ]
    answers = metadata["answers"]
    baseline = metadata["baseline_interval"]
    if [item["answer_id"] for item in answers] != [
        "ANS_000001", "ANS_000002", "ANS_000003", "ANS_000004"
    ]:
        raise ValueError("expected four ordered pilot Answer intervals")

    output.mkdir(parents=True)
    package_entries = []
    validations = {}
    for rater_id, directory_name in zip(RATER_IDS, ("rater_a", "rater_b")):
        rater_dir = output / directory_name
        rater_dir.mkdir()
        instructions = rater_dir / "annotation_instructions.md"
        intervals_path = rater_dir / "answer_intervals.json"
        labels_path = rater_dir / "annotation_labels.json"
        template_path = rater_dir / "annotation_events.template.json"
        instructions.write_text(_instructions(rater_id), encoding="utf-8")
        write_strict_json(intervals_path, {
            "schema_version": "1.0.0",
            "participant_id": PARTICIPANT_ID,
            "session_id": SESSION_ID,
            "rater_id": rater_id,
            "video_relative_path": VIDEO_RELATIVE_PATH,
            "interval_rule": "[start, end)",
            "baseline_excluded": True,
            "excluded_baseline_interval": baseline,
            "answer_intervals": answers,
        })
        write_strict_json(labels_path, {
            "schema_version": "1.0.0",
            "rater_id": rater_id,
            "rubric_id": RUBRIC_ID,
            "rubric_version": RUBRIC_VERSION,
            "observable_only": True,
            "interval_end_exclusive": True,
            "inference_prohibited": True,
            "labels": labels,
            "prohibited_concepts": forbidden_concept_names(),
        })
        template = build_empty_template(rater_id)
        validate_rater_submission(
            template,
            expected_rater_id=rater_id,
            answers=answers,
            registry=registry,
            require_completed=False,
        )
        write_strict_json(template_path, template)
        files = (instructions, intervals_path, labels_path, template_path)
        package_entries.append({
            "rater_id": rater_id,
            "directory": directory_name,
            "video_relative_path": VIDEO_RELATIVE_PATH,
            "expected_result_file": f"{directory_name}/annotation_events.json",
            "result_file_included": False,
            "files": [
                {
                    "path": f"{directory_name}/{path.name}",
                    "sha256": sha256_file(path),
                }
                for path in files
            ],
        })
        result_path = rater_dir / "annotation_events.json"
        validations[rater_id] = _validate_or_missing(
            rater_id,
            result_path,
            answers=answers,
            registry=registry,
        )

    cross_rater_warnings: list[str] = []
    a_result = output / "rater_a" / "annotation_events.json"
    b_result = output / "rater_b" / "annotation_events.json"
    if a_result.exists() and b_result.exists():
        if sha256_file(a_result) == sha256_file(b_result):
            cross_rater_warnings.append("IDENTICAL_RESULT_FILE_HASH")
        else:
            a_events = load_strict_json(a_result)["events"]
            b_events = load_strict_json(b_result)["events"]
            if a_events == b_events:
                cross_rater_warnings.append("IDENTICAL_EVENT_CONTENT")
    current_status = annotation_readiness_status(
        validations["RATER_A"], validations["RATER_B"]
    )
    manifest = {
        "schema_version": "1.0.0",
        "stage": 18,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "split_name": "DEVELOPMENT",
        "video": {
            "filename": metadata["video_file"],
            "sha256": stage17["video"]["sha256"],
        },
        "rubric_id": RUBRIC_ID,
        "rubric_version": RUBRIC_VERSION,
        "label_count": len(labels),
        "answer_count": len(answers),
        "baseline_annotation_excluded": True,
        "packages": package_entries,
        "independence_contract": {
            "rater_ids_distinct": True,
            "same_video_and_rubric": True,
            "separate_result_files_required": True,
            "all_blind_flags_required": list(BLIND_FLAG_NAMES),
            "result_files_prepopulated": False,
        },
        "source_references": {
            "stage17_manifest_sha256": sha256_file(
                args.stage17_manifest.resolve()
            ),
            "registry_sha256": sha256_file(args.registry.resolve()),
            "metadata_sha256": sha256_file(args.metadata.resolve()),
        },
    }
    status_value = {
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "rater_a_result_file_exists":
            validations["RATER_A"]["result_file_exists"],
        "rater_b_result_file_exists":
            validations["RATER_B"]["result_file_exists"],
        "current_status": current_status,
        "cross_rater_warnings": cross_rater_warnings,
        "agreement_calculated": False,
        "kappa_calculated": False,
        "dataset_frozen": False,
    }
    report = {
        "schema_version": "1.0.0",
        "stage": 18,
        "participant_id": PARTICIPANT_ID,
        "session_id": SESSION_ID,
        "rubric_id": RUBRIC_ID,
        "rubric_version": RUBRIC_VERSION,
        "label_count": len(labels),
        "answer_count": len(answers),
        "rater_packages_separate": True,
        "blind_contract_valid": True,
        "template_event_count": {
            "RATER_A": 0,
            "RATER_B": 0,
        },
        "rater_results": {
            "RATER_A": validations["RATER_A"]["validation_status"],
            "RATER_B": validations["RATER_B"]["validation_status"],
        },
        "current_status": current_status,
        "actual_annotation_events_generated": False,
        "model_derived_labels_generated": False,
        "agreement_calculated": False,
        "kappa_calculated": False,
        "evaluative_value_produced": False,
        "evaluation_boundary_produced": False,
        "psychological_inference_produced": False,
        "ml_training_performed": False,
        "dataset_frozen": False,
        "dependency_changed": False,
    }
    for value in (
        manifest,
        validations["RATER_A"],
        validations["RATER_B"],
        status_value,
        report,
    ):
        assert_no_forbidden_semantics(value)
    write_strict_json(output / "annotation_package_manifest.json", manifest)
    write_strict_json(
        output / "rater_a_validation.json", validations["RATER_A"]
    )
    write_strict_json(
        output / "rater_b_validation.json", validations["RATER_B"]
    )
    write_strict_json(
        output / "annotation_readiness_status.json", status_value
    )
    write_strict_json(output / "validation_report.json", report)
    (output / "validation_report.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
