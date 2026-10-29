"""
core/memory.py — قاعدة بيانات الذاكرة والتعلم المستمر
يعمل على SQLite محلياً وعلى PostgreSQL (Neon) عند ضبط DATABASE_URL.

الجداول:
- sessions   : جلسات المستخدم
- datasets   : الملفات المرفوعة
- operations : العمليات المنفّذة (الطلبات + الأكواد + النتائج)
- feedback   : تقييمات المستخدم
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from config import CONFIG
from core.db import (
    clear_all_sql,
    connect_database,
    execute_sql_script,
    get_database_backend,
    get_database_url,
    get_schema_sql,
    normalize_database_url,
)
from core.security import redact_text
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
SCHEMA_SQL = get_schema_sql("sqlite")


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
        mem.log_operation("احسب المتوسط", "code", "", True)
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        database_url: str | None = None,
    ) -> None:
        if db_path is not None and database_url is None:
            # مسار ملف صريح => SQLite دائماً (لا نلمس قاعدة الإنتاج من الاختبارات)
            self.database_url = ""
            self.backend = "sqlite"
        else:
            configured = getattr(CONFIG.memory, "database_url", "") or ""
            self.database_url = normalize_database_url(
                database_url or configured or get_database_url() or ""
            )
            self.backend = get_database_backend(self.database_url)

        self.db_path = Path(db_path or CONFIG.memory.db_path)
        if self.backend == "sqlite":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @property
    def backend_name(self) -> str:
        if self.backend == "postgresql":
            return "PostgreSQL (Neon)"
        return "SQLite"

    def _init_db(self) -> None:
        """ينشئ الجداول إن لم تكن موجودة."""
        with self._connect() as conn:
            execute_sql_script(conn, get_schema_sql(self.backend))
            conn.commit()
        logger.info("✅ قاعدة البيانات جاهزة (%s)", self.backend)

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        """مدير سياق للاتصال بقاعدة البيانات."""
        if self.backend == "postgresql":
            with connect_database(database_url=self.database_url) as conn:
                yield conn
            return

        with connect_database(db_path=self.db_path) as conn:
            yield conn

    # --------------------------------------------------------
    # أدوات داخلية
    # --------------------------------------------------------
    @staticmethod
    def _row_to_dict(row: Any | None) -> dict[str, Any] | None:
        """يحوّل صف قاعدة البيانات إلى dict."""
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
        """يحوّل قائمة صفوف إلى قائمة dicts."""
        return [dict(r) for r in rows]

    @staticmethod
    def _row_to_dataset(d: dict[str, Any]) -> Dataset:
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

    # ========================================================
    # SESSIONS — الجلسات
    # ========================================================
    def create_session(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """ينشئ جلسة جديدة ويعيد session_id."""
        now = now_iso()
        meta_json = safe_json_dumps(metadata or {})

        with self._connect() as conn:
            session_id = conn.insert(
                """
                INSERT INTO sessions (name, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, meta_json, now, now),
            )
            conn.commit()

        logger.info("📁 جلسة جديدة #%d: %s", session_id, name)
        return session_id

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
                id=d["id"],
                name=d["name"],
                metadata=safe_json_loads(d.get("metadata"), default={}),
                created_at=d["created_at"],
                updated_at=d["updated_at"],
            )
            for d in self._rows_to_dicts(rows)
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
        file_hash: str | None = None,
    ) -> int:
        """يخزّن ملفاً مرفوعاً، مع دعم hash يدوي عند الحاجة."""
        file_path = Path(file_path)
        file_hash = file_hash or hash_file(file_path)
        now = now_iso()
        info_json = safe_json_dumps(columns_info or {})

        with self._connect() as conn:
            dataset_id = conn.insert(
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

        logger.info("📊 ملف جديد #%d: %s (%d×%d)", dataset_id, filename, rows, cols)
        return dataset_id

    def get_dataset(self, dataset_id: int) -> Dataset | None:
        """يعيد dataset بالمعرّف."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE id = ?",
                (dataset_id,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_dataset(dict(row))

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
        return self._row_to_dataset(dict(row))

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

        return [self._row_to_dataset(d) for d in self._rows_to_dicts(rows)]

    def delete_dataset(self, dataset_id: int) -> bool:
        """يحذف dataset وكل عملياته."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM datasets WHERE id = ?",
                (dataset_id,),
            )
            conn.commit()
            return cur.rowcount > 0

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
        """يسجّل عملية في قاعدة البيانات ويعيد operation_id."""
        now = now_iso()
        user_request = redact_text(user_request)
        generated_code = redact_text(generated_code)
        result_summary = redact_text(result_summary)
        error = redact_text(error)

        with self._connect() as conn:
            op_id = conn.insert(
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

        status = "✅" if success else "❌"
        logger.info("%s عملية #%d: %s", status, op_id, truncate_text(user_request, 60))
        return op_id

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
        """يعيد قائمة العمليات مع فلاتر اختيارية."""
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

        return [self._row_to_operation(d) for d in self._rows_to_dicts(rows)]

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
        """يضيف تقييماً لعملية (1 إلى 5) ويعيد feedback_id."""
        if not (1 <= rating <= 5):
            raise ValueError("⚠️ التقييم يجب أن يكون بين 1 و 5")

        now = now_iso()
        with self._connect() as conn:
            fb_id = conn.insert(
                """
                INSERT INTO feedback
                    (operation_id, rating, comment, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (operation_id, rating, comment, now),
            )
            conn.commit()

        logger.info("⭐ تقييم #%d لعملية #%d: %d/5", fb_id, operation_id, rating)
        return fb_id

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
                id=d["id"],
                operation_id=d["operation_id"],
                rating=d["rating"],
                comment=d.get("comment") or "",
                created_at=d["created_at"],
            )
            for d in self._rows_to_dicts(rows)
        ]

    def get_average_rating(self, operation_id: int) -> float | None:
        """يعيد متوسط تقييم عملية."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT AVG(rating) AS avg_rating FROM feedback WHERE operation_id = ?",
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
        يبحث عن عمليات مشابهة لطلب المستخدم (تشابه نصي بالكلمات المفتاحية).
        """
        limit = limit or CONFIG.memory.max_few_shot_examples

        keywords = self._extract_keywords(user_request)
        if not keywords:
            return []

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

        scored: list[tuple[int, Operation]] = []
        for d in self._rows_to_dicts(rows):
            op = self._row_to_operation(d)
            score = sum(1 for kw in keywords if kw.lower() in op.user_request.lower())
            scored.append((score, op))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [op for _, op in scored[:limit]]

    @staticmethod
    def _extract_keywords(text: str, min_length: int = 3) -> list[str]:
        """يستخرج كلمات مفتاحية من نص ويتجاهل كلمات التوقف الشائعة."""
        import re

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
        يعيد أمثلة جاهزة للاستخدام في prompt الـ LLM:
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
        """يعيد إحصائيات شاملة عن قاعدة البيانات."""
        with self._connect() as conn:
            stats: dict[str, Any] = {}

            stats["total_sessions"] = int(
                conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
            )
            stats["total_datasets"] = int(
                conn.execute("SELECT COUNT(*) AS n FROM datasets").fetchone()["n"]
            )
            stats["total_operations"] = int(
                conn.execute("SELECT COUNT(*) AS n FROM operations").fetchone()["n"]
            )
            stats["successful_operations"] = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM operations WHERE success = 1"
                ).fetchone()["n"]
            )
            stats["failed_operations"] = (
                stats["total_operations"] - stats["successful_operations"]
            )

            if stats["total_operations"] > 0:
                stats["success_rate"] = round(
                    stats["successful_operations"] / stats["total_operations"] * 100,
                    2,
                )
            else:
                stats["success_rate"] = 0.0

            row = conn.execute(
                "SELECT AVG(execution_time) AS v FROM operations WHERE success = 1"
            ).fetchone()
            stats["avg_execution_time"] = round(float(row["v"] or 0.0), 3)

            stats["total_feedback"] = int(
                conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
            )

            row = conn.execute("SELECT AVG(rating) AS v FROM feedback").fetchone()
            stats["avg_rating"] = round(float(row["v"] or 0.0), 2)

            # حجم قاعدة البيانات
            stats["db_size_mb"] = 0.0
            try:
                if self.backend == "postgresql":
                    row = conn.execute(
                        "SELECT pg_database_size(current_database()) AS size"
                    ).fetchone()
                    stats["db_size_mb"] = round(float(row["size"]) / 1024 / 1024, 3)
                else:
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
                SELECT user_request, COUNT(*) AS count
                FROM operations
                GROUP BY user_request
                ORDER BY count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {"request": d["user_request"], "count": int(d["count"])}
            for d in self._rows_to_dicts(rows)
        ]

    # ========================================================
    # EXPORT — تصدير البيانات
    # ========================================================
    def export_to_json(
        self,
        output_path: str | Path,
        include_operations: bool = True,
        include_feedback: bool = True,
    ) -> Path:
        """يصدّر محتوى قاعدة البيانات إلى JSON."""
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
            rows = conn.execute("SELECT * FROM sessions").fetchall()
            data["sessions"] = self._rows_to_dicts(rows)

            rows = conn.execute("SELECT * FROM datasets").fetchall()
            data["datasets"] = self._rows_to_dicts(rows)

            if include_operations:
                rows = conn.execute("SELECT * FROM operations").fetchall()
                data["operations"] = self._rows_to_dicts(rows)

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
        """يصدّر كل جدول إلى ملف CSV منفصل ويعيد {table_name: file_path}."""
        import csv

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        exported: dict[str, Path] = {}
        tables = ["sessions", "datasets", "operations", "feedback"]

        with self._connect() as conn:
            for table in tables:
                rows = self._rows_to_dicts(
                    conn.execute(f"SELECT * FROM {table}").fetchall()
                )
                if not rows:
                    continue

                csv_path = output_dir / f"{table}.csv"
                fieldnames = list(rows[0].keys())

                with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(row)

                exported[table] = csv_path
                logger.info("📤 تم تصدير %s → %s", table, csv_path)

        return exported

    # ========================================================
    # CLEANUP — تنظيف
    # ========================================================
    def clear_all(self, confirm: bool = False) -> bool:
        """يحذف كل البيانات (بحذر!). يتطلب confirm=True."""
        if not confirm:
            raise ValueError("⚠️ لحذف كل البيانات، مرّر confirm=True")

        with self._connect() as conn:
            if self.backend == "postgresql":
                conn.execute(clear_all_sql(self.backend))
            else:
                conn.execute("DELETE FROM feedback")
                conn.execute("DELETE FROM operations")
                conn.execute("DELETE FROM datasets")
                conn.execute("DELETE FROM sessions")
                conn.execute("DELETE FROM sqlite_sequence")
            conn.commit()

        logger.warning("🧹 تم حذف كل البيانات من قاعدة البيانات")
        return True

    def cleanup_old_operations(self, days: int = 30) -> int:
        """يحذف العمليات الأقدم من N يوم ويعيد عددها."""
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
        """يعيد ضغط قاعدة SQLite. على PostgreSQL (Neon) تتولاه الخدمة تلقائياً."""
        if self.backend == "postgresql":
            logger.info("VACUUM غير مطلوب: Neon يديره تلقائياً")
            return
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
# اختبار مباشر (SQLite مؤقت فقط — لا يلمس قاعدة الإنتاج)
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = Path(tmp_dir) / "test_memory.db"
        mem = MemoryStore(test_db)
        print(f"\n📁 قاعدة اختبار: {test_db} ({mem.backend})")

        sid = mem.create_session("جلسة اختبار", {"user": "test"})
        print(f"[1] Session ID: {sid} | الاسم: {mem.get_session(sid).name}")

        csv_file = Path(tmp_dir) / "data.csv"
        csv_file.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
        did = mem.save_dataset(
            filename="data.csv", file_path=csv_file, rows=2, cols=3,
            columns_info={"a": "int", "b": "int", "c": "int"}, session_id=sid,
        )
        print(f"[2] Dataset ID: {did} | عدد الملفات: {len(mem.list_datasets())}")

        op1 = mem.log_operation(
            user_request="احسب متوسط العمود a", generated_code="avg = df['a'].mean()",
            result_summary="المتوسط = 2.5", success=True, execution_time=0.5,
            dataset_id=did, session_id=sid,
        )
        print(f"[3] Operation ID: {op1}")

        mem.add_feedback(op1, rating=5, comment="ممتاز")
        mem.add_feedback(op1, rating=4, comment="جيد")
        print(f"[4] متوسط التقييم: {mem.get_average_rating(op1)}")

        print(f"[5] أمثلة few-shot: {len(mem.get_few_shot_examples('احسب متوسط العمود a'))}")
        print(f"[6] الإحصائيات: {mem.get_statistics()}")

        mem.clear_all(confirm=True)
        print(f"[7] عمليات متبقية: {mem.get_statistics()['total_operations']}")

    print("\n✅ اكتمل اختبار memory.py")