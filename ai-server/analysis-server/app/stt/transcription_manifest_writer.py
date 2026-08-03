"""Stage 25 strict writers and atomic session-directory replacement."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any

from app.audio.audio_manifest_writer import write_json_atomic, write_text_atomic


def write_answer(path: str | Path, value: dict[str, Any]) -> None:
    write_json_atomic(path, value)


def write_manifest(path: str | Path, value: dict[str, Any]) -> None:
    write_json_atomic(path, value)


def replace_directory(staged: Path, destination: Path, backup: Path) -> None:
    moved_existing = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_existing = True
        os.replace(staged, destination)
        if moved_existing:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if moved_existing and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise


__all__ = [
    "replace_directory",
    "write_answer",
    "write_json_atomic",
    "write_manifest",
    "write_text_atomic",
]
