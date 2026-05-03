"""End-to-end stdio smoke test: launches the installed `arquivo-pt-mcp` console
script as a subprocess and speaks MCP over stdio.

Proves the server entry point boots, registers the right tools, and answers
JSON-RPC over the stdio transport. No live arquivo.pt API calls — this is
about the MCP plumbing, not the upstream API.

Bundled under the `integration` marker / `RUN_INTEGRATION=1` gate so it runs
in the same nightly job as the live-API tests and stays out of the fast local
unit-test loop.
"""

import os

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.integration_fixtures import EXPECTED_TOOL_NAMES

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 to run stdio smoke test",
    ),
]


async def test_stdio_lists_tools():
    """Spawn the server, initialize, and verify list_tools returns the expected set."""
    params = StdioServerParameters(command="arquivo-pt-mcp")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = {t.name for t in result.tools}
    assert names == EXPECTED_TOOL_NAMES, f"unexpected tool set: {names}"


async def test_stdio_tool_schemas_have_required_fields():
    """Every tool advertises an inputSchema with at least the obvious required field."""
    params = StdioServerParameters(command="arquivo-pt-mcp")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    by_name = {t.name: t for t in result.tools}
    assert by_name["search"].inputSchema["required"] == ["query"]
    assert by_name["image_search"].inputSchema["required"] == ["query"]
    assert by_name["list_versions"].inputSchema["required"] == ["url"]
    assert by_name["get_snapshot"].inputSchema["required"] == ["url"]
    assert by_name["extract_text"].inputSchema["required"] == ["url"]
    assert by_name["get_screenshot"].inputSchema["required"] == ["url"]
