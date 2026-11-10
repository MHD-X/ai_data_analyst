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
    return f"""
    <style>
    /* Between Data theme */
    .stApp {{ direction: {direction}; }}
    .stApp [data-testid="stMain"] {{
        padding-top: 0.5rem;
        padding-bottom: 1rem;
    }}
    .stButton > button {{
        background: var(--primary-color, blue);
        border: 1px solid var(--primary-color, blue);
        border-radius: 10px;
        color: white;
        font-weight: 600;
    }}
    .stFileUploader {{
        border-radius: 12px;
        background: var(--secondary-background-color, lightgray);
    }}
    .stSidebar {{
        background: var(--secondary-background-color, lightgray);
    }}
    </style>
    """


def apply_theme(lang: str | None = None) -> None:
    """No-op: use Streamlit's default native rendering instead of custom layout overrides."""
    return None


def _on_theme_toggle() -> None:
    st.session_state["theme_mode"] = THEME_DARK if st.session_state.get("theme_dark_toggle") else THEME_LIGHT


def render_theme_toggle() -> None:
    st.session_state.setdefault("theme_mode", THEME_LIGHT)
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
