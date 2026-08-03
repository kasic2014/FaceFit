"""Build the Stage 20 pilot Annotation batch registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.pilot_annotation_batch import (  # noqa: E402
    CurrentSessionSources,
    PilotBatchError,
    build_pilot_annotation_batch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vision-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_pilot_annotation_batch(
            CurrentSessionSources.from_vision_root(args.vision_root),
            args.output_dir,
            created_at=args.created_at,
        )
    except PilotBatchError as exc:
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
