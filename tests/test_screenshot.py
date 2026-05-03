"""Tests for the get_screenshot tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from arquivo_pt_mcp import _screenshot_url, clear_cache, get_screenshot

# ── URL construction (pure) ───────────────────────────────────


def test_screenshot_url_matches_docs_example():
    inner, outer = _screenshot_url("http://example.pt/page.html", "20050315120000")
    assert inner == "https://arquivo.pt/noFrame/replay/20050315120000/http://example.pt/page.html"
    assert outer == (
        "https://arquivo.pt/screenshot?url="
        "https%3A%2F%2Farquivo.pt%2FnoFrame%2Freplay%2F20050315120000"
        "%2Fhttp%3A%2F%2Fexample.pt%2Fpage.html"
    )


# ── URL-mode happy path ──────────────────────────────────────


@pytest.mark.asyncio
async def test_url_mode_returns_screenshot_url():
    clear_cache()

    snapshot_result = {
        "url": "http://publico.pt",
        "found": True,
        "timestamp": "20100601000000",
        "archive_url": "https://arquivo.pt/wayback/20100601000000/http://publico.pt",
        "no_frame_url": "",
        "captured_at_iso": "2010-06-01T00:00:00",
    }

    with patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result):
        result = await get_screenshot("http://publico.pt", timestamp="20100601000000")

    assert isinstance(result, dict)
    assert result["found"] is True
    assert result["url"] == "http://publico.pt"
    assert result["timestamp"] == "20100601000000"
    assert result["screenshot_url"].startswith("https://arquivo.pt/screenshot?url=")
    assert result["no_frame_url"].startswith("https://arquivo.pt/noFrame/replay/")
    assert result["captured_at_iso"] == "2010-06-01T00:00:00"
    assert "inline" not in result


# ── URL-mode "not found" ─────────────────────────────────────


@pytest.mark.asyncio
async def test_url_mode_not_found_no_http_call():
    clear_cache()

    not_found = {
        "url": "http://never-archived.example.com",
        "found": False,
        "message": "no captures found",
    }

    with patch("arquivo_pt_mcp.get_snapshot", return_value=not_found):
        result = await get_screenshot("http://never-archived.example.com")

    assert isinstance(result, dict)
    assert result["found"] is False
    assert result["message"] == "no captures found"


# ── Inline-mode happy path ───────────────────────────────────


@pytest.mark.asyncio
async def test_inline_mode_returns_png_bytes():
    clear_cache()

    snapshot_result = {
        "url": "http://publico.pt",
        "found": True,
        "timestamp": "20100601000000",
        "archive_url": "https://arquivo.pt/wayback/20100601000000/http://publico.pt",
        "no_frame_url": "",
        "captured_at_iso": "2010-06-01T00:00:00",
    }

    # Minimal valid PNG: 8-byte signature + minimal IHDR chunk
    png_body = (
        b"\x89PNG\r\n\x1a\n"  # PNG signature
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.content = png_body

    with (
        patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
        patch("arquivo_pt_mcp._fetch_with_retry", return_value=mock_resp),
    ):
        result = await get_screenshot("http://publico.pt", timestamp="20100601000000", inline=True)

    assert isinstance(result, tuple)
    assert len(result) == 3
    meta, body, mime = result
    assert meta["inline"] is True
    assert meta["byte_size"] == len(png_body)
    assert meta["truncated"] is False
    assert body == png_body
    assert mime == "image/png"


# ── Inline-mode size cap ─────────────────────────────────────


@pytest.mark.asyncio
async def test_inline_mode_size_cap():
    clear_cache()

    snapshot_result = {
        "url": "http://publico.pt",
        "found": True,
        "timestamp": "20100601000000",
        "archive_url": "",
        "no_frame_url": "",
        "captured_at_iso": "2010-06-01T00:00:00",
    }

    body_1kb = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1014  # ~1 KB

    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.content = body_1kb

    with (
        patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
        patch("arquivo_pt_mcp._fetch_with_retry", return_value=mock_resp),
    ):
        result = await get_screenshot(
            "http://publico.pt", timestamp="20100601000000", inline=True, max_bytes=500
        )

    assert isinstance(result, dict)
    assert result["truncated"] is True
    assert result["byte_size"] == len(body_1kb)
    assert "note" in result


# ── Inline-mode 404 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_inline_mode_404_returns_warning():
    clear_cache()

    snapshot_result = {
        "url": "http://publico.pt",
        "found": True,
        "timestamp": "20100601000000",
        "archive_url": "",
        "no_frame_url": "",
        "captured_at_iso": "2010-06-01T00:00:00",
    }

    error = httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404))

    with (
        patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
        patch("arquivo_pt_mcp._fetch_with_retry", side_effect=error),
    ):
        result = await get_screenshot("http://publico.pt", timestamp="20100601000000", inline=True)

    assert isinstance(result, dict)
    assert result["found"] is True
    assert result["screenshot_url"].startswith("https://arquivo.pt/screenshot?url=")
    assert "warning" in result
    assert "404" in result["warning"]


# ── Inline-mode wrong content-type ───────────────────────────


@pytest.mark.asyncio
async def test_inline_mode_wrong_content_type():
    clear_cache()

    snapshot_result = {
        "url": "http://publico.pt",
        "found": True,
        "timestamp": "20100601000000",
        "archive_url": "",
        "no_frame_url": "",
        "captured_at_iso": "2010-06-01T00:00:00",
    }

    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.content = b"<html><body>error</body></html>"

    with (
        patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
        patch("arquivo_pt_mcp._fetch_with_retry", return_value=mock_resp),
    ):
        result = await get_screenshot("http://publico.pt", timestamp="20100601000000", inline=True)

    assert isinstance(result, dict)
    assert "warning" in result
    assert "text/html" in result["warning"]


# ── Cache hit (inline) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_inline_cache_avoids_second_http_request():
    clear_cache()

    snapshot_result = {
        "url": "http://publico.pt",
        "found": True,
        "timestamp": "20100601000000",
        "archive_url": "",
        "no_frame_url": "",
        "captured_at_iso": "2010-06-01T00:00:00",
    }

    png_body = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.content = png_body

    fetch_mock = AsyncMock(return_value=mock_resp)

    with (
        patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
        patch("arquivo_pt_mcp._fetch_with_retry", new=fetch_mock),
    ):
        result1 = await get_screenshot("http://publico.pt", timestamp="20100601000000", inline=True)
        result2 = await get_screenshot("http://publico.pt", timestamp="20100601000000", inline=True)

    assert result1[1] == result2[1]
    assert fetch_mock.call_count == 1
