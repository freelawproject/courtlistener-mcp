"""Identify citations and compare their case names with
CourtListener's."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullCitation,
    FullLawCitation,
    IdCitation,
    ShortCaseCitation,
    SupraCitation,
    UnknownCitation,
)
from eyecite.utils import DISALLOWED_NAMES

# Similarity below this is flagged as a possible hallucinated citation
# (volume+reporter+page match, but the case name does not).
CASE_NAME_MATCH_THRESHOLD = 0.8


_VS_PATTERN = re.compile(r"\b(vs?\.?|versus)\b", re.IGNORECASE)
_NON_WORD_PATTERN = re.compile(r"[^\w\s]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


# Generic party-name phrases drawn from eyecite's DISALLOWED_NAMES list.
# Only the lowercase-in-source entries are party terms worth stripping
# ("state", "united states", etc.); the capitalized AG-surname entries in
# that list exist for eyecite's own extraction filter, not for
# name-weight adjustment. Sorted longest-first so multi-word phrases
# (e.g. "united states") match before their single-word overlaps.
_STOP_PHRASES: tuple[tuple[str, ...], ...] = tuple(
    sorted(
        (tuple(p.split()) for p in DISALLOWED_NAMES if p == p.lower()),
        key=len,
        reverse=True,
    )
)


def normalize_case_name(name: str | None) -> str:
    """Normalize a case name for comparison.

    Lowercases, collapses ``v.``/``vs.``/``versus`` to ``v``, strips
    punctuation, and collapses whitespace. Returns empty string for
    None/empty input.
    """
    if not name:
        return ""
    s = name.lower()
    s = _VS_PATTERN.sub("v", s)
    s = _NON_WORD_PATTERN.sub(" ", s)
    s = _WHITESPACE_PATTERN.sub(" ", s).strip()
    return s


def _strip_generic_party_terms(normalized: str) -> str:
    """Drop tokens matching generic party phrases (e.g. "united states").

    Operates on an already-normalized string (lowercase, punctuation
    stripped). Multi-word phrases are matched greedily against contiguous
    token runs.
    """
    tokens = normalized.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        for phrase in _STOP_PHRASES:
            n = len(phrase)
            if tuple(tokens[i : i + n]) == phrase:
                i += n
                break
        else:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def case_name_similarity(a: str | None, b: str | None) -> float:
    """Return a 0.0-1.0 similarity score between two case names.

    Generic party phrases from eyecite's DISALLOWED_NAMES (e.g.
    ``"united states"``, ``"state"``, ``"people"``) are stripped before
    token comparison so the signal comes from the discriminating parts
    of the name, not shared prosecutorial prefixes. Combines token-set
    Jaccard with a subset boost (short form contained in long form
    scores 1.0) and falls back to character-level ``difflib`` ratio for
    non-tokenizable edge cases. Returns 0.0 if either side normalizes
    to empty.
    """
    na, nb = normalize_case_name(a), normalize_case_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Prefer comparing the discriminating tokens. Fall back to the
    # unstripped forms when stripping empties one side (e.g. a name made
    # entirely of generic terms).
    sa, sb = _strip_generic_party_terms(na), _strip_generic_party_terms(nb)
    if not sa or not sb:
        sa, sb = na, nb
    ta, tb = set(sa.split()), set(sb.split())
    if ta and tb:
        smaller, larger = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        if smaller.issubset(larger):
            return 1.0
        jaccard = len(ta & tb) / len(ta | tb)
    else:
        jaccard = 0.0
    return max(jaccard, SequenceMatcher(None, sa, sb).ratio())


def input_case_name(cite: FullCaseCitation) -> str | None:
    """Extract the input case name from an eyecite FullCaseCitation.

    Returns ``"Plaintiff v. Defendant"`` when both are present, otherwise
    whichever single party name is available, or None.
    """
    meta = cite.metadata
    plaintiff = getattr(meta, "plaintiff", None)
    defendant = getattr(meta, "defendant", None)
    if plaintiff and defendant:
        return f"{plaintiff} v. {defendant}"
    return plaintiff or defendant or None


def case_name_mismatch(result: dict, input_case_name: str | None) -> bool:
    """True if a FOUND result's cluster name diverges from the input name.

    Only reports mismatches for status=200 with both an input case name
    and a verified cluster name available.
    """
    if not input_case_name or result.get("status") != 200:
        return False
    clusters = result.get("clusters", [])
    if not clusters:
        return False
    verified_name = clusters[0].get("case_name")
    if not verified_name:
        return False
    similarity = case_name_similarity(input_case_name, verified_name)
    return similarity < CASE_NAME_MATCH_THRESHOLD


def auto_resolve_identical_clusters(
    clusters: list[dict],
) -> dict | None:
    """If all candidate clusters have the same normalized name, pick one.

    Selection: highest ``citation_count`` (tie-break: earliest
    ``date_filed``). Returns the chosen cluster, or None if names differ.
    """
    if len(clusters) < 2:
        return None
    names = {normalize_case_name(c.get("case_name")) for c in clusters}
    names.discard("")
    if len(names) != 1:
        return None

    def sort_key(c: dict) -> tuple[int, str]:
        # Negative citation_count so higher counts sort first; ascending
        # date_filed so the earliest wins on ties.
        return (-(c.get("citation_count") or 0), c.get("date_filed") or "")

    return sorted(clusters, key=sort_key)[0]


def citation_type_label(cite: CitationBase) -> str:
    """Human-readable label for a citation type."""
    labels = {
        FullCaseCitation: "full",
        ShortCaseCitation: "short",
        IdCitation: "id.",
        SupraCitation: "supra",
        FullLawCitation: "statute",
        UnknownCitation: "unknown",
    }
    return labels.get(type(cite), type(cite).__name__)


def canonical_key(cite: FullCitation) -> str:
    """Canonical key for deduplication: 'volume reporter page'."""
    g = cite.groups
    return f"{g['volume']} {g['reporter']} {g['page']}"
