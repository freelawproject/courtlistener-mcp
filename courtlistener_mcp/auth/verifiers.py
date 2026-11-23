"""Verify CourtListener credentials, OAuth access tokens and API tokens,
with the results cached in the session store."""

from __future__ import annotations

import logging
import time

import httpx
from courtlistener.settings import get_api_base_url
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

from courtlistener_mcp.session import get_session, hmac_hex
from courtlistener_mcp.settings import (
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_INTROSPECTION_URL,
    TOKEN_CACHE_TTL_SECONDS,
    VERIFICATION_TIMEOUT_SECONDS,
)
from courtlistener_mcp.tokens import (
    NO_CLIENT_ID,
    UNKNOWN_CLIENT_ID,
    TokenInfo,
    TokenKind,
)

logger = logging.getLogger(__name__)


class CachedTokenVerifier(TokenVerifier):
    """Verify one kind of CourtListener credential, caching the result in
    the session store for the token's lifetime or ``TOKEN_CACHE_TTL``."""

    kind: TokenKind

    def __init__(self) -> None:
        super().__init__(required_scopes=["api"])

    async def check(self, token: str) -> TokenInfo | None:
        """Ask CourtListener about *token*; ``None`` when it is not valid."""
        raise NotImplementedError

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        session = get_session()
        info = await session.get_token_info(token, self.kind)
        cached = info is not None
        if info is None:
            info = await self.check(token)
            if info is None:
                return None
            logger.info("verified %s credential", self.kind)
            await session.store_token_info(
                token, self.kind, info, cache_ttl(info)
            )
        return AccessToken(
            token=token,
            client_id=self.client_id(info),
            # API tokens have no scopes of their own; echo the required set.
            scopes=(
                info["scopes"]
                if "scopes" in info
                else list(self.required_scopes)
            ),
            expires_at=info.get("expires_at"),
            claims={
                "user_hash": info["user_hash"],
                "token_kind": self.kind,
                "cached": cached,
            },
        )

    def client_id(self, info: TokenInfo) -> str:
        """The OAuth client *info* belongs to. API tokens have none; an
        OAuth token cached before client ids were recorded is unknown."""
        if self.kind == TokenKind.API:
            return NO_CLIENT_ID
        return info.get("client_id") or UNKNOWN_CLIENT_ID


class OAuthTokenVerifier(CachedTokenVerifier):
    """A CourtListener OAuth access token, checked by introspection. The
    proxy calls this on the token it holds behind each MCP-issued one."""

    kind = TokenKind.OAUTH

    async def check(self, token: str) -> TokenInfo | None:
        """Introspect *token* at CourtListener with the server's client credentials."""
        if not (OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET):
            logger.error(
                "COURTLISTENER_OAUTH_CLIENT_ID and COURTLISTENER_OAUTH_CLIENT_SECRET "
                "are required to introspect tokens"
            )
            return None
        try:
            async with httpx.AsyncClient(
                timeout=VERIFICATION_TIMEOUT_SECONDS
            ) as http:
                resp = await http.post(
                    OAUTH_INTROSPECTION_URL,
                    data={"token": token, "token_type_hint": "access_token"},
                    auth=(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET),
                )
        except httpx.HTTPError as exc:
            logger.warning("introspection call failed: %s", exc)
            return None
        if resp.status_code in (401, 403):
            logger.error(
                "CourtListener rejected the introspection client credentials"
            )
            return None
        if resp.status_code != 200:
            logger.warning("introspection returned HTTP %s", resp.status_code)
            return None
        data = resp.json()
        if not data.get("active"):
            return None
        sub = data.get("sub")
        if not sub:
            logger.warning("introspection response has no `sub`")
            return None
        exp = data.get("exp")
        return TokenInfo(
            user_hash=hmac_hex(str(sub)),
            client_id=data.get("client_id"),
            scopes=str(data.get("scope") or "").split(),
            expires_at=int(exp) if exp else None,
        )


class ApiTokenVerifier(CachedTokenVerifier):
    """A CourtListener API token, checked against the API root."""

    kind = TokenKind.API

    async def check(self, token: str) -> TokenInfo | None:
        """Try *token* against the CourtListener API root."""
        try:
            async with httpx.AsyncClient(
                timeout=VERIFICATION_TIMEOUT_SECONDS
            ) as http:
                resp = await http.get(
                    f"{get_api_base_url()}/",
                    headers={"Authorization": f"Token {token}"},
                )
        except httpx.HTTPError as exc:
            logger.warning("api-token validation call failed: %s", exc)
            return None
        if 200 <= resp.status_code < 300 or throttled_by_django(resp):
            return TokenInfo(user_hash=hmac_hex(token))
        return None


def throttled_by_django(resp: httpx.Response) -> bool:
    """A 429 carrying DRF's throttle body, which Django only sends after
    authenticating the token; an edge 429 says nothing about the token."""
    if resp.status_code != 429:
        return False
    try:
        body = resp.json()
    except ValueError:
        return False
    return isinstance(body, dict) and "throttled" in str(
        body.get("detail", "")
    )


def cache_ttl(info: TokenInfo) -> int:
    """How long to cache *info*: the configured TTL, cut at the token's expiry."""
    expires_at = info.get("expires_at")
    if expires_at is None:
        return TOKEN_CACHE_TTL_SECONDS
    return max(1, min(TOKEN_CACHE_TTL_SECONDS, expires_at - int(time.time())))
