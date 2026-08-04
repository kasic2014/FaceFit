"""Load and validate JSON scoring profiles and inventories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .profile_validator import validate_profile
from .scoring_errors import PROFILE_INVALID, ScoringError


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ScoringError(PROFILE_INVALID, f"Invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ScoringError(PROFILE_INVALID, "JSON root must be an object")
    return payload


def load_inventory(path: str | Path) -> dict[str, Any]:
    inventory = load_json(path)
    rows = inventory.get("metrics")
    if not isinstance(rows, list):
        raise ScoringError(PROFILE_INVALID, "Inventory metrics must be an array")
    ids = [row.get("metricId") for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or len(ids) != len(set(ids)):
        raise ScoringError(PROFILE_INVALID, "Inventory metric IDs must be unique")
    return inventory


def load_profile(path: str | Path, inventory: dict[str, Any]) -> tuple[dict[str, Any], str]:
    profile = load_json(path)
    validation = validate_profile(profile, inventory)
    return profile, validation["profileHash"]
