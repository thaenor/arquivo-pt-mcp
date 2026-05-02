"""Integration tests against the live arquivo.pt API.

Skipped unless RUN_INTEGRATION=1 is set. Marked with the `integration` pytest
marker so the nightly CI job can target them with `-m integration`. These
tests exercise the full request/response path against the real service —
their job is to catch upstream API drift the unit-test mocks can't see.

Organized as one class per tool plus a class for the MCP `call_tool` wrapper.
"""

import json
import os

import httpx
import pytest

from arquivo_pt_mcp import (
    call_tool,
    extract_text,
    get_snapshot,
    image_search,
    list_versions,
    search,
)
from tests.integration_fixtures import (
    KNOWN_ARCHIVED_URL,
    KNOWN_TIMESTAMP_2010,
    NEVER_ARCHIVED_URL,
    NONSENSE_QUERY,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 to run live arquivo.pt tests",
    ),
]


def _in_range(ts: str, low: str, high: str) -> bool:
    """Compare 14-char timestamps as strings (lexical order matches chronological)."""
    return low <= (ts or "").ljust(14, "0") <= high


# ─── search ────────────────────────────────────────────────


class TestSearch:
    async def test_basic_query(self):
        result = await search("publico", max_items=2)
        assert result["returned"] >= 1
        for item in result["results"]:
            assert item["original_url"]
            assert item["archive_url"].startswith("https://arquivo.pt/wayback/")
            assert item["captured"]
            # snippet is informational; just verify the field exists
            assert "snippet" in item

    async def test_max_items_respected(self):
        result = await search("portugal", max_items=3)
        assert result["returned"] <= 3

    async def test_date_range_with_mixed_formats(self):
        # "2005" → 20050101000000; "2010-12-31" → 20101231000000.
        result = await search("eleicoes", max_items=5, from_date="2005", to_date="2010-12-31")
        for item in result["results"]:
            ts = item["captured"]
            assert _in_range(ts, "20050000000000", "20110000000000"), (
                f"capture {ts} fell outside requested range"
            )

    async def test_site_search_filter(self):
        result = await search("noticias", max_items=5, site_search="publico.pt")
        assert result["returned"] >= 1
        for item in result["results"]:
            assert "publico.pt" in (item["original_url"] or "")

    async def test_zero_results(self):
        result = await search(NONSENSE_QUERY)
        assert result["returned"] == 0


# ─── image_search ──────────────────────────────────────────


class TestImageSearch:
    async def test_basic_query(self):
        result = await image_search("lisboa", max_items=2)
        assert result["returned"] >= 1
        for item in result["results"]:
            assert item["image_url"]
            assert item["captured"]

    async def test_site_search_restriction(self):
        # publico.pt has known image presence; just verify scoping works
        result = await image_search("noticias", max_items=3, site_search="publico.pt")
        for item in result["results"]:
            # original_url is the page URL — should contain the domain
            assert "publico.pt" in (item["original_url"] or "")

    async def test_image_type_filter(self):
        result = await image_search("porto", max_items=3, image_type="jpeg")
        assert result["returned"] >= 1
        for item in result["results"]:
            assert item["mime"] == "image/jpeg"

    async def test_zero_results(self):
        result = await image_search(NONSENSE_QUERY)
        assert result["returned"] == 0


# ─── list_versions (CDX) ───────────────────────────────────


class TestListVersions:
    async def test_known_url_has_captures(self):
        result = await list_versions(KNOWN_ARCHIVED_URL, limit=3)
        assert result["count"] >= 2
        for cap in result["captures"]:
            assert cap["timestamp"]
            assert cap["archive_url"].startswith("https://arquivo.pt/wayback/")

    async def test_limit_one(self):
        result = await list_versions(KNOWN_ARCHIVED_URL, limit=1)
        assert result["count"] == 1

    async def test_captures_are_sorted(self):
        result = await list_versions(KNOWN_ARCHIVED_URL, limit=10)
        assert result["count"] >= 2
        timestamps = [c["timestamp"] for c in result["captures"]]
        assert timestamps == sorted(timestamps), f"captures not in order: {timestamps}"

    async def test_never_archived_url(self):
        result = await list_versions(NEVER_ARCHIVED_URL)
        assert result["count"] == 0
        assert result["captures"] == []


# ─── get_snapshot ──────────────────────────────────────────


class TestGetSnapshot:
    async def test_latest_no_timestamp(self):
        result = await get_snapshot(KNOWN_ARCHIVED_URL)
        assert result["found"] is True
        assert result["timestamp"]
        assert "noFrame" in result["no_frame_url"]
        # Verify the regular Wayback archive URL is reachable (noFrame may 404).
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(result["archive_url"])
            assert r.status_code < 400, f"archive_url not reachable: {r.status_code}"

    async def test_year_only_timestamp(self):
        result = await get_snapshot(KNOWN_ARCHIVED_URL, timestamp="2010")
        assert result["found"] is True
        # _normalize_date("2010") → "20100000000000"
        assert "20100000000000" in result["archive_url"]

    async def test_iso_date_timestamp(self):
        result = await get_snapshot(KNOWN_ARCHIVED_URL, timestamp="2010-06-01")
        assert result["found"] is True
        assert "20100601" in result["archive_url"]

    async def test_never_archived_url(self):
        result = await get_snapshot(NEVER_ARCHIVED_URL)
        assert result["found"] is False


# ─── extract_text ──────────────────────────────────────────


class TestExtractText:
    async def test_real_page(self):
        result = await extract_text(KNOWN_ARCHIVED_URL, timestamp=KNOWN_TIMESTAMP_2010)
        assert result.get("found") is not False  # tool returns no `found` key on success
        assert result["char_count"] > 0
        # No HTML tags should leak through.
        assert "<" not in result["text"]
        assert ">" not in result["text"]

    async def test_max_chars_truncation(self):
        result = await extract_text(
            KNOWN_ARCHIVED_URL, timestamp=KNOWN_TIMESTAMP_2010, max_chars=5
        )
        assert result["char_count"] > 0
        assert len(result["text"]) <= 5
        assert result["truncated"] is True

    async def test_never_archived(self):
        result = await extract_text(NEVER_ARCHIVED_URL)
        assert result.get("found") is False


# ─── MCP call_tool dispatcher ──────────────────────────────


class TestMcpDispatcher:
    """Exercises the actual MCP entry surface, not the bare tool functions."""

    @pytest.mark.parametrize(
        "name,args",
        [
            ("search", {"query": "publico", "max_items": 1}),
            ("image_search", {"query": "lisboa", "max_items": 1}),
            ("list_versions", {"url": KNOWN_ARCHIVED_URL, "limit": 1}),
            ("get_snapshot", {"url": KNOWN_ARCHIVED_URL, "timestamp": "2010"}),
            (
                "extract_text",
                {"url": KNOWN_ARCHIVED_URL, "timestamp": KNOWN_TIMESTAMP_2010, "max_chars": 1000},
            ),
        ],
    )
    async def test_call_tool_each_tool(self, name, args):
        result = await call_tool(name, args)
        assert len(result) == 1
        assert result[0].type == "text"
        # Result text must be valid JSON — the dispatcher wraps tool output in json.dumps.
        parsed = json.loads(result[0].text)
        assert isinstance(parsed, dict)

    async def test_call_tool_unknown(self):
        result = await call_tool("nonexistent_tool", {})
        assert len(result) == 1
        assert "unknown tool" in result[0].text
