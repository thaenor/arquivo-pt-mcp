# Review — Streamable HTTP Transport Wiring

**Commit reviewed:** `ce03932` — *feat: wire Streamable HTTP dispatcher into main entry point (#8)*
**Plan:** [`action-plans/streamable-http-transport.md`](./streamable-http-transport.md)
**Reviewer:** Claude (Opus 4.7)
**Date:** 2026-05-03

---

## 1. Summary

The commit lands the bulk of §5–§9 of the plan. Stdio remains the default and untouched; a new `--transport http` path stands up a Starlette/uvicorn ASGI app around `StreamableHTTPSessionManager`, with health endpoint, DNS-rebinding guard, CORS, env-var fallbacks, and three new test files. The implementation is faithful to the plan's architecture (single-shot manager, lazy imports, lifespan-wrapped manager, `/mcp` + `/healthz` routes) and meaningfully exercised by tests.

It also has a few real issues that should not ship as-is:

- **`--path` is dead code** — accepted on the CLI but never affects the mount.
- **`cli.main()` is dead code** — duplicates the dispatcher in `__init__.main()` and is never wired as an entry point.
- **`server._tool_cache`** — `/healthz` reaches into a private SDK attribute behind a bare `except Exception`.
- **List-args (`--allowed-host`, `--allowed-origin`) merge with env vars** instead of overriding them — inconsistent with how `--port` and `--host` behave.
- **Default-arg booleans for `--stateless` and `--json-response`** are awkward (always `True`); the post-processing makes it work but the CLI surface is misleading.

None are blockers for the existing functionality (stdio is unchanged; basic HTTP works), but the dead-code paths in particular should be removed or wired before they confuse future contributors.

---

## 2. What was changed

| Area | Change | Verdict |
|---|---|---|
| `pyproject.toml` | Added `starlette>=0.37`, `uvicorn[standard]>=0.30` to core deps | OK — matches plan §4.1 (recommended path over the optional extra) |
| `src/arquivo_pt_mcp/__init__.py` | Renamed `_async_main` → `_async_main_stdio`, added `_async_main_http`, dispatcher in `main()` calling `cli.parse_argv()`, kept `_async_main` alias | OK — faithful to plan §7 |
| `src/arquivo_pt_mcp/cli.py` | New — argparse parser with env fallbacks, DNS-rebinding guard, plus a (dead) `main()` | Mostly OK; see §4 below |
| `src/arquivo_pt_mcp/http_app.py` | New — `create_app()` factory, `run_uvicorn()` helper, `/mcp` + `/healthz`, lifespan, CORS | OK; see §4 below |
| `tests/test_cli.py` | 7 unit tests — defaults, env precedence, DNS guard, etc. | OK |
| `tests/test_http_app.py` | 4 tests — healthz, initialize POST, GET-without-session, app independence | OK |
| `tests/test_http_smoke.py` | Integration test — spawns subprocess, talks MCP over `streamablehttp_client` | OK; see §4 below |
| `.github/workflows/ci.yml` | Added `tests/test_http_smoke.py` to integration step | OK |
| `README.md` | New "Modo Remoto" / "Remote mode" sections (PT + EN) | OK; minor polish suggested |
| `ROADMAP.md` | Ticked off Streamable HTTP under Milestone 5 | OK |

**Plan items not landed in this commit (acceptable — flagged for follow-up):**

- DevContainer `forwardPorts: [8000]` (plan §9.2) — not added. The README still binds to `127.0.0.1` by default, so the host can't reach an in-container server without either `--host 0.0.0.0` (gated by the new DNS-rebinding guard) or a port forward.
- `EXPECTED_HEALTHZ_BODY` constant in `tests/integration_fixtures.py` (plan §3 line 103) — not added. Smoke test asserts `status_code == 200` only, no body shape assertion. Acceptable.

---

## 3. What works well

- **Lazy imports.** `starlette` and `uvicorn` are only imported when `--transport http` is taken (`__init__.py:978`, `http_app.py` body), preserving the cheap stdio cold-start. Per plan §12 pitfall #4.
- **Single-shot manager handled correctly.** `StreamableHTTPSessionManager` is constructed *inside* `create_app()` (`http_app.py:46`), and the lifespan wraps `session_manager.run()` (`http_app.py:74`). Tested end-to-end by `test_http_app.py::test_create_app_independence`. Per plan §5.4 / §12 pitfall #1, #2.
- **DNS-rebinding guard is real and tested.** Public bind without `--allowed-host` raises `SystemExit` (`cli.py:155`, `tests/test_cli.py::test_public_bind_guard`). Per plan §6.2 / §12 pitfall #6.
- **Env-var precedence is right for scalars.** `ARQUIVO_PT_MCP_PORT` sets default; `--port` overrides. Tested in `test_cli.py::test_env_var_precedence`.
- **Smoke test mirrors the stdio one.** Same `RUN_INTEGRATION=1` gate, same `EXPECTED_TOOL_NAMES` import, same subprocess+terminate pattern. Tool-set assertion is the right check for an HTTP-plumbing test (it verifies the dispatcher, not the upstream API).
- **README documents the operational caveat** about caches being shared in HTTP mode (plan §9.3) and the reverse-proxy advice for public exposure.

---

## 4. Issues found

### 4.1 (bug) `--path` is silently ignored

`cli.py:65–69` defines `--path` (default `/mcp`, env `ARQUIVO_PT_MCP_PATH`), but it's never threaded into the active entry point:

- `__init__._async_main_http()` calls `create_app(...)` with no path arg.
- `create_app()` mounts the manager at the module constant `MCP_PATH = "/mcp"` (`http_app.py:92`), not at any caller-supplied path.
- `cli.run_uvicorn()` accepts `path` but doesn't forward it to `create_app()` either.

So a user who runs `arquivo-pt-mcp --transport http --path /custom-mcp` gets exactly the same `POST /mcp` endpoint, with no warning. This is a misleading API.

**Fix options (pick one):**

1. **Wire it through.** Add `path: str = "/mcp"` to `create_app()`, use it in `Mount(path, ...)`. Pass `args.path` from `_async_main_http`.
2. **Drop the flag.** If we don't actually want a configurable path (the README and `.mcp.json` examples all hardcode `/mcp`), remove `--path` and `ARQUIVO_PT_MCP_PATH` from `cli.py` and the plan.

Either is fine; option 1 matches the spirit of the plan §6.1.

### 4.2 (bug / dead code) `cli.main()` is unreachable and partially diverges from the real entry point

Two `main()` functions exist:

- `arquivo_pt_mcp:main` — registered in `pyproject.toml:38` as the `arquivo-pt-mcp` console script. This is what users hit. It dispatches via `_async_main_stdio()` / `_async_main_http()` using `uvicorn.Server(config).serve()`.
- `arquivo_pt_mcp.cli:main` — never registered, not imported elsewhere. It re-dispatches: stdio → calls `__init__.main()` (which would re-parse argv and re-enter cli.main? no — it goes through __init__.main this time, fine but circular-looking); http → calls `run_uvicorn()` which uses `uvicorn.run(...)` (sync) instead of `Server.serve()` (async).

The two HTTP startup paths are functionally equivalent but diverge in non-trivial ways (sync vs async runner; `run_uvicorn` separately handles `log_config`, `access_log` is `False` in `__init__` but default-True in `run_uvicorn`). Maintaining two ways to start the server invites drift.

**Fix:** delete `cli.main()` and `cli.run_uvicorn()`. Keep `cli.parse_argv()`, the helpers, and the module's docstring. The dispatcher in `__init__.main()` is the only path we need.

If we want `python -m arquivo_pt_mcp.cli` to also work, replace `cli.main()` with a one-liner: `from arquivo_pt_mcp import main; main()`.

### 4.3 (fragile) `/healthz` reaches into `server._tool_cache`

`http_app.py:58–62`:

```python
try:
    tool_count = len(server._tool_cache)
except Exception:
    tool_count = 0
```

Two problems:

1. **Private attribute access.** `_tool_cache` is an SDK internal. The next `mcp` upgrade can rename or remove it, and the broad `except Exception` will silently report `0` — a green health check that's actually lying.
2. **No coverage.** None of the tests verifies the count is non-zero. `test_healthz_returns_ok` only asserts `isinstance(data["tools"], int)`, which passes even when the catch fires.

**Fix:** count tools via the public path. The handler at `__init__.py:619` (`@server.list_tools()`) is what returns the canonical list. Either:

- Cache the expected tool count from the handler at module load (we know it's 5, and it's enumerated in `tests/integration_fixtures.py:EXPECTED_TOOL_NAMES`).
- Or just drop the `tools` field from `/healthz` — `{"status": "ok", "transport": "streamable-http"}` is enough for a probe. Push tool enumeration to clients via `list_tools()` where it belongs.

### 4.4 (inconsistency) List args merge with env vars; scalar args override

`cli.py:99–101`:

```python
parser.add_argument(
    "--allowed-host",
    action="append",
    default=_env_list("ARQUIVO_PT_MCP_ALLOWED_HOSTS"),
    ...
)
```

With `action="append"`, argparse appends to (not replaces) the default list. So if `ARQUIVO_PT_MCP_ALLOWED_HOSTS=foo.com,bar.com` and the user passes `--allowed-host baz.com`, you get `["foo.com", "bar.com", "baz.com"]`. Compare to `--port`, where CLI cleanly overrides env (per `test_env_var_precedence`).

This may be desired (additive composition for trust lists), but it isn't documented and isn't symmetric with the rest of the parser. Plan §6 doesn't specify either way.

**Fix options:**

1. **Document and keep.** Add a one-line README note: "list-valued env vars are merged with CLI flags".
2. **Make it consistent.** Use `default=None`, then post-process: `args.allowed_host = args.allowed_host or _env_list("ARQUIVO_PT_MCP_ALLOWED_HOSTS") or []`.

I'd lean toward option 2 for symmetry; option 1 is fine if the merge behavior is intentional.

### 4.5 (smell) `--stateless` and `--json-response` defaults are misleading

`cli.py:84–88`:

```python
parser.add_argument(
    "--stateless",
    action="store_true",
    default=True,
    help="Enable stateless sessions (default).",
)
```

`action="store_true"` with `default=True` means the flag is **always** True after parsing — there's no way to set it False from the CLI. The post-processing block (`if args.stateful: args.stateless = False`) compensates, but reading the parser definition in isolation is misleading. Same shape for `--json-response`/`--sse-response`.

**Fix:** use a mutually exclusive group, as plan §6.1 actually wrote (`[--json-response | --sse-response]`, `[--stateful | --stateless]`):

```python
mode = parser.add_mutually_exclusive_group()
mode.add_argument("--json-response", dest="response_mode", action="store_const", const="json")
mode.add_argument("--sse-response",  dest="response_mode", action="store_const", const="sse")
parser.set_defaults(response_mode="json")
```

argparse will then reject `--json-response --sse-response` with a clean error message instead of silently letting `--sse-response` win.

### 4.6 (minor) `_is_loopback` duplicated

Defined once in `cli.py:38–39` and again identically in `http_app.py:21–22`. The `http_app.py` copy isn't used anywhere — `create_app()` doesn't run the guard (the guard lives in the CLI). Drop the unused copy from `http_app.py`.

### 4.7 (minor) Missing CI step from plan §9.1

Plan §9.1 says: *"Add a step before integration to install the HTTP extra: `pip install -e \".[dev,http]\"` (only matters if §4.2 was chosen)."* The implementation chose §4.1 (deps in core), so this step is correctly omitted. **No action needed**, but worth confirming the integration job's `pip install -e ".[dev]"` does pull `starlette`/`uvicorn` transitively from core deps. (It does — `[dev]` doesn't shadow the core `dependencies` array.)

