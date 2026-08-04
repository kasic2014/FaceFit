from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx

from app.core.settings import AnalysisApiSettings
from app.schemas.analysis_api import MediaAnalysisRequest
from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerPayloadTooLarge,
    AnalyzerTimeout,
)
from app.services.media import _validate_url, download_media

MP4 = b"\x00\x00\x00\x18ftypisom" + (b"\x00" * 64)


class FakeResponse:
    def __init__(self, status=200, content=MP4, headers=None, failure=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {
            "content-type": "video/mp4",
            "content-length": str(len(content)),
        }
        self.failure = failure

    async def __aenter__(self):
        if self.failure:
            raise self.failure
        return self

    async def __aexit__(self, *_args):
        return False

    async def aiter_bytes(self, _chunk_size):
        midpoint = max(1, len(self.content) // 2)
        yield self.content[:midpoint]
        yield self.content[midpoint:]


class FakeClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def stream(self, *_args, **_kwargs):
        return self.response


class MediaDownloadTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name)
        self.settings = AnalysisApiSettings(
            service_token="test",
            max_upload_bytes=1024,
            temp_directory=self.path,
            media_allowed_hosts=("kr.object.ncloudstorage.com",),
        )
        self.body = MediaAnalysisRequest(
            schemaVersion="1",
            requestId=uuid4(),
            answerId=uuid4(),
            mediaUrl=(
                "https://kr.object.ncloudstorage.com/bucket/key.mp4"
                "?X-Amz-Signature=secret"
            ),
            mediaMimeType="video/mp4",
            mediaSizeBytes=len(MP4),
            recordedDurationSec=30,
        )
        self.public_dns = patch(
            "app.services.media.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("8.8.8.8", 443))],
        )
        self.public_dns.start()

    def tearDown(self):
        self.public_dns.stop()
        self.temporary.cleanup()

    async def run_download(self, response):
        with patch(
            "app.services.media.httpx.AsyncClient",
            return_value=FakeClient(response),
        ):
            return await download_media(self.body, self.settings)

    async def test_streams_valid_media_and_cleanup_removes_request_directory(self):
        managed = await self.run_download(FakeResponse())
        self.assertEqual(managed.path.read_bytes(), MP4)
        self.assertEqual(managed.size_bytes, len(MP4))
        managed.cleanup()
        self.assertEqual(list(self.path.rglob("*")), [])

    async def test_missing_content_length_is_accepted_with_actual_byte_limit(self):
        managed = await self.run_download(FakeResponse(headers={
            "content-type": "video/mp4",
        }))
        managed.cleanup()
        self.assertEqual(list(self.path.rglob("*")), [])

    async def test_http_statuses_and_network_timeout_are_distinguished(self):
        for response, expected in (
            (FakeResponse(status=403), AnalyzerMediaFailure),
            (FakeResponse(status=404), AnalyzerMediaFailure),
            (FakeResponse(status=302), AnalyzerMediaFailure),
            (FakeResponse(status=500), AnalyzerTimeout),
            (
                FakeResponse(
                    failure=httpx.ReadTimeout("timeout", request=httpx.Request("GET", "https://x"))
                ),
                AnalyzerTimeout,
            ),
        ):
            with self.subTest(status=response.status_code):
                with self.assertRaises(expected):
                    await self.run_download(response)
                self.assertEqual(list(self.path.rglob("*")), [])

    async def test_declared_and_actual_limits_content_type_and_signature(self):
        cases = (
            (FakeResponse(headers={"content-type": "video/mp4", "content-length": "2048"}),
             AnalyzerPayloadTooLarge),
            (FakeResponse(headers={"content-type": "text/plain", "content-length": str(len(MP4))}),
             AnalyzerMediaFailure),
            (FakeResponse(content=b"not-mp4", headers={"content-type": "video/mp4"}),
             AnalyzerMediaFailure),
            (FakeResponse(content=b"", headers={"content-type": "video/mp4", "content-length": "0"}),
             AnalyzerMediaFailure),
        )
        for response, expected in cases:
            with self.subTest(expected=expected.__name__):
                with self.assertRaises(expected):
                    await self.run_download(response)
                self.assertEqual(list(self.path.rglob("*")), [])

    def test_ssrf_policy_rejects_non_https_userinfo_ports_hosts_and_private_dns(self):
        invalid = (
            "http://kr.object.ncloudstorage.com/bucket/key?sig=x",
            "https://user@kr.object.ncloudstorage.com/bucket/key?sig=x",
            "https://kr.object.ncloudstorage.com:444/bucket/key?sig=x",
            "https://evil.example/bucket/key?sig=x",
            "https://localhost/bucket/key?sig=x",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(AnalyzerMediaFailure):
                _validate_url(url, self.settings)

        with patch(
            "app.services.media.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 443))],
        ), self.assertRaises(AnalyzerMediaFailure):
            _validate_url(self.body.mediaUrl, self.settings)
        with patch(
            "app.services.media.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("169.254.169.254", 443))],
        ), self.assertRaises(AnalyzerMediaFailure):
            _validate_url(self.body.mediaUrl, self.settings)


if __name__ == "__main__":
    unittest.main()
