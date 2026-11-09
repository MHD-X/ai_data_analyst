"""
ui/dashboard.py — لوحة التحكم الرئيسية المتقدمة

تعرض:
    1. تقرير تدقيق البيانات والحجر الصحي (Data Audit & Quarantine)
    2. ملخص الملف الحالي ومعاينته
    3. إحصائيات المشروع والعمليات
    4. أكثر الطلبات تكراراً
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.anomaly import detect_anomalies
from core.audit_config import build_audit_config
from core.data_audit import audit_dataframe
from core.forecasting import build_series, detect_date_columns, forecast_series, make_figure
from core.memory import get_memory
from core.narrative import build_facts, llm_narrative, template_narrative
from ui.data_audit import render_audit_report
from ui.report_export import render_report_export
from utils.column_matcher import friendly_missing_column_message, resolve_column
from utils.helpers import (
    format_timestamp,
    get_dataframe_summary,
    truncate_text,
)
from utils.i18n import t

EMPTY_PERIOD_LABELS = {
    "zero": "اعتبرها صفراً (لا مبيعات)",
    "interpolate": "اعتبرها بيانات ناقصة (استكمال خطي)",
}


# ============================================================
# القسم 1: فحص البيانات وملخص الملف الحالي
# ============================================================
def _selected_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """يقرأ عمودَي التاريخ والمقياس اللذين اختارهما المستخدم (إن كانا صالحين)."""
    date_col = st.session_state.get("dash_select_date_col")
    value_col = st.session_state.get("dash_select_value_col")
    if date_col not in df.columns:
        date_col = None
    if value_col not in df.columns:
        value_col = None
    return date_col, value_col


def _render_current_file() -> None:
    """يعرض تقرير التدقيق والحجر الصحي وملخص الملف الحالي."""
    df: pd.DataFrame | None = st.session_state.get("df")
    if df is None:
        st.info(t("no_file"))
        return

    name = st.session_state.get("dataset_name") or "?"
    st.markdown(f"### 📄 {name}")

    summary = get_dataframe_summary(df)
    rows = summary.get("rows", 0)
    cols = summary.get("columns", 0)
    mem_mb = summary.get("memory_usage_mb", 0.0)

    # 1. قسم الحجر الصحي والتأكد من جودة البيانات أولاً
    st.markdown(f"#### {t('forecast.data_quality_heading')}")
    try:
        date_col, value_col = _selected_columns(df)
        cfg = build_audit_config(df, date_col=date_col, value_col=value_col)
        report = audit_dataframe(df, cfg)
        render_audit_report(report)
    except Exception as exc:
        st.warning(t("forecast.audit_error"))
        st.caption(f"{t('explanation')}: {exc}")

    st.divider()

    # 2. ملخص الهيكل والمعاينة الفنية
    st.markdown(f"#### {t('forecast.overview')}")
    c1, c2, c3 = st.columns(3)
    c1.metric(t("rows_label"), f"{rows:,}")
    c2.metric(t("cols_label"), f"{cols:,}")
    c3.metric("💾 RAM", f"{mem_mb:.2f} MB")

    # معاينة البيانات
    with st.expander(t("preview"), expanded=False):
        st.dataframe(df.head(20), use_container_width=True)

    # أنواع الأعمدة والقيم المفقودة
    with st.expander(t("columns"), expanded=False):
        dtypes = summary.get("dtypes", {})
        null_counts = summary.get("null_counts", {})
        cols_data = []
        for col_name, dtype in dtypes.items():
            cols_data.append({
                t("columns"): col_name,
                "Type": str(dtype),
                "Nulls": null_counts.get(col_name, 0),
            })
        if cols_data:
            st.dataframe(
                pd.DataFrame(cols_data),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# القسم 2: إحصائيات المشروع
# ============================================================
def _render_statistics() -> None:
    """يعرض إحصائيات قاعدة البيانات والعمليات."""
    st.markdown(f"### {t('dash_title')}")

    try:
        user_id = (st.session_state.get("user") or {}).get("id")
        stats = get_memory().get_statistics(user_id=user_id)
    except Exception as exc:
        st.warning(f"⚠️ تعذّر تحميل الإحصائيات: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("total_operations"), stats.get("total_operations", 0))
    c2.metric(
        t("success_rate"),
        f"{stats.get('success_rate', 0):.1f}%",
    )
    c3.metric(t("total_datasets"), stats.get("total_datasets", 0))
    c4.metric(t("total_sessions"), stats.get("total_sessions", 0))

    with st.expander("📊 " + t("results"), expanded=False):
        col_a, col_b, col_c = st.columns(3)
        col_a.metric(
            "✅ " + t("success"),
            stats.get("successful_operations", 0),
        )
        col_b.metric(
            "❌ " + t("failed"),
            stats.get("failed_operations", 0),
        )
        col_c.metric(
            "⏱️ متوسط الوقت",
            f"{stats.get('avg_execution_time', 0):.2f}s",
        )
        col_d, col_e = st.columns(2)
        col_d.metric(
            "⭐ متوسط التقييم",
            f"{stats.get('avg_rating', 0):.2f}",
        )
        col_e.metric(
            "🗜️ حجم DB",
            f"{stats.get('db_size_mb', 0):.2f} MB",
        )


# ============================================================
# القسم 3: آخر العمليات
# ============================================================
def _render_recent_operations() -> None:
    """يعرض آخر 10 عمليات من الذاكرة."""
    st.markdown(f"### {t('recent_operations')}")

    try:
        user_id = (st.session_state.get("user") or {}).get("id")
        ops = get_memory().list_operations(limit=10, user_id=user_id)
    except Exception as exc:
        st.warning(f"⚠️ تعذّر تحميل العمليات: {exc}")
        return

    if not ops:
        st.caption(t("no_operations"))
        return

    rows_data = []
    for op in ops:
        rows_data.append({
            "#": op.id,
            t("explanation"): truncate_text(op.user_request, 40),
            t("success"): "✅" if op.success else "❌",
            "⏱️": f"{op.execution_time:.2f}s",
            "📅": format_timestamp(op.created_at, "%m-%d %H:%M"),
        })

    if rows_data:
        st.dataframe(
            pd.DataFrame(rows_data),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# القسم 4: أكثر الطلبات تكراراً
# ============================================================
def _render_top_requests() -> None:
    """يعرض أكثر الطلبات تكراراً."""
    st.markdown(f"### {t('top_requests')}")

    try:
        user_id = (st.session_state.get("user") or {}).get("id")
        tops = get_memory().get_top_requests(limit=10, user_id=user_id)
    except Exception:
        tops = []

    if not tops:
        st.caption("—")
        return

    rows_data = []
    for i, item in enumerate(tops, 1):
        rows_data.append({
            "#": i,
            t("explanation"): truncate_text(item.get("request", ""), 60),
            "🔢": item.get("count", 0),
        })

    if rows_data:
        st.dataframe(
            pd.DataFrame(rows_data),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# تحليل البيانات والنتائج التنفيذية
# ============================================================
def build_dashboard_analysis(
    df: pd.DataFrame,
    *,
    date_col: str | None = None,
    value_col: str | None = None,
    agg: str = "sum",
    freq: str = "W",
    horizon: int = 4,
    threshold: float = 3.5,
    empty_periods: str = "zero",
) -> dict[str, Any]:
    """يُنشئ مجموعة كاملة من النتائج التنفيذية للوحة التحكم دون تعديل البيانات الأصلية.

    empty_periods:
        "zero"        → الفترة بلا سجلات تُعتبر صفراً (السلوك الافتراضي).
        "interpolate" → الفترة بلا سجلات تُعتبر بيانات ناقصة وتُستكمل خطياً.
    """
    if df is None or df.empty:
        raise ValueError("لا توجد بيانات لتحليلها.")

    analysis_df = df.copy()
    audit = None
    audit_error = None
    try:
        cfg = build_audit_config(df, date_col=date_col, value_col=value_col)
        audit = audit_dataframe(df, cfg)
        analysis_df = audit.valid.copy()
    except Exception as exc:
        audit_error = str(exc)

    date_candidates = detect_date_columns(analysis_df, min_ratio=0.5)
    if not date_candidates:
        raise ValueError("لم يُعثر على عمود تاريخ صالح في الملف.")
    chosen_date = resolve_column(analysis_df, date_col) if date_col is not None else date_candidates[0]
    if chosen_date is None:
        raise ValueError(friendly_missing_column_message(date_col, df, lang="ar"))

    numeric_cols = [c for c in analysis_df.columns if pd.api.types.is_numeric_dtype(analysis_df[c])]
    if not numeric_cols:
        raise ValueError("لا يوجد عمود رقمي مناسب للتحليل.")
    chosen_value = resolve_column(analysis_df, value_col) if value_col is not None else numeric_cols[0]
    if chosen_value is None:
        raise ValueError(friendly_missing_column_message(value_col, df, lang="ar"))

    series = build_series(
        analysis_df,
        date_col=chosen_date,
        value_col=None if chosen_value == "count" else chosen_value,
        agg=agg,
        freq=freq,
        dedupe_on=None,
        empty_periods=empty_periods,
    )
    result = forecast_series(series, horizon=horizon, freq=freq)
    anomalies = detect_anomalies(series, threshold=threshold)
    facts = build_facts(series, result, anomalies=anomalies, agg=agg)

    try:
        narrative, source = llm_narrative(facts)
    except Exception:
        narrative, source = template_narrative(facts), "template"

    return {
        "date_col": chosen_date,
        "value_col": chosen_value,
        "agg": agg,
        "freq": freq,
        "horizon": horizon,
        "threshold": threshold,
        "empty_periods": empty_periods,
        "series": series,
        "result": result,
        "anomalies": anomalies,
        "facts": facts,
        "narrative": narrative,
        "narrative_source": source,
        "audit": audit,
        "audit_error": audit_error,
        "rows_total": len(df),
        "rows_used": len(analysis_df),
        "metric": str(series.name),
    }


def _render_analysis_panel(bundle: dict[str, Any]) -> None:
    """يعرض النتائج التنفيذية (الملخص، الرسم، الشواذ، التصدير)."""
    result = bundle["result"]
    anomalies = bundle["anomalies"]
    narrative = bundle["narrative"]

    total_rows = int(bundle.get("rows_total", 0))
    rows_used = int(bundle.get("rows_used", 0))
    rows_excluded = max(total_rows - rows_used, 0)
    st.info(
        f"{t('forecast.total_rows')}: {total_rows:,} | {t('forecast.valid_rows')}: {rows_used:,} "
        f"| {t('forecast.quarantined_rows')}: {rows_excluded:,}"
    )
    if bundle.get("audit_error"):
        st.warning(t("forecast.audit_error"))

    st.markdown(f"### {t('forecast.summary_panel')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("forecast.model_label"), result.model_name)
    c2.metric(t("forecast.average_prediction"), f"{float(result.forecast['yhat'].mean()):,.2f}")
    c3.metric(t("forecast.last_value"), f"{float(bundle['series'].iloc[-1]):,.2f}")
    c4.metric(t("forecast.anomalies"), anomalies.count if anomalies is not None else 0)

    st.plotly_chart(make_figure(result), use_container_width=True)

    with st.expander(t("forecast.summary"), expanded=True):
        st.markdown(narrative)

    if anomalies is not None and anomalies.count:
        with st.expander("⚠️ " + t("forecast.anomalies"), expanded=False):
            display = anomalies.table.reset_index().rename(columns={
                "index": "التاريخ",
                "value": "القيمة",
                "expected": "المتوقعة",
                "score": "درجة الشذوذ",
                "direction": "الاتجاه",
            })
            st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.caption(t("forecast.no_anomalies"))

    render_report_export(bundle)


# ============================================================
# نقطة الدخول
# ============================================================
def render_dashboard(*args: Any, **kwargs: Any) -> None:
    """يرسم لوحة التحكم كاملة مع التنسيق والتصميم الاحترافي."""
    df = st.session_state.get("df")
    if df is None or not st.session_state.get("df_loaded"):
        st.info(t("no_file"))
        return

    st.markdown(f"### {t('forecast.auto_analysis')}")
    with st.container():
        date_options = detect_date_columns(df, min_ratio=0.5)
        metric_options = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if not date_options or not metric_options:
            st.warning(t("forecast.no_valid_data"))
            return

        c1, c2, c3, c4 = st.columns(4)
        date_col = c1.selectbox(t("forecast.date_column"), date_options, index=0, key="dash_select_date_col")
        value_col = c2.selectbox(t("forecast.metric"), metric_options, index=0, key="dash_select_value_col")
        freq = c3.selectbox(
            t("forecast.frequency"),
            ["D", "W", "ME"],
            format_func={"D": "Daily", "W": "Weekly", "ME": "Monthly"}.get,
            index=1,
            key="dash_select_freq",
        )
        horizon = c4.slider(t("forecast.prediction_window"), min_value=1, max_value=12, value=4, key="dash_slider_horizon")

        empty_periods = st.selectbox(
            t("forecast.empty_periods"),
            list(EMPTY_PERIOD_LABELS),
            format_func=lambda key: (
                t("forecast.empty_zero") if key == "zero" else t("forecast.empty_interpolate")
            ),
            index=0,
            key="dash_select_empty_periods",
            help=t("forecast.empty_periods_help"),
        )

        if st.button(t("forecast.run_analysis"), type="primary", use_container_width=True, key="dash_btn_run_analysis"):
            try:
                bundle = build_dashboard_analysis(
                    df,
                    date_col=date_col,
                    value_col=value_col,
                    agg="sum",
                    freq=freq,
                    horizon=horizon,
                    empty_periods=empty_periods,
                )
                st.session_state["analysis_bundle"] = bundle
            except Exception as exc:
                st.error(t("forecast.analysis_error", error=str(exc)))
                return

    bundle = st.session_state.get("analysis_bundle")
    if bundle is not None:
        _render_analysis_panel(bundle)

    _render_current_file()
    st.divider()
    _render_statistics()
    st.divider()
    _render_recent_operations()
    st.divider()
    _render_top_requests()