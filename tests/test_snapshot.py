"""Tests for get_snapshot and extract_text tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
        """Latest snapshot via CDX is parsed from real JSON-Lines format."""
        cdx_response = json.dumps(
            {
                "urlkey": "pt,publico)/",
                "timestamp": "20240101120000",
                "url": "http://publico.pt/",
                "mime": "text/html",
                "status": "200",
                "digest": "SHA1:abc",
                "length": "12345",
            }
        )

        mock_resp = MagicMock()
        mock_resp.text = cdx_response

        with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
            result = await get_snapshot("http://publico.pt")

        assert result["found"] is True
        assert result["timestamp"] == "20240101120000"
        assert "noFrame" in result["no_frame_url"]

    @pytest.mark.asyncio
    async def test_get_snapshot_not_found(self):
        """Empty CDX response (real API behavior for never-archived URLs)."""
        mock_resp = MagicMock()
        mock_resp.text = ""

        with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
            result = await get_snapshot("http://nonexistent.example.pt")

        assert result["found"] is False


class TestExtractText:
    @pytest.mark.asyncio
    async def test_extract_text_basic(self, mock_html_response):
        """Test text extraction strips HTML properly via regex fallback path."""
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

        with (
            patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
            patch(
                "arquivo_pt_mcp._fetch_with_retry",
                side_effect=[httpx.TimeoutException("timeout"), mock_resp],
            ),
        ):
            result = await extract_text("http://example.pt", timestamp="20050315")

        assert result["url"] == "http://example.pt"
        assert result["extraction_method"] == "regex"
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


class TestExtractTextServerFallback:
    @pytest.mark.asyncio
    async def test_server_extraction_success(self, mock_html_response):
        """Primary path: text comes from /textextracted endpoint."""
        snapshot_result = {
            "url": "http://example.pt",
            "found": True,
            "timestamp": "20050315120000",
            "archive_url": "https://arquivo.pt/wayback/20050315120000/http://example.pt",
            "no_frame_url": "https://arquivo.pt/wayback/noFrame/20050315120000/http://example.pt",
        }

        mock_textextracted = MagicMock()
        mock_textextracted.text = (
            "Server-extracted text content from the archived Portuguese web page. "
            "This text has enough characters to avoid triggering the low-content warning."
        )
        mock_textextracted.raise_for_status = MagicMock()

        with patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result):
            with patch(
                "arquivo_pt_mcp._fetch_with_retry",
                new=AsyncMock(return_value=mock_textextracted),
            ):
                result = await extract_text("http://example.pt", timestamp="20050315")

        assert result["extraction_method"] == "server"
        assert "Server-extracted text" in result["text"]
        assert "warning" not in result

    @pytest.mark.asyncio
    async def test_falls_back_to_regex_on_server_error(self, mock_html_response):
        """When /textextracted fails, fall back to regex HTML stripping."""
        snapshot_result = {
            "url": "http://example.pt",
            "found": True,
            "timestamp": "20050315120000",
            "archive_url": "https://arquivo.pt/wayback/20050315120000/http://example.pt",
            "no_frame_url": "https://arquivo.pt/wayback/noFrame/20050315120000/http://example.pt",
        }

        mock_html_resp = MagicMock()
        mock_html_resp.text = mock_html_response
        mock_html_resp.raise_for_status = MagicMock()

        with (
            patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result),
            patch(
                "arquivo_pt_mcp._fetch_with_retry",
                side_effect=[httpx.TimeoutException("timeout"), mock_html_resp],
            ),
        ):
            result = await extract_text("http://example.pt", timestamp="20050315")

        assert result["extraction_method"] == "regex"
        assert "Hello Arquivo" in result["text"]

    @pytest.mark.asyncio
    async def test_warning_when_both_methods_yield_little_text(self):
        """Warning is present when both server and regex extraction yield < 100 chars."""
        snapshot_result = {
            "url": "http://example.pt",
            "found": True,
            "timestamp": "20000515120000",
            "archive_url": "https://arquivo.pt/wayback/20000515120000/http://example.pt",
            "no_frame_url": "https://arquivo.pt/wayback/noFrame/20000515120000/http://example.pt",
        }

        mock_textextracted = MagicMock()
        mock_textextracted.text = "Tiny"
        mock_textextracted.raise_for_status = MagicMock()

        with patch("arquivo_pt_mcp.get_snapshot", return_value=snapshot_result):
            with patch(
                "arquivo_pt_mcp._fetch_with_retry",
                new=AsyncMock(return_value=mock_textextracted),
            ):
                result = await extract_text("http://example.pt", timestamp="20000515")

        assert result["extraction_method"] == "server"
        assert result["char_count"] < 100
        assert "warning" in result
