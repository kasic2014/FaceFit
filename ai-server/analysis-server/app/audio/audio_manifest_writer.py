"""Strict, atomic JSON and text writers for audio preprocessing artifacts."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any


class ManifestWriteError(ValueError):
    pass


def ensure_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ManifestWriteError(f"Non-finite value at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            ensure_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            ensure_finite(item, f"{path}[{index}]")


def strict_json_bytes(value: Any) -> bytes:
    ensure_finite(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json_atomic(path: str | Path, value: Any) -> None:
    _atomic_bytes(Path(path), strict_json_bytes(value))


def write_text_atomic(path: str | Path, value: str) -> None:
    _atomic_bytes(Path(path), value.encode("utf-8"))
