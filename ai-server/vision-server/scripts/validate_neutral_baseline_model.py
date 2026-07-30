"""CLI for the Stage 9 session baseline and relative-feature smoke test."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.neutral_baseline_smoke import (  # noqa: E402
    DEFAULT_NEUTRAL_BASELINE_OUTPUT_ROOT,
    NeutralBaselineSmokeError,
    NeutralBaselineSmokeValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test a session-local baseline and raw-baseline relative "
            "features using protected Stage 6-8 outputs."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--collection-start-ms", type=int, default=0)
    parser.add_argument("--collection-end-ms", type=int)
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_NEUTRAL_BASELINE_OUTPUT_ROOT),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        report = NeutralBaselineSmokeValidator().validate(
            args.input,
            collection_start_ms=args.collection_start_ms,
            collection_end_ms=args.collection_end_ms,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )
    except NeutralBaselineSmokeError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
