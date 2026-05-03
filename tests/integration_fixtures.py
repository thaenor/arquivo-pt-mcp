"""Constants used by integration tests against the live arquivo.pt API.

Single source of truth so external-state breakage only needs one fix.
"""

KNOWN_ARCHIVED_URL = "publico.pt"
"""A major Portuguese newspaper archived since 1996; safe to assume many captures."""

KNOWN_TIMESTAMP_2010 = "20100601000000"
"""A point in time we expect to have a publico.pt capture nearby."""

NEVER_ARCHIVED_URL = "https://this-was-never-archived-zzz999.example.com/"
"""example.com subdomain that's extremely unlikely to be in any web archive."""

NONSENSE_QUERY = "zxqwfyvbnmplkjhgfdsa12345"
"""Random characters; expected to return zero search results."""

EXPECTED_TOOL_NAMES = {
    "search",
    "image_search",
    "list_versions",
    "get_snapshot",
    "extract_text",
    "get_screenshot",
}
"""The complete set of tools the MCP server should expose."""
