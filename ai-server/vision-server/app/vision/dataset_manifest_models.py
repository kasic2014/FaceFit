"""Metadata-only dataset manifest and participant split contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.vision.data_collection_models import PARTICIPANT_RE, SHA256_RE, _required_id


SPLIT_NAMES = frozenset(
    {"DEVELOPMENT", "CALIBRATION", "VALIDATION", "HOLDOUT"}
)


@dataclass(frozen=True)
class DatasetManifest:
    manifest_id: str
    version: str
    status: str
    protocol_id: str
    participant_ids: tuple[str, ...]
    session_ids: tuple[str, ...]
    answer_ids: tuple[str, ...]
    artifact_sha256: dict[str, str]
    contains_media: bool
    contains_direct_identifiers: bool
    frozen: bool

    def __post_init__(self) -> None:
        _required_id(self.manifest_id, "manifest_id")
        _required_id(self.protocol_id, "protocol_id")
        if self.status != "DRAFT":
            raise ValueError("Stage 13 dataset manifest must remain DRAFT")
        if self.contains_media or self.contains_direct_identifiers or self.frozen:
            raise ValueError("fixture manifest must be metadata-only and unfrozen")
        if len(set(self.participant_ids)) != len(self.participant_ids):
            raise ValueError("duplicate participant_id in manifest")
        if any(not PARTICIPANT_RE.fullmatch(item) for item in self.participant_ids):
            raise ValueError("invalid participant_id in manifest")
        if len(set(self.session_ids)) != len(self.session_ids):
            raise ValueError("duplicate session_id in manifest")
        if len(set(self.answer_ids)) != len(self.answer_ids):
            raise ValueError("duplicate answer_id in manifest")
        if any(not SHA256_RE.fullmatch(value) for value in self.artifact_sha256.values()):
            raise ValueError("artifact hashes must be lowercase SHA-256")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in ("participant_ids", "session_ids", "answer_ids"):
            value[field] = list(getattr(self, field))
        value["artifact_sha256"] = dict(sorted(self.artifact_sha256.items()))
        return value


@dataclass(frozen=True)
class DatasetSplitAssignment:
    participant_id: str
    split: str
    seed: int
    assignment_method: str

    def __post_init__(self) -> None:
        if not PARTICIPANT_RE.fullmatch(self.participant_id):
            raise ValueError("invalid participant_id")
        if self.split not in SPLIT_NAMES:
            raise ValueError("invalid dataset split")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if self.assignment_method != "PARTICIPANT_LEVEL_DETERMINISTIC":
            raise ValueError("assignment must be participant-level deterministic")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
