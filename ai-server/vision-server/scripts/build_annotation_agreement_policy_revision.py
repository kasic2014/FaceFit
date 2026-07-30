"""Build the Stage 19.2 tie-breaker governance review package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.annotation_policy_revision import (  # noqa: E402
    VALIDATION_FAILED_STATUS,
    build_policy_revision_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage191-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--rater-annotation", type=Path, action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_policy_revision_package(
        args.stage191_dir,
        args.output_dir,
        decision_path=args.decision,
        rater_annotation_paths=args.rater_annotation,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if report["current_status"] == VALIDATION_FAILED_STATUS else 0


if __name__ == "__main__":
    raise SystemExit(main())
