from __future__ import annotations

import html

import streamlit as st

from utils.i18n import is_rtl, t

THEME_LIGHT = "light"
THEME_DARK = "dark"

_UPLOAD_ICON_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    '<polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>'
)


def build_theme_css(lang: str | None = None, mode: str = THEME_LIGHT) -> str:
    """Return a minimal, safe stylesheet that respects RTL/LTR without overriding Streamlit's layout."""
    direction = "rtl" if is_rtl(lang) else "ltr"
    panel_bg = "black" if mode == THEME_DARK else "white"
    page_bg = "black" if mode == THEME_DARK else "white"
    text_color = "white" if mode == THEME_DARK else "black"
    muted_color = "lightgray" if mode == THEME_DARK else "gray"
    button_bg = "black" if mode == THEME_DARK else "blue"
    border_color = "lightgray" if mode == THEME_DARK else "silver"
    return f"""
    <style>
    /* Between Data theme */
    .stApp {{
        direction: {direction};
        background: {page_bg};
        color: {text_color};
    }}
    .stApp [data-testid="stMain"] {{
        padding-top: 0.5rem;
        padding-bottom: 1rem;
    }}
    .stApp [data-testid="stSidebar"] {{
        background: {panel_bg};
        color: {text_color};
        direction: {direction};
    }}
    .stApp .stMarkdown, .stApp .stForm, .stApp .stDataFrameContainer, .stApp .stTextInput, .stApp .stSelectbox, .stApp .stFileUploader {{
        direction: {direction};
        text-align: start;
    }}
    .stButton > button {{
        background: {button_bg};
        border: 1px solid {border_color};
        border-radius: 10px;
        color: white;
        font-weight: 600;
    }}
    .stFileUploader {{
        border-radius: 12px;
        background: {panel_bg};
        border: 1px solid {border_color};
    }}
    .stSidebar {{
        background: {panel_bg};
    }}
    .stTabs [role="tablist"], .stSidebar .stSelectbox, .stSidebar .stButton {{
        direction: {direction};
    }}
    .auth-card, .auth-shell {{
        direction: {direction};
    }}
    .auth-title {{
        color: {text_color};
    }}
    .auth-subtitle {{
        color: {muted_color};
    }}
    .stAlert, .stSuccess, .stWarning, .stInfo {{
        border-radius: 10px;
    }}
    </style>
    """


def _resolve_theme_mode() -> str:
    value = st.session_state.get("theme_mode")
    if value is None:
        value = st.session_state.get("theme_dark_toggle")
    if value is None:
        return THEME_LIGHT
    return THEME_DARK if bool(value) else THEME_LIGHT


def apply_theme(lang: str | None = None, mode: str | None = None) -> None:
    """Apply the current theme mode to the active Streamlit session and keep state consistent."""
    resolved_mode = (mode or _resolve_theme_mode()).lower()
    if resolved_mode not in {THEME_LIGHT, THEME_DARK}:
        resolved_mode = THEME_LIGHT
    st.session_state["theme_mode"] = resolved_mode
    st.session_state["theme_dark_toggle"] = resolved_mode == THEME_DARK
    try:
        st.set_option("theme.base", resolved_mode)
    except Exception:
        pass
    st.markdown(build_theme_css(lang=lang or st.session_state.get("lang"), mode=resolved_mode), unsafe_allow_html=True)


def _on_theme_toggle() -> None:
    mode = THEME_DARK if st.session_state.get("theme_dark_toggle") else THEME_LIGHT
    st.session_state["theme_mode"] = mode
    try:
        st.set_option("theme.base", mode)
    except Exception:
        pass


def render_theme_toggle() -> None:
    theme_mode = st.session_state.get("theme_mode", THEME_LIGHT)
    st.session_state.setdefault("theme_mode", theme_mode)
    st.session_state.setdefault("theme_dark_toggle", theme_mode == THEME_DARK)
    st.toggle(
        t("theme_dark_mode"),
        value=st.session_state["theme_mode"] == THEME_DARK,
        key="theme_dark_toggle",
        on_change=_on_theme_toggle,
    )


def render_welcome_card(message: str) -> None:
    st.markdown(
        '<div class="bd-welcome">'
        f'<div class="bd-welcome-icon">{_UPLOAD_ICON_SVG}</div>'
        f'<div><h3>{html.escape(t("welcome.title"))}</h3><p>{html.escape(message)}</p></div>'
        "</div>",
        unsafe_allow_html=True,
    )
