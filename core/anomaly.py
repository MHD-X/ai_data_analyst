"""
core/anomaly.py — كشف القيم الشاذة في السلسلة الزمنية

الطريقة: Median/MAD متين (Robust z-score) على بواقي السلسلة عن وسيط متحرك مركزي.
- الوسيط المتحرك يمتص الاتجاه، فلا تُعدّ النقاط الصاعدة تدريجياً شاذة.
- لا تعديل للبيانات: الشواذ تُظلَّل وتُعرض فقط (التعويض = تخمين، وهو ممنوع هنا).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MIN_POINTS = 8


@dataclass
class AnomalyResult:
    table: pd.DataFrame                 # index=التاريخ؛ value, expected, score, direction
    threshold: float
    method: str = "robust_mad"
    notes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.table)


def _empty(threshold: float, note: str) -> AnomalyResult:
    cols = ["value", "expected", "score", "direction"]
    return AnomalyResult(pd.DataFrame(columns=cols), threshold, notes=[note])


def detect_anomalies(y: pd.Series, threshold: float = 3.5,
                     window: int | None = None) -> AnomalyResult:
    n = len(y)
    if n < MIN_POINTS:
        return _empty(threshold, f"عدد الفترات ({n}) أقل من {MIN_POINTS}: لا يمكن كشف الشواذ بثقة.")

    w = window or min(7, n if n % 2 else n - 1)
    w = max(3, w if w % 2 else w + 1)

    expected = y.rolling(w, center=True, min_periods=w // 2 + 1).median()
    resid = y - expected
    center = resid.median()
    mad = (resid - center).abs().median()
    scale = 1.4826 * mad
    notes: list[str] = []
    if not scale or not np.isfinite(scale):
        scale = resid.std(ddof=1)
        notes.append("التذبذب الأساسي شبه معدوم؛ استُخدم الانحراف المعياري بدل MAD.")
    if not scale or not np.isfinite(scale):
        return _empty(threshold, "السلسلة ثابتة تقريباً؛ لا شواذ.")

    score = (resid - center) / scale
    flagged = score.abs() > threshold
    tbl = pd.DataFrame({
        "value": y[flagged], "expected": expected[flagged], "score": score[flagged],
        "direction": np.where(score[flagged] > 0, "ارتفاع", "انخفاض"),
    })
    return AnomalyResult(tbl, threshold, notes=notes)