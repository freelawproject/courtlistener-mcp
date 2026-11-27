"""Settings, read from the environment."""

import base64
import hashlib
import logging
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent

INSECURE_SECRET_KEY = "insecure-do-not-use-in-production"


class Settings(BaseSettings):
    """The settings that come from environment variables."""

    model_config = SettingsConfigDict(
        env_ignore_empty=True, validate_by_name=True
    )

    git_sha: str = "unknown"

    # Redis connection URL. In-memory storage is used when unset.
    redis_url: str | None = Field(None, repr=False)

    # Postgres for the OAuth token store, used when PGHOST is set.
    pghost: str | None = None
    pgport: int = 5432
    pguser: str | None = None
    pgpassword: str | None = Field(None, repr=False)
    pgdatabase: str = "postgres"
    pgpool_max: int = 4

    # Public base URL of this MCP server (the OAuth resource identifier).
    mcp_base_url: str = "https://mcp.courtlistener.com"

    # HMAC key for hashing tokens and user identifiers into storage keys.
    mcp_secret_key: str = Field("", repr=False)

    # Fernet key encrypting the OAuth store's values.
    mcp_storage_encryption_key: bytes = Field(b"", repr=False)

    # Key signing the access tokens this server issues to MCP clients.
    mcp_jwt_signing_key: str | bytes = Field("", repr=False)

    # CourtListener, the identity provider this server brokers logins for.
    oauth_issuer: str = Field(
        "https://www.courtlistener.com",
        validation_alias="COURTLISTENER_OAUTH_ISSUER",
    )
    oauth_introspection_url: str = Field(
        "", validation_alias="COURTLISTENER_OAUTH_INTROSPECTION_URL"
    )

    # This server's own confidential OAuth application at CourtListener.
    oauth_client_id: str | None = Field(
        None, validation_alias="COURTLISTENER_OAUTH_CLIENT_ID"
    )
    oauth_client_secret: str | None = Field(
        None,
        validation_alias="COURTLISTENER_OAUTH_CLIENT_SECRET",
        repr=False,
    )
    oauth_scopes: Annotated[list[str], NoDecode] = Field(
        ["openid", "api", "wiki", "email", "profile"],
        validation_alias="COURTLISTENER_OAUTH_SCOPES",
    )

    # The Free Law Project wiki the wiki tools read.
    wiki_base_url: str = "https://wiki.free.law"

    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.05

    # How long a verified token's info is cached.
    token_cache_ttl_seconds: int = Field(
        600, validation_alias="MCP_TOKEN_CACHE_TTL"
    )

    @field_validator("oauth_issuer", "wiki_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("oauth_scopes", mode="before")
    @classmethod
    def _split_scopes(cls, value: object) -> object:
        return value.split() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _fill_derived_keys(self) -> Self:
        if not self.mcp_secret_key:
            logger.warning(
                "MCP_SECRET_KEY is not set; falling back to an insecure "
                "default. Set a strong random value before going to "
                "production."
            )
            self.mcp_secret_key = INSECURE_SECRET_KEY
        if not self.mcp_storage_encryption_key:
            logger.warning(
                "MCP_STORAGE_ENCRYPTION_KEY is not set; deriving it from "
                "MCP_SECRET_KEY."
            )
            self.mcp_storage_encryption_key = base64.urlsafe_b64encode(
                hashlib.sha256(self.mcp_secret_bytes + b":storage").digest()
            )
        if not self.mcp_jwt_signing_key:
            logger.warning(
                "MCP_JWT_SIGNING_KEY is not set; deriving it from "
                "MCP_SECRET_KEY."
            )
            self.mcp_jwt_signing_key = hashlib.sha256(
                self.mcp_secret_bytes + b":jwt"
            ).digest()
        if not self.oauth_introspection_url:
            self.oauth_introspection_url = f"{self.oauth_issuer}/o/introspect/"
        return self

    @property
    def postgres_configured(self) -> bool:
        return self.pghost is not None

    @property
    def postgres_host(self) -> str:
        return self.pghost or "localhost"

    @property
    def mcp_secret_bytes(self) -> bytes:
        return self.mcp_secret_key.encode("utf-8")

    @property
    def oauth_authorization_url(self) -> str:
        return f"{self.oauth_issuer}/o/authorize/"

    @property
    def oauth_token_url(self) -> str:
        return f"{self.oauth_issuer}/o/token/"

    @property
    def oauth_revocation_url(self) -> str:
        return f"{self.oauth_issuer}/o/revoke_token/"

    @property
    def sentry_release(self) -> str | None:
        """The build's commit, as `/health` reports it; None without one."""
        return self.git_sha if self.git_sha not in ("", "unknown") else None


settings = Settings()

# Per-operation socket timeouts for the Redis session client.
REDIS_SOCKET_TIMEOUT_SECONDS = 5
REDIS_CONNECT_TIMEOUT_SECONDS = 5

# The scopes a sign-in needs before the wiki tools will call the wiki.
WIKI_SCOPES = ("wiki", "profile", "email")

# Legacy MCP clients that are unable to request the needed wiki scopes.
WIKI_TOOLS_EXCLUDED_CLIENTS: frozenset[str] = frozenset(
    {
        "hYpWm7HA64HnqF3LimQSw22VwT7ZgnbIepfjInbe",  # Legacy ChatGPT
        "rmfqZfHRXRKia9dA4JDXKjkCXLviRpmtNPWUNifz",  # Legacy Gemini Enterprise
    }
)

# Session-scoped state (query pagination, citation jobs) lives this long.
SESSION_TTL_SECONDS = 3600  # 1 hour

# How long a cached document lives in the session store (shared across users).
DOCUMENT_TTL_SECONDS = 86400  # 24 hours

# How long each day's active-user set is kept.
ACTIVE_USERS_TTL_SECONDS = 60 * 86400  # 60 days

# Timeout for the upstream calls made during token verification.
VERIFICATION_TIMEOUT_SECONDS = 20

# Result-count bounds for search/list tools.
DEFAULT_NUM_RESULTS = 20
MAX_NUM_RESULTS = 100

# Domain-verification token for the OpenAI Apps directory listing.
OPENAI_APPS_CHALLENGE_TOKEN = "oR-QatCh96AHxvH1yYTS7_oP4ByrYVSuoCmAifKJyVg"
