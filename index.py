“””
arquivo-pt-mcp — Model Context Protocol server for Arquivo.pt
(the Portuguese Web Archive).

Exposes four tools:

- search           full-text/URL search across the archive
- list_versions    CDX query: every capture of a given URL
- get_snapshot     fetch a specific archived page
- extract_text     fetch + strip HTML, return readable text

Endpoints used:
https://arquivo.pt/textsearch                 (search API)
https://arquivo.pt/wayback/cdx                (CDX server)
https://arquivo.pt/wayback/{timestamp}/{url}  (Memento/Wayback)

API docs: https://github.com/arquivo/pwa-technologies/wiki/Arquivo.pt-API
“””

from **future** import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

ARQUIVO_BASE = “https://arquivo.pt”
TEXTSEARCH = f”{ARQUIVO_BASE}/textsearch”
CDX = f”{ARQUIVO_BASE}/wayback/cdx”
WAYBACK = f”{ARQUIVO_BASE}/wayback”

USER_AGENT = “arquivo-pt-mcp/0.1 (+https://github.com/your-org/arquivo-pt-mcp)”
DEFAULT_TIMEOUT = 30.0

server = Server(“arquivo-pt”)

# —– helpers —————————————————————

def _client() -> httpx.AsyncClient:
return httpx.AsyncClient(
timeout=DEFAULT_TIMEOUT,
headers={“User-Agent”: USER_AGENT, “Accept”: “application/json”},
follow_redirects=True,
)

def _normalize_date(d: str | None) -> str | None:
“”“Accept YYYY, YYYY-MM, YYYY-MM-DD, or YYYYMMDDHHMMSS — return YYYYMMDD000000-style.”””
if not d:
return None
digits = re.sub(r”\D”, “”, d)
if len(digits) < 4:
raise ValueError(f”date must include at least a 4-digit year: {d!r}”)
# Pad on the right with zeros up to 14 chars
return (digits + “00000000000000”)[:14]

def _strip_html(html: str) -> str:
# Drop scripts/styles, then tags, then collapse whitespace.
html = re.sub(r”<(script|style)\b[^>]*>.*?</\1>”, “ “, html, flags=re.I | re.S)
text = re.sub(r”<[^>]+>”, “ “, html)
text = re.sub(r”\s+”, “ “, text)
return text.strip()

# —– tool implementations –––––––––––––––––––––––––

async def search(
query: str,
max_items: int = 10,
from_date: str | None = None,
to_date: str | None = None,
site_search: str | None = None,
) -> dict[str, Any]:
“”“Full-text search across Arquivo.pt.”””
params: dict[str, Any] = {“q”: query, “maxItems”: max(1, min(max_items, 50))}
if (f := _normalize_date(from_date)):
params[“from”] = f
if (t := _normalize_date(to_date)):
params[“to”] = t
if site_search:
params[“siteSearch”] = site_search

```
async with _client() as client:
    resp = await client.get(TEXTSEARCH, params=params)
    resp.raise_for_status()
    data = resp.json()

items = []
for item in data.get("response_items", []):
    items.append({
        "title": item.get("title"),
        "original_url": item.get("originalURL"),
        "archive_url": item.get("linkToArchive"),
        "captured": item.get("tstamp"),
        "snippet": item.get("snippet"),
        "mime": item.get("mimeType"),
    })
return {
    "query": query,
    "total_estimated": data.get("estimated_nr_results"),
    "returned": len(items),
    "results": items,
}
```

async def list_versions(url: str, limit: int = 50) -> dict[str, Any]:
“”“List every archived capture of a URL via the CDX server.”””
params = {“url”: url, “output”: “json”, “limit”: min(limit, 500)}
async with _client() as client:
resp = await client.get(CDX, params=params)
resp.raise_for_status()
text = resp.text.strip()

```
# CDX returns either JSON-array-of-arrays or NDJSON depending on flags.
captures = []
if text.startswith("["):
    rows = json.loads(text)
    # First row is column headers in CDX-J style.
    if rows and isinstance(rows[0], list):
        headers, *body = rows
        for row in body:
            rec = dict(zip(headers, row))
            captures.append({
                "timestamp": rec.get("timestamp"),
                "original": rec.get("original"),
                "mime": rec.get("mimetype"),
                "status": rec.get("statuscode"),
                "digest": rec.get("digest"),
                "archive_url": f"{WAYBACK}/{rec.get('timestamp')}/{rec.get('original')}",
            })
else:
    # Space-separated CDX format fallback.
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 7:
            ts, orig, mime, status = parts[1], parts[2], parts[3], parts[4]
            captures.append({
                "timestamp": ts,
                "original": orig,
                "mime": mime,
                "status": status,
                "archive_url": f"{WAYBACK}/{ts}/{orig}",
            })

return {"url": url, "count": len(captures), "captures": captures}
```

async def get_snapshot(url: str, timestamp: str | None = None) -> dict[str, Any]:
“”“Fetch metadata + URL for a specific snapshot. If timestamp is None, latest.”””
if timestamp:
ts = _normalize_date(timestamp)
snapshot_url = f”{WAYBACK}/{ts}/{url}”
else:
# Use CDX with limit=1 sorted descending for the latest capture.
params = {“url”: url, “output”: “json”, “limit”: 1, “sort”: “reverse”}
async with _client() as client:
resp = await client.get(CDX, params=params)
resp.raise_for_status()
rows = resp.json() if resp.text.startswith(”[”) else []
if not rows or len(rows) < 2:
return {“url”: url, “found”: False, “message”: “no captures found”}
headers, row = rows[0], rows[1]
rec = dict(zip(headers, row))
ts = rec.get(“timestamp”)
snapshot_url = f”{WAYBACK}/{ts}/{url}”

```
return {
    "url": url,
    "found": True,
    "timestamp": ts,
    "archive_url": snapshot_url,
    "captured_at_iso": _ts_to_iso(ts),
}
```

async def extract_text(url: str, timestamp: str | None = None, max_chars: int = 8000) -> dict[str, Any]:
“”“Fetch a snapshot and return cleaned text content.”””
snap = await get_snapshot(url, timestamp)
if not snap.get(“found”):
return snap

```
async with _client() as client:
    # Use the noFrame variant when available — strips Wayback's banner.
    archive_url = snap["archive_url"].replace(f"{WAYBACK}/", f"{WAYBACK}/noFrame/")
    resp = await client.get(archive_url)
    resp.raise_for_status()
    html = resp.text

text = _strip_html(html)
truncated = len(text) > max_chars
return {
    "url": url,
    "timestamp": snap["timestamp"],
    "archive_url": snap["archive_url"],
    "char_count": len(text),
    "truncated": truncated,
    "text": text[:max_chars],
}
```

def _ts_to_iso(ts: str | None) -> str | None:
if not ts or len(ts) < 8:
return None
try:
return datetime.strptime(ts.ljust(14, “0”), “%Y%m%d%H%M%S”).isoformat()
except ValueError:
return None

# —– MCP wiring ————————————————————

@server.list_tools()
async def list_tools() -> list[Tool]:
return [
Tool(
name=“search”,
description=(
“Full-text search across the Portuguese Web Archive (Arquivo.pt). “
“Use for finding pages that ever contained given terms, optionally “
“scoped by date range or site.”
),
inputSchema={
“type”: “object”,
“properties”: {
“query”: {“type”: “string”, “description”: “Search terms”},
“max_items”: {“type”: “integer”, “default”: 10, “minimum”: 1, “maximum”: 50},
“from_date”: {“type”: “string”, “description”: “YYYY, YYYY-MM, or YYYY-MM-DD”},
“to_date”: {“type”: “string”, “description”: “YYYY, YYYY-MM, or YYYY-MM-DD”},
“site_search”: {“type”: “string”, “description”: “Restrict to a domain, e.g. ‘publico.pt’”},
},
“required”: [“query”],
},
),
Tool(
name=“list_versions”,
description=“List every archived capture of a specific URL (CDX query). Use to see how a page changed over time.”,
inputSchema={
“type”: “object”,
“properties”: {
“url”: {“type”: “string”},
“limit”: {“type”: “integer”, “default”: 50, “minimum”: 1, “maximum”: 500},
},
“required”: [“url”],
},
),
Tool(
name=“get_snapshot”,
description=“Get the archive URL for a specific snapshot of a page. Omit timestamp for the latest capture.”,
inputSchema={
“type”: “object”,
“properties”: {
“url”: {“type”: “string”},
“timestamp”: {“type”: “string”, “description”: “YYYY, YYYY-MM-DD, or YYYYMMDDHHMMSS”},
},
“required”: [“url”],
},
),
Tool(
name=“extract_text”,
description=“Fetch an archived snapshot and return its readable text content (HTML stripped).”,
inputSchema={
“type”: “object”,
“properties”: {
“url”: {“type”: “string”},
“timestamp”: {“type”: “string”},
“max_chars”: {“type”: “integer”, “default”: 8000, “minimum”: 500, “maximum”: 50000},
},
“required”: [“url”],
},
),
]

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
handlers = {
“search”: search,
“list_versions”: list_versions,
“get_snapshot”: get_snapshot,
“extract_text”: extract_text,
}
handler = handlers.get(name)
if not handler:
return [TextContent(type=“text”, text=f”unknown tool: {name}”)]
try:
result = await handler(**arguments)
return [TextContent(type=“text”, text=json.dumps(result, ensure_ascii=False, indent=2))]
except httpx.HTTPStatusError as e:
return [TextContent(type=“text”, text=f”arquivo.pt returned HTTP {e.response.status_code}: {e.response.text[:500]}”)]
except Exception as e:
return [TextContent(type=“text”, text=f”error in {name}: {type(e).**name**}: {e}”)]

async def main() -> None:
async with stdio_server() as (read, write):
await server.run(read, write, server.create_initialization_options())

if **name** == “**main**”:
asyncio.run(main())
