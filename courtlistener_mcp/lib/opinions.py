"""Order and summarize the opinions in a cluster."""

from courtlistener import AsyncCourtListener

from courtlistener_mcp.lib.results import collect_results

ORDERED_OPINION_TYPES = (
    ("020lead", "lead-opinion"),
    ("010combined", "combined-opinion"),
    ("015unamimous", "unanimous-opinion"),  # misspelled in the API
    ("025plurality", "plurality-opinion"),
    ("080onthemerits", "on-the-merits"),
)


OPINION_TYPE_RANK = {
    spelling: rank
    for rank, spellings in enumerate(ORDERED_OPINION_TYPES)
    for spelling in spellings
}


def opinion_sort_key(opinion: dict) -> tuple[int, int, int]:
    """Rank an opinion so the court's main opinion sorts first."""
    ordering_key = opinion.get("ordering_key")
    opinion_type: str = opinion.get("type") or ""
    return (
        ordering_key if isinstance(ordering_key, int) else 99999,
        OPINION_TYPE_RANK.get(opinion_type, len(ORDERED_OPINION_TYPES)),
        opinion.get("id") or 0,
    )


def summarize_opinions(opinions: list[dict]) -> list[dict]:
    """Compact, main-opinion-first summary of a cluster's opinions.

    Accepts opinion records from either the search index or the REST
    API and keeps only the identifying fields: ``id``, ``type``, and
    whichever authorship fields are populated.
    """
    valid = [
        opinion
        for opinion in opinions
        if isinstance(opinion, dict) and opinion.get("id") is not None
    ]
    valid.sort(key=opinion_sort_key)
    summary = []
    for opinion in valid:
        entry: dict = {"id": opinion["id"]}
        if opinion.get("type"):
            entry["type"] = opinion["type"]
        if opinion.get("author_str"):
            entry["author"] = opinion["author_str"]
        if opinion.get("author_id") is not None:
            entry["author_id"] = opinion["author_id"]
        if opinion.get("joined_by_str"):
            entry["joined_by"] = opinion["joined_by_str"]
        if opinion.get("joined_by_ids"):
            entry["joined_by_ids"] = opinion["joined_by_ids"]
        if opinion.get("per_curiam"):
            entry["per_curiam"] = True
        summary.append(entry)
    return summary


def describe_opinion(opinion: dict) -> str:
    """Render a summarized opinion as ``id (type, author)`` for prose."""
    details = [
        str(value)
        for value in (opinion.get("type"), opinion.get("author"))
        if value
    ]
    if opinion.get("per_curiam"):
        details.append("per curiam")
    if details:
        return f"{opinion['id']} ({', '.join(details)})"
    return str(opinion["id"])


def add_opinion_ids(results: list[dict]) -> None:
    """Add ``opinion_id`` and ``cluster_opinions`` to opinion search results.

    ``opinion_id`` is the main opinion's id; ``cluster_opinions`` lists
    every opinion in the cluster, main first, with type and authorship.
    """
    for result in results:
        summary = summarize_opinions(result.get("opinions") or [])
        if summary:
            result.setdefault("opinion_id", summary[0]["id"])
            result.setdefault("cluster_opinions", summary)


CLUSTER_OPINION_FIELDS = [
    "id",
    "type",
    "ordering_key",
    "author_str",
    "author_id",
    "joined_by_str",
    "per_curiam",
]


async def resolve_cluster_opinions(
    cluster_id: int, client: AsyncCourtListener
) -> list[dict]:
    """Return a cluster's opinions, summarized, main opinion first."""
    response = client.opinions.list(
        cluster=cluster_id, fields=CLUSTER_OPINION_FIELDS
    )
    opinions = summarize_opinions(await collect_results(response, 20))
    if not opinions:
        raise ValueError(f"Cluster {cluster_id} has no opinions.")
    return opinions
