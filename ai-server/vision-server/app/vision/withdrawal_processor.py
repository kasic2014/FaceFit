"""Metadata-only withdrawal propagation; never deletes a file."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from app.vision.pilot_collection_models import (
    PilotAnswerRecord,
    PilotSessionRun,
    RecordingFileRecord,
    WithdrawalRequest,
)


@dataclass(frozen=True)
class WithdrawalProcessingResult:
    withdrawal_request_id: str
    participant_id: str
    participant_status: str
    blocked_session_ids: tuple[str, ...]
    blocked_answer_ids: tuple[str, ...]
    blocked_file_references: tuple[str, ...]
    annotation_use_blocked: bool
    manifest_use_blocked: bool
    file_action_status: str
    actual_file_deleted: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in (
            "blocked_session_ids",
            "blocked_answer_ids",
            "blocked_file_references",
        ):
            value[field] = list(getattr(self, field))
        return value


def process_withdrawal(
    request: WithdrawalRequest,
    sessions: Iterable[PilotSessionRun],
    answers: Iterable[PilotAnswerRecord],
    files: Iterable[RecordingFileRecord],
) -> WithdrawalProcessingResult:
    participant_sessions = tuple(
        item for item in sessions
        if item.participant_id == request.participant_id
    )
    session_ids = {item.pilot_session_id for item in participant_sessions}
    participant_answers = tuple(
        item for item in answers if item.pilot_session_id in session_ids
    )
    participant_files = tuple(
        item for item in files
        if item.participant_id == request.participant_id
    )
    return WithdrawalProcessingResult(
        request.withdrawal_request_id,
        request.participant_id,
        "WITHDRAWN",
        tuple(sorted(session_ids)),
        tuple(sorted(item.answer_id for item in participant_answers)),
        tuple(sorted(item.file_reference for item in participant_files)),
        True,
        True,
        request.disposition,
        False,
    )
