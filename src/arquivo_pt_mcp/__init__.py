"""
arquivo-pt-mcp — Model Context Protocol server for Arquivo.pt
(the Portuguese Web Archive).

Exposes six tools:

- search           full-text/URL search across the archive
- list_versions    CDX query: every capture of a given URL
- get_snapshot     fetch a specific archived page
- extract_text     fetch + strip HTML, return readable text
- image_search     search 1.8B+ archived images
- get_screenshot   PNG render of an archived page

Endpoints used:
  https://arquivo.pt/textsearch                 (search API)
  https://arquivo.pt/imagesearch                 (image search API)
  https://arquivo.pt/wayback/cdx                (CDX server)
  https://arquivo.pt/wayback/{timestamp}/{url}  (Memento/Wayback)

API docs: docs/api-reference.md

Supports both stdio and streamable HTTP transports.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.metadata
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

try:
    __version__ = importlib.metadata.version("arquivo-pt-mcp")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0.dev"

import httpx
from cachetools import TTLCache
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ImageContent, TextContent, Tool
from pydantic import ValidationError

from arquivo_pt_mcp.models import (
    ExtractTextParams,
    GetScreenshotParams,
    GetSnapshotParams,
    ImageSearchParams,
    ListVersionsParams,
    SearchParams,
)

ARQUIVO_BASE = "https://arquivo.pt"
TEXTSEARCH = f"{ARQUIVO_BASE}/textsearch"
IMAGESEARCH = f"{ARQUIVO_BASE}/imagesearch"
CDX = f"{ARQUIVO_BASE}/wayback/cdx"
WAYBACK = f"{ARQUIVO_BASE}/wayback"
TEXTEXTRACTED = f"{ARQUIVO_BASE}/textextracted"

USER_AGENT = f"arquivo-pt-mcp/{__version__} (https://github.com/thaenor/arquivo-pt-mcp)"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 5

server = Server("arquivo-pt")

# ─── caching ────────────────────────────────────────────────

CDX_CACHE = TTLCache(maxsize=1000, ttl=15 * 60)
SEARCH_CACHE = TTLCache(maxsize=1000, ttl=15 * 60)
SNAPSHOT_CACHE = TTLCache(maxsize=1000, ttl=60 * 60)
SCREENSHOT_CACHE = TTLCache(maxsize=200, ttl=60 * 60)


def clear_cache() -> None:
    """Clear all module-level caches (useful for testing)."""
    CDX_CACHE.clear()
    SEARCH_CACHE.clear()
    SNAPSHOT_CACHE.clear()
    SCREENSHOT_CACHE.clear()


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
                "urlkey": rec.get("urlkey", ""),
                "collection": rec.get("collection", ""),
                "archive_url": f"{WAYBACK}/{ts}/{orig}" if ts and orig else "",
            }
        )
    return captures


def _screenshot_url(url: str, ts: str) -> tuple[str, str]:
    """Return (no_frame_replay_url, screenshot_url) for a (url, timestamp).

    The Arquivo.pt screenshot endpoint takes the noFrame replay URL as a
    percent-encoded query argument — see docs/api-reference.md §4.
    """
    inner = f"{ARQUIVO_BASE}/noFrame/replay/{ts}/{url}"
    return inner, f"{ARQUIVO_BASE}/screenshot?url={quote(inner, safe='')}"


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
    collection: str | None = None,
    mime_type: str | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Full-text search across Arquivo.pt."""
    cache_key = (
        query,
        max_items,
        from_date,
        to_date,
        site_search,
        collection,
        mime_type,
        offset,
    )
    if cache_key in SEARCH_CACHE:
        return SEARCH_CACHE[cache_key]

    params: dict[str, Any] = {"q": query, "maxItems": max_items}
    if f := _normalize_date(from_date):
        params["from"] = f
    if t := _normalize_date(to_date):
        params["to"] = t
    if site_search:
        params["siteSearch"] = site_search
    if collection:
        params["collection"] = collection
    if mime_type:
        params["type"] = mime_type
    if offset > 0:
        params["offset"] = offset

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
        "next_page": data.get("next_page"),
        "previous_page": data.get("previous_page"),
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
    size: str | None = None,
    safe_search: str = "on",
    collection: str | None = None,
    offset: int = 0,
    more: list[str] | None = None,
) -> dict[str, Any]:
    """Search 1.8B+ archived images on Arquivo.pt (Dionisius)."""
    cache_key = (
        query,
        max_items,
        from_date,
        to_date,
        site_search,
        image_type,
        size,
        safe_search,
        collection,
        offset,
        tuple(sorted(more)) if more else (),
    )
    if cache_key in SEARCH_CACHE:
        return SEARCH_CACHE[cache_key]

    params: dict[str, Any] = {"q": query, "maxItems": max_items}
    if f := _normalize_date(from_date):
        params["from"] = f
    if t := _normalize_date(to_date):
        params["to"] = t
    if site_search:
        params["siteSearch"] = site_search
    if image_type:
        params["type"] = image_type
    if size:
        params["size"] = size
    if safe_search:
        params["safeSearch"] = safe_search
    if collection:
        params["collection"] = collection
    if offset > 0:
        params["offset"] = offset
    if more:
        params["more"] = ",".join(more)

    async with _client() as client:
        resp = await _fetch_with_retry(client, IMAGESEARCH, params=params)
        data = resp.json()

    items = []
    for item in data.get("responseItems", []):
        alt_list = item.get("imgAlt") or []
        entry = {
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
        if "imgDigest" in item:
            entry["digest"] = item["imgDigest"]
        if "pageHost" in item:
            entry["page_host"] = item["pageHost"]
        if "pageImages" in item:
            entry["page_images"] = item["pageImages"]
        if "safe" in item:
            entry["safe"] = item["safe"]
        items.append(entry)
    result = {
        "query": query,
        "total_estimated": data.get("totalItems"),
        "returned": len(items),
        "results": items,
    }
    SEARCH_CACHE[cache_key] = result
    return result


async def list_versions(
    url: str,
    limit: int = 50,
    offset: int = 0,
    compact: bool = False,
    filter: list[str] | None = None,
    match_type: str = "exact",
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str = "default",
    closest: str | None = None,
) -> dict[str, Any]:
    """List every archived capture of a URL via the CDX server."""
    cache_key = (
        url,
        limit,
        offset,
        tuple(sorted(filter)) if filter else (),
        match_type,
        from_date,
        to_date,
        sort,
        closest,
    )
    if cache_key in CDX_CACHE:
        captures = CDX_CACHE[cache_key]
    else:
        if filter:
            params: Any = [("url", url), ("output", "json"), ("limit", str(limit))]
            if offset > 0:
                params.append(("offset", str(offset)))
            for f in filter:
                params.append(("filter", f))
            if match_type != "exact":
                params.append(("matchType", match_type))
            if f_d := _normalize_date(from_date):
                params.append(("from", f_d))
            if t_d := _normalize_date(to_date):
                params.append(("to", t_d))
            if sort != "default":
                params.append(("sort", sort))
            if closest:
                params.append(("closest", _normalize_date(closest)))
        else:
            params = {"url": url, "output": "json", "limit": limit}
            if offset > 0:
                params["offset"] = offset
            if match_type != "exact":
                params["matchType"] = match_type
            if f_d := _normalize_date(from_date):
                params["from"] = f_d
            if t_d := _normalize_date(to_date):
                params["to"] = t_d
            if sort != "default":
                params["sort"] = sort
            if closest:
                params["closest"] = _normalize_date(closest)
        async with _client() as client:
            resp = await _fetch_with_retry(client, CDX, params=params)
            text = resp.text.strip()
        captures = _parse_cdx_jsonl(text)
        CDX_CACHE[cache_key] = captures

    if compact:
        by_year: dict[str, int] = {}
        for c in captures:
            year = c["timestamp"][:4] if c.get("timestamp") else "unknown"
            by_year[year] = by_year.get(year, 0) + 1
        compact_captures = [
            {
                "timestamp": c["timestamp"],
                "original": c["original"],
                "archive_url": c["archive_url"],
            }
            for c in captures
        ]
        return {
            "url": url,
            "count": len(captures),
            "summary": dict(sorted(by_year.items())),
            "captures": compact_captures,
            "note": (
                f"Showing {len(captures)} captures in compact form. "
                "Set compact=false for full CDX metadata (mime, status, digest, length). "
                "Use offset parameter to paginate through older captures."
            ),
        }

    return {"url": url, "count": len(captures), "captures": captures}


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


async def get_screenshot(
    url: str,
    timestamp: str | None = None,
    inline: bool = False,
    max_bytes: int = 500_000,
) -> dict[str, Any] | tuple[dict[str, Any], bytes, str]:
    """Get the Arquivo.pt PNG render of a snapshot.

    With inline=False (default): return JSON containing the screenshot URL.
    With inline=True: also return the raw PNG bytes for embedding as
    ImageContent (subject to max_bytes).

    Returns a dict in URL-only mode, or a (dict, png_bytes, mime) triple
    in inline mode. The dispatcher in call_tool() unpacks both shapes.
    """
    snap = await get_snapshot(url, timestamp)
    if not snap.get("found"):
        return snap
    ts = snap["timestamp"]
    no_frame, screenshot_url = _screenshot_url(url, ts)

    base = {
        "url": url,
        "timestamp": ts,
        "found": True,
        "screenshot_url": screenshot_url,
        "no_frame_url": no_frame,
        "captured_at_iso": _ts_to_iso(ts),
    }

    if not inline:
        return base

    cache_key = (url, ts, max_bytes)
    if cache_key in SCREENSHOT_CACHE:
        cached_meta, cached_bytes, cached_mime = SCREENSHOT_CACHE[cache_key]
        return cached_meta, cached_bytes, cached_mime

    async with _client() as client:
        try:
            resp = await _fetch_with_retry(client, screenshot_url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                base["warning"] = (
                    "screenshot endpoint returned 404 — Arquivo.pt has not "
                    "rendered this snapshot. Try a different timestamp."
                )
                return base
            raise

    mime = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime != "image/png":
        base["warning"] = f"unexpected content-type {mime!r} from screenshot endpoint"
        return base

    body = resp.content
    if len(body) > max_bytes:
        base["truncated"] = True
        base["byte_size"] = len(body)
        base["note"] = (
            f"PNG ({len(body)} bytes) exceeds max_bytes={max_bytes}; "
            "screenshot URL still returned. Increase max_bytes to embed."
        )
        return base

    meta = {**base, "inline": True, "byte_size": len(body), "truncated": False}
    SCREENSHOT_CACHE[cache_key] = (meta, body, mime)
    return meta, body, mime


async def extract_text(
    url: str, timestamp: str | None = None, max_chars: int = 8000
) -> dict[str, Any]:
    """Fetch a snapshot and return cleaned text content."""
    snap = await get_snapshot(url, timestamp)
    if not snap.get("found"):
        return snap

    ts = snap.get("timestamp", "")
    cache_key = (snap["archive_url"], max_chars)
    if cache_key in SNAPSHOT_CACHE:
        return SNAPSHOT_CACHE[cache_key]

    text = ""
    extraction_method = ""

    if ts:
        async with _client() as client:
            try:
                resp = await _fetch_with_retry(client, TEXTEXTRACTED, params={"m": f"{url}/{ts}"})
                text = resp.text.strip()
                extraction_method = "server"
            except (httpx.HTTPStatusError, httpx.TimeoutException):
                pass

    if not text:
        extraction_method = "regex"
        async with _client() as client:
            raw_archive_url = snap.get("no_frame_url") or snap["archive_url"]
            try:
                resp = await _fetch_with_retry(client, raw_archive_url)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and snap.get("no_frame_url"):
                    resp = await _fetch_with_retry(client, snap["archive_url"])
                else:
                    raise
            text = _strip_html(resp.text)

    truncated = len(text) > max_chars
    result = {
        "url": url,
        "timestamp": ts,
        "archive_url": snap.get("archive_url"),
        "extraction_method": extraction_method,
        "char_count": len(text),
        "truncated": truncated,
        "text": text[:max_chars],
    }

    if len(text) < 100:
        result["warning"] = (
            f"Only {len(text)} characters extracted. Early Portuguese web pages were often "
            "image/table-based and yield little extractable text. "
            "Try a different timestamp when the page may have had more text content, "
            "or use get_snapshot + WebFetch to inspect the page visually."
        )

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
                    "collection": {
                        "type": "string",
                        "description": "Restrict to a collection ID (e.g. 'EAWP33')",
                    },
                    "mime_type": {
                        "type": "string",
                        "enum": ["pdf", "html", "doc", "xls", "ppt", "rtf"],
                        "description": "Filter by MIME type: pdf, html, doc, xls, ppt, rtf",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "description": (
                            "Pagination offset. Use with next_page/previous_page from "
                            "response to walk through results instead of fetching "
                            "next_page URL via WebFetch."
                        ),
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
                    "size": {
                        "type": "string",
                        "enum": ["small", "medium", "large"],
                        "description": (
                            "Image dimensions: small (≤65536 px²), medium, large (>810000 px²)"
                        ),
                    },
                    "safe_search": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "default": "on",
                        "description": (
                            "NSFW filter; set to 'off' to disable. When off, "
                            "pair with more=['safe'] to get the safe score "
                            "(values <0.500 indicate unsafe)."
                        ),
                    },
                    "collection": {
                        "type": "string",
                        "description": "Restrict to a collection ID",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "description": "Pagination offset",
                    },
                    "more": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["imgDigest", "pageHost", "pageImages", "safe"],
                        },
                        "description": (
                            "Surface hidden fields: imgDigest (MD5 hash), "
                            "pageHost (source host), pageImages (image count "
                            "on page), safe (NSFW score 0.000-1.000, where "
                            "<0.500 = unsafe)"
                        ),
                    },
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
                    "compact": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return year-bucketed summary instead of full CDX "
                            "records. Reduces output size for URLs with many "
                            "captures."
                        ),
                    },
                    "filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Field filters, repeatable. Format: '=field:value' "
                            "(exact), '!=field:value' (negate+exact), "
                            "'~field:regex' (regex), '!~field:regex' "
                            "(negate+regex). Example: ['=status:200', "
                            "'=mime:text/html']"
                        ),
                    },
                    "match_type": {
                        "type": "string",
                        "enum": ["exact", "prefix", "host", "domain"],
                        "default": "exact",
                        "description": "URL matching: exact (default), prefix, host, or domain",
                    },
                    "from_date": {
                        "type": "string",
                        "description": (
                            "Start timestamp: YYYY, YYYY-MM, YYYY-MM-DD, or YYYYMMDDHHMMSS"
                        ),
                    },
                    "to_date": {
                        "type": "string",
                        "description": "End timestamp (same format as from_date)",
                    },
                    "sort": {
                        "type": "string",
                        "enum": ["default", "reverse", "closest"],
                        "default": "default",
                        "description": (
                            "Sort order: default (chronological), reverse "
                            "(newest first), closest (require 'closest' param)"
                        ),
                    },
                    "closest": {
                        "type": "string",
                        "description": (
                            "Timestamp for sort=closest to rank by "
                            "time-distance. Accepts same date formats as "
                            "from_date."
                        ),
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
        Tool(
            name="get_screenshot",
            description=(
                "Get the Arquivo.pt PNG render of an archived page. By default "
                "returns the screenshot URL; pass inline=true to embed the PNG "
                "(useful for letting the model see the page). Omit timestamp "
                "for the latest capture."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to screenshot"},
                    "timestamp": {
                        "type": "string",
                        "description": "YYYY, YYYY-MM-DD, or YYYYMMDDHHMMSS",
                    },
                    "inline": {
                        "type": "boolean",
                        "default": False,
                        "description": "Embed the PNG bytes in the response (heavier).",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "default": 500000,
                        "minimum": 1000,
                        "maximum": 5000000,
                        "description": "When inline=true, cap the embedded PNG size.",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


PARAM_MODELS = {
    "search": SearchParams,
    "image_search": ImageSearchParams,
    "list_versions": ListVersionsParams,
    "get_snapshot": GetSnapshotParams,
    "extract_text": ExtractTextParams,
    "get_screenshot": GetScreenshotParams,
}


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent]:
    handlers = {
        "search": search,
        "image_search": image_search,
        "list_versions": list_versions,
        "get_snapshot": get_snapshot,
        "extract_text": extract_text,
        "get_screenshot": get_screenshot,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"unknown tool: {name}")]

    model = PARAM_MODELS.get(name)
    if model:
        try:
            arguments = model(**arguments).model_dump()
        except ValidationError as e:
            return [TextContent(type="text", text=f"invalid arguments: {e}")]

    try:
        result = await handler(**arguments)

        if isinstance(result, tuple) and len(result) == 3:
            meta, body, mime = result
            return [
                TextContent(type="text", text=json.dumps(meta, ensure_ascii=False, indent=2)),
                ImageContent(
                    type="image",
                    data=base64.b64encode(body).decode("ascii"),
                    mimeType=mime,
                ),
            ]

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
    from arquivo_pt_mcp.cli import parse_argv  # lazy to avoid circular imports

    args = parse_argv()
    if args.transport == "stdio":
        asyncio.run(_async_main_stdio())
    else:
        asyncio.run(_async_main_http(args))


async def _async_main_stdio() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


# deprecated thin alias for backward compatibility
_async_main = _async_main_stdio


async def _async_main_http(args: argparse.Namespace) -> None:
    import uvicorn

    from arquivo_pt_mcp.http_app import create_app  # lazy import

    app = create_app(
        path=args.path,
        json_response=args.json_response,
        stateless=args.stateless,
        allowed_hosts=args.allowed_host,
        allowed_origins=args.allowed_origin,
        enable_dns_rebinding_protection=not args.no_dns_rebinding_protection,
    )
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=False,
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    main()
