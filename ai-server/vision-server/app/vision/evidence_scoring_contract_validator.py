"""Fixture-only Stage 11 contract smoke over protected Stage 10 aggregates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.core import config
from app.vision.data_quality_gate import evaluate_data_quality_gate
from app.vision.evidence_loaders import (
    EvidenceLoadError,
    EvidenceRegistryLoader,
)
from app.vision.evidence_models import SYNTHETIC_FIXTURE_NOTICE
from app.vision.evidence_registry import EvidenceExecutionMode
from app.vision.metric_registry import build_stage10_metric_registry
from app.vision.neutral_baseline_serializer import dumps_strict
from app.vision.scoring_models import MetricScoreStatus
from app.vision.scoring_strategy import TestFixtureBandScoringStrategy


SAFE_VIDEO_ID = "SPK001_FACE_SHOULDERS_MOTION_01_6cd4d7ac"
DEFAULT_STAGE10_INPUT = (
    config.OUTPUT_DIR
    / "interval_aggregation_validation"
    / SAFE_VIDEO_ID
    / "interval_aggregates.jsonl"
)
DEFAULT_FIXTURE_DIRECTORY = (
    config.VISION_SERVER_ROOT / "config" / "evidence" / "fixtures"
)
DEFAULT_OUTPUT_ROOT = (
    config.OUTPUT_DIR / "evidence_scoring_contract_validation"
)
PROTECTED_STAGE_ROOTS = (
    config.OUTPUT_DIR / "motion_validation",
    config.OUTPUT_DIR / "target_tracking_validation",
    config.OUTPUT_DIR / "head_pose_validation",
    config.OUTPUT_DIR / "posture_raw_validation",
    config.OUTPUT_DIR / "neutral_baseline_smoke",
    config.OUTPUT_DIR / "interval_aggregation_validation",
)


class EvidenceScoringContractValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def protected_stage_hashes(safe_id: str) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for root in PROTECTED_STAGE_ROOTS:
        directory = root / safe_id
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    result[path.resolve()] = sha256_file(path)
    return result


def load_strict_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise EvidenceScoringContractValidationError(
            "STAGE10_INPUT_NOT_FOUND",
            f"Stage 10 aggregate input not found: {path}",
        )
    rows: list[dict[str, Any]] = []
    try:
        for line_number, text in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not text.strip():
                raise ValueError(f"blank line at {line_number}")
            value = json.loads(
                text,
                parse_constant=lambda constant: (_ for _ in ()).throw(
                    ValueError(constant)
                ),
            )
            if not isinstance(value, dict):
                raise ValueError(f"non-object line at {line_number}")
            rows.append(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise EvidenceScoringContractValidationError(
            "INVALID_STAGE10_STRICT_JSONL",
            f"{path.name}: {exc}",
        ) from exc
    if not rows:
        raise EvidenceScoringContractValidationError(
            "EMPTY_STAGE10_AGGREGATES",
            f"No Stage 10 rows in {path}",
        )
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(dumps_strict(row))
            stream.write("\n")


def _markdown(report: dict[str, Any]) -> str:
    counts = report["smoke_counts"]
    return "\n".join(
        (
            "# Stage 11 evidence/scoring contract smoke report",
            "",
            f"- Technical judgment: `{report['technical_judgment']}`",
            f"- Stage 10 intervals: {counts['interval_count']}",
            f"- Fixture rules evaluated: {counts['rule_count']}",
            f"- Metric resolutions: {counts['resolved_metric_count']}",
            f"- Unavailable metrics: {counts['unavailable_metric_count']}",
            f"- Quality gate pass / fail: {counts['quality_gate_pass_count']} / "
            f"{counts['quality_gate_fail_count']}",
            f"- `SCORED_TEST_FIXTURE` results: "
            f"{counts['scored_test_fixture_count']}",
            "",
            "## Fixture-only warning",
            "",
            SYNTHETIC_FIXTURE_NOTICE,
            "",
            "이 결과는 모델·버전·단위·품질 게이트·provenance 연결을 검증하는 "
            "합성 fixture 결과이며 실제 면접 점수나 자세 평가가 아닙니다.",
            "",
            "No paper was searched or downloaded, no production threshold was "
            "approved, and no user-facing score, grade, or feedback was produced.",
            "",
        )
    )


class EvidenceScoringContractValidator:
    def validate(
        self,
        stage10_input: str | Path = DEFAULT_STAGE10_INPUT,
        *,
        fixture_directory: str | Path = DEFAULT_FIXTURE_DIRECTORY,
        output_root: str | Path = DEFAULT_OUTPUT_ROOT,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        source = Path(stage10_input).resolve()
        if source.name != "interval_aggregates.jsonl":
            raise EvidenceScoringContractValidationError(
                "INVALID_STAGE10_INPUT_NAME",
                "Stage 11 smoke requires interval_aggregates.jsonl",
            )
        safe_id = source.parent.name
        if not safe_id:
            raise EvidenceScoringContractValidationError(
                "INVALID_STAGE10_INPUT_DIRECTORY",
                "Cannot determine the protected video ID",
            )
        destination = Path(output_root).resolve() / safe_id
        if destination.exists() and not overwrite:
            raise EvidenceScoringContractValidationError(
                "OUTPUT_ALREADY_EXISTS",
                f"Output exists: {destination}",
            )
        source_hash = sha256_file(source)
        protected = protected_stage_hashes(safe_id)
        rows = load_strict_jsonl(source)
        metric_registry = build_stage10_metric_registry()
        try:
            registry = EvidenceRegistryLoader.load_directory(
                fixture_directory,
                metric_registry=metric_registry,
                execution_mode=(
                    EvidenceExecutionMode.TEST_FIXTURE_MODE.value
                ),
            )
        except EvidenceLoadError as exc:
            raise EvidenceScoringContractValidationError(
                exc.code,
                str(exc),
            ) from exc

        strategy = TestFixtureBandScoringStrategy()
        result_rows: list[dict[str, Any]] = []
        resolved_count = 0
        unavailable_count = 0
        gate_pass_count = 0
        gate_fail_count = 0
        rule_count = sum(
            len(profile.rules)
            for profile in registry.threshold_profiles.values()
        )
        for interval in rows:
            interval_id = interval.get("interval_id")
            if not isinstance(interval_id, str) or not interval_id:
                raise EvidenceScoringContractValidationError(
                    "STAGE10_SCHEMA_MISMATCH",
                    "Every Stage 10 aggregate requires interval_id",
                )
            try:
                metric_registry.validate_paths(interval)
            except (TypeError, ValueError) as exc:
                raise EvidenceScoringContractValidationError(
                    "STAGE10_METRIC_PATH_VALIDATION_FAILED",
                    f"{interval_id}: {exc}",
                ) from exc
            for threshold_key in sorted(registry.threshold_profiles):
                threshold_profile = registry.threshold_profiles[threshold_key]
                evidence_profile = registry.profiles[
                    (
                        threshold_profile.evidence_profile_id,
                        threshold_profile.evidence_profile_version,
                    )
                ]
                for threshold_rule in threshold_profile.rules:
                    metric = metric_registry.get(threshold_rule.metric_id)
                    resolution = metric_registry.resolve(
                        interval,
                        threshold_rule.metric_id,
                    )
                    if resolution.available:
                        resolved_count += 1
                    else:
                        unavailable_count += 1
                    gate = evaluate_data_quality_gate(
                        resolution,
                        threshold_rule,
                    )
                    if gate.passed:
                        gate_pass_count += 1
                    else:
                        gate_fail_count += 1
                    provenance = registry.build_provenance(
                        evidence_profile=evidence_profile,
                        threshold_profile=threshold_profile,
                        rule_id=threshold_rule.rule_id,
                        metric_id=threshold_rule.metric_id,
                    )
                    score_result = strategy.score(
                        resolution,
                        metric,
                        threshold_rule,
                        threshold_profile,
                        evidence_profile,
                        provenance,
                    )
                    result_rows.append(
                        {
                            "schema_version": "1.0",
                            "interval_id": interval_id,
                            "execution_mode": registry.execution_mode,
                            "fixture_notice": SYNTHETIC_FIXTURE_NOTICE,
                            "metric_resolution": resolution.to_dict(),
                            "data_quality_gate": gate.to_dict(),
                            "metric_score_result": score_result.to_dict(),
                        }
                    )

        scored_count = sum(
            item["metric_score_result"]["status"]
            == MetricScoreStatus.SCORED_TEST_FIXTURE.value
            for item in result_rows
        )
        status_counts: dict[str, int] = {}
        for item in result_rows:
            status = item["metric_score_result"]["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        all_fixture_scored = (
            bool(result_rows)
            and scored_count == len(result_rows)
            and gate_fail_count == 0
            and unavailable_count == 0
        )
        report = {
            "schema_version": "1.0",
            "validation_type": "evidence_scoring_contract_fixture_smoke",
            "status": "completed",
            "generated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "execution_mode": registry.execution_mode,
            "stage10_input": {
                "path": str(source),
                "sha256": source_hash,
            },
            "fixture_directory": str(Path(fixture_directory).resolve()),
            "registry_counts": {
                "source_count": len(registry.sources),
                "evidence_record_count": len(registry.records),
                "mapping_count": len(registry.mappings),
                "evidence_profile_count": len(registry.profiles),
                "threshold_profile_count": len(
                    registry.threshold_profiles
                ),
                "metric_definition_count": len(
                    metric_registry.definitions
                ),
                "conflict_count": len(registry.conflicts),
            },
            "smoke_counts": {
                "interval_count": len(rows),
                "rule_count": rule_count,
                "result_count": len(result_rows),
                "resolved_metric_count": resolved_count,
                "unavailable_metric_count": unavailable_count,
                "quality_gate_pass_count": gate_pass_count,
                "quality_gate_fail_count": gate_fail_count,
                "scored_test_fixture_count": scored_count,
                "status_counts": dict(sorted(status_counts.items())),
            },
            "all_results_are_scored_test_fixture": all_fixture_scored,
            "real_user_score_generated": False,
            "paper_search_or_download_performed": False,
            "production_threshold_approved": False,
            "technical_judgment": (
                "evidence_scoring_contract_smoke_completed_with_test_fixtures"
                if all_fixture_scored
                else "evidence_scoring_contract_smoke_completed_with_fixture_limitations"
            ),
            "fixture_notice": SYNTHETIC_FIXTURE_NOTICE,
            "limitations": [
                "All sources, evidence records, mappings, profiles, thresholds, "
                "and output values are synthetic TEST_FIXTURE data.",
                "Fixture output values are not real posture or interview scores.",
                "The smoke validates contracts and references, not scientific "
                "validity or user performance.",
                "Only existing Stage 10 aggregates are read; Stages 5-10 are "
                "not recomputed or modified.",
            ],
            "outputs": {
                "validation_report_json": "validation_report.json",
                "validation_report_markdown": "validation_report.md",
                "loaded_evidence_registry_json": (
                    "loaded_evidence_registry.json"
                ),
                "fixture_metric_score_results_jsonl": (
                    "fixture_metric_score_results.jsonl"
                ),
                "evidence_conflicts_json": "evidence_conflicts.json",
            },
        }

        output_root_path = Path(output_root).resolve()
        output_root_path.mkdir(parents=True, exist_ok=True)
        staged: Path | None = Path(
            tempfile.mkdtemp(prefix=f".{safe_id}.", dir=output_root_path)
        )
        try:
            (staged / "loaded_evidence_registry.json").write_text(
                dumps_strict(registry.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            _write_jsonl(
                staged / "fixture_metric_score_results.jsonl",
                result_rows,
            )
            (staged / "evidence_conflicts.json").write_text(
                dumps_strict(
                    {
                        "schema_version": "1.0",
                        "auto_resolution_performed": False,
                        "conflicts": [
                            item.to_dict() for item in registry.conflicts
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (staged / "validation_report.json").write_text(
                dumps_strict(report, indent=2) + "\n",
                encoding="utf-8",
            )
            (staged / "validation_report.md").write_text(
                _markdown(report),
                encoding="utf-8",
            )
            if not source.is_file() or sha256_file(source) != source_hash:
                raise EvidenceScoringContractValidationError(
                    "PROTECTED_STAGE10_INPUT_CHANGED",
                    "Stage 10 aggregate input changed during validation",
                )
            if any(
                not path.is_file() or sha256_file(path) != digest
                for path, digest in protected.items()
            ):
                raise EvidenceScoringContractValidationError(
                    "PROTECTED_STAGE_OUTPUT_CHANGED",
                    "A protected Stage 5-10 output changed during validation",
                )
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.old")
                if backup.exists():
                    raise EvidenceScoringContractValidationError(
                        "STALE_OUTPUT_BACKUP",
                        f"Refusing replacement while backup exists: {backup}",
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
