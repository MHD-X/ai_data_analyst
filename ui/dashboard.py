"""
ui/dashboard.py — لوحة التحكم الرئيسية

تعرض:
    1. ملخص الملف الحالي (صفوف/أعمدة/أنواع)
    2. معاينة البيانات
    3. إحصائيات المشروع (عمليات، نجاح، ملفات)
    4. آخر العمليات
    5. أكثر الطلبات تكراراً
    6. الأنواع الرسومية الموصى بها
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.memory import get_memory
from utils.helpers import (
    format_timestamp,
    get_dataframe_summary,
    truncate_text,
)
from utils.i18n import t


# ============================================================
# القسم 1: ملخص الملف الحالي
# ============================================================
def _render_current_file() -> None:
    """يعرض ملخصاً للملف الحالي إن وُجد."""
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

    # مقاييس في 3 أعمدة
    c1, c2, c3 = st.columns(3)
    c1.metric(t("rows_label"), f"{rows:,}")
    c2.metric(t("cols_label"), f"{cols:,}")
    c3.metric("💾 RAM", f"{mem_mb:.2f} MB")

    # معاينة في expander
    with st.expander(t("preview"), expanded=False):
        st.dataframe(df.head(20), use_container_width=True)

    # أنواع الأعمدة
    with st.expander(t("columns")):
        dtypes = summary.get("dtypes", {})
        null_counts = summary.get("null_counts", {})
        cols_data = []
        for col_name, dtype in dtypes.items():
            cols_data.append({
                t("columns"): col_name,
                "Type": dtype,
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
    """يعرض إحصائيات قاعدة البيانات."""
    st.markdown(f"### {t('dash_title')}")

    try:
        stats = get_memory().get_statistics()
    except Exception as exc:
        st.warning(f"⚠️ تعذّر تحميل الإحصائيات: {exc}")
        return

    # 4 مقاييس رئيسية
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("total_operations"), stats.get("total_operations", 0))
    c2.metric(
        t("success_rate"),
        f"{stats.get('success_rate', 0):.1f}%",
    )
    c3.metric(t("total_datasets"), stats.get("total_datasets", 0))
    c4.metric(t("total_sessions"), stats.get("total_sessions", 0))

    # مقاييس ثانوية
    with st.expander("📊 " + t("results")):
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

    # نبني جدول
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
# نقطة الدخول
# ============================================================
def render_dashboard(*args: Any, **kwargs: Any) -> None:
    """
    يرسم لوحة التحكم كاملة.
    يُستدعى من app.py داخل `with tab_dash:`.
    """
    # ملخص الملف الحالي
    _render_current_file()

    st.divider()

    # إحصائيات المشروع
    _render_statistics()

    st.divider()

    # آخر العمليات
    _render_recent_operations()

    st.divider()

    # أكثر الطلبات
    _render_top_requests()