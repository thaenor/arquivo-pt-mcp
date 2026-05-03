"""Tests for the list_versions (CDX) tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arquivo_pt_mcp import list_versions


@pytest.mark.asyncio
async def test_list_versions_jsonl_format(mock_cdx_jsonl_response):
    """Real CDX returns JSON-Lines: one JSON object per line."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await list_versions("publico.pt")

    assert result["url"] == "publico.pt"
    assert result["count"] == 2
    assert result["captures"][0]["timestamp"] == "20050315120000"
    assert result["captures"][0]["original"] == "http://publico.pt/"
    assert result["captures"][0]["mime"] == "text/html"
    assert result["captures"][1]["status"] == "200"
    assert result["captures"][1]["digest"] == "SHA1GHIJKL"
    assert result["captures"][0]["archive_url"].startswith(
        "https://arquivo.pt/wayback/20050315120000/"
    )


@pytest.mark.asyncio
async def test_list_versions_empty_response():
    """Empty body (real API behavior for never-archived URLs)."""
    mock_resp = MagicMock()
    mock_resp.text = ""

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await list_versions("nonexistent.example.pt")

    assert result["count"] == 0
    assert result["captures"] == []


@pytest.mark.asyncio
async def test_list_versions_skips_malformed_lines(mock_cdx_jsonl_response):
    """A malformed line in JSONL output shouldn't blow up the whole response."""
    text = mock_cdx_jsonl_response + "\nthis-is-not-json\n"
    mock_resp = MagicMock()
    mock_resp.text = text

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await list_versions("publico.pt")

    assert result["count"] == 2  # malformed line skipped


@pytest.mark.asyncio
async def test_list_versions_offset(mock_cdx_jsonl_response):
    """Offset parameter is passed through to CDX when > 0."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        result = await list_versions("publico.pt", limit=10, offset=10)

    assert result["url"] == "publico.pt"
    passed_params = mock_fetch.call_args.kwargs["params"]
    assert passed_params["offset"] == 10
    assert passed_params["limit"] == 10


@pytest.mark.asyncio
async def test_list_versions_compact_mode(mock_cdx_jsonl_response):
    """Compact mode returns year summary + reduced capture fields, not raw CDX metadata."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await list_versions("publico.pt", compact=True)

    assert "summary" in result
    assert result["summary"]["2005"] == 1
    assert result["summary"]["2006"] == 1
    assert "captures" in result
    assert "note" in result
    cap = result["captures"][0]
    assert "mime" not in cap
    assert "digest" not in cap
    assert "status" not in cap
    assert "length" not in cap
    assert cap["timestamp"] == "20050315120000"
    assert cap["archive_url"].startswith("https://arquivo.pt/wayback/")


@pytest.mark.asyncio
async def test_list_versions_compact_false_is_current_behavior(mock_cdx_jsonl_response):
    """Explicit compact=False (the default) must return the same shape as today."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await list_versions("publico.pt", compact=False)

    assert result["url"] == "publico.pt"
    assert result["count"] == 2
    assert "captures" in result
    assert result["captures"][0]["mime"] == "text/html"
    assert result["captures"][0]["digest"] == "SHA1ABCDEF"


@pytest.mark.asyncio
async def test_list_versions_preserves_urlkey_and_collection(mock_cdx_jsonl_response):
    """urlkey and collection fields are preserved for matchType=domain disambiguation."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch("arquivo_pt_mcp._fetch_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await list_versions("publico.pt")

    assert result["captures"][0]["urlkey"] == "pt,publico)/"
    assert result["captures"][0]["collection"] == "Roteiro"


@pytest.mark.asyncio
async def test_list_versions_with_filter_repeated_tuples(mock_cdx_jsonl_response):
    """Multiple filter values become repeated tuples in params."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await list_versions("publico.pt", filter=["=status:200", "=mime:text/html"])

    params = mock_fetch.call_args.kwargs.get("params", {})
    filter_params = [v for k, v in params if k == "filter"]
    assert filter_params == ["=status:200", "=mime:text/html"]


@pytest.mark.asyncio
async def test_list_versions_match_type_passed_through(mock_cdx_jsonl_response):
    """match_type=domain is passed to the CDX server."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await list_versions("publico.pt", match_type="domain")

    params = mock_fetch.call_args.kwargs.get("params", {})
    passed = dict(params) if not isinstance(params, dict) else params
    assert passed.get("matchType") == "domain"


@pytest.mark.asyncio
async def test_list_versions_closest_triggers_sort(mock_cdx_jsonl_response):
    """closest=... triggers sort=closest in the API params."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await list_versions("publico.pt", sort="closest", closest="20050315120000")

    params = mock_fetch.call_args.kwargs.get("params", {})
    passed = dict(params) if not isinstance(params, dict) else params
    assert passed.get("sort") == "closest"
    assert passed.get("closest") == "20050315120000"


@pytest.mark.asyncio
async def test_list_versions_from_to_dates(mock_cdx_jsonl_response):
    """from_date and to_date are normalized and passed to CDX."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await list_versions("publico.pt", from_date="2005", to_date="2006")

    params = mock_fetch.call_args.kwargs.get("params", {})
    passed = dict(params) if not isinstance(params, dict) else params
    assert passed.get("from") == "20050000000000"
    assert passed.get("to") == "20060000000000"


@pytest.mark.asyncio
async def test_list_versions_match_type_exact_not_sent(mock_cdx_jsonl_response):
    """match_type=exact (default) should not be sent to the API."""
    mock_resp = MagicMock()
    mock_resp.text = mock_cdx_jsonl_response

    with patch(
        "arquivo_pt_mcp._fetch_with_retry",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_fetch:
        await list_versions("publico.pt", match_type="exact")

    params = mock_fetch.call_args.kwargs.get("params", {})
    passed = dict(params) if not isinstance(params, dict) else params
    assert "matchType" not in passed
