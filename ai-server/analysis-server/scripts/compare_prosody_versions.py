"""Compare immutable prosody v1 JSON files with separately generated v2 files."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.prosody_metrics import (  # noqa: E402
    ProsodyAnalysisError,
    strict_json_text,
    write_json_atomic,
)
from app.speech.prosody_validation import (  # noqa: E402
    run_synthetic_validation_suite,
)


SAMPLE_NAMES = (
    "speech_01_clean",
    "speech_03_silence_long",
    "speech_04_fast",
    "speech_05_slow",
    "speech_06_noise",
)

CSV_FIELDS = (
    "sample",
    "v1_error_code",
    "v2_error_code",
    "v1_pitch_median_hz",
    "v2_pitch_median_hz",
    "pitch_median_delta_hz",
    "v1_pitch_range_semitones",
    "v2_pitch_range_semitones",
    "pitch_range_delta_semitones",
    "v1_pitch_coverage_ratio",
    "v2_pitch_coverage_ratio",
    "pitch_coverage_delta",
    "v1_octave_candidate_count",
    "v2_octave_candidate_count",
    "v2_unresolved_frame_count",
    "v1_large_pitch_jump_count",
    "v2_raw_large_pitch_jump_count",
    "v2_corrected_large_pitch_jump_count",
    "v2_estimator_agreement_ratio",
    "v2_corrected_frame_count",
    "v1_reliability_flags",
    "v2_reliability_flags",
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    value = json.loads(
        path.read_text(encoding="utf-8-sig"),
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON constant: {token}")
        ),
    )
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(first: Any, second: Any) -> float | None:
    before = _number(first)
    after = _number(second)
    if before is None or after is None:
        return None
    return round(after - before, 6)


def compare_payloads(
    sample: str,
    v1: dict[str, Any],
    v2: dict[str, Any],
) -> dict[str, Any]:
    v1_pitch = v1.get("pitch_summary") or {}
    v1_intonation = v1.get("intonation_summary") or {}
    v1_reliability = v1.get("prosody_reliability") or {}
    v2_pitch = v2.get("validated_pitch_summary") or {}
    v2_correction = v2.get("correction_summary") or {}
    v2_reliability = v2.get("prosody_reliability") or {}
    v1_error = v1.get("error") or {}
    v2_error = v2.get("error") or {}
    row = {
        "sample": sample,
        "v1_error_code": v1_error.get("code"),
        "v2_error_code": v2_error.get("code"),
        "v1_pitch_median_hz": v1_pitch.get("pitch_median_hz"),
        "v2_pitch_median_hz": v2_pitch.get("pitch_median_hz"),
        "v1_pitch_range_semitones": v1_pitch.get(
            "pitch_range_semitones"
        ),
        "v2_pitch_range_semitones": v2_pitch.get(
            "pitch_range_semitones"
        ),
        "v1_pitch_coverage_ratio": v1_pitch.get("pitch_coverage_ratio"),
        "v2_pitch_coverage_ratio": v2_pitch.get("pitch_coverage_ratio"),
        "v1_octave_candidate_count": v1_reliability.get(
            "octave_error_candidate_count"
        ),
        "v2_octave_candidate_count": v2_correction.get(
            "octave_candidate_count"
        ),
        "v2_unresolved_frame_count": v2_correction.get(
            "unresolved_frame_count"
        ),
        "v1_large_pitch_jump_count": v1_intonation.get(
            "large_pitch_jump_count"
        ),
        "v2_raw_large_pitch_jump_count": v2_correction.get(
            "raw_large_jump_count"
        ),
        "v2_corrected_large_pitch_jump_count": v2_correction.get(
            "corrected_large_jump_count"
        ),
        "v2_estimator_agreement_ratio": v2_correction.get(
            "estimator_agreement_ratio"
        ),
        "v2_corrected_frame_count": v2_correction.get(
            "corrected_frame_count"
        ),
        "v1_reliability_flags": list(
            v1_reliability.get("reliability_flags") or []
        ),
        "v2_reliability_flags": list(
            v2_reliability.get("reliability_flags") or []
        ),
    }
    row.update(
        {
            "pitch_median_delta_hz": _delta(
                row["v1_pitch_median_hz"], row["v2_pitch_median_hz"]
            ),
            "pitch_range_delta_semitones": _delta(
                row["v1_pitch_range_semitones"],
                row["v2_pitch_range_semitones"],
            ),
            "pitch_coverage_delta": _delta(
                row["v1_pitch_coverage_ratio"],
                row["v2_pitch_coverage_ratio"],
            ),
        }
    )
    return row


def compare_directories(
    v1_directory: Path,
    v2_directory: Path,
    sample_names: tuple[str, ...] = SAMPLE_NAMES,
) -> dict[str, Any]:
    rows = []
    for sample in sample_names:
        v1 = _load(v1_directory / f"{sample}_prosody.json")
        v2 = _load(v2_directory / f"{sample}_prosody_v2.json")
        rows.append(compare_payloads(sample, v1, v2))
    return {
        "schema_version": "1.0",
        "description": (
            "Objective v1/v2 prosody metric comparison. Real recordings have "
            "no truth-based accuracy claim and are not used for scoring."
        ),
        "v1_directory": str(v1_directory),
        "v2_directory": str(v2_directory),
        "sample_count": len(rows),
        "comparisons": rows,
        "synthetic_validation": run_synthetic_validation_suite(),
        "error": None,
    }


def write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for source in rows:
                row = dict(source)
                for field in ("v1_reliability_flags", "v2_reliability_flags"):
                    row[field] = "|".join(row.get(field) or [])
                writer.writerow({field: row.get(field) for field in CSV_FIELDS})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProsodyAnalysisError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-dir", type=Path, required=True)
    parser.add_argument("--v2-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = compare_directories(args.v1_dir, args.v2_dir)
        write_json_atomic(args.output, result)
        write_csv_atomic(args.csv_output, result["comparisons"])
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        ProsodyAnalysisError,
    ) as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "PROSODY_COMPARISON_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(strict_json_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
