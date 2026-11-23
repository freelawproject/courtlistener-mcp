from __future__ import annotations

from mcp.types import ToolAnnotations

from courtlistener_mcp.exceptions import SessionDataNotFoundError
from courtlistener_mcp.lib.citation_analysis import resume_analysis
from courtlistener_mcp.tools.base import MCPTool


class ResumeCitationAnalysisTool(MCPTool):
    """Resume verifying citations from a previous analysis.

    Use this after analyze_citations returns with pending citations
    due to rate limiting (more than 250 unique case citations).
    Takes the job_id and verifies the next batch.
    """

    name: str = "resume_citation_analysis"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Resume Citation Analysis",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": (
                        "The job ID (short UUID) from a previous "
                        "analyze_citations call."
                    ),
                },
                "wait": {
                    "type": "boolean",
                    "description": (
                        "If true, the server sleeps through the upstream "
                        "rate-limit window (capped at ~90s) and retries "
                        "automatically. Use this after a previous call "
                        "reported a short wait_until. Default false: the "
                        "tool returns immediately on rate limit so you can "
                        "tell the user before waiting."
                    ),
                    "default": False,
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> str:
        job_id = arguments["job_id"]
        wait = bool(arguments.get("wait", False))
        async with self.get_client() as client:
            output = await resume_analysis(job_id, client, wait=wait)
        if output is None:
            raise SessionDataNotFoundError(
                f"Job ID {job_id!r} not found. The session may have expired.",
                tool_name=self.name,
                argument_name="job_id",
            )
        return output
