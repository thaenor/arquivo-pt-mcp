"""Tests for the image_search tool."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from arquivo_pt_mcp import image_search


@pytest.mark.asyncio
async def test_image_search_basic(mock_image_search_response):
    """Test basic image search returns parsed results."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_image_search_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
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
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("arquivo_pt_mcp._client", return_value=mock_client):
        result = await image_search("Porto", image_type="jpeg")

    call_args = mock_client.get.call_args
    params = call_args.kwargs.get("params", call_args[1].get("params", {}))
    assert params.get("type") == "jpeg"