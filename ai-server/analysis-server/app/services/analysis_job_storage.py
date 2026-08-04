"""Atomic, thread-safe, restart-readable Analysis API job storage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Iterator

from app.audio.audio_manifest_writer import strict_json_bytes, write_json_atomic
from app.audio.session_audio_preprocessor import load_strict_json


class JobStorageError(RuntimeError):
    """Raised for invalid, missing, or unreadable job records."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_job_id(job_id: str) -> str:
    try:
        parsed = uuid.UUID(job_id)
    except (ValueError, AttributeError) as exc:
        raise JobStorageError("JOB_NOT_FOUND", "Analysis job was not found") from exc
    canonical = str(parsed)
    if canonical != job_id.lower():
        raise JobStorageError("JOB_NOT_FOUND", "Analysis job was not found")
    return canonical


class AnalysisJobStorage:
    def __init__(self, output_root: str | Path) -> None:
        self.root = Path(output_root) / "analysis_api" / "jobs"
        self._mutex = threading.RLock()
        self._creation_lock_path = self.root / ".job-creation.guard"

    def _path(self, job_id: str) -> Path:
        canonical = validate_job_id(job_id)
        path = (self.root / f"{canonical}.json").resolve()
        if path.parent != self.root.resolve():
            raise JobStorageError("JOB_NOT_FOUND", "Analysis job was not found")
        return path

    def create(self, record: dict[str, Any]) -> None:
        path = self._path(str(record.get("jobId", "")))
        with self._mutex:
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(descriptor)
                try:
                    write_json_atomic(path, record)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
            except FileExistsError as exc:
                raise JobStorageError("JOB_STORAGE_ERROR", "Analysis job identifier collision") from exc
            except JobStorageError:
                raise
            except Exception as exc:
                raise JobStorageError("JOB_STORAGE_ERROR", "Analysis job could not be stored") from exc

    def write(self, record: dict[str, Any]) -> None:
        path = self._path(str(record.get("jobId", "")))
        with self._mutex:
            if not path.is_file():
                raise JobStorageError("JOB_NOT_FOUND", "Analysis job was not found")
            try:
                write_json_atomic(path, record)
            except Exception as exc:
                raise JobStorageError("JOB_STORAGE_ERROR", "Analysis job could not be stored") from exc

    def read(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        with self._mutex:
            if not path.is_file():
                raise JobStorageError("JOB_NOT_FOUND", "Analysis job was not found")
            try:
                record = load_strict_json(path)
            except Exception as exc:
                raise JobStorageError("JOB_STORAGE_ERROR", "Analysis job record is invalid") from exc
            if record.get("jobId") != validate_job_id(job_id):
                raise JobStorageError("JOB_STORAGE_ERROR", "Analysis job record is invalid")
            return record

    def list_records(self) -> list[dict[str, Any]]:
        with self._mutex:
            if not self.root.exists():
                return []
            records: list[dict[str, Any]] = []
            try:
                paths = sorted(self.root.glob("*.json"))
            except OSError as exc:
                raise JobStorageError("JOB_STORAGE_ERROR", "Analysis job storage is unavailable") from exc
            for path in paths:
                try:
                    validate_job_id(path.stem)
                    records.append(self.read(path.stem))
                except JobStorageError as exc:
                    if exc.code == "JOB_NOT_FOUND":
                        continue
                    raise
            return records

    def delete(self, job_id: str) -> None:
        path = self._path(job_id)
        with self._mutex:
            try:
                path.unlink(missing_ok=False)
            except FileNotFoundError as exc:
                raise JobStorageError("JOB_NOT_FOUND", "Analysis job was not found") from exc
            except OSError as exc:
                raise JobStorageError("JOB_STORAGE_ERROR", "Analysis job could not be deleted") from exc

    @contextmanager
    def creation_guard(self, timeout_seconds: float = 5.0) -> Iterator[None]:
        """Serialize idempotency lookup plus creation across threads and processes."""
        token = str(uuid.uuid4())
        deadline = time.monotonic() + timeout_seconds
        acquired = False
        with self._mutex:
            self._creation_lock_path.parent.mkdir(parents=True, exist_ok=True)
            while not acquired:
                metadata = {
                    "token": token,
                    "acquiredAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                try:
                    descriptor = os.open(
                        self._creation_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                    try:
                        os.write(descriptor, strict_json_bytes(metadata))
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                    acquired = True
                except FileExistsError:
                    try:
                        age = time.time() - self._creation_lock_path.stat().st_mtime
                        if age > 30:
                            self._creation_lock_path.unlink(missing_ok=True)
                            continue
                    except OSError:
                        pass
                    if time.monotonic() >= deadline:
                        raise JobStorageError(
                            "JOB_STORAGE_ERROR", "Analysis job creation lock timed out"
                        )
                    time.sleep(0.01)
            try:
                yield
            finally:
                try:
                    current = load_strict_json(self._creation_lock_path)
                    if current.get("token") == token:
                        self._creation_lock_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def check_available(self) -> bool:
        descriptor: int | None = None
        probe: Path | None = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / f".probe-{uuid.uuid4()}.tmp"
            descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, b"ok")
            os.close(descriptor)
            descriptor = None
            return True
        except OSError:
            return False
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if probe is not None:
                try:
                    probe.unlink(missing_ok=True)
                except OSError:
                    pass
