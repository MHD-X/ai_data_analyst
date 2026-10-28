"""
core/prompts.py — قوالب الـ Prompts الذكية
Smart prompt templates for LLM interactions.

يوفّر:
- System prompts جاهزة لكل نوع مهمة
- Context injection من DataFrames
- Few-shot examples من الذاكرة
- Response parsing (استخراج الكود من رد الـ LLM)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from config import CONFIG
from core.security import mask_df_for_llm
from utils.helpers import (
    clean_code_block,
    describe_dataframe,
    get_dataframe_summary,
    truncate_text,
)

logger = logging.getLogger(__name__)


# ============================================================
# الثوابت
# ============================================================
TASK_ANALYZE = "analyze"
TASK_CLEAN = "clean"
TASK_PREDICT = "predict"
TASK_VISUALIZE = "visualize"
TASK_REPORT = "report"
TASK_CUSTOM = "custom"

SUPPORTED_TASKS = (
    TASK_ANALYZE,
    TASK_CLEAN,
    TASK_PREDICT,
    TASK_VISUALIZE,
    TASK_REPORT,
    TASK_CUSTOM,
)

TASK_KEYWORDS: dict[str, tuple[str, ...]] = {
    TASK_ANALYZE: (
        "حلل", "تحليل", "analyze", "analysis", "explore",
        "استكشف", "افحص", "examine", "summary", "ملخص",
    ),
    TASK_CLEAN: (
        "نظف", "تنظيف", "clean", "cleaning", "معالجة",
        "handle", "fill", "املأ", "احذف الفارغ", "duplicates",
        "المكرر", "missing", "المفقود", "outliers", "الشواذ",
    ),
    TASK_PREDICT: (
        "تنبأ", "تنبؤ", "predict", "forecast", "توقع",
        "future", "المستقبل", "اتجاه", "trend", "توقعات",
    ),
    TASK_VISUALIZE: (
        "ارسم", "رسم", "plot", "chart", "graph", "visualize",
        "مخطط", "شكل", "بياني", "histogram", "bar", "line",
        "pie", "scatter", "box",
    ),
    TASK_REPORT: (
        "تقرير", "report", "استراتيجي", "strategic",
        "ملخص تنفيذي", "executive", "توصيات", "recommendations",
        "رؤى", "insights",
    ),
}


# ============================================================
# System Prompts
# ============================================================
SYSTEM_PROMPT_BASE = """You are an expert Data Analyst AI assistant integrated into a local Python application.

## Your Role
- Generate **Python code** that analyzes, cleans, visualizes, or predicts from data.
- The code you generate will be **executed locally** in a sandboxed environment.

## Environment
- Python 3.11
- Available libraries: pandas, numpy, plotly (express + graph_objects), scikit-learn, statsmodels, scipy
- A DataFrame named `df` is **already loaded** with the user's data.
- The sandbox can read the in-memory dataframe and a temporary CSV copy if needed, but it must not access the network or the host filesystem outside the allowed working directory.

## Code Rules (STRICT)
1. **Always use the pre-loaded `df` variable** — do NOT try to read files.
2. **Never use**: `os`, `sys`, `subprocess`, `open()` for writing, `requests`, `eval`, `exec`, `__import__`.
3. **Only import** from the allowed libraries listed above.
4. **Print results** using `print()` — they will be captured.
5. **For visualizations**, use `plotly.express` (as `px`) or `plotly.graph_objects` (as `go`).
6. **Handle errors gracefully** — check for missing columns, empty data, etc.
7. **Keep code concise** — focus on the task.

## Output Format (CRITICAL)
Return your response in this EXACT format:

```python
# Your Python code here
```

Explanation:
A brief explanation (2-4 sentences) of what the code does.

