"""
core/code_executor.py — Sandbox آمن لتنفيذ أكواد Python المولّدة
Secure sandbox for executing LLM-generated Python code.

الاستراتيجية:
1. فحص ثابت للكود (Static Analysis) لكشف الأنماط الخطيرة
2. تنفيذ في subprocess معزول مع timeout صارم
3. التقاط النتائج (dataframes, figures, prints, errors)

الإصلاحات:
- [1] إزالة _patched_px_function الميت
- [2] فصل علامات JSON في أسطر مستقلة
- [3] التقاط رسوم Plotly من globals
- [4] تنظيف stdout في كل الفروع
- [5] تصدير df إذا عدّله المستخدم
- [6] استخدام exec(compile(...))
- [7] نقل import time للأعلى
- [8] [جديد] إصلاح UnicodeEncodeError على Windows:
      - PYTHONIOENCODING=utf-8 + PYTHONUTF8=1 في subprocess
      - إعادة تغليف sys.stdout/stderr في السكربت المولّد
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import CONFIG, DATA_DIR
from utils.column_matcher import (
    friendly_missing_column_message,
    normalize_column_name,
    resolve_column,
)

logger = logging.getLogger(__name__)


# ============================================================
# نماذج البيانات
# ============================================================
@dataclass
class ExecutionResult:
    """نتيجة تنفيذ كود."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    error_type: str = ""
    figures: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    code: str = ""

    def to_dict(self, include_details: bool = False) -> dict[str, Any]:
        base: dict[str, Any] = {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
            "error_type": self.error_type,
            "figures_count": len(self.figures),
            "variables_count": len(self.variables),
            "execution_time": self.execution_time,
        }
        if include_details:
            base["figures"] = self.figures
            base["variables"] = self.variables
            base["code"] = self.code
        return base


# ============================================================
# استثناءات
# ============================================================
class CodeExecutorError(Exception):
    """خطأ عام في المنفّذ."""


class UnsafeCodeError(CodeExecutorError):
    """الكود يحتوي على أنماط خطيرة."""


class ExecutionTimeoutError(CodeExecutorError):
    """انتهت مهلة التنفيذ."""


