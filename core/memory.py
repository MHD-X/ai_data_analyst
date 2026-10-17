"""
core/memory.py — قاعدة بيانات الذاكرة والتعلم المستمر
SQLite-based memory for tracking operations and enabling few-shot learning.

الجداول:
- sessions   : جلسات المستخدم
- datasets   : الملفات المرفوعة
- operations : العمليات المنفّذة (الطلبات + الأكواد + النتائج)
- feedback   : تقييمات المستخدم
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from config import CONFIG
from utils.helpers import (
    hash_file,
    now_iso,
    safe_json_dumps,
    safe_json_loads,
    truncate_text,
)

logger = logging.getLogger(__name__)


# ============================================================
# Schema SQL
# ============================================================
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- ============ الجلسات ============
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    metadata     TEXT DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- ============ الملفات المرفوعة ============
CREATE TABLE IF NOT EXISTS datasets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER,
    filename     TEXT NOT NULL,
    file_hash    TEXT NOT NULL,
    file_path    TEXT,
    rows         INTEGER DEFAULT 0,
    cols         INTEGER DEFAULT 0,
    columns_info TEXT DEFAULT '{}',
    created_at   TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_datasets_hash ON datasets(file_hash);
CREATE INDEX IF NOT EXISTS idx_datasets_session ON datasets(session_id);

-- ============ العمليات ============
CREATE TABLE IF NOT EXISTS operations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id      INTEGER,
    session_id      INTEGER,
    user_request    TEXT NOT NULL,
    generated_code  TEXT,
    result_summary  TEXT,
    success         INTEGER DEFAULT 0,
    execution_time  REAL DEFAULT 0,
    error           TEXT,
    error_type      TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_operations_dataset ON operations(dataset_id);
CREATE INDEX IF NOT EXISTS idx_operations_success ON operations(success);
CREATE INDEX IF NOT EXISTS idx_operations_created ON operations(created_at);

-- ============ التقييمات ============
CREATE TABLE IF NOT EXISTS feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL,
    rating       INTEGER CHECK(rating BETWEEN 1 AND 5),
    comment      TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_operation ON feedback(operation_id);
"""


# ============================================================
# نماذج البيانات (Data Classes)
# ============================================================
@dataclass
class Session:
    id: int | None = None
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Dataset:
    id: int | None = None
    session_id: int | None = None
    filename: str = ""
    file_hash: str = ""
    file_path: str = ""
    rows: int = 0
    cols: int = 0
    columns_info: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Operation:
    id: int | None = None
    dataset_id: int | None = None
    session_id: int | None = None
    user_request: str = ""
    generated_code: str = ""
    result_summary: str = ""
    success: bool = False
    execution_time: float = 0.0
    error: str = ""
    error_type: str = ""
    created_at: str = ""


@dataclass
class Feedback:
    id: int | None = None
    operation_id: int = 0
    rating: int = 5
    comment: str = ""
    created_at: str = ""


# ============================================================
# الفئة الرئيسية
# ============================================================
class MemoryStore:
    """
    مدير قاعدة بيانات الذاكرة.

    الاستخدام:
        mem = MemoryStore()
        session_id = mem.create_session("جلسة تجريبية")
        mem.log_operation(session_id, "احسب المتوسط", "code", True)
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or CONFIG.memory.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """ينشئ الجداول إن لم تكن موجودة."""
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        logger.info("✅ قاعدة البيانات جاهزة: %s", self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """مدير سياق للاتصال بقاعدة البيانات."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # --------------------------------------------------------
    # أدوات داخلية
    # --------------------------------------------------------
    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        """يحوّل صف SQLite إلى dict."""
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        """يحوّل قائمة صفوف إلى قائمة dicts."""
        return [dict(r) for r in rows]

