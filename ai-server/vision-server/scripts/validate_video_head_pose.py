"""CLI for raw approximate TARGET_001 head pose validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.head_pose_validator import (  # noqa: E402
    DEFAULT_HEAD_POSE_OUTPUT_ROOT,
    HeadPoseValidationError,
    HeadPoseValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate raw approximate PnP head pose.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--analysis-fps", type=float, default=5.0)
    parser.add_argument("--output-root", default=str(DEFAULT_HEAD_POSE_OUTPUT_ROOT))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-diagnostic-overlay", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        report = HeadPoseValidator().validate(
            args.input, analysis_fps=args.analysis_fps,
            output_root=args.output_root, overwrite=args.overwrite,
            generate_overlay=not args.no_diagnostic_overlay,
        )
    except HeadPoseValidationError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
