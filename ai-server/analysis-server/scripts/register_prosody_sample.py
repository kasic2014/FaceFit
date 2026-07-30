"""Register one anonymous sample in a prosody validation manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.prosody_dataset import (  # noqa: E402
    RECORDING_CONDITIONS,
    ProsodyDatasetError,
    register_sample,
    strict_json_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--speaker-code", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--script-id", required=True)
    parser.add_argument("--repetition-index", required=True, type=int)
    parser.add_argument("--device-code", required=True)
    parser.add_argument("--environment-code", required=True)
    parser.add_argument(
        "--recording-condition",
        required=True,
        choices=sorted(RECORDING_CONDITIONS),
    )
    parser.add_argument("--wav", required=True, type=Path)
    parser.add_argument("--stt-json", required=True, type=Path)
    parser.add_argument("--speech-metrics-json", required=True, type=Path)
    parser.add_argument("--prosody-v21-json", required=True, type=Path)
    parser.add_argument("--consent-confirmed", action="store_true")
    parser.add_argument("--notes", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    sample = {
        "sample_id": args.sample_id,
        "speaker_code": args.speaker_code,
        "session_id": args.session_id,
        "script_id": args.script_id,
        "repetition_index": args.repetition_index,
        "device_code": args.device_code,
        "environment_code": args.environment_code,
        "recording_condition": args.recording_condition,
        "wav_path": args.wav,
        "stt_json_path": args.stt_json,
        "speech_metrics_json_path": args.speech_metrics_json,
        "prosody_v21_json_path": args.prosody_v21_json,
        "consent_confirmed": args.consent_confirmed,
        "notes": args.notes,
    }
    try:
        record = register_sample(
            args.manifest,
            sample,
            workspace_root=Path.cwd(),
        )
    except ProsodyDatasetError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    print(strict_json_text({"sample": record, "error": None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
