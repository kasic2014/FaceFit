"""Check the analysis server's minimum local execution environment."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SERVER_ROOT))

from app.core.config import APP_PATHS  # noqa: E402


def report(status: str, label: str, detail: object) -> None:
    """Print one consistently formatted check result."""
    print(f"[{status}] {label}: {detail}")


def check_writable(directory: Path) -> tuple[bool, str]:
    """Verify write/delete access without leaving the test file behind."""
    test_file = directory / ".environment-write-test.tmp"
    created = False

    try:
        with test_file.open("x", encoding="utf-8") as stream:
            stream.write("environment write test\n")
        created = True
        test_file.unlink()
        created = False
        return True, "temporary file creation and deletion succeeded"
    except OSError as error:
        return False, f"{type(error).__name__}: {error}"
    finally:
        if created:
            try:
                test_file.unlink()
            except OSError:
                pass


def main() -> int:
    """Run all checks and return a process-friendly exit code."""
    failures = 0
    python_version = platform.python_version()
    expected_python = sys.version_info[:2] == (3, 12)
    report("OK" if expected_python else "FAIL", "Python version", python_version)
    failures += not expected_python

    executable = Path(sys.executable).resolve()
    executable_exists = executable.is_file()
    report(
        "OK" if executable_exists else "FAIL",
        "Python executable",
        executable,
    )
    failures += not executable_exists

    report("OK", "Operating system", platform.platform())
    report("OK", "System architecture", platform.machine() or "unknown")
    report("OK", "Current working directory", Path.cwd().resolve())

    root_matches = APP_PATHS.root_dir == ANALYSIS_SERVER_ROOT
    root_exists = APP_PATHS.root_dir.is_dir()
    root_ok = root_matches and root_exists
    report("OK" if root_ok else "FAIL", "Analysis-server root", APP_PATHS.root_dir)
    failures += not root_ok

    in_virtual_environment = sys.prefix != sys.base_prefix
    report(
        "OK" if in_virtual_environment else "FAIL",
        "Virtual environment active",
        f"sys.prefix={sys.prefix}; sys.base_prefix={sys.base_prefix}",
    )
    failures += not in_virtual_environment

    for directory in APP_PATHS.all_directories():
        exists = directory.is_dir()
        report("OK" if exists else "FAIL", f"Directory exists [{directory.name}]", directory)
        failures += not exists

        if not exists:
            report("FAIL", f"Directory writable [{directory.name}]", "directory does not exist")
            failures += 1
            continue

        writable, detail = check_writable(directory)
        report("OK" if writable else "FAIL", f"Directory writable [{directory.name}]", detail)
        failures += not writable

    remaining_temp_files = [
        directory / ".environment-write-test.tmp"
        for directory in APP_PATHS.all_directories()
        if (directory / ".environment-write-test.tmp").exists()
    ]
    cleanup_ok = not remaining_temp_files
    report(
        "OK" if cleanup_ok else "FAIL",
        "Temporary file cleanup",
        "complete" if cleanup_ok else remaining_temp_files,
    )
    failures += not cleanup_ok

    if failures:
        report("FAIL", "Environment check", f"{failures} required check(s) failed")
        return 1

    report("OK", "Environment check", "all required checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
