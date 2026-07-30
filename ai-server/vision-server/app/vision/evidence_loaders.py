"""Strict JSON loaders for fixture evidence registry components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.vision.evidence_mapping_models import EvidenceMetricMapping
from app.vision.evidence_models import (
    ApplicabilityScope,
    EvidenceRecord,
    EvidenceSource,
)
from app.vision.evidence_profile_models import EvidenceProfile
from app.vision.evidence_registry import EvidenceRegistry
from app.vision.metric_registry import FaceFitMetricRegistry
from app.vision.threshold_models import (
    MetricThresholdRule,
    ThresholdBand,
    ThresholdProfile,
)


class EvidenceLoadError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_strict_json(path: str | Path) -> Any:
    resolved = Path(path).resolve()
    try:
        return json.loads(
            resolved.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(value)
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise EvidenceLoadError(
            "INVALID_STRICT_EVIDENCE_JSON",
            f"{resolved.name}: {exc}",
        ) from exc


def _list(payload: Any, key: str) -> list[dict[str, Any]]:
    values = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not all(
        isinstance(value, dict) for value in values
    ):
        raise EvidenceLoadError(
            "INVALID_EVIDENCE_COLLECTION",
            f"Expected a list for {key}",
        )
    return values


class EvidenceSourceLoader:
    @staticmethod
    def load(path: str | Path) -> tuple[EvidenceSource, ...]:
        try:
            result = []
            for value in _list(load_strict_json(path), "sources"):
                payload = dict(value)
                payload["authors"] = tuple(payload.get("authors") or ())
                result.append(EvidenceSource(**payload))
            return tuple(result)
        except (TypeError, ValueError) as exc:
            raise EvidenceLoadError("INVALID_EVIDENCE_SOURCE", str(exc)) from exc


class EvidenceRecordLoader:
    @staticmethod
    def load(path: str | Path) -> tuple[EvidenceRecord, ...]:
        result: list[EvidenceRecord] = []
        try:
            for value in _list(
                load_strict_json(path),
                "evidence_records",
            ):
                payload = dict(value)
                scope = payload.get("applicability_scope")
                if isinstance(scope, dict):
                    scope_payload = dict(scope)
                    scope_payload["limitations"] = tuple(
                        scope_payload.get("limitations") or ()
                    )
                    payload["applicability_scope"] = ApplicabilityScope(
                        **scope_payload
                    )
                else:
                    payload["applicability_scope"] = None
                result.append(EvidenceRecord(**payload))
        except (TypeError, ValueError) as exc:
            raise EvidenceLoadError("INVALID_EVIDENCE_RECORD", str(exc)) from exc
        return tuple(result)


class MetricMappingLoader:
    @staticmethod
    def load(path: str | Path) -> tuple[EvidenceMetricMapping, ...]:
        try:
            result = []
            for value in _list(load_strict_json(path), "mappings"):
                payload = dict(value)
                payload["limitations"] = tuple(
                    payload.get("limitations") or ()
                )
                result.append(EvidenceMetricMapping(**payload))
            return tuple(result)
        except (TypeError, ValueError) as exc:
            raise EvidenceLoadError("INVALID_METRIC_MAPPING", str(exc)) from exc


class EvidenceProfileLoader:
    @staticmethod
    def load(path: str | Path) -> tuple[EvidenceProfile, ...]:
        try:
            result = []
            for value in _list(load_strict_json(path), "profiles"):
                payload = dict(value)
                for key in ("source_ids", "evidence_ids", "mapping_ids"):
                    payload[key] = tuple(payload.get(key) or ())
                result.append(EvidenceProfile(**payload))
            return tuple(result)
        except (TypeError, ValueError) as exc:
            raise EvidenceLoadError("INVALID_EVIDENCE_PROFILE", str(exc)) from exc


class ThresholdProfileLoader:
    @staticmethod
    def load(path: str | Path) -> tuple[ThresholdProfile, ...]:
        result: list[ThresholdProfile] = []
        try:
            for value in _list(
                load_strict_json(path),
                "threshold_profiles",
            ):
                profile = dict(value)
                rules: list[MetricThresholdRule] = []
                for rule_value in profile.get("rules") or []:
                    rule = dict(rule_value)
                    rule["bands"] = tuple(
                        ThresholdBand(**band)
                        for band in rule.get("bands") or []
                    )
                    rules.append(MetricThresholdRule(**rule))
                profile["rules"] = tuple(rules)
                result.append(ThresholdProfile(**profile))
        except (TypeError, ValueError) as exc:
            raise EvidenceLoadError("INVALID_THRESHOLD_PROFILE", str(exc)) from exc
        return tuple(result)


class EvidenceRegistryLoader:
    @staticmethod
    def load_directory(
        directory: str | Path,
        *,
        metric_registry: FaceFitMetricRegistry,
        execution_mode: str,
    ) -> EvidenceRegistry:
        root = Path(directory).resolve()
        required = {
            "sources": root / "sources.json",
            "records": root / "evidence_records.json",
            "mappings": root / "metric_mappings.json",
            "profiles": root / "evidence_profile.json",
            "thresholds": root / "threshold_profile.json",
        }
        missing = [path.name for path in required.values() if not path.is_file()]
        if missing:
            raise EvidenceLoadError(
                "EVIDENCE_FIXTURE_FILE_MISSING",
                ", ".join(sorted(missing)),
            )
        try:
            return EvidenceRegistry(
                sources=EvidenceSourceLoader.load(required["sources"]),
                records=EvidenceRecordLoader.load(required["records"]),
                mappings=MetricMappingLoader.load(required["mappings"]),
                profiles=EvidenceProfileLoader.load(required["profiles"]),
                threshold_profiles=ThresholdProfileLoader.load(
                    required["thresholds"]
                ),
                metric_registry=metric_registry,
                execution_mode=execution_mode,
            )
        except ValueError as exc:
            raise EvidenceLoadError(
                "EVIDENCE_REFERENCE_VALIDATION_FAILED",
                str(exc),
            ) from exc
