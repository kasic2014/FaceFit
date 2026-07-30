"""Discover and register NVIDIA pip-package DLL directories on Windows."""

from __future__ import annotations

import ctypes
import os
import platform
import sysconfig
import threading
from pathlib import Path
from typing import Any


PRELOAD_ORDER = (
    "cudart64_12.dll",
    "cublasLt64_12.dll",
    "cublas64_12.dll",
    "cudnn64_9.dll",
)
PRELOAD_ERROR_CODES = {
    "cudart64_12.dll": "CUDART_PRELOAD_FAILED",
    "cublasLt64_12.dll": "CUBLAS_LT_PRELOAD_FAILED",
    "cublas64_12.dll": "CUBLAS_PRELOAD_FAILED",
    "cudnn64_9.dll": "CUDNN_PRELOAD_FAILED",
}

# Windows closes a registered directory when its handle is garbage-collected.
_DLL_DIRECTORY_HANDLES: list[Any] = []
_REGISTERED_DIRECTORIES: set[str] = set()
_ADD_DLL_DIRECTORY_FAILURES: dict[str, dict[str, str]] = {}
# ctypes library objects also own handles that must live for the process lifetime.
_PRELOADED_DLL_HANDLES: dict[str, Any] = {}
_PRELOAD_FAILURES: dict[str, dict[str, str]] = {}
_REGISTRY_LOCK = threading.Lock()


def _default_site_packages() -> Path:
    paths = sysconfig.get_paths()
    return Path(paths.get("purelib") or paths["platlib"])


def find_cuda_dll_candidates(site_packages: Path) -> dict[str, list[Path]]:
    """Find every required DLL candidate below the active site-packages."""
    site_packages = Path(site_packages)
    if not site_packages.is_dir():
        return {name: [] for name in PRELOAD_ORDER}

    required_by_casefold = {name.casefold(): name for name in PRELOAD_ORDER}
    matches: dict[str, list[Path]] = {name: [] for name in PRELOAD_ORDER}
    for candidate in site_packages.rglob("*"):
        canonical_name = required_by_casefold.get(candidate.name.casefold())
        if canonical_name is not None and candidate.is_file():
            matches[canonical_name].append(candidate.resolve())
    for candidates in matches.values():
        candidates.sort(key=_candidate_sort_key)
    return matches


def _candidate_sort_key(path: Path) -> tuple[int, str]:
    """Prefer NVIDIA pip-package bin directories, then lexical path order."""
    parts = {part.casefold() for part in path.parts}
    nvidia_bin_priority = 0 if "nvidia" in parts and path.parent.name.casefold() == "bin" else 1
    return nvidia_bin_priority, str(path).casefold()


def find_cuda_dlls(site_packages: Path) -> dict[str, Path]:
    """Select one deterministic DLL path per required library."""
    candidates = find_cuda_dll_candidates(site_packages)
    return {name: paths[0] for name, paths in candidates.items() if paths}


def _deduplicate_directories(found: dict[str, Path]) -> list[Path]:
    directories: list[Path] = []
    seen: set[str] = set()
    for name in PRELOAD_ORDER:
        dll_path = found.get(name)
        if dll_path is None:
            continue
        directory = dll_path.parent.resolve()
        key = _path_key(directory)
        if key not in seen:
            seen.add(key)
            directories.append(directory)
    return directories


