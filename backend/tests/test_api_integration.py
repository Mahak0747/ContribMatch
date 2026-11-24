"""End-to-end API tests: FastAPI + SQLite + service + ML engine. Only GitHub (fake transport) and the embedding
model (test double) are replaced; everything else is the real code path."""
import re
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import CachedIssue, Profile, RecommendationItem, RecommendationRun
from tests.github_mock import REPOS, make_item

ML = {"skills": ["Python", "PyTorch"], "domains": ["machine learning"], "experience_level": "beginner",
      "preferred_languages": ["Python"], "learning_interests": ["Rust"]}


def ml_items():
    base = [
        make_item(1, "octo/alpha", body="Training the neural network with PyTorch in Python.", labels=("good first issue", "machine-learning")),
        make_item(2, "octo/alpha", body="Fix typo in the docs.", labels=("documentation",)),
        make_item(3, "octo/beta", body="Container pipeline for docker deploy.", labels=("bug",)),
        make_item(4, "octo/beta", body="Complex gradient rewrite.", labels=("advanced",), comments=12),
    ]
    for item, title in zip(base, ["Add PyTorch dataloader tests", "Fix README typo", "Dockerfile build fails", "Refactor gradient engine"]):
        item["title"] = title
    return base


def count(model):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model))


def run(api, body=None, **kw):
    return api.client.post("/api/recommendations", json=body or {"profile": ML, **kw})


@pytest.fixture()
def A(api):
    api.fake.items = ml_items()
    return api


# ---------------------------------------------------------------- profile
def test_profile_create_then_idempotent(A):
    r1 = A.client.post("/api/profile", json=ML)
    assert r1.status_code == 201 and r1.json()["id"] >= 1 and r1.json()["created_at"].endswith(("Z", "+00:00"))
    shuffled = {**ML, "skills": ["pytorch", "PYTHON"], "domains": ["Machine Learning"]}
    r2 = A.client.post("/api/profile", json=shuffled)
    assert r2.status_code == 200 and r2.json()["id"] == r1.json()["id"]
    assert count(Profile) == 1


@pytest.mark.parametrize("bad", [
    {"skills": "python"}, {"skills": [1]}, {"skills": ["a"], "experience_level": "guru"},
    {"skills": ["a"], "surprise": 1}, {"skills": ["x" * 60]},
])
def test_profile_validation_422(A, bad):
    r = A.client.post("/api/profile", json=bad)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert count(Profile) == 0