Language:
- If the user writes in Arabic, respond in Arabic.
- If the user writes in English, respond in English.
"""

SYSTEM_PROMPT_ANALYZE = """You are a senior Data Analyst. Your task is to ANALYZE the data and extract insights.
Focus on:
- Descriptive statistics (mean, median, std, percentiles)
- Distributions and patterns
- Correlations between numeric columns
- Group-by aggregations
- Data quality issues
Generate Python code that reveals meaningful insights.
"""

SYSTEM_PROMPT_CLEAN = """You are a Data Cleaning expert. Your task is to CLEAN and PREPARE the data.
Focus on:
- Handling missing values (drop, fill, interpolate)
- Removing duplicates
- Fixing data types (dates, numbers, categories)
- Handling outliers (detect, cap, remove)
- Standardizing text (trim, lower, normalize)
Generate Python code that cleans the data and reports what was changed.
"""

SYSTEM_PROMPT_PREDICT = """You are a Forecasting expert. Your task is to PREDICT future trends.
Focus on:
- Time series analysis (trend, seasonality)
- Forecasting methods: linear regression, moving averages, ARIMA
- Confidence intervals
- Trend direction and magnitude
Generate Python code that:
1. Prepares the time series
2. Fits an appropriate model
3. Forecasts future values
4. Plots historical + forecast
If no date column exists, explain why prediction is not possible.
"""

SYSTEM_PROMPT_VISUALIZE = """You are a Data Visualization expert. Your task is to CREATE compelling charts using Plotly.
Focus on:
- Choosing the RIGHT chart type for the data
- Clear titles, axis labels, and legends
- Interactive features (hover, zoom)
- Color schemes that convey meaning
Generate Python code that creates an interactive Plotly figure.
Use plotly.express for simplicity or plotly.graph_objects for control.
"""

SYSTEM_PROMPT_REPORT = """You are a Strategic Business Analyst. Your task is to produce a STRATEGIC REPORT.
Focus on:
- Executive summary of key findings
- Business implications
- Actionable recommendations
- Risks and opportunities
- Next steps
Generate Python code that computes the numbers you need,
then provide a strategic narrative in your explanation.
"""

SYSTEM_PROMPT_CUSTOM = """You are a flexible Data Analyst. Follow the user's request precisely.
Generate Python code that accomplishes exactly what the user asks.
If the request is ambiguous, make reasonable assumptions and state them in your explanation.
"""

SYSTEM_PROMPTS: dict[str, str] = {
    TASK_ANALYZE: SYSTEM_PROMPT_ANALYZE,
    TASK_CLEAN: SYSTEM_PROMPT_CLEAN,
    TASK_PREDICT: SYSTEM_PROMPT_PREDICT,
    TASK_VISUALIZE: SYSTEM_PROMPT_VISUALIZE,
    TASK_REPORT: SYSTEM_PROMPT_REPORT,
    TASK_CUSTOM: SYSTEM_PROMPT_CUSTOM,
}

def detect_language(text: str) -> str:
    """يكشف لغة النص: 'ar' أو 'en'."""
    if not text:
        return "en"
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    english_chars = len(re.findall(r"[a-zA-Z]", text))

    return "ar" if arabic_chars > english_chars else "en"

def detect_task_type(user_request: str) -> str:
    """
    يكشف نوع المهمة من نص الطلب.
    يعيد أحد: analyze, clean, predict, visualize, report, custom
    """
    if not user_request:
        return TASK_CUSTOM
    request_lower = user_request.lower()

    scores: dict[str, int] = {}
    for task, keywords in TASK_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in request_lower)
        if score > 0:
            scores[task] = score

    if not scores:
        return TASK_CUSTOM

    return max(scores.items(), key=lambda x: x[1])[0]
# ============================================================
# Data Classes
# ============================================================
@dataclass
class PromptContext:
    """سياق كامل لبناء prompt."""
    user_request: str
    task_type: str = TASK_CUSTOM
    language: str = "ar"
    dataframe_info: str = ""
    dataframe_summary: dict[str, Any] = field(default_factory=dict)
    few_shot_examples: list[dict[str, str]] = field(default_factory=list)
    extra_instructions: str = ""
    max_code_lines: int = 100


# ============================================================
# Context Builder — بناء سياق DataFrame
# ============================================================
def build_dataframe_context(
    df: pd.DataFrame,
    max_columns: int = 30,
    sample_rows: int = 5,
    include_stats: bool = True,
) -> str:
    """
    يبني وصفاً نصياً لـ DataFrame لإرساله للـ LLM.

    Args:
        df: البيانات
        max_columns: الحد الأقصى للأعمدة المعروضة
        sample_rows: عدد الصفوف في العينة
        include_stats: هل نضمّن الإحصائيات؟

    Returns:
        نص وصفي للـ DataFrame
    """
    if df is None or df.empty:
        return "⚠️ لا توجد بيانات محمّلة (df فارغ)"

    masked_df = mask_df_for_llm(df)
    lines: list[str] = []

    # ============ الحجم ============
    lines.append("## Data Overview")
    lines.append(f"- **Shape**: {df.shape[0]:,} rows × {df.shape[1]} columns")
    lines.append(
        f"- **Memory**: {df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB"
    )
    lines.append("")

    # ============ الأعمدة ============
    lines.append("## Columns")
    for i, col in enumerate(masked_df.columns[:max_columns], 1):
        dtype = str(masked_df[col].dtype)
        nulls = int(masked_df[col].isnull().sum())
        null_pct = (nulls / len(masked_df) * 100) if len(masked_df) > 0 else 0.0
        unique = masked_df[col].nunique()

        info = f"{i}. `{col}` — type: `{dtype}`"
        info += f" | nulls: {nulls} ({null_pct:.1f}%)"
        info += f" | unique: {unique}"

        # إضافة أمثلة للقيم النصية
        if dtype == "object" and unique <= 10:
            try:
                samples = masked_df[col].dropna().unique()[:5].tolist()
                samples_str = ", ".join(str(s)[:30] for s in samples)
                info += f" | samples: [{samples_str}]"
            except Exception:
                pass

        lines.append(info)

    if len(df.columns) > max_columns:
        lines.append(f"... and {len(df.columns) - max_columns} more columns")

    lines.append("")

    # ============ العينة ============
    lines.append(f"## Sample Data (first {sample_rows} rows)")
    try:
        sample_str = masked_df.head(sample_rows).to_string(max_colwidth=25)
        lines.append("```")
        lines.append(sample_str)
        lines.append("```")
    except Exception as e:
        lines.append(f"(فشل عرض العينة: {e})")
    lines.append("")

    # ============ الإحصائيات ============
    if include_stats:
        numeric_cols = masked_df.select_dtypes(include=["number"]).columns
        if len(numeric_cols) > 0:
            lines.append("## Numeric Statistics")
            try:
                stats = masked_df[numeric_cols].describe().round(2)
                lines.append("```")
                lines.append(stats.to_string())
                lines.append("```")
            except Exception:
                pass
            lines.append("")

        # قيم مفقودة
        missing = masked_df.isnull().sum()
        missing = missing[missing > 0].sort_values(ascending=False)
        if len(missing) > 0:
            lines.append("## Missing Values")
            for col, count in missing.head(10).items():
                pct = count / len(df) * 100
                lines.append(f"- `{col}`: {count} ({pct:.1f}%)")
            lines.append("")

    return "\n".join(lines)


# ============================================================
# Few-Shot Builder — بناء أمثلة من الذاكرة
# ============================================================
def build_few_shot_section(
    examples: list[dict[str, str]],
    max_examples: int = 3,
    max_code_length: int = 800,
) -> str:
    """
    يبني قسم الأمثلة (Few-Shot) للـ prompt.

    Args:
        examples: قائمة من {"request", "code", "result"}
        max_examples: الحد الأقصى للأمثلة
        max_code_length: الحد الأقصى لطول الكود

    Returns:
        نص قسم Few-Shot (أو "" لو لا توجد أمثلة)
    """
    if not examples:
        return ""

    lines: list[str] = []
    lines.append("## Similar Past Operations (for reference)")
    lines.append(
        "These are successful operations from previous sessions. "
        "Use them as style/approach reference, but adapt to the current data."
    )
    lines.append("")

    for i, ex in enumerate(examples[:max_examples], 1):
        request = ex.get("request", "").strip()
        code = ex.get("code", "").strip()
        result = ex.get("result", "").strip()

        if not code:
            continue

        lines.append(f"### Example {i}")
        lines.append(f"**Request**: {truncate_text(request, 200)}")
        lines.append("```python")
        lines.append(truncate_text(code, max_code_length))
        lines.append("```")

        if result:
            lines.append(f"**Result**: {truncate_text(result, 200)}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# Prompt Builder — بناء الـ Prompt الكامل
# ============================================================
def build_full_prompt(
    context: PromptContext,
) -> tuple[str, str]:
    """
    يبني (system_prompt, user_prompt) كاملين.

    Returns:
        (system_prompt, user_prompt)
    """
    # ============ System Prompt ============
    base = SYSTEM_PROMPT_BASE
    task_specific = SYSTEM_PROMPTS.get(context.task_type, SYSTEM_PROMPT_CUSTOM)

    system_prompt = f"{base}\n\n## Task-Specific Instructions\n\n{task_specific}"

    if context.extra_instructions:
        system_prompt += f"\n\n## Additional Instructions\n\n{context.extra_instructions}"

    # ============ User Prompt ============
    user_parts: list[str] = []

    # 1. البيانات
    if context.dataframe_info:
        user_parts.append("# Data Context")
        user_parts.append(context.dataframe_info)
        user_parts.append("")

    # 2. أمثلة سابقة
    if context.few_shot_examples:
        few_shot = build_few_shot_section(context.few_shot_examples)
        if few_shot:
            user_parts.append(few_shot)
            user_parts.append("")

    # 3. الطلب
    user_parts.append("# Your Task")
    user_parts.append(context.user_request)
    user_parts.append("")

    # 4. تعليمات إضافية
    user_parts.append("# Reminders")
    user_parts.append(f"- Language: respond in **{'Arabic' if context.language == 'ar' else 'English'}**")
    user_parts.append(f"- Max code length: ~{context.max_code_lines} lines")
    user_parts.append("- Use the pre-loaded `df` variable")
    user_parts.append("- Return code inside ```python ... ``` block")
    user_parts.append("- Print results with `print()`")

    user_prompt = "\n".join(user_parts)

    return system_prompt, user_prompt

# ============ نهاية الجزء 2/5 — أكمل بالجزء التالي ============
# ============================================================
# Response Parser — تحليل رد الـ LLM
# ============================================================
@dataclass
class ParsedResponse:
    """نتيجة تحليل رد الـ LLM."""
    code: str = ""
    explanation: str = ""
    raw_response: str = ""
    has_code: bool = False
    language: str = "python"
    warnings: list[str] = field(default_factory=list)


def extract_code_blocks(text: str) -> list[dict[str, str]]:
    """
    يستخرج كل كتل الكود من نص markdown.

    Returns:
        list of {"language": "python", "code": "..."}
    """
    if not text:
        return []

    # نمط ```language\n...code...\n```
    pattern = r"```(\w+)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    blocks: list[dict[str, str]] = []
    for lang, code in matches:
        blocks.append({
            "language": (lang or "text").lower().strip(),
            "code": code.strip(),
        })

    return blocks


def extract_explanation(text: str) -> str:
    """
    يستخرج الشرح من رد الـ LLM (كل شيء خارج كتل الكود).
    """
    if not text:
        return ""

    # نحذف كل كتل الكود
    pattern = r"```(?:\w+)?\s*\n.*?```"
    explanation = re.sub(pattern, "", text, flags=re.DOTALL)

    # ننظّف العناوين الشائعة
    explanation = re.sub(
        r"^\s*\*\*(Explanation|الشرح|شرح)\s*:?\*\*\s*",
        "",
        explanation,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # ننظّف المسافات الزائدة
    explanation = re.sub(r"\n{3,}", "\n\n", explanation)
    explanation = explanation.strip()

    return explanation


def parse_llm_response(text: str) -> ParsedResponse:
    """
    يحلّل رد الـ LLM ويستخرج الكود والشرح.

    Args:
        text: الرد الخام من الـ LLM

    Returns:
        ParsedResponse مع الكود والشرح والتحذيرات
    """
    result = ParsedResponse(raw_response=text)

    if not text or not text.strip():
        result.warnings.append("⚠️ الرد فارغ")
        return result

    # 1. استخراج كل كتل الكود
    blocks = extract_code_blocks(text)

    # 2. نبحث عن أول كتلة Python
    python_block: dict[str, str] | None = None
    other_blocks: list[dict[str, str]] = []

    for block in blocks:
        if block["language"] in ("python", "py", "python3"):
            if python_block is None:
                python_block = block
            else:
                other_blocks.append(block)
        else:
            other_blocks.append(block)

    # 3. نحدد الكود النهائي
    if python_block:
        result.code = python_block["code"]
        result.has_code = True
        result.language = "python"
    elif blocks:
        # لا توجد كتلة Python لكن هناك كتلة أخرى — نأخذ الأولى
        result.code = blocks[0]["code"]
        result.has_code = True
        result.language = blocks[0]["language"]
        result.warnings.append(
            f"⚠️ لم نجد كتلة Python — استخدمنا كتلة {blocks[0]['language']}"
        )
    else:
        # لا توجد كتل كود — نحاول استخراج كود مباشر
        stripped = text.strip()
        if stripped.startswith(("import ", "from ", "def ", "class ", "#")):
            result.code = stripped
            result.has_code = True
            result.warnings.append("⚠️ الكود لم يكن داخل كتلة markdown")
        else:
            result.warnings.append("⚠️ لم نجد أي كود في الرد")

    # 4. استخراج الشرح
    result.explanation = extract_explanation(text)

    # 5. تحذيرات إضافية
    if result.has_code and len(result.code) < 10:
        result.warnings.append("⚠️ الكود قصير جداً — قد يكون غير مكتمل")

    if result.has_code and len(result.code) > 5000:
        result.warnings.append(
            f"⚠️ الكود طويل جداً ({len(result.code)} حرف) — قد يسبب مشاكل"
        )

    return result


# ============================================================
# Code Validation — فحص الكود قبل التنفيذ
# ============================================================
def validate_generated_code(code: str) -> tuple[bool, list[str]]:
    """
    فحص أولي للكود قبل إرساله للـ Sandbox.

    Args:
        code: كود Python

    Returns:
        (is_valid, warnings)
    """
    warnings: list[str] = []

    if not code or not code.strip():
        return False, ["⚠️ الكود فارغ"]

    # 1. فحص أن الكود يستخدم df
    if "df" not in code:
        warnings.append(
            "⚠️ الكود لا يستخدم المتغير 'df' — تأكد من أنه يعمل على البيانات"
        )

    # 2. فحص استيرادات خطيرة
    dangerous_imports = [
        r"\bimport\s+os\b",
        r"\bimport\s+sys\b",
        r"\bimport\s+subprocess\b",
        r"\bimport\s+shutil\b",
        r"\bimport\s+socket\b",
        r"\bimport\s+requests\b",
        r"\bfrom\s+os\s+import\b",
        r"\bfrom\s+sys\s+import\b",
        r"\bfrom\s+subprocess\s+import\b",
    ]
    for pattern in dangerous_imports:
        if re.search(pattern, code):
            return False, [f"🚫 استيراد خطير: {pattern}"]

    # 3. فحص دوال خطيرة
    dangerous_calls = [
        (r"\bopen\s*\(", "فتح ملفات"),
        (r"\beval\s*\(", "تنفيذ ديناميكي"),
        (r"\bexec\s*\(", "تنفيذ ديناميكي"),
        (r"\b__import__\s*\(", "استيراد ديناميكي"),
        (r"\bos\.system\b", "أوامر نظام"),
        (r"\bsubprocess\.", "عمليات فرعية"),
    ]
    for pattern, desc in dangerous_calls:
        if re.search(pattern, code):
            return False, [f"🚫 كود خطير: {desc}"]

    # 4. فحص أن الكود لا يحتوي على "print" فقط
    if "print" not in code and "fig" not in code:
        warnings.append(
            "⚠️ الكود لا يحتوي على print() أو fig — قد لا تظهر أي نتيجة"
        )

    # 5. فحص بناء الجملة
    try:
        import ast
        ast.parse(code)
    except SyntaxError as e:
        return False, [f"❌ خطأ في بناء الجملة: {e}"]

    return True, warnings


# ============================================================
# High-Level API
# ============================================================
def prepare_prompt(
    user_request: str,
    df: pd.DataFrame | None = None,
    few_shot_examples: list[dict[str, str]] | None = None,
    task_type: str | None = None,
    language: str | None = None,
    extra_instructions: str = "",
) -> tuple[str, str, str]:
    """
    دالة شاملة لبناء prompt كامل.

    Args:
        user_request: طلب المستخدم
        df: البيانات (اختياري)
        few_shot_examples: أمثلة سابقة (اختياري)
        task_type: نوع المهمة (يُكشف تلقائياً لو None)
        language: اللغة (تُكشف تلقائياً لو None)
        extra_instructions: تعليمات إضافية

    Returns:
        (system_prompt, user_prompt, detected_task)
    """
    # كشف تلقائي
    if task_type is None:
        task_type = detect_task_type(user_request)
    if language is None:
        language = detect_language(user_request)

    # بناء سياق البيانات
    dataframe_info = ""
    if df is not None:
        dataframe_info = build_dataframe_context(df)

    # بناء السياق
    context = PromptContext(
        user_request=user_request,
        task_type=task_type,
        language=language,
        dataframe_info=dataframe_info,
        few_shot_examples=few_shot_examples or [],
        extra_instructions=extra_instructions,
    )

    system_prompt, user_prompt = build_full_prompt(context)
    return system_prompt, user_prompt, task_type


# ============================================================
# Advanced Templates — قوالب متخصصة
# ============================================================
def build_clean_prompt(
    df: pd.DataFrame,
    user_request: str = "",
    language: str | None = None,
    few_shot_examples: list[dict[str, str]] | None = None,
) -> tuple[str, str, str]:
    request = user_request or "نظف البيانات وأصلح المشاكل"
    if language is None:
        language = detect_language(request)

    extra = """
