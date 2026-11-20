from __future__ import annotations

import streamlit as st

from config import get_setting
from core.auth import AuthStore, login, register, request_password_reset, resend_code, reset_password, verify_email
from utils.i18n import is_rtl, t


def _user_session_payload(user: dict | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "role": user.get("role", "user"),
        "must_change_password": int(user.get("must_change_password", 0)),
    }


def _dev_code_notice(code: str | None) -> None:
    if code and get_setting("AUTH_DEV_SHOW_CODE", "0") == "1":
        st.info(f"DEV CODE: {code}")


def _logout() -> None:
    for key in list(st.session_state.keys()):
        if key != "lang":
            del st.session_state[key]
    st.rerun()


def _auth_css() -> str:
    return """
    <style>
      .auth-shell {{
        max-width: 760px;
        margin: 1.25rem auto;
      }}
      .auth-card {{
        max-width: 720px;
        margin: auto;
      }}
      .auth-title {{
        font-size: clamp(1.8rem, 4vw, 2.6rem);
        font-weight: 800;
      }}
      .auth-subtitle {{
        color: color-mix(in srgb, currentColor 68%, transparent);
      }}
      @media (max-width: 760px) {{
        .auth-shell {{
          margin: 0.5rem auto;
        }}
      }}
    </style>
    """


def _render_login_form() -> None:
    with st.form("auth_login_form"):
        email = st.text_input(t("auth.email"), key="auth_login_email")
        password = st.text_input(t("auth.password"), type="password", key="auth_login_password")
        submitted = st.form_submit_button(t("auth.login"), type="primary", use_container_width=True)
    if submitted:
        result = login(email, password)
        if result.ok:
            st.session_state["user"] = _user_session_payload(result.user)
            st.success(t(result.message_key))
            st.rerun()
        else:
            st.error(t(result.message_key))


def _render_register_form() -> None:
    if get_setting("SIGNUP_OPEN", "0") != "1":
        st.warning(t("auth.signup_closed"))
        return
    with st.form("auth_register_form"):
        email = st.text_input(t("auth.email"), key="auth_register_email")
        display_name = st.text_input(t("auth.display_name"), key="auth_register_name")
        password = st.text_input(t("auth.password"), type="password", key="auth_register_password")
        submitted = st.form_submit_button(t("auth.register"), type="primary", use_container_width=True)
    if submitted:
        result = register(email, password, display_name)
        if result.ok:
            st.success(t(result.message_key))
            st.session_state["auth_verify_email"] = email
            st.session_state["auth_purpose"] = "verify"
            _dev_code_notice(result.code)
        else:
            st.error(t(result.message_key))


def _render_verify_form() -> None:
    if st.session_state.get("auth_verify_email"):
        st.session_state.setdefault("auth_verify_email", st.session_state["auth_verify_email"])
    with st.form("auth_verify_form"):
        email = st.text_input(t("auth.email"), key="auth_verify_email")
        code = st.text_input(t("auth.verification_code"), key="auth_verify_code")
        submitted = st.form_submit_button(t("auth.verify"), type="primary", use_container_width=True)
    if submitted:
        result = verify_email(email, code)
        if result.ok:
            st.session_state["user"] = _user_session_payload(result.user)
            st.success(t(result.message_key))
            st.rerun()
        else:
            st.error(t(result.message_key))

    if st.button(t("auth.resend_code"), type="secondary", use_container_width=True, key="auth_resend_code"):
        result = resend_code(email, "verify")
        if result.ok:
            st.info(t("auth.code_sent"))
            _dev_code_notice(result.code)
        else:
            st.error(t(result.message_key))


def _render_forgot_form() -> None:
    with st.form("auth_forgot_form"):
        email = st.text_input(t("auth.email"), key="auth_reset_email")
        submitted = st.form_submit_button(t("auth.request_reset"), type="primary", use_container_width=True)
    if submitted:
        result = request_password_reset(email)
        st.info(t(result.message_key))


def render_password_change_required(user: dict | None) -> None:
    if user is None:
        return
    with st.form("auth_change_password_required"):
        old_password = st.text_input(t("auth.current_password"), type="password")
        new_password = st.text_input(t("auth.new_password"), type="password")
        submitted = st.form_submit_button(t("auth.change_password"), type="primary", use_container_width=True)
    if submitted:
        from core.auth import change_password
        result = change_password(user["id"], old_password, new_password)
        if result.ok:
            st.session_state["user"]["must_change_password"] = 0
            st.success(t(result.message_key))
            st.rerun()
        else:
            st.error(t(result.message_key))


def _sync_lang_state() -> None:
    value = st.session_state.get("auth_language") or st.session_state.get("language") or st.session_state.get("lang")
    if not value:
        return
    from utils.i18n import normalize_language
    normalized = normalize_language(value)
    st.session_state["lang"] = normalized
    st.session_state["language"] = normalized


def _render_auth_header() -> None:
    from ui.theme import render_brand
    render_brand(large=True, center=True)


def _render_auth_controls() -> None:
    from utils.i18n import SUPPORTED_LANGS
    current = st.session_state.get("lang") or "ar"
    choices = list(SUPPORTED_LANGS)
    st.selectbox(
        "",
        options=choices,
        index=choices.index(current) if current in choices else 0,
        format_func=lambda code: SUPPORTED_LANGS[code],
        key="auth_language",
        on_change=_sync_lang_state,
    )


def render_auth_page() -> None:
    from ui.theme import apply_theme

    apply_theme(lang=st.session_state.get("lang") or "ar")
    st.markdown(_auth_css(), unsafe_allow_html=True)

    mode = st.session_state.get("auth_mode", "register")
    if mode not in {"login", "register", "verify", "reset"}:
        mode = "register"

    left, center, right = st.columns([1, 2, 1])
    with center:
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        _render_auth_controls()

        if mode == "login":
            _render_auth_header()
            _render_login_form()
            c1, c2, c3 = st.columns(3)
            if c1.button(t("auth.create_one"), key="switch_to_register", use_container_width=True):
                st.session_state["auth_mode"] = "register"
                st.rerun()
            if c2.button(t("auth.verify_email_short"), key="switch_to_verify", use_container_width=True):
                st.session_state["auth_mode"] = "verify"
                st.rerun()
            if c3.button(t("auth.reset_link"), key="switch_to_reset", use_container_width=True):
                st.session_state["auth_mode"] = "reset"
                st.rerun()
        elif mode == "verify":
            _render_auth_header()
            if st.button(t("auth.log_in"), key="switch_to_login_from_verify", use_container_width=True):
                st.session_state["auth_mode"] = "login"
                st.rerun()
            _render_verify_form()
        elif mode == "reset":
            _render_auth_header()
            if st.button(t("auth.log_in"), key="switch_to_login_from_reset", use_container_width=True):
                st.session_state["auth_mode"] = "login"
                st.rerun()
            _render_forgot_form()
        else:
            _render_auth_header()
            if st.button(t("auth.log_in"), key="switch_to_login", use_container_width=True):
                st.session_state["auth_mode"] = "login"
                st.rerun()
            _render_register_form()
        st.markdown('</div>', unsafe_allow_html=True)


__all__ = ["_logout", "render_auth_page", "render_password_change_required"]
