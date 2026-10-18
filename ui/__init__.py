"""
ui/__init__.py — تهيئة الحالة المشتركة ومكوّنات الواجهة.

يُستورد من app.py:
    from ui import ensure_session, init_state

ويصدّر المكوّنات الرئيسية للاستخدام الخارجي.

ملاحظة: دوال إدارة الـ DataFrame موجودة هنا أيضاً لاستخدامها من أي وحدة
واجهة (sidebar, chat, dashboard) دون تكرار الكود.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from config import CONFIG
from core.memory import get_memory
from utils.helpers import now_iso


# ============================================================
# تهيئة الحالة
# ============================================================
def init_state() -> None:
    """
    يهيّئ مفاتيح st.session_state الافتراضية (idempotent).
    يُستدعى مرة واحدة من app.py عند بدء التطبيق.
    """
    defaults: dict[str, Any] = {
        # اللغة
        "lang": CONFIG.ui.default_language,
        # الملف الحالي
        "df": None,
        "df_loaded": False,
        "data_path": None,
        "dataset_id": None,
        "dataset_name": None,
        # الجلسة
        "session_id": None,
        # المحادثة
        "messages": [],
        "last_operation_id": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


# ============================================================
# إدارة الـ DataFrame (المصدر الوحيد للحقيقة)
# ============================================================
def set_dataframe(
    df: pd.DataFrame | None,
    *,
    path: str | None = None,
    name: str | None = None,
    dataset_id: int | None = None,
    reset_messages: bool = False,
) -> None:
    """
    يخزّن DataFrame في session_state ويُحدّث كل المفاتيح المرتبطة.

    Args:
        df: DataFrame أو None
        path: مسار الملف على القرص
        name: اسم الملف الأصلي
        dataset_id: معرّف dataset في الذاكرة
        reset_messages: هل نُصفّر المحادثة؟ (نعم عند رفع ملف جديد)
    """
    ss = st.session_state
    ss["df"] = df
    ss["df_loaded"] = bool(
        df is not None
        and not (hasattr(df, "empty") and df.empty)
    )
    if path is not None:
        ss["data_path"] = path
    if name is not None:
        ss["dataset_name"] = name
    if dataset_id is not None:
        ss["dataset_id"] = dataset_id
    if reset_messages:
        ss["messages"] = []
        ss["last_operation_id"] = None


def clear_dataframe() -> None:
    """
    يحذف DataFrame من session_state (عند حذف الملف).
    يُصفّر أيضاً المحادثة لأنها كانت مرتبطة بالملف.
    """
    ss = st.session_state
    ss["df"] = None
    ss["df_loaded"] = False
    ss["data_path"] = None
    ss["dataset_id"] = None
    ss["dataset_name"] = None
    ss["messages"] = []
    ss["last_operation_id"] = None


def get_dataframe() -> pd.DataFrame | None:
    """يعيد DataFrame الحالي (أو None)."""
    return st.session_state.get("df")


def has_dataframe() -> bool:
    """هل يوجد DataFrame محمّل وجاهز؟"""
    return bool(st.session_state.get("df_loaded"))


# ============================================================
# إدارة الجلسة
# ============================================================
def ensure_session() -> int:
    """
    يضمن وجود جلسة نشطة في قاعدة البيانات.
    يعيد session_id (ينشئ جلسة جديدة إن لم توجد).
    """
    sid = st.session_state.get("session_id")
    if sid is not None:
        return sid

    memory = get_memory()
    sid = memory.create_session(
        name=f"Session {now_iso()}",
        metadata={"source": "streamlit"},
    )
    st.session_state["session_id"] = sid
    return sid


# ============================================================
# Exports — يجب أن تكون في النهاية لتجنب circular imports
# ============================================================
# noqa: E402 لأننا نستورد بعد تعريف الدوال (نتجنب circular imports)
from ui.chat import render_chat  # noqa: E402
from ui.dashboard import render_dashboard  # noqa: E402
from ui.sidebar import render_sidebar  # noqa: E402


__all__ = [
    # تهيئة
    "init_state",
    "ensure_session",
    # إدارة DataFrame
    "set_dataframe",
    "clear_dataframe",
    "get_dataframe",
    "has_dataframe",
    # المكوّنات
    "render_chat",
    "render_dashboard",
    "render_sidebar",
]