"""Create empty UTF-8 BOM CSV and strict JSON prosody dataset manifests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.prosody_dataset import (  # noqa: E402
    ProsodyDatasetError,
    create_empty_manifest,
    strict_json_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        csv_path, json_path = create_empty_manifest(args.output)
    except ProsodyDatasetError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    print(
        strict_json_text(
            {
                "csv_manifest": str(csv_path),
                "json_manifest": str(json_path),
                "sample_count": 0,
                "error": None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
