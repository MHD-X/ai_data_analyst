from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency in local SQLite mode
    psycopg = None

from config import CONFIG, get_setting

POSTGRES_SCHEMES = (
    "postgresql://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
    "postgres://",
)


def get_database_url() -> str:
    """Return the configured database URL for cloud Postgres, if present."""
    for key in ("DATABASE_URL", "TEST_DATABASE_URL"):
        value = (os.getenv(key) or get_setting(key, "") or "").strip()
        if value:
            return value
    return ""


def get_database_backend(database_url: str | None = None) -> str:
    """Return the active backend name: 'postgresql' or 'sqlite'."""
    url = (database_url or get_database_url() or "").strip()
    if url and url.startswith(POSTGRES_SCHEMES):
        return "postgresql"
    return "sqlite"


def get_backend_name(database_url: str | None = None) -> str:
    """Human-readable backend label used in the UI."""
    backend = get_database_backend(database_url)
    if backend == "postgresql":
        return "PostgreSQL (Neon)"
    return "SQLite"


def is_deployed_environment() -> bool:
    """True when the app is likely running in a hosted environment."""
    return any(
        os.getenv(name)
        for name in (
            "STREAMLIT_SERVER_HEADLESS",
            "STREAMLIT_SHARING",
            "STREAMLIT_APP_MODE",
            "APP_ENV",
            "WEBSITE_HOSTNAME",
            "VERCEL",
            "RENDER",
            "HEROKU_APP_NAME",
            "KUBERNETES_SERVICE_HOST",
        )
    )


def get_schema_sql(backend: str | None = None) -> str:
    backend = (backend or get_database_backend()).lower()
    if backend == "postgresql":
        return """
        CREATE TABLE IF NOT EXISTS sessions (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS datasets (
            id BIGSERIAL PRIMARY KEY,
            session_id BIGINT,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            file_path TEXT,
            rows INTEGER DEFAULT 0,
            cols INTEGER DEFAULT 0,
            columns_info TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_datasets_hash ON datasets(file_hash);
        CREATE INDEX IF NOT EXISTS idx_datasets_session ON datasets(session_id);

        CREATE TABLE IF NOT EXISTS operations (
            id BIGSERIAL PRIMARY KEY,
            dataset_id BIGINT,
            session_id BIGINT,
            user_request TEXT NOT NULL,
            generated_code TEXT,
            result_summary TEXT,
            success INTEGER DEFAULT 0,
            execution_time REAL DEFAULT 0,
            error TEXT,
            error_type TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_operations_dataset ON operations(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_operations_success ON operations(success);
        CREATE INDEX IF NOT EXISTS idx_operations_created ON operations(created_at);

        CREATE TABLE IF NOT EXISTS feedback (
            id BIGSERIAL PRIMARY KEY,
            operation_id BIGINT NOT NULL,
            rating INTEGER CHECK (rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_feedback_operation ON feedback(operation_id);
        """

    return """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        metadata TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        filename TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        file_path TEXT,
        rows INTEGER DEFAULT 0,
        cols INTEGER DEFAULT 0,
        columns_info TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_datasets_hash ON datasets(file_hash);
    CREATE INDEX IF NOT EXISTS idx_datasets_session ON datasets(session_id);

    CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER,
        session_id INTEGER,
        user_request TEXT NOT NULL,
        generated_code TEXT,
        result_summary TEXT,
        success INTEGER DEFAULT 0,
        execution_time REAL DEFAULT 0,
        error TEXT,
        error_type TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_operations_dataset ON operations(dataset_id);
    CREATE INDEX IF NOT EXISTS idx_operations_success ON operations(success);
    CREATE INDEX IF NOT EXISTS idx_operations_created ON operations(created_at);

    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id INTEGER NOT NULL,
        rating INTEGER CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_feedback_operation ON feedback(operation_id);
    """


def execute_sql_script(conn: Any, sql_text: str) -> None:
    backend = get_database_backend()
    if backend == "postgresql":
        statements = [part.strip() for part in sql_text.split(";") if part.strip()]
        for statement in statements:
            conn.execute(statement)
        return
    conn.executescript(sql_text)


def clear_all_sql(backend: str | None = None) -> str:
    backend = (backend or get_database_backend()).lower()
    if backend == "postgresql":
        return "TRUNCATE TABLE feedback, operations, datasets, sessions RESTART IDENTITY CASCADE;"
    return "DELETE FROM feedback; DELETE FROM operations; DELETE FROM datasets; DELETE FROM sessions; DELETE FROM sqlite_sequence;"


@contextmanager
def connect_database(
    db_path: str | Path | None = None,
    database_url: str | None = None,
) -> Iterator[Any]:
    backend = get_database_backend(database_url)

    if backend == "postgresql":
        url = (database_url or get_database_url() or "").strip()
        if not url:
            raise RuntimeError("DATABASE_URL is not configured.")
        if psycopg is None:
            raise RuntimeError("psycopg[binary]==3.2.3 is required for PostgreSQL support.")
        conn = psycopg.connect(url, autocommit=False)
        try:
            yield conn
        finally:
            conn.close()
        return

    path = Path(db_path or CONFIG.memory.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = __import__("sqlite3").connect(str(path), timeout=10.0)
    conn.row_factory = __import__("sqlite3").Row
    try:
        yield conn
    finally:
        conn.close()


__all__ = [
    "clear_all_sql",
    "connect_database",
    "execute_sql_script",
    "get_backend_name",
    "get_database_backend",
    "get_database_url",
    "get_schema_sql",
    "is_deployed_environment",
]
