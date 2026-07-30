"""CLI for Stage 14 metadata-fixture pilot readiness validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.pilot_collection_validator import (  # noqa: E402
    DEFAULT_FIXTURE,
    DEFAULT_OUTPUT,
    PilotCollectionReadinessValidator,
    PilotCollectionValidationError,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Stage 14 with synthetic metadata fixtures."
    )
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--overwrite", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        report = PilotCollectionReadinessValidator().validate(
            fixture_path=args.fixture,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )
    except PilotCollectionValidationError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
