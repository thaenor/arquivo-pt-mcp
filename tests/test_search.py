"""Tests for the search tool."""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from arquivo_pt_mcp import search


@pytest.mark.asyncio
async def test_search_basic(mock_search_response):
    """Test basic search returns parsed results."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
        result = await search("eleições 2005")

    assert result["query"] == "eleições 2005"
    assert result["returned"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Eleições 2005 - Resultados"
    assert result["results"][0]["original_url"] == "http://www.publico.pt/politica/eleicoes2005"
    assert result["results"][0]["archive_url"].startswith("https://arquivo.pt/wayback/")
    assert result["total_estimated"] == 42


@pytest.mark.asyncio
async def test_search_with_date_range(mock_search_response):
    """Test search with from/to date normalization."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
        result = await search("eleições", from_date="2004", to_date="2006-06")

    assert result["query"] == "eleições"
    # Verify the params were passed
    call_args = mock_client.get.call_args
    params = call_args.kwargs.get("params", call_args[1].get("params", {}))
    assert params.get("from") == "20040000000000"
    assert params.get("to") == "20060600000000"


@pytest.mark.asyncio
async def test_search_site_filter(mock_search_response):
    """Test site search restriction."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
        result = await search("eleições", site_search="publico.pt")

    assert result["returned"] == 1