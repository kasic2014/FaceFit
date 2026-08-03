"""Contracts and deterministic boundary rules for STT preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


SESSION_PATTERN = re.compile(r"^SES_\d{6}$")
ANSWER_PATTERN = re.compile(r"^ANS_\d{6}$")
SAMPLE_RATE_HZ = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BITS = 16
PCM_CODEC = "PCM_S16LE"
CONTAINER = "WAV"
DURATION_TOLERANCE_MS = 1
SOURCE_DURATION_TOLERANCE_MS = 50


class AudioContractError(ValueError):
    """Raised when a public identifier or interval contract is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AudioInterval:
    interval_type: str
    output_id: str
    start_ms: int
    end_ms: int
    answer_id: str | None = None

    def __post_init__(self) -> None:
        if self.interval_type not in {"BASELINE", "ANSWER"}:
            raise AudioContractError("INVALID_INTERVAL_TYPE", "Unsupported interval type")
        if isinstance(self.start_ms, bool) or isinstance(self.end_ms, bool):
            raise AudioContractError("INVALID_INTERVAL", "Interval boundaries must be integers")
        if not isinstance(self.start_ms, int) or not isinstance(self.end_ms, int):
            raise AudioContractError("INVALID_INTERVAL", "Interval boundaries must be integers")
        if self.start_ms < 0 or self.start_ms >= self.end_ms:
            raise AudioContractError("EMPTY_AUDIO", "Interval must satisfy 0 <= start < end")
        if self.interval_type == "BASELINE":
            if self.output_id != "BASELINE" or self.answer_id is not None:
                raise AudioContractError("INVALID_INTERVAL", "Invalid baseline identity")
        elif (
            self.answer_id is None
            or self.output_id != self.answer_id
            or ANSWER_PATTERN.fullmatch(self.answer_id) is None
        ):
            raise AudioContractError("INVALID_ANSWER_ID", "Invalid answer identity")

    @property
    def expected_duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def start_sample(self) -> int:
        return milliseconds_to_sample(self.start_ms)

    @property
    def end_sample(self) -> int:
        return milliseconds_to_sample(self.end_ms)

    @property
    def expected_sample_count(self) -> int:
        return self.end_sample - self.start_sample

    def contract_dict(self) -> dict[str, Any]:
        return {
            "intervalType": self.interval_type,
            "answerId": self.answer_id,
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "startSample": self.start_sample,
            "endSample": self.end_sample,
            "expectedDurationMs": self.expected_duration_ms,
            "expectedSampleCount": self.expected_sample_count,
        }


@dataclass(frozen=True)
class SessionAudioInput:
    session_id: str
    video_path: Any
    metadata_path: Any
    source_sha256: str
    intervals: tuple[AudioInterval, ...]


def validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or SESSION_PATTERN.fullmatch(session_id) is None:
        raise AudioContractError("INVALID_SESSION_ID", "sessionId must match SES_ followed by six digits")
    return session_id


def milliseconds_to_sample(milliseconds: int, sample_rate_hz: int = SAMPLE_RATE_HZ) -> int:
    """Map a [start, end) millisecond boundary to a sample using floor."""
    if isinstance(milliseconds, bool) or not isinstance(milliseconds, int) or milliseconds < 0:
        raise AudioContractError("INVALID_INTERVAL", "Milliseconds must be a non-negative integer")
    if sample_rate_hz <= 0:
        raise AudioContractError("INVALID_SAMPLE_RATE", "Sample rate must be positive")
    return milliseconds * sample_rate_hz // 1000


def audio_contract() -> dict[str, Any]:
    return {
        "container": CONTAINER,
        "codec": PCM_CODEC,
        "sampleRateHz": SAMPLE_RATE_HZ,
        "channels": CHANNELS,
        "sampleWidthBits": SAMPLE_WIDTH_BITS,
        "intervalRule": "[startMs, endMs)",
        "boundaryConversion": "floor(milliseconds * sampleRateHz / 1000)",
        "paddingSamples": 0,
        "durationToleranceMs": DURATION_TOLERANCE_MS,
        "sourceDurationToleranceMs": SOURCE_DURATION_TOLERANCE_MS,
    }
