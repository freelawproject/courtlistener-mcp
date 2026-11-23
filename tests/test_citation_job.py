"""Unit tests for CitationJob, the stored state of a citation analysis."""

from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from courtlistener.exceptions import CourtListenerAPIError
from eyecite import get_citations, resolve_citations

from courtlistener_mcp.lib.citation_jobs import (
    MAX_CITATIONS_PER_REQUEST,
    CitationJob,
)
from courtlistener_mcp.session import InMemorySession, get_session, set_session
from courtlistener_mcp.tools.analyze_citations import AnalyzeCitationsTool
from courtlistener_mcp.tools.resume_citation_analysis import (
    ResumeCitationAnalysisTool,
)

TEXT = (
    "See Brown v. Board of Education, 347 U.S. 483 (1954). "
    "Brown, 347 U.S. at 495. Id. at 496. "
    "Also Gideon v. Wainwright, 372 U.S. 335 (1963)."
)


def job_from(text: str) -> CitationJob:
    return CitationJob.from_resolutions(resolve_citations(get_citations(text)))


class TestFromResolutions:
    def test_collects_unique_case_citations_in_order(self):
        job = job_from(TEXT)
        assert job.unique_citations == ["347 U.S. 483", "372 U.S. 335"]
        assert job.pending == ["347 U.S. 483", "372 U.S. 335"]
        assert job.verified == {}

    def test_counts_references_by_type(self):
        job = job_from(TEXT)
        count, breakdown = job.references("347 U.S. 483")
        assert count == 3
        assert "1 full" in breakdown
        assert "1 short" in breakdown
        assert "1 id." in breakdown

    def test_keeps_the_input_case_name(self):
        job = job_from(TEXT)
        assert job.input_case_names["347 U.S. 483"] == (
            "Brown v. Board of Education"
        )

    def test_slip_opinion_without_page_is_unresolvable_up_front(self):
        job = job_from("Smith v. Jones, 586 U. S. ___ (2019).")
        [key] = job.unique_citations
        assert key.endswith(" None")
        assert job.pending == []
        assert job.verified[key]["status"] is None


class TestRecordResults:
    def test_found_result_is_summarized_and_leaves_pending(self):
        job = CitationJob(unique_citations=["1 U.S. 1"], pending=["1 U.S. 1"])
        job.record_results(
            [
                {
                    "citation": "1 U.S. 1",
                    "status": 200,
                    "clusters": [
                        {
                            "id": 7,
                            "case_name": "A v. B",
                            "docket": 9,
                            "citations": [
                                {"volume": 1, "reporter": "U.S.", "page": 1}
                            ],
                        }
                    ],
                }
            ],
            ["1 U.S. 1"],
        )
        assert job.pending == []
        [cluster] = job.verified["1 U.S. 1"]["clusters"]
        assert cluster["cluster_id"] == 7
        assert cluster["docket_id"] == 9
        assert cluster["citations"] == ["1 U.S. 1"]

    def test_matches_results_case_insensitively(self):
        job = CitationJob(unique_citations=["1 U.S. 1"], pending=["1 U.S. 1"])
        job.record_results(
            [{"citation": "1 u.s. 1", "status": 404, "clusters": []}],
            ["1 U.S. 1"],
        )
        assert job.verified["1 U.S. 1"]["status"] == 404

    def test_rate_limited_citation_stays_pending(self):
        job = CitationJob(unique_citations=["1 U.S. 1"], pending=["1 U.S. 1"])
        job.record_results(
            [{"citation": "1 U.S. 1", "status": 429}], ["1 U.S. 1"]
        )
        assert job.pending == ["1 U.S. 1"]
        assert job.verified == {}

    def test_citation_without_a_result_becomes_unresolvable(self):
        job = CitationJob(unique_citations=["1 U.S. 1"], pending=["1 U.S. 1"])
        job.record_results([], ["1 U.S. 1"])
        assert job.pending == []
        assert job.verified["1 U.S. 1"]["error_message"] == (
            "No result returned by API"
        )


class TestStorage:
    def test_round_trips_through_json(self):
        job = job_from(TEXT)
        stored = json.loads(json.dumps(job.to_dict()))
        assert CitationJob.from_dict(stored) == job

    def test_loads_a_job_stored_before_input_case_names(self):
        job = CitationJob.from_dict(
            {
                "resource_refs": {},
                "unique_citations": ["1 U.S. 1"],
                "verified": {},
                "pending": ["1 U.S. 1"],
            }
        )
        assert job.input_case_names == {}
        assert job.pending == ["1 U.S. 1"]


