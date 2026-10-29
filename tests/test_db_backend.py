from core.db import get_database_backend, get_database_url, is_deployed_environment
from core.memory import MemoryStore


def test_detects_sqlite_backend_by_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert get_database_backend() == "sqlite"
    assert get_database_url() == ""


def test_detects_postgres_backend_when_url_present(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    assert get_database_backend() == "postgresql"
    assert get_database_url().startswith("postgresql://")


def test_memory_store_exposes_backend_name(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    mem = MemoryStore(db_path=tmp_path / "memory.db")
    assert mem.backend == "sqlite"
    assert mem.backend_name in {"SQLite", "SQLite (local)"}


def test_deployed_environment_warning_logic(monkeypatch):
    monkeypatch.setenv("STREAMLIT_SERVER_HEADLESS", "true")
    assert is_deployed_environment() is True
