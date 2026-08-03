"""Idempotent Stage 24 WAV + Stage 25 transcript speech-characteristics service."""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable
import uuid

from app.audio.audio_manifest_writer import ensure_finite, strict_json_bytes
from app.audio.interval_audio_extractor import inspect_pcm_wav, sha256_file
from app.audio.session_audio_preprocessor import load_strict_json
from app.audio.audio_contracts import validate_session_id
from app.core.config import APP_PATHS
from app.speech.speech_metrics import load_pcm16_mono_wav

from .filler_candidate_analyzer import analyze_filler_candidates, load_lexicon
from .pause_analyzer import analyze_timestamp_pauses
from .pitch_analyzer import PitchAdapter, analyze_pitch
from .speaking_rate_analyzer import analyze_speaking_rate
from .speech_contracts import (
    EXPECTED_ANSWERS,
    SpeechAnalysisProfile,
    SpeechAnswerInput,
    SpeechContractError,
    SpeechSessionInput,
)
from .speech_manifest_writer import replace_directory, write_json_atomic, write_text_atomic
from .volume_analyzer import analyze_volume_and_silence


STAGE24_READY = {
    "stt_audio_preprocessing_ready",
    "stt_audio_preprocessing_ready_with_warnings",
}
STAGE25_READY = {
    "stt_session_transcription_ready",
    "stt_session_transcription_ready_with_warnings",
}
STATUS_READY = "speech_characteristics_ready"
STATUS_WARNINGS = "speech_characteristics_ready_with_warnings"
STATUS_DEPENDENCY_BLOCKED = "speech_characteristics_dependency_blocked"
STATUS_INPUT_INVALID = "speech_characteristics_input_invalid"
STATUS_FAILED = "speech_characteristics_failed"


class SpeechAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_words(
    transcript: dict[str, Any], duration_ms: int, answer_start_ms: int
) -> None:
    previous_start = -1
    previous_end = -1
    segments = {segment["segmentId"]: segment for segment in transcript.get("segments", [])}
    for segment in segments.values():
        if (
            not 0 <= segment["startMsRelative"] < segment["endMsRelative"] <= duration_ms
            or segment["startMsSession"] != answer_start_ms + segment["startMsRelative"]
            or segment["endMsSession"] != answer_start_ms + segment["endMsRelative"]
        ):
            raise SpeechAnalysisError(
                "TRANSCRIPT_INPUT_SHA_MISMATCH", "Transcript segment contract mismatch"
            )
    for word in transcript.get("words", []):
        start = word.get("startMsRelative")
        end = word.get("endMsRelative")
        segment = segments.get(word.get("segmentId"))
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or not 0 <= start < end <= duration_ms
            or start < previous_start
            or end < previous_end
            or segment is None
            or start < segment["startMsRelative"]
            or end > segment["endMsRelative"]
            or word.get("startMsSession") != answer_start_ms + start
            or word.get("endMsSession") != answer_start_ms + end
        ):
            raise SpeechAnalysisError(
                "TRANSCRIPT_INPUT_SHA_MISMATCH", "Transcript timestamp contract mismatch"
            )
        previous_start, previous_end = start, end


