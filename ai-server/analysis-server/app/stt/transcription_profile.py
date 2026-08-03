"""Central model and hardware profiles for official STT transcription."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MODEL_ALIAS = "large-v3-turbo"
MODEL_ID = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
MODEL_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"


class ProfileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TranscriptionProfile:
    name: str
    model: str
    model_id: str
    revision: str
    device: str
    compute_type: str
    fallback_model: bool = False

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {
            "profile": value["name"],
            "model": value["model"],
            "modelId": value["model_id"],
            "revision": value["revision"],
            "device": value["device"],
            "computeType": value["compute_type"],
            "fallbackModel": value["fallback_model"],
        }


CUDA_FLOAT16 = TranscriptionProfile(
    name="cuda-float16",
    model=MODEL_ALIAS,
    model_id=MODEL_ID,
    revision=MODEL_REVISION,
    device="cuda",
    compute_type="float16",
)
CPU_INT8 = TranscriptionProfile(
    name="cpu-int8",
    model=MODEL_ALIAS,
    model_id=MODEL_ID,
    revision=MODEL_REVISION,
    device="cpu",
    compute_type="int8",
)
PROFILES = {profile.name: profile for profile in (CUDA_FLOAT16, CPU_INT8)}


def runtime_capabilities() -> dict[str, Any]:
    try:
        import ctranslate2

        cuda_count = int(ctranslate2.get_cuda_device_count())
        cuda_types = sorted(ctranslate2.get_supported_compute_types("cuda"))
        cpu_types = sorted(ctranslate2.get_supported_compute_types("cpu"))
        return {
            "ctranslate2Available": True,
            "cudaDeviceCount": cuda_count,
            "cudaComputeTypes": cuda_types,
            "cpuComputeTypes": cpu_types,
        }
    except Exception as exc:
        return {
            "ctranslate2Available": False,
            "cudaDeviceCount": 0,
            "cudaComputeTypes": [],
            "cpuComputeTypes": [],
            "errorType": type(exc).__name__,
        }


def resolve_profile(name: str = "auto") -> TranscriptionProfile:
    capabilities = runtime_capabilities()
    if not capabilities["ctranslate2Available"]:
        code = (
            "STT_DEPENDENCY_BLOCKED"
            if capabilities.get("errorType") in {"ImportError", "ModuleNotFoundError"}
            else "STT_RUNTIME_UNAVAILABLE"
        )
        raise ProfileError(code, "CTranslate2 is unavailable")
    selected = name
    if name == "auto":
        selected = (
            "cuda-float16"
            if capabilities["cudaDeviceCount"] > 0
            and "float16" in capabilities["cudaComputeTypes"]
            else "cpu-int8"
        )
    profile = PROFILES.get(selected)
    if profile is None:
        raise ProfileError("INVALID_MODEL_PROFILE", "Unknown model profile")
    supported = (
        capabilities["cudaComputeTypes"]
        if profile.device == "cuda"
        else capabilities["cpuComputeTypes"]
    )
    if profile.device == "cuda" and capabilities["cudaDeviceCount"] < 1:
        raise ProfileError("STT_RUNTIME_UNAVAILABLE", "CUDA device is unavailable")
    if profile.compute_type not in supported:
        raise ProfileError(
            "STT_RUNTIME_UNAVAILABLE",
            f"Compute type {profile.compute_type} is unavailable on {profile.device}",
        )
    return profile
