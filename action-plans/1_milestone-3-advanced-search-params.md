# Implementation Plan — Milestone 3: Advanced Search Params

**current status: needs review**

**Scope:** ROADMAP.md → Milestone 3 → first checkbox only
(*"Advanced search params"*). The other Milestone 3 items
(`get_screenshot`, `get_metadata`, `diff_snapshots`, bulk CDX export,
proximity-search docs) are **out of scope** of this plan.

**Source of truth for parameter semantics:**
`arquivo-pt-mcp/docs/api-reference.md` (sections 1–3).

---

## 1. Goal

Surface the under-used Arquivo.pt query parameters through the three
search-shaped MCP tools so that an LLM client can ask precise,
disambiguating questions of the archive without having to fall back to
raw `WebFetch`.

| Tool           | New parameters                                                                  |
|----------------|---------------------------------------------------------------------------------|
| `search`       | `collection`, `type`, `offset`                                                  |
| `image_search` | `size`, `safe_search`, `collection`, `offset`, `more`                           |
| `list_versions`| `filter`, `match_type`, `from_date`, `to_date`, `sort`, `closest`               |

No new tools, no new files. Only:

- `src/arquivo_pt_mcp/__init__.py` (handlers + `inputSchema`)
- `src/arquivo_pt_mcp/models.py` (Pydantic validation)
- `tests/test_search.py`, `tests/test_image_search.py`,
  `tests/test_list_versions.py`, `tests/test_models.py` (coverage)

---

## 2. Current State (snapshot, May 2026)

- `search()` (`__init__.py:174`) accepts only `query`, `max_items`,
  `from_date`, `to_date`, `site_search`. Hard-caps `max_items` at 50
  even though the API supports 500.
- `image_search()` (`__init__.py:223`) adds `image_type` but is missing
  the four most useful image-side filters (`size`, `safeSearch`,
  `collection`, `more`) and `offset`.
- `list_versions()` (`__init__.py:278`) only forwards `url`, `limit`,
  `offset`. The CDX server's filtering, regex, time-range, and
  closest-match features are all unreachable.
- `_parse_cdx_jsonl()` (`__init__.py:118`) drops the SURT
  `urlkey` and `collection` fields when `matchType=domain/host` —
  they need to be preserved once the new match types are exposed.
- The TextSearch response wrapper carries `next_page` /
  `previous_page` URLs (`api-reference.md:58–59`); we currently
  discard them, so `offset` would be functional but discoverability
  would be poor. Surface these alongside pagination.

---

## 3. Per-tool changes

### 3.1 `search`

**API params to add** (`api-reference.md` §1):

| MCP arg     | API param    | Validation                                                       |
|-------------|--------------|------------------------------------------------------------------|
| `collection`| `collection` | free-form string, optional                                       |
| `type`      | `type`       | enum: `pdf`, `html`, `doc`, `xls`, `ppt`, `rtf` (case-insensitive)|
| `offset`    | `offset`     | int, ≥ 0, default 0                                              |

**Naming note.** Python keyword `type` is fine as a kwarg if we accept
it via `**arguments` from Pydantic, but it shadows the builtin. Use
`mime_type` as the Python kwarg and map to API `type` inside the
handler. Same trick is already used for `image_type` → `type` in
`image_search`.

**Cache key.** Extend the tuple in `SEARCH_CACHE` lookup
(`__init__.py:182`) with the new fields. Order must stay stable so
existing cached entries are simply orphaned (they will TTL out in 15
min — no migration needed).

**Response.** Add `next_page` and `previous_page` keys (verbatim from
`data.get("next_page")` / `data.get("previous_page")`) to the returned
dict, so the model can paginate without reconstructing the URL.

### 3.2 `image_search`

**API params to add** (`api-reference.md` §3):

| MCP arg       | API param     | Validation                                              |
|---------------|---------------|---------------------------------------------------------|
| `size`        | `size`        | enum: `small`, `medium`, `large`                        |
| `safe_search` | `safeSearch`  | enum: `on`, `off` (default `on`)                        |
| `collection`  | `collection`  | string                                                  |
| `offset`      | `offset`      | int, ≥ 0, default 0                                     |
| `more`        | `more`        | comma-joined subset of `imgDigest`, `pageHost`, `pageImages`, `safe` |

**`more` handling.** Accept `more` as a `list[str]` in Pydantic, then
join with `,` before passing to the API. The hidden `safe` score
(`api-reference.md:259`) must be **surfaced explicitly** in the per-item
output dict when present, especially when `safe_search=off`. Document
the `<0.500 = unsafe` convention in the schema description so a model
can interpret it without reading the API docs.

**`max_items`** stays clamped at 50 for parity with current behaviour;
the API allows 200 but bumping the ceiling belongs to the *Bulk CDX
export* milestone item, not this one. Same for `search`'s 500 cap.

### 3.3 `list_versions`

**API params to add** (`api-reference.md` §2):

