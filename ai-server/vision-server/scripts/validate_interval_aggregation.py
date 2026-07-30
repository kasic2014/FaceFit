"""CLI for Stage 10 interval aggregation validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.interval_aggregation_validator import (  # noqa: E402
    DEFAULT_INTERVAL_AGGREGATION_OUTPUT_ROOT,
    IntervalAggregationValidationError,
    IntervalAggregationValidator,
    parse_interval_definitions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate Stage 9 relative features into strict time intervals."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--intervals-json")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_INTERVAL_AGGREGATION_OUTPUT_ROOT),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        intervals = (
            parse_interval_definitions(args.intervals_json)
            if args.intervals_json
            else None
        )
        report = IntervalAggregationValidator().validate(
            args.input,
            intervals=intervals,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )
    except IntervalAggregationValidationError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
