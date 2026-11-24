# ContribMatch backend

FastAPI + SQLAlchemy (SQLite) + async HTTPX.

## Run
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                  # runtime + test tools (requirements.txt = runtime only)
cp .env.example .env                                  # Windows: copy .env.example .env
# optional but recommended: put a GitHub token in .env as GITHUB_TOKEN=...
uvicorn app.main:app --reload --port 8000
pytest
```
Interactive docs: http://localhost:8000/docs

## Endpoints
| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/api/health/live` | liveness only, no database access (Render health check) | 200 |
| GET | `/api/health` | readiness: also checks the database | 200 |
| POST | `/api/profile` | validate and save a developer profile (identical profiles are de-duplicated) | 201 new / 200 existing |
| POST | `/api/recommendations` | discover real GitHub issues, rank, explain, store; returns the top 10 | 201 |
| GET | `/api/recommendations/{id}` | a stored recommendation run | 200 |
| GET | `/api/history?limit=&offset=` | past runs, newest first | 200 |
| GET | `/api/analytics` | aggregates computed from the stored history | 200 |
| GET | `/api/issues/search` | raw GitHub issue search (Stage 2) | 200 |

Errors: 404 unknown profile/run, 422 invalid input (including an empty profile), 429 GitHub rate limit (with
`Retry-After`), 502/503/504 GitHub or model problems. Body shape: `{"error": {"code", "message", "details?"}}`.

### Recommendation workflow (`POST /api/recommendations`)
Body: `{"profile_id": 1}` **or** `{"profile": {...}}`, optional `top_k` (1-20, default 10) and `labels` override.
1. Resolve and validate the profile (inline profiles are saved first). 2. Plan up to 3 GitHub searches from the profile
(`services/search_plan.py`): languages (preferred, else languages found in skills), first domain as keyword, labels chosen by
experience level (beginner: good first issue / beginner / help wanted; intermediate: help wanted / good first issue;
advanced: help wanted), then a widening query. 3. Run the searches sequentially; a failure only aborts the request
if nothing at all was fetched, otherwise it is reported in `warnings`. 4. Merge/deduplicate by issue id.
5. Embed + score + rank + explain (`app/ml`). 6. Store the run, its items and every analysed issue in SQLite.
The first request loads the embedding model (needs internet once to download it); set `PRELOAD_MODEL=true` to load at startup.

### Persistence (SQLite, SQLAlchemy)
`profiles`, `cached_issues` (latest copy of each analysed issue), `recommendation_runs`, `recommendation_items`.
Tables are created with `create_all` (no migrations yet): after a model change in development, delete `backend/data/*.db`.
A stored run shows issues as last cached, so a later run that re-fetches an issue updates what older runs display.
GitHub calls are additionally de-duplicated by the in-memory caches from Stage 2.

### Analytics (`GET /api/analytics`)
Totals (profiles, runs, recommendations, issues analysed, unique issues, cached issues), average scores, histograms of overall
and skill-compatibility scores, distribution of matched-skill counts, top matched skills, requested domains (from profiles),
language and label distribution of recommended issues, experience-level mix. All of it is queried from the database.

### `GET /api/issues/search`
| Param | Notes |
|---|---|
| `language` | repository primary language, e.g. `Python`, `C++` |
| `labels` | repeat the param or comma-separate; max 5; matched as OR (e.g. `good first issue`, `help wanted`, `beginner`) |
| `domain`, `q` | keywords searched in issue title/body |
| `sort` | `updated` (default), `created`, `comments`, `best-match` |
| `per_page` (1-50, default 20), `page` (1-10) | pagination |
| `unassigned` | default `true`: only issues with no assignee |

Always applied: `is:issue is:open archived:false` (pull requests are excluded; also filtered defensively).

Response: `issues[]` (title, body, url, state, labels, comments, created/updated dates, repo name/url/description/language/stars/last push), plus `query`, `total_count`, `cached`, `stale`, `warnings`, `rate_limit`.

Errors use `{"error": {"code", "message", "details?"}}`: 422 invalid params, 400 GitHub rejected query, 429 rate limited (with `Retry-After`), 502 upstream/credential problem, 503 GitHub down, 504 timeout.

