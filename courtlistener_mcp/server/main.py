"""Build the MCP server and its HTTP app; ``main`` runs it (the
``courtlistener-mcp`` command)."""

import asyncio
import contextlib

from fastmcp import FastMCP
from fastmcp.apps import UI_MIME_TYPE
from fastmcp.server.auth import AuthProvider
from mcp.types import Icon
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from courtlistener_mcp.auth.proxy import (
    CourtListenerOAuthProxy,
    admit_token_scheme,
)
from courtlistener_mcp.auth.store import (
    get_oauth_store,
    oauth_store_ready,
    postgres_connect,
)
from courtlistener_mcp.lib.views import MCP_VIEWS
from courtlistener_mcp.lib.web import asset_path, data_uri, render
from courtlistener_mcp.metrics import render_metrics
from courtlistener_mcp.server.middleware import WikiToolAccess
from courtlistener_mcp.server.prompts import GLOBAL_INSTRUCTIONS
from courtlistener_mcp.session import RedisSession, get_session
from courtlistener_mcp.settings import (
    GIT_SHA,
    MCP_BASE_URL,
    MCP_JWT_SIGNING_KEY,
    OAUTH_AUTHORIZATION_URL,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_REVOCATION_URL,
    OAUTH_SCOPES,
    OAUTH_TOKEN_URL,
    OPENAI_APPS_CHALLENGE_TOKEN,
    POSTGRES_CONFIGURED,
    REDIS_URL,
    WIKI_TOOLS_EXCLUDED_CLIENTS,
)
from courtlistener_mcp.tools import MCP_TOOLS

# The files in assets/icons/ served at the root.
ICONS = ["favicon.svg", "favicon.ico", "apple-touch-icon.png"]
ICON_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


def create_mcp_server(auth: AuthProvider | None = None) -> FastMCP:
    mcp = FastMCP(
        name="CourtListener",
        instructions=GLOBAL_INSTRUCTIONS,
        website_url="https://courtlistener.com",
        icons=[
            Icon(
                src=data_uri("icons/favicon.svg"),
                mime_type="image/svg+xml",
                sizes=["16x16", "32x32"],
            ),
            Icon(
                src=data_uri("icons/apple-touch-icon.png"),
                mime_type="image/png",
                sizes=["180x180"],
            ),
        ],
        tools=list(MCP_TOOLS.values()),
        auth=auth,
        middleware=[WikiToolAccess(WIKI_TOOLS_EXCLUDED_CLIENTS)],
        # Tools validate their own arguments; see MCPTool.validate_arguments.
        strict_input_validation=False,
    )

    for view in MCP_VIEWS:
        mcp.resource(
            view.uri,
            name=view.name,
            description=view.description,
            mime_type=UI_MIME_TYPE,
            app=view.app,
        )(view.html)

    # The icons, at the root where browsers look for them.
    async def icon(request):
        path = asset_path(f"icons{request.url.path}")
        return FileResponse(path, headers=ICON_CACHE_HEADERS)

    for name in ICONS:
        mcp.custom_route(f"/{name}", methods=["GET"], name=name)(icon)

    @mcp.custom_route("/", methods=["GET"])
    async def index(request):
        return HTMLResponse(render("html/index.html"))

    # OpenAI Apps directory domain-verification challenge
    @mcp.custom_route("/.well-known/openai-apps-challenge", methods=["GET"])
    async def openai_apps_challenge(request):
        return PlainTextResponse(OPENAI_APPS_CHALLENGE_TOKEN)

    # Health check route
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request):
        services = {"mcp": True}

        session = get_session()
        if isinstance(session, RedisSession):
            services["redis"] = await session.ping()

        if POSTGRES_CONFIGURED:
            try:
                conn = await postgres_connect(timeout=5)
                try:
                    await conn.execute("SELECT 1", timeout=5)
                finally:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(conn.close(), 5)
                services["postgres"] = True
            except Exception:
                services["postgres"] = False

        # Temporary sanity check
        config = {
            "oauth_client": bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET)
        }
        if POSTGRES_CONFIGURED:
            try:
                config["oauth_store"] = await asyncio.wait_for(
                    oauth_store_ready(), 5
                )
            except TimeoutError:
                config["oauth_store"] = False

        return JSONResponse(
            {
                "status": "healthy" if all(services.values()) else "unhealthy",
                "version": GIT_SHA,
                "services": services,
                "config": config,
            }
        )

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics(request):
        body, content_type = await render_metrics()
        return Response(body, media_type=content_type)

    return mcp


def create_auth_provider() -> CourtListenerOAuthProxy:
    """The OAuth authorization server fronting CourtListener for MCP clients."""
    if not (OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET):
        raise ValueError(
            "COURTLISTENER_OAUTH_CLIENT_ID and COURTLISTENER_OAUTH_CLIENT_SECRET "
            "are required for HTTP mode"
        )
    return CourtListenerOAuthProxy(
        upstream_authorization_endpoint=OAUTH_AUTHORIZATION_URL,
        upstream_token_endpoint=OAUTH_TOKEN_URL,
        upstream_revocation_endpoint=OAUTH_REVOCATION_URL,
        upstream_client_id=OAUTH_CLIENT_ID,
        upstream_client_secret=OAUTH_CLIENT_SECRET,
        valid_scopes=OAUTH_SCOPES,
        base_url=MCP_BASE_URL,
        client_storage=get_oauth_store(),
        jwt_signing_key=MCP_JWT_SIGNING_KEY,
    )


class McpPathAlias:
    """Serve the MCP endpoint at /mcp and /mcp/ as aliases of /."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] == "http" and scope["path"] in ("/mcp", "/mcp/"):
            scope = {**scope, "path": "/", "raw_path": b"/"}
        await self.app(scope, receive, send)


def create_http_app():
    if REDIS_URL is None:
        raise ValueError("REDIS_URL is required for HTTP mode")
    mcp = create_mcp_server(auth=create_auth_provider())
    middleware = [
        Middleware(McpPathAlias),
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=[
                "mcp-protocol-version",
                "mcp-session-id",
                "mcp-method",
                "mcp-name",
                "Authorization",
                "Content-Type",
            ],
            expose_headers=["mcp-session-id"],
        ),
    ]
    app = mcp.http_app(path="/", stateless_http=True, middleware=middleware)
    admit_token_scheme(app)
    return app


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
