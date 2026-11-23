from urllib.parse import quote

from mcp.types import ToolAnnotations

from courtlistener_mcp.exceptions import WikiAPIError
from courtlistener_mcp.lib.wiki import page_path, tidy_page, wiki_get
from courtlistener_mcp.tools.base import WikiTool


class WikiReadPageTool(WikiTool):
    """Read one Free Law Project wiki page as Markdown.

    `path` is the page's `path` from `wiki_list_pages` or `wiki_search`,
    e.g. `engineering/deploys`. The page's `url` works too, as do links
    found in page content, such as `/c/engineering/deploys/`. An
    `#anchor` on any of them is ignored. Returns the page's path, title,
    description, `updated_at`, `url` and its `content` as Markdown, with
    data placeholders filled in and wiki links resolved. It also gives
    the page's `revision` and whether you `can_edit` it; if you can, it
    gives the page's data source too (`data_source_url`, the JSON its
    `[[ key ]]` placeholders are filled from, and `data_source_ttl`).
    Directories aren't pages: to see a directory's pages, search it with
    `in:<directory path>`.
    """

    name: str = "wiki_read_page"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Read Wiki Page",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "The page's path, e.g. `engineering/deploys`, its "
                        "wiki URL, or a link from page content (`#...` or "
                        "`/c/...`)."
                    ),
                },
                "raw": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Return the page's source instead, including wiki "
                        "syntax such as `#path` links and `[[ placeholders "
                        "]]`. Use it to see exactly how a page is written; "
                        "leave it off to read the page."
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def call_wiki(self, arguments: dict) -> dict:
        path = page_path(arguments["path"], self.name)
        params = {"raw": "true"} if arguments.get("raw") else {}
        try:
            page = await wiki_get(f"pages/{quote(path, safe='/')}", **params)
        except WikiAPIError as exc:
            if exc.status != "404":
                raise
            raise WikiAPIError(
                f"The wiki has no page you can read at {path!r}. If that's "
                "a directory, search its pages with `wiki_search` and "
                f"`in:{path}`.",
                exc.status,
            ) from exc
        return tidy_page(page)
