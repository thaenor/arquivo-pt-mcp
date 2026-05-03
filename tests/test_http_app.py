"""Unit tests for the Starlette ASGI application factory."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from arquivo_pt_mcp.http_app import MCP_PATH, create_app


@pytest.fixture
def client():
    app = create_app(enable_dns_rebinding_protection=False)
    with TestClient(app) as c:
        yield c


def test_healthz_returns_ok(client):
    """GET /healthz returns 200 JSON with expected fields."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["transport"] == "streamable-http"


def test_mcp_initialize_post(client):
    """POST /mcp/ with a valid MCP initialize payload returns serverInfo."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream"}
    response = client.post(f"{MCP_PATH}/", json=payload, headers=headers)
    assert 200 <= response.status_code < 300
    data = response.json()
    assert data.get("jsonrpc") == "2.0"
    result = data.get("result", {})
    assert result.get("serverInfo", {}).get("name") == "arquivo-pt"


def test_mcp_get_missing_session_returns_4xx(client):
    """GET /mcp/ without a session header is a client error."""
    response = client.get(f"{MCP_PATH}/")
    assert 400 <= response.status_code < 500


def test_create_app_independence():
    """Two calls to create_app produce independent apps that both serve healthz."""
    app1 = create_app(enable_dns_rebinding_protection=False)
    app2 = create_app(enable_dns_rebinding_protection=False)
    assert app1 is not app2

    with TestClient(app1) as c1:
        r1 = c1.get("/healthz")
        assert r1.status_code == 200

    with TestClient(app2) as c2:
        r2 = c2.get("/healthz")
        assert r2.status_code == 200
