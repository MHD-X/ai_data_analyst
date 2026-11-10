"""Canonical UI state and shared session helpers for the app."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from config import CONFIG
from core.memory import get_memory
from utils.helpers import now_iso


STATE_DEFAULTS: dict[str, Any] = {
    "lang": CONFIG.ui.default_language,
    "language": CONFIG.ui.default_language,
    "theme_mode": "light",
    "theme_dark_toggle": False,
    "df": None,
    "df_loaded": False,
    "data_path": None,
    "dataset_id": None,
    "dataset_name": None,
    "session_id": None,
    "messages": [],
    "last_operation_id": None,
}


def init_state() -> None:
    """Initialize missing session_state keys without overwriting existing values."""
    for key, value in STATE_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    if st.session_state.get("lang") is None:
        st.session_state["lang"] = CONFIG.ui.default_language
    if st.session_state.get("language") is None:
        st.session_state["language"] = st.session_state["lang"]
    if st.session_state.get("theme_mode") is None:
        st.session_state["theme_mode"] = "light"
    if st.session_state.get("theme_dark_toggle") is None:
        st.session_state["theme_dark_toggle"] = False
    from utils.i18n import normalize_language

    st.session_state["lang"] = normalize_language(st.session_state.get("lang"))
    st.session_state["language"] = normalize_language(st.session_state.get("language"))
    st.session_state["theme_mode"] = "dark" if st.session_state.get("theme_dark_toggle") else "light"


def set_dataframe(
    df: pd.DataFrame | None,
    *,
    path: str | None = None,
    name: str | None = None,
    dataset_id: int | None = None,
    reset_messages: bool = False,
) -> None:
    """Persist the current dataframe and related metadata in session_state."""
    ss = st.session_state
    ss["df"] = df
    ss["df_loaded"] = bool(df is not None and not (hasattr(df, "empty") and df.empty))
    if path is not None:
        ss["data_path"] = path
    if name is not None:
        ss["dataset_name"] = name
    if dataset_id is not None:
        ss["dataset_id"] = dataset_id
    if reset_messages:
        ss["messages"] = []
        ss["last_operation_id"] = None


def clear_dataframe() -> None:
    """Clear the active dataframe and associated conversation state."""
    ss = st.session_state
    ss["df"] = None
    ss["df_loaded"] = False
    ss["data_path"] = None
    ss["dataset_id"] = None
    ss["dataset_name"] = None
    ss["messages"] = []
    ss["last_operation_id"] = None


def reset_dataset_state() -> None:
    """Reset dataset-specific state when a new file is selected or removed."""
    clear_dataframe()


def get_dataframe() -> pd.DataFrame | None:
    return st.session_state.get("df")


def has_dataframe() -> bool:
    return bool(st.session_state.get("df_loaded"))


def ensure_session() -> int:
    ss = st.session_state
    user = ss.get("user") or {}
    user_id = user.get("id")
    sid = ss.get("session_id")

    if sid is not None:
        memory = get_memory()
        current_session = memory.get_session(int(sid), user_id=user_id)
        if current_session is not None:
            return sid
        ss["session_id"] = None

    memory = get_memory()
    sid = memory.create_session(
        name=f"Session {now_iso()}",
        metadata={"source": "streamlit"},
        user_id=int(user_id) if user_id is not None else None,
    )
    ss["session_id"] = sid
    return sid


def render_chat(*args: Any, **kwargs: Any) -> None:
    from ui.chat import render_chat as _render_chat

    return _render_chat(*args, **kwargs)


def render_dashboard(*args: Any, **kwargs: Any) -> None:
    from ui.dashboard import render_dashboard as _render_dashboard

    return _render_dashboard(*args, **kwargs)


def render_sidebar(*args: Any, **kwargs: Any) -> None:
    from ui.sidebar import render_sidebar as _render_sidebar

    return _render_sidebar(*args, **kwargs)


__all__ = [
    "init_state",
    "ensure_session",
    "set_dataframe",
    "clear_dataframe",
    "reset_dataset_state",
    "get_dataframe",
    "has_dataframe",
    "render_chat",
    "render_dashboard",
    "render_sidebar",
]
