"""Privacy-limited manifest and benchmark tools for prosody v2.1 artifacts.

The dataset benchmark measures within-speaker repeatability and recording
condition sensitivity. It never runs audio analysis and does not produce
speaker rankings, human-trait inference, or scores.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable


RECORDING_CONDITIONS = {
    "clean",
    "fast",
    "slow",
    "background_noise",
    "clipping",
    "natural",
    "other",
}
PROCESSING_STATUSES = {
    "registered",
    "artifacts_missing",
    "analysis_failed",
    "ready_for_benchmark",
    "excluded",
}
PROHIBITED_FIELDS = {
    "real_name",
    "email",
    "phone",
    "birth_date",
    "gender",
    "address",
    "account_id",
}
PUBLIC_MANIFEST_FIELDS = (
    "sample_id",
    "speaker_code",
    "session_id",
    "script_id",
    "repetition_index",
    "device_code",
    "environment_code",
    "recording_condition",
    "wav_path",
    "stt_json_path",
    "speech_metrics_json_path",
    "prosody_v21_json_path",
    "consent_confirmed",
    "created_at",
    "notes",
)
INTERNAL_MANIFEST_FIELDS = (
    "processing_status",
    "exclusion_reasons",
    "wav_sha256",
    "stt_json_sha256",
    "speech_metrics_json_sha256",
    "prosody_v21_json_sha256",
)
MANIFEST_FIELDS = PUBLIC_MANIFEST_FIELDS + INTERNAL_MANIFEST_FIELDS
COMPOSITE_KEY_FIELDS = (
    "speaker_code",
    "session_id",
    "script_id",
    "repetition_index",
    "device_code",
    "recording_condition",
)
SAMPLE_RESULT_FIELDS = (
    "sample_id",
    "speaker_code",
    "session_id",
    "script_id",
    "repetition_index",
    "device_code",
    "environment_code",
    "recording_condition",
    "processing_status",
    "exclusion_reasons",
    "estimated_noise_floor_dbfs",
    "speech_reference_dbfs",
    "snr_proxy_db",
    "clipping_frame_ratio",
    "non_word_voiced_ratio",
    "background_noise_suspected",
    "clipping_suspected",
    "pitch_median_hz",
    "pitch_range_semitones",
    "validated_pitch_overall_coverage_ratio",
    "validated_pitch_voiced_coverage_ratio",
    "dual_estimator_joint_valid_voiced_ratio",
    "estimator_agreement_ratio_conditioned_on_joint_valid",
    "estimator_agreement_ratio_over_acoustic_voiced",
    "harmonic_ambiguity_ratio",
    "agreement_frame_harmonic_ambiguity_ratio",
    "shared_octave_error_risk",
    "harmonic_ambiguity_risk",
    "reliability_status",
    "reliability_flags",
)
BENCHMARK_CSV_FIELDS = (
    "section",
    "group_id",
    "speaker_code",
    "script_id",
    "session_id",
    "device_code",
    "recording_condition",
    "sample_count",
    "ready_sample_count",
    "excluded_sample_count",
    "details_json",
)
LIMITATIONS = [
    "이 결과는 내부 측정 반복성과 장치·환경 민감도를 확인하기 위한 것이다.",
    "화자 간 절대 피치 비교의 기준이 아니다.",
    "면접 능력, 자신감, 긴장, 감정 또는 합격 가능성을 나타내지 않는다.",
    "데이터가 적은 그룹은 일반화할 수 없다.",
    "reliability status는 면접 평가가 아니라 측정값의 내부 사용 가능성이다.",
]


class ProsodyDatasetError(Exception):
    """A classified manifest or benchmark failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def strict_json_text(payload: Any) -> str:
    return json.dumps(
        _sanitize(payload),
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sanitize(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _sanitize(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(nested) for nested in value]
    return value


def _atomic_text(path: Path, text: str, *, encoding: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding=encoding, newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProsodyDatasetError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _validate_no_prohibited_fields(mapping: dict[str, Any]) -> None:
    found = sorted(PROHIBITED_FIELDS.intersection(mapping))
    if found:
        raise ProsodyDatasetError(
            "PROHIBITED_PERSONAL_FIELD",
            f"Prohibited manifest fields: {', '.join(found)}",
        )


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def _normalize_record(source: dict[str, Any]) -> dict[str, Any]:
    _validate_no_prohibited_fields(source)
    record = {field: source.get(field, "") for field in MANIFEST_FIELDS}
    try:
        record["repetition_index"] = int(record["repetition_index"])
    except (TypeError, ValueError) as exc:
        raise ProsodyDatasetError(
            "INVALID_REPETITION_INDEX",
            "repetition_index must be an integer.",
        ) from exc
    record["consent_confirmed"] = _parse_bool(record["consent_confirmed"])
    reasons = record.get("exclusion_reasons")
    if isinstance(reasons, str):
        record["exclusion_reasons"] = [
            item for item in reasons.split("|") if item
        ]
    elif isinstance(reasons, list):
        record["exclusion_reasons"] = [str(item) for item in reasons]
    else:
        record["exclusion_reasons"] = []
    return record


def _json_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "description": (
            "Anonymous internal prosody repeatability and recording-condition "
            "validation manifest. No sensitive personal data."
        ),
        "fields": list(MANIFEST_FIELDS),
        "samples": records,
    }


def write_manifest_csv_atomic(
    path: Path | str, records: list[dict[str, Any]]
) -> None:
    output = Path(path)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            for source in records:
                record = _normalize_record(source)
                row = dict(record)
                row["consent_confirmed"] = (
                    "true" if record["consent_confirmed"] else "false"
                )
                row["exclusion_reasons"] = "|".join(
                    record["exclusion_reasons"]
                )
                writer.writerow({field: row.get(field, "") for field in MANIFEST_FIELDS})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except (OSError, csv.Error) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProsodyDatasetError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def write_manifest_json_atomic(
    path: Path | str, records: list[dict[str, Any]]
) -> None:
    output = Path(path)
    text = strict_json_text(_json_payload(records)) + "\n"
    _atomic_text(output, text, encoding="utf-8")


def manifest_pair_paths(path: Path | str) -> tuple[Path, Path]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        return source.with_suffix(".csv"), source
    if source.suffix.lower() == ".csv":
        return source, source.with_suffix(".json")
    raise ProsodyDatasetError(
        "UNSUPPORTED_MANIFEST_FORMAT",
        "Manifest path must end in .csv or .json.",
    )


def write_manifest_pair_atomic(
    path: Path | str, records: list[dict[str, Any]]
) -> tuple[Path, Path]:
    csv_path, json_path = manifest_pair_paths(path)
    write_manifest_csv_atomic(csv_path, records)
    write_manifest_json_atomic(json_path, records)
    return csv_path, json_path


def create_empty_manifest(path: Path | str) -> tuple[Path, Path]:
    return write_manifest_pair_atomic(path, [])


def read_manifest(path: Path | str) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise ProsodyDatasetError("MANIFEST_NOT_FOUND", str(source))
    try:
        if source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames is None:
                    raise ProsodyDatasetError(
                        "MANIFEST_SCHEMA_INVALID", "CSV has no header."
                    )
                prohibited = PROHIBITED_FIELDS.intersection(reader.fieldnames)
                if prohibited:
                    raise ProsodyDatasetError(
                        "PROHIBITED_PERSONAL_FIELD",
                        f"Prohibited manifest fields: {', '.join(sorted(prohibited))}",
                    )
                missing = set(PUBLIC_MANIFEST_FIELDS).difference(
                    reader.fieldnames
                )
                if missing:
                    raise ProsodyDatasetError(
                        "MANIFEST_SCHEMA_INVALID",
                        f"Missing fields: {', '.join(sorted(missing))}",
                    )
                return [_normalize_record(dict(row)) for row in reader]
        if source.suffix.lower() == ".json":
            payload = json.loads(
                source.read_text(encoding="utf-8-sig"),
                parse_constant=lambda token: (_ for _ in ()).throw(
                    ValueError(f"Non-finite JSON constant: {token}")
                ),
            )
            if not isinstance(payload, dict):
                raise ProsodyDatasetError(
                    "MANIFEST_SCHEMA_INVALID", "JSON root must be an object."
                )
            _validate_no_prohibited_fields(payload)
            samples = payload.get("samples")
            if not isinstance(samples, list):
                raise ProsodyDatasetError(
                    "MANIFEST_SCHEMA_INVALID", "samples must be an array."
                )
            return [_normalize_record(dict(item)) for item in samples]
        raise ProsodyDatasetError(
            "UNSUPPORTED_MANIFEST_FORMAT",
            "Manifest path must end in .csv or .json.",
        )
    except ProsodyDatasetError:
        raise
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, ValueError) as exc:
        raise ProsodyDatasetError(
            "MANIFEST_READ_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _load_strict_json(path: Path, reason: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"Non-finite JSON constant: {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProsodyDatasetError(
            reason, f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProsodyDatasetError(reason, "JSON root must be an object.")
    return payload


def _relative_path(path: Path | str, workspace_root: Path) -> str:
    source = Path(path)
    resolved = (
        source.resolve()
        if source.is_absolute()
        else (workspace_root / source).resolve()
    )
    try:
        return resolved.relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return Path(os.path.relpath(resolved, workspace_root.resolve())).as_posix()


def _resolve_path(path_text: Any, workspace_root: Path) -> Path:
    source = Path(str(path_text))
    return source if source.is_absolute() else workspace_root / source


def _validate_identity(record: dict[str, Any]) -> None:
    for field in (
        "sample_id",
        "speaker_code",
        "session_id",
        "script_id",
        "device_code",
        "environment_code",
    ):
        if not str(record.get(field, "")).strip():
            raise ProsodyDatasetError(
                "REQUIRED_FIELD_MISSING", f"{field} is required."
            )
    condition = str(record.get("recording_condition", ""))
    if condition not in RECORDING_CONDITIONS:
        raise ProsodyDatasetError(
            "INVALID_RECORDING_CONDITION", condition
        )


def _artifact_assessment(
    record: dict[str, Any],
    workspace_root: Path,
    *,
    verify_stored_hashes: bool,
) -> tuple[str, list[str], dict[str, str], dict[str, Any] | None, dict[str, Any] | None]:
    reasons = list(record.get("exclusion_reasons") or [])
    paths = {
        "wav": _resolve_path(record["wav_path"], workspace_root),
        "stt": _resolve_path(record["stt_json_path"], workspace_root),
        "metrics": _resolve_path(
            record["speech_metrics_json_path"], workspace_root
        ),
        "prosody": _resolve_path(
            record["prosody_v21_json_path"], workspace_root
        ),
    }
    missing_reasons = {
        "wav": "wav_missing",
        "stt": "stt_missing",
        "metrics": "quality_metrics_missing",
        "prosody": "prosody_missing",
    }
    hashes: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            reasons.append(missing_reasons[name])
            hashes[f"{name}_sha256"] = ""
        else:
            hashes[f"{name}_sha256"] = sha256_file(path)

    if not record["consent_confirmed"]:
        reasons.append("consent_not_confirmed")
    if any(reason in reasons for reason in missing_reasons.values()):
        status = "artifacts_missing"
        if "consent_not_confirmed" in reasons:
            status = "excluded"
        return status, list(dict.fromkeys(reasons)), hashes, None, None

    stt: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    prosody: dict[str, Any] | None = None
    try:
        stt = _load_strict_json(paths["stt"], "stt_json_invalid")
    except ProsodyDatasetError:
        reasons.append("stt_json_invalid")
    try:
        metrics = _load_strict_json(
            paths["metrics"], "quality_metrics_json_invalid"
        )
    except ProsodyDatasetError:
        reasons.append("quality_metrics_json_invalid")
    try:
        prosody = _load_strict_json(paths["prosody"], "prosody_json_invalid")
    except ProsodyDatasetError:
        reasons.append("prosody_json_invalid")
    if prosody is not None:
        if str(prosody.get("schema_version")) != "2.1":
            reasons.append("unsupported_schema")
        if prosody.get("error") is not None:
            reasons.append("prosody_error")

    if verify_stored_hashes:
        stored_names = {
            "wav": "wav_sha256",
            "stt": "stt_json_sha256",
            "metrics": "speech_metrics_json_sha256",
            "prosody": "prosody_v21_json_sha256",
        }
        for name, stored_field in stored_names.items():
            stored = str(record.get(stored_field, "")).strip().lower()
            if stored and stored != hashes[f"{name}_sha256"]:
                reasons.append("hash_mismatch")

    reasons = list(dict.fromkeys(reasons))
    if "consent_not_confirmed" in reasons:
        status = "excluded"
    elif any(
        reason
        in {
            "stt_json_invalid",
            "quality_metrics_json_invalid",
            "prosody_json_invalid",
            "unsupported_schema",
            "prosody_error",
        }
        for reason in reasons
    ):
        status = "analysis_failed"
    elif "hash_mismatch" in reasons:
        status = "excluded"
    elif record.get("processing_status") == "excluded":
        status = "excluded"
    else:
        status = "ready_for_benchmark"
    return status, reasons, hashes, metrics, prosody


def register_sample(
    manifest_path: Path | str,
    sample: dict[str, Any],
    *,
    workspace_root: Path | str | None = None,
) -> dict[str, Any]:
    """Register one sample and atomically update CSV and JSON manifests."""
    _validate_no_prohibited_fields(sample)
    root = Path(workspace_root) if workspace_root is not None else Path.cwd()
    records = read_manifest(manifest_path)
    record_source = dict(sample)
    for field in (
        "wav_path",
        "stt_json_path",
        "speech_metrics_json_path",
        "prosody_v21_json_path",
    ):
        if field not in record_source:
            raise ProsodyDatasetError(
                "REQUIRED_FIELD_MISSING", f"{field} is required."
            )
        record_source[field] = _relative_path(record_source[field], root)
    record_source.setdefault("created_at", utc_now_text())
    record_source.setdefault("notes", "")
    record_source.setdefault("processing_status", "registered")
    record_source.setdefault("exclusion_reasons", [])
    record = _normalize_record(record_source)
    _validate_identity(record)

    if any(existing["sample_id"] == record["sample_id"] for existing in records):
        raise ProsodyDatasetError(
            "DUPLICATE_SAMPLE_ID", str(record["sample_id"])
        )
    composite = tuple(record[field] for field in COMPOSITE_KEY_FIELDS)
    if any(
        tuple(existing[field] for field in COMPOSITE_KEY_FIELDS) == composite
        for existing in records
    ):
        raise ProsodyDatasetError(
            "DUPLICATE_COMPOSITE_KEY",
            "|".join(str(value) for value in composite),
        )

    status, reasons, hashes, _, _ = _artifact_assessment(
        record, root, verify_stored_hashes=False
    )
    record["processing_status"] = status
    record["exclusion_reasons"] = reasons
    record["wav_sha256"] = hashes.get("wav_sha256", "")
    record["stt_json_sha256"] = hashes.get("stt_sha256", "")
    record["speech_metrics_json_sha256"] = hashes.get(
        "metrics_sha256", ""
    )
    record["prosody_v21_json_sha256"] = hashes.get(
        "prosody_sha256", ""
    )
    records.append(record)
    write_manifest_pair_atomic(manifest_path, records)
    return record


def _value(mapping: dict[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _sanitize(current)


def _sample_result(
    record: dict[str, Any],
    workspace_root: Path,
) -> dict[str, Any]:
    status, reasons, _, metrics, prosody = _artifact_assessment(
        record, workspace_root, verify_stored_hashes=True
    )
    quality = (
        metrics.get("audio_quality")
        if isinstance(metrics, dict)
        and isinstance(metrics.get("audio_quality"), dict)
        else {}
    )
    prosody = prosody or {}
    reliability = (
        prosody.get("prosody_reliability")
        if isinstance(prosody.get("prosody_reliability"), dict)
        else {}
    )
    quality_flags = {
        str(value) for value in quality.get("reliability_flags", [])
    }
    clipping_ratio = _value(quality, "clipping_frame_ratio")
    clipping_suspected = (
        "clipping_suspected" in quality_flags
        or bool(_value(reliability, "clipping_suspected"))
        or (
            isinstance(clipping_ratio, (int, float))
            and clipping_ratio > 0.01
        )
    )
    result = {
        field: record.get(field)
        for field in (
            "sample_id",
            "speaker_code",
            "session_id",
            "script_id",
            "repetition_index",
            "device_code",
            "environment_code",
            "recording_condition",
        )
    }
    result.update(
        {
            "processing_status": status,
            "exclusion_reasons": reasons,
            "estimated_noise_floor_dbfs": _value(
                quality, "estimated_noise_floor_dbfs"
            ),
            "speech_reference_dbfs": _value(
                quality, "speech_reference_dbfs"
            ),
            "snr_proxy_db": _value(quality, "snr_proxy_db"),
            "clipping_frame_ratio": clipping_ratio,
            "non_word_voiced_ratio": _value(
                quality, "non_word_voiced_ratio"
            ),
            "background_noise_suspected": _value(
                quality, "background_noise_suspected"
            ),
            "clipping_suspected": clipping_suspected,
            "pitch_median_hz": _value(
                prosody, "validated_pitch_summary", "pitch_median_hz"
            ),
            "pitch_range_semitones": _value(
                prosody,
                "validated_pitch_summary",
                "pitch_range_semitones",
            ),
            "validated_pitch_overall_coverage_ratio": _value(
                prosody,
                "coverage_summary",
                "validated_pitch_overall_coverage_ratio",
            ),
            "validated_pitch_voiced_coverage_ratio": _value(
                prosody,
                "coverage_summary",
                "validated_pitch_voiced_coverage_ratio",
            ),
            "dual_estimator_joint_valid_voiced_ratio": _value(
                prosody,
                "coverage_summary",
                "dual_estimator_joint_valid_voiced_ratio",
            ),
            "estimator_agreement_ratio_conditioned_on_joint_valid": _value(
                prosody,
                "agreement_summary",
                "estimator_agreement_ratio_conditioned_on_joint_valid",
            ),
            "estimator_agreement_ratio_over_acoustic_voiced": _value(
                prosody,
                "agreement_summary",
                "estimator_agreement_ratio_over_acoustic_voiced",
            ),
            "harmonic_ambiguity_ratio": _value(
                prosody,
                "harmonic_support_summary",
                "harmonic_ambiguity_ratio",
            ),
            "agreement_frame_harmonic_ambiguity_ratio": _value(
                prosody,
                "harmonic_support_summary",
                "agreement_harmonic_ambiguity_ratio",
            ),
            "shared_octave_error_risk": _value(
                prosody,
                "shared_failure_diagnostics",
                "shared_octave_error_risk",
            ),
            "harmonic_ambiguity_risk": _value(
                prosody,
                "shared_failure_diagnostics",
                "harmonic_ambiguity_risk",
            ),
            "reliability_status": prosody.get(
                "analysis_reliability_level"
            ),
            "reliability_flags": list(
                reliability.get("reliability_flags") or []
            ),
        }
    )
    if status != "ready_for_benchmark":
        for field in SAMPLE_RESULT_FIELDS[10:]:
            if field not in {
                "background_noise_suspected",
                "clipping_suspected",
                "reliability_flags",
            }:
                result[field] = None
        result["background_noise_suspected"] = None
        result["clipping_suspected"] = None
        result["reliability_flags"] = []
        result["reliability_status"] = "unknown"
    return result


def median_mad(values: Iterable[Any]) -> tuple[float | None, float | None]:
    valid = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    if not valid:
        return None, None
    center = float(median(valid))
    deviation = float(median(abs(value - center) for value in valid))
    return round(center, 6), round(deviation, 6)


def _status_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(
        str(sample.get("reliability_status") or "unknown")
        for sample in samples
    )
    return {
        "sufficient_for_experimental_summary": counter[
            "sufficient_for_experimental_summary"
        ],
        "limited": counter["limited"],
        "unreliable": counter["unreliable"],
        "unknown": counter["unknown"],
    }


def build_repeatability_groups(
    samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        if sample.get("processing_status") != "ready_for_benchmark":
            continue
        key = (
            sample["speaker_code"],
            sample["script_id"],
            sample["device_code"],
            sample["recording_condition"],
        )
        grouped[key].append(sample)
    results = []
    for key, group in sorted(grouped.items()):
        if len({item["repetition_index"] for item in group}) < 2:
            continue
        pitch_center, pitch_mad = median_mad(
            item["pitch_median_hz"] for item in group
        )
        range_center, range_mad = median_mad(
            item["pitch_range_semitones"] for item in group
        )
        coverage_center, coverage_mad = median_mad(
            item["validated_pitch_voiced_coverage_ratio"] for item in group
        )
        harmonic_center, harmonic_mad = median_mad(
            item["harmonic_ambiguity_ratio"] for item in group
        )
        results.append(
            {
                "speaker_code": key[0],
                "script_id": key[1],
                "device_code": key[2],
                "recording_condition": key[3],
                "sample_count": len(group),
                "pitch_median_group_median_hz": pitch_center,
                "pitch_median_mad_hz": pitch_mad,
                "pitch_median_relative_mad": (
                    round(pitch_mad / abs(pitch_center), 6)
                    if pitch_center not in (None, 0) and pitch_mad is not None
                    else None
                ),
                "pitch_range_group_median_semitones": range_center,
                "pitch_range_mad_semitones": range_mad,
                "voiced_coverage_group_median": coverage_center,
                "voiced_coverage_mad": coverage_mad,
                "harmonic_ambiguity_group_median": harmonic_center,
                "harmonic_ambiguity_mad": harmonic_mad,
                "reliability_status_counts": _status_counts(group),
            }
        )
    return results


def _max_difference(values: Iterable[Any]) -> float | None:
    valid = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    return round(max(valid) - min(valid), 6) if len(valid) >= 2 else None


def build_device_comparison_groups(
    samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        if sample.get("processing_status") != "ready_for_benchmark":
            continue
        key = (
            sample["speaker_code"],
            sample["script_id"],
            sample["session_id"],
            sample["repetition_index"],
            sample["recording_condition"],
        )
        grouped[key].append(sample)
    results = []
    for key, group in sorted(grouped.items()):
        devices = {item["device_code"] for item in group}
        if len(devices) < 2:
            continue
        pitch = [
            float(item["pitch_median_hz"])
            for item in group
            if isinstance(item.get("pitch_median_hz"), (int, float))
            and item["pitch_median_hz"] > 0
        ]
        semitone_difference = (
            round(12.0 * math.log2(max(pitch) / min(pitch)), 6)
            if len(pitch) >= 2
            else None
        )
        results.append(
            {
                "speaker_code": key[0],
                "script_id": key[1],
                "session_id": key[2],
                "repetition_index": key[3],
                "recording_condition": key[4],
                "device_count": len(devices),
                "pitch_median_max_difference_hz": _max_difference(pitch),
                "pitch_median_max_difference_semitones": semitone_difference,
                "pitch_range_max_difference_semitones": _max_difference(
                    item["pitch_range_semitones"] for item in group
                ),
                "voiced_coverage_max_difference": _max_difference(
                    item["validated_pitch_voiced_coverage_ratio"]
                    for item in group
                ),
                "harmonic_ambiguity_max_difference": _max_difference(
                    item["harmonic_ambiguity_ratio"] for item in group
                ),
                "reliability_status_by_device": {
                    str(item["device_code"]): str(
                        item.get("reliability_status") or "unknown"
                    )
                    for item in group
                },
            }
        )
    return results


def build_condition_summary(
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[str(sample["recording_condition"])].append(sample)
    result = {}
    metric_fields = {
        "pitch_voiced_coverage": "validated_pitch_voiced_coverage_ratio",
        "joint_valid_voiced_ratio": "dual_estimator_joint_valid_voiced_ratio",
        "harmonic_ambiguity": "harmonic_ambiguity_ratio",
        "clipping_ratio": "clipping_frame_ratio",
        "snr_proxy": "snr_proxy_db",
    }
    for condition, group in sorted(grouped.items()):
        ready = [
            item
            for item in group
            if item.get("processing_status") == "ready_for_benchmark"
        ]
        summary: dict[str, Any] = {
            "sample_count": len(group),
            "ready_sample_count": len(ready),
            "excluded_sample_count": len(group) - len(ready),
            "reliability_status_counts": _status_counts(group),
        }
        for prefix, field in metric_fields.items():
            center, deviation = median_mad(item.get(field) for item in ready)
            summary[f"{prefix}_median"] = center
            summary[f"{prefix}_mad"] = deviation
        result[condition] = summary
    return result


def benchmark_dataset(
    manifest_file: Path | str,
    *,
    workspace_root: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root) if workspace_root is not None else Path.cwd()
    result = {
        "schema_version": "1.0",
        "manifest_file": str(manifest_file),
        "generated_at": utc_now_text(),
        "dataset_summary": {},
        "reliability_summary": {},
        "repeatability_groups": [],
        "device_comparison_groups": [],
        "condition_summary": {},
        "sample_results": [],
        "limitations": list(LIMITATIONS),
        "warnings": [],
        "error": None,
    }
    try:
        records = read_manifest(manifest_file)
        sample_results = [_sample_result(record, root) for record in records]
        ready = [
            item
            for item in sample_results
            if item["processing_status"] == "ready_for_benchmark"
        ]
        result["dataset_summary"] = {
            "total_samples": len(sample_results),
            "ready_samples": len(ready),
            "excluded_samples": len(sample_results) - len(ready),
            "speaker_count": len(
                {item["speaker_code"] for item in sample_results}
            ),
            "device_count": len(
                {item["device_code"] for item in sample_results}
            ),
            "script_count": len(
                {item["script_id"] for item in sample_results}
            ),
            "session_count": len(
                {item["session_id"] for item in sample_results}
            ),
            "condition_counts": dict(
                sorted(
                    Counter(
                        item["recording_condition"] for item in sample_results
                    ).items()
                )
            ),
        }
        result["reliability_summary"] = _status_counts(sample_results)
        result["repeatability_groups"] = build_repeatability_groups(
            sample_results
        )
        result["device_comparison_groups"] = build_device_comparison_groups(
            sample_results
        )
        result["condition_summary"] = build_condition_summary(sample_results)
        result["sample_results"] = sample_results
        for item in sample_results:
            if item["processing_status"] != "ready_for_benchmark":
                result["warnings"].append(
                    {
                        "code": "SAMPLE_EXCLUDED",
                        "sample_id": item["sample_id"],
                        "reasons": item["exclusion_reasons"],
                    }
                )
    except ProsodyDatasetError as exc:
        result["error"] = {"code": exc.code, "detail": exc.detail}
    except Exception as exc:
        result["error"] = {
            "code": "BENCHMARK_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return _sanitize(result)


def write_json_atomic(path: Path | str, payload: Any) -> None:
    _atomic_text(
        Path(path), strict_json_text(payload) + "\n", encoding="utf-8"
    )


def _compact_json(value: Any) -> str:
    return json.dumps(
        _sanitize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def write_csv_atomic(
    path: Path | str,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
    output = Path(path)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except (OSError, csv.Error) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProsodyDatasetError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def _benchmark_csv_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "section": "dataset_summary",
            "group_id": "dataset",
            "sample_count": result["dataset_summary"].get("total_samples"),
            "ready_sample_count": result["dataset_summary"].get(
                "ready_samples"
            ),
            "excluded_sample_count": result["dataset_summary"].get(
                "excluded_samples"
            ),
            "details_json": _compact_json(result["dataset_summary"]),
        },
        {
            "section": "reliability_summary",
            "group_id": "reliability",
            "details_json": _compact_json(result["reliability_summary"]),
        },
    ]
    for index, group in enumerate(result["repeatability_groups"], 1):
        rows.append(
            {
                "section": "repeatability",
                "group_id": f"repeatability_{index:03d}",
                "speaker_code": group["speaker_code"],
                "script_id": group["script_id"],
                "device_code": group["device_code"],
                "recording_condition": group["recording_condition"],
                "sample_count": group["sample_count"],
                "details_json": _compact_json(group),
            }
        )
    for index, group in enumerate(result["device_comparison_groups"], 1):
        rows.append(
            {
                "section": "device_comparison",
                "group_id": f"device_{index:03d}",
                "speaker_code": group["speaker_code"],
                "script_id": group["script_id"],
                "session_id": group["session_id"],
                "recording_condition": group["recording_condition"],
                "details_json": _compact_json(group),
            }
        )
    for condition, group in result["condition_summary"].items():
        rows.append(
            {
                "section": "condition",
                "group_id": condition,
                "recording_condition": condition,
                "sample_count": group["sample_count"],
                "ready_sample_count": group["ready_sample_count"],
                "excluded_sample_count": group["excluded_sample_count"],
                "details_json": _compact_json(group),
            }
        )
    return rows


def write_benchmark_outputs(
    result: dict[str, Any],
    output_json: Path | str,
    output_csv: Path | str,
    sample_output_csv: Path | str,
) -> None:
    if result.get("error") is not None:
        raise ProsodyDatasetError(
            "BENCHMARK_RESULT_INVALID",
            str(result["error"]),
        )
    write_json_atomic(output_json, result)
    write_csv_atomic(
        output_csv,
        BENCHMARK_CSV_FIELDS,
        _benchmark_csv_rows(result),
    )
    rows = []
    for source in result["sample_results"]:
        row = dict(source)
        row["exclusion_reasons"] = "|".join(
            source.get("exclusion_reasons") or []
        )
        row["reliability_flags"] = "|".join(
            source.get("reliability_flags") or []
        )
        rows.append(row)
    write_csv_atomic(sample_output_csv, SAMPLE_RESULT_FIELDS, rows)


__all__ = [
    "BENCHMARK_CSV_FIELDS",
    "COMPOSITE_KEY_FIELDS",
    "LIMITATIONS",
    "MANIFEST_FIELDS",
    "PROCESSING_STATUSES",
    "PROHIBITED_FIELDS",
    "PUBLIC_MANIFEST_FIELDS",
    "RECORDING_CONDITIONS",
    "SAMPLE_RESULT_FIELDS",
    "ProsodyDatasetError",
    "benchmark_dataset",
    "build_condition_summary",
    "build_device_comparison_groups",
    "build_repeatability_groups",
    "create_empty_manifest",
    "median_mad",
    "read_manifest",
    "register_sample",
    "sha256_file",
    "strict_json_text",
    "write_benchmark_outputs",
    "write_manifest_pair_atomic",
]
