"""
core/report_export.py — تصدير تقرير التنبؤ (Excel منسّق + PDF عربي)

المتطلبات: xlsxwriter, reportlab, matplotlib, arabic-reshaper, python-bidi
الخط: يُستخدم DejaVu Sans المرفق مع matplotlib (يدعم العربية دون إعداد).
      لخط أجمل ضع Regular.ttf و Bold.ttf (مثلاً Cairo) في assets/fonts/.
"""
from __future__ import annotations

import io
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from core.anomaly import AnomalyResult
from core.data_audit import AuditReport, neutralize_formulas
from core.forecasting import ForecastResult
from core.narrative import ForecastFacts, facts_rows

ASSETS_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MAX_QUARANTINE_ROWS = 10_000
DISCLAIMER = ("هذا تقرير تنبؤ إحصائي مبني على البيانات التاريخية المرفوعة فقط، "
              "ولا يأخذ في الحسبان عوامل خارجية. استخدمه كأداة مساندة للقرار لا كضمان للنتائج.")


@dataclass
class ReportBundle:
    metric: str
    series: pd.Series
    result: ForecastResult
    facts: ForecastFacts
    narrative: str
    narrative_source: str                       # "llm" | "template"
    anomalies: AnomalyResult | None = None
    audit: AuditReport | None = None
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")


def plain_paragraphs(text: str) -> list[str]:
    """نص السرد بدون رموز Markdown، فقرة لكل عنصر."""
    clean = re.sub(r"\*\*|__|`", "", text)
    return [p.strip() for p in re.split(r"\n\s*\n|\n", clean) if p.strip()]


def _source_label(src: str) -> str:
    return "صياغة آلية بالذكاء الاصطناعي من أرقام محسوبة" if src == "llm" else "صياغة آلية من قالب جاهز"


# ============================================================
# Excel
# ============================================================
def _combined_frame(b: ReportBundle) -> pd.DataFrame:
    y, fc = b.series, b.result.forecast
    idx = y.index.append(fc.index)
    comb = pd.DataFrame(index=idx, columns=["الفعلي", "التنبؤ", "الحد الأدنى", "الحد الأعلى", "قيمة شاذة"],
                        dtype="float64")
    comb.loc[y.index, "الفعلي"] = y.values
    comb.loc[fc.index, "التنبؤ"] = fc["yhat"].values
    comb.loc[fc.index, "الحد الأدنى"] = fc["lower"].values
    comb.loc[fc.index, "الحد الأعلى"] = fc["upper"].values
    comb.loc[y.index[-1], "التنبؤ"] = y.iloc[-1]          # استمرارية الخط
    if b.anomalies is not None and b.anomalies.count:
        comb.loc[b.anomalies.table.index, "قيمة شاذة"] = b.anomalies.table["value"].values
    comb.index.name = "التاريخ"
    return comb


def _autosize(ws, df: pd.DataFrame, with_index: bool = False, cap: int = 45) -> None:
    cols = ([df.index.name or ""] if with_index else []) + [str(c) for c in df.columns]
    for i, name in enumerate(cols):
        series = df.index if (with_index and i == 0) else df.iloc[:, i - (1 if with_index else 0)]
        sample = [len(str(v)) for v in list(series)[:200]]
        ws.set_column(i, i, min(max([len(name), *sample, 8]) + 3, cap))


def build_excel_report(b: ReportBundle) -> bytes:
    buf = io.BytesIO()
    opts = {"options": {"strings_to_formulas": False, "strings_to_urls": False}}  # حماية من حقن الصيغ
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="yyyy-mm-dd",
                        date_format="yyyy-mm-dd", engine_kwargs=opts) as writer:
        wb = writer.book
        base = {"font_name": "Arial", "font_size": 11}
        F = {
            "title": wb.add_format({**base, "bold": True, "font_size": 18, "font_color": "#1F3864", "align": "right"}),
            "h": wb.add_format({**base, "bold": True, "font_size": 13, "font_color": "#FFFFFF", "bg_color": "#2F5597", "align": "right"}),
            "wrap": wb.add_format({**base, "text_wrap": True, "valign": "top", "align": "right"}),
            "label": wb.add_format({**base, "bold": True, "bg_color": "#DDEBF7", "border": 1, "align": "right"}),
            "value": wb.add_format({**base, "border": 1, "align": "right"}),
            "num": wb.add_format({**base, "num_format": "#,##0.00"}),
            "note": wb.add_format({**base, "italic": True, "font_color": "#7F7F7F", "text_wrap": True, "align": "right"}),
        }
        _sheet_summary(wb, b, F)
        _sheet_forecast(writer, wb, b, F)
        _sheet_anomalies(writer, wb, b, F)
        _sheet_quality(writer, wb, b, F)
    return buf.getvalue()


