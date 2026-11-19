# RECAP search recipes

Worked examples for the `search` tool with RECAP types. Replace the values with
the user's. The recipes leave out `fields` for brevity; add the ones you need
from the result field list in the `courtlistener` skill's `search-types.md`.

## Filters available to `r`, `rd`, and `d`

`q`, `court`, `case_name`, `docket_number`, `party_name`, `atty_name`,
`assigned_to`, `referred_to`, `nature_of_suit`, `cause`, `description`,
`document_number`, `attachment_number`, `available_only`, `filed_after`,
`filed_before`, `entry_date_filed_after`, `entry_date_filed_before`, `order_by`.

`filed_*` is the date the case was filed. `entry_date_filed_*` is the date of a
docket entry. Dates accept `2024-01-31` or relative forms such as `past 1 year`.

## A known case by docket number

```json
{"type": "r", "court": "cand", "docket_number": "4:20-cv-05640", "num_results": 5}
```

## Cases involving a party, newest first

```json
{"type": "d", "party_name": "Acme Corporation", "filed_after": "past 2 years",
 "order_by": "dateFiled desc", "num_results": 20}
```

## Recent filings of one kind in one court

```json
{"type": "rd", "court": "nysd", "description": "motion to dismiss",
 "entry_date_filed_after": "30 days ago", "available_only": true,
 "order_by": "entry_date_filed desc", "num_results": 20}
```

## Cases assigned to a judge on a topic

```json
{"type": "r", "court": "txed", "assigned_to": "Smith", "q": "patent infringement",
 "filed_after": "2024-01-01", "num_results": 20}
```

## The latest entries on a docket you already have

Use `call_endpoint`, not `search`:

```json
{"endpoint_id": "docket-entries",
 "query": {"docket": 12345678, "order_by": "-date_filed",
           "fields": ["id", "entry_number", "date_filed", "description", "recap_documents"]},
 "num_results": 20}
```

`order_by` also accepts `date_filed`, `entry_number`, and `-entry_number`. Call
`get_endpoint_schema` for `docket-entries` only if you need other filters.

## Court IDs

Federal district court IDs are short codes such as `cand` (N.D. California),
`nysd` (S.D. New York), `txed` (E.D. Texas), and `dcd` (D.D.C.). Circuit courts
are `ca1` through `ca11`, `cadc`, and `cafc`. For any other court, call
`get_choices` with `field_name: "court"` once and reuse the list.
