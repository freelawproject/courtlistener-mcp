"""The ASGI app for gunicorn and uvicorn, with Sentry set up."""

import sentry_sdk
from sentry_sdk.integrations.mcp import MCPIntegration

from courtlistener_mcp.exceptions import before_send
from courtlistener_mcp.server.main import create_http_app
from courtlistener_mcp.settings import settings

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    release=settings.sentry_release,
    integrations=[MCPIntegration()],
    traces_sample_rate=settings.sentry_traces_sample_rate,
    before_send=before_send,
)

app = create_http_app()
