"""Tests for retry logic."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from arquivo_pt_mcp import MAX_RETRIES, _fetch_with_retry


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text
        self.request = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=None,
                response=self,
            )


@pytest.mark.asyncio
async def test_fetch_with_retry_429_then_success():
    """429 responses should be retried with exponential backoff, eventually returning the 200."""
    client = AsyncMock()
    responses = [
        FakeResponse(429),
        FakeResponse(429),
        FakeResponse(200, text="ok"),
    ]
    client.get.side_effect = responses

    with patch("arquivo_pt_mcp.asyncio.sleep") as mock_sleep:
        resp = await _fetch_with_retry(client, "https://example.com/test")

    assert client.get.call_count == 3
    assert resp.status_code == 200
    assert resp.text == "ok"

    # Exponential backoff: sleep(1), sleep(2)
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


@pytest.mark.asyncio
async def test_fetch_with_retry_429_exhausted():
    """If 429 persists through all retries, the last exception should be raised."""
    client = AsyncMock()
    client.get.side_effect = [FakeResponse(429)] * (MAX_RETRIES + 1)

    with patch("arquivo_pt_mcp.asyncio.sleep") as mock_sleep:
        with pytest.raises(httpx.HTTPStatusError):
            await _fetch_with_retry(client, "https://example.com/test")

    assert client.get.call_count == MAX_RETRIES + 1
    assert mock_sleep.call_count == MAX_RETRIES
