from __future__ import annotations

from utils.i18n import is_rtl


def build_theme_css(lang: str | None = None) -> str:
    """Theme CSS that follows the active Streamlit theme and stays RTL-aware."""
    is_rtl_lang = is_rtl(lang)
    direction = "rtl" if is_rtl_lang else "ltr"
    text_align = "right" if is_rtl_lang else "left"
    sidebar_side = "right" if is_rtl_lang else "left"
    sidebar_offset = "110%" if is_rtl_lang else "-110%"
    font_stack = "'Cairo', 'Segoe UI', Tahoma, sans-serif" if is_rtl_lang else "'Inter', 'Segoe UI', sans-serif"

    return f"""
    <style>
    /* Between Data - theme-safe styles */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');

    :root {{
        --theme-safe-border: var(--border-color, currentColor);
    }}

    html, body {{
        margin: 0;
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
    }}

    .stApp {{
        background: var(--background-color);
        color: var(--text-color);
        font-family: {font_stack};
        direction: {direction};
        min-height: 100vh;
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
    }}

    .stApp [data-testid="stMain"],
    .stApp .block-container {{
        width: 100% !important;
        max-width: 100% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        margin: 0 auto !important;
        overflow-x: hidden !important;
    }}

    [data-testid="stSidebar"] {{
        position: relative !important;
        background: var(--secondary-background-color);
        color: var(--text-color);
        border: 0 !important;
        border-{sidebar_side}: 1px solid var(--theme-safe-border) !important;
        width: 20rem !important;
        min-width: 15rem !important;
        max-width: 24rem !important;
        transition: width 0.25s ease, min-width 0.25s ease, max-width 0.25s ease, opacity 0.2s ease, transform 0.25s ease;
        overflow: hidden !important;
        z-index: 10 !important;
    }}

    [data-testid="stSidebar"] > div:first-child {{
        width: 100%;
        min-width: 0;
    }}

    [data-testid="stSidebar"][aria-expanded="false"] {{
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        opacity: 0 !important;
        transform: translateX({sidebar_offset}) !important;
        pointer-events: none !important;
        border-{sidebar_side}: 0 !important;
        overflow: hidden !important;
    }}

    [data-testid="stSidebarCollapsedControl"] {{
        position: fixed !important;
        top: 0.75rem !important;
        {sidebar_side}: 0.75rem !important;
        z-index: 2147483647 !important;
        background: var(--primary-color) !important;
        color: white !important;
        border: 0 !important;
        border-radius: 0.75rem !important;
        opacity: 1 !important;
        visibility: visible !important;
        pointer-events: auto !important;
    }}

    [data-testid="stSidebarCollapsedControl"]:hover {{
        filter: brightness(1.05);
    }}

    [data-testid="stHeader"] {{
        background: transparent !important;
    }}

    #MainMenu,
    footer,
    [data-testid="stDecoration"] {{
        display: none !important;
    }}

    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"],
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    .stTabs [role="tab"],
    .stSelectbox label,
    .stTextInput label,
    .stTextArea label,
    .stNumberInput label,
    .stDateInput label {{
        text-align: {text_align} !important;
        direction: {direction};
    }}

    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] .stMarkdownContainer {{
        color: var(--text-color) !important;
        opacity: 1 !important;
    }}

    .stApp .element-container,
    .stApp [data-testid="stVerticalBlockBorderWrapper"] > div,
    .stApp [data-testid="stVerticalBlock"] > div,
    .stApp [data-testid="stElementContainer"] > div {{
        border-radius: 16px;
    }}

    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div,
    .stDateInput > div > div > div,
    [data-baseweb="select"] > div {{
        background: var(--background-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--theme-safe-border) !important;
        border-radius: 14px !important;
    }}

    .stButton > button,
    .stFileUploader {{
        background: var(--primary-color);
        color: white;
        min-height: 40px;
        border: 0;
        border-radius: 10px;
        font-weight: 600;
    }}

    .stTabs [role="tablist"] {{
        background: var(--secondary-background-color);
        border-radius: 14px;
        padding: 0.2rem;
    }}

    .stTabs [role="tab"] {{
        color: var(--text-color);
        font-weight: 600;
        padding: 0.55rem 1rem;
    }}

    .stMarkdownContainer code,
    pre,
    [data-testid="stCode"],
    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    .js-plotly-plot {{
        direction: ltr !important;
        text-align: left !important;
    }}

    @media (max-width: 640px) {{
        .stApp [data-testid="stMain"],
        .stApp .block-container {{
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }}

        [data-testid="stSidebar"] {{
            width: 15rem !important;
            min-width: 15rem !important;
        }}
    }}
    </style>
    """


def apply_theme(lang: str | None = None) -> None:
    """Inject the current theme CSS into the Streamlit app."""
    import streamlit as st

    st.markdown(build_theme_css(lang), unsafe_allow_html=True)
