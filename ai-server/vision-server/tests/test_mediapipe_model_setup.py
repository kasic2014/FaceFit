from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = VISION_SERVER_ROOT.parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.core import config
from app.vision import model_registry as registry
from scripts import setup_mediapipe_models as setup


REQUIREMENTS_SHA256 = "8a18c111dc4e4d93e8e1c0e28615298a32819d78d78996303f1171b3fad6e925"
REQUIREMENTS_LOCK_SHA256 = "d05e1d8c452a61bf2638aace9bc320278eee5716ef15f8697d6c75ce8a2bc091"
ANALYSIS_TREE_SHA256 = "3251e4557822f8d064021749e885a8bb61136152bbac6d0b10d0336973603d5f"
SESSION001_SHA256 = "6523d266058fba6daff29c10a15780545bc3d7eac8e9e0b2b940212f9c1b9ea2"


class FakeResponse:
    def __init__(
        self,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.data = data
        self.position = 0
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        if self.position >= len(self.data):
            return b""
        if size < 0:
            size = len(self.data) - self.position
        result = self.data[self.position : self.position + size]
        self.position += len(result)
        return result


def fake_descriptor(
    directory: Path,
    *,
    model_id: str = "face_landmarker",
    url: str = (
        "https://storage.googleapis.com/mediapipe-models/test/model.task"
    ),
    minimum_size: int = 8,
) -> registry.ModelDescriptor:
    return registry.ModelDescriptor(
        model_id=model_id,
        variant="test",
        source_url=url,
        local_path=directory / f"{model_id}.task",
        allowed_host=registry.ALLOWED_MODEL_HOST,
        minimum_size_bytes=minimum_size,
    )


def strict_load(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def protected_tree_digest(
    *,
    session_only: bool = False,
) -> str:
    analysis = WORKSPACE_ROOT / "ai-server" / "analysis-server"
    files = [
        path
        for path in analysis.rglob("*")
        if path.is_file()
        and ".venv" not in path.parts
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and not path.is_relative_to(
            analysis / "data" / "output" / "stt_preprocessing"
        )
        and not path.is_relative_to(
            analysis / "data" / "output" / "stt_transcription"
        )
        and (not session_only or "SESSION001" in path.as_posix())
    ]
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(WORKSPACE_ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


class RegistryTests(unittest.TestCase):
    def test_official_face_url(self) -> None:
        descriptor = registry.get_model_descriptor("face_landmarker")
        self.assertEqual(
            descriptor.source_url,
            "https://storage.googleapis.com/mediapipe-models/"
            "face_landmarker/face_landmarker/float16/latest/"
            "face_landmarker.task",
        )

    def test_official_pose_full_url(self) -> None:
        descriptor = registry.get_model_descriptor("pose_landmarker")
        self.assertEqual(descriptor.variant, "full_float16_latest")
        self.assertIn("pose_landmarker_full", descriptor.source_url)
        self.assertNotIn("lite", descriptor.source_url)
        self.assertNotIn("heavy", descriptor.source_url)

    def test_allowed_host(self) -> None:
        descriptor = registry.get_model_descriptor("face_landmarker")
        registry.validate_model_url(descriptor)
        self.assertEqual(descriptor.allowed_host, "storage.googleapis.com")

    def test_non_allowed_host_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(
                Path(directory),
                url="https://example.com/model.task",
            )
            with self.assertRaisesRegex(
                registry.ModelRegistryError,
                "not allowed",
            ) as raised:
                registry.validate_model_url(descriptor)
        self.assertEqual(raised.exception.code, "MODEL_URL_NOT_ALLOWED")

    def test_non_https_url_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(
                Path(directory),
                url="http://storage.googleapis.com/model.task",
            )
            with self.assertRaises(registry.ModelRegistryError) as raised:
                registry.validate_model_url(descriptor)
        self.assertEqual(raised.exception.code, "MODEL_URL_NOT_ALLOWED")

    def test_model_local_paths(self) -> None:
        self.assertEqual(
            registry.get_model_descriptor("face_landmarker").local_path,
            config.FACE_LANDMARKER_MODEL_PATH,
        )
        self.assertEqual(
            registry.get_model_descriptor("pose_landmarker").local_path,
            config.POSE_LANDMARKER_MODEL_PATH,
        )

    def test_environment_model_path_resolution(self) -> None:
        absolute = (VISION_SERVER_ROOT / "models" / "alternate.task").resolve()
        with mock.patch.dict(
            os.environ,
            {"POSE_LANDMARKER_MODEL_PATH": str(absolute)},
        ):
            result = config.resolve_model_path(
                "POSE_LANDMARKER_MODEL_PATH",
                "models/pose_landmarker_full.task",
            )
        self.assertEqual(result, absolute)

    def test_sha256_calculation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.task"
            path.write_bytes(b"binary model")
            self.assertEqual(
                registry.sha256_file(path),
                hashlib.sha256(b"binary model").hexdigest(),
            )

    def test_missing_model_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = registry.inspect_model(fake_descriptor(Path(directory)))
        self.assertEqual(state["status"], "missing")

    def test_manifestless_existing_model_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            descriptor.local_path.write_bytes(b"PKbinary model")
            state = registry.inspect_model(descriptor)
        self.assertEqual(state["status"], "unverified_existing_file")

    def test_checksum_mismatch_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            data = b"PKbinary model"
            descriptor.local_path.write_bytes(data)
            manifest = {
                "schema_version": "1.0",
                "models": [
                    {
                        "model_id": descriptor.model_id,
                        "file_size_bytes": len(data),
                        "sha256": "0" * 64,
                        "verified": True,
                    }
                ],
            }
            state = registry.inspect_model(descriptor, manifest)
        self.assertEqual(state["status"], "checksum_mismatch")


class DownloadTests(unittest.TestCase):
    def test_temporary_download_file_and_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            data = b"PKbinary model"
            real_replace = os.replace
            with mock.patch.object(
                setup.os,
                "replace",
                wraps=real_replace,
            ) as replace:
                setup.download_model(
                    descriptor,
                    opener=lambda *args, **kwargs: FakeResponse(data),
                )
            source, destination = replace.call_args.args
            self.assertTrue(str(source).endswith(".part"))
            self.assertEqual(Path(destination), descriptor.local_path)

    def test_normal_binary_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            data = b"PKbinary model"
            result = setup.download_model(
                descriptor,
                opener=lambda *args, **kwargs: FakeResponse(data),
            )
            self.assertEqual(descriptor.local_path.read_bytes(), data)
            self.assertEqual(result["file_size_bytes"], len(data))
            self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())

    def test_octet_stream_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            setup.download_model(
                descriptor,
                opener=lambda *args, **kwargs: FakeResponse(
                    b"PKbinary model",
                    "application/octet-stream",
                ),
            )
            self.assertTrue(descriptor.local_path.is_file())

    def test_empty_response_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            with self.assertRaises(registry.ModelRegistryError) as raised:
                setup.download_model(
                    descriptor,
                    opener=lambda *args, **kwargs: FakeResponse(b""),
                )
        self.assertEqual(raised.exception.code, "MODEL_FILE_EMPTY")

    def test_html_response_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            with self.assertRaises(registry.ModelRegistryError) as raised:
                setup.download_model(
                    descriptor,
                    opener=lambda *args, **kwargs: FakeResponse(
                        b"<html>error</html>",
                        "text/html",
                    ),
                )
        self.assertEqual(raised.exception.code, "MODEL_RESPONSE_INVALID")

    def test_xml_response_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            with self.assertRaises(registry.ModelRegistryError) as raised:
                setup.download_model(
                    descriptor,
                    opener=lambda *args, **kwargs: FakeResponse(
                        b"<?xml version='1.0'?><Error/>",
                        "application/octet-stream",
                    ),
                )
        self.assertEqual(raised.exception.code, "MODEL_RESPONSE_INVALID")

    def test_json_response_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            with self.assertRaises(registry.ModelRegistryError) as raised:
                setup.download_model(
                    descriptor,
                    opener=lambda *args, **kwargs: FakeResponse(
                        b'{"error":"not found"}',
                    ),
                )
        self.assertEqual(raised.exception.code, "MODEL_RESPONSE_INVALID")

    def test_minimum_size_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory), minimum_size=100)
            with self.assertRaises(registry.ModelRegistryError) as raised:
                setup.download_model(
                    descriptor,
                    opener=lambda *args, **kwargs: FakeResponse(b"PKtiny"),
                )
        self.assertEqual(raised.exception.code, "MODEL_FILE_TOO_SMALL")

    def test_http_error_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))

            def fail(*args, **kwargs):
                raise urllib.error.HTTPError(
                    descriptor.source_url,
                    404,
                    "Not Found",
                    {},
                    None,
                )

            with self.assertRaises(registry.ModelRegistryError) as raised:
                setup.download_model(descriptor, opener=fail)
        self.assertEqual(raised.exception.code, "MODEL_HTTP_ERROR")

    def test_partial_file_is_cleaned_after_failure(self) -> None:
        class BrokenResponse(FakeResponse):
            def read(self, size: int = -1) -> bytes:
                if self.position:
                    raise OSError("connection interrupted")
                self.position = 1
                return b"PKpartial"

        with tempfile.TemporaryDirectory() as directory:
            descriptor = fake_descriptor(Path(directory))
            with self.assertRaises(registry.ModelRegistryError):
                setup.download_model(
                    descriptor,
                    opener=lambda *args, **kwargs: BrokenResponse(b"unused"),
                )
            self.assertEqual(list(Path(directory).glob("*.part")), [])
            self.assertFalse(descriptor.local_path.exists())