## How GitHub usage is kept low
- One search request per query (30 requests/min with token, 10 without).
- Repository details are not in search results, so they are fetched once per **unique repository** (never per issue), concurrently with a cap, and cached 24 h.
- Search results are cached in memory for 10 min. If GitHub is rate-limited or down and an expired cached result exists, it is served with `stale: true` and a warning.
- Timeouts and 5xx errors are retried with exponential backoff; rate limits are not retried.
- Without `GITHUB_TOKEN` the core API allows only 60 requests/hour, so repo details can run out quickly. The endpoint still returns issues, with `repo_description`/`repo_language` empty and a warning. Set a token for real use.

The in-memory cache resets on restart. Persistent issue caching in SQLite comes in Stage 4.

## Recommendation engine (`app/ml/`)

> **What is pretrained and what is ours.** The embedding model (`sentence-transformers/all-MiniLM-L6-v2`) is a
> **pretrained third-party model that runs locally**; we do **not** train or fine-tune it. Everything else
> (text construction, the five scores, weights, explanations) is our own hand-designed algorithm. The weights and
> thresholds are **initial design choices, not learned parameters**. No paid or hosted LLM APIs are used.

Pipeline (`engine.py`): profile + issues -> text (`text_builder.py`) -> **one batched** embedding call
(`embedder.py`: model loaded once, vectors cached by text hash, normalised) -> cosine similarity (scikit-learn) ->
five components (`scoring.py`) -> weighted final score -> pandas sort -> explanations (`explain.py`).

| Component | Weight | Definition (all 0-100) |
|---|---|---|
| Semantic similarity | 45% | cosine(profile, issue) mapped linearly: <=0.10 -> 0, >=0.60 -> 100 (design constants) |
| Skill compatibility | 20% | skills + preferred languages found in the issue. Whole-word match; title/labels/repo language = 1.0, description only = 0.6; `100*min(1, sum/min(#terms,3))` |
| Experience compatibility | 15% | *Estimated* issue difficulty (labels, description length, comment count) vs. the developer's level. No evidence -> neutral 50 |
| Repository activity | 10% | recency of repo last push (0.50) and issue last update (0.35), 45-day half-life, plus stars on a log scale (0.15). Missing parts are dropped and weights renormalised |
| Beginner friendliness | 10% | label-based estimate: base 30, +45 beginner label, +10 "help wanted", +10 substantive description, -10 empty description / long discussion, -25 "advanced/hard" label |

`Final = 0.45*semantic + 0.20*skill + 0.15*experience + 0.10*activity + 0.10*beginner`

GitHub does not provide difficulty or suitable experience level, so those two components are **estimates**; the
evidence used is returned in `difficulty_signals`. Experience level is intentionally not part of the embedded profile text.

Each recommendation returns the overall score and the five component scores, `cosine_similarity`, `matching_skills`,
`relevant_labels`, `potential_skills_to_learn` and an `explanation`. Explanations are assembled only from detected
facts (skills literally found, labels present, dates, the semantic score); if nothing matched, the explanation says so.
`potential_skills_to_learn` lists your stated learning interests found in the issue, then other known technologies
literally mentioned in it that you did not list.

Known limits: term matching is lexical (no stemming); very ambiguous names (`go`, `r`, `c`) only match via the
repo's primary language or an alias such as `golang`; the technology vocabulary is a fixed list.

### Keyword vs semantic comparison
```bash
python -m app.ml.compare                      # small SYNTHETIC illustration, needs the real model
python -m app.ml.compare --issues saved.json  # real issues saved from /api/issues/search
```
The first run downloads the model (~90 MB) from Hugging Face. Tests use deterministic test doubles instead of the
model, so they run offline; they verify code paths and logic only, **not** model quality. Measured quality is the job of Stage 6.

## Evaluation
`evaluation/` holds a reproducible benchmark (20 profiles, 240 real GitHub issues with relevance labels) comparing keyword,
semantic-only and hybrid ranking. See `evaluation/README.md` for the method, the actual results so far, and the limitations.
Run it with `python evaluation/evaluate.py` (the semantic and hybrid systems need the model download).

## PostgreSQL and cloud deployment
`DATABASE_URL` selects the database: SQLite for local development (default) or PostgreSQL (for example Neon). A
`postgresql://` or `postgres://` URL is switched to the psycopg 3 driver automatically; tables are created on startup, or
on the first request if the database was unreachable at boot. PostgreSQL connections use pre-checks, recycling and a
connect timeout; a database outage returns 503 `database_unavailable` and never crashes the server.
The embedding model loads lazily (`PRELOAD_MODEL=false`) and `scripts/prefetch_model.py` can download it at build time.
See `../docs/DEPLOYMENT.md` for Neon, Render and Vercel setup, and its list of known risks.
