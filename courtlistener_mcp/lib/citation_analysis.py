"""Citation analysis end to end: extract citations with eyecite, verify
them against CourtListener in batches, keep the job in the session for
resuming, and render the report."""

from __future__ import annotations

import asyncio
from typing import Any

from courtlistener import AsyncCourtListener
from courtlistener.exceptions import CourtListenerAPIError
from eyecite import get_citations, resolve_citations
from eyecite.models import CitationBase

from courtlistener_mcp.lib.citation_jobs import (
    CitationJob,
    build_compact_string,
)
from courtlistener_mcp.lib.citation_matching import citation_type_label
from courtlistener_mcp.lib.citation_rendering import (
    format_analysis,
    format_rate_limit_note,
    format_resolved_citations,
    format_resume,
)
from courtlistener_mcp.session import get_session, make_id

RESUME_TOOL = "resume_citation_analysis"

MAX_TEXT_LENGTH = 1_000_000


async def find_citations(
    text: str, *, resolve: bool = True
) -> tuple[list[CitationBase], dict[Any, list[CitationBase]]]:
    """Run eyecite's extraction (and resolution) in a worker thread.

    Both are CPU-bound and pure Python; on a long opinion they take long
    enough that running them on the event loop stalls every other request
    on the worker. In a thread the GIL still serializes the work, but the
    loop gets switched back in every few milliseconds, so other requests
    keep moving. Resolutions are empty when *resolve* is false or nothing
    was found.
    """

    def work() -> tuple[list[CitationBase], dict[Any, list[CitationBase]]]:
        cites = get_citations(text)
        resolutions = resolve_citations(cites) if resolve and cites else {}
        return cites, resolutions

    return await asyncio.to_thread(work)


async def extract_citations(text: str, resolve: bool = True) -> str:
    """List the citations in *text*, grouped by what they refer to when
    *resolve* is true. Runs locally, with no API calls."""
    cites, resolutions = await find_citations(text, resolve=resolve)
    if not cites:
        return "No citations found."
    if resolve:
        return format_resolved_citations(cites, resolutions)
    lines = [f"Found {len(cites)} citation(s):\n"]
    for i, cite in enumerate(cites, 1):
        label = citation_type_label(cite)
        lines.append(f'  {i}. [{label}] "{cite.matched_text()}"')
    return "\n".join(lines)


async def verify_next_batch(
    job: CitationJob,
    client: AsyncCourtListener,
    *,
    retry_on_rate_limit: bool = False,
) -> Any:
    """Send the job's next batch to the citation-lookup API and record
    the results.

    Returns the rate-limit detail when the API throttled the whole
    request (the batch stays pending), otherwise None.
    """
    batch = job.next_batch()
    if not batch:
        return None
    try:
        results = await client.citation_lookup.lookup_text(
            build_compact_string(batch),
            retry_on_rate_limit=retry_on_rate_limit,
        )
    except CourtListenerAPIError as e:
        if e.status_code != 429:
            raise
        return e.detail
    job.record_results(results, batch)
    return None


async def analyze_text(text: str, client: AsyncCourtListener) -> str:
    """Analyze the citations in *text*: verify the first batch, store the
    job for ``resume_citation_analysis``, and render the report."""
    cites, resolutions = await find_citations(text)
    if not cites:
        return "No citations found."

    job = CitationJob.from_resolutions(resolutions)
    rate_limit_detail = await verify_next_batch(job, client)

    analysis_id = make_id()
    await get_session().store_citation_analysis(analysis_id, job.to_dict())

    output = format_analysis(analysis_id, cites, resolutions, job)
    if rate_limit_detail is not None:
        output += "\n\n" + format_rate_limit_note(
            rate_limit_detail, resumable_with=RESUME_TOOL
        )
    return output


async def resume_analysis(
    job_id: str, client: AsyncCourtListener, *, wait: bool = False
) -> str | None:
    """Verify the next batch of a stored analysis and render what changed.

    Returns None when the session has no job with this id.
    """
    stored = await get_session().get_citation_analysis(job_id)
    if stored is None:
        return None
    job = CitationJob.from_dict(stored)

    if not job.pending:
        return f"Job {job_id!r} is already complete.  All citations processed."

    previously_verified = set(job.verified)
    rate_limit_detail = await verify_next_batch(
        job, client, retry_on_rate_limit=wait
    )
    if rate_limit_detail is not None:
        return (
            format_resume(job_id, job, set())
            + "\n\n"
            + format_rate_limit_note(
                rate_limit_detail, resumable_with=RESUME_TOOL
            )
        )
    newly_verified = set(job.verified) - previously_verified

    await get_session().store_citation_analysis(job_id, job.to_dict())

    return format_resume(job_id, job, newly_verified)
