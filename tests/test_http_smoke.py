"""End-to-end streamable HTTP smoke test: launches the installed `arquivo-pt-mcp`
console script in HTTP mode and speaks MCP over the streamable HTTP transport.

Proves the server entry point boots, registers the right tools, and answers
JSON-RPC over Streamable HTTP. No live arquivo.pt API calls — this tests the
MCP plumbing, not the upstream API.

Bundled under the `integration` marker / `RUN_INTEGRATION=1` gate so it runs
in the same nightly job as the live-API tests and stays out of the fast local
unit-test loop.
"""

import os
import socket
import subprocess
import time

import httpx
import pytest
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


async def test_http_lists_tools():
    """Spawn the HTTP server, initialize, and verify list_tools returns the expected set."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    proc = subprocess.Popen(
        [
            "arquivo-pt-mcp",
            "--transport",
            "http",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ]
    )

    start = time.time()
    health_url = f"http://127.0.0.1:{port}/healthz"
    while time.time() - start < 5:
        try:
            r = httpx.get(health_url, timeout=1)
            if r.status_code == 200:
                break
        except Exception:  # noqa: S112
            pass
        time.sleep(0.1)
    else:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Server did not become healthy within 5s")

    try:
        mcp_url = f"http://127.0.0.1:{port}/mcp"
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

        names = {t.name for t in result.tools}
        assert names == EXPECTED_TOOL_NAMES, f"unexpected tool set: {names}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
