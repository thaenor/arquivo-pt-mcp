# Implementation Plan — `diff_snapshots` Tool

**current status: ready to develop**

**Scope.** ROADMAP.md → Milestone 3 → fourth checkbox only
(*"Diff tool — new `diff_snapshots` tool comparing two snapshots of
the same URL and returning a human-readable change summary"*). The
remaining Milestone 3 items (bulk CDX export, proximity-search docs)
are covered in their own plans.

**Depends on:** `get_metadata` (`action-plans/3_get-metadata-tool.md`)
ideally landing first — `mode="metadata"` of this tool reuses it. If
sequencing is inconvenient, see §10 pitfall #6 for a fallback.

**Source of truth for the inputs:** `extract_text` (text mode) and
`get_metadata` (metadata mode) — both already validated against the
live API. No new Arquivo.pt endpoints are involved.

---

## 1. Goal

Add a new MCP tool — `diff_snapshots` — that compares **two captures
of the same URL** at different timestamps and returns a structured,
human-readable summary of what changed. Two comparison modes:

1. **`mode="text"` (default).** Fetch the cleaned text content of
   both snapshots via `extract_text`, run a unified diff, and return:
   - A bounded unified-diff hunk (capped by `max_diff_chars`).
   - Summary stats: lines added, lines removed, lines unchanged,
     similarity ratio (0.0–1.0 from `difflib.SequenceMatcher`).
   - Length deltas, first-line / title-ish previews of each side.
2. **`mode="metadata"` (cheap).** Fetch only `get_metadata` for both
   captures and compare HTTP status, MIME type, content length, and
   MD5 digest. Returns `changed: bool` plus a per-field diff. Useful
   for "did the page change at all between these two crawls?"
   without paying for the body fetch — the MD5 digest answers that
   question definitively.

The tool's interface mirrors `get_snapshot` for the URL+timestamp
shape, doubled.

---

## 2. Current state (May 2026)

- `extract_text()` in `src/arquivo_pt_mcp/__init__.py` (currently
  around line 561 — locate by name; line numbers have drifted as the
  codebase grew) is the text source. It already handles snapshot
  resolution (`get_snapshot`), the server-side `/textextracted`
  endpoint, the HTML-stripping fallback, the `max_chars` cap, and the
  short-extraction warning. Reuse, do not reimplement. Its return
  dict carries `timestamp`, `extraction_method`, `char_count`,
  `truncated`, `text` (and an optional `warning`); on the not-found
  path it returns the `get_snapshot` dict verbatim, which has
  `found=False`. The handler in §5.1.5 relies on both shapes.
- `get_metadata()` (planned in `3_get-metadata-tool.md`, not yet
  shipped at the time this plan was written) is the metadata-mode
  backend. If it has not landed when this plan is executed, see §10
  pitfall #6 for the inline fallback.
- `get_snapshot()` (currently around line 449) is reused indirectly
  via `extract_text` / `get_metadata` — `diff_snapshots` does not
  call it directly.
- No diff dependency exists today. Python's `difflib` (stdlib) is
  sufficient — no new pyproject dependencies. If we later want
  word-level diffs or HTML-aware diffs, that becomes a follow-up
  (§9).
- The `call_tool` dispatcher (currently around line 906, signature
  `-> list[TextContent | ImageContent]`) already handles
  dict-returning tools; this tool returns a plain dict. **No
  dispatcher change.**
- Module-level caches: text-mode benefits from `SNAPSHOT_CACHE`
  (already populated by `extract_text`). Metadata-mode benefits from
  `METADATA_CACHE` (planned by the metadata-tool plan). The diff
  result itself is a deterministic function of two cached inputs —
  worth a small `DIFF_CACHE`.

---

## 3. Tool design

### 3.1 Name and inputs

```
diff_snapshots(
    url: str,                          # required — same URL on both sides
    timestamp_a: str,                  # required — older snapshot, conventionally
    timestamp_b: str,                  # required — newer snapshot, conventionally
    mode: Literal["text","metadata"] = "text",
    max_chars: int = 8000,             # text mode: per-side body cap (forwarded to extract_text)
    max_diff_chars: int = 8000,        # text mode: cap on the returned diff hunk
    context_lines: int = 3,            # text mode: difflib unified-diff context
) -> dict
```

| Field | Validation | Notes |
|---|---|---|
| `url` | non-empty string | Single URL — the diff compares two captures of the *same* page. Cross-URL diffs are out of scope (§10). |
| `timestamp_a` | required, `YYYY` / `YYYY-MM-DD` / `YYYYMMDDHHMMSS` | Order is by *convention*, not enforced — the tool labels them `a` and `b` and uses `a` as the "from" side of the diff. |
| `timestamp_b` | required, same formats | If equal to `timestamp_a` after normalization, return `{"changed": false, "note": "same capture"}` and skip both fetches. |
| `mode` | `"text"` or `"metadata"` | Default `"text"`. |
| `max_chars` | `500 ≤ max_chars ≤ 50_000` | Per-side, forwarded verbatim to `extract_text`. |
| `max_diff_chars` | `1_000 ≤ max_diff_chars ≤ 50_000` | Cap on the unified-diff string in the response. |
| `context_lines` | `0 ≤ context_lines ≤ 10` | Forwarded to `difflib.unified_diff(n=...)`. |

Both timestamps are required. There's no "diff against latest" mode
in v1 — that would silently change the diff when arquivo.pt rolls a
new capture. If users want it, add it later as
`timestamp_b="latest"` sentinel (§10).

### 3.2 Output — text mode

```json
{
  "url": "<input url>",
  "mode": "text",
  "a": {
    "timestamp": "<resolved 14-digit ts>",
    "char_count": 1234,
    "extraction_method": "server",
    "preview": "<first ~120 chars>"
  },
  "b": {
    "timestamp": "<resolved 14-digit ts>",
    "char_count": 4567,
    "extraction_method": "regex",
    "preview": "<first ~120 chars>"
  },
  "changed": true,
  "similarity": 0.71,
  "lines_added": 42,
  "lines_removed": 12,
  "lines_unchanged": 89,
  "char_delta": 3333,
  "diff": "--- a@20100101000000\n+++ b@20150101000000\n@@ -1,3 +1,3 @@\n …",
  "diff_truncated": false
}
```

If `extract_text` returns `found=False` for either side, **abort
early**: return `{"url": url, "mode": "text", "error": "snapshot not
found", "side": "a" | "b", "timestamp": "<ts>"}`. Do not attempt the
diff against an empty string.

If both bodies are non-empty but identical, set `changed=false`,
`similarity=1.0`, all line counts to their identical values,
`char_delta=0`, `diff=""`, and `diff_truncated=false`.

### 3.3 Output — metadata mode

```json
{
  "url": "<input url>",
  "mode": "metadata",
  "a": { /* same shape as get_metadata(url, ts_a), trimmed to status/mime/length/digest fields */ },
  "b": { /* same */ },
  "changed": true,
  "fields_changed": ["digest", "content_length"],
  "deltas": {
    "content_length": { "a": 12345, "b": 14002, "delta": 1657 },
    "digest":         { "a": "ABCD…", "b": "WXYZ…" }
  }
}
```

Comparison rules:

- `changed = (a.digest != b.digest)` is the authoritative answer
  when both digests are present. The MD5 hash captures any payload
  change.
- If either digest is missing, fall back to comparing
  `(status_code, mime_type, content_length)`. Add `"note":
  "digest unavailable; comparison based on status/mime/length"`.
- `fields_changed` lists all fields whose values differ between `a`
  and `b`, in this fixed order: `status_code`, `mime_type`,
  `content_length`, `digest`. Drop fields where either side is
  `None`.

If `get_metadata` returns `found=False` for either side, abort with
the same shape as text mode (just with `"mode": "metadata"`).

### 3.4 Same-timestamp short-circuit

After normalizing both timestamps via `_normalize_date`:

```python
if _normalize_date(timestamp_a) == _normalize_date(timestamp_b):
    return {
        "url": url,
        "mode": mode,
        "changed": False,
        "note": "timestamps resolve to the same capture; no fetch performed",
        "a": {"timestamp": _normalize_date(timestamp_a)},
        "b": {"timestamp": _normalize_date(timestamp_b)},
    }
```

This dodges a wasteful pair of fetches and avoids paradoxical
"changed=true" results due to the regex/server extraction path
varying between calls (see §11 pitfall #2).

### 3.5 Caching

```python
DIFF_CACHE = TTLCache(maxsize=200, ttl=60 * 60)
```

- Cache key: `(url, ts_a_norm, ts_b_norm, mode, max_chars,
  max_diff_chars, context_lines)`. All `extract_text`-affecting
  parameters must participate.
- The text-mode bodies are *already* cached by `SNAPSHOT_CACHE`, so
  the inputs are cheap to recompute; this cache exists to avoid the
  diff CPU itself, which is non-trivial for ~50 KB documents.
- Metadata-mode entries are tiny; `maxsize=200` is plenty.
- Add `DIFF_CACHE.clear()` to `clear_cache()` (currently around
  line 79). The function already clears `CDX_CACHE`, `SEARCH_CACHE`,
  `SNAPSHOT_CACHE`, and `SCREENSHOT_CACHE` — append `DIFF_CACHE` to
  preserve insertion order.

---

## 4. Files touched

| File | Change |
|------|--------|
| `src/arquivo_pt_mcp/__init__.py` | Add `DIFF_CACHE`, `_unified_diff_summary()` helper, `diff_snapshots()` async function, `Tool` entry in `list_tools`, register in `handlers` and `PARAM_MODELS`. |
| `src/arquivo_pt_mcp/models.py` | Add `DiffSnapshotsParams` (with `mode` Literal). |
| `tests/test_diff.py` | **New.** Unit tests for text-mode happy path, metadata-mode happy path, identical-content, same-timestamp short-circuit, not-found on either side, diff truncation. |
| `tests/conftest.py` | Add `mock_extracted_text_a` / `mock_extracted_text_b` fixtures (two short, comparable strings). |
| `tests/test_models.py` | Add validation cases for `DiffSnapshotsParams`. |
| `tests/test_cache.py` | Add `clear_cache` empties `DIFF_CACHE`. |
| `tests/test_integration.py` | Add an `integration`-marked metadata-mode test against two known captures of `publico.pt`. Skip text mode in CI to avoid two heavy fetches per run. |
| `tests/integration_fixtures.py` | Add `"diff_snapshots"` to `EXPECTED_TOOL_NAMES`. |
| `tests/test_stdio_smoke.py` | Add `assert by_name["diff_snapshots"].inputSchema["required"] == ["url", "timestamp_a", "timestamp_b"]`. |
| `README.md` | Document the new tool in both 🇵🇹 and 🇬🇧 tables. |
| `ROADMAP.md` | Tick the fourth checkbox under Milestone 3. |

No changes to `extract_text`, `get_metadata`, `get_snapshot`,
`_fetch_with_retry`, or the existing `call_tool` dispatcher.

---

## 5. Per-file changes

### 5.1 `src/arquivo_pt_mcp/__init__.py`

#### 5.1.1 Imports

Add at the top of the file (near the existing stdlib imports):

```python
import difflib
```

#### 5.1.2 New cache (after the existing cache block)

```python
DIFF_CACHE = TTLCache(maxsize=200, ttl=60 * 60)
```

#### 5.1.3 Update `clear_cache`

Append `DIFF_CACHE.clear()` to the body (preserve insertion order of
the existing clears).

#### 5.1.4 New helper `_unified_diff_summary`

Place near the other `_*` helpers — currently `_screenshot_url` sits
around line 168 and `_parse_cdx_jsonl` around line 132. Drop this
helper just below `_screenshot_url` to keep helpers grouped before
`_fetch_with_retry`. Pure function — no I/O, easy to test in
isolation.

```python
def _unified_diff_summary(
    text_a: str,
    text_b: str,
    label_a: str,
    label_b: str,
    *,
    context_lines: int = 3,
    max_diff_chars: int = 8000,
) -> dict[str, Any]:
    """Return a dict with similarity, line stats, and a bounded unified diff."""
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()

    matcher = difflib.SequenceMatcher(a=lines_a, b=lines_b, autojunk=False)
    similarity = round(matcher.ratio(), 4)

    added = removed = unchanged = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "insert":
            added += j2 - j1
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1

    diff_iter = difflib.unified_diff(
        lines_a, lines_b,
        fromfile=label_a, tofile=label_b,
        n=context_lines, lineterm="",
    )
    full_diff = "\n".join(diff_iter)
    truncated = len(full_diff) > max_diff_chars
    diff = full_diff[:max_diff_chars] if truncated else full_diff

    return {
        "changed": (added > 0 or removed > 0),
        "similarity": similarity,
        "lines_added": added,
        "lines_removed": removed,
        "lines_unchanged": unchanged,
        "diff": diff,
        "diff_truncated": truncated,
    }
```

**Note:** `autojunk=False` matters — `SequenceMatcher`'s default
treats common lines as "junk" for performance, which skews
similarity ratios on short documents. Disable it.

#### 5.1.5 New `diff_snapshots()` handler

Place after `extract_text`. Skeleton:

```python
async def diff_snapshots(
    url: str,
    timestamp_a: str,
    timestamp_b: str,
    mode: str = "text",
    max_chars: int = 8000,
    max_diff_chars: int = 8000,
    context_lines: int = 3,
) -> dict[str, Any]:
    """Compare two snapshots of the same URL."""
    ts_a = _normalize_date(timestamp_a)
    ts_b = _normalize_date(timestamp_b)

    if ts_a == ts_b:
        return {
            "url": url, "mode": mode, "changed": False,
            "note": "timestamps resolve to the same capture; no fetch performed",
            "a": {"timestamp": ts_a}, "b": {"timestamp": ts_b},
        }

    cache_key = (url, ts_a, ts_b, mode, max_chars, max_diff_chars, context_lines)
    if cache_key in DIFF_CACHE:
        return DIFF_CACHE[cache_key]

    if mode == "metadata":
        result = await _diff_metadata(url, ts_a, ts_b)
    else:
        result = await _diff_text(
            url, ts_a, ts_b, max_chars, max_diff_chars, context_lines,
        )

    DIFF_CACHE[cache_key] = result
    return result


async def _diff_text(
    url: str, ts_a: str, ts_b: str,
    max_chars: int, max_diff_chars: int, context_lines: int,
) -> dict[str, Any]:
    side_a = await extract_text(url, ts_a, max_chars=max_chars)
    if not side_a.get("found", True) or "text" not in side_a:
        return {"url": url, "mode": "text", "error": "snapshot not found",
                "side": "a", "timestamp": ts_a}
    side_b = await extract_text(url, ts_b, max_chars=max_chars)
    if not side_b.get("found", True) or "text" not in side_b:
        return {"url": url, "mode": "text", "error": "snapshot not found",
                "side": "b", "timestamp": ts_b}

    summary = _unified_diff_summary(
        side_a["text"], side_b["text"],
        label_a=f"a@{ts_a}", label_b=f"b@{ts_b}",
        context_lines=context_lines, max_diff_chars=max_diff_chars,
    )

    def _side(s: dict[str, Any], ts: str) -> dict[str, Any]:
        text = s.get("text", "")
        return {
            "timestamp": s.get("timestamp") or ts,
            "char_count": s.get("char_count", len(text)),
            "extraction_method": s.get("extraction_method"),
            "preview": text[:120],
        }

    return {
        "url": url, "mode": "text",
        "a": _side(side_a, ts_a), "b": _side(side_b, ts_b),
        "char_delta": side_b.get("char_count", 0) - side_a.get("char_count", 0),
        **summary,
    }


async def _diff_metadata(url: str, ts_a: str, ts_b: str) -> dict[str, Any]:
    side_a = await get_metadata(url, ts_a)
    if not side_a.get("found"):
        return {"url": url, "mode": "metadata", "error": "snapshot not found",
                "side": "a", "timestamp": ts_a}
    side_b = await get_metadata(url, ts_b)
    if not side_b.get("found"):
        return {"url": url, "mode": "metadata", "error": "snapshot not found",
                "side": "b", "timestamp": ts_b}

    fields = ("status_code", "mime_type", "content_length", "digest")
    fields_changed: list[str] = []
    deltas: dict[str, Any] = {}
    for f in fields:
        a_v, b_v = side_a.get(f), side_b.get(f)
        if a_v is None or b_v is None:
            continue
        if a_v != b_v:
            fields_changed.append(f)
            entry: dict[str, Any] = {"a": a_v, "b": b_v}
            if f == "content_length":
                entry["delta"] = b_v - a_v
            deltas[f] = entry

    digest_unavailable = (
        side_a.get("digest") is None or side_b.get("digest") is None
    )
    changed = (
        side_a.get("digest") != side_b.get("digest")
        if not digest_unavailable
        else bool(fields_changed)
    )

    trimmed_a = {k: side_a.get(k) for k in ("timestamp", *fields)}
    trimmed_b = {k: side_b.get(k) for k in ("timestamp", *fields)}

    out: dict[str, Any] = {
        "url": url, "mode": "metadata",
        "a": trimmed_a, "b": trimmed_b,
        "changed": changed,
        "fields_changed": fields_changed,
        "deltas": deltas,
    }
    if digest_unavailable:
        out["note"] = "digest unavailable; comparison based on status/mime/length"
    return out
```

`_diff_text` and `_diff_metadata` are private helpers (leading
underscore) but kept module-level so tests can target them directly.

#### 5.1.6 Register in `list_tools`

Append after the previous tool entry:

```python
Tool(
    name="diff_snapshots",
    description=(
        "Compare two snapshots of the same URL and report what changed. "
        "mode='text' (default) returns a bounded unified diff plus line "
        "stats and similarity ratio. mode='metadata' compares HTTP status, "
        "MIME type, content length, and MD5 digest only — much cheaper, "
        "and the digest answers 'did anything change?' definitively."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to diff"},
            "timestamp_a": {
                "type": "string",
                "description": "Older snapshot timestamp (YYYY, YYYY-MM-DD, YYYYMMDDHHMMSS)",
            },
            "timestamp_b": {
                "type": "string",
                "description": "Newer snapshot timestamp (same formats)",
            },
            "mode": {
                "type": "string",
                "enum": ["text", "metadata"],
                "default": "text",
            },
            "max_chars": {
                "type": "integer", "default": 8000,
                "minimum": 500, "maximum": 50000,
                "description": "Per-side text body cap (text mode only).",
            },
            "max_diff_chars": {
                "type": "integer", "default": 8000,
                "minimum": 1000, "maximum": 50000,
                "description": "Cap on the returned diff hunk (text mode only).",
            },
            "context_lines": {
                "type": "integer", "default": 3,
                "minimum": 0, "maximum": 10,
                "description": "Lines of context per diff hunk (text mode only).",
            },
        },
        "required": ["url", "timestamp_a", "timestamp_b"],
    },
),
```

#### 5.1.7 Register in `PARAM_MODELS` and `handlers`

`"diff_snapshots": DiffSnapshotsParams,` and
`"diff_snapshots": diff_snapshots,` in their respective maps.

### 5.2 `src/arquivo_pt_mcp/models.py`

```python
from typing import Literal

class DiffSnapshotsParams(BaseModel):
    url: str
    timestamp_a: str
    timestamp_b: str
    mode: Literal["text", "metadata"] = "text"
    max_chars: int = Field(default=8000, ge=500, le=50_000)
    max_diff_chars: int = Field(default=8000, ge=1_000, le=50_000)
    context_lines: int = Field(default=3, ge=0, le=10)
```

`Literal` is already imported at the top of `models.py` for other
models — confirm before adding.

---

## 6. Tests

### 6.1 `tests/test_diff.py` (new)

#### 6.1.1 `_unified_diff_summary` pure tests

- Two identical strings → `changed=False, similarity=1.0, lines_added=0,
  lines_removed=0, diff=""`.
- Strings differing by one inserted line → `changed=True, lines_added=1,
  lines_removed=0`, diff contains `+` on the inserted line.
- Strings differing such that the unified-diff exceeds
  `max_diff_chars=200` → `diff_truncated=True`, `len(diff) <= 200`.

#### 6.1.2 Same-timestamp short-circuit

Patch `extract_text` to fail loudly if called. Call
`diff_snapshots(url, "20100101", "20100101000000")`. Both normalize
to `"20100101000000"` (verified: `_normalize_date` digits-pads with
zeros to 14 chars — see `__init__.py:_normalize_date`). Assert
`changed=False`, `note` mentions same capture, and `extract_text`
was **not** called.

**Note for the executor:** `_normalize_date("2010")` produces
`"20100000000000"` (NOT `"20100101000000"`) — bare-year inputs are
left as `YYYY` followed by zeros, they are *not* coerced to
January 1. Use `"20100101"` (or `"2010-01-01"`) to test the
short-circuit, not `"2010"`.

#### 6.1.3 Text mode happy path

Mock `extract_text` to return two short, different bodies (use the
new fixtures in §6.2). Call `diff_snapshots`. Assert the response
shape from §3.2: `mode="text"`, `a.timestamp`, `b.timestamp`,
`changed=True`, `similarity` between 0 and 1, line counts present,
`diff` non-empty and starts with `--- a@`.

#### 6.1.4 Text mode — side `a` not found

Mock `extract_text(url, ts_a)` → `{"found": False, "message": "no captures found"}`.
Mock `extract_text(url, ts_b)` to fail loudly if called (assert
short-circuit). Assert response is
`{"url": ..., "mode": "text", "error": "snapshot not found", "side": "a", "timestamp": ts_a}`.

#### 6.1.5 Text mode — side `b` not found (after `a` succeeded)

Same shape, `side="b"`. Confirms both error paths.

#### 6.1.6 Metadata mode happy path

Mock `get_metadata(url, ts_a)` → digest `"AAA"`, length 100.
Mock `get_metadata(url, ts_b)` → digest `"BBB"`, length 150.
Assert `changed=True`, `fields_changed == ["content_length", "digest"]`
(status/mime equal so omitted), `deltas["content_length"]["delta"] == 50`.

#### 6.1.7 Metadata mode — digest missing on one side

Mock side `a` with `digest=None`. Assert `note` mentions digest
unavailable, `changed` reflects `(status, mime, length)` comparison.

#### 6.1.8 Cache hit

Two identical calls → second does not invoke `extract_text` /
`get_metadata`. Assert via call-count instrumentation.

### 6.2 `tests/conftest.py` (extend)

```python
@pytest.fixture
def mock_extracted_text_a():
    return (
        "Welcome to Público\n"
        "Headlines for January 1, 2010:\n"
        "- Government announces new budget\n"
        "- Sporting wins national cup\n"
    )

@pytest.fixture
def mock_extracted_text_b():
    return (
        "Welcome to Público\n"
        "Headlines for January 1, 2015:\n"
        "- Election results\n"
        "- Sporting wins national cup\n"
        "- Sapo announces new product\n"
    )
```

Two unchanged lines, two changed, one inserted. Gives stable
similarity ratio for §6.1.3 to assert against.

### 6.3 `tests/test_models.py` (extend)

- `DiffSnapshotsParams(url="x", timestamp_a="2010", timestamp_b="2011")` succeeds.
- Missing any of `url` / `timestamp_a` / `timestamp_b` raises.
- `mode="invalid"` raises.
- `max_diff_chars=999` raises (below `ge=1_000`).

### 6.4 `tests/test_cache.py` (extend)

Populate `DIFF_CACHE` with one entry; `clear_cache()`; assert empty.

### 6.5 `tests/test_stdio_smoke.py` (extend)

```python
assert by_name["diff_snapshots"].inputSchema["required"] == [
    "url", "timestamp_a", "timestamp_b",
]
```

### 6.6 `tests/integration_fixtures.py` (extend)

Add `"diff_snapshots"` to `EXPECTED_TOOL_NAMES`.

### 6.7 `tests/test_integration.py` (extend, integration-marked)

```python
@pytest.mark.integration
async def test_diff_snapshots_metadata_live():
    from arquivo_pt_mcp import diff_snapshots
    result = await diff_snapshots(
        "publico.pt",
        timestamp_a="20100101000000",
        timestamp_b="20150101000000",
        mode="metadata",
    )
    assert "error" not in result
    assert result["mode"] == "metadata"
    assert isinstance(result["changed"], bool)
    # We don't assert changed=True — same URL across years is *almost*
    # certainly a different capture, but tolerate either outcome:
    assert "a" in result and "b" in result
```

Skip text-mode in the live integration to avoid two heavy fetches
per run; the unit tests cover that path with mocks.

---

## 7. README & ROADMAP

### 7.1 `README.md` (both halves)

Add a row to the tools table:

| 🇵🇹 | 🇬🇧 |
|---|---|
| **`diff_snapshots`** — Compara duas capturas do mesmo URL (modo texto ou metadados) | **`diff_snapshots`** — Compare two snapshots of the same URL (text or metadata mode) |

Add an example prompt:

> *"Compara a homepage do Público entre 2010 e 2015 — só em metadados primeiro."*
> *"Diff Público's homepage between 2010 and 2015 — metadata-only first."*

### 7.2 `ROADMAP.md`

Tick the fourth Milestone 3 item:

```diff
- - [ ] **Diff tool** — new `diff_snapshots` tool …
+ - [x] **Diff tool** — new `diff_snapshots` tool …
```

---

## 8. Verification checklist

Run inside the DevContainer:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
pytest tests/ -v --tb=short
pytest tests/test_diff.py tests/test_models.py tests/test_cache.py -v
RUN_INTEGRATION=1 pytest tests/test_stdio_smoke.py -v
RUN_INTEGRATION=1 pytest tests/test_integration.py -v -k diff
```

---

## 9. Out of scope / follow-ups

1. **Cross-URL diffs.** `diff_snapshots(url_a=..., ts_a=..., url_b=..., ts_b=...)`.
   Useful for "how does Público compare to Expresso on the same day?"
   Defer until asked — the v1 single-URL shape is the common case.
2. **`timestamp_b="latest"` sentinel** for "diff against current
   latest capture". Pleasant, but couples result to wall-clock state
   in a way that breaks reproducibility unless we also surface the
   resolved ts. Add when there is a real use case.
3. **Word-level / inline diffs** (`difflib.ndiff` or third-party
   `diff-match-patch`). Better readability but pulls a dep and the
   character-cap semantics get weird.
4. **HTML-aware diffs** that compare DOM structure rather than
   stripped text. Heavier (needs `lxml` or `selectolax`); valuable
   for layout/structural changes that survive text extraction.
5. **Image-mode diff** using the screenshot tool's PNG bytes.
   Requires Pillow + a perceptual-hash library. Real demand
   uncertain; the metadata-mode digest already catches "did anything
   change."
6. **Surface `linkToMetadata` from `search` results** (also flagged
   in the metadata plan §10) so a model can chain `search → diff` by
   timestamp without an extra `list_versions` call.

---

## 10. Pitfalls the executor must respect

1. **Set `autojunk=False` on `SequenceMatcher`.** The default
   silently drops "common" lines from the comparison, making
   similarity ratios on short documents misleading. Tested
   indirectly by §6.1.1 (identical → 1.0).
2. **Don't compare snapshots without resolving timestamps first.**
   `_normalize_date("20100101")` and `_normalize_date("20100101000000")`
   both produce `"20100101000000"` — they should short-circuit, not
   fetch twice. Tested by §6.1.2. **Heads-up:** `_normalize_date("2010")`
   produces `"20100000000000"` (zeros, not Jan 1) — inputs that look
   equivalent to a human are not always equivalent post-normalization.
   The short-circuit compares the *normalized* values, which is
   correct; just don't write tests assuming bare years coerce to Jan 1.
3. **`extract_text`'s `extraction_method` can vary** between the
   server-side `/textextracted` and the regex fallback for the same
   capture across runs (the server may transiently 404). Two text
   diffs of the same pair can therefore differ in
   `extraction_method` even though the *text* is the same. The diff
   stats are stable; the bodies are stable enough; `extraction_method`
   is informational. Don't write tests asserting it.
4. **Cap the diff *output*, not the inputs of `unified_diff`.**
   Truncating the text *before* computing the diff produces lies
   ("removed 100 lines" when really 80 of them were past the cap).
   `_unified_diff_summary` is correct: it computes line stats
   against the full inputs and only truncates the rendered diff
   string. The body cap (`max_chars`) is enforced by `extract_text`
   itself, which is fine because its truncation is documented in the
   per-side `truncated` field.
5. **Metadata mode must be cheap.** Do not fetch bodies in metadata
   mode — even as a "validation" step. Two `get_metadata` calls plus
   a tiny dict-comparison is the entire point.
6. **If `get_metadata` has not landed yet**, gate `mode="metadata"`
   behind a `try/except ImportError`-style runtime check (or temporarily
   raise `NotImplementedError` from `_diff_metadata` with a clear
   message: "metadata mode requires get_metadata, planned in
   `action-plans/3_get-metadata-tool.md`"). Do not block this
   plan on it — `mode="text"` is independently valuable. Once
   metadata lands, remove the guard.
7. **`difflib.unified_diff` returns a generator** — `"\n".join(it)`
   is correct but make sure no `next()` peek happens before the join,
   or you'll silently drop the first line.
8. **The `diff` field is a multi-line string carrying real
   newlines.** When the dispatcher serializes via `json.dumps(...,
   indent=2)`, those newlines become `\n` escapes — readable but
   not pretty. Acceptable for v1; revisit if a client complains.

---

*Plan author note for the executor: work §5.1 → §5.2 → §6.2 → §6.1 →
§6.{3..7} → §7. Run lint and unit tests after each subsection. Keep
the implementation in one commit and the tests in a second.*
