"""Apply the frozen prosody v2.1 analyzer to one converted recording session.

This is orchestration only.  It does not transcribe, convert audio, rerun
speech metrics, tune thresholds, or change the prosody v2.1 implementation.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from app.speech.prosody_validation_v21 import (  # noqa: E402
    analyze_speech_prosody_v21,
)


EXPECTED_FILE_COUNT = 24
PC_DEVICE = "DEV_PC_MIC_01"
PHONE_DEVICE = "DEV_PHONE_01"
SAMPLE_ID_PATTERN = re.compile(
    r"^(?P<speaker>SPK\d+)_(?P<session>SESSION\d+)_"
    r"(?P<script>SCRIPT\d+)_(?P<device>DEV_(?:PC_MIC|PHONE)_\d+)_"
    r"(?P<condition>clean|natural)_R(?P<repetition>\d+)$"
)
MANIFEST_FIELDS = (
    "sample_id",
    "speaker_code",
    "session_id",
    "script_id",
    "recording_condition",
    "repetition_index",
    "device_code",
    "capture_pair_key",
    "audio_file",
    "audio_sha256",
    "audio_duration_sec",
    "stt_json_file",
    "speech_metrics_json_file",
    "prosody_v21_json_file",
    "schema_version",
    "pitch_median_hz",
    "pitch_min_hz",
    "pitch_max_hz",
    "pitch_range_semitones",
    "pitch_std_semitones",
    "intonation_variability",
    "ending_pattern",
    "ending_pitch_change_semitones",
    "total_frame_count",
    "voiced_frame_count",
    "validated_frame_count",
    "joint_valid_frame_count",
    "validated_overall_coverage",
    "validated_over_voiced_coverage",
    "joint_over_voiced_coverage",
    "conditioned_estimator_agreement",
    "agree_frame_count",
    "disagree_frame_count",
    "acf_only_frame_count",
    "yin_only_frame_count",
    "both_invalid_frame_count",
    "octave_correction_count",
    "unresolved_ambiguity_count",
    "harmonic_support_diagnostics",
    "clipping_ratio",
    "background_noise_warning",
    "low_pitch_coverage_warning",
    "shared_octave_harmonic_risk",
    "reliability_status",
    "internal_use_status",
    "warnings",
    "error",
)
ERROR_CODES = {
    "STANDARD_WAV_NOT_FOUND",
    "CONVERSION_MANIFEST_INVALID",
    "PROSODY_V21_ANALYSIS_FAILED",
    "PROSODY_V21_RESULT_INVALID",
    "DEVICE_PAIR_INCOMPLETE",
    "SPEECH_METRICS_NOT_FOUND",
    "REPEATABILITY_GROUP_INVALID",
    "PROSODY_V21_WRITE_FAILED",
    "SESSION_PROSODY_V21_FAILED",
}


class SessionProsodyV21Error(Exception):
    """Structured session-level failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def strict_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(path: Path | str, root: Path | str) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def _strict_constant(token: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {token}")


def load_json(path: Path | str, code: str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise SessionProsodyV21Error(code, str(source))
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8-sig"),
            parse_constant=_strict_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SessionProsodyV21Error(
            code, f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SessionProsodyV21Error(code, f"JSON object required: {source}")
    return payload


def atomic_json(path: Path | str, payload: Any) -> None:
    target = Path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(strict_json_text(payload))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except (OSError, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise SessionProsodyV21Error(
            "PROSODY_V21_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if value is None:
        return ""
    return value


def atomic_csv(
    path: Path | str,
    rows: list[dict[str, Any]],
    fields: tuple[str, ...] = MANIFEST_FIELDS,
) -> None:
    target = Path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {field: _csv_value(row.get(field)) for field in fields}
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except (OSError, csv.Error, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise SessionProsodyV21Error(
            "PROSODY_V21_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def parse_sample_id(sample_id: str) -> dict[str, Any]:
    match = SAMPLE_ID_PATTERN.fullmatch(str(sample_id))
    if match is None:
        raise SessionProsodyV21Error(
            "CONVERSION_MANIFEST_INVALID",
            f"Invalid sample_id: {sample_id}",
        )
    parts = match.groupdict()
    return {
        "sample_id": sample_id,
        "speaker_code": parts["speaker"],
        "session_id": parts["session"],
        "script_id": parts["script"],
        "device_code": parts["device"],
        "recording_condition": parts["condition"],
        "repetition_index": int(parts["repetition"]),
        "capture_pair_key": (
            f"{parts['speaker']}|{parts['session']}|{parts['script']}|"
            f"{parts['condition']}|{int(parts['repetition'])}"
        ),
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _validated_pitch_diagnostics(
    frames: list[dict[str, Any]],
) -> dict[str, float | None]:
    values = [
        number
        for frame in frames
        if frame.get("valid")
        and (_number(frame.get("corrected_f0_hz")) is not None)
        for number in [_number(frame.get("corrected_f0_hz"))]
        if number is not None and number > 0
    ]
    if not values:
        return {
            "pitch_min_hz": None,
            "pitch_max_hz": None,
            "pitch_std_semitones": None,
            "intonation_variability": None,
        }
    reference = statistics.median(values)
    semitones = [12.0 * math.log2(value / reference) for value in values]
    standard_deviation = statistics.pstdev(semitones)
    return {
        "pitch_min_hz": round(min(values), 3),
        "pitch_max_hz": round(max(values), 3),
        "pitch_std_semitones": round(standard_deviation, 6),
        # Existing prosody terminology is retained; this is not an assessment.
        "intonation_variability": round(standard_deviation, 6),
    }


def _ending_diagnostics(
    segments: list[dict[str, Any]],
) -> tuple[str | None, float | None]:
    for segment in reversed(segments):
        ending = segment.get("ending_intonation")
        if isinstance(ending, dict):
            return (
                ending.get("ending_pattern"),
                _number(ending.get("ending_pitch_change_semitones")),
            )
    return None, None


def internal_use_status(reliability: str | None) -> str:
    if reliability == "sufficient_for_experimental_summary":
        return "experimental_summary_eligible"
    if reliability in {"limited", "unreliable"}:
        return "diagnostic_only"
    return "analysis_unavailable"


def validate_v21_result(result: dict[str, Any]) -> None:
    required_objects = (
        "coverage_summary",
        "agreement_summary",
        "dual_estimator_status",
        "harmonic_support_summary",
        "shared_failure_diagnostics",
        "validated_pitch_summary",
        "correction_summary",
        "loudness_summary",
    )
    if result.get("schema_version") != "2.1":
        raise SessionProsodyV21Error(
            "PROSODY_V21_RESULT_INVALID", "schema_version must be 2.1"
        )
    if result.get("error") is not None:
        raise SessionProsodyV21Error(
            "PROSODY_V21_ANALYSIS_FAILED",
            json.dumps(result["error"], ensure_ascii=False),
        )
    if any(not isinstance(result.get(name), dict) for name in required_objects):
        raise SessionProsodyV21Error(
            "PROSODY_V21_RESULT_INVALID",
            "Required prosody v2.1 result objects are missing.",
        )
    status = result["dual_estimator_status"]
    if sum(int(value) for value in status.values()) != int(
        result["coverage_summary"].get("total_analysis_frame_count", -1)
    ):
        raise SessionProsodyV21Error(
            "PROSODY_V21_RESULT_INVALID",
            "Dual-estimator matrix does not sum to total frames.",
        )


@contextmanager
def core_quality_metrics_path(
    speech_metrics_path: Path,
) -> Iterator[Path]:
    """Expose the existing nested raw quality object to the frozen core.

    SESSION001's session wrapper retains the reused raw speech-metrics result
    under ``existing_speech_metrics``.  The frozen v2.1 core predates that
    wrapper and requires ``audio_quality`` at the top level.  A temporary
    read-only compatibility view avoids modifying either side.
    """
    payload = load_json(speech_metrics_path, "SPEECH_METRICS_NOT_FOUND")
    if isinstance(payload.get("audio_quality"), dict):
        yield speech_metrics_path
        return
    existing = payload.get("existing_speech_metrics")
    quality = (
        existing.get("audio_quality")
        if isinstance(existing, dict)
        else None
    )
    if not isinstance(quality, dict):
        raise SessionProsodyV21Error(
            "SPEECH_METRICS_NOT_FOUND",
            f"audio_quality not found: {speech_metrics_path}",
        )
    with tempfile.TemporaryDirectory(prefix="prosody_v21_quality_") as directory:
        compatibility_path = Path(directory) / "quality_metrics.json"
        compatibility_path.write_text(
            strict_json_text(
                {
                    "audio_quality": quality,
                    "error": existing.get("error"),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        yield compatibility_path


def build_manifest_row(
    metadata: dict[str, Any],
    result: dict[str, Any],
    audio_path: Path,
    stt_path: Path,
    speech_metrics_path: Path,
    output_path: Path,
    relative_root: Path,
    *,
    expected_audio_sha256: str | None = None,
) -> dict[str, Any]:
    coverage = result["coverage_summary"]
    agreement = result["agreement_summary"]
    statuses = result["dual_estimator_status"]
    harmonic = result["harmonic_support_summary"]
    diagnostics = result["shared_failure_diagnostics"]
    correction = result["correction_summary"]
    pitch = result["validated_pitch_summary"]
    loudness = result["loudness_summary"]
    frames = result.get("frames")
    derived = _validated_pitch_diagnostics(
        frames if isinstance(frames, list) else []
    )
    ending_pattern, ending_change = _ending_diagnostics(
        result.get("segment_prosody")
        if isinstance(result.get("segment_prosody"), list)
        else []
    )
    audio_sha256 = sha256_file(audio_path)
    warnings = list(result.get("warnings") or [])
    warnings.extend(str(item) for item in diagnostics.get("risk_flags") or [])
    if expected_audio_sha256 and audio_sha256 != expected_audio_sha256:
        warnings.append("AUDIO_SHA256_DIFFERS_FROM_CONVERSION_MANIFEST")
    unique_warnings: list[Any] = []
    seen_warnings: set[str] = set()
    for warning in warnings:
        key = json.dumps(
            warning,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        if key not in seen_warnings:
            seen_warnings.add(key)
            unique_warnings.append(warning)
    warnings = unique_warnings
    reliability = result.get("analysis_reliability_level")
    octave_corrections = sum(
        int(correction.get(name) or 0)
        for name in (
            "octave_halving_corrections",
            "octave_doubling_corrections",
        )
    )
    return {
        **metadata,
        "audio_file": relative_path(audio_path, relative_root),
        "audio_sha256": audio_sha256,
        "audio_duration_sec": result.get("audio_duration_sec"),
        "stt_json_file": relative_path(stt_path, relative_root),
        "speech_metrics_json_file": relative_path(
            speech_metrics_path, relative_root
        ),
        "prosody_v21_json_file": relative_path(output_path, relative_root),
        "schema_version": result.get("schema_version"),
        "pitch_median_hz": pitch.get("pitch_median_hz"),
        **derived,
        "pitch_range_semitones": pitch.get("pitch_range_semitones"),
        "ending_pattern": ending_pattern,
        "ending_pitch_change_semitones": ending_change,
        "total_frame_count": coverage.get("total_analysis_frame_count"),
        "voiced_frame_count": coverage.get("acoustic_voiced_frame_count"),
        "validated_frame_count": coverage.get(
            "validated_pitch_frame_count"
        ),
        "joint_valid_frame_count": coverage.get(
            "both_estimators_valid_frame_count"
        ),
        "validated_overall_coverage": coverage.get(
            "validated_pitch_overall_coverage_ratio"
        ),
        "validated_over_voiced_coverage": coverage.get(
            "validated_pitch_voiced_coverage_ratio"
        ),
        "joint_over_voiced_coverage": coverage.get(
            "dual_estimator_joint_valid_voiced_ratio"
        ),
        "conditioned_estimator_agreement": agreement.get(
            "estimator_agreement_ratio_conditioned_on_joint_valid"
        ),
        "agree_frame_count": statuses.get("both_valid_agree"),
        "disagree_frame_count": statuses.get("both_valid_disagree"),
        "acf_only_frame_count": statuses.get("autocorrelation_only"),
        "yin_only_frame_count": statuses.get("yin_only"),
        "both_invalid_frame_count": statuses.get("both_invalid"),
        "octave_correction_count": octave_corrections,
        "unresolved_ambiguity_count": correction.get(
            "unresolved_frame_count"
        ),
        "harmonic_support_diagnostics": harmonic,
        "clipping_ratio": loudness.get("clipping_frame_ratio"),
        "background_noise_warning": bool(
            diagnostics.get("background_noise_suspected")
        ),
        "low_pitch_coverage_warning": bool(
            diagnostics.get("low_joint_valid_coverage")
            or diagnostics.get("low_validated_voiced_coverage")
        ),
        "shared_octave_harmonic_risk": bool(
            diagnostics.get("shared_octave_error_risk")
            or diagnostics.get("harmonic_ambiguity_risk")
        ),
        "reliability_status": reliability,
        "internal_use_status": internal_use_status(reliability),
        "warnings": warnings,
        "error": None,
    }


def _saved_v21_result(result: dict[str, Any]) -> dict[str, Any]:
    saved = copy.deepcopy(result)
    saved["frames"] = []
    configuration = saved.setdefault("configuration", {})
    configuration["frames_omitted_from_output"] = True
    return saved


def _failure_row(
    metadata: dict[str, Any],
    audio_path: Path,
    stt_path: Path,
    metrics_path: Path,
    output_path: Path,
    root: Path,
    error: dict[str, str],
) -> dict[str, Any]:
    return {
        **metadata,
        "audio_file": relative_path(audio_path, root),
        "audio_sha256": sha256_file(audio_path) if audio_path.is_file() else "",
        "stt_json_file": relative_path(stt_path, root),
        "speech_metrics_json_file": relative_path(metrics_path, root),
        "prosody_v21_json_file": relative_path(output_path, root),
        "reliability_status": "analysis_failed",
        "internal_use_status": "analysis_unavailable",
        "warnings": [],
        "error": error,
    }


def analyze_session(
    conversion_manifest_path: Path | str,
    stt_pc_directory: Path | str,
    stt_phone_directory: Path | str,
    speech_metrics_pc_directory: Path | str,
    speech_metrics_phone_directory: Path | str,
    output_pc_directory: Path | str,
    output_phone_directory: Path | str,
    manifest_json_path: Path | str,
    manifest_csv_path: Path | str,
    relative_root: Path | str,
    *,
    analyzer: Callable[..., dict[str, Any]] = analyze_speech_prosody_v21,
) -> dict[str, Any]:
    root = Path(relative_root)
    manifest = load_json(
        conversion_manifest_path, "CONVERSION_MANIFEST_INVALID"
    )
    conversions = manifest.get("conversions")
    if not isinstance(conversions, list) or len(conversions) != EXPECTED_FILE_COUNT:
        raise SessionProsodyV21Error(
            "CONVERSION_MANIFEST_INVALID",
            f"Expected {EXPECTED_FILE_COUNT} conversion rows.",
        )
    sample_ids = [str(row.get("sample_id", "")) for row in conversions]
    if len(set(sample_ids)) != EXPECTED_FILE_COUNT:
        raise SessionProsodyV21Error(
            "CONVERSION_MANIFEST_INVALID", "Duplicate sample_id."
        )

    rows: list[dict[str, Any]] = []
    for conversion in conversions:
        metadata = parse_sample_id(str(conversion.get("sample_id", "")))
        device = metadata["device_code"]
        if device not in {PC_DEVICE, PHONE_DEVICE}:
            raise SessionProsodyV21Error(
                "CONVERSION_MANIFEST_INVALID", f"Unknown device: {device}"
            )
        destination = conversion.get("destination_path")
        if not isinstance(destination, str) or not destination:
            raise SessionProsodyV21Error(
                "CONVERSION_MANIFEST_INVALID",
                f"destination_path missing: {metadata['sample_id']}",
            )
        audio_path = Path(destination)
        if not audio_path.is_absolute():
            audio_path = root / audio_path
        stt_directory = (
            Path(stt_pc_directory) if device == PC_DEVICE else Path(stt_phone_directory)
        )
        metrics_directory = (
            Path(speech_metrics_pc_directory)
            if device == PC_DEVICE
            else Path(speech_metrics_phone_directory)
        )
        output_directory = (
            Path(output_pc_directory)
            if device == PC_DEVICE
            else Path(output_phone_directory)
        )
        stt_path = stt_directory / f"{metadata['sample_id']}.json"
        metrics_path = metrics_directory / f"{metadata['sample_id']}.json"
        output_path = output_directory / f"{metadata['sample_id']}.json"
        error: dict[str, str] | None = None
        try:
            if not audio_path.is_file():
                raise SessionProsodyV21Error(
                    "STANDARD_WAV_NOT_FOUND", str(audio_path)
                )
            if not metrics_path.is_file():
                raise SessionProsodyV21Error(
                    "SPEECH_METRICS_NOT_FOUND", str(metrics_path)
                )
            if not stt_path.is_file():
                raise SessionProsodyV21Error(
                    "PROSODY_V21_ANALYSIS_FAILED",
                    f"STT JSON not found: {stt_path}",
                )
            stt = load_json(stt_path, "PROSODY_V21_ANALYSIS_FAILED")
            if stt.get("error") is not None:
                raise SessionProsodyV21Error(
                    "PROSODY_V21_ANALYSIS_FAILED",
                    f"STT result has an error: {metadata['sample_id']}",
                )
            for field in (
                "speaker_code",
                "session_id",
                "script_id",
                "recording_condition",
                "repetition_index",
                "device_code",
                "capture_pair_key",
            ):
                if field in stt and str(stt[field]) != str(metadata[field]):
                    raise SessionProsodyV21Error(
                        "CONVERSION_MANIFEST_INVALID",
                        f"STT metadata mismatch for {metadata['sample_id']}: {field}",
                    )
            with core_quality_metrics_path(metrics_path) as core_metrics_path:
                result = analyzer(
                    audio_path,
                    stt_path,
                    core_metrics_path,
                    include_frames=True,
                )
            if not isinstance(result, dict):
                raise SessionProsodyV21Error(
                    "PROSODY_V21_RESULT_INVALID", "Analyzer returned non-object."
                )
            validate_v21_result(result)
            # The persisted provenance always points to the immutable SESSION
            # metrics file, never to an ephemeral compatibility view.
            result["quality_metrics_file"] = relative_path(metrics_path, root)
            row = build_manifest_row(
                metadata,
                result,
                audio_path,
                stt_path,
                metrics_path,
                output_path,
                root,
                expected_audio_sha256=conversion.get("destination_sha256"),
            )
            atomic_json(output_path, _saved_v21_result(result))
            rows.append(row)
        except SessionProsodyV21Error as exc:
            error = {"code": exc.code, "detail": exc.detail}
        except Exception as exc:
            error = {
                "code": "PROSODY_V21_ANALYSIS_FAILED",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        if error is not None:
            rows.append(
                _failure_row(
                    metadata,
                    audio_path,
                    stt_path,
                    metrics_path,
                    output_path,
                    root,
                    error,
                )
            )

    successful = [row for row in rows if row.get("error") is None]
    summary = {
        "total_files": len(rows),
        "successful_files": len(successful),
        "failed_files": len(rows) - len(successful),
        "pc_files": sum(row["device_code"] == PC_DEVICE for row in rows),
        "phone_files": sum(row["device_code"] == PHONE_DEVICE for row in rows),
        "clean_files": sum(
            row["recording_condition"] == "clean" for row in rows
        ),
        "natural_files": sum(
            row["recording_condition"] == "natural" for row in rows
        ),
    }
    payload = {
        "schema_version": "1.0",
        "prosody_schema_version": "2.1",
        "session_id": manifest.get("session_id", "SESSION001"),
        "description": (
            "Batch application of the frozen prosody v2.1 experimental "
            "baseline. No transcription, speech metrics, or audio conversion "
            "was executed."
        ),
        "summary": summary,
        "files": rows,
        "derived_field_notes": {
            "pitch_min_hz_and_pitch_max_hz": (
                "Extrema of v2.1 validated corrected F0 frames."
            ),
            "pitch_std_semitones": (
                "Population standard deviation around each file's validated "
                "median F0; no pitch correction value is applied."
            ),
            "intonation_variability": (
                "Alias of pitch_std_semitones for descriptive reporting only."
            ),
            "internal_use_status": (
                "Derived directly from the frozen v2.1 reliability label; it "
                "is not a score."
            ),
        },
        "limitations": [
            "Prosody v2.1 is an experimental baseline and not human ground truth.",
            "Estimator agreement does not guarantee correct F0; shared octave or harmonic ambiguity may remain.",
            "Pitch is not linked to gender, emotion, confidence, interview score, or selection outcome.",
            "No universal normal pitch range or SESSION001-specific threshold tuning is applied.",
        ],
        "error": (
            {
                "code": "SESSION_PROSODY_V21_FAILED",
                "detail": f"{summary['failed_files']} of {summary['total_files']} files failed.",
            }
            if summary["failed_files"]
            else None
        ),
    }
    atomic_json(manifest_json_path, payload)
    atomic_csv(manifest_csv_path, rows)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversion-manifest", type=Path, required=True)
    parser.add_argument("--stt-pc-dir", type=Path, required=True)
    parser.add_argument("--stt-phone-dir", type=Path, required=True)
    parser.add_argument("--speech-metrics-pc-dir", type=Path, required=True)
    parser.add_argument("--speech-metrics-phone-dir", type=Path, required=True)
    parser.add_argument("--output-pc-dir", type=Path, required=True)
    parser.add_argument("--output-phone-dir", type=Path, required=True)
    parser.add_argument("--manifest-json-output", type=Path, required=True)
    parser.add_argument("--manifest-csv-output", type=Path, required=True)
    parser.add_argument("--relative-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = analyze_session(
            args.conversion_manifest,
            args.stt_pc_dir,
            args.stt_phone_dir,
            args.speech_metrics_pc_dir,
            args.speech_metrics_phone_dir,
            args.output_pc_dir,
            args.output_phone_dir,
            args.manifest_json_output,
            args.manifest_csv_output,
            args.relative_root,
        )
    except SessionProsodyV21Error as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "SESSION_PROSODY_V21_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(strict_json_text({"summary": result["summary"], "error": result["error"]}))
    return 1 if result["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
