# Implementation Plan — Streamable HTTP Transport

**current status: ready to develop**

**Scope.** Add support for serving `arquivo-pt-mcp` over the **Streamable
HTTP** transport defined by the MCP spec (the modern replacement for the
older HTTP+SSE transport), while keeping the existing **stdio** transport
fully functional and the default. Result: the same five tools, same
handlers, same Pydantic models — exposed either over stdio (local
client) or as a long-running HTTP service.

**Out of scope.** Authentication/OAuth, Docker image, PyPI publishing,
horizontal scaling, persistent caches, observability stack. Each is
covered as a *follow-up* in §10.

**Source of truth for SDK semantics.** The plan is grounded in
`mcp==1.27.0` (already present in the DevContainer):

- `mcp.server.streamable_http_manager.StreamableHTTPSessionManager`
- `mcp.server.streamable_http.StreamableHTTPServerTransport` (used
  internally by the manager — not called directly by us)
- `mcp.server.transport_security.TransportSecuritySettings`
- `mcp.client.streamable_http.streamablehttp_client` (used by the new
  smoke test)

---

## 1. Goal

Let the model talk to `arquivo-pt-mcp` either:

1. **Locally over stdio** (today's behaviour, unchanged) —
   `command = arquivo-pt-mcp` in the client config.
2. **Remotely over Streamable HTTP** —
   `url = https://example.com/mcp` in the client config; the server runs
   as a long-lived process bound to a port.

Mode is chosen at startup:

```
arquivo-pt-mcp                     # stdio (default, unchanged)
arquivo-pt-mcp --transport stdio   # stdio (explicit)
arquivo-pt-mcp --transport http    # streamable HTTP, defaults below
arquivo-pt-mcp --transport http --host 0.0.0.0 --port 8000
```

The HTTP endpoint is `POST /mcp` (and `GET /mcp` for the SSE event
stream when `--json-response` is **not** set). Health check at
`GET /healthz` for ops/probes.

---

## 2. Current state (May 2026)

- `server = Server("arquivo-pt")` is built in
  `src/arquivo_pt_mcp/__init__.py:57` using the **low-level** SDK API.
  All five `@server.list_tools()` / `@server.call_tool()` handlers
  (`__init__.py:425`–`__init__.py:605`) are transport-agnostic and
  reusable as-is.
- `_async_main()` (`__init__.py:613`) is hardcoded to `stdio_server`:
  ```python
  async def _async_main() -> None:
      async with stdio_server() as (read, write):
          await server.run(read, write, server.create_initialization_options())
  ```
- `main()` (`__init__.py:608`) is the console-script entry point
  registered in `pyproject.toml:38` as
  `arquivo-pt-mcp = "arquivo_pt_mcp:main"`. It currently takes no
  arguments — `argparse` is **not** wired in.
- Module-level caches (`CDX_CACHE`, `SEARCH_CACHE`, `SNAPSHOT_CACHE`
  at `__init__.py:61–63`) are per-process. In stdio mode that is
  per-client. In HTTP mode they become *shared across all
  connected clients* — acceptable, because arquivo.pt is a public
  archive with no per-user state, but call it out in the README.
- No HTTP server, ASGI app, web framework, or uvicorn dependency
  exists today. `httpx` is currently only used as a *client* for
  arquivo.pt.
- `tests/test_stdio_smoke.py` already proves the stdio plumbing
  end-to-end. We add a parallel HTTP smoke test, **without removing
  the stdio one** — both transports must remain green.
- `.mcp.json` at the workspace root references the local Homebrew
  binary (`/opt/homebrew/bin/arquivo-pt-mcp`). It does not need to
  change to gain HTTP support; HTTP wiring is documented in the README
  and is a *deployment* concern, not a `.mcp.json` concern.
- DevContainer (`.devcontainer/devcontainer.json`) has no
  `forwardPorts`, so a port-bound HTTP server is reachable from the
  host only after we add one.

---

## 3. Files touched

| File | Change |
|------|--------|
| `pyproject.toml` | Add `starlette`, `uvicorn[standard]`. New optional-extra `http`. |
| `src/arquivo_pt_mcp/__init__.py` | Refactor `main()` → argparse dispatcher. Rename `_async_main` → `_async_main_stdio`. Add `_async_main_http`. No handler changes. |
| `src/arquivo_pt_mcp/http_app.py` | **New.** Builds the Starlette ASGI app around `StreamableHTTPSessionManager`. |
| `src/arquivo_pt_mcp/cli.py` | **New.** `argparse` definition + env-var fallbacks. Keeps `__init__.py` free of CLI noise. |
| `src/arquivo_pt_mcp/server.py` | No code change; update the docstring to mention both transports. |
| `tests/test_http_app.py` | **New.** In-process ASGI tests via `httpx.ASGITransport`. |
| `tests/test_http_smoke.py` | **New.** Integration test (`RUN_INTEGRATION=1`) — boots a real subprocess on an ephemeral port and uses `streamablehttp_client`. |
| `tests/test_cli.py` | **New.** Unit tests for the argparse parser. |
| `tests/integration_fixtures.py` | Add `EXPECTED_HEALTHZ_BODY` constant if used by the smoke test. |
| `.devcontainer/devcontainer.json` | Add `"forwardPorts": [8000]` and `"appPort": [8000]` so the host can reach the HTTP server. |
| `.github/workflows/ci.yml` | Extend the `integration` job command to include `tests/test_http_smoke.py` (already covered if we keep the broad `tests/` glob; verify). |
| `README.md` | New "Remote (Streamable HTTP)" section in both 🇵🇹 and 🇬🇧 halves; new client-config snippets. |
| `ROADMAP.md` | Tick off "Remote / hosted server" item if present, else add it under Milestone 5. |

No changes to `models.py`, the five tool handlers, the cache layer,
`_fetch_with_retry`, or any of the existing unit-test files.

---

## 4. Dependency changes (`pyproject.toml`)

### 4.1 Runtime dependencies

Add to the `[project] dependencies` array (`pyproject.toml:22`):

```toml
"starlette>=0.37",
"uvicorn[standard]>=0.30",
```

Rationale:

- `starlette` is the ASGI framework used by `StreamableHTTPSessionManager`'s
  example wiring. It is already a transitive dependency of `mcp[cli]`,
  but we depend on it directly so removing the `[cli]` extra later
  doesn't break us.
- `uvicorn[standard]` is the production ASGI server. The `[standard]`
  extra brings `httptools`, `websockets`, `uvloop` — needed for
  realistic throughput.

### 4.2 Optional extra (preferred — keeps stdio-only installs lean)

If we want to keep the default install minimal, move the two new deps
into a new optional extra and gate HTTP mode on it:

```toml
[project.optional-dependencies]
http = [
    "starlette>=0.37",
    "uvicorn[standard]>=0.30",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.4.0",
    "arquivo-pt-mcp[http]",   # dev installs everything
]
```

The CLI must then **lazy-import** `starlette` / `uvicorn` only when
`--transport http` is selected, and emit a clear error if the import
fails:

> `arquivo-pt-mcp http transport requires the 'http' extra. Install with: pip install 'arquivo-pt-mcp[http]'`

**Recommended:** ship the deps in core `[project] dependencies` (4.1)
for a smooth first cut; promoting to an optional extra later is
mechanical. Pick **one** of 4.1 or 4.2 — do not do both.

### 4.3 Pinned-or-not

Keep the lower bounds (`>=0.37`, `>=0.30`) consistent with the rest of
`pyproject.toml`. Do not add upper bounds.

---

## 5. New module: `src/arquivo_pt_mcp/http_app.py`

Pure factory module. **Imports the existing `server` object** from
`arquivo_pt_mcp` (do not redefine handlers). Public surface:

```python
def create_app(
    *,
    json_response: bool = True,
    stateless: bool = True,
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    enable_dns_rebinding_protection: bool = True,
) -> Starlette: ...
```

### 5.1 Wiring

1. Build a `TransportSecuritySettings` from the kwargs.
2. Build `StreamableHTTPSessionManager(app=server, json_response=...,
   stateless=..., security_settings=...)`.
3. Build a `lifespan` async context manager that wraps
   `session_manager.run()` (the SDK requires it — see
   `streamable_http_manager.py` docstring).
4. Mount routes:
   - `Mount("/mcp", app=session_manager.handle_request)` — that is
     `handle_request` *bound*; it has the `(scope, receive, send)`
     ASGI signature.
   - `Route("/healthz", health, methods=["GET"])` — returns
     `JSONResponse({"status": "ok", "tools": 5, "transport": "streamable-http"})`.
5. Return `Starlette(debug=False, routes=routes, lifespan=lifespan)`.

### 5.2 Defaults & rationale

| Setting | Default | Why |
|---|---|---|
| `json_response` | `True` | Every tool here is a single request → single response. SSE buys nothing for our workload and complicates clients/proxies. |
| `stateless` | `True` | Each request gets a fresh transport instance. Trivially horizontally scalable, no sticky sessions, no session cleanup. We don't use server-initiated notifications, prompts, or sampling, so we lose nothing. |
| `enable_dns_rebinding_protection` | `True` | Default in the SDK; keep it. |
| `allowed_hosts` | `[]` (any when binding loopback) | The CLI populates this when `--host 0.0.0.0`. |
| `allowed_origins` | `[]` | Same. |

### 5.3 Constants

Define in this module:

```python
MCP_PATH = "/mcp"
HEALTH_PATH = "/healthz"
```

Export both. Reference them from tests instead of hardcoding strings.

### 5.4 Caveat the executor must respect

`StreamableHTTPSessionManager` instances are **single-shot**: calling
`.run()` twice raises. Therefore `create_app()` must instantiate the
manager *inside* the function (not at module scope). One Starlette app
== one manager. This is enforced by tests in §7.1.

---

## 6. CLI module: `src/arquivo_pt_mcp/cli.py`

Use stdlib `argparse`. No third-party CLI dep.

### 6.1 Parser shape

```
arquivo-pt-mcp [--transport {stdio,http}]
               [--host HOST] [--port PORT] [--path PATH]
               [--json-response | --sse-response]
               [--stateful | --stateless]
               [--allowed-host HOST ...]
               [--allowed-origin ORIGIN ...]
               [--no-dns-rebinding-protection]
               [--log-level {critical,error,warning,info,debug}]
```

| Flag | Default | Env-var fallback |
|---|---|---|
| `--transport` | `stdio` | `ARQUIVO_PT_MCP_TRANSPORT` |
| `--host` | `127.0.0.1` | `ARQUIVO_PT_MCP_HOST` |
| `--port` | `8000` | `ARQUIVO_PT_MCP_PORT` (int) |
| `--path` | `/mcp` | `ARQUIVO_PT_MCP_PATH` |
| `--json-response` / `--sse-response` | json | `ARQUIVO_PT_MCP_RESPONSE_MODE` ∈ `{json,sse}` |
| `--stateful` / `--stateless` | stateless | `ARQUIVO_PT_MCP_STATEFUL` (bool) |
| `--allowed-host` (multi) | `[]` | `ARQUIVO_PT_MCP_ALLOWED_HOSTS` (comma-separated) |
| `--allowed-origin` (multi) | `[]` | `ARQUIVO_PT_MCP_ALLOWED_ORIGINS` (comma-separated) |
| `--no-dns-rebinding-protection` | off | — |
| `--log-level` | `info` | `ARQUIVO_PT_MCP_LOG_LEVEL` |

### 6.2 Validation

- If `--transport stdio` is selected, **all** HTTP-only flags must be
  silently ignored (do not error — common in scripts that always pass
  `--port`).
- If `--transport http` and `--host` is `0.0.0.0` (or any non-loopback
  address) **and** `allowed_hosts` is empty **and**
  `--no-dns-rebinding-protection` is *not* passed, **abort** with a
  helpful error: explain DNS-rebinding risk and tell the user to pass
  `--allowed-host`. Tested in §7.3.

### 6.3 `parse_argv(argv: list[str] | None = None) -> argparse.Namespace`

Pure function; no side effects. The dispatcher in `__init__.main()`
calls it.

---

## 7. Refactor `src/arquivo_pt_mcp/__init__.py`

### 7.1 Rename existing entry point

```python
async def _async_main_stdio() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
```

The body is identical to today's `_async_main` (`__init__.py:613`).
Just rename. Do **not** delete the old name yet — keep a thin alias
(`_async_main = _async_main_stdio`) for one release in case any
external script imports it. Mark the alias `# deprecated` in a
comment and remove it next release.

### 7.2 New HTTP entry point

```python
async def _async_main_http(args: argparse.Namespace) -> None:
    from arquivo_pt_mcp.http_app import create_app  # lazy

    app = create_app(
        json_response=(args.response_mode == "json"),
        stateless=args.stateless,
        allowed_hosts=args.allowed_hosts,
        allowed_origins=args.allowed_origins,
        enable_dns_rebinding_protection=not args.no_dns_rebinding_protection,
    )
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=True,
    )
    await uvicorn.Server(config).serve()
```

Uvicorn imported at the top of the function body to keep stdio-only
installs from importing it at module load.

### 7.3 New `main()` dispatcher

Replace the body at `__init__.py:608` with:

```python
def main() -> None:
    from arquivo_pt_mcp.cli import parse_argv  # lazy
    args = parse_argv()
    if args.transport == "stdio":
        asyncio.run(_async_main_stdio())
    else:
        asyncio.run(_async_main_http(args))
```

### 7.4 Remove the now-unused `__main__` block

`__init__.py:618` (`if __name__ == "__main__": main()`) keeps working.
No change.

### 7.5 Update module docstring

The header docstring (`__init__.py:1–20`) lists "five tools" — leave
that alone. Append one line: *"Servable over stdio (default) or
Streamable HTTP. See README for the latter."*

---

## 8. Tests

All new tests use `pytest-asyncio`'s auto mode (already configured in
`pyproject.toml:44`).

