from __future__ import annotations

import html

import streamlit as st

from utils.i18n import is_rtl, t


def build_theme_css(lang: str | None = None, mode: str | None = None) -> str:
    direction = "rtl" if is_rtl(lang) else "ltr"
    code_direction = "ltr"
    return f"""
<style>
/* Between Data */
:root {{ --bd-radius: 12px; }}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {{ direction: {direction}; }}
[data-testid="stSidebar"] {{ direction: {direction}; }}
[data-testid="stMain"], [data-testid="stSidebar"] {{
  --bd-border: color-mix(in srgb, currentColor 18%, transparent);
  --bd-muted: color-mix(in srgb, currentColor 68%, transparent);
  --bd-surface: color-mix(in srgb, currentColor 5%, transparent);
}}
[data-testid="stMain"] .stMarkdown, [data-testid="stMain"] .stForm,
[data-testid="stMain"] .stDataFrameContainer, [data-testid="stMain"] .stTextInput,
[data-testid="stMain"] .stSelectbox, [data-testid="stMain"] .stFileUploader {{ text-align: start; }}
[data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] .stForm,
[data-testid="stSidebar"] .stTextInput, [data-testid="stSidebar"] .stSelectbox {{ text-align: start; }}
.bd-brand {{ display: inline-flex; align-items: baseline; gap: 0.28em; font-weight: 800; direction: ltr; }}
.bd-brand-mark {{ width: 1.55em; height: 1.55em; display: inline-grid; place-items: center; border-radius: 0.35em; background: hsl(221 83% 53%); color: hsl(0 0% 100%); font-size: 0.72em; }}
.bd-brand-accent {{ color: hsl(221 83% 53%); }}
.bd-brand-large {{ font-size: clamp(1.8rem, 5vw, 3rem); }}
.bd-brand-center {{ justify-content: center; width: 100%; }}
.auth-card, .bd-card, [data-testid="stExpander"] {{ border: 1px solid var(--bd-border); border-radius: var(--bd-radius); }}
.auth-card, .bd-card {{ padding: 1.25rem; background: var(--bd-surface); }}
.bd-metric-card {{ border: 1px solid var(--bd-border); border-radius: var(--bd-radius); padding: 0.9rem; }}
[data-testid="stChatMessage"] {{ border: 1px solid var(--bd-border); border-radius: var(--bd-radius); }}
.stButton > button {{ border-radius: var(--bd-radius); font-weight: 650; transition: filter 160ms ease, transform 160ms ease; }}
.stButton > button:hover {{ filter: brightness(1.05); }}
.stButton > button:active {{ transform: translateY(1px); }}
.stTabs [role="tab"] {{ border-bottom: 2px solid transparent; }}
.stTabs [role="tab"][aria-selected="true"] {{ border-bottom-color: hsl(221 83% 53%); }}
.stFileUploader {{ border: 1.5px dashed var(--bd-border); border-radius: var(--bd-radius); }}
.stFileUploader [data-testid="stFileUploaderDropzone"] {{ border: 1.5px dashed var(--bd-border); }}
.stFileUploader [data-testid="stFileUploaderDropzone"] svg {{ width: 1.6rem; height: 1.6rem; }}
.stDataFrame, [data-testid="stTable"] {{ direction: {code_direction}; }}
[data-testid="stPlotlyChart"] {{ direction: ltr; }}
pre, code {{ direction: ltr; text-align: left; }}
button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible,
[data-baseweb="select"]:focus-visible {{ outline: 2px solid hsl(221 83% 53%); outline-offset: 2px; }}
.bd-empty {{ max-width: 38rem; margin: 1.5rem auto; text-align: center; color: var(--bd-muted); }}
.bd-empty-icon {{ font-size: 1.6rem; line-height: 1; opacity: 0.75; }}
@media (max-width: 760px) {{
  [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  [data-testid="stHorizontalBlock"] > div {{ width: 100% !important; flex: 1 1 100% !important; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .stButton > button {{ transition: none; }}
}}
</style>
"""


def apply_theme(lang: str | None = None, mode: str | None = None) -> None:
    st.markdown(build_theme_css(lang=lang or st.session_state.get("lang") or "ar"), unsafe_allow_html=True)


def brand_html(large: bool = False) -> str:
    size_class = " bd-brand-large" if large else ""
    return (f'<span class="bd-brand{size_class}" aria-label="Between Data">'
            '<span class="bd-brand-mark">B</span><span>Between</span>'
            '<span class="bd-brand-accent">Data</span></span>')


def render_brand(large: bool = True, center: bool = True) -> None:
    center_class = " bd-brand-center" if center else ""
    st.markdown(f'<div class="bd-brand{center_class}">{brand_html(large).replace("bd-brand-large", "")}</div>', unsafe_allow_html=True)


def render_empty_state(message: str | None = None) -> None:
    text = html.escape(message or t("no_file"))
    st.markdown(f'<div class="bd-empty"><div class="bd-empty-icon">+</div><p>{text}</p></div>', unsafe_allow_html=True)


def render_welcome_card(message: str) -> None:
    render_empty_state(message)