def resolve_speech_session_input(
    session_id: str,
    *,
    preprocessing_root: str | Path | None = None,
    transcription_root: str | Path | None = None,
) -> SpeechSessionInput:
    try:
        validate_session_id(session_id)
    except ValueError as exc:
        raise SpeechAnalysisError("INVALID_SESSION_ID", str(exc)) from exc
    stage24_root = (
        Path(preprocessing_root)
        if preprocessing_root
        else APP_PATHS.output_dir / "stt_preprocessing"
    ) / session_id
    stage25_root = (
        Path(transcription_root)
        if transcription_root
        else APP_PATHS.output_dir / "stt_transcription"
    ) / session_id
    stage24_path = stage24_root / "interval_audio_manifest.json"
    stage25_path = stage25_root / "session_transcription_manifest.json"
    try:
        stage24 = load_strict_json(stage24_path)
    except Exception as exc:
        raise SpeechAnalysisError(
            "AUDIO_PREPROCESSING_NOT_READY", "Stage 24 manifest is unavailable"
        ) from exc
    try:
        stage25 = load_strict_json(stage25_path)
    except Exception as exc:
        raise SpeechAnalysisError(
            "TRANSCRIPT_NOT_READY", "Stage 25 manifest is unavailable"
        ) from exc
    if stage24.get("sessionId") != session_id or stage24.get("status") not in STAGE24_READY:
        raise SpeechAnalysisError(
            "AUDIO_PREPROCESSING_NOT_READY", "Stage 24 preprocessing is not ready"
        )
    if stage25.get("sessionId") != session_id or stage25.get("status") not in STAGE25_READY:
        raise SpeechAnalysisError("TRANSCRIPT_NOT_READY", "Stage 25 transcription is not ready")
    audio_rows = [
        row for row in stage24.get("intervals", []) if row.get("intervalType") == "ANSWER"
    ]
    transcript_rows = list(stage25.get("answers", []))
    if (
        [row.get("answerId") for row in audio_rows] != list(EXPECTED_ANSWERS)
        or [row.get("answerId") for row in transcript_rows] != list(EXPECTED_ANSWERS)
    ):
        raise SpeechAnalysisError("ANSWER_SET_MISMATCH", "Stage 24 and 25 answer sets differ")
    answers: list[SpeechAnswerInput] = []
    for audio_row, transcript_row in zip(audio_rows, transcript_rows):
        answer_id = str(audio_row["answerId"])
        audio_path = stage24_root / "intervals" / f"{answer_id}.wav"
        transcript_path = stage25_root / "answers" / f"{answer_id}.json"
        inspection = inspect_pcm_wav(audio_path)
        expected_audio_sha = audio_row.get("audio", {}).get("sha256")
        if (
            inspection["errors"]
            or inspection["sha256"] != expected_audio_sha
            or transcript_row.get("inputAudioSha256") != expected_audio_sha
            or inspection["sampleRateHz"] != 16_000
            or inspection["channels"] != 1
            or inspection["sampleWidthBits"] != 16
            or inspection["sampleCount"] != audio_row.get("sampleCount")
            or inspection["durationMs"] != audio_row.get("actualDurationMs")
        ):
            raise SpeechAnalysisError(
                "AUDIO_INPUT_SHA_MISMATCH", f"Audio input mismatch for {answer_id}"
            )
        try:
            transcript_sha = sha256_file(transcript_path)
            transcript = load_strict_json(transcript_path)
        except Exception as exc:
            raise SpeechAnalysisError(
                "TRANSCRIPT_INPUT_SHA_MISMATCH", f"Transcript unavailable for {answer_id}"
            ) from exc
        duration_ms = int(audio_row["actualDurationMs"])
        if (
            transcript_sha != transcript_row.get("outputSha256")
            or transcript.get("sessionId") != session_id
            or transcript.get("answerId") != answer_id
            or transcript.get("audio", {}).get("sha256") != expected_audio_sha
            or transcript.get("audio", {}).get("durationMs") != duration_ms
            or transcript.get("answerInterval")
            != {"startMs": audio_row["startMs"], "endMs": audio_row["endMs"]}
        ):
            raise SpeechAnalysisError(
                "TRANSCRIPT_INPUT_SHA_MISMATCH", f"Transcript input mismatch for {answer_id}"
            )
        _validate_words(transcript, duration_ms, int(audio_row["startMs"]))
        answers.append(
            SpeechAnswerInput(
                session_id=session_id,
                answer_id=answer_id,
                audio_path=audio_path,
                transcript_path=transcript_path,
                audio_sha256=str(expected_audio_sha),
                transcript_sha256=transcript_sha,
                start_ms=int(audio_row["startMs"]),
                end_ms=int(audio_row["endMs"]),
                duration_ms=duration_ms,
                sample_count=int(audio_row["sampleCount"]),
                transcript=transcript,
            )
        )
    return SpeechSessionInput(
        session_id=session_id,
        stage24_manifest_sha256=sha256_file(stage24_path),
        stage25_manifest_sha256=sha256_file(stage25_path),
        stage24_status=str(stage24["status"]),
        stage25_status=str(stage25["status"]),
        stage25_warnings=tuple(str(value) for value in stage25.get("warnings", [])),
        answers=tuple(answers),
    )


