"""Tests for the search tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arquivo_pt_mcp import search


@pytest.mark.asyncio
async def test_search_basic(mock_search_response):
    """Test basic search returns parsed results."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.text = json.dumps(mock_search_response)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
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
    mock_resp.text = json.dumps(mock_search_response)

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        result = await search("eleições", from_date="2004", to_date="2006-06")

    assert result["query"] == "eleições"
    # Verify the params were passed
    params = mock_fetch.call_args.kwargs.get("params", {})
    assert params.get("from") == "20040000000000"
    assert params.get("to") == "20060600000000"


@pytest.mark.asyncio
async def test_search_site_filter(mock_search_response):
    """Test site search restriction."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.text = json.dumps(mock_search_response)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await search("eleições", site_search="publico.pt")

    assert result["returned"] == 1


@pytest.mark.asyncio
async def test_search_with_collection_and_mime_type(mock_search_response):
    """New params collection, mime_type and offset end up in the API params."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.text = json.dumps(mock_search_response)

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await search("eleições", collection="EAWP33", mime_type="pdf", offset=10)

    params = mock_fetch.call_args.kwargs.get("params", {})
    assert params.get("collection") == "EAWP33"
    assert params.get("type") == "pdf"
    assert params.get("offset") == 10


@pytest.mark.asyncio
async def test_search_returns_next_and_previous_page(mock_search_response):
    """next_page and previous_page are surfaced in the result."""
    mock_response_with_pages = dict(mock_search_response)
    mock_response_with_pages["next_page"] = "https://arquivo.pt/textsearch?...&offset=50"
    mock_response_with_pages["previous_page"] = "https://arquivo.pt/textsearch?...&offset=0"

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_with_pages
    mock_resp.text = json.dumps(mock_response_with_pages)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await search("eleições")

    assert result["next_page"] == "https://arquivo.pt/textsearch?...&offset=50"
    assert result["previous_page"] == "https://arquivo.pt/textsearch?...&offset=0"


@pytest.mark.asyncio
async def test_search_offset_zero_not_sent(mock_search_response):
    """offset=0 should not be sent to the API (it's the default)."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_search_response
    mock_resp.text = json.dumps(mock_search_response)

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await search("eleições", offset=0)

    params = mock_fetch.call_args.kwargs.get("params", {})
    assert "offset" not in params
