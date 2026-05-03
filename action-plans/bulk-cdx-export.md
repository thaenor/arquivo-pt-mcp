# Implementation Plan — Bulk CDX Export

**current status: needs architect review**

**Scope.** ROADMAP.md → Milestone 3 → fifth checkbox only
(*"Bulk CDX export — pagination via `offset`/`limit` already works,
but max limit is capped at 500 (API supports 100,000) and the
response lacks pagination metadata (total count, next-page
indicator)"*). The other Milestone 3 items
(`diff_snapshots`, proximity-search docs) are covered in their own
plans.

**Source of truth for limits and parameters:**
`docs/api-reference.md` §2 (CDX server). The official ceiling is
**100,000 captures per request** (line 134), against our current
client-side cap of 500 (`models.py:40`).

---

## 1. Goal

Two related changes to `list_versions`:

1. **Raise `limit` from 500 → 100_000**, matching the documented
   upstream ceiling. Default stays 50 (responses with thousands of
   captures are rarely what an LLM wants to read inline).
2. **Add pagination metadata** to the response so a client can walk
   captures programmatically without inferring state:
   - `requested_limit` — what we asked for
   - `returned` — how many we got
   - `offset` — the offset we requested
   - `has_more` — best-effort boolean (`true` iff `returned ==
     requested_limit`; `false` otherwise)
   - `next_offset` — `offset + returned` when `has_more`, else `None`

This is **not** a new tool — it is an enhancement to
`list_versions`. Same handler, same name, additive output keys, no
breaking change.

---

## 2. Current state (May 2026)

- `list_versions()` (`src/arquivo_pt_mcp/__init__.py:335`) already
  accepts `limit` and `offset`. The Pydantic model at
  `models.py:40` caps `limit` with `Field(default=50, ge=1, le=500)`
  — **the only thing standing between us and the API ceiling**.
- The handler already handles every other CDX param surfaced by the
  upstream (`filter`, `match_type`, `from_date`, `to_date`, `sort`,
  `closest`). No new query-shape work.
- The non-compact response is currently
  `{"url": ..., "count": ..., "captures": [...]}` (`__init__.py:413`).
  The compact response adds `summary` and a `note`. Neither carries
  pagination metadata.
- `_parse_cdx_jsonl` (`__init__.py:123`) is happy with arbitrary
  result counts — no internal cap. The 500-cap is purely a
  client-side validation choice.
- `CDX_CACHE` is `TTLCache(maxsize=1000, ttl=15*60)`. A 100K-entry
  capture list is ~10–20 MB of JSON in memory. **At 1000 cached
  responses worst-case, the working set is ~10–20 GB — not
  acceptable.** Address this explicitly (§4.4).
- The CDX server has **no documented `showResumeKey` /
  `showNumPages` parameter** in `docs/api-reference.md`. We will not
  rely on either; pagination metadata must be derivable from
  `(offset, limit, returned)` alone. See §11 pitfall #1.
- Rate limit: CDX is 250 req / 180 s per IP. A single 100K request
  is one call against that budget — bulk consumers benefit
  proportionally. `_fetch_with_retry` already handles 429.

---

## 3. Design

### 3.1 Limit raise — model and schema

```diff
# src/arquivo_pt_mcp/models.py
- limit: int = Field(default=50, ge=1, le=500)
+ limit: int = Field(default=50, ge=1, le=100_000)
```

```diff
# src/arquivo_pt_mcp/__init__.py — list_versions Tool inputSchema
  "limit": {
      "type": "integer",
      "default": 50,
-     "minimum": 1,
-     "maximum": 500,
+     "minimum": 1,
+     "maximum": 100000,
+     "description": "Number of captures per request (max 100000, the documented CDX ceiling). Default 50; large values produce large responses — prefer compact=true for >500.",
  },
```

The default stays 50. We do **not** raise the default — bulk fetches
should be opt-in.

### 3.2 Response pagination metadata

Add four keys to **both** the compact and non-compact branches of
`list_versions`:

```python
returned = len(captures)
has_more = returned == limit                    # best-effort heuristic
next_offset = (offset + returned) if has_more else None

result = {
    "url": url,
    "count": returned,
    # ... existing fields ...
    "requested_limit": limit,
    "returned": returned,
    "offset": offset,
    "has_more": has_more,
    "next_offset": next_offset,
}
```

The `count` key stays for back-compat. `returned` is its synonym
named consistently with the new pagination block. Document both as
equivalent in the tool description.

**Why `has_more` is a heuristic:** without `showResumeKey` or a
documented total-count field, "we returned exactly `limit` rows"
is the only signal. It can over-report (last page happens to align
exactly with `limit` → `has_more=true` but the next call returns
0) but never under-reports. That is the safe direction; document it
in the tool description.

### 3.3 Compact-mode interaction

`compact=true` already returns a `summary` (year-bucketed counts).
With pagination metadata, the contract becomes:

- `summary` is computed over the **current page only**, not the
  whole capture history. Add a sentence to the existing `note` line
  saying so.
- The `compact_captures` list still carries the per-row data so
  pagination is meaningful in compact mode too.

### 3.4 Cache resizing

`CDX_CACHE = TTLCache(maxsize=1000, ttl=15*60)` is dangerous once
the limit ceiling is 100K rows per entry. Two options:

1. **Shrink `maxsize` based on entry size.** Drop to `maxsize=200`,
   which keeps the worst-case bound at ~2–4 GB — still too large.
2. **Use a size-aware eviction policy.** `cachetools.LRUCache` with
   a custom `getsizeof` could work, but the project's other caches
   are all `TTLCache` and changing one breaks consistency.

**Recommended (option 3):** keep `TTLCache` but **skip caching for
large responses**. Concretely, do not write to `CDX_CACHE` when
`returned > 5000`. Rationale: large bulk requests are typically a
one-shot export, not a repeated query, so a cache miss on the second
call is fine. Implementation:

```python
if returned <= 5000:
    CDX_CACHE[cache_key] = captures
```

Document the threshold in a comment so a future reader doesn't
accidentally remove the guard.

### 3.5 Tool description update

Update the `list_versions` description in `list_tools` to mention:

- The new ceiling (100K).
- Pagination keys in the response (`has_more`, `next_offset`).
- The recommendation to use `compact=true` for very large requests.

---

## 4. Files touched

| File | Change |
|------|--------|
| `src/arquivo_pt_mcp/models.py` | Raise `ListVersionsParams.limit` cap from 500 → 100_000. |
| `src/arquivo_pt_mcp/__init__.py` | Add pagination keys to both `list_versions` return branches. Add the cache-skip guard. Update the `list_versions` Tool inputSchema (`maximum: 100000`) and description. |
| `tests/test_list_versions.py` | New cases for pagination metadata, large-response cache skip, and the raised cap. |
| `tests/test_models.py` | Update / add validation cases for the new cap (limit=100_000 succeeds; limit=100_001 fails). |
| `tests/test_integration.py` | Add an `integration`-marked test that fetches 600 captures of a known URL (above the old 500 cap) to prove the upstream actually accepts the new ceiling. Do **not** request the full 100K in CI. |
| `tests/test_cache.py` | Add a case that a 6000-capture mock response is **not** stored in `CDX_CACHE`. |
| `README.md` | One-paragraph note in both halves: bulk export now possible up to 100K per request; show `has_more` / `next_offset` walk pattern. |
| `ROADMAP.md` | Tick the fifth Milestone 3 checkbox. |

No new files. No new dependencies. No `models.py` Pydantic model
besides the one-character cap change. No changes to `_parse_cdx_jsonl`,
`_fetch_with_retry`, or the dispatcher.

---

## 5. Per-file changes

### 5.1 `src/arquivo_pt_mcp/models.py`

One-line edit at line 40:

```diff
-    limit: int = Field(default=50, ge=1, le=500)
+    limit: int = Field(default=50, ge=1, le=100_000)
```

Underscore for readability — Python accepts it as `100000`.

### 5.2 `src/arquivo_pt_mcp/__init__.py` — handler

Inside `list_versions()`, **after** the captures list is populated
(immediately after `__init__.py:390`, where `CDX_CACHE[cache_key] =
captures` is today), restructure the cache write and assemble
pagination metadata before the compact/non-compact split:

```python
# replace the unconditional cache write with a guarded one
if len(captures) <= 5000:
    CDX_CACHE[cache_key] = captures

returned = len(captures)
has_more = returned == limit
next_offset = (offset + returned) if has_more else None
pagination = {
    "requested_limit": limit,
    "returned": returned,
    "offset": offset,
    "has_more": has_more,
    "next_offset": next_offset,
}
```

Then merge `pagination` into the existing return dicts:

```python
if compact:
    # existing compact build...
    return {
        "url": url,
        "count": returned,
        "summary": dict(sorted(by_year.items())),
        "captures": compact_captures,
        "note": (
            f"Showing {returned} captures in compact form (this page only). "
            "summary counts reflect the current page, not the full history. "
            "Set compact=false for full CDX metadata. "
            "Use offset / next_offset to paginate."
        ),
        **pagination,
    }

return {
    "url": url,
    "count": returned,
    "captures": captures,
    **pagination,
}
```

### 5.3 `src/arquivo_pt_mcp/__init__.py` — Tool inputSchema

Inside the `list_versions` `Tool(...)` block in `list_tools`, update:

- `limit.maximum: 500` → `100000`
- Append to the description (whole field):

  > "Number of captures per request (max 100000 — the documented
  > CDX ceiling). Default 50. Use compact=true for large pulls; the
  > response includes has_more / next_offset for pagination."

