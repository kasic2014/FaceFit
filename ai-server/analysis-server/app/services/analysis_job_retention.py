"""Conservative retention planning for terminal Analysis API job JSON only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .analysis_job_storage import AnalysisJobStorage, JobStorageError


TERMINAL = {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "FAILED"}
ACTIVE = {"QUEUED", "RUNNING"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


class AnalysisJobRetention:
    def __init__(
        self,
        storage: AnalysisJobStorage,
        *,
        retention_days: int,
        max_records: int,
        lock_owner_ids: Callable[[], set[str]],
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.storage = storage
        self.retention_days = retention_days
        self.max_records = max_records
        self._lock_owner_ids = lock_owner_ids
        self._now = now

    def cleanup(self, *, apply: bool = False) -> dict[str, Any]:
        records = self.storage.list_records()
        cutoff = self._now() - timedelta(days=self.retention_days)
        lock_owners = self._lock_owner_ids()
        candidates: list[dict[str, Any]] = []
        protected = {"active": 0, "lockOwner": 0, "recent": 0, "invalidTimestamp": 0}
        for record in records:
            job_id = str(record.get("jobId", ""))
            status = record.get("status")
            if status in ACTIVE:
                protected["active"] += 1
                continue
            if job_id in lock_owners:
                protected["lockOwner"] += 1
                continue
            if status not in TERMINAL:
                protected["active"] += 1
                continue
            reference = _parse_time(
                record.get("completedAt") or record.get("updatedAt") or record.get("createdAt")
            )
            if reference is None:
                protected["invalidTimestamp"] += 1
                continue
            if reference >= cutoff:
                protected["recent"] += 1
                continue
            candidates.append({"jobId": job_id, "completedAt": record.get("completedAt")})

        candidates.sort(key=lambda row: str(row.get("completedAt") or ""))
        deleted: list[str] = []
        errors: list[dict[str, str]] = []
        if apply:
            for candidate in candidates:
                try:
                    self.storage.delete(candidate["jobId"])
                    deleted.append(candidate["jobId"])
                except JobStorageError as exc:
                    errors.append({"jobId": candidate["jobId"], "code": exc.code})
        projected = len(records) - (len(deleted) if apply else len(candidates))
        return {
            "mode": "APPLY" if apply else "DRY_RUN",
            "retentionDays": self.retention_days,
            "maxRecords": self.max_records,
            "recordCount": len(records),
            "candidateCount": len(candidates),
            "candidates": [row["jobId"] for row in candidates],
            "deletedCount": len(deleted),
            "deleted": deleted,
            "protected": protected,
            "projectedRecordCount": projected,
            "maxRecordsExceeded": projected > self.max_records,
            "errors": errors,
        }
