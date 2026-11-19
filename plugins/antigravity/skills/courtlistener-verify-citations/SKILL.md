---
name: courtlistener-verify-citations
description: >-
  Checks whether the legal citations in a brief, memo, opinion, or other text
  are real and point to the cases they claim to. Load this skill before calling
  `analyze_citations`, `extract_citations`, or `resume_citation_analysis`. Use
  when the user asks to verify, check, validate, or audit citations, asks
  whether a citation or case is real, or wants a cite-check or a table of
  authorities reviewed. Load the `courtlistener` skill first.
---

# Verify citations with CourtListener

The goal is a report that tells the user, for every case citation, whether
CourtListener found it and whether the case name matches. Follow the steps in
order.

## Step 1: Decide what text is being checked

- **A case already on CourtListener, and you have its ID.** Pass `opinion_id`
  or `cluster_id` to `analyze_citations`. No text needs to be sent. Don't search
  for the case just to get an ID when the user has already pasted the text.
- **Public text the user supplied** (a filed brief, a published opinion, an
  article). Send it as `text`, prose included.
- **Private text the user supplied** (an unfiled draft, a client memo). The
  whole `text` would be sent to CourtListener's server. Don't send anything
  yet. Offer to send only the citations, each with its case name and no
  surrounding sentences, for example `Smith v. Jones, 123 F.3d 456 (9th Cir.
  1997)`, one per line, and wait for the user to agree. Send the full text only
  if the user confirms it may be shared.
- **A few citations the user typed.** Send them as `text`.

Keep each case name next to its citation in whatever you send. The check that
catches a real citation attached to the wrong case compares the two, and it
cannot run on a bare `123 F.3d 456`.

`analyze_citations` takes exactly one of `text`, `opinion_id`, or `cluster_id`.

## Step 2: Choose the tool

| Situation | Tool |
| --- | --- |
| Verify the citations | `analyze_citations` |
| Only list or count citations, or see how short cites, *id.*, and *supra* resolve | `extract_citations` (no CourtListener API quota used) |
| A previous analysis returned a `job_id` with pending citations | `resume_citation_analysis` |

Don't run `extract_citations` and then `analyze_citations` on the same text as
a matter of routine: `analyze_citations` already extracts. Use
`extract_citations` first only for a very long document, so you can tell the
user how many citations there are before spending quota.

`analyze_citations` spends one request of the main quota per call, plus a
separate per-citation allowance.

## Step 3: Finish large jobs

`analyze_citations` verifies about 250 unique case citations per call. For more,
it returns a `job_id` and marks the rest `PENDING`.

1. Tell the user how many are verified and how many are pending.
2. Call `resume_citation_analysis` with the `job_id`.
3. If it reports a short wait (`wait_until`), call it again with `wait: true`.
   The server then waits out the limit, up to about 90 seconds, and retries.
4. Repeat until nothing is pending. Jobs expire after about an hour of
   inactivity, so finish in the same session.

## Step 4: Read every status

Never summarize a result as "all good" without reading each status. See
[citation-statuses.md](references/citation-statuses.md) for what each one means
and what to do next. The short version:

- `FOUND` with no warning: the citation resolves to a real case.
- `FOUND` with a `WARNING` about the case name: the reporter citation is real
  but the name in the text is different. This is the classic sign of a
  fabricated or mixed-up citation. Always flag it.
- `NOT FOUND`: CourtListener has no case at that citation. It may be wrong, or
  it may be a source CourtListener doesn't hold. Follow up before calling it
  fake.
- `AMBIGUOUS`: the citation matches more than one case. Resolve it.
- `INVALID` or `UNRESOLVABLE`: the citation could not be parsed or resolved.

## Step 5: Follow up, within reason

Follow up only on citations that are not a clean `FOUND`, and keep it to one
extra search per citation:

- For `NOT FOUND`, search opinions for the case (`type: "o"`). Put two or three
  distinctive words from the name in `q`, and add `court` and a date range from
  the citation's year. Don't rely on the full name in `case_name`: CourtListener
  often stores names in abbreviated form (`Int'l` for International), so an
  exact name can miss. A well-known case can be `NOT FOUND` simply because
  CourtListener doesn't list that reporter citation for it. If the case exists
  under other citations, say so and give them.
- For a name mismatch, report both the name in the text and the name
  CourtListener has for that citation.
- If there are more than about ten problem citations, report the first batch
  and ask the user whether to continue.

## Step 6: Report

Use the table format in [citation-statuses.md](references/citation-statuses.md).
Lead with the count of problems, list problem citations first, and link every
found case. State plainly that a `FOUND` result confirms the case exists at that
citation. It does not confirm that the case says what the text claims; offer to
check a specific quotation or proposition with `search_document` if the user
wants that.
