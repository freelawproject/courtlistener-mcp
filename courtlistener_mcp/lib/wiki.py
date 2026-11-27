"""The Free Law Project wiki: its API client, and what the wiki tools
share (scope checks, page tidying, schema properties)."""

from typing import Any

import httpx
from fastmcp.server.dependencies import get_access_token

from courtlistener_mcp.exceptions import WikiAPIError
from courtlistener_mcp.settings import WIKI_SCOPES, settings
from courtlistener_mcp.tokens import TokenKind


async def wiki_get(path: str, **params: Any) -> dict:
    """GET *path* from the Free Law Project wiki's API as the current user."""
    headers = {}
    token = get_access_token()
    if token is not None and token.claims.get("token_kind") != TokenKind.API:
        headers["Authorization"] = f"Bearer {token.token}"
    try:
        async with httpx.AsyncClient(
            base_url=settings.wiki_base_url, timeout=30, follow_redirects=True
        ) as http:
            resp = await http.get(
                f"/api/v1/{path}", params=params, headers=headers
            )
    except httpx.HTTPError as exc:
        raise WikiAPIError(
            f"The wiki could not be reached: {exc}", "connection"
        ) from exc
    status = str(resp.status_code)
    if resp.status_code == 401:
        raise WikiAPIError(
            "The wiki did not accept your CourtListener sign-in; "
            "reconnect this server to grant it wiki access.",
            status,
        )
    if resp.status_code == 404:
        page = path.removeprefix("pages/")
        raise WikiAPIError(
            f"The wiki has no page you can read at {page!r}.", status
        )
    if not resp.is_success:
        raise WikiAPIError(f"The wiki returned HTTP {status}.", status)
    return resp.json()


MISSING_WIKI_SCOPES_MESSAGE = (
    "Please disconnect and reconnect the CourtListener connector to access "
    "the wiki."
)


# The `page` argument of the wiki's paginated list and search endpoints.
WIKI_PAGE_PROPERTY = {
    "type": "integer",
    "minimum": 1,
    "description": "Page of results to return (default 1).",
}


def missing_wiki_scopes() -> bool:
    """Whether the request's OAuth sign-in lacks a scope the wiki needs.

    API token and stdio sessions have no scopes; they read the wiki as
    the public, as ``wiki_get`` sends them without a credential."""
    token = get_access_token()
    if token is None or token.claims.get("token_kind") == TokenKind.API:
        return False
    return not set(WIKI_SCOPES) <= set(token.scopes)


def wiki_page_url(path: str) -> str:
    """The URL of the wiki page at *path*."""
    return f"{settings.wiki_base_url}/c/{path}"


def tidy_page(page: dict) -> dict:
    """*page* with a ``url`` and its text fields' CRLFs turned into LFs,
    which the wiki stores but which only cost the model tokens."""
    for field in ("description", "snippet", "content"):
        if isinstance(page.get(field), str):
            page[field] = page[field].replace("\r\n", "\n")
    if "path" in page:
        page["url"] = wiki_page_url(page["path"])
    return page


def tidy_listing(data: dict, key: str, arguments: dict) -> dict:
    """A page of the wiki's list or search results, made ready to return.

    Each page summary under *key* is tidied. The wiki answers a ``page``
    past the end with the last page; that comes back empty instead, under
    the page number asked for, so a caller looping on ``page`` sees no
    duplicates."""
    requested = arguments.get("page")
    if requested is not None and data.get("page") not in (None, requested):
        data.update(page=requested, next_page=None, **{key: []})
    for page in data.get(key, []):
        tidy_page(page)
    return data


def wiki_page_params(arguments: dict) -> dict:
    """The ``page`` query parameter, when the caller asked for one."""
    page = arguments.get("page")
    return {} if page is None else {"page": page}
