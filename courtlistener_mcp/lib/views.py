"""The MCP App views the server offers: pages in ``assets/html/`` that hosts
show alongside a tool's result. Each is served as a resource, and the tools
that show it point at it with ``View.tool_meta``."""

from dataclasses import dataclass, field

from fastmcp.apps import AppConfig, app_config_to_meta_dict

from courtlistener_mcp.lib.web import render


@dataclass(frozen=True)
class View:
    name: str
    description: str
    page: str
    """The page under ``assets/html/``."""
    app: AppConfig = field(
        default_factory=lambda: AppConfig(prefers_border=True)
    )

    @property
    def uri(self) -> str:
        return f"ui://courtlistener/{self.page}"

    def html(self) -> str:
        return render(f"html/{self.page}")

    def tool_meta(self, **config) -> dict:
        """A tool's ``_meta`` pointing at this view. As the MCP Apps SDK's
        ``registerAppTool`` does, it carries the URI under the older flat
        ``ui/resourceUri`` key too, for hosts that only read that."""
        ui = app_config_to_meta_dict(
            AppConfig(resource_uri=self.uri, **config)
        )
        return {"ui": ui, "ui/resourceUri": self.uri}


WIKI_EDIT_VIEW = View(
    name="wiki_edit_review",
    description="Review and save a proposed wiki edit or new page.",
    page="wiki-edit.html",
)

MCP_VIEWS = [WIKI_EDIT_VIEW]