# ============ نهاية الجزء 1/5 — أكمل بالجزء التالي ============
 # ========================================================
    # SESSIONS — الجلسات
    # ========================================================
    def create_session(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """
        ينشئ جلسة جديدة.
        يعيد session_id.
        """
        now = now_iso()
        meta_json = safe_json_dumps(metadata or {})

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sessions (name, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, meta_json, now, now),
            )
            conn.commit()
            session_id = cur.lastrowid

        logger.info("📁 جلسة جديدة #%d: %s", session_id, name)
        return int(session_id)

    def get_session(self, session_id: int) -> Session | None:
        """يعيد جلسة بالمعرّف."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        d = dict(row)
        return Session(
            id=d["id"],
            name=d["name"],
            metadata=safe_json_loads(d.get("metadata"), default={}),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """يعيد آخر الجلسات."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            Session(
                id=r["id"],
                name=r["name"],
                metadata=safe_json_loads(r["metadata"], default={}),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def update_session(
        self,
        session_id: int,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """يحدّث جلسة موجودة."""
        updates: list[str] = []
        params: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(safe_json_dumps(metadata))

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(now_iso())
        params.append(session_id)

        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_session(self, session_id: int) -> bool:
        """يحذف جلسة وكل ما يتعلق بها (CASCADE)."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    # ========================================================
    # DATASETS — الملفات المرفوعة
    # ========================================================
    def save_dataset(
        self,
        filename: str,
        file_path: str | Path,
        rows: int,
        cols: int,
        columns_info: dict[str, Any] | None = None,
        session_id: int | None = None,
    ) -> int:
        """
        يحفظ بيانات ملف مرفوع.
        يحسب hash تلقائياً من الملف.
        يعيد dataset_id.
        """
        file_path = Path(file_path)
        file_hash = hash_file(file_path)
        now = now_iso()
        info_json = safe_json_dumps(columns_info or {})

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO datasets
                    (session_id, filename, file_hash, file_path,
                     rows, cols, columns_info, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    filename,
                    file_hash,
                    str(file_path),
                    rows,
                    cols,
                    info_json,
                    now,
                ),
            )
            conn.commit()
            dataset_id = cur.lastrowid

        logger.info(
            "📊 ملف جديد #%d: %s (%d×%d)",
            dataset_id, filename, rows, cols,
        )
        return int(dataset_id)

    def get_dataset(self, dataset_id: int) -> Dataset | None:
        """يعيد dataset بالمعرّف."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE id = ?",
                (dataset_id,),
            ).fetchone()

        if row is None:
            return None

        d = dict(row)
        return Dataset(
            id=d["id"],
            session_id=d.get("session_id"),
            filename=d["filename"],
            file_hash=d["file_hash"],
            file_path=d.get("file_path") or "",
            rows=d.get("rows") or 0,
            cols=d.get("cols") or 0,
            columns_info=safe_json_loads(d.get("columns_info"), default={}),
            created_at=d["created_at"],
        )

    def get_dataset_by_hash(self, file_hash: str) -> Dataset | None:
        """يعيد dataset ببصمة الملف (لو رُفع سابقاً)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM datasets
                WHERE file_hash = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (file_hash,),
            ).fetchone()

        if row is None:
            return None

        d = dict(row)
        return Dataset(
            id=d["id"],
            session_id=d.get("session_id"),
            filename=d["filename"],
            file_hash=d["file_hash"],
            file_path=d.get("file_path") or "",
            rows=d.get("rows") or 0,
            cols=d.get("cols") or 0,
            columns_info=safe_json_loads(d.get("columns_info"), default={}),
            created_at=d["created_at"],
        )

    def list_datasets(
        self,
        session_id: int | None = None,
        limit: int = 50,
    ) -> list[Dataset]:
        """يعيد قائمة الملفات (اختياري: جلسة معينة)."""
        with self._connect() as conn:
            if session_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM datasets
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM datasets
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [
            Dataset(
                id=r["id"],
                session_id=r.get("session_id"),
                filename=r["filename"],
                file_hash=r["file_hash"],
                file_path=r.get("file_path") or "",
                rows=r.get("rows") or 0,
                cols=r.get("cols") or 0,
                columns_info=safe_json_loads(r.get("columns_info"), default={}),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def delete_dataset(self, dataset_id: int) -> bool:
        """يحذف dataset وكل عملياته."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM datasets WHERE id = ?",
                (dataset_id,),
            )
            conn.commit()
            return cur.rowcount > 0

