"""
arquivo-pt-mcp — Model Context Protocol server for Arquivo.pt
(the Portuguese Web Archive).

Exposes five tools:

- search           full-text/URL search across the archive
- list_versions    CDX query: every capture of a given URL
- get_snapshot     fetch a specific archived page
- extract_text     fetch + strip HTML, return readable text
- image_search     search 1.8B+ archived images

Endpoints used:
  https://arquivo.pt/textsearch                 (search API)
  https://arquivo.pt/imagesearch                 (image search API)
  https://arquivo.pt/wayback/cdx                (CDX server)
  https://arquivo.pt/wayback/{timestamp}/{url}  (Memento/Wayback)

API docs: docs/api-reference.md
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote  # noqa: F401 — kept for future URL-encoding needs

import httpx
from cachetools import TTLCache
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

ARQUIVO_BASE = "https://arquivo.pt"
TEXTSEARCH = f"{ARQUIVO_BASE}/textsearch"
IMAGESEARCH = f"{ARQUIVO_BASE}/imagesearch"
CDX = f"{ARQUIVO_BASE}/wayback/cdx"
WAYBACK = f"{ARQUIVO_BASE}/wayback"

USER_AGENT = "arquivo-pt-mcp/0.1.0 (https://github.com/thaenor/arquivo-pt-mcp)"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 5

server = Server("arquivo-pt")

# ─── caching ────────────────────────────────────────────────

CDX_CACHE = TTLCache(maxsize=1000, ttl=15 * 60)
SEARCH_CACHE = TTLCache(maxsize=1000, ttl=15 * 60)
SNAPSHOT_CACHE = TTLCache(maxsize=1000, ttl=60 * 60)


def clear_cache() -> None:
    """Clear all module-level caches (useful for testing)."""
    CDX_CACHE.clear()
    SEARCH_CACHE.clear()
    SNAPSHOT_CACHE.clear()


# ─── helpers ────────────────────────────────────────────────


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


def _normalize_date(d: str | None) -> str | None:
    """Accept YYYY, YYYY-MM, YYYY-MM-DD, or YYYYMMDDHHMMSS — return YYYYMMDD000000-style."""
    if not d:
        return None
    digits = re.sub(r"\D", "", d)
    if len(digits) < 4:
        raise ValueError(f"date must include at least a 4-digit year: {d!r}")
    return (digits + "00000000000000")[:14]


def _ts_to_iso(ts: str | None) -> str | None:
    if not ts or len(ts) < 8:
        return None
    try:
        return datetime.strptime(ts.ljust(14, "0"), "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        return ts


def _strip_html(html: str) -> str:
    """Remove scripts, styles, and HTML tags, then collapse whitespace.

    This is a best-effort regex-based stripper. For heavily JavaScript-rendered
    pages, very little text may be extractable. Consider linkToExtractedText
    in the Arquivo.pt API for server-side extraction.
    """
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&\w+;", " ", text)  # strip HTML entities
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_cdx_jsonl(text: str) -> list[dict[str, Any]]:
    """Parse Arquivo.pt CDX server output (JSON-Lines: one JSON object per line).

    Real keys: urlkey, timestamp, url, mime, status, digest, length, offset,
    filename, collection, source, source-coll. Empty body → []. Malformed
    lines are skipped rather than aborting the whole response.
    """
    captures: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        ts = rec.get("timestamp", "")
        orig = rec.get("url", "")
        captures.append(
            {
                "timestamp": ts,
                "original": orig,
                "mime": rec.get("mime", ""),
                "status": rec.get("status", ""),
                "digest": rec.get("digest", ""),
                "length": rec.get("length", ""),
                "archive_url": f"{WAYBACK}/{ts}/{orig}" if ts and orig else "",
            }
        )
    return captures


async def _fetch_with_retry(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    """Fetch with manual retry on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.TimeoutException as e:
            last_exc = e
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 429 and e.response.status_code < 500:
                raise  # client errors don't benefit from retry
            last_exc = e
        if attempt < MAX_RETRIES:
            await asyncio.sleep(2**attempt)
    raise last_exc  # type: ignore[misc]


# ─── tool implementations ──────────────────────────────────


