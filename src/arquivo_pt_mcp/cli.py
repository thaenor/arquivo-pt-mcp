"""CLI argument parser for arquivo-pt-mcp transport selection."""

from __future__ import annotations

import argparse
import os
import sys


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

    # Response mode
    parser.add_argument(
        "--json-response",
        action="store_true",
        default=False,
        help="Use JSON response mode for Streamable HTTP.",
    )
    parser.add_argument(
        "--sse-response",
        action="store_true",
        default=False,
        help="Use SSE response mode for Streamable HTTP.",
    )

    # Stateful / Stateless
    stateful_env = _env_bool("ARQUIVO_PT_MCP_STATEFUL")
    parser.add_argument(
        "--stateful",
        action="store_true",
        default=stateful_env if stateful_env is not None else False,
        help="Enable stateful sessions. Env: ARQUIVO_PT_MCP_STATEFUL",
    )
    parser.add_argument(
        "--stateless",
        action="store_true",
        default=True,
        help="Enable stateless sessions (default).",
    )

    # Security
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=_env_list("ARQUIVO_PT_MCP_ALLOWED_HOSTS"),
        help=(
            "Allowed host for DNS rebinding protection (repeatable). "
            "Env: ARQUIVO_PT_MCP_ALLOWED_HOSTS"
        ),
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        default=_env_list("ARQUIVO_PT_MCP_ALLOWED_ORIGINS"),
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

    # Resolve response mode: --sse-response takes precedence over default json
    if args.sse_response:
        args.json_response = False
    elif not args.json_response:
        # Default to JSON when neither flag is passed
        args.json_response = True

    # Resolve stateful/stateless: --stateful overrides default stateless
    if args.stateful:
        args.stateless = False

    # DNS rebinding guard
    if args.transport == "http":
        host = args.host
        allowed_hosts = args.allowed_host or []
        if (
            host
            and not _is_loopback(host)
            and not allowed_hosts
            and not args.no_dns_rebinding_protection
        ):
            parser.error(
                f"Binding to non-loopback address '{host}' without allowed_hosts "
                "is unsafe due to DNS rebinding. Pass --allowed-host or "
                "--no-dns-rebinding-protection to proceed."
            )

    return args


def main() -> None:
    """Synchronous entry point used by the console script."""
    args = parse_argv()
    if args.transport == "stdio":
        from arquivo_pt_mcp import main as stdio_main

        stdio_main()
    elif args.transport == "http":
        from arquivo_pt_mcp.http_app import run_uvicorn

        run_uvicorn(
            host=args.host,
            port=args.port,
            path=args.path,
            json_response=args.json_response,
            stateless=args.stateless,
            allowed_hosts=args.allowed_host or None,
            allowed_origins=args.allowed_origin or None,
            enable_dns_rebinding_protection=not args.no_dns_rebinding_protection,
            log_level=args.log_level,
        )
    else:
        # Should never happen because choices restrict the value
        print(f"unknown transport: {args.transport}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
