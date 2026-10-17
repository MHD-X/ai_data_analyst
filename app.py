"""
app.py — نقطة الدخول (Streamlit)
تشغيل:  streamlit run app.py

العقد مع مكوّنات الواجهة (كل دالة بلا معاملات وتقرأ/تكتب st.session_state):
    ui.sidebar.render_sidebar()      # تُستدعى داخل with st.sidebar
    ui.chat.render_chat()            # داخل تبويب المحادثة
    ui.dashboard.render_dashboard()  # داخل تبويب لوحة المعلومات
"""
from __future__ import annotations

import importlib
import io
import sys
from typing import Callable

# ============================================================
# [إصلاح UnicodeEncodeError] إجبار stdout/stderr على UTF-8
# يجب أن يكون قبل أي استيراد آخر — خاصة streamlit.
# ============================================================
def _force_utf8_std_streams() -> None:
    """يضمن أن stdout/stderr يستخدمان UTF-8 (مهم على Windows بالعربية)."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if enc.replace("-", "") == "utf8":
                continue
            if hasattr(stream, "buffer"):
                setattr(
                    sys, name,
                    io.TextIOWrapper(
                        stream.buffer,
                        encoding="utf-8",
                        errors="replace",
                        line_buffering=True,
                    ),
                )
        except Exception:
            pass


_force_utf8_std_streams()
# ============================================================

import streamlit as st

from config import CONFIG, validate_config

# يجب أن يكون أول أمر Streamlit في السكربت
st.set_page_config(
    page_title=CONFIG.ui.page_title,
    page_icon=CONFIG.ui.page_icon,
    layout=CONFIG.ui.layout,
    initial_sidebar_state="expanded",
)

from ui import ensure_session, init_state  # noqa: E402
from utils.i18n import SUPPORTED_LANGS, rtl_css, t  # noqa: E402


def _render(
    module_name: str,
    func_name: str,
    fallback: Callable[[], None] | None = None,
) -> None:
    """يحمّل وحدة واجهة ويستدعي دالتها، ويعرض رسالة واضحة بدل انهيار التطبيق."""
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        st.error(t("module_load_error", module=module_name))
        st.exception(exc)
        return

    fn = getattr(module, func_name, None)
    if fn is None:
        if fallback is not None:
            fallback()
        else:
            st.info(t("under_construction", module=module_name, func=func_name))
        return
    fn()


def _fallback_sidebar() -> None:
    """شريط جانبي مؤقت (اختيار اللغة فقط) حتى يكتمل ui/sidebar.py."""
    st.selectbox(
        t("language"),
        options=list(SUPPORTED_LANGS),
        format_func=lambda code: SUPPORTED_LANGS[code],
        key="lang",
    )
    st.info(t("under_construction", module="ui.sidebar", func="render_sidebar"))


def main() -> None:
    init_state()

    try:
        ensure_session()
    except Exception as exc:
        st.error(t("db_error"))
        st.exception(exc)
        st.stop()

    st.markdown(rtl_css(), unsafe_allow_html=True)

    with st.sidebar:
        st.header(t("sidebar_title"))
        _render("ui.sidebar", "render_sidebar", fallback=_fallback_sidebar)

    st.title(f"{CONFIG.ui.page_icon} {t('app_title')}")
    st.caption(t("app_subtitle"))

    ok, errors = validate_config()
    if not ok:
        for err in errors:
            st.warning(err)

    tab_chat, tab_dash = st.tabs([t("tab_chat"), t("tab_dashboard")])
    with tab_chat:
        _render("ui.chat", "render_chat")
    with tab_dash:
        _render("ui.dashboard", "render_dashboard")


if __name__ == "__main__":
    main()