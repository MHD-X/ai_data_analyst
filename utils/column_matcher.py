from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def normalize_column_name(value: Any) -> str:
    """Normalizes a likely column name for fuzzy matching."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("\u0640", "")
    text = text.replace("_", " ").replace("-", " ")
    text = text.replace("/", " ").replace("\\", " ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _score_pair(requested: str, candidate: str) -> float:
    if not requested or not candidate:
        return 0.0
    if requested == candidate:
        return 1.0
    if requested in candidate or candidate in requested:
        return 0.9

    req_tokens = set(re.findall(r"[\w\u0600-\u06FF]+", requested))
    cand_tokens = set(re.findall(r"[\w\u0600-\u06FF]+", candidate))
    token_overlap = len(req_tokens & cand_tokens)
    union = len(req_tokens | cand_tokens)
    token_score = (token_overlap / union) if union else 0.0
    seq_ratio = difflib.SequenceMatcher(None, requested, candidate).ratio()
    score = (0.6 * seq_ratio) + (0.4 * token_score)
    return round(max(0.0, min(1.0, score)), 6)


def _pick_best_match(candidates: list[tuple[float, Any]], requested: str) -> Any:
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], len(str(item[1]))), reverse=True)
    best_score, best_value = candidates[0]
    if len(candidates) > 1:
        second_score = candidates[1][0]
        if abs(best_score - second_score) < 0.05 and best_score >= 0.6:
            logger.warning(
                "Ambiguous column match for %r: %s (best=%s, second=%s)",
                requested,
                [str(v) for _, v in candidates[:5]],
                best_value,
                candidates[1][1],
            )
    return best_value


def resolve_column(df: pd.DataFrame | None, requested: Any, cutoff: float = 0.6) -> str | None:
    """Resolve a likely column name to the actual dataframe column.

    Order: exact > normalized > contains > fuzzy.
    """
    if df is None or df.empty:
        return None
    if requested is None:
        return None

    columns = list(df.columns)
    if not columns:
        return None

    if requested in columns:
        return str(requested)

    requested_norm = normalize_column_name(requested)
    if not requested_norm:
        return None

    normalized_map: dict[str, list[Any]] = {}
    for col in columns:
        key = normalize_column_name(col)
        normalized_map.setdefault(key, []).append(col)

    # Exact normalized match
    exact_candidates = normalized_map.get(requested_norm)
    if exact_candidates:
        if len(exact_candidates) == 1:
            return str(exact_candidates[0])
        chosen = _pick_best_match([(1.0, c) for c in exact_candidates], requested_norm)
        logger.warning("Duplicate normalized column match for %r -> %s", requested, chosen)
        return str(chosen)

    # Substring/contains match
    contains: list[tuple[float, Any]] = []
    for col in columns:
        candidate_norm = normalize_column_name(col)
        if requested_norm in candidate_norm or candidate_norm in requested_norm:
            contains.append((_score_pair(requested_norm, candidate_norm), col))
    if contains:
        chosen = _pick_best_match(contains, requested_norm)
        if chosen is not None:
            logger.warning("Resolved column %r using contains-match to %s", requested, chosen)
            return str(chosen)

    # Fuzzy match via custom token-aware score
    scored: list[tuple[float, Any]] = []
    for col in columns:
        candidate_norm = normalize_column_name(col)
        score = _score_pair(requested_norm, candidate_norm)
        if score >= cutoff:
            scored.append((score, col))
    if scored:
        chosen = _pick_best_match(scored, requested_norm)
        if chosen is not None:
            logger.warning("Resolved fuzzy column %r to %s", requested, chosen)
            return str(chosen)

    return None


def resolve_columns(df: pd.DataFrame | None, requested_list: Any, cutoff: float = 0.6) -> tuple[dict[Any, str], list[Any]]:
    """Resolves many requested column names at once and returns resolved + missing."""
    if df is None or df.empty:
        return {}, list(requested_list or [])
    if requested_list is None:
        return {}, []

    if isinstance(requested_list, (str, bytes)):
        requested_list = [requested_list]

    resolved: dict[Any, str] = {}
    missing: list[Any] = []
    for requested in requested_list:
        actual = resolve_column(df, requested, cutoff=cutoff)
        if actual is None:
            missing.append(requested)
        else:
            resolved[requested] = actual
    return resolved, missing


def safe_get_column(df: pd.DataFrame | None, requested: Any, cutoff: float = 0.6) -> pd.Series | None:
    """Safe getter for a dataframe column using fuzzy resolution."""
    if df is None or df.empty:
        return None
    actual = resolve_column(df, requested, cutoff=cutoff)
    if actual is None:
        logger.warning(
            "Column not found for requested value %r. Available columns: %s",
            requested,
            [str(c) for c in df.columns],
        )
        return None
    return df[actual]


def friendly_missing_column_message(requested: Any, df: pd.DataFrame | None, cutoff: float = 0.6, lang: str | None = None) -> str:
    """Builds a clear user-friendly message for a missing column."""
    if df is None or df.empty:
        if lang and lang.lower().startswith("ar"):
            return "لا توجد أعمدة متاحة في البيانات لتحليل هذا الحقل."
        return "There are no available columns in the data for this field."

    requested_text = "" if requested is None else str(requested)
    available = [str(c) for c in df.columns[:10]]
    tail = "" if len(df.columns) <= 10 else f" ... (+{len(df.columns) - 10} أكثر)"
    closest = []
    for col in df.columns:
        score = _score_pair(normalize_column_name(requested_text), normalize_column_name(col))
        if score >= cutoff:
            closest.append(str(col))
    closest = closest[:5]

    if lang and lang.lower().startswith("ar"):
        if closest:
            return (
                f"لم يتم العثور على العمود المطلوب «{requested_text}». "
                f"أقرب الأعمدة المتاحة: {', '.join(closest)}."
            )
        return (
            f"لم يتم العثور على العمود المطلوب «{requested_text}». "
            f"الأعمدة المتاحة: {', '.join(available)}{tail}."
        )

    if closest:
        return (
            f"Column '{requested_text}' could not be resolved. "
            f"Closest available columns: {', '.join(closest)}."
        )
    return (
        f"Column '{requested_text}' could not be resolved. "
        f"Available columns: {', '.join(available)}{tail}."
    )
