"""CLI for Stage 11 fixture-only evidence/scoring contract validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.evidence_scoring_contract_validator import (  # noqa: E402
    DEFAULT_FIXTURE_DIRECTORY,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_STAGE10_INPUT,
    EvidenceScoringContractValidationError,
    EvidenceScoringContractValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Stage 11 evidence and scoring contracts using only "
            "synthetic TEST_FIXTURE data."
        )
    )
    parser.add_argument("--input", default=str(DEFAULT_STAGE10_INPUT))
    parser.add_argument(
        "--fixture-directory",
        default=str(DEFAULT_FIXTURE_DIRECTORY),
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
        report = EvidenceScoringContractValidator().validate(
            args.input,
            fixture_directory=args.fixture_directory,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )
    except EvidenceScoringContractValidationError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
