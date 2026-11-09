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
from utils.i18n import t

MAX_DISPLAY_ROWS = 2000
EMPTY_MARK = "⟨فارغ⟩"


def _display(df: pd.DataFrame) -> pd.DataFrame:
    return df.astype("string").fillna(EMPTY_MARK)


def render_audit_report(report: AuditReport) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("audit.total_rows"), f"{report.total_rows:,}")
    c2.metric(t("audit.valid_rows"), f"{report.valid_rows:,}")
    c3.metric(t("audit.quarantined_rows"), f"{report.quarantined_rows:,}")
    c4.metric(t("audit.warning_rows"), f"{report.warning_rows:,}")
    st.caption(t("audit.summary_message"))

    if report.issues.empty:
        st.success(t("audit.no_issues"))
    else:
        st.dataframe(report.summary_by_issue(), hide_index=True, use_container_width=True)

    tab_valid, tab_q, tab_w = st.tabs([
        "✅ " + t("audit.valid_rows"),
        "🚫 " + t("audit.quarantined_rows"),
        "⚠️ " + t("audit.warning_rows"),
    ])

    with tab_valid:
        st.caption(t("audit.preview_rows", count=min(200, report.valid_rows), total=f"{report.valid_rows:,}"))
        st.dataframe(_display(report.valid.head(200)), use_container_width=True)

    with tab_q:
        if report.quarantined_rows == 0:
            st.success(t("audit.no_quarantine"))
        else:
            st.warning(t("audit.review_quarantine"))
            if report.quarantined_rows > MAX_DISPLAY_ROWS:
                st.caption(f"{t('audit.preview_rows', count=MAX_DISPLAY_ROWS, total=f'{report.quarantined_rows:,}')}")
            st.dataframe(_display(report.quarantine.head(MAX_DISPLAY_ROWS)), use_container_width=True)
            st.download_button(
                t("audit.download_quarantine"),
                neutralize_formulas(report.quarantine).to_csv(index=False).encode("utf-8-sig"),
                file_name="quarantine.csv",
                mime="text/csv",
                key="btn_download_quarantine_csv",
            )

    with tab_w:
        warns = report.issues[report.issues["severity"] != ERROR] if not report.issues.empty else report.issues
        if warns.empty:
            st.success(t("audit.no_warnings"))
        else:
            st.caption(t("audit.warning_review"))
            view = warns[["row_number", "column", "issue_type", "message", "raw_value"]].head(MAX_DISPLAY_ROWS)
            view.columns = [t("audit.row_number"), t("audit.column"), t("audit.issue_type"), t("audit.detail"), t("audit.value")]
            st.dataframe(view, hide_index=True, use_container_width=True)