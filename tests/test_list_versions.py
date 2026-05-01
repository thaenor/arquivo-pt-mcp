"""Tests for the list_versions (CDX) tool."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from arquivo_pt_mcp import list_versions


@pytest.mark.asyncio
async def test_list_versions_json_format(mock_cdx_json_response):
    """Test CDX response parsing with JSON array-of-arrays format."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_json_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
        result = await list_versions("publico.pt")

    assert result["url"] == "publico.pt"
    assert result["count"] == 2
    assert result["captures"][0]["timestamp"] == "20050315120000"
    assert result["captures"][1]["status"] == "200"


@pytest.mark.asyncio
async def test_list_versions_text_format(mock_cdx_text_response):
    """Test CDX response parsing with space-separated text format."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_text_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
        result = await list_versions("publico.pt")

    assert result["url"] == "publico.pt"
    assert result["count"] == 1
    assert result["captures"][0]["timestamp"] == "20050315120000"
    assert "archive_url" in result["captures"][0]


@pytest.mark.asyncio
async def test_list_versions_empty_response():
    """Test CDX with empty response."""
    mock_resp = MagicMock()
    mock_resp.text = ""
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
        result = await list_versions("nonexistent.example.pt")

    assert result["count"] == 0
    assert result["captures"] == []