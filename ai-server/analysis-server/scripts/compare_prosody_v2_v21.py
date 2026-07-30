"""Compare prosody v2 with v2.1 denominator and risk diagnostics."""

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
from app.speech.prosody_validation_v21 import (  # noqa: E402
    run_synthetic_validation_v21_suite,
)


SAMPLES = (
    "speech_01_clean",
    "speech_03_silence_long",
    "speech_04_fast",
    "speech_05_slow",
    "speech_06_noise",
)

CSV_FIELDS = (
    "sample",
    "v2_error_code",
    "v21_error_code",
    "v2_overall_coverage_ratio",
    "v21_overall_coverage_ratio",
    "v2_voiced_coverage_ratio",
    "v21_voiced_coverage_ratio",
    "v21_joint_valid_ratio",
    "v21_joint_valid_voiced_ratio",
    "v21_agreement_frame_count",
    "v21_conditioned_agreement_ratio",
    "v21_agreement_ratio_over_acoustic_voiced",
    "v21_agreement_ratio_over_total_frames",
    "v21_harmonic_ambiguity_ratio",
    "v21_shared_octave_error_risk",
    "v21_harmonic_ambiguity_risk",
    "v21_reliability_level",
    "v21_reliability_flags",
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    payload = json.loads(
        path.read_text(encoding="utf-8-sig"),
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON constant: {token}")
        ),
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def compare_payloads(
    sample: str,
    v2: dict[str, Any],
    v21: dict[str, Any],
) -> dict[str, Any]:
    v2_pitch = v2.get("validated_pitch_summary") or {}
    coverage = v21.get("coverage_summary") or {}
    agreement = v21.get("agreement_summary") or {}
    harmonic = v21.get("harmonic_support_summary") or {}
    risks = v21.get("shared_failure_diagnostics") or {}
    v2_error = v2.get("error") or {}
    v21_error = v21.get("error") or {}
    return {
        "sample": sample,
        "v2_error_code": v2_error.get("code"),
        "v21_error_code": v21_error.get("code"),
        "v2_overall_coverage_ratio": v2_pitch.get("pitch_coverage_ratio"),
        "v21_overall_coverage_ratio": coverage.get(
            "validated_pitch_overall_coverage_ratio"
        ),
        "v2_voiced_coverage_ratio": v2_pitch.get(
            "pitch_voiced_coverage_ratio"
        ),
        "v21_voiced_coverage_ratio": coverage.get(
            "validated_pitch_voiced_coverage_ratio"
        ),
        "v21_joint_valid_ratio": coverage.get(
            "dual_estimator_joint_valid_ratio"
        ),
        "v21_joint_valid_voiced_ratio": coverage.get(
            "dual_estimator_joint_valid_voiced_ratio"
        ),
        "v21_agreement_frame_count": agreement.get(
            "estimator_agreement_frame_count"
        ),
        "v21_conditioned_agreement_ratio": agreement.get(
            "estimator_agreement_ratio_conditioned_on_joint_valid"
        ),
        "v21_agreement_ratio_over_acoustic_voiced": agreement.get(
            "estimator_agreement_ratio_over_acoustic_voiced"
        ),
        "v21_agreement_ratio_over_total_frames": agreement.get(
            "estimator_agreement_ratio_over_total_frames"
        ),
        "v21_harmonic_ambiguity_ratio": harmonic.get(
            "harmonic_ambiguity_ratio"
        ),
        "v21_shared_octave_error_risk": risks.get(
            "shared_octave_error_risk"
        ),
        "v21_harmonic_ambiguity_risk": risks.get(
            "harmonic_ambiguity_risk"
        ),
        "v21_reliability_level": v21.get("analysis_reliability_level"),
        "v21_reliability_flags": list(
            (v21.get("prosody_reliability") or {}).get(
                "reliability_flags"
            )
            or []
        ),
    }


def compare_directories(
    v2_directory: Path,
    v21_directory: Path,
    samples: tuple[str, ...] = SAMPLES,
) -> dict[str, Any]:
    comparisons = []
    for sample in samples:
        v2 = _load(v2_directory / f"{sample}_prosody_v2.json")
        v21 = _load(v21_directory / f"{sample}_prosody_v21.json")
        comparisons.append(compare_payloads(sample, v2, v21))
    return {
        "schema_version": "1.0",
        "description": (
            "Objective v2/v2.1 aggregation comparison. No real-audio "
            "accuracy, precision, recall, score, or human-trait inference."
        ),
        "sample_count": len(comparisons),
        "comparisons": comparisons,
        "synthetic_validation": run_synthetic_validation_v21_suite(),
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
                row["v21_reliability_flags"] = "|".join(
                    row["v21_reliability_flags"]
                )
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
    parser.add_argument("--v2-dir", type=Path, required=True)
    parser.add_argument("--v21-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = compare_directories(args.v2_dir, args.v21_dir)
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
                        "code": "PROSODY_V21_COMPARISON_FAILED",
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
