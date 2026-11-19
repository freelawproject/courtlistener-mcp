---
name: courtlistener-judge-research
description: >-
  Researches a U.S. judge with CourtListener: biography, court positions and
  appointment, opinions written, oral arguments heard, and judicial financial
  disclosures. Use when the user asks who a judge is, who appointed them, what
  they have ruled or written on a topic, what cases are before them, or what
  their financial disclosures show. Load the `courtlistener` skill first.
---

# Judge research with CourtListener

A full profile can take many calls. Ask what the user needs, or infer it from
the question, and fetch only that part. Offer the other parts at the end.

## Step 1: Identify the judge

Search with `type: "p"` and the `name` filter. Add `court` when you know it,
because common names match many people. Other useful filters: `appointer`,
`political_affiliation`, `school`, `dob_state`, `born_after`, `born_before`.

If more than one person matches, show a short list (name, court, years) and ask
which one. Keep the person's ID from the result; every later step uses it.

## Step 2: Fetch only the part that was asked for

| The user asks about | Call |
| --- | --- |
| Basic biography, who appointed them | The search result usually has it: each entry in its `positions` list names the court, the `appointer`, and the nomination and confirmation dates. Otherwise `get_endpoint_item` on `people`. |
| Courts served, appointment, confirmation, dates | `call_endpoint` on `positions`, filtered by `person`. The `appointer` on a position is the ID of another record, not a name; if the judge search result already names the appointer, use that. |
| Education | `call_endpoint` on `educations`, filtered by `person` |
| Opinions they wrote, or wrote on a topic | `search` with `type: "o"`, the `judge` filter, and `court`; add `q` for the topic |
| Oral arguments they sat on | `search` with `type: "oa"` and the `judge` filter |
| Federal cases assigned to them | `search` with `type: "r"` or `"d"` and `assigned_to`; see the `courtlistener-docket-research` skill |
| Financial disclosures | See below |

The `judge` and `assigned_to` filters match on the name as text, so add `court`
and a date range to keep other judges with the same surname out of the results.

## Step 3: Financial disclosures

Disclosures can't be searched with `search`. They come from the REST endpoints,
in two hops. See [judge-endpoints.md](references/judge-endpoints.md) for the
endpoint names and example calls.

1. List the judge's disclosures: `call_endpoint` on `financial-disclosures`,
   filtered by `person`, with `fields` set to `id`, `year`, `report_type`, and
   `is_amended`. Each record is one filing. If the user named no year, use the
   latest `year` returned and say which year you used.
2. For the filing the user cares about, fetch one category at a time, filtered
   by `financial_disclosure`: `investments`, `gifts`, `debts`, `agreements`,
   `reimbursements`, `non-investment-incomes`, `spouse-incomes`, or
   `disclosure-positions`.

Keep this bounded:

- One judge, one filing, and one or two categories is a handful of calls.
  Several judges or several years multiplies that. Run the most useful slice
  first, show it, and ask before running the rest.
- Investment lists can be long. Pass `fields` and page with `get_more_results`
  only if the user wants the full list.
- Disclosure amounts are reported as value-range codes, not exact figures (for
  example `J` means 1 to 15,000 dollars). The `investments` schema from
  `get_endpoint_schema` lists what every code means. Report the range, and say
  that it is a range.
- Some entries are marked `redacted`. Say so instead of treating them as empty.

## Reporting

- Report only what the records show. Don't add biography, rulings, or
  characterizations of a judge from memory.
- Link the judge's CourtListener page and each case you cite, using
  `https://www.courtlistener.com` plus the result's URL path.
- A disclosure shows what was reported for a year. It is not evidence of a
  conflict in any particular case. If the user is asking about a possible
  conflict, set out the holding, the dates, and the case side by side and let
  them draw the conclusion.
- If CourtListener has no disclosures for a judge or year, say that it has none.
  Don't infer that none were filed.
