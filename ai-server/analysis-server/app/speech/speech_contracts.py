"""Versioned Stage 26 measurement profile and internal input contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


EXPECTED_ANSWERS = tuple(f"ANS_{index:06d}" for index in range(1, 5))
PAUSE_VIEW_THRESHOLDS_MS = (250, 500, 1000, 2000)


class SpeechContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SpeechAnalysisProfile:
    name: str = "stage26-measurement-v1"
    version: str = "1.0.0"
    frame_length_ms: int = 25
    hop_length_ms: int = 10
    silence_reference_percentile: float = 90.0
    silence_offset_db: float = -20.0
    silence_min_dbfs: float = -80.0
    silence_max_dbfs: float = -35.0
    near_silent_rms_dbfs: float = -60.0
    clipping_amplitude: float = 32767 / 32768
    pitch_frame_length_ms: int = 40
    pitch_hop_length_ms: int = 10
    pitch_fmin_hz: float = 50.0
    pitch_fmax_hz: float = 500.0
    pitch_min_correlation: float = 0.35
    pitch_min_voiced_frames: int = 10
    pitch_boundary_margin_hz: float = 5.0
    pitch_boundary_candidate_ratio: float = 0.20
    pause_view_thresholds_ms: tuple[int, ...] = PAUSE_VIEW_THRESHOLDS_MS
    filler_lexicon_name: str = "ko-filler-candidates"
    filler_lexicon_version: str = "1.0.0"

    def validate(self) -> None:
        if self.frame_length_ms <= 0 or self.hop_length_ms <= 0:
            raise SpeechContractError("INVALID_PROFILE", "Invalid acoustic frame profile")
        if self.pitch_frame_length_ms <= 0 or self.pitch_hop_length_ms <= 0:
            raise SpeechContractError("INVALID_PROFILE", "Invalid pitch frame profile")
        if not 0 < self.pitch_fmin_hz < self.pitch_fmax_hz:
            raise SpeechContractError("INVALID_PROFILE", "Invalid pitch search range")
        if tuple(sorted(set(self.pause_view_thresholds_ms))) != self.pause_view_thresholds_ms:
            raise SpeechContractError("INVALID_PROFILE", "Pause views must be unique and ordered")

    def public_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["pause_view_thresholds_ms"] = list(self.pause_view_thresholds_ms)
        return {
            "name": payload["name"],
            "version": payload["version"],
            "analysisMode": "MEASUREMENT_ONLY",
            "thresholdPurpose": "TECHNICAL_VIEW_ONLY",
            "scoringApproved": False,
            "acousticSilence": {
                "frameLengthMs": payload["frame_length_ms"],
                "hopLengthMs": payload["hop_length_ms"],
                "thresholdMode": "P90_FRAME_RMS_DBFS_PLUS_OFFSET",
                "referencePercentile": payload["silence_reference_percentile"],
                "offsetDb": payload["silence_offset_db"],
                "minimumDbfs": payload["silence_min_dbfs"],
                "maximumDbfs": payload["silence_max_dbfs"],
                "nearSilentCandidateDbfs": payload["near_silent_rms_dbfs"],
            },
            "volume": {"clippingAmplitude": payload["clipping_amplitude"]},
            "pitch": {
                "frameLengthMs": payload["pitch_frame_length_ms"],
                "hopLengthMs": payload["pitch_hop_length_ms"],
                "fminHz": payload["pitch_fmin_hz"],
                "fmaxHz": payload["pitch_fmax_hz"],
                "minimumCorrelation": payload["pitch_min_correlation"],
                "minimumVoicedFrames": payload["pitch_min_voiced_frames"],
                "boundaryMarginHz": payload["pitch_boundary_margin_hz"],
                "boundaryCandidateRatio": payload["pitch_boundary_candidate_ratio"],
            },
            "pauseViewThresholdsMs": payload["pause_view_thresholds_ms"],
            "fillerLexicon": {
                "name": payload["filler_lexicon_name"],
                "version": payload["filler_lexicon_version"],
            },
        }


DEFAULT_PROFILE = SpeechAnalysisProfile()
PROFILES = {DEFAULT_PROFILE.name: DEFAULT_PROFILE}


def resolve_profile(name: str = DEFAULT_PROFILE.name) -> SpeechAnalysisProfile:
    profile = PROFILES.get(name)
    if profile is None:
        raise SpeechContractError("INVALID_PROFILE", "Unknown speech analysis profile")
    profile.validate()
    return profile


@dataclass(frozen=True)
class SpeechAnswerInput:
    session_id: str
    answer_id: str
    audio_path: Path
    transcript_path: Path
    audio_sha256: str
    transcript_sha256: str
    start_ms: int
    end_ms: int
    duration_ms: int
    sample_count: int
    transcript: dict[str, Any]


@dataclass(frozen=True)
class SpeechSessionInput:
    session_id: str
    stage24_manifest_sha256: str
    stage25_manifest_sha256: str
    stage24_status: str
    stage25_status: str
    stage25_warnings: tuple[str, ...]
    answers: tuple[SpeechAnswerInput, ...]
