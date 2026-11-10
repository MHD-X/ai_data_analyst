"""core/db.py — robust database layer for SQLite and PostgreSQL.

This module exposes a thread-safe, pool-backed connection interface for PostgreSQL and
keeps the project-compatible SQLite fallback for local development and tests.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

try:
    import psycopg2
    from psycopg2 import pool as psycopg_pool
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - optional dependency for PostgreSQL
    psycopg2 = None
    psycopg_pool = None
    RealDictCursor = None


def _require_postgres_dependencies() -> None:
    """Raise a clear error when PostgreSQL support is requested without the driver installed."""
    if psycopg2 is None or psycopg_pool is None:
        raise RuntimeError(
            "PostgreSQL support requires psycopg2-binary>=2.9.9. "
            "Install it with: pip install psycopg2-binary>=2.9.9"
        )

from config import get_setting

logger = logging.getLogger(__name__)

POSTGRES_SCHEMES = (
    "postgresql://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
    "postgres://",
)

CONNECT_RETRIES = 3
_PG_POOL_LOCK = threading.RLock()
_POSTGRES_POOLS: dict[str, Any] = {}


# ============================================================
# إعدادات الاتصال
# ============================================================
def normalize_database_url(url: str | None) -> str:
    """Normalize PostgreSQL connection URLs used by the project."""
    url = (url or "").strip()
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def get_database_url() -> str:
    """Read PostgreSQL URL from environment or app secrets."""
    for key in ("DATABASE_URL", "TEST_DATABASE_URL"):
        value = (os.getenv(key) or get_setting(key, "") or "").strip()
        if value:
            return value
    return ""


def get_database_backend(database_url: str | None = None) -> str:
    """Resolve active backend: 'postgresql' or 'sqlite'."""
    url = (database_url or get_database_url() or "").strip()
    if url and url.startswith(POSTGRES_SCHEMES):
        return "postgresql"
    return "sqlite"


def get_backend_name(database_url: str | None = None) -> str:
    """User-friendly backend label, never leaking the DSN."""
    return "PostgreSQL (Neon)" if get_database_backend(database_url) == "postgresql" else "SQLite"


def is_deployed_environment() -> bool:
    """True when the app appears to run in a hosted environment."""
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


def _get_postgres_pool(database_url: str) -> Any:
    """Create and cache a PostgreSQL connection pool.

    Uses psycopg2.pool.SimpleConnectionPool to avoid per-request connection creation and
    ensures a single pool object is reused across threads safely.
    """
    _require_postgres_dependencies()

    normalized = normalize_database_url(database_url)
    with _PG_POOL_LOCK:
        pool = _POSTGRES_POOLS.get(normalized)
        if pool is None:
            pool = psycopg_pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=normalized,
            )
            _POSTGRES_POOLS[normalized] = pool
        return pool


def close_postgres_pools() -> None:
    """Close all cached PostgreSQL pools."""
    with _PG_POOL_LOCK:
        for pool in list(_POSTGRES_POOLS.values()):
            try:
                pool.closeall()
            except Exception:
                pass
        _POSTGRES_POOLS.clear()


# ============================================================
# المخطط (Schema)
# ============================================================
# Audit fix: hardened DB pooling, WAL SQLite mode, and user-scoping indexes.
def get_schema_sql(backend: str | None = None) -> str:
    backend = (backend or get_database_backend()).lower()
    if backend == "postgresql":
        return """
        CREATE TABLE IF NOT EXISTS sessions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 0,
            name TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS datasets (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 0,
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

        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_datasets_user ON datasets(user_id);
        CREATE INDEX IF NOT EXISTS idx_datasets_hash ON datasets(file_hash);
        CREATE INDEX IF NOT EXISTS idx_datasets_session ON datasets(session_id);

        CREATE TABLE IF NOT EXISTS operations (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 0,
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

        CREATE INDEX IF NOT EXISTS idx_operations_user ON operations(user_id);
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

        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            email_verified INTEGER NOT NULL DEFAULT 0,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT NULL,
            created_at TEXT NOT NULL,
            last_login_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS email_codes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            purpose TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_email_codes_user ON email_codes(user_id);
        CREATE INDEX IF NOT EXISTS idx_email_codes_purpose ON email_codes(purpose);
        """

    return """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL,
        metadata TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 0,
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

    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_datasets_user ON datasets(user_id);
    CREATE INDEX IF NOT EXISTS idx_datasets_hash ON datasets(file_hash);
    CREATE INDEX IF NOT EXISTS idx_datasets_session ON datasets(session_id);

    CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 0,
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

    CREATE INDEX IF NOT EXISTS idx_operations_user ON operations(user_id);
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

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        email_verified INTEGER NOT NULL DEFAULT 0,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until TEXT NULL,
        created_at TEXT NOT NULL,
        last_login_at TEXT NULL
    );

    CREATE TABLE IF NOT EXISTS email_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        purpose TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        used INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_email_codes_user ON email_codes(user_id);
    CREATE INDEX IF NOT EXISTS idx_email_codes_purpose ON email_codes(purpose);
    """


def clear_all_sql(backend: str | None = None) -> str:
    backend = (backend or get_database_backend()).lower()
    if backend == "postgresql":
        return "TRUNCATE TABLE feedback, operations, datasets, sessions RESTART IDENTITY CASCADE;"
    return (
        "DELETE FROM feedback; DELETE FROM operations; DELETE FROM datasets; "
        "DELETE FROM sessions; DELETE FROM sqlite_sequence;"
    )


def ensure_user_scoping_columns(conn: Any, backend: str | None = None) -> None:
    """Adds user_id columns to older databases without dropping data."""
    backend = (backend or get_database_backend()).lower()
    tables = ("sessions", "datasets", "operations")

    if backend == "postgresql":
        for table in tables:
            row = conn.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                LIMIT 1
                """,
                (table, "user_id"),
            ).fetchone()
            if row is None:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id BIGINT NOT NULL DEFAULT 0;")
        for index_sql in (
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_datasets_user ON datasets(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_operations_user ON operations(user_id);",
        ):
            conn.execute(index_sql)
        return

    for table in tables:
        columns = [item[1] for item in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "user_id" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
    for index_sql in (
        "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_datasets_user ON datasets(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_operations_user ON operations(user_id);",
    ):
        conn.execute(index_sql)


# ============================================================
# ترجمة الاستعلامات
# ============================================================
def translate_sql(sql: str, backend: str) -> str:
    """Translate placeholders to the dialect used by a backend.

    PostgreSQL uses %s, SQLite uses ?. The project now standardizes on %s in source code,
    and this helper keeps the SQLite fallback compatible.
    """
    if backend != "postgresql":
        return sql.replace("%s", "?")
    return sql


# ============================================================
# غلاف الاتصال
# ============================================================
class DBConnection:
    """Unified DB wrapper for SQLite and PostgreSQL connections."""

    def __init__(self, raw: Any, backend: str) -> None:
        self._raw = raw
        self.backend = backend

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        values = tuple(params) if params else ()
        if self.backend == "postgresql":
            query = sql.replace("?", "%s") if "?" in sql else sql
            if hasattr(self._raw, "cursor"):
                cursor_factory = RealDictCursor if RealDictCursor is not None else None
                if cursor_factory is not None:
                    cur = self._raw.cursor(cursor_factory=cursor_factory)
                else:
                    cur = self._raw.cursor()
                if values:
                    cur.execute(query, values)
                else:
                    cur.execute(query)
                return cur
            return self._raw.execute(query, values) if values else self._raw.execute(query)

        translated = translate_sql(sql, self.backend)
        return self._raw.execute(translated, values)

    def insert(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """Execute an INSERT and return the generated identifier."""
        if self.backend == "postgresql":
            cur = self.execute(sql.rstrip().rstrip(";") + " RETURNING id", params)
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("INSERT did not return a generated id.")
            return int(row["id"])

        cur = self.execute(sql, params)
        return int(cur.lastrowid)

    def executescript(self, sql_text: str) -> None:
        if self.backend == "postgresql":
            statements = [part.strip() for part in sql_text.split(";")]
            cur = self._raw.cursor()
            try:
                for statement in statements:
                    if statement:
                        cur.execute(statement)
            finally:
                cur.close()
            return
        self._raw.executescript(sql_text)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        try:
            self._raw.rollback()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._raw.close()
        except Exception:
            pass


def execute_sql_script(conn: Any, sql_text: str) -> None:
    """Run DDL scripts against either DBConnection or a raw connection."""
    if isinstance(conn, DBConnection):
        conn.executescript(sql_text)
        return
    if get_database_backend() == "postgresql":
        cursor = conn.cursor()
        try:
            for statement in (part.strip() for part in sql_text.split(";")):
                if statement:
                    cursor.execute(statement)
        finally:
            cursor.close()
        return
    conn.executescript(sql_text)


# ============================================================
# الاتصال
# ============================================================
@contextmanager
def _acquire_pg_connection(
    database_url: str,
) -> Iterator[DBConnection]:
    """Acquire and manage a PostgreSQL connection from the shared pool."""
    _require_postgres_dependencies()
    pool = _get_postgres_pool(database_url)
    conn = None
    last_error: Exception | None = None
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            conn = pool.getconn()
            if getattr(conn, "closed", 0):
                pool.putconn(conn, close=True)
                raise RuntimeError("PostgreSQL connection is stale.")
            conn.autocommit = False
            wrapped = DBConnection(conn, "postgresql")
            try:
                yield wrapped
                wrapped.commit()
            except Exception:
                wrapped.rollback()
                raise
            finally:
                if conn is not None:
                    try:
                        pool.putconn(conn)
                    except Exception:
                        pass
            return
        except Exception as exc:  # pragma: no cover - retry path
            last_error = exc
            if conn is not None:
                try:
                    if getattr(conn, "closed", 0):
                        pool.putconn(conn, close=True)
                    else:
                        pool.putconn(conn)
                except Exception:
                    pass
                conn = None
            if attempt < CONNECT_RETRIES:
                time.sleep(0.2 * attempt)
    if conn is not None:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
    raise RuntimeError(f"Failed to open PostgreSQL connection after {CONNECT_RETRIES} attempts") from last_error


@contextmanager
def get_db_connection(
    db_path: str | Path | None = None,
    database_url: str | None = None,
) -> Iterator[DBConnection]:
    """Thread-safe DB connection context manager.

    PostgreSQL uses a pooled connection from psycopg2.pool.SimpleConnectionPool; SQLite uses a
    dedicated connection per context. Each call commits on success and rolls back on failure.
    """
    database_url = database_url or get_database_url()
    if db_path is not None and not database_url:
        backend = "sqlite"
    else:
        backend = get_database_backend(database_url)

    if backend == "postgresql":
        if not database_url:
            database_url = normalize_database_url(get_database_url())
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured.")
        with _acquire_pg_connection(database_url) as wrapped:
            yield wrapped
        return

    sqlite_path = Path(db_path or os.getenv("DB_PATH") or "data/memory.db")
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    wrapped = DBConnection(conn, "sqlite")
    try:
        yield wrapped
        wrapped.commit()
    except Exception:
        wrapped.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def connect_database(
    db_path: str | Path | None = None,
    database_url: str | None = None,
) -> Iterator[DBConnection]:
    """Backward-compatible alias to the thread-safe DB connection context manager."""
    with get_db_connection(db_path=db_path, database_url=database_url) as connection:
        yield connection


__all__ = [
    "DBConnection",
    "close_postgres_pools",
    "connect_database",
    "ensure_user_scoping_columns",
    "get_backend_name",
    "get_database_backend",
    "get_database_url",
    "get_db_connection",
    "get_schema_sql",
    "normalize_database_url",
    "translate_sql",
    "execute_sql_script",
]