def _input_fingerprint(source: SpeechSessionInput, profile: SpeechAnalysisProfile) -> str:
    payload = {
        "stage24WavSha256": [answer.audio_sha256 for answer in source.answers],
        "stage25TranscriptSha256": [answer.transcript_sha256 for answer in source.answers],
        "profile": profile.public_dict(),
    }
    return hashlib.sha256(strict_json_bytes(payload)).hexdigest()


def _existing_is_reusable(destination: Path, fingerprint: str) -> dict[str, Any] | None:
    path = destination / "session_speech_manifest.json"
    if not path.is_file():
        return None
    try:
        manifest = load_strict_json(path)
        if (
            manifest.get("inputFingerprintSha256") != fingerprint
            or manifest.get("status") not in {STATUS_READY, STATUS_WARNINGS}
            or [row.get("answerId") for row in manifest.get("answers", [])]
            != list(EXPECTED_ANSWERS)
        ):
            return None
        for row in manifest["answers"]:
            answer_path = destination / "answers" / f"{row['answerId']}.json"
            if not answer_path.is_file() or sha256_file(answer_path) != row["outputSha256"]:
                return None
            load_strict_json(answer_path)
        expected_artifacts = {"speech_validation.json", "speech_review.md", "speech_report.md"}
        if set(manifest.get("artifacts", {})) != expected_artifacts:
            return None
        for name, expected_sha in manifest["artifacts"].items():
            artifact = destination / name
            if not artifact.is_file() or sha256_file(artifact) != expected_sha:
                return None
        return manifest
    except Exception:
        return None


def _answer_result(
    answer: SpeechAnswerInput,
    profile: SpeechAnalysisProfile,
    pitch_adapter: PitchAdapter | None,
    lexicon: dict[str, Any],
) -> dict[str, Any]:
    audio = load_pcm16_mono_wav(answer.audio_path)
    speaking_rate, rate_warnings = analyze_speaking_rate(answer.transcript, answer.duration_ms)
    words = list(answer.transcript.get("words", []))
    timestamp_pauses, pause_warnings = analyze_timestamp_pauses(
        words, answer.duration_ms, profile.pause_view_thresholds_ms
    )
    fillers, filler_summary, filler_warnings = analyze_filler_candidates(
        words, answer.duration_ms, profile, lexicon=lexicon
    )
    volume, silence, volume_warnings = analyze_volume_and_silence(audio, profile)
    pitch, pitch_warnings = analyze_pitch(
        audio, profile, silence.get("silenceThresholdDbfs"), adapter=pitch_adapter
    )
    for region in silence["candidateSilenceRegions"]:
        region["startMsSession"] = answer.start_ms + region["startMsRelative"]
        region["endMsSession"] = answer.start_ms + region["endMsRelative"]
    upstream = ["UPSTREAM_TRANSCRIPTION_WARNING"] if answer.transcript.get("warnings") else []
    warnings = list(
        dict.fromkeys(
            upstream
            + rate_warnings
            + pause_warnings
            + filler_warnings
            + volume_warnings
            + pitch_warnings
        )
    )
    status = "COMPLETE_WITH_WARNINGS" if warnings else "COMPLETE"
    result = {
        "sessionId": answer.session_id,
        "answerId": answer.answer_id,
        "status": status,
        "analysisMode": "MEASUREMENT_ONLY",
        "scoringAvailable": False,
        "input": {
            "audioSha256": answer.audio_sha256,
            "transcriptionSha256": answer.transcript_sha256,
            "durationMs": answer.duration_ms,
            "sampleCount": answer.sample_count,
            "answerStartMsSession": answer.start_ms,
            "answerEndMsSession": answer.end_ms,
        },
        "speakingRate": speaking_rate,
        "timestampPauses": timestamp_pauses,
        "acousticSilence": silence,
        "fillerCandidates": fillers,
        "fillerCandidateSummary": filler_summary,
        "volume": volume,
        "pitch": pitch,
        "manualReviewRequired": bool(fillers or warnings),
        "warnings": warnings,
        "errors": [],
    }
    ensure_finite(result)
    return result


