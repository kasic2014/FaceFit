"""Run prosody v2.1 denominator and harmonic-support diagnostics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.prosody_metrics import ProsodyAnalysisError  # noqa: E402
from app.speech.prosody_validation_v21 import (  # noqa: E402
    analyze_speech_prosody_v21,
    strict_json_text,
    write_json_atomic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav_file", type=Path)
    parser.add_argument("stt_json", type=Path)
    parser.add_argument("quality_metrics_json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--include-frames",
        action="store_true",
        help="Include per-frame dual-estimator and harmonic diagnostics.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = analyze_speech_prosody_v21(
        args.wav_file,
        args.stt_json,
        args.quality_metrics_json,
        include_frames=args.include_frames,
    )
    try:
        write_json_atomic(args.output, result)
    except ProsodyAnalysisError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
        print(strict_json_text(result))
        return 1
    print(strict_json_text(result))
    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
