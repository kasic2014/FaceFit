"""Cross-process session/pipeline execution locks with conservative recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import time
from typing import Any, Callable

from app.audio.audio_manifest_writer import strict_json_bytes
from app.audio.session_audio_preprocessor import load_strict_json


PIPELINES = {"STT_TRANSCRIPTION", "SPEECH_CHARACTERISTICS", "STT_AND_SPEECH"}
SESSION_PATTERN = re.compile(r"^SES_\d{6}$")
TERMINAL = {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"}


class JobLockError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LockAcquisition:
    path: Path
    recovered_stale_lock: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


class AnalysisJobLockManager:
    def __init__(
        self,
        output_root: str | Path,
        *,
        wait_seconds: float,
        stale_seconds: float,
        now: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.root = Path(output_root) / "analysis_api" / "locks"
        self.wait_seconds = wait_seconds
        self.stale_seconds = stale_seconds
        self._now = now
        self._monotonic = monotonic
        self._sleep = sleeper

    def _path(self, session_id: str, pipeline: str) -> Path:
        if SESSION_PATTERN.fullmatch(session_id) is None or pipeline not in PIPELINES:
            raise JobLockError("JOB_LOCK_CORRUPTED", "Analysis job lock key is invalid")
        path = (self.root / f"{session_id}__{pipeline}.lock").resolve()
        if path.parent != self.root.resolve():
            raise JobLockError("JOB_LOCK_CORRUPTED", "Analysis job lock key is invalid")
        return path

    def acquire(
        self,
        *,
        job_id: str,
        session_id: str,
        pipeline: str,
        job_lookup: Callable[[str], dict[str, Any] | None],
        active_job_ids: Callable[[], set[str]],
    ) -> LockAcquisition:
        path = self._path(session_id, pipeline)
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = self._monotonic() + self.wait_seconds
        recovered = False
        while True:
            metadata = {
                "jobId": job_id,
                "sessionId": session_id,
                "pipeline": pipeline,
                "acquiredAt": self._now().isoformat().replace("+00:00", "Z"),
            }
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(descriptor, strict_json_bytes(metadata))
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                return LockAcquisition(path=path, recovered_stale_lock=recovered)
            except FileExistsError:
                if self._recover_if_stale(
                    path, job_lookup=job_lookup, active_job_ids=active_job_ids
                ):
                    recovered = True
                    continue
                if self._monotonic() >= deadline:
                    raise JobLockError(
                        "JOB_LOCK_TIMEOUT", "Analysis execution lock wait timed out"
                    )
                self._sleep(min(0.1, max(0.0, deadline - self._monotonic())))
            except JobLockError:
                raise
            except OSError as exc:
                raise JobLockError("JOB_LOCK_ERROR", "Analysis execution lock failed") from exc

    def _recover_if_stale(
        self,
        path: Path,
        *,
        job_lookup: Callable[[str], dict[str, Any] | None],
        active_job_ids: Callable[[], set[str]],
    ) -> bool:
        try:
            metadata = load_strict_json(path)
            owner = metadata.get("jobId")
            if not isinstance(owner, str) or not owner:
                raise ValueError("owner missing")
            acquired_at = _parse_utc(metadata.get("acquiredAt"))
        except Exception as exc:
            raise JobLockError("JOB_LOCK_CORRUPTED", "Analysis job lock is corrupted") from exc
        age = (self._now() - acquired_at).total_seconds()
        if age <= self.stale_seconds or owner in active_job_ids():
            return False
        owner_record = job_lookup(owner)
        if owner_record is not None and owner_record.get("status") not in TERMINAL:
            return False
        try:
            current = load_strict_json(path)
            if current != metadata:
                return False
            path.unlink(missing_ok=False)
            return True
        except FileNotFoundError:
            return True
        except Exception as exc:
            raise JobLockError("JOB_LOCK_ERROR", "Stale analysis lock recovery failed") from exc

    def release(self, acquisition: LockAcquisition, *, job_id: str) -> bool:
        try:
            metadata = load_strict_json(acquisition.path)
            if metadata.get("jobId") != job_id:
                return False
            acquisition.path.unlink(missing_ok=False)
            return True
        except FileNotFoundError:
            return True
        except Exception:
            return False

    def owner_job_ids(self) -> set[str]:
        owners: set[str] = set()
        if not self.root.exists():
            return owners
        for path in self.root.glob("*.lock"):
            try:
                value = load_strict_json(path).get("jobId")
                if isinstance(value, str):
                    owners.add(value)
            except Exception:
                continue
        return owners

    def recover_stale_locks(
        self,
        *,
        job_lookup: Callable[[str], dict[str, Any] | None],
        active_job_ids: Callable[[], set[str]],
    ) -> dict[str, int]:
        result = {"recovered": 0, "corrupted": 0, "preserved": 0}
        if not self.root.exists():
            return result
        for path in sorted(self.root.glob("*.lock")):
            try:
                if self._recover_if_stale(
                    path, job_lookup=job_lookup, active_job_ids=active_job_ids
                ):
                    result["recovered"] += 1
                else:
                    result["preserved"] += 1
            except JobLockError as exc:
                if exc.code == "JOB_LOCK_CORRUPTED":
                    result["corrupted"] += 1
                else:
                    result["preserved"] += 1
        return result
