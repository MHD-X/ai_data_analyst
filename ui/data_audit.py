"""
ui/data_audit.py — عرض نتيجة فحص البيانات: قسم "الصالحة" وقسم "المعزولة (Quarantine)".
لا يعدّل أي بيانات؛ يعرض فقط. (التحويل لنصوص هنا للعرض فقط حتى لا يفشل Arrow مع الأعمدة المختلطة.)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from core.data_audit import ERROR, AuditReport, neutralize_formulas

MAX_DISPLAY_ROWS = 2000
EMPTY_MARK = "⟨فارغ⟩"


def _display(df: pd.DataFrame) -> pd.DataFrame:
    return df.astype("string").fillna(EMPTY_MARK)


def render_audit_report(report: AuditReport) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("إجمالي الصفوف", f"{report.total_rows:,}")
    c2.metric("✅ صالحة للتحليل", f"{report.valid_rows:,}")
    c3.metric("🚫 معزولة", f"{report.quarantined_rows:,}")
    c4.metric("⚠️ تحذيرات", f"{report.warning_rows:,}")
    st.caption("لم يُحذف أو يُعدَّل أي صف، ولم تُعوَّض أي قيمة مفقودة: الصالح + المعزول = الإجمالي.")

    if report.issues.empty:
        st.success("لم يُكتشف أي مشكلة في الأعمدة الحرجة المختارة.")
    else:
        st.dataframe(report.summary_by_issue(), hide_index=True, use_container_width=True)

    tab_valid, tab_q, tab_w = st.tabs(["✅ البيانات الصالحة", "🚫 البيانات المعزولة (Quarantine)", "⚠️ التحذيرات"])

    with tab_valid:
        st.caption(f"معاينة أول {min(200, report.valid_rows)} صف من {report.valid_rows:,}")
        st.dataframe(_display(report.valid.head(200)), use_container_width=True)

    with tab_q:
        if report.quarantined_rows == 0:
            st.success("لا توجد صفوف معزولة.")
        else:
            st.warning("هذه الصفوف لن تدخل التحليل. راجعها يدوياً وصحّحها في ملفك الأصلي ثم أعد رفعه.")
            if report.quarantined_rows > MAX_DISPLAY_ROWS:
                st.caption(f"يُعرض أول {MAX_DISPLAY_ROWS:,} صف؛ التنزيل يشمل الكل.")
            st.dataframe(_display(report.quarantine.head(MAX_DISPLAY_ROWS)), use_container_width=True)
            st.download_button(
                "⬇️ تنزيل الصفوف المعزولة (CSV)",
                neutralize_formulas(report.quarantine).to_csv(index=False).encode("utf-8-sig"),
                file_name="quarantine.csv",
                mime="text/csv",
                key="btn_download_quarantine_csv",
            )

    with tab_w:
        warns = report.issues[report.issues["severity"] != ERROR] if not report.issues.empty else report.issues
        if warns.empty:
            st.success("لا توجد تحذيرات.")
        else:
            st.caption("صفوف تبقى صالحة للتحليل لكنها تستحق المراجعة (مثل المعرّفات المكررة).")
            view = warns[["row_number", "column", "issue_type", "message", "raw_value"]].head(MAX_DISPLAY_ROWS)
            view.columns = ["رقم الصف", "العمود", "المشكلة", "التفصيل", "القيمة"]
            st.dataframe(view, hide_index=True, use_container_width=True)