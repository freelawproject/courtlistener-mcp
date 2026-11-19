# Beyond search: the REST endpoints

`search` and the document tools cover most questions. For richer detail, three
tools expose the CourtListener REST API.

| Tool | Use it when |
| --- | --- |
| `get_endpoint_item` | You have an ID and want one record. Takes `endpoint_id`, `item_id`, and `fields`. No schema lookup needed. |
| `call_endpoint` | You need to list or filter records. Takes `endpoint_id`, `query`, and `num_results`. |
| `get_endpoint_schema` | You need the filter and field names for an endpoint before calling `call_endpoint`. It doesn't spend API quota. Call it once per endpoint and reuse the answer. |

## Rules that prevent wasted calls

- In `call_endpoint`, `fields` goes inside `query` with the other parameters:
  `{"endpoint_id": "dockets", "query": {"court": "scotus", "fields": ["id", "docket_number"]}}`.
  In `get_endpoint_item` and `search`, `fields` is a top-level argument.
- Endpoint field names are snake_case (`case_name`, `date_filed`, `citations`).
  Don't copy camelCase names from search results.
- Leave large text fields (`plain_text`, `html_with_citations`, `html`) out of
  `fields`. Read text with `read_document` instead.
- Page with `get_more_results` and the returned `query_id`. If a count is
  missing, `get_counts` with the same `query_id` returns it.
- A few choice lists are too long for the schemas. `get_choices` returns them
  for `court`, `dob_state`, `dod_state`, `location_state`, `position_type`, and
  `source`. Every other choice field lists its values in the schema.

## Endpoint IDs by topic

| Topic | `endpoint_id` values |
| --- | --- |
| Case law | `clusters` (case-level metadata: name, date, citations, judges), `opinions` (one opinion's text and author), `opinions-cited` (which opinion cites which), `courts` |
| Federal dockets | `dockets`, `docket-entries`, `recap-documents`, `parties`, `attorneys`, `originating-court-information`, `bankruptcy-information`, `fjc-integrated-database` |
| Oral arguments | `audio` |
| Judges | `people`, `positions`, `educations`, `political-affiliations`, `aba-ratings`, `schools`, `sources`, `retention-events` |
| Judicial financial disclosures | `financial-disclosures`, `investments`, `gifts`, `debts`, `agreements`, `reimbursements`, `non-investment-incomes`, `spouse-incomes`, `disclosure-positions` |
| The user's own account | `alerts`, `docket-alerts`, `prayers`, `tags`, `docket-tags` |

## Common joins

- **Case metadata versus opinion text.** `case_name`, `date_filed`, `citations`,
  and `judges` live on `clusters`. An opinion links to its cluster by
  `cluster_id`. Opinion IDs and cluster IDs are different numbers.
- **Docket to its entries.** `call_endpoint` on `docket-entries` with the docket
  ID in the `docket` filter.
- **Who cites a case.** `call_endpoint` on `opinions-cited` with the opinion ID
  in the `cited_opinion` filter returns the citing opinions; `citing_opinion`
  goes the other way. CourtListener's search help also documents a
  `cites:(<cluster_id>)` operator for `q` in opinion searches, which lets you
  sort the citing cases by date or citation count.
