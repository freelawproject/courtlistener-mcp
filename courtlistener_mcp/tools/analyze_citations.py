from __future__ import annotations

from mcp.types import ToolAnnotations

from courtlistener_mcp.lib.citation_analysis import analyze_text
from courtlistener_mcp.lib.opinions import (
    describe_opinion,
)
from courtlistener_mcp.tools.base import MCPTool, resolve_document_arguments


class AnalyzeCitationsTool(MCPTool):
    """Analyze and verify legal citations against CourtListener.

    Extracts all citations locally using eyecite, then verifies each
    unique case citation against CourtListener's database via the
    citation-lookup API. Returns case name, date, citation count,
    and verification status for each citation.

    For documents with more than 250 unique case citations, the first
    batch is verified immediately and a job_id is returned. Use
    resume_citation_analysis to continue verifying remaining citations.

    Terminology in the output:

    * **citation occurrence** — each citation as it appears in the text.
    * **unique citation string** — distinct ``volume reporter page``
      triples (e.g., one case cited three times is one string).
    * **unique case cluster** — distinct CourtListener case clusters
      after parallel-citation dedup (several strings may map to one).

    Case-name cross-check: when a citation verifies by reporter but
    its input case name differs significantly from the cluster's
    canonical name, a WARNING is emitted flagging a possible
    hallucinated citation.

    Input should include exactly one of opinion_id or cluster_id.
    """

    name: str = "analyze_citations"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Analyze Citations",
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
                    "description": (
                        "Legal text to analyze. Citations will be "
                        "extracted locally and verified against "
                        "CourtListener."
                    ),
                },
                "opinion_id": {
                    "type": "integer",
                    "description": (
                        "Alternatively, if the opinion is available "
                        "in CourtListener, you can provide the opinion ID"
                    ),
                },
                "cluster_id": {
                    "type": "integer",
                    "description": (
                        "ID of an opinion cluster (the `cluster_id` in "
                        "search results).  Analyzes the case's main "
                        "opinion; ids for any concurrences or dissents "
                        "are named in the output so they can be "
                        "analyzed separately."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> str:
        text = arguments.get("text")
        opinion_id = arguments.get("opinion_id")
        cluster_id = arguments.get("cluster_id")

        self.require_one_of(arguments, "text", "opinion_id", "cluster_id")

        note = ""
        async with self.get_client() as client:
            siblings = ""
            if text is None:
                _, opinion_id, resolved = await resolve_document_arguments(
                    arguments, client
                )
                if len(resolved) > 1:
                    others = ", ".join(
                        describe_opinion(opinion) for opinion in resolved[1:]
                    )
                    siblings = (
                        "Analyze the others separately, one call per "
                        f"opinion_id: {others}."
                    )
                    note = (
                        f"Analyzed opinion {opinion_id}, the main opinion "
                        f"of {len(resolved)} in cluster {cluster_id}. "
                        f"{siblings}\n\n"
                    )

            if opinion_id is not None:
                opinion = await client.opinions.get(opinion_id)
                text = opinion.get("html_with_citations")
                if not text:
                    if cluster_id is not None:
                        raise ValueError(
                            f"Text not available for opinion {opinion_id} "
                            f"of cluster {cluster_id}. {siblings}".strip()
                        )
                    raise ValueError(
                        "Text not available for opinion ID. If this id "
                        "came from a search result it may be a "
                        "cluster_id, which is a separate id-space; pass "
                        "it as cluster_id instead."
                    )

            assert text is not None  # for mypy
            return note + await analyze_text(text, client)
