"""Fixture path, pseudonymous filename, and file metadata validation."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from app.vision.pilot_collection_models import RecordingFileRecord


PROHIBITED_FILENAME_TOKENS = (
    "NAME", "EMAIL", "PHONE", "BIRTH", "DOB", "COMPANY", "SSN", "RRN"
)
FILENAME_RE = re.compile(
    r"^(PTC_\d{6})_(SES_\d{6})_(ANS_\d{6})\.(mp4|mov|mkv)$",
    re.IGNORECASE,
)


def validate_recording_file_record(record: RecordingFileRecord) -> None:
    normalized = record.file_reference.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("file_reference must be a safe relative fixture path")
    if tuple(path.parts[:3]) not in {
        ("data", "pilot", "incoming"),
        ("data", "pilot", "validated"),
        ("data", "pilot", "excluded"),
        ("data", "pilot", "withdrawn"),
    }:
        raise ValueError("file_reference must use a pilot storage area")
    upper_name = path.name.upper()
    if any(token in upper_name for token in PROHIBITED_FILENAME_TOKENS):
        raise ValueError("filename contains prohibited personal information")
    match = FILENAME_RE.fullmatch(path.name)
    if match is None:
        raise ValueError("filename must use participant_session_answer.ext")
    if match.group(1).upper() != record.participant_id:
        raise ValueError("filename participant reference mismatch")
    if match.group(2).upper() != record.session_id:
        raise ValueError("filename session reference mismatch")
    if match.group(3).upper() != record.answer_id:
        raise ValueError("filename answer reference mismatch")
