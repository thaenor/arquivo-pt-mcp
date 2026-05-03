"""Starlette ASGI application factory for Streamable HTTP transport."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from arquivo_pt_mcp import server

if TYPE_CHECKING:
    from starlette.applications import Starlette

MCP_PATH = "/mcp"
HEALTH_PATH = "/healthz"

logger = logging.getLogger(__name__)


def _is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost")


def create_app(  # noqa: PLR0913
    *,
    json_response: bool = True,
    stateless: bool = True,
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    enable_dns_rebinding_protection: bool = True,
) -> Starlette:
    """Return a configured Starlette app with Streamable HTTP support."""
    # Lazy imports to avoid hard dependency at import time
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=enable_dns_rebinding_protection,
        allowed_hosts=list(allowed_hosts) if allowed_hosts else [],
        allowed_origins=list(allowed_origins) if allowed_origins else [],
    )

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=json_response,
        stateless=stateless,
        security_settings=security_settings,
    )

    async def health(request: Request) -> JSONResponse:  # noqa: ARG001
        """Health-check endpoint returning server status."""
        try:
            tool_count = len(server._tool_cache)
        except Exception:
            tool_count = 0
        return JSONResponse(
            {
                "status": "ok",
                "tools": tool_count,
                "transport": "streamable-http",
            }
        )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:  # noqa: ARG001
        """Wrap the StreamableHTTP session manager lifecycle."""
        async with session_manager.run():
            yield

    middleware: list[Middleware] = []
    if allowed_origins:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=allowed_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        )

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Mount(MCP_PATH, app=session_manager.handle_request),
            Route(HEALTH_PATH, health),
        ],
        middleware=middleware,
    )

    return app


def run_uvicorn(  # noqa: PLR0913
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    path: str = "/mcp",
    json_response: bool = True,
    stateless: bool = True,
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    enable_dns_rebinding_protection: bool = True,
    log_level: str = "info",
) -> None:
    """Create the ASGI app and run it with uvicorn."""
    import uvicorn

    app = create_app(
        json_response=json_response,
        stateless=stateless,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
        enable_dns_rebinding_protection=enable_dns_rebinding_protection,
    )

    log_config = uvicorn.config.LOGGING_CONFIG
    logging.getLogger("arquivo_pt_mcp").setLevel(getattr(logging, log_level.upper()))

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        log_config=log_config,
    )
