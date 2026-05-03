# Implementation Plan — Proximity / Phrase Search Documentation

**current status: needs architect review**

**Scope.** ROADMAP.md → Milestone 3 → sixth checkbox only
(*"Proximity / phrase search — phrase quotes and `-exclusion` already
pass through to the API correctly, but they are undocumented in the
tool descriptions and `inputSchema` (the API does not support `NEAR`,
boolean operators, or wildcards)"*).

**This is a documentation-only change.** No new tools, no new
parameters, no handler logic. The features already work — they are
just invisible to the model. The full plan is small.

**Source of truth for the operator surface:**
`docs/api-reference.md` line 34 (text search) and line 200 (image
search), both of which state simply: *"Supports `" "` for phrases
and `-` to exclude."* The roadmap entry confirms the negative space:
**no NEAR, no boolean operators (AND/OR/NOT), no wildcards in `q`**.

---

## 1. Goal

Make the model aware of two query-string features that the upstream
already supports and that our handlers already pass through verbatim:

1. **Phrase search.** Wrapping terms in `"…"` matches the exact
   phrase. Example: `q="acordo ortográfico"` matches the phrase, not
   pages with both words anywhere.
2. **Exclusion.** Prefixing a term with `-` excludes pages that
   contain it. Example: `q=eleições -autárquicas` excludes pages
   mentioning `autárquicas`.

And to make the model **stop trying** features that don't exist:

- No `NEAR/n` proximity operator.
- No `AND` / `OR` / `NOT` keywords (the upstream silently ignores
  them or treats them as literal terms — confusing).
- No `*` or `?` wildcards inside `q` (the `siteSearch` and CDX
  `matchType=prefix` are different things and stay as-is).

Both `search` and `image_search` accept the same operator surface
(verified at `api-reference.md:34` and `:200` — identical wording).

---

## 2. Current state (May 2026)

- `search()` (`src/arquivo_pt_mcp/__init__.py:191`) builds the
  outgoing `params["q"] = query` verbatim — no escaping, no
  rewriting. Phrase quotes and `-` prefixes pass through to
  arquivo.pt unchanged. `image_search()` (`__init__.py:254`) does
  the same with `params["q"]`.
- The two `Tool` entries' `description` and `inputSchema.properties.query.description`
  fields say nothing about operators. The `search` tool description
  reads: *"Full-text search across the Portuguese Web Archive
  (Arquivo.pt). Use for finding pages that ever contained given
  terms, optionally scoped by date range or site."* (`__init__.py:597–601`).
- `tests/test_search.py`, `tests/test_image_search.py`, and
  `tests/test_stdio_smoke.py` do **not** assert on description text
  (verified by `grep -n "description" tests/`). The smoke test only
  pins `required` fields. So this plan changes only strings — zero
  test churn beyond optionally adding a couple of sanity tests
  proving query-string passthrough.
- No new endpoints, no new params on the wire. The handlers are
  already correct.

---

## 3. Design

### 3.1 What to add to each tool

For both `search` and `image_search`, update **two** strings:

1. The tool's top-level `description` — append a "Query syntax"
   sentence.
2. `inputSchema.properties.query.description` — replace the bare
   `"Search terms"` with concrete operator examples and a bounded
   list of what does and does not work.

Use the same wording in both tools so the model learns one rule.

### 3.2 Proposed text — top-level descriptions

**`search`** (replaces `__init__.py:597–601`):

> Full-text search across the Portuguese Web Archive (Arquivo.pt).
> Use for finding pages that ever contained given terms, optionally
> scoped by date range, site, collection, or MIME type. Query syntax
> supports phrase quotes (`"acordo ortográfico"`) and term exclusion
> (`-autárquicas`). The API does **not** support boolean operators
> (`AND` / `OR` / `NOT`), proximity operators (`NEAR`), or wildcards
> in the query — wildcards belong to `siteSearch` (which accepts
> domain wildcards) and to `list_versions(match_type="prefix")`.

**`image_search`** (replaces the analogous block in `list_tools`):

> Search 1.8B+ archived images on Arquivo.pt (Dionisius image
> search). Find historical photos, logos, and graphics from the
> Portuguese web. Query syntax supports phrase quotes
> (`"praça do comércio"`) and term exclusion (`-mapa`). The API
> does **not** support boolean operators (`AND` / `OR` / `NOT`),
> proximity operators (`NEAR`), or wildcards in the query.

### 3.3 Proposed text — `query.description`

For both tools:

> Search terms. Supports phrase quotes (`"…"`) and term exclusion
> (`-term`). Examples: `eleições 2005` (loose match), `"acordo
> ortográfico"` (exact phrase), `eleições -autárquicas`
> (exclude). Boolean operators (AND/OR/NOT), proximity (NEAR), and
> wildcards (`*`, `?`) are **not** supported by the upstream API.

Identical text in both tools — copy-paste, do not paraphrase. A
shared constant is overkill for two strings (§6 pitfall #2).

### 3.4 What stays the same

- Both handlers' Python code: untouched.
- Pydantic models (`SearchParams`, `ImageSearchParams`): untouched.
  No new validators — we are *not* validating that `q` is
  syntactically clean. The upstream tolerates extra whitespace,
  unbalanced quotes, etc.; let it.
- Tests: the smoke test's `required` assertion on `query` still
  holds.
- README: optionally extend the Portuguese / English examples
  sections (§5) — minor, not strictly required.

---

## 4. Files touched

| File | Change |
|------|--------|
| `src/arquivo_pt_mcp/__init__.py` | Replace two `description` strings (top-level) and two `query.description` strings (inputSchema) inside `list_tools`. **No code logic change.** |
| `tests/test_search.py` | Add **one** sanity test asserting query-string passthrough (proves the handler does not mangle quotes / dashes). Optional but cheap insurance. |
| `tests/test_image_search.py` | Same: one passthrough sanity test. |
| `README.md` | Add a one-sentence "Query syntax" note to the search example sections in both 🇵🇹 and 🇬🇧 halves. |
| `ROADMAP.md` | Tick the sixth Milestone 3 checkbox. |

No new files. No `models.py` change. No dependency change. No
fixture change. No CI change.

---

## 5. Per-file changes

### 5.1 `src/arquivo_pt_mcp/__init__.py`

Two pairs of `Edit` calls — one pair for `search`, one for
`image_search`. Use the exact text from §3.2 and §3.3.

The `search` block lives at `__init__.py:594–637` (current line
numbers may shift — locate by tool name). The `image_search` block
lives immediately after.

**Specifically (executor instructions):**

1. In the `search` Tool's `description=(…)` argument, replace the
   existing tuple-string with the §3.2 `search` text.
2. In the `search` Tool's `inputSchema.properties.query.description`,
   replace `"Search terms"` with the §3.3 text.
3. In the `image_search` Tool's `description=(…)`, replace with the
   §3.2 `image_search` text.
4. In the `image_search` Tool's `inputSchema.properties.query.description`,
   replace `"Image search terms"` with the §3.3 text.

Do not touch any other field in either Tool. Do not reorder
properties. Do not "tidy up" sibling entries while you are there.

### 5.2 `tests/test_search.py` (extend)

Add one test:

```python
async def test_search_passes_query_operators_verbatim(monkeypatch, mock_search_response):
    """Phrase quotes and exclusion prefix must reach the API unmodified."""
    seen: dict = {}

    async def fake_get(self, url, **kwargs):
        seen["url"] = url
        seen["params"] = kwargs.get("params")
        return _make_resp(mock_search_response)  # use whatever helper the file already uses

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    from arquivo_pt_mcp import search
    await search('"acordo ortográfico" -autárquicas')
    assert seen["params"]["q"] == '"acordo ortográfico" -autárquicas'
```

Reuse the response-mocking style already present in the file — do
not invent a new pattern. If the file uses `respx`, `monkeypatch`,
or a custom transport, follow whichever it uses.

### 5.3 `tests/test_image_search.py` (extend)

Same shape — assert `params["q"]` is the verbatim input. Use
`mock_image_search_response`.

### 5.4 `README.md`

In the "Exemplos de utilização" / "Usage examples" section of each
half, add one new bullet **and** one new sentence:

```diff
+ - *"Procura pelo termo exato \"acordo ortográfico\" no Arquivo.pt."*
+ - *"Procura por 'eleições' excluindo páginas que falem de 'autárquicas': eleições -autárquicas."*

+ > **Sintaxe.** A pesquisa aceita aspas para frases exatas e o prefixo `-` para excluir termos. Não suporta `AND` / `OR` / `NEAR` nem caracteres-curinga (`*`, `?`).
```

Mirror in English. Keep the wording short — the inputSchema
description is the canonical reference; README is just a hint.

### 5.5 `ROADMAP.md`

Tick the sixth Milestone 3 checkbox:

```diff
- - [ ] **Proximity / phrase search** — phrase quotes and `-exclusion` already pass through to the API correctly, but they are undocumented in the tool descriptions and `inputSchema` (the API does not support `NEAR`, boolean operators, or wildcards)
+ - [x] **Proximity / phrase search** — tool descriptions and inputSchema now document phrase quotes and exclusion. The API does not support NEAR / boolean operators / wildcards.
```

---

## 6. Verification checklist

Inside the DevContainer:

```bash
# Lint clean (descriptions are just strings; no formatting concern)
ruff check src/ tests/
ruff format --check src/ tests/

# Tests still pass — no logic changed
pytest tests/ -v --tb=short

# New passthrough sanity tests pass
pytest tests/test_search.py tests/test_image_search.py -v -k "passes_query"

# Smoke test: schemas still validate, required fields unchanged
RUN_INTEGRATION=1 pytest tests/test_stdio_smoke.py -v

# Optional manual sanity — talk to the live API with each operator
RUN_INTEGRATION=1 pytest tests/test_integration.py -v -k search
```

No new integration tests are warranted: the upstream behaviour for
phrases and exclusion is well-known and documented; further live
verification is the operator's responsibility, not the test
suite's.

---

## 7. Out of scope / follow-ups

1. **Operator validation.** Tempting, but the upstream is the
   authority. Adding a Pydantic validator to forbid `AND` / `OR` /
   `NEAR` in `q` would surprise users who legitimately want to
   search for the literal word "and" — and the upstream just treats
   it as a stopword anyway.
2. **Query auto-quoting.** Some clients quote multi-word queries
   automatically. We do not — passthrough is the right default;
   prompt-engineering at the model side handles it.
3. **CDX wildcard / `match_type=prefix` documentation.** The
   `list_versions` tool already has a `match_type` enum. If its
   description should also call out wildcards, that's a separate
   one-line edit — but distinct from query-syntax docs.
4. **Bilingual operator examples.** Sticking with Portuguese
   examples (`acordo ortográfico`, `autárquicas`) makes the
   semantics clearest for the corpus. Adding English examples
   (`election -primary`) would dilute that signal. Skip.

---

## 8. Pitfalls the executor must respect

1. **Do not change handler code.** This plan is *only* descriptions
   and a couple of passthrough tests. If you find yourself editing
   `params["q"] = query`, stop — that's a different plan.
2. **Use the same wording in both tools** (§3.3). Resist the urge
   to paraphrase the second one. Consistency helps the model
   generalize the rule. A shared constant is overkill for two
   strings; copy-paste is fine.
3. **Keep examples Portuguese** (`acordo ortográfico`,
   `autárquicas`, `praça do comércio`). The corpus is Portuguese;
   English examples would be confusing.
4. **Do not add input validation for operators.** The handler must
   stay forgiving. Tests at §5.2 / §5.3 confirm passthrough — they
   should *not* try to assert error behaviour for malformed
   queries.
5. **Smoke test still passes unchanged.** The smoke test asserts
   `required: ["query"]`, not the description string. Confirm by
   running `pytest tests/test_stdio_smoke.py` — it should be green
   without modification.
6. **Watch for trailing whitespace in the multi-line strings.**
   Ruff format will normalize indentation but won't catch trailing
   spaces inside string literals; review the diff manually before
   committing.

---

*Plan author note for the executor: this is a 30-minute change.
Land it as a single commit. Sequence: §5.1 → §5.4 → §5.2 → §5.3 →
§5.5. Run lint and full pytest at the end; nothing should break.*
