# CLAUDE.md

MCP server for [Arquivo.pt](https://arquivo.pt), the Portuguese Web Archive. Exposes 6 tools: `search`, `image_search`, `list_versions`, `get_snapshot`, `extract_text`, `get_screenshot`.

## Workflow

This Claude session is expected to run **inside the project's DevContainer**.

container:
id: 5f6c44112660
name: pensive_moser
image: mcr.microsoft.com/devcontainers/python:3.12

What do run inside the Docker Container:

- Python commands
- tests
- anything tightly couple with the code

What to run on bare metal (Macbook)
- git and gh (already authenticated)
- hf (hugging face) (already authenticated)
- related curl commands to troubleshoot issues with git or huggingFace

When in doubt, pause the process and confirm with the user. Never install any dependencies on the bare metal machine.

## Commands

- Install dev deps: `uv sync --extra dev` (or `pip install -e ".[dev]"`)
- Lint / format: `ruff check src tests` · `ruff format src tests`
- Tests: `pytest -q` · single file: `pytest tests/test_search.py -q` · single test: `pytest tests/test_search.py::test_search_basic -q`
- Coverage: `pytest --cov=arquivo_pt_mcp`
- Integration (live API, opt-in): `RUN_INTEGRATION=1 pytest -m integration -v`
- Run server (stdio): `uv run arquivo-pt-mcp`
- Run server (HTTP): `arquivo-pt-mcp --transport http --host 127.0.0.1 --port 8000`
- Build wheel: `python -m build`

`pytest.ini_options` sets `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`. The `integration` marker is registered; tests without `RUN_INTEGRATION=1` skip via `tests/integration_fixtures.py`.

## Architecture

### Single-module core, thin wrappers

`src/arquivo_pt_mcp/__init__.py` is the whole server: tool implementations, MCP wiring (`@server.list_tools`, `@server.call_tool`), HTTP helpers, and the `main()` entry point all live there. The other source files are deliberately thin:

- `server.py` — re-exports `main` for `python -m arquivo_pt_mcp.server`-style use. Don't add logic here.
- `cli.py` — argparse + env-var fallbacks for transport/host/port/security flags. Pure parsing; no I/O.
- `http_app.py` — Starlette ASGI factory used only when `--transport http`. Lazy-imported from `__init__._async_main_http` to avoid pulling Starlette/uvicorn into stdio runs.
- `models.py` — Pydantic `*Params` models. Validation runs in `call_tool` *before* dispatch via the `PARAM_MODELS` map; tool handlers themselves accept loose kwargs.

When changing a tool's signature, update **three** places: the handler in `__init__.py`, the `Tool(...)` schema in `list_tools()`, and the corresponding model in `models.py`.

### Two transports, one Server instance

The module-level `server = Server("arquivo-pt")` is shared. `_async_main_stdio` runs `stdio_server()`; `_async_main_http` builds a Starlette app via `create_app()` that mounts `StreamableHTTPSessionManager` at `/mcp` and a `/healthz` route. **In-memory caches are shared across all HTTP clients** — keep this in mind when reasoning about isolation.

### Caching

Four module-level `TTLCache`s in `__init__.py`:

- `SEARCH_CACHE` — both `search` and `image_search` (15 min, max 1000)
- `CDX_CACHE` — `list_versions` and the `get_snapshot` "latest capture" lookup (15 min, max 1000)
- `SNAPSHOT_CACHE` — `extract_text` results (60 min, max 1000)
- `SCREENSHOT_CACHE` — `get_screenshot` inline PNG bytes (60 min, max 200)

Cache keys are tuples of every parameter that affects output (including `max_chars`, `max_bytes`, sorted `more`/`filter` lists). The autouse `_clear_caches` fixture in `tests/conftest.py` resets all of them between tests; `clear_cache()` is available for manual use.

### Retry & error model

`_fetch_with_retry` retries up to `MAX_RETRIES = 5` with `2**attempt` backoff, but **only** on timeouts, 429, and 5xx. Other 4xx errors raise immediately — don't paper over them. The `call_tool` dispatcher catches `HTTPStatusError` / `TimeoutException` / generic `Exception` and converts to `TextContent` error responses; tool handlers should let exceptions propagate rather than catching locally.

### Date handling

All date-like params flow through `_normalize_date()`, which accepts `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or `YYYYMMDDHHMMSS` and pads to a 14-char Wayback timestamp. Use it on any new date param rather than reimplementing parsing.

### Inline images (get_screenshot)

`get_screenshot(inline=True)` returns a `(meta, png_bytes, mime)` triple instead of a dict. The dispatcher in `call_tool` detects the 3-tuple shape and emits both `TextContent` and `ImageContent`. If you add another tool that returns binary content, follow the same shape — don't add a new branch in the dispatcher unless the tuple contract no longer fits.

### Test fixture fidelity

Mocks in `tests/conftest.py` are shaped to match real Arquivo.pt responses (verified 2026-05-02). The CDX response uses **JSON-Lines** (one object per line), not a JSON array — `_parse_cdx_jsonl` reflects that. If you update fixtures, keep them faithful to the wire format or unit tests stop catching real regressions.

## CI / release

- `.github/workflows/ci.yml` — lint + test matrix (3.11/3.12/3.13) + import-validation on every push/PR. Integration job runs only on `workflow_dispatch`; it was previously scheduled nightly but disabled due to unreliable transatlantic connectivity from US-based GitHub runners to `arquivo.pt` (Portugal). It never blocks PRs.
- `.github/workflows/publish.yml` — tag `v*.*.*` triggers PyPI publish (trusted publisher, no token) and a GitHub Release.
- `.github/workflows/huggingface.yml` — same tag triggers HF Spaces deploy (Dockerfile-based, port 7860). The Dockerfile pins `ARQUIVO_PT_MCP_ALLOWED_HOSTS` to the HF Space hostname — update it if the Space is renamed.

US-based GitHub runners sometimes can't reach `arquivo.pt` (Portugal) reliably — occasional integration failures with `httpx.ConnectError` / `ConnectTimeout` are environmental, not regressions.
