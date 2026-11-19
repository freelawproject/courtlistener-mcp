---
name: courtlistener-docket-research
description: >-
  Finds and reads federal court dockets and filings in CourtListener's RECAP
  archive of PACER records. Use when the user asks for a docket, the filings or
  latest activity in a federal case, a complaint, motion, order, or brief, cases
  involving a party or attorney, or cases before a particular judge, wants to
  follow a case or get docket alerts, or mentions RECAP or PACER. Load the
  `courtlistener` skill first. Don't use for finding case law by topic; use an
  opinion search for that.
---

# Docket research with CourtListener

RECAP is CourtListener's archive of federal district, bankruptcy, and appellate
records from PACER. Three search types cover it. Pick one before the first call.

| The user wants | `type` | What comes back |
| --- | --- | --- |
| A case and its relevant filings | `r` | Dockets, each with its matching filings nested |
| Specific filings across cases (every motion to dismiss mentioning a term) | `rd` | Individual filings |
| A list of cases, no filings | `d` | Dockets only |

All three accept the same filters. See
[recap-recipes.md](references/recap-recipes.md) for worked examples.

## Step 1: Find the docket

Use the most specific filter you have, in this order:

1. `docket_number` together with `court`. A docket number alone is not unique
   across courts.
2. `case_name`.
3. `party_name` or `atty_name`, narrowed with `court` and a date filter.
4. `q` for free-text terms, narrowed with `nature_of_suit`, `assigned_to`, or
   dates.

Use a small `num_results`. Pass `fields` once you know the result field names
for the type (see the `courtlistener` skill). If several dockets match, show the
user a short list (case name, court, docket number, date filed) and ask which
one, instead of opening each.

## Step 2: Get the filings

- If the `r` search already returned the filings the user asked about, answer
  from it.
- For a fuller list, call `call_endpoint` on `docket-entries` with the docket ID
  in the `docket` filter (the `docket_id` from the search result), and `fields`
  limited to what you need. Sort with `order_by: "-date_filed"` to get the
  latest activity. A recent entry's `description` can be empty until its text
  is added.
- For one kind of filing in a known case, an `rd` search with `docket_number`,
  `court`, and `description` is usually one call.

## Step 3: Read a filing

Only filings whose `is_available` is true have text on CourtListener.

- **Available.** Call `read_document` with `recap_document_id`. For a long
  filing, pass `chunk_index` (a number, or a list of up to 10) instead of
  reading it whole. To find a passage, call `search_document`, which accepts up
  to 10 document IDs and returns matching snippets.
- **Not available.** Say that the filing exists on the docket but its text has
  not been added to CourtListener. Don't try to fetch the PDF from a storage
  URL. Mention that the user can request it through Pray and Pay, and call
  `pray_for_document` only if they ask you to.

Use `available_only: true` in the search when the user needs filings they can
read right now.

## Step 4: Follow a case over time

`subscribe_to_docket_alert` emails the user when a docket changes, and
`create_search_alert` does the same for a saved search. Both change the user's
account. If the user asked for the alert, say what you are doing and make the
call. If it is your suggestion, offer it and wait for a yes.

## Reporting

- Give the case name, court, docket number, and a link built from
  `https://www.courtlistener.com` plus the result's URL path.
- List filings with entry number, date, and description. Mark which ones are
  available to read.
- RECAP holds what users and Free Law Project have contributed from PACER, so a
  docket can be incomplete or out of date. Say when the newest entry is dated,
  and don't describe a missing filing as never filed.
