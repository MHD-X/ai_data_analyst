from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import get_setting
from core.auth import AuthStore, login, register, request_password_reset, resend_code, reset_password, verify_email
from utils.i18n import is_rtl, t

ROOT = Path(__file__).resolve().parents[1]
LOGIN_BG_PATH = ROOT / "assets" / "login-bg.jpg"


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
    is_dark = st.get_option("theme.base") == "dark"
    page_bg = "#121826" if is_dark else "#f3f4f6"
    card_bg = "#1f2937" if is_dark else "#ffffff"
    border = "#374151" if is_dark else "#e5e7eb"
    text = "#f9fafb" if is_dark else "#111827"
    muted = "#cbd5e1" if is_dark else "#6b7280"
    accent = "#10b981"
    return f"""
    <style>
      .auth-shell {{
        max-width: 480px;
        margin: 2rem auto;
        padding: 0 1rem;
      }}
      .auth-card {{
        background: {card_bg};
        border: 1px solid {border};
        border-radius: 18px;
        box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
        padding: 1.5rem;
        color: {text};
      }}
      .auth-badge {{
        display: inline-block;
        padding: 0.4rem 0.7rem;
        border-radius: 999px;
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.2);
        color: {accent};
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 1rem;
      }}
      .auth-title {{
        font-size: clamp(2rem, 4vw, 2.6rem);
        font-weight: 800;
        line-height: 1.15;
        margin: 0 0 0.7rem 0;
        color: {text};
      }}
      .auth-subtitle {{
        margin: 0 0 1.2rem 0;
        color: {muted};
        font-size: 0.98rem;
      }}
      .auth-row {{
        display: flex;
        gap: 0.75rem;
        margin-top: 0.75rem;
      }}
      .auth-row > div {{
        flex: 1 1 0;
      }}
      .stTextInput > label,
      .stNumberInput > label,
      .stSelectbox > label {{
        color: {text} !important;
        font-weight: 600 !important;
      }}
      .stTextInput > div > div > input,
      .stTextArea > div > div > textarea,
      .stSelectbox > div > div > div {{
        background: {page_bg} !important;
        border: 1px solid {border} !important;
        border-radius: 12px !important;
        color: {text} !important;
        min-height: 48px !important;
      }}
      .stTextInput input::placeholder,
      .stTextArea textarea::placeholder {{
        color: {muted} !important;
      }}
      .stButton > button {{
        width: 100% !important;
        min-height: 48px !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
      }}
      @media (max-width: 640px) {{
        .auth-shell {{
          margin: 0.75rem auto;
          padding: 0 0.5rem;
        }}
        .auth-card {{
          padding: 1.1rem;
        }}
        .auth-row {{
          flex-direction: column;
        }}
      }}
    </style>
    """


def _render_login_form() -> None:
    with st.form("auth_login_form"):
        email = st.text_input(t("auth.email"), key="auth_login_email", placeholder="me@example.com")
        password = st.text_input(t("auth.password"), type="password", key="auth_login_password", placeholder="••••••••••")
        submitted = st.form_submit_button(t("auth.login"), use_container_width=True)
        if submitted:
            result = login(email, password)
            if result.ok:
                st.session_state["user"] = _user_session_payload(result.user)
                st.success(t(result.message_key))
                st.rerun()
            else:
                st.error(t(result.message_key))
                if result.message_key == "auth.email_unverified":
                    st.info(t("auth.resend_hint"))


def _render_register_form() -> None:
    if get_setting("SIGNUP_OPEN", "0") != "1":
        st.warning(t("auth.signup_closed"))
        return
    with st.form("auth_register_form"):
        email = st.text_input(t("auth.email"), key="auth_register_email", placeholder="me@example.com")
        display_name = st.text_input(t("auth.display_name"), key="auth_register_name", placeholder="Jane Doe")
        password = st.text_input(t("auth.password"), type="password", key="auth_register_password", placeholder="Minimum 10 characters")
        submitted = st.form_submit_button(t("auth.register"), use_container_width=True)
        if submitted:
            result = register(email, password, display_name)
            if result.ok:
                st.success(t(result.message_key))
                st.session_state["auth_email"] = email
                st.session_state["auth_purpose"] = "verify"
                _dev_code_notice(result.code)
            else:
                st.error(t(result.message_key))