def _path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _detail(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _error(code: str, detail: str, **context: str) -> dict[str, str]:
    return {"code": code, "detail": detail, **context}


def _new_result() -> dict[str, Any]:
    return {
        "platform": platform.system(),
        "registered": False,
        "registered_directories": [],
        "directories": [],
        "process_path_updated": False,
        "process_path_directories": [],
        "found_dlls": {},
        "missing_dlls": [],
        "preloaded_dlls": [],
        "preload_failures": [],
        "add_dll_directory_failures": [],
        "warnings": [],
        "errors": [],
    }


def _update_process_path(directories: list[Path], result: dict[str, Any]) -> None:
    desired = [str(directory) for directory in directories]
    result["process_path_directories"] = desired
    current_path = os.environ.get("PATH", "")
    existing_keys = {
        _path_key(entry)
        for entry in current_path.split(os.pathsep)
        if entry.strip()
    }
    new_directories = [directory for directory in desired if _path_key(directory) not in existing_keys]
    if not new_directories:
        return
    try:
        os.environ["PATH"] = os.pathsep.join(
            new_directories + ([current_path] if current_path else [])
        )
        result["process_path_updated"] = True
    except (OSError, TypeError, ValueError) as exc:
        entry = _error("PROCESS_PATH_UPDATE_FAILED", _detail(exc))
        result["errors"].append(entry)


def register_cuda_runtime(site_packages: Path | None = None) -> dict[str, Any]:
    """Discover, register, expose, and preload CUDA DLLs for this process only."""
    result = _new_result()
    if result["platform"] != "Windows":
        result["warnings"].append("CUDA_RUNTIME_REGISTRATION_SKIPPED_NON_WINDOWS")
        return result

    package_root = Path(site_packages) if site_packages is not None else _default_site_packages()
    try:
        candidates = find_cuda_dll_candidates(package_root)
        found = {name: paths[0] for name, paths in candidates.items() if paths}
    except (OSError, RuntimeError) as exc:
        result["errors"].append(_error("DLL_DISCOVERY_FAILED", _detail(exc)))
        return result

    for name in PRELOAD_ORDER:
        paths = candidates[name]
        if not paths:
            result["missing_dlls"].append(name)
            result["errors"].append(
                _error(
                    "DLL_DISCOVERY_FAILED",
                    f"{name} was not found under {package_root}",
                    dll=name,
                )
            )
            continue
        selected = paths[0]
        result["found_dlls"][name] = {
            "exists": selected.is_file(),
            "selected_path": str(selected),
            "directory": str(selected.parent),
            "match_count": len(paths),
            "matches": [str(path) for path in paths],
            "selection_criterion": "nvidia_package_bin_then_lexical_path",
        }

    directories = _deduplicate_directories(found)
    result["directories"] = [str(directory) for directory in directories]
    add_dll_directory = getattr(os, "add_dll_directory", None)
    win_dll = getattr(ctypes, "WinDLL", None)

    with _REGISTRY_LOCK:
        if add_dll_directory is None:
            entry = _error(
                "DLL_DIRECTORY_REGISTRATION_FAILED",
                "os.add_dll_directory is unavailable on this Python runtime",
            )
            result["add_dll_directory_failures"].append(entry)
            result["errors"].append(entry)
        else:
            for directory in directories:
                key = _path_key(directory)
                if key in _ADD_DLL_DIRECTORY_FAILURES:
                    entry = _ADD_DLL_DIRECTORY_FAILURES[key]
                    result["add_dll_directory_failures"].append(entry)
                    result["errors"].append(entry)
                    continue
                if key not in _REGISTERED_DIRECTORIES:
                    try:
                        handle = add_dll_directory(str(directory))
                    except (OSError, RuntimeError) as exc:
                        entry = _error(
                            "DLL_DIRECTORY_REGISTRATION_FAILED",
                            _detail(exc),
                            directory=str(directory),
                        )
                        _ADD_DLL_DIRECTORY_FAILURES[key] = entry
                        result["add_dll_directory_failures"].append(entry)
                        result["errors"].append(entry)
                        continue
                    _DLL_DIRECTORY_HANDLES.append(handle)
                    _REGISTERED_DIRECTORIES.add(key)
                result["registered_directories"].append(str(directory))

        _update_process_path(directories, result)

        if win_dll is None:
            for name in PRELOAD_ORDER:
                if name not in found:
                    continue
                entry = _error(
                    PRELOAD_ERROR_CODES[name],
                    "ctypes.WinDLL is unavailable on this Python runtime",
                    dll=name,
                )
                result["preload_failures"].append(entry)
                result["errors"].append(entry)
        else:
            for name in PRELOAD_ORDER:
                dll_path = found.get(name)
                if dll_path is None:
                    continue
                key = _path_key(dll_path)
                if key in _PRELOAD_FAILURES:
                    entry = _PRELOAD_FAILURES[key]
                    result["preload_failures"].append(entry)
                    result["errors"].append(entry)
                    continue
                if key not in _PRELOADED_DLL_HANDLES:
                    try:
                        handle = win_dll(str(dll_path))
                    except (OSError, RuntimeError) as exc:
                        entry = _error(
                            PRELOAD_ERROR_CODES[name],
                            _detail(exc),
                            dll=name,
                            path=str(dll_path),
                        )
                        _PRELOAD_FAILURES[key] = entry
                        result["preload_failures"].append(entry)
                        result["errors"].append(entry)
                        continue
                    _PRELOADED_DLL_HANDLES[key] = handle
                result["preloaded_dlls"].append(str(dll_path))

    result["registered"] = (
        not result["errors"]
        and len(found) == len(PRELOAD_ORDER)
        and len(result["preloaded_dlls"]) == len(PRELOAD_ORDER)
    )
    return result


def register_cuda_dll_directories(site_packages: Path | None = None) -> dict[str, Any]:
    """Backward-compatible alias for callers using the previous function name."""
    return register_cuda_runtime(site_packages)
