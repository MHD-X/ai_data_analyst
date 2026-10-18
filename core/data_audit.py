"""
core/data_audit.py — فحص البيانات وعزل الصفوف المشكوك فيها (Audit & Quarantine)

المبادئ (ثابتة):
  1. لا حذف:   كل صف يذهب إلى valid أو quarantine، والمجموع = الأصل (يُتحقق منه برمجياً).
  2. لا تعويض: لا fillna ولا coerce على البيانات المُرجَعة؛ القيم تبقى كما رُفعت.
  3. كل صف معزول معه سبب دقيق: العمود + نوع المشكلة + القيمة الخام.

مستويات الخطورة:
  error   → يُعزل الصف (لا يدخل التحليل حتى يراجعه المستخدم).
  warning → يبقى الصف صالحاً لكن يُعرض للتنبيه (مثل المعرّف المكرر).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable

import numpy as np
import pandas as pd

from core.forecasting import parse_dates

ERROR = "error"
WARNING = "warning"

ROW_COL = "رقم الصف في الملف"
REASON_COL = "سبب العزل"

ISSUE_MISSING = "قيمة مفقودة"
ISSUE_TYPE = "نوع بيانات غير مطابق"
ISSUE_INF = "قيمة لا نهائية"
ISSUE_BAD_DATE = "تاريخ تالف"
ISSUE_OLD_DATE = "تاريخ خارج النطاق"
ISSUE_FUTURE = "تاريخ مستقبلي"
ISSUE_DATE_FORMAT = "تنسيق تاريخ مختلف عن السائد"
ISSUE_DUP = "معرّف مكرر"

_ISSUE_COLS = ["row_index", "row_number", "column", "issue_type",
               "severity", "message", "raw_value", "reason"]


# ============================================================
# الإعدادات والنتيجة
# ============================================================
@dataclass(frozen=True)
class AuditConfig:
    date_cols: tuple = ()
    numeric_cols: tuple = ()
    required_cols: tuple = ()          # أعمدة حرجة إضافية (لا يُسمح فيها بالفراغ)
    id_col: Hashable | None = None     # لكشف التكرار فقط (تحذير، لا عزل)
    min_date: str = "2000-01-01"
    allow_future: bool = False
    minority_format_share: float = 0.10


@dataclass
class AuditReport:
    valid: pd.DataFrame
    quarantine: pd.DataFrame
    issues: pd.DataFrame
    column_profile: pd.DataFrame
    total_rows: int
    config: AuditConfig = field(default_factory=AuditConfig)

    @property
    def valid_rows(self) -> int:
        return len(self.valid)

    @property
    def quarantined_rows(self) -> int:
        return len(self.quarantine)

    @property
    def warning_rows(self) -> int:
        if self.issues.empty:
            return 0
        return int(self.issues.loc[self.issues["severity"] == WARNING, "row_index"].nunique())

    def summary_by_issue(self) -> pd.DataFrame:
        cols = ["العمود", "نوع المشكلة", "الإجراء", "عدد الصفوف"]
        if self.issues.empty:
            return pd.DataFrame(columns=cols)
        g = (self.issues.groupby(["column", "issue_type", "severity"])["row_index"]
             .nunique().reset_index(name="rows"))
        g["_ord"] = (g["severity"] != ERROR).astype(int)
        g = g.sort_values(["_ord", "rows"], ascending=[True, False])
        g["severity"] = g["severity"].map({ERROR: "عزل", WARNING: "تحذير"})
        g.columns = ["العمود", "نوع المشكلة", "الإجراء", "عدد الصفوف", "_ord"]
        return g[cols].reset_index(drop=True)


# ============================================================
# أدوات فحص أولية
# ============================================================
def _missing_mask(s: pd.Series) -> pd.Series:
    """NaN/None أو نص فارغ/مسافات فقط. (كشف فقط — لا تعويض.)"""
    m = s.isna()
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        m = m | s.map(lambda v: isinstance(v, str) and not v.strip())
    return m.astype(bool)


def _date_signature(s: pd.Series) -> pd.Series:
    """بصمة تنسيق التاريخ: الأرقام → 9، وكسور الثانية تُدمج (3 أو 6 خانات = نفس التنسيق)."""
    sig = s.astype(str).str.replace(r"\d", "9", regex=True)
    return sig.str.replace(r"\.9+", ".9+", regex=True)


def _emit(frames: list, mask: pd.Series, column, issue: str, severity: str,
          message: str, raw: pd.Series | None = None) -> None:
    idx = np.flatnonzero(mask.to_numpy(dtype=bool))
    if idx.size == 0:
        return
    raws = [""] * idx.size if raw is None else raw.iloc[idx].map(lambda v: str(v)[:60]).tolist()
    frames.append(pd.DataFrame({
        "row_index": idx, "row_number": idx + 2, "column": str(column),
        "issue_type": issue, "severity": severity, "message": message, "raw_value": raws,
    }))


# ============================================================
# الفحوص
# ============================================================
def _check_missing(work, col, frames):
    _emit(frames, _missing_mask(work[col]), col, ISSUE_MISSING, ERROR, "الحقل فارغ في عمود حرج")


def _check_numeric(work, col, frames):
    s = work[col]
    present = ~_missing_mask(s)
    if pd.api.types.is_numeric_dtype(s):
        arr = pd.to_numeric(s, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
        _emit(frames, pd.Series(np.isinf(arr), index=s.index), col, ISSUE_INF, ERROR,
              "قيمة لا نهائية", s)
        return
    parsed = pd.to_numeric(s.where(present), errors="coerce")
    arr = parsed.to_numpy(dtype="float64", na_value=np.nan)
    _emit(frames, present & parsed.isna(), col, ISSUE_TYPE, ERROR,
          "نص في عمود يُفترض أن يكون رقمياً", s)
    _emit(frames, present & pd.Series(np.isinf(arr), index=s.index), col, ISSUE_INF, ERROR,
          "قيمة لا نهائية", s)


def _check_dates(work, col, cfg: AuditConfig, frames):
    s = work[col]
    present = ~_missing_mask(s)

    if pd.api.types.is_numeric_dtype(s):
        _emit(frames, present, col, ISSUE_BAD_DATE, ERROR, "قيمة رقمية في عمود تاريخ", s)
        return

    parsed = parse_dates(s.where(present))
    _emit(frames, present & parsed.isna(), col, ISSUE_BAD_DATE, ERROR,
          "لا يمكن قراءتها كتاريخ", s)

    ok = present & parsed.notna()
    min_ts = pd.Timestamp(cfg.min_date)
    _emit(frames, ok & (parsed < min_ts), col, ISSUE_OLD_DATE, ERROR,
          f"التاريخ أقدم من {cfg.min_date}", s)

    if not cfg.allow_future:
        limit = pd.Timestamp.now(tz="UTC").tz_localize(None) + pd.Timedelta(days=1)
        _emit(frames, ok & (parsed > limit), col, ISSUE_FUTURE, ERROR,
              "التاريخ في المستقبل", s)

    # تنسيقات غير منتظمة (تحذير فقط — لا نخمّن أيّ التنسيقين هو الصحيح)
    if ok.sum() >= 20 and not pd.api.types.is_datetime64_any_dtype(s):
        sig = _date_signature(s[ok])
        share = sig.value_counts(normalize=True)
        if share.iloc[0] >= 0.5:
            minority = sig.map(share) < cfg.minority_format_share
            mask = pd.Series(False, index=s.index)
            mask.loc[sig.index[minority.to_numpy()]] = True
            _emit(frames, mask, col, ISSUE_DATE_FORMAT, WARNING,
                  f"التنسيق السائد في العمود مختلف ({share.index[0]})", s)


def _check_duplicates(work, col, frames):
    s = work[col]
    dup = s.duplicated(keep=False) & ~_missing_mask(s)
    _emit(frames, dup, col, ISSUE_DUP, WARNING,
          "المعرّف يظهر في أكثر من صف (لم يُحذف أي منها)", s)


def _profile(work: pd.DataFrame, critical: set) -> pd.DataFrame:
    n = len(work)
    rows = []
    for c in work.columns:
        miss = _missing_mask(work[c])
        rows.append({
            "العمود": str(c), "النوع": str(work[c].dtype),
            "مفقود": int(miss.sum()),
            "نسبة المفقود %": round(float(miss.mean()) * 100, 1) if n else 0.0,
            "حرج": c in critical,
        })
    return pd.DataFrame(rows)


# ============================================================
# نقطة الدخول
# ============================================================
def audit_dataframe(df: pd.DataFrame, cfg: AuditConfig) -> AuditReport:
    work = df.reset_index(drop=True)   # الفهرس الموضعي؛ رقم الصف = الفهرس + 2 (الترويسة = 1)

    critical = list(dict.fromkeys([*cfg.required_cols, *cfg.date_cols, *cfg.numeric_cols]))
    needed = critical + ([cfg.id_col] if cfg.id_col is not None else [])
    absent = [c for c in needed if c not in work.columns]
    if absent:
        raise ValueError(f"أعمدة غير موجودة في الملف: {absent}")

    frames: list[pd.DataFrame] = []
    for col in critical:
        _check_missing(work, col, frames)
    for col in cfg.numeric_cols:
        _check_numeric(work, col, frames)
    for col in cfg.date_cols:
        _check_dates(work, col, cfg, frames)
    if cfg.id_col is not None:
        _check_duplicates(work, cfg.id_col, frames)

    if frames:
        issues = pd.concat(frames, ignore_index=True)
        issues["reason"] = (
            "[" + issues["column"] + "] " + issues["issue_type"] + ": " + issues["message"]
            + issues["raw_value"].map(lambda r: f" — القيمة: «{r}»" if r else "")
        )
    else:
        issues = pd.DataFrame(columns=_ISSUE_COLS)

    errors = issues[issues["severity"] == ERROR]
    reasons = errors.groupby("row_index")["reason"].agg("؛ ".join)
    q_idx = reasons.index.to_numpy(dtype=int)

    quarantine = work.iloc[q_idx].copy()
    quarantine.insert(0, REASON_COL, reasons.to_numpy())
    quarantine.insert(0, ROW_COL, q_idx + 2)
    valid = work.drop(index=q_idx)

    if len(valid) + len(quarantine) != len(work):  # ضمان "لا حذف"
        raise RuntimeError("خلل: مجموع الصالح والمعزول لا يساوي الأصل.")

    return AuditReport(valid, quarantine, issues, _profile(work, set(critical)),
                       len(work), cfg)


def neutralize_formulas(df: pd.DataFrame) -> pd.DataFrame:
    """للتصدير فقط: يمنع تنفيذ نصوص تبدأ بـ = + - @ كصيغ عند فتح CSV في Excel."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].map(
                lambda v: "'" + v if isinstance(v, str) and v and v[0] in "=+-@\t\r" else v
            )
    return out