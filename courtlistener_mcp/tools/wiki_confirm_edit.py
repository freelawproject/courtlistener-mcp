import time
from urllib.parse import quote

from mcp.types import ToolAnnotations

from courtlistener_mcp.exceptions import SessionUnavailableError, WikiAPIError
from courtlistener_mcp.lib.views import WIKI_EDIT_VIEW
from courtlistener_mcp.lib.wiki import wiki_page_url, wiki_write
from courtlistener_mcp.lib.wiki_edits import (
    RETRY_HINT,
    save_may_succeed_later,
)
from courtlistener_mcp.session import get_session
from courtlistener_mcp.tools.base import WikiTool


class WikiConfirmEditTool(WikiTool):
    """Save a new wiki page or an edit the user approved in the review
    view.

    Called by the review view when the user clicks Save, not by the model.
    """

    name: str = "wiki_confirm_edit"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Save Reviewed Wiki Change",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )
    meta: dict | None = WIKI_EDIT_VIEW.tool_meta(visibility=["app"])

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"token": {"type": "string"}},
            "required": ["token"],
            "additionalProperties": False,
        }

    async def call_wiki(self, arguments: dict) -> dict:
        session = get_session()
        try:
            proposal = await session.pop_wiki_edit(arguments["token"])
        except SessionUnavailableError as exc:
            # The pop may or may not have run, so promise nothing: a
            # second try either saves or finds the change gone.
            raise WikiAPIError(
                "The change couldn't be read just now; you can try saving "
                "again.",
                "store",
            ) from exc
        if proposal is None:
            raise WikiAPIError(
                "This change has expired or was already saved. Ask for it "
                "to be proposed again.",
                "410",
            )
        body = dict(proposal)
        action = body.pop("action", "edit")
        expires_at = body.pop("expires_at", 0)
        try:
            if action == "create":
                page = await wiki_write("POST", "pages/", body)
            else:
                path = body.pop("path")
                page = await wiki_write(
                    "PATCH", f"pages/{quote(path, safe='/')}", body
                )
        except WikiAPIError as exc:
            # Put it back if the wiki may take it on a second try, for the
            # time it had left.
            left = int(expires_at - time.time())
            if not save_may_succeed_later(exc, action) or left < 1:
                raise
            try:
                await session.store_wiki_edit(
                    arguments["token"], proposal, left
                )
            except SessionUnavailableError:
                raise WikiAPIError(
                    f"{exc} The change couldn't be kept, so ask for it to "
                    "be proposed again.",
                    exc.status,
                    code=exc.code,
                ) from exc
            raise WikiAPIError(
                f"{exc} {RETRY_HINT}", exc.status, code=exc.code
            ) from exc
        return {
            "path": page.get("path"),
            "title": page.get("title"),
            "revision": page.get("revision"),
            "url": wiki_page_url(page["path"]) if page.get("path") else None,
        }
