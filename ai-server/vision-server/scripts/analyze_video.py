"""CLI for local sequential MediaPipe VIDEO-mode analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision.frame_sampler import DEFAULT_ANALYSIS_FPS  # noqa: E402
from app.vision.video_analyzer import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    VideoAnalysisError,
    VideoAnalyzer,
)


SUCCESS_STATUSES = {
    "completed",
    "completed_with_warnings",
    "partial_completed",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze one local video with Face/Pose VIDEO mode."
    )
    parser.add_argument("--input", required=True, help="Local input video path.")
    parser.add_argument(
        "--analysis-fps",
        type=float,
        default=DEFAULT_ANALYSIS_FPS,
    )
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-overlay", action="store_true")
    parser.add_argument("--require-overlay", action="store_true")
    parser.add_argument("--save-all-sampled-frames", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if arguments.no_overlay and arguments.require_overlay:
        print(
            "VIDEO_CLI_USAGE_ERROR: --no-overlay and --require-overlay conflict.",
            file=sys.stderr,
        )
        return 2
    try:
        with VideoAnalyzer() as analyzer:
            result = analyzer.analyze(
                arguments.input,
                arguments.analysis_fps,
                output_root=arguments.output_root,
                overwrite=arguments.overwrite,
                generate_overlay=not arguments.no_overlay,
                require_overlay=arguments.require_overlay,
                save_all_sampled_frames=arguments.save_all_sampled_frames,
            )
    except VideoAnalysisError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in SUCCESS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
