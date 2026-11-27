# Deploying ContribMatch: Neon (database) + Render (API) + Vercel (frontend)

> **Status.** These files and settings were prepared by static inspection and targeted tests only. **Nothing has been deployed**, and the
> application has **not been run against a live PostgreSQL database**, on Render, or on Vercel. Dashboard labels below follow each service's
> documentation as I know it and may differ slightly from what you see. Read [Known risks](#known-risks-read-before-going-public) first.

## What gets deployed where

| Part | Service | Config in this repo |
|---|---|---|
| Database | Neon PostgreSQL | none: you create it and copy one connection string |
| API (FastAPI) | Render web service | `render.yaml`, `backend/.python-version`, `backend/scripts/prefetch_model.py` |
| Frontend (React) | Vercel static site | `frontend/vercel.json`, `frontend/.env.example` |

The browser talks to Render directly (`VITE_API_BASE_URL`); Render talks to GitHub and Neon. **Secrets exist only on Render**
(`DATABASE_URL`, `GITHUB_TOKEN`). The frontend never receives either, and its build fails if a secret-looking `VITE_*` variable is present.

## Do it in this order (each step needs a value from the previous one)

1. Neon: create the database, copy the **pooled** connection string.
2. Render: create the API with that string. Set `CORS_ORIGINS` to a placeholder for now. Copy the service URL.
3. Vercel: create the site with `VITE_API_BASE_URL` = that URL + `/api`. Copy the site URL.
4. Render: set `CORS_ORIGINS` to the Vercel URL. Verify.

---
## 1. Neon: database setup

1. Sign in at https://console.neon.tech and choose **Create project**.
2. **Name:** `contribmatch`. **Postgres version:** the default is fine. **Region:** **AWS US West 2 (Oregon)** to sit next to the Render region in `render.yaml` (`oregon`). If you pick another Neon region, change the Render region to the closest one.
3. Keep the default database (`neondb`) and role. Create the project.
4. Click **Connect** and **turn on "Connection pooling"**. The host should now contain `-pooler`:
   ```
   postgresql://neondb_owner:<PASSWORD>@ep-xxxxxxxx-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```
   Copy the whole string. Use it **exactly as shown** as `DATABASE_URL` on Render. You do **not** need to add `+psycopg`: the app rewrites `postgresql://` and `postgres://` to its psycopg 3 driver itself.
5. **Tables are created automatically** by the app on startup (or on the first request that needs the database). There is nothing to run by hand. After the API is live you can confirm in Neon's **SQL Editor**:
   ```sql
   select table_name from information_schema.tables where table_schema = 'public' order by 1;
   ```
   Expect `cached_issues`, `profiles`, `recommendation_items`, `recommendation_runs`.
6. Things to know:
   - **Auto-suspend.** Neon's free compute sleeps after a few idle minutes; the first query afterwards takes a moment to wake it. The app handles this (10 s connect timeout, connection pre-checks, 5-minute connection recycling, and a retry on the next request). The Render health check uses `/api/health/live`, which never touches the database, so it does not keep Neon awake.
   - **Existing data.** Your local SQLite history is **not** migrated; the cloud database starts empty. (A one-off copy script is not included.)
   - **Secret.** The string contains a password. Never commit it or paste it into the frontend. If it leaks, use Neon's **Reset password** and update Render.
   - Check Neon's current plan limits (storage, compute hours) for your needs.
7. Local development is unchanged: leave `DATABASE_URL` as the SQLite default in `backend/.env`. To test locally against Neon, put the string in your local `.env` (git-ignored); consider a separate Neon branch for that.

---
## 2. Render: API setup

Commit and push the repository to GitHub yourself first (nothing in this process pushes for you).

### Option A: Blueprint (uses `render.yaml`)
Render dashboard → **New** → **Blueprint** → choose the repository → Render reads `render.yaml`, shows one web service and asks for the three secret values:
`DATABASE_URL` (the Neon string), `GITHUB_TOKEN`, `CORS_ORIGINS` (use `http://localhost:5173` for now) → **Apply**.

### Option B: manual web service (same settings)
| Setting | Value |
|---|---|
| Type | Web Service |
| Name | `contribmatch-api` |
| Region | Oregon (US West), same as Neon |
| Branch | your deploy branch (for example `main`) |
| Root Directory | `backend` |
| Runtime / Language | Python 3 |
| **Build Command** | `pip install --upgrade pip && pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt && python scripts/prefetch_model.py` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips "*"` |
| Instance Type | **Standard (2 GB)**: see [memory](#1-memory-is-the-biggest-deployment-risk) |
| Health Check Path | `/api/health/live` |
| Auto-Deploy | Off (until you are happy) |

**Environment variables**

| Key | Value | Secret? |
|---|---|---|
| `PYTHON_VERSION` | `3.12.3` (if Render rejects the patch version, use any 3.12.x it offers) | no |
| `ENVIRONMENT` | `production` | no |
| `DEBUG` | `false` | no |
| `LOG_LEVEL` | `INFO` | no |
| `PRELOAD_MODEL` | `false` (the model loads lazily on the first recommendation request) | no |
| `MODEL_CACHE_DIR` | `.model_cache` | no |
| `DATABASE_URL` | the Neon pooled string | **yes** |
| `GITHUB_TOKEN` | a GitHub personal access token, **no scopes needed** (public data only) | **yes** |
| `CORS_ORIGINS` | your Vercel URL, for example `https://contribmatch.vercel.app` (no path; a trailing `/` is tolerated). Several origins: comma-separated | no |
| `CORS_ORIGIN_REGEX` | optional, for example `https://contribmatch-[a-z0-9-]+\.vercel\.app` to allow Vercel preview URLs | no |

Why each command part is there:
- `pip install torch --index-url …/whl/cpu` installs **CPU-only PyTorch** first. The default wheel pulls ~2 GB of CUDA libraries Render cannot use, which slows or breaks the build.
- `prefetch_model.py` downloads the ~90 MB embedding model **into the build** (`MODEL_CACHE_DIR`) so the first user request does not download it. The model is still loaded into memory only lazily. If the download fails, the build continues with a warning and the app downloads the model on first use instead.
- `--host 0.0.0.0 --port $PORT` is what Render requires. Only **one** worker is used on purpose (each worker would load its own copy of the model).
- `--proxy-headers --forwarded-allow-ips "*"` makes redirects keep `https://` behind Render's proxy.

### Verify the API (replace the host)
```bash
curl https://YOUR-SERVICE.onrender.com/api/health/live        # {"status":"ok"}
curl https://YOUR-SERVICE.onrender.com/api/health             # database should be "ok"
curl -i -H "Origin: https://YOUR-SITE.vercel.app" https://YOUR-SERVICE.onrender.com/api/health
#   -> look for: access-control-allow-origin: https://YOUR-SITE.vercel.app
```
Interactive docs: `https://YOUR-SERVICE.onrender.com/docs`.

---
## 3. Vercel: frontend setup

Vercel → **Add New… → Project** → import the repository.

| Setting | Value |
|---|---|
| Framework Preset | **Vite** |
| Root Directory | `frontend` |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Node.js Version | **22.x** (also set by `engines` in `package.json`) |

(`frontend/vercel.json` already contains these plus a fallback to `index.html` so deep links such as `/dashboard` survive a refresh, and basic security headers.)

**Environment variable** (Project → Settings → Environment Variables), for **Production** (and **Preview** if you use previews):

| Name | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://YOUR-SERVICE.onrender.com/api` |

- It is read **when the site is built**: after changing it, **redeploy**.
- If you give only the origin (`https://YOUR-SERVICE.onrender.com`), `/api` is added for you.
- It is public by design (it ends up in the JavaScript bundle). **Add no other variables**: anything starting with `VITE_` is public, and the build refuses names or values that look like tokens or database URLs.

Deploy, copy the site URL (for example `https://contribmatch.vercel.app`), then **go back to Render and set `CORS_ORIGINS` to it**; Render restarts the service. Until you do, the browser will show the "Cannot reach the backend" error because the API refuses the origin.

Local development is unchanged: `npm run dev` still proxies `/api` to `http://localhost:8000` when `VITE_API_BASE_URL` is unset.

---
## Known risks (read before going public)

### 1. Memory is the biggest deployment risk
PyTorch plus the embedding model is large. Render's **Free and Starter instances have 512 MB RAM**, which I expect to be **too small**, so the service would be killed (out of memory) on the first recommendation request. `render.yaml` therefore specifies **Standard (2 GB)**, the smallest size I'd expect to work. **This is an estimate: I could not measure memory use here.** Check Render's current instance sizes and prices, and watch the Metrics tab after the first request. A lighter model runtime (for example ONNX) would be a code change and was not done.

### 2. The API is public, unauthenticated and unthrottled
Anyone who finds the URL can call `POST /api/recommendations`, which spends your **GitHub token's quota**, CPU, memory and database storage. There is **no rate limiting** and no authentication. Consider adding limits before sharing the URL widely.

### 3. History and analytics are global and visible to everyone
`GET /api/history` and `/api/analytics` return data from **all** users of the deployment, including the skills, domains and experience levels people entered. That is fine for a private demo and a privacy problem for a public app. Per-user ownership would be a behaviour change and was deliberately not made.

### 4. Slow first request / cold starts
The first recommendation after a deploy or restart loads the model (and Neon may wake from sleep). Expect it to take noticeably longer; the frontend waits up to 180 s. Free web services on Render also spin down when idle (not applicable to paid instances).

### 5. Unverified until you deploy
Not run against a live PostgreSQL, Render or Vercel: the build command on Render (CPU PyTorch + model prefetch), the Python version string, Neon's pooled connection, and real model quality (the semantic and hybrid benchmark has **not been run**; see `backend/evaluation/README.md`). Most likely first-deploy problems are listed below.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Browser shows "Cannot reach the ContribMatch backend" | `VITE_API_BASE_URL` not set before the build (redeploy after setting it), or `CORS_ORIGINS` on Render does not exactly match your Vercel URL |
| Browser console: CORS error | `CORS_ORIGINS` wrong or still the placeholder; preview URLs need `CORS_ORIGIN_REGEX` |
| `/api/health` says `database: unavailable`, or API returns 503 `service_unavailable` / `database_unavailable` | wrong or expired `DATABASE_URL`; use the pooled string from Neon; check Render logs (they never print the URL) |
| Render build fails on `torch` | the PyTorch CPU index may not have a wheel for your `PYTHON_VERSION`; keep 3.12.x |
| Render rejects `PYTHON_VERSION` | use another 3.12.x patch version Render lists |
| Service restarts / "out of memory" during the first recommendation | instance too small; use Standard or larger |
| `POST /api/recommendations` returns 503 about the model | the model could not be downloaded or loaded; check the build log for the prefetch warning and Render's outbound network |
| 429 `rate_limited` | GitHub limits reached; make sure `GITHUB_TOKEN` is set on Render |
| Pages other than `/` give 404 on Vercel | `vercel.json` rewrite missing; make sure Root Directory is `frontend` |
| Build fails with "Refusing to build: VITE_…" | a secret-looking variable was added in Vercel; remove it (secrets belong on Render only) |

---
## Diagnosing a failing first recommendation request (diagnostic logging)

The backend logs every stage of `POST /api/recommendations` under the logger name **`app.diag`**, tagged `[req=xxxxxx]` so one request can be followed
through the log. In Render's **Logs** tab, search for `app.diag`. This needs `LOG_LEVEL=INFO` (the default in `render.yaml`). Nothing here changes behaviour,
scoring or the API, and `PRELOAD_MODEL` stays `false`.

**At startup** (one block per boot; a free instance boots again after every sleep):
- `startup: python=… cpu_limit=0.10 cpus memory_limit=512MB …` shows what the container really has. Fields read `none` or `n/a` if Render does not expose them.
- `startup: preload_model=False | model cache: dir=… verdict=READY | NOT FOUND | INCOMPLETE` says whether the model files are already on disk **at the path the app will read**
  (`NOT FOUND` means the first request has to download ~90 MB; compare with the build log line `Model files are in …` or `WARNING: could not prefetch`).
- `startup complete: the model is NOT loaded yet …`

**Per request**, in order: `recommendation request: START` → `github issue discovery: START/DONE` → `Loading embedding model` → `model cache: …` →
`model import (sentence_transformers + PyTorch): START/DONE` → `libraries: … torch_threads=N` → `model load (weights + tokenizer): START/DONE` → `Embedding model ready` →
`embedding generation: START/DONE` → `ranking …: DONE` → `database storage: START/DONE` → `recommendation request: DONE`.
Each line ends with `rss=` (this process now), `peak_rss=` (highest so far), `container=used/limit` (whole container, includes reclaimable file cache),
`oom_kills=` (kills the kernel counted for this container), `proc_cpu=` (CPU seconds used by the process) and `throttled=N x/S s` (how often and how long the CPU limit paused it).
DONE lines also show `in <wall seconds> (cpu <cpu seconds>)`. While the import, load or encoding runs, a `still running after N s | rss=…` line is logged every 3 to 5 seconds.

| What you see | What it means |
|---|---|
| `still running` lines show `rss`/`peak_rss` climbing toward the limit, then **no more lines**; the next lines are a new `startup:` block **without** a `shutdown:` line before it; Render **Events** says "Ran out of memory" | memory exhaustion (the process was killed with SIGKILL, which cannot be logged). `peak_rss` on the last line shows how far it got |
| a `shutdown: active stages=model import … [req=…]` line, then a new `startup:` block; Events says "Health check failed", a deploy, or a restart | Render **stopped** the instance (SIGTERM); not an out-of-memory kill |
| `still running` lines keep coming, `rss` is flat and well below the limit, wall time grows much faster than `(cpu …)`, `throttled=` keeps rising | the process is alive but **starved of CPU** (0.1 CPU): the request is just slow, and may outlive the browser's wait. The backend keeps working after the browser gives up |
| `model cache … verdict=NOT FOUND` or `INCOMPLETE`, and `model load` takes long with a small `(cpu …)` | the model is being **downloaded** (network/disk wait), so the build-time prefetch did not land where the app reads |
| `Embedding model load FAILED … full traceback follows` | a real error with its cause in the traceback (the API then answers 503 `service_unavailable`) |
| everything through `ranking …: DONE`, then `database storage: FAILED` | a database problem, not the model |
| `recommendation request: FAILED … (CancelledError)` | the request was cancelled while still in the async part (client went away) |

Also check in the Render dashboard: **Events** (out of memory, health-check failures, restarts), **Metrics** (memory against the 512 MB line, CPU), and in the browser's
Network tab the status and how long the POST ran before failing. A proxy-generated 502/504 has no CORS headers, so the browser reports it as "Cannot reach the backend".
