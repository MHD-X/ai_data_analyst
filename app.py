"""app.py — secure Streamlit application entry point."""
from __future__ import annotations

import importlib
import io
import logging
import re
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_LOGO_PATH = ROOT / "assets" / "logo.png"
_ICON_PATH = ROOT / "assets" / "icon.png"


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

from config import CONFIG, validate_config

st.set_page_config(
    page_title=CONFIG.ui.page_title,
    page_icon=str(_ICON_PATH),
    layout=CONFIG.ui.layout,
)
from core.auth import AuthStore, is_authenticated, require_role, session_logout
from ui import ensure_session, init_state
from utils.i18n import SUPPORTED_LANGS, get_lang, normalize_language, t

logger = logging.getLogger(__name__)

_FORECAST_TAB_LABELS = {"ar": "🔮 التنبؤات", "en": "🔮 Forecast"}


def _streamlit_supports_logo() -> bool:
    try:
        version = getattr(st, "__version__", "0") or "0"
        numeric = [int(part) for part in re.findall(r"\d+", version)[:3]]
        if len(numeric) >= 2:
            return tuple(numeric[:2]) >= (1, 35)
    except Exception:
        pass
    return hasattr(st, "logo")


def _render_logo_images() -> bool:
    if not _LOGO_PATH.exists() or not _ICON_PATH.exists():
        logger.warning("Logo image not found. Please add assets/logo.png and assets/icon.png")
        return False

    if _streamlit_supports_logo():
        try:
            st.logo(str(_LOGO_PATH), icon_image=str(_ICON_PATH))
            return True
        except TypeError:
            try:
                st.logo(image=str(_LOGO_PATH), icon_image=str(_ICON_PATH))
                return True
            except Exception:
                pass
        except Exception:
            pass

    st.image(str(_LOGO_PATH), width=220)
    return True


def _render_main_page_logo() -> None:
    if not _LOGO_PATH.exists():
        logger.warning("Logo image not found. Please add assets/logo.png and assets/icon.png")
        return
    st.image(str(_LOGO_PATH), width=220)


@st.cache_resource(show_spinner=False)
def _bootstrap_once() -> str | None:
    try:
        result = AuthStore().bootstrap_admin()
    except Exception:
        logger.warning("Admin bootstrap failed", exc_info=True)
        return "db_error"
    return result if isinstance(result, str) else None


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

    reason = _bootstrap_once()
    if reason:
        st.session_state["admin_bootstrap_error"] = reason
    else:
        st.session_state.pop("admin_bootstrap_error", None)

    _render_logo_images()

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

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last = st.session_state.get("last_seen")
    if last and now - last > timedelta(minutes=30):
        session_logout(st.session_state)
        st.warning("Session expired. Please sign in again.")
        st.rerun()
    st.session_state["last_seen"] = now

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

    _render_main_page_logo()
    st.title(t("app_title"))
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
