"""Canonical MediaPipe model metadata and integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core import config


MANIFEST_PATH = config.MODELS_DIR / "model_manifest.json"
ALLOWED_MODEL_HOST = "storage.googleapis.com"


class ModelRegistryError(RuntimeError):
    """A model registry or integrity error with a stable machine code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelDescriptor:
    model_id: str
    variant: str
    source_url: str
    local_path: Path
    allowed_host: str
    minimum_size_bytes: int


def get_model_descriptor(model_id: str) -> ModelDescriptor:
    """Return one canonical descriptor by model ID."""

    descriptors = {
        "face_landmarker": ModelDescriptor(
            model_id="face_landmarker",
            variant="float16_latest",
            source_url=(
                "https://storage.googleapis.com/mediapipe-models/"
                "face_landmarker/face_landmarker/float16/latest/"
                "face_landmarker.task"
            ),
            local_path=config.FACE_LANDMARKER_MODEL_PATH,
            allowed_host=ALLOWED_MODEL_HOST,
            minimum_size_bytes=1_000_000,
        ),
        "pose_landmarker": ModelDescriptor(
            model_id="pose_landmarker",
            variant="full_float16_latest",
            source_url=(
                "https://storage.googleapis.com/mediapipe-models/"
                "pose_landmarker/pose_landmarker_full/float16/latest/"
                "pose_landmarker_full.task"
            ),
            local_path=config.POSE_LANDMARKER_MODEL_PATH,
            allowed_host=ALLOWED_MODEL_HOST,
            minimum_size_bytes=5_000_000,
        ),
    }
    try:
        return descriptors[model_id]
    except KeyError as exc:
        raise ModelRegistryError(
            "MODEL_NOT_FOUND",
            f"Unknown model ID: {model_id}",
        ) from exc


def get_all_model_descriptors() -> tuple[ModelDescriptor, ModelDescriptor]:
    return (
        get_model_descriptor("face_landmarker"),
        get_model_descriptor("pose_landmarker"),
    )


def validate_model_url(descriptor: ModelDescriptor) -> None:
    """Allow only the canonical HTTPS host."""

    parsed = urlparse(descriptor.source_url)
    if parsed.scheme.lower() != "https" or parsed.hostname != descriptor.allowed_host:
        raise ModelRegistryError(
            "MODEL_URL_NOT_ALLOWED",
            f"Model URL is not allowed for {descriptor.model_id}.",
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {value}")


def read_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any] | None:
    """Read and structurally validate a strict model manifest."""

    if not path.is_file():
        return None
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ModelRegistryError(
            "MODEL_MANIFEST_INVALID",
            f"Model manifest is invalid: {exc}",
        ) from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.0"
        or not isinstance(manifest.get("models"), list)
    ):
        raise ModelRegistryError(
            "MODEL_MANIFEST_INVALID",
            "Model manifest has an unsupported structure.",
        )
    for entry in manifest["models"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("model_id"), str):
            raise ModelRegistryError(
                "MODEL_MANIFEST_INVALID",
                "Model manifest contains an invalid model entry.",
            )
    return manifest


def write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    """Write strict UTF-8 JSON through a same-directory temporary file."""

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def manifest_entry(
    model_id: str,
    manifest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if manifest is None:
        return None
    return next(
        (
            entry
            for entry in manifest["models"]
            if entry.get("model_id") == model_id
        ),
        None,
    )


def _looks_like_error_document(prefix: bytes) -> bool:
    normalized = prefix.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return normalized.startswith(
        (
            b"<!doctype html",
            b"<html",
            b"<?xml",
            b"<error",
            b"{",
            b"[",
        )
    )


def validate_model_file(
    path: Path,
    minimum_size_bytes: int,
) -> tuple[int, str]:
    """Validate size and reject common web error documents."""

    if not path.is_file():
        raise ModelRegistryError("MODEL_NOT_FOUND", f"Model file not found: {path}")
    size = path.stat().st_size
    if size == 0:
        raise ModelRegistryError("MODEL_FILE_EMPTY", f"Model file is empty: {path}")
    if size < minimum_size_bytes:
        raise ModelRegistryError(
            "MODEL_FILE_TOO_SMALL",
            f"Model file is below the minimum safe size: {path}",
        )
    with path.open("rb") as source:
        prefix = source.read(512)
    if _looks_like_error_document(prefix):
        raise ModelRegistryError(
            "MODEL_RESPONSE_INVALID",
            f"Model file resembles a web error document: {path}",
        )
    return size, sha256_file(path)


def inspect_model(
    descriptor: ModelDescriptor,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the model's stable readiness state."""

    path = descriptor.local_path.resolve(strict=False)
    if not path.is_file():
        return {"status": "missing", "path": str(path), "verified": False}
    try:
        size, checksum = validate_model_file(path, descriptor.minimum_size_bytes)
    except ModelRegistryError as exc:
        return {
            "status": "invalid_file",
            "path": str(path),
            "verified": False,
            "error_code": exc.code,
            "error": str(exc),
        }
    entry = manifest_entry(descriptor.model_id, manifest)
    if entry is None or entry.get("verified") is not True:
        return {
            "status": "unverified_existing_file",
            "path": str(path),
            "file_size_bytes": size,
            "sha256": checksum,
            "verified": False,
        }
    if entry.get("sha256") != checksum or entry.get("file_size_bytes") != size:
        return {
            "status": "checksum_mismatch",
            "path": str(path),
            "file_size_bytes": size,
            "sha256": checksum,
            "expected_sha256": entry.get("sha256"),
            "verified": False,
        }
    return {
        "status": "ready",
        "path": str(path),
        "file_size_bytes": size,
        "sha256": checksum,
        "verified": True,
        "manifest_entry": entry,
    }


def require_model_ready(
    descriptor: ModelDescriptor,
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    """Require a model to exist and match its manifest before loading."""

    manifest = read_manifest(manifest_path)
    state = inspect_model(descriptor, manifest)
    error_codes = {
        "missing": "MODEL_NOT_FOUND",
        "unverified_existing_file": "MODEL_UNVERIFIED",
        "checksum_mismatch": "MODEL_CHECKSUM_MISMATCH",
        "invalid_file": state.get("error_code", "MODEL_RESPONSE_INVALID"),
        "download_failed": "MODEL_DOWNLOAD_FAILED",
    }
    if state["status"] != "ready":
        raise ModelRegistryError(
            error_codes.get(state["status"], "MODEL_UNVERIFIED"),
            f"Model {descriptor.model_id} is not ready: {state['status']}",
        )
    return state


def manifest_local_path(path: Path) -> str:
    resolved = path.resolve(strict=False)
    try:
        return resolved.relative_to(config.VISION_SERVER_ROOT).as_posix()
    except ValueError:
        return str(resolved)
