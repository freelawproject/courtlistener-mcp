from courtlistener.exceptions import CourtListenerAPIError
from mcp.types import ToolAnnotations

from courtlistener_mcp.lib.documents import (
    DEFAULT_CHUNK_SIZE,
    chunk_text,
    document_not_found,
    fetch_document_text,
)
from courtlistener_mcp.tools.base import (
    DOCUMENT_ID_ARGUMENTS,
    MCPTool,
    resolve_document_arguments,
)

MAX_CHUNKS_PER_CALL = 10


class ReadDocumentTool(MCPTool):
    """Read the full text of a court opinion or RECAP document.

    Fetches the document text and either returns it in full or as one or
    more paginated chunks.  For opinions, uses the ``html_with_citations``
    field (the most complete text representation).  For RECAP documents,
    uses ``plain_text``.

    **Usage patterns**

    - *Full read*: omit ``chunk_index`` to receive the entire document
      along with its ``total_chars``.
    - *Single chunk*: pass an integer ``chunk_index`` (0-based) to
      receive one window of ``chunk_size`` characters.  The response
      includes ``total_chunks`` so you can jump directly to any part of
      the document (e.g. set ``chunk_index`` to ``total_chunks - 1`` to
      read the conclusion).
    - *Multiple chunks*: pass a list of chunk indexes to retrieve several
      non-contiguous windows in a single call (up to
      10).  Useful when you already know the chunk
      size from a previous call and want the next N pages at once.

    Input should include exactly one of opinion_id, recap_document_id, or cluster_id.
    """

    name: str = "read_document"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Read Document",
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
                    "type": "integer",
                    "description": "ID of the opinion to read.",
                },
                "recap_document_id": {
                    "type": "integer",
                    "description": "ID of the RECAP document to read.",
                },
                "cluster_id": {
                    "type": "integer",
                    "description": (
                        "ID of an opinion cluster (the `cluster_id` in "
                        "search results).  Reads the case's main "
                        "opinion; every opinion in the cluster (with "
                        "type and author) is listed in `cluster_opinions`, "
                        "so concurrences and dissents can be read by "
                        "`opinion_id`."
                    ),
                },
                "chunk_index": {
                    "anyOf": [
                        {"type": "integer", "minimum": 0},
                        {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0},
                            "minItems": 1,
                            "maxItems": MAX_CHUNKS_PER_CALL,
                        },
                    ],
                    "description": (
                        "0-based index (or list of indexes) of the chunk(s) "
                        "to return.  Omit to receive the full document text."
                    ),
                },
                "chunk_size": {
                    "type": "integer",
                    "description": (
                        f"Characters per chunk (default {DEFAULT_CHUNK_SIZE}). "
                        "Only relevant when chunk_index is supplied."
                    ),
                    "minimum": 100,
                    "default": DEFAULT_CHUNK_SIZE,
                },
            },
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict:
        self.require_one_of(arguments, *DOCUMENT_ID_ARGUMENTS)
        cluster_id = arguments.get("cluster_id")
        chunk_index = arguments.get("chunk_index")
        chunk_size = arguments.get("chunk_size", DEFAULT_CHUNK_SIZE)

        async with self.get_client() as client:
            (
                document_type,
                document_id,
                cluster_opinions,
            ) = await resolve_document_arguments(arguments, client)
            # Echo the id argument(s) the caller gave.
            ids: dict = (
                {"cluster_id": cluster_id, "opinion_id": document_id}
                if cluster_id is not None
                else {f"{document_type}_id": document_id}
            )

            try:
                text = await fetch_document_text(
                    document_type, document_id, client
                )
            except CourtListenerAPIError as exc:
                # In cluster mode the resolution already succeeded, so a
                # missing main opinion keeps the other opinions usable.
                if cluster_id is None or exc.status_code != 404:
                    raise
                return {
                    **ids,
                    "error": document_not_found(document_type, document_id),
                    "cluster_opinions": cluster_opinions,
                }

        result: dict = dict(ids)
        if cluster_opinions:
            result["cluster_opinions"] = cluster_opinions

        if not text:
            result["error"] = "No text is available for this document."
            return result

        result.update(chunk_text(text, chunk_index, chunk_size))
        return result
