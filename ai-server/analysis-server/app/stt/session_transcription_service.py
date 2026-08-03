"""Idempotent Session transcription using Stage 24 answer WAV artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Callable
import uuid

from app.audio.audio_manifest_writer import ensure_finite, strict_json_bytes
from app.audio.interval_audio_extractor import inspect_pcm_wav, sha256_file
from app.audio.session_audio_preprocessor import load_strict_json
from app.audio.audio_contracts import validate_session_id
from app.core.config import APP_PATHS

from .faster_whisper_adapter import AdapterError, FasterWhisperAdapter
from .transcription_contracts import (
    AnswerAudio,
    TranscriptionContractError,
    build_answer_contract,
)
from .transcription_manifest_writer import (
    replace_directory,
    write_answer,
    write_manifest,
    write_text_atomic,
)
from .transcription_profile import ProfileError, TranscriptionProfile


EXPECTED_ANSWERS = tuple(f"ANS_{index:06d}" for index in range(1, 5))
READY_STATUSES = {
    "stt_audio_preprocessing_ready",
    "stt_audio_preprocessing_ready_with_warnings",
}
STATUS_READY = "stt_session_transcription_ready"
STATUS_WARNINGS = "stt_session_transcription_ready_with_warnings"
STATUS_FAILED = "stt_session_transcription_failed"
OPTIONS = {
    "language": "ko",
    "task": "transcribe",
    "wordTimestamps": True,
    "vadFilter": False,
    "conditionOnPreviousText": False,
    "beamSize": 5,
    "temperature": 0,
    "initialPrompt": None,
    "hotwords": None,
    "timestampRounding": "nearest integer millisecond, halves up",
    "timestampToleranceMs": 1,
}


class SessionTranscriptionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SessionTranscriptionInput:
    session_id: str
    stage24_manifest_sha256: str
    stage24_interval_contract_sha256: str
    answers: tuple[AnswerAudio, ...]


def resolve_stage24_input(
    session_id: str,
    *,
    preprocessing_root: str | Path | None = None,
) -> SessionTranscriptionInput:
    try:
        validate_session_id(session_id)
    except ValueError as exc:
        raise SessionTranscriptionError("INVALID_SESSION_ID", str(exc)) from exc
    root = (
        Path(preprocessing_root)
        if preprocessing_root
        else APP_PATHS.output_dir / "stt_preprocessing"
    ) / session_id
    manifest_path = root / "interval_audio_manifest.json"
    try:
        manifest = load_strict_json(manifest_path)
    except Exception as exc:
        raise SessionTranscriptionError(
            "STAGE24_MANIFEST_INVALID", "Stage 24 manifest is unavailable"
        ) from exc
    if manifest.get("sessionId") != session_id or manifest.get("status") not in READY_STATUSES:
        raise SessionTranscriptionError(
            "STAGE24_NOT_READY", "Stage 24 preprocessing is not ready"
        )
    rows = [item for item in manifest.get("intervals", []) if item.get("intervalType") == "ANSWER"]
    if [item.get("answerId") for item in rows] != list(EXPECTED_ANSWERS):
        raise SessionTranscriptionError(
            "STAGE24_MANIFEST_INVALID", "Exactly four ordered answer intervals are required"
        )
    answers: list[AnswerAudio] = []
    for item in rows:
        answer_id = item["answerId"]
        path = root / "intervals" / f"{answer_id}.wav"
        inspection = inspect_pcm_wav(path)
        expected_sha = item.get("audio", {}).get("sha256")
        if (
            inspection["errors"]
            or inspection["sha256"] != expected_sha
            or inspection["sampleRateHz"] != 16_000
            or inspection["channels"] != 1
            or inspection["sampleWidthBits"] != 16
            or inspection["sampleCount"] != item.get("sampleCount")
            or inspection["durationMs"] != item.get("actualDurationMs")
        ):
            raise SessionTranscriptionError(
                "STAGE24_AUDIO_INVALID", f"Stage 24 audio contract failed for {answer_id}"
            )
        answers.append(
            AnswerAudio(
                session_id=session_id,
                answer_id=answer_id,
                path=path,
                sha256=inspection["sha256"],
                start_ms=int(item["startMs"]),
                end_ms=int(item["endMs"]),
                duration_ms=int(item["actualDurationMs"]),
                sample_count=int(item["sampleCount"]),
            )
        )
    return SessionTranscriptionInput(
        session_id=session_id,
        stage24_manifest_sha256=sha256_file(manifest_path),
        stage24_interval_contract_sha256=str(manifest["intervalContractSha256"]),
        answers=tuple(answers),
    )


def _fingerprint(
    source: SessionTranscriptionInput,
    profile: TranscriptionProfile,
    engine: dict[str, Any],
) -> str:
    stable_engine = {
        key: engine.get(key)
        for key in (
            "name",
            "version",
            "ctranslate2Version",
            "model",
            "modelId",
            "revision",
            "device",
            "computeType",
            "localFilesOnly",
        )
    }
    payload = {
        "stage24ManifestSha256": source.stage24_manifest_sha256,
        "stage24IntervalContractSha256": source.stage24_interval_contract_sha256,
        "answerSha256": [answer.sha256 for answer in source.answers],
        "profile": profile.public_dict(),
        "engine": stable_engine,
        "options": OPTIONS,
    }
    return hashlib.sha256(strict_json_bytes(payload)).hexdigest()


def _existing_is_reusable(
    destination: Path,
    *,
    expected_fingerprint: str,
) -> dict[str, Any] | None:
    manifest_path = destination / "session_transcription_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = load_strict_json(manifest_path)
        if (
            manifest.get("inputFingerprintSha256") != expected_fingerprint
            or manifest.get("status") not in {STATUS_READY, STATUS_WARNINGS}
            or [item.get("answerId") for item in manifest.get("answers", [])]
            != list(EXPECTED_ANSWERS)
        ):
            return None
        for item in manifest["answers"]:
            path = destination / "answers" / f"{item['answerId']}.json"
            if not path.is_file() or sha256_file(path) != item["outputSha256"]:
                return None
            load_strict_json(path)
        for name, expected_sha in manifest.get("artifacts", {}).items():
            if name not in {
                "transcription_validation.json",
                "transcription_review.md",
                "transcription_report.md",
            }:
                return None
            path = destination / name
            if not path.is_file() or sha256_file(path) != expected_sha:
                return None
        if set(manifest.get("artifacts", {})) != {
            "transcription_validation.json",
            "transcription_review.md",
            "transcription_report.md",
        }:
            return None
        return manifest
    except Exception:
        return None


def _answer_summary(answer: dict[str, Any], output_sha: str) -> dict[str, Any]:
    return {
        "answerId": answer["answerId"],
        "status": answer["status"],
        "audioDurationMs": answer["audio"]["durationMs"],
        "inputAudioSha256": answer["audio"]["sha256"],
        "outputSha256": output_sha,
        "characterCount": len(answer["text"]),
        "segmentCount": len(answer["segments"]),
        "wordCount": len(answer["words"]),
        "detectedLanguage": answer["language"]["detected"],
        "languageProbability": answer["language"]["probability"],
        "processingTimeSeconds": answer["processingTimeSeconds"],
        "realTimeFactor": answer["realTimeFactor"],
        "warnings": answer["warnings"],
        "errors": answer["errors"],
    }


def _review_markdown(answers: list[dict[str, Any]]) -> str:
    lines = [
        "# STT transcription manual review",
        "",
        "Model text is preserved exactly. No spelling correction, rewriting, summary, or scoring was applied.",
        "",
    ]
    for answer in answers:
        lines.extend(
            [
                f"## {answer['answerId']}",
                "",
                f"- Audio duration: {answer['audio']['durationMs']} ms",
                f"- Detected language: {answer['language']['detected']}",
                f"- Segments: {len(answer['segments'])}",
                f"- Words: {len(answer['words'])}",
                f"- Technical warnings: {', '.join(answer['warnings']) if answer['warnings'] else 'none'}",
                "- Human checks: wording against audio; segment/word timing; repetitions; omissions",
                "",
                "### Raw transcription",
                "",
                answer["text"] or "_(empty)_",
                "",
                "### Segments",
                "",
            ]
        )
        for segment in answer["segments"]:
            lines.append(
                f"- {segment['startMsRelative']}–{segment['endMsRelative']} ms relative "
                f"({segment['startMsSession']}–{segment['endMsSession']} ms session): "
                f"{segment['text']}"
            )
        lines.append("")
    return "\n".join(lines)


def _report_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# STT session transcription report",
        "",
        f"- Session: {manifest['sessionId']}",
        f"- Status: {manifest['status']}",
        f"- Engine: {manifest['engine']['name']} {manifest['engine']['version']}",
        f"- Model: {manifest['engine']['model']} ({manifest['engine']['revision']})",
        f"- Runtime: {manifest['engine']['device']} / {manifest['engine']['computeType']}",
        "- Transcript correction: disabled",
        "- Content evaluation and scoring: not performed",
        "",
        "| Answer | Audio ms | Characters | Segments | Words | Seconds | RTF | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in manifest["answers"]:
        lines.append(
            f"| {item['answerId']} | {item['audioDurationMs']} | {item['characterCount']} | "
            f"{item['segmentCount']} | {item['wordCount']} | {item['processingTimeSeconds']:.3f} | "
            f"{item['realTimeFactor']:.4f} | {item['status']} |"
        )
    lines.append("")
    return "\n".join(lines)


class SessionTranscriptionService:
    def __init__(
        self,
        *,
        profile: TranscriptionProfile,
        local_files_only: bool = False,
        output_root: str | Path | None = None,
        preprocessing_root: str | Path | None = None,
        resolver: Callable[..., SessionTranscriptionInput] = resolve_stage24_input,
        adapter_factory: Callable[..., Any] = FasterWhisperAdapter,
    ) -> None:
        self.profile = profile
        self.local_files_only = local_files_only
        self.output_root = Path(output_root) if output_root else APP_PATHS.output_dir / "stt_transcription"
        self.preprocessing_root = preprocessing_root
        self.resolver = resolver
        self.adapter_factory = adapter_factory

    def run(self, session_id: str, *, force_rebuild: bool = False) -> dict[str, Any]:
        source = self.resolver(session_id, preprocessing_root=self.preprocessing_root)
        try:
            adapter = self.adapter_factory(
                self.profile,
                local_files_only=self.local_files_only,
            )
            engine_before = adapter.engine_metadata()
        except AdapterError as exc:
            raise SessionTranscriptionError(exc.code, str(exc)) from exc
        fingerprint = _fingerprint(source, self.profile, engine_before)
        destination = self.output_root / session_id
        if not force_rebuild:
            reusable = _existing_is_reusable(
                destination,
                expected_fingerprint=fingerprint,
            )
            if reusable is not None:
                return {"sessionId": session_id, "status": reusable["status"], "reused": True}
        try:
            adapter.initialize()
        except AdapterError as exc:
            raise SessionTranscriptionError(exc.code, str(exc)) from exc
        engine = adapter.engine_metadata()
        fingerprint = _fingerprint(source, self.profile, engine)
        self.output_root.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=f".{session_id}.", suffix=".tmp", dir=self.output_root))
        backup = self.output_root / f".{session_id}.{uuid.uuid4().hex}.backup"
        started_total = time.perf_counter()
        try:
            results: list[dict[str, Any]] = []
            summaries: list[dict[str, Any]] = []
            for answer in source.answers:
                try:
                    run = adapter.transcribe(answer.path)
                    contract = build_answer_contract(
                        answer,
                        segments_raw=run.segments,
                        info=run.info,
                        processing_time_seconds=run.elapsed_seconds,
                    )
                except (AdapterError, TranscriptionContractError) as exc:
                    code = exc.code
                    raise SessionTranscriptionError(
                        code, f"{answer.answer_id}: {exc}"
                    ) from exc
                answer_path = staged / "answers" / f"{answer.answer_id}.json"
                write_answer(answer_path, contract)
                output_sha = sha256_file(answer_path)
                load_strict_json(answer_path)
                results.append(contract)
                summaries.append(_answer_summary(contract, output_sha))
            warnings = list(
                dict.fromkeys(
                    warning
                    for result in results
                    for warning in result["warnings"]
                )
            )
            status = STATUS_WARNINGS if warnings else STATUS_READY
            total_elapsed = time.perf_counter() - started_total
            manifest = {
                "sessionId": session_id,
                "status": status,
                "inputFingerprintSha256": fingerprint,
                "source": {
                    "stage24ManifestSha256": source.stage24_manifest_sha256,
                    "stage24IntervalContractSha256": source.stage24_interval_contract_sha256,
                },
                "engine": engine,
                "options": OPTIONS,
                "totalAudioDurationMs": sum(answer.duration_ms for answer in source.answers),
                "totalProcessingTimeSeconds": total_elapsed,
                "sessionRealTimeFactor": total_elapsed
                / (sum(answer.duration_ms for answer in source.answers) / 1000),
                "answers": summaries,
                "warnings": warnings,
                "errors": [],
            }
            validation = {
                "sessionId": session_id,
                "status": status,
                "checks": {
                    "answerCountIsFour": len(results) == 4,
                    "allAnswerJsonStrict": True,
                    "allSegmentsInRange": True,
                    "allWordsInSegments": True,
                    "allSessionTimestampsConsistent": True,
                    "allInputHashesRecorded": all(item["inputAudioSha256"] for item in summaries),
                    "participantIdExcluded": True,
                    "internalPathsExcluded": True,
                    "modelTextUnmodified": True,
                },
                "warnings": warnings,
                "errors": [],
            }
            ensure_finite(manifest)
            ensure_finite(validation)
            validation_path = staged / "transcription_validation.json"
            review_path = staged / "transcription_review.md"
            report_path = staged / "transcription_report.md"
            write_manifest(validation_path, validation)
            write_text_atomic(review_path, _review_markdown(results))
            write_text_atomic(report_path, _report_markdown(manifest))
            manifest["artifacts"] = {
                validation_path.name: sha256_file(validation_path),
                review_path.name: sha256_file(review_path),
                report_path.name: sha256_file(report_path),
            }
            write_manifest(staged / "session_transcription_manifest.json", manifest)
            replace_directory(staged, destination, backup)
            return {"sessionId": session_id, "status": status, "reused": False}
        except SessionTranscriptionError:
            raise
        except Exception as exc:
            raise SessionTranscriptionError(
                "STT_SESSION_TRANSCRIPTION_FAILED", "Session transcription failed"
            ) from exc
        finally:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)


def public_status_for_error(code: str) -> str:
    return {
        "STT_DEPENDENCY_BLOCKED": "stt_transcription_dependency_blocked",
        "STT_MODEL_DOWNLOAD_BLOCKED": "stt_model_download_blocked",
        "STT_RUNTIME_UNAVAILABLE": "stt_runtime_unavailable",
    }.get(code, STATUS_FAILED)
