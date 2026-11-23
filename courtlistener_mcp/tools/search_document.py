from typing import ClassVar

from mcp.types import ToolAnnotations

from courtlistener_mcp.lib.documents import (
    DEFAULT_SNIPPET_SIZE,
    MAX_SNIPPETS,
    search_document_text,
)
from courtlistener_mcp.tools.base import (
    DOCUMENT_ID_ARGUMENTS,
    MCPTool,
    resolve_document_arguments,
)

MAX_DOCS_PER_CALL = 10


class SearchDocumentTool(MCPTool):
    """Search for snippets within one or more court opinions or RECAP documents.

    Performs a case-insensitive literal search (similar to grep) and
    returns up to 20 matching excerpts per document with surrounding
    context.  Use this to locate specific language—a party name, a
    statutory citation, a key phrase—without reading whole documents.

    Pass a list of IDs (up to 10) to search several
    documents in a single call.  Results are returned as a list; errors
    on individual documents are included as an ``error`` field so one
    unavailable document does not abort the rest.

    When ``match_count`` exceeds ``shown``, the first 20
    matches are returned.  Use ``read_document`` with ``chunk_index`` to
    read the area around a match's ``position`` if you need more context.

    Input should include exactly one of opinion_id, recap_document_id, or cluster_id.
    """

    name: str = "search_document"
    argument_aliases: ClassVar[dict[str, str]] = {"q": "query"}
    annotations: ToolAnnotations = ToolAnnotations(
        title="Search Document",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "opinion_id": {
                    "anyOf": [
                        {"type": "integer"},
                        {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 1,
                            "maxItems": MAX_DOCS_PER_CALL,
                        },
                    ],
                    "description": (
                        "ID or list of IDs of opinions to search "
                        f"(up to {MAX_DOCS_PER_CALL})."
                    ),
                },
                "recap_document_id": {
                    "anyOf": [
                        {"type": "integer"},
                        {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 1,
                            "maxItems": MAX_DOCS_PER_CALL,
                        },
                    ],
                    "description": (
                        "ID or list of IDs of RECAP documents to search "
                        f"(up to {MAX_DOCS_PER_CALL})."
                    ),
                },
                "cluster_id": {
                    "type": "integer",
                    "description": (
                        "ID of an opinion cluster (the `cluster_id` in "
                        "search results).  Searches the case's main "
                        "opinion; every opinion in the cluster (with "
                        "type and author) is listed in `cluster_opinions`, "
                        "so concurrences and dissents can be searched by "
                        "`opinion_id`."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Literal phrase to search for (case-insensitive). "
                        f"Up to {MAX_SNIPPETS} matches are returned per document."
                    ),
                },
                "snippet_size": {
                    "type": "integer",
                    "description": (
                        "Characters of context to show on each side of a "
                        f"match (default {DEFAULT_SNIPPET_SIZE})."
                    ),
                    "minimum": 50,
                    "default": DEFAULT_SNIPPET_SIZE,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict:
        self.require_one_of(arguments, *DOCUMENT_ID_ARGUMENTS)
        cluster_id = arguments.get("cluster_id")
        query: str = arguments["query"]
        snippet_size = arguments.get("snippet_size", DEFAULT_SNIPPET_SIZE)

        async with self.get_client() as client:
            (
                document_type,
                raw,
                cluster_opinions,
            ) = await resolve_document_arguments(arguments, client)
            multi = isinstance(raw, list)
            document_ids = raw if multi else [raw]

            results = [
                await search_document_text(
                    document_type, document_id, query, snippet_size, client
                )
                for document_id in document_ids
            ]

        if multi:
            return {"results": results}

        result = results[0]
        if cluster_id is not None:
            result = {"cluster_id": cluster_id, **result}
            result["cluster_opinions"] = cluster_opinions
        return result
