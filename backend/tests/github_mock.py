"""Fake GitHub API for tests (httpx.MockTransport). No network access."""
import httpx


def make_item(i: int, repo: str = "octo/alpha", *, labels=("good first issue",), body="Some body", pr=False, **over):
    owner, name = repo.split("/")
    item = {
        "id": 1000 + i, "number": i, "title": f"Issue {i}", "body": body,
        "html_url": f"https://github.com/{repo}/issues/{i}", "state": "open",
        "labels": None if labels is None else [{"name": l} for l in labels], "comments": i,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-02-01T00:00:00Z",
        "repository_url": f"https://api.github.com/repos/{repo}",
    }
    if pr:
        item["pull_request"] = {"url": "x"}
    item.update(over)
    return item


REPOS = {
    "octo/alpha": {"description": "Alpha ML toolkit", "language": "Python", "stargazers_count": 120, "pushed_at": "2026-02-10T00:00:00Z"},
    "octo/beta": {"description": None, "language": "Go", "stargazers_count": 5, "pushed_at": "2025-01-01T00:00:00Z"},
}


class FakeGitHub:
    """Callable handler that records requests and can be told to misbehave."""

    def __init__(self, items=None, total=None):
        self.items = items if items is not None else [make_item(1), make_item(2, "octo/beta")]
        self.total = total if total is not None else len(self.items)
        self.requests: list[httpx.Request] = []
        self.search_status = 200
        self.search_headers: dict = {}
        self.search_json = None
        self.repo_status = 200
        self.fail_times = 0          # number of initial search calls that return 500
        self.raise_timeout = False
        self.rate_limit_after = None  # int: search calls beyond this many return 429

    @property
    def search_calls(self):
        return [r for r in self.requests if r.url.path == "/search/issues"]

    @property
    def repo_calls(self):
        return [r for r in self.requests if r.url.path.startswith("/repos/")]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/search/issues":
            if self.raise_timeout:
                raise httpx.ReadTimeout("timeout", request=request)
            if self.rate_limit_after is not None and len(self.search_calls) > self.rate_limit_after:
                return httpx.Response(429, headers={"retry-after": "30"}, json={"message": "rate limit"})
            if self.fail_times > 0:
                self.fail_times -= 1
                return httpx.Response(500, json={"message": "boom"})
            if self.search_status != 200:
                return httpx.Response(self.search_status, headers=self.search_headers,
                                      json=self.search_json or {"message": "error"})
            return httpx.Response(200, headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9",
                                                "x-ratelimit-reset": "1900000000"},
                                  json={"total_count": self.total, "incomplete_results": False, "items": self.items})
        if path.startswith("/repos/"):
            if self.repo_status != 200:
                return httpx.Response(self.repo_status, headers=self.search_headers if self.repo_status == 403 else {},
                                      json={"message": "API rate limit exceeded" if self.repo_status == 403 else "err"})
            full = "/".join(path.split("/")[2:4])
            if full in REPOS:
                return httpx.Response(200, json=REPOS[full])
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(404, json={"message": "Not Found"})
