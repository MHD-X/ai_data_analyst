"""
core/forecasting.py — تنبؤ زمني حتمي (لا يعتمد على كود يولّده LLM)

التدفق:
    detect_date_columns -> build_series -> forecast_series -> make_figure
النماذج: naive / moving_avg / linear (sklearn) / holt_damped / holt_winters (statsmodels)
الاختيار: backtest بنافذة متدحرجة ثم أقل MAE.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial
from typing import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from utils.column_matcher import friendly_missing_column_message, resolve_column

logger = logging.getLogger(__name__)

MIN_POINTS = 8          # أقل عدد نقاط لإجراء backtest ومقارنة النماذج
MIN_TRAIN = 5           # أقل طول تدريب داخل الـ backtest
FREQ_LABELS = {"D": "يومي", "W": "أسبوعي", "ME": "شهري"}
SEASONAL_PERIOD = {"D": 7, "ME": 12}

ModelFn = Callable[[pd.Series, int], tuple[np.ndarray, np.ndarray, np.ndarray]]


@dataclass
class ForecastResult:
    model_name: str
    history: pd.Series
    forecast: pd.DataFrame            # index=تاريخ، الأعمدة: yhat, lower, upper
    backtest_mae: dict[str, float]
    freq: str
    warnings: list[str] = field(default_factory=list)


# ============================================================
# التواريخ
# ============================================================
def parse_dates(s: pd.Series) -> pd.Series:
    """يحوّل نصاً إلى تواريخ (naive UTC) ويجرّب عدة صيغ ويختار الأفضل."""
    best: pd.Series | None = None
    for kw in ({"format": "ISO8601"}, {"format": "mixed"}, {}):
        try:
            out = pd.to_datetime(s, errors="coerce", utc=True, **kw)
        except Exception:
            continue
        if best is None or out.notna().sum() > best.notna().sum():
            best = out
    if best is None:
        return pd.Series(pd.NaT, index=s.index)
    return best.dt.tz_localize(None)


def detect_date_columns(df: pd.DataFrame, min_ratio: float = 0.8) -> list:
    found: list = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            found.append(c)
            continue
        if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
            continue  # الأعمدة الرقمية (مثل أرقام الهواتف) تُحوَّل لتواريخ خاطئة
        sample = s.dropna().astype(str).head(200)
        if sample.empty:
            continue
        looks_like_date = sample.str.contains(
            r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", regex=True
        ).mean()
        if looks_like_date < min_ratio:
            continue
        if parse_dates(sample).notna().mean() >= min_ratio:
            found.append(c)
    return found


# ============================================================
# بناء السلسلة الزمنية
# ============================================================
def build_series(
    df: pd.DataFrame,
    date_col,
    value_col=None,
    agg: str = "sum",
    freq: str = "W",
    dedupe_on=None,
    drop_partial: bool = True,
) -> pd.Series:
    """
    يجمّع البيانات إلى سلسلة منتظمة.
    value_col=None أو agg='count' => عدّ السجلات.
    dedupe_on: عمود معرّف (مثل Enrollment ID) لإزالة الصفوف المكررة قبل التجميع.
    """
    requested_cols = [date_col, value_col, dedupe_on]
    resolved_date_col = resolve_column(df, date_col) if date_col is not None else None
    if resolved_date_col is None:
        raise ValueError(friendly_missing_column_message(date_col, df, lang="ar"))

    resolved_value_col = resolve_column(df, value_col) if value_col is not None else None
    if value_col is not None and resolved_value_col is None:
        raise ValueError(friendly_missing_column_message(value_col, df, lang="ar"))

    resolved_dedupe_on = resolve_column(df, dedupe_on) if dedupe_on is not None else None
    if dedupe_on is not None and resolved_dedupe_on is None:
        raise ValueError(friendly_missing_column_message(dedupe_on, df, lang="ar"))

    cols = [c for c in (resolved_date_col, resolved_value_col, resolved_dedupe_on) if c is not None]
    work = df[list(dict.fromkeys(cols))].copy()

    if resolved_dedupe_on is not None:
        work = work.drop_duplicates(subset=[resolved_dedupe_on])

    work["_ts"] = parse_dates(work[resolved_date_col])
    work = work.dropna(subset=["_ts"])
    if work.empty:
        raise ValueError("لا توجد تواريخ صالحة في العمود المختار.")

    if resolved_value_col is None or agg == "count":
        work["_v"] = 1.0
        agg = "sum"
    else:
        work["_v"] = pd.to_numeric(work[resolved_value_col], errors="coerce")
        work = work.dropna(subset=["_v"])
        if work.empty:
            raise ValueError("العمود المختار لا يحتوي قيماً رقمية.")

    r = work.set_index("_ts")["_v"].resample(freq)
    s = r.sum() if agg == "sum" else r.mean().interpolate(limit_direction="both")

    # آخر فترة ناقصة (مثل أسبوع لم ينتهِ) تُضلّل النموذج → نحذفها
    last_ts = work["_ts"].max()
    if drop_partial and freq != "D" and len(s) > 1 and last_ts.normalize() < s.index[-1]:
        s = s.iloc[:-1]

    s.name = str(value_col) if value_col is not None else "count"
    return s.astype(float)


# ============================================================
# النماذج — كلها (train, h) -> (yhat, lower, upper)
# ============================================================
def _band(yhat: np.ndarray, sigma: float, widen: bool = False):
    sigma = 0.0 if not np.isfinite(sigma) else float(sigma)
    mult = np.sqrt(np.arange(1, len(yhat) + 1)) if widen else 1.0
    return yhat - 1.96 * sigma * mult, yhat + 1.96 * sigma * mult


def _naive(train: pd.Series, h: int):
    yhat = np.full(h, train.iloc[-1], dtype=float)
    sigma = np.std(np.diff(train.values), ddof=1) if len(train) > 2 else 0.0
    lo, hi = _band(yhat, sigma, widen=True)
    return yhat, lo, hi


def _moving_avg(train: pd.Series, h: int):
    k = min(4, len(train))
    tail = train.iloc[-k:]
    yhat = np.full(h, tail.mean(), dtype=float)
    lo, hi = _band(yhat, tail.std(ddof=1) if k > 1 else 0.0)
    return yhat, lo, hi


def _linear(train: pd.Series, h: int):
    from sklearn.linear_model import LinearRegression

    n = len(train)
    X = np.arange(n).reshape(-1, 1)
    model = LinearRegression().fit(X, train.values)
    sigma = (train.values - model.predict(X)).std(ddof=2) if n > 2 else 0.0
    yhat = model.predict(np.arange(n, n + h).reshape(-1, 1))
    lo, hi = _band(yhat, sigma)
    return yhat, lo, hi


def _holt(train: pd.Series, h: int, period: int | None = None):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    kw: dict = dict(trend="add", damped_trend=True, initialization_method="estimated")
    if period:
        kw.update(seasonal="add", seasonal_periods=period)
    fit = ExponentialSmoothing(np.asarray(train, dtype=float), **kw).fit()
    yhat = np.asarray(fit.forecast(h), dtype=float)
    lo, hi = _band(yhat, float(np.std(fit.resid, ddof=1)), widen=True)
    return yhat, lo, hi


def _candidate_models(freq: str, n: int) -> dict[str, ModelFn]:
    models: dict[str, ModelFn] = {
        "naive": _naive,
        "moving_avg": _moving_avg,
        "linear": _linear,
    }
    try:
        import statsmodels  # noqa: F401

        models["holt_damped"] = partial(_holt, period=None)
        p = SEASONAL_PERIOD.get(freq)
        if p and n >= 3 * p:
            models["holt_winters"] = partial(_holt, period=p)
    except ImportError:
        logger.info("statsmodels غير مثبّت — نماذج Holt متوقفة")
    return models


# ============================================================
# Backtest + الاختيار
# ============================================================
def _backtest(fn: ModelFn, y: pd.Series, h_bt: int, folds: int = 2) -> float:
    errs: list[float] = []
    for k in range(folds):
        end = len(y) - k * h_bt
        if end - h_bt < MIN_TRAIN:
            break
        train, test = y.iloc[: end - h_bt], y.iloc[end - h_bt : end]
        yhat, _, _ = fn(train, h_bt)
        errs.append(float(np.mean(np.abs(test.values - yhat))))
    return float(np.mean(errs)) if errs else float("inf")


def forecast_series(y: pd.Series, horizon: int = 4, freq: str = "W") -> ForecastResult:
    n = len(y)
    if n < 4:
        raise ValueError(f"عدد الفترات ({n}) أقل من 4 — لا يمكن التنبؤ بشكل مفيد.")

    warns: list[str] = []
    models = _candidate_models(freq, n)
    scores: dict[str, float] = {}

    if n >= MIN_POINTS:
        h_bt = max(1, min(horizon, n // 4))
        for name, fn in models.items():
            try:
                score = _backtest(fn, y, h_bt)
                if np.isfinite(score):
                    scores[name] = score
            except Exception as exc:  # نموذج واحد فاشل لا يوقف الباقي
                logger.warning("نموذج %s فشل: %s", name, exc)
    else:
        warns.append("عدد الفترات قليل (<8): لا يمكن المقارنة بين النماذج، استُخدم الاتجاه الخطي.")

    best = min(scores, key=scores.get) if scores else "linear"
    yhat, lo, hi = models[best](y, horizon)

    if (y.values >= 0).all():
        yhat, lo, hi = (np.clip(a, 0, None) for a in (yhat, lo, hi))
    if n < 12:
        warns.append("السلسلة قصيرة: اعتبر التنبؤ تقريبياً ولا تعتمد عليه وحده.")
    if scores and best not in ("naive",) and scores.get("naive", np.inf) <= scores[best]:
        warns.append("النموذج المختار لم يتفوّق على التنبؤ الساذج (آخر قيمة): البيانات قد تكون عشوائية.")

    idx = pd.date_range(y.index[-1], periods=horizon + 1, freq=freq)[1:]
    fc = pd.DataFrame({"yhat": yhat, "lower": lo, "upper": hi}, index=idx)
    return ForecastResult(best, y, fc, scores, freq, warns)


# ============================================================
# الرسم
# ============================================================
def make_figure(res: ForecastResult, title: str | None = None) -> go.Figure:
    y, f = res.history, res.forecast
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=y.index, y=y.values, mode="lines+markers", name="التاريخي"))
    fig.add_trace(go.Scatter(
        x=f.index, y=f["upper"], mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=f.index, y=f["lower"], mode="lines", line=dict(width=0), fill="tonexty",
        fillcolor="rgba(99,110,250,0.2)", name="نطاق 95%", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[y.index[-1], *f.index], y=[y.iloc[-1], *f["yhat"]],
        mode="lines+markers", line=dict(dash="dash"), name="التنبؤ",
    ))
    fig.update_layout(
        template="plotly_white", hovermode="x unified",
        title=title or f"التنبؤ — {y.name} ({res.model_name})",
        xaxis_title="التاريخ", yaxis_title=str(y.name),
    )
    return fig