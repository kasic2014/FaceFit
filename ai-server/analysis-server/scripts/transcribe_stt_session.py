"""Transcribe the four canonical Stage 24 answer WAVs for one Session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.stt.session_transcription_service import (  # noqa: E402
    SessionTranscriptionError,
    SessionTranscriptionService,
    public_status_for_error,
)
from app.stt.transcription_profile import ProfileError, resolve_profile  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument(
        "--model-profile",
        choices=("auto", "cuda-float16", "cpu-int8"),
        default="auto",
    )
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--output-root", type=Path)
    return parser


def _strict_print(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        profile = resolve_profile(args.model_profile)
        service = SessionTranscriptionService(
            profile=profile,
            local_files_only=args.local_files_only,
            output_root=args.output_root,
        )
        result = service.run(args.session_id, force_rebuild=args.force_rebuild)
    except (ProfileError, SessionTranscriptionError) as exc:
        _strict_print(
            {
                "sessionId": args.session_id,
                "status": public_status_for_error(exc.code),
                "error": {"code": exc.code, "message": str(exc)},
            }
        )
        return 1
    _strict_print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
