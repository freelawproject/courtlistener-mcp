# Developer Documentation

## Getting Started

```sh
uv sync --extra dev                                # install
uv run pytest                                      # tests (uv run tox for the full run)
uv run tox -- --run-integration                    # with integration tests (needs COURTLISTENER_API_TOKEN)
uv run mypy                                        # type check
uv run pre-commit run --all-files                  # lint and format (ruff)
uv run python scripts/generate_mcp_tool_docs.py    # regenerate the docs
```

To run the server locally, see [Self-hosting / local development](../MCP_README.md#self-hosting--local-development).

## Code Layout

Tools are thin, like Django views, and the logic behind them lives in `lib/`, like CourtListener's `cl/lib/`.

```
courtlistener_mcp/
  settings.py        settings, read from the environment
  exceptions.py      the errors tools raise, and the Sentry filter
  tokens.py          credential kinds and verified-token info
  session.py         per-user state: stored queries, citation jobs, caches
  metrics.py         Prometheus metrics
  lib/               the logic, one module per concept
    schema.py        endpoint ids, choice lists, shared schema properties
    results.py       paging, query ids, field filtering
    opinions.py      opinion ordering and summaries
    documents.py     document text: fetching, chunking, snippet search
    citation_*.py    citation analysis, jobs, matching and rendering
    tags.py          tag schemas and error messages
    web.py           the web files under assets/, rendered for pages and app views
    wiki.py          the wiki API client, and the wiki tools' shared pieces
  tools/             the MCP tools, one module per tool
    __init__.py      the registry (MCP_TOOLS)
    base.py          MCPTool and WikiTool
    <tool_name>.py   e.g. search_document.py
  auth/              proxy.py (OAuth proxy, auth gate), verifiers.py, store.py
  server/            main.py, app.py (ASGI), middleware.py, prompts.py
```

### Where code goes

1. **One tool per module in `tools/`, named after the tool.** The `search_document` tool is `tools/search_document.py`. `tools/` holds nothing else except the registry and `base.py`.
2. **Tools stay thin.** A tool declares its schema and annotations, checks its arguments, and calls into `lib/`. When a tool grows logic that isn't about MCP (fetching, matching, formatting, state), the logic moves to `lib/`. This holds even if only one tool uses it.
3. **Every `lib/` module is named after a concept** (`opinions`, `citation_matching`, `wiki`), never `utils`, `helpers` or `misc`.
   - New code joins the module for its concept, or starts a new one.
   - Related modules share a prefix (`citation_jobs`, `citation_matching`, `citation_rendering`).
   - When a concept outgrows one module, it becomes a subpackage (`lib/citations/`).
4. **Imports flow one way:**
   - `settings`, `exceptions` and `tokens` import nothing else from the package.
   - `session` and `metrics` import only those (and `metrics` reads `session`).
   - `lib/` imports those, never `tools/`, `auth/` or `server/`.
   - `tools/` and `auth/` import `lib/` and below, never each other.
   - `server/` wires everything together, and nothing imports from it.

   `tests/test_import_layers.py` enforces this. A new top-level module has to be added to a layer there.
5. **Every module starts with a docstring** saying what it holds. If you can't say it in a line or two, the module is doing too much. Tool modules are the exception: a tool module is one class, and that class's docstring is the tool's description. `tests/test_module_docstrings.py` checks this.

## Adding a Tool

1. Write `tools/<tool_name>.py` with a class that extends `MCPTool` (or `WikiTool` for a wiki tool). Put any logic it needs in `lib/`.
2. Register it in `tools/__init__.py`.
3. Add tests under `tests/`.
4. Regenerate the docs (see [Generating Documentation](#generating-documentation)).
5. Add a `CHANGES.md` bullet.

## Generating Documentation

`scripts/generate_mcp_tool_docs.py` writes the tool docs from the tool registry:

- **`docs/mcp_tools/<tool>.md`:** one page per tool, with its source module, estimated definition size, description, annotations and parameters.
- **`docs/mcp_tools/<tool>.inputs.json`:** the tool's raw input schema.
- **`docs/README.md`:** the handwritten intro from `docs/.src/README.md`, followed by a table of every tool with its title and source module.

Rerun it after adding, removing, renaming or moving a tool, or changing its description or schema:

```sh
uv run python scripts/generate_mcp_tool_docs.py
```

The generator stops with an error if `docs/mcp_tools/` has a page for a tool that's no longer registered. CI also regenerates the docs and fails if they differ from what's committed, so commit the regenerated files along with your change.

## Changes and Releases

- **Changelog:** every PR adds a bullet to the Upcoming section of `CHANGES.md`, unless it's labeled `no changelog`. CI checks this.
- **Commits and PR titles** use Conventional Commits.
- **Releases:** the Release PR workflow opens a release PR every Monday when `main` has unreleased commits. Merging it tags the release and publishes it to PyPI. To release by hand, use the `release` skill (`.claude/skills/release/`).
