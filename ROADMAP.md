# Roadmap — arquivo-pt-mcp

This document describes the planned evolution of `arquivo-pt-mcp`, the MCP server for the Portuguese Web Archive ([Arquivo.pt](https://arquivo.pt)).

Items are grouped into milestones. Completed items are checked off as they land.

---

## Milestone 1 — Solid Foundation ✅ *(current state)*

The initial release ships a working MCP server with the five core tools, published to PyPI and tested in CI.

- [x] `search` — full-text search with optional date range and site filters
- [x] `image_search` — search across 1.8B+ archived images
- [x] `list_versions` — list all CDX captures for a given URL
- [x] `get_snapshot` — retrieve a specific archived page by URL + timestamp
- [x] `extract_text` — fetch an archived page and return plain text (HTML stripped)
- [ ] Published to PyPI (`pip install arquivo-pt-mcp`)
- [x] CI pipeline (GitHub Actions)
- [x] Bilingual README (🇵🇹 / 🇬🇧)

---

## Milestone 2 — Reliability & Performance ✅

Focus: make the server production-ready for heavy, unattended use.

- [x] **TTL caching** — in-memory `TTLCache` for search, CDX, and snapshot responses (max 1000 entries each; 15 min TTL for search/CDX, 1 h for snapshots)
- [x] **Rate-limit handling** — detect `429` and 5xx responses, retry with exponential backoff (`2^attempt` seconds, up to `MAX_RETRIES=5`)
- [x] **Timeout & error normalisation** — `call_tool` dispatcher catches `httpx.HTTPStatusError`, `httpx.TimeoutException`, and generic exceptions, returning consistent error messages
- [x] **Input validation** — Pydantic models for all five tools with range/required-field constraints, validated in the `call_tool` dispatcher
- [x] **Test coverage ≥ 80 %** — 39 unit tests + 28 integration tests; coverage at 85 % for the main module

---

## Milestone 3 — Richer Search Capabilities

Focus: expose more of the Arquivo.pt API surface to the model.

- [x] **1. Advanced search params** — `search`: add `collection`, `type` (MIME filter), and `offset` (pagination); `list_versions`: add `filter` (status/MIME/regex), `matchType` (`prefix`/`host`/`domain`), `from`/`to` date range, `sort`, and `closest`; `image_search`: add `size` (small/medium/large), `safeSearch`, `collection`, `offset`, and `more` (surface hidden fields: `imgDigest`, `safe` score)
- [x] **2. Screenshot tool** — new `get_screenshot` tool returning the Arquivo.pt PNG render URL for any snapshot; the screenshot endpoint (`/screenshot?url=…`) is already referenced in `search` results but is not directly accessible as a tool
- [ ] **3. Metadata tool** — new `get_metadata` tool querying `/textsearch?metadata={url}/{timestamp}` to return HTTP status code, MIME type, content length, and digest for a specific capture (redirect chain and language are not available from the Arquivo.pt API)
- [ ] **4. Diff tool** — new `diff_snapshots` tool comparing two snapshots of the same URL and returning a human-readable change summary
- [ ] **5. Bulk CDX export** — pagination via `offset`/`limit` already works, but max limit is capped at 500 (API supports 100,000) and the response lacks pagination metadata (total count, next-page indicator)
- [ ] **6. Proximity / phrase search** — phrase quotes and `-exclusion` already pass through to the API correctly, but they are undocumented in the tool descriptions and `inputSchema` (the API does not support `NEAR`, boolean operators, or wildcards)

---

## Milestone 4 — Write Access & Save Page Now

Focus: allow the model to contribute new captures to the archive.

- [ ] **`save_page_now` tool** — submit a live URL to Arquivo.pt for immediate archival via `/save/now/record/{url}`; the endpoint is anonymous (no documented auth model), but captures are slow and bulk use is discouraged by Arquivo.pt's terms of service
- [ ] **Scheduled capture** — optional `schedule_capture` tool for recurring archival of a URL at a given interval

---

## Milestone 5 — Client Ecosystem & Distribution

Focus: make the server trivial to install and use across all major MCP clients.

- [ ] **Verified integration guides** for Cursor, Zed, Cline, Windsurf, and Continue
- [ ] **Docker image** — `ghcr.io/thaenor/arquivo-pt-mcp:latest` for environments without Python
- [ ] **`npx`-style zero-install** — investigate `uvx arquivo-pt-mcp` as the recommended single-command setup
- [ ] **Smithery / MCP Hub listing** — submit to the community MCP server registries for discoverability
- [ ] **GitHub release automation** — tag-triggered PyPI publish via Trusted Publisher (OIDC)

---

## Milestone 6 — Developer Experience & Community

Focus: lower the barrier for contributors and researchers.

- [ ] **CONTRIBUTING.md** — development setup, PR conventions, and coding standards
- [ ] **Architecture docs** — `docs/architecture.md` explaining the tool registration pattern, HTTP client, and test strategy
- [ ] **Example notebooks** — Jupyter notebooks demonstrating historical research workflows (e.g., tracking front-page evolution of a newspaper)
- [ ] **Changelog** (`CHANGELOG.md`) following Keep a Changelog conventions
- [ ] **Issue templates** — bug report and feature request forms in `.github/`

---

## Ideas Under Consideration

These may be promoted to a milestone based on community interest:

- Semantic / vector search over archived text using embeddings
- A `browse_timeline` resource exposing archive history as an MCP resource (not just a tool)
- Support for the [CommonCrawl](https://commoncrawl.org/) CDX API as a complementary backend
- A web UI playground for testing queries outside of an LLM client
- **Memento TimeMap access** — `/wayback/timemap/json/{url}` returns the full capture history in RFC 7089 NDJSON; could serve as an alternative `list_versions` backend with standard Memento datetime fields and no 500-cap constraint (Memento rate limit: 400 req/180 s)

---

*Last updated: May 2026. To suggest changes, open an issue or start a discussion.*