# ============================================================
# الفئة الرئيسية
# ============================================================
class CodeExecutor:
    """منفّذ كود Python آمن."""

    # أنماط خطيرة في الكود المصدري (regex)
    DANGEROUS_PATTERNS: tuple[tuple[str, str], ...] = (
        (r"\bos\s*\.\s*system\b", "استدعاء أوامر النظام"),
        (r"\bos\s*\.\s*popen\b", "استدعاء أوامر النظام"),
        (r"\bsubprocess\b", "تشغيل عمليات فرعية"),
        (r"\bshutil\s*\.\s*rmtree\b", "حذف مجلدات"),
        (r"\bos\s*\.\s*remove\b", "حذف ملفات"),
        (r"\bos\s*\.\s*unlink\b", "حذف ملفات"),
        (r"\b__import__\s*\(", "استيراد ديناميكي"),
        (r"\beval\s*\(", "تنفيذ كود ديناميكي"),
        (r"\bexec\s*\(", "تنفيذ كود ديناميكي"),
        (r"\bcompile\s*\(", "تجميع كود ديناميكي"),
        (r"\bsocket\b", "اتصالات شبكية"),
        (r"\brequests\b", "طلبات شبكية"),
        (r"\burllib\b", "طلبات شبكية"),
        (r"\bhttpx\b", "طلبات شبكية"),
        (r"\bpickle\s*\.\s*loads\b", "تحميل كائنات خطير"),
        (r"\bsys\s*\.\s*exit\b", "إنهاء العملية"),
        (r"\bquit\s*\(", "إنهاء العملية"),
        (r"\bexit\s*\(", "إنهاء العملية"),
        (r"\bglobals\s*\(", "وصول للنطاق العام"),
        (r"\blocals\s*\(", "وصول للنطاق المحلي"),
        (r"\bgetattr\s*\([^,]+,\s*['\"]__", "وصول للخصائص الخاصة"),
    )

    # وحدات محظورة تماماً
    FORBIDDEN_MODULES: frozenset[str] = frozenset({
        "os", "sys", "subprocess", "shutil", "socket",
        "requests", "urllib", "urllib2", "urllib3", "httpx",
        "pickle", "marshal", "shelve", "dbm",
        "ctypes", "cffi", "multiprocessing", "threading",
        "signal", "pty", "tty", "termios",
        "importlib", "pkgutil", "runpy",
    })

    def __init__(
        self,
        timeout: int | None = None,
        allowed_modules: tuple[str, ...] | None = None,
    ) -> None:
        self.timeout = timeout or CONFIG.sandbox.timeout_seconds
        self.allowed_modules = (
            allowed_modules or CONFIG.sandbox.allowed_modules
        )

    # --------------------------------------------------------
    # الفحص الثابت
    # --------------------------------------------------------
    def _static_check(self, code: str) -> None:
        """يفحص الكود قبل التنفيذ."""
        for pattern, description in self.DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                raise UnsafeCodeError(
                    f"🚫 كود غير آمن: {description} (النمط: {pattern})"
                )

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise CodeExecutorError(f"❌ خطأ في بناء الجملة: {e}") from e

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._check_module(node.module)
            elif isinstance(node, ast.Call):
                self._check_call(node)

    def _check_call(self, node: ast.Call) -> None:
        """فحص open() للكتابة."""
        func = node.func
        is_open = (
            (isinstance(func, ast.Name) and func.id == "open")
            or (isinstance(func, ast.Attribute) and func.attr == "open")
        )
        if not is_open:
            return

        mode_value: str | None = None
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            if isinstance(node.args[1].value, str):
                mode_value = node.args[1].value

        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    mode_value = kw.value.value

        if mode_value and any(c in mode_value for c in ("w", "a", "+")):
            raise UnsafeCodeError(
                f"🚫 كود غير آمن: فتح ملف للكتابة (mode={mode_value!r})"
            )

    def _check_module(self, module_name: str) -> None:
        """يتحقق من أن الوحدة مسموحة."""
        root_module = module_name.split(".")[0]

        if root_module in self.FORBIDDEN_MODULES:
            raise UnsafeCodeError(
                f"🚫 الوحدة '{module_name}' محظورة لأسباب أمنية"
            )

        if root_module not in self.allowed_modules:
            raise UnsafeCodeError(
                f"🚫 الوحدة '{module_name}' غير مسموحة. "
                f"المسموح: {', '.join(sorted(self.allowed_modules))}"
            )

    @staticmethod
    def _rewrite_dataframe_column_references(code: str, df: Any | None) -> str:
        """Rewrites likely DataFrame column references to the actual columns in the file."""
        if not code or df is None or getattr(df, "empty", True):
            return code
        result = code
        patterns = (
            r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\[\s*\[\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\]\s*\])",
            r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\[\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\])",
            r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.loc\s*\[\s*[:,\s]*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\])",
            r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.groupby\s*\(\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\))",
            r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.sort_values\s*\(\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\))",
            r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.drop\s*\(\s*columns\s*=\s*\[\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\])",
        )

        for pattern in patterns:
            def _replace(match: re.Match[str]) -> str:
                raw_name = match.group("name")
                resolved = resolve_column(df, raw_name, cutoff=0.55)
                if resolved is None:
                    return match.group(0)
                return f"{match.group('prefix')}{resolved}{match.group('suffix')}"

            result = re.sub(pattern, _replace, result)

        return result

    # --------------------------------------------------------
    # بناء سكربت التنفيذ
    # --------------------------------------------------------
    def _build_runner_script(self, user_code: str, data_path: str | None) -> str:
        """يبني سكربت Python كامل للتنفيذ في subprocess."""
        data_loading = ""
        if data_path:
            data_loading = f"""
# ===== تحميل البيانات =====
_data_path = {repr(data_path)}
if _data_path.endswith('.csv'):
    df = pd.read_csv(_data_path)
elif _data_path.endswith(('.xlsx', '.xls')):
    df = pd.read_excel(_data_path)
else:
    df = None
# ==========================
"""

        user_code_literal = repr(user_code)

        script = f'''
# ===== [إصلاح UnicodeEncodeError] إجبار stdout/stderr على UTF-8 =====
import io as _io
import re
import sys as _sys


def _force_utf8(stream):
    """يعيد تغليف stream بترميز UTF-8 لو لم يكن كذلك."""
    try:
        enc = (getattr(stream, "encoding", "") or "").lower()
        if enc.replace("-", "") == "utf8":
            return stream
        if hasattr(stream, "buffer"):
            return _io.TextIOWrapper(
                stream.buffer, encoding="utf-8", errors="replace",
                line_buffering=True,
            )
    except Exception:
        pass
    return stream

_sys.stdout = _force_utf8(_sys.stdout)
_sys.stderr = _force_utf8(_sys.stderr)
# ====================================================================

import json
import traceback
import warnings
warnings.filterwarnings("ignore")

# ===== استيرادات آمنة =====
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

ROOT = {str(Path(__file__).resolve().parents[2])!r}
if ROOT not in _sys.path:
    _sys.path.insert(0, ROOT)

from utils.column_matcher import resolve_column


def _rewrite_dataframe_reference(code: str, frame):
    if not code or frame is None or getattr(frame, "empty", True):
        return code
    result = code
    patterns = (
        r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\[\s*\[\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\]\s*\])",
        r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\[\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\])",
        r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.loc\s*\[\s*[:,\s]*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\])",
        r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.groupby\s*\(\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\))",
        r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.sort_values\s*\(\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\))",
        r"(?P<prefix>\b(?:df|data|dataset|frame)\s*\.drop\s*\(\s*columns\s*=\s*\[\s*[\'\"])(?P<name>[^\'\"]+)(?P<suffix>[\'\"]\s*\])",
    )
    for pattern in patterns:
        def _replace(match):
            raw_name = match.group("name")
            resolved = resolve_column(frame, raw_name, cutoff=0.55)
            if resolved is None:
                return match.group(0)
            return f"{match.group('prefix')}{resolved}{match.group('suffix')}"

        result = re.sub(pattern, _replace, result)
    return result

# ===== تحميل البيانات =====
{data_loading}

# ===== كود المستخدم =====
_user_code = {user_code_literal}
if 'df' in globals() and globals()['df'] is not None:
    _user_code = _rewrite_dataframe_reference(_user_code, globals()['df'])

try:
    exec(compile(_user_code, "<user_code>", "exec"), globals())
except KeyError as _e:
    missing = None
    try:
        missing = re.search(r"['\"]([^'\"]+)['\"]", str(_e)).group(1)
    except Exception:
        missing = None

    if 'df' in globals() and globals()['df'] is not None and missing:
        _resolved = resolve_column(globals()['df'], missing, cutoff=0.55)
        if _resolved:
            _user_code = _rewrite_dataframe_reference(_user_code, globals()['df'])
            try:
                exec(compile(_user_code, "<user_code>", "exec"), globals())
            except Exception as _retry_error:
                _error_info = {
                    "type": type(_retry_error).__name__,
                    "message": str(_retry_error),
                    "traceback": traceback.format_exc(),
                }
                print("__EXECUTION_ERROR__")
                print(json.dumps(_error_info, default=str, ensure_ascii=False))
                _sys.exit(0)
    else:
        _error_info = {
            "type": type(_e).__name__,
            "message": str(_e),
            "traceback": traceback.format_exc(),
        }
        print("__EXECUTION_ERROR__")
        print(json.dumps(_error_info, default=str, ensure_ascii=False))
        _sys.exit(0)
except Exception as _e:
    _error_info = {
        "type": type(_e).__name__,
        "message": str(_e),
        "traceback": traceback.format_exc(),
    }
    print("__EXECUTION_ERROR__")
    print(json.dumps(_error_info, default=str, ensure_ascii=False))
    _sys.exit(0)

# ===== التقاط المتغيرات والرسوم =====
_exports = {{}}
_figures_json = []

_skip_names = {{
    "pd", "np", "px", "go", "pio", "json", "traceback", "warnings",
    "_exports", "_figures_json", "_skip_names", "_e", "_error_info",
    "_user_code", "_data_path", "_name", "_value", "_f",
    "_io", "_sys", "_force_utf8",
}}

for _name, _value in list(globals().items()):
    if _name.startswith("_") or _name in _skip_names:
        continue

    try:
        if isinstance(_value, go.Figure):
            try:
                _figures_json.append(json.loads(pio.to_json(_value)))
            except Exception:
                pass
            _exports[_name] = {{"type": "Figure", "captured": True}}

        elif isinstance(_value, pd.DataFrame):
            _exports[_name] = {{
                "type": "DataFrame",
                "shape": list(_value.shape),
                "columns": [str(c) for c in _value.columns],
                "head": json.loads(_value.head(10).to_json(orient="split", date_format="iso")),
            }}
        elif isinstance(_value, np.integer):
            _exports[_name] = {{"type": "int", "value": int(_value)}}
        elif isinstance(_value, np.floating):
            _exports[_name] = {{"type": "float", "value": float(_value)}}
        elif isinstance(_value, np.bool_):
            _exports[_name] = {{"type": "bool", "value": bool(_value)}}
        elif isinstance(_value, pd.Series):
            _exports[_name] = {{
                "type": "Series",
                "name": str(_value.name),
                "length": len(_value),
                "head": json.loads(_value.head(10).to_json(date_format="iso")),
            }}
        elif isinstance(_value, (int, float, str, bool)):
            _exports[_name] = {{"type": type(_value).__name__, "value": _value}}
        elif isinstance(_value, (list, tuple)) and len(_value) <= 100:
            _exports[_name] = {{"type": type(_value).__name__, "value": list(_value)}}
        elif isinstance(_value, dict) and len(_value) <= 100:
            _exports[_name] = {{"type": "dict", "value": str(_value)[:500]}}
    except Exception:
        pass

# ===== طباعة النتيجة النهائية =====
_result = {{
    "success": True,
    "variables": _exports,
    "figures": _figures_json,
}}
print("__EXECUTION_RESULT__")
print(json.dumps(_result, default=str, ensure_ascii=False))
'''

        return textwrap.dedent(script).strip()

    # --------------------------------------------------------
    # التنفيذ الفعلي
    # --------------------------------------------------------
    def execute(
        self,
        code: str,
        data_path: str | Path | None = None,
    ) -> ExecutionResult:
        """ينفّذ كود Python بأمان."""
        result = ExecutionResult(success=False, code=code)
        start_time = time.time()

        if data_path is not None:
            data_path = Path(data_path).resolve()

        # 1. فحص ثابت
        try:
            self._static_check(code)
        except UnsafeCodeError as e:
            result.error = str(e)
            result.error_type = "UnsafeCodeError"
            result.execution_time = time.time() - start_time
            logger.warning("🚫 كود مرفوض: %s", e)
            return result
        except CodeExecutorError as e:
            result.error = str(e)
            result.error_type = "SyntaxError"
            result.execution_time = time.time() - start_time
            return result

        # 2. بناء السكربت
        data_path_str = str(data_path) if data_path else None
        if data_path is not None and Path(data_path).exists():
            try:
                import pandas as pd

                if str(data_path).lower().endswith(".csv"):
                    resolved_df = pd.read_csv(data_path)
                elif str(data_path).lower().endswith((".xlsx", ".xls")):
                    resolved_df = pd.read_excel(data_path)
                else:
                    resolved_df = None
                code = self._rewrite_dataframe_column_references(code, resolved_df)
            except Exception:
                pass
        runner_script = self._build_runner_script(code, data_path_str)

        # 3. كتابة السكربت في ملف مؤقت
        tmp_dir = DATA_DIR / "temp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        script_file = tmp_dir / f"run_{uuid.uuid4().hex[:8]}.py"

        try:
            script_file.write_text(runner_script, encoding="utf-8")

            # ============================================================
            # [إصلاح UnicodeEncodeError] إجبار subprocess على UTF-8
            # ============================================================
            child_env = os.environ.copy()
            child_env["PYTHONIOENCODING"] = "utf-8"
            child_env["PYTHONUTF8"] = "1"
            # على Windows: بعض إصدارات Python تحتاج هذا أيضاً
            child_env["PYTHONLEGACYWINDOWSSTDIO"] = "0"

            proc = subprocess.run(
                [sys.executable, str(script_file)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
                cwd=str(DATA_DIR),
                env=child_env,
            )

            # 5. تحليل المخرجات
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            if "__EXECUTION_ERROR__" in stdout:
                before, _, after = stdout.partition("__EXECUTION_ERROR__")
                result.stdout = before.strip()
                result.stderr = stderr
                payload = after.lstrip("\n").strip()
                try:
                    err = json.loads(payload)
                    result.error = err.get("message", "خطأ غير معروف")
                    result.error_type = err.get("type", "Exception")
                    if err.get("traceback"):
                        result.stderr = (stderr + "\n" + err["traceback"]).strip()
                except json.JSONDecodeError:
                    result.error = payload[:500] or "فشل تحليل الخطأ"
                    result.error_type = "ParseError"

            elif "__EXECUTION_RESULT__" in stdout:
                before, _, after = stdout.partition("__EXECUTION_RESULT__")
                result.stdout = before.strip()
                result.stderr = stderr
                payload = after.lstrip("\n").strip()
                try:
                    parsed = json.loads(payload)
                    result.success = True
                    result.variables = parsed.get("variables", {})
                    result.figures = parsed.get("figures", [])
                except json.JSONDecodeError as e:
                    result.error = f"فشل تحليل النتيجة: {e}"
                    result.error_type = "ParseError"

            else:
                result.stdout = stdout.strip()
                result.stderr = stderr
                result.error = "⚠️ لم يتم إرجاع نتيجة. تحقق من stderr للأخطاء."
                result.error_type = "NoResult"
                if stderr:
                    result.error = stderr[:500]

            result.execution_time = time.time() - start_time
            return result

        except subprocess.TimeoutExpired:
            result.error = f"⏱️ انتهت المهلة ({self.timeout} ثانية)"
            result.error_type = "TimeoutError"
            result.execution_time = time.time() - start_time
            logger.warning("⏱️ timeout بعد %d ثانية", self.timeout)
            return result

        except Exception as e:
            result.error = f"❌ خطأ غير متوقع: {e}"
            result.error_type = type(e).__name__
            result.execution_time = time.time() - start_time
            logger.exception("خطأ في التنفيذ")
            return result

        finally:
            try:
                if script_file.exists():
                    script_file.unlink()
            except Exception:
                pass

    # --------------------------------------------------------
    # تنظيف الملفات المؤقتة
    # --------------------------------------------------------
    @staticmethod
    def cleanup_temp_files(max_age_hours: int = 24) -> int:
        """يحذف ملفات temp أقدم من max_age_hours."""
        tmp_dir = DATA_DIR / "temp"
        if not tmp_dir.exists():
            return 0

        now = time.time()
        max_age_seconds = max_age_hours * 3600
        deleted = 0

        for f in tmp_dir.glob("run_*.py"):
            try:
                if (now - f.stat().st_mtime) > max_age_seconds:
                    f.unlink()
                    deleted += 1
            except Exception:
                pass

        return deleted


# ============================================================
# نسخة عامة (Singleton)
# ============================================================
_default_executor: CodeExecutor | None = None


def get_executor() -> CodeExecutor:
    """يعيد نسخة مشتركة من المنفّذ."""
    global _default_executor
    if _default_executor is None:
        _default_executor = CodeExecutor()
    return _default_executor