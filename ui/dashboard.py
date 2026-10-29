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


# ============================================================
# القسم 1: فحص البيانات وملخص الملف الحالي
# ============================================================
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
    st.markdown("#### 🛡️ تقرير جودة البيانات والحجر الصحي (Data Audit & Quarantine)")
    try:
        cfg = build_audit_config(df)
        report = audit_dataframe(df, cfg)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("إجمالي الصفوف", f"{report.total_rows:,}")
        c2.metric("✅ صالحة للتحليل", f"{report.valid_rows:,}")
        c3.metric("🚫 معزولة", f"{report.quarantined_rows:,}")
        c4.metric("📌 الأسباب", f"{len(report.summary_by_issue()):,}")
        if not report.summary_by_issue().empty:
            st.dataframe(report.summary_by_issue(), hide_index=True, use_container_width=True)
        render_audit_report(report)
    except Exception as exc:
        st.warning("⚠️ تعذّر فحص جودة البيانات؛ تم عرض الملف الكامل فقط مع تنبيه مرئي.")
        st.caption(f"السبب: {exc}")

    st.divider()

    # 2. ملخص الهيكل والمعاينة الفنية
    st.markdown("#### 📊 النظرة العامة والتركيب")
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
        stats = get_memory().get_statistics()
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
        ops = get_memory().list_operations(limit=10)
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
        tops = get_memory().get_top_requests(limit=10)
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
) -> dict[str, Any]:
    """يُنشئ مجموعة كاملة من النتائج التنفيذية للوحة التحكم دون تعديل البيانات الأصلية."""
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

    date_candidates = detect_date_columns(analysis_df)
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
    st.info(f"إجمالي الصفوف: {total_rows:,} | الصفوف المستعملة في التحليل: {rows_used:,} | الصفوف المستبعدة: {rows_excluded:,}")
    if bundle.get("audit_error"):
        st.warning("تعذّر فحص جودة البيانات؛ التحليل تم على الملف كاملاً دون استبعاد أي صف.")

    st.markdown("### 🔮 التنبؤ والملخص التنفيذي")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("النموذج", result.model_name)
    c2.metric("متوسط التنبؤ", f"{float(result.forecast['yhat'].mean()):,.2f}")
    c3.metric("آخر قيمة", f"{float(bundle['series'].iloc[-1]):,.2f}")
    c4.metric("الشواذ", anomalies.count if anomalies is not None else 0)

    st.plotly_chart(make_figure(result), use_container_width=True)

    with st.expander("📌 الملخص التنفيذي بالعربية", expanded=True):
        st.markdown(narrative)

    if anomalies is not None and anomalies.count:
        with st.expander("⚠️ القيم الشاذة", expanded=False):
            display = anomalies.table.reset_index().rename(columns={
                "index": "التاريخ",
                "value": "القيمة",
                "expected": "المتوقعة",
                "score": "درجة الشذوذ",
                "direction": "الاتجاه",
            })
            st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.caption("لم تُرصد قيم شاذة في السلسلة التاريخية.")

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

    st.markdown("### 📊 تحليل البيانات التلقائي")
    with st.container():
        date_options = detect_date_columns(df)
        metric_options = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if not date_options or not metric_options:
            st.warning("الملف الحالي لا يحتوي على عمود تاريخ صالح أو عمود رقمي مناسب للتحليل.")
            return

        c1, c2, c3, c4 = st.columns(4)
        date_col = c1.selectbox("عمود التاريخ", date_options, index=0, key="dash_select_date_col")
        value_col = c2.selectbox("المقياس", metric_options, index=0, key="dash_select_value_col")
        freq = c3.selectbox(
            "التجميع",
            ["D", "W", "ME"],
            format_func={"D": "يومي", "W": "أسبوعي", "ME": "شهري"}.get,
            index=1,
            key="dash_select_freq",
        )
        horizon = c4.slider("فترة التنبؤ", min_value=1, max_value=12, value=4, key="dash_slider_horizon")

        if st.button("🚀 إنشاء التحليل", type="primary", use_container_width=True, key="dash_btn_run_analysis"):
            try:
                bundle = build_dashboard_analysis(
                    df,
                    date_col=date_col,
                    value_col=value_col,
                    agg="sum",
                    freq=freq,
                    horizon=horizon,
                )
                st.session_state["analysis_bundle"] = bundle
            except Exception as exc:
                st.error(f"تعذّر إنشاء التحليل: {exc}")
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