| MCP arg       | API param   | Validation                                                                    |
|---------------|-------------|-------------------------------------------------------------------------------|
| `filter`      | `filter`    | `list[str]`, repeatable; each item must match `^[!=~]{1,2}[a-zA-Z]+:.+$`     |
| `match_type`  | `matchType` | enum: `exact`, `prefix`, `host`, `domain`                                     |
| `from_date`   | `from`      | passes through `_normalize_date`                                              |
| `to_date`     | `to`        | passes through `_normalize_date`                                              |
| `sort`        | `sort`      | enum: `default`, `reverse`, `closest` (drop `default` before sending)         |
| `closest`     | `closest`   | string, normalized via `_normalize_date`                                      |

**Cross-field rules** (Pydantic `model_validator`):

- `closest` requires `sort == "closest"` (and vice versa is recommended).
  If user passes `closest` alone, auto-set `sort = "closest"` rather
  than rejecting — friendlier for a model that forgets one of the two.
- When `match_type` is `prefix`/`host`/`domain`, the user's `url` likely
  doesn't include a wildcard; pass it as-is. The CDX server handles both
  styles (`api-reference.md:138`).

**`filter` repeatability.** `httpx` supports `params=[("filter", "..."),
("filter", "...")]` (list of tuples) — switch the `params` construction
to that form when `filter` is non-empty, otherwise keep the dict form.

**Cache key.** Extend the `CDX_CACHE` key (`__init__.py:282`) with the
new args. The `(url,)` single-element key used by `get_snapshot`
(`__init__.py:327`) **must not change shape** — keep it as a
distinct key namespace so latest-snapshot lookups don't collide
with a `list_versions(url=..., from_date=...)` call. Concretely: keep
`get_snapshot`'s key as `(url,)`, and make `list_versions`'s key a
longer tuple. They live in the same `TTLCache`, but tuples of different
lengths never collide.

**`_parse_cdx_jsonl` update.** Preserve `urlkey` and `collection`
fields in the returned per-capture dict so `matchType=domain` actually
returns useful disambiguation. Backward-compatible (just two extra keys).

---

## 4. File-by-file changes

### `src/arquivo_pt_mcp/models.py`

Add new fields, plus a small helper for the CDX `filter` regex.

```python
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

_FILTER_RE = re.compile(r"^[!=~]{1,2}[A-Za-z]+:.+$")


class SearchParams(BaseModel):
    query: str
    max_items: int = Field(default=10, ge=1, le=50)
    from_date: str | None = None
    to_date: str | None = None
    site_search: str | None = None
    collection: str | None = None
    mime_type: Literal["pdf", "html", "doc", "xls", "ppt", "rtf"] | None = None
    offset: int = Field(default=0, ge=0)


class ImageSearchParams(BaseModel):
    query: str
    max_items: int = Field(default=10, ge=1, le=50)
    from_date: str | None = None
    to_date: str | None = None
    site_search: str | None = None
    image_type: str | None = None
    size: Literal["small", "medium", "large"] | None = None
    safe_search: Literal["on", "off"] = "on"
    collection: str | None = None
    offset: int = Field(default=0, ge=0)
    more: list[Literal["imgDigest", "pageHost", "pageImages", "safe"]] = Field(
        default_factory=list
    )


class ListVersionsParams(BaseModel):
    url: str
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    compact: bool = False
    filter: list[str] = Field(default_factory=list)
    match_type: Literal["exact", "prefix", "host", "domain"] = "exact"
    from_date: str | None = None
    to_date: str | None = None
    sort: Literal["default", "reverse", "closest"] = "default"
    closest: str | None = None

    @field_validator("filter")
    @classmethod
    def _check_filter_syntax(cls, v: list[str]) -> list[str]:
        bad = [f for f in v if not _FILTER_RE.match(f)]
        if bad:
            raise ValueError(
                f"filter expressions must look like '=field:value' or '~field:regex'; bad: {bad}"
            )
        return v

    @model_validator(mode="after")
    def _closest_implies_closest_sort(self) -> "ListVersionsParams":
        if self.closest and self.sort == "default":
            self.sort = "closest"
        if self.sort == "closest" and not self.closest:
            raise ValueError("sort='closest' requires a 'closest' timestamp")
        return self
```

### `src/arquivo_pt_mcp/__init__.py`

Three handler updates plus three `Tool` schema updates.

**`search()` (line 174):** add new kwargs, set `params["collection"]`,
`params["type"]`, `params["offset"]`. Surface `next_page` /
`previous_page` in the result dict. Extend cache key.

**`image_search()` (line 223):** add new kwargs, set
`params["size"]`, `params["safeSearch"]`, `params["collection"]`,
`params["offset"]`, and `params["more"] = ",".join(more)` if non-empty.
When mapping `responseItems`, conditionally include `digest`,
`page_host`, `page_images`, `safe` fields when present in the source
item. Extend cache key.

