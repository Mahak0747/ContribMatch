"""Diagnostics added to find out why the first recommendation request fails on a small Render instance.
They verify the logging only; behaviour, scoring and API contracts are covered by the existing tests."""
import asyncio
import logging
import re
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.concurrency import run_in_threadpool
from fastapi.testclient import TestClient

from app.ml import diagnostics as d
from app.ml.embedder import EmbeddingModelError, SentenceTransformerEmbedder, get_embedder
from tests.github_mock import make_item

MB = 1024 * 1024
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def diag_messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "app.diag"]


def index_of(messages, fragment, start=0):
    for i in range(start, len(messages)):
        if fragment in messages[i]:
            return i
    raise AssertionError(f"{fragment!r} not found after position {start} in:\n" + "\n".join(messages))


# ------------------------------------------------------------------------------- resource readers
def write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_cgroup_v2_memory_cpu_and_oom_counter(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "CGROUP_ROOT", tmp_path)
    write(tmp_path, "memory.current", str(400 * MB))
    write(tmp_path, "memory.max", str(512 * MB))
    write(tmp_path, "memory.peak", str(480 * MB))
    write(tmp_path, "memory.events", "low 0\nhigh 0\nmax 3\noom 2\noom_kill 2\n")
    write(tmp_path, "cpu.max", "10000 100000")
    write(tmp_path, "cpu.stat", "usage_usec 5\nnr_periods 900\nnr_throttled 130\nthrottled_usec 44200000\n")
    mem, cpu = d.cgroup_memory(), d.cgroup_cpu()
    assert (mem["usage_mb"], mem["limit_mb"], mem["peak_mb"], mem["oom_kills"]) == (400, 512, 480, 2)
    assert cpu["cpus"] == pytest.approx(0.1) and cpu["throttled_periods"] == 130 and cpu["throttled_seconds"] == pytest.approx(44.2)
    snap = d.snapshot()
    assert "container=400MB/512MB" in snap and "oom_kills=2" in snap and "throttled=130x/44.2s" in snap


def test_cgroup_v2_unlimited_values(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "CGROUP_ROOT", tmp_path)
    write(tmp_path, "memory.current", str(100 * MB))
    write(tmp_path, "memory.max", "max")
    write(tmp_path, "cpu.max", "max 100000")
    assert d.cgroup_memory()["limit_mb"] is None and d.cgroup_cpu()["cpus"] is None
    assert "no-limit" in d.snapshot()


def test_cgroup_v1_and_unlimited_sentinel(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "CGROUP_ROOT", tmp_path)
    write(tmp_path, "memory/memory.usage_in_bytes", str(300 * MB))
    write(tmp_path, "memory/memory.limit_in_bytes", str(512 * MB))
    write(tmp_path, "memory/memory.max_usage_in_bytes", str(350 * MB))
    write(tmp_path, "cpu/cpu.cfs_quota_us", "10000")
    write(tmp_path, "cpu/cpu.cfs_period_us", "100000")
    write(tmp_path, "cpu/cpu.stat", "nr_periods 10\nnr_throttled 4\nthrottled_time 2000000000\n")
    assert d.cgroup_memory()["limit_mb"] == 512 and d.cgroup_memory()["peak_mb"] == 350
    assert d.cgroup_cpu()["cpus"] == pytest.approx(0.1) and d.cgroup_cpu()["throttled_seconds"] == pytest.approx(2.0)
    write(tmp_path, "memory/memory.limit_in_bytes", "9223372036854771712")           # "no limit" in v1
    assert d.cgroup_memory()["limit_mb"] is None


def test_process_memory_from_proc_status(tmp_path, monkeypatch):
    status = tmp_path / "status"
    status.write_text("Name:\tpython\nVmHWM:\t  204800 kB\nVmRSS:\t  102400 kB\n")
    monkeypatch.setattr(d, "PROC_STATUS", status)
    monkeypatch.setattr(d, "CGROUP_ROOT", tmp_path / "nothing")
    assert d.snapshot().startswith("rss=100MB peak_rss=200MB")


