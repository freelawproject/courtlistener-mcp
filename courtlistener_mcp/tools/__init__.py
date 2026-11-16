from courtlistener_mcp.tools.analyze_citations_tool import (
    AnalyzeCitationsTool,
)
from courtlistener_mcp.tools.call_endpoint_tool import CallEndpointTool
from courtlistener_mcp.tools.create_search_alert_tool import (
    CreateSearchAlertTool,
)
from courtlistener_mcp.tools.delete_search_alert_tool import (
    DeleteSearchAlertTool,
)
from courtlistener_mcp.tools.extract_citations_tool import (
    ExtractCitationsTool,
)
from courtlistener_mcp.tools.get_api_usage_tool import GetApiUsageTool
from courtlistener_mcp.tools.get_choices_tool import GetChoicesTool
from courtlistener_mcp.tools.get_counts_tool import GetCountsTool
from courtlistener_mcp.tools.get_endpoint_item_tool import (
    GetEndpointItemTool,
)
from courtlistener_mcp.tools.get_endpoint_schema_tool import (
    GetEndpointSchemaTool,
)
from courtlistener_mcp.tools.get_more_results_tool import (
    GetMoreResultsTool,
)
from courtlistener_mcp.tools.mcp_tool import MCPTool
from courtlistener_mcp.tools.pray_for_document_tool import (
    PrayForDocumentTool,
)
from courtlistener_mcp.tools.read_document_tool import ReadDocumentTool
from courtlistener_mcp.tools.resume_citation_analysis_tool import (
    ResumeCitationAnalysisTool,
)
from courtlistener_mcp.tools.search_document_tool import SearchDocumentTool
from courtlistener_mcp.tools.search_tool import SearchTool
from courtlistener_mcp.tools.subscribe_to_docket_alert_tool import (
    SubscribeToDocketAlertTool,
)
from courtlistener_mcp.tools.unsubscribe_from_docket_alert_tool import (
    UnsubscribeFromDocketAlertTool,
)
from courtlistener_mcp.tools.wiki_list_pages_tool import WikiListPagesTool
from courtlistener_mcp.tools.wiki_read_page_tool import WikiReadPageTool
from courtlistener_mcp.tools.wiki_search_tool import WikiSearchTool
from courtlistener_mcp.tools.withdraw_prayer_tool import WithdrawPrayerTool

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
        GetApiUsageTool(),
        WikiListPagesTool(),
        WikiSearchTool(),
        WikiReadPageTool(),
    ]
}