class ManifestAndSetupTests(unittest.TestCase):
    def test_manifest_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            registry.write_json_atomic(
                {"schema_version": "1.0", "models": []},
                path,
            )
            self.assertEqual(strict_load(path)["schema_version"], "1.0")

    def test_manifest_allow_nan_false(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            with self.assertRaises(ValueError):
                registry.write_json_atomic({"value": math.nan}, path)
            self.assertFalse(path.exists())

    def test_manifest_atomic_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            real_replace = os.replace
            with mock.patch.object(
                registry.os,
                "replace",
                wraps=real_replace,
            ) as replace:
                registry.write_json_atomic(
                    {"schema_version": "1.0", "models": []},
                    path,
                )
            replace.assert_called_once()
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_invalid_manifest_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaises(registry.ModelRegistryError) as raised:
                registry.read_manifest(path)
        self.assertEqual(raised.exception.code, "MODEL_MANIFEST_INVALID")

    def test_existing_ready_model_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descriptor = fake_descriptor(root)
            data = b"PKbinary model"
            descriptor.local_path.write_bytes(data)
            manifest_path = root / "model_manifest.json"
            report_path = root / "setup_report.json"
            registry.write_json_atomic(
                {
                    "schema_version": "1.0",
                    "generated_at": "2026-01-01T00:00:00Z",
                    "models": [
                        {
                            "model_id": descriptor.model_id,
                            "variant": descriptor.variant,
                            "source_url": descriptor.source_url,
                            "local_path": descriptor.local_path.name,
                            "file_size_bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "downloaded_at": "2026-01-01T00:00:00Z",
                            "download_status": "downloaded",
                            "verified": True,
                        }
                    ],
                },
                manifest_path,
            )
            with (
                mock.patch.object(setup, "MANIFEST_PATH", manifest_path),
                mock.patch.object(setup, "REPORT_PATH", report_path),
                mock.patch.object(
                    setup,
                    "get_all_model_descriptors",
                    return_value=(descriptor,),
                ),
                mock.patch.object(setup, "download_model") as download,
            ):
                report = setup.setup_models()
            download.assert_not_called()
            self.assertEqual(report["models"][0]["status"], "skipped")
            self.assertEqual(report["status"], "ready")

    def test_unverified_existing_model_fails_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descriptor = fake_descriptor(root)
            descriptor.local_path.write_bytes(b"PKbinary model")
            with (
                mock.patch.object(setup, "MANIFEST_PATH", root / "manifest.json"),
                mock.patch.object(setup, "REPORT_PATH", root / "report.json"),
                mock.patch.object(
                    setup,
                    "get_all_model_descriptors",
                    return_value=(descriptor,),
                ),
            ):
                report = setup.setup_models()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["errors"][0]["code"], "MODEL_UNVERIFIED")

    def test_checksum_mismatch_fails_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descriptor = fake_descriptor(root)
            data = b"PKbinary model"
            descriptor.local_path.write_bytes(data)
            manifest_path = root / "manifest.json"
            registry.write_json_atomic(
                {
                    "schema_version": "1.0",
                    "models": [
                        {
                            "model_id": descriptor.model_id,
                            "file_size_bytes": len(data),
                            "sha256": "0" * 64,
                            "verified": True,
                        }
                    ],
                },
                manifest_path,
            )
            with (
                mock.patch.object(setup, "MANIFEST_PATH", manifest_path),
                mock.patch.object(setup, "REPORT_PATH", root / "report.json"),
                mock.patch.object(
                    setup,
                    "get_all_model_descriptors",
                    return_value=(descriptor,),
                ),
            ):
                report = setup.setup_models()
        self.assertEqual(report["errors"][0]["code"], "MODEL_CHECKSUM_MISMATCH")

    def test_overwrite_option_redownloads_existing_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descriptor = fake_descriptor(root)
            descriptor.local_path.write_bytes(b"PKold model!")
            downloaded = {
                "file_size_bytes": 12,
                "sha256": "a" * 64,
                "downloaded_at": "2026-01-01T00:00:00Z",
            }
            with (
                mock.patch.object(setup, "MANIFEST_PATH", root / "manifest.json"),
                mock.patch.object(setup, "REPORT_PATH", root / "report.json"),
                mock.patch.object(
                    setup,
                    "get_all_model_descriptors",
                    return_value=(descriptor,),
                ),
                mock.patch.object(
                    setup,
                    "download_model",
                    return_value=downloaded,
                ) as download,
            ):
                report = setup.setup_models(overwrite_models=True)
            download.assert_called_once_with(descriptor)
            self.assertEqual(report["models"][0]["status"], "downloaded")

    def test_setup_cli_success_zero(self) -> None:
        with (
            mock.patch.object(
                setup,
                "setup_models",
                return_value={"status": "ready"},
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(setup.main([]), 0)

    def test_setup_cli_failure_one(self) -> None:
        with (
            mock.patch.object(
                setup,
                "setup_models",
                return_value={"status": "failed"},
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(setup.main([]), 1)

    def test_setup_cli_usage_error_two(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.assertEqual(setup.main(["--unknown"]), 2)


class ProtectionBaselineTests(unittest.TestCase):
    def test_requirements_file_is_unchanged(self) -> None:
        actual = hashlib.sha256(
            (VISION_SERVER_ROOT / "requirements.txt").read_bytes()
        ).hexdigest()
        self.assertEqual(actual, REQUIREMENTS_SHA256)

    def test_requirements_lock_file_is_unchanged(self) -> None:
        actual = hashlib.sha256(
            (VISION_SERVER_ROOT / "requirements-lock.txt").read_bytes()
        ).hexdigest()
        self.assertEqual(actual, REQUIREMENTS_LOCK_SHA256)

    def test_analysis_server_protected_tree_is_unchanged(self) -> None:
        self.assertEqual(protected_tree_digest(), ANALYSIS_TREE_SHA256)

    def test_session001_is_unchanged(self) -> None:
        self.assertEqual(
            protected_tree_digest(session_only=True),
            SESSION001_SHA256,
        )
