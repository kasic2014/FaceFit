"""Privacy-aware, finite, atomic JSON writer."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path, PureWindowsPath
import tempfile
from typing import Any

BANNED_KEYS = {
    "participantid", "consent", "raterid", "absolutepath", "videofilename",
    "audiofilename", "modelcachepath", "transcripttext", "emotion", "personality",
    "confidence", "anxiety", "passprobability", "gender", "age", "race",
    "nationality", "disability", "disease", "religion", "hometown",
}


def validate_strict_json(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).replace("_", "").lower()
            if normalized in BANNED_KEYS:
                raise ValueError(f"Forbidden field at {path}.{key}")
            validate_strict_json(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            validate_strict_json(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Non-finite number at {path}")
    elif isinstance(value, str):
        if PureWindowsPath(value).is_absolute() or value.startswith("/"):
            raise ValueError(f"Absolute path at {path}")


def strict_json_bytes(value: Any) -> bytes:
    validate_strict_json(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_json_atomic(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = strict_json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
