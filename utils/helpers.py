"""
utils/helpers.py — دوال مساعدة عامة
General-purpose helper functions used across the project.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# 1. بصمة الملفات
# ============================================================
def hash_file(file_path: str | Path, algorithm: str = "sha256") -> str:
    """
    يحسب بصمة (hash) لملف.
    مفيد لتحديد إن كان الملف نفسه رُفع سابقاً.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"الملف غير موجود: {path}")

    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_string(text: str, algorithm: str = "sha256") -> str:
    """يحسب بصمة نص."""
    h = hashlib.new(algorithm)
    h.update(text.encode("utf-8"))
    return h.hexdigest()


# ============================================================
# 2. وصف DataFrames للـ LLM
# ============================================================
def describe_dataframe(
    df: pd.DataFrame,
    max_columns: int = 30,
    sample_rows: int = 5,
) -> str:
    """
    ينتج وصفاً نصياً مختصراً لـ DataFrame ليُرسل للـ LLM.
    """
    lines: list[str] = []
    lines.append(f"📊 الشكل: {df.shape[0]} صف × {df.shape[1]} عمود")
    lines.append("")

    lines.append("📋 الأعمدة وأنواعها:")
    for i, col in enumerate(df.columns[:max_columns]):
        dtype = str(df[col].dtype)
        nulls = int(df[col].isnull().sum())
        null_pct = (nulls / len(df) * 100) if len(df) > 0 else 0
        unique = df[col].nunique()
        lines.append(
            f"  {i+1}. {col!r} | نوع: {dtype} | "
            f"قيم فارغة: {nulls} ({null_pct:.1f}%) | "
            f"قيم فريدة: {unique}"
        )

    if len(df.columns) > max_columns:
        lines.append(f"  ... و {len(df.columns) - max_columns} عمود إضافي")

    lines.append("")
    lines.append(f"👀 أول {sample_rows} صفوف:")
    try:
        sample_str = df.head(sample_rows).to_string(max_colwidth=30)
        lines.append(sample_str)
    except Exception as e:
        lines.append(f"(فشل عرض العينة: {e})")

    # إحصائيات للأعمدة الرقمية
    numeric_cols = df.select_dtypes(include=["number"]).columns
    if len(numeric_cols) > 0:
        lines.append("")
        lines.append("📈 إحصائيات الأعمدة الرقمية:")
        try:
            stats = df[numeric_cols].describe().round(2)
            lines.append(stats.to_string())
        except Exception:
            pass

    return "\n".join(lines)


def get_dataframe_summary(df: pd.DataFrame) -> dict[str, Any]:
    """يعيد ملخصاً منظّماً (dict) عن DataFrame."""
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": [str(c) for c in df.columns],
        "dtypes": {str(c): str(df[c].dtype) for c in df.columns},
        "null_counts": {str(c): int(df[c].isnull().sum()) for c in df.columns},
        "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
    }