def _sheet_summary(wb, b: ReportBundle, F) -> None:
    ws = wb.add_worksheet("الملخص")
    ws.right_to_left()
    ws.set_column(0, 0, 32)
    ws.set_column(1, 1, 80)
    ws.merge_range(0, 0, 0, 1, f"تقرير التنبؤ — {b.metric}", F["title"])
    ws.set_row(0, 30)
    ws.merge_range(1, 0, 1, 1, f"تاريخ الإنشاء: {b.generated_at}  |  {_source_label(b.narrative_source)}", F["note"])

    row = 3
    ws.merge_range(row, 0, row, 1, "الملخص التنفيذي", F["h"])
    row += 1
    for para in plain_paragraphs(b.narrative):
        ws.merge_range(row, 0, row, 1, para, F["wrap"])
        ws.set_row(row, 16 * max(1, math.ceil(len(para) / 95)))
        row += 1

    row += 1
    ws.merge_range(row, 0, row, 1, "المؤشرات الرئيسية", F["h"])
    row += 1
    for label, value in facts_rows(b.facts):
        ws.write_string(row, 0, label, F["label"])
        ws.write_string(row, 1, value, F["value"])
        row += 1

    row += 1
    ws.merge_range(row, 0, row, 1, DISCLAIMER, F["note"])
    ws.set_row(row, 34)


def _sheet_forecast(writer, wb, b: ReportBundle, F) -> None:
    name = "التنبؤ"
    comb = _combined_frame(b)
    comb.to_excel(writer, sheet_name=name)
    ws = writer.sheets[name]
    ws.right_to_left()
    ws.set_column(0, 0, 14)
    ws.set_column(1, 5, 16, F["num"])
    ws.freeze_panes(1, 1)

    rows = len(comb)
    chart = wb.add_chart({"type": "line"})

    def add(col: int, **kw) -> None:
        chart.add_series({
            "name": [name, 0, col],
            "categories": [name, 1, 0, rows, 0],
            "values": [name, 1, col, rows, col],
            **kw,
        })

    add(1, line={"color": "#2F5597", "width": 2.25}, marker={"type": "circle", "size": 4})
    add(2, line={"color": "#ED7D31", "width": 2.25, "dash_type": "dash"})
    add(3, line={"color": "#A5A5A5", "width": 1, "dash_type": "round_dot"})
    add(4, line={"color": "#A5A5A5", "width": 1, "dash_type": "round_dot"})
    if b.anomalies is not None and b.anomalies.count:
        add(5, line={"none": True},
            marker={"type": "diamond", "size": 10, "fill": {"color": "red"}, "border": {"color": "red"}})
    chart.set_title({"name": f"التنبؤ — {b.metric}"})
    chart.set_x_axis({"date_axis": True, "num_format": "yyyy-mm-dd", "label_position": "low"})
    chart.set_legend({"position": "bottom"})
    chart.set_size({"width": 900, "height": 430})
    ws.insert_chart(1, 7, chart)


def _sheet_anomalies(writer, wb, b: ReportBundle, F) -> None:
    name = "الشواذ"
    if b.anomalies is None or not b.anomalies.count:
        ws = wb.add_worksheet(name)
        ws.right_to_left()
        ws.set_column(0, 0, 70)
        ws.write_string(0, 0, "لم تُرصد قيم شاذة في البيانات التاريخية.", F["wrap"])
        return
    t = b.anomalies.table.rename(columns={"value": "القيمة الفعلية", "expected": "القيمة المتوقعة",
                                          "score": "درجة الشذوذ", "direction": "الاتجاه"})
    t.index.name = "التاريخ"
    t.round(2).to_excel(writer, sheet_name=name)
    ws = writer.sheets[name]
    ws.right_to_left()
    _autosize(ws, t, with_index=True)


