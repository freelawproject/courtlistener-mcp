# Disabled workflows

Workflows inherited from `courtlistener-api-client` that must not run here
yet. GitHub only runs files in `.github/workflows/`, so these are inert.

- `deploy.yml` deploys the MCP on every push to `main`.
- `pypi.yml` publishes to PyPI on `v*` tags.

Production still deploys from `courtlistener-api-client`. #2 brings back the
ones this repo needs once the refactor is complete, and deletes the rest.
