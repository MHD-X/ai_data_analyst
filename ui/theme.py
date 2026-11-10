from __future__ import annotations

import streamlit as st

from utils.i18n import is_rtl


def _opt(name: str, fallback: str) -> str:
    try:
        value = st.get_option(f"theme.{name}")
        return value if value else fallback
    except Exception:
        return fallback


def _tokens(lang: str | None = None) -> dict[str, str]:
    is_rtl_lang = is_rtl(lang)
    primary = _opt("primaryColor", "var(--primary-color)")
    bg = _opt("backgroundColor", "var(--background-color)")
    surface = _opt("secondaryBackgroundColor", "var(--secondary-background-color)")
    text = _opt("textColor", "var(--text-color)")
    return {
        "__PRIMARY__": primary,
        "__BG__": bg,
        "__SURFACE__": surface,
        "__TEXT__": text,
        "__DIRECTION__": "rtl" if is_rtl_lang else "ltr",
        "__ALIGN__": "right" if is_rtl_lang else "left",
        "__FONT__": "'Cairo', 'Segoe UI', Tahoma, sans-serif" if is_rtl_lang else "'Inter', 'Segoe UI', sans-serif",
    }


def build_theme_css(lang: str | None = None) -> str:
    """Build the app-wide theme stylesheet using the active language direction and theme tokens."""
    tokens = _tokens(lang)
    css = """
    <style>
    /* Between Data theme */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --primary-color: __PRIMARY__;
        --bg-color: __BG__;
        --surface-color: __SURFACE__;
        --text-color: __TEXT__;
        --border-color: color-mix(in srgb, __TEXT__ 20%, transparent);
        --soft-primary: color-mix(in srgb, __PRIMARY__ 18%, white);
        --soft-surface: color-mix(in srgb, __SURFACE__ 70%, white);
    }

    html, body {
        margin: 0;
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
    }

    .stApp {
        background: var(--bg-color);
        color: var(--text-color);
        font-family: __FONT__;
        direction: __DIRECTION__;
        text-align: __ALIGN__;
        min-height: 100vh;
    }

    .stApp [data-testid="stMain"],
    .stApp .block-container {
        max-width: 100% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    h1, h2, h3, h4, h5, h6,
    p, label, .stTabs [role="tab"],
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMarkdownContainer"],
    .stDataFrame, .stTable,
    .stFileUploader, .stAlert,
    .stButton > button,
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div,
    .stDateInput > div > div > div {
        direction: __DIRECTION__;
        text-align: __ALIGN__;
    }

    .stButton > button {
        background: color-mix(in srgb, __PRIMARY__ 92%, white);
        border: 1px solid color-mix(in srgb, __PRIMARY__ 70%, transparent);
        color: white;
        border-radius: 0.75rem;
        font-weight: 600;
        min-height: 2.6rem;
        transition: transform 150ms ease, box-shadow 150ms ease;
    }

    .stButton > button:hover {
        filter: brightness(1.04);
    }

    .stButton > button:focus-visible,
    .stTextInput > div > div > input:focus-visible,
    .stTextArea > div > div > textarea:focus-visible,
    .stSelectbox > div > div > div:focus-visible,
    .stFileUploader:focus-visible {
        outline: 2px solid color-mix(in srgb, __PRIMARY__ 70%, white);
        outline-offset: 2px;
    }

    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div,
    .stDateInput > div > div > div {
        background: color-mix(in srgb, __BG__ 80%, white);
        color: var(--text-color);
        border: 1px solid var(--border-color);
        border-radius: 0.8rem;
    }

    .stTabs [role="tablist"] {
        background: var(--surface-color);
        border-radius: 0.75rem;
        padding: 0.2rem;
    }

    .stTabs [role="tab"] {
        color: var(--text-color);
        border-radius: 0.6rem;
        font-weight: 600;
    }

    .stTabs [role="tab"][aria-selected="true"] {
        background: color-mix(in srgb, __PRIMARY__ 12%, white);
        color: var(--text-color);
    }

    .stDataFrame > div,
    .stTable > div,
    [data-testid="stMetric"],
    .stAlert,
    .stExpander,
    .stFileUploader {
        background: color-mix(in srgb, __SURFACE__ 64%, white);
        border: 1px solid var(--border-color);
        border-radius: 1rem;
        box-shadow: 0 4px 18px color-mix(in srgb, __PRIMARY__ 6%, transparent);
    }

    .stFileUploader {
        padding: 0.35rem 0.5rem;
    }

    .stFileUploader button {
        background: color-mix(in srgb, __PRIMARY__ 92%, white) !important;
        color: white;
    }

    .stChatMessage {
        background: color-mix(in srgb, __SURFACE__ 72%, white);
        border: 1px solid var(--border-color);
        border-radius: 1rem;
    }

    [data-testid="stHeader"] {
        background: transparent !important;
    }

    header,
    footer,
    [data-testid="stDecoration"] {
        display: none !important;
    }

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
        .stApp .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }

        .stTabs [role="tab"] {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }
    }
    </style>
    """

    for token, value in tokens.items():
        css = css.replace(token, str(value))
    return css


def apply_theme(lang: str | None = None) -> None:
    """Inject the theme stylesheet into Streamlit."""
    st.markdown(build_theme_css(lang), unsafe_allow_html=True)