## Cleaning-Specific Rules
1. **Always report what was changed** — print before/after stats.
2. **Handle missing values carefully**:
  - Numeric: fill with median (or mean if normally distributed)
  - Categorical: fill with mode or "Unknown"
  - Drop rows only if < 5% missing
3. **Remove duplicates** — report how many were removed.
4. **Fix data types**:
  - Convert date-like strings to datetime
  - Convert numeric strings to numbers
  - Strip whitespace from text
5. **Detect outliers** using IQR method for numeric columns.
6. **Print a summary** at the end: rows before/after, columns cleaned.
"""

    context = PromptContext(
        user_request=request,
        task_type=TASK_CLEAN,
        language=language,
        dataframe_info=build_dataframe_context(df),
        few_shot_examples=few_shot_examples or [],
        extra_instructions=extra,
        max_code_lines=120,
    )

    system, user = build_full_prompt(context)
    return system, user, TASK_CLEAN


def build_predict_prompt(
    df: pd.DataFrame,
    user_request: str = "",
    target_column: str | None = None,
    date_column: str | None = None,
    periods_ahead: int = 10,
    language: str | None = None,
    few_shot_examples: list[dict[str, str]] | None = None,
) -> tuple[str, str, str]:
    request = user_request or "تنبأ بالقيم المستقبلية"
    if language is None:
        language = detect_language(request)

    extra = f"""
