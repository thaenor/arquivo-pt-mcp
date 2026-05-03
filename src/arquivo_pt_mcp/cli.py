"""CLI argument parser for arquivo-pt-mcp transport selection."""

from __future__ import annotations

import argparse
import os


def _env_bool(name: str) -> bool | None:
    val = os.environ.get(name)
    if val is None:
        return None
    return val.lower() in ("1", "true", "yes", "on")


def _env_str(name: str) -> str | None:
    return os.environ.get(name)


def _env_int(name: str) -> int | None:
    val = os.environ.get(name)
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _env_list(name: str) -> list[str] | None:
    val = os.environ.get(name)
    if val is None:
        return None
    return [v.strip() for v in val.split(",") if v.strip()]


def _is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost")


def parse_argv(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments with environment-variable fallbacks."""
    parser = argparse.ArgumentParser(prog="arquivo-pt-mcp")

    # Transport
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=_env_str("ARQUIVO_PT_MCP_TRANSPORT") or "stdio",
        help="Transport protocol (default: stdio). Env: ARQUIVO_PT_MCP_TRANSPORT",
    )

    # HTTP server options
    parser.add_argument(
        "--host",
        default=_env_str("ARQUIVO_PT_MCP_HOST") or "127.0.0.1",
        help="Bind host for HTTP transport. Env: ARQUIVO_PT_MCP_HOST",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_env_int("ARQUIVO_PT_MCP_PORT") or 8000,
        help="Bind port for HTTP transport. Env: ARQUIVO_PT_MCP_PORT",
    )
    parser.add_argument(
        "--path",
        default=_env_str("ARQUIVO_PT_MCP_PATH") or "/mcp",
        help="HTTP route mount path. Env: ARQUIVO_PT_MCP_PATH",
    )

    # Response mode (mutually exclusive)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--json-response",
        dest="response_mode",
        action="store_const",
        const="json",
        help="Use JSON response mode for Streamable HTTP (default).",
    )
    mode.add_argument(
        "--sse-response",
        dest="response_mode",
        action="store_const",
        const="sse",
        help="Use SSE response mode for Streamable HTTP.",
    )
    parser.set_defaults(response_mode="json")

    # Stateful / Stateless (mutually exclusive)
    stateful_env = _env_bool("ARQUIVO_PT_MCP_STATEFUL")
    default_session = "stateful" if stateful_env else "stateless"
    session = parser.add_mutually_exclusive_group()
    session.add_argument(
        "--stateful",
        dest="session_mode",
        action="store_const",
        const="stateful",
        help="Enable stateful sessions. Env: ARQUIVO_PT_MCP_STATEFUL",
    )
    session.add_argument(
        "--stateless",
        dest="session_mode",
        action="store_const",
        const="stateless",
        help="Enable stateless sessions (default).",
    )
    parser.set_defaults(session_mode=default_session)

    # Security
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=None,
        help=(
            "Allowed host for DNS rebinding protection (repeatable). "
            "Env: ARQUIVO_PT_MCP_ALLOWED_HOSTS"
        ),
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        default=None,
        help="Allowed CORS origin (repeatable). Env: ARQUIVO_PT_MCP_ALLOWED_ORIGINS",
    )
    parser.add_argument(
        "--no-dns-rebinding-protection",
        action="store_true",
        default=False,
        help="Disable DNS rebinding protection.",
    )

    # Logging
    parser.add_argument(
        "--log-level",
        choices=["critical", "error", "warning", "info", "debug"],
        default=_env_str("ARQUIVO_PT_MCP_LOG_LEVEL") or "info",
        help="Logging level. Env: ARQUIVO_PT_MCP_LOG_LEVEL",
    )

    args = parser.parse_args(argv)

    # Compute boolean flags from mutually exclusive groups
    args.json_response = args.response_mode == "json"
    args.sse_response = args.response_mode == "sse"
    args.stateless = args.session_mode == "stateless"
    args.stateful = args.session_mode == "stateful"

    # List-arg env precedence: CLI overrides env var (consistent with scalars)
    if args.allowed_host is None:
        args.allowed_host = _env_list("ARQUIVO_PT_MCP_ALLOWED_HOSTS") or []
    if args.allowed_origin is None:
        args.allowed_origin = _env_list("ARQUIVO_PT_MCP_ALLOWED_ORIGINS") or []

    # DNS rebinding guard
    if args.transport == "http":
        host = args.host
        if (
            host
            and not _is_loopback(host)
            and not args.allowed_host
            and not args.no_dns_rebinding_protection
        ):
            parser.error(
                f"Binding to non-loopback address '{host}' without allowed_hosts "
                "is unsafe due to DNS rebinding. Pass --allowed-host or "
                "--no-dns-rebinding-protection to proceed."
            )

    return args
