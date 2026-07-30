"""Build the policy-gated Face-Fit Stage 19 agreement review package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.pilot_annotation_agreement import (  # noqa: E402
    VALIDATION_FAILED_STATUS,
    build_stage19_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_stage19_package(
        package_dir=args.package_dir,
        metadata_path=args.metadata,
        registry_path=args.registry,
        output_dir=args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if report["current_status"] == VALIDATION_FAILED_STATUS else 0


if __name__ == "__main__":
    raise SystemExit(main())
