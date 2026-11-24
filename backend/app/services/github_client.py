"""Async GitHub REST client for discovering open issues.

Design notes
- One search call per request (``/search/issues``) returns up to ``per_page`` issues.
- Repository details (description, language, stars) are NOT in search results, so we fetch
  ``/repos/{owner}/{repo}`` once per *unique* repository (not per issue), concurrently, and
  cache it for a long time.
- Search results are cached in memory (TTL). If GitHub is rate-limited/unavailable and an
  expired cached result exists, it is served with ``stale=True`` instead of failing.
- The token is only ever placed in the outgoing Authorization header.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    BadRequestError,
    ExternalServiceError,
    GatewayTimeoutError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
)
from app.schemas.issues import Issue, IssueSearchParams, IssueSearchResponse, RateLimitInfo

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 2000


class TTLCache:
    """Tiny in-memory cache. Expired entries are kept (until evicted) so they can serve as stale fallback."""

    def __init__(self, max_size: int = 256):
        self._d: OrderedDict[Any, tuple[Any, float, float]] = OrderedDict()
        self._max = max_size

    def set(self, key, value, ttl: float) -> None:
        now = time.monotonic()
        self._d[key] = (value, now + ttl, now)
        self._d.move_to_end(key)
        while len(self._d) > self._max:
            self._d.popitem(last=False)

    def get(self, key):
        """Return (value, is_fresh, age_seconds) or None."""
        item = self._d.get(key)
        if item is None:
            return None
        value, expires, stored = item
        now = time.monotonic()
        return value, now < expires, now - stored

    def clear(self) -> None:
        self._d.clear()


def build_search_query(params: IssueSearchParams) -> str:
    """Build the GitHub issue-search query string (values are pre-validated/sanitised)."""
    parts = ["is:issue", "is:open", "archived:false"]
    if params.unassigned:
        parts.append("no:assignee")
    if params.language:
        lang = params.language
        parts.append(f'language:"{lang}"' if not lang.isalnum() else f"language:{lang}")
    if params.labels:
        # comma-separated values inside one qualifier are OR-ed by GitHub
        parts.append("label:" + ",".join(f'"{l}"' for l in params.labels))
    keywords = " ".join(x for x in (params.domain, params.q) if x)
    if keywords:
        parts.append(keywords)
        parts.append("in:title,body")
    return " ".join(parts)


def _parse_rate_limit(headers: httpx.Headers) -> RateLimitInfo | None:
    def _int(name):
        try:
            return int(headers[name])
        except (KeyError, ValueError):
            return None

    limit, remaining, reset = _int("x-ratelimit-limit"), _int("x-ratelimit-remaining"), _int("x-ratelimit-reset")
    if limit is None and remaining is None and reset is None:
        return None
    return RateLimitInfo(
        limit=limit,
        remaining=remaining,
        reset_at=datetime.fromtimestamp(reset, tz=timezone.utc) if reset else None,
    )


class GitHubClient:
    def __init__(
        self,
        token: str = "",
        base_url: str = "https://api.github.com",
        timeout: float = 10.0,
        max_retries: int = 2,
        backoff: float = 0.5,
        search_ttl: int = 600,
        repo_ttl: int = 86400,
        repo_concurrency: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ContribMatch/0.2",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.authenticated = bool(token)
        self._http = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout,
            follow_redirects=True, transport=transport,
        )
        self._max_retries = max_retries
        self._backoff = backoff
        self._search_ttl = search_ttl
        self._repo_ttl = repo_ttl
        self._repo_concurrency = max(1, repo_concurrency)
        self._search_cache = TTLCache(128)
        self._repo_cache = TTLCache(1024)

    @classmethod
    def from_settings(cls, s: Settings) -> "GitHubClient":
        return cls(
            token=s.github_token, base_url=s.github_api_url, timeout=s.github_timeout_seconds,
            max_retries=s.github_max_retries, backoff=s.github_retry_backoff_seconds,
            search_ttl=s.github_search_cache_ttl_seconds, repo_ttl=s.github_repo_cache_ttl_seconds,
            repo_concurrency=s.github_repo_concurrency,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def clear_cache(self) -> None:
        self._search_cache.clear()
        self._repo_cache.clear()

    # ------------------------------------------------------------------ HTTP
    @staticmethod
    def _rate_limit_error(resp: httpx.Response) -> RateLimitError | None:
        """Return a RateLimitError if this 403/429 response is a rate-limit response."""
        try:
            message = str(resp.json().get("message", ""))
        except Exception:
            message = ""
        h = resp.headers
        is_limited = (
            resp.status_code == 429
            or h.get("x-ratelimit-remaining") == "0"
            or "retry-after" in h
            or "rate limit" in message.lower()
        )
        if not is_limited:
            return None
        retry_after = 60
        if "retry-after" in h:
            try:
                retry_after = int(h["retry-after"])
            except ValueError:
                pass
        elif h.get("x-ratelimit-reset", "").isdigit():
            retry_after = int(h["x-ratelimit-reset"]) - int(time.time())
        retry_after = max(1, min(retry_after, 3600))
        hint = "" if "authorization" in {k.lower() for k in resp.request.headers} else " Configuring GITHUB_TOKEN raises the limit."
        return RateLimitError(f"GitHub API rate limit reached. Retry in about {retry_after}s.{hint}", retry_after)

    async def _request(self, path: str, params: dict | None = None) -> tuple[Any, httpx.Headers]:
        last_timeout = False
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._http.get(path, params=params)
            except httpx.TimeoutException:
                last_timeout = True
                logger.warning("GitHub request timed out (%s), attempt %d", path, attempt + 1)
            except httpx.TransportError as exc:
                last_timeout = False
                logger.warning("GitHub transport error (%s): %s", path, type(exc).__name__)
            else:
                status = resp.status_code
                if status == 200:
                    try:
                        return resp.json(), resp.headers
                    except ValueError:
                        raise ExternalServiceError("GitHub returned an invalid response") from None
                if status in (403, 429):
                    rl = self._rate_limit_error(resp)
                    if rl:
                        raise rl
                    raise ExternalServiceError("GitHub denied the request (403)")
                if status == 401:
                    raise ExternalServiceError("GitHub rejected the configured credentials")
                if status == 404:
                    raise NotFoundError("GitHub resource not found")
                if status == 422:
                    raise BadRequestError("GitHub could not process this search query")
                if status < 500:
                    raise ExternalServiceError(f"Unexpected response from GitHub ({status})")
                last_timeout = False
                logger.warning("GitHub %d for %s, attempt %d", status, path, attempt + 1)
            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff * (2 ** attempt))
        if last_timeout:
            raise GatewayTimeoutError("GitHub did not respond in time")
        raise ServiceUnavailableError("GitHub is currently unavailable")

    # --------------------------------------------------------------- parsing
    @staticmethod
    def _parse_issue(item: dict) -> tuple[dict, str] | None:
        """Convert a raw search item to Issue kwargs (without repo details). None if PR/malformed."""
        if "pull_request" in item:
            return None
        try:
            repo_api_url = item["repository_url"]
            full_name = "/".join(repo_api_url.rstrip("/").split("/")[-2:])
            labels = [
                (l.get("name") if isinstance(l, dict) else str(l))
                for l in (item.get("labels") or [])
            ]
            data = dict(
                id=item["id"], number=item["number"], title=(item["title"] or "").strip(),
                body=(item.get("body") or "").strip()[:MAX_BODY_CHARS],
                url=item["html_url"], state=item.get("state", "open"),
                labels=[l for l in labels if l], comments=item.get("comments") or 0,
                created_at=item["created_at"], updated_at=item["updated_at"],
                repo_full_name=full_name, repo_url=f"https://github.com/{full_name}",
            )
            return data, full_name
        except (KeyError, TypeError, AttributeError):
            logger.warning("Skipping malformed issue item")
            return None

    async def _get_repo(self, full_name: str) -> dict:
        cached = self._repo_cache.get(full_name)
        if cached and cached[1]:
            return cached[0]
        try:
            data, _ = await self._request(f"/repos/{full_name}")
        except AppError:
            if cached:  # stale fallback
                return cached[0]
            raise
        info = {
            "description": data.get("description"),
            "language": data.get("language"),
            "stars": data.get("stargazers_count"),
            "pushed_at": data.get("pushed_at"),
        }
        self._repo_cache.set(full_name, info, self._repo_ttl)
        return info

    async def _fetch_repos(self, names: list[str]) -> tuple[dict[str, dict], list[str]]:
        sem = asyncio.Semaphore(self._repo_concurrency)
        results: dict[str, dict] = {}
        state = {"rate_limited": False, "failed": 0}

        async def one(name: str):
            async with sem:
                if state["rate_limited"]:
                    return
                try:
                    results[name] = await self._get_repo(name)
                except RateLimitError:
                    state["rate_limited"] = True
                except AppError:
                    state["failed"] += 1

        await asyncio.gather(*(one(n) for n in names))
        warnings = []
        missing = len(names) - len(results)
        if state["rate_limited"]:
            warnings.append(f"Repository details unavailable for {missing} repositories (GitHub rate limit reached).")
        elif missing:
            warnings.append(f"Repository details unavailable for {missing} repositories.")
        return results, warnings

    # ---------------------------------------------------------------- search
    async def _fetch_search(self, params: IssueSearchParams) -> IssueSearchResponse:
        q = build_search_query(params)
        query: dict[str, Any] = {"q": q, "per_page": params.per_page, "page": params.page}
        if params.sort != "best-match":
            query.update(sort=params.sort, order="desc")
        data, headers = await self._request("/search/issues", query)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ExternalServiceError("GitHub returned an unexpected search response")

        parsed: list[tuple[dict, str]] = []
        seen_ids: set[int] = set()
        seen_urls: set[str] = set()
        for item in data["items"]:
            p = self._parse_issue(item) if isinstance(item, dict) else None
            if not p:
                continue
            d, _ = p
            if d["id"] in seen_ids or d["url"] in seen_urls:
                continue
            seen_ids.add(d["id"])
            seen_urls.add(d["url"])
            parsed.append(p)

        repos, warnings = await self._fetch_repos(sorted({name for _, name in parsed}))
        issues: list[Issue] = []
        for d, name in parsed:
            r = repos.get(name) or {}
            try:
                issues.append(Issue(
                    **d,
                    repo_description=r.get("description"), repo_language=r.get("language"),
                    repo_stars=r.get("stars"), repo_pushed_at=r.get("pushed_at"),
                ))
            except ValidationError:
                logger.warning("Skipping issue that failed validation")
        return IssueSearchResponse(
            query=q, total_count=int(data.get("total_count") or 0),
            incomplete_results=bool(data.get("incomplete_results")),
            count=len(issues), page=params.page, per_page=params.per_page, issues=issues,
            warnings=warnings, rate_limit=_parse_rate_limit(headers),
        )

    async def search_issues(self, params: IssueSearchParams) -> IssueSearchResponse:
        key = params.cache_key()
        cached = self._search_cache.get(key)
        if cached and cached[1]:
            return cached[0].model_copy(update={"cached": True})
        try:
            result = await self._fetch_search(params)
        except (RateLimitError, ServiceUnavailableError, GatewayTimeoutError, ExternalServiceError) as exc:
            if cached:
                mins = max(1, int(cached[2] // 60))
                return cached[0].model_copy(update={
                    "cached": True, "stale": True,
                    "warnings": [*cached[0].warnings, f"{exc.message} Showing results cached about {mins} min ago."],
                })
            raise
        # Don't cache results whose repo enrichment was cut short, so they get completed next time.
        ttl = self._search_ttl if not result.warnings else min(self._search_ttl, 60)
        self._search_cache.set(key, result, ttl)
        return result