### 4.8 (minor) DevContainer `forwardPorts` not added

Plan §9.2 calls for `"forwardPorts": [8000]` in `.devcontainer/devcontainer.json`. Not in this commit. Anyone running the HTTP server inside the DevContainer to reach it from the macOS host will need to either:

- Edit devcontainer.json themselves and rebuild, or
- Bind to `0.0.0.0` and pass `--allowed-host` (which the README already documents).

Not blocking; consider doing this in a follow-up if developers complain.

---

## 5. Suggestions (non-blocking)

- **README — show the public-bind invocation.** The English/Portuguese sections mention `--allowed-host <hostname>` for public exposure, but don't show a complete command. Consider adding:
  ```bash
  arquivo-pt-mcp --transport http --host 0.0.0.0 --allowed-host arquivo-pt-mcp.example.com
  ```
  immediately after the reverse-proxy note. This matches what the DNS-rebinding guard actually requires.

- **`tests/test_http_app.py::test_mcp_initialize_post`** uses `client.post(f"{MCP_PATH}/", ...)` with a trailing slash. Worth confirming both `/mcp` and `/mcp/` are expected to work — Starlette `Mount` is somewhat sensitive to trailing slashes. If it must be `/mcp/`, document it in the README; if both work, add a test for the no-slash case.

