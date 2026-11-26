import asyncio
import difflib
from urllib.parse import quote

from fastmcp.tools import ToolResult
from mcp.types import TextContent, ToolAnnotations

from courtlistener_mcp.exceptions import (
    ToolArgumentValidationError,
    WikiAPIError,
)
from courtlistener_mcp.lib.views import WIKI_EDIT_VIEW
from courtlistener_mcp.lib.wiki import (
    DATA_SOURCE_FIELDS,
    DATA_SOURCE_PROPERTIES,
    page_path,
    wiki_get,
    wiki_oauth_token,
    wiki_page_url,
)
from courtlistener_mcp.lib.wiki_edits import (
    PROPOSAL_META_KEY,
    apply_edits,
    lf,
    render_preview,
    store_proposal,
    with_final_newline_of,
    without_nulls,
)
from courtlistener_mcp.tools.base import WikiTool


class WikiEditPageTool(WikiTool):
    """Propose an edit to a Free Law Project wiki page you're allowed to
    edit. The user reviews it and saves it; nothing is saved by this tool.

    First read the page with `wiki_read_page` and `raw: true`: edits
    apply to the page's source, and the read gives the page's `revision`
    (pass it as `base_revision`) and `can_edit`. Send either `edits`, a
    list of `{old, new}` replacements where each `old` occurs exactly once
    in the source, or `content`, the whole new source. `title` renames the
    page, which also changes its `path`. `data_source_url` and
    `data_source_ttl` set the page's data source for `[[ key ]]`
    placeholders; the read shows its current ones.

    The user is shown the change (a diff, plus the page rendered and as
    source, before and after) with a Save button. Only the user can save
    it: don't ask them to confirm in chat, and don't propose the same
    change again while they're reviewing it. If the page changes before
    they save, saving fails and you'll need to read it and propose the
    edit again. Editing needs an OAuth sign-in; with an API token the wiki
    can only be read.
    """

    name: str = "wiki_edit_page"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Edit Wiki Page",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
    meta: dict | None = WIKI_EDIT_VIEW.tool_meta()

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The page's path, e.g. `engineering/deploys`.",
                },
                "base_revision": {
                    "type": "integer",
                    "description": "The `revision` from your latest read.",
                },
                "change_message": {
                    "type": "string",
                    "description": "A short description of the change.",
                },
                "edits": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "old": {"type": "string", "minLength": 1},
                            "new": {"type": "string"},
                        },
                        "required": ["old", "new"],
                        "additionalProperties": False,
                    },
                    "description": (
                        "Replacements applied in order to the page source; "
                        "each `old` must occur exactly once."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "The whole new page source.",
                },
                "title": {
                    "type": "string",
                    "description": "A new title. This changes the page's path.",
                },
                **DATA_SOURCE_PROPERTIES,
            },
            "required": ["path", "base_revision", "change_message"],
            "additionalProperties": False,
        }

    async def call_wiki(self, arguments: dict) -> ToolResult:
        wiki_oauth_token()
        arguments = without_nulls(arguments)
        changeable = ("edits", "content", "title", *DATA_SOURCE_FIELDS)
        if not any(key in arguments for key in changeable):
            raise self.invalid(
                "Nothing to change: send `edits`, `content`, `title`, "
                "`data_source_url` or `data_source_ttl`.",
                list(changeable),
            )
        if "edits" in arguments and "content" in arguments:
            raise self.invalid(
                "Send `content` or `edits`, not both.", ["content", "edits"]
            )

        path = page_path(arguments["path"], self.name)
        page = await wiki_get(f"pages/{quote(path, safe='/')}", raw="true")
        if not page.get("can_edit"):
            raise WikiAPIError("You can't edit this page.", "403")
        base_revision = arguments["base_revision"]
        if page.get("revision") != base_revision:
            raise WikiAPIError(
                f"The page is at revision {page.get('revision')}, not "
                f"{base_revision}: it has changed since you read it. Read it "
                "again with `raw: true` and propose the edit from that.",
                "409",
            )

        # The wiki stores CRLFs, but reads give the model LFs, so edits
        # and comparisons work on LFs. The save restores the page's own
        # line endings, so its history shows only the lines that changed.
        stored = page["content"]
        old_source = lf(stored)
        if "edits" in arguments:
            new_source = apply_edits(old_source, arguments["edits"], self.name)
        else:
            new_source = lf(arguments.get("content", old_source))
        new_source = with_final_newline_of(old_source, new_source)
        new_title = arguments.get("title", page["title"])
        # Only the data source settings sent that differ from the page's.
        data_source = {
            field: arguments[field]
            for field in DATA_SOURCE_FIELDS
            if field in arguments and arguments[field] != page.get(field)
        }
        if (
            new_source == old_source
            and new_title == page["title"]
            and not data_source
        ):
            raise self.invalid(
                "Nothing to change: the page already has that title, "
                "content and data source.",
                list(changeable),
            )

        # How the page looks now and how it would look, each filled from
        # the data source it would have, for the review view's preview tabs.
        old_url = page.get("data_source_url")
        new_url = data_source.get("data_source_url", old_url)
        if new_source == old_source and new_url == old_url:
            old_preview = new_preview = await render_preview(
                old_source, old_url
            )
        else:
            old_preview, new_preview = await asyncio.gather(
                render_preview(old_source, old_url),
                render_preview(new_source, new_url),
            )

        token, expires_at = await store_proposal(
            {
                "path": path,
                "base_revision": base_revision,
                "change_message": arguments["change_message"],
                "content": new_source.replace("\n", "\r\n")
                if "\r\n" in stored
                else new_source,
                "title": new_title,
                **data_source,
            }
        )
        diff_lines = list(
            difflib.unified_diff(
                old_source.splitlines(),
                new_source.splitlines(),
                fromfile=f"{path} (revision {base_revision})",
                tofile=f"{path} (proposed)",
                lineterm="",
            )
        )
        # Past the two file header lines, every + or - line is a change,
        # even one that starts "---" (a Markdown rule taken out).
        changes = [line[:1] for line in diff_lines[2:]]
        added, removed = changes.count("+"), changes.count("-")
        renamed = (
            f" and renames it to {new_title!r}"
            if new_title != page["title"]
            else ""
        )
        if data_source:
            renamed += " and changes its data source"
        url = wiki_page_url(path)
        summary = (
            f"Proposed an edit to {path!r} that adds {added} and removes "
            f"{removed} lines{renamed}. It is shown to the user for review; "
            "nothing is saved until they click Save in that view. If they "
            "say no review view appeared, their client can't show it, and "
            f"they can make the edit in the wiki: {url}"
        )
        return ToolResult(
            content=[TextContent(type="text", text=summary)],
            meta={
                PROPOSAL_META_KEY: {
                    "action": "edit",
                    "token": token,
                    "expires_at": expires_at,
                    "path": path,
                    "url": url,
                    "title": page["title"],
                    "new_title": new_title,
                    "base_revision": base_revision,
                    "change_message": arguments["change_message"],
                    "new_source": new_source,
                    "old_source": old_source,
                    # Rendered HTML, or None if the wiki couldn't render it.
                    "new_preview": new_preview,
                    "old_preview": old_preview,
                    "diff": "\n".join(diff_lines),
                    # Each changed setting as {"old": ..., "new": ...}.
                    "data_source": {
                        field: {"old": page.get(field), "new": value}
                        for field, value in data_source.items()
                    },
                }
            },
        )

    def invalid(
        self, message: str, argument_names: list[str]
    ) -> ToolArgumentValidationError:
        return ToolArgumentValidationError(
            message, tool_name=self.name, argument_names=argument_names
        )
