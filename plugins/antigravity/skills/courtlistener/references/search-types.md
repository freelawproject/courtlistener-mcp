# Search types, filters, and sort orders

Reference for the `search` tool. Every search accepts `type`, `q`, `court`,
`order_by`, `fields`, and `num_results`. The other filters depend on `type`.
Passing a filter that the chosen type doesn't support is an error.

## Filters by type

| `type` | Searches | Filters (besides `q`, `court`, `order_by`) |
| --- | --- | --- |
| `o` | Opinions (case law) | `semantic`, `case_name`, `docket_number`, `judge`, `citation`, `neutral_cite`, `filed_after`, `filed_before`, `cited_gt`, `cited_lt`, `stat_Published`, `stat_Unpublished`, `stat_Errata`, `stat_Separate`, `stat_In-chambers`, `stat_Relating-to`, `stat_Unknown` |
| `r` | Federal dockets, with matching filings nested | `available_only`, `case_name`, `description`, `docket_number`, `nature_of_suit`, `cause`, `filed_after`, `filed_before`, `entry_date_filed_after`, `entry_date_filed_before`, `document_number`, `attachment_number`, `assigned_to`, `referred_to`, `party_name`, `atty_name` |
| `rd` | Individual federal filings | Same as `r` |
| `d` | Federal dockets only | Same as `r` |
| `p` | Judges | `name`, `born_after`, `born_before`, `dob_city`, `dob_state`, `school`, `appointer`, `selection_method`, `political_affiliation` |
| `oa` | Oral arguments | `case_name`, `docket_number`, `judge`, `argued_after`, `argued_before` |

## Notes on specific filters

- **`court`** takes a court ID, a space-separated list of IDs, or an array of
  IDs. The Supreme Court is `scotus`. The federal courts of appeals are `ca1`,
  `ca2`, `ca3`, `ca4`, `ca5`, `ca6`, `ca7`, `ca8`, `ca9`, `ca10`, `ca11`, `cadc`
  (D.C. Circuit), and `cafc` (Federal Circuit). District courts use short codes
  such as `cand`, `nysd`, `txed`, `dcd`. State intermediate appellate courts use
  one statewide ID (`texapp`, `calctapp`); never append a district number. For
  any other court, call `get_choices` with `field_name: "court"` once and reuse
  the answer.
- **`semantic`** works only with `type: "o"`. It matches meaning instead of
  keywords.
- **Dates** (`filed_after`, `argued_before`, and so on) accept an ISO date
  (`2024-01-31`) or a relative expression such as `3 days ago`, `-2m`, or
  `past 1 year`.
- **`cited_gt` / `cited_lt`** filter opinions by how many times they have been
  cited.
- **`stat_*`** flags choose precedential status for opinions, for example
  `stat_Published: true`. Two of the names contain a hyphen; write them exactly
  as shown.
- **`available_only`** limits RECAP results to filings whose text is already on
  CourtListener.
- **`filed_*` versus `entry_date_filed_*`** in RECAP searches: the first is when
  the case was filed, the second is when a docket entry was filed.

## Sort orders (`order_by`)

| `type` | Values |
| --- | --- |
| `o` | `score desc` (relevance), `dateFiled desc`, `dateFiled asc`, `citeCount desc`, `citeCount asc` |
| `r`, `rd`, `d` | `score desc`, `dateFiled desc`, `dateFiled asc`, `entry_date_filed desc`, `entry_date_filed asc` |
| `p` | `score desc`, `name_reverse asc`, and the date-of-birth and date-of-death orders listed in the tool's input schema |
| `oa` | `score desc`, `dateArgued desc`, `dateArgued asc` |

## Field names

Search results have their own field names. Many are camelCase (`caseName`,
`dateFiled`, `citation`); some are not (`absolute_url`, `cluster_id`). Use the
names as they appear in a result in the `fields` argument of `search`. They are
not the names the REST endpoints use; see [api-endpoints.md](api-endpoints.md).

The result fields differ by search type. The most useful ones:

| `type` | Result fields |
| --- | --- |
| `o` | `caseName`, `court`, `court_id`, `dateFiled`, `citation`, `docketNumber`, `status`, `citeCount`, `judge`, `absolute_url`, `cluster_id`, `docket_id`. The tool adds `opinion_id` and `cluster_opinions`. |
| `r`, `d` | `caseName`, `court`, `court_id`, `docketNumber`, `dateFiled`, `dateTerminated`, `assignedTo`, `referredTo`, `suitNature`, `cause`, `party`, `attorney`, `docket_id`, `docket_absolute_url`. With `r`, matching filings are nested in `recap_documents`, each with `id`, `document_number`, `entry_date_filed`, `short_description`, `description`, `is_available`, `page_count`, `absolute_url`. |
| `p` | `name`, `id`, `dob`, `dob_city`, `dob_state`, `gender`, `political_affiliation`, `school`, `aba_rating`, `absolute_url`, and `positions` (each with `court`, `court_exact`, `position_type`, `appointer`, `selection_method`, `date_nominated`, `date_confirmation`, `date_start`, `date_termination`). |
| `oa` | `caseName`, `court`, `court_id`, `dateArgued`, `docketNumber`, `judge`, `duration`, `download_url`, `snippet`, `absolute_url`, `docket_id`, `id`. |

These lists are not complete and can change. If you ask for a name that doesn't
exist, the search still succeeds and returns a `missing_fields` warning that
lists the available names. Use that list to correct `fields` on the next call.