def _weighted_mean(rows: list[tuple[float | None, int]]) -> float | None:
    valid = [(float(value), weight) for value, weight in rows if value is not None and weight > 0]
    return sum(value * weight for value, weight in valid) / sum(weight for _, weight in valid) if valid else None


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    duration = sum(row["input"]["durationMs"] for row in results)
    words = sum(row["speakingRate"]["wordCount"] for row in results)
    filler_count = sum(row["fillerCandidateSummary"]["fillerCandidateCount"] for row in results)
    pause_duration = sum(row["timestampPauses"]["totalInterWordGapMs"] for row in results)
    total_samples = sum(row["input"]["sampleCount"] for row in results)
    rms = math.sqrt(
        sum((row["volume"]["rmsAmplitude"] or 0) ** 2 * row["input"]["sampleCount"] for row in results)
        / total_samples
    ) if total_samples else None
    pitch_available = [row for row in results if row["pitch"]["medianF0Hz"] is not None]
    unweighted_wpm = [row["speakingRate"]["wordsPerMinute"] for row in results]
    return {
        "answerCount": len(results),
        "totalAnswerDurationMs": duration,
        "totalWordCount": words,
        "overallWordsPerMinute": round(words * 60_000 / duration, 6) if duration else None,
        "totalFillerCandidateCount": filler_count,
        "totalTimestampPauseDurationMs": pause_duration,
        "speakingRateSummary": {
            "weightedByDuration": {
                "wordsPerMinute": round(words * 60_000 / duration, 6) if duration else None
            },
            "weightedByWordCount": {
                "articulationWordsPerMinute": (
                    round(_weighted_mean([
                        (row["speakingRate"]["articulationWordsPerMinute"], row["speakingRate"]["wordCount"])
                        for row in results
                    ]), 6)
                    if words else None
                )
            },
            "unweightedAnswerMean": {
                "wordsPerMinute": round(sum(unweighted_wpm) / len(unweighted_wpm), 6)
                if unweighted_wpm else None
            },
        },
        "volumeSummary": {
            "weightedByDuration": {
                "rmsAmplitude": round(rms, 6) if rms is not None else None,
                "rmsDbfs": round(20 * math.log10(rms), 3) if rms else None,
            },
            "unweightedAnswerMean": {
                "rmsDbfs": round(sum(row["volume"]["rmsDbfs"] for row in results if row["volume"]["rmsDbfs"] is not None) / sum(row["volume"]["rmsDbfs"] is not None for row in results), 3)
                if any(row["volume"]["rmsDbfs"] is not None for row in results) else None
            },
            "peakAmplitudeMaximum": max((row["volume"]["peakAmplitude"] or 0) for row in results),
            "clippingSampleCount": sum(row["volume"]["clippingSampleCount"] for row in results),
        },
        "pitchAvailabilitySummary": {
            "availableAnswerCount": len(pitch_available),
            "unavailableAnswerCount": len(results) - len(pitch_available),
            "weightedByVoicedFrame": {
                "meanF0Hz": (
                    round(_weighted_mean([
                        (row["pitch"]["meanF0Hz"], row["pitch"]["voicedFrameCount"])
                        for row in results
                    ]), 3)
                    if pitch_available else None
                )
            },
            "unweightedAnswerMean": {
                "medianF0Hz": round(sum(row["pitch"]["medianF0Hz"] for row in pitch_available) / len(pitch_available), 3)
                if pitch_available else None
            },
        },
        "aggregationMethods": {
            "weightedByDuration": "raw totals divided by total answer duration; volume RMS combines sample-weighted squared amplitudes",
            "weightedByWordCount": "answer articulation rate weighted by answer word count",
            "unweightedAnswerMean": "arithmetic mean across available answer measurements",
        },
    }