def _sheet_quality(writer, wb, b: ReportBundle, F) -> None:
    a = b.audit
    if a is None:
        return
    name = "جودة البيانات"
    ws = wb.add_worksheet(name)
    ws.right_to_left()
    ws.set_column(0, 0, 32)
    ws.set_column(1, 3, 22)
    ws.write_string(0, 0, "إجمالي الصفوف", F["label"]); ws.write_number(0, 1, a.total_rows, F["value"])
    ws.write_string(1, 0, "صالحة للتحليل", F["label"]); ws.write_number(1, 1, a.valid_rows, F["value"])
    ws.write_string(2, 0, "معزولة (Quarantine)", F["label"]); ws.write_number(2, 1, a.quarantined_rows, F["value"])
    ws.write_string(3, 0, "صفوف بها تحذيرات", F["label"]); ws.write_number(3, 1, a.warning_rows, F["value"])
    ws.merge_range(4, 0, 4, 3, "لم يُحذف أو يُعدَّل أي صف: الصالح + المعزول = الإجمالي.", F["note"])

    summary = a.summary_by_issue()
    for j, col in enumerate(summary.columns):
        ws.write_string(6, j, col, F["h"])
    for i, rec in enumerate(summary.itertuples(index=False), start=7):
        for j, v in enumerate(rec):
            ws.write(i, j, v, F["value"])

    if a.quarantined_rows:
        q = neutralize_formulas(a.quarantine.head(MAX_QUARANTINE_ROWS))
        q = q.astype(object).where(q.notna(), None)
        q.to_excel(writer, sheet_name="الصفوف المعزولة", index=False)
        qws = writer.sheets["الصفوف المعزولة"]
        qws.right_to_left()
        qws.freeze_panes(1, 0)
        _autosize(qws, q, cap=60)


# ============================================================
# PDF
# ============================================================
_RE_AR = re.compile(r"[\u0600-\u06FF]")


def _ar(text) -> str:
    """نص عربي → ترتيب بصري صحيح (تشكيل الحروف + bidi)."""
    import arabic_reshaper
    try:
        from bidi import get_display
    except ImportError:  # python-bidi < 0.5
        from bidi.algorithm import get_display
    text = "" if text is None else str(text)
    return get_display(arabic_reshaper.reshape(text), base_dir="R")


def _cell(text) -> str:
    text = "" if text is None else str(text)
    return _ar(text) if _RE_AR.search(text) else text


def _font_paths() -> tuple[str, str]:
    reg, bold = ASSETS_FONTS / "Regular.ttf", ASSETS_FONTS / "Bold.ttf"
    if reg.exists() and bold.exists():
        return str(reg), str(bold)
    import matplotlib
    d = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    return str(d / "DejaVuSans.ttf"), str(d / "DejaVuSans-Bold.ttf")


def _register_fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "BD-Regular" in pdfmetrics.getRegisteredFontNames():
        return
    reg, bold = _font_paths()
    pdfmetrics.registerFont(TTFont("BD-Regular", reg))
    pdfmetrics.registerFont(TTFont("BD-Bold", bold))


