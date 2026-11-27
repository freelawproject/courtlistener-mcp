"""Document text: fetching it through the shared document cache, reading
it in chunks, and searching it for snippets."""

import math
import re

from courtlistener import AsyncCourtListener
from courtlistener.exceptions import CourtListenerAPIError

from courtlistener_mcp.session import get_session


async def fetch_document_text(
    document_type: str, document_id: int, client: AsyncCourtListener
) -> str | None:
    """Return full document text, fetching from the API on cache miss."""
    document_types = {
        "opinion": ("opinions", "html_with_citations"),
        "recap_document": ("recap_documents", "plain_text"),
    }
    if document_type not in document_types:
        raise ValueError(f"Unknown document_type: {document_type!r}")

    session = get_session()
    cached = await session.get_document(document_type, document_id)
    if cached is not None:
        return cached

    resource_name, field = document_types[document_type]
    item = await getattr(client, resource_name).get(
        document_id, fields=[field]
    )
    text = item.get(field) or ""

    if text:
        await session.store_document(document_type, document_id, text)

    return text or None


def document_not_found(document_type: str, document_id: int) -> str:
    """The error a document tool reports for a document CourtListener
    doesn't have."""
    label = {"recap_document": "RECAP document"}.get(
        document_type, document_type
    )
    return f"No {label} found with id {document_id}."


DEFAULT_CHUNK_SIZE = 8000


def past_end_note(indexes: list[int], total_chunks: int) -> str:
    """Explain chunk indexes past the end of a document."""
    verb, pronoun = ("are", "them") if len(indexes) > 1 else ("is", "it")
    return (
        f"chunk_index {', '.join(map(str, indexes))} {verb} past the end "
        f"of this document, which has {total_chunks} chunk(s) "
        f"(0-{total_chunks - 1}). No text returned for {pronoun}."
    )


def chunk_text(
    text: str,
    chunk_index: int | list[int] | None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict:
    """The whole text, or the chunk(s) of it at *chunk_index*.

    Returns ``total_chars`` with either ``text`` (the whole document, or
    one chunk) or ``chunks`` (several), plus the paging fields and a
    ``note`` for indexes past the end.
    """
    total_chars = len(text)
    total_chunks = math.ceil(total_chars / chunk_size)
    result: dict = {"total_chars": total_chars}

    if chunk_index is None:
        result["text"] = text
    elif isinstance(chunk_index, list):
        out_of_range = [i for i in chunk_index if i >= total_chunks]
        result["chunk_size"] = chunk_size
        result["total_chunks"] = total_chunks
        result["chunks"] = [
            {
                "chunk_index": i,
                "text": text[i * chunk_size : (i + 1) * chunk_size],
            }
            for i in chunk_index
            if i < total_chunks
        ]
        if out_of_range:
            result["note"] = past_end_note(out_of_range, total_chunks)
    else:
        result["chunk_index"] = chunk_index
        result["chunk_size"] = chunk_size
        result["total_chunks"] = total_chunks
        if chunk_index >= total_chunks:
            result["note"] = past_end_note([chunk_index], total_chunks)
        else:
            start = chunk_index * chunk_size
            result["text"] = text[start : start + chunk_size]

    return result


DEFAULT_SNIPPET_SIZE = 300
MAX_SNIPPETS = 20


def find_snippets(
    text: str, query: str, snippet_size: int = DEFAULT_SNIPPET_SIZE
) -> tuple[int, list[dict]]:
    """Return (match_count, snippets) for a case-insensitive literal
    search of *text*, with up to ``MAX_SNIPPETS`` snippets."""
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = list(pattern.finditer(text))
    snippets = []
    for m in matches[:MAX_SNIPPETS]:
        start = max(0, m.start() - snippet_size)
        end = min(len(text), m.end() + snippet_size)
        snippet_text = text[start:end]
        if start > 0:
            snippet_text = "..." + snippet_text
        if end < len(text):
            snippet_text = snippet_text + "..."
        snippets.append({"position": m.start(), "text": snippet_text})
    return len(matches), snippets


async def search_document_text(
    document_type: str,
    document_id: int,
    query: str,
    snippet_size: int,
    client: AsyncCourtListener,
) -> dict:
    """Search one document's text, reporting a missing document in an
    ``error`` field instead of raising, so it doesn't sink a batch."""
    # "opinion" -> "opinion_id", "recap_document" -> "recap_document_id"
    result: dict = {f"{document_type}_id": document_id, "query": query}

    try:
        text = await fetch_document_text(document_type, document_id, client)
    except CourtListenerAPIError as exc:
        if exc.status_code != 404:
            raise
        result["error"] = document_not_found(document_type, document_id)
        return result

    if not text:
        result["error"] = "No text is available for this document."
        return result

    match_count, snippets = find_snippets(text, query, snippet_size)
    result.update(
        {
            "total_chars": len(text),
            "match_count": match_count,
            "shown": len(snippets),
            "snippets": snippets,
        }
    )
    return result
