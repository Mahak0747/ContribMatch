import os
import tempfile

# Must be set before the app (and its DB engine) is imported, so tests never touch the dev DB.
_tmp = tempfile.mkdtemp(prefix="contribmatch_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---- GitHub mock helpers -------------------------------------------------------
import httpx  # noqa: E402

from app.api.deps import get_github_client  # noqa: E402
from app.services.github_client import GitHubClient  # noqa: E402
from tests.github_mock import FakeGitHub  # noqa: E402


@pytest.fixture()
def fake_github():
    return FakeGitHub()


@pytest.fixture()
def gh_client_factory(fake_github):
    def make(**kw):
        kw.setdefault("backoff", 0)
        return GitHubClient(transport=httpx.MockTransport(fake_github), **kw)
    return make


@pytest.fixture()
def gh_api(fake_github, gh_client_factory):
    """TestClient whose GitHub dependency talks to the fake. Returns (client, fake, github_client)."""
    gh = gh_client_factory(token="fake-test-token-123")
    app.dependency_overrides[get_github_client] = lambda: gh
    with TestClient(app) as c:
        yield c, fake_github, gh
    app.dependency_overrides.clear()


# ---- DB isolation + full-stack API fixture ------------------------------------
from app.db.base import Base  # noqa: E402
from app.db.session import engine as db_engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    import app.models  # noqa: F401
    Base.metadata.drop_all(bind=db_engine)
    init_db()
    yield


@pytest.fixture()
def api(fake_github, gh_client_factory):
    """TestClient with BOTH external dependencies replaced: GitHub -> fake transport, embedding model ->
    test double. Returns an object with .client, .fake, .gh, .embedder."""
    from types import SimpleNamespace

    from app.api.deps import get_engine
    from app.ml.engine import RecommendationEngine
    from tests.ml_doubles import NOW, ConceptEmbedder

    gh = gh_client_factory(token="fake-test-token-123")
    emb = ConceptEmbedder()
    eng = RecommendationEngine(emb, now=NOW)
    app.dependency_overrides[get_github_client] = lambda: gh
    app.dependency_overrides[get_engine] = lambda: eng
    with TestClient(app) as c:
        yield SimpleNamespace(client=c, fake=fake_github, gh=gh, embedder=emb, engine=eng)
    app.dependency_overrides.clear()
