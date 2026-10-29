from __future__ import annotations

import streamlit as st

from config import get_setting
from core.auth import AuthStore, login, register, request_password_reset, resend_code, reset_password, verify_email
from utils.i18n import t


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


def _render_login_form() -> None:
    with st.form("auth_login_form"):
        email = st.text_input(t("auth.email"), key="auth_login_email")
        password = st.text_input(t("auth.password"), type="password", key="auth_login_password")
        submitted = st.form_submit_button(t("auth.login"))
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
        email = st.text_input(t("auth.email"), key="auth_register_email")
        display_name = st.text_input(t("auth.display_name"), key="auth_register_name")
        password = st.text_input(t("auth.password"), type="password", key="auth_register_password")
        submitted = st.form_submit_button(t("auth.register"))
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
        email = st.text_input(t("auth.email"), key="auth_verify_email")
        code = st.text_input(t("auth.verification_code"), key="auth_verify_code")
        submitted = st.form_submit_button(t("auth.verify"))
        if submitted:
            result = verify_email(email, code)
            if result.ok:
                st.success(t(result.message_key))
                st.session_state["user"] = _user_session_payload(result.user)
                st.rerun()
            else:
                st.error(t(result.message_key))
                if st.button(t("auth.resend_code")):
                    resend_code(email, "verify")
                    st.info(t("auth.code_sent"))


def _render_forgot_form() -> None:
    with st.form("auth_forgot_form"):
        email = st.text_input(t("auth.email"), key="auth_reset_email")
        submitted = st.form_submit_button(t("auth.request_reset"))
        if submitted:
            result = request_password_reset(email)
            st.info(t(result.message_key))


def render_password_change_required(user: dict | None) -> None:
    if user is None:
        return
    with st.form("auth_change_password_required"):
        old_password = st.text_input(t("auth.current_password"), type="password")
        new_password = st.text_input(t("auth.new_password"), type="password")
        submitted = st.form_submit_button(t("auth.change_password"))
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
    st.title("Between Data")
    st.caption(t("auth.auth_intro"))
    login_tab, register_tab, verify_tab, reset_tab = st.tabs([
        t("auth.login"),
        t("auth.register"),
        t("auth.verify"),
        t("auth.reset_password"),
    ])
    with login_tab:
        _render_login_form()
    with register_tab:
        _render_register_form()
    with verify_tab:
        _render_verify_form()
    with reset_tab:
        _render_forgot_form()


__all__ = ["_logout", "render_auth_page", "render_password_change_required"]
