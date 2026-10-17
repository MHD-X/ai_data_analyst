"""
ui/sidebar.py — الشريط الجانبي

المسؤوليات:
    1. اختيار اللغة (ar/en)
    2. رفع ملف البيانات (CSV/Excel) + كشف التكرار بـ hash
    3. عرض معلومات الملف الحالي (صفوف/أعمدة/معاينة)
    4. إدارة الجلسات (عرض/إنشاء/حذف)
    5. أدوات: مسح المحادثة، إحصائيات الذاكرة

يُستدعى من app.py داخل `with st.sidebar:`.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import UPLOADS_DIR
from core.memory import get_memory
from utils.helpers import (
    get_dataframe_summary,
    get_file_size_mb,
    hash_file,
    read_data_file,
)
from utils.i18n import SUPPORTED_LANGS, t


# ============================================================
# أدوات مساعدة داخلية
# ============================================================
def _set_dataframe_in_state(
    df: pd.DataFrame | None,
    *,
    path: str | None = None,
    name: str | None = None,
    dataset_id: int | None = None,
    reset_messages: bool = False,
) -> None:
    """
    يخزّن DataFrame في session_state (المصدر الوحيد للحقيقة).
    استدعها بعد أي رفع/اختيار ملف.

    Args:
        df: DataFrame أو None
        path: مسار الملف على القرص
        name: اسم الملف الأصلي
        dataset_id: معرّف dataset في الذاكرة
        reset_messages: هل نُصفّر المحادثة؟
    """
    ss = st.session_state
    ss["df"] = df
    ss["df_loaded"] = df is not None and not (
        hasattr(df, "empty") and df.empty
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


def _clear_dataframe_from_state() -> None:
    """يحذف DataFrame من session_state."""
    ss = st.session_state
    ss["df"] = None
    ss["df_loaded"] = False
    ss["data_path"] = None
    ss["dataset_id"] = None
    ss["dataset_name"] = None
    ss["messages"] = []
    ss["last_operation_id"] = None


# ============================================================
# اختيار اللغة
# ============================================================
def _render_language() -> None:
    st.selectbox(
        t("language"),
        options=list(SUPPORTED_LANGS),
        format_func=lambda code: SUPPORTED_LANGS[code],
        key="lang",
    )


# ============================================================
# رفع الملف
# ============================================================
def _save_uploaded_file(uploaded) -> Path:
    """يحفظ الملف المرفوع على القرص ويعيد مساره."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS_DIR / uploaded.name
    with open(dest, "wb") as f:
        f.write(uploaded.getbuffer())
    return dest


def _handle_upload(uploaded) -> None:
    """
    يعالج ملفاً مرفوعاً:
      1. يحفظه على القرص
      2. يقرأه كـ DataFrame
      3. يخزّنه في session_state (دائماً — حتى لو موجود سابقاً)
      4. يسجّله في الذاكرة
    """
    ss = st.session_state
    memory = get_memory()

    # 1) حفظ على القرص
    try:
        path = _save_uploaded_file(uploaded)
    except Exception as exc:
        st.error(t("file_error", error=str(exc)))
        return

    # 2) قراءة DataFrame (دائماً — حتى لو الملف مرفوع سابقاً،
    #    لأن الذاكرة تحفظ metadata فقط وليس الملف نفسه)
    try:
        df = read_data_file(path)
    except Exception as exc:
        st.error(t("file_error", error=str(exc)))
        return

    # 3) حساب البصمة
    try:
        fhash = hash_file(path)
    except Exception:
        fhash = ""

    # 4) تسجيل في الذاكرة (أو استرجاع dataset_id من السجل القديم)
    dataset_id: int | None = None
    try:
        existing = memory.get_dataset_by_hash(fhash) if fhash else None
        if existing is not None:
            dataset_id = existing.id
            st.info(t("file_already_known"))
        else:
            columns_info = {
                str(c): str(df[c].dtype) for c in df.columns
            }
            dataset_id = memory.save_dataset(
                filename=uploaded.name,
                file_path=str(path),
                rows=len(df),
                cols=len(df.columns),
                columns_info=columns_info,
                session_id=ss.get("session_id"),
            )
    except Exception as exc:
        # فشل التسجيل لا يجب أن يوقف التطبيق
        st.warning(f"⚠️ تعذّر تسجيل الملف في الذاكرة: {exc}")

    # 5) خزّن DataFrame في session_state (مهما كان الحال)
    _set_dataframe_in_state(
        df,
        path=str(path),
        name=uploaded.name,
        dataset_id=dataset_id,
        reset_messages=True,
    )

    # 6) تأكيد
    st.success(t("file_loaded", name=uploaded.name))
    st.rerun()


