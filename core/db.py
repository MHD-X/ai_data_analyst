"""
core/db.py — طبقة الاتصال بقاعدة البيانات (SQLite محلياً / PostgreSQL على Neon)

كل استعلام يمر عبر DBConnection الذي:
  - يحوّل علامات "?" إلى "%s" عند استخدام PostgreSQL
  - يعيد الصفوف كقواميس (dict) في الحالتين
  - يوفّر insert() يعيد المعرّف الجديد (RETURNING id / lastrowid)
لا يُطبع رابط الاتصال ولا كلمة السر في أي رسالة.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - اختياري في وضع SQLite المحلي
    psycopg = None
    dict_row = None

from config import CONFIG, get_setting

logger = logging.getLogger(__name__)

POSTGRES_SCHEMES = (
    "postgresql://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
    "postgres://",
)

CONNECT_RETRIES = 3


# ============================================================
# إعدادات الاتصال
# ============================================================
def normalize_database_url(url: str | None) -> str:
    """psycopg لا يفهم 'postgresql+psycopg://' أو 'postgres://' فنوحّد الصيغة."""
    url = (url or "").strip()
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def get_database_url() -> str:
    """يعيد رابط قاعدة Postgres السحابية إن وُجد."""
    for key in ("DATABASE_URL", "TEST_DATABASE_URL"):
        value = (os.getenv(key) or get_setting(key, "") or "").strip()
        if value:
            return value
    return ""


def get_database_backend(database_url: str | None = None) -> str:
    """يعيد اسم المحرك الفعّال: 'postgresql' أو 'sqlite'."""
    url = (database_url or get_database_url() or "").strip()
    if url and url.startswith(POSTGRES_SCHEMES):
        return "postgresql"
    return "sqlite"


def get_backend_name(database_url: str | None = None) -> str:
    """اسم مقروء للمحرك يُعرض في الواجهة (لا يتضمن الرابط أبداً)."""
    if get_database_backend(database_url) == "postgresql":
        return "PostgreSQL (Neon)"
    return "SQLite"


def is_deployed_environment() -> bool:
    """True عندما يُرجَّح أن التطبيق يعمل على استضافة."""
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


# ============================================================
# المخطط (Schema)
# ============================================================
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


def clear_all_sql(backend: str | None = None) -> str:
    backend = (backend or get_database_backend()).lower()
    if backend == "postgresql":
        return "TRUNCATE TABLE feedback, operations, datasets, sessions RESTART IDENTITY CASCADE;"
    return (
        "DELETE FROM feedback; DELETE FROM operations; DELETE FROM datasets; "
        "DELETE FROM sessions; DELETE FROM sqlite_sequence;"
    )


# ============================================================
# ترجمة الاستعلامات
# ============================================================
def translate_sql(sql: str, backend: str) -> str:
    """يحوّل '?' إلى '%s' لـ PostgreSQL، ويهرّب أي '%' موجودة أصلاً في نص الاستعلام."""
    if backend != "postgresql":
        return sql
    return sql.replace("%", "%%").replace("?", "%s")


# ============================================================
# غلاف الاتصال
# ============================================================
class DBConnection:
    """غلاف موحّد فوق sqlite3 و psycopg؛ كل الاستعلامات في المشروع تمر منه."""

    def __init__(self, raw: Any, backend: str) -> None:
        self._raw = raw
        self.backend = backend

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        values = tuple(params) if params else ()
        if self.backend == "postgresql":
            if values:
                return self._raw.execute(translate_sql(sql, "postgresql"), values)
            return self._raw.execute(sql)  # بلا معاملات: لا تُفسَّر علامة % أصلاً
        return self._raw.execute(sql, values)

    def insert(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """ينفّذ INSERT ويعيد المعرّف الجديد (RETURNING id أو lastrowid)."""
        if self.backend == "postgresql":
            cur = self.execute(sql.rstrip().rstrip(";") + " RETURNING id", params)
            row = cur.fetchone()
            return int(row["id"])
        cur = self.execute(sql, params)
        return int(cur.lastrowid)

    def executescript(self, sql_text: str) -> None:
        if self.backend == "postgresql":
            for statement in (part.strip() for part in sql_text.split(";")):
                if statement:
                    self._raw.execute(statement)
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
    """ينفّذ سكربت DDL على أي اتصال (DBConnection أو sqlite3 خام)."""
    if isinstance(conn, DBConnection):
        conn.executescript(sql_text)
        return
    if get_database_backend() == "postgresql":
        for statement in (part.strip() for part in sql_text.split(";")):
            if statement:
                conn.execute(statement)
        return
    conn.executescript(sql_text)


# ============================================================
# الاتصال
# ============================================================
@contextmanager
def connect_database(
    db_path: str | Path | None = None,
    database_url: str | None = None,
) -> Iterator[DBConnection]:
    # مسار ملف صريح بدون رابط = SQLite دائماً (حماية الاختبارات من لمس القاعدة الحقيقية)
    if database_url is None and db_path is not None:
        backend = "sqlite"
    else:
        backend = get_database_backend(database_url)

    if backend == "postgresql":
        url = normalize_database_url(database_url or get_database_url())
        if not url:
            raise RuntimeError("DATABASE_URL is not configured.")
        if psycopg is None:
            raise RuntimeError("psycopg[binary] is required for PostgreSQL support.")

        raw = None
        last_error: Exception | None = None
        for attempt in range(1, CONNECT_RETRIES + 1):
            try:
                raw = psycopg.connect(
                    url,
                    autocommit=False,
                    row_factory=dict_row,
                    prepare_threshold=None,  # ضروري مع PgBouncer (Neon pooler)
                    connect_timeout=15,
                )
                break
            except psycopg.OperationalError as exc:  # القاعدة قد تكون نائمة وتحتاج ثوانٍ
                last_error = exc
                logger.warning("محاولة اتصال %d/%d فشلت (%s)", attempt, CONNECT_RETRIES, type(exc).__name__)
                time.sleep(0.8 * attempt)
        if raw is None:
            # لا نمرّر الاستثناء الأصلي حتى لا يتسرب أي جزء من الرابط
            raise RuntimeError(
                f"تعذّر الاتصال بقاعدة PostgreSQL بعد {CONNECT_RETRIES} محاولات "
                f"({type(last_error).__name__})"
            ) from None

        conn = DBConnection(raw, "postgresql")
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    path = Path(db_path or CONFIG.memory.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), timeout=10.0)
    raw.row_factory = sqlite3.Row
    conn = DBConnection(raw, "sqlite")
    try:
        yield conn
    finally:
        conn.close()


__all__ = [
    "DBConnection",
    "clear_all_sql",
    "connect_database",
    "execute_sql_script",
    "get_backend_name",
    "get_database_backend",
    "get_database_url",
    "get_schema_sql",
    "is_deployed_environment",
    "normalize_database_url",
    "translate_sql",
]