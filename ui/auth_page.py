from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import get_setting
from core.auth import AuthStore, login, register, request_password_reset, resend_code, reset_password, verify_email
from utils.i18n import t

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
    form_bg = "#1e1e1e" if is_dark else "#ffffff"
    form_bg_alt = "#111827" if is_dark else "#f8fafc"
    border = "#2b2f36" if is_dark else "#e5e7eb"
    text = "#f9fafb" if is_dark else "#111827"
    muted = "#9ca3af" if is_dark else "#6b7280"
    accent = "#10b981"
    accent_hover = "#059669"
    return f"""
    <style>
      header, footer, [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stStatusWidget"] {{
        display: none !important;
      }}
      .block-container {{
        padding: 0 !important;
        margin: 0 !important;
        max-width: none !important;
        width: 100% !important;
      }}
      .auth-shell {{
        width: 100vw;
        margin-left: calc(50% - 50vw);
        margin-right: calc(50% - 50vw);
        min-height: 100vh;
        background: {page_bg};
      }}
      .auth-image-box {{
        width: 100%;
        height: 100vh;
        overflow: hidden;
        background: linear-gradient(135deg, #0f172a 0%, #111827 100%);
      }}
      .auth-image-box img {{
        width: 100%;
        height: 100vh;
        object-fit: cover;
        display: block;
        border: 0;
      }}
      .auth-form-panel {{
        background: {form_bg};
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: clamp(2rem, 5vw, 5rem);
      }}
      .auth-card {{
        width: min(100%, 430px);
      }}
      .auth-badge {{
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.45rem 0.8rem;
        border-radius: 999px;
        background: rgba(16, 185, 129, 0.12);
        color: {accent};
        border: 1px solid rgba(16, 185, 129, 0.2);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 1.4rem;
      }}
      .auth-title {{
        color: {text};
        font-size: clamp(2.2rem, 3vw, 3rem);
        line-height: 1.1;
        font-weight: 800;
        margin-bottom: 0.75rem;
      }}
      .auth-subtitle {{
        color: {muted};
        font-size: 0.98rem;
        margin-bottom: 1.5rem;
      }}
      .auth-subtitle .auth-link-button {{
        color: {accent};
        background: transparent;
        border: none;
        padding: 0;
        font-weight: 700;
        text-decoration: none;
        cursor: pointer;
      }}
      .stTextInput > label, .stNumberInput > label, .stSelectbox > label {{
        color: {text} !important;
        font-weight: 600 !important;
      }}
      .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stSelectbox > div > div > div {{
        background: {form_bg_alt} !important;
        border: 1px solid {border} !important;
        border-radius: 14px !important;
        color: {text} !important;
        min-height: 52px !important;
        box-shadow: none !important;
      }}
      .stTextInput input::placeholder, .stTextArea textarea::placeholder {{
        color: {muted} !important;
      }}
      .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {{
        border-color: {accent} !important;
        box-shadow: 0 0 0 1px rgba(16, 185, 129, 0.35) !important;
      }}
      .stButton > button {{
        width: 100% !important;
        border-radius: 14px !important;
        min-height: 52px !important;
        border: 1px solid transparent !important;
        background: {accent} !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        box-shadow: 0 12px 25px rgba(16, 185, 129, 0.22) !important;
        transition: all 0.2s ease !important;
      }}
      .stButton > button:hover {{
        background: {accent_hover} !important;
        transform: translateY(-1px);
      }}
      .stButton > button:focus:not(:active) {{
        box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.18) !important;
      }}
      .auth-secondary-row {{
        display: flex;
        justify-content: space-between;
        gap: 0.75rem;
        margin-top: 1rem;
      }}
      .auth-secondary-row .stButton > button {{
        width: auto !important;
        min-height: 38px !important;
        background: transparent !important;
        color: {accent} !important;
        border: 1px solid {border} !important;
        box-shadow: none !important;
      }}
      .auth-secondary-row .stButton > button:hover {{
        background: rgba(16, 185, 129, 0.06) !important;
      }}
      @media (max-width: 768px) {{
        .auth-image-box {{ height: 220px; }}
        .auth-image-box img {{ height: 220px; }}
        .auth-form-panel {{ min-height: auto; padding: 1.5rem 1rem 2rem; }}
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

    left_col, right_col = st.columns([1, 1], gap="none")

    with left_col:
        left_col.markdown('<div class="auth-image-box">', unsafe_allow_html=True)
        if LOGIN_BG_PATH.exists():
            left_col.image(str(LOGIN_BG_PATH), use_container_width=True, output_format="JPEG")
        else:
            left_col.markdown(
                '<div style="width:100%;height:100%;background:linear-gradient(135deg, #0f172a 0%, #111827 100%);"></div>',
                unsafe_allow_html=True,
            )
        left_col.markdown('</div>', unsafe_allow_html=True)

    with right_col:
        st.markdown('<div class="auth-form-panel"><div class="auth-card">', unsafe_allow_html=True)

        if mode == "login":
            st.markdown('<div class="auth-badge">Between Data</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-title">Welcome back</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-subtitle">Need an account?</div>', unsafe_allow_html=True)
            if st.button("Create one", key="switch_to_register", use_container_width=False):
                st.session_state["auth_mode"] = "register"
                st.rerun()
            _render_login_form()
            st.markdown('<div class="auth-secondary-row">', unsafe_allow_html=True)
            if st.button("Verify email", key="switch_to_verify", use_container_width=True):
                st.session_state["auth_mode"] = "verify"
                st.rerun()
            if st.button("Reset password", key="switch_to_reset", use_container_width=True):
                st.session_state["auth_mode"] = "reset"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        elif mode == "verify":
            st.markdown('<div class="auth-badge">Security</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-title">Verify your email</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-subtitle">Back to login?</div>', unsafe_allow_html=True)
            if st.button("Log in", key="switch_to_login_from_verify", use_container_width=False):
                st.session_state["auth_mode"] = "login"
                st.rerun()
            _render_verify_form()

        elif mode == "reset":
            st.markdown('<div class="auth-badge">Recovery</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-title">Reset password</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-subtitle">Remember it?</div>', unsafe_allow_html=True)
            if st.button("Log in", key="switch_to_login_from_reset", use_container_width=False):
                st.session_state["auth_mode"] = "login"
                st.rerun()
            _render_forgot_form()

        else:
            st.markdown('<div class="auth-badge">Between Data</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-title">Create an account</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-subtitle">Already have an account?</div>', unsafe_allow_html=True)
            if st.button("Log in", key="switch_to_login", use_container_width=False):
                st.session_state["auth_mode"] = "login"
                st.rerun()
            _render_register_form()

        st.markdown('</div></div>', unsafe_allow_html=True)


__all__ = ["_logout", "render_auth_page", "render_password_change_required"]
