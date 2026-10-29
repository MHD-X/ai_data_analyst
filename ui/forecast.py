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

_COUNT = "(عدد السجلات)"
_NONE = "—"


def render_forecast() -> None:
    df = st.session_state.get("df")
    if df is None or not st.session_state.get("df_loaded"):
        st.info("ارفع ملفاً من الشريط الجانبي أولاً.")
        return

    date_cols = detect_date_columns(df, min_ratio=0.5)
    if not date_cols:
        st.warning("لم يُعثر على عمود تاريخ صالح في الملف.")
        return

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    id_options = [_NONE, *df.columns]
    default_id = next(
        (i for i, c in enumerate(id_options) if "enrollment" in str(c).lower()), 0
    )

    c1, c2, c3 = st.columns(3)
    date_col = c1.selectbox("عمود التاريخ", date_cols)
    value_opt = c2.selectbox("المقياس", [_COUNT, *numeric_cols])
    freq = c3.selectbox("التجميع", list(FREQ_LABELS), format_func=FREQ_LABELS.get, index=1)

    c4, c5, c6 = st.columns(3)
    agg = c4.selectbox("الدالة", ["sum", "mean"], disabled=(value_opt == _COUNT))
    dedupe = c5.selectbox("إزالة التكرار حسب", id_options, index=default_id,
                          help="مهم لو الملف فيه صفوف مكررة لنفس السجل (مثل ربط الشهادات).")
    horizon = c6.slider("عدد الفترات القادمة", 1, 12, 4)

    audit_df = df
    audit_report = None
    try:
        audit_report = audit_dataframe(df, build_audit_config(df, date_col=date_col, value_col=None if value_opt == _COUNT else value_opt))
        audit_df = audit_report.valid
        c7, c8, c9 = st.columns(3)
        c7.metric("إجمالي الصفوف", f"{audit_report.total_rows:,}")
        c8.metric("✅ صالحة للاستخدام", f"{audit_report.valid_rows:,}")
        c9.metric("🚫 معزولة", f"{audit_report.quarantined_rows:,}")
        if not audit_report.summary_by_issue().empty:
            st.dataframe(audit_report.summary_by_issue(), hide_index=True, use_container_width=True)
    except Exception as exc:
        st.warning("⚠️ تعذّر فحص جودة البيانات؛ تم استخدام الملف الكامل مع تنبيه مرئي.")
        st.caption(f"السبب: {exc}")

    if not st.button("🔮 توليد التنبؤ", type="primary"):
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
        st.error(f"تعذّر إنشاء التنبؤ: {exc}")
        return

    for w in res.warnings:
        st.warning(w)

    last_avg = float(series.iloc[-4:].mean())
    nxt = float(res.forecast["yhat"].iloc[0])
    delta = ((nxt - last_avg) / last_avg * 100) if last_avg else 0.0
    m1, m2, m3 = st.columns(3)
    m1.metric("النموذج المختار", res.model_name)
    m2.metric("الفترة القادمة", f"{nxt:,.0f}", f"{delta:+.1f}% مقابل متوسط آخر 4")
    m3.metric("عدد الفترات التاريخية", len(series))

    st.plotly_chart(make_figure(res), use_container_width=True)

    with st.expander("جدول التنبؤ"):
        out = res.forecast.round(2)
        st.dataframe(out, use_container_width=True)
        st.download_button(
            "⬇️ تنزيل CSV",
            out.to_csv().encode("utf-8-sig"),
            file_name="forecast.csv",
            mime="text/csv",
        )
    if res.backtest_mae:
        with st.expander("مقارنة النماذج (MAE — الأقل أفضل)"):
            st.dataframe(
                pd.Series(res.backtest_mae, name="MAE").sort_values().to_frame().round(2),
                use_container_width=True,
            )