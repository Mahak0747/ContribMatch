"""Stage timing and resource diagnostics for the recommendation pipeline.

Standard library only (no psutil), so it adds no dependency, and cheap enough for a 0.1-CPU instance: a snapshot
reads a few tiny files under /proc and /sys/fs/cgroup. Every reader returns "unavailable" instead of raising, so
diagnostics can never break a request.

All stage lines use the logger name ``app.diag`` and carry ``[req=<id>]`` so one request can be followed through
the log. Search the Render logs for ``app.diag``.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import platform
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger("app.diag")

# Set once per recommendation request. It propagates into the worker thread used for ranking and storage.
request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

PROC_STATUS = Path("/proc/self/status")
CGROUP_ROOT = Path("/sys/fs/cgroup")
MB = 1024 * 1024


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:6]
    request_id.set(rid)
    return rid


# ------------------------------------------------------------------------------------------ low-level readers
def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, ValueError):
        return None


def _int(text: str | None) -> int | None:
    try:
        return int(text.split()[0]) if text and text.split()[0] != "max" else None
    except (ValueError, IndexError):
        return None


def _limit_mb(text: str | None) -> float | None:
    """Memory limit in MB, or None for 'unlimited' (cgroup v2 prints 'max', v1 prints a huge sentinel)."""
    n = _int(text)
    return None if n is None or n >= 1 << 50 else n / MB


def _proc_mb(field: str) -> float | None:
    text = _read(PROC_STATUS)
    if text:
        for line in text.splitlines():
            if line.startswith(field + ":"):
                try:
                    return int(line.split()[1]) / 1024  # the file reports kB
                except (ValueError, IndexError):
                    return None
    return None


def _kv_lines(text: str | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in (text or "").splitlines():
        key, _, val = line.partition(" ")
        try:
            out[key] = int(val.strip())
        except ValueError:
            pass
    return out


def cgroup_memory() -> dict[str, float | int | None]:
    """Container (cgroup) memory: usage, limit, peak and the number of OOM kills the kernel recorded."""
    r = CGROUP_ROOT
    out: dict[str, float | int | None] = {"usage_mb": None, "limit_mb": None, "peak_mb": None, "oom_kills": None}
    cur = _int(_read(r / "memory.current"))
    if cur is not None:                                              # cgroup v2
        out["usage_mb"] = cur / MB
        out["limit_mb"] = _limit_mb(_read(r / "memory.max"))
        peak = _int(_read(r / "memory.peak"))
        out["peak_mb"] = peak / MB if peak is not None else None
        out["oom_kills"] = _kv_lines(_read(r / "memory.events")).get("oom_kill")
        return out
    v1 = r / "memory"                                                # cgroup v1
    use = _int(_read(v1 / "memory.usage_in_bytes"))
    if use is not None:
        out["usage_mb"] = use / MB
        out["limit_mb"] = _limit_mb(_read(v1 / "memory.limit_in_bytes"))
        peak = _int(_read(v1 / "memory.max_usage_in_bytes"))
        out["peak_mb"] = peak / MB if peak is not None else None
        out["oom_kills"] = _kv_lines(_read(v1 / "memory.oom_control")).get("oom_kill")
    return out


def cgroup_cpu() -> dict[str, float | int | None]:
    """CPU allowance (in CPUs, e.g. 0.1) and how often / how long the container was throttled."""
    r = CGROUP_ROOT
    out: dict[str, float | int | None] = {"cpus": None, "throttled_periods": None, "throttled_seconds": None}
    cpu_max = _read(r / "cpu.max")
    if cpu_max:                                                      # cgroup v2: "<quota> <period>" or "max <period>"
        parts = cpu_max.split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                out["cpus"] = int(parts[0]) / int(parts[1])
            except (ValueError, ZeroDivisionError):
                pass
        stat = _kv_lines(_read(r / "cpu.stat"))
        out["throttled_periods"] = stat.get("nr_throttled")
        if "throttled_usec" in stat:
            out["throttled_seconds"] = stat["throttled_usec"] / 1e6
        return out
    for v1 in (r / "cpu", r / "cpu,cpuacct"):                        # cgroup v1
        quota, period = _int(_read(v1 / "cpu.cfs_quota_us")), _int(_read(v1 / "cpu.cfs_period_us"))
        if quota is not None and period:
            if quota > 0:
                out["cpus"] = quota / period
            stat = _kv_lines(_read(v1 / "cpu.stat"))
            out["throttled_periods"] = stat.get("nr_throttled")
            if "throttled_time" in stat:
                out["throttled_seconds"] = stat["throttled_time"] / 1e9
            return out
    return out


# ------------------------------------------------------------------------------------------------- summaries
def _mb(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0f}MB"


def snapshot() -> str:
    """One compact line: process memory, container memory vs limit, OOM kills, CPU used and CPU throttling."""
    try:
        parts = [f"rss={_mb(_proc_mb('VmRSS'))}", f"peak_rss={_mb(_proc_mb('VmHWM'))}"]
        mem = cgroup_memory()
        if mem["usage_mb"] is not None:
            parts.append(f"container={_mb(mem['usage_mb'])}/{_mb(mem['limit_mb']) if mem['limit_mb'] else 'no-limit'}")
        if mem["oom_kills"] is not None:
            parts.append(f"oom_kills={mem['oom_kills']}")
        parts.append(f"proc_cpu={time.process_time():.1f}s")
        cpu = cgroup_cpu()
        if cpu["throttled_periods"] is not None:
            secs = cpu["throttled_seconds"]
            parts.append(f"throttled={cpu['throttled_periods']}x" + (f"/{secs:.1f}s" if secs is not None else ""))
        return " ".join(parts)
    except Exception:  # noqa: BLE001 - diagnostics must never break a request
        return "resources unavailable"


def describe_runtime() -> str:
    try:
        mem, cpu = cgroup_memory(), cgroup_cpu()
        affinity = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
        return (f"python={platform.python_version()} pid={os.getpid()} cpu_count={os.cpu_count()} "
                f"usable_cpus={affinity} cpu_limit={'%.2f cpus' % cpu['cpus'] if cpu['cpus'] else 'none'} "
                f"memory_limit={_mb(mem['limit_mb']) if mem['limit_mb'] else 'none/unknown'} | {snapshot()}")
    except Exception:  # noqa: BLE001
        return "runtime details unavailable"


def describe_ml_libraries() -> str:
    """Versions and PyTorch thread count, read from already-imported modules (imports nothing itself)."""
    def ver(name: str) -> str:
        mod = sys.modules.get(name)
        return "not-imported" if mod is None else str(getattr(mod, "__version__", "?"))

    threads = "n/a"
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            threads = str(torch.get_num_threads())
        except Exception:  # noqa: BLE001
            pass
    return (f"libraries: sentence_transformers={ver('sentence_transformers')} transformers={ver('transformers')} "
            f"torch={ver('torch')} torch_threads={threads}")


# ---------------------------------------------------------------------------------------------- model cache
CACHE_FILES = ("modules.json", "config.json", "tokenizer.json", "tokenizer_config.json",
               "sentence_bert_config.json", "1_Pooling/config.json")
WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")


def hub_cache_dir(cache_folder: str | None) -> Path:
    """Where sentence-transformers / huggingface_hub look for model files for this configuration."""
    if cache_folder:
        return Path(cache_folder)
    env = os.environ
    for var in ("SENTENCE_TRANSFORMERS_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if env.get(var):
            return Path(env[var])
    if env.get("HF_HOME"):
        return Path(env["HF_HOME"]) / "hub"
    base = Path(env["XDG_CACHE_HOME"]) if env.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    return base / "huggingface" / "hub"


def describe_model_cache(model_name: str, cache_folder: str | None) -> str:
    """Are the model files already on disk? Looks only at files; loads and downloads nothing."""
    try:
        cache = hub_cache_dir(cache_folder)
        repo = cache / ("models--" + model_name.replace("/", "--"))
        head = f"model cache: dir={cache} (configured={'MODEL_CACHE_DIR' if cache_folder else 'library default'})"
        if not cache.exists():
            return f"{head} | cache dir does not exist | verdict=NOT FOUND: the first request would have to download the model"
        if not repo.exists():
            return f"{head} | {repo.name} missing | verdict=NOT FOUND: the first request would have to download the model"

        ref = _read(repo / "refs" / "main")
        snapshots = repo / "snapshots"
        snap = snapshots / ref.strip() if ref and (snapshots / ref.strip()).is_dir() else None
        if snap is None and snapshots.is_dir():
            dirs = sorted(p for p in snapshots.iterdir() if p.is_dir())
            snap = dirs[0] if dirs else None
        if snap is None:
            return f"{head} | no snapshot folder | verdict=INCOMPLETE: the model would be downloaded again"

        missing = [f for f in CACHE_FILES if not (snap / f).exists()]          # exists() is False for broken links
        weights = [f for f in WEIGHT_FILES if (snap / f).exists()]
        if not weights:
            missing.append("model.safetensors|pytorch_model.bin")
        w_mb = (snap / weights[0]).stat().st_size / MB if weights else 0
        blobs = repo / "blobs"
        total = sum(p.stat().st_size for p in blobs.iterdir() if p.is_file()) / MB if blobs.is_dir() else 0
        verdict = ("READY: files are on disk (the load should not download model weights)" if not missing
                   else f"INCOMPLETE: missing {missing}")
        return (f"{head} | snapshot={snap.name[:8]} weights={weights[0] + f' ({w_mb:.0f}MB)' if weights else 'MISSING'} "
                f"files_ok={len(CACHE_FILES) - len([m for m in missing if m in CACHE_FILES])}/{len(CACHE_FILES)} "
                f"cache_size={total:.0f}MB | verdict={verdict}")
    except Exception as exc:  # noqa: BLE001
        return f"model cache: could not inspect ({type(exc).__name__})"


# --------------------------------------------------------------------------------------------------- stages
_ACTIVE: dict[object, tuple[str, str, float]] = {}
_ACTIVE_LOCK = threading.Lock()


def active_stages() -> list[str]:
    """Stages that are running right now (used by the shutdown log to show what was interrupted)."""
    now = time.perf_counter()
    with _ACTIVE_LOCK:
        return [f"{name} [req={rid}] running {now - t0:.1f}s" for name, rid, t0 in _ACTIVE.values()]


def _kv(info: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in info.items())


def _heartbeat(name: str, rid: str, t0: float, stop: threading.Event, every: float) -> None:
    """While a long stage runs, log memory every few seconds. If the process is killed, the last line shows how far
    memory had grown; if the lines keep coming, the process is alive and the stage is simply slow."""
    while not stop.wait(every):
        logger.info("[req=%s] %s: still running after %.1fs | %s", rid, name, time.perf_counter() - t0, snapshot())


@contextlib.contextmanager
def stage(name: str, *, heartbeat: float | None = None, **info) -> Iterator[dict]:
    """Log START and DONE/FAILED for a pipeline stage with wall time, CPU time and a resource snapshot.

    Yields a dict; entries added to it are appended to the DONE line. Only the exception TYPE is logged on
    failure (messages can contain connection details); callers that want a traceback log it themselves.
    """
    rid = request_id.get()
    result: dict = {}
    t0, c0 = time.perf_counter(), time.process_time()
    key = object()
    with _ACTIVE_LOCK:
        _ACTIVE[key] = (name, rid, t0)
    logger.info("[req=%s] %s: START %s| %s", rid, name, _kv(info) + " " if info else "", snapshot())
    stop = threading.Event()
    if heartbeat:
        threading.Thread(target=_heartbeat, args=(name, rid, t0, stop, heartbeat), daemon=True,
                         name="diag-heartbeat").start()
    try:
        yield result
    except BaseException as exc:
        logger.error("[req=%s] %s: FAILED after %.2fs (%s) | %s", rid, name, time.perf_counter() - t0,
                     type(exc).__name__, snapshot())
        raise
    else:
        extra = _kv({**info, **result})
        logger.info("[req=%s] %s: DONE in %.2fs (cpu %.2fs) %s| %s", rid, name, time.perf_counter() - t0,
                    time.process_time() - c0, extra + " " if extra else "", snapshot())
    finally:
        stop.set()
        with _ACTIVE_LOCK:
            _ACTIVE.pop(key, None)
