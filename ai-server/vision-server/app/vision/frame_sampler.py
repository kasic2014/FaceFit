"""Deterministic timestamp-based sequential video frame sampling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import cv2
import numpy as np

from app.vision.video_loader import decode_frame


MIN_ANALYSIS_FPS = 1.0
MAX_ANALYSIS_FPS = 15.0
DEFAULT_ANALYSIS_FPS = 5.0


class FrameSamplingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SampledFrame:
    sample_index: int
    source_frame_index: int
    timestamp_ms: int
    timestamp_sec: float
    bgr_frame: np.ndarray
    width: int
    height: int


def validate_analysis_fps(value: float) -> float:
    try:
        fps = float(value)
    except (TypeError, ValueError) as exc:
        raise FrameSamplingError(
            "ANALYSIS_FPS_INVALID",
            "Analysis FPS must be numeric.",
        ) from exc
    if not np.isfinite(fps) or not MIN_ANALYSIS_FPS <= fps <= MAX_ANALYSIS_FPS:
        raise FrameSamplingError(
            "ANALYSIS_FPS_OUT_OF_RANGE",
            f"Analysis FPS must be between {MIN_ANALYSIS_FPS} and {MAX_ANALYSIS_FPS}.",
        )
    return fps


class FrameSampler:
    """Read every source frame once and yield deterministic sampled frames."""

    def __init__(
        self,
        capture: cv2.VideoCapture,
        original_fps: float,
        analysis_fps: float = DEFAULT_ANALYSIS_FPS,
    ) -> None:
        if not np.isfinite(original_fps) or original_fps <= 0:
            raise FrameSamplingError(
                "VIDEO_FPS_INVALID",
                "Original video FPS must be positive.",
            )
        self.capture = capture
        self.original_fps = float(original_fps)
        self.requested_analysis_fps = validate_analysis_fps(analysis_fps)
        self.effective_analysis_fps = min(
            self.original_fps,
            self.requested_analysis_fps,
        )
        self.decoded_frame_count = 0
        self.sampled_frame_count = 0
        self.skipped_frame_count = 0
        self.duplicate_frame_count = 0
        self.duplicate_timestamp_count = 0
        self.first_timestamp_ms: int | None = None
        self.last_timestamp_ms: int | None = None
        self.timestamps_strictly_increasing = True

    def __iter__(self) -> Iterator[SampledFrame]:
        next_sample_sec = 0.0
        period_sec = 1.0 / self.effective_analysis_fps
        last_source_index: int | None = None
        last_timestamp: int | None = None
        source_index = 0
        epsilon = 1e-9
        while True:
            success, frame = decode_frame(self.capture)
            if not success or frame is None:
                break
            self.decoded_frame_count += 1
            timestamp_sec = source_index / self.original_fps
            should_sample = timestamp_sec + epsilon >= next_sample_sec
            if should_sample:
                timestamp_ms = int(round(timestamp_sec * 1000.0))
                if source_index == last_source_index:
                    self.duplicate_frame_count += 1
                elif last_timestamp is not None and timestamp_ms <= last_timestamp:
                    self.duplicate_timestamp_count += 1
                    self.timestamps_strictly_increasing = False
                else:
                    height, width = frame.shape[:2]
                    sample = SampledFrame(
                        sample_index=self.sampled_frame_count,
                        source_frame_index=source_index,
                        timestamp_ms=timestamp_ms,
                        timestamp_sec=timestamp_ms / 1000.0,
                        bgr_frame=frame,
                        width=int(width),
                        height=int(height),
                    )
                    self.sampled_frame_count += 1
                    if self.first_timestamp_ms is None:
                        self.first_timestamp_ms = timestamp_ms
                    self.last_timestamp_ms = timestamp_ms
                    last_source_index = source_index
                    last_timestamp = timestamp_ms
                    while next_sample_sec <= timestamp_sec + epsilon:
                        next_sample_sec += period_sec
                    yield sample
            else:
                self.skipped_frame_count += 1
            source_index += 1
        self.skipped_frame_count = (
            self.decoded_frame_count - self.sampled_frame_count
        )

    def summary(self) -> dict[str, int | float | bool | None]:
        return {
            "original_fps": self.original_fps,
            "requested_analysis_fps": self.requested_analysis_fps,
            "effective_analysis_fps": self.effective_analysis_fps,
            "decoded_frame_count": self.decoded_frame_count,
            "sampled_frame_count": self.sampled_frame_count,
            "skipped_frame_count": self.skipped_frame_count,
            "duplicate_frame_count": self.duplicate_frame_count,
            "duplicate_timestamp_count": self.duplicate_timestamp_count,
            "first_timestamp_ms": self.first_timestamp_ms,
            "last_timestamp_ms": self.last_timestamp_ms,
            "timestamps_strictly_increasing": self.timestamps_strictly_increasing,
        }
