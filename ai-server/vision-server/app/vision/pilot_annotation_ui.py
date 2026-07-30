"""Local, isolated Rater A/B annotation editing contracts for Stage 18.5."""

from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.vision.pilot_annotation_package import (
    PARTICIPANT_ID,
    RATER_IDS,
    SESSION_ID,
    registry_from_dict,
    validate_rater_submission,
)
from app.vision.pilot_video_intake import (
    ensure_finite,
    load_strict_json,
)


EVENT_ID_RE = re.compile(r"^(RATER_[AB])_EVT_(\d{6})$")


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Write strict JSON through an adjacent temporary file then replace."""
    ensure_finite(value)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


class AnnotationWorkspace:
    """One-rater workspace that cannot resolve another rater's directory."""

    def __init__(
        self,
        package_root: str | Path,
        *,
        session_id: str,
        rater_id: str,
        video_path: str | Path | None = None,
    ) -> None:
        if session_id != SESSION_ID:
            raise ValueError("unsupported session_id")
        if rater_id not in RATER_IDS:
            raise ValueError("unsupported rater_id")
        self.package_root = Path(package_root).resolve()
        self.session_id = session_id
        self.rater_id = rater_id
        self.rater_directory = self.package_root / rater_id.lower()
        if self.rater_directory.parent != self.package_root:
            raise ValueError("invalid rater workspace path")
        self._intervals = load_strict_json(
            self.rater_directory / "answer_intervals.json"
        )
        self._labels = load_strict_json(
            self.rater_directory / "annotation_labels.json"
        )
        self._template = load_strict_json(
            self.rater_directory / "annotation_events.template.json"
        )
        if (
            self._intervals["participant_id"] != PARTICIPANT_ID
            or self._intervals["session_id"] != session_id
            or self._intervals["rater_id"] != rater_id
            or self._template["rater_id"] != rater_id
            or self._labels["rater_id"] != rater_id
        ):
            raise ValueError("rater package reference mismatch")
        self.registry = registry_from_dict({
            "labels": self._labels["labels"],
            "rubrics": [{
                "rubric_id": self._labels["rubric_id"],
                "version": self._labels["rubric_version"],
                "status": "DRAFT",
                "label_ids": [item["label_id"] for item in self._labels["labels"]],
                "interval_end_exclusive": self._labels["interval_end_exclusive"],
                "inference_prohibited": self._labels["inference_prohibited"],
            }],
        })
        self.answers = list(self._intervals["answer_intervals"])
        self.draft_path = self.rater_directory / "annotation_events.draft.json"
        self.result_path = self.rater_directory / "annotation_events.json"
        self.video_path = (
            Path(video_path).resolve()
            if video_path is not None
            else (self.rater_directory / self._intervals["video_relative_path"]).resolve()
        )
        if not self.video_path.is_file():
            raise FileNotFoundError(f"video not found: {self.video_path}")
        self.document = self._load_draft_or_template()
        self._issued_sequences = self._existing_sequences()
        self._validate_draft()

    @property
    def labels(self) -> list[dict[str, Any]]:
        return deepcopy(self._labels["labels"])

    @property
    def events(self) -> list[dict[str, Any]]:
        return deepcopy(self.document["events"])

    def _load_draft_or_template(self) -> dict[str, Any]:
        source = self.draft_path if self.draft_path.exists() else (
            self.rater_directory / "annotation_events.template.json"
        )
        return load_strict_json(source)

    def _existing_sequences(self) -> set[int]:
        values: set[int] = set()
        for event in self.document["events"]:
            match = EVENT_ID_RE.fullmatch(event["annotation_event_id"])
            if match and match.group(1) == self.rater_id:
                values.add(int(match.group(2)))
        return values

    def _validate_draft(self) -> None:
        validate_rater_submission(
            self.document,
            expected_rater_id=self.rater_id,
            answers=self.answers,
            registry=self.registry,
            require_completed=False,
        )

    def answer_for_timestamp(self, timestamp_ms: int) -> dict[str, Any] | None:
        for answer in self.answers:
            if answer["start_timestamp_ms"] <= timestamp_ms < answer["end_timestamp_ms"]:
                return deepcopy(answer)
        return None

    def next_event_id(self) -> str:
        sequence = max(self._issued_sequences, default=0) + 1
        return f"{self.rater_id}_EVT_{sequence:06d}"

    def add_event(
        self,
        *,
        answer_id: str,
        label_id: str,
        direction: str | None,
        start_timestamp_ms: int,
        end_timestamp_ms: int,
        note: str | None = None,
    ) -> str:
        event_id = self.next_event_id()
        interval = next(
            (item for item in self.answers if item["answer_id"] == answer_id),
            None,
        )
        if interval is None:
            raise ValueError("unknown answer_id")
        event = {
            "annotation_event_id": event_id,
            "answer_id": answer_id,
            "interval_id": interval["interval_id"],
            "label_id": label_id,
            "direction": direction,
            "start_timestamp_ms": start_timestamp_ms,
            "end_timestamp_ms": end_timestamp_ms,
            "rater_confidence": None,
            "note": note,
        }
        candidate = deepcopy(self.document)
        candidate["events"].append(event)
        self._validate_value(candidate)
        self.document = candidate
        self._issued_sequences.add(int(event_id.rsplit("_", 1)[1]))
        return event_id

    def update_event(self, event_id: str, **changes: Any) -> None:
        permitted = {
            "answer_id", "label_id", "direction", "start_timestamp_ms",
            "end_timestamp_ms", "note",
        }
        unexpected = set(changes) - permitted
        if unexpected:
            raise ValueError("unsupported event update field")
        candidate = deepcopy(self.document)
        for event in candidate["events"]:
            if event["annotation_event_id"] == event_id:
                event.update(changes)
                if "answer_id" in changes:
                    interval = next(
                        (item for item in self.answers
                         if item["answer_id"] == changes["answer_id"]),
                        None,
                    )
                    if interval is None:
                        raise ValueError("unknown answer_id")
                    event["interval_id"] = interval["interval_id"]
                self._validate_value(candidate)
                self.document = candidate
                return
        raise KeyError("annotation event not found")

    def delete_event(self, event_id: str) -> None:
        candidate = deepcopy(self.document)
        candidate["events"] = [
            item for item in candidate["events"]
            if item["annotation_event_id"] != event_id
        ]
        if len(candidate["events"]) == len(self.document["events"]):
            raise KeyError("annotation event not found")
        self._validate_value(candidate)
        self.document = candidate

    def _validate_value(self, value: dict[str, Any]) -> None:
        validate_rater_submission(
            value,
            expected_rater_id=self.rater_id,
            answers=self.answers,
            registry=self.registry,
            require_completed=False,
        )

    def save_draft(self) -> Path:
        self.document["completed_at"] = None
        self._validate_draft()
        _atomic_write_json(self.draft_path, self.document)
        return self.draft_path

    def complete(
        self,
        *,
        confirm_empty_events: bool = False,
        confirm_replace_existing: bool = False,
        completed_at: str | None = None,
    ) -> Path:
        if not self.document["events"] and not confirm_empty_events:
            raise ValueError("empty event completion requires explicit confirmation")
        if self.result_path.exists() and not confirm_replace_existing:
            raise FileExistsError("result file already exists; explicit replacement required")
        candidate = deepcopy(self.document)
        candidate["completed_at"] = completed_at or datetime.now(timezone.utc).isoformat()
        validate_rater_submission(
            candidate,
            expected_rater_id=self.rater_id,
            answers=self.answers,
            registry=self.registry,
            require_completed=True,
        )
        _atomic_write_json(self.result_path, candidate)
        self.document = candidate
        return self.result_path
