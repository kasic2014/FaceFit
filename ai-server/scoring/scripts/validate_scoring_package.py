"""Validate package structure, registries, fixture profile, and synthetic run."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.profile_loader import load_inventory, load_json, load_profile
from engine.scoring_service import score_payload
from engine.strict_json_writer import strict_json_bytes

REQUIRED = [
    "contracts/metric-input.schema.json", "contracts/metric-inventory.schema.json", "contracts/evidence-record.schema.json",
    "contracts/threshold-profile.schema.json", "contracts/scoring-result.schema.json", "registries/scoring-axis-registry-v1.json",
    "registries/metric-inventory-v1.json", "fixtures/profiles/experimental-scoring-profile-v1.json",
    "fixtures/inputs/synthetic-scoring-input-v1.json", "evidence/.gitignore", "data/output/.gitignore",
]


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"MISSING:{relative}")
    for schema in (ROOT / "contracts").glob("*.schema.json"):
        try:
            json.loads(schema.read_text(encoding="utf-8"))
        except Exception:
            errors.append(f"INVALID_JSON:{schema.relative_to(ROOT)}")
    inventory = load_inventory(ROOT / "registries" / "metric-inventory-v1.json")
    for metric in inventory["metrics"]:
        path = metric["implementationPath"]
        if Path(path).is_absolute() or not (REPOSITORY / path).is_file():
            errors.append(f"IMPLEMENTATION_PATH:{metric['metricId']}")
        if metric["evidenceStatus"] == "UNMAPPED" and metric["eligibleForScoringCandidate"]:
            errors.append(f"UNMAPPED_ELIGIBLE:{metric['metricId']}")
    profile, _ = load_profile(ROOT / "fixtures" / "profiles" / "experimental-scoring-profile-v1.json", inventory)
    payload = load_json(ROOT / "fixtures" / "inputs" / "synthetic-scoring-input-v1.json")
    result = score_payload(payload, profile, inventory, allow_experimental=True)
    strict_json_bytes(result)
    if result["overallScoreAvailable"] or result["overallScore"] is not None:
        errors.append("OVERALL_DEFAULT_NOT_DISABLED")
    if result["evidenceIds"] != ["EVIDENCE_TEST_FIXTURE_ONLY"]:
        errors.append("FIXTURE_EVIDENCE_ID_INVALID")
    status = "experimental_scoring_engine_ready" if not errors else "experimental_scoring_engine_validation_failed"
    print(json.dumps({"status": status, "metricCount": len(inventory["metrics"]), "errors": errors}, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
