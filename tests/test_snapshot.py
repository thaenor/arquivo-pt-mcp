"""Tests for get_snapshot and extract_text tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arquivo_pt_mcp import _strip_html, extract_text, get_snapshot


class TestGetSnapshot:
    @pytest.mark.asyncio
    async def test_get_snapshot_with_timestamp(self):
        """Test getting a snapshot with explicit timestamp."""
        result = await get_snapshot("http://publico.pt", timestamp="20050315")

        assert result["url"] == "http://publico.pt"
        assert result["found"] is True
        assert "20050315" in result["archive_url"]
        assert "noFrame" in result["no_frame_url"]

    @pytest.mark.asyncio
    async def test_get_snapshot_latest(self):
        """Test getting latest snapshot via CDX fallback."""
        cdx_response = json.dumps(
            [
                ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                ["20240101120000", "http://publico.pt/", "text/html", "200", "SHA1:abc", "12345"],
            ]
        )

        mock_resp = MagicMock()
        mock_resp.text = cdx_response
        mock_resp.json.return_value = json.loads(cdx_response)

        with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
            result = await get_snapshot("http://publico.pt")

        assert result["found"] is True
        assert result["timestamp"] == "20240101120000"

    @pytest.mark.asyncio
    async def test_get_snapshot_not_found(self):
        """Test snapshot not found returns found=False."""
        cdx_response = json.dumps([])

        mock_resp = MagicMock()
        mock_resp.text = cdx_response
        mock_resp.json.return_value = []

        with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
            result = await get_snapshot("http://nonexistent.example.pt")

        assert result["found"] is False


class TestExtractText:
    @pytest.mark.asyncio
    async def test_extract_text_basic(self, mock_html_response):
        """Test text extraction strips HTML properly."""
        # get_snapshot with timestamp returns result without CDX call
        snapshot_result = {
            "url": "http://example.pt",
            "found": True,
            "timestamp": "20050315120000",
            "archive_url": "https://arquivo.pt/wayback/20050315120000/http://example.pt",
            "no_frame_url": "https://arquivo.pt/wayback/noFrame/20050315120000/http://example.pt",
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
            result = await extract_text("http://example.pt", timestamp="20050315")

        assert result["url"] == "http://example.pt"
        assert "Hello Arquivo" in result["text"]
        assert "test content from 2005" in result["text"]
        assert "<script>" not in result["text"]
        assert "<style>" not in result["text"]


class TestStripHtml:
    def test_strip_html_basic(self):
        """Test basic HTML stripping."""
        html = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        assert _strip_html(html) == "Test Hello world"

    def test_strip_html_scripts(self):
        """Test script tag removal."""
        html = "<html><body><p>Content</p><script>var x = 1;</script></body></html>"
        result = _strip_html(html)
        assert "var x" not in result
        assert "Content" in result

    def test_strip_html_styles(self):
        """Test style tag removal."""
        html = "<html><body><p>Text</p><style>body{color:red}</style></body></html>"
        result = _strip_html(html)
        assert "color" not in result
        assert "Text" in result

    def test_strip_html_entities(self):
        """Test HTML entity stripping."""
        html = "<p>Caf&eacute; &amp; restaurant</p>"
        result = _strip_html(html)
        assert "&amp;" not in result
        assert "Caf" in result  # &eacute; stripped to space
