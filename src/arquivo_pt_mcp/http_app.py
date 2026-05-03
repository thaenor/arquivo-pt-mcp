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


def create_app(  # noqa: PLR0913
    *,
    path: str = "/mcp",
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
        return JSONResponse(
            {
                "status": "ok",
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

    # Accept both /mcp and /mcp/ without an HTTP 307. Starlette's Mount only
    # matches the trailing-slash form; some MCP clients POST to /mcp and either
    # don't follow redirects or drop the body when they do.
    trailing = path if path.endswith("/") else path + "/"

    class _NormalizeMcpPath:
        def __init__(self, app):  # type: ignore[no-untyped-def]
            self.app = app

        async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
            if scope["type"] == "http" and scope["path"] == path:
                scope = {**scope, "path": trailing, "raw_path": trailing.encode("ascii")}
            await self.app(scope, receive, send)

    middleware.append(Middleware(_NormalizeMcpPath))

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Mount(path, app=session_manager.handle_request),
            Route(HEALTH_PATH, health),
        ],
        middleware=middleware,
    )
    app.router.redirect_slashes = False

    return app
