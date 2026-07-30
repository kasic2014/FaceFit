"""Strict deterministic JSON serialization for baseline model artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any


def _payload(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    return value


def dumps_strict(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(
        _payload(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
        indent=indent,
    )