async def search(
    query: str,
    max_items: int = 10,
    from_date: str | None = None,
    to_date: str | None = None,
    site_search: str | None = None,
) -> dict[str, Any]:
    """Full-text search across Arquivo.pt."""
    cache_key = (query, max_items, from_date, to_date, site_search)
    if cache_key in SEARCH_CACHE:
        return SEARCH_CACHE[cache_key]

    params: dict[str, Any] = {"q": query, "maxItems": max(1, min(max_items, 50))}
    if f := _normalize_date(from_date):
        params["from"] = f
    if t := _normalize_date(to_date):
        params["to"] = t
    if site_search:
        params["siteSearch"] = site_search

    async with _client() as client:
        resp = await _fetch_with_retry(client, TEXTSEARCH, params=params)
        data = resp.json()

    items = []
    for item in data.get("response_items", []):
        items.append(
            {
                "title": item.get("title"),
                "original_url": item.get("originalURL"),
                "archive_url": item.get("linkToArchive"),
                "screenshot_url": item.get("linkToScreenshot"),
                "no_frame_url": item.get("linkToNoFrame"),
                "extracted_text_url": item.get("linkToExtractedText"),
                "captured": item.get("tstamp"),
                "snippet": item.get("snippet"),
                "mime": item.get("mimeType"),
            }
        )
    result = {
        "query": query,
        "total_estimated": data.get("estimated_nr_results"),
        "returned": len(items),
        "results": items,
    }
    SEARCH_CACHE[cache_key] = result
    return result


async def image_search(
    query: str,
    max_items: int = 10,
    from_date: str | None = None,
    to_date: str | None = None,
    site_search: str | None = None,
    image_type: str | None = None,
) -> dict[str, Any]:
    """Search 1.8B+ archived images on Arquivo.pt (Dionisius)."""
    cache_key = (query, max_items, from_date, to_date, site_search, image_type)
    if cache_key in SEARCH_CACHE:
        return SEARCH_CACHE[cache_key]

    params: dict[str, Any] = {"q": query, "maxItems": max(1, min(max_items, 50))}
    if f := _normalize_date(from_date):
        params["from"] = f
    if t := _normalize_date(to_date):
        params["to"] = t
    if site_search:
        params["siteSearch"] = site_search
    if image_type:
        params["type"] = image_type

    async with _client() as client:
        resp = await _fetch_with_retry(client, IMAGESEARCH, params=params)
        data = resp.json()

    items = []
    for item in data.get("responseItems", []):
        alt_list = item.get("imgAlt") or []
        items.append(
            {
                "title": item.get("pageTitle"),
                "original_url": item.get("pageURL"),
                "image_url": item.get("imgSrc") or item.get("imgLinkToArchive"),
                "image_archive_url": item.get("imgLinkToArchive"),
                "page_archive_url": item.get("pageLinkToArchive"),
                "captured": item.get("imgTstamp"),
                "page_captured": item.get("pageTstamp"),
                "width": item.get("imgWidth"),
                "height": item.get("imgHeight"),
                "alt": alt_list[0] if isinstance(alt_list, list) and alt_list else None,
                "mime": item.get("imgMimeType"),
            }
        )
    result = {
        "query": query,
        "total_estimated": data.get("totalItems"),
        "returned": len(items),
        "results": items,
    }
    SEARCH_CACHE[cache_key] = result
    return result


