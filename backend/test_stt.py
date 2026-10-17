"""Regression tests for browser-to-Groq STT failure classification."""
from __future__ import annotations

import asyncio
import io
import unittest
from unittest.mock import patch

from fastapi import UploadFile

from main import _stt_error_response, stt


class _StubResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _StubClient:
    def __init__(self, response: _StubResponse, **_kwargs: object) -> None:
        self.response = response

    async def __aenter__(self) -> "_StubClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> _StubResponse:
        return self.response


class SttErrorResponseTests(unittest.TestCase):
    def test_invalid_media_is_actionable_not_gateway_error(self) -> None:
        response = _stt_error_response(400, "could not process file")
        self.assertEqual(response.status_code, 422)
        self.assertIn(b"invalid or unsupported audio", response.body)

    def test_provider_outage_is_gateway_error(self) -> None:
        response = _stt_error_response(500, "upstream failure")
        self.assertEqual(response.status_code, 502)

    def test_auth_failure_does_not_leak_provider_detail(self) -> None:
        response = _stt_error_response(401, "provider-specific auth detail")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"provider-specific", response.body)

    def test_route_maps_invalid_browser_media_to_422(self) -> None:
        response = _StubResponse(400, "could not process file")
        upload = UploadFile(filename="turn.webm", file=io.BytesIO(b"not audio"))
        with patch("main.httpx.AsyncClient", return_value=_StubClient(response)):
            result = asyncio.run(stt(upload))
        self.assertEqual(result.status_code, 422)


if __name__ == "__main__":
    unittest.main()
