"""Safely download and pin the official MediaPipe model baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision.model_registry import (  # noqa: E402
    MANIFEST_PATH,
    ModelDescriptor,
    ModelRegistryError,
    get_all_model_descriptors,
    inspect_model,
    manifest_entry,
    manifest_local_path,
    read_manifest,
    validate_model_file,
    validate_model_url,
    write_json_atomic,
)


REPORT_PATH = VISION_SERVER_ROOT / "model_setup_report.json"
TEXT_ERROR_CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "text/html",
    "text/plain",
    "text/xml",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _response_content_type(response: Any) -> str:
    raw_value = response.headers.get("Content-Type", "")
    return raw_value.split(";", 1)[0].strip().lower()


def download_model(
    descriptor: ModelDescriptor,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Download one model to a temporary file and atomically commit it."""

    validate_model_url(descriptor)
    destination = descriptor.local_path.resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".part",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            try:
                with opener(descriptor.source_url, timeout=120) as response:
                    content_type = _response_content_type(response)
                    if content_type in TEXT_ERROR_CONTENT_TYPES:
                        raise ModelRegistryError(
                            "MODEL_RESPONSE_INVALID",
                            (
                                f"Unexpected response content type for "
                                f"{descriptor.model_id}: {content_type}"
                            ),
                        )
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            except urllib.error.HTTPError as exc:
                raise ModelRegistryError(
                    "MODEL_HTTP_ERROR",
                    f"HTTP error while downloading {descriptor.model_id}: {exc.code}",
                ) from exc
            except ModelRegistryError:
                raise
            except (OSError, urllib.error.URLError) as exc:
                raise ModelRegistryError(
                    "MODEL_DOWNLOAD_FAILED",
                    f"Download failed for {descriptor.model_id}: {exc}",
                ) from exc
            except Exception as exc:
                raise ModelRegistryError(
                    "MODEL_DOWNLOAD_FAILED",
                    f"Download failed for {descriptor.model_id}: {exc}",
                ) from exc

        size, checksum = validate_model_file(
            temporary_path,
            descriptor.minimum_size_bytes,
        )
        os.replace(temporary_path, destination)
        temporary_path = None
        return {
            "file_size_bytes": size,
            "sha256": checksum,
            "downloaded_at": utc_now(),
        }
    except PermissionError as exc:
        raise ModelRegistryError(
            "MODEL_DIRECTORY_NOT_WRITABLE",
            f"Model directory is not writable: {destination.parent}",
        ) from exc
    except ModelRegistryError:
        raise
    except OSError as exc:
        raise ModelRegistryError(
            "MODEL_DOWNLOAD_FAILED",
            f"Could not finalize model {descriptor.model_id}: {exc}",
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _manifest_record(
    descriptor: ModelDescriptor,
    *,
    file_size_bytes: int,
    checksum: str,
    downloaded_at: str,
    download_status: str,
) -> dict[str, Any]:
    return {
        "model_id": descriptor.model_id,
        "variant": descriptor.variant,
        "source_url": descriptor.source_url,
        "local_path": manifest_local_path(descriptor.local_path),
        "file_size_bytes": file_size_bytes,
        "sha256": checksum,
        "downloaded_at": downloaded_at,
        "download_status": download_status,
        "verified": True,
    }


def setup_models(overwrite_models: bool = False) -> dict[str, Any]:
    """Prepare both models and write manifest/report artifacts."""

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "failed",
        "generated_at": utc_now(),
        "overwrite_models": overwrite_models,
        "models": [],
        "warnings": [],
        "errors": [],
    }
    try:
        existing_manifest = read_manifest(MANIFEST_PATH)
    except ModelRegistryError as exc:
        report["errors"].append({"code": exc.code, "message": str(exc)})
        _write_setup_report(report)
        return report

    records_by_id = {
        entry["model_id"]: dict(entry)
        for entry in (existing_manifest or {}).get("models", [])
    }

    for descriptor in get_all_model_descriptors():
        try:
            state = inspect_model(descriptor, existing_manifest)
            if state["status"] == "ready" and not overwrite_models:
                previous = manifest_entry(descriptor.model_id, existing_manifest)
                assert previous is not None
                record = _manifest_record(
                    descriptor,
                    file_size_bytes=state["file_size_bytes"],
                    checksum=state["sha256"],
                    downloaded_at=previous["downloaded_at"],
                    download_status="skipped",
                )
                records_by_id[descriptor.model_id] = record
                report["models"].append(
                    {
                        "model_id": descriptor.model_id,
                        "status": "skipped",
                        "verified": True,
                        "file_size_bytes": state["file_size_bytes"],
                        "sha256": state["sha256"],
                    }
                )
                continue

            if state["status"] == "unverified_existing_file" and not overwrite_models:
                raise ModelRegistryError(
                    "MODEL_UNVERIFIED",
                    (
                        f"Existing model has no verified manifest entry: "
                        f"{descriptor.local_path}"
                    ),
                )
            if state["status"] == "checksum_mismatch" and not overwrite_models:
                raise ModelRegistryError(
                    "MODEL_CHECKSUM_MISMATCH",
                    f"Existing model checksum does not match: {descriptor.local_path}",
                )
            if state["status"] == "invalid_file" and not overwrite_models:
                raise ModelRegistryError(
                    state.get("error_code", "MODEL_RESPONSE_INVALID"),
                    state.get("error", "Existing model is invalid."),
                )

            downloaded = download_model(descriptor)
            record = _manifest_record(
                descriptor,
                file_size_bytes=downloaded["file_size_bytes"],
                checksum=downloaded["sha256"],
                downloaded_at=downloaded["downloaded_at"],
                download_status="downloaded",
            )
            records_by_id[descriptor.model_id] = record
            report["models"].append(
                {
                    "model_id": descriptor.model_id,
                    "status": "downloaded",
                    "verified": True,
                    "file_size_bytes": downloaded["file_size_bytes"],
                    "sha256": downloaded["sha256"],
                }
            )
        except ModelRegistryError as exc:
            report["models"].append(
                {
                    "model_id": descriptor.model_id,
                    "status": (
                        "download_failed"
                        if exc.code in {"MODEL_DOWNLOAD_FAILED", "MODEL_HTTP_ERROR"}
                        else "failed"
                    ),
                    "verified": False,
                    "error_code": exc.code,
                }
            )
            report["errors"].append({"code": exc.code, "message": str(exc)})

    if records_by_id:
        manifest = {
            "schema_version": "1.0",
            "generated_at": utc_now(),
            "models": [
                records_by_id[descriptor.model_id]
                for descriptor in get_all_model_descriptors()
                if descriptor.model_id in records_by_id
            ],
        }
        try:
            write_json_atomic(manifest, MANIFEST_PATH)
        except (OSError, TypeError, ValueError) as exc:
            report["errors"].append(
                {
                    "code": "MODEL_MANIFEST_WRITE_FAILED",
                    "message": f"Could not write model manifest: {exc}",
                }
            )

    report["status"] = "ready" if not report["errors"] else "failed"
    _write_setup_report(report)
    return report


def _write_setup_report(report: dict[str, Any]) -> None:
    try:
        write_json_atomic(report, REPORT_PATH)
    except (OSError, TypeError, ValueError) as exc:
        raise ModelRegistryError(
            "MEDIAPIPE_MODEL_SETUP_FAILED",
            f"Could not write model setup report: {exc}",
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and verify the pinned MediaPipe model baseline."
    )
    parser.add_argument(
        "--overwrite-models",
        action="store_true",
        help="Atomically replace even an existing model after validation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        report = setup_models(arguments.overwrite_models)
    except ModelRegistryError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print(f"Model setup report: {REPORT_PATH}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