## Forecasting-Specific Rules
1. **Target column**: {target_column or 'auto-detect a numeric column'}
2. **Date column**: {date_column or 'auto-detect a datetime column'}
3. **Forecast horizon**: {periods_ahead} periods ahead.
4. **Method selection** (in order of preference):
  - If enough data (> 24 points): use `statsmodels` ARIMA or simple exponential smoothing
  - If < 24 points: use linear regression with time index
  - Always include a confidence interval
5. **Print**:
  - Historical trend summary
  - Forecast values (as a table)
  - Trend direction (up/down/flat)
6. **Plot**:
  - Historical line + forecasted line
  - Use `px.line` with different colors
  - Add confidence band if available
7. **If no date column exists**: explain clearly why forecasting is not possible.
"""

    context = PromptContext(
        user_request=request,
        task_type=TASK_PREDICT,
        language=language,
        dataframe_info=build_dataframe_context(df),
        few_shot_examples=few_shot_examples or [],
        extra_instructions=extra,
        max_code_lines=150,
    )

    system, user = build_full_prompt(context)
    return system, user, TASK_PREDICT


def build_visualize_prompt(
    df: pd.DataFrame,
    user_request: str = "",
    chart_type: str | None = None,
    language: str | None = None,
    few_shot_examples: list[dict[str, str]] | None = None,
) -> tuple[str, str, str]:
    request = user_request or "ارسم مخططاً مناسباً للبيانات"
    if language is None:
        language = detect_language(request)

    chart_hint = ""
    if chart_type:
        chart_hint = f"\n2. **Use chart type**: `{chart_type}`"

    extra = f"""
