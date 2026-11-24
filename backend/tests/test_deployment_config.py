"""Static checks of the deployment files (Render, Vercel, env examples). They cannot prove a deployment works,
only that the files are consistent with each other and with the application code."""
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
SECRET_VALUE = re.compile(r"(ghp_|gho_|github_pat_|postgres(ql)?://[^/\s:]+:(?!PASSWORD)[^@\s]+@)", re.I)


@pytest.fixture(scope="module")
def render():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((ROOT / "render.yaml").read_text())["services"][0]


def test_render_service_basics(render):
    assert render["type"] == "web" and render["runtime"] == "python" and render["rootDir"] == "backend"
    assert render["autoDeploy"] is False
    assert render["healthCheckPath"] == "/api/health/live"


def test_render_start_command_binds_render_port_on_all_interfaces(render):
    cmd = render["startCommand"]
    assert cmd.startswith("uvicorn app.main:app")
    assert "--host 0.0.0.0" in cmd and "--port $PORT" in cmd and "--reload" not in cmd and "--workers" not in cmd


def test_render_build_command(render):
    steps = [s.strip() for s in render["buildCommand"].split("&&")]
    assert steps[1].startswith("pip install torch --index-url https://download.pytorch.org/whl/cpu")
    assert steps.index("pip install -r requirements.txt") > 1             # CPU torch first, then the rest
    assert steps[-1] == "python scripts/prefetch_model.py"
    assert (BACKEND / "scripts" / "prefetch_model.py").exists()


def test_render_env_is_safe_and_matches_application_settings(render):
    env = {e["key"]: e for e in render["envVars"]}
    assert env["PYTHON_VERSION"]["value"].startswith("3.12.")
    assert env["PRELOAD_MODEL"]["value"] == "false" and env["ENVIRONMENT"]["value"] == "production"
    assert env["DEBUG"]["value"] == "false"
    for secret in ("DATABASE_URL", "GITHUB_TOKEN"):
        assert env[secret].get("sync") is False and "value" not in env[secret]
    assert "CORS_ORIGINS" in env
    # every variable is one the app reads (or Render itself reads)
    known = {n.upper() for n in Settings.model_fields} | {"PYTHON_VERSION"}
    assert set(env) <= known, set(env) - known
    for e in env.values():
        assert not SECRET_VALUE.search(str(e.get("value", "")))


def test_render_config_agrees_with_the_defaults_in_code():
    assert Settings(_env_file=None).preload_model is False                     # lazy loading is the default
    assert (BACKEND / ".python-version").read_text().strip().startswith("3.12.")


def test_postgres_driver_is_a_runtime_dependency():
    req = (BACKEND / "requirements.txt").read_text()
    assert re.search(r"^psycopg\[binary\]>=3", req, re.M) and "psycopg2" not in req
    assert "pytest" not in req                                                  # test tools stay out of production


def test_vercel_config():
    v = json.loads((FRONTEND / "vercel.json").read_text())
    assert v["outputDirectory"] == "dist" and v["buildCommand"] == "npm run build" and v["installCommand"] == "npm ci"
    assert {"source": "/(.*)", "destination": "/index.html"} in v["rewrites"]       # React Router deep links
    text = json.dumps(v)
    assert "onrender.com" not in text and not SECRET_VALUE.search(text)               # backend URL comes from the env var
    pkg = json.loads((FRONTEND / "package.json").read_text())
    assert pkg["scripts"]["build"] == "tsc -b && vite build" and pkg["engines"]["node"] == "22.x"


def test_env_examples_contain_no_real_secrets():
    be = (BACKEND / ".env.example").read_text()
    assert re.search(r"^DATABASE_URL=sqlite:///", be, re.M)                    # local default is preserved
    assert not SECRET_VALUE.search(be)
    fe = (FRONTEND / ".env.example").read_text()
    names = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", fe, re.M))
    assert names == {"VITE_API_BASE_URL"}
    assert not re.search(r"TOKEN|SECRET|PASSWORD|DATABASE", fe.split("VITE_API_BASE_URL")[-1])


def test_no_env_files_are_shipped():
    found = [p for p in ROOT.rglob(".env") if "node_modules" not in p.parts and ".git" not in p.parts]
    assert found == []


def test_frontend_source_does_not_read_backend_secrets():
    files = [p for p in (FRONTEND / "src").rglob("*.ts*") if "test" not in p.parts]
    src = "\n".join(p.read_text() for p in files)
    # the only environment variables the browser code may read are the public build-time ones
    used = set(re.findall(r"import\.meta\.env\.([A-Za-z_]+)", src))
    assert used <= {"VITE_API_BASE_URL", "PROD", "DEV", "MODE", "BASE_URL", "SSR"}, used
    assert "process.env" not in src
    # the words appear only in a user-facing hint telling the operator what to configure on the backend
    mentions = {p.name for p in files if re.search(r"GITHUB_TOKEN|DATABASE_URL", p.read_text())}
    assert mentions <= {"errors.ts"}, mentions


# ------------------------------------------------------------------ prefetch script
def _load_prefetch():
    spec = importlib.util.spec_from_file_location("prefetch_model", BACKEND / "scripts" / "prefetch_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prefetch_downloads_only_the_files_needed(monkeypatch, tmp_path):
    seen = {}
    fake = types.ModuleType("huggingface_hub")
    fake.snapshot_download = lambda **kw: seen.update(kw) or str(tmp_path / "snap")
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
    monkeypatch.setenv("MODEL_CACHE_DIR", ".model_cache")
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        assert _load_prefetch().main([]) == 0
    finally:
        get_settings.cache_clear()
    assert seen["repo_id"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert seen["cache_dir"] == str((BACKEND / ".model_cache").resolve())      # same folder the app will read
    assert "onnx/*" in seen["ignore_patterns"]


@pytest.mark.parametrize("args,code", [([], 0), (["--strict"], 1)])
def test_prefetch_failure_is_a_warning_unless_strict(monkeypatch, args, code, capsys):
    fake = types.ModuleType("huggingface_hub")

    def boom(**kw):
        raise OSError("no network")

    fake.snapshot_download = boom
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
    assert _load_prefetch().main(args) == code
    assert "WARNING" in capsys.readouterr().err
