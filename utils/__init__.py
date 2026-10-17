"""
ui/__init__.py — عقد الحالة المشتركة (session_state) بين مكوّنات الواجهة.

المفاتيح المتفق عليها:
    lang              : "ar" | "en"
    session_id        : int | None   (جلسة قاعدة البيانات الحالية)
    dataset_id        : int | None   (الملف الحالي في قاعدة البيانات)
    df                : pd.DataFrame | None
    data_path         : str | None   (مسار الملف المحفوظ في data/uploads)
    filename          : str | None
    messages          : list[dict]   (سجل المحادثة المعروض)
    last_operation_id : int | None   (لربط التقييم بآخر عملية)
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

STATE_DEFAULTS: dict[str, Any] = {
    "lang": None,
    "session_id": None,
    "dataset_id": None,
    "df": None,
    "data_path": None,
    "filename": None,
    "messages": [],
    "last_operation_id": None,
}


def init_state() -> None:
    """يهيّئ المفاتيح الناقصة فقط، ولا يلمس الموجود."""
    import streamlit as st

    from config import CONFIG

    for key, value in STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)
    if st.session_state["lang"] is None:
        st.session_state["lang"] = CONFIG.ui.default_language


def ensure_session() -> int:
    """ينشئ جلسة في قاعدة البيانات إن لم توجد، ويعيد معرّفها."""
    import streamlit as st

    from core.memory import get_memory
    from utils.i18n import t

    if st.session_state.get("session_id") is None:
        name = t("default_session_name", ts=datetime.now().strftime("%Y-%m-%d %H:%M"))
        st.session_state["session_id"] = get_memory().create_session(name=name)
    return st.session_state["session_id"]


def reset_dataset_state() -> None:
    """يمسح كل ما يتعلق بالملف الحالي والمحادثة (عند تغيير الملف)."""
    import streamlit as st

    for key in ("dataset_id", "df", "data_path", "filename", "last_operation_id"):
        st.session_state[key] = None
    st.session_state["messages"] = []