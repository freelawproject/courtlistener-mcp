# Citation statuses and report format

## What each status means

| Status in the tool output | Meaning | What to do |
| --- | --- | --- |
| `FOUND` | The citation resolves to a case on CourtListener. | Report as verified, with the case name, court, date, and link. |
| `FOUND` plus `WARNING: Input case name ...` | The reporter citation is real, but the case name in the text differs significantly from the case at that citation. | Flag as a likely wrong or fabricated citation. Show both names. |
| `NOT FOUND` | No case at that citation on CourtListener. This also happens to real cases whose citation CourtListener doesn't list. | Search for the case once by distinctive words from its name. Report as "not found on CourtListener", not as "fake", unless the follow-up also finds nothing and the user understands the limit. |
| `AMBIGUOUS` | The citation matches more than one case. | Use the case name or year in the text to pick the right one. If you can't, list the candidates. |
| `INVALID` | The citation could not be parsed. | Show the text as written and ask the user to check the format. |
| `UNRESOLVABLE` | The citation could not be tied to a case, for example a short cite with no earlier full cite. | Report it and give the reason shown. |
| `PENDING` | Not yet verified; the job hit its batch limit. | Continue with `resume_citation_analysis`. |

## Terms in the output

- **Citation occurrence**: each time a citation appears in the text.
- **Unique citation string**: a distinct volume, reporter, and page. One case
  cited three times is one string.
- **Unique case cluster**: a distinct case after parallel citations are merged.
  Several strings can point to the same case.

Use these terms when you give counts, so the numbers match the tool output.

## Only case citations are verified

`analyze_citations` verifies case citations against CourtListener's case law.
Statutes, regulations, and secondary sources are extracted but not verified.
Say so in the report if the text contains them.

## Report template

Start with one sentence: how many unique case citations were checked and how
many need attention. Then the table, problems first.

| # | Citation as written | Result | Case on CourtListener | Note |
| --- | --- | --- | --- | --- |
| 1 | *Smith v. Jones*, 123 F.3d 456 | Name mismatch | [*Doe v. Roe*](https://www.courtlistener.com/...) (9th Cir. 1997) | The citation exists but belongs to a different case. |
| 2 | 999 U.S. 999 | Not found | None | No case at this citation; name search also found nothing. |
| 3 | 573 U.S. 208 | Found | [*Alice Corp. v. CLS Bank*](https://www.courtlistener.com/...) (U.S. 2014) | |

The rows above show the format only. Fill the table from the tool output, never
from memory.

End with what the check does not cover: it confirms each case exists at its
citation, not that the case supports the proposition it is cited for.