## Visualization-Specific Rules
1. **Choose the RIGHT chart**:
  - Time series → `px.line`
  - Comparison → `px.bar`
  - Distribution → `px.histogram` or `px.box`
  - Relationship → `px.scatter`
  - Composition → `px.pie` or `px.sunburst`
  - Correlation → `px.imshow` (heatmap){chart_hint}
3. **Always include**:
  - Clear title (in user's language)
  - Axis labels
  - Legend (if multiple series)
  - Color scheme (`color_discrete_sequence` for aesthetics)
4. **Make it interactive**:
  - Enable hover data
  - Add `template="plotly_white"` for clean look
5. **Create the figure** and assign it to `fig`.
6. **Print** a short summary of what the chart shows.
"""

    context = PromptContext(
        user_request=request,
        task_type=TASK_VISUALIZE,
        language=language,
        dataframe_info=build_dataframe_context(df, include_stats=False),
        few_shot_examples=few_shot_examples or [],
        extra_instructions=extra,
        max_code_lines=100,
    )

    system, user = build_full_prompt(context)
    return system, user, TASK_VISUALIZE


def build_report_prompt(
    df: pd.DataFrame,
    user_request: str = "",
    business_context: str = "",
    language: str | None = None,
    few_shot_examples: list[dict[str, str]] | None = None,
) -> tuple[str, str, str]:
    request = user_request or "أعطني تقريراً استراتيجياً شاملاً"
    if language is None:
        language = detect_language(request)

    context_hint = ""
    if business_context:
        context_hint = f"\n\n**Business Context**: {business_context}"

    extra = f"""
## Report-Specific Rules
1. **Structure the report** as:
  - **Executive Summary** (2-3 sentences)
  - **Key Findings** (3-5 bullet points with numbers)
  - **Business Implications** (what this means)
  - **Recommendations** (3-5 actionable items)
  - **Risks & Opportunities**
  - **Next Steps**{context_hint}
2. **Generate Python code** that computes ALL the numbers you cite.
3. **Use clear labels** in the output (e.g., "Total Revenue: 1,234,567").
4. **Include visualizations** where helpful (1-2 charts max).
5. **Be specific** — use numbers, percentages, dates.
6. **Be honest** — if data is insufficient, say so.
"""

    context = PromptContext(
        user_request=request,
        task_type=TASK_REPORT,
        language=language,
        dataframe_info=build_dataframe_context(df),
        few_shot_examples=few_shot_examples or [],
        extra_instructions=extra,
        max_code_lines=150,
    )

    system, user = build_full_prompt(context)
    return system, user, TASK_REPORT


if __name__ == "__main__":
    import pandas as pd

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print("=" * 60)
    print("🧪 اختبار core/prompts.py — شامل")
    print("=" * 60)

    # ---------- 1. كشف اللغة والمهمة ----------
    print("\n[1] كشف اللغة والمهمة:")
    print(f"   'حلل البيانات' → {detect_language('حلل البيانات')}, {detect_task_type('حلل البيانات')}")
    print(f"   'clean data' → {detect_language('clean data')}, {detect_task_type('clean data')}")

    # ---------- 2. Response Parser ----------
    print("\n[2] Response Parser:")
    sample_response = (
        "Sure! Here's the code:\n\n"
        "```python\n"
        "import pandas as pd\n"
        "avg = df['salary'].mean()\n"
        "print(f'المتوسط: {avg}')\n"
        "```\n\n"
        "**Explanation:**\n"
        "This code calculates the average salary from the DataFrame.\n"
    )
    parsed = parse_llm_response(sample_response)
    print(f"   ✅ has_code: {parsed.has_code}")
    print(f"   📝 code: {parsed.code[:80]}...")
    print(f"   💬 explanation: {parsed.explanation[:80]}...")
    print(f"   ⚠️ warnings: {parsed.warnings}")

    # ---------- 3. Code Validation ----------
    print("\n[3] Code Validation:")
    good_code = "avg = df['salary'].mean()\nprint(avg)"
    bad_code = "import os\nos.system('dir')"
    syntax_error = "x = 10\ny = / 5"

    print(f"   ✅ كود جيد: {validate_generated_code(good_code)}")
    print(f"   🚫 كود خطير: {validate_generated_code(bad_code)}")
    print(f"   ❌ خطأ نحوي: {validate_generated_code(syntax_error)}")

    # ---------- 4. Prepare Prompt ----------
    print("\n[4] prepare_prompt:")
    df = pd.DataFrame({
        "name": ["Ali", "Sara", "Omar"],
        "salary": [5000.0, 7000.0, 9000.0],
    })
    system, user, task = prepare_prompt(
        "حلل توزيع الرواتب",
        df=df,
    )
    print(f"   ✅ Task detected: {task}")
    print(f"   📏 System: {len(system)} chars")
    print(f"   📏 User:   {len(user)} chars")

    # ---------- 5. Response بدون كود ----------
    print("\n[5] Response بدون كود:")
    no_code = "I cannot help with that request."
    parsed2 = parse_llm_response(no_code)
    print(f"   ✅ has_code: {parsed2.has_code}")
    print(f"   ⚠️ warnings: {parsed2.warnings}")

    # ---------- 6. Response فارغ ----------
    print("\n[6] Response فارغ:")
    parsed3 = parse_llm_response("")
    print(f"   ✅ has_code: {parsed3.has_code}")
    print(f"   ⚠️ warnings: {parsed3.warnings}")

    print("\n" + "=" * 60)
    print("✅ اكتمل اختبار prompts.py بالكامل")
    print("=" * 60)
    # ============================================================
# Auto Prompt Builder — يختار القالب تلقائياً
# ============================================================
def build_auto_prompt(
    df: pd.DataFrame | None,
    user_request: str,
    few_shot_examples: list[dict[str, str]] | None = None,
    extra_instructions: str = "",
) -> tuple[str, str, str]:
    task = detect_task_type(user_request)
    language = detect_language(user_request)

    if df is None:
        return prepare_prompt(
            user_request=user_request,
            df=None,
            few_shot_examples=few_shot_examples,
            task_type=task,
            language=language,
            extra_instructions=extra_instructions,
        )

    if task == TASK_CLEAN:
        return build_clean_prompt(df, user_request, language, few_shot_examples=few_shot_examples)

    if task == TASK_PREDICT:
        return build_predict_prompt(df, user_request, language=language, few_shot_examples=few_shot_examples)

    if task == TASK_VISUALIZE:
        return build_visualize_prompt(df, user_request, language=language, few_shot_examples=few_shot_examples)

    if task == TASK_REPORT:
        return build_report_prompt(df, user_request, language=language, few_shot_examples=few_shot_examples)

    return prepare_prompt(
        user_request=user_request,
        df=df,
        few_shot_examples=few_shot_examples,
        task_type=task,
        language=language,
        extra_instructions=extra_instructions,
    )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    other = len(text) - arabic
    tokens = (arabic / 2) + (other / 4)
    return int(tokens)


def check_prompt_size(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 8000,
) -> tuple[bool, int, str]:
    total = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)

    if total > max_tokens:
        msg = f"⚠️ الـ prompt كبير جداً: ~{total} tokens (الحد: {max_tokens}). قد يفشل الطلب."
        return False, total, msg

    if total > max_tokens * 0.8:
        msg = f"⚠️ الـ prompt كبير: ~{total} tokens (قريب من الحد)"
        return True, total, msg

    return True, total, f"✅ حجم الـ prompt مناسب: ~{total} tokens"


PROMPT_BUILDERS: dict[str, callable] = {
    TASK_ANALYZE: lambda df, req, **kw: prepare_prompt(req, df=df, task_type=TASK_ANALYZE, **kw),
    TASK_CLEAN: lambda df, req, **kw: build_clean_prompt(df, req, **kw),
    TASK_PREDICT: lambda df, req, **kw: build_predict_prompt(df, req, **kw),
    TASK_VISUALIZE: lambda df, req, **kw: build_visualize_prompt(df, req, **kw),
    TASK_REPORT: lambda df, req, **kw: build_report_prompt(df, req, **kw),
    TASK_CUSTOM: lambda df, req, **kw: prepare_prompt(req, df=df, task_type=TASK_CUSTOM, **kw),
}


def get_prompt_for_task(
    task_type: str,
    df: pd.DataFrame | None,
    user_request: str,
    **kwargs: Any,
) -> tuple[str, str, str]:
    if task_type not in PROMPT_BUILDERS:
        logger.warning("⚠️ مهمة غير معروفة: %s — نستخدم custom", task_type)
        task_type = TASK_CUSTOM

    builder = PROMPT_BUILDERS[task_type]
    return builder(df, user_request, **kwargs)


def _run_integration_test() -> None:
    import pandas as pd

    print("=" * 60)
    print("🧪 اختبار تكاملي شامل — prompts.py")
    print("=" * 60)

    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=20, freq="D"),
        "sales": [100 + i * 5 for i in range(20)],
        "region": ["North", "South"] * 10,
    })

    print("\n[1] build_auto_prompt:")
    test_requests = [
        "حلل البيانات",
        "نظف البيانات",
        "ارسم مخطط",
        "تنبأ بالمبيعات",
        "أعطني تقرير",
    ]
    for req in test_requests:
        _, _, task = build_auto_prompt(df, req)
        print(f"   '{req}' → {task}")

    print("\n[2] estimate_tokens:")
    samples = [
        "Hello world",
        "مرحباً بالعالم",
        "Mixed نص with English",
    ]
    for s in samples:
        print(f"   '{s}' → ~{estimate_tokens(s)} tokens")

    print("\n[3] check_prompt_size:")
    sys_p, usr_p, _ = build_auto_prompt(df, "حلل البيانات")
    ok, tokens, msg = check_prompt_size(sys_p, usr_p)
    print(f"   {msg}")

    print("\n[4] PROMPT_BUILDERS registry:")
    for task in PROMPT_BUILDERS:
        print(f"   ✅ {task}")

    print("\n[5] get_prompt_for_task:")
    for task in SUPPORTED_TASKS:
        sys_p, usr_p, returned_task = get_prompt_for_task(
            task, df, "طلب اختباري"
        )
        print(f"   {task:12s} → returned: {returned_task:12s} | size: {len(sys_p)+len(usr_p)}")

    print("\n" + "=" * 60)
    print("✅ اكتمل الاختبار التكاملي")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    _run_integration_test()