"""The OAuth proxy that makes this server an authorization server in
front of CourtListener, and the auth gate that also admits CourtListener
API tokens."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, cast

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.middleware import RequireAuthMiddleware
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.oauth_proxy.models import ProxyDCRClient
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser,
    BearerAuthBackend,
)
from mcp.server.auth.middleware.bearer_auth import (
    RequireAuthMiddleware as SDKRequireAuthMiddleware,
)
from mcp.server.auth.provider import TokenVerifier as TokenVerifierProtocol
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from courtlistener_mcp.auth.verifiers import (
    ApiTokenVerifier,
    OAuthTokenVerifier,
)
from courtlistener_mcp.metrics import (
    auth_rejections_total,
    oauth_registrations_total,
)
from courtlistener_mcp.tokens import UNKNOWN_CLIENT_ID, TokenKind

logger = logging.getLogger(__name__)

# The shape of a client id CourtListener issued when it was the authorization
# server. Clients still holding one are recognised on first use.
LEGACY_CLIENT_ID = re.compile(r"[A-Za-z0-9]{40}")


class CourtListenerOAuthProxy(OAuthProxy):
    """Authorization server for MCP clients that brokers CourtListener
    logins and also accepts CourtListener API tokens."""

    def __init__(self, **kwargs: Any) -> None:
        self.courtlistener_verifier = OAuthTokenVerifier()
        super().__init__(
            token_verifier=self.courtlistener_verifier,
            forward_resource=False,
            require_authorization_consent="external",
            **kwargs,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Tokens this server issued, plus, until CourtListener stops issuing
        to clients directly, CourtListener tokens presented as bearers."""
        if (access := await super().load_access_token(token)) is not None:
            return self.with_mcp_client(token, cast(AccessToken, access))
        if token_issuer(token) == "mcp":
            return None
        return await self.courtlistener_verifier.verify_token(token)

    def with_mcp_client(self, token: str, access: AccessToken) -> AccessToken:
        """Put the MCP client that holds *token* back on *access*.

        For a token it issued, the proxy returns the upstream verification,
        whose client is this server's own CourtListener application; the
        client the token was issued to is only in the JWT. If that can't
        be read, the client is ``UNKNOWN_CLIENT_ID``."""
        client_id = None
        try:
            client_id = self.jwt_issuer.verify_token(token).get("client_id")
        except Exception as exc:
            logger.warning("could not re-read an issued token: %s", exc)
        return access.model_copy(
            update={"client_id": str(client_id or UNKNOWN_CLIENT_ID)}
        )

    def get_middleware(self) -> list:
        return [
            Middleware(
                AuthenticationMiddleware,
                backend=CourtListenerAuthBackend(self, ApiTokenVerifier()),
            ),
            Middleware(AuthContextMiddleware),
        ]

    async def register_client(
        self, client_info: OAuthClientInformationFull
    ) -> None:
        await super().register_client(client_info)
        oauth_registrations_total.labels(source="dcr").inc()

    def get_challenge_scopes(
        self, required_scopes: list[str] | None = None
    ) -> list[str]:
        """Advertise preferred scopes in the WWW-Authenticate challenge."""
        options = cast(
            ClientRegistrationOptions, self.client_registration_options
        )
        return list(cast("list[str]", options.valid_scopes))

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """FastMCP 4 registers the OIDC discovery alias only through
        ``get_well_known_routes``, which ``http_app`` never calls; serve
        it here for clients that discover via OpenID Connect."""
        routes = super().get_routes(mcp_path)
        alias = [
            Route(
                "/.well-known/openid-configuration",
                endpoint=route.endpoint,
                methods=route.methods,
            )
            for route in routes
            if isinstance(route, Route)
            and route.path == "/.well-known/oauth-authorization-server"
        ]
        return routes + alias

    async def get_client(
        self, client_id: str
    ) -> OAuthClientInformationFull | None:
        """Registered clients, plus clients registered with CourtListener
        before this server became the authorization server, which are
        registered here the first time they show up."""
        client = await super().get_client(client_id)
        if client is None:
            if not LEGACY_CLIENT_ID.fullmatch(client_id):
                return None
            await super().register_client(
                OAuthClientInformationFull(
                    client_id=client_id,
                    redirect_uris=[AnyUrl("http://localhost")],
                    grant_types=["authorization_code", "refresh_token"],
                    token_endpoint_auth_method="none",
                )
            )
            oauth_registrations_total.labels(source="legacy").inc()
            client = await super().get_client(client_id)
        if (
            client is not None
            and LEGACY_CLIENT_ID.fullmatch(client_id)
            and isinstance(client, ProxyDCRClient)
        ):
            # Registered on first use with a placeholder redirect URI; the
            # real one is known only to CourtListener, so accept what the
            # client presents, as DCR would have let it register anyway.
            client.allow_unregistered_redirect_uris = True
        return client


class CourtListenerAuthBackend(BearerAuthBackend):
    """``Bearer`` is an MCP-issued token, checked by the proxy; ``Token``
    is a CourtListener API token, checked by *api_verifier*. The scheme
    is binding."""

    def __init__(
        self, proxy: TokenVerifierProtocol, api_verifier: ApiTokenVerifier
    ) -> None:
        super().__init__(proxy)
        self.api_verifier = api_verifier

    async def authenticate(self, conn: HTTPConnection):
        auth_header = next(
            (
                conn.headers.get(key)
                for key in conn.headers
                if key.lower() == "authorization"
            ),
            None,
        )
        if not auth_header:
            return None

        scheme, _, credential = auth_header.partition(" ")
        kind = TokenKind.from_scheme(scheme)
        if kind is TokenKind.OAUTH:
            result = await super().authenticate(conn)
            if result is None:
                auth_rejections_total.labels(
                    scheme=kind.scheme, issuer=token_issuer(credential)
                ).inc()
            return result
        if kind is not TokenKind.API or not (credential := credential.strip()):
            return None

        auth_info = await self.api_verifier.verify_token(credential)
        if auth_info and (
            not auth_info.expires_at
            or auth_info.expires_at >= int(time.time())
        ):
            return AuthCredentials(auth_info.scopes), AuthenticatedUser(
                auth_info
            )
        auth_rejections_total.labels(
            scheme=kind.scheme, issuer="courtlistener"
        ).inc()
        return None


class DualSchemeAuthGate:
    """Admit an authenticated user whatever scheme it arrived under.

    FastMCP's route gate 401s any request without a ``Bearer`` header
    before looking at the user the auth backend authenticated, which
    would lock out the ``Token`` scheme; skip the header check once the
    backend has authenticated, keeping the SDK's scope enforcement."""

    def __init__(self, gate: RequireAuthMiddleware) -> None:
        self.gate = gate

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] == "http" and isinstance(
            scope.get("user"), AuthenticatedUser
        ):
            await SDKRequireAuthMiddleware.__call__(
                self.gate, scope, receive, send
            )
            return
        await self.gate(scope, receive, send)


def admit_token_scheme(app: Starlette) -> None:
    """Wrap FastMCP's auth gates in *app* so the ``Token`` scheme passes."""
    for route in app.routes:
        if isinstance(route, Route) and isinstance(
            route.app, RequireAuthMiddleware
        ):
            route.app = DualSchemeAuthGate(route.app)


def token_issuer(credential: str) -> str:
    """``mcp`` for a token shaped like this server's JWTs, else ``courtlistener``."""
    return "mcp" if credential.strip().count(".") == 2 else "courtlistener"
