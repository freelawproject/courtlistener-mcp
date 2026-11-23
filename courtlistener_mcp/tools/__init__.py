"""The MCP tools, one module per tool, and the registry (``MCP_TOOLS``).

Tools are thin: each declares its schema and annotations, checks its
arguments, and calls into ``lib`` for the work."""

from courtlistener_mcp.tools.add_docket_to_tag import AddDocketToTagTool
from courtlistener_mcp.tools.analyze_citations import AnalyzeCitationsTool
from courtlistener_mcp.tools.base import MCPTool
from courtlistener_mcp.tools.call_endpoint import CallEndpointTool
from courtlistener_mcp.tools.create_search_alert import CreateSearchAlertTool
from courtlistener_mcp.tools.create_tag import CreateTagTool
from courtlistener_mcp.tools.delete_search_alert import DeleteSearchAlertTool
from courtlistener_mcp.tools.delete_tag import DeleteTagTool
from courtlistener_mcp.tools.extract_citations import ExtractCitationsTool
from courtlistener_mcp.tools.get_api_usage import GetApiUsageTool
from courtlistener_mcp.tools.get_choices import GetChoicesTool
from courtlistener_mcp.tools.get_counts import GetCountsTool
from courtlistener_mcp.tools.get_endpoint_item import GetEndpointItemTool
from courtlistener_mcp.tools.get_endpoint_schema import GetEndpointSchemaTool
from courtlistener_mcp.tools.get_more_results import GetMoreResultsTool
from courtlistener_mcp.tools.pray_for_document import PrayForDocumentTool
from courtlistener_mcp.tools.read_document import ReadDocumentTool
from courtlistener_mcp.tools.remove_docket_from_tag import (
    RemoveDocketFromTagTool,
)
from courtlistener_mcp.tools.resume_citation_analysis import (
    ResumeCitationAnalysisTool,
)
from courtlistener_mcp.tools.search import SearchTool
from courtlistener_mcp.tools.search_document import SearchDocumentTool
from courtlistener_mcp.tools.subscribe_to_docket_alert import (
    SubscribeToDocketAlertTool,
)
from courtlistener_mcp.tools.unsubscribe_from_docket_alert import (
    UnsubscribeFromDocketAlertTool,
)
from courtlistener_mcp.tools.update_tag import UpdateTagTool
from courtlistener_mcp.tools.wiki_list_pages import WikiListPagesTool
from courtlistener_mcp.tools.wiki_read_page import WikiReadPageTool
from courtlistener_mcp.tools.wiki_search import WikiSearchTool
from courtlistener_mcp.tools.withdraw_prayer import WithdrawPrayerTool

MCP_TOOLS: dict[str, MCPTool] = {
    tool.name: tool
    for tool in [
        SearchTool(),
        GetEndpointSchemaTool(),
        CallEndpointTool(),
        GetEndpointItemTool(),
        GetChoicesTool(),
        GetCountsTool(),
        GetMoreResultsTool(),
        ReadDocumentTool(),
        SearchDocumentTool(),
        ExtractCitationsTool(),
        AnalyzeCitationsTool(),
        ResumeCitationAnalysisTool(),
        CreateSearchAlertTool(),
        DeleteSearchAlertTool(),
        SubscribeToDocketAlertTool(),
        UnsubscribeFromDocketAlertTool(),
        PrayForDocumentTool(),
        WithdrawPrayerTool(),
        CreateTagTool(),
        UpdateTagTool(),
        DeleteTagTool(),
        AddDocketToTagTool(),
        RemoveDocketFromTagTool(),
        GetApiUsageTool(),
        WikiListPagesTool(),
        WikiSearchTool(),
        WikiReadPageTool(),
    ]
}
