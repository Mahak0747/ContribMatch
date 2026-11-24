import asyncio

import httpx

from tests.github_mock import make_item

URL = "/api/issues/search"


def test_search_returns_normalised_issues(gh_api):
    c, fake, _ = gh_api
    r = c.get(URL, params={"language": "Python", "labels": ["good first issue", "help wanted"]})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2 and body["cached"] is False and body["stale"] is False
    i = body["issues"][0]
    assert i["title"] == "Issue 1" and i["url"] == "https://github.com/octo/alpha/issues/1"
    assert i["labels"] == ["good first issue"] and i["state"] == "open"
    assert i["repo_full_name"] == "octo/alpha" and i["repo_url"] == "https://github.com/octo/alpha"
    assert i["repo_description"] == "Alpha ML toolkit" and i["repo_language"] == "Python" and i["repo_stars"] == 120
    assert i["created_at"].startswith("2026-01-01") and i["updated_at"].startswith("2026-02-01")
    assert i["comments"] == 1
    assert body["rate_limit"]["remaining"] == 9


def test_query_sent_to_github(gh_api):
    c, fake, _ = gh_api
    c.get(URL, params={"language": "Python", "labels": "good first issue,help wanted", "domain": "web", "per_page": 5})
    req = fake.search_calls[0]
    q = req.url.params["q"]
    assert "is:issue" in q and "is:open" in q and "language:Python" in q
    assert 'label:"good first issue","help wanted"' in q
    assert req.url.params["per_page"] == "5" and req.url.params["sort"] == "updated"


def test_pull_requests_excluded_and_duplicates_removed(gh_api):
    c, fake, _ = gh_api
    fake.items = [make_item(1), make_item(2, pr=True), make_item(1), make_item(3, "octo/beta")]
    body = c.get(URL).json()
    assert [i["number"] for i in body["issues"]] == [1, 3]


def test_repo_fetched_once_per_unique_repo(gh_api):
    c, fake, _ = gh_api
    fake.items = [make_item(i) for i in range(1, 8)] + [make_item(9, "octo/beta")]
    assert c.get(URL).json()["count"] == 8
    assert len(fake.repo_calls) == 2


def test_results_cached_no_extra_calls(gh_api):
    c, fake, _ = gh_api
    c.get(URL, params={"language": "Go"})
    n_search, n_repo = len(fake.search_calls), len(fake.repo_calls)
    r2 = c.get(URL, params={"language": "go"})  # case-insensitive key
    assert r2.json()["cached"] is True
    assert (len(fake.search_calls), len(fake.repo_calls)) == (n_search, n_repo)


def test_repo_cache_shared_across_searches(gh_api):
    c, fake, _ = gh_api
    c.get(URL, params={"q": "one"})
    calls = len(fake.repo_calls)
    c.get(URL, params={"q": "two"})
    assert len(fake.search_calls) == 2 and len(fake.repo_calls) == calls


def test_missing_body_and_labels_handled(gh_api):
    c, fake, _ = gh_api
    fake.items = [make_item(1, body=None, labels=()), make_item(2, labels=None)]
    body = c.get(URL).json()
    assert body["count"] == 2
    assert body["issues"][0]["body"] == "" and body["issues"][0]["labels"] == []
    assert body["issues"][1]["labels"] == []


def test_malformed_item_skipped(gh_api):
    c, fake, _ = gh_api
    fake.items = [{"id": 5}, make_item(2)]
    assert c.get(URL).json()["count"] == 1


def test_long_body_truncated(gh_api):
    c, fake, _ = gh_api
    fake.items = [make_item(1, body="x" * 5000)]
    assert len(c.get(URL).json()["issues"][0]["body"]) == 2000


def test_empty_results(gh_api):
    c, fake, _ = gh_api
    fake.items, fake.total = [], 0
    body = c.get(URL).json()
    assert body["count"] == 0 and body["issues"] == []


# ---- failure handling -------------------------------------------------------
def test_rate_limit_returns_429_with_retry_after(gh_api):
    c, fake, _ = gh_api
    fake.search_status = 403
    fake.search_headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}
    r = c.get(URL)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["details"]["retry_after_seconds"] >= 1