def test_next_batch_is_capped():
    keys = [f"{i} U.S. 1" for i in range(MAX_CITATIONS_PER_REQUEST + 5)]
    job = CitationJob(unique_citations=keys, pending=list(keys))
    assert job.next_batch() == keys[:MAX_CITATIONS_PER_REQUEST]


class TestAnalyzeThenResume:
    """The job analyze_citations stores is the one resume picks up."""

    @pytest.fixture(autouse=True)
    def in_memory_session(self, monkeypatch):
        # The session is keyed by the user's credential.
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "test-token")
        set_session(InMemorySession())
        yield
        set_session(None)

    def test_rate_limited_analysis_resumes_from_the_stored_job(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.citation_lookup.lookup_text = AsyncMock(
            side_effect=[
                CourtListenerAPIError(429, {}, MagicMock()),
                [
                    {"citation": "347 U.S. 483", "status": 404},
                    {"citation": "372 U.S. 335", "status": 404},
                ],
            ]
        )
        with (
            patch.object(
                AnalyzeCitationsTool, "get_client", return_value=client
            ),
            patch.object(
                ResumeCitationAnalysisTool, "get_client", return_value=client
            ),
        ):
            first = asyncio.run(AnalyzeCitationsTool().call({"text": TEXT}))
            job_id = re.search(r"Job ID: (\w+)", first).group(1)
            assert "Verification: 0 of 2 verified." in first
            assert "Rate limited" in first

            resumed = asyncio.run(
                ResumeCitationAnalysisTool().call({"job_id": job_id})
            )
        assert "Verification: 2 of 2 verified." in resumed
        assert "Newly verified (2)" in resumed
        assert "References in document: 3" in resumed
        stored = asyncio.run(get_session().get_citation_analysis(job_id))
        assert CitationJob.from_dict(stored).pending == []


def test_from_dict_ignores_unknown_keys():
    """A job stored by a newer version still loads after a rollback."""
    job = CitationJob.from_dict(
        {"unique_citations": ["1 U.S. 1"], "pending": [], "added_later": 1}
    )
    assert job == CitationJob(unique_citations=["1 U.S. 1"])


class TestMultipleBatches:
    """More than one request's worth of citations, with a per-citation
    429 inside a batch."""

    @pytest.fixture(autouse=True)
    def in_memory_session(self, monkeypatch):
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "test-token")
        set_session(InMemorySession())
        yield
        set_session(None)

    def test_resumes_until_every_citation_is_verified(self):
        count = MAX_CITATIONS_PER_REQUEST + 10
        text = " ".join(
            f"Case{i} v. Other{i}, {i + 1} U.S. 1 (1950)."
            for i in range(count)
        )
        throttled = {"5 U.S. 1"}
        sent: list[list[str]] = []

        async def lookup_text(compact, **kwargs):
            batch = compact.split("; ")
            sent.append(batch)
            results = []
            for key in batch:
                if key in throttled:
                    throttled.discard(key)
                    results.append({"citation": key, "status": 429})
                else:
                    results.append(
                        {"citation": key, "status": 404, "clusters": []}
                    )
            return results

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.citation_lookup.lookup_text = lookup_text
        with (
            patch.object(
                AnalyzeCitationsTool, "get_client", return_value=client
            ),
            patch.object(
                ResumeCitationAnalysisTool, "get_client", return_value=client
            ),
        ):
            first = asyncio.run(AnalyzeCitationsTool().call({"text": text}))
            job_id = re.search(r"Job ID: (\w+)", first).group(1)
            assert (
                f"Verification: {MAX_CITATIONS_PER_REQUEST - 1} of {count}"
                in first
            )
            second = asyncio.run(
                ResumeCitationAnalysisTool().call({"job_id": job_id})
            )
        assert [len(batch) for batch in sent] == [
            MAX_CITATIONS_PER_REQUEST,
            11,
        ]
        assert sent[1][0] == "5 U.S. 1"
        assert f"Verification: {count} of {count} verified." in second
        assert "All citations verified!" in second
