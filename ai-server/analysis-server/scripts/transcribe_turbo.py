"""Transcribe one validated WAV file with faster-whisper Large V3 Turbo."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.speech.whisper_service import (  # noqa: E402
    DEFAULT_BEAM_SIZE,
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL_NAME,
    WhisperService,
)

from inspect_audio import inspect_audio  # noqa: E402


DEFAULT_MODEL = DEFAULT_MODEL_NAME
MODEL_DESCRIPTION = "Whisper Large V3 Turbo"


def new_result(
    audio_file: Path,
    model_name: str = DEFAULT_MODEL,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    return {
        "model": model_name,
        "model_description": MODEL_DESCRIPTION,
        "device": device,
        "compute_type": compute_type,
        "language": language,
        "detected_language": None,
        "language_probability": None,
        "audio_file": str(audio_file),
        "audio_duration_sec": None,
        "model_load_time_sec": None,
        "transcription_time_sec": None,
        "total_time_sec": None,
        "realtime_factor": None,
        "transcript": "",
        "segments": [],
        "warnings": [],
        "error": None,
    }


def exception_detail(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def classify_exception(error: BaseException, stage: str) -> str:
    """Map common model, CUDA, and NVIDIA DLL errors to stable codes."""
    message = exception_detail(error).lower()
    if any(token in message for token in ("out of memory", "cuda_error_out_of_memory")):
        return "CUDA_OUT_OF_MEMORY"
    if any(token in message for token in ("cublas", "cublas64", "libcublas")):
        return "CUBLAS_NOT_FOUND"
    if any(token in message for token in ("cudnn", "cudnn64", "libcudnn")):
        return "CUDNN_NOT_FOUND"
    if "compute type" in message and any(
        token in message for token in ("unsupported", "not supported", "invalid")
    ):
        return "UNSUPPORTED_COMPUTE_TYPE"
    if any(
        token in message
        for token in (
            "no cuda device",
            "no cuda-capable device",
            "cuda device not found",
            "invalid device ordinal",
        )
    ):
        return "CUDA_DEVICE_NOT_FOUND"
    if any(
        token in message
        for token in (
            "cuda runtime",
            "cuda driver",
            "cudart",
            "nvcuda.dll",
            "cudaerror",
            "failed to initialize cuda",
        )
    ):
        return "CUDA_RUNTIME_ERROR"
    if stage == "model_load" and any(
        token in message
        for token in (
            "download",
            "huggingface",
            "snapshot_download",
            "connection",
            "timed out",
            "repository not found",
            "localentrynotfounderror",
        )
    ):
        return "MODEL_DOWNLOAD_FAILED"
    if stage == "model_load":
        return "MODEL_LOAD_FAILED"
    return "TRANSCRIPTION_FAILED"


def set_error(result: dict[str, Any], code: str, detail: str) -> dict[str, Any]:
    result["error"] = {"code": code, "detail": detail}
    return result


def word_to_dict(word: Any) -> dict[str, Any]:
    return {
        "start": getattr(word, "start", None),
        "end": getattr(word, "end", None),
        "word": getattr(word, "word", ""),
        "probability": getattr(word, "probability", None),
    }


def segment_to_dict(segment: Any) -> dict[str, Any]:
    return {
        "id": getattr(segment, "id", None),
        "start": getattr(segment, "start", None),
        "end": getattr(segment, "end", None),
        "text": getattr(segment, "text", ""),
        "avg_logprob": getattr(segment, "avg_logprob", None),
        "no_speech_prob": getattr(segment, "no_speech_prob", None),
        "words": [word_to_dict(word) for word in (getattr(segment, "words", None) or [])],
    }


def rounded_seconds(value: float) -> float:
    return round(value, 6)


def transcribe_audio(
    audio_file: Path,
    *,
    model_name: str = DEFAULT_MODEL,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
    language: str = DEFAULT_LANGUAGE,
    beam_size: int = DEFAULT_BEAM_SIZE,
    service: WhisperService | None = None,
) -> dict[str, Any]:
    """Validate and transcribe exactly one audio file without fallback or batching."""
    audio_file = Path(audio_file)
    result = new_result(audio_file, model_name, device, compute_type, language)
    if not audio_file.is_file():
        return set_error(result, "INPUT_FILE_NOT_FOUND", f"File not found: {audio_file}")

    inspection = inspect_audio(audio_file)
    result["warnings"] = list(inspection.get("warnings", []))
    if not inspection.get("valid", False):
        detail = json.dumps(inspection.get("errors", []), ensure_ascii=False)
        return set_error(result, "INPUT_AUDIO_INVALID", detail)

    duration = inspection.get("metadata", {}).get("duration_sec")
    result["audio_duration_sec"] = duration
    pipeline_started = time.perf_counter()

    whisper_service = service or WhisperService(
        model_name=model_name,
        device=device,
        compute_type=compute_type,
    )
    try:
        whisper_service.initialize()
    except Exception as exc:
        result["model_load_time_sec"] = whisper_service.load_time_sec
        result["total_time_sec"] = rounded_seconds(time.perf_counter() - pipeline_started)
        return set_error(result, classify_exception(exc, "model_load"), exception_detail(exc))
    result["model_load_time_sec"] = whisper_service.load_time_sec

    transcription_started = time.perf_counter()
    try:
        segments, info = whisper_service.transcribe(
            str(audio_file),
            language=language,
            task="transcribe",
            beam_size=beam_size,
            word_timestamps=True,
            vad_filter=False,
        )
    except Exception as exc:
        result["transcription_time_sec"] = rounded_seconds(
            time.perf_counter() - transcription_started
        )
        result["total_time_sec"] = rounded_seconds(time.perf_counter() - pipeline_started)
        return set_error(result, classify_exception(exc, "transcription"), exception_detail(exc))

    result["transcription_time_sec"] = rounded_seconds(
        time.perf_counter() - transcription_started
    )
    result["total_time_sec"] = rounded_seconds(time.perf_counter() - pipeline_started)
    result["detected_language"] = getattr(info, "language", None)
    result["language_probability"] = getattr(info, "language_probability", None)
    result["segments"] = [segment_to_dict(segment) for segment in segments]
    result["transcript"] = "".join(segment["text"] for segment in result["segments"]).strip()
    if isinstance(duration, (int, float)) and duration > 0:
        result["realtime_factor"] = round(result["transcription_time_sec"] / duration, 6)
    return result


def write_result_json(result: dict[str, Any], output_file: Path) -> bool:
    """Write a result, recording a structured error if the write fails."""
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True
    except (OSError, TypeError, ValueError) as exc:
        set_error(result, "OUTPUT_WRITE_FAILED", exception_detail(exc))
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_file", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--compute-type", default=DEFAULT_COMPUTE_TYPE)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--beam-size", type=int, default=DEFAULT_BEAM_SIZE)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = transcribe_audio(
        args.audio_file,
        model_name=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
        beam_size=args.beam_size,
    )
    if args.output is not None:
        write_result_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
