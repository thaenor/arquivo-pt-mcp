# Implementation Plan — `get_screenshot` Tool

**current status: ready to develop**

**Scope.** ROADMAP.md → Milestone 3 → second checkbox only
(*"Screenshot tool — new `get_screenshot` tool returning the
Arquivo.pt PNG render URL for any snapshot"*). The other Milestone 3
items (`get_metadata`, `diff_snapshots`, bulk CDX export, proximity
docs) are **out of scope**.

**Source of truth for the endpoint:**
`arquivo-pt-mcp/docs/api-reference.md` §4 (line 289) and §1.3
(line 72 — the `linkToScreenshot` example shows the exact format).

---

## 1. Goal

Add a sixth MCP tool — `get_screenshot` — that, given a URL and an
optional timestamp, returns the Arquivo.pt PNG render of that
snapshot. Two output modes:

1. **URL mode (default).** Return a JSON object with the screenshot
   URL plus the resolved timestamp. Cheap, deterministic, ideal for
   handing to a user or to `WebFetch`.
2. **Inline mode (opt-in).** Fetch the PNG and embed it as MCP
   `ImageContent` in the response so the model can actually *see* the
   page. Bounded by `max_bytes` to protect the model's context window
   and the network.

The interface mirrors `get_snapshot` so a model that already knows how
to ask for snapshots can ask for screenshots with no extra learning.

---

## 2. Current state (May 2026)

- Five tools registered in `src/arquivo_pt_mcp/__init__.py:425–553`
  via `@server.list_tools()`. None of them produce binary content.
- `search()` (`__init__.py:174`) **already surfaces**
  `screenshot_url` (`__init__.py:205`) by passing through the
  `linkToScreenshot` field from `/textsearch`. Therefore the
  screenshot URL format is already well-established in the codebase
  and confirmed against live API responses.
- `get_snapshot()` (`__init__.py:319–358`) is the natural backend for
  resolving `(url, timestamp?) → (resolved_ts, archive_url)`. Reuse,
  do not reimplement.
- **Latent bug (out of scope to fix here, see §10).**
  `get_snapshot()` builds `no_frame_url` at `__init__.py:351-353` as
  `https://arquivo.pt/wayback/noFrame/{ts}/{url}` because of how
  `WAYBACK = f"{ARQUIVO_BASE}/wayback"` (`__init__.py:50`) interacts
  with the `.replace(...)` call. Per `docs/api-reference.md:283`,
  that pattern returns **HTTP 404** — the correct pattern is
  `https://arquivo.pt/noFrame/replay/{ts}/{url}`. Because of this,
  `get_screenshot` **must compute its own noFrame URL** rather than
  trusting `get_snapshot()['no_frame_url']`. The bug should be fixed
  in a separate plan; flagged in §10.
- `call_tool` dispatcher (`__init__.py:565`) is annotated
  `-> list[TextContent]`. The MCP low-level server accepts any
  `Iterable[ContentBlock]`, so widening the annotation to
  `list[TextContent | ImageContent]` is the only structural change
  needed to support inline image responses.
- `from urllib.parse import quote` is already imported but unused
  (`__init__.py:29`, marked `noqa: F401`). The new tool will *use*
  it — drop the `# noqa: F401` comment.
- No caching layer exists for binary content. We add one
  (`SCREENSHOT_CACHE`) sized small enough that the worst-case memory
  footprint stays predictable.
- All existing tests are transport- and tool-agnostic; nothing in
  them needs to change.

---

## 3. The Arquivo.pt screenshot endpoint

From `docs/api-reference.md:289`:

```
https://arquivo.pt/screenshot?url={percent-encoded noFrame replay URL}
```

The "noFrame replay URL" passed in the `url=` query parameter must be:

```
https://arquivo.pt/noFrame/replay/{YYYYMMDDHHMMSS}/{originalURL}
```

(Confirmed by the `linkToScreenshot` example at
`api-reference.md:72`.)

Returns: `image/png`. No documented size cap; observed sizes range
from ~30 KB to ~1.5 MB. No documented rate limit beyond the global
one (already handled by `_fetch_with_retry`).

### URL construction reference

Given `url = "http://www.publico.pt/"` and `ts = "20100601000000"`:

```python
inner = f"https://arquivo.pt/noFrame/replay/{ts}/{url}"
screenshot_url = f"https://arquivo.pt/screenshot?url={quote(inner, safe='')}"
```

The `safe=''` argument is critical — the inner `://` and `/` must be
percent-encoded so the outer URL stays well-formed. Verify against
the API-reference example:

- Input inner: `https://arquivo.pt/noFrame/replay/20050315120000/http://example.pt/page.html`
- Expected outer query value: `https%3A%2F%2Farquivo.pt%2FnoFrame%2Freplay%2F20050315120000%2Fhttp%3A%2F%2Fexample.pt%2Fpage.html`

A unit test in §7.1 pins this byte-for-byte.

---

## 4. Tool design

### 4.1 Name and inputs

```
get_screenshot(
    url: str,                         # required
    timestamp: str | None = None,     # optional; latest if omitted
    inline: bool = False,             # opt-in: embed PNG bytes
    max_bytes: int = 500_000,         # safety cap for inline mode
) -> dict | (dict, ImageContent)
```

Parameter semantics:

| Field | Validation | Notes |
|---|---|---|
| `url` | non-empty string | Same shape as `get_snapshot.url`. |
| `timestamp` | None, `YYYY`, `YYYY-MM-DD`, or `YYYYMMDDHHMMSS` | Reuse `_normalize_date()` (`__init__.py:84`). |
| `inline` | bool | When True, fetch the PNG and return `ImageContent`. |
| `max_bytes` | int, `1_000 ≤ max_bytes ≤ 5_000_000` | Only used when `inline=True`. Default 500 KB is enough for ~95 % of real captures based on spot-check. |

### 4.2 Outputs

**URL mode (`inline=False`, default).** A single `TextContent` with
JSON:

```json
{
  "url": "<original url>",
  "timestamp": "<resolved 14-digit ts>",
  "found": true,
  "screenshot_url": "https://arquivo.pt/screenshot?url=...",
  "no_frame_url":   "https://arquivo.pt/noFrame/replay/<ts>/<url>",
  "captured_at_iso": "2010-06-01T00:00:00"
}
```

If `get_snapshot` says `found=False`, return:

```json
{ "url": "<original url>", "found": false, "message": "no captures found" }
```

**Inline mode (`inline=True`).** Two-part response:

1. The same JSON `TextContent` as above (the model still needs the
   URL and timestamp).
2. An `ImageContent` block: `{type:"image", data:<base64 PNG>, mimeType:"image/png"}`.

Add `"inline": true, "byte_size": <int>, "truncated": <bool>` to the
JSON. If the PNG exceeds `max_bytes`, omit the `ImageContent` block,
set `truncated=true`, and add a `note` explaining the cap was hit.
**Never** silently truncate a PNG — a partial PNG is broken.

### 4.3 Error handling

Three paths to handle inside the tool body itself; the outer
`call_tool` exception layer (`__init__.py:588–605`) catches the rest.

| Condition | Behaviour |
|---|---|
| `get_snapshot` returns `found=False` | Return that dict verbatim, no fetch. |
| Inline fetch returns 404 | Return URL-mode JSON plus `"warning": "screenshot endpoint returned 404 — Arquivo.pt has not rendered this snapshot"`. The endpoint can return 404 for very old/large captures. |
| Inline fetch returns non-PNG `Content-Type` | Treat as failure: return URL-mode JSON plus a warning. Do not embed garbage. |
| Inline fetch exceeds `max_bytes` (per `Content-Length` *or* observed body size) | Return URL-mode JSON plus `truncated=true` as in §4.2. |

### 4.4 Caching

Add a third TTL cache:

```python
SCREENSHOT_CACHE = TTLCache(maxsize=200, ttl=60 * 60)
```

- Smaller `maxsize` (200 vs 1000) because each entry can be ~500 KB
  → worst case ~100 MB. That is acceptable for a single-process
  server but worth right-sizing.
- 1 h TTL matches `SNAPSHOT_CACHE` — screenshots of an immutable
  archived capture do not change, so TTL is purely a memory-pressure
  release valve.
- Cache key: `(url, ts, max_bytes)` for inline mode. For URL-only
  mode, **no caching needed** — it is a pure string operation.
- Add `SCREENSHOT_CACHE.clear()` to the existing `clear_cache()`
  helper (`__init__.py:66`).

---

## 5. Files touched

| File | Change |
|------|--------|
| `src/arquivo_pt_mcp/__init__.py` | Add `SCREENSHOT_CACHE`, `_screenshot_url()` helper, `get_screenshot()` async function, `Tool` entry in `list_tools`, register in `handlers` and `PARAM_MODELS`, widen `call_tool` return annotation, drop `# noqa: F401` from the `quote` import. |
| `src/arquivo_pt_mcp/models.py` | Add `GetScreenshotParams`. |
| `tests/test_screenshot.py` | **New.** Unit tests for URL construction, URL-mode response, inline-mode happy path, inline-mode size cap, 404 handling, non-PNG handling. |
| `tests/test_models.py` | Add validation cases for `GetScreenshotParams`. |
| `tests/test_cache.py` | Add a case proving `clear_cache` empties `SCREENSHOT_CACHE`. |
| `tests/test_integration.py` | Add an `integration`-marked test that hits the live screenshot endpoint for a known capture (e.g. `publico.pt` at 2010-06-01) and asserts a non-empty PNG comes back. |
| `tests/integration_fixtures.py` | Add `EXPECTED_TOOL_NAMES` membership for `get_screenshot`. |
| `tests/test_stdio_smoke.py` | Add `assert by_name["get_screenshot"].inputSchema["required"] == ["url"]`. |
| `README.md` | Document the new tool in both 🇵🇹 and 🇬🇧 tables. |
| `ROADMAP.md` | Tick the second checkbox under Milestone 3. |

No changes to `_fetch_with_retry`, `_strip_html`, the existing five
handlers, the existing caches' configuration, or the HTTP transport
(if/when shipped — the new tool works identically over stdio and HTTP).

---

## 6. Per-file changes

### 6.1 `src/arquivo_pt_mcp/__init__.py`

#### 6.1.1 Imports (top of file)

- Add `import base64` near the existing `import json` (`__init__.py:25`).
- Drop `# noqa: F401 — kept for future URL-encoding needs` from the
  `from urllib.parse import quote` line (`__init__.py:29`). It will
  be live now.
- Add `from mcp.types import ImageContent, TextContent, Tool`
  (extend the existing import at `__init__.py:35`).

#### 6.1.2 New cache (after line 63)

```python
SCREENSHOT_CACHE = TTLCache(maxsize=200, ttl=60 * 60)
```

#### 6.1.3 Update `clear_cache` (around line 66)

Add one line: `SCREENSHOT_CACHE.clear()`. Keep the existing comment
about test usage.

#### 6.1.4 New helper `_screenshot_url(url, ts)` near the other `_*` helpers

```python
def _screenshot_url(url: str, ts: str) -> tuple[str, str]:
    """Return (no_frame_replay_url, screenshot_url) for a (url, timestamp).

    The Arquivo.pt screenshot endpoint takes the noFrame replay URL as a
    percent-encoded query argument — see docs/api-reference.md §4.
    """
    inner = f"{ARQUIVO_BASE}/noFrame/replay/{ts}/{url}"
    return inner, f"{ARQUIVO_BASE}/screenshot?url={quote(inner, safe='')}"
```

Place it after `_parse_cdx_jsonl` (`__init__.py:149`), before
`_fetch_with_retry` (`__init__.py:152`). Keeping helpers grouped.

**Note on `safe`:** the `safe=''` argument means *no* characters are
exempt from percent-encoding, including `/` and `:`. This matches
the live `linkToScreenshot` value shown in
`docs/api-reference.md:72`.

#### 6.1.5 New `get_screenshot()` handler

Place it immediately after `get_snapshot` (`__init__.py:358`),
before `extract_text`. Skeleton:

```python
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
```

**Note on the return shape.** Returning a `dict | tuple` makes the
dispatcher slightly more complex but avoids a second cache or a
side-channel. An alternative would be to return the bytes inside the
dict (base64) and have the dispatcher pull them out. Either is
defensible — pick the tuple approach because `bytes` doesn't survive
the `json.dumps` round-trip the dispatcher does today
(`__init__.py:587`).

#### 6.1.6 Register in `list_tools` (`__init__.py:425`)

Append after the `extract_text` Tool entry:

```python
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
```

#### 6.1.7 Register in `PARAM_MODELS` (`__init__.py:556`)

Add `"get_screenshot": GetScreenshotParams,`.

#### 6.1.8 Register in `handlers` map (`__init__.py:567`)

Add `"get_screenshot": get_screenshot,`.

#### 6.1.9 Widen `call_tool` return annotation and dispatcher

Change the signature at `__init__.py:566` from
`-> list[TextContent]` to `-> list[TextContent | ImageContent]`.

After the `result = await handler(**arguments)` call
(`__init__.py:586`), branch on the shape:

```python
result = await handler(**arguments)

if isinstance(result, tuple) and len(result) == 3:
    meta, body, mime = result
    return [
        TextContent(type="text", text=json.dumps(meta, ensure_ascii=False, indent=2)),
        ImageContent(type="image", data=base64.b64encode(body).decode("ascii"), mimeType=mime),
    ]

return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
```

The dict path is unchanged from today; the tuple path is the new
inline-image branch. **Only** `get_screenshot` ever produces the
tuple — but the dispatcher does not need to know that; the shape
discriminates.

### 6.2 `src/arquivo_pt_mcp/models.py`

Add at the bottom (mirroring `GetSnapshotParams` style):

```python
class GetScreenshotParams(BaseModel):
    url: str
    timestamp: str | None = None
    inline: bool = False
    max_bytes: int = Field(default=500_000, ge=1_000, le=5_000_000)
```

No custom validators needed — `_normalize_date` runs inside the
handler already.

---

## 7. Tests

All new tests use the existing `mock_*` fixtures in
`tests/conftest.py` where applicable; for screenshot-specific
behaviour add a small dedicated fixture.

### 7.1 `tests/test_screenshot.py` (new)

#### 7.1.1 URL construction (pure)

Pin the byte-for-byte format against the API-reference example:

```python
def test_screenshot_url_matches_docs_example():
    from arquivo_pt_mcp import _screenshot_url
    inner, outer = _screenshot_url("http://example.pt/page.html", "20050315120000")
    assert inner == "https://arquivo.pt/noFrame/replay/20050315120000/http://example.pt/page.html"
    assert outer == (
        "https://arquivo.pt/screenshot?url="
        "https%3A%2F%2Farquivo.pt%2FnoFrame%2Freplay%2F20050315120000"
        "%2Fhttp%3A%2F%2Fexample.pt%2Fpage.html"
    )
```

#### 7.1.2 URL-mode happy path

Mock `get_snapshot` (or the underlying CDX call) to resolve to a
known timestamp; call `get_screenshot(url, ts)`; assert `inline` is
absent and `screenshot_url` is the expected outer URL.

#### 7.1.3 URL-mode "not found"

Mock CDX → empty captures; call `get_screenshot(url)` (no timestamp);
assert returned dict is `{"url": ..., "found": False,
"message": "no captures found"}` and **no HTTP call** to
`/screenshot` was made.

#### 7.1.4 Inline-mode happy path

Mock the screenshot endpoint to return a tiny valid PNG (use the
8-byte signature `\x89PNG\r\n\x1a\n` plus a minimal IHDR — or just a
fixed ~50-byte blob; tests do not need to render). Assert the tool
returns a 3-tuple, the dict has `inline=True` and matching
`byte_size`, and the bytes round-trip identically.

#### 7.1.5 Inline-mode size cap

Use a 1 KB body and `max_bytes=500`. Assert returned shape is the
plain dict (not the tuple), `truncated=True`, `byte_size=1024`, and a
`note` mentions the cap.

#### 7.1.6 Inline-mode 404

Mock the screenshot endpoint to return 404. Assert the dict is
returned (not the tuple), `screenshot_url` and `no_frame_url` are
still populated, and `warning` mentions the 404.

#### 7.1.7 Inline-mode wrong content-type

Mock the screenshot endpoint to return 200 with
`Content-Type: text/html` and an HTML body. Assert the dict is
returned (not the tuple) and `warning` mentions the unexpected
content-type. **Crucial test** — guards against shipping garbage
bytes to the model as a "PNG".

#### 7.1.8 Cache hit (inline)

Call inline twice with identical args; assert the second call does
**not** hit the network (mock the client and assert call count == 1).

### 7.2 `tests/test_models.py` (extend)

- `GetScreenshotParams(url="x")` succeeds with defaults.
- `GetScreenshotParams(url="x", max_bytes=999)` raises
  `ValidationError` (below `ge=1_000`).
- `GetScreenshotParams(url="x", max_bytes=5_000_001)` raises
  `ValidationError` (above `le=5_000_000`).

### 7.3 `tests/test_cache.py` (extend)

Add: populate `SCREENSHOT_CACHE` with one entry, call `clear_cache()`,
assert empty.

### 7.4 `tests/test_stdio_smoke.py` (extend)

Inside `test_stdio_tool_schemas_have_required_fields`, add:

```python
assert by_name["get_screenshot"].inputSchema["required"] == ["url"]
```

### 7.5 `tests/integration_fixtures.py` (extend)

Add `"get_screenshot"` to the `EXPECTED_TOOL_NAMES` set. The existing
`test_stdio_lists_tools` (`tests/test_stdio_smoke.py:31`) and
`test_http_smoke.py` (if shipped) will then enforce membership
end-to-end.

### 7.6 `tests/test_integration.py` (extend, integration-marked)

```python
@pytest.mark.integration
async def test_get_screenshot_url_mode_live():
    from arquivo_pt_mcp import get_screenshot
    result = await get_screenshot("publico.pt", timestamp="20100601000000")
    assert result["found"] is True
    assert result["screenshot_url"].startswith("https://arquivo.pt/screenshot?url=")
    assert "noFrame%2Freplay" in result["screenshot_url"]
```

Optional second test (kept short to avoid hammering arquivo.pt):

```python
@pytest.mark.integration
async def test_get_screenshot_inline_live_smoke():
    from arquivo_pt_mcp import get_screenshot
    result = await get_screenshot("publico.pt", timestamp="20100601000000",
                                   inline=True, max_bytes=2_000_000)
    # Either we got the image, or arquivo.pt didn't render that capture:
    assert isinstance(result, (dict, tuple))
    if isinstance(result, tuple):
        meta, body, mime = result
        assert mime == "image/png"
        assert body[:8] == b"\x89PNG\r\n\x1a\n"
        assert meta["inline"] is True
```

The "either-or" branch tolerates the realistic 404 outcome documented
in §4.3 — flaky integration tests are worse than tests that admit
both legitimate outcomes.

---

## 8. README & ROADMAP

### 8.1 `README.md` (both 🇵🇹 and 🇬🇧)

Add a row to the tools table:

| 🇵🇹 | 🇬🇧 |
|---|---|
| **`get_screenshot`** — Obtém o URL de uma captura PNG renderizada de uma página arquivada (opcionalmente com os bytes inline) | **`get_screenshot`** — Get the PNG render URL of an archived page (optionally embed the bytes inline) |

Add an example prompt to the "Exemplos de utilização" / "Usage
examples" sections:

> *"Mostra-me uma screenshot da homepage do Público em 1 de janeiro de 2010."*
> *"Show me a screenshot of Público's homepage on Jan 1, 2010."*

### 8.2 `ROADMAP.md`

Tick the second item under Milestone 3:

```diff
- - [ ] **Screenshot tool** — new `get_screenshot` tool …
+ - [x] **Screenshot tool** — new `get_screenshot` tool …
```

---

## 9. Verification checklist

Run inside the DevContainer
(`docker exec -w /workspaces/Python-space/arquivo-pt-mcp interesting_saha …`):

```bash
# 1. Lint clean
ruff check src/ tests/
ruff format --check src/ tests/

# 2. Unit tests pass (including the new ones)
pytest tests/ -v --tb=short

# 3. Tool count is now six everywhere
pytest tests/test_screenshot.py tests/test_models.py tests/test_cache.py -v

# 4. End-to-end smoke (stdio); EXPECTED_TOOL_NAMES enforces the new tool
RUN_INTEGRATION=1 pytest tests/test_stdio_smoke.py -v

# 5. Live API check (will skip without RUN_INTEGRATION=1)
RUN_INTEGRATION=1 pytest tests/test_integration.py -v -k screenshot

# 6. Manual sanity: build a screenshot URL with the helper and curl it
python -c "
from arquivo_pt_mcp import _screenshot_url
_, u = _screenshot_url('publico.pt', '20100601000000')
print(u)
" | xargs -I{} curl -s -o /tmp/shot.png -w '%{http_code} %{content_type} %{size_download}\n' {}
file /tmp/shot.png
```

The final `file` should report `PNG image data` (or, less commonly,
report a 404 — both are documented outcomes per §4.3).

---

## 10. Out of scope / follow-ups

1. **Fix the latent `no_frame_url` bug in `get_snapshot`** (see §2).
   Replace the ad-hoc `.replace(f"{WAYBACK}/", f"{WAYBACK}/noFrame/")`
   at `__init__.py:351-353` with the corrected pattern
   `f"{ARQUIVO_BASE}/noFrame/replay/{ts}/{url}"`. Audit `extract_text`
   for downstream impact (it uses `no_frame_url` at `__init__.py:389`)
   and update any test fixtures that hard-code the broken URL. Worth
   its own short plan because it affects two tools and the test
   matrix.
2. **Resource exposure.** Once the screenshot tool is solid, consider
   exposing the noFrame replay URL as an MCP `Resource` so clients
   can subscribe to it without invoking the tool. Out of scope for
   Milestone 3.
3. **Image caching to disk.** The in-memory `SCREENSHOT_CACHE` is
   bounded to ~100 MB worst case. For long-running HTTP deployments,
   spilling to disk (or to Redis when multi-replica) would let us
   keep more captures hot. Pair with the Streamable HTTP follow-up.
4. **Thumbnails.** Arquivo.pt does not document a thumbnailing
   endpoint, but a downscaling helper (Pillow) would let the tool
   embed inline screenshots cheaply. Adds a heavy optional
   dependency — defer until there is a real use case.
5. **WebP / quality knobs.** None advertised by the upstream API; if
   they appear later, add a `format` arg.

---

## 11. Pitfalls the executor must respect

1. **Use `quote(inner, safe='')`, not bare `quote(inner)`.** The
   default `safe='/'` leaves `/` un-encoded and the result will
   ambiguously parse on the server side. The reference example at
   `docs/api-reference.md:72` percent-encodes `/` and `:` — your
   helper must too. Pinned by the test in §7.1.1.
2. **Do not trust `get_snapshot()['no_frame_url']`.** It is buggy
   today (see §2). The new tool must call `_screenshot_url(url, ts)`
   to compute its own. Fixing the upstream bug is §10 follow-up.
3. **Do not base64-encode bytes inside the handler.** Keep raw
   `bytes` in the return tuple; the dispatcher in
   `call_tool` (`__init__.py:586`) does the base64 once, in one
   place, near the `ImageContent` construction. This keeps the
   handler easily testable without a base64 round-trip.
4. **Return the same `dict` shape on every error path.** Tests in
   §7.1.3, §7.1.5, §7.1.6, and §7.1.7 all assert "dict, not tuple".
   Easy to break by accidentally returning the tuple with empty
   bytes — don't.
5. **Validate `Content-Type` before trusting the body.** A
   misconfigured proxy in front of arquivo.pt could return an HTML
   error page with status 200. Treat anything other than `image/png`
   as a soft failure (warning + URL-mode response). Tested in §7.1.7.
6. **`max_bytes` check must consider `Content-Length` *and* the
   actual body length.** A hostile or buggy server can send more bytes
   than it promised. The reference snippet in §6.1.5 only checks the
   final `len(body)`, which is the safe choice — `httpx` does buffer
   the whole body before returning, so we will not stream junk into
   memory beyond `DEFAULT_TIMEOUT` worth of bandwidth. If anyone
   later switches to streamed reads, both checks become necessary.
7. **`SCREENSHOT_CACHE` only caches the inline path.** The URL-only
   path is pure string construction; caching it would just waste
   memory and tests would have to assert a no-op cache hit. Keep the
   cache narrow.

---

*Plan author note for the executor: work §6.1 → §6.2 → §7.1 →
§7.{2..6} → §8 in that order. Run `ruff check` and the relevant
test subset after each numbered subsection. Keep the `__init__.py`
changes in one commit and the test additions in a second so the
diff is reviewable.*