def _render_uploader() -> None:
    uploaded = st.file_uploader(
        t("upload_file"),
        type=["csv", "xlsx", "xls"],
        help=t("upload_help"),
        key="file_uploader",
    )
    if uploaded is None:
        return

    # نمنع إعادة المعالجة لنفس الملف في نفس الجلسة
    # (استخدمنا اسم + حالة df_loaded للتحقق)
    last_name = st.session_state.get("dataset_name")
    df_loaded = st.session_state.get("df_loaded", False)

    if last_name == uploaded.name and df_loaded:
        return

    _handle_upload(uploaded)


# ============================================================
# معلومات الملف الحالي
# ============================================================
def _render_file_info() -> None:
    df: pd.DataFrame | None = st.session_state.get("df")
    if df is None:
        return

    name = st.session_state.get("dataset_name") or "-"
    st.markdown(f"**📄 {name}**")

    summary = get_dataframe_summary(df)
    rows = summary.get("rows", 0)
    cols = summary.get("columns", 0)

    col1, col2 = st.columns(2)
    col1.metric(t("rows_label"), rows)
    col2.metric(t("cols_label"), cols)

    # زر حذف الملف
    if st.button(t("remove_file"), use_container_width=True, key="remove_file_btn"):
        _clear_dataframe_from_state()
        st.rerun()

    with st.expander(t("preview")):
        st.dataframe(df.head(10), use_container_width=True)

    with st.expander(t("columns")):
        st.write(", ".join(map(str, df.columns)))


# ============================================================
# إدارة الجلسات
# ============================================================
def _render_sessions() -> None:
    memory = get_memory()
    ss = st.session_state

    st.markdown(f"**🗂️ {t('sessions')}**")

    if st.button(t("new_session"), use_container_width=True, key="new_session_btn"):
        try:
            sid = memory.create_session(
                name=t("default_session_name", ts="").strip() or "Session"
            )
            ss["session_id"] = sid
            ss["messages"] = []
            st.rerun()
        except Exception as exc:
            st.error(f"❌ تعذّر إنشاء جلسة: {exc}")

    try:
        sessions = memory.list_sessions(limit=10)
    except Exception:
        sessions = []

    current = ss.get("session_id")
    for s in sessions:
        marker = "🟢" if s.id == current else "⚪"
        st.caption(f"{marker} #{s.id} — {s.name}")

    # حذف الجلسة الحالية مع تأكيد
    if current:
        with st.expander(t("delete_session")):
            st.warning(t("delete_confirm"))
            if st.button(
                t("confirm_delete"),
                use_container_width=True,
                key="confirm_delete_session",
            ):
                try:
                    memory.delete_session(current)
                    ss["session_id"] = None
                    ss["messages"] = []
                    st.rerun()
                except Exception:
                    st.error(t("db_error"))


# ============================================================
# أدوات
# ============================================================
def _render_tools() -> None:
    ss = st.session_state

    if st.button(t("clear_chat"), use_container_width=True, key="clear_chat_btn"):
        ss["messages"] = []
        ss["last_operation_id"] = None
        st.rerun()

    with st.expander("🧹 " + t("dash_title")):
        try:
            stats = get_memory().get_statistics()
            st.caption(f"📊 {t('total_operations')}: {stats.get('total_operations', 0)}")
            st.caption(f"📁 {t('total_datasets')}: {stats.get('total_datasets', 0)}")
            st.caption(f"💬 {t('total_sessions')}: {stats.get('total_sessions', 0)}")
            st.caption(f"✅ {t('success_rate')}: {stats.get('success_rate', 0)}%")
        except Exception:
            st.caption("—")


# ============================================================
# نقطة الدخول
# ============================================================
def render_sidebar() -> None:
    """يرسم الشريط الجانبي كاملاً. يُستدعى من app.py داخل `with st.sidebar:`."""
    _render_language()
    st.divider()

    _render_uploader()
    _render_file_info()
    st.divider()

    _render_sessions()
    st.divider()

    _render_tools()