import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_DIR, Settings


def test_cors_list_parsing():
    s = Settings(cors_origins=" http://a.com , http://b.com ,", _env_file=None)
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]


def test_relative_sqlite_resolved_against_backend_dir():
    s = Settings(database_url="sqlite:///./data/x.db", _env_file=None)
    assert s.sqlalchemy_url == f"sqlite:///{(BACKEND_DIR / 'data/x.db').resolve()}"


def test_memory_sqlite_untouched():
    s = Settings(database_url="sqlite:///:memory:", _env_file=None)
    assert s.sqlalchemy_url == "sqlite:///:memory:"


def test_invalid_log_level():
    with pytest.raises(ValidationError):
        Settings(log_level="LOUD", _env_file=None)


def test_env_example_documents_every_setting():
    """Every configurable setting must appear in .env.example so deployers can discover it."""
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    documented = {line.split("=", 1)[0].strip().lstrip("# ").upper() for line in text.splitlines() if "=" in line}
    missing = [name for name in Settings.model_fields if name.upper() not in documented]
    assert not missing, f"undocumented in .env.example: {missing}"


def test_env_example_has_no_real_secrets():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    token_line = next(l for l in text.splitlines() if l.startswith("GITHUB_TOKEN="))
    assert token_line == "GITHUB_TOKEN="           # must stay empty in the example


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test")
    monkeypatch.setenv("GITHUB_TOKEN", "  tok  ")
    s = Settings(_env_file=None)
    assert s.cors_origin_list == ["http://a.test"] and s.github_token == "tok"
