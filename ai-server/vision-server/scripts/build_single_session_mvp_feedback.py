"""Build Stage 22 single-Session Vision MVP feedback outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.single_session_mvp_feedback import (  # noqa: E402
    EXPECTED_PARTICIPANT_ID,
    EXPECTED_SESSION_ID,
    SingleSessionMvpError,
    build_and_write_single_session_mvp_feedback,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vision-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--participant-id", default=EXPECTED_PARTICIPANT_ID
    )
    parser.add_argument("--session-id", default=EXPECTED_SESSION_ID)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_and_write_single_session_mvp_feedback(
            vision_root=args.vision_root,
            output_dir=args.output_dir,
            participant_id=args.participant_id,
            session_id=args.session_id,
        )
    except SingleSessionMvpError as exc:
        print(
            json.dumps(
                {"result_status": exc.code, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
