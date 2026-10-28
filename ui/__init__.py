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
    st.session_state["dataset_id"] = None
    st.session_state["df"] = None
    st.session_state["df_loaded"] = False
    st.session_state["data_path"] = None
    st.session_state["dataset_name"] = None
    st.session_state["messages"] = []
    st.session_state["last_operation_id"] = None


def get_dataframe() -> pd.DataFrame | None:
    return st.session_state.get("df")


def has_dataframe() -> bool:
    return bool(st.session_state.get("df_loaded"))


def ensure_session() -> int:
    sid = st.session_state.get("session_id")
    if sid is not None:
        return sid
    memory = get_memory()
    sid = memory.create_session(name=f"Session {now_iso()}", metadata={"source": "streamlit"})
    st.session_state["session_id"] = sid
    return sid


from ui.chat import render_chat  # noqa: E402
from ui.dashboard import render_dashboard  # noqa: E402
from ui.sidebar import render_sidebar  # noqa: E402


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
