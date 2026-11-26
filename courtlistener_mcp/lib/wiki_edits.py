"""Proposed wiki changes, which the user reviews before they're saved:
applying edits to a page's source, rendering previews, and the proposal
the review view is sent."""

import secrets
import time

from courtlistener_mcp.exceptions import (
    SessionUnavailableError,
    ToolArgumentValidationError,
    WikiAPIError,
)
from courtlistener_mcp.lib.wiki import wiki_write
from courtlistener_mcp.session import WIKI_EDIT_TTL_SECONDS, get_session

# The key under the tool result's ``_meta`` that carries the proposed edit
# to the review view. Hosts hand a result's ``_meta`` to the view, not to
# the model, so the confirmation token stays out of the model's reach.
PROPOSAL_META_KEY = "courtlistener/wikiEditProposal"

# Ends the error a save gets when the wiki may take it on a second try:
# the proposal is kept, and the review view, which looks for this text,
# lets the user click Save again.
RETRY_HINT = "The change is kept, so you can try saving again."


async def store_proposal(proposal: dict) -> tuple[str, int]:
    """Keep *proposal* for the user to review, under a new single-use
    token; returns the token and when the proposal expires."""
    token = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + WIKI_EDIT_TTL_SECONDS
    try:
        await get_session().store_wiki_edit(
            token, {**proposal, "expires_at": expires_at}
        )
    except SessionUnavailableError as exc:
        raise WikiAPIError(
            "The change couldn't be kept for review just now. Try again "
            "in a moment.",
            "store",
        ) from exc
    return token, expires_at


def save_may_succeed_later(exc: WikiAPIError, action: str) -> bool:
    """Whether a save the wiki refused with *exc* could be tried again
    unchanged. An edit can, if the page is open in the wiki's editor, the
    wiki is limiting the user's rate, or it's down or unreachable: if the
    first try did save, the second is refused as a stale revision. A create
    has no such guard, and a 5xx or a timeout can come after the page was
    made, so only a rate limit, which refuses before saving, is retried."""
    if action == "create":
        return exc.status == "429"
    return (
        exc.code == "locked"
        or exc.status in ("429", "connection")
        or exc.status.startswith("5")
    )


def without_nulls(arguments: dict) -> dict:
    """*arguments* less those sent as null, which means not sent: some
    clients send every optional argument, as null when unused."""
    return {
        key: value for key, value in arguments.items() if value is not None
    }


def lf(text: str) -> str:
    return text.replace("\r\n", "\n")


async def render_preview(
    content: str, data_source_url: str | None
) -> str | None:
    """*content* rendered to HTML by the wiki as the user would see it, with
    placeholders filled from *data_source_url*; None if it can't be
    rendered, since a missing preview shouldn't stop the edit being
    reviewed."""
    body = {"content": content}
    if data_source_url:
        body["data_source_url"] = data_source_url
    try:
        return (await wiki_write("POST", "preview/", body))["html"]
    except (WikiAPIError, KeyError, TypeError, ValueError):
        return None


def with_final_newline_of(old: str, new: str) -> str:
    """*new* ending in a newline exactly when *old* does. Whether a page
    ends in one is invisible in a line diff and the review view, so the
    page keeps its own, and a change that only adds or drops it is no
    change at all."""
    if not new:
        return new
    body = new.removesuffix("\n")
    return body + "\n" if old.endswith("\n") else body


def apply_edits(
    content: str, edits: list[dict], tool_name: str = "wiki_edit_page"
) -> str:
    """*content* with each ``{old, new}`` edit applied in order; each
    ``old`` must occur exactly once in the text as it then stands."""
    for n, edit in enumerate(edits):
        old, new = lf(edit["old"]), lf(edit["new"])
        count = content.count(old) if old else 0
        if count != 1:
            if count == 0:
                problem = (
                    "isn't in the page source. Edits apply to the source, "
                    "which differs from a normal read (placeholders and wiki "
                    "links aren't filled in): read the page with `raw: true` "
                    "and copy `old` from that"
                )
            else:
                problem = (
                    f"occurs {count} times in the page source; include more "
                    "of the surrounding text so it occurs exactly once"
                )
            raise ToolArgumentValidationError(
                f"Edit {n}: its `old` text {problem}.",
                tool_name=tool_name,
                argument_names=["edits"],
            )
        content = content.replace(old, new)
    return content
