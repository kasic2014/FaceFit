"""CLI for one local static image Face/Pose landmark analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision.static_image_analyzer import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    StaticImageAnalysisError,
    StaticImageAnalyzer,
)


SUCCESS_STATUSES = {
    "completed",
    "completed_with_no_face",
    "completed_with_no_pose",
    "completed_with_no_detections",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze one local static image with Face/Pose IMAGE mode."
    )
    parser.add_argument("--input", required=True, help="Local input image path.")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root directory for per-image outputs.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Atomically replace existing output files for the same image.",
    )
    parser.add_argument(
        "--no-overlays",
        action="store_true",
        help="Write analysis.json only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        with StaticImageAnalyzer() as analyzer:
            result = analyzer.analyze(
                arguments.input,
                output_root=arguments.output_root,
                overwrite=arguments.overwrite,
                generate_overlays=not arguments.no_overlays,
            )
    except StaticImageAnalysisError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"STATIC_IMAGE_ANALYSIS_FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in SUCCESS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
