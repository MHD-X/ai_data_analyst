from __future__ import annotations

import pandas as pd

from core.data_audit import AuditConfig
from core.forecasting import detect_date_columns


def _id_column_candidates(df: pd.DataFrame) -> list[str]:
    candidates: list[tuple[float, int, str]] = []
    for col in df.columns:
        name = str(col).lower()
        if not any(token in name for token in ("id", "معرف", "رقم")):
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        uniqueness = float(s.nunique() / len(s))
        candidates.append((uniqueness, len(str(col)), str(col)))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [col for _, _, col in candidates]


def build_audit_config(
    df: pd.DataFrame,
    date_col: str | None = None,
    value_col: str | None = None,
) -> AuditConfig:
    """Creates a deterministic audit configuration for the current dataframe."""
    if df is None or df.empty:
        return AuditConfig()

    date_cols: list[str] = []
    if date_col is not None and date_col in df.columns:
        date_cols = [str(date_col)]
    else:
        date_cols = [str(col) for col in detect_date_columns(df)]

    id_col = None
    id_candidates = _id_column_candidates(df)
    if id_candidates:
        id_col = id_candidates[0]

    numeric_cols = [
        str(col)
        for col in df.columns
        if pd.api.types.is_numeric_dtype(df[col]) and str(col) != str(id_col)
    ]

    chosen_metric = None
    if value_col is not None and str(value_col) in df.columns:
        chosen_metric = str(value_col)
    elif numeric_cols:
        chosen_metric = numeric_cols[0]

    required = list(dict.fromkeys([*date_cols, *( [chosen_metric] if chosen_metric else [] )]))
    return AuditConfig(
        date_cols=tuple(date_cols),
        numeric_cols=tuple(numeric_cols),
        required_cols=tuple(required),
        id_col=id_col,
    )
