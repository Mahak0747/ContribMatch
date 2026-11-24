"""Collect REAL candidate GitHub issues for every evaluation profile and freeze them in data/candidates.json.

    python evaluation/collect_candidates.py            # search only (works unauthenticated, ~7 min)
    python evaluation/collect_candidates.py --enrich   # also fetch repo description/language/stars/pushed_at
                                                       # (needs GITHUB_TOKEN; costs one core-API call per repo)

Pooling: for each profile, issues come from three GitHub searches ranked by GitHub's own "best match"
(NOT by ContribMatch's scorers, so candidate selection does not depend on the systems being evaluated):
  specific   - profile language + one domain keyword (up to 6 issues)
  broad      - profile language (or a related keyword) only (up to 4)
  distractor - an unrelated language/keyword (up to 2), so every candidate list also contains clear negatives
The pool tag is stored for post-hoc analysis only; it is never used for scoring and was hidden while labelling.
Candidate order is shuffled with a fixed seed so file order carries no signal.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.exceptions import RateLimitError  # noqa: E402
from app.schemas.issues import Issue, IssueSearchParams  # noqa: E402
from app.services.github_client import GitHubClient, build_search_query  # noqa: E402

SEED = 20260101
PER_POOL = {"specific": 6, "broad": 4, "distractor": 2}
FETCH = {"specific": 12, "broad": 10, "distractor": 6}
SEARCH_DELAY = 6.5  # unauthenticated search limit is 10 requests/minute

# (language, keyword) for the specific / broad / distractor searches of each profile.
PLANS: dict[str, tuple[tuple, tuple, tuple]] = {
    "q01": (("Python", "flask"), ("Python", ""), ("Rust", "")),
    "q02": (("JavaScript", "css"), ("JavaScript", ""), ("Go", "")),
    "q03": (("Python", "pytorch"), ("Python", "machine learning"), ("Java", "")),
    "q04": (("Rust", "performance"), ("C++", ""), ("Ruby", "")),
    "q05": (("TypeScript", "react"), ("TypeScript", ""), ("Python", "pandas")),
    "q06": (("Java", "android"), ("Java", ""), ("Python", "django")),
    "q07": (("Go", "kubernetes"), ("Go", "docker"), ("JavaScript", "css")),
    "q08": (("Python", "pandas"), ("Python", "data"), ("Go", "")),
    "q09": (("Python", "django"), ("Python", "postgresql"), ("Swift", "")),
    "q10": (("C#", "unity"), ("C#", ""), ("Python", "nlp")),
    "q11": ((None, "documentation"), (None, "typo"), ("Rust", "")),
    "q12": (("Swift", "ios"), ("Swift", ""), ("Java", "spring")),
    "q13": (("Python", "security"), (None, "cryptography"), ("JavaScript", "css")),
    "q14": (("Ruby", "rails"), ("Ruby", ""), ("C", "")),
    "q15": (("C", "cli"), ("C", ""), ("TypeScript", "react")),
    "q16": (("PHP", "laravel"), ("PHP", ""), ("Go", "")),
    "q17": (("TypeScript", "cli"), ("TypeScript", "graphql"), ("Python", "scikit-learn")),
    "q18": (("Python", "nlp"), ("Python", "transformers"), ("PHP", "")),
    "q19": (("Kotlin", "android"), ("Kotlin", ""), ("Python", "flask")),
    "q20": (("Python", "ansible"), ("Shell", ""), ("Swift", "")),
}
LABELS = {"beginner": ["good first issue", "help wanted"], "intermediate": ["help wanted"], "advanced": ["help wanted"]}


async def search(client: GitHubClient, params: IssueSearchParams) -> list[dict]:
    q = build_search_query(params)
    for attempt in range(4):
        try:
            # private helpers are used on purpose: the public search also spends core-API calls on repo details
            data, _ = await client._request("/search/issues", {"q": q, "per_page": params.per_page, "page": 1})
            break
        except RateLimitError as exc:
            wait = exc.retry_after + 2
            print(f"    rate limited, sleeping {wait}s", flush=True)
            await asyncio.sleep(wait)
    else:
        raise RuntimeError("GitHub search kept rate limiting")
    out = []
    for item in data.get("items", []):
        parsed = client._parse_issue(item)
        if parsed:
            out.append(parsed[0])
    return out


PARTIAL = HERE / "data" / ".candidates_partial.json"


async def main(enrich: bool, max_queries: int | None) -> None:
    queries = {r["query_id"]: r for r in csv.DictReader(open(HERE / "evaluation_queries.csv", encoding="utf-8"))}
    client = GitHubClient.from_settings(get_settings())
    # resumable: finished profiles are saved after each one, so an interrupted run continues where it stopped
    result: dict[str, list[dict]] = json.loads(PARTIAL.read_text(encoding="utf-8")) if PARTIAL.exists() else {}
    done_this_run = 0
    for qid, row in queries.items():
        if qid in result:
            continue
        if max_queries is not None and done_this_run >= max_queries:
            print(f"stopping after {done_this_run} profiles; {len(queries) - len(result)} remaining. Run again to continue.")
            return
        rng = random.Random(f"{SEED}-{qid}")   # per-profile seed so order does not depend on resume points
        labels = LABELS[row["experience_level"]]
        pools: dict[str, list[dict]] = {}
        for pool, (lang, kw) in zip(("specific", "broad", "distractor"), PLANS[qid]):
            params = IssueSearchParams(language=lang, labels=labels, q=kw or None, per_page=FETCH[pool])
            print(f"{qid} {pool:10s} {build_search_query(params)}", flush=True)
            pools[pool] = await search(client, params)
            await asyncio.sleep(SEARCH_DELAY)

        chosen: dict[int, dict] = {}
        for pool in ("specific", "broad", "distractor"):
            n = 0
            for d in pools[pool]:
                if d["id"] not in chosen and n < PER_POOL[pool]:
                    chosen[d["id"]] = {**d, "pool": pool}
                    n += 1
        for pool in ("specific", "broad"):          # top up to at least 10 candidates if a pool ran dry
            for d in pools[pool]:
                if len(chosen) >= 10:
                    break
                chosen.setdefault(d["id"], {**d, "pool": pool})
        items = list(chosen.values())
        rng.shuffle(items)
        result[qid] = items
        done_this_run += 1
        PARTIAL.write_text(json.dumps(result), encoding="utf-8")
        pool_counts = ", ".join(f"{p}:{sum(1 for i in items if i['pool'] == p)}" for p in PER_POOL)
        print(f"  -> {qid}: {len(items)} candidates ({pool_counts})", flush=True)

    if enrich:
        repos = sorted({i["repo_full_name"] for items in result.values() for i in items})
        print(f"enriching {len(repos)} repositories", flush=True)
        meta = {}
        for name in repos:
            try:
                meta[name] = await client._get_repo(name)
            except Exception as exc:  # noqa: BLE001
                print(f"  repo {name}: {type(exc).__name__}", flush=True)
        for items in result.values():
            for i in items:
                m = meta.get(i["repo_full_name"])
                if m:
                    i.update(repo_description=m["description"], repo_language=m["language"],
                             repo_stars=m["stars"], repo_pushed_at=m["pushed_at"])

    # validate against the production schema, then freeze
    for items in result.values():
        for i in items:
            Issue.model_validate({k: v for k, v in i.items() if k != "pool"})
    out = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "GitHub REST search API (open issues, pull requests excluded, unassigned)",
        "repo_metadata_collected": enrich,
        "seed": SEED,
        "queries": {q: [json.loads(Issue.model_validate({k: v for k, v in i.items() if k != 'pool'}).model_dump_json()) | {"pool": i["pool"]} for i in items]
                    for q, items in result.items()},
    }
    (HERE / "data" / "candidates.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    await client.aclose()
    PARTIAL.unlink(missing_ok=True)
    print("saved", HERE / "data" / "candidates.json", "total issues:", sum(len(v) for v in result.values()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrich", action="store_true", help="fetch repository metadata (needs GITHUB_TOKEN)")
    ap.add_argument("--max-queries", type=int, default=None, help="process at most N profiles, then stop (resume by re-running)")
    args = ap.parse_args()
    asyncio.run(main(args.enrich, args.max_queries))
