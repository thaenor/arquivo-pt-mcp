# Implementation Plan — `get_metadata` Tool

**current status: ready to develop**

**Scope.** ROADMAP.md → Milestone 3 → third checkbox only
(*"Metadata tool — new `get_metadata` tool querying
`/textsearch?metadata={url}/{timestamp}` to return HTTP status code,
MIME type, content length, and digest for a specific capture"*).
The other Milestone 3 items (`diff_snapshots`, bulk CDX export,
proximity-search docs) are **out of scope**. The screenshot tool is
covered separately in `get-screenshot-tool.md`.

**Source of truth for the endpoint:**
`arquivo-pt-mcp/docs/api-reference.md` §4 (line 291), §1.2 response
schema (lines 53–87), and §1.3 per-item fields (lines 89–111). The
live `linkToMetadata` example at line 76 is the canonical URL format
this tool must reproduce byte-for-byte.

---

## 1. Goal

Add a seventh MCP tool — `get_metadata` — that, given a URL and an
optional timestamp, returns the **per-capture metadata** Arquivo.pt
holds for that specific snapshot. The response surfaces information
that today is either dropped by `search()` (the `linkToMetadata`
field) or only obtainable indirectly (HEAD-ing the replay URL):

- HTTP `statusCode` of the original capture (200, 301, 404, …)
- `mimeType` (e.g. `text/html`, `application/pdf`)
- `contentLength` in bytes
- `digest` (MD5 hash of the captured payload)
- `encoding` (charset, if known)
- `collection` ID (which crawl this came from)
- `fileName` and byte `offset` inside the WARC/ARC (the canonical
  archive coordinates of the capture — only populated in metadata
  mode)
- The full link family for that capture (`archive_url`,
  `no_frame_url`, `original_file_url`, `screenshot_url`,
  `extracted_text_url`, `metadata_url`)
- `title` and `captured_at_iso`

The interface mirrors `get_snapshot` and `get_screenshot` so a model
that already knows how to ask for snapshots can ask for metadata with
no extra learning.

**Explicitly not returned** (per ROADMAP scope-limit and confirmed
against `docs/api-reference.md`):

- Redirect chain — Arquivo.pt does not expose post-capture redirect
  resolution.
- Language — no `language` field is documented in the TextSearch
  response.

---

## 2. Current state (May 2026)

- Five tools registered in `src/arquivo_pt_mcp/__init__.py:425–553`.
  None of them surface per-capture metadata.
- `search()` (`__init__.py:174–220`) **already calls** the same
  `/textsearch` endpoint this tool will use, but in *full-text* mode
  (passing `q=...`). The response shape is identical between the two
  modes — the wrapper, the `response_items` array, and the per-item
  fields are the same. `get_metadata` reuses the wire format the rest
  of the code already understands.
- Crucially, `search()` **drops `linkToMetadata`** at the field-mapping
  step (`__init__.py:198–212`): only `title`, `original_url`,
  `archive_url`, `screenshot_url`, `no_frame_url`,
  `extracted_text_url`, `captured`, `snippet`, `mime` are surfaced.
  `linkToMetadata`, `statusCode`, `contentLength`, `digest`, `encoding`,
  `collection`, `fileName`, `offset` are **all discarded today**. This
  tool is the first place those land.
- `get_snapshot()` (`__init__.py:319–358`) is the natural backend for
  resolving `(url, timestamp?) → resolved_ts`. Reuse, do not
  reimplement.
- `_fetch_with_retry` (`__init__.py:152`) already handles
  rate-limit/transient failures uniformly — the `/textsearch?metadata=…`
  path inherits that for free.
- `from urllib.parse import quote` (`__init__.py:29`, currently
  `noqa: F401`) will be live in this tool. If
  `get-screenshot-tool.md` lands first, the import is already
  un-suppressed and this plan only needs to *use* it.
- `call_tool` dispatcher (`__init__.py:565`) returns
  `list[TextContent]`; this tool returns a plain dict and needs no
  dispatcher change. (Contrast with `get_screenshot` inline mode,
  which forces the `ImageContent` widening.)
- Module-level caches (`CDX_CACHE`, `SEARCH_CACHE`, `SNAPSHOT_CACHE`
  at `__init__.py:61–63`) are the existing pattern. We add a fourth
  small one (`METADATA_CACHE`).
- Tests use real-shape fixtures in `tests/conftest.py`. We add
  `mock_metadata_response` modeled on `mock_search_response` — the
  wire format is the same wrapper.

---

## 3. The Arquivo.pt metadata endpoint

From `docs/api-reference.md:291`:

```
GET https://arquivo.pt/textsearch?metadata={percent-encoded url}/{timestamp}
```

The query value is the **single string** `{url}/{timestamp}`,
percent-encoded as a whole. Example from the live `linkToMetadata`
field (`api-reference.md:76`):

```
https://arquivo.pt/textsearch?metadata=http%3A%2F%2Fexample.pt%2Fpage.html%2F20050315120000
```

### URL construction reference

Given `url = "http://example.pt/page.html"` and
`ts = "20050315120000"`:

```python
metadata_arg = quote(f"{url}/{ts}", safe="")
metadata_url = f"{TEXTSEARCH}?metadata={metadata_arg}"
```

Note: `safe=""` is critical (same rationale as `get_screenshot`) so
that `:`, `/`, and any URL-unsafe characters in the original URL get
percent-encoded. A unit test in §7.1 pins this byte-for-byte.

### Response shape (verified against `docs/api-reference.md` §1.2)

The endpoint returns the same wrapper as full-text search. In
metadata mode, `response_items` should contain **exactly one entry**
(the specific capture). Empty `response_items` means "no such
capture" — treat as `found=False` (see §4.3).

The metadata-mode item is the only place where `fileName` and the
per-item `offset` are populated (`api-reference.md:87`,
`api-reference.md:110-111`).

### Rate limit

Same as TextSearch: 250 req / 180 s per IP
(`api-reference.md:13`). `_fetch_with_retry` already handles 429.

---

## 4. Tool design

### 4.1 Name and inputs

```
get_metadata(
    url: str,                     # required
    timestamp: str | None = None, # optional; latest if omitted
) -> dict
```

| Field | Validation | Notes |
|---|---|---|
| `url` | non-empty string | Same shape as `get_snapshot.url`. Trailing `/` is **not** stripped — see §11 pitfalls. |
| `timestamp` | None, `YYYY`, `YYYY-MM-DD`, or `YYYYMMDDHHMMSS` | Reuse `_normalize_date()` (`__init__.py:84`). |

### 4.2 Output

A single `TextContent` carrying JSON:

```json
{
  "url": "<original url, as supplied>",
  "timestamp": "<resolved 14-digit ts>",
  "found": true,
  "title": "Eleições 2005 - Resultados",
  "status_code": "200",
  "mime_type": "text/html",
  "content_length": 12345,
  "digest": "MD5_HASH_HEX",
  "encoding": "UTF-8",
  "collection": "AWP4",
  "warc_filename": "IAH-20090523070559-03202-awp01.fccn.pt",
  "warc_offset": 16800267,
  "captured_at_iso": "2005-03-15T12:00:00",
  "archive_url":         "https://arquivo.pt/wayback/<ts>/<url>",
  "no_frame_url":        "https://arquivo.pt/noFrame/replay/<ts>/<url>",
  "original_file_url":   "https://arquivo.pt/noFrame/replay/<ts>id_/<url>",
  "screenshot_url":      "https://arquivo.pt/screenshot?url=...",
  "extracted_text_url":  "https://arquivo.pt/textextracted?m=...",
  "metadata_url":        "https://arquivo.pt/textsearch?metadata=..."
}
```

### 4.3 Field-mapping table

Authoritative source-to-output map. The executor must follow this
table verbatim — no additions, no renames.

| Output key | Upstream key | Type coercion | Notes |
|---|---|---|---|
| `url` | (input) | str | Echo the user's input. Do not normalize. |
| `timestamp` | `tstamp` | str (14 digits) | Falls back to the resolved timestamp from `get_snapshot` if upstream omits it. |
| `found` | n/a | bool | `true` when upstream returns ≥1 item. |
| `title` | `title` | str \| None | Drop if absent. |
| `status_code` | `statusCode` | str \| None | Keep as string — upstream emits `"200"`, not `200`. Avoids accidentally losing leading zeros in non-HTTP cases. |
| `mime_type` | `mimeType` | str \| None | |
| `content_length` | `contentLength` | int \| None | Coerce: `int(value)` with try/except → None. |
| `digest` | `digest` | str \| None | MD5 hex per `api-reference.md:99`. |
| `encoding` | `encoding` | str \| None | May be empty string upstream — coerce empty → None. |
| `collection` | `collection` | str \| None | Same empty-→-None treatment. |
| `warc_filename` | `fileName` | str \| None | Only populated in metadata mode. |
| `warc_offset` | `offset` | int \| None | Coerce to int; upstream sometimes emits a string. |
| `captured_at_iso` | derived from `tstamp` | str \| None | Reuse `_ts_to_iso()` (`__init__.py:94`). |
| `archive_url` | `linkToArchive` | str | Pass through verbatim. |
| `no_frame_url` | `linkToNoFrame` | str | **Pass through from upstream** — do *not* construct it, and do **not** trust `get_snapshot()['no_frame_url']` (which is buggy, see `get-screenshot-tool.md` §2). |
| `original_file_url` | `linkToOriginalFile` | str | Pass through. |
| `screenshot_url` | `linkToScreenshot` | str | Pass through. |
| `extracted_text_url` | `linkToExtractedText` | str | Pass through. |
| `metadata_url` | `linkToMetadata` | str | Pass through. Acts as the canonical "give me this again" URL. |

Snake-case is the project convention (every other tool's output uses
it). Status code is intentionally a *string* because that's what the
upstream emits and downstream code may be string-comparing it.

### 4.4 Error / not-found handling

| Condition | Behaviour |
|---|---|
| `get_snapshot` returns `found=False` | Return `{"url": url, "found": false, "message": "no captures found"}` verbatim, no `/textsearch?metadata=` call. |
| Upstream returns 200 but `response_items` is empty | Return `{"url": url, "timestamp": <resolved ts>, "found": false, "message": "no metadata for this capture"}`. Distinct message — distinguishes "URL never archived" from "URL archived but metadata-mode returned nothing", which can happen for very old captures whose WARC index is incomplete. |
| Upstream returns 429 / 5xx | Already retried by `_fetch_with_retry`; eventually surfaces via the dispatcher's existing exception handlers (`__init__.py:588–605`). No new error path. |
| Upstream returns >1 item (shouldn't happen in metadata mode but is technically possible) | Use the **first** item. Add `"warning": "metadata mode returned <N> items, used first"` to the output. Tested in §7.1.6. |

### 4.5 Caching

```python
METADATA_CACHE = TTLCache(maxsize=1000, ttl=60 * 60)
```

- `maxsize=1000` matches the other text-payload caches; entries are
  small (~1 KB JSON).
- 1 h TTL matches `SNAPSHOT_CACHE` — metadata for an immutable
  archived capture does not change, so TTL is purely a memory-pressure
  release valve.
- Cache key: `(url, ts)` *after* timestamp resolution. Caching on
  the user-supplied (possibly None) timestamp would orphan entries
  every time the latest capture rolls over.
- Add `METADATA_CACHE.clear()` to the existing `clear_cache()`
  helper (`__init__.py:66`).

---

## 5. Files touched

| File | Change |
|------|--------|
| `src/arquivo_pt_mcp/__init__.py` | Add `METADATA_CACHE`, `_metadata_url()` helper, `get_metadata()` async function, `Tool` entry in `list_tools`, register in `handlers` and `PARAM_MODELS`. Drop `# noqa: F401` from the `quote` import if not already dropped by `get-screenshot-tool.md`. |
| `src/arquivo_pt_mcp/models.py` | Add `GetMetadataParams`. |
| `tests/test_metadata.py` | **New.** Unit tests for URL construction, happy-path mapping, type coercion, not-found, empty-items, multi-item-warning, caching. |
| `tests/conftest.py` | Add `mock_metadata_response` fixture (mirrors `mock_search_response` but with one fully-populated metadata-mode item). |
| `tests/test_models.py` | Add validation cases for `GetMetadataParams`. |
| `tests/test_cache.py` | Add a case proving `clear_cache` empties `METADATA_CACHE`. |
| `tests/test_integration.py` | Add an `integration`-marked test against a known capture. |
| `tests/integration_fixtures.py` | Add `"get_metadata"` to `EXPECTED_TOOL_NAMES`. |
| `tests/test_stdio_smoke.py` | Add `assert by_name["get_metadata"].inputSchema["required"] == ["url"]`. |
| `README.md` | Document the new tool in both 🇵🇹 and 🇬🇧 tables. |
| `ROADMAP.md` | Tick the third checkbox under Milestone 3. |

No changes to `_fetch_with_retry`, `_strip_html`, `_normalize_date`,
`_ts_to_iso`, the existing five handlers, the existing caches'
configuration, the HTTP transport, or the `call_tool` dispatcher
shape (it already handles dict-returning tools).

**Coordination with `get-screenshot-tool.md`:** if both plans land in
the same release, sequence them with `get_metadata` second so the
`call_tool` dispatcher and the `quote` import un-suppression are
already in place. Otherwise both plans contain the same one-line
edits; do them once, with `git diff` confirming no double-application.

---

## 6. Per-file changes

### 6.1 `src/arquivo_pt_mcp/__init__.py`

#### 6.1.1 Imports (top of file)

If not already done by `get-screenshot-tool.md`: drop the
`# noqa: F401 — kept for future URL-encoding needs` comment from the
`from urllib.parse import quote` line (`__init__.py:29`).

No other imports needed — `httpx`, `TTLCache`, `TextContent`, `Tool`,
and `ValidationError` are already imported.

#### 6.1.2 New cache

After the existing cache definitions (`__init__.py:61–63`):

```python
METADATA_CACHE = TTLCache(maxsize=1000, ttl=60 * 60)
```

#### 6.1.3 Update `clear_cache` (around `__init__.py:66`)

Add `METADATA_CACHE.clear()` to the body. Order: `CDX_CACHE`,
`SEARCH_CACHE`, `SNAPSHOT_CACHE`, `METADATA_CACHE` (insertion
chronology — the executor must not rearrange the others, only append).

#### 6.1.4 New helper `_metadata_url(url, ts)`

Place after `_parse_cdx_jsonl` (`__init__.py:149`), before
`_fetch_with_retry` (`__init__.py:152`). If `get-screenshot-tool.md`
already added `_screenshot_url` here, place this helper immediately
below it — keep helpers grouped.

```python
def _metadata_url(url: str, ts: str) -> str:
    """Return the canonical /textsearch?metadata=… URL for a (url, timestamp).

    Format verified against the live linkToMetadata field documented at
    docs/api-reference.md:76.
    """
    return f"{TEXTSEARCH}?metadata={quote(f'{url}/{ts}', safe='')}"
```

#### 6.1.5 New `get_metadata()` handler

Place immediately after `get_snapshot` (`__init__.py:358`), before
`extract_text` (or before `get_screenshot` if that lands first —
preserve alphabetical-ish ordering of the `get_*` family). Skeleton:

```python
async def get_metadata(
    url: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Per-capture metadata for a specific snapshot.

    Returns HTTP status code, MIME type, content length, MD5 digest,
    WARC location, and the full link family. Redirect chain and
    language are not exposed by the Arquivo.pt API.
    """
    snap = await get_snapshot(url, timestamp)
    if not snap.get("found"):
        return snap
    ts = snap["timestamp"]

    cache_key = (url, ts)
    if cache_key in METADATA_CACHE:
        return METADATA_CACHE[cache_key]

    metadata_url = _metadata_url(url, ts)
    async with _client() as client:
        resp = await _fetch_with_retry(client, metadata_url)
        data = resp.json()

    items = data.get("response_items") or []
    if not items:
        result = {
            "url": url,
            "timestamp": ts,
            "found": False,
            "message": "no metadata for this capture",
        }
        METADATA_CACHE[cache_key] = result
        return result

    item = items[0]

    def _int_or_none(v: Any) -> int | None:
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def _empty_to_none(v: Any) -> Any:
        return v if v not in (None, "") else None

    result: dict[str, Any] = {
        "url": url,
        "timestamp": item.get("tstamp") or ts,
        "found": True,
        "title": _empty_to_none(item.get("title")),
        "status_code": _empty_to_none(item.get("statusCode")),
        "mime_type": _empty_to_none(item.get("mimeType")),
        "content_length": _int_or_none(item.get("contentLength")),
        "digest": _empty_to_none(item.get("digest")),
        "encoding": _empty_to_none(item.get("encoding")),
        "collection": _empty_to_none(item.get("collection")),
        "warc_filename": _empty_to_none(item.get("fileName")),
        "warc_offset": _int_or_none(item.get("offset")),
        "captured_at_iso": _ts_to_iso(item.get("tstamp") or ts),
        "archive_url": item.get("linkToArchive"),
        "no_frame_url": item.get("linkToNoFrame"),
        "original_file_url": item.get("linkToOriginalFile"),
        "screenshot_url": item.get("linkToScreenshot"),
        "extracted_text_url": item.get("linkToExtractedText"),
        "metadata_url": item.get("linkToMetadata") or metadata_url,
    }

    if len(items) > 1:
        result["warning"] = (
            f"metadata mode returned {len(items)} items, used first"
        )

    METADATA_CACHE[cache_key] = result
    return result
```

**Notes for the executor:**

- The two `_int_or_none` / `_empty_to_none` closures are deliberately
  local (not module-level helpers) because they are only used here and
  inlining them keeps `__init__.py` flat. If a future tool needs the
  same coercion, promote them — but do it in that future plan, not
  this one (don't pre-abstract).
- The `metadata_url` falls back to our locally-constructed URL only
  if upstream omits `linkToMetadata`. In practice it will always be
  present; the fallback is defensive.
- Do **not** strip a trailing `/` from `url` before passing to
  `_metadata_url`. See §11 pitfall #3.

#### 6.1.6 Register in `list_tools` (`__init__.py:425`)

Append after the previous tool entry (after `extract_text`, or after
`get_screenshot` if that landed first):

```python
Tool(
    name="get_metadata",
    description=(
        "Get per-capture metadata for a specific archived snapshot — "
        "HTTP status code, MIME type, content length, MD5 digest, WARC "
        "location, and the link family for that capture. Omit timestamp "
        "for the latest. Redirect chain and language are not exposed by "
        "the Arquivo.pt API."
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
```

#### 6.1.7 Register in `PARAM_MODELS` (`__init__.py:556`)

Add `"get_metadata": GetMetadataParams,`.

#### 6.1.8 Register in `handlers` map (`__init__.py:567`)

Add `"get_metadata": get_metadata,`.

### 6.2 `src/arquivo_pt_mcp/models.py`

Add at the bottom (mirroring `GetSnapshotParams`):

```python
class GetMetadataParams(BaseModel):
    url: str
    timestamp: str | None = None
```

No custom validators — `_normalize_date` runs inside `get_snapshot`,
which `get_metadata` delegates to.

---

## 7. Tests

### 7.1 `tests/test_metadata.py` (new)

Use `pytest-asyncio`'s auto mode (already configured in
`pyproject.toml:44`). Mock the HTTP layer using the same
monkeypatching pattern other test files use (inspect
`tests/test_search.py` for the canonical shape — it already mocks
`httpx.AsyncClient.get`).

#### 7.1.1 URL construction (pure)

Pin the byte-for-byte format against the API-reference example at
line 76:

```python
def test_metadata_url_matches_docs_example():
    from arquivo_pt_mcp import _metadata_url
    assert _metadata_url("http://example.pt/page.html", "20050315120000") == (
        "https://arquivo.pt/textsearch?metadata="
        "http%3A%2F%2Fexample.pt%2Fpage.html%2F20050315120000"
    )
```

#### 7.1.2 Happy-path field mapping

Mock the response with `mock_metadata_response` (see §7.2). Call
`get_metadata("http://publico.pt/", "20050315120000")`. Assert
**every** key from §4.3 is present and matches:

```python
async def test_get_metadata_maps_all_fields(mock_metadata_response, monkeypatch):
    # ... patch _fetch_with_retry to return the mock ...
    result = await get_metadata("http://publico.pt/", "20050315120000")
    assert result["found"] is True
    assert result["status_code"] == "200"
    assert result["mime_type"] == "text/html"
    assert result["content_length"] == 12345          # int, not "12345"
    assert result["digest"] == "MD5_HASH_HEX"
    assert result["encoding"] == "UTF-8"
    assert result["collection"] == "AWP4"
    assert result["warc_filename"] == "IAH-...arc.gz"
    assert result["warc_offset"] == 16800267          # int
    assert result["captured_at_iso"] == "2005-03-15T12:00:00"
    assert result["archive_url"].startswith("https://arquivo.pt/wayback/")
    assert result["no_frame_url"].startswith("https://arquivo.pt/noFrame/replay/")
    assert result["metadata_url"].startswith("https://arquivo.pt/textsearch?metadata=")
```

#### 7.1.3 Type coercion edges

Variants of the mock fixture, asserted one per test:

- `contentLength = ""` → `content_length is None`.
- `contentLength = "not-a-number"` → `content_length is None`.
- `offset = "16800267"` (string) → `warc_offset == 16800267` (int).
- `offset = None` → `warc_offset is None`.
- `encoding = ""` → `encoding is None` (not `""`).
- `collection = ""` → `collection is None`.

#### 7.1.4 Not-found via `get_snapshot`

Mock CDX → empty captures; call `get_metadata("never-archived.example.com")`.
Assert `{"url": ..., "found": False, "message": "no captures found"}`
and **no** call to `/textsearch?metadata=`.

#### 7.1.5 Empty `response_items`

Mock the `/textsearch?metadata=` response to return
`{"response_items": []}`. Assert
`{"url": ..., "timestamp": ..., "found": False, "message": "no metadata for this capture"}`.
The "timestamp" key must be present — distinguishes this case from
§7.1.4.

#### 7.1.6 Multi-item warning

Mock the response with two items. Assert the first item is mapped,
and `result["warning"] == "metadata mode returned 2 items, used first"`.

#### 7.1.7 Cache hit

Call `get_metadata(url, ts)` twice with identical args. Assert the
second call does **not** invoke `_fetch_with_retry` (mock it with a
counter).

#### 7.1.8 Cache key uses *resolved* timestamp

Call `get_metadata("http://publico.pt/")` (no timestamp), then
`get_metadata("http://publico.pt/", <the resolved ts>)`. Assert the
second call is a cache hit. Guards against accidentally caching
under `(url, None)` — see §11 pitfall #4.

### 7.2 `tests/conftest.py` (extend)

Add a fixture mirroring `mock_search_response` but populated with
metadata-mode-realistic values. The body should contain exactly one
item with **all** of `statusCode`, `contentLength`, `digest`,
`encoding`, `collection`, `fileName`, `offset`, `linkToMetadata`,
`linkToOriginalFile`, and the rest of the link family — i.e. the same
shape shown in `docs/api-reference.md:62–82`:

```python
@pytest.fixture
def mock_metadata_response():
    """Sample /textsearch?metadata=… response. One fully-populated item.

    Shape mirrors the live API verified May 2026 — see
    docs/api-reference.md §1.2.
    """
    return {
        "serviceName": "Arquivo.pt - Search Service v1.1",
        "linkToService": "https://arquivo.pt/textsearch",
        "request_parameters": {"metadata": "http://publico.pt//20050315120000"},
        "response_items": [
            {
                "title": "Eleições 2005 - Resultados",
                "originalURL": "http://publico.pt/",
                "tstamp": "20050315120000",
                "date": "1110888000",
                "contentLength": 12345,
                "digest": "MD5_HASH_HEX",
                "mimeType": "text/html",
                "encoding": "UTF-8",
                "collection": "AWP4",
                "statusCode": "200",
                "fileName": "IAH-20090523070559-03202-awp01.fccn.pt",
                "offset": 16800267,
                "linkToArchive": "https://arquivo.pt/wayback/20050315120000/http://publico.pt/",
                "linkToNoFrame": "https://arquivo.pt/noFrame/replay/20050315120000/http://publico.pt/",
                "linkToOriginalFile": "https://arquivo.pt/noFrame/replay/20050315120000id_/http://publico.pt/",
                "linkToScreenshot": "https://arquivo.pt/screenshot?url=https%3A%2F%2Farquivo.pt%2FnoFrame%2Freplay%2F20050315120000%2Fhttp%3A%2F%2Fpublico.pt%2F",
                "linkToExtractedText": "https://arquivo.pt/textextracted?m=http%3A%2F%2Fpublico.pt%2F%2F20050315120000",
                "linkToMetadata": "https://arquivo.pt/textsearch?metadata=http%3A%2F%2Fpublico.pt%2F%2F20050315120000",
            }
        ],
    }
```

### 7.3 `tests/test_models.py` (extend)

- `GetMetadataParams(url="x")` succeeds; `timestamp is None`.
- `GetMetadataParams(url="x", timestamp="20050315120000")` succeeds.
- `GetMetadataParams()` raises `ValidationError` (missing required
  `url`).

### 7.4 `tests/test_cache.py` (extend)

Populate `METADATA_CACHE` with one entry, call `clear_cache()`,
assert empty.

### 7.5 `tests/test_stdio_smoke.py` (extend)

Inside `test_stdio_tool_schemas_have_required_fields`, add:

```python
assert by_name["get_metadata"].inputSchema["required"] == ["url"]
```

### 7.6 `tests/integration_fixtures.py` (extend)

Add `"get_metadata"` to `EXPECTED_TOOL_NAMES`. The `test_stdio_lists_tools`
integration test (and the planned HTTP smoke test) will then enforce
membership end-to-end.

### 7.7 `tests/test_integration.py` (extend, integration-marked)

```python
@pytest.mark.integration
async def test_get_metadata_live():
    from arquivo_pt_mcp import get_metadata
    result = await get_metadata("publico.pt", timestamp="20100601000000")
    assert result["found"] is True
    assert result["status_code"] in ("200", "301", "302")  # tolerant
    assert result["mime_type"]                              # non-empty
    assert isinstance(result["content_length"], int)
    assert result["metadata_url"].startswith(
        "https://arquivo.pt/textsearch?metadata="
    )
```

The status-code assertion is intentionally tolerant — `publico.pt`
captures across the years include redirect captures. Pinning to `200`
would create a flake when arquivo.pt promotes a different capture as
the latest.

---

## 8. README & ROADMAP

### 8.1 `README.md` (both 🇵🇹 and 🇬🇧)

Add a row to the tools table:

| 🇵🇹 | 🇬🇧 |
|---|---|
| **`get_metadata`** — Obtém metadados de uma captura (código HTTP, MIME, tamanho, MD5, ficheiro WARC) | **`get_metadata`** — Get per-capture metadata (HTTP status, MIME type, length, MD5 digest, WARC location) |

Add an example prompt to the "Exemplos de utilização" / "Usage
examples" section:

> *"Que tipo MIME e código HTTP tinha a homepage do Público em 1 de janeiro de 2010?"*
> *"What MIME type and HTTP status did Público's homepage have on Jan 1, 2010?"*

### 8.2 `ROADMAP.md`

Tick the third item under Milestone 3:

```diff
- - [ ] **Metadata tool** — new `get_metadata` tool …
+ - [x] **Metadata tool** — new `get_metadata` tool …
```

---

## 9. Verification checklist

Run inside the DevContainer
(`docker exec -w /workspaces/Python-space/arquivo-pt-mcp interesting_saha …`):

```bash
# 1. Lint clean
ruff check src/ tests/
ruff format --check src/ tests/

# 2. All unit tests pass (including the new ones)
pytest tests/ -v --tb=short

# 3. Targeted runs for the new code
pytest tests/test_metadata.py tests/test_models.py tests/test_cache.py -v

# 4. Stdio smoke; EXPECTED_TOOL_NAMES enforces the new tool
RUN_INTEGRATION=1 pytest tests/test_stdio_smoke.py -v

# 5. Live API check (will skip without RUN_INTEGRATION=1)
RUN_INTEGRATION=1 pytest tests/test_integration.py -v -k metadata

# 6. Manual sanity: build a metadata URL and curl it
python -c "
from arquivo_pt_mcp import _metadata_url
print(_metadata_url('publico.pt', '20100601000000'))
" | xargs -I{} curl -fsS -H 'Accept: application/json' {} \
  | python -m json.tool | head -40
```

The final `curl` should print a JSON object with `response_items`
containing one entry that has `statusCode`, `contentLength`, etc.

---

## 10. Out of scope / follow-ups

1. **Surface `linkToMetadata` from `search` results.** The current
   `search()` handler at `__init__.py:198–212` drops it. Once
   `get_metadata` exists, `search` should pass the field through as
   `metadata_url` so the model can chain `search` → `get_metadata`
   without rebuilding URLs. Trivial change but separable; ship as a
   one-line PR after this lands.
2. **Batch metadata.** Arquivo.pt does not document a batch metadata
   endpoint, but for "give me metadata for the last 50 captures of
   X" workflows we could add a `get_metadata_for_captures(url, limit)`
   that calls `list_versions` then loops `get_metadata`. Worth its
   own plan because of rate-limit concerns (250 / 180 s on TextSearch).
3. **Diff tool (`diff_snapshots`)**, the next ROADMAP item, will use
   `get_metadata` to compare digest/length/status across two captures
   cheaply — establishing this tool first makes that one shorter.
4. **Resource exposure.** The metadata payload is a natural fit for an
   MCP `Resource`, allowing clients to subscribe to "the latest
   metadata for URL X" without polling. Defer until at least one
   client asks for it.
5. **Fix the latent `no_frame_url` bug in `get_snapshot`.** Documented
   in `get-screenshot-tool.md` §10. `get_metadata` is unaffected
   because it pulls `no_frame_url` from the upstream response (where
   it is correct), but the fix is still owed.

---

## 11. Pitfalls the executor must respect

1. **Use `quote(f"{url}/{ts}", safe="")`, not bare `quote(...)`.**
   The default `safe="/"` leaves `/` un-encoded and the upstream
   parser will mis-segment `http://example.pt/path/20050315120000`
   into `http://example.pt/path/2005` + leftover. Pinned by the test
   in §7.1.1.
2. **The query value is `{url}/{ts}` as a *single* percent-encoded
   string**, not two separate parameters. Do not be tempted to write
   `?metadata={url}&timestamp={ts}` — the API does not accept that
   shape.
3. **Do not strip a trailing `/` from `url`.** Passing
   `http://publico.pt/` produces `http://publico.pt//20100601000000`
   (double slash). The upstream tolerates it (this exact shape
   appears in real `linkToMetadata` URLs) and stripping changes the
   user's intent silently. Echo the user's `url` byte-for-byte in
   the response.
4. **Cache key must use the *resolved* timestamp**, not the
   user-supplied one. If a user calls `get_metadata("x.pt")` (no
   timestamp), the resolved ts is whatever `get_snapshot` picked;
   caching under `(url, None)` would miss every subsequent call that
   names the same ts explicitly. Tested in §7.1.8.
5. **`statusCode` is a string upstream**, not an int. Keep it as a
   string in the output. Tests at §7.1.2 / §7.7 must use `"200"`
   (string), not `200`.
6. **`contentLength` and `offset` may arrive as int *or* string**
   depending on the capture vintage (older WARC indexes emit
   strings). Always coerce to `int | None`. Tested in §7.1.3.
7. **`response_items` may legitimately be empty** even for a URL
   that *does* have captures — metadata mode draws from a slightly
   different index than CDX, and very old captures sometimes show up
   in CDX (and thus pass the `get_snapshot` check) but yield empty
   metadata. Distinguish this case from "URL never archived" by the
   different `message` value (see §4.4).
8. **`linkToMetadata` from upstream is the canonical URL** — it may
   differ from our locally-constructed `_metadata_url(url, ts)` in
   how it normalizes the URL (e.g., adding/removing trailing slash,
   different percent-encoding of unreserved characters). When both
   are available, prefer the upstream value in the output (see the
   field-mapping table in §4.3). Our locally-constructed URL is the
   fallback and the cache-key salt.
9. **Do not store the raw upstream item in the cache.** Cache the
   *normalized* result dict only — otherwise downstream changes to
   the field-mapping table would silently serve stale-shape entries
   for an hour after deploy.

---

*Plan author note for the executor: work §6.1 → §6.2 → §7.2 → §7.1 →
§7.{3..7} → §8 in that order. The fixture (§7.2) goes before the
tests that consume it. Run `ruff check` and the relevant test
subset after each numbered subsection. Keep the `__init__.py` +
`models.py` changes in one commit and the test additions in a
second so the diff is reviewable.*
