"""Dry-run-by-default cleanup for terminal Analysis API job records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.analysis_api_config import AnalysisApiConfig
from app.services.analysis_job_lock import AnalysisJobLockManager
from app.services.analysis_job_retention import AnalysisJobRetention
from app.services.analysis_job_storage import AnalysisJobStorage


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="List candidates without deleting")
    mode.add_argument("--apply", action="store_true", help="Delete eligible terminal job JSON")
    args = parser.parse_args()
    config = AnalysisApiConfig.from_env()
    storage = AnalysisJobStorage(config.output_root)
    locks = AnalysisJobLockManager(
        config.output_root,
        wait_seconds=config.job_lock_wait_seconds,
        stale_seconds=config.stale_lock_seconds,
    )
    retention = AnalysisJobRetention(
        storage,
        retention_days=config.job_retention_days,
        max_records=config.job_max_records,
        lock_owner_ids=locks.owner_job_ids,
    )
    report = retention.cleanup(apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
