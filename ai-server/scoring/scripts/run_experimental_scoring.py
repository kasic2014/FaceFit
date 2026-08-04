"""Run synthetic/research scoring with an explicit opt-in."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCORING_ROOT = Path(__file__).resolve().parents[1]
if str(SCORING_ROOT) not in sys.path:
    sys.path.insert(0, str(SCORING_ROOT))

from engine.profile_loader import load_inventory, load_json, load_profile
from engine.scoring_errors import EXPERIMENTAL_NOT_ENABLED, ScoringError
from engine.scoring_service import score_payload
from engine.strict_json_writer import write_json_atomic


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run Face-Fit experimental fixture scoring.")
    result.add_argument("--profile", required=True)
    result.add_argument("--input", required=True)
    result.add_argument("--output-root", default=str(SCORING_ROOT / "data" / "output" / "experimental" / "synthetic-session"))
    result.add_argument("--allow-experimental", action="store_true")
    result.add_argument("--validate-only", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if not args.allow_experimental:
            raise ScoringError(EXPERIMENTAL_NOT_ENABLED, "Pass --allow-experimental explicitly")
        inventory = load_inventory(SCORING_ROOT / "registries" / "metric-inventory-v1.json")
        profile, digest = load_profile(args.profile, inventory)
        payload = load_json(args.input)
        validation = {"status": "PASSED", "profileId": profile["profileId"], "profileVersion": profile["version"], "profileHash": digest, "scoringMode": "EXPERIMENTAL"}
        if args.validate_only:
            print(json.dumps(validation, ensure_ascii=False, sort_keys=True))
            return 0
        result = score_payload(payload, profile, inventory, mode="EXPERIMENTAL", allow_experimental=True)
        output = Path(args.output_root)
        write_json_atomic(output / "scoring-result.json", result)
        write_json_atomic(output / "scoring-provenance.json", {
            "sessionId": result["sessionId"], "profileId": result["profileId"], "profileVersion": result["profileVersion"],
            "profileHash": result["profileHash"], "engineVersion": result["engineVersion"], "scoringMode": result["scoringMode"],
            "generatedAt": result["generatedAt"], "evidenceIds": result["evidenceIds"]
        })
        write_json_atomic(output / "scoring-validation.json", validation)
        print(json.dumps({"status": "experimental_scoring_engine_ready", "outputRoot": str(output)}, ensure_ascii=False))
        return 0
    except ScoringError as exc:
        print(json.dumps({"status": "experimental_scoring_engine_validation_failed", "errorCode": exc.code, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
