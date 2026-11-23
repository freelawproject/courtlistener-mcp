"""Render citation extraction and verification results as text."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from courtlistener.async_client.citation_lookup import parse_wait_until
from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullLawCitation,
)
from eyecite.models import (
    Resource as CitationResource,
)

from courtlistener_mcp.lib.citation_jobs import CitationJob
from courtlistener_mcp.lib.citation_matching import (
    CASE_NAME_MATCH_THRESHOLD,
    auto_resolve_identical_clusters,
    canonical_key,
    case_name_mismatch,
    case_name_similarity,
    citation_type_label,
)


def format_rate_limit_note(detail: Any, *, resumable_with: str) -> str:
    """Build a one-line note describing the upstream rate limit.

    Always returns a usable message — when ``wait_until`` can't be
    parsed, falls back to advice without a timestamp. ``resumable_with``
    names the tool to call next (e.g. ``resume_citation_analysis``).
    """
    target = parse_wait_until(detail)
    base = (
        f"Rate limited by the upstream API. Call `{resumable_with}` to "
        f"retry; set `wait=true` to have the server sleep through the "
        f"rate-limit window."
    )
    if target is None:
        return base
    seconds = max(
        0, int((target - datetime.now(timezone.utc)).total_seconds())
    )
    return (
        f"Rate limited by the upstream API (retry in ~{seconds}s, "
        f"wait_until={target.isoformat()}). Call `{resumable_with}` "
        f"with `wait=true` to have the server sleep through the window."
    )


def unresolved_citations(
    cites: list[CitationBase], resolutions: Any
) -> list[CitationBase]:
    """The citations eyecite couldn't tie to any resource."""
    resolved_ids = {
        id(c) for cite_list in resolutions.values() for c in cite_list
    }
    return [c for c in cites if id(c) not in resolved_ids]


def format_unresolved_section(unresolved: list[CitationBase]) -> list[str]:
    """Render the Unresolved section, deduped by (label, matched text).

    Eyecite emits every textual occurrence of short forms (``id.``,
    ``supra``, repeated short cites), so the raw list is noisy. Collapse
    identical rows into one with a reference count, matching how the
    resolved-cases section presents repeats.
    """
    counts: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for c in unresolved:
        key = (citation_type_label(c), c.matched_text() or "")
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1

    lines = ["\nUnresolved:"]
    for i, key in enumerate(order, 1):
        label, text = key
        n = counts[key]
        suffix = f" — {n} reference(s)" if n > 1 else ""
        lines.append(f'  {i}. [{label}] "{text}"{suffix}')
    return lines


def format_resolved_citations(
    cites: list[CitationBase],
    resolutions: Any,
) -> str:
    """Format citations grouped by resolved resource."""
    cases: list[tuple[CitationResource, list[CitationBase]]] = []
    statutes: list[tuple[CitationResource, list[CitationBase]]] = []

    for resource, cite_list in resolutions.items():
        primary = resource.citation
        if isinstance(primary, FullCaseCitation):
            cases.append((resource, cite_list))
        elif isinstance(primary, FullLawCitation):
            statutes.append((resource, cite_list))

    unresolved = unresolved_citations(cites, resolutions)

    total = len(cites)
    parts = []
    summary_parts = []
    if cases:
        summary_parts.append(f"{len(cases)} unique case(s)")
    if statutes:
        summary_parts.append(f"{len(statutes)} statute(s)")
    if unresolved:
        summary_parts.append(f"{len(unresolved)} unresolved")

    parts.append(
        f"Found {total} citation(s) referencing "
        + ", ".join(summary_parts)
        + ".\n"
    )

    if cases:
        parts.append("Cases:")
        for i, (resource, cite_list) in enumerate(cases, 1):
            primary = resource.citation
            key = canonical_key(primary)
            meta = primary.metadata
            name = ""
            if meta.plaintiff and meta.defendant:
                name = f"{meta.plaintiff} v. {meta.defendant}"
            year = meta.year or ""
            header = f"  {i}. {key}"
            if name:
                header += f" ({name}"
                if year:
                    header += f", {year}"
                header += ")"
            elif year:
                header += f" ({year})"
            header += f" — {len(cite_list)} reference(s)"
            parts.append(header)
            for c in cite_list:
                label = citation_type_label(c)
                parts.append(f'       [{label}] "{c.matched_text()}"')

    if statutes:
        parts.append("\nStatutes:")
        for i, (resource, cite_list) in enumerate(statutes, 1):
            primary = resource.citation
            parts.append(
                f'  {i}. "{primary.matched_text()}" '
                f"— {len(cite_list)} reference(s)"
            )
            for c in cite_list:
                if c is not primary:
                    label = citation_type_label(c)
                    parts.append(f'       [{label}] "{c.matched_text()}"')

    if unresolved:
        parts.extend(format_unresolved_section(unresolved))

    return "\n".join(parts)