- Update the top-level `description` of the `list_versions` tool
  (the human-readable one above `inputSchema`) to mention bulk
  pagination:

  > "List every archived capture of a specific URL (CDX query). Use
  > to see how a page changed over time. Supports filters, match
  > types, date ranges, and bulk pagination via limit/offset/
  > next_offset (up to 100000 captures per call)."

### 5.4 (Nothing else.) `_parse_cdx_jsonl`, `_fetch_with_retry`,
the cache definition, the dispatcher, and `clear_cache` are all
unchanged.

---

## 6. Tests

### 6.1 `tests/test_list_versions.py` (extend)

#### 6.1.1 Pagination metadata — partial page

Mock `_fetch_with_retry` to return 30 capture lines. Call
`list_versions(url, limit=50)`. Assert:

```python
assert result["returned"] == 30
assert result["requested_limit"] == 50
assert result["offset"] == 0
assert result["has_more"] is False
assert result["next_offset"] is None
```

#### 6.1.2 Pagination metadata — full page (suspected more)

Mock to return exactly 50 captures. Call
`list_versions(url, limit=50)`. Assert:

```python
assert result["returned"] == 50
assert result["has_more"] is True
assert result["next_offset"] == 50
```

#### 6.1.3 Pagination metadata — second page

Mock to return 30 captures. Call
`list_versions(url, limit=50, offset=100)`. Assert
`offset == 100`, `next_offset is None` (under-full page).

