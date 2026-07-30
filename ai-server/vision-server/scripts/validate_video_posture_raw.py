"""CLI for TARGET_001 raw shoulder posture validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.posture_raw_validator import (  # noqa: E402
    DEFAULT_POSTURE_RAW_OUTPUT_ROOT,
    PostureRawValidationError,
    PostureRawValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate raw 2D TARGET_001 shoulder posture metrics."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--analysis-fps", type=float, default=5.0)
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_POSTURE_RAW_OUTPUT_ROOT),
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-diagnostic-overlay", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        report = PostureRawValidator().validate(
            args.input,
            analysis_fps=args.analysis_fps,
            output_root=args.output_root,
            overwrite=args.overwrite,
            generate_overlay=not args.no_diagnostic_overlay,
        )
    except PostureRawValidationError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
