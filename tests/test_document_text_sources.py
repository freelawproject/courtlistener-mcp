"""Document text falls back across text fields and reports its source."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from courtlistener_mcp.lib.documents import (
    OPINION_TEXT_FIELDS,
    fetch_document_text,
)
from courtlistener_mcp.session import InMemorySession, get_session, set_session
from courtlistener_mcp.tools.analyze_citations import AnalyzeCitationsTool
from courtlistener_mcp.tools.read_document import ReadDocumentTool
from courtlistener_mcp.tools.search_document import SearchDocumentTool


@pytest.fixture(autouse=True)
def in_memory_session():
    set_session(InMemorySession())
    yield
    set_session(None)


def make_client(opinion: dict | None = None, recap: dict | None = None):
    client = MagicMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False

    def getter(record):
        async def get(document_id, fields=None):
            return {f: (record or {}).get(f, "") for f in fields}

        return get

    client.opinions.get.side_effect = getter(opinion)
    client.recap_documents.get.side_effect = getter(recap)
    return client


def fetch(document_type, client):
    return asyncio.run(fetch_document_text(document_type, 1, client))


def run_get_document(document_type):
    return asyncio.run(get_session().get_document(document_type, 1))


class TestFetchDocumentText:
    def test_fallback_order_matches_courtlistener(self):
        # CourtListener's own best-text order (OPINION_TEXT_SOURCE_FIELDS).
        assert OPINION_TEXT_FIELDS == [
            "html_with_citations",
            "xml_harvard",
            "xml_scan",
            "html_columbia",
            "html_lawbox",
            "html_anon_2020",
            "html",
            "plain_text",
        ]

    def test_prefers_html_with_citations_in_one_request(self):
        client = make_client(
            {"html_with_citations": "<p>cited</p>", "plain_text": "plain"}
        )
        assert fetch("opinion", client) == (
            "<p>cited</p>",
            "html_with_citations",
        )
        client.opinions.get.assert_called_once_with(
            1, fields=["html_with_citations"]
        )

    def test_falls_back_in_order_with_one_more_request(self):
        client = make_client({"html": "<p>html</p>", "plain_text": "plain"})
        assert fetch("opinion", client) == ("<p>html</p>", "html")
        assert client.opinions.get.call_count == 2
        assert (
            client.opinions.get.call_args.kwargs["fields"]
            == (OPINION_TEXT_FIELDS[1:])
        )

    @pytest.mark.parametrize("field", OPINION_TEXT_FIELDS)
    def test_every_opinion_field_is_a_source(self, field):
        assert fetch("opinion", make_client({field: "text"})) == (
            "text",
            field,
        )

    def test_no_text_in_any_field(self):
        client = make_client({})
        assert fetch("opinion", client) is None
        assert run_get_document("opinion") is None

    def test_recap_uses_plain_text_only(self):
        client = make_client(recap={"plain_text": "filed"})
        assert fetch("recap_document", client) == ("filed", "plain_text")
        client.recap_documents.get.assert_called_once_with(
            1, fields=["plain_text"]
        )

    def test_recap_without_plain_text_makes_one_request(self):
        client = make_client(recap={})
        assert fetch("recap_document", client) is None
        client.recap_documents.get.assert_called_once()

    def test_cache_keeps_the_source(self):
        fetch("opinion", make_client({"xml_harvard": "<opinion/>"}))
        client = make_client({})
        assert fetch("opinion", client) == ("<opinion/>", "xml_harvard")
        client.opinions.get.assert_not_called()


class TestTextSourceInResponses:
    def test_read_document(self):
        client = make_client({"plain_text": "plain"})
        with patch.object(ReadDocumentTool, "get_client", return_value=client):
            result = asyncio.run(ReadDocumentTool().call({"opinion_id": 1}))
        assert result["text_source"] == "plain_text"
        assert result["text"] == "plain"

    def test_search_document(self):
        client = make_client({"html_lawbox": "<p>needle</p>"})
        with patch.object(
            SearchDocumentTool, "get_client", return_value=client
        ):
            result = asyncio.run(
                SearchDocumentTool().call({"opinion_id": 1, "query": "needle"})
            )
        assert result["text_source"] == "html_lawbox"
        assert result["match_count"] == 1

    def test_no_text_has_no_source(self):
        client = make_client({})
        with patch.object(ReadDocumentTool, "get_client", return_value=client):
            result = asyncio.run(ReadDocumentTool().call({"opinion_id": 1}))
        assert "text_source" not in result
        assert result["error"] == "No text is available for this document."

    def test_analyze_citations_verifies_citations_from_fallback_markup(
        self, monkeypatch
    ):
        # The stored citation job is keyed by the user's credential.
        monkeypatch.setenv("COURTLISTENER_API_TOKEN", "test-token")
        client = make_client(
            {
                "xml_harvard": (
                    "<opinion><p>As held in Brown v. Board of Education, "
                    "347 U.S. 483 (1954), segregation is unlawful.</p>"
                    "</opinion>"
                )
            }
        )
        client.citation_lookup.lookup_text = AsyncMock(
            return_value=[{"citation": "347 U.S. 483", "status": 404}]
        )
        with patch.object(
            AnalyzeCitationsTool, "get_client", return_value=client
        ):
            output = asyncio.run(
                AnalyzeCitationsTool().call({"opinion_id": 1})
            )
        client.citation_lookup.lookup_text.assert_awaited_once()
        sent = client.citation_lookup.lookup_text.await_args.args[0]
        assert "347 U.S. 483" in sent
        assert output.startswith("Text source: xml_harvard.\n\n")
        assert "347 U.S. 483" in output

    def test_analyze_citations_uses_the_fallback(self):
        client = make_client({"plain_text": "no citations here"})
        with patch.object(
            AnalyzeCitationsTool, "get_client", return_value=client
        ):
            output = asyncio.run(
                AnalyzeCitationsTool().call({"opinion_id": 1})
            )
        assert output == "Text source: plain_text.\n\nNo citations found."
