"""Unit tests for Windows CUDA DLL discovery and registration."""

from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import cuda_runtime


class CudaRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.site_packages = Path(self.temporary_directory.name) / "site-packages"
        self.site_packages.mkdir()
        cuda_runtime._DLL_DIRECTORY_HANDLES.clear()
        cuda_runtime._REGISTERED_DIRECTORIES.clear()
        cuda_runtime._ADD_DLL_DIRECTORY_FAILURES.clear()
        cuda_runtime._PRELOADED_DLL_HANDLES.clear()
        cuda_runtime._PRELOAD_FAILURES.clear()

    def create_dlls(self) -> dict[str, Path]:
        locations = {
            "cudart64_12.dll": self.site_packages / "nvidia" / "cuda_runtime" / "bin",
            "cublasLt64_12.dll": self.site_packages / "nvidia" / "cublas" / "bin",
            "cublas64_12.dll": self.site_packages / "nvidia" / "cublas" / "bin",
            "cudnn64_9.dll": self.site_packages / "nvidia" / "cudnn" / "bin",
        }
        for name, directory in locations.items():
            directory.mkdir(parents=True, exist_ok=True)
            (directory / name).touch()
        return {name: directory / name for name, directory in locations.items()}

    def register(
        self,
        add_directory: MagicMock | None = None,
        win_dll: MagicMock | None = None,
        current_path: str = "existing-one;existing-two",
    ) -> dict:
        add_directory = add_directory or MagicMock(return_value=MagicMock())
        win_dll = win_dll or MagicMock(return_value=MagicMock())
        with patch.object(cuda_runtime.platform, "system", return_value="Windows"), patch.object(
            cuda_runtime.os, "add_dll_directory", add_directory, create=True
        ), patch.object(cuda_runtime.ctypes, "WinDLL", win_dll, create=True), patch.dict(
            cuda_runtime.os.environ, {"PATH": current_path}, clear=False
        ):
            result = cuda_runtime.register_cuda_runtime(self.site_packages)
            self.process_path_after_registration = cuda_runtime.os.environ["PATH"]
        return result

    def test_dll_paths_are_discovered(self) -> None:
        expected = self.create_dlls()
        found = cuda_runtime.find_cuda_dlls(self.site_packages)
        self.assertEqual(found, {name: path.resolve() for name, path in expected.items()})

    def test_duplicate_dll_prefers_nvidia_package_bin_and_reports_all_matches(self) -> None:
        expected = self.create_dlls()
        bundled = self.site_packages / "ctranslate2" / "cudnn64_9.dll"
        bundled.parent.mkdir()
        bundled.touch()
        result = self.register()
        cudnn = result["found_dlls"]["cudnn64_9.dll"]
        self.assertEqual(cudnn["selected_path"], str(expected["cudnn64_9.dll"].resolve()))
        self.assertEqual(cudnn["match_count"], 2)
        self.assertEqual(len(cudnn["matches"]), 2)
        self.assertEqual(cudnn["selection_criterion"], "nvidia_package_bin_then_lexical_path")

    def test_dll_directories_are_deduplicated(self) -> None:
        self.create_dlls()
        result = self.register(MagicMock(return_value=MagicMock()))
        self.assertEqual(len(result["directories"]), 3)

    def test_os_add_dll_directory_is_called(self) -> None:
        self.create_dlls()
        add_directory = MagicMock(return_value=MagicMock())
        result = self.register(add_directory)
        self.assertTrue(result["registered"])
        self.assertEqual(add_directory.call_count, 3)

    def test_directory_handles_are_retained(self) -> None:
        self.create_dlls()
        handles = [MagicMock(), MagicMock(), MagicMock()]
        add_directory = MagicMock(side_effect=handles)
        self.register(add_directory)
        self.assertEqual(cuda_runtime._DLL_DIRECTORY_HANDLES, handles)

    def test_process_path_prepends_dll_directories(self) -> None:
        self.create_dlls()
        result = self.register()
        entries = self.process_path_after_registration.split(cuda_runtime.os.pathsep)
        self.assertEqual(entries[:3], result["process_path_directories"])
        self.assertTrue(result["process_path_updated"])

    def test_process_path_preserves_existing_content(self) -> None:
        self.create_dlls()
        original = "existing-one;existing-two"
        self.register(current_path=original)
        self.assertTrue(self.process_path_after_registration.endswith(original))

    def test_process_path_does_not_duplicate_directories(self) -> None:
        self.create_dlls()
        first = self.register()
        existing = cuda_runtime.os.pathsep.join(
            first["process_path_directories"] + ["existing-one", "existing-two"]
        )
        second = self.register(current_path=existing)
        entries = self.process_path_after_registration.split(cuda_runtime.os.pathsep)
        for directory in second["process_path_directories"]:
            self.assertEqual(entries.count(directory), 1)
        self.assertFalse(second["process_path_updated"])

    def test_win_dll_receives_full_paths(self) -> None:
        expected = self.create_dlls()
        win_dll = MagicMock(return_value=MagicMock())
        self.register(win_dll=win_dll)
        self.assertEqual(
            [call.args[0] for call in win_dll.call_args_list],
            [str(expected[name].resolve()) for name in cuda_runtime.PRELOAD_ORDER],
        )
        self.assertTrue(all(Path(call.args[0]).is_absolute() for call in win_dll.call_args_list))

    def test_win_dll_preload_order(self) -> None:
        self.create_dlls()
        win_dll = MagicMock(return_value=MagicMock())
        self.register(win_dll=win_dll)
        self.assertEqual(
            [Path(call.args[0]).name for call in win_dll.call_args_list],
            list(cuda_runtime.PRELOAD_ORDER),
        )

    def test_win_dll_handles_are_retained(self) -> None:
        self.create_dlls()
        handles = [MagicMock() for _ in cuda_runtime.PRELOAD_ORDER]
        self.register(win_dll=MagicMock(side_effect=handles))
        self.assertEqual(list(cuda_runtime._PRELOADED_DLL_HANDLES.values()), handles)

    def test_preload_failure_has_library_specific_code(self) -> None:
        self.create_dlls()

        def load(path: str) -> MagicMock:
            if Path(path).name == "cublas64_12.dll":
                raise OSError("dependent library missing")
            return MagicMock()

        result = self.register(win_dll=MagicMock(side_effect=load))
        self.assertIn(
            "CUBLAS_PRELOAD_FAILED",
            {failure["code"] for failure in result["preload_failures"]},
        )

    def test_missing_required_dlls_have_specific_errors(self) -> None:
        cublas_dir = self.site_packages / "nvidia" / "cublas" / "bin"
        cublas_dir.mkdir(parents=True)
        (cublas_dir / "cublas64_12.dll").touch()
        result = self.register(MagicMock(return_value=MagicMock()))
        self.assertEqual(
            set(result["missing_dlls"]),
            {"cublasLt64_12.dll", "cudnn64_9.dll", "cudart64_12.dll"},
        )
        discovery_errors = [error for error in result["errors"] if error["code"] == "DLL_DISCOVERY_FAILED"]
        self.assertEqual(len(discovery_errors), 3)

    def test_two_calls_are_idempotent(self) -> None:
        self.create_dlls()
        add_directory = MagicMock(return_value=MagicMock())
        win_dll = MagicMock(return_value=MagicMock())
        with patch.object(cuda_runtime.platform, "system", return_value="Windows"), patch.object(
            cuda_runtime.os, "add_dll_directory", add_directory, create=True
        ), patch.object(cuda_runtime.ctypes, "WinDLL", win_dll, create=True), patch.dict(
            cuda_runtime.os.environ, {"PATH": "existing"}, clear=False
        ):
            first = cuda_runtime.register_cuda_runtime(self.site_packages)
            path_after_first = cuda_runtime.os.environ["PATH"]
            second = cuda_runtime.register_cuda_runtime(self.site_packages)
            path_after_second = cuda_runtime.os.environ["PATH"]
        self.assertEqual(add_directory.call_count, 3)
        self.assertEqual(win_dll.call_count, 4)
        self.assertEqual(path_after_first, path_after_second)
        self.assertTrue(first["process_path_updated"])
        self.assertFalse(second["process_path_updated"])

    def test_concurrent_calls_do_not_duplicate_registration(self) -> None:
        import threading

        self.create_dlls()
        add_directory = MagicMock(return_value=MagicMock())
        win_dll = MagicMock(return_value=MagicMock())
        results: list[dict] = []
        with patch.object(cuda_runtime.platform, "system", return_value="Windows"), patch.object(
            cuda_runtime.os, "add_dll_directory", add_directory, create=True
        ), patch.object(cuda_runtime.ctypes, "WinDLL", win_dll, create=True), patch.dict(
            cuda_runtime.os.environ, {"PATH": "existing"}, clear=False
        ):
            threads = [
                threading.Thread(
                    target=lambda: results.append(
                        cuda_runtime.register_cuda_runtime(self.site_packages)
                    )
                )
                for _ in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
            path_entries = cuda_runtime.os.environ["PATH"].split(cuda_runtime.os.pathsep)
        self.assertEqual(len(results), 2)
        self.assertEqual(add_directory.call_count, 3)
        self.assertEqual(win_dll.call_count, 4)
        for directory in results[0]["process_path_directories"]:
            self.assertEqual(path_entries.count(directory), 1)

    def test_non_windows_platform_is_safely_skipped(self) -> None:
        add_directory = MagicMock()
        with patch.object(cuda_runtime.platform, "system", return_value="Linux"), patch.object(
            cuda_runtime.os, "add_dll_directory", add_directory, create=True
        ):
            result = cuda_runtime.register_cuda_runtime(self.site_packages)
        self.assertFalse(result["registered"])
        self.assertIn("CUDA_RUNTIME_REGISTRATION_SKIPPED_NON_WINDOWS", result["warnings"])
        add_directory.assert_not_called()

    def test_registration_failure_has_specific_error(self) -> None:
        self.create_dlls()
        result = self.register(MagicMock(side_effect=OSError("access denied")))
        self.assertFalse(result["registered"])
        self.assertIn(
            "DLL_DIRECTORY_REGISTRATION_FAILED",
            {error["code"] for error in result["add_dll_directory_failures"]},
        )


if __name__ == "__main__":
    unittest.main()