def _wrap_rtl(text: str, font: str, size: float, max_w: float) -> list[str]:
    """التفاف يدوي: bidi يُطبَّق على كل سطر منفصلاً (تطبيقه على فقرة كاملة يعكس ترتيب الأسطر)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    lines, cur = [], []
    for w in text.split():
        trial = cur + [w]
        if cur and stringWidth(_ar(" ".join(trial)), font, size) > max_w:
            lines.append(_ar(" ".join(cur)))
            cur = [w]
        else:
            cur = trial
    if cur:
        lines.append(_ar(" ".join(cur)))
    return lines


def _chart_png(b: ReportBundle) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    reg, _ = _font_paths()
    if ASSETS_FONTS in Path(reg).parents:
        font_manager.fontManager.addfont(reg)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=reg).get_name()

    y, f = b.series, b.result.forecast
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(y.index, y.values, color="#2F5597", marker="o", ms=3, lw=1.8, label=_ar("التاريخي"))
    ax.fill_between(f.index, f["lower"], f["upper"], color="#6366F1", alpha=0.18, label=_ar("نطاق الثقة 95%"))
    ax.plot([y.index[-1], *f.index], [y.iloc[-1], *f["yhat"]], color="#ED7D31", ls="--", marker="o", ms=3,
            lw=1.8, label=_ar("التنبؤ"))
    if b.anomalies is not None and b.anomalies.count:
        t = b.anomalies.table
        ax.scatter(t.index, t["value"], color="red", marker="X", s=60, zorder=5, label=_ar("قيمة شاذة"))
    ax.set_title(_ar(f"التنبؤ — {b.metric}"), fontsize=12)
    ax.set_ylabel(_ar(str(y.name)))
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out = io.BytesIO()
    fig.savefig(out, format="png", dpi=150)
    plt.close(fig)
    return out.getvalue()


def build_pdf_report(b: ReportBundle) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.8 * cm,
                            title="Between Data - Forecast Report", author="Between Data")
    width = A4[0] - 3.6 * cm
    S = {
        "title": ParagraphStyle("t", fontName="BD-Bold", fontSize=18, leading=26, alignment=TA_RIGHT,
                                textColor=colors.HexColor("#1F3864")),
        "meta": ParagraphStyle("m", fontName="BD-Regular", fontSize=8.5, leading=13, alignment=TA_RIGHT,
                               textColor=colors.HexColor("#7F7F7F")),
        "h": ParagraphStyle("h", fontName="BD-Bold", fontSize=13, leading=20, alignment=TA_RIGHT,
                            textColor=colors.HexColor("#2F5597"), spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", fontName="BD-Regular", fontSize=10.5, leading=17, alignment=TA_RIGHT),
    }

    def lines(text: str, style: str = "body", prefix: str = "") -> list:
        st = S[style]
        wrapped = _wrap_rtl(prefix + text, st.fontName, st.fontSize, width * 0.97)
        return [Paragraph(escape(ln), st) for ln in wrapped]

    def table(header: list[str], rows: list[list], col_w: list[float] | None = None) -> Table:
        data = [[_cell(h) for h in header][::-1]] + [[_cell(c) for c in r][::-1] for r in rows]
        widths = (col_w[::-1] if col_w else None)
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "BD-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "BD-Regular"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5597")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FC")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    el: list = []
    el += lines(f"تقرير التنبؤ — {b.metric}", "title")
    el += lines(f"تاريخ الإنشاء: {b.generated_at}  |  {_source_label(b.narrative_source)}", "meta")
    el.append(Spacer(1, 8))

    el += lines("الملخص التنفيذي", "h")
    for para in plain_paragraphs(b.narrative):
        el += lines(para, prefix="• ")
        el.append(Spacer(1, 3))

    el.append(Spacer(1, 6))
    png = io.BytesIO(_chart_png(b))
    el.append(Image(png, width=width, height=width * 4.2 / 9))

    el += lines("المؤشرات الرئيسية", "h")
    el.append(table(["المؤشر", "القيمة"], [list(r) for r in facts_rows(b.facts)],
                    [width * 0.4, width * 0.6]))

    el += lines("جدول التنبؤ", "h")
    fc = b.result.forecast
    rows = [[d.strftime("%Y-%m-%d"), f"{r.yhat:,.2f}", f"{r.lower:,.2f}", f"{r.upper:,.2f}"]
            for d, r in fc.iterrows()]
    el.append(table(["التاريخ", "التنبؤ", "الحد الأدنى", "الحد الأعلى"], rows))

    el += lines("القيم الشاذة", "h")
    if b.anomalies is not None and b.anomalies.count:
        t = b.anomalies.table.reindex(b.anomalies.table["score"].abs().sort_values(ascending=False).index).head(15)
        rows = [[d.strftime("%Y-%m-%d"), f"{r.value:,.2f}", f"{r.expected:,.2f}", f"{r.score:+.1f}", r.direction]
                for d, r in t.iterrows()]
        el.append(table(["التاريخ", "الفعلية", "المتوقعة", "الدرجة", "الاتجاه"], rows))
    else:
        el += lines("لم تُرصد قيم شاذة في البيانات التاريخية.")

    if b.audit is not None:
        a = b.audit
        el += lines("جودة البيانات", "h")
        el += lines(f"إجمالي الصفوف {a.total_rows:,}، الصالحة {a.valid_rows:,}، المعزولة {a.quarantined_rows:,}، "
                    f"وبها تحذيرات {a.warning_rows:,}. لم يُحذف أو يُعدَّل أي صف.")
        s = a.summary_by_issue().head(12)
        if len(s):
            el.append(table(list(s.columns), s.astype(str).values.tolist()))

    el.append(Spacer(1, 10))
    el += lines(DISCLAIMER, "meta")

    def footer(canvas, d) -> None:
        canvas.setFont("BD-Regular", 8)
        canvas.setFillColor(colors.HexColor("#7F7F7F"))
        canvas.drawCentredString(A4[0] / 2, 1 * cm, f"Between Data  •  {d.page}")

    doc.build(el, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ============================================================
# Streamlit UI: تصدير سريع من لوحة التحكم
# ============================================================
def _report_bundle_from_state(bundle: dict[str, Any] | ReportBundle) -> ReportBundle:
    """يحوّل القيم الموجودة في session_state إلى نسخة ReportBundle جاهزة للتصدير."""
    if isinstance(bundle, ReportBundle):
        return bundle

    series = bundle.get("series")
    result = bundle.get("result")
    facts = bundle.get("facts")
    if series is None or result is None or facts is None:
        raise ValueError("لا توجد بيانات كافية لإنشاء تقرير التصدير.")

    return ReportBundle(
        metric=str(bundle.get("metric") or series.name or "dataset"),
        series=series,
        result=result,
        facts=facts,
        narrative=str(bundle.get("narrative") or ""),
        narrative_source=str(bundle.get("narrative_source") or "template"),
        anomalies=bundle.get("anomalies"),
        audit=bundle.get("audit"),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def render_report_downloads(bundle: dict[str, Any] | ReportBundle | None) -> None:
    """يعرض أزرار التصدير في الواجهة مع التحقق من التبعيات."""
    if bundle is None:
        return

    try:
        report = _report_bundle_from_state(bundle)
    except Exception as exc:
        st = __import__("streamlit")
        st.warning(f"تعذّر تجهيز تقرير التصدير: {exc}")
        return

    import streamlit as st

    st.markdown("### ⬇️ تصدير التقرير")
    col1, col2, col3 = st.columns(3)

    try:
        excel_bytes = build_excel_report(report)
        col1.download_button(
            "📘 Excel",
            data=excel_bytes,
            file_name=f"forecast_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_download_excel_report",
        )
    except Exception as exc:
        col1.warning(f"Excel غير متاح: {exc}")

    try:
        pdf_bytes = build_pdf_report(report)
        col2.download_button(
            "📄 PDF",
            data=pdf_bytes,
            file_name=f"forecast_report_{datetime.now():%Y%m%d_%H%M%S}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="btn_download_pdf_report",
        )
    except Exception as exc:
        col2.warning(f"PDF غير متاح: {exc}")

    forecast_csv = report.result.forecast.reset_index().rename(columns={"index": "التاريخ"}).to_csv(index=False, encoding="utf-8-sig")
    col3.download_button(
        "📊 CSV",
        data=forecast_csv,
        file_name=f"forecast_data_{datetime.now():%Y%m%d_%H%M%S}.csv",
        mime="text/csv",
        use_container_width=True,
        key="btn_download_csv_report",
    )


def render_report_export(bundle: dict[str, Any] | ReportBundle | None) -> None:
    """واجهة تصدير التقرير المعروضة صراحةً داخل dashboard أو أي صفحة أخرى."""
    if bundle is None:
        return
    render_report_downloads(bundle)