def _render_verify_form() -> None:
    with st.form("auth_verify_form"):
        email = st.text_input(t("auth.email"), key="auth_verify_email", placeholder="me@example.com")
        code = st.text_input(t("auth.verification_code"), key="auth_verify_code", placeholder="123456")
        submitted = st.form_submit_button(t("auth.verify"), use_container_width=True)
        if submitted:
            result = verify_email(email, code)
            if result.ok:
                st.success(t(result.message_key))
                st.session_state["user"] = _user_session_payload(result.user)
                st.rerun()
            else:
                st.error(t(result.message_key))
                if st.button(t("auth.resend_code"), use_container_width=True):
                    resend_code(email, "verify")
                    st.info(t("auth.code_sent"))


def _render_forgot_form() -> None:
    with st.form("auth_forgot_form"):
        email = st.text_input(t("auth.email"), key="auth_reset_email", placeholder="me@example.com")
        submitted = st.form_submit_button(t("auth.request_reset"), use_container_width=True)
        if submitted:
            result = request_password_reset(email)
            st.info(t(result.message_key))


def render_password_change_required(user: dict | None) -> None:
    if user is None:
        return
    with st.form("auth_change_password_required"):
        old_password = st.text_input(t("auth.current_password"), type="password")
        new_password = st.text_input(t("auth.new_password"), type="password")
        submitted = st.form_submit_button(t("auth.change_password"), use_container_width=True)
        if submitted:
            from core.auth import change_password
            result = change_password(user["id"], old_password, new_password)
            if result.ok:
                st.session_state["user"]["must_change_password"] = 0
                st.success(t(result.message_key))
                st.rerun()
            else:
                st.error(t(result.message_key))


def render_auth_page() -> None:
    st.markdown(_auth_css(), unsafe_allow_html=True)

    mode = st.session_state.get("auth_mode", "register")
    if mode not in {"login", "register", "verify", "reset"}:
        mode = "register"

    current_lang = st.session_state.get("lang") or "en"
    direction = "rtl" if is_rtl(current_lang) else "ltr"
    st.markdown(f'<div dir="{direction}" class="auth-shell">', unsafe_allow_html=True)
    st.markdown('<div class="auth-card">', unsafe_allow_html=True)

    if mode == "login":
        st.markdown('<div class="auth-badge">Between Data</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-title">{t("auth.welcome_back")}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-subtitle">{t("auth.need_account")}</div>', unsafe_allow_html=True)
        if st.button(t("auth.create_one"), key="switch_to_register", use_container_width=True):
            st.session_state["auth_mode"] = "register"
            st.rerun()
        _render_login_form()
        if st.button(t("auth.verify_email_short"), key="switch_to_verify", use_container_width=True):
            st.session_state["auth_mode"] = "verify"
            st.rerun()
        if st.button(t("auth.reset_link"), key="switch_to_reset", use_container_width=True):
            st.session_state["auth_mode"] = "reset"
            st.rerun()

    elif mode == "verify":
        st.markdown('<div class="auth-badge">Security</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-title">{t("auth.verify_email")}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-subtitle">{t("auth.back_to_login")}</div>', unsafe_allow_html=True)
        if st.button(t("auth.log_in"), key="switch_to_login_from_verify", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()
        _render_verify_form()

    elif mode == "reset":
        st.markdown('<div class="auth-badge">Recovery</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-title">{t("auth.reset_password_title")}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-subtitle">{t("auth.remember_it")}</div>', unsafe_allow_html=True)
        if st.button(t("auth.log_in"), key="switch_to_login_from_reset", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()
        _render_forgot_form()

    else:
        st.markdown('<div class="auth-badge">Between Data</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-title">{t("auth.create_account")}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="auth-subtitle">{t("auth.already_account")}</div>', unsafe_allow_html=True)
        if st.button(t("auth.log_in"), key="switch_to_login", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()
        _render_register_form()

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


__all__ = ["_logout", "render_auth_page", "render_password_change_required"]