def _format_found_cluster(
    citation_key: str,
    cluster: dict,
    ref_count: int,
    ref_breakdown: str,
    index: int,
    input_case_name: str | None,
) -> str:
    """Render a FOUND cluster, warning when the input case name diverges."""
    name = cluster.get("case_name", "Unknown")
    date = cluster.get("date_filed", "")
    cite_count = cluster.get("citation_count", 0)
    url = cluster.get("absolute_url", "")
    parallel = cluster.get("citations", [])
    cluster_id = cluster.get("cluster_id")

    similarity: float | None = None
    mismatch = False
    if input_case_name:
        similarity = case_name_similarity(input_case_name, name)
        mismatch = similarity < CASE_NAME_MATCH_THRESHOLD

    header = f"  {index}. {citation_key} — {name}"
    if date:
        header += f" ({date})"
    lines = [header]
    if mismatch:
        lines.append(
            "     WARNING: Input case name "
            f'"{input_case_name}" differs from verified "{name}" '
            f"(similarity {similarity:.2f}). Possible hallucinated citation."
        )
    lines.append(f"     Status: FOUND (cited by {cite_count} opinion(s))")
    if cluster_id is not None:
        lines.append(f"     Cluster ID: {cluster_id}")
    lines.append(f"     References in document: {ref_count} ({ref_breakdown})")
    if url:
        lines.append(f"     URL: https://www.courtlistener.com{url}")
    if parallel:
        lines.append(f"     Parallel citations: {', '.join(parallel)}")
    return "\n".join(lines)


def format_verification_result(
    citation_key: str,
    result: dict,
    ref_count: int,
    ref_breakdown: str,
    index: int,
    input_case_name: str | None = None,
) -> str:
    """Format a single verified citation for display.

    When ``input_case_name`` is provided and a FOUND result's cluster
    case name differs significantly (similarity below
    ``CASE_NAME_MATCH_THRESHOLD``), a warning is prepended to flag
    possible hallucinated citations. An AMBIGUOUS result whose candidate
    clusters all share the same normalized name is auto-resolved to the
    most-cited cluster, tie-breaking on earliest ``date_filed``.
    """
    status = result.get("status")
    if status == 200:
        clusters = result.get("clusters", [])
        if not clusters:
            return (
                f"  {index}. {citation_key}\n"
                f"     Status: FOUND (no cluster details)\n"
                f"     References in document: {ref_count} ({ref_breakdown})"
            )
        cluster = clusters[0]
        return _format_found_cluster(
            citation_key,
            cluster,
            ref_count,
            ref_breakdown,
            index,
            input_case_name,
        )

    elif status == 404:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: NOT FOUND — may be incorrect or not in CourtListener\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status == 300:
        clusters = result.get("clusters", [])
        resolved = auto_resolve_identical_clusters(clusters)
        if resolved is not None:
            other_ids = [
                c.get("cluster_id")
                for c in clusters
                if c is not resolved and c.get("cluster_id") is not None
            ]
            note = (
                f"     Auto-resolved from {len(clusters)} clusters with "
                f"identical name; other cluster IDs: "
                f"{', '.join(str(i) for i in other_ids)}"
            )
            body = _format_found_cluster(
                citation_key,
                resolved,
                ref_count,
                ref_breakdown,
                index,
                input_case_name,
            )
            return body + "\n" + note

        candidate_lines = []
        for c in clusters:
            name = c.get("case_name", "?")
            cid = c.get("cluster_id")
            date = c.get("date_filed") or ""
            count = c.get("citation_count")
            extras = []
            if cid is not None:
                extras.append(f"cluster_id={cid}")
            if date:
                extras.append(date)
            if count is not None:
                extras.append(f"cited by {count}")
            suffix = f" ({'; '.join(extras)})" if extras else ""
            candidate_lines.append(f"       - {name}{suffix}")
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: AMBIGUOUS — matches {len(clusters)} cases:\n"
            + "\n".join(candidate_lines)
            + f"\n     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status == 400:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: INVALID — could not be parsed by the API\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    elif status is None:
        error = result.get("error_message", "")
        reason = error if error else "citation not recognized by API"
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: UNRESOLVABLE — {reason}\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )
    else:
        return (
            f"  {index}. {citation_key}\n"
            f"     Status: {status}\n"
            f"     References in document: {ref_count} ({ref_breakdown})"
        )


