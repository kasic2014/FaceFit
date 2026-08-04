"""Validate Stage 32 evidence research artifacts and optional real adapter smoke checks."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AI_SERVER = ROOT.parent
REPOSITORY = AI_SERVER.parent
EXPECTED_STATUS = "scoring_gap_evidence_research_ready_with_access_limitations"
EXPECTED_GAP_IDS = {
    "KOREAN_SPEECH_RATE", "KOREAN_ARTICULATION_RATE", "KOREAN_PAUSE_DURATION",
    "KOREAN_FILLER_VALIDATION", "WEBCAM_HEAD_POSE_BEHAVIOR", "HEAD_POSE_VS_EYE_GAZE",
    "SEATED_SHOULDER_POSTURE", "SHOULDER_CENTER_MOVEMENT", "MICROPHONE_LOUDNESS_NORMALIZATION",
    "HUMAN_BEHAVIOR_RUBRIC", "INTER_RATER_RELIABILITY", "MULTI_SESSION_DISTRIBUTION",
    "THRESHOLD_SENSITIVITY", "AXIS_WEIGHT_VALIDATION", "BIAS_AND_FAIRNESS_VALIDATION",
    "VALIDATION_DESIGN",
}
BLOCKED_IDS = {"GAP_GAZE_001", "GAP_BODY_003"}
FORBIDDEN_TRACKED_SUFFIXES = {".pdf", ".csv", ".tsv", ".tgz", ".zip", ".html", ".wav", ".mp3", ".mp4", ".webm"}
ABSOLUTE_PATH_RE = re.compile(r"(?:\b[A-Za-z]:[\\/]|/(?:Users|home|tmp)/)")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def metric_ids() -> set[str]:
    return {row["metricId"] for row in load_json(ROOT / "registries" / "metric-inventory-v1.json")["metrics"]}


def stage32_records() -> list[dict[str, Any]]:
    return [load_json(path) for path in sorted((ROOT / "evidence" / "records").glob("GAP_*.json"))]


def _schema_shape_errors(record: dict[str, Any], required: set[str], allowed: set[str]) -> list[str]:
    errors: list[str] = []
    evidence_id = record.get("evidenceId", "UNKNOWN")
    if set(record) != required or set(record) - allowed:
        errors.append(f"{evidence_id}: evidence record fields do not match the common contract")
    if not re.fullmatch(r"GAP_(?:DATA|SPEECH|FILLER|RUBRIC|GAZE|BODY|AUDIO|METHOD)_\d{3}", str(evidence_id)):
        errors.append(f"{evidence_id}: invalid Stage 32 evidence id")
    if record.get("thresholdExists") is not False or record.get("thresholdValue") is not None:
        errors.append(f"{evidence_id}: threshold fields must remain unavailable")
    assessment = record.get("thresholdAssessment", {})
    if assessment.get("behaviorThresholdReported") is not False or assessment.get("productionThresholdUsable") is not False:
        errors.append(f"{evidence_id}: threshold assessment is unsafe")
    if "THRESHOLD_CANDIDATE" in record.get("intendedUses", []):
        errors.append(f"{evidence_id}: threshold candidate use is prohibited")
    if not SHA_RE.fullmatch(str(record.get("fileSha256", ""))):
        errors.append(f"{evidence_id}: invalid material hash")
    for mapping in record.get("faceFitMappings", []):
        if mapping.get("numericThresholdSupported") is not False:
            errors.append(f"{evidence_id}: mapping claims numeric threshold support")
    return errors


def validate_artifacts() -> dict[str, Any]:
    errors: list[str] = []
    catalog = load_json(ROOT / "evidence" / "source-catalog-stage32-v1.json")
    records = stage32_records()
    matrix = load_json(ROOT / "mappings" / "metric-evidence-matrix-v1.json")
    readiness = load_json(ROOT / "mappings" / "threshold-readiness-v1.json")
    gaps = load_json(ROOT / "mappings" / "gap-source-mapping-v1.json")
    rubric = load_json(ROOT / "docs" / "human-behavior-rubric-draft-v1.json")
    pilot = load_json(ROOT / "docs" / "pilot-data-collection-spec-v1.json")
    schema = load_json(ROOT / "contracts" / "evidence-record.schema.json")
    rubric_schema = load_json(ROOT / "contracts" / "human-behavior-rubric.schema.json")
    inventory_ids = metric_ids()

    source_ids = [row["evidenceId"] for row in catalog.get("sources", [])]
    record_ids = [row["evidenceId"] for row in records]
    if catalog.get("sourceCount") != 18 or len(source_ids) != 18 or len(set(source_ids)) != 18:
        errors.append("Stage 32 source catalog must contain exactly 18 unique sources")
    if set(source_ids) != set(record_ids) or len(records) != 18:
        errors.append("Stage 32 catalog and evidence records must have the same exact 18 ids")
    if any(row.get("productionApproved") is not False for row in [catalog, matrix, readiness, gaps, rubric, pilot]):
        errors.append("Every Stage 32 artifact must fail closed for production")
    for source in catalog.get("sources", []):
        if not SHA_RE.fullmatch(str(source.get("fileSha256", ""))) or int(source.get("fileSizeBytes", 0)) <= 0:
            errors.append(f"{source.get('evidenceId')}: invalid catalog integrity metadata")
        if source.get("evidenceId") in BLOCKED_IDS:
            if source.get("fileIntegrity") != "HTML_CHALLENGE_NOT_PDF" or source.get("reviewStatus") != "REVIEW_BLOCKED":
                errors.append(f"{source.get('evidenceId')}: access challenge must be explicit")
        details = source.get("reviewDetails", {})
        required_review_fields = {
            "sourceId", "sourceType", "localFileName", "accessLevel", "reviewDepth",
            "reviewStatus", "licenseSummary", "relatedGaps", "relatedMetrics",
            "evidenceRelationship", "supportedClaims", "unsupportedClaims",
            "measurementDefinition", "population", "taskContext",
            "equipmentOrCaptureSetting", "annotationMethod", "raterCount",
            "interRaterMethod", "reportedLimitations", "faceFitApplicability",
            "faceFitNonApplicability", "extractionLocations", "thresholdUse",
            "productionApproved",
        }
        if set(details) != required_review_fields:
            errors.append(f"{source.get('evidenceId')}: material review fields are incomplete")
        if details.get("sourceId") != source.get("evidenceId"):
            errors.append(f"{source.get('evidenceId')}: review identity mismatch")
        if details.get("thresholdUse") != "PROHIBITED" or details.get("productionApproved") is not False:
            errors.append(f"{source.get('evidenceId')}: material review does not fail closed")
        local_name = str(details.get("localFileName", ""))
        if not local_name or Path(local_name).name != local_name:
            errors.append(f"{source.get('evidenceId')}: localFileName must be a basename only")
    required, allowed = set(schema["required"]), set(schema["properties"])
    for record in records:
        errors.extend(_schema_shape_errors(record, required, allowed))
        if record["evidenceId"] in BLOCKED_IDS and record["access"]["reviewDepth"] != "REVIEW_BLOCKED":
            errors.append(f"{record['evidenceId']}: blocked material claims review")

    for artifact_name, artifact in (("matrix", matrix), ("readiness", readiness)):
        rows = artifact.get("metrics", [])
        ids = [row.get("metricId") for row in rows]
        if artifact.get("metricCount") != 18 or set(ids) != inventory_ids or len(ids) != len(set(ids)):
            errors.append(f"{artifact_name}: must cover the exact 18 registered metrics")
        if artifact.get("scoringAvailable") is not False or artifact.get("score") is not None:
            errors.append(f"{artifact_name}: scoring must remain unavailable")
    for row in matrix.get("metrics", []):
        if row.get("stage31Readiness") != row.get("stage32Readiness") or row.get("readinessChanged") is not False:
            errors.append(f"{row.get('metricId')}: Stage 32 must not promote readiness")
        if row.get("productionReadiness") != "NOT_READY":
            errors.append(f"{row.get('metricId')}: production readiness must remain blocked")
        for mapping in row.get("evidenceMappings", []):
            if mapping.get("numericThresholdSupported") is not False:
                errors.append(f"{row.get('metricId')}: numeric mapping support is prohibited")
    for row in readiness.get("metrics", []):
        review = row.get("stage32Review", {})
        if review.get("priorReadiness") != review.get("currentReadiness") or review.get("changed") is not False:
            errors.append(f"{row.get('metricId')}: threshold readiness was promoted")
        if review.get("thresholdExists") is not False or review.get("thresholdValue") is not None:
            errors.append(f"{row.get('metricId')}: threshold value must be null")

    gap_rows = gaps.get("gaps", [])
    gap_ids = [row.get("gapId") for row in gap_rows]
    if gaps.get("gapCount") != 16 or set(gap_ids) != EXPECTED_GAP_IDS or len(gap_ids) != len(set(gap_ids)):
        errors.append("Gap mapping must contain the exact 16 Stage 32 gaps")
    if gaps.get("resolvedGapCount") != 0:
        errors.append("No Stage 32 gap may be marked resolved")
    for row in gap_rows:
        required_gap_fields = {
            "gapId", "evidenceState", "evidenceIds", "affectedMetricIds",
            "productionBlocking", "resolved", "thresholdSupported",
            "stage32Conclusion", "description", "severity", "blockingProduction",
            "existingSources", "newStage32Sources", "evidenceCoverage",
            "remainingProblem", "nextRequiredAction", "ownerType", "status",
        }
        if set(row) != required_gap_fields:
            errors.append(f"{row.get('gapId')}: gap review fields are incomplete")
        if row.get("productionBlocking") is not True or row.get("resolved") is not False or row.get("thresholdSupported") is not False:
            errors.append(f"{row.get('gapId')}: gap must remain production-blocking")
        if row.get("blockingProduction") is not True or row.get("status") != row.get("evidenceState"):
            errors.append(f"{row.get('gapId')}: gap status is inconsistent")
        if row.get("newStage32Sources") != row.get("evidenceIds"):
            errors.append(f"{row.get('gapId')}: Stage 32 source mapping is inconsistent")
        if not set(row.get("affectedMetricIds", [])) <= inventory_ids:
            errors.append(f"{row.get('gapId')}: unknown affected metric")

    expected_levels = {"LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4"}
    item_ids: set[str] = set()
    for item in rubric.get("items", []):
        if item.get("itemId") in item_ids:
            errors.append(f"duplicate rubric item: {item.get('itemId')}")
        item_ids.add(item.get("itemId"))
        if set(item.get("anchors", {})) != expected_levels:
            errors.append(f"{item.get('itemId')}: rubric anchors are incomplete")
        if not set(item.get("metricLinks", [])) <= inventory_ids:
            errors.append(f"{item.get('itemId')}: rubric links an unknown metric")
        if item.get("productionUse") != "PROHIBITED_UNTIL_VALIDATED":
            errors.append(f"{item.get('itemId')}: rubric production use is unsafe")
    if rubric.get("scoreGenerationAllowed") is not False or rubric.get("pilotValidationRequired") is not True:
        errors.append("Rubric must remain research-only")
    if set(rubric.get("prohibitedInferences", [])) != {
        "PERSONALITY", "EMOTION", "ANXIETY", "CONFIDENCE", "DECEPTION",
        "GENDER", "HEALTH", "JOB_FIT", "HIRING_RECOMMENDATION",
    }:
        errors.append("Rubric prohibited-inference list is incomplete")
    if rubric_schema.get("properties", {}).get("productionApproved", {}).get("const") is not False:
        errors.append("Rubric schema does not fail closed")
    if pilot.get("status") != "DESIGN_ONLY_NOT_AUTHORIZED_FOR_COLLECTION":
        errors.append("Pilot spec must not authorize collection")
    if pilot.get("sampleDesign", {}).get("targetSampleSize") != "TBD_BY_POWER_ANALYSIS":
        errors.append("Pilot sample size must remain TBD")
    if pilot.get("sampleDesign", {}).get("minimumRaters") != "MINIMUM_NOT_YET_APPROVED":
        errors.append("Pilot rater count must remain TBD")
    for field in ("researchQuestions", "eligibility", "answerIntervalDefinition", "disagreementHandling", "approvalProcess", "productionPromotionConditions", "stopConditions"):
        if not pilot.get(field):
            errors.append(f"Pilot spec is missing {field}")
    if any(row.get("status") != "NOT_MET" for row in pilot.get("decisionGates", [])):
        errors.append("Pilot decision gates must remain unmet")

    tracked = subprocess.run(
        ["git", "ls-files", "--", "ai-server/scoring"],
        cwd=REPOSITORY, check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    forbidden_tracked = [name for name in tracked if Path(name).suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES or "/private/" in name.replace("\\", "/")]
    if forbidden_tracked:
        errors.append("Private or source material is tracked: " + ", ".join(forbidden_tracked))
    for path in ROOT.rglob("*"):
        if not path.is_file() or "private" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in {".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="strict")
        if ABSOLUTE_PATH_RE.search(text):
            errors.append(f"{path.relative_to(ROOT)}: absolute local path found")
        if '"participantId"' in text or '"transcriptText"' in text or '"raterId"' in text:
            errors.append(f"{path.relative_to(ROOT)}: prohibited raw-data field found")

    state_counts = Counter(row["evidenceState"] for row in gap_rows)
    return {
        "status": EXPECTED_STATUS if not errors else "stage32_validation_failed",
        "sourceCount": len(source_ids),
        "recordCount": len(records),
        "metricCount": len(matrix.get("metrics", [])),
        "gapCount": len(gap_rows),
        "rubricItemCount": len(rubric.get("items", [])),
        "accessBlockedCount": sum(row.get("reviewStatus") == "REVIEW_BLOCKED" for row in catalog.get("sources", [])),
        "gapStateCounts": dict(sorted(state_counts.items())),
        "productionApproved": False,
        "scoringAvailable": False,
        "scoreStatus": "NOT_AVAILABLE",
        "score": None,
        "reason": "THRESHOLD_EVIDENCE_NOT_APPROVED",
        "errors": errors,
    }


def real_adapter_smoke(
    speech_dir: Path | None = None,
    vision_file: Path | None = None,
) -> dict[str, Any]:
    sys.path.insert(0, str(AI_SERVER))
    from scoring.adapters.speech_metric_adapter import adapt_speech_answer
    from scoring.adapters.vision_metric_adapter import adapt_vision_answer
    from scoring.engine.quality_gate import evaluate_quality
    from scoring.engine.scoring_service import disabled_result

    inventory = load_json(ROOT / "registries" / "metric-inventory-v1.json")
    rules = {row["metricId"]: row for row in inventory["metrics"]}
    if speech_dir is None:
        speech_dir = AI_SERVER / "analysis-server" / "data" / "output" / "speech_characteristics" / "SES_000001" / "answers"
    if vision_file is None:
        vision_file = AI_SERVER / "vision-server" / "data" / "output" / "pilot_video_intake_validation" / "SES_000001" / "stage10_intervals" / "PTC_000001_SES_000001_a54511b0" / "interval_aggregates.jsonl"
    speech_files = sorted(speech_dir.glob("ANS_*.json"))
    if not speech_files:
        raise FileNotFoundError("No real speech answer artifacts found")
    speech_rows: list[dict[str, Any]] = []
    for path in speech_files:
        speech_rows.extend(adapt_speech_answer("SES_000001", load_json(path), inventory))
    vision_rows: list[dict[str, Any]] = []
    for line in vision_file.read_text(encoding="utf-8").splitlines():
        aggregate = json.loads(line)
        if aggregate.get("interval_type") != "ANSWER":
            continue
        match = re.fullmatch(r"INT_ANSWER_(\d{3})", aggregate.get("interval_id", ""))
        if not match:
            raise ValueError("Unexpected Vision answer interval id")
        answer_id = f"ANS_{int(match.group(1)):06d}"
        vision_rows.extend(adapt_vision_answer("SES_000001", answer_id, aggregate, inventory))
    if len(speech_rows) != len(speech_files) * 10:
        raise AssertionError("Speech adapter did not emit the exact ten analysis metrics per answer")
    if not vision_rows or len(vision_rows) % 6:
        raise AssertionError("Vision adapter did not emit six behavior metrics per answer")
    outcomes = []
    for row in speech_rows + vision_rows:
        outcome = evaluate_quality(row["quality"], rules[row["metricId"]].get("qualityGate", {}))
        if outcome["qualityStatus"] not in {"PASSED", "INSUFFICIENT_DATA", "LOW_AVAILABILITY", "HIGH_MISSING_RATIO", "ANSWER_TOO_SHORT", "INSUFFICIENT_WORDS", "INSUFFICIENT_VOICED_FRAMES", "INVALID_TIMESTAMP"}:
            raise AssertionError("Unexpected quality-gate status")
        if row.get("score") is not None:
            raise AssertionError("Adapter smoke must not produce scores")
        outcomes.append(outcome)
    disabled = disabled_result("SES_000001")
    if disabled.get("scoringAvailable") is not False or disabled.get("score") is not None:
        raise AssertionError("Scoring did not fail closed")
    return {
        "speechAnswerCount": len(speech_files),
        "speechMetricRowCount": len(speech_rows),
        "visionAnswerCount": len(vision_rows) // 6,
        "visionMetricRowCount": len(vision_rows),
        "qualityGateAppliedCount": len(outcomes),
        "qualityGatePassedCount": sum(row["passed"] for row in outcomes),
        "qualityGateFailedCount": sum(not row["passed"] for row in outcomes),
        "productionApproved": False,
        "scoringAvailable": False,
        "scoreStatus": disabled["scoreStatus"],
        "score": None,
        "reason": disabled["reason"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-adapter-smoke", action="store_true")
    args = parser.parse_args()
    report = validate_artifacts()
    if args.real_adapter_smoke and not report["errors"]:
        try:
            report["realAdapterSmoke"] = real_adapter_smoke()
        except Exception as exc:
            report["errors"].append(f"real adapter smoke failed: {type(exc).__name__}: {exc}")
            report["status"] = "stage32_validation_failed"
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
