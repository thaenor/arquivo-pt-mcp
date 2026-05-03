"""Tests for the image_search tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arquivo_pt_mcp import image_search


@pytest.mark.asyncio
async def test_image_search_basic(mock_image_search_response):
    """Test basic image search returns parsed results."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_image_search_response
    mock_resp.text = json.dumps(mock_image_search_response)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await image_search("Praça do Comércio")

    assert result["query"] == "Praça do Comércio"
    assert result["returned"] == 1
    assert result["results"][0]["title"] == "Lisboa - Praça do Comércio"
    assert result["total_estimated"] == 15


@pytest.mark.asyncio
async def test_image_search_with_type_filter(mock_image_search_response):
    """Test image search with format filter."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_image_search_response
    mock_resp.text = json.dumps(mock_image_search_response)

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await image_search("Porto", image_type="jpeg")

    params = mock_fetch.call_args.kwargs.get("params", {})
    assert params.get("type") == "jpeg"


@pytest.mark.asyncio
async def test_image_search_with_more_becomes_comma_joined(mock_image_search_response):
    """more=['safe'] becomes params['more'] == 'safe'."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_image_search_response
    mock_resp.text = json.dumps(mock_image_search_response)

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await image_search("Porto", more=["safe"])

    params = mock_fetch.call_args.kwargs.get("params", {})
    assert params.get("more") == "safe"


@pytest.mark.asyncio
async def test_image_search_multiple_more_joined():
    """more=['safe', 'imgDigest'] becomes 'safe,imgDigest'."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "totalItems": 1,
        "responseItems": [{"pageTitle": "T", "imgDigest": "abc", "safe": "0.850"}],
    }
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await image_search("Porto", more=["safe", "imgDigest"])

    params = mock_fetch.call_args.kwargs.get("params", {})
    assert params.get("more") == "safe,imgDigest"


@pytest.mark.asyncio
async def test_image_search_surfaces_safe_field():
    """Per-item safe field appears when present in the source item."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "totalItems": 1,
        "responseItems": [
            {
                "pageTitle": "Test",
                "imgSrc": "http://example.com/img.jpg",
                "imgLinkToArchive": "http://arquivo.pt/wayback/...",
                "pageURL": "http://example.com",
                "pageLinkToArchive": "http://arquivo.pt/wayback/...",
                "imgTstamp": "20050315120000",
                "pageTstamp": "20050315120000",
                "safe": "0.300",
            }
        ],
    }
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await image_search("nsfw query", safe_search="off", more=["safe"])

    assert result["results"][0]["safe"] == "0.300"


@pytest.mark.asyncio
async def test_image_search_with_size_and_collection(mock_image_search_response):
    """size and collection params are passed through."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_image_search_response
    mock_resp.text = json.dumps(mock_image_search_response)

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await image_search("Porto", size="large", collection="EAWP33", offset=20)

    params = mock_fetch.call_args.kwargs.get("params", {})
    assert params.get("size") == "large"
    assert params.get("collection") == "EAWP33"
    assert params.get("offset") == 20
