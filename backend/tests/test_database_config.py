"""PostgreSQL / Neon readiness and database-failure handling.

No PostgreSQL server is needed: the PostgreSQL parts are checked by compiling SQL for the PostgreSQL dialect
and by testing the configuration logic. They do NOT prove behaviour against a live Neon database."""
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401  (registers tables)
from app.core.config import BACKEND_DIR, Settings
from app.core.exceptions import register_exception_handlers
from app.db import session as S
from app.db.base import Base
from app.db.session import SessionLocal
from app.main import app as fastapi_app
from app.ml.profile import DeveloperProfile
from app.schemas.issues import Issue
from app.services.profile_service import create_or_get_profile
from app.services.recommendation_service import history_statement
from tests.github_mock import make_item

NEON = "postgresql://neon_user:s3cr3t-pw@ep-cool-123-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


def cfg(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


# --------------------------------------------------------------------------- URL handling
@pytest.mark.parametrize("given,expected_prefix", [
    (NEON, "postgresql+psycopg://neon_user:s3cr3t-pw@ep-cool-123-pooler"),
    (NEON.replace("postgresql://", "postgres://"), "postgresql+psycopg://neon_user"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),          # explicit driver untouched
    ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
])
def test_postgres_urls_use_the_psycopg_driver(given, expected_prefix):
    assert cfg(database_url=given).sqlalchemy_url.startswith(expected_prefix)


def test_query_parameters_are_preserved():
    url = cfg(database_url=NEON).sqlalchemy_url
    assert url.endswith("?sslmode=require&channel_binding=require")


def test_sqlite_behaviour_is_unchanged():
    rel = cfg(database_url="sqlite:///./data/contribmatch.db")
    assert rel.sqlalchemy_url == f"sqlite:///{(BACKEND_DIR / 'data/contribmatch.db').resolve()}"
    assert cfg(database_url="sqlite:///:memory:").sqlalchemy_url == "sqlite:///:memory:"
    assert cfg(database_url="sqlite:////abs/x.db").sqlalchemy_url == "sqlite:////abs/x.db"
    assert rel.is_sqlite and not cfg(database_url=NEON).is_sqlite


@pytest.mark.parametrize("bad", ["mysql://u:hunter2@h/db", "", "not a url hunter2"])
def test_invalid_database_url_is_rejected_without_leaking_it(bad):
    with pytest.raises(ValidationError) as exc:
        cfg(database_url=bad)
    assert "hunter2" not in str(exc.value)


def test_database_url_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", NEON)
    assert Settings(_env_file=None).sqlalchemy_url.startswith("postgresql+psycopg://")


# --------------------------------------------------------------------------- engine options
def test_postgres_engine_options_for_neon():
    s = cfg(database_url=NEON)
    o = S.engine_options(s.sqlalchemy_url, s)
    assert o["pool_pre_ping"] is True and o["pool_recycle"] == 300 and o["pool_size"] == 5 and o["max_overflow"] == 5
    assert o["connect_args"]["connect_timeout"] == 10
    assert o["connect_args"]["prepare_threshold"] is None       # safe behind Neon's PgBouncer pooler
    assert "poolclass" not in o


def test_psycopg2_url_does_not_get_a_psycopg3_only_option():
    s = cfg()
    assert "prepare_threshold" not in S.engine_options("postgresql+psycopg2://u:p@h/db", s)["connect_args"]


def test_sqlite_engine_options_unchanged():
    s = cfg()
    assert S.engine_options("sqlite:////tmp/x.db", s) == {"connect_args": {"check_same_thread": False}}
    mem = S.engine_options("sqlite:///:memory:", s)
    assert mem["connect_args"] == {"check_same_thread": False} and mem["poolclass"].__name__ == "StaticPool"


# --------------------------------------------------------------------------- CORS
def test_cors_origins_tolerate_trailing_slashes():
    s = cfg(cors_origins="https://app.vercel.app/, http://localhost:5173 ,, ")
    assert s.cors_origin_list == ["https://app.vercel.app", "http://localhost:5173"]


def test_cors_regex_and_exact_origins(monkeypatch):
    import app.main as m
    monkeypatch.setattr(m, "get_settings", lambda: cfg(cors_origins="https://prod.example/", cors_origin_regex=r"https://[a-z0-9-]+\.preview\.example"))
    c = TestClient(m.create_app())                                    # no lifespan needed for /health/live
    def origin(o):
        return c.get("/api/health/live", headers={"Origin": o}).headers.get("access-control-allow-origin")
    assert origin("https://prod.example") == "https://prod.example"           # slash in config tolerated
    assert origin("https://pr-12.preview.example") == "https://pr-12.preview.example"
    assert origin("https://evil.example") is None


# --------------------------------------------------------------------------- PostgreSQL schema
def test_schema_compiles_for_postgresql():
    pg = postgresql.dialect()
    ddl = {t.name: re.sub(r"\s+", " ", str(CreateTable(t).compile(dialect=pg))) for t in Base.metadata.sorted_tables}
    assert set(ddl) == {"profiles", "cached_issues", "recommendation_runs", "recommendation_items"}
    # GitHub issue ids exceed 32 bits, so they must be BIGINT (not SERIAL) columns
    assert "id BIGINT NOT NULL" in ddl["cached_issues"] and "SERIAL" not in ddl["cached_issues"]
    assert "issue_id BIGINT NOT NULL" in ddl["recommendation_items"]
    assert "id SERIAL NOT NULL" in ddl["profiles"] and "id SERIAL NOT NULL" in ddl["recommendation_runs"]
    assert "JSON" in ddl["profiles"] and "JSON" in ddl["recommendation_runs"] and "JSON" in ddl["recommendation_items"]
    assert "TIMESTAMP WITHOUT TIME ZONE" in ddl["recommendation_runs"]            # UTC stored by UTCDateTime
    assert "BOOLEAN" in ddl["recommendation_runs"] and "FLOAT" in ddl["recommendation_items"]
    assert "FOREIGN KEY(issue_id) REFERENCES cached_issues (id)" in ddl["recommendation_items"]
    assert not any("AUTOINCREMENT" in d for d in ddl.values())
    for t in Base.metadata.sorted_tables:
        for ix in t.indexes:
            CreateIndex(ix).compile(dialect=pg)


def test_history_query_has_no_outer_group_by_for_postgresql():
    """The ORM eager-loads each run's profile; an outer GROUP BY on runs.id alone is rejected by PostgreSQL."""
    sql = str(history_statement(20, 0).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert sql.count("GROUP BY") == 1 and "GROUP BY recommendation_items.run_id" in sql   # only inside the subquery
    assert "LEFT OUTER JOIN (SELECT" in sql and "LIMIT 20 OFFSET 0" in sql


# --------------------------------------------------------------------------- NUL characters
def test_nul_characters_are_stripped_for_postgresql():
    issue = Issue.model_validate(_issue_kwargs(title="bad\x00title", body="a\x00b", labels=["x\x00y"], repo_description="d\x00"))
    assert "\x00" not in issue.title + issue.body + issue.labels[0] + issue.repo_description
    assert DeveloperProfile(skills=["Py\x00thon"]).skills == ["Python"]


def _issue_kwargs(**over):
    from app.services.github_client import GitHubClient
    return GitHubClient._parse_issue(make_item(1, **over))[0] | {k: v for k, v in over.items() if k in ("title", "body", "repo_description", "labels")}


# --------------------------------------------------------------------------- concurrency safety
def test_concurrent_duplicate_profile_insert_returns_the_existing_row(monkeypatch):
    p = DeveloperProfile(skills=["Python"])
    with SessionLocal() as db:
        first, created = create_or_get_profile(db, p)
        assert created
        real, calls = db.scalar, {"n": 0}

        def blind_first_lookup(stmt, *a, **k):          # simulate: the other request commits between lookup and insert
            calls["n"] += 1
            return None if calls["n"] == 1 else real(stmt, *a, **k)

        monkeypatch.setattr(db, "scalar", blind_first_lookup)
        again, created2 = create_or_get_profile(db, p)
    assert created2 is False and again.id == first.id


# --------------------------------------------------------------------------- failures
def _mini_app(exc_factory):
    a = FastAPI()
    register_exception_handlers(a)

    @a.get("/boom")
    def boom():
        raise exc_factory()
    return TestClient(a, raise_server_exceptions=False)


@pytest.mark.parametrize("factory", [
    lambda: OperationalError("SELECT 1", {}, Exception("connection to ep-x.neon.tech failed password=hunter2")),
    lambda: InterfaceError("SELECT 1", {}, Exception("connection already closed hunter2")),
    lambda: PoolTimeoutError("QueuePool limit of size 5 overflow 5 reached hunter2"),
])
def test_connection_errors_become_a_clean_503(factory):
    r = _mini_app(factory).get("/boom")
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"
    assert r.headers["retry-after"] == "5"
    assert "hunter2" not in r.text and "neon" not in r.text.lower()


def test_database_down_on_first_request_then_recovers(client, monkeypatch):
    real, calls = S.init_db, {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("CREATE TABLE", {}, Exception("connection refused hunter2"))
        return real(*a, **k)

    monkeypatch.setattr(S, "init_db", flaky)
    monkeypatch.setattr(S, "_initialised", False)
    down = client.get("/api/history")
    assert down.status_code == 503 and down.json()["error"]["code"] == "service_unavailable"
    assert "hunter2" not in down.text
    assert client.get("/api/history").status_code == 200          # retried and succeeded on the next request


def test_server_starts_even_if_the_database_is_unreachable_at_boot(monkeypatch):
    import app.main as m

    def down():
        raise OperationalError("CREATE TABLE", {}, Exception("connection refused"))

    monkeypatch.setattr(m, "ensure_initialized", down)
    with TestClient(fastapi_app) as c:                            # lifespan runs; must not raise
        assert c.get("/api/health/live").json() == {"status": "ok"}


def test_liveness_never_touches_the_database(client, monkeypatch):
    def forbidden():
        raise AssertionError("liveness must not query the database")

    monkeypatch.setattr("app.api.routes.health.check_db", forbidden)
    monkeypatch.setattr("app.api.routes.health.ensure_initialized", forbidden)
    assert client.get("/api/health/live").json() == {"status": "ok"}


def test_readiness_reports_degraded_when_tables_cannot_be_created(client, monkeypatch):
    def fail():
        raise OperationalError("CREATE TABLE", {}, Exception("x"))

    monkeypatch.setattr("app.api.routes.health.ensure_initialized", fail)
    body = client.get("/api/health").json()
    assert body["status"] == "degraded" and body["database"] == "unavailable"


def test_root_route_points_to_docs_and_health(client):
    r = client.get("/")
    assert r.status_code == 200 and r.json()["health"] == "/api/health"
