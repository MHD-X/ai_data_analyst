"""core/narrative.py — التفسير الآلي لنتائج التنبؤ (بالعربية)

التصميم (لأن الأرقام في التقارير لا يجوز أن "يؤلّفها" نموذج لغوي):
  1. build_facts      : كل الأرقام تُحسب حتمياً من النتائج.
  2. template_narrative: صياغة عربية جاهزة من الحقائق (تعمل دائماً، بدون إنترنت).
  3. llm_narrative    : اختياري — يُرسَل للنموذج ملخص الحقائق المجمّعة فقط
                        (لا صفوف خام، لا بيانات شخصية) ليصيغها بأسلوب تنفيذي.
                        عند أي فشل يُرجَع للقالب تلقائياً.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from core.forecasting import ForecastResult

logger = logging.getLogger(__name__)

# (مفرد، مثنى، جمع 3–10، تمييز 11+)
_UNITS = {
    "D": ("يوم", "يومين", "أيام", "يوماً"),
    "W": ("أسبوع", "أسبوعين", "أسابيع", "أسبوعاً"),
    "ME": ("شهر", "شهرين", "أشهر", "شهراً"),
}
MODEL_AR = {
    "naive": "التنبؤ الساذج (آخر قيمة)",
    "moving_avg": "المتوسط المتحرك",
    "linear": "الانحدار الخطي",
    "holt_damped": "التمهيد الأسي (Holt) باتجاه مخمَّد",
    "holt_winters": "هولت-وينترز الموسمي",
}


@dataclass
class ForecastFacts:
    metric: str
    agg: str
    freq: str
    n_periods: int
    history_start: str
    history_end: str
    horizon: int
    last_value: float
    recent_avg: float
    forecast_first: float
    forecast_mean: float
    forecast_total: float
    trend: str
    volatility: str
    accuracy: str
    model: str
    growth_pct: float | None = None
    cv: float | None = None
    band_rel: float | None = None
    mae: float | None = None
    mae_rel: float | None = None
    anomaly_count: int = 0
    anomaly_dates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ============================================================
# أدوات تنسيق
# ============================================================
def _f(x) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def fmt_num(x: float | None) -> str:
    if x is None:
        return "—"
    a = abs(x)
    if a >= 1000:
        return f"{x:,.0f}"
    if a >= 10:
        return f"{x:,.1f}"
    return f"{x:,.2f}"


def fmt_pct(x: float | None, signed: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


def period_phrase(freq: str, n: int) -> str:
    one, two, plural, tamyiz = _UNITS.get(freq, _UNITS["W"])
    if n == 1:
        return f"{one} واحد"
    if n == 2:
        return two
    return f"{n} {plural}" if n <= 10 else f"{n} {tamyiz}"


# ============================================================
# الحقائق
# ============================================================
def build_facts(series: pd.Series, res: ForecastResult, anomalies=None,
                agg: str = "sum") -> ForecastFacts:
    y, fc = series, res.forecast
    recent_avg = float(y.iloc[-4:].mean())
    fmean = float(fc["yhat"].mean())

    growth = (fmean - recent_avg) / abs(recent_avg) * 100 if recent_avg else None
    trend = ("غير محدد" if growth is None
             else "صاعد" if growth > 5 else "هابط" if growth < -5 else "مستقر")

    tail = y.iloc[-12:]
    mean_t = float(tail.mean())
    cv = _f(tail.std(ddof=1) / abs(mean_t)) if mean_t and len(tail) > 1 else None
    volatility = ("غير محدد" if cv is None
                  else "منخفض" if cv < 0.15 else "متوسط" if cv < 0.35 else "مرتفع")

    half = (fc["upper"] - fc["lower"]) / 2
    band_rel = _f((half / fc["yhat"].abs().replace(0, np.nan)).mean())

    mae = _f(res.backtest_mae.get(res.model_name))
    y_mean = float(y.mean())
    mae_rel = _f(mae / abs(y_mean)) if (mae is not None and y_mean) else None
    accuracy = ("غير متاح" if mae_rel is None
                else "جيدة" if mae_rel < 0.10 else "متوسطة" if mae_rel < 0.25 else "ضعيفة")

    a_count, a_dates = 0, []
    if anomalies is not None and anomalies.count:
        a_count = anomalies.count
        top = anomalies.table["score"].abs().nlargest(3).index
        a_dates = [d.strftime("%Y-%m-%d") for d in top]

    return ForecastFacts(
        metric=str(y.name), agg=agg, freq=res.freq, n_periods=len(y),
        history_start=y.index[0].strftime("%Y-%m-%d"), history_end=y.index[-1].strftime("%Y-%m-%d"),
        horizon=len(fc), last_value=float(y.iloc[-1]), recent_avg=recent_avg,
        forecast_first=float(fc["yhat"].iloc[0]), forecast_mean=fmean,
        forecast_total=float(fc["yhat"].sum()), trend=trend, volatility=volatility,
        accuracy=accuracy, model=res.model_name, growth_pct=_f(growth), cv=cv,
        band_rel=band_rel, mae=mae, mae_rel=mae_rel, anomaly_count=a_count,
        anomaly_dates=a_dates, warnings=list(res.warnings),
    )


def facts_rows(f: ForecastFacts) -> list[tuple[str, str]]:
    """جدول المؤشرات الرئيسية (يُستخدم في الواجهة وPDF وExcel)."""
    rows = [
        ("المقياس", f.metric),
        ("النموذج المختار", MODEL_AR.get(f.model, f.model)),
        ("الفترة التاريخية", f"{f.history_start} → {f.history_end} ({f.n_periods} فترة)"),
        ("آخر قيمة فعلية", fmt_num(f.last_value)),
        ("متوسط آخر 4 فترات", fmt_num(f.recent_avg)),
        ("التنبؤ للفترة القادمة", fmt_num(f.forecast_first)),
        ("متوسط التنبؤ", fmt_num(f.forecast_mean)),
    ]
    if f.agg == "sum":
        rows.append(("إجمالي التنبؤ", fmt_num(f.forecast_total)))
    rows += [
        ("نسبة النمو المتوقعة", fmt_pct(f.growth_pct, signed=True)),
        ("الاتجاه", f.trend),
        ("مستوى التذبذب", f"{f.volatility}" + (f" ({f.cv:.0%})" if f.cv is not None else "")),
        ("دقة النموذج (اختبار رجعي)", f.accuracy + (f" (خطأ ≈ {f.mae_rel:.0%})" if f.mae_rel is not None else "")),
        ("القيم الشاذة المرصودة", str(f.anomaly_count)),
    ]
    return rows


# ============================================================
# الصياغة بالقالب
# ============================================================
def template_narrative(f: ForecastFacts) -> str:
    horizon = period_phrase(f.freq, f.horizon)
    model = MODEL_AR.get(f.model, f.model)
    parts: list[str] = []

    total = f" وبإجمالي متوقع نحو {fmt_num(f.forecast_total)}" if f.agg == "sum" else ""
    parts.append(
        f"**الملخص التنفيذي:** استناداً إلى {f.n_periods} فترة من البيانات "
        f"({f.history_start} حتى {f.history_end})، يتوقع نموذج «{model}» أن يبلغ متوسط "
        f"«{f.metric}» نحو {fmt_num(f.forecast_mean)} خلال الـ{horizon} القادمة{total}."
    )

    if f.growth_pct is None:
        parts.append("**الاتجاه:** تعذّر حساب نسبة النمو لأن متوسط آخر 4 فترات يساوي صفراً.")
    elif f.trend == "مستقر":
        parts.append(
            f"**الاتجاه:** مستقر؛ التغير المتوقع {fmt_pct(f.growth_pct, True)} فقط "
            f"مقارنة بمتوسط آخر 4 فترات ({fmt_num(f.recent_avg)})."
        )
    else:
        verb = "نمواً" if f.trend == "صاعد" else "تراجعاً"
        parts.append(
            f"**الاتجاه:** {f.trend}؛ يُتوقع {verb} بنسبة {fmt_pct(abs(f.growth_pct))} "
            f"مقارنة بمتوسط آخر 4 فترات ({fmt_num(f.recent_avg)})."
        )

    vol = f"**التذبذب:** مستوى التذبذب التاريخي {f.volatility}"
    if f.cv is not None:
        vol += f" (معامل التباين {f.cv:.0%})"
    if f.band_rel is not None:
        vol += f"، ويبلغ عرض نطاق الثقة 95% نحو ±{f.band_rel:.0%} من القيمة المتوقعة"
    parts.append(vol + ".")

    if f.mae_rel is not None:
        parts.append(
            f"**دقة النموذج:** {f.accuracy} في الاختبار الرجعي "
            f"(متوسط الخطأ المطلق {fmt_num(f.mae)} ≈ {f.mae_rel:.0%} من متوسط السلسلة)."
        )
    else:
        parts.append("**دقة النموذج:** لم يتوفر اختبار رجعي لقلة عدد الفترات.")

    if f.anomaly_count:
        dates = "، ".join(f.anomaly_dates)
        parts.append(
            f"**القيم الشاذة:** رُصدت {f.anomaly_count} فترة غير طبيعية (أبرزها: {dates}). "
            "قد تؤثر على التنبؤ، ويُنصح بمراجعتها قبل الاعتماد على النتائج."
        )
    else:
        parts.append("**القيم الشاذة:** لم تُرصد فترات غير طبيعية في البيانات التاريخية.")

    for w in f.warnings:
        parts.append(f"**تنبيه:** {w}")
    return "\n\n".join(parts)


# ============================================================
# الصياغة بالنموذج اللغوي (اختيارية)
# ============================================================
_LLM_SYSTEM = (
    "أنت محلل بيانات أول تكتب بالعربية الفصحى المهنية الموجزة. "
    "اكتب ملخصاً تنفيذياً من فقرة واحدة أو فقرتين (110–170 كلمة) لنتائج تنبؤ إحصائي. "
    "قواعد صارمة: استخدم الأرقام الواردة في الحقائق فقط دون أي رقم جديد أو تقريب مختلف؛ "
    "لا تخترع أسباباً أو أحداثاً؛ اذكر الاتجاه ونسبة النمو ومستوى التذبذب ودقة النموذج "
    "والقيم الشاذة إن وُجدت؛ اختم بتنبيه موجز إلى عدم اليقين. بدون عناوين أو رموز تنسيق."
)


def llm_narrative(f: ForecastFacts) -> tuple[str, str]:
    """يعيد (النص، المصدر) حيث المصدر 'llm' أو 'template' عند الرجوع للقالب."""
    try:
        from core.llm_client import get_client

        facts = asdict(f)
        facts["model"] = MODEL_AR.get(f.model, f.model)
        facts["period_unit"] = _UNITS.get(f.freq, _UNITS["W"])[0]
        text = get_client().chat(
            [
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": "الحقائق (JSON):\n" + json.dumps(facts, ensure_ascii=False)},
            ],
            retries=1, temperature=0.2, max_tokens=700,
        ).strip()
        if len(text) < 60:
            raise ValueError("رد قصير جداً")
        return text, "llm"
    except Exception as exc:
        logger.warning("تعذّرت صياغة LLM، استُخدم القالب: %s", exc)
        return template_narrative(f), "template"
