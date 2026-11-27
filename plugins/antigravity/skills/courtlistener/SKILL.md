---
name: courtlistener
description: >-
  Foundation skill for the CourtListener MCP server. Load it before the first
  CourtListener tool call in a conversation. Covers which search type to use,
  how to keep calls few, how to handle rate limits and sign-in errors, when the
  account-changing tools may be used, and how to report results. Use when the
  user asks to find a court opinion, case, docket, filing, judge, or oral
  argument, asks about U.S. case law, or mentions CourtListener, RECAP, or
  PACER. Don't use for legal advice or for courts outside the United States.
---

# CourtListener

CourtListener is Free Law Project's free database of U.S. court records. This
plugin connects to its hosted MCP server. The server sends its own usage notes
when it connects (where `fields` goes, search versus API field names, reading
document text, link formats). Follow those notes; this skill adds what they
leave out.

## 1. Pick the right search type

`search` takes a `type`. Choosing the wrong one is the most common wasted call.

| The user wants | `type` | Then |
| --- | --- | --- |
| Case law, a decision, cases citing a case | `o` | `read_document` or `search_document` for the text |
| A federal case's docket with its matching filings | `r` | See the `courtlistener-docket-research` skill |
| Individual federal filings | `rd` | Same skill |
| Federal dockets only, no filings | `d` | Same skill |
| A judge | `p` | See the `courtlistener-judge-research` skill |
| Oral argument audio | `oa` | Filter with `court`, `argued_after`, `argued_before`, `judge` |

Each type accepts different filters. A filter that isn't valid for the chosen
type is rejected. See [search-types.md](references/search-types.md) for the
filters, sort orders, and date formats of every type.

For an open-ended legal question, start with one semantic opinion search
(`type: "o"`, `semantic: true`, plain-language `q`). For a known case name,
citation, or phrase, use keyword search with the matching filter (`case_name`,
`citation`, `docket_number`).

## 2. Keep calls few

Every call spends the user's CourtListener API quota, and the quota can be
small: an account may be limited to a handful of requests per minute. Send only
a few calls in one turn, and call `get_api_usage` (which is free) if you need to
know the limits before a larger job.

- Plan before the first call. Start with the single best search. Add another
  call only if the results leave a gap.
- Pass `fields` to keep results small, and set `num_results` to what you need
  (default 20, maximum 100). In `search`, a field name that doesn't exist is
  not an error: the response carries a `missing_fields` warning that lists the
  available names, so correct the list on the next call. If you don't know the
  result field names for a search type yet, make the first search with a small
  `num_results` and no `fields`, then use `fields` from then on.
- To see more of the same results, call `get_more_results` with the earlier
  `query_id`. Don't repeat the search.
- If a search result already answers the question, answer from it. Don't fetch
  the full record just to confirm.
- When you have an ID, use `get_endpoint_item`. It needs no schema lookup first.
- Document text is cached on the server for an hour, so re-reading a document
  you just opened is cheap. Pagination cursors and citation jobs expire after
  about an hour of inactivity.
- `extract_citations` runs on the server without calling the CourtListener API,
  so it doesn't spend quota.
- One tool call can spend more than one request. The document tools spend one
  per document, or two for an opinion whose citation-linked text is missing and
  they fall back to another text field. Passing a `cluster_id` costs an extra
  request to look up the cluster's opinions. Pass the `opinion_id` from the
  search result when you have it.

For anything beyond search and document reading (clusters, docket entries,
parties, financial disclosures, citation graphs), see
[api-endpoints.md](references/api-endpoints.md).

## 3. Rate limits and errors

- **HTTP 429 or a rate-limit message.** Don't retry in a loop. Call
  `get_api_usage`, which works even while other tools are throttled. Read the
  `user` scope: it is the main quota. Tell the user what is used, what remains,
  and when it resets (`reset_at`). If the reset is seconds away, wait once and
  retry once. Otherwise answer with what you have and say which lookups were
  skipped.
- **"Unauthorized" or HTTP 401.** The sign-in expired or was revoked. Retry
  once. If it fails again, ask the user to reconnect CourtListener in the
  plugin's settings.
- **A filter or field is rejected.** Don't guess again. Check
  [search-types.md](references/search-types.md) for `search`, or call
  `get_endpoint_schema` for `call_endpoint`, then fix the request.
- **Results look empty or wrong.** Try one broader query (fewer filters). If it
  is still empty, say so and suggest the user try the same query at
  https://www.courtlistener.com/.

## 4. Tools that change the user's account

`create_search_alert`, `delete_search_alert`, `subscribe_to_docket_alert`,
`unsubscribe_from_docket_alert`, `pray_for_document`, and `withdraw_prayer`
change the user's CourtListener account. Call them only when the user asks for
that action. When they have asked (for example "subscribe me to this docket"),
say in one line what you are doing and make the call in the same turn; no second
confirmation is needed. When it is your idea, offer it and wait for a yes. Never
call them as a side effect of research.

## 5. What you send leaves the user's machine

Everything in a tool's inputs is sent to CourtListener's server, including the
`text` given to `extract_citations` and `analyze_citations` (the extraction runs
on that server, not on the user's machine). Describe the legal issue in general
terms: case names, citations, courts, judges, topics. Before sending the text of
a private document (a draft brief, a client memo), confirm with the user that it
may be shared with an outside service. Case names and citations the user asks
about directly need no confirmation. Citations lifted from a private document
are different, because the list can reveal what the document argues: ask before
sending them, as the `courtlistener-verify-citations` skill describes.

## 6. Reporting results

- Report only what the tools returned. Don't add holdings, outcomes, dates, or
  docket numbers from memory. Never invent an ID or a citation.
- For each case give the name, court, date, and a link. Build the link from
  `https://www.courtlistener.com` plus the result's `absolute_url`.
- For "recent" or "latest" requests, add a date filter and say which period
  you searched: `filed_after` for opinions, `entry_date_filed_after` for
  filings (in RECAP searches `filed_after` is the date the case began).
- A case can have several opinions (majority, concurrence, dissent). Check
  `cluster_opinions` before describing what a court held.
- If something is outside CourtListener's coverage, say so plainly instead of
  guessing. For coverage and how-to questions about CourtListener itself, use
  `wiki_search` and `wiki_read_page` (or `wiki_list_pages` to browse), when
  those tools are available, to check Free Law Project's documentation.
- You are a research aid, not a lawyer. Present what the records say and let the
  user draw the legal conclusion.