def test_snapshot_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "PROC_STATUS", tmp_path / "missing")
    monkeypatch.setattr(d, "CGROUP_ROOT", tmp_path / "missing")
    assert "rss=n/a" in d.snapshot() and d.describe_runtime()
    monkeypatch.setattr(d, "cgroup_memory", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert d.snapshot() == "resources unavailable"


def test_diagnostics_module_uses_only_the_standard_library():
    tree_imports = set(re.findall(r"^(?:from|import) ([a-z_]+)", Path(d.__file__).read_text(), re.M))
    assert tree_imports <= set(sys.stdlib_module_names) | {"__future__"}, tree_imports


# ------------------------------------------------------------------------------------- stages
def test_stage_logs_start_done_with_timing_cpu_and_memory(caplog):
    caplog.set_level(logging.INFO)
    rid = d.new_request_id()
    with d.stage("demo", items=3) as done:
        done["found"] = 2
    msgs = diag_messages(caplog)
    assert re.fullmatch(r"[0-9a-f]{6}", rid)
    assert msgs[0].startswith(f"[req={rid}] demo: START items=3 | rss=")
    assert re.search(rf"\[req={rid}\] demo: DONE in \d+\.\d\ds \(cpu \d+\.\d\ds\) items=3 found=2 \| rss=", msgs[1])


def test_stage_failure_logs_only_the_exception_type_and_reraises(caplog):
    caplog.set_level(logging.INFO)
    with pytest.raises(ValueError):
        with d.stage("risky"):
            raise ValueError("password=hunter2 host=ep-x.neon.tech")
    failed = [m for m in diag_messages(caplog) if "FAILED" in m]
    assert len(failed) == 1 and "(ValueError)" in failed[0] and "hunter2" not in failed[0] and "neon" not in failed[0]


def test_heartbeat_reports_while_running_and_stops_afterwards(caplog):
    caplog.set_level(logging.INFO)
    with d.stage("slow", heartbeat=0.05):
        time.sleep(0.3)
    beats = [m for m in diag_messages(caplog) if "still running" in m]
    assert len(beats) >= 2 and all("rss=" in m for m in beats)
    time.sleep(0.2)
    assert len([m for m in diag_messages(caplog) if "still running" in m]) == len(beats)       # thread stopped


def test_active_stages_are_tracked_for_the_shutdown_log():
    assert d.active_stages() == []
    with d.stage("long operation"):
        active = d.active_stages()
        assert len(active) == 1 and active[0].startswith("long operation [req=")
    assert d.active_stages() == []


def test_request_id_reaches_the_worker_thread_used_for_ranking_and_storage():
    async def main():
        d.request_id.set("abc123")
        return await run_in_threadpool(d.request_id.get)
    assert asyncio.run(main()) == "abc123"


# ------------------------------------------------------------------------------------ model cache
def make_cache(root: Path, *, weights=True, skip=(), model=MODEL) -> Path:
    repo = root / ("models--" + model.replace("/", "--"))
    snap = repo / "snapshots" / "abcdef1234567890"
    (repo / "refs").mkdir(parents=True)
    (repo / "refs" / "main").write_text("abcdef1234567890")
    (repo / "blobs").mkdir()
    for f in d.CACHE_FILES:
        if f not in skip:
            write(snap, f, "{}")
    if weights:
        (snap).mkdir(parents=True, exist_ok=True)
        (repo / "blobs" / "w").write_bytes(b"\0" * (2 * MB))
        (snap / "model.safetensors").write_bytes(b"\0" * (2 * MB))
    return root


def test_cache_ready(tmp_path):
    make_cache(tmp_path)
    msg = d.describe_model_cache(MODEL, str(tmp_path))
    assert "verdict=READY" in msg and "model.safetensors (2MB)" in msg and "files_ok=6/6" in msg and "snapshot=abcdef12" in msg


def test_cache_incomplete_lists_what_is_missing(tmp_path):
    make_cache(tmp_path, weights=False, skip=("tokenizer.json",))
    msg = d.describe_model_cache(MODEL, str(tmp_path))
    assert "verdict=INCOMPLETE" in msg and "tokenizer.json" in msg and "weights=MISSING" in msg


def test_cache_broken_symlink_counts_as_missing(tmp_path):
    make_cache(tmp_path)
    link = tmp_path / ("models--" + MODEL.replace("/", "--")) / "snapshots" / "abcdef1234567890" / "model.safetensors"
    link.unlink()
    try:
        link.symlink_to(tmp_path / "does-not-exist")
    except OSError:
        pytest.skip("symlinks not supported here")
    assert "weights=MISSING" in d.describe_model_cache(MODEL, str(tmp_path))


def test_cache_not_found(tmp_path):
    assert "cache dir does not exist" in d.describe_model_cache(MODEL, str(tmp_path / "nope"))
    assert "verdict=NOT FOUND" in d.describe_model_cache(MODEL, str(tmp_path))                  # empty dir: repo missing


def test_cache_dir_resolution_order(tmp_path, monkeypatch):
    for var in ("SENTENCE_TRANSFORMERS_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert d.hub_cache_dir(None) == tmp_path / ".cache" / "huggingface" / "hub"
    monkeypatch.setenv("HF_HOME", "/hf")
    assert d.hub_cache_dir(None) == Path("/hf/hub")
    monkeypatch.setenv("HF_HUB_CACHE", "/hub")
    assert d.hub_cache_dir(None) == Path("/hub")
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", "/st")
    assert d.hub_cache_dir(None) == Path("/st")
    assert d.hub_cache_dir("/configured") == Path("/configured")                                # explicit setting wins


# ------------------------------------------------------------------------------- embedder logging
class FakeST:
    def __init__(self, name, **kw):
        self.name = name

    def encode(self, texts, **kw):
        import numpy as np
        return np.ones((len(texts), 3), dtype="float32")


@pytest.fixture()
def fake_sentence_transformers(monkeypatch):
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer, mod.__version__ = FakeST, "9.9.9"
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)


def test_first_embedding_logs_cache_import_load_and_encode_in_order(fake_sentence_transformers, caplog, tmp_path):
    make_cache(tmp_path)
    caplog.set_level(logging.INFO)
    e = SentenceTransformerEmbedder(MODEL, cache_folder=str(tmp_path))
    e.embed(["a", "b"])
    msgs = [r.getMessage() for r in caplog.records]
    i = index_of(msgs, f"Loading embedding model {MODEL}")                       # the original line is unchanged
    i = index_of(msgs, "model cache: dir=" + str(tmp_path), i)
    assert "verdict=READY" in msgs[i]
    i = index_of(msgs, "model import (sentence_transformers + PyTorch): START", i)
    i = index_of(msgs, "model import (sentence_transformers + PyTorch): DONE", i)
    i = index_of(msgs, "libraries: sentence_transformers=9.9.9", i)
    i = index_of(msgs, "model load (weights + tokenizer): START", i)
    i = index_of(msgs, "model load (weights + tokenizer): DONE", i)
    i = index_of(msgs, "Embedding model ready", i)
    i = index_of(msgs, "embedding generation: START texts=2 already_cached=0 batch_size=32", i)
    index_of(msgs, "embedding generation: DONE", i)


def test_cached_embeddings_do_not_reload_or_log_stages_again(fake_sentence_transformers, caplog):
    e = SentenceTransformerEmbedder(MODEL)
    e.embed(["a"])
    caplog.clear()
    caplog.set_level(logging.INFO)
    e.embed(["a"])
    assert [r for r in caplog.records if r.name == "app.diag"] == [] and e.load_count == 1


def test_load_failure_logs_the_full_traceback(monkeypatch, caplog):
    class Boom:
        def __init__(self, name, **kw):
            raise RuntimeError("weights file is corrupt: boom-detail")

    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = Boom
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)
    caplog.set_level(logging.INFO)
    with pytest.raises(EmbeddingModelError):
        SentenceTransformerEmbedder(MODEL).embed(["a"])
    err = [r for r in caplog.records if r.name == "app.ml.embedder" and r.levelno == logging.ERROR]
    assert len(err) == 1 and err[0].exc_info is not None
    assert "Traceback (most recent call last)" in caplog.text and "RuntimeError: weights file is corrupt: boom-detail" in caplog.text
    stage_failed = [m for m in diag_messages(caplog) if "model load" in m and "FAILED" in m]
    assert len(stage_failed) == 1 and "(RuntimeError)" in stage_failed[0] and "boom-detail" not in stage_failed[0]