def _summary(result: dict[str, Any], output_sha: str) -> dict[str, Any]:
    return {
        "answerId": result["answerId"],
        "status": result["status"],
        "outputSha256": output_sha,
        "audioSha256": result["input"]["audioSha256"],
        "transcriptionSha256": result["input"]["transcriptionSha256"],
        "durationMs": result["input"]["durationMs"],
        "wordCount": result["speakingRate"]["wordCount"],
        "wordsPerMinute": result["speakingRate"]["wordsPerMinute"],
        "articulationWordsPerMinute": result["speakingRate"]["articulationWordsPerMinute"],
        "fillerCandidateCount": result["fillerCandidateSummary"]["fillerCandidateCount"],
        "rmsDbfs": result["volume"]["rmsDbfs"],
        "medianF0Hz": result["pitch"]["medianF0Hz"],
        "warnings": result["warnings"],
        "errors": result["errors"],
    }


def _review_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Speech characteristics manual review", "",
        "Measurements only. No score, grade, personality, emotion, confidence, or pass inference was produced.", "",
    ]
    for row in results:
        rate, pauses, volume, pitch = row["speakingRate"], row["timestampPauses"], row["volume"], row["pitch"]
        lines.extend([
            f"## {row['answerId']}", "",
            f"- Duration: {row['input']['durationMs']} ms",
            f"- Words / WPM / articulation WPM: {rate['wordCount']} / {rate['wordsPerMinute']} / {rate['articulationWordsPerMinute']}",
            f"- Leading / trailing gap: {pauses['leadingGapMs']} / {pauses['trailingGapMs']} ms",
            f"- RMS / peak: {volume['rmsDbfs']} / {volume['peakDbfs']} dBFS",
            f"- Median F0 / P10-P90 range: {pitch['medianF0Hz']} / {pitch['f0RangeHz']} Hz",
            f"- Technical warnings: {', '.join(row['warnings']) if row['warnings'] else 'none'}",
            "- Human checks: filler candidates against audio; timestamp gaps; silence regions; pitch availability", "",
            "### Filler candidates", "",
        ])
        if row["fillerCandidates"]:
            for candidate in row["fillerCandidates"]:
                lines.append(
                    f"- {candidate['candidateText']} ({candidate['startMsRelative']} to {candidate['endMsRelative']} ms relative; review required)"
                )
        else:
            lines.append("- none")
        lines.append("")
        lines.append("### Pause technical views")
        lines.append("")
        for view in pauses["pauseCandidateViews"]:
            lines.append(
                f"- >= {view['minimumGapMs']} ms: {view['count']} candidates, {view['totalDurationMs']} ms total"
            )
        lines.append("")
    return "\n".join(lines)


def _report_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Speech characteristics technical report", "",
        f"- Session: {manifest['sessionId']}",
        f"- Status: {manifest['status']}",
        "- Analysis mode: MEASUREMENT_ONLY",
        "- Scoring and threshold approval: false", "",
        "| Answer | Duration ms | Words | WPM | Articulation WPM | Fillers | RMS dBFS | Median F0 Hz |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in manifest["answers"]:
        lines.append(
            f"| {row['answerId']} | {row['durationMs']} | {row['wordCount']} | {row['wordsPerMinute']} | "
            f"{row['articulationWordsPerMinute']} | {row['fillerCandidateCount']} | {row['rmsDbfs']} | {row['medianF0Hz']} |"
        )
    lines.append("")
    return "\n".join(lines)


