"""Immutable, versioned evidence profile models."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from app.vision.evidence_models import (
    EvidenceStatus,
    _enum_value,
    _required,
)


SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)


class EvidenceDomain(str, Enum):
    HEAD_POSE = "HEAD_POSE"
    POSTURE = "POSTURE"
    GAZE = "GAZE"
    VOICE = "VOICE"
    CONTENT = "CONTENT"
    COMPOSITE = "COMPOSITE"


def validate_semver(version: str) -> None:
    if not isinstance(version, str) or not SEMVER_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid semantic version: {version}")


def validate_iso_datetime(value: str, name: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc


@dataclass(frozen=True)
class EvidenceProfile:
    profile_id: str
    version: str
    name: str
    description: str
    source_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    domain: str
    status: str
    created_at: str
    updated_at: str
    supersedes_version: str | None
    notes: str | None

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_id, "profile_id"),
            (self.name, "name"),
            (self.description, "description"),
        ):
            _required(value, name)
        validate_semver(self.version)
        _enum_value(self.domain, EvidenceDomain, "domain")
        _enum_value(self.status, EvidenceStatus, "status")
        validate_iso_datetime(self.created_at, "created_at")
        validate_iso_datetime(self.updated_at, "updated_at")
        for values, name in (
            (self.source_ids, "source_ids"),
            (self.evidence_ids, "evidence_ids"),
            (self.mapping_ids, "mapping_ids"),
        ):
            if not values or len(values) != len(set(values)):
                raise ValueError(f"{name} must be non-empty and unique")
        if self.supersedes_version is not None:
            validate_semver(self.supersedes_version)
            if self.supersedes_version == self.version:
                raise ValueError("supersedes_version cannot reference itself")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
