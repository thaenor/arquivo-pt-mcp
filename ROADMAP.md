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
- [x] Published to PyPI (`pip install arquivo-pt-mcp`)
- [x] CI pipeline (GitHub Actions)
- [x] MIT licence
- [x] Bilingual README (🇵🇹 / 🇬🇧)

---

## Milestone 2 — Reliability & Performance

Focus: make the server production-ready for heavy, unattended use.

- [ ] **TTL caching** — in-memory (or optional Redis) cache for search and CDX responses to reduce redundant calls to Arquivo.pt
- [ ] **Rate-limit handling** — detect `429` responses and retry with configurable exponential backoff
- [ ] **Timeout & error normalisation** — consistent `McpError` codes for network failures, invalid timestamps, and empty result sets
- [ ] **Input validation** — stricter Pydantic models for all tool arguments (date formats, URL sanity, result count bounds)
- [ ] **Test coverage ≥ 80 %** — expand the `tests/` suite with async unit tests and mocked HTTP responses

---

## Milestone 3 — Richer Search Capabilities

Focus: expose more of the Arquivo.pt API surface to the model.

- [ ] **Advanced domain / collection search** — filter `search` and `list_versions` by top-level domain, collection, or MIME type
- [ ] **Metadata tool** — new `get_metadata` tool returning HTTP status code, content type, redirect chain, and language for a given snapshot
- [ ] **Diff tool** — new `diff_snapshots` tool comparing two snapshots of the same URL and returning a human-readable change summary
- [ ] **Bulk CDX export** — allow `list_versions` to page through large capture histories without truncation
- [ ] **Proximity / phrase search** — pass advanced query operators through to `textsearch` when the Arquivo.pt API supports them

---

## Milestone 4 — Write Access & Save Page Now

Focus: allow the model to contribute new captures to the archive.

- [ ] **`save_page_now` tool** — submit a live URL to Arquivo.pt for immediate archival (requires API credentials; document the credential setup)
- [ ] **Credential management** — secure passing of API key via environment variable or MCP config, with clear error messages when missing
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

---

*Last updated: May 2026. To suggest changes, open an issue or start a discussion.*