#### 6.1.4 Compact mode carries pagination

Same mock as 6.1.2. Call `list_versions(url, limit=50, compact=True)`.
Assert pagination keys are present alongside `summary` and
`compact_captures`.

#### 6.1.5 New cap accepts large limits

Call `list_versions(url, limit=10_000)` with a tiny mock response.
Should not raise. Assert `requested_limit == 10_000`.

#### 6.1.6 Above-cap rejects

Call `list_versions(url, limit=100_001)` (via the `call_tool`
dispatcher so Pydantic validation kicks in). Assert validation
error response. Or assert directly via `ListVersionsParams` —
`tests/test_models.py` is the cleaner home for this.

### 6.2 `tests/test_models.py` (extend)

```python
def test_list_versions_limit_accepts_new_ceiling():
    p = ListVersionsParams(url="x", limit=100_000)
    assert p.limit == 100_000

def test_list_versions_limit_rejects_above_ceiling():
    with pytest.raises(ValidationError):
        ListVersionsParams(url="x", limit=100_001)
```

Update or remove any existing test that hard-coded `le=500`.

### 6.3 `tests/test_cache.py` (extend)

#### 6.3.1 Large response is not cached

Build a fake CDX response with 6000 well-formed JSON lines. Mock
`_fetch_with_retry` to return it. Call `list_versions(url, limit=10_000)`.
Assert the result is correct (`returned == 6000`). Then **call again**
with the same args — assert `_fetch_with_retry` was invoked **twice**
(no cache hit), proving the skip guard fires.

#### 6.3.2 Small response is still cached

Companion test: 100 captures → cached → second call uses cache
(call count == 1).

### 6.4 `tests/test_integration.py` (extend, integration-marked)

```python
@pytest.mark.integration
async def test_list_versions_above_old_cap_live():
    """Prove the API accepts 600 captures (above the old 500 cap).

    publico.pt has thousands of captures across years; 600 is a
    safe ask that exercises the new ceiling without blasting CI.
    """
    from arquivo_pt_mcp import list_versions
    result = await list_versions("publico.pt", limit=600)
    assert result["returned"] >= 1
    assert result["requested_limit"] == 600
    # tolerant: arquivo.pt may legitimately return fewer than asked
    assert result["returned"] <= 600
```

Do **not** test 100_000 in CI — even a single 100K request can
take minutes and produces a heavy response. Reserve full-ceiling
testing for manual / on-demand runs.

### 6.5 No changes elsewhere

`tests/test_stdio_smoke.py` and `tests/integration_fixtures.py`
need no updates — there is no new tool. The smoke test's
`required` assertions still hold.

---

## 7. README & ROADMAP

### 7.1 `README.md` (both halves)