### 8.1 `tests/test_cli.py` (unit)

Cases (one assert each unless noted):

1. `parse_argv([])` → `transport == "stdio"`, all HTTP flags at defaults.
2. `parse_argv(["--transport", "http"])` → `host == "127.0.0.1"`, `port == 8000`.
3. `parse_argv(["--transport", "http", "--port", "9000"])` → port 9000.
4. `parse_argv(["--transport", "http", "--sse-response"])` → `response_mode == "sse"`.
5. `parse_argv(["--transport", "http", "--stateful"])` → `stateless is False`.
6. Env-var precedence: monkeypatch `ARQUIVO_PT_MCP_PORT=9001`, call
   `parse_argv(["--transport","http"])`, assert `port == 9001`. Then
   call `parse_argv(["--transport","http","--port","9002"])` and
   assert CLI wins (9002).
7. Public-bind guard: `parse_argv(["--transport","http","--host","0.0.0.0"])`
   raises `SystemExit` (argparse's error behaviour). Add
   `--allowed-host example.com` and assert it succeeds.

### 8.2 `tests/test_http_app.py` (unit, in-process ASGI)

Use `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` so we
do not need a port. The `lifespan="auto"` flag on `ASGITransport` runs
the lifespan context — confirm against `httpx` docs at execution time.

Cases:

1. **`/healthz` returns 200 JSON.**
   ```python
   async with create_app_lifespan() as app:
       async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as c:
           r = await c.get("http://test/healthz")
           assert r.status_code == 200
           assert r.json()["status"] == "ok"
   ```
2. **`POST /mcp` with an `initialize` JSON-RPC body returns a JSON
   response carrying `serverInfo.name == "arquivo-pt"`.** Use
   `Accept: application/json, text/event-stream` (the SDK requires
   both).
3. **`GET /mcp` with no session header returns 4xx** (the SDK rejects
   it). Pin the exact status code only after observing it during
   implementation — the test should assert `400 <= status < 500`.
4. **Two `create_app()` calls produce independent apps** — wire them
   both up in the same test, hit `/healthz` on each. Guards against
   the "single-shot" pitfall in §5.4.

### 8.3 `tests/test_http_smoke.py` (integration, real subprocess)

Marked `pytest.mark.integration` and gated on
`RUN_INTEGRATION=1`, exactly like `tests/test_stdio_smoke.py`.

Pattern, mirroring the stdio smoke test:

```python
import os, socket, subprocess, time, pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from tests.integration_fixtures import EXPECTED_TOOL_NAMES

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 to run streamable-http smoke test",
    ),
]
```

Test body:

1. Pick an ephemeral port:
   `s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()`.
2. `proc = subprocess.Popen(["arquivo-pt-mcp", "--transport", "http",
   "--port", str(port), "--log-level", "warning"])`.
3. Poll `GET http://127.0.0.1:{port}/healthz` (with `httpx`) until 200
   or 5 s timeout.
4. ```python
   async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
       async with ClientSession(read, write) as session:
           await session.initialize()
           result = await session.list_tools()
   ```
5. Assert `{t.name for t in result.tools} == EXPECTED_TOOL_NAMES`.
6. **Always** `proc.terminate(); proc.wait(timeout=5)` in a `finally`
   (use a context-manager helper to be safe).

### 8.4 No changes to existing tests

`tests/test_search.py`, `tests/test_image_search.py`,
`tests/test_list_versions.py`, `tests/test_snapshot.py`,
`tests/test_cache.py`, `tests/test_helpers.py`, `tests/test_models.py`,
`tests/test_retry.py`, `tests/test_integration.py`, and
`tests/test_stdio_smoke.py` are transport-agnostic and must remain
green unchanged.

---

## 9. CI, DevContainer, README, ROADMAP

### 9.1 CI (`.github/workflows/ci.yml`)

- The `test` job already runs `python -m pytest tests/ -v --tb=short`
  (line 35) → picks up `test_cli.py` and `test_http_app.py` automatically.
  No edit required for unit tests.
- The `integration` job (line ~58) currently runs
  `pytest tests/test_integration.py tests/test_stdio_smoke.py`. **Add**
  `tests/test_http_smoke.py` to the same line.
- Add a step **before** integration to install the HTTP extra:
  `pip install -e ".[dev,http]"` (only matters if §4.2 was chosen).

### 9.2 DevContainer (`.devcontainer/devcontainer.json`)

Add:

```json
"forwardPorts": [8000],
"portsAttributes": {
  "8000": {
    "label": "arquivo-pt-mcp (Streamable HTTP)",
    "onAutoForward": "silent"
  }
}
```

This lets a developer running `arquivo-pt-mcp --transport http` inside
the container hit it from the macOS host at `http://localhost:8000/mcp`.

### 9.3 README

Add a new section in **both** the Portuguese and English halves,
right after "Configuração" / "Configuration", titled **"Modo Remoto
(HTTP)" / "Remote mode (HTTP)"**. Content:

- One-liner explanation: the same five tools, served as a long-running
  process; useful for self-hosted deployments and for clients that
  prefer URLs over local commands.
- Quick start:
  ```bash
  arquivo-pt-mcp --transport http --host 127.0.0.1 --port 8000
  ```
- Client-side examples (mirror the stdio examples already in the
  README):
  - **Claude Desktop / Claude.ai connectors:** show the URL form
    `https://arquivo-pt-mcp.example.com/mcp`.
  - **Cursor:** `Type: SSE/HTTP`, URL as above.
- Security note: bind to loopback by default; if exposing publicly,
  put it behind a TLS-terminating reverse proxy (Caddy, nginx,
  Traefik) and pass `--allowed-host arquivo-pt-mcp.example.com`.
- Caches note: in HTTP mode the in-memory caches are shared across
  callers. arquivo.pt is a public archive so this has no privacy
  implication, but it does mean cache hit/miss patterns differ from
  stdio mode.

### 9.4 ROADMAP

If `ROADMAP.md` Milestone 5 mentions "Remote / hosted server" or
similar, tick it off. Otherwise add an entry under Milestone 5:

> - [x] **Streamable HTTP transport** — `arquivo-pt-mcp --transport http`
>   serves the same tools as a long-running ASGI process. See
>   `temp/action-plans/streamable-http-transport.md`.

(Verbatim — keep the cross-reference.)

---

## 10. Follow-ups (explicitly not in this plan)

In rough priority order:

1. **Authentication.** Use `mcp.server.auth` to add OAuth-style
   protection. arquivo.pt itself is open, but a public HTTP MCP
   endpoint is rate-limit / abuse exposure for the operator.
2. **Docker image.** `Dockerfile` + `docker-compose.yml` + GHCR
   publish. Fits Milestone 5 of the existing roadmap.
3. **Persistent / shared cache.** Replace `cachetools.TTLCache` with
   Redis when running multi-replica.
4. **Observability.** OpenTelemetry traces around `_fetch_with_retry`,
   structured logging, Prometheus `/metrics`.
5. **Resumable streams.** Pass an `EventStore` implementation to
   `StreamableHTTPSessionManager` so disconnected clients can resume
   long-running tool calls. Only matters if we add long-running tools
   later (`save_page_now` is a candidate — see ROADMAP Milestone 4).
6. **Multi-tenancy / per-client rate limiting.** Currently a single
   global limiter would suffice; add it before exposing publicly.

---

## 11. Verification checklist

The executor agent must run these (inside the DevContainer:
`docker exec -w /workspaces/Python-space/arquivo-pt-mcp interesting_saha …`)
and confirm each passes before declaring done:

```bash
# 1. Lint stays clean
ruff check src/ tests/
ruff format --check src/ tests/

# 2. All existing unit tests still pass
pytest tests/ -v --tb=short

# 3. New CLI / HTTP-app unit tests pass
pytest tests/test_cli.py tests/test_http_app.py -v

# 4. Stdio still boots end-to-end
RUN_INTEGRATION=1 pytest tests/test_stdio_smoke.py -v

# 5. New HTTP smoke test passes against a real subprocess
RUN_INTEGRATION=1 pytest tests/test_http_smoke.py -v

# 6. Manual sanity check
arquivo-pt-mcp --transport http --port 8765 &
SERVER_PID=$!
sleep 1
curl -fsS http://127.0.0.1:8765/healthz | python -m json.tool
kill $SERVER_PID

# 7. Default behaviour unchanged
echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"x","version":"0"}},"id":1}' \
  | arquivo-pt-mcp >/tmp/init.out
grep -q '"name":"arquivo-pt"' /tmp/init.out
```

(Note: step 7 is approximate — the stdio handshake actually requires
multiple framed messages. The real assertion lives in
`tests/test_stdio_smoke.py`. Step 7 is just a smell test.)

---

## 12. Pitfalls the executor must respect

1. **`StreamableHTTPSessionManager.run()` is single-shot.** Reusing an
   instance across requests/apps raises. Always construct a fresh one
   inside `create_app()`. Tested in §8.2 case 4.
2. **The lifespan must wrap `manager.run()`.** Calling
   `handle_request` without an active task group raises
   `RuntimeError("Task group is not initialized.")`. The Starlette
   `lifespan` parameter is the canonical fix; do not call
   `manager.run()` ad-hoc.
3. **The `Accept` header on `POST /mcp` must include both
   `application/json` and `text/event-stream`** for SDK clients to be
   happy. Build this into the integration smoke test fixture, not the
   server.
4. **Do not import `starlette` or `uvicorn` at the top of
   `__init__.py`.** Stdio users on a minimal install must not pay for
   web-server imports. Lazy-import inside `_async_main_http` /
   `http_app`.
5. **CLI `--port` collides with no existing flag** — but `--host`
   collides conceptually with `httpx`'s host parameter inside the
   tool handlers. They are independent (one is the bind address, one
   is the upstream API). Keep them mentally separated when writing
   the README.
6. **The DevContainer port 8000 forward** only works if uvicorn binds
   to `0.0.0.0` *inside* the container. Document in the README that
   for in-container use the dev should pass
   `--host 0.0.0.0 --allowed-host localhost --allowed-host 127.0.0.1`.
   The default `127.0.0.1` is correct for production but
   counter-intuitive in a container.
7. **`server` is a *module-level singleton*** in
   `__init__.py:57`. Having multiple `StreamableHTTPSessionManager`s
   share it is fine (they just all dispatch to the same handlers),
   but **two managers on the same `server` cannot both be `.run()`ing
   in the same process** because `Server.run` is itself a one-shot per
   transport pair. In practice we have exactly one manager per
   process, so this is a non-issue — flagging it because it would bite
   anyone who tried to run two HTTP listeners in one process.

---

*Plan author note for the executor: work the sections in order. After
each section, run `ruff check` and the unit-test subset relevant to
that section before moving on. Do not bundle §5 + §7 + §8 into one
commit — at minimum keep `pyproject.toml + http_app.py + cli.py` in
one commit and the `__init__.py` refactor + tests in a second.*
