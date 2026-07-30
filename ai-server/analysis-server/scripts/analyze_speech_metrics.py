"""Analyze silence, omitted speech, and hallucination candidates from WAV and STT JSON."""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.speech_metrics import (  # noqa: E402
    analyze_speech_metrics,
    serialize_json,
    write_json_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_file", type=Path)
    parser.add_argument("stt_json_file", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = analyze_speech_metrics(args.audio_file, args.stt_json_file)
        if args.output is not None:
            write_json_file(args.output, result)
    except (OSError, ValueError, json.JSONDecodeError, wave.Error) as exc:
        result = {
            "error": {
                "code": "SPEECH_METRICS_FAILED",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        }
        print(serialize_json(result))
        return 1
    print(serialize_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