# ============================================================
# 3. JSON آمن
# ============================================================
def safe_json_loads(text: str, default: Any = None) -> Any:
    """يحلّل JSON بأمان، يعيد default عند الفشل."""
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(obj: Any, default: str = "{}") -> str:
    """يحوّل كائن إلى JSON بأمان."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return default


# ============================================================
# 4. معالجة النصوص
# ============================================================
def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """يقطع نصاً طويلاً."""
    if not text or len(text) <= max_length:
        return text or ""
    return text[: max_length - len(suffix)] + suffix


def clean_code_block(text: str) -> str:
    """
    يستخرج الكود من كتلة markdown (```python ... ```).
    """
    if not text:
        return ""

    # نمط ```python ... ```
    pattern = r"```(?:python|py)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    if matches:
        return matches[0].strip()

    # لو لم توجد كتلة، نعيد النص كما هو
    return text.strip()

# ============ نهاية الجزء 1/2 — أكمل بالجزء التالي ============
# ============================================================
# 5. الوقت والتواريخ
# ============================================================
def now_iso() -> str:
    """يعيد الوقت الحالي بصيغة ISO 8601."""
    return datetime.now().isoformat(timespec="seconds")


def format_timestamp(dt_str: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """يحوّل نص ISO إلى تاريخ مقروء."""
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime(fmt)
    except Exception:
        return dt_str


def humanize_duration(seconds: float) -> str:
    """يحوّل الثواني إلى نص مقروء."""
    if seconds < 1:
        return f"{seconds*1000:.0f} مللي ثانية"
    if seconds < 60:
        return f"{seconds:.1f} ثانية"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes} دقيقة {secs} ثانية"


# ============================================================
# 6. الملفات
# ============================================================
def get_file_size_mb(file_path: str | Path) -> float:
    """يعيد حجم الملف بالميجابايت."""
    return Path(file_path).stat().st_size / 1024 / 1024


def get_file_extension(file_path: str | Path) -> str:
    """يعيد امتداد الملف بحروف صغيرة بدون نقطة."""
    return Path(file_path).suffix.lower().lstrip(".")


def is_supported_data_file(file_path: str | Path) -> bool:
    """يتحقق إن كان الملف مدعوماً للقراءة."""
    return get_file_extension(file_path) in {"csv", "xlsx", "xls"}


def read_data_file(file_path: str | Path) -> pd.DataFrame:
    """
    يقرأ ملف CSV أو Excel بشكل موحّد.
    """
    path = Path(file_path)
    ext = get_file_extension(path)

    if ext == "csv":
        # محاولات متعددة للترميز
        for encoding in ("utf-8", "utf-8-sig", "cp1256", "latin-1"):
            try:
                return pd.read_csv(path, encoding=encoding)
            except (UnicodeDecodeError, Exception):
                continue
        raise ValueError(f"❌ فشل قراءة الملف: {path}")

    if ext in ("xlsx", "xls"):
        return pd.read_excel(path)

    raise ValueError(f"❌ امتداد غير مدعوم: {ext}")


# ============================================================
# 7. DataFrames — عمليات مفيدة
# ============================================================
def get_dataframe_preview(df: pd.DataFrame, n: int = 5) -> str:
    """يعيد نص معاينة DataFrame."""
    try:
        return df.head(n).to_string(max_colwidth=40)
    except Exception:
        return "(فشل عرض المعاينة)"


def detect_datetime_columns(df: pd.DataFrame) -> list[str]:
    """يحاول كشف الأعمدة التي يمكن تحويلها لتواريخ."""
    candidates: list[str] = []
    for col in df.columns:
        if df[col].dtype == "object":
            try:
                sample = df[col].dropna().head(20)
                if len(sample) == 0:
                    continue
                pd.to_datetime(sample, errors="raise")
                candidates.append(str(col))
            except Exception:
                pass
    return candidates


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """قسمة آمنة (تتجنب القسمة على صفر)."""
    try:
        return a / b if b != 0 else default
    except Exception:
        return default


# ============================================================
# 8. اختبار مباشر
# ============================================================
if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("🧪 اختبار utils/helpers.py")
    print("=" * 60)

    # اختبار 1: hash
    test_str = "مرحباً بالعالم"
    h = hash_string(test_str)
    print(f"\n[1] hash_string: {h[:16]}...")

    # اختبار 2: DataFrame description
    df = pd.DataFrame({
        "name": ["Ali", "Sara", "Omar"],
        "age": [25, 30, 35],
        "salary": [5000.5, 7000.0, 9000.75],
    })
    print("\n[2] describe_dataframe:")
    print(describe_dataframe(df, sample_rows=2))

    # اختبار 3: summary
    print("\n[3] get_dataframe_summary:")
    summary = get_dataframe_summary(df)
    print(f"   Rows: {summary['rows']}, Cols: {summary['columns']}")
    print(f"   Memory: {summary['memory_usage_mb']} MB")

    # اختبار 4: JSON
    print("\n[4] safe_json:")
    _valid_json_input = '{"a": 1}'
    _parsed = safe_json_loads(_valid_json_input)
    _invalid = safe_json_loads("not json", default={})
    print(f"   Valid: {_parsed}")
    print(f"   Invalid: {_invalid}")

    # اختبار 5: clean_code_block
    print("\n[5] clean_code_block:")
    raw = "Here is code:\n```python\nimport pandas as pd\nprint('hi')\n```"
    print(f"   {clean_code_block(raw)}")

    # اختبار 6: truncate
    print("\n[6] truncate_text:")
    long_text = "a" * 100
    print(f"   {truncate_text(long_text, max_length=20)}")

    # اختبار 7: file operations
    print("\n[7] file operations:")
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as f:
        f.write("a,b,c\n1,2,3\n4,5,6\n")
        tmp_path = f.name
    print(f"   Extension: {get_file_extension(tmp_path)}")
    print(f"   Supported: {is_supported_data_file(tmp_path)}")
    print(f"   Size: {get_file_size_mb(tmp_path):.4f} MB")
    loaded = read_data_file(tmp_path)
    print(f"   Loaded shape: {loaded.shape}")

    # اختبار 8: datetime detection
    print("\n[8] detect_datetime_columns:")
    df2 = pd.DataFrame({
        "date": ["2024-01-01", "2024-02-01"],
        "value": [10, 20],
    })
    print(f"   Detected: {detect_datetime_columns(df2)}")

    # اختبار 9: humanize duration
    print("\n[9] humanize_duration:")
    print(f"   0.5s → {humanize_duration(0.5)}")
    print(f"   45s  → {humanize_duration(45)}")
    print(f"   90s  → {humanize_duration(90)}")

    print("\n" + "=" * 60)
    print("✅ اكتمل اختبار helpers.py بنجاح")
    print("=" * 60)