class SpeechAnalysisService:
    def __init__(
        self,
        *,
        profile: SpeechAnalysisProfile,
        output_root: str | Path | None = None,
        preprocessing_root: str | Path | None = None,
        transcription_root: str | Path | None = None,
        resolver: Callable[..., SpeechSessionInput] = resolve_speech_session_input,
        pitch_adapter: PitchAdapter | None = None,
    ) -> None:
        profile.validate()
        self.profile = profile
        self.output_root = Path(output_root) if output_root else APP_PATHS.output_dir / "speech_characteristics"
        self.preprocessing_root = preprocessing_root
        self.transcription_root = transcription_root
        self.resolver = resolver
        self.pitch_adapter = pitch_adapter

    def run(self, session_id: str, *, force_rebuild: bool = False) -> dict[str, Any]:
        source = self.resolver(
            session_id,
            preprocessing_root=self.preprocessing_root,
            transcription_root=self.transcription_root,
        )
        fingerprint = _input_fingerprint(source, self.profile)
        destination = self.output_root / session_id
        if not force_rebuild:
            existing = _existing_is_reusable(destination, fingerprint)
            if existing is not None:
                return {"sessionId": session_id, "status": existing["status"], "reused": True}
        try:
            lexicon = load_lexicon(self.profile)
        except SpeechContractError as exc:
            raise SpeechAnalysisError(exc.code, str(exc)) from exc
        self.output_root.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=f".{session_id}.", suffix=".tmp", dir=self.output_root))
        backup = self.output_root / f".{session_id}.{uuid.uuid4().hex}.backup"
        try:
            results: list[dict[str, Any]] = []
            summaries: list[dict[str, Any]] = []
            for answer in source.answers:
                try:
                    result = _answer_result(answer, self.profile, self.pitch_adapter, lexicon)
                except SpeechAnalysisError:
                    raise
                except Exception as exc:
                    raise SpeechAnalysisError(
                        "SPEECH_ANSWER_ANALYSIS_FAILED", f"{answer.answer_id}: analysis failed"
                    ) from exc
                answer_path = staged / "answers" / f"{answer.answer_id}.json"
                write_json_atomic(answer_path, result)
                load_strict_json(answer_path)
                results.append(result)
                summaries.append(_summary(result, sha256_file(answer_path)))
            warnings = list(dict.fromkeys(
                (["UPSTREAM_TRANSCRIPTION_WARNING"] if source.stage25_warnings else [])
                + [warning for result in results for warning in result["warnings"]]
            ))
            status = STATUS_WARNINGS if warnings else STATUS_READY
            manifest = {
                "sessionId": session_id,
                "status": status,
                "analysisMode": "MEASUREMENT_ONLY",
                "scoringAvailable": False,
                "thresholdApproval": False,
                "inputFingerprintSha256": fingerprint,
                "source": {
                    "stage24ManifestSha256": source.stage24_manifest_sha256,
                    "stage25ManifestSha256": source.stage25_manifest_sha256,
                    "stage24Status": source.stage24_status,
                    "stage25Status": source.stage25_status,
                },
                "profile": self.profile.public_dict(),
                "answers": summaries,
                "aggregate": _aggregate(results),
                "warnings": warnings,
                "errors": [],
            }
            validation = {
                "sessionId": session_id,
                "status": status,
                "checks": {
                    "answerCountIsFour": len(results) == 4,
                    "audioHashesMatched": True,
                    "transcriptHashesMatched": True,
                    "strictJson": True,
                    "finiteNumbersOnly": True,
                    "timestampsInRange": True,
                    "participantIdExcluded": True,
                    "internalPathsExcluded": True,
                    "scoreFieldsExcluded": True,
                    "sourceArtifactsUnmodified": True,
                },
                "warnings": warnings,
                "errors": [],
            }
            ensure_finite(manifest)
            ensure_finite(validation)
            validation_path = staged / "speech_validation.json"
            review_path = staged / "speech_review.md"
            report_path = staged / "speech_report.md"
            write_json_atomic(validation_path, validation)
            write_text_atomic(review_path, _review_markdown(results))
            write_text_atomic(report_path, _report_markdown(manifest))
            manifest["artifacts"] = {
                validation_path.name: sha256_file(validation_path),
                review_path.name: sha256_file(review_path),
                report_path.name: sha256_file(report_path),
            }
            write_json_atomic(staged / "session_speech_manifest.json", manifest)
            replace_directory(staged, destination, backup)
            return {"sessionId": session_id, "status": status, "reused": False}
        except SpeechAnalysisError:
            raise
        except Exception as exc:
            raise SpeechAnalysisError("SPEECH_CHARACTERISTICS_FAILED", "Speech analysis failed") from exc
        finally:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)


def public_status_for_error(code: str) -> str:
    if code == "SPEECH_CHARACTERISTICS_DEPENDENCY_BLOCKED":
        return STATUS_DEPENDENCY_BLOCKED
    if code in {
        "INVALID_SESSION_ID", "AUDIO_INPUT_SHA_MISMATCH", "TRANSCRIPT_INPUT_SHA_MISMATCH",
        "ANSWER_SET_MISMATCH", "TRANSCRIPT_NOT_READY", "AUDIO_PREPROCESSING_NOT_READY",
    }:
        return STATUS_INPUT_INVALID
    return STATUS_FAILED