Add a short subsection under `list_versions` example:

> 🇬🇧 **Bulk export.** `list_versions` now accepts `limit` up to
> 100000 (the documented CDX ceiling). The response includes
> `has_more` and `next_offset` so a client can walk the full
> capture history programmatically. Combine with `compact=true` for
> very large pulls to keep the response readable.
>
> 🇵🇹 **Exportação em massa.** `list_versions` aceita agora `limit`
> até 100000 (o tecto documentado do CDX). A resposta inclui
> `has_more` e `next_offset` para um cliente percorrer toda a
> história de capturas programaticamente. Combine com
> `compact=true` para grandes solicitações.

### 7.2 `ROADMAP.md`

Tick the fifth Milestone 3 checkbox:

```diff
- - [ ] **Bulk CDX export** — pagination via `offset`/`limit` already works, but max limit is capped at 500 (API supports 100,000) …
+ - [x] **Bulk CDX export** — `list_versions` now accepts limit up to 100000 and returns has_more / next_offset.
```

---

## 8. Verification checklist

Inside the DevContainer:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
pytest tests/ -v --tb=short
pytest tests/test_list_versions.py tests/test_models.py tests/test_cache.py -v
RUN_INTEGRATION=1 pytest tests/test_integration.py -v -k list_versions
```

Manual sanity check (uses 600 captures — well below the ceiling but
above the old cap):

```bash
arquivo-pt-mcp <<EOF | head -40
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"x","version":"0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_versions","arguments":{"url":"publico.pt","limit":600,"compact":true}}}
EOF
```

The response should include a `"requested_limit": 600` field and
plausibly `"has_more": true`.

---

## 9. Out of scope / follow-ups

1. **`showResumeKey` / `showNumPages`.** If arquivo.pt later
   documents these (or testing reveals they work undocumented), add
   `resume_key` / `total_pages` to the pagination block. Best-effort
   pagination via `(offset, limit)` is sufficient until then.
2. **Streaming export.** A real "bulk export to NDJSON file" tool
   would stream rather than buffer 100K records in memory. Out of
   scope here — would need either a write-to-disk side-effect (which
   MCP tools should avoid) or a resource-style streaming response.
   File a separate plan when there is concrete demand.
3. **Total-count estimate.** No upstream field we can rely on. If we
   wanted a UI-friendly "approximately N captures total", we could
   binary-search via paged HEAD-style requests, but the request
   budget is not worth it.
4. **`limit` defaults.** Stays at 50. If users routinely ask for
   bulk, raising the default to e.g. 200 is a separate UX call.
5. **Per-tool rate-limit tracking.** Out of scope; the current
   `_fetch_with_retry` is the single line of defence.

---

## 10. Pitfalls the executor must respect

1. **Do not invent pagination signals that are not documented.** No
   `resumeKey`, no `numPages` query params unless the executor first
   verifies they work against the live API and updates
   `docs/api-reference.md` with proof. The plan's `has_more`
   heuristic deliberately uses only `(offset, limit, returned)`.
2. **Do not raise the default `limit`.** Default stays 50. Bulk
   pulls are opt-in. The ROADMAP only asks for the ceiling, not the
   default.
3. **Cache-skip threshold matters.** 5000 is chosen so that any
   response ≤100 KB or so still benefits from caching, while 100K
   responses never do. Don't lower it without thinking through the
   memory implications.
4. **Don't break `count`.** Existing callers may still read it. Keep
   `count` as a synonym for `returned`. The two are always equal in
   the new code.
5. **Pagination keys must be present in *both* compact and non-
   compact branches.** Easy to add to one and forget the other —
   §6.1.4 catches that.
6. **`has_more=true` does not guarantee a non-empty next page.**
   Document this in the tool description so the model doesn't loop
   forever on a boundary-aligned final page. The next call will
   return `returned=0, has_more=false` and break the loop naturally.
7. **`offset` is a CDX server parameter, not a magic count.** The
   server interprets `offset=N` as "skip the first N captures
   *after* applying filter / matchType / from / to / sort". Pagination
   walking with the same other params is well-defined; changing any
   of them between pages restarts the pagination semantics. Mention
   this in the tool description so a model doesn't conflate them.
8. **Don't pre-validate that `offset + limit` fits in some bound.**
   The CDX server is happy with very large offsets (it just returns
   empty). Forwarding the user's value verbatim is correct.

---

*Plan author note for the executor: work §5.1 → §5.2 → §5.3 → §6 →
§7 in that order. Run lint and `pytest tests/test_list_versions.py
tests/test_models.py tests/test_cache.py` after each subsection.
The whole change is small enough to land as one commit.*
