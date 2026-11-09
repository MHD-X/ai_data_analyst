from __future__ import annotations

from utils.i18n import is_rtl


def build_theme_css(lang: str | None = None) -> str:
    """Return the app-wide theme CSS for the active language.

    The configuration is intentionally centralized so the visual layer remains
    modular and can be reused across the Streamlit app without touching the
    business logic in the core package.
    """
    is_rtl_lang = is_rtl(lang)
    direction = "rtl" if is_rtl_lang else "ltr"
    text_align = "right" if is_rtl_lang else "left"
    font_stack = "'Cairo', 'Segoe UI', Tahoma, sans-serif" if is_rtl_lang else "'Inter', 'Segoe UI', sans-serif"

    return f"""
    <style>
    /* Between Data — premium RTL analytics experience */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');

    :root {{
        --between-bg: #0b1020;
        --between-bg-soft: #111827;
        --between-panel: rgba(15, 23, 42, 0.78);
        --between-panel-strong: rgba(17, 24, 39, 0.96);
        --between-surface: rgba(148, 163, 184, 0.13);
        --between-border: rgba(148, 163, 184, 0.22);
        --between-primary: #0f172a;
        --between-primary-soft: #1e293b;
        --between-accent: #2f7cf6;
        --between-accent-soft: rgba(47, 124, 246, 0.14);
        --between-success: #10b981;
        --between-success-soft: rgba(16, 185, 129, 0.12);
        --between-warning: #f59e0b;
        --between-text: #e5edf9;
        --between-text-muted: #b7c7df;
        --between-shadow: 0 18px 40px rgba(2, 6, 23, 0.38);
        --between-grid: rgba(148, 163, 184, 0.18);
    }}

    html, body {{
        margin: 0;
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
    }}

    .stApp {{
        background: linear-gradient(135deg, var(--between-bg) 0%, var(--between-bg-soft) 100%);
        color: var(--between-text);
        font-family: {font_stack};
        direction: {direction};
        min-height: 100vh;
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
    }}

    .stApp > div, .stApp > section, .stApp [data-testid="stMain"] {{
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
    }}

    .stApp .main, .stApp [data-testid="stMain"], .stApp .block-container {{
        width: 100% !important;
        max-width: 100% !important;
        padding-left: clamp(0.75rem, 2vw, 2rem) !important;
        padding-right: clamp(0.75rem, 2vw, 2rem) !important;
        margin: 0 auto !important;
        overflow-x: hidden !important;
        transition: width 0.25s ease, max-width 0.25s ease, padding 0.25s ease;
    }}

    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, rgba(11, 16, 32, 0.98) 0%, rgba(15, 23, 42, 0.96) 100%);
        border-right: 1px solid var(--between-border);
        border-left: 1px solid var(--between-border);
        box-shadow: inset -1px 0 0 rgba(255,255,255,0.04);
        width: 20rem !important;
        min-width: 15rem !important;
        max-width: 24rem !important;
        transition: width 0.25s ease, min-width 0.25s ease, max-width 0.25s ease, opacity 0.2s ease;
        overflow-x: hidden !important;
    }}

    [data-testid="stSidebar"] > div:first-child {{
        width: 100%;
        min-width: 0;
        transition: opacity 0.2s ease, visibility 0.2s ease;
    }}

    [data-testid="stSidebar"][aria-expanded="false"] {{
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        opacity: 0;
        overflow: hidden !important;
    }}

    [data-testid="stSidebar"][aria-expanded="false"] > div:first-child {{
        opacity: 0;
        visibility: hidden;
    }}

    [data-testid="stSidebar"] .stSelectbox,
    [data-testid="stSidebar"] .stFileUploader,
    [data-testid="stSidebar"] .stButton,
    [data-testid="stSidebar"] .stExpander {{
        margin-bottom: 0.75rem;
    }}

    .stHeader {{
        background: transparent !important;
    }}

    .stApp > header {{
        background-color: transparent !important;
    }}

    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stFileUploaderLabel"],
    [data-testid="stExpanderSummary"],
    .stTabs [role="tab"],
    .stSelectbox label,
    .stTextInput label,
    .stTextArea label,
    .stNumberInput label,
    .stDateInput label {{
        text-align: {text_align} !important;
        direction: {direction};
    }}

    [data-testid="stMetric"] {{
        background: linear-gradient(135deg, rgba(148, 163, 184, 0.12), rgba(15, 23, 42, 0.68));
        border: 1px solid var(--between-border);
        border-radius: 18px;
        box-shadow: var(--between-shadow);
        padding: 1rem 1.1rem;
    }}

    [data-testid="stMetricLabel"] {{
        color: var(--between-text-muted) !important;
        font-size: 0.78rem !important;
        letter-spacing: 0.02em; 
    }}

    [data-testid="stMetricValue"] {{
        color: var(--between-text) !important;
        font-size: 1.85rem !important;
        font-weight: 700 !important;
    }}

    .stButton > button {{
        background: linear-gradient(135deg, var(--between-accent) 0%, #4b8dff 100%);
        color: white !important;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 0.72rem 1.15rem;
        font-weight: 700;
        box-shadow: 0 10px 22px rgba(47, 124, 246, 0.28);
        transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease;
    }}

    .stButton > button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 14px 30px rgba(47, 124, 246, 0.38);
        filter: brightness(1.04);
    }}

    .stButton > button:focus {{
        box-shadow: 0 0 0 0.18rem rgba(47, 124, 246, 0.22);
        outline: none;
    }}

    .stDownloadButton > button,
    .stFormSubmitButton > button {{
        background: linear-gradient(135deg, var(--between-success) 0%, #34d399 100%);
        box-shadow: 0 10px 22px rgba(16, 185, 129, 0.25);
    }}

    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div,
    .stDateInput > div > div > div,
    .stFileUploader > section,
    .stFileUploader > div,
    [data-baseweb="select"] > div,
    [data-testid="stFileUploaderDropzone"] {{
        background: rgba(15, 23, 42, 0.7) !important;
        border: 1px solid var(--between-border) !important;
        border-radius: 14px !important;
        color: var(--between-text) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
    }}

    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {{
        color: var(--between-text-muted) !important;
    }}

    [data-testid="stFileUploaderDropzone"] {{
        border: 1.5px dashed rgba(148,163,184,0.45) !important;
        background: rgba(15, 23, 42, 0.52) !important;
        min-height: 120px;
        padding: 1rem;
    }}

    [data-testid="stFileUploaderDropzone"]:hover {{
        border-color: rgba(47,124,246,0.9) !important;
        background: rgba(47,124,246,0.07) !important;
    }}

    .stTabs [role="tablist"] {{
        background: rgba(15, 23, 42, 0.52);
        border: 1px solid var(--between-border);
        border-radius: 14px;
        padding: 0.2rem;
        gap: 0.35rem;
    }}

    .stTabs [role="tab"] {{
        border-radius: 10px;
        color: var(--between-text-muted);
        font-weight: 600;
        padding: 0.55rem 1rem;
    }}

    .stTabs [role="tab"][aria-selected="true"] {{
        background: linear-gradient(135deg, rgba(47,124,246,0.18), rgba(16,185,129,0.12));
        color: var(--between-text);
        border: 1px solid rgba(47,124,246,0.4);
    }}

    .stDataFrame, .stTable {{
        border: 1px solid var(--between-border);
        border-radius: 14px;
        overflow: hidden;
        box-shadow: var(--between-shadow);
    }}

    .stDataFrame > div {{
        background: rgba(255, 255, 255, 0.97);
    }}

    .stAlert,
    .stInfo,
    .stWarning,
    .stSuccess,
    .stError {{
        border-radius: 14px;
        border: 1px solid transparent;
        padding: 0.9rem 1rem;
    }}

    .stInfo {{
        background: rgba(47,124,246,0.12);
        border-color: rgba(47,124,246,0.25);
    }}

    .stSuccess {{
        background: rgba(16,185,129,0.12);
        border-color: rgba(16,185,129,0.2);
    }}

    .stWarning {{
        background: rgba(245,158,11,0.12);
        border-color: rgba(245,158,11,0.25);
    }}

    .stError {{
        background: rgba(239,68,68,0.12);
        border-color: rgba(239,68,68,0.2);
    }}

    .stMarkdownContainer code, pre {{
        direction: ltr !important;
        text-align: left !important;
    }}

    .stApp [data-testid="stVerticalBlockBorderWrapper"] > div,
    .stApp [data-testid="stVerticalBlock"] > div,
    .stApp [data-testid="stElementContainer"] > div {{
        border-radius: 16px;
    }}

    .brand-badge {{
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        background: linear-gradient(135deg, rgba(47,124,246,0.14), rgba(16,185,129,0.12));
        border: 1px solid rgba(47,124,246,0.28);
        border-radius: 999px;
        color: var(--between-text);
        font-weight: 700;
        padding: 0.5rem 0.9rem;
        margin-bottom: 0.75rem;
        box-shadow: var(--between-shadow);
    }}

    .stChatInput textarea {{
        direction: {direction};
        text-align: {text_align};
        background: rgba(15,23,42,0.72) !important;
        border: 1px solid var(--between-border) !important;
        border-radius: 14px !important;
    }}

    .stApp .element-container {{
        border-radius: 18px;
    }}
    </style>
    """


def apply_theme(lang: str | None = None) -> None:
    """Inject the current theme CSS into the Streamlit app."""
    import streamlit as st

    st.markdown(build_theme_css(lang), unsafe_allow_html=True)
