# Judge endpoints and example calls

All of these use `call_endpoint` (to list) or `get_endpoint_item` (one record by
ID). In `call_endpoint`, filters and `fields` go inside `query`. Field names are
snake_case. The first time you use an endpoint, call `get_endpoint_schema` for
it and reuse the answer for the rest of the conversation.

## Biography

| `endpoint_id` | Holds | Key filters |
| --- | --- | --- |
| `people` | One record per judge: names, dates and places of birth and death, gender | `name_last`, `name_first`, `dob_state` |
| `positions` | Each court position or other job: court, dates, who appointed, how selected, confirmation votes | `person`, `court`, `position_type`, `appointer` |
| `educations` | Schools and degrees | `person` |
| `political-affiliations` | Party affiliations over time | `person` |
| `aba-ratings` | American Bar Association ratings | `person` |

```json
{"endpoint_id": "positions",
 "query": {"person": 1234,
           "fields": ["court", "position_type", "date_start", "date_termination", "appointer", "how_selected"]}}
```

## Financial disclosures

| `endpoint_id` | Holds | Key filter |
| --- | --- | --- |
| `financial-disclosures` | One record per annual filing | `person` |
| `investments` | Holdings, income, and transactions, as value-range codes | `financial_disclosure` |
| `gifts` | Gifts received | `financial_disclosure` |
| `debts` | Liabilities | `financial_disclosure` |
| `agreements` | Agreements, such as with a former employer | `financial_disclosure` |
| `reimbursements` | Travel and other reimbursements | `financial_disclosure` |
| `non-investment-incomes` | Income other than from investments | `financial_disclosure` |
| `spouse-incomes` | Spouse's income sources | `financial_disclosure` |
| `disclosure-positions` | Outside positions held | `financial_disclosure` |

Step 1, list a judge's filings:

```json
{"endpoint_id": "financial-disclosures",
 "query": {"person": 1234, "order_by": "-id",
           "fields": ["id", "year", "report_type", "is_amended"]},
 "num_results": 20}
```

`year` is the filing year. A judge can have more than one record for the same
year. `order_by` accepts `id`, `date_created`, and
`date_modified` (prefix `-` for descending); there is no sort by `year`, so
read the years from the results.

Step 2, one category of one filing:

```json
{"endpoint_id": "investments",
 "query": {"financial_disclosure": 5678,
           "fields": ["description", "gross_value_code", "income_during_reporting_period_code",
                      "transaction_during_reporting_period", "transaction_value_code", "redacted"]},
 "num_results": 50}
```

## Long choice lists

Of the six fields `get_choices` covers, four matter for judges:
`position_type`, `location_state`, `dob_state`, and `dod_state` (the other two
are `court` and `source`). Every other choice field, such as
`political_affiliation` or `how_selected`, lists its values in the schema. The
value-range codes on `investments` are listed in that endpoint's schema.
