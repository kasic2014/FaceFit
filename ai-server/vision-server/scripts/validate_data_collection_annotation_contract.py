"""CLI for Stage 13 metadata-fixture contract validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.data_collection_validator import (  # noqa: E402
    DEFAULT_FIXTURE_DIRECTORY,
    DEFAULT_OUTPUT_ROOT,
    DataCollectionAnnotationContractValidator,
    DataCollectionValidationError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Stage 13 using synthetic metadata fixtures only."
    )
    parser.add_argument(
        "--fixture-directory", default=str(DEFAULT_FIXTURE_DIRECTORY)
    )
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        report = DataCollectionAnnotationContractValidator().validate(
            fixture_directory=args.fixture_directory,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )
    except DataCollectionValidationError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
