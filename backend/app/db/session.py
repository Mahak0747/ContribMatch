"""SQLAlchemy engine/session management for SQLite (local) and PostgreSQL (Neon, cloud)."""
import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceUnavailableError
from app.db.base import Base

logger = logging.getLogger(__name__)


def engine_options(url: str, settings: Settings) -> dict[str, Any]:
    """Keyword arguments for `create_engine`, chosen by database type. Pure function (no I/O)."""
    if url.startswith("sqlite"):
        opts: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool
            opts["poolclass"] = StaticPool
        return opts

    connect_args: dict[str, Any] = {"connect_timeout": settings.db_connect_timeout_seconds}
    if "+psycopg2" not in url:
        # psycopg 3 creates server-side prepared statements after a few repeats. Those do not survive a
        # transaction-mode connection pooler (Neon's "-pooler" endpoint uses PgBouncer), so disable them.
        connect_args["prepare_threshold"] = None
    return {
        "pool_pre_ping": True,                              # test a pooled connection before using it
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_recycle": settings.db_pool_recycle_seconds,   # Neon closes idle connections / suspends compute
        "pool_timeout": settings.db_pool_timeout_seconds,
        "connect_args": connect_args,
    }


def make_engine(url: str, settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, **engine_options(url, settings))


engine: Engine = make_engine(get_settings().sqlalchemy_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_init_lock = threading.Lock()
_initialised = False


def init_db(bind: Engine | None = None) -> None:
    """Create all tables for imported models. Safe to call repeatedly (existing tables are left alone)."""
    import app.models  # noqa: F401  (registers models on Base.metadata)
    Base.metadata.create_all(bind=bind or engine)


def ensure_initialized() -> None:
    """Create the tables once per process, and retry on later calls if it failed.

    The cloud database can be asleep or briefly unreachable when the app boots, so a failure here must not
    crash the server: the next request that needs the database simply tries again.
    """
    global _initialised
    if _initialised:
        return
    with _init_lock:
        if not _initialised:
            init_db()
            _initialised = True
            logger.info("Database tables are ready (%s)", engine.dialect.name)


def check_db(bind: Engine | None = None) -> bool:
    try:
        with (bind or engine).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_db() -> Iterator[Session]:
    try:
        ensure_initialized()
    except SQLAlchemyError as exc:
        # type name only: the exception text can contain connection details
        logger.error("Database unavailable: %s", type(exc).__name__)
        raise ServiceUnavailableError("The database is temporarily unavailable. Please try again shortly.") from exc
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
