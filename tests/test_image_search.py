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

    with (
        patch(
            "arquivo_pt_mcp._fetch_with_retry",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_fetch
    ):
        await image_search("Porto", image_type="jpeg")

    params = mock_fetch.call_args.kwargs.get("params", {})
    assert params.get("type") == "jpeg"
