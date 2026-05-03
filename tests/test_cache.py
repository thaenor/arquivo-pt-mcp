"""Tests for TTL caching behavior."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arquivo_pt_mcp import SCREENSHOT_CACHE, clear_cache, extract_text, list_versions, search


@pytest.mark.asyncio
async def test_search_cache_avoids_second_http_request(mock_search_response):
    """Calling search twice with the same args should only make one HTTP request."""
    clear_cache()

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.text = json.dumps(mock_search_response)

    fetch_mock = AsyncMock(return_value=mock_resp)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=fetch_mock):
        result1 = await search("eleições 2005")
        result2 = await search("eleições 2005")

    assert result1 == result2
    assert fetch_mock.call_count == 1


@pytest.mark.asyncio
async def test_list_versions_cache_avoids_second_http_request(mock_cdx_jsonl_response):
    """Calling list_versions twice with the same args should only make one HTTP request."""
    clear_cache()

    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    fetch_mock = AsyncMock(return_value=mock_resp)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=fetch_mock):
        result1 = await list_versions("http://publico.pt", limit=10)
        result2 = await list_versions("http://publico.pt", limit=10)

    assert result1 == result2
    assert fetch_mock.call_count == 1


@pytest.mark.asyncio
async def test_extract_text_cache_avoids_second_http_request(mock_html_response):
    """Calling extract_text twice should fetch snapshot HTML only once."""
    clear_cache()

    snapshot_result = {
        "url": "http://example.pt",
        "found": True,
        "timestamp": "20050315120000",
        "archive_url": "https://arquivo.pt/wayback/20050315120000/http://example.pt",
        "no_frame_url": ("https://arquivo.pt/wayback/noFrame/20050315120000/http://example.pt"),
        "captured_at_iso": "2005-03-15T12:00:00",
    }

    mock_resp = MagicMock()
    mock_resp.text = mock_html_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
        patch("arquivo_pt_mcp._client", return_value=mock_client),
    ):
        result1 = await extract_text("http://example.pt", timestamp="20050315")
        result2 = await extract_text("http://example.pt", timestamp="20050315")

    assert result1 == result2
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_clear_cache_removes_entries(mock_search_response):
    """clear_cache should empty all caches so the next call hits the network."""
    clear_cache()

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.text = json.dumps(mock_search_response)

    fetch_mock = AsyncMock(return_value=mock_resp)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=fetch_mock):
        await search("term")
        clear_cache()
        await search("term")

    assert fetch_mock.call_count == 2


def test_clear_cache_empties_screenshot_cache():
    clear_cache()
    SCREENSHOT_CACHE[("url", "ts", 500_000)] = ({}, b"data", "image/png")
    assert len(SCREENSHOT_CACHE) == 1
    clear_cache()
    assert len(SCREENSHOT_CACHE) == 0
