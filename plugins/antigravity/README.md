# CourtListener

Legal research from [CourtListener](https://www.courtlistener.com), Free Law Project's free database of U.S. court records, inside Antigravity.

The plugin connects your agent to the hosted CourtListener MCP server. With it you can:

- Search case law, federal dockets and filings from PACER (RECAP), judges and oral arguments
- Read opinions and court filings, and search within them
- Extract and verify legal citations in a document
- Create and manage search and docket alerts

## Skills

The plugin includes four skills that teach the agent how to use the CourtListener tools well. The agent loads them on its own when a request matches.

| Skill | What it covers |
| --- | --- |
| `courtlistener` | The foundation: choosing the right search type, keeping calls few, handling rate limits and sign-in errors, and reporting results with links. |
| `courtlistener-verify-citations` | Checking the citations in a brief, memo or opinion, and reporting which are found, mismatched, ambiguous or missing. |
| `courtlistener-docket-research` | Finding federal dockets and filings in RECAP, reading filings, and following a case. |
| `courtlistener-judge-research` | Researching a judge: positions, opinions, oral arguments and financial disclosures. |

The agent only creates alerts, docket subscriptions or Pray and Pay requests when you ask it to.

## Sign-in

You sign in with your CourtListener account the first time the agent uses a CourtListener tool: Antigravity opens your browser to authorize it. There's no API key to configure. Don't have an account? [Create one for free](https://www.courtlistener.com/register/).

## Learn more

- [CourtListener MCP documentation](https://wiki.free.law/c/courtlistener/help/api/mcp)
- [Free Law Project](https://free.law)
- Questions or problems: [contact us](https://www.courtlistener.com/contact/?issue_type=mcp)
