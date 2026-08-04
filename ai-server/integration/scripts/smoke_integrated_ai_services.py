"""Run the integrated Session twice and verify idempotent stable fields."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Sequence


INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
AI_SERVER_ROOT = INTEGRATION_ROOT.parent
if str(AI_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVER_ROOT))

from integration.contracts.common_contracts import atomic_write_json  # noqa: E402
from integration.services.ai_api_client import AiApiClient, AiApiClientConfig  # noqa: E402
from integration.services.integrated_session_service import IntegratedSessionService  # noqa: E402


DYNAMIC_KEYS = frozenset(
    {
        "generatedAt",
        "requestId",
        "jobId",
        "createdAt",
        "queuedAt",
        "startedAt",
        "completedAt",
        "updatedAt",
        "queueWaitMs",
        "executionDurationMs",
        "totalDurationMs",
    }
)


def stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key not in DYNAMIC_KEYS}
    if isinstance(value, list):
        return [stable(item) for item in value]
    return deepcopy(value)


def parser() -> argparse.ArgumentParser:
    defaults = AiApiClientConfig.from_env()
    result = argparse.ArgumentParser(description="Stage 28 two-pass HTTP smoke test.")
    result.add_argument("--session-id", default="SES_000001")
    result.add_argument(
        "--vision-base-url",
        default=defaults.vision_base_url,
    )
    result.add_argument(
        "--analysis-base-url",
        default=defaults.analysis_base_url,
    )
    result.add_argument("--timeout-seconds", type=float, default=120.0)
    result.add_argument("--poll-interval-ms", type=int, default=250)
    result.add_argument(
        "--output-root", type=Path, default=INTEGRATION_ROOT / "data" / "output"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = AiApiClientConfig(
        vision_base_url=args.vision_base_url,
        analysis_base_url=args.analysis_base_url,
        poll_interval_ms=args.poll_interval_ms,
        timeout_seconds=args.timeout_seconds,
    )
    service = IntegratedSessionService(AiApiClient(config))
    first = service.run(args.session_id)
    service.write_outputs(args.output_root, first)
    second = service.run(args.session_id)
    service.write_outputs(args.output_root, second)
    stable_match = stable(first["integratedSession"]) == stable(second["integratedSession"])
    vision_job_reused = (
        first["runtimeMetadata"]["visionJobId"] is not None
        and first["runtimeMetadata"]["visionJobId"] == second["runtimeMetadata"]["visionJobId"]
    )
    analysis_job_reused = (
        first["runtimeMetadata"]["analysisJobId"] is not None
        and first["runtimeMetadata"]["analysisJobId"] == second["runtimeMetadata"]["analysisJobId"]
    )
    first_result = first["integratedSession"]
    validation = second["integrationValidation"]
    smoke = {
        "sessionId": args.session_id,
        "status": (
            "PASSED"
            if stable_match and validation["valid"] and vision_job_reused and analysis_job_reused
            else "FAILED"
        ),
        "runCount": 2,
        "stableContractMatch": stable_match,
        "visionJobReused": vision_job_reused,
        "analysisJobReused": analysis_job_reused,
        "integrationStatus": first_result["status"],
        "answerCount": len(first_result["answers"]),
        "visionAnswerCount": first_result["components"]["vision"]["answerCount"],
        "segmentCount": first_result["components"]["transcription"]["segmentCount"],
        "wordCount": first_result["components"]["transcription"]["wordCount"],
        "speechAnswerCount": first_result["components"]["speechCharacteristics"]["answerCount"],
        "fillerCandidateCount": first_result["components"]["speechCharacteristics"]["fillerCandidateCount"],
        "pitchAvailableAnswerCount": first_result["components"]["speechCharacteristics"]["pitchAvailableAnswerCount"],
        "timestampErrorCount": validation["timestampValidation"]["errorCount"],
        "transcriptTextExposed": first_result["components"]["transcription"]["textExposed"],
        "scoringAvailable": first_result["scoringAvailable"],
    }
    atomic_write_json(
        args.output_root / "stage28_validation" / f"{args.session_id}_integration_smoke.json",
        smoke,
    )
    print(json.dumps(smoke, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0 if smoke["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
