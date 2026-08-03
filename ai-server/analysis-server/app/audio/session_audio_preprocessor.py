"""Session-resolved, idempotent STT audio preprocessing pipeline."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable
import uuid

from scripts.convert_audio import convert_audio as convert_audio_to_stt
from scripts.convert_audio import find_ffmpeg as find_existing_ffmpeg

from app.core.config import ANALYSIS_SERVER_ROOT, APP_PATHS

from .audio_contracts import (
    AudioContractError,
    AudioInterval,
    SessionAudioInput,
    SOURCE_DURATION_TOLERANCE_MS,
    audio_contract,
    validate_session_id,
)
from .audio_manifest_writer import ensure_finite, strict_json_bytes, write_json_atomic, write_text_atomic
from .interval_audio_extractor import extract_intervals, inspect_pcm_wav, sha256_file


PARTICIPANT_PATTERN = re.compile(r"^PTC_\d{6}$")
STATUS_READY = "stt_audio_preprocessing_ready"
STATUS_WARNINGS = "stt_audio_preprocessing_ready_with_warnings"
STATUS_FAILED = "stt_audio_preprocessing_failed"


class PreprocessingError(RuntimeError):
    """Stable technical failure from the preprocessing pipeline."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _reject_constant(value: str) -> None:
    raise PreprocessingError("NON_FINITE_JSON", f"Non-finite JSON value: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreprocessingError("DUPLICATE_JSON_KEY", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_strict_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8-sig"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except PreprocessingError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreprocessingError("INVALID_JSON", "Canonical session metadata is invalid") from exc
    if not isinstance(value, dict):
        raise PreprocessingError("INVALID_JSON", "Canonical session metadata must be an object")
    ensure_finite(value)
    return value


def _session_intervals(metadata: dict[str, Any]) -> tuple[AudioInterval, ...]:
    baseline = metadata.get("baseline_interval")
    answers = metadata.get("answers")
    if not isinstance(baseline, dict) or not isinstance(answers, list):
        raise PreprocessingError("INVALID_INTERVAL", "Canonical interval contract is missing")
    try:
        intervals = [
            AudioInterval(
                interval_type="BASELINE",
                output_id="BASELINE",
                start_ms=baseline["start_timestamp_ms"],
                end_ms=baseline["end_timestamp_ms"],
            )
        ]
        for answer in answers:
            if not isinstance(answer, dict):
                raise AudioContractError("INVALID_INTERVAL", "Answer interval must be an object")
            intervals.append(
                AudioInterval(
                    interval_type="ANSWER",
                    output_id=answer["answer_id"],
                    answer_id=answer["answer_id"],
                    start_ms=answer["start_timestamp_ms"],
                    end_ms=answer["end_timestamp_ms"],
                )
            )
    except (AudioContractError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, AudioContractError) else "INVALID_INTERVAL"
        raise PreprocessingError(code, "Canonical interval contract is invalid") from exc
    identities = [item.output_id for item in intervals]
    if len(identities) != len(set(identities)):
        raise PreprocessingError("INVALID_INTERVAL", "Duplicate interval identity")
    ordered = sorted(intervals, key=lambda item: (item.start_ms, item.end_ms))
    for left, right in zip(ordered, ordered[1:]):
        if right.start_ms < left.end_ms:
            raise PreprocessingError("INVALID_INTERVAL", "Intervals overlap")
    return tuple(intervals)


def resolve_session_input(
    session_id: str,
    *,
    vision_server_root: str | Path | None = None,
) -> SessionAudioInput:
    """Resolve the Stage 15 canonical incoming triplet without caller paths."""
    try:
        validate_session_id(session_id)
    except AudioContractError as exc:
        raise PreprocessingError(exc.code, str(exc)) from exc
    vision_root = Path(vision_server_root) if vision_server_root else ANALYSIS_SERVER_ROOT.parent / "vision-server"
    incoming = vision_root / "data" / "pilot" / "incoming"
    metadata_candidates = sorted(incoming.glob(f"*_{session_id}.metadata.json"))
    if len(metadata_candidates) != 1:
        raise PreprocessingError("SESSION_NOT_FOUND", "Canonical session metadata was not uniquely resolved")
    metadata_path = metadata_candidates[0]
    metadata = load_strict_json(metadata_path)
    participant_id = metadata.get("participant_id")
    if not isinstance(participant_id, str) or PARTICIPANT_PATTERN.fullmatch(participant_id) is None:
        raise PreprocessingError("INVALID_PARTICIPANT_ID", "Canonical participant reference is invalid")
    if metadata.get("session_id") != session_id or metadata.get("withdrawn") is not False:
        raise PreprocessingError("SESSION_NOT_AVAILABLE", "Canonical session is not available for analysis")
    expected_stem = f"{participant_id}_{session_id}"
    video_name = metadata.get("video_file")
    if (
        not isinstance(video_name, str)
        or Path(video_name).name != video_name
        or Path(video_name).stem != expected_stem
        or Path(video_name).suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}
    ):
        raise PreprocessingError("INVALID_VIDEO_REFERENCE", "Canonical video reference is invalid")
    video_path = incoming / video_name
    consent_path = incoming / f"{expected_stem}.consent.json"
    if not video_path.is_file():
        raise PreprocessingError("SESSION_VIDEO_MISSING", "Canonical session video is missing")
    consent = load_strict_json(consent_path)
    if (
        consent.get("participant_id") != participant_id
        or consent.get("consent_reference_id") != metadata.get("consent_reference_id")
        or consent.get("consent_status") != "GRANTED"
        or consent.get("video_collection_allowed") is not True
        or consent.get("automated_analysis_allowed") is not True
        or consent.get("withdrawn_at") is not None
    ):
        raise PreprocessingError("CONSENT_NOT_GRANTED", "Canonical consent does not permit analysis")
    actual_sha = sha256_file(video_path)
    if actual_sha != metadata.get("expected_sha256"):
        raise PreprocessingError("SOURCE_HASH_MISMATCH", "Canonical session video checksum mismatch")
    return SessionAudioInput(
        session_id=session_id,
        video_path=video_path,
        metadata_path=metadata_path,
        source_sha256=actual_sha,
        intervals=_session_intervals(metadata),
    )