async def list_versions(url: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List every archived capture of a URL via the CDX server."""
    cache_key = (url, limit, offset)
    if cache_key in CDX_CACHE:
        return CDX_CACHE[cache_key]

    params = {"url": url, "output": "json", "limit": min(limit, 500)}
    if offset > 0:
        params["offset"] = offset
    async with _client() as client:
        resp = await _fetch_with_retry(client, CDX, params=params)
        text = resp.text.strip()

    captures = _parse_cdx_jsonl(text)
    result = {"url": url, "count": len(captures), "captures": captures}
    CDX_CACHE[cache_key] = result
    return result


async def get_snapshot(url: str, timestamp: str | None = None) -> dict[str, Any]:
    """Fetch metadata + URL for a specific snapshot. If timestamp is None, get latest."""
    if timestamp:
        ts = _normalize_date(timestamp)
        snapshot_url = f"{WAYBACK}/{ts}/{url}"
    else:
        # Use CDX with limit=1 sorted descending for the latest capture.
        cache_key = (url,)
        if cache_key in CDX_CACHE:
            cached = CDX_CACHE[cache_key]
            return {
                "url": url,
                "found": True,
                "timestamp": cached["timestamp"],
                "archive_url": cached["archive_url"],
                "no_frame_url": cached["no_frame_url"],
                "captured_at_iso": cached["captured_at_iso"],
            }
        params = {"url": url, "output": "json", "limit": 1, "sort": "reverse"}
        async with _client() as client:
            resp = await _fetch_with_retry(client, CDX, params=params)
            captures = _parse_cdx_jsonl(resp.text)
        if not captures:
            return {"url": url, "found": False, "message": "no captures found"}
        ts = captures[0]["timestamp"]
        snapshot_url = f"{WAYBACK}/{ts}/{url}" if ts else ""

    result = {
        "url": url,
        "found": True,
        "timestamp": ts,
        "archive_url": snapshot_url,
        "no_frame_url": (
            snapshot_url.replace(f"{WAYBACK}/", f"{WAYBACK}/noFrame/") if snapshot_url else ""
        ),
        "captured_at_iso": _ts_to_iso(ts),
    }
    if not timestamp:
        CDX_CACHE[(url,)] = result
    return result


async def extract_text(
    url: str, timestamp: str | None = None, max_chars: int = 8000
) -> dict[str, Any]:
    """Fetch a snapshot and return cleaned text content."""
    snap = await get_snapshot(url, timestamp)
    if not snap.get("found"):
        return snap

    raw_archive_url = snap.get("no_frame_url") or snap["archive_url"]
    cache_key = (raw_archive_url, max_chars)
    if cache_key in SNAPSHOT_CACHE:
        return SNAPSHOT_CACHE[cache_key]

    async with _client() as client:
        resp = await client.get(raw_archive_url)
        if resp.status_code == 404 and snap.get("no_frame_url"):
            resp = await client.get(snap["archive_url"])
        resp.raise_for_status()
        html = resp.text

    text = _strip_html(html)
    truncated = len(text) > max_chars
    result = {
        "url": url,
        "timestamp": snap.get("timestamp"),
        "archive_url": snap.get("archive_url"),
        "char_count": len(text),
        "truncated": truncated,
        "text": text[:max_chars],
    }
    SNAPSHOT_CACHE[cache_key] = result
    return result


# ─── MCP wiring ─────────────────────────────────────────────


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search",
            description=(
                "Full-text search across the Portuguese Web Archive (Arquivo.pt). "
                "Use for finding pages that ever contained given terms, optionally "
                "scoped by date range or site."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms"},
                    "max_items": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                    "from_date": {
                        "type": "string",
                        "description": "Start date: YYYY, YYYY-MM, or YYYY-MM-DD",
                    },
                    "to_date": {
                        "type": "string",
                        "description": "End date: YYYY, YYYY-MM, or YYYY-MM-DD",
                    },
                    "site_search": {
                        "type": "string",
                        "description": "Restrict to a domain, e.g. 'publico.pt'",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="image_search",
            description=(
                "Search 1.8B+ archived images on Arquivo.pt (Dionisius image search). "
                "Find historical photos, logos, and graphics from the Portuguese web."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Image search terms"},
                    "max_items": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "from_date": {
                        "type": "string",
                        "description": "Start date: YYYY, YYYY-MM, or YYYY-MM-DD",
                    },
                    "to_date": {
                        "type": "string",
                        "description": "End date: YYYY, YYYY-MM, or YYYY-MM-DD",
                    },
                    "site_search": {"type": "string", "description": "Restrict to a domain"},
                    "image_type": {"type": "string", "description": "Image format: jpeg, png, gif"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_versions",
            description=(
                "List every archived capture of a specific URL (CDX query). "
                "Use to see how a page changed over time."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to query capture history for"},
                    "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "description": "Pagination offset for CDX results (skip first N captures)",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="get_snapshot",
            description=(
                "Get the archive URL for a specific snapshot of a page. "
                "Omit timestamp for the latest capture."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to look up"},
                    "timestamp": {
                        "type": "string",
                        "description": "YYYY, YYYY-MM-DD, or YYYYMMDDHHMMSS",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="extract_text",
            description=(
                "Fetch an archived snapshot and return its readable text content (HTML stripped)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to extract text from"},
                    "timestamp": {
                        "type": "string",
                        "description": "Optional: specific snapshot timestamp",
                    },
                    "max_chars": {
                        "type": "integer",
                        "default": 8000,
                        "minimum": 500,
                        "maximum": 50000,
                    },
                },
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handlers = {
        "search": search,
        "image_search": image_search,
        "list_versions": list_versions,
        "get_snapshot": get_snapshot,
        "extract_text": extract_text,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"unknown tool: {name}")]
    try:
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except httpx.HTTPStatusError as e:
        return [
            TextContent(
                type="text",
                text=(
                    f"arquivo.pt returned HTTP {e.response.status_code}: {e.response.text[:500]}"
                ),
            )
        ]
    except httpx.TimeoutException:
        return [
            TextContent(
                type="text",
                text=(f"arquivo.pt request timed out after {DEFAULT_TIMEOUT}s"),
            )
        ]
    except Exception as e:
        return [TextContent(type="text", text=f"error in {name}: {type(e).__name__}: {e}")]


def main() -> None:
    """Synchronous entry point for the console script."""
    asyncio.run(_async_main())


async def _async_main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    main()