- **`server.py`** docstring update from plan §3 ("update the docstring to mention both transports") doesn't appear to have been done. Tiny but worth catching.

- **Smoke test cleanup.** `proc.terminate(); proc.wait(timeout=5)` in `finally` is right, but if `terminate()` is slow (`uvicorn` graceful shutdown can hang on lingering connections), the test may block CI. Consider `proc.kill()` after a short wait, or pass `--lifespan off` to uvicorn for the test.

- **Document the dispatcher contract.** `__init__.main()` calls `cli.parse_argv()` which in turn errors out (`SystemExit`) on bad args. That's fine, but a one-line comment in `__init__.main()` saying "exits on argparse errors" prevents future drift.

---

## 6. Verification status

I did **not** execute the plan §11 verification suite as part of this review (no DevContainer commands run). To close the loop, the executor should run, inside the DevContainer:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
pytest tests/ -v --tb=short
RUN_INTEGRATION=1 pytest tests/test_stdio_smoke.py tests/test_http_smoke.py -v
arquivo-pt-mcp --transport http --port 8765 &
SERVER_PID=$!
sleep 1
curl -fsS http://127.0.0.1:8765/healthz | python -m json.tool
kill $SERVER_PID
```

Static review of the diff suggests all of the above will pass as-written. The four issues in §4 are correctness/maintainability concerns, not test failures.

---

## 7. Recommended follow-up commits

Suggested grouping, in priority order:

1. **Fix `--path`** — either wire it through `create_app(path=...)` and `_async_main_http`, or remove the flag. (§4.1)
2. **Delete `cli.main()` and `cli.run_uvicorn()`** — single source of truth for HTTP startup. (§4.2)
3. **Replace `server._tool_cache` access in `/healthz`** — drop the field or compute it from a public path. (§4.3)
4. **Make list-arg env precedence consistent with scalars**, or document the merge behavior. (§4.4)
5. **Use `add_mutually_exclusive_group()` for `--json-response`/`--sse-response` and `--stateful`/`--stateless`.** (§4.5)
6. *(optional)* DevContainer port forward + `server.py` docstring touch-up. (§4.8, §5)

Each is a few lines and independently mergeable.
