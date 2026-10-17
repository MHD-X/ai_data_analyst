"""
core/security.py — أدوات الأمان والخصوصية

1) mask_df_for_llm   : إخفاء PII قبل إرسال وصف البيانات إلى مزوّد LLM
2) save_encrypted    : تخزين الملفات المرفوعة مشفّرة (Fernet) على القرص
3) temp_csv_for_sandbox : نسخة UTF-8 مؤقتة للـ sandbox تُحذف دائماً بعد التنفيذ
4) redact_text       : تنظيف نصوص الطلبات/الأكواد قبل حفظها في الذاكرة

توليد المفتاح (مرة واحدة) ثم وضعه في .env أو Streamlit Secrets:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import io
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from config import UPLOADS_DIR, get_setting

MASK = "<MASKED>"

# ---------- PII ----------
_EXACT_PII = {"name", "الاسم", "اسم"}
_PII_HINTS = (
    "full_name", "fullname", "customer_name", "student_name",
    "الاسم الكامل", "اسم العميل", "اسم الطالب",
    "phone", "mobile", "هاتف", "جوال", "واتساب", "whatsapp",
    "email", "بريد", "address", "عنوان",
)
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_PHONE = re.compile(r"(?<!\d)\+?\d{9,15}(?!\d)")


def _is_pii_column(name: str, s: pd.Series) -> bool:
    n = str(name).strip().lower()
    if n in _EXACT_PII or any(h in n for h in _PII_HINTS):
        return True
    if s.dtype == object:
        sample = s.dropna().astype(str).head(100)
        if len(sample) and (
            sample.str.contains(_RE_EMAIL).mean() > 0.3
            or sample.str.contains(_RE_PHONE).mean() > 0.3
        ):
            return True
    return False


def mask_df_for_llm(df: pd.DataFrame) -> pd.DataFrame:
    """نسخة من df تُخفى فيها أعمدة PII. تُستخدم فقط لبناء وصف البيانات للـ LLM."""
    out = df.copy()
    for c in df.columns:
        if _is_pii_column(c, df[c]):
            out[c] = MASK
    return out


def redact_text(text: str) -> str:
    """يمسح الإيميلات وأرقام الهواتف من نص قبل تخزينه."""
    return _RE_PHONE.sub("<PHONE>", _RE_EMAIL.sub("<EMAIL>", text or ""))


# ---------- أسماء الملفات ----------
_SAFE = re.compile(r"[^\w\-]+", re.UNICODE)


def safe_filename(name: str) -> str:
    """يمنع path traversal ويمنع الكتابة فوق ملف مستخدم آخر (اسم فريد)."""
    p = Path(name).name
    stem = _SAFE.sub("_", Path(p).stem)[:80] or "file"
    return f"{stem}_{uuid.uuid4().hex[:8]}{Path(p).suffix.lower()}"


# ---------- التشفير ----------
def _cipher():
    from cryptography.fernet import Fernet

    key = get_setting("DATA_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("DATA_ENCRYPTION_KEY غير موجود (انظر تعليمات توليد المفتاح أعلى الملف).")
    return Fernet(key.encode())


def save_encrypted(data: bytes, original_name: str) -> Path:
    """يحفظ bytes مشفّرة باسم آمن + .enc ويعيد المسار."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS_DIR / (safe_filename(original_name) + ".enc")
    dest.write_bytes(_cipher().encrypt(data))
    return dest


def load_encrypted_df(path: str | Path) -> pd.DataFrame:
    """يفك التشفير في الذاكرة فقط ويعيد DataFrame (دون كتابة نسخة مكشوفة)."""
    path = Path(path)
    raw = _cipher().decrypt(path.read_bytes())
    ext = path.with_suffix("").suffix.lower()  # x.csv.enc -> .csv
    if ext == ".csv":
        for enc in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(raw), encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("تعذّر فك ترميز CSV")
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(io.BytesIO(raw))
    raise ValueError(f"امتداد غير مدعوم: {ext}")


# ---------- نسخة مؤقتة للـ sandbox ----------
@contextmanager
def temp_csv_for_sandbox(df: pd.DataFrame) -> Iterator[str]:
    """
    يكتب df كـ CSV (UTF-8) في مجلد مؤقت خاص (صلاحيات 0700) ويحذفه دائماً.
    يحل أيضاً مشكلة ترميز cp1256 داخل الـ sandbox (الذي يقرأ CSV بلا fallback).
    """
    tmp = Path(tempfile.mkdtemp(prefix="bd_"))
    try:
        p = tmp / "data.csv"
        df.to_csv(p, index=False, encoding="utf-8")
        yield str(p)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)