**`list_versions()` (line 278):** rebuild `params` as a list of
2-tuples when `filter` is non-empty so repeated keys work; otherwise
keep the dict form. Pass `matchType`, `from`, `to`, `sort`, `closest`.
Extend cache key. Update `_parse_cdx_jsonl` to keep `urlkey` and
`collection`.

**`Tool(... inputSchema=...)` blocks (lines 423–548):** add the new
properties with descriptions copied from
`docs/api-reference.md`. For `more`, advertise that surfacing `safe`
flips the model into NSFW-aware mode (cite the `<0.500` rule).

### Tests

| File                          | New cases (mock-based, no network) |
|-------------------------------|------------------------------------|
| `tests/test_models.py`        | `collection` accepted; `mime_type` rejects `xml`; `offset` rejects negatives; `filter` regex rejects `"status:200"` (missing operator); `closest` without `sort` auto-sets sort; `sort=closest` without `closest` raises. |
| `tests/test_search.py`        | New params end up in the `params` dict passed to `_fetch_with_retry`; `next_page` / `previous_page` returned. |
| `tests/test_image_search.py`  | `more=["safe"]` becomes `params["more"] == "safe"`; per-item `safe` field surfaces when present in mock. |
| `tests/test_list_versions.py` | Multiple `filter` values become repeated tuples; `match_type=domain` passes through; `closest=…` triggers `sort=closest`; cache key disambiguation: `list_versions(url=...)` ≠ `get_snapshot(url=...)` cache hit. |

Coverage target: stay ≥ 80 % for the main module (current 85 %, per
ROADMAP §Milestone 2).

---

## 5. Implementation order

Sequenced so each step ships green tests:

1. **`models.py`** — add fields + validators. Add `test_models.py`
   cases. Run `pytest tests/test_models.py`.
2. **`_parse_cdx_jsonl`** — preserve `urlkey`/`collection`. Add a case
   to `test_helpers.py`. (Pure function, no integration risk.)
3. **`search()` handler** — wire params, return `next_page`. Update
   `test_search.py` and the `inputSchema` for `search` in
   `list_tools()`.
4. **`image_search()` handler** — wire params, surface hidden fields.
   Update `test_image_search.py` and its `inputSchema`.
5. **`list_versions()` handler** — repeated-`filter` params, time
   range, `match_type`, `sort`/`closest`. Update
   `test_list_versions.py` and its `inputSchema`.
6. **Smoke test** — run `tests/test_stdio_smoke.py` to confirm the
   server still negotiates `list_tools`.
7. **Manual integration sanity check** —
   `RUN_INTEGRATION=1 pytest tests/test_integration.py -k "search or list_versions or image_search"`
   inside the DevContainer. Skip if the network is unavailable.

Each step is a self-contained commit; the PR can be merged step-wise
or squashed.

---

## 6. Edge cases & gotchas

- **`type`/`mime_type` ambiguity.** API spells it `type`, but `type` is
  a Python builtin; the handler takes `mime_type` and maps it. Be
  explicit in the schema `description` so the LLM knows the value
  semantics (`pdf`, `html`, …).
- **`safe_search=off` plus `more` without `safe`.** If a caller turns
  off the filter but doesn't request the `safe` score, they have no
  way to filter NSFW client-side. The schema description for
  `safe_search` should recommend pairing `off` with `more=["safe"]`.
- **CDX `filter` injection.** `filter` strings are passed verbatim to
  `httpx`, which percent-encodes the value. The regex prefix-check
  prevents the most obvious mistakes (missing operator, no field). It
  does **not** sandbox the regex itself — a pathological pattern
  (`~url:(.*)+$`) could push CPU on the Arquivo.pt side, but that's
  the API operator's problem to rate-limit, not ours.
- **Cache-key collisions.** The `CDX_CACHE` is shared between
  `list_versions` and `get_snapshot`'s latest-capture path. Different
  tuple arities means no collisions, but be careful not to refactor
  one of them into a dataclass / dict key without addressing the
  other.
- **`next_page` URL leakage.** The Arquivo.pt response's `next_page`
  URL embeds the original query string verbatim. That's fine for our
  use, but worth noting in the schema description so a model knows
  it can re-issue the call with `offset=…` instead of fetching the URL
  via `WebFetch`.
- **Backward compatibility.** All new params are optional with safe
  defaults. Existing callers that pass only the previous arg set
  continue to work unchanged.

---

## 7. Out of scope (deferred to other Milestone 3 items)

- Raising `max_items` ceiling for `search` (50 → 500) and
  `image_search` (50 → 200). Belongs to *Bulk CDX export* /
  pagination-metadata work.
- New tools (`get_screenshot`, `get_metadata`, `diff_snapshots`).
- Documenting phrase / exclusion query syntax in tool descriptions.

These will pair naturally with this PR but ship as separate changes so
each milestone checkbox can be ticked independently.