def resolve_ffmpeg(explicit_path: str | Path | None = None) -> Path | None:
    candidate, error = (
        find_existing_ffmpeg()
        if explicit_path is None
        else find_existing_ffmpeg(Path(explicit_path))
    )
    if error == "FFMPEG_NOT_FOUND":
        return None
    if error is not None:
        raise PreprocessingError(error, "Configured FFmpeg executable is invalid")
    return candidate


def probe_media(path: str | Path, *, ffmpeg_path: Path | None = None) -> dict[str, Any]:
    """Inspect media with PyAV and cross-check with ffprobe when available."""
    try:
        import av  # type: ignore[import-not-found]
    except ImportError as exc:
        raise PreprocessingError("AUDIO_DECODE_FAILED", "PyAV is unavailable") from exc
    source = Path(path)
    try:
        with av.open(str(source)) as container:
            audio_streams = list(container.streams.audio)
            video_streams = list(container.streams.video)
            if not audio_streams:
                raise PreprocessingError("AUDIO_STREAM_MISSING", "No audio stream was found")
            audio = audio_streams[0]
            video = video_streams[0] if video_streams else None
            duration_seconds = None
            if audio.duration is not None and audio.time_base is not None:
                duration_seconds = float(audio.duration * audio.time_base)
            elif container.duration is not None:
                duration_seconds = container.duration / 1_000_000
            metadata: dict[str, Any] = {
                "audioStreamCount": len(audio_streams),
                "videoStreamCount": len(video_streams),
                "videoCodec": video.codec_context.name if video is not None else None,
                "videoWidth": video.codec_context.width if video is not None else None,
                "videoHeight": video.codec_context.height if video is not None else None,
                "videoFps": float(video.average_rate) if video is not None and video.average_rate else None,
                "videoFrameCount": video.frames if video is not None and video.frames else None,
                "audioCodec": audio.codec_context.name,
                "audioSampleRateHz": audio.codec_context.sample_rate,
                "audioChannels": audio.codec_context.channels,
                "durationMs": round(duration_seconds * 1000) if duration_seconds is not None else None,
                "probeMethods": ["PYAV"],
                "ffprobeCrossCheck": None,
            }
    except PreprocessingError:
        raise
    except Exception as exc:
        raise PreprocessingError("AUDIO_DECODE_FAILED", "Media probing failed") from exc
    ffprobe = None
    if ffmpeg_path is not None:
        sibling = ffmpeg_path.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.is_file():
            ffprobe = sibling
    if ffprobe is None:
        discovered = shutil.which("ffprobe")
        ffprobe = Path(discovered) if discovered else None
    if ffprobe is not None:
        command = [
            str(ffprobe), "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,codec_name,sample_rate,channels",
            "-of", "json", str(source),
        ]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=30, check=False
            )
            if completed.returncode == 0:
                payload = json.loads(completed.stdout)
                streams = payload.get("streams", [])
                metadata["probeMethods"].append("FFPROBE")
                metadata["ffprobeCrossCheck"] = {
                    "audioStreamCount": sum(item.get("codec_type") == "audio" for item in streams),
                    "durationMs": round(float(payload["format"]["duration"]) * 1000),
                }
        except (KeyError, OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
            metadata["ffprobeCrossCheck"] = {"available": False}
    return metadata


def _decode_with_ffmpeg(source: Path, output: Path, executable: Path) -> None:
    result = convert_audio_to_stt(
        source,
        output,
        overwrite=True,
        ffmpeg_path=executable,
        validate_output=False,
    )
    if not result["success"]:
        raise PreprocessingError("AUDIO_DECODE_FAILED", "FFmpeg could not decode the source")


def _decode_with_pyav(source: Path, output: Path) -> None:
    try:
        import av  # type: ignore[import-not-found]
        input_container = av.open(str(source))
        audio_streams = list(input_container.streams.audio)
        if not audio_streams:
            input_container.close()
            raise PreprocessingError("AUDIO_STREAM_MISSING", "No audio stream was found")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16_000)
        with av.open(str(output), mode="w", format="wav") as target:
            target_stream = target.add_stream("pcm_s16le", rate=16_000)
            target_stream.layout = "mono"
            for frame in input_container.decode(audio_streams[0]):
                for converted in resampler.resample(frame):
                    for packet in target_stream.encode(converted):
                        target.mux(packet)
            for converted in resampler.resample(None):
                for packet in target_stream.encode(converted):
                    target.mux(packet)
            for packet in target_stream.encode(None):
                target.mux(packet)
        input_container.close()
    except PreprocessingError:
        raise
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise PreprocessingError("AUDIO_DECODE_FAILED", "PyAV could not decode the source") from exc


