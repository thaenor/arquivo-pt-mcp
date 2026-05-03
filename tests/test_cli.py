"""Unit tests for the CLI argument parser."""

from __future__ import annotations

import pytest

from arquivo_pt_mcp.cli import parse_argv


def test_parse_argv_defaults_stdio():
    """No args → transport == 'stdio', all HTTP flags at defaults."""
    args = parse_argv([])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"
    assert args.json_response is True
    assert args.sse_response is False
    assert args.stateless is True
    assert args.stateful is False
    assert args.allowed_host == []
    assert args.allowed_origin == []
    assert args.no_dns_rebinding_protection is False
    assert args.log_level == "info"


def test_parse_argv_http_defaults():
    """--transport http uses default host and port."""
    args = parse_argv(["--transport", "http"])
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.transport == "http"


def test_parse_argv_http_custom_port():
    """Custom port is respected."""
    args = parse_argv(["--transport", "http", "--port", "9000"])
    assert args.port == 9000


def test_parse_argv_sse_response():
    """--sse-response disables json_response."""
    args = parse_argv(["--transport", "http", "--sse-response"])
    assert args.json_response is False


def test_parse_argv_stateful():
    """--stateful disables stateless."""
    args = parse_argv(["--transport", "http", "--stateful"])
    assert args.stateless is False
    assert args.stateful is True


def test_env_var_precedence(monkeypatch):
    """Env vars set defaults; CLI arguments override env vars."""
    monkeypatch.setenv("ARQUIVO_PT_MCP_PORT", "9001")
    args = parse_argv(["--transport", "http"])
    assert args.port == 9001

    args2 = parse_argv(["--transport", "http", "--port", "9002"])
    assert args2.port == 9002


def test_public_bind_guard():
    """Binding to a non-loopback address without allowed_hosts raises SystemExit."""
    with pytest.raises(SystemExit):
        parse_argv(["--transport", "http", "--host", "0.0.0.0"])

    # With --allowed-host the guard passes.
    args = parse_argv(["--transport", "http", "--host", "0.0.0.0", "--allowed-host", "example.com"])
    assert args.host == "0.0.0.0"
    assert args.allowed_host == ["example.com"]
