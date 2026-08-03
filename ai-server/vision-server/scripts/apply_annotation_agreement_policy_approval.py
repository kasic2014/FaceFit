"""Apply the authorized Stage 19.3 tie-breaker governance decision."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.annotation_policy_approval import (  # noqa: E402
    PolicyApprovalError,
    build_policy_approval_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-dir", type=Path, required=True)
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--rater-annotation", type=Path, action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_policy_approval_package(
            args.revision_dir,
            decision_path=args.decision,
            rater_annotation_paths=args.rater_annotation,
        )
    except PolicyApprovalError as exc:
        print(
            json.dumps(
                {"current_status": exc.code, "error": str(exc)},
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
