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

_DARK_LOGO_CSS = """
[data-testid="stImage"] img {
    background: hsl(0 0% 100%);
    border-radius: 0.75rem;
    padding: 0.5rem 0.75rem;
}
"""


def _opt(name: str, fallback: str) -> str:
    try:
        value = st.get_option(f"theme.{name}")
        return value if value else fallback
    except Exception:
        return fallback


def _palette(mode: str) -> dict[str, str]:
    if mode == THEME_DARK:
        return {
            "__BG__": "hsl(222 47% 7%)",
            "__SURFACE__": "hsl(222 40% 11%)",
            "__SIDEBAR__": "hsl(224 44% 9%)",
            "__TEXT__": "hsl(210 40% 96%)",
            "__MUTED__": "hsl(215 20% 70%)",
            "__BORDER__": "hsl(217 33% 24%)",
            "__SHADOW__": "hsl(222 60% 2% / 0.6)",
            "__DARK_LOGO__": _DARK_LOGO_CSS,
        }
    return {
        "__BG__": _opt("backgroundColor", "hsl(219 33% 98%)"),
        "__SURFACE__": "hsl(0 0% 100%)",
        "__SIDEBAR__": _opt("secondaryBackgroundColor", "hsl(220 30% 96%)"),
        "__TEXT__": _opt("textColor", "hsl(215 39% 17%)"),
        "__MUTED__": "hsl(215 16% 42%)",
        "__BORDER__": "hsl(215 25% 86%)",
        "__SHADOW__": "hsl(222 47% 11% / 0.08)",
        "__DARK_LOGO__": "",
    }


def _tokens(lang: str | None, mode: str) -> dict[str, str]:
    rtl = is_rtl(lang)
    tokens = _palette(mode)
    tokens.update({
        "__PRIMARY__": _opt("primaryColor", "hsl(221 83% 53%)"),
        "__ON_PRIMARY__": "hsl(0 0% 100%)",
        "__DIRECTION__": "rtl" if rtl else "ltr",
        "__ALIGN__": "right" if rtl else "left",
        "__FONT__": "'Cairo', 'Segoe UI', Tahoma, sans-serif" if rtl else "'Inter', 'Segoe UI', sans-serif",
    })
    return tokens


