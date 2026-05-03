# CLAUDE.md

This file describes how Claude (or other MCP-capable agents) should work with the **`arquivo-pt-mcp`** repository.

---

## High-level behavior

- Treat this project as a **Model Context Protocol server** for **[Arquivo.pt](https://arquivo.pt)**, the Portuguese Web Archive.[cite:3]
- Prefer using the existing MCP tools (`search`, `image_search`, `list_versions`, `get_snapshot`, `extract_text`, `get_screenshot`) instead of re-implementing HTTP calls to Arquivo.pt.
- When a user wants to query archived Portuguese web content, route those tasks through this MCP server rather than calling the Arquivo.pt API directly.[cite:3]

---

## Dev environment & containers

- There is a **VSCode Dev Container** configured for this project. When running shell commands that modify code, dependencies, or run tests, assume they should be executed **inside the dev container**.
- Only **Git operations** (e.g. `git status`, `git commit`, `git push`, `git rebase`) should be run on the **host macOS machine**, not inside the container (unless the user explicitly says otherwise).
- When giving instructions, make this workflow explicit, for example:
  - "Open the repository in VSCode and `Reopen in Container`."
  - "Then run `uv sync --extra dev` inside the container."
  - "Run `git status` on the host terminal before committing."

If you need to describe how to get a shell inside the running dev container, use wording like:

```bash
# On the host (macOS), from the repo root
# VSCode will usually handle this automatically, but conceptually:
# 1. Start the Dev Container via VSCode
# 2. Open a terminal that is attached to the container

# Once you are inside the container shell, run project commands there
uv sync --extra dev
pytest -q
```

Do **not** suggest running Docker or `docker exec` manually unless the user explicitly wants low-level container operations; VSCode normally manages the Dev Container lifecycle.

---

## Key commands (inside container)

Unless the user has a different preference, assume that all the following commands are executed **inside the dev container shell**:

- Install dependencies for development:

  ```bash
  uv sync --extra dev
  ```

- Run tests:

  ```bash
  pytest -q
  pytest --cov=arquivo_pt_mcp
  ```

- Run integration tests against the live Arquivo.pt API (only when requested):

  ```bash
  RUN_INTEGRATION=1 pytest -m integration -v
  ```

- Lint and format:

  ```bash
  ruff check src tests
  ruff format src tests
  ```

These commands reflect the project configuration in `pyproject.toml` and `README.md`.[cite:3][cite:9]

---

## Host-only operations (macOS)

On the **host machine**, outside of the container:

- Run all **Git** commands:

  ```bash
  git status
  git diff
  git add ...
  git commit -m "..."
  git push
  ```

- Manage branches, tags, and GitHub-related operations (e.g. `gh pr create`, `gh pr checkout`) using the host environment, unless the user explicitly says they prefer doing this from inside the container.

When providing step-by-step instructions, always keep this separation clear: **code and tooling inside the container, git on the host**.

---

## CLI tools and skills

This project is intended to be used from LLM agents with **MCP support**, as well as locally from the command line.[cite:3]

When suggesting tooling for local workflows:

- Prefer **`uv`** as the Python package manager and runner, as used in the README:

  ```bash
  uv run arquivo-pt-mcp
  uv add arquivo-pt-mcp
  ```

- Ensure the following CLIs are available in examples and instructions when appropriate:
  - **`hf`** — Hugging Face CLI (for integration with Hugging Face Spaces or models).
  - **`gh`** — GitHub CLI (for managing releases, PRs, workflows).

If a user asks how to set these up, you can suggest (on macOS Homebrew-based systems):

```bash
brew install gh
pip install --upgrade "huggingface_hub[cli]"
```

Do not assume these tools are installed inside the dev container unless the Docker/DevContainer config explicitly indicates so; when needed, include installation steps in the container as well.

---

## Project structure notes

Useful files and directories for Claude to know about:

- `src/arquivo_pt_mcp/__init__.py` — main MCP server implementation and tool definitions.[cite:8]
- `src/arquivo_pt_mcp/cli.py` — CLI entry point used by `arquivo-pt-mcp` console script.[cite:8][cite:9]
- `src/arquivo_pt_mcp/http_app.py` — HTTP server implementation for `--transport http` mode.[cite:6][cite:8]
- `src/arquivo_pt_mcp/models.py` — Pydantic models and validation for inputs/outputs.[cite:8][cite:9]
- `src/arquivo_pt_mcp/server.py` — MCP server wiring / startup helpers.[cite:8]
- `tests/` — unit and integration tests.[cite:2][cite:9]
- `.github/workflows/ci.yml` — CI pipeline for tests, linting, and integration tests.[cite:5]
- `.github/workflows/publish.yml` — publishing to PyPI.
- `.github/workflows/huggingface.yml` — workflow(s) related to Hugging Face deployments or spaces.[cite:5]
- `Dockerfile` — container image that runs `arquivo-pt-mcp` in HTTP mode, currently used for hosting (e.g. on Hugging Face Spaces).[cite:6]

When editing code, prefer small, focused changes, and add or update tests in `tests/` accordingly.

---

## Running the MCP server

Inside the container (or any Python environment with the project installed):

- Local MCP CLI mode (used by Claude Desktop / Cursor when configured with `command`):

  ```bash
  uv run arquivo-pt-mcp
  ```

- HTTP transport mode (for remote / streamable setups):

  ```bash
  arquivo-pt-mcp --transport http --host 127.0.0.1 --port 8000
  ```

These are the same commands described in `README.md`; prefer to reference them instead of inventing new ones.[cite:3]

---

## How Claude should use this server

When a user question involves **Portuguese web history** or content that likely exists in Arquivo.pt, Claude should:

1. Prefer using the MCP tools provided by this server.
2. Choose the most appropriate tool based on the task:
   - `search` / `image_search` for broad queries.
   - `list_versions` when the user cares about how a URL changes over time.
   - `get_snapshot` when the user wants a specific timestamp.
   - `extract_text` when the user wants readable content without HTML noise.
   - `get_screenshot` when the visual layout of the page matters.
3. Be explicit about any limitations of the underlying Arquivo.pt APIs (e.g. rate limits, intermittent network issues) and gracefully handle errors as described in the tests and README.[cite:3][cite:9]

Claude should avoid scraping arbitrary websites directly when the same content is available via Arquivo.pt, particularly for historical snapshots, and should respect the semantics of the provided tools.
