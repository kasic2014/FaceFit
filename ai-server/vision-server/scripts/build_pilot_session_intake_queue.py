"""Build the Stage 21 additional pilot Session intake queue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.vision.pilot_session_intake_queue import (  # noqa: E402
    PilotSessionIntakeError,
    build_pilot_session_intake_queue,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vision-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.vision_root
    batch = (
        root
        / "data"
        / "output"
        / "pilot_annotation_batch"
        / "PILOT_ANNOTATION_BATCH_001"
    )
    try:
        report = build_pilot_session_intake_queue(
            incoming_dir=root / "data" / "pilot" / "incoming",
            batch_sessions_path=batch / "pilot_batch_sessions.json",
            split_validation_path=batch / "participant_split_validation.json",
            fixture_registry_path=(
                root / "config" / "pilot_collection" / "fixtures"
                / "pilot_registry.json"
            ),
            output_dir=args.output_dir,
            generated_at=args.generated_at,
        )
    except PilotSessionIntakeError as exc:
        print(
            json.dumps(
                {"final_status": exc.code, "error": str(exc)},
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
