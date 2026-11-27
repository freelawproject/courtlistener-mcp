"""Settings read from the environment: names, defaults and derived values."""

import base64
import hashlib

import pytest

from courtlistener_mcp.settings import INSECURE_SECRET_KEY, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Unset every variable Settings reads, so the real environment can't leak in."""
    for name, field in Settings.model_fields.items():
        alias = field.validation_alias
        monkeypatch.delenv(str(alias or name).upper(), raising=False)


def test_defaults():
    s = Settings()
    assert s.git_sha == "unknown"
    assert s.redis_url is None
    assert s.postgres_configured is False
    assert s.postgres_host == "localhost"
    assert (s.pgport, s.pguser, s.pgpassword) == (5432, None, None)
    assert (s.pgdatabase, s.pgpool_max) == ("postgres", 4)
    assert s.mcp_base_url == "https://mcp.courtlistener.com"
    assert s.mcp_secret_key == INSECURE_SECRET_KEY
    assert s.oauth_issuer == "https://www.courtlistener.com"
    assert s.oauth_authorization_url == (
        "https://www.courtlistener.com/o/authorize/"
    )
    assert s.oauth_token_url == "https://www.courtlistener.com/o/token/"
    assert s.oauth_revocation_url == (
        "https://www.courtlistener.com/o/revoke_token/"
    )
    assert s.oauth_introspection_url == (
        "https://www.courtlistener.com/o/introspect/"
    )
    assert (s.oauth_client_id, s.oauth_client_secret) == (None, None)
    assert s.oauth_scopes == ["openid", "api", "wiki", "email", "profile"]
    assert s.wiki_base_url == "https://wiki.free.law"
    assert s.sentry_dsn is None
    assert s.sentry_traces_sample_rate == 0.05
    assert s.token_cache_ttl_seconds == 600


@pytest.mark.parametrize(
    ("env", "value", "attr", "expected"),
    [
        ("GIT_SHA", "15e16b0", "git_sha", "15e16b0"),
        ("REDIS_URL", "redis://r:6379", "redis_url", "redis://r:6379"),
        ("PGHOST", "db", "pghost", "db"),
        ("PGPORT", "5433", "pgport", 5433),
        ("PGUSER", "mcp", "pguser", "mcp"),
        ("PGPASSWORD", "pw", "pgpassword", "pw"),
        ("PGDATABASE", "mcpdb", "pgdatabase", "mcpdb"),
        ("PGPOOL_MAX", "2", "pgpool_max", 2),
        ("MCP_BASE_URL", "http://m.test", "mcp_base_url", "http://m.test"),
        ("MCP_SECRET_KEY", "s3cret", "mcp_secret_key", "s3cret"),
        (
            "MCP_STORAGE_ENCRYPTION_KEY",
            "fernet-key",
            "mcp_storage_encryption_key",
            b"fernet-key",
        ),
        ("MCP_JWT_SIGNING_KEY", "jwt-key", "mcp_jwt_signing_key", "jwt-key"),
        (
            "COURTLISTENER_OAUTH_ISSUER",
            "https://cl.test/",
            "oauth_issuer",
            "https://cl.test",
        ),
        (
            "COURTLISTENER_OAUTH_INTROSPECTION_URL",
            "https://i.test/",
            "oauth_introspection_url",
            "https://i.test/",
        ),
        ("COURTLISTENER_OAUTH_CLIENT_ID", "id", "oauth_client_id", "id"),
        (
            "COURTLISTENER_OAUTH_CLIENT_SECRET",
            "sec",
            "oauth_client_secret",
            "sec",
        ),
        (
            "COURTLISTENER_OAUTH_SCOPES",
            "openid  api",
            "oauth_scopes",
            ["openid", "api"],
        ),
        (
            "WIKI_BASE_URL",
            "https://w.test/",
            "wiki_base_url",
            "https://w.test",
        ),
        (
            "SENTRY_DSN",
            "https://k@s.test/1",
            "sentry_dsn",
            "https://k@s.test/1",
        ),
        (
            "SENTRY_TRACES_SAMPLE_RATE",
            "0.5",
            "sentry_traces_sample_rate",
            0.5,
        ),
        ("MCP_TOKEN_CACHE_TTL", "30", "token_cache_ttl_seconds", 30),
    ],
)
def test_each_setting_reads_its_variable(
    monkeypatch, env, value, attr, expected
):
    monkeypatch.setenv(env, value)
    assert getattr(Settings(), attr) == expected


def test_empty_variables_fall_back_to_the_defaults(monkeypatch):
    for env in ("PGHOST", "PGPORT", "SENTRY_DSN", "SENTRY_TRACES_SAMPLE_RATE"):
        monkeypatch.setenv(env, "")
    s = Settings()
    assert s.postgres_configured is False
    assert s.pgport == 5432
    assert s.sentry_dsn is None
    assert s.sentry_traces_sample_rate == 0.05


def test_postgres_is_configured_by_pghost(monkeypatch):
    monkeypatch.setenv("PGHOST", "db.example.test")
    s = Settings()
    assert s.postgres_configured is True
    assert s.postgres_host == "db.example.test"


def test_oauth_urls_follow_the_issuer(monkeypatch):
    monkeypatch.setenv("COURTLISTENER_OAUTH_ISSUER", "https://cl.test/")
    s = Settings()
    assert s.oauth_authorization_url == "https://cl.test/o/authorize/"
    assert s.oauth_token_url == "https://cl.test/o/token/"
    assert s.oauth_revocation_url == "https://cl.test/o/revoke_token/"
    assert s.oauth_introspection_url == "https://cl.test/o/introspect/"


def test_unset_keys_derive_from_the_secret_key(monkeypatch):
    monkeypatch.setenv("MCP_SECRET_KEY", "s3cret")
    s = Settings()
    assert s.mcp_secret_bytes == b"s3cret"
    assert s.mcp_storage_encryption_key == base64.urlsafe_b64encode(
        hashlib.sha256(b"s3cret:storage").digest()
    )
    assert s.mcp_jwt_signing_key == hashlib.sha256(b"s3cret:jwt").digest()


def test_sentry_release_is_the_commit_sha(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "15e16b0")
    assert Settings().sentry_release == "15e16b0"


@pytest.mark.parametrize("git_sha", ["unknown", ""])
def test_no_sentry_release_without_a_build_sha(monkeypatch, git_sha):
    monkeypatch.setenv("GIT_SHA", git_sha)
    assert Settings().sentry_release is None


def test_repr_hides_the_secrets(monkeypatch):
    secrets = {
        "REDIS_URL": "redis://:redis-pw@redis.test:6379/0",
        "PGPASSWORD": "pg-pw",
        "MCP_SECRET_KEY": "secret-key",
        "MCP_STORAGE_ENCRYPTION_KEY": "storage-key",
        "MCP_JWT_SIGNING_KEY": "jwt-key",
        "COURTLISTENER_OAUTH_CLIENT_SECRET": "client-secret",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    shown = repr(Settings())
    for value in secrets.values():
        assert value not in shown
