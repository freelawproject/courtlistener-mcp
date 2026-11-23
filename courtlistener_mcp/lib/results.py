"""Collect, paginate and shape the results of search and endpoint
calls."""

import re

from courtlistener.async_client.resource import AsyncResourceIterator

from courtlistener_mcp.session import get_session, make_id
from courtlistener_mcp.settings import DEFAULT_NUM_RESULTS


def normalize_fields(fields):
    """Accept comma- or space-separated `fields` strings."""
    if isinstance(fields, str):
        return [f for f in re.split(r"[,\s]+", fields.strip(" ,")) if f]
    return fields


async def collect_results(
    response: AsyncResourceIterator, num_results: int = DEFAULT_NUM_RESULTS
) -> list[dict]:
    """Consume up to *num_results* items from an AsyncResourceIterator."""
    results: list[dict] = []
    if num_results <= 0:
        return results
    async for item in response:
        results.append(item)
        if len(results) >= num_results:
            break
    return results


async def prepare_query_id(
    response: AsyncResourceIterator, fields: list[str] | None = None
) -> str:
    """Store the query response and return a short UUID query ID."""
    query_id = make_id()
    data: dict = {"response": await response.dump()}
    if fields is not None:
        data["fields"] = fields
    await get_session().store_query(query_id, data)
    return query_id


def filter_results_by_fields(
    results: list[dict], fields: list[str] | None
) -> tuple[list[dict], bool]:
    """Apply client-side field filtering to a list of result dicts.

    Returns the (possibly filtered) results and a boolean indicating
    whether any requested fields were missing from the data.
    """
    if not fields:
        return results, False
    missing = any(k not in result for result in results for k in fields)
    filtered = [
        {
            k: v
            for k, v in r.items()
            # Always keep the opinion ids to avoid cluster_id confusion
            if k in fields or k in ("opinion_id", "cluster_opinions")
        }
        for r in results
    ]
    return filtered, missing


def prepare_count(count: int | str | None, query_id: str) -> int | str | None:
    if isinstance(count, int):
        return count
    elif isinstance(count, str):
        return (
            f"To get the count use the `get_counts` tool with "
            f'query_id="{query_id}".'
        )
    return None


async def prepare_has_more_str(
    response: AsyncResourceIterator, query_id: str
) -> str | None:
    if await response.has_more():
        return (
            f"More results are available. Use the `get_more_results` "
            f'tool with query_id="{query_id}" to retrieve them.'
        )
    return None