def format_analysis(
    analysis_id: str,
    cites: list[CitationBase],
    resolutions: Any,
    job: CitationJob,
) -> str:
    """Format the full analysis output.

    Terminology used below:

    * **citation occurrence** — one citation as it appears in the text.
    * **unique citation string** — distinct ``volume reporter page``
      triples; many occurrences can share one string (e.g., a case cited
      three times).
    * **unique case cluster** — distinct CourtListener case clusters
      after parallel-citation dedup; several strings can map to one
      cluster.
    """
    unique_citations = job.unique_citations
    verified = job.verified
    pending = job.pending
    input_case_names = job.input_case_names
    # Count by type
    case_count = sum(
        1 for r in resolutions if isinstance(r.citation, FullCaseCitation)
    )
    statute_count = sum(
        1 for r in resolutions if not isinstance(r.citation, FullCaseCitation)
    )
    unresolved = unresolved_citations(cites, resolutions)

    parts = [f"Citation Analysis (Job ID: {analysis_id})\n"]

    # Summary line
    extraction_parts = [f"{len(cites)} citation occurrence(s)"]
    extraction_parts.append(
        f"{len(unique_citations)} unique citation string(s)"
    )
    if case_count:
        extraction_parts.append(f"{case_count} unique case cluster(s)")
    if statute_count:
        extraction_parts.append(f"{statute_count} statute(s)")
    if unresolved:
        extraction_parts.append(f"{len(unresolved)} unresolved")
    parts.append("Extraction: " + ", ".join(extraction_parts) + ".")

    verified_count = len(verified)
    total_unique = len(unique_citations)
    pending_count = len(pending)
    verification_line = (
        f"Verification: {verified_count} of {total_unique} verified."
    )
    if pending_count:
        verification_line += (
            f" ({pending_count} pending — use resume_citation_analysis "
            f'with job_id="{analysis_id}")'
        )
    parts.append(verification_line)

    mismatch_count = sum(
        1
        for key in verified
        if case_name_mismatch(verified[key], input_case_names.get(key))
    )
    if mismatch_count:
        parts.append(
            f"WARNING: {mismatch_count} citation(s) matched by reporter "
            "but case name differs significantly — possible hallucinations."
        )

    # Verified cases
    if verified or pending:
        parts.append("\nCases:")
        idx = 1
        for key in unique_citations:
            ref_count, ref_breakdown = job.references(key)
            if key in verified:
                parts.append(
                    format_verification_result(
                        key,
                        verified[key],
                        ref_count,
                        ref_breakdown,
                        idx,
                        input_case_names.get(key),
                    )
                )
            else:
                parts.append(f"  {idx}. {key}\n     Status: PENDING")
            idx += 1

    # Statutes
    statute_resources = [
        (r, cl)
        for r, cl in resolutions.items()
        if not isinstance(r.citation, FullCaseCitation)
    ]
    if statute_resources:
        parts.append("\nStatutes:")
        for i, (resource, cite_list) in enumerate(statute_resources, 1):
            primary = resource.citation
            count = len(cite_list)
            parts.append(
                f'  {i}. "{primary.matched_text()}" — {count} reference(s)'
            )

    # Unresolved
    if unresolved:
        parts.extend(format_unresolved_section(unresolved))

    return "\n".join(parts)


def format_resume(
    job_id: str,
    job: CitationJob,
    newly_verified: set[str],
) -> str:
    """Format the resume output showing newly verified citations."""
    verified = job.verified
    pending = job.pending
    unique = job.unique_citations
    input_case_names = job.input_case_names
    total = len(unique)

    parts = [f"Citation Analysis (Job ID: {job_id}) — Resumed\n"]

    parts.append(f"Verification: {len(verified)} of {total} verified.")
    if pending:
        parts.append(
            f"({len(pending)} still pending — call "
            f'resume_citation_analysis again with job_id="{job_id}")'
        )
    else:
        parts.append("All citations verified!")

    if newly_verified:
        parts.append(f"\nNewly verified ({len(newly_verified)}):")
        idx = 1
        for key in unique:
            if key in newly_verified:
                ref_count, ref_breakdown = job.references(key)
                parts.append(
                    format_verification_result(
                        key,
                        verified[key],
                        ref_count,
                        ref_breakdown,
                        idx,
                        input_case_names.get(key),
                    )
                )
                idx += 1
    elif pending:
        parts.append(
            "\nNo new citations verified in this batch "
            "(may still be rate-limited)."
        )

    return "\n".join(parts)
