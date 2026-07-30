"""Convert supported audio/video recordings to the Face-Fit STT WAV contract."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from inspect_audio import inspect_audio


FFMPEG_TIMEOUT_SECONDS = 120
SUPPORTED_INPUT_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".webm", ".mp4", ".mov", ".mkv",
}


def find_ffmpeg() -> tuple[Path | None, str | None]:
    """Resolve ffmpeg from FFMPEG_PATH first, then the current PATH."""
    configured_path = os.getenv("FFMPEG_PATH")
    if configured_path:
        candidate = Path(configured_path)
        if candidate.is_file():
            return candidate, None
        return None, "FFMPEG_PATH_INVALID"

    discovered_path = shutil.which("ffmpeg")
    if discovered_path:
        return Path(discovered_path), None
    return None, "FFMPEG_NOT_FOUND"


def conversion_result(input_file: Path, output_file: Path) -> dict[str, Any]:
    """Create the stable result shape returned by :func:`convert_audio`."""
    return {
        "success": False,
        "input_file": str(input_file),
        "output_file": str(output_file),
        "ffmpeg_path": None,
        "processing_time_sec": None,
        "errors": [],
        "warnings": [],
    }


def convert_audio(input_file: Path, output_file: Path, overwrite: bool = False) -> dict[str, Any]:
    """Convert *input_file* to a mono, 16 kHz, signed-16-bit WAV file."""
    result = conversion_result(input_file, output_file)
    errors: list[str] = result["errors"]

    if not input_file.exists():
        errors.append("INPUT_FILE_NOT_FOUND")
        return result
    if not input_file.is_file():
        errors.append("INPUT_NOT_FILE")
        return result
    if input_file.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
        errors.append("UNSUPPORTED_INPUT_FORMAT")
        return result
    if output_file.suffix.lower() != ".wav":
        errors.append("INVALID_OUTPUT_EXTENSION")
        return result
    if input_file.resolve() == output_file.resolve():
        errors.append("INPUT_OUTPUT_SAME_PATH")
        return result
    if output_file.exists() and not overwrite:
        errors.append("OUTPUT_ALREADY_EXISTS")
        return result

    ffmpeg_path, resolution_error = find_ffmpeg()
    if resolution_error:
        errors.append(resolution_error)
        return result
    result["ffmpeg_path"] = str(ffmpeg_path)

    command = [
        str(ffmpeg_path), "-hide_banner", "-loglevel", "error", "-y" if overwrite else "-n",
        "-i", str(input_file), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(output_file),
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        result["processing_time_sec"] = time.monotonic() - started
        errors.append("FFMPEG_TIMEOUT")
        return result
    except (FileNotFoundError, OSError):
        result["processing_time_sec"] = time.monotonic() - started
        errors.append("FFMPEG_EXECUTION_FAILED")
        return result

    result["processing_time_sec"] = time.monotonic() - started
    if completed.returncode != 0:
        errors.append("FFMPEG_NONZERO_EXIT")
        return result
    if not output_file.is_file():
        errors.append("OUTPUT_NOT_CREATED")
        return result

    inspection = inspect_audio(output_file)
    if not inspection["valid"]:
        errors.append("OUTPUT_VALIDATION_FAILED")
        result["warnings"].extend(inspection["errors"] + inspection["warnings"])
        return result
    result["success"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path, help="Input recording path")
    parser.add_argument("output_file", type=Path, help="Output WAV path")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of an existing output file")
    args = parser.parse_args()
    result = convert_audio(args.input_file, args.output_file, args.overwrite)
    print(result)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
