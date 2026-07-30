from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np


VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

from app.vision import image_loader


def write_encoded_image(path: Path, image: np.ndarray) -> None:
    success, encoded = cv2.imencode(path.suffix, image)
    if not success:
        raise AssertionError(f"Could not encode test image as {path.suffix}")
    path.write_bytes(encoded.tobytes())


class ImageLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image = np.zeros((12, 18, 3), dtype=np.uint8)
        self.image[:, :, 0] = 10
        self.image[:, :, 1] = 20
        self.image[:, :, 2] = 30

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _assert_supported(self, extension: str) -> None:
        path = self.root / f"sample{extension}"
        write_encoded_image(path, self.image)
        validated = image_loader.validate_image_path(path)
        self.assertEqual(validated, path.resolve())
        _, decoded = image_loader.load_bgr_image(path)
        self.assertEqual(decoded.shape[:2], (12, 18))

    def test_supports_jpg(self) -> None:
        self._assert_supported(".jpg")

    def test_supports_jpeg(self) -> None:
        self._assert_supported(".jpeg")

    def test_supports_png(self) -> None:
        self._assert_supported(".png")

    def test_supports_webp(self) -> None:
        self._assert_supported(".webp")

    def test_supports_bmp(self) -> None:
        self._assert_supported(".bmp")

    def test_unsupported_extension(self) -> None:
        path = self.root / "image.gif"
        path.write_bytes(b"GIF89a")
        with self.assertRaises(image_loader.ImageInputError) as raised:
            image_loader.validate_image_path(path)
        self.assertEqual(raised.exception.code, "IMAGE_EXTENSION_UNSUPPORTED")

    def test_missing_file(self) -> None:
        with self.assertRaises(image_loader.ImageInputError) as raised:
            image_loader.validate_image_path(self.root / "missing.png")
        self.assertEqual(raised.exception.code, "IMAGE_NOT_FOUND")

    def test_non_regular_file(self) -> None:
        directory = self.root / "folder.png"
        directory.mkdir()
        with self.assertRaises(image_loader.ImageInputError) as raised:
            image_loader.validate_image_path(directory)
        self.assertEqual(raised.exception.code, "IMAGE_NOT_REGULAR_FILE")

    def test_empty_file(self) -> None:
        path = self.root / "empty.png"
        path.touch()
        with self.assertRaises(image_loader.ImageInputError) as raised:
            image_loader.validate_image_path(path)
        self.assertEqual(raised.exception.code, "IMAGE_FILE_EMPTY")

    def test_corrupt_image(self) -> None:
        path = self.root / "corrupt.png"
        path.write_bytes(b"not an image")
        with self.assertRaises(image_loader.ImageInputError) as raised:
            image_loader.load_bgr_image(path)
        self.assertEqual(raised.exception.code, "IMAGE_DECODE_FAILED")

    def test_loads_normal_bgr_image(self) -> None:
        path = self.root / "normal.png"
        write_encoded_image(path, self.image)
        _, decoded = image_loader.load_bgr_image(path)
        np.testing.assert_array_equal(decoded, self.image)

    def test_bgr_to_rgb_conversion(self) -> None:
        rgb = image_loader.convert_bgr_to_rgb(self.image)
        self.assertEqual(rgb[0, 0].tolist(), [30, 20, 10])

    def test_grayscale_to_rgb_conversion(self) -> None:
        gray = np.full((4, 5), 17, dtype=np.uint8)
        rgb = image_loader.convert_bgr_to_rgb(gray)
        self.assertEqual(rgb.shape, (4, 5, 3))
        self.assertEqual(rgb[0, 0].tolist(), [17, 17, 17])

    def test_creates_mediapipe_image(self) -> None:
        rgb = image_loader.convert_bgr_to_rgb(self.image)
        media_image = image_loader.create_mediapipe_image(rgb)
        self.assertEqual(media_image.width, 18)
        self.assertEqual(media_image.height, 12)

    def test_metadata_dimensions_channels_and_dtype(self) -> None:
        path = self.root / "metadata.png"
        write_encoded_image(path, self.image)
        metadata = image_loader.inspect_image_metadata(path, self.image)
        self.assertEqual(metadata["width"], 18)
        self.assertEqual(metadata["height"], 12)
        self.assertEqual(metadata["channels"], 3)
        self.assertEqual(metadata["dtype"], "uint8")
        self.assertTrue(metadata["decoded"])

    def test_sha256(self) -> None:
        path = self.root / "hash.png"
        data = b"test image bytes"
        path.write_bytes(data)
        self.assertEqual(
            image_loader.calculate_sha256(path),
            hashlib.sha256(data).hexdigest(),
        )

    def test_safe_image_id_contains_hash_prefix(self) -> None:
        result = image_loader.create_safe_image_id(
            "test front.png",
            "64184e2299aa",
        )
        self.assertEqual(result, "test_front_64184e22")

    def test_safe_image_id_removes_path_traversal(self) -> None:
        result = image_loader.create_safe_image_id(
            r"..\..\private\person image.jpg",
            "abcdef123456",
        )
        self.assertEqual(result, "person_image_abcdef12")
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)
        self.assertNotIn("\\", result)

    def test_same_name_different_hash_does_not_collide(self) -> None:
        first = image_loader.create_safe_image_id("sample.png", "11111111aaaa")
        second = image_loader.create_safe_image_id("sample.png", "22222222bbbb")
        self.assertNotEqual(first, second)

    def test_large_image_warning(self) -> None:
        path = self.root / "large.png"
        write_encoded_image(path, self.image)
        with mock.patch.object(
            image_loader,
            "LARGE_IMAGE_PIXELS",
            1,
        ):
            metadata = image_loader.inspect_image_metadata(path, self.image)
        self.assertEqual(len(metadata["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