def test_import_failure_is_logged_with_traceback_too(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)             # makes "import" raise ImportError
    caplog.set_level(logging.INFO)
    with pytest.raises(EmbeddingModelError):
        SentenceTransformerEmbedder(MODEL).embed(["a"])
    assert "ModuleNotFoundError" in caplog.text and "model import (sentence_transformers + PyTorch): FAILED" in caplog.text


def test_a_second_request_logs_that_it_is_waiting_for_the_load(fake_sentence_transformers, caplog):
    caplog.set_level(logging.INFO)
    e = SentenceTransformerEmbedder(MODEL)
    e._lock.acquire()                                       # pretend another request is loading right now
    t = threading.Thread(target=e._load)
    t.start()
    time.sleep(0.2)
    e._lock.release()
    t.join(5)
    assert any("another request is already loading the model" in r.getMessage() for r in caplog.records)
    assert e.load_count == 1


# --------------------------------------------------------------------------- end to end (fake GitHub)
PROFILE = {"profile": {"skills": ["Python"], "preferred_languages": ["Python"], "experience_level": "beginner"}}


def test_every_pipeline_stage_is_logged_in_order_under_one_request_id(api, caplog):
    caplog.set_level(logging.INFO)
    api.fake.items = [make_item(1, "octo/alpha", body="Python tests"), make_item(2, "octo/beta", body="docs")]
    r = api.client.post("/api/recommendations", json=PROFILE)
    assert r.status_code == 201 and len(r.json()["recommendations"]) == 2                  # behaviour unchanged
    msgs = diag_messages(caplog)
    i = index_of(msgs, "recommendation request: START")
    i = index_of(msgs, "github issue discovery: START", i)
    i = index_of(msgs, "github issue discovery: DONE", i)
    assert "issues=2" in msgs[i] and "searches_ok=" in msgs[i]
    i = index_of(msgs, "ranking (embeddings + scoring + explanations): START", i)
    i = index_of(msgs, "ranking (embeddings + scoring + explanations): DONE", i)
    assert "recommendations=2" in msgs[i]
    i = index_of(msgs, "database storage: START", i)
    i = index_of(msgs, "database storage: DONE", i)
    i = index_of(msgs, "recommendation request: DONE", i)
    assert "run_id=" in msgs[i] and "recommendations=2" in msgs[i]
    ids = {m for msg in msgs for m in re.findall(r"\[req=([0-9a-f]{6})\]", msg)}
    assert len(ids) == 1, f"stages logged under different request ids: {ids}"             # incl. the worker thread
    assert all("rss=" in m for m in msgs if "DONE" in m or "START" in m)


