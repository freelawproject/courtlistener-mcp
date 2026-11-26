"""The Free Law Project wiki: its API client (reads, and writes as the
user), and what the wiki tools share (scope checks, page paths and
tidying, schema properties)."""

import json
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.dependencies import get_access_token

from courtlistener_mcp.exceptions import (
    ToolArgumentValidationError,
    WikiAPIError,
)
from courtlistener_mcp.settings import WIKI_BASE_URL, WIKI_SCOPES
from courtlistener_mcp.tokens import TokenKind


async def wiki_get(path: str, **params: Any) -> dict:
    """GET *path* from the Free Law Project wiki's API as the current user."""
    headers = {}
    token = get_access_token()
    if token is not None and token.claims.get("token_kind") != TokenKind.API:
        headers["Authorization"] = f"Bearer {token.token}"
    try:
        async with httpx.AsyncClient(
            base_url=WIKI_BASE_URL, timeout=30, follow_redirects=True
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


def wiki_oauth_token() -> AccessToken:
    """The current user's OAuth token, which writing to the wiki needs: an
    API token or a stdio session can only read it, as the public."""
    token = get_access_token()
    if token is None or token.claims.get("token_kind") == TokenKind.API:
        raise WikiAPIError(
            "Editing the wiki needs an OAuth sign-in to this server, "
            "not an API token.",
            # Not 401, which is kept for the wiki rejecting a sign-in.
            "403",
        )
    return token


async def wiki_write(method: str, path: str, body: dict) -> dict:
    """Send a JSON ``POST`` or ``PATCH`` to the wiki's API as the current
    user: a write, or a preview rendered as them. It needs the user's OAuth
    bearer; a refusal comes back as a ``WikiAPIError`` carrying the wiki's
    own explanation and error code."""
    token = wiki_oauth_token()
    try:
        async with httpx.AsyncClient(
            base_url=WIKI_BASE_URL, timeout=30, follow_redirects=True
        ) as http:
            resp = await http.request(
                method,
                f"/api/v1/{path}",
                json=body,
                headers={"Authorization": f"Bearer {token.token}"},
            )
    except httpx.HTTPError as exc:
        raise WikiAPIError(
            f"The wiki could not be reached: {exc}", "connection"
        ) from exc
    if resp.is_success:
        return resp.json()
    try:
        error = resp.json()
    except ValueError:
        error = None
    if not isinstance(error, dict):
        error = {}
    detail = error.get("detail")
    if not isinstance(detail, str):
        detail = json.dumps(error) if error else resp.text[:500]
    code = error.get("error")
    raise WikiAPIError(
        f"The wiki refused the change (HTTP {resp.status_code}): {detail}",
        str(resp.status_code),
        code=code if isinstance(code, str) else None,
    )


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
    return f"{WIKI_BASE_URL}/c/{path}"


def page_path(
    value: str, tool_name: str, argument: str = "path", what: str = "page"
) -> str:
    """The wiki content path *value* names: a path, a page URL, or a link
    from page content (the wiki's ``#path`` syntax, or a site link
    ``/c/...``), less any query or ``#anchor``. A bare ``c/...`` is a path,
    under a directory ``c``. URLs and links arrive percent-encoded and are
    decoded, so the path isn't encoded twice on its way to the API; a plain
    path is taken literally. A *value* that names no page is reported as a
    bad *argument* to *tool_name*. Directories are named the same way, with
    *what* ``"directory"``."""

    def invalid(message: str) -> ToolArgumentValidationError:
        return ToolArgumentValidationError(
            f"Invalid arguments for tool '{tool_name}':\n- {message}",
            tool_name=tool_name,
            argument_names=[argument],
        )

    value = value.strip()
    is_link = value.startswith(("#", "/c/"))
    value = value.removeprefix("#")
    url = urlsplit(value)
    is_url = bool(url.scheme or url.netloc)
    if is_url and (
        url.netloc != urlsplit(WIKI_BASE_URL).netloc
        or not url.path.startswith("/c/")
    ):
        raise invalid(f"{value!r} is not a wiki {what} URL.")
    path = unquote(url.path) if is_url or is_link else url.path
    if path.startswith("/c/"):
        path = path.removeprefix("/c/")
    path = path.strip("/")
    if not path:
        raise invalid(f"`{argument}` must name a wiki {what}.")
    return path


# Input schema for a page's data source, which fills its `[[ key ]]`
# placeholders; shared by the create and edit tools.
DATA_SOURCE_FIELDS = ("data_source_url", "data_source_ttl")
DATA_SOURCE_PROPERTIES = {
    "data_source_url": {
        "type": "string",
        "description": (
            "The page's data source: a URL returning JSON whose values "
            "fill its `[[ key ]]` placeholders (`[[ stats.open ]]` for "
            'nested keys). Only domains the wiki allows work. `""` '
            "removes it."
        ),
    },
    "data_source_ttl": {
        "type": "integer",
        "minimum": 10,
        "maximum": 86400,
        "description": "Seconds to cache the data source's response, "
        "from 10 to 86400 (a day); 300 by default.",
    },
}


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
