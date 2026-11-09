"""app.py — secure Streamlit application entry point."""
from __future__ import annotations

import importlib
import io
import logging
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _force_utf8_std_streams() -> None:
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
                    sys,
                    name,
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

import streamlit as st

from config import CONFIG, get_setting, validate_config
from core.auth import AuthStore, is_authenticated, require_role, session_logout
from ui import ensure_session, init_state
from ui.theme import apply_theme
from utils.i18n import SUPPORTED_LANGS, get_lang, normalize_language, rtl_css, t

logger = logging.getLogger(__name__)

_FORECAST_TAB_LABELS = {"ar": "🔮 التنبؤات", "en": "🔮 Forecast"}


def _render(module_name: str, func_name: str, fallback: Callable[[], None] | None = None) -> None:
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
    st.selectbox(
        t("language"),
        options=list(SUPPORTED_LANGS),
        format_func=lambda code: SUPPORTED_LANGS[code],
        key="language",
        on_change=lambda: st.session_state.__setitem__("lang", st.session_state.get("language")),
    )
    st.info(t("under_construction", module="ui.sidebar", func="render_sidebar"))


def _admin_bootstrap_notice() -> None:
    reason = st.session_state.get("admin_bootstrap_error")
    if not reason:
        return

    notices = {
        "not_configured": t("auth.admin_bootstrap_missing"),
        "password_policy": t("auth.admin_bootstrap_failed_password_policy"),
        "invalid_email": t("auth.admin_bootstrap_failed_invalid_email"),
        "db_error": t("auth.admin_bootstrap_failed_db_error"),
    }
    st.warning(notices.get(reason, t("auth.admin_bootstrap_failed", reason=reason)))


def _logout_current_user() -> None:
    session_logout(st.session_state)
    st.rerun()


def main() -> None:
    init_state()
    raw_lang = st.session_state.get("language") or st.session_state.get("lang") or CONFIG.ui.default_language
    normalized = normalize_language(raw_lang)
    st.session_state["lang"] = normalized
    st.session_state["language"] = normalized

    try:
        bootstrap_result = AuthStore().bootstrap_admin()
    except Exception:
        logger.warning("Admin bootstrap failed unexpectedly during app startup", exc_info=True)
        bootstrap_result = "db_error"

    if isinstance(bootstrap_result, str):
        st.session_state["admin_bootstrap_error"] = bootstrap_result
    else:
        st.session_state.pop("admin_bootstrap_error", None)

    st.markdown(rtl_css(), unsafe_allow_html=True)
    apply_theme(get_lang())

    user = st.session_state.get("user")
    if not is_authenticated(st.session_state, user):
        _admin_bootstrap_notice()
        from ui.auth_page import render_auth_page

        render_auth_page()
        st.stop()

    if user.get("must_change_password"):
        from ui.auth_page import render_password_change_required

        render_password_change_required(user)
        st.stop()

    if not require_role(["user", "admin"], st.session_state, user):
        st.warning("Access denied")
        session_logout(st.session_state)
        st.stop()

    try:
        ensure_session()
    except Exception as exc:
        st.error(t("db_error"))
        logger.exception("Session startup failed")
        st.exception(exc)
        st.stop()

    with st.sidebar:
        st.header(t("sidebar_title"))
        _render("ui.sidebar", "render_sidebar", fallback=_fallback_sidebar)

    st.title(f"{CONFIG.ui.page_icon} {t('app_title')}")
    st.caption(t("app_subtitle"))

    ok, errors = validate_config()
    if not ok:
        for err in errors:
            st.warning(err)

    forecast_label = _FORECAST_TAB_LABELS.get(get_lang(), _FORECAST_TAB_LABELS["en"])
    tab_chat, tab_forecast, tab_dash = st.tabs([t("tab_chat"), forecast_label, t("tab_dashboard")])

    with tab_chat:
        _render("ui.chat", "render_chat")
    with tab_forecast:
        _render("ui.forecast", "render_forecast")
    with tab_dash:
        _render("ui.dashboard", "render_dashboard")


if __name__ == "__main__":
    main()
