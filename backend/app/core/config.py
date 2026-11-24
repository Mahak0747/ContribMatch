"""Application configuration loaded from environment variables / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # A validation error must never echo a setting's value: DATABASE_URL and GITHUB_TOKEN are secrets.
        hide_input_in_errors=True,
    )

    app_name: str = "ContribMatch API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Comma-separated exact origins (scheme + host, no path, no trailing slash needed).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional regex for origins that cannot be listed (e.g. Vercel preview URLs). Empty = disabled.
    cors_origin_regex: str = ""

    # SQLite for local development, PostgreSQL (Neon) in the cloud. Secret: never log or commit it.
    database_url: str = "sqlite:///./data/contribmatch.db"
    db_pool_size: int = 5                  # PostgreSQL only
    db_max_overflow: int = 5               # PostgreSQL only
    db_pool_recycle_seconds: int = 300     # drop idle connections before Neon suspends/closes them
    db_pool_timeout_seconds: int = 30      # wait for a free pooled connection
    db_connect_timeout_seconds: int = 10   # fail fast when the database is unreachable

    # ML (pretrained model runs locally; downloaded from Hugging Face on first use)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32
    embedding_cache_max_items: int = 5000
    # Where model files are cached. Empty = Hugging Face default (~/.cache/huggingface).
    # Relative paths are resolved against backend/ (so a build step and the running app agree).
    model_cache_dir: str = ""

    preload_model: bool = False            # load the embedding model at startup (else on first request)
    max_search_queries: int = 3            # GitHub searches per recommendation request
    candidates_per_query: int = 30         # issues fetched per search

    # GitHub. The token is backend-only and is never returned by any endpoint.
    github_token: str = ""
    github_api_url: str = "https://api.github.com"
    github_timeout_seconds: float = 10.0
    github_max_retries: int = 2
    github_retry_backoff_seconds: float = 0.5
    github_search_cache_ttl_seconds: int = 600      # 10 min
    github_repo_cache_ttl_seconds: int = 86400      # 24 h
    github_repo_concurrency: int = 5

    @field_validator("github_token")
    @classmethod
    def _strip_token(cls, v: str) -> str:
        return v.strip()

    @field_validator("database_url")
    @classmethod
    def _valid_database_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("sqlite:", "postgres://", "postgresql://", "postgresql+")):
            # deliberately does not include the value (it may contain a password)
            raise ValueError("DATABASE_URL must start with sqlite:///, postgresql:// or postgres://")
        return v

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid LOG_LEVEL: {v}")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        """Origins never end with '/', but copy-pasted URLs often do, which would silently never match."""
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip().rstrip("/")]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite:")

    @property
    def sqlalchemy_url(self) -> str:
        """URL handed to SQLAlchemy.

        * SQLite: relative paths are resolved against backend/ so the working directory does not matter.
        * PostgreSQL: Neon (and most hosts) give `postgresql://` or `postgres://` URLs. SQLAlchemy would
          pick the psycopg2 driver for those, but this project ships psycopg 3, so the scheme is rewritten
          to `postgresql+psycopg://`. An explicit driver (`postgresql+...`) is left alone.
        """
        url = self.database_url
        for plain in ("postgres://", "postgresql://"):
            if url.startswith(plain):
                return "postgresql+psycopg://" + url[len(plain):]
        prefix = "sqlite:///"
        if url.startswith(prefix):
            path = url[len(prefix):]
            if path and path != ":memory:" and not Path(path).is_absolute():
                return f"{prefix}{(BACKEND_DIR / path).resolve()}"
        return url

    @property
    def model_cache_path(self) -> Path | None:
        if not self.model_cache_dir.strip():
            return None
        p = Path(self.model_cache_dir.strip())
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
