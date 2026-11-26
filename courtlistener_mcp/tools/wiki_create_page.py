from fastmcp.tools import ToolResult
from mcp.types import TextContent, ToolAnnotations

from courtlistener_mcp.exceptions import ToolArgumentValidationError
from courtlistener_mcp.lib.views import WIKI_EDIT_VIEW
from courtlistener_mcp.lib.wiki import (
    DATA_SOURCE_FIELDS,
    DATA_SOURCE_PROPERTIES,
    page_path,
    wiki_oauth_token,
    wiki_page_url,
)
from courtlistener_mcp.lib.wiki_edits import (
    PROPOSAL_META_KEY,
    render_preview,
    store_proposal,
    without_nulls,
)
from courtlistener_mcp.tools.base import WikiTool


class WikiCreatePageTool(WikiTool):
    """Propose a new Free Law Project wiki page in a directory you can
    edit. The user reviews it and creates it; nothing is saved by this
    tool.

    `directory` is an existing directory's path, e.g. `engineering`; the
    new page takes its visibility and edit permissions from it, and pages
    can't be created at the top level. `content` is the page's Markdown
    source. `data_source_url` and `data_source_ttl` give the page a data
    source for `[[ key ]]` placeholders.

    The user is shown the page, rendered and as source, with a Create
    button. Only the user can create it: don't ask them to confirm in
    chat, and don't propose the same page again while they're reviewing
    it. A title already used in the directory gets a numbered path
    (`-2`), so if a create seems to have failed, search for the page
    before proposing it again.
    """

    name: str = "wiki_create_page"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Create Wiki Page",
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
                "directory": {
                    "type": "string",
                    "description": "The directory's path, e.g. `engineering`.",
                },
                "title": {"type": "string", "description": "The page title."},
                "content": {
                    "type": "string",
                    "description": "The page's Markdown source.",
                },
                "change_message": {
                    "type": "string",
                    "description": "A short description of the change.",
                },
                **DATA_SOURCE_PROPERTIES,
            },
            "required": ["directory", "title", "content", "change_message"],
            "additionalProperties": False,
        }

    async def call_wiki(self, arguments: dict) -> ToolResult:
        wiki_oauth_token()
        arguments = without_nulls(arguments)
        if not arguments["directory"].strip().strip("/"):
            raise ToolArgumentValidationError(
                "`directory` must name a directory: pages can't be created "
                "at the top level.",
                tool_name=self.name,
                argument_names=["directory"],
            )
        # Taken as a path, a URL or a link, as the other wiki tools take
        # a page's.
        directory = page_path(
            arguments["directory"], self.name, "directory", "directory"
        )
        data_source = {
            field: arguments[field]
            for field in DATA_SOURCE_FIELDS
            if field in arguments
        }
        content, title = arguments["content"], arguments["title"]
        preview = await render_preview(
            content, data_source.get("data_source_url")
        )

        token, expires_at = await store_proposal(
            {
                "action": "create",
                "directory": directory,
                "title": title,
                "content": content,
                "change_message": arguments["change_message"],
                **data_source,
            }
        )
        url = wiki_page_url(directory)
        summary = (
            f"Proposed a new page {title!r} in {directory!r} "
            f"({len(content.splitlines())} lines). It is shown to the user "
            "for review; nothing is saved until they click Create in that "
            "view. If they say no review view appeared, their client can't "
            f"show it, and they can create the page in the wiki: {url}"
        )
        return ToolResult(
            content=[TextContent(type="text", text=summary)],
            meta={
                PROPOSAL_META_KEY: {
                    "action": "create",
                    "token": token,
                    "expires_at": expires_at,
                    "path": directory,
                    "url": url,
                    "title": title,
                    "new_title": title,
                    "change_message": arguments["change_message"],
                    "new_source": content,
                    # Rendered HTML, or None if the wiki couldn't render it.
                    "new_preview": preview,
                    # Each setting as {"old": None, "new": ...}.
                    "data_source": {
                        field: {"old": None, "new": value}
                        for field, value in data_source.items()
                    },
                }
            },
        )
