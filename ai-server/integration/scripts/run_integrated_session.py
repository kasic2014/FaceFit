"""Run one Stage 28 integrated Session against the public AI APIs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
AI_SERVER_ROOT = INTEGRATION_ROOT.parent
if str(AI_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVER_ROOT))

from integration.contracts.common_contracts import IntegrationContractError  # noqa: E402
from integration.services.ai_api_client import AiApiClient, AiApiClientConfig  # noqa: E402
from integration.services.integrated_session_service import IntegratedSessionService  # noqa: E402


def parser() -> argparse.ArgumentParser:
    defaults = AiApiClientConfig.from_env()
    result = argparse.ArgumentParser(
        description="Build a privacy-minimized Vision and Analysis Session result."
    )
    result.add_argument("--session-id", required=True)
    result.add_argument(
        "--vision-base-url",
        default=defaults.vision_base_url,
    )
    result.add_argument(
        "--analysis-base-url",
        default=defaults.analysis_base_url,
    )
    result.add_argument(
        "--timeout-seconds",
        type=float,
        default=defaults.timeout_seconds,
    )
    result.add_argument(
        "--poll-interval-ms",
        type=int,
        default=defaults.poll_interval_ms,
    )
    result.add_argument(
        "--output-root", type=Path, default=INTEGRATION_ROOT / "data" / "output"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = AiApiClientConfig(
            vision_base_url=args.vision_base_url,
            analysis_base_url=args.analysis_base_url,
            poll_interval_ms=args.poll_interval_ms,
            timeout_seconds=args.timeout_seconds,
        )
        service = IntegratedSessionService(AiApiClient(config))
        package = service.run(args.session_id)
        service.write_outputs(args.output_root, package)
        integrated = package["integratedSession"]
        summary = {
            "sessionId": integrated["sessionId"],
            "status": integrated["status"],
            "answerCount": len(integrated["answers"]),
            "warningCount": len(integrated["warnings"]),
            "errorCount": len(integrated["errors"]),
            "transcriptTextExposed": integrated["components"]["transcription"]["textExposed"],
        }
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False, sort_keys=True))
        return 0 if integrated["status"] != "INTEGRATED_FAILED" else 2
    except IntegrationContractError as exc:
        print(json.dumps({"status": "INTEGRATED_FAILED", "error": exc.to_dict()}, allow_nan=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
