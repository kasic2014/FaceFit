"""Benchmark registered prosody v2.1 artifacts without rerunning analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.prosody_dataset import (  # noqa: E402
    ProsodyDatasetError,
    benchmark_dataset,
    strict_json_text,
    write_benchmark_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--sample-output-csv", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = benchmark_dataset(args.manifest, workspace_root=Path.cwd())
    if result["error"] is not None:
        print(strict_json_text(result))
        return 1
    try:
        write_benchmark_outputs(
            result,
            args.output_json,
            args.output_csv,
            args.sample_output_csv,
        )
    except ProsodyDatasetError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
        print(strict_json_text(result))
        return 1
    print(strict_json_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
