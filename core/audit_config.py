from __future__ import annotations

import re

import pandas as pd

from core.data_audit import AuditConfig
from core.forecasting import detect_date_columns

_ID_RE = re.compile(r"(^|[^a-z])id($|[^a-z])|معرف|رقم", re.IGNORECASE)


def _id_column_candidates(df: pd.DataFrame) -> list[str]:
    candidates: list[tuple[float, int, str]] = []
    for col in df.columns:
        name = str(col)
        if not _ID_RE.search(name):
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        uniqueness = float(s.nunique() / len(s))
        candidates.append((uniqueness, len(name), name))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [col for _, _, col in candidates]


def build_audit_config(
    df: pd.DataFrame,
    date_col: str | None = None,
    value_col: str | None = None,
) -> AuditConfig:
    """Pick the canonical date/id/metric columns for an audit."""
    if df is None or df.empty:
        return AuditConfig()

    date_cols: list[str] = []
    if date_col is not None and date_col in df.columns:
        date_cols = [str(date_col)]
    else:
        date_cols = [str(col) for col in detect_date_columns(df)]

    id_candidates = _id_column_candidates(df)
    id_col = id_candidates[0] if id_candidates else None

    metric = None
    if value_col is not None and str(value_col) in df.columns:
        metric = str(value_col)
    else:
        for col in df.columns:
            name = str(col)
            if name == str(id_col):
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                metric = name
                break

    numeric_cols = tuple([metric]) if metric else ()
    required_cols = list(dict.fromkeys([*date_cols, *numeric_cols]))
    return AuditConfig(
        date_cols=tuple(date_cols),
        numeric_cols=numeric_cols,
        required_cols=tuple(required_cols),
        id_col=id_col,
    )
