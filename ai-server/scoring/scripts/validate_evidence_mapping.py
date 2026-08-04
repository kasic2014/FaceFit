"""Validate Stage 31 evidence records, mappings, readiness, gaps, and repository safety."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]

SOURCE_IDS = {
    *(f"SRC_INT_{number:03d}" for number in range(1, 8)),
    *(f"SRC_PUB_{number:03d}" for number in range(1, 5)),
    *(f"SRC_HEAD_{number:03d}" for number in range(1, 6)),
    *(f"SRC_POSE_{number:03d}" for number in range(1, 5)),
}
ACCESS_LEVELS = {
    "FULL_TEXT_PDF", "AUTHOR_ACCEPTED_MANUSCRIPT", "OFFICIAL_HTML_FULL_TEXT",
    "OFFICIAL_ABSTRACT_ONLY", "METADATA_ONLY", "ACCESS_BLOCKED",
}
REVIEW_DEPTHS = {"FULL_TEXT_REVIEWED", "ABSTRACT_REVIEWED", "METADATA_REVIEWED", "REVIEW_BLOCKED"}
RELATIONS = {"DIRECT", "PROXY", "UNIT_CONVERSION", "DERIVED", "NOT_APPLICABLE"}
USES = {
    "CONTEXT", "AXIS_SELECTION", "METRIC_DEFINITION", "METRIC_DIRECTION", "QUALITY_GATE",
    "MEASUREMENT_LIMITATION", "HUMAN_RUBRIC", "VALIDATION_DESIGN", "FAIRNESS_LIMITATION",
    "THRESHOLD_CANDIDATE",
}
READINESS = {
    "NOT_READY", "DIRECTION_ONLY", "METRIC_DEFINITION_ONLY", "QUALITY_GATE_ONLY",
    "MEASUREMENT_LIMITATION_ONLY", "EXCLUDED_FROM_SCORING",
}
MATRIX_DIRECTION = {"NOT_READY", "CANDIDATE", "NOT_APPLICABLE"}
REQUIRED_GAPS = {
    "KOREAN_SPEECH_RATE", "KOREAN_ARTICULATION_RATE", "KOREAN_PAUSE_DURATION",
    "KOREAN_FILLER_VALIDATION", "WEBCAM_HEAD_POSE_BEHAVIOR", "HEAD_POSE_VS_EYE_GAZE",
    "SEATED_SHOULDER_POSTURE", "SHOULDER_CENTER_MOVEMENT", "MICROPHONE_LOUDNESS_NORMALIZATION",
    "HUMAN_BEHAVIOR_RUBRIC", "INTER_RATER_RELIABILITY", "MULTI_SESSION_DISTRIBUTION",
    "THRESHOLD_SENSITIVITY", "AXIS_WEIGHT_VALIDATION", "BIAS_AND_FAIRNESS_VALIDATION",
}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
URL_RE = re.compile(r"^https://", re.IGNORECASE)
ABSOLUTE_PATH_RE = re.compile(r"(?:\b[A-Za-z]:[\\/]|/(?:Users|home|tmp)/)")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def inventory_metric_ids() -> set[str]:
    inventory = load_json(ROOT / "registries" / "metric-inventory-v1.json")
    return {row["metricId"] for row in inventory["metrics"]}


def load_records() -> list[dict[str, Any]]:
    return [load_json(path) for path in sorted((ROOT / "evidence" / "records").glob("SRC_*.json"))]


def _walk(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    access = Counter(record["access"]["accessLevel"] for record in records)
    reviews = Counter(record["access"]["reviewDepth"] for record in records)
    contexts = Counter(record["study"]["context"] for record in records)
    uses = Counter(use for record in records for use in record["intendedUses"])
    statuses = Counter(status for record in records for status in record["adoptionStatuses"])
    return {
        "version": "1.0.0",
        "generatedFrom": "evidence/records/SRC_*.json",
        "evidenceTotal": len(records),
        "accessLevels": {key: access[key] for key in sorted(ACCESS_LEVELS)},
        "reviewDepths": {key: reviews[key] for key in sorted(REVIEW_DEPTHS)},
        "contexts": {key: contexts[key] for key in sorted({"EMPLOYMENT_INTERVIEW", "PUBLIC_SPEAKING", "HEAD_POSE_MEASUREMENT", "POSE_MEASUREMENT"})},
        "intendedUses": {key: uses[key] for key in sorted(USES)},
        "adoptionStatuses": {
            key: statuses[key]
            for key in sorted({
                "ACCEPTED_CONTEXT", "ACCEPTED_AXIS_SELECTION", "ACCEPTED_METRIC_DEFINITION",
                "ACCEPTED_METRIC_DIRECTION", "ACCEPTED_QUALITY_GATE", "ACCEPTED_MEASUREMENT_LIMITATION",
                "ACCEPTED_HUMAN_RUBRIC", "ACCEPTED_VALIDATION_DESIGN", "EXPERIMENTAL_ONLY",
                "REJECTED_FOR_THRESHOLD", "NOT_APPLICABLE",
            })
        },
        "extractionLocationCount": sum(len(record["extractionLocations"]) for record in records),
    }


def load_gaps() -> list[dict[str, Any]]:
    text = (ROOT / "docs" / "scoring-gap-analysis-v1.md").read_text(encoding="utf-8")
    match = re.search(r"<!-- GAP_DATA_START -->\s*```json\s*(.*?)\s*```\s*<!-- GAP_DATA_END -->", text, re.DOTALL)
    if not match:
        raise ValueError("machine-readable gap register not found")
    return json.loads(match.group(1), parse_constant=_reject_constant)["gaps"]


def _validate_catalog(errors: list[str]) -> dict[str, Any]:
    catalog = load_json(ROOT / "evidence" / "source-catalog-v1.json")
    sources = catalog.get("sources", [])
    ids = [source.get("evidenceId") for source in sources]
    if len(sources) != 20 or catalog.get("sourceCount") != 20:
        errors.append("CATALOG_COUNT")
    if len(ids) != len(set(ids)):
        errors.append("CATALOG_DUPLICATE_ID")
    if set(ids) != SOURCE_IDS:
        errors.append("CATALOG_SOURCE_IDS")
    categories = {"EMPLOYMENT_INTERVIEW", "PUBLIC_SPEAKING", "HEAD_POSE_MEASUREMENT", "POSE_MEASUREMENT"}
    for source in sources:
        source_id = source.get("evidenceId", "UNKNOWN")
        if not source.get("title"):
            errors.append(f"CATALOG_TITLE:{source_id}")
        doi = source.get("doi")
        if doi is not None and not DOI_RE.match(doi):
            errors.append(f"CATALOG_DOI:{source_id}")
        if not URL_RE.match(source.get("officialUrl", "")):
            errors.append(f"CATALOG_URL:{source_id}")
        if source.get("category") not in categories:
            errors.append(f"CATALOG_CATEGORY:{source_id}")
    return catalog


def _validate_record(record: dict[str, Any], metric_ids: set[str], errors: list[str]) -> None:
    source_id = record.get("evidenceId", "UNKNOWN")
    required = {
        "evidenceId", "title", "authors", "year", "doi", "officialUrl", "fileSha256",
        "metricDefinition", "thresholdExists", "thresholdValue", "unit", "extractionLocations",
        "mapping", "access", "study", "measurements", "reportedFindings", "faceFitMappings",
        "intendedUses", "adoptionStatuses", "thresholdAssessment", "limitations", "status",
    }
    if set(record) != required:
        errors.append(f"RECORD_FIELDS:{source_id}")
    if not record.get("title") or not record.get("authors"):
        errors.append(f"RECORD_IDENTITY:{source_id}")
    doi = record.get("doi")
    if doi is not None and not DOI_RE.match(doi):
        errors.append(f"RECORD_DOI:{source_id}")
    if not URL_RE.match(record.get("officialUrl", "")):
        errors.append(f"RECORD_URL:{source_id}")
    file_hash = record.get("fileSha256")
    if file_hash is not None and not SHA_RE.match(file_hash):
        errors.append(f"RECORD_SHA:{source_id}")
    access = record.get("access", {})
    if access.get("accessLevel") not in ACCESS_LEVELS:
        errors.append(f"ACCESS_LEVEL:{source_id}")
    if access.get("reviewDepth") not in REVIEW_DEPTHS:
        errors.append(f"REVIEW_DEPTH:{source_id}")
    if access.get("reviewDepth") == "FULL_TEXT_REVIEWED" and not record.get("extractionLocations"):
        errors.append(f"FULL_TEXT_LOCATION:{source_id}")
    if access.get("reviewDepth") in {"ABSTRACT_REVIEWED", "METADATA_REVIEWED", "REVIEW_BLOCKED"}:
        if any(location.get("page") is not None for location in record.get("extractionLocations", [])):
            errors.append(f"UNREVIEWED_PAGE:{source_id}")
    if record.get("study", {}).get("participantDescription") is not None:
        errors.append(f"PARTICIPANT_DESCRIPTION:{source_id}")
    if not set(record.get("intendedUses", [])).issubset(USES) or not record.get("intendedUses"):
        errors.append(f"INTENDED_USE:{source_id}")
    assessment = record.get("thresholdAssessment", {})
    if record.get("thresholdExists") is not False or record.get("thresholdValue") is not None:
        errors.append(f"LEGACY_THRESHOLD:{source_id}")
    if assessment.get("behaviorThresholdReported") is not False or assessment.get("productionThresholdUsable") is not False:
        errors.append(f"PRODUCTION_THRESHOLD:{source_id}")
    if "THRESHOLD_CANDIDATE" in record.get("intendedUses", []):
        errors.append(f"THRESHOLD_CANDIDATE:{source_id}")
    for measurement in record.get("measurements", []):
        if measurement.get("measurementType") == "BEHAVIOR_THRESHOLD" or measurement.get("behaviorBoundaryReported") is not False:
            errors.append(f"BEHAVIOR_THRESHOLD_MEASUREMENT:{source_id}")
    for mapping in record.get("faceFitMappings", []):
        _validate_mapping(mapping, source_id, metric_ids, errors)
    for json_path, value in _walk(record):
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(f"NONFINITE:{source_id}:{json_path}")
        if isinstance(value, str) and ABSOLUTE_PATH_RE.search(value):
            errors.append(f"ABSOLUTE_PATH:{source_id}:{json_path}")
        key = json_path.rsplit(".", 1)[-1].lower()
        if "weight" in key and value not in (None, False, [], {}):
            errors.append(f"WEIGHT_VALUE:{source_id}:{json_path}")
        if key in {"productionapproved", "eligibleforscoringcandidate"} and value is True:
            errors.append(f"PRODUCTION_FLAG:{source_id}:{json_path}")
        if key in {"participantid", "transcript", "transcripttext", "sessionid", "answerid"} and value not in (None, "", [], {}):
            errors.append(f"SENSITIVE_DATA:{source_id}:{json_path}")


def _validate_mapping(mapping: dict[str, Any], owner: str, metric_ids: set[str], errors: list[str]) -> None:
    relation = mapping.get("relation")
    metric_id = mapping.get("faceFitMetricId")
    if relation not in RELATIONS:
        errors.append(f"MAPPING_RELATION:{owner}")
    if metric_id not in metric_ids:
        errors.append(f"MAPPING_METRIC:{owner}:{metric_id}")
    if mapping.get("numericThresholdSupported") is not False:
        errors.append(f"MAPPING_THRESHOLD:{owner}:{metric_id}")
    if relation == "DIRECT" and not all(mapping.get(key) is True for key in ("definitionMatch", "unitMatch", "calculationMatch")):
        errors.append(f"DIRECT_CONDITIONS:{owner}:{metric_id}")
    if relation in {"PROXY", "NOT_APPLICABLE"} and not mapping.get("reason"):
        errors.append(f"MAPPING_REASON:{owner}:{metric_id}")
    if relation == "UNIT_CONVERSION" and not mapping.get("conversion"):
        errors.append(f"UNIT_CONVERSION:{owner}:{metric_id}")


def _validate_matrix(records: list[dict[str, Any]], metric_ids: set[str], errors: list[str]) -> None:
    matrix = load_json(ROOT / "mappings" / "metric-evidence-matrix-v1.json")
    rows = matrix.get("metrics", [])
    ids = [row.get("metricId") for row in rows]
    evidence_ids = {record["evidenceId"] for record in records}
    if len(rows) != 18 or matrix.get("metricCount") != 18 or len(ids) != len(set(ids)) or set(ids) != metric_ids:
        errors.append("MATRIX_METRICS")
    if matrix.get("productionApproved") is not False:
        errors.append("MATRIX_PRODUCTION")
    for row in rows:
        metric_id = row.get("metricId", "UNKNOWN")
        if row.get("numericThresholdReadiness") != "NOT_READY" or row.get("productionReadiness") != "NOT_READY":
            errors.append(f"MATRIX_READINESS:{metric_id}")
        if row.get("directionReadiness") not in MATRIX_DIRECTION:
            errors.append(f"MATRIX_DIRECTION:{metric_id}")
        if not row.get("evidenceMappings"):
            errors.append(f"MATRIX_NO_EVIDENCE:{metric_id}")
        for mapping in row.get("evidenceMappings", []):
            if mapping.get("evidenceId") not in evidence_ids:
                errors.append(f"MATRIX_EVIDENCE:{metric_id}")
            _validate_mapping({**mapping, "faceFitMetricId": metric_id}, metric_id, metric_ids, errors)
    by_id = {row["metricId"]: row for row in rows}
    for metric_id in {"QUALITY_HEAD_AVAILABILITY_RATIO", "QUALITY_POSTURE_AVAILABILITY_RATIO"}:
        row = by_id.get(metric_id, {})
        if set(row.get("supportedUses", [])) - {"QUALITY_GATE", "MEASUREMENT_LIMITATION"}:
            errors.append(f"QUALITY_BEHAVIOR_USE:{metric_id}")
        if row.get("directionReadiness") != "NOT_APPLICABLE":
            errors.append(f"QUALITY_DIRECTION:{metric_id}")
    clipping = by_id.get("SPEECH_CLIPPING_SAMPLE_RATIO", {})
    if clipping.get("supportedUses") != ["QUALITY_GATE"]:
        errors.append("CLIPPING_BEHAVIOR_USE")
    f0_text = json.dumps(by_id.get("SPEECH_F0_RANGE_HZ", {}), ensure_ascii=False).lower()
    if any(term in f0_text for term in ("confidence", "emotion", "personality", "gender", "sex score")):
        errors.append("F0_PERSON_INFERENCE")
    all_text = json.dumps(matrix, ensure_ascii=False).lower()
    if any(phrase in all_text for phrase in ("head pose is eye", "head pose equals eye", "head pose as eye tracking")):
        errors.append("HEAD_POSE_EYE_EQUIVALENCE")


def _validate_readiness(metric_ids: set[str], errors: list[str]) -> None:
    data = load_json(ROOT / "mappings" / "threshold-readiness-v1.json")
    rows = data.get("metrics", [])
    ids = [row.get("metricId") for row in rows]
    if len(rows) != 18 or data.get("metricCount") != 18 or set(ids) != metric_ids or len(ids) != len(set(ids)):
        errors.append("READINESS_METRICS")
    if data.get("productionApproved") is not False or data.get("thresholdProfileCreated") is not False or data.get("scoreWeightsCreated") is not False:
        errors.append("READINESS_PRODUCTION")
    for row in rows:
        if row.get("readiness") not in READINESS:
            errors.append(f"READINESS_ENUM:{row.get('metricId')}")
    by_id = {row["metricId"]: row["readiness"] for row in rows}
    required = {
        "QUALITY_HEAD_AVAILABILITY_RATIO": "QUALITY_GATE_ONLY",
        "QUALITY_POSTURE_AVAILABILITY_RATIO": "QUALITY_GATE_ONLY",
        "SPEECH_CLIPPING_SAMPLE_RATIO": "QUALITY_GATE_ONLY",
        "SPEECH_F0_RANGE_HZ": "EXCLUDED_FROM_SCORING",
    }
    for metric_id, expected in required.items():
        if by_id.get(metric_id) != expected:
            errors.append(f"READINESS_PROTECTION:{metric_id}")


def _validate_gaps(metric_ids: set[str], errors: list[str]) -> None:
    try:
        gaps = load_gaps()
    except Exception as exc:
        errors.append(f"GAP_PARSE:{exc}")
        return
    ids = [gap.get("gapId") for gap in gaps]
    if set(ids) != REQUIRED_GAPS or len(ids) != len(set(ids)):
        errors.append("GAP_IDS")
    required_fields = {
        "gapId", "affectedMetricIds", "priority", "risk", "currentEvidence", "currentlyPossibleUses",
        "currentlyImpossibleUses", "neededEvidenceType", "searchKeywordsKo", "searchKeywordsEn",
        "requiredPilotData", "blockingProductionScoring",
    }
    for gap in gaps:
        gap_id = gap.get("gapId", "UNKNOWN")
        if set(gap) != required_fields:
            errors.append(f"GAP_FIELDS:{gap_id}")
        if not set(gap.get("affectedMetricIds", [])).issubset(metric_ids) or not gap.get("affectedMetricIds"):
            errors.append(f"GAP_METRICS:{gap_id}")
        if not gap.get("searchKeywordsKo") or not gap.get("searchKeywordsEn") or not gap.get("requiredPilotData"):
            errors.append(f"GAP_RESEARCH:{gap_id}")
        if gap.get("blockingProductionScoring") is not True:
            errors.append(f"GAP_BLOCKING:{gap_id}")


def _validate_repository(errors: list[str]) -> None:
    result = subprocess.run(
        [
            "git", "-c", f"safe.directory={REPOSITORY}", "-C", str(REPOSITORY),
            "ls-files", "--cached", "--others", "--exclude-standard", "--", "ai-server/scoring",
        ],
        check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        errors.append("GIT_FILE_SCAN")
        return
    forbidden_extensions = {".pdf", ".doc", ".docx", ".wav", ".mp3", ".mp4", ".mov", ".avi"}
    for relative in result.stdout.splitlines():
        normalized = relative.replace("\\", "/")
        if Path(normalized).suffix.lower() in forbidden_extensions:
            errors.append(f"FORBIDDEN_FILE:{normalized}")
        if "/evidence/private/" in f"/{normalized}":
            errors.append(f"PRIVATE_FILE:{normalized}")
    for path in [
        ROOT / "evidence" / "source-catalog-v1.json",
        *(ROOT / "evidence" / "records").glob("SRC_*.json"),
        *(ROOT / "mappings").glob("*.json"),
        ROOT / "docs" / "evidence-review-summary-v1.md",
        ROOT / "docs" / "scoring-gap-analysis-v1.md",
    ]:
        text = path.read_text(encoding="utf-8")
        if ABSOLUTE_PATH_RE.search(text):
            errors.append(f"ABSOLUTE_PATH_FILE:{path.relative_to(ROOT)}")
        lowered = text.lower()
        if any(key in lowered for key in ('"participantid"', '"transcripttext"', '"sessionid"', '"answerid"')):
            errors.append(f"SENSITIVE_FIELD_FILE:{path.relative_to(ROOT)}")


def validate() -> dict[str, Any]:
    errors: list[str] = []
    try:
        metric_ids = inventory_metric_ids()
        catalog = _validate_catalog(errors)
        records = load_records()
    except Exception as exc:
        return {"status": "scoring_evidence_mapping_validation_failed", "errors": [f"LOAD:{exc}"]}
    record_ids = [record.get("evidenceId") for record in records]
    if len(records) != 20 or len(record_ids) != len(set(record_ids)) or set(record_ids) != SOURCE_IDS:
        errors.append("RECORD_SOURCE_IDS")
    if {source["evidenceId"] for source in catalog["sources"]} != set(record_ids):
        errors.append("CATALOG_RECORD_MISMATCH")
    for record in records:
        _validate_record(record, metric_ids, errors)
    _validate_matrix(records, metric_ids, errors)
    _validate_readiness(metric_ids, errors)
    _validate_gaps(metric_ids, errors)
    expected_summary = build_summary(records)
    actual_summary = load_json(ROOT / "mappings" / "evidence-use-summary-v1.json")
    if actual_summary != expected_summary:
        errors.append("SUMMARY_MISMATCH")
    _validate_repository(errors)
    if errors:
        status = "scoring_evidence_mapping_validation_failed"
    elif any(record["access"]["reviewDepth"] != "FULL_TEXT_REVIEWED" for record in records):
        status = "scoring_evidence_mapping_ready_with_access_limitations"
    else:
        status = "scoring_evidence_mapping_ready_for_gap_research"
    return {
        "status": status,
        "sourceCount": len(records),
        "metricCount": len(metric_ids),
        "gapCount": len(load_gaps()),
        "errors": sorted(set(errors)),
    }


def main() -> int:
    report = validate()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
