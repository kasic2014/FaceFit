"""Automatic collection quality result completeness and decision logic."""

from __future__ import annotations

from collections.abc import Iterable

from app.vision.pilot_collection_models import (
    CollectionQualityCheck,
    QualityCheckType,
)


def validate_quality_checks(
    checks: Iterable[CollectionQualityCheck],
    *,
    pilot_session_id: str,
) -> dict[str, object]:
    values = tuple(checks)
    if any(item.pilot_session_id != pilot_session_id for item in values):
        raise ValueError("quality check session mismatch")
    by_type = {item.check_type: item for item in values}
    if len(by_type) != len(values):
        raise ValueError("duplicate quality check type")
    required = {item.value for item in QualityCheckType}
    missing = sorted(required - set(by_type))
    if missing:
        raise ValueError(f"missing quality checks: {', '.join(missing)}")
    failed = tuple(
        item for item in values if item.status == "FAILED"
    )
    warnings = tuple(
        item for item in values if item.status == "WARNING"
    )
    not_checked = tuple(
        item for item in values if item.status == "NOT_CHECKED"
    )
    return {
        "automatic_validation_passed": not failed and not not_checked,
        "release_quality_passed": not failed and not warnings and not not_checked,
        "manual_review_required": True,
        "failed_check_count": len(failed),
        "warning_check_count": len(warnings),
        "not_checked_count": len(not_checked),
        "exclusion_reasons": sorted(
            {
                item.reason_code for item in failed
                if item.reason_code is not None
            }
        ),
        "warning_is_user_posture_failure": False,
    }
