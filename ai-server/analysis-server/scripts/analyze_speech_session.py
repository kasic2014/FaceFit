"""Measure Stage 26 speech characteristics for one canonical Session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.speech.speech_contracts import (  # noqa: E402
    DEFAULT_PROFILE,
    SpeechContractError,
    resolve_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--profile", choices=(DEFAULT_PROFILE.name,), default=DEFAULT_PROFILE.name)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        from app.speech.speech_analysis_service import (
            SpeechAnalysisError,
            SpeechAnalysisService,
            public_status_for_error,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        result = {
            "sessionId": args.session_id,
            "status": "speech_characteristics_dependency_blocked",
            "error": {
                "code": "SPEECH_CHARACTERISTICS_DEPENDENCY_BLOCKED",
                "message": f"Required speech dependency is unavailable: {type(exc).__name__}",
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1
    try:
        service = SpeechAnalysisService(
            profile=resolve_profile(args.profile), output_root=args.output_root
        )
        result = service.run(args.session_id, force_rebuild=args.force_rebuild)
    except (SpeechAnalysisError, SpeechContractError) as exc:
        result = {
            "sessionId": args.session_id,
            "status": public_status_for_error(exc.code),
            "error": {"code": exc.code, "message": str(exc)},
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