def extract_source_audio(
    source: str | Path,
    output: str | Path,
    *,
    ffmpeg_path: str | Path | None = None,
) -> tuple[str, list[str]]:
    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    executable = resolve_ffmpeg(ffmpeg_path)
    warnings: list[str] = []
    if executable is not None:
        _decode_with_ffmpeg(source_path, output_path, executable)
        method = "FFMPEG"
    else:
        _decode_with_pyav(source_path, output_path)
        method = "PYAV"
        warnings.append("FFMPEG_UNAVAILABLE_PYAV_FALLBACK")
    inspection = inspect_pcm_wav(output_path)
    if inspection["errors"]:
        output_path.unlink(missing_ok=True)
        raise PreprocessingError(inspection["errors"][0], "Decoded WAV violates the audio contract")
    return method, warnings


def _contract_sha(intervals: tuple[AudioInterval, ...]) -> str:
    payload = {
        "audioContract": audio_contract(),
        "intervals": [item.contract_dict() for item in intervals],
    }
    return hashlib.sha256(strict_json_bytes(payload)).hexdigest()


def _public_interval(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in (
            "intervalType", "answerId", "startMs", "endMs", "startSample",
            "endSample", "expectedDurationMs", "expectedSampleCount",
            "actualDurationMs", "sampleCount", "status", "warnings", "audio",
        )
    }