# ============ نهاية الجزء 2/5 — أكمل بالجزء التالي ============
# ========================================================
    # OPERATIONS — العمليات المنفّذة
    # ========================================================
    def log_operation(
        self,
        user_request: str,
        generated_code: str = "",
        result_summary: str = "",
        success: bool = False,
        execution_time: float = 0.0,
        error: str = "",
        error_type: str = "",
        dataset_id: int | None = None,
        session_id: int | None = None,
    ) -> int:
        """
        يسجّل عملية في قاعدة البيانات.
        يعيد operation_id.
        """
        now = now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO operations
                    (dataset_id, session_id, user_request, generated_code,
                     result_summary, success, execution_time,
                     error, error_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    session_id,
                    user_request,
                    generated_code,
                    truncate_text(result_summary, max_length=2000),
                    1 if success else 0,
                    float(execution_time),
                    truncate_text(error, max_length=2000),
                    error_type,
                    now,
                ),
            )
            conn.commit()
            op_id = cur.lastrowid

        status = "✅" if success else "❌"
        logger.info(
            "%s عملية #%d: %s",
            status, op_id, truncate_text(user_request, 60),
        )
        return int(op_id)

    def get_operation(self, operation_id: int) -> Operation | None:
        """يعيد عملية بالمعرّف."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM operations WHERE id = ?",
                (operation_id,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_operation(dict(row))

    def list_operations(
        self,
        dataset_id: int | None = None,
        session_id: int | None = None,
        success_only: bool = False,
        limit: int = 50,
    ) -> list[Operation]:
        """
        يعيد قائمة العمليات مع فلاتر اختيارية.
        """
        query = "SELECT * FROM operations WHERE 1=1"
        params: list[Any] = []

        if dataset_id is not None:
            query += " AND dataset_id = ?"
            params.append(dataset_id)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if success_only:
            query += " AND success = 1"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_operation(dict(r)) for r in rows]

    def update_operation_summary(
        self,
        operation_id: int,
        result_summary: str,
    ) -> bool:
        """يحدّث ملخص عملية (مفيد بعد الحصول على رد LLM)."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE operations SET result_summary = ? WHERE id = ?",
                (truncate_text(result_summary, 2000), operation_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_operation(self, operation_id: int) -> bool:
        """يحذف عملية."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM operations WHERE id = ?",
                (operation_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def _row_to_operation(d: dict[str, Any]) -> Operation:
        """يحوّل صف قاعدة بيانات إلى كائن Operation."""
        return Operation(
            id=d["id"],
            dataset_id=d.get("dataset_id"),
            session_id=d.get("session_id"),
            user_request=d.get("user_request") or "",
            generated_code=d.get("generated_code") or "",
            result_summary=d.get("result_summary") or "",
            success=bool(d.get("success", 0)),
            execution_time=float(d.get("execution_time") or 0.0),
            error=d.get("error") or "",
            error_type=d.get("error_type") or "",
            created_at=d.get("created_at") or "",
        )

    # ========================================================
    # FEEDBACK — تقييمات المستخدم
    # ========================================================
    def add_feedback(
        self,
        operation_id: int,
        rating: int,
        comment: str = "",
    ) -> int:
        """
        يضيف تقييماً لعملية.
        rating: من 1 إلى 5
        يعيد feedback_id.
        """
        if not (1 <= rating <= 5):
            raise ValueError("⚠️ التقييم يجب أن يكون بين 1 و 5")

        now = now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO feedback
                    (operation_id, rating, comment, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (operation_id, rating, comment, now),
            )
            conn.commit()
            fb_id = cur.lastrowid

        logger.info("⭐ تقييم #%d لعملية #%d: %d/5", fb_id, operation_id, rating)
        return int(fb_id)

    def get_feedback_for_operation(
        self,
        operation_id: int,
    ) -> list[Feedback]:
        """يعيد كل تقييمات عملية معينة."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM feedback
                WHERE operation_id = ?
                ORDER BY created_at DESC
                """,
                (operation_id,),
            ).fetchall()

        return [
            Feedback(
                id=r["id"],
                operation_id=r["operation_id"],
                rating=r["rating"],
                comment=r.get("comment") or "",
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_average_rating(self, operation_id: int) -> float | None:
        """يعيد متوسط تقييم عملية."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT AVG(rating) as avg_rating FROM feedback WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()

        if row is None or row["avg_rating"] is None:
            return None
        return float(row["avg_rating"])

    def delete_feedback(self, feedback_id: int) -> bool:
        """يحذف تقييماً."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM feedback WHERE id = ?",
                (feedback_id,),
            )
            conn.commit()
            return cur.rowcount > 0

# ============ نهاية الجزء 3/5 — أكمل بالجزء التالي ============
 # ========================================================
    # FEW-SHOT RETRIEVAL — استرجاع أمثلة مشابهة
    # ========================================================
    def find_similar_operations(
        self,
        user_request: str,
        dataset_id: int | None = None,
        limit: int | None = None,
        success_only: bool = True,
    ) -> list[Operation]:
        """
        يبحث عن عمليات مشابهة لطلب المستخدم.
        يستخدم تشابه نصي بسيط (كلمات مفتاحية).

        Args:
            user_request: الطلب الحالي
            dataset_id: لو محدد، يبحث في نفس الملف فقط
            limit: عدد النتائج (افتراضي من CONFIG)
            success_only: فقط العمليات الناجحة
        """
        limit = limit or CONFIG.memory.max_few_shot_examples

        # استخراج كلمات مفتاحية من الطلب
        keywords = self._extract_keywords(user_request)
        if not keywords:
            return []

        # بناء استعلام LIKE لكل كلمة
        conditions: list[str] = []
        params: list[Any] = []

        for kw in keywords[:5]:  # أول 5 كلمات مفتاحية
            conditions.append("LOWER(user_request) LIKE ?")
            params.append(f"%{kw.lower()}%")

        query = "SELECT * FROM operations WHERE ("
        query += " OR ".join(conditions) + ")"

        if success_only:
            query += " AND success = 1"

        if dataset_id is not None:
            query += " AND dataset_id = ?"
            params.append(dataset_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit * 3)  # نجلب أكثر ثم نرتّب

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        # ترتيب حسب عدد الكلمات المفتاحية المتطابقة
        scored: list[tuple[int, Operation]] = []
        for r in rows:
            op = self._row_to_operation(dict(r))
            score = sum(
                1 for kw in keywords
                if kw.lower() in op.user_request.lower()
            )
            scored.append((score, op))

        scored.sort(key=lambda x: (-x[0], x[1].created_at), reverse=False)
        # نرجع الأفضل حسب score مع الأحدث
        scored.sort(key=lambda x: x[0], reverse=True)

        return [op for _, op in scored[:limit]]

    @staticmethod
    def _extract_keywords(text: str, min_length: int = 3) -> list[str]:
        """
        يستخرج كلمات مفتاحية من نص.
        يتجاهل كلمات التوقف الشائعة.
        """
        import re

        # قائمة كلمات توقف عربية وإنجليزية
        stopwords = {
            # عربية
            "من", "إلى", "في", "على", "عن", "مع", "هذا", "هذه",
            "ذلك", "التي", "الذي", "أن", "إن", "كان", "قد", "ما",
            "لا", "لم", "لن", "هل", "أو", "و", "ثم", "كل", "بعض",
            "كيف", "ماذا", "لماذا", "متى", "أين", "أي", "هو", "هي",
            # إنجليزية
            "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "are", "was",
            "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "should", "could",
            "can", "may", "might", "must", "this", "that", "these",
            "those", "what", "which", "who", "when", "where", "why",
            "how", "please", "me", "my", "your", "show", "give",
        }

        # استخراج الكلمات (عربية + إنجليزية + أرقام)
        words = re.findall(r"[\w\u0600-\u06FF]+", text)
        keywords: list[str] = []

        for w in words:
            w_lower = w.lower()
            if len(w) >= min_length and w_lower not in stopwords:
                if w_lower not in keywords:
                    keywords.append(w_lower)

        return keywords

    def get_few_shot_examples(
        self,
        user_request: str,
        dataset_id: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """
        يعيد أمثلة جاهزة للاستخدام في prompt الـ LLM.

        Returns:
            list of {"request": ..., "code": ..., "result": ...}
        """
        ops = self.find_similar_operations(
            user_request,
            dataset_id=dataset_id,
            limit=limit,
        )

        examples: list[dict[str, str]] = []
        for op in ops:
            if not op.generated_code:
                continue
            examples.append({
                "request": op.user_request,
                "code": op.generated_code,
                "result": op.result_summary or "",
            })

        return examples

    # ========================================================
    # STATISTICS — إحصائيات
    # ========================================================
    def get_statistics(self) -> dict[str, Any]:
        """
        يعيد إحصائيات شاملة عن قاعدة البيانات.
        """
        with self._connect() as conn:
            stats: dict[str, Any] = {}

            # عدد الجلسات
            stats["total_sessions"] = conn.execute(
                "SELECT COUNT(*) FROM sessions"
            ).fetchone()[0]

            # عدد الملفات
            stats["total_datasets"] = conn.execute(
                "SELECT COUNT(*) FROM datasets"
            ).fetchone()[0]

            # عدد العمليات
            stats["total_operations"] = conn.execute(
                "SELECT COUNT(*) FROM operations"
            ).fetchone()[0]

            # نجحت
            stats["successful_operations"] = conn.execute(
                "SELECT COUNT(*) FROM operations WHERE success = 1"
            ).fetchone()[0]

            # فشلت
            stats["failed_operations"] = (
                stats["total_operations"] - stats["successful_operations"]
            )

            # نسبة النجاح
            if stats["total_operations"] > 0:
                stats["success_rate"] = round(
                    stats["successful_operations"] / stats["total_operations"] * 100,
                    2,
                )
            else:
                stats["success_rate"] = 0.0

            # متوسط وقت التنفيذ
            row = conn.execute(
                "SELECT AVG(execution_time) FROM operations WHERE success = 1"
            ).fetchone()
            stats["avg_execution_time"] = round(row[0] or 0.0, 3)

            # عدد التقييمات
            stats["total_feedback"] = conn.execute(
                "SELECT COUNT(*) FROM feedback"
            ).fetchone()[0]

            # متوسط التقييم العام
            row = conn.execute(
                "SELECT AVG(rating) FROM feedback"
            ).fetchone()
            stats["avg_rating"] = round(row[0] or 0.0, 2)

            # حجم قاعدة البيانات
            try:
                stats["db_size_mb"] = round(
                    self.db_path.stat().st_size / 1024 / 1024, 3
                )
            except Exception:
                stats["db_size_mb"] = 0.0

        return stats

    def get_recent_operations(self, limit: int = 10) -> list[Operation]:
        """يعيد آخر العمليات."""
        return self.list_operations(limit=limit)

    def get_top_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        """يعيد أكثر الطلبات تكراراً."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_request, COUNT(*) as count
                FROM operations
                GROUP BY user_request
                ORDER BY count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [{"request": r["user_request"], "count": r["count"]} for r in rows]

# ============ نهاية الجزء 4/5 — أكمل بالجزء التالي ============
    # ========================================================
    # EXPORT — تصدير البيانات
    # ========================================================
    def export_to_json(
        self,
        output_path: str | Path,
        include_operations: bool = True,
        include_feedback: bool = True,
    ) -> Path:
        """
        يصدّر محتوى قاعدة البيانات إلى JSON.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "exported_at": now_iso(),
            "sessions": [],
            "datasets": [],
            "operations": [],
            "feedback": [],
        }

        with self._connect() as conn:
            # الجلسات
            rows = conn.execute("SELECT * FROM sessions").fetchall()
            data["sessions"] = self._rows_to_dicts(rows)

            # الملفات
            rows = conn.execute("SELECT * FROM datasets").fetchall()
            data["datasets"] = self._rows_to_dicts(rows)

            # العمليات
            if include_operations:
                rows = conn.execute("SELECT * FROM operations").fetchall()
                data["operations"] = self._rows_to_dicts(rows)

            # التقييمات
            if include_feedback:
                rows = conn.execute("SELECT * FROM feedback").fetchall()
                data["feedback"] = self._rows_to_dicts(rows)

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("📤 تم التصدير إلى: %s", output_path)
        return output_path

    def export_to_csv(
        self,
        output_dir: str | Path,
    ) -> dict[str, Path]:
        """
        يصدّر كل جدول إلى ملف CSV منفصل.
        يعيد dict: {table_name: file_path}
        """
        import csv

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        exported: dict[str, Path] = {}
        tables = ["sessions", "datasets", "operations", "feedback"]

        with self._connect() as conn:
            for table in tables:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                if not rows:
                    continue

                csv_path = output_dir / f"{table}.csv"
                fieldnames = rows[0].keys()

                with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(dict(row))

                exported[table] = csv_path
                logger.info("📤 تم تصدير %s → %s", table, csv_path)

        return exported

    # ========================================================
    # CLEANUP — تنظيف
    # ========================================================
    def clear_all(self, confirm: bool = False) -> bool:
        """
        يحذف كل البيانات (بحذر!).
        يتطلب confirm=True.
        """
        if not confirm:
            raise ValueError(
                "⚠️ لحذف كل البيانات، مرّر confirm=True"
            )

        with self._connect() as conn:
            conn.execute("DELETE FROM feedback")
            conn.execute("DELETE FROM operations")
            conn.execute("DELETE FROM datasets")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM sqlite_sequence")
            conn.commit()

        logger.warning("🧹 تم حذف كل البيانات من قاعدة البيانات")
        return True

    def cleanup_old_operations(self, days: int = 30) -> int:
        """
        يحذف العمليات الأقدم من N يوم.
        يعيد عدد العمليات المحذوفة.
        """
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM operations WHERE created_at < ?",
                (cutoff,),
            )
            conn.commit()
            deleted = cur.rowcount

        logger.info("🧹 حذف %d عملية أقدم من %d يوم", deleted, days)
        return deleted

    def vacuum(self) -> None:
        """يعيد ضغط قاعدة البيانات (يوفّر مساحة)."""
        with self._connect() as conn:
            conn.execute("VACUUM")
            conn.commit()
        logger.info("🗜️ تم ضغط قاعدة البيانات")


# ============================================================
# نسخة عامة (Singleton)
# ============================================================
_default_memory: MemoryStore | None = None


def get_memory() -> MemoryStore:
    """يعيد نسخة مشتركة من MemoryStore."""
    global _default_memory
    if _default_memory is None:
        _default_memory = MemoryStore()
    return _default_memory


def reset_memory() -> None:
    """يعيد تعيين النسخة المشتركة."""
    global _default_memory
    _default_memory = None


# ============================================================
# اختبار مباشر
# ============================================================
if __name__ == "__main__":
    import tempfile

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print("=" * 60)
    print("🧪 اختبار core/memory.py")
    print("=" * 60)

    # استخدام قاعدة بيانات مؤقتة للاختبار
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = Path(tmp_dir) / "test_memory.db"
        mem = MemoryStore(test_db)
        print(f"\n📁 قاعدة اختبار: {test_db}")

        # ---------- 1. الجلسات ----------
        print("\n[1] الجلسات:")
        sid = mem.create_session("جلسة اختبار", {"user": "test"})
        print(f"   ✅ Session ID: {sid}")
        s = mem.get_session(sid)
        print(f"   📝 الاسم: {s.name}")
        print(f"   📋 عدد الجلسات: {len(mem.list_sessions())}")

        # ---------- 2. الملفات ----------
        print("\n[2] الملفات:")
        csv_file = Path(tmp_dir) / "data.csv"
        csv_file.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
        did = mem.save_dataset(
            filename="data.csv",
            file_path=csv_file,
            rows=2,
            cols=3,
            columns_info={"a": "int", "b": "int", "c": "int"},
            session_id=sid,
        )
        print(f"   ✅ Dataset ID: {did}")
        d = mem.get_dataset(did)
        print(f"   📄 الملف: {d.filename} ({d.rows}×{d.cols})")

        # ---------- 3. العمليات ----------
        print("\n[3] العمليات:")
        op1 = mem.log_operation(
            user_request="احسب متوسط العمود a",
            generated_code="avg = df['a'].mean()",
            result_summary="المتوسط = 2.5",
            success=True,
            execution_time=0.5,
            dataset_id=did,
            session_id=sid,
        )
        op2 = mem.log_operation(
            user_request="ارسم مخطط العمود b",
            generated_code="px.line(df, y='b')",
            result_summary="تم رسم المخطط",
            success=True,
            execution_time=1.2,
            dataset_id=did,
            session_id=sid,
        )
        op3 = mem.log_operation(
            user_request="احسب مجموع العمود c",
            generated_code="total = df['c'].sum()",
            result_summary="المجموع = 9",
            success=False,
            error="KeyError: 'c'",
            error_type="KeyError",
            dataset_id=did,
            session_id=sid,
        )
        print(f"   ✅ العمليات: {op1}, {op2}, {op3}")

        # ---------- 4. التقييمات ----------
        print("\n[4] التقييمات:")
        fb1 = mem.add_feedback(op1, rating=5, comment="ممتاز")
        fb2 = mem.add_feedback(op1, rating=4, comment="جيد")
        print(f"   ⭐ تقييمات: {fb1}, {fb2}")
        print(f"   📊 متوسط التقييم: {mem.get_average_rating(op1)}")

         # ---------- 5. Few-Shot Retrieval ----------
        print("\n[5] البحث عن عمليات مشابهة:")
        similar = mem.find_similar_operations("احسب متوسط العمود a")
        print(f"   🔍 عدد النتائج المشابهة: {len(similar)}")
        for op in similar:
            print(f"     - {op.user_request}")

        # ---------- 6. أمثلة Few-Shot ----------
        print("\n[6] أمثلة Few-Shot:")
        examples = mem.get_few_shot_examples("احسب متوسط العمود a")
        print(f"   📚 عدد الأمثلة: {len(examples)}")
        for ex in examples:
            print(f"     → {ex['request']}")

        # ---------- 7. الإحصائيات ----------
        print("\n[7] الإحصائيات:")
        stats = mem.get_statistics()
        for k, v in stats.items():
            print(f"   {k}: {v}")

        # ---------- 8. التصدير ----------
        print("\n[8] التصدير:")
        json_path = mem.export_to_json(Path(tmp_dir) / "export.json")
        print(f"   📤 JSON: {json_path.name} ({json_path.stat().st_size} bytes)")

        csv_dir = Path(tmp_dir) / "csv_export"
        csv_files = mem.export_to_csv(csv_dir)
        print(f"   📤 CSV: {list(csv_files.keys())}")

        # ---------- 9. التنظيف ----------
        print("\n[9] التنظيف:")
        deleted = mem.cleanup_old_operations(days=0)
        print(f"   🧹 عمليات محذوفة: {deleted}")

        # ---------- 10. الحذف الكامل ----------
        print("\n[10] الحذف الكامل:")
        mem.clear_all(confirm=True)
        stats_after = mem.get_statistics()
        print(f"   ✅ عمليات متبقية: {stats_after['total_operations']}")

    print("\n" + "=" * 60)
    print("✅ اكتمل اختبار memory.py بنجاح")
    print("=" * 60)