def test_empty_profile_422(A):
    r = A.client.post("/api/profile", json={"experience_level": "advanced"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unprocessable"
    assert A.client.post("/api/profile", content="not json", headers={"content-type": "application/json"}).status_code == 422


# ---------------------------------------------------------------- recommendations
def test_full_workflow_inline_profile(A):
    r = run(A)
    assert r.status_code == 201 and r.headers["location"] == f"/api/recommendations/{r.json()['id']}"
    b = r.json()
    recs = b["recommendations"]
    assert b["issues_analyzed"] == 4 and len(recs) == 4
    assert [x["rank"] for x in recs] == [1, 2, 3, 4]
    assert recs[0]["issue"]["title"] == "Add PyTorch dataloader tests"
    top = recs[0]
    assert set(top["scores"]) == {"overall", "semantic_similarity", "skill_compatibility", "experience_compatibility",
                                  "repository_activity", "beginner_friendliness"}
    assert all(0 <= v <= 100 for x in recs for v in x["scores"].values())
    assert top["matching_skills"] == ["Python", "PyTorch"] and "good first issue" in top["relevant_labels"]
    assert top["explanation"] and top["issue"]["url"].startswith("https://github.com/")
    assert top["issue"]["repo_language"] == "Python"
    assert b["model"] == "test-concept-embedder" and abs(sum(b["weights"].values()) - 1) < 1e-9
    assert any(q.startswith("is:issue is:open") for q in b["search_queries"])
    assert "fake-test-token-123" not in r.text


def test_profile_id_flow_and_persistence_roundtrip(A):
    pid = A.client.post("/api/profile", json=ML).json()["id"]
    created = run(A, {"profile_id": pid, "top_k": 3})
    assert created.status_code == 201 and len(created.json()["recommendations"]) == 3
    fetched = A.client.get(f"/api/recommendations/{created.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created.json()                       # stored result == returned result
    assert count(RecommendationRun) == 1 and count(RecommendationItem) == 3 and count(CachedIssue) == 4


def test_top_10_default_and_issues_analyzed(A):
    A.fake.items = [make_item(i, "octo/alpha") for i in range(1, 26)]
    b = run(A).json()
    assert len(b["recommendations"]) == 10 and b["issues_analyzed"] == 25
    assert len(run(A, top_k=20).json()["recommendations"]) == 20


@pytest.mark.parametrize("body,code", [
    ({}, 422), ({"profile": ML, "profile_id": 1}, 422), ({"profile": ML, "top_k": 0}, 422),
    ({"profile": ML, "top_k": 21}, 422), ({"profile_id": 0}, 422), ({"profile": ML, "labels": list("abcdefg")}, 422),
    ({"profile": {"skills": "x"}}, 422), ({"profile": {"experience_level": "beginner"}}, 422),
    ({"profile_id": 999}, 404),
])
def test_recommendation_request_errors(A, body, code):
    r = A.client.post("/api/recommendations", json=body)
    assert r.status_code == code and "error" in r.json()
    assert count(RecommendationRun) == 0


def test_unknown_run_and_bad_id(A):
    assert A.client.get("/api/recommendations/12345").status_code == 404
    assert A.client.get("/api/recommendations/abc").status_code == 422
    assert A.client.get("/api/recommendations/0").status_code == 422


def test_search_plan_uses_profile_and_level(A):
    run(A)
    qs = [r.url.params["q"] for r in A.fake.search_calls]
    assert 1 <= len(qs) <= 3
    assert "language:Python" in qs[0] and 'label:"good first issue","beginner","help wanted"' in qs[0]
    assert "machine learning" in qs[0]
    adv = {**ML, "experience_level": "advanced"}
    A.fake.requests.clear()
    A.gh.clear_cache()
    run(A, {"profile": adv})
    assert 'label:"help wanted"' in A.fake.search_calls[0].url.params["q"]


def test_labels_override(A):
    run(A, labels=["documentation"])
    assert 'label:"documentation"' in A.fake.search_calls[0].url.params["q"]


def test_repeat_request_makes_no_extra_github_calls(A):
    run(A)
    calls = (len(A.fake.search_calls), len(A.fake.repo_calls))
    assert run(A).status_code == 201
    assert (len(A.fake.search_calls), len(A.fake.repo_calls)) == calls
    assert count(RecommendationRun) == 2 and count(CachedIssue) == 4      # issues upserted, not duplicated


def test_two_languages_two_queries_deduped(A):
    prof = {**ML, "preferred_languages": ["Python", "Go"]}
    b = run(A, {"profile": prof}).json()
    assert len(A.fake.search_calls) >= 2
    assert b["issues_analyzed"] == 4                # same fake items from both searches are merged by issue id


def test_no_language_derives_from_skills_else_keyword(A):
    run(A, {"profile": {"skills": ["Python", "Docker"], "experience_level": "beginner"}})
    assert "language:Python" in A.fake.search_calls[0].url.params["q"]
    A.fake.requests.clear(); A.gh.clear_cache()
    run(A, {"profile": {"skills": ["Docker"], "experience_level": "beginner"}})
    qs = [r.url.params["q"] for r in A.fake.search_calls]
    assert len(qs) == 1 and "docker" in qs[0].lower() and "in:title,body" in qs[0]      # no label-only noise query
    A.fake.requests.clear(); A.gh.clear_cache()
    run(A, {"profile": {"domains": ["web development"], "skills": ["React"], "experience_level": "beginner"}})
    qs = [r.url.params["q"] for r in A.fake.search_calls]
    assert "web development" in qs[0] and "react" in qs[1].lower()


# ---------------------------------------------------------------- failure modes
def test_rate_limited_with_nothing_fetched_429_and_nothing_stored(A):
    A.fake.search_status, A.fake.search_headers = 429, {"retry-after": "42"}
    r = run(A)
    assert r.status_code == 429 and r.headers["retry-after"] == "42"
    assert count(RecommendationRun) == 0 and len(A.fake.search_calls) == 1     # stopped after first rate limit


def test_github_down_503_and_timeout_504(A):
    A.fake.fail_times = 99
    assert run(A).status_code == 503
    A.fake.fail_times = 0; A.fake.raise_timeout = True; A.gh.clear_cache()
    assert run(A).status_code == 504
    assert count(RecommendationRun) == 0


def test_partial_failure_still_returns_with_warning(A):
    A.fake.rate_limit_after = 1
    b = run(A, {"profile": {**ML, "preferred_languages": ["Python", "Go"]}})
    assert b.status_code == 201
    body = b.json()
    assert body["recommendations"] and any("rate limit" in w.lower() for w in body["warnings"])


def test_no_matching_issues_returns_empty_list_with_warning(A):
    A.fake.items, A.fake.total = [], 0
    r = run(A)
    assert r.status_code == 201
    b = r.json()
    assert b["recommendations"] == [] and b["issues_analyzed"] == 0
    assert any("No open GitHub issues" in w for w in b["warnings"])
    assert count(RecommendationRun) == 1


def test_embedding_model_unavailable_503(A):
    from app.api.deps import get_engine
    from app.main import app
    from app.ml.embedder import EmbeddingModelError
    from app.ml.engine import RecommendationEngine

    class Broken:
        model_name = "broken"
        def embed(self, texts):
            raise EmbeddingModelError("no model")

    app.dependency_overrides[get_engine] = lambda: RecommendationEngine(Broken())
    r = run(A)
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_unavailable"
    assert "internet" in r.json()["error"]["message"]
    assert count(RecommendationRun) == 0 and count(CachedIssue) == 0


def test_db_failure_rolls_back(A, monkeypatch):
    from app.services import recommendation_service as rs
    orig = rs.RecommendationRun
    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(rs, "RecommendationRun", boom)
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app, raise_server_exceptions=False).post("/api/recommendations", json={"profile": ML})
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error" and "disk full" not in r.text
    monkeypatch.setattr(rs, "RecommendationRun", orig)
    assert count(RecommendationRun) == 0 and count(CachedIssue) == 0


# ---------------------------------------------------------------- history
def test_history_order_pagination_and_fields(A):
    ids = [run(A, {"profile": {**ML, "skills": ["Python", f"extra{i}"]}}).json()["id"] for i in range(3)]
    h = A.client.get("/api/history").json()
    assert h["total"] == 3 and [e["id"] for e in h["items"]] == ids[::-1]
    e = h["items"][0]
    assert e["recommendation_count"] == 4 and e["issues_analyzed"] == 4 and e["top_score"] > 0
    assert e["experience_level"] == "beginner" and "Python" in e["skills"]
    page = A.client.get("/api/history", params={"limit": 2, "offset": 2}).json()
    assert [x["id"] for x in page["items"]] == [ids[0]] and page["limit"] == 2 and page["offset"] == 2
    assert A.client.get("/api/history", params={"offset": 99}).json()["items"] == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "x"}])