def _existing_is_reusable(
    output: Path,
    source_sha: str,
    contract_sha: str,
) -> dict[str, Any] | None:
    manifest_path = output / "interval_audio_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = load_strict_json(manifest_path)
        if (
            manifest.get("source", {}).get("inputSha256") != source_sha
            or manifest.get("intervalContractSha256") != contract_sha
            or manifest.get("status") not in {STATUS_READY, STATUS_WARNINGS}
        ):
            return None
        source_audio = output / "source_audio" / f"{manifest['sessionId']}_source.wav"
        expected = [source_audio] + [
            output / "intervals" / (
                "BASELINE.wav" if item["intervalType"] == "BASELINE" else f"{item['answerId']}.wav"
            )
            for item in manifest["intervals"]
        ]
        if not all(path.is_file() and path.stat().st_size > 0 for path in expected):
            return None
        if sha256_file(source_audio) != manifest["source"]["sha256"]:
            return None
        for path, item in zip(expected[1:], manifest["intervals"]):
            if sha256_file(path) != item["audio"]["sha256"]:
                return None
        return manifest
    except (KeyError, OSError, PreprocessingError, TypeError):
        return None


def _report(manifest: dict[str, Any], method: str) -> str:
    lines = [
        "# STT audio preprocessing report",
        "",
        f"- Session: {manifest['sessionId']}",
        f"- Status: {manifest['status']}",
        f"- Decode method: {method}",
        f"- Source duration: {manifest['source']['durationMs']} ms",
        f"- Source samples: {manifest['source']['sampleCount']}",
        f"- Interval boundary: {manifest['audioContract']['intervalRule']}",
        f"- Boundary conversion: {manifest['audioContract']['boundaryConversion']}",
        f"- Duration tolerance: {manifest['audioContract']['durationToleranceMs']} ms",
        f"- Source duration tolerance: {manifest['audioContract']['sourceDurationToleranceMs']} ms",
        "",
        "| Interval | Expected ms | Actual ms | Expected samples | Actual samples | Status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for item in manifest["intervals"]:
        identity = item["answerId"] or "BASELINE"
        lines.append(
            f"| {identity} | {item['expectedDurationMs']} | {item['actualDurationMs']} | "
            f"{item['expectedSampleCount']} | {item['sampleCount']} | {item['status']} |"
        )
    lines.extend(["", "No padding, denoising, gain change, silence removal, or time-axis change was applied.", ""])
    return "\n".join(lines)


class SessionAudioPreprocessor:
    def __init__(
        self,
        *,
        output_root: str | Path | None = None,
        vision_server_root: str | Path | None = None,
        ffmpeg_path: str | Path | None = None,
        resolver: Callable[..., SessionAudioInput] = resolve_session_input,
    ) -> None:
        self.output_root = Path(output_root) if output_root else APP_PATHS.output_dir / "stt_preprocessing"
        self.vision_server_root = Path(vision_server_root) if vision_server_root else ANALYSIS_SERVER_ROOT.parent / "vision-server"
        self.ffmpeg_path = Path(ffmpeg_path) if ffmpeg_path else None
        self.resolver = resolver

    def run(self, session_id: str, *, force_rebuild: bool = False) -> dict[str, Any]:
        try:
            session = self.resolver(session_id, vision_server_root=self.vision_server_root)
        except TypeError:
            session = self.resolver(session_id)
        contract_sha = _contract_sha(session.intervals)
        destination = self.output_root / session.session_id
        if not force_rebuild:
            reusable = _existing_is_reusable(destination, session.source_sha256, contract_sha)
            if reusable is not None:
                return {"sessionId": session.session_id, "status": reusable["status"], "reused": True}
        self.output_root.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=f".{session.session_id}.", suffix=".tmp", dir=self.output_root))
        backup: Path | None = None
        try:
            ffmpeg = resolve_ffmpeg(self.ffmpeg_path)
            media = probe_media(session.video_path, ffmpeg_path=ffmpeg)
            source_wav = staged / "source_audio" / f"{session.session_id}_source.wav"
            method, decode_warnings = extract_source_audio(
                session.video_path, source_wav, ffmpeg_path=self.ffmpeg_path
            )
            source_audio = inspect_pcm_wav(source_wav)
            ffprobe_check = media.get("ffprobeCrossCheck")
            reference_duration = (
                ffprobe_check.get("durationMs")
                if isinstance(ffprobe_check, dict) and isinstance(ffprobe_check.get("durationMs"), int)
                else media.get("durationMs")
            )
            source_duration_difference = (
                abs(source_audio["durationMs"] - reference_duration)
                if isinstance(reference_duration, int)
                else None
            )
            source_duration_within_tolerance = (
                source_duration_difference is None
                or source_duration_difference <= SOURCE_DURATION_TOLERANCE_MS
            )
            max_end = max(item.end_sample for item in session.intervals)
            if max_end > source_audio["sampleCount"]:
                raise PreprocessingError("INTERVAL_OUT_OF_RANGE", "Interval exceeds decoded audio")
            try:
                extracted = extract_intervals(source_wav, staged / "intervals", session.intervals)
            except AudioContractError as exc:
                raise PreprocessingError(exc.code, str(exc)) from exc
            duration_warnings = [] if source_duration_within_tolerance else ["DURATION_MISMATCH"]
            warnings = sorted(
                set(decode_warnings + duration_warnings + source_audio["warnings"] + [
                    warning for item in extracted for warning in item["warnings"]
                ])
            )
            status = STATUS_WARNINGS if warnings else STATUS_READY
            manifest = {
                "sessionId": session.session_id,
                "status": status,
                "audioContract": audio_contract(),
                "intervalContractSha256": contract_sha,
                "source": {
                    "durationMs": source_audio["durationMs"],
                    "sampleCount": source_audio["sampleCount"],
                    "sha256": source_audio["sha256"],
                    "inputSha256": session.source_sha256,
                },
                "intervals": [_public_interval(item) for item in extracted],
                "warnings": warnings,
                "errors": [],
            }
            source_metadata = {
                "sessionId": session.session_id,
                "status": "COMPLETE_WITH_WARNINGS" if decode_warnings else "COMPLETE",
                "decodeMethod": method,
                "sourceMedia": media,
                "standardAudio": source_audio,
                "sourceDurationValidation": {
                    "referenceDurationMs": reference_duration,
                    "decodedDurationMs": source_audio["durationMs"],
                    "differenceMs": source_duration_difference,
                    "toleranceMs": SOURCE_DURATION_TOLERANCE_MS,
                    "withinTolerance": source_duration_within_tolerance,
                },
                "warnings": decode_warnings + duration_warnings + source_audio["warnings"],
                "errors": [],
            }
            validation = {
                "sessionId": session.session_id,
                "status": status,
                "checks": {
                    "sourceReadable": source_audio["readable"],
                    "sourceDecodable": source_audio["decodable"],
                    "sourceContractValid": not source_audio["errors"],
                    "sourceDurationWithinTolerance": source_duration_within_tolerance,
                    "allIntervalsComplete": all(item["status"] in {"COMPLETE", "COMPLETE_WITH_WARNINGS"} for item in extracted),
                    "allDurationsWithinTolerance": all(abs(item["actualDurationMs"] - item["expectedDurationMs"]) <= 1 for item in extracted),
                    "allSampleCountsExact": all(item["sampleCount"] == item["expectedSampleCount"] for item in extracted),
                    "noEmptyFiles": all(item["audio"]["fileSizeBytes"] > 0 for item in extracted),
                },
                "warnings": warnings,
                "errors": [],
            }
            ensure_finite(manifest)
            write_json_atomic(staged / "source_audio_metadata.json", source_metadata)
            write_json_atomic(staged / "interval_audio_manifest.json", manifest)
            write_json_atomic(staged / "preprocessing_validation.json", validation)
            write_text_atomic(staged / "preprocessing_report.md", _report(manifest, method))
            if destination.exists():
                backup = self.output_root / f".{session.session_id}.{uuid.uuid4().hex}.backup"
                os.replace(destination, backup)
            os.replace(staged, destination)
            if backup is not None:
                shutil.rmtree(backup)
            return {"sessionId": session.session_id, "status": status, "reused": False}
        except PreprocessingError:
            raise
        except Exception as exc:
            raise PreprocessingError("AUDIO_DECODE_FAILED", "STT preprocessing failed") from exc
        finally:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            if backup is not None and backup.exists() and not destination.exists():
                os.replace(backup, destination)
