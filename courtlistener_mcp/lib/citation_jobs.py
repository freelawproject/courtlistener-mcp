"""The state of a citation analysis, kept between verification batches."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from eyecite.models import FullCaseCitation

from courtlistener_mcp.lib.citation_matching import (
    canonical_key,
    citation_type_label,
    input_case_name,
)

# Delimiter used between citations in the compact string sent to the
# citation-lookup API.  Semicolon-space is a natural Bluebook list
# separator that eyecite reliably parses without cleanup.
CITATION_DELIMITER = "; "

# Maximum citations per API request before 429 throttling.
MAX_CITATIONS_PER_REQUEST = 250


def build_compact_string(unique_citations: list[str]) -> str:
    """Join unique citation strings with our delimiter for the API."""
    return CITATION_DELIMITER.join(unique_citations)


def summarize_cluster(cluster: dict) -> dict:
    """Keep the cluster fields the analysis output uses."""
    return {
        "cluster_id": cluster.get("id"),
        "case_name": cluster.get("case_name"),
        "case_name_short": cluster.get("case_name_short"),
        "date_filed": cluster.get("date_filed"),
        "citation_count": cluster.get("citation_count"),
        "precedential_status": cluster.get("precedential_status"),
        "absolute_url": cluster.get("absolute_url"),
        "docket_id": cluster.get("docket"),
        "citations": [
            f"{c['volume']} {c['reporter']} {c['page']}"
            for c in cluster.get("citations", [])
            if c.get("volume") and c.get("reporter") and c.get("page")
        ],
    }


def unresolvable_result(key: str, error_message: str) -> dict:
    """A verification result for a citation the API can't resolve."""
    return {
        "status": None,
        "citation": key,
        "clusters": [],
        "error_message": error_message,
    }


@dataclass
class CitationJob:
    """A citation analysis: what was found and how far verification got.

    ``analyze_citations`` builds one, verifies the first batch and stores
    it in the session; ``resume_citation_analysis`` loads it to verify
    the next batch. Every field is keyed by a unique citation string
    (``volume reporter page``):

    * ``unique_citations``: the case citations to verify, in text order.
    * ``resource_refs``: how often each is referenced in the text
      (``ref_count``) and by which citation types (``ref_breakdown``).
    * ``input_case_names``: the case name the text gives, when it has one.
    * ``verified``: the summarized citation-lookup result for each
      citation verified so far.
    * ``pending``: the citations still to send to the API.
    """

    unique_citations: list[str] = field(default_factory=list)
    resource_refs: dict[str, dict] = field(default_factory=dict)
    input_case_names: dict[str, str] = field(default_factory=dict)
    verified: dict[str, dict] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)

    @classmethod
    def from_resolutions(cls, resolutions: Any) -> CitationJob:
        """Start a job from eyecite's resolved citations.

        Slip opinion citations without a page number (keys like
        ``"586 U. S. None"``) can't be resolved by the API, so they are
        marked unresolvable up front instead of being sent.
        """
        job = cls()
        seen: set[str] = set()
        for resource, cite_list in resolutions.items():
            primary = getattr(resource, "citation", None)
            if not isinstance(primary, FullCaseCitation):
                continue
            key = canonical_key(primary)
            counts: dict[str, int] = {}
            for c in cite_list:
                label = citation_type_label(c)
                counts[label] = counts.get(label, 0) + 1
            job.resource_refs[key] = {
                "ref_count": sum(counts.values()),
                "ref_breakdown": ", ".join(
                    f"{v} {k}" for k, v in counts.items()
                ),
            }
            if key in seen:
                continue
            seen.add(key)
            job.unique_citations.append(key)
            name = input_case_name(primary)
            if name:
                job.input_case_names[key] = name
            if key.endswith(" None"):
                job.verified[key] = unresolvable_result(
                    key, "Slip opinion citation without page number"
                )
            else:
                job.pending.append(key)
        return job

    @classmethod
    def from_dict(cls, data: dict) -> CitationJob:
        """Load a job stored with ``to_dict``; missing fields default."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def to_dict(self) -> dict:
        """The job as JSON-ready data for the session store.

        Not a deep copy: the session encodes it straight away.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def next_batch(self) -> list[str]:
        """The pending citations to send in the next API request."""
        return self.pending[:MAX_CITATIONS_PER_REQUEST]

    def references(self, key: str) -> tuple[int, str]:
        """How often *key* is referenced in the text, and as what."""
        refs = self.resource_refs.get(key, {})
        return refs.get("ref_count", 1), refs.get("ref_breakdown", "")

    def record_results(self, results: list[dict], batch: list[str]) -> None:
        """Record the API's results for *batch*.

        Each API result is matched back to the batch citation it belongs
        to by comparing the citation text. Results with status 429 are
        left in pending for later retry.

        After processing all results, any batch citations that received
        no API result at all are marked as unresolvable and removed from
        pending. Without this sweep, citations the API doesn't recognize
        (e.g. slip opinion cites like "586 U. S. None") would stay in
        pending forever, causing resume_citation_analysis to loop
        infinitely.
        """
        rate_limited_keys: set[str] = set()

        for result in results:
            citation_text = result.get("citation", "")
            status = result.get("status")

            # Match this result to a batch citation
            matched_key = None
            if citation_text in batch:
                matched_key = citation_text
            else:
                normalized = citation_text.strip().lower()
                for key in batch:
                    if key.strip().lower() == normalized:
                        matched_key = key
                        break

            if matched_key is None:
                continue

            if status == 429:
                # Rate-limited — leave in pending for retry
                rate_limited_keys.add(matched_key)
                continue

            self.verified[matched_key] = {
                "status": status,
                "citation": citation_text,
                "clusters": [
                    summarize_cluster(cluster)
                    for cluster in result.get("clusters", [])
                ],
                "error_message": result.get("error_message"),
            }
            if matched_key in self.pending:
                self.pending.remove(matched_key)

        # Sweep: mark batch citations that got no API result as
        # unresolvable. Only skip citations that were explicitly
        # rate-limited (429), since those should genuinely be retried.
        for key in batch:
            if key in self.verified or key in rate_limited_keys:
                continue
            self.verified[key] = unresolvable_result(
                key, "No result returned by API"
            )
            if key in self.pending:
                self.pending.remove(key)