def test_history_invalid_params(A, params):
    assert A.client.get("/api/history", params=params).status_code == 422


def test_history_empty(A):
    assert A.client.get("/api/history").json() == {"total": 0, "limit": 20, "offset": 0, "items": []}


# ---------------------------------------------------------------- analytics
def test_analytics_empty_db(A):
    b = A.client.get("/api/analytics").json()
    assert b["totals"] == {"profiles": 0, "recommendation_runs": 0, "recommendations_generated": 0,
                           "issues_analyzed": 0, "unique_issues_recommended": 0, "cached_issues": 0}
    assert b["average_scores"] is None and b["top_matching_skills"] == []
    assert sum(x["count"] for x in b["score_distribution"]) == 0


def test_analytics_matches_stored_data(A):
    r1 = run(A).json()
    r2 = run(A, {"profile": {"skills": ["React", "CSS"], "domains": ["web development"], "experience_level": "advanced"}, "top_k": 2}).json()
    b = A.client.get("/api/analytics").json()
    n = len(r1["recommendations"]) + len(r2["recommendations"])
    assert b["totals"]["recommendation_runs"] == 2 and b["totals"]["profiles"] == 2
    assert b["totals"]["recommendations_generated"] == n == 6
    assert b["totals"]["issues_analyzed"] == r1["issues_analyzed"] + r2["issues_analyzed"] == 8
    assert b["totals"]["unique_issues_recommended"] == 4 and b["totals"]["cached_issues"] == 4
    assert sum(x["count"] for x in b["score_distribution"]) == n
    assert sum(x["count"] for x in b["skill_compatibility_distribution"]) == n
    assert sum(x["count"] for x in b["matching_skill_count_distribution"]) == n
    assert {x["label"] for x in b["requested_domains"]} == {"machine learning", "web development"}
    assert {x["label"]: x["count"] for x in b["experience_level_distribution"]} == {"beginner": 1, "advanced": 1}
    assert {x["label"]: x["count"] for x in b["top_matching_skills"]}.get("Python", 0) >= 1
    expected_avg = round(sum(x["scores"]["overall"] for x in r1["recommendations"] + r2["recommendations"]) / n, 1)
    assert b["average_scores"]["overall"] == pytest.approx(expected_avg, abs=0.1)
    langs = {x["label"]: x["count"] for x in b["recommended_language_distribution"]}
    assert sum(langs.values()) == n


# ---------------------------------------------------------------- architecture / security
def test_ml_package_is_independent_of_web_and_db():
    """Clean separation: app/ml must not import FastAPI, SQLAlchemy, the DB, routes or services."""
    banned = re.compile(r"^\s*(from|import)\s+(fastapi|sqlalchemy|starlette|app\.(api|db|models|services|core))", re.M)
    for f in Path("app/ml").glob("*.py"):
        text = f.read_text()
        assert not banned.search(text.replace("from app.core.config import get_settings", "")), f
    # (embedder.get_embedder lazily imports settings; scoring/engine/etc. are pure)


def test_health_and_issue_search_still_work(A):
    assert A.client.get("/api/health").json()["status"] == "ok"
    assert A.client.get("/api/issues/search").status_code == 200


def test_cors_for_new_endpoints(A):
    r = A.client.options("/api/recommendations", headers={"Origin": "http://localhost:5173",
                                                          "Access-Control-Request-Method": "POST"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_refetching_an_issue_refreshes_fetched_at(A):
    import time
    run(A)
    with SessionLocal() as db:
        first = db.scalar(select(CachedIssue.fetched_at).where(CachedIssue.id == 1001))
    time.sleep(0.05)
    A.gh.clear_cache()
    run(A, {"profile": {**ML, "skills": ["Python", "Other"]}})
    with SessionLocal() as db:
        second = db.scalar(select(CachedIssue.fetched_at).where(CachedIssue.id == 1001))
        assert db.scalar(select(func.count()).select_from(CachedIssue)) == 4
    assert second > first