def test_two_requests_get_different_ids(api, caplog):
    caplog.set_level(logging.INFO)
    api.fake.items = [make_item(1, "octo/alpha")]
    for _ in range(2):
        assert api.client.post("/api/recommendations", json=PROFILE).status_code == 201
    starts = [m for m in diag_messages(caplog) if "recommendation request: START" in m]
    assert len(starts) == 2 and len({re.search(r"req=(\w+)", m).group(1) for m in starts}) == 2


def test_model_failure_is_visible_in_the_stage_log_and_the_api_still_returns_503(api, caplog):
    from app.api.deps import get_engine
    from app.main import app
    from app.ml.engine import RecommendationEngine

    class NoModel:
        model_name = "x"

        def embed(self, texts):
            raise EmbeddingModelError("no model")

    app.dependency_overrides[get_engine] = lambda: RecommendationEngine(NoModel())
    caplog.set_level(logging.INFO)
    r = api.client.post("/api/recommendations", json=PROFILE)
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_unavailable"
    msgs = diag_messages(caplog)
    index_of(msgs, "ranking (embeddings + scoring + explanations): FAILED")
    index_of(msgs, "recommendation request: FAILED")
    assert "(EmbeddingModelError)" in " ".join(msgs)


def test_github_failure_is_visible_as_a_failed_request(api, caplog):
    caplog.set_level(logging.INFO)
    api.fake.search_status, api.fake.search_headers = 429, {"retry-after": "30"}
    assert api.client.post("/api/recommendations", json=PROFILE).status_code == 429
    msgs = diag_messages(caplog)
    index_of(msgs, "github issue discovery: FAILED")
    assert "(RateLimitError)" in " ".join(m for m in msgs if "request: FAILED" in m)


# ------------------------------------------------------------------------------ startup / shutdown
def test_startup_logs_runtime_and_cache_status_without_loading_the_model(caplog):
    from app.main import app
    caplog.set_level(logging.INFO)
    with TestClient(app):
        assert get_embedder()._model is None                                              # still lazy
        assert get_embedder().load_count == 0
    msgs = diag_messages(caplog)
    i = index_of(msgs, "startup: python=")
    assert "cpu_limit=" in msgs[i] and "memory_limit=" in msgs[i] and "rss=" in msgs[i]
    i = index_of(msgs, "startup: preload_model=False | model cache:", i)
    i = index_of(msgs, "startup complete: the model is NOT loaded yet", i)
    index_of(msgs, "shutdown: active stages=none", i)


def test_preload_model_still_defaults_to_false():
    from app.core.config import Settings
    assert Settings(_env_file=None).preload_model is False
