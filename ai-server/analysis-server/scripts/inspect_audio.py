"""Inspect whether an audio file matches the Face-Fit STT input contract."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


FFPROBE_TIMEOUT_SECONDS = 15
REQUIRED_CODEC = "pcm_s16le"
REQUIRED_SAMPLE_RATE = 16000
REQUIRED_CHANNELS = 1


def find_ffprobe() -> tuple[Path | None, str | None]:
    """Resolve ffprobe from FFPROBE_PATH first, then the current PATH."""
    configured_path = os.getenv("FFPROBE_PATH")
    if configured_path:
        candidate = Path(configured_path)
        if candidate.is_file():
            return candidate, None
        return None, "FFPROBE_PATH_INVALID"

    discovered_path = shutil.which("ffprobe")
    if discovered_path:
        return Path(discovered_path), None
    return None, "FFPROBE_NOT_FOUND"


def empty_metadata() -> dict[str, Any]:
    return {
        "duration_sec": None,
        "codec_name": None,
        "sample_rate": None,
        "channels": None,
        "sample_fmt": None,
        "bits_per_sample": None,
    }


def inspect_audio(audio_file: Path) -> dict[str, Any]:
    """Return metadata plus validation errors and warnings for *audio_file*."""
    result: dict[str, Any] = {
        "file_path": str(audio_file),
        "valid": False,
        "errors": [],
        "warnings": [],
        "metadata": empty_metadata(),
    }
    errors: list[str] = result["errors"]
    warnings: list[str] = result["warnings"]

    if not audio_file.is_file():
        errors.append("FILE_NOT_FOUND")
        return result
    if audio_file.suffix.lower() != ".wav":
        errors.append("INVALID_EXTENSION")
        return result

    ffprobe_path, resolution_error = find_ffprobe()
    if resolution_error:
        errors.append(resolution_error)
        return result

    command = [
        str(ffprobe_path), "-v", "error", "-select_streams", "a:0",
        "-show_entries", "format=duration:stream=codec_name,sample_rate,channels,sample_fmt,bits_per_sample",
        "-of", "json", str(audio_file),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS, check=False,
        )
    except FileNotFoundError:
        errors.append("FFPROBE_EXECUTION_NOT_FOUND")
        return result
    except subprocess.TimeoutExpired:
        errors.append("FFPROBE_TIMEOUT")
        return result
    except OSError:
        errors.append("FFPROBE_EXECUTION_FAILED")
        return result

    if completed.returncode != 0:
        errors.append("FFPROBE_NONZERO_EXIT")
        return result
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        errors.append("FFPROBE_INVALID_JSON")
        return result

    streams = payload.get("streams", [])
    if not streams:
        errors.append("AUDIO_STREAM_NOT_FOUND")
        return result

    stream = streams[0]
    metadata = result["metadata"]
    metadata["duration_sec"] = _as_float(payload.get("format", {}).get("duration"))
    metadata["codec_name"] = stream.get("codec_name")
    metadata["sample_rate"] = _as_int(stream.get("sample_rate"))
    metadata["channels"] = _as_int(stream.get("channels"))
    metadata["sample_fmt"] = stream.get("sample_fmt")
    metadata["bits_per_sample"] = _as_int(stream.get("bits_per_sample"))

    if metadata["codec_name"] != REQUIRED_CODEC:
        errors.append("INVALID_CODEC")
    if metadata["sample_rate"] != REQUIRED_SAMPLE_RATE:
        errors.append("INVALID_SAMPLE_RATE")
    if metadata["channels"] != REQUIRED_CHANNELS:
        errors.append("INVALID_CHANNELS")
    if metadata["bits_per_sample"] is not None and metadata["bits_per_sample"] != 16:
        errors.append("INVALID_BITS_PER_SAMPLE")
    duration = metadata["duration_sec"]
    if duration is not None and duration < 20:
        warnings.append("DURATION_BELOW_RECOMMENDED")
    if duration is not None and duration > 60:
        warnings.append("DURATION_ABOVE_RECOMMENDED")
    result["valid"] = not errors
    return result


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_file", type=Path, help="Path to the audio file to inspect")
    args = parser.parse_args()
    result = inspect_audio(args.audio_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
