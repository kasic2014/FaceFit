"""Build standardized source and interval WAVs for one canonical Session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.audio.session_audio_preprocessor import (  # noqa: E402
    PreprocessingError,
    SessionAudioPreprocessor,
    STATUS_FAILED,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--ffmpeg-path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = SessionAudioPreprocessor(
        output_root=args.output_root,
        ffmpeg_path=args.ffmpeg_path,
    )
    try:
        result = service.run(args.session_id, force_rebuild=args.force_rebuild)
    except PreprocessingError as exc:
        result = {
            "sessionId": args.session_id,
            "status": STATUS_FAILED,
            "error": {"code": exc.code, "message": str(exc)},
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