_CSS_TEMPLATE = """
<style>
/* Between Data theme */
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --primary-color: __PRIMARY__;
    --on-primary: __ON_PRIMARY__;
    --bg-color: __BG__;
    --surface-color: __SURFACE__;
    --sidebar-color: __SIDEBAR__;
    --text-color: __TEXT__;
    --muted-color: __MUTED__;
    --border-color: __BORDER__;
    --hover-color: color-mix(in srgb, __PRIMARY__ 12%, transparent);
    --shadow-color: __SHADOW__;
    --radius-lg: 1rem;
    --radius-md: 0.75rem;
}

html, body {
    margin: 0;
    max-width: 100%;
    overflow-x: hidden;
}

.stApp {
    background: var(--bg-color);
    color: var(--text-color);
    font-family: __FONT__;
    direction: __DIRECTION__;
    text-align: __ALIGN__;
}

.stApp [data-testid="stMain"],
.stApp [data-testid="stMainBlockContainer"],
.stApp .block-container {
    max-width: 100% !important;
    padding: 1.5rem clamp(1rem, 3vw, 2.5rem) 3rem !important;
}

.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp p, .stApp li, .stApp label, .stApp [data-testid="stMarkdownContainer"] {
    color: var(--text-color);
}

.stApp h1, .stApp h2, .stApp h3 {
    line-height: 1.2;
    letter-spacing: -0.01em;
}

.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] * {
    color: var(--muted-color) !important;
}

.stButton > button,
.stDownloadButton > button {
    background: var(--primary-color);
    border: 1px solid var(--primary-color);
    color: var(--on-primary);
    border-radius: 999px;
    font-weight: 600;
    min-height: 2.5rem;
    padding: 0.5rem 1.25rem;
    box-shadow: 0 6px 16px color-mix(in srgb, var(--primary-color) 28%, transparent);
    transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
}

.stButton > button *,
.stDownloadButton > button * {
    color: inherit !important;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    transform: translateY(-1px);
    filter: brightness(1.05);
}

.stButton > button:active,
.stDownloadButton > button:active {
    transform: translateY(0);
}

.stButton > button[kind="secondary"] {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    color: var(--text-color);
    box-shadow: none;
}

.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
}

[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="select"] > div,
[data-testid="stChatInput"] {
    background: var(--surface-color) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
}

[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: var(--text-color) !important;
}

[data-baseweb="select"] div {
    color: var(--text-color);
}

[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="menu"] {
    background: var(--surface-color) !important;
}

[data-baseweb="menu"] li {
    color: var(--text-color) !important;
}

[data-testid="stFileUploaderDropzone"] {
    background: var(--surface-color);
    border: 2px dashed color-mix(in srgb, var(--primary-color) 45%, var(--border-color));
    border-radius: var(--radius-lg);
    transition: border-color 160ms ease, background 160ms ease;
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--primary-color);
    background: var(--hover-color);
}

[data-testid="stFileUploaderDropzone"] button {
    background: var(--primary-color) !important;
    color: var(--on-primary) !important;
    border: none !important;
    border-radius: 999px !important;
}

[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] span {
    color: var(--muted-color) !important;
}

.stTabs [data-baseweb="tab-list"] {
    justify-content: center;
    gap: 0.5rem;
    background: transparent;
    padding: 0.25rem 0 0.75rem;
}

.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

.stTabs button[data-baseweb="tab"] {
    background: transparent;
    border: 1px solid var(--border-color);
    border-radius: 999px;
    padding: 0.5rem 1.25rem;
    font-weight: 600;
    color: var(--muted-color);
    transition: background 160ms ease, color 160ms ease, transform 160ms ease;
}

.stTabs button[data-baseweb="tab"]:hover {
    background: var(--hover-color);
    color: var(--text-color);
    transform: translateY(-1px);
}

.stTabs button[data-baseweb="tab"][aria-selected="true"] {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: var(--on-primary);
    box-shadow: 0 8px 20px color-mix(in srgb, var(--primary-color) 35%, transparent);
}

[data-testid="stMetric"],
[data-testid="stExpander"],
[data-testid="stDataFrame"],
[data-testid="stAlert"] {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    box-shadow: 0 4px 18px var(--shadow-color);
}

[data-testid="stChatMessage"] {
    background: transparent;
    padding: 0.35rem 0;
    direction: __DIRECTION__;
}

[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 1.25rem;
    box-shadow: 0 6px 18px var(--shadow-color);
    padding: 0.85rem 1rem;
    color: var(--text-color);
    line-height: 1.7;
}

[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] p {
    margin: 0.15rem 0;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    flex-direction: row-reverse;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
    background: var(--primary-color);
    border-color: transparent;
    border-start-end-radius: 0.35rem;
    box-shadow: 0 8px 20px color-mix(in srgb, var(--primary-color) 30%, transparent);
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] * {
    color: var(--on-primary) !important;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {
    border-start-start-radius: 0.35rem;
}

[data-testid="stSidebar"] {
    background: var(--sidebar-color);
    border-inline-start: 1px solid var(--border-color);
    border-inline-end: 0;
    direction: __DIRECTION__;
    text-align: __ALIGN__;
    width: min(22rem, 88vw) !important;
}

[data-testid="stSidebar"] > div:first-child {
    width: min(22rem, 88vw) !important;
}

[data-testid="stSidebarUserContent"] {
    padding: 1.25rem 1rem 2rem;
}

[data-testid="stSidebarUserContent"] > div {
    width: 100%;
}

[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
    text-align: __ALIGN__ !important;
}

[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    direction: __DIRECTION__;
}

[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    padding: 1rem;
    text-align: center;
}

[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] {
    align-items: center;
    text-align: center;
}

[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
    margin-inline: auto;
}

[data-testid="stSidebar"] [data-testid="stExpander"] {
    overflow: hidden;
}

[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    justify-content: center;
}

[data-testid="stSidebar"] [data-testid="stMetric"] {
    padding: 0.75rem;
}

[data-testid="stSidebar"] hr {
    margin: 1rem 0;
    border-color: var(--border-color);
}

[data-testid="stHeader"] {
    background: transparent !important;
}

[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
footer {
    display: none !important;
}

[data-testid="stSidebarCollapseButton"] button,
[data-testid="collapsedControl"] button {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 999px !important;
    background: var(--surface-color) !important;
    border: 1px solid var(--border-color) !important;
    box-shadow: 0 6px 18px var(--shadow-color);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 160ms ease, background 160ms ease;
}

[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="collapsedControl"] button:hover {
    background: var(--hover-color) !important;
    transform: scale(1.06);
}

[data-testid="stSidebarCollapseButton"] button svg,
[data-testid="collapsedControl"] button svg {
    display: none;
}

[data-testid="stSidebarCollapseButton"] button::after,
[data-testid="collapsedControl"] button::after {
    content: "\\2039";
    font-size: 1.5rem;
    line-height: 1;
    color: var(--primary-color);
}

[data-testid="collapsedControl"] {
    position: fixed;
    top: 1rem;
    inset-inline-start: 1rem;
    z-index: 1000;
}

[data-testid="stSidebarCollapseButton"] {
    position: absolute;
    top: 1rem;
    inset-inline-end: -1.25rem;
    z-index: 1000;
}

[data-testid="stLogo"] {
    height: 2.5rem !important;
    width: auto !important;
    max-width: 100%;
}

.bd-theme-toggle label {
    font-weight: 600;
}

.bd-sidebar-section {
    margin: 0.25rem 0 0.75rem;
}

.bd-sidebar-section .bd-section-kicker {
    display: block;
    color: var(--primary-color);
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    margin-bottom: 0.2rem;
}

.bd-sidebar-section h3 {
    font-size: 1.05rem;
    margin: 0;
}

.bd-sidebar-section p {
    color: var(--muted-color) !important;
    font-size: 0.78rem;
    line-height: 1.5;
    margin: 0.25rem 0 0;
}

.bd-file-heading {
    align-items: center;
    display: flex;
    gap: 0.6rem;
    margin: 0.35rem 0 0.75rem;
    overflow: hidden;
}

.bd-file-heading strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.bd-file-icon {
    align-items: center;
    background: var(--hover-color);
    border: 1px solid color-mix(in srgb, var(--primary-color) 24%, var(--border-color));
    border-radius: 0.55rem;
    color: var(--primary-color);
    display: inline-flex;
    flex: 0 0 auto;
    font-size: 0.62rem;
    font-weight: 800;
    height: 2rem;
    justify-content: center;
    letter-spacing: 0.04em;
    width: 2rem;
}

.bd-welcome {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.25rem 1.5rem;
    border: 1px dashed var(--border-color);
    border-radius: var(--radius-lg);
    background: var(--surface-color);
    box-shadow: 0 4px 18px var(--shadow-color);
    max-width: 640px;
}

.bd-welcome-icon {
    flex-shrink: 0;
    width: 3rem;
    height: 3rem;
    border-radius: 999px;
    display: grid;
    place-items: center;
    background: var(--hover-color);
    color: var(--primary-color);
}

.bd-welcome-icon svg {
    width: 1.5rem;
    height: 1.5rem;
}

.bd-welcome h3 {
    margin: 0 0 0.25rem;
    font-size: 1.1rem;
    color: var(--text-color) !important;
}

.bd-welcome p {
    margin: 0;
    color: var(--muted-color) !important;
    line-height: 1.5;
}

__DARK_LOGO__

pre, code, [data-testid="stCode"],
[data-testid="stDataFrame"],
[data-testid="stTable"],
.js-plotly-plot {
    direction: ltr !important;
    text-align: left !important;
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        scroll-behavior: auto !important;
    }
}

@media (max-width: 768px) {
    .stApp [data-testid="stMain"],
    .stApp [data-testid="stMainBlockContainer"],
    .stApp .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }

    .stTabs button[data-baseweb="tab"] {
        padding: 0.4rem 0.75rem;
    }
}
</style>
"""


def build_theme_css(lang: str | None = None, mode: str = THEME_LIGHT) -> str:
    """Build the app-wide stylesheet for the active language direction and light/dark mode."""
    css = _CSS_TEMPLATE
    for token, value in _tokens(lang, mode).items():
        css = css.replace(token, str(value))
    return css


def apply_theme(lang: str | None = None) -> None:
    """Inject the theme stylesheet using the session's light/dark mode."""
    mode = st.session_state.get("theme_mode", THEME_LIGHT)
    st.markdown(build_theme_css(lang, mode), unsafe_allow_html=True)


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
