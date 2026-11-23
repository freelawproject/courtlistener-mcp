from __future__ import annotations

from mcp.types import ToolAnnotations

from courtlistener_mcp.lib.citation_analysis import extract_citations
from courtlistener_mcp.tools.base import MCPTool


class ExtractCitationsTool(MCPTool):
    """Extract and resolve legal citations from text using eyecite.

    Runs locally with no API calls or rate limits. Handles all
    citation types: full case citations, id., supra, short cites,
    and statutes.

    Use this tool to understand the citation structure of a document
    before selectively verifying citations with analyze_citations.
    """

    name: str = "extract_citations"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Extract Citations",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Legal text to extract citations from.",
                },
                "resolve": {
                    "type": "boolean",
                    "description": (
                        "Whether to resolve id./supra/short cites to "
                        "their antecedents. Defaults to true."
                    ),
                    "default": True,
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> str:
        return extract_citations(
            arguments["text"], resolve=arguments.get("resolve", True)
        )