def test_secondary_rate_limit_429(gh_api):
    c, fake, _ = gh_api
    fake.search_status = 429
    fake.search_headers = {"retry-after": "30"}
    r = c.get(URL)
    assert r.status_code == 429 and r.headers["retry-after"] == "30"


def test_stale_cache_served_when_rate_limited(fake_github, gh_client_factory):
    from fastapi.testclient import TestClient
    from app.api.deps import get_github_client
    from app.main import app
    gh = gh_client_factory(search_ttl=0)  # entries expire immediately
    app.dependency_overrides[get_github_client] = lambda: gh
    try:
        with TestClient(app) as c:
            assert c.get(URL).status_code == 200
            fake_github.search_status = 429
            fake_github.search_headers = {"retry-after": "10"}
            r = c.get(URL)
            assert r.status_code == 200
            b = r.json()
            assert b["stale"] is True and b["cached"] is True and b["count"] == 2
            assert any("rate limit" in w.lower() for w in b["warnings"])
    finally:
        app.dependency_overrides.clear()


def test_timeout_returns_504_after_retries(gh_api):
    c, fake, _ = gh_api
    fake.raise_timeout = True
    r = c.get(URL)
    assert r.status_code == 504 and r.json()["error"]["code"] == "upstream_timeout"
    assert len(fake.search_calls) == 3  # 1 + 2 retries


def test_server_error_retried_then_succeeds(gh_api):
    c, fake, _ = gh_api
    fake.fail_times = 2
    assert c.get(URL).status_code == 200
    assert len(fake.search_calls) == 3


def test_persistent_server_error_503(gh_api):
    c, fake, _ = gh_api
    fake.fail_times = 99
    r = c.get(URL)
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_unavailable"


def test_github_422_maps_to_400(gh_api):
    c, fake, _ = gh_api
    fake.search_status = 422
    assert c.get(URL).status_code == 400


def test_bad_credentials_502_without_leaking_token(gh_api):
    c, fake, _ = gh_api
    fake.search_status = 401
    r = c.get(URL)
    assert r.status_code == 502
    assert "fake-test-token-123" not in r.text


def test_repo_failure_degrades_gracefully(gh_api):
    c, fake, _ = gh_api
    fake.repo_status = 500
    r = c.get(URL)
    assert r.status_code == 200
    b = r.json()
    assert b["count"] == 2 and b["issues"][0]["repo_description"] is None
    assert any("Repository details unavailable" in w for w in b["warnings"])


def test_repo_rate_limit_stops_further_repo_calls(gh_api):
    c, fake, gh = gh_api
    fake.items = [make_item(i, f"o/r{i}") for i in range(1, 11)]
    fake.repo_status = 403
    fake.search_headers = {"x-ratelimit-remaining": "0"}
    gh._repo_concurrency = 1
    r = c.get(URL)
    assert r.status_code == 200 and r.json()["count"] == 10
    assert len(fake.repo_calls) == 1
    assert any("rate limit" in w.lower() for w in r.json()["warnings"])


# ---- security & validation ---------------------------------------------------
def test_token_sent_to_github_but_never_returned(gh_api):
    c, fake, _ = gh_api
    r = c.get(URL)
    assert fake.search_calls[0].headers["authorization"] == "Bearer fake-test-token-123"
    assert "fake-test-token-123" not in r.text and "fake-test-token-123" not in str(dict(r.headers))


def test_no_auth_header_without_token(fake_github, gh_client_factory):
    gh = gh_client_factory(token="")
    asyncio.run(gh.search_issues(__import__("app.schemas.issues", fromlist=["x"]).IssueSearchParams()))
    assert "authorization" not in fake_github.search_calls[0].headers


def test_invalid_query_params_422(gh_api):
    c, fake, _ = gh_api
    for params in ({"per_page": 0}, {"sort": "x"}, {"page": 99}, {"language": "a;b"}, {"nope": 1}):
        r = c.get(URL, params=params)
        assert r.status_code == 422, params
        assert r.json()["error"]["code"] == "validation_error"
    assert fake.requests == []  # invalid input never reaches GitHub
