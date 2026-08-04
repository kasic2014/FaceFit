"""Download the two canonical MediaPipe task bundles with SHA-256 pinning."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path


MODELS = (
    (
        "face_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    ),
    (
        "pose_landmarker_full.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
        "4eaa5eb7a98365221087693fcc286334cf0858e2eb6e15b506aa4a7ecdcec4ad",
    ),
)


def download(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for filename, url, expected in MODELS:
        destination = output / filename
        if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected:
            destination.chmod(0o444)
            continue
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=output, delete=False) as target:
                temporary = Path(target.name)
                with urllib.request.urlopen(url, timeout=60) as response:
                    while chunk := response.read(1024 * 1024):
                        target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError(f"checksum mismatch for {filename}")
            os.replace(temporary, destination)
            destination.chmod(0o444)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    download(parser.parse_args().output)
