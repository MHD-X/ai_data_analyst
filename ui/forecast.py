"""
ui/forecast.py — تبويب التنبؤات
يقرأ st.session_state["df"] ولا يستدعي أي LLM.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.audit_config import build_audit_config
from core.data_audit import audit_dataframe
from core.forecasting import (
    FREQ_LABELS,
    build_series,
    detect_date_columns,
    forecast_series,
    make_figure,
)
from utils.i18n import get_lang, t

_COUNT = "__count__"
_NONE = "—"


def _freq_label(code: str) -> str:
    return {
        "D": t("period_daily"),
        "W": t("period_weekly"),
        "ME": t("period_monthly"),
    }.get(code, code)


def render_forecast() -> None:
    df = st.session_state.get("df")
    if df is None or not st.session_state.get("df_loaded"):
        st.info(t("forecast.no_file"))
        return

    date_cols = detect_date_columns(df, min_ratio=0.5)
    if not date_cols:
        st.warning(t("forecast.no_valid_date"))
        return

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    id_options = [_NONE, *df.columns]
    default_id = next(
        (i for i, c in enumerate(id_options) if "enrollment" in str(c).lower()), 0
    )

    c1, c2, c3 = st.columns(3)
    count_label = t("forecast.count_records")
    date_col = c1.selectbox(t("forecast.date_column"), date_cols)
    value_opt = c2.selectbox(
        t("forecast.metric"),
        [_COUNT, *numeric_cols],
        format_func=lambda code: count_label if code == _COUNT else code,
    )
    freq = c3.selectbox(t("forecast.frequency"), list(FREQ_LABELS), format_func=_freq_label, index=1)

    c4, c5, c6 = st.columns(3)
    agg = c4.selectbox(t("forecast.aggregate"), ["sum", "mean"], disabled=(value_opt == _COUNT))
    dedupe = c5.selectbox(
        t("forecast.dedupe"),
        id_options,
        index=default_id,
        help=t("forecast.dedupe_help"),
    )
    horizon = c6.slider(t("forecast.horizon"), 1, 12, 4)

    audit_df = df
    audit_report = None
    try:
        audit_report = audit_dataframe(df, build_audit_config(df, date_col=date_col, value_col=None if value_opt == _COUNT else value_opt))
        audit_df = audit_report.valid
        c7, c8, c9 = st.columns(3)
        c7.metric(t("forecast.total_rows"), f"{audit_report.total_rows:,}")
        c8.metric(t("forecast.valid_rows"), f"{audit_report.valid_rows:,}")
        c9.metric(t("forecast.quarantined_rows"), f"{audit_report.quarantined_rows:,}")
        if not audit_report.summary_by_issue().empty:
            st.dataframe(audit_report.summary_by_issue(), hide_index=True, use_container_width=True)
    except Exception as exc:
        st.warning(t("forecast.audit_error"))
        st.caption(f"{t('explanation')}: {exc}")

    if not st.button(t("forecast.generate"), type="primary"):
        return

    try:
        series = build_series(
            audit_df,
            date_col=date_col,
            value_col=None if value_opt == _COUNT else value_opt,
            agg=agg,
            freq=freq,
            dedupe_on=None if dedupe == _NONE else dedupe,
        )
        res = forecast_series(series, horizon=horizon, freq=freq)
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(t("forecast.analysis_error", error=str(exc)))
        return

    for w in res.warnings:
        st.warning(w)

    last_avg = float(series.iloc[-4:].mean())
    nxt = float(res.forecast["yhat"].iloc[0])
    delta = ((nxt - last_avg) / last_avg * 100) if last_avg else 0.0
    m1, m2, m3 = st.columns(3)
    m1.metric(t("forecast.model"), res.model_name)
    m2.metric(t("forecast.next_period"), f"{nxt:,.0f}", f"{delta:+.1f}% vs last 4 average")
    m3.metric(t("forecast.history_periods"), len(series))

    st.plotly_chart(make_figure(res), use_container_width=True)

    with st.expander(t("forecast.table")):
        out = res.forecast.round(2)
        st.dataframe(out, use_container_width=True)
        st.download_button(
            t("forecast.download_csv"),
            out.to_csv().encode("utf-8-sig"),
            file_name="forecast.csv",
            mime="text/csv",
        )
    if res.backtest_mae:
        with st.expander(t("forecast.model_comparison")):
            st.dataframe(
                pd.Series(res.backtest_mae, name="MAE").sort_values().to_frame().round(2),
                use_container_width=True,
            )