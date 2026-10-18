"""
ui/chat.py — واجهة المحادثة

التدفق عند كل طلب:
    prepare_prompt -> LLM -> parse -> validate -> execute -> log -> render

شكل رسالة المساعد داخل st.session_state["messages"]:
    {
      "role": "assistant", "explanation": str, "code": str, "notice": str,
      "result": {success, stdout, stderr, error, error_type,
                 figures, variables, execution_time} | None,
      "operation_id": int | None, "rated": bool,
    }
ورسالة المستخدم: {"role": "user", "content": str}
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.code_executor import (
    CodeExecutorError,
    ExecutionTimeoutError,
    UnsafeCodeError,
    get_executor,
)
from core.llm_client import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    get_client,
)
from core.memory import get_memory
from core.prompts import (
    parse_llm_response,
    prepare_prompt,
    validate_generated_code,
)
from utils.helpers import humanize_duration, truncate_text
from utils.i18n import t


# ============================================================
# التسجيل في الذاكرة
# ============================================================
def _log(
    user_request: str,
    code: str,
    summary: str,
    success: bool,
    seconds: float,
    error: str,
    error_type: str,
) -> int | None:
    """يسجّل العملية. فشل التسجيل لا يجب أن يوقف التطبيق."""
    ss = st.session_state
    try:
        return get_memory().log_operation(
            user_request=user_request,
            generated_code=code,
            result_summary=summary,
            success=success,
            execution_time=seconds,
            error=error,
            error_type=error_type,
            dataset_id=ss.get("dataset_id"),
            session_id=ss.get("session_id"),
        )
    except Exception:
        return None


def _summarize(result: Any) -> str:
    """ملخص قصير يُخزَّن في الذاكرة ويُستخدم لاحقاً كمثال few-shot."""
    stdout = (result.stdout or "").strip()
    if stdout:
        return truncate_text(stdout, 500)
    names = ", ".join(result.variables.keys()) or "-"
    return f"variables: {names}; figures: {len(result.figures)}"


def _msg(
    *,
    notice: str = "",
    explanation: str = "",
    code: str = "",
    result: dict[str, Any] | None = None,
    op_id: int | None = None,
) -> dict[str, Any]:
    """يبني رسالة مساعد جاهزة للتخزين في session_state."""
    return {
        "role": "assistant",
        "notice": notice,
        "explanation": explanation,
        "code": code,
        "result": result,
        "operation_id": op_id,
        "rated": False,
    }


# ============================================================
# خط المعالجة
# ============================================================
def _run_pipeline(user_request: str, status: Any) -> dict[str, Any]:
    """
    ينفّذ خط المعالجة كاملاً:
      1. بناء الـ prompt
      2. استدعاء LLM
      3. تحليل الرد
      4. فحص الكود
      5. تنفيذ في Sandbox
      6. تسجيل في الذاكرة
      7. إرجاع الرسالة
    """
    ss = st.session_state

    # 1) بناء الـ prompt مع أمثلة من الذاكرة
    try:
        examples = get_memory().get_few_shot_examples(
            user_request,
            dataset_id=ss.get("dataset_id"),
        )
    except Exception:
        examples = []

    system_prompt, user_prompt, _task = prepare_prompt(
        user_request,
        df=ss.get("df"),
        few_shot_examples=examples,
    )

    llm_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 2) استدعاء النموذج
    status.update(label=t("generating_code"))
    try:
        raw = get_client().chat(llm_messages)
    except LLMAuthError:
        return _msg(notice=t("llm_auth_error"))
    except LLMRateLimitError:
        return _msg(notice=t("llm_rate_limit"))
    except LLMTimeoutError:
        return _msg(notice=t("llm_timeout"))
    except LLMError as exc:
        return _msg(notice=t("llm_error", error=str(exc)))
    except Exception as exc:
        return _msg(notice=t("llm_error", error=str(exc)))

    # 3) تحليل الرد
    parsed = parse_llm_response(raw)
    if not parsed.has_code or not parsed.code.strip():
        return _msg(
            notice=t("no_code_returned"),
            explanation=parsed.explanation or raw,
        )

    # 4) فحص أولي للكود
    ok, problems = validate_generated_code(parsed.code)
    if not ok:
        reason = "; ".join(problems)
        op_id = _log(
            user_request, parsed.code, "", False, 0.0,
            reason, "ValidationError",
        )
        return _msg(
            notice=t("unsafe_code", reason=reason),
            explanation=parsed.explanation,
            code=parsed.code,
            op_id=op_id,
        )

    # 5) التنفيذ في الـ sandbox
    status.update(label=t("executing"))
    try:
        result = get_executor().execute(
            parsed.code,
            data_path=ss.get("data_path"),
        )
    except UnsafeCodeError as exc:
        op_id = _log(
            user_request, parsed.code, "", False, 0.0,
            str(exc), "UnsafeCodeError",
        )
        return _msg(
            notice=t("unsafe_code", reason=str(exc)),
            explanation=parsed.explanation,
            code=parsed.code,
            op_id=op_id,
        )
    except (ExecutionTimeoutError, CodeExecutorError) as exc:
        etype = type(exc).__name__
        op_id = _log(
            user_request, parsed.code, "", False, 0.0,
            str(exc), etype,
        )
        return _msg(
            notice=f"{t('failed')}: {exc}",
            explanation=parsed.explanation,
            code=parsed.code,
            op_id=op_id,
        )

    # 6) التسجيل في الذاكرة
    op_id = _log(
        user_request,
        parsed.code,
        _summarize(result) if result.success else "",
        result.success,
        result.execution_time,
        result.error,
        result.error_type,
    )
    ss["last_operation_id"] = op_id

    result_dict = {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": result.error,
        "error_type": result.error_type,
        "figures": result.figures,
        "variables": result.variables,
        "execution_time": result.execution_time,
    }

    return _msg(
        explanation=parsed.explanation,
        code=parsed.code,
        result=result_dict,
        op_id=op_id,
    )


# ============================================================
# العرض — المتغيّرات
# ============================================================
def _render_variable(name: str, info: dict[str, Any]) -> None:
    """يعرض متغيّراً واحداً من ناتج التنفيذ."""
    kind = info.get("type")
    st.markdown(f"**{name}**")

    if kind == "DataFrame":
        head = info.get("head") or {}
        frame = pd.DataFrame(
            head.get("data", []),
            index=head.get("index"),
            columns=head.get("columns", info.get("columns")),
        )
        st.dataframe(frame, use_container_width=True)
        rows, cols = (info.get("shape") or [len(frame), len(frame.columns)])[:2]
        st.caption(t("rows_cols", rows=rows, cols=cols))
        if rows > len(frame):
            st.caption(t("head_note", shown=len(frame), total=rows))

    elif kind == "Series":
        head = info.get("head") or {}
        st.dataframe(
            pd.Series(head, name=info.get("name")).to_frame(),
            use_container_width=True,
        )
        total = info.get("length", len(head))
        if total > len(head):
            st.caption(t("head_note", shown=len(head), total=total))

    elif kind in ("list", "tuple"):
        st.write(info.get("value"))

    else:  # int / float / str / bool / dict
        st.code(str(info.get("value")), language="text")


# ============================================================
# العرض — النتيجة
# ============================================================
def _render_result(result: dict[str, Any], idx: int) -> None:
    """يعرض نتيجة التنفيذ (نجاح أو فشل)."""
    if not result.get("success"):
        label = f"{t('failed')} — {result.get('error_type') or ''}".rstrip(" —")
        st.error(label)
        if result.get("error"):
            st.code(result["error"], language="text")
        # نعرض stderr لو موجود
        stderr = (result.get("stderr") or "").strip()
        if stderr and stderr != result.get("error"):
            with st.expander("🔍 " + t("results")):
                st.code(stderr, language="text")
        return

    seconds = humanize_duration(result.get("execution_time") or 0.0)
    st.success(f"{t('success')} · {t('execution_time', seconds=seconds)}")

    stdout = (result.get("stdout") or "").strip()
    if stdout:
        st.markdown(f"**{t('output')}**")
        st.code(stdout, language="text")

    # الرسوم: نتجاوز الفارغ والمكرر
    seen: set[str] = set()
    figures: list[dict[str, Any]] = []
    for fig in result.get("figures") or []:
        if not isinstance(fig, dict) or not fig.get("data"):
            continue
        sig = json.dumps(fig, sort_keys=True, default=str)
        if sig not in seen:
            seen.add(sig)
            figures.append(fig)

    for i, fig in enumerate(figures):
        try:
            st.plotly_chart(
                go.Figure(fig),
                use_container_width=True,
                key=f"fig_{idx}_{i}",
            )
        except Exception:
            st.warning(t("figure_error"))

    variables = result.get("variables") or {}
    if variables:
        st.markdown(f"**{t('variables_title')}**")
        for name, info in variables.items():
            _render_variable(name, info)

    if not stdout and not figures and not variables:
        st.caption(t("no_visible_output"))


# ============================================================
# التقييم
# ============================================================
def _on_rate(idx: int, op_id: int, rating: int) -> None:
    """يُسجّل تقييم المستخدم."""
    try:
        get_memory().add_feedback(op_id, rating, "")
    except Exception:
        pass
    st.session_state["messages"][idx]["rated"] = True


# ============================================================
# العرض — رسالة المساعد
# ============================================================
def _render_assistant(msg: dict[str, Any], idx: int) -> None:
    """يعرض رسالة مساعد كاملة (شرح + كود + نتيجة + تقييم)."""
    if msg.get("explanation"):
        st.markdown(msg["explanation"])
    if msg.get("notice"):
        st.warning(msg["notice"])
    if msg.get("code"):
        with st.expander(t("show_code")):
            st.code(msg["code"], language="python")
    if msg.get("result"):
        _render_result(msg["result"], idx)

    op_id = msg.get("operation_id")
    if op_id and msg.get("result"):
        if msg.get("rated"):
            st.caption(t("thanks_feedback"))
        else:
            st.caption(t("rate_this"))
            col_up, col_down, _ = st.columns([1, 1, 4])
            col_up.button(
                t("helpful"),
                key=f"rate_up_{op_id}_{idx}",
                on_click=_on_rate,
                args=(idx, op_id, 5),
            )
            col_down.button(
                t("not_helpful"),
                key=f"rate_down_{op_id}_{idx}",
                on_click=_on_rate,
                args=(idx, op_id, 1),
            )


def _render_message(msg: dict[str, Any], idx: int) -> None:
    """يعرض رسالة واحدة (مستخدم أو مساعد)."""
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            _render_assistant(msg, idx)


# ============================================================
# معالجة طلب جديد
# ============================================================
def _handle_prompt(prompt: str) -> None:
    """يستقبل طلباً جديداً من المستخدم ويعالجه."""
    messages: list[dict[str, Any]] = st.session_state["messages"]
    messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.status(t("thinking"), expanded=False) as status:
            reply = _run_pipeline(prompt, status)
            succeeded = bool(
                reply["result"] and reply["result"]["success"]
            )
            status.update(
                label=t("success") if succeeded else t("failed"),
                state="complete" if succeeded else "error",
            )
        messages.append(reply)
        _render_assistant(reply, len(messages) - 1)


# ============================================================
# نقطة الدخول
# ============================================================
def render_chat() -> None:
    """
    يرسم واجهة المحادثة.
    - لو لا يوجد df → رسالة توضيحية.
    - لو يوجد df → عرض الرسائل + صندوق الإدخال.
    """
    # فحص وجود DataFrame (باستخدام المفتاح السريع df_loaded)
    df_loaded = st.session_state.get("df_loaded", False)
    df = st.session_state.get("df")

    if not df_loaded or df is None:
        st.info(t("no_file"))
        return

    # عرض ملخص الملف
    name = st.session_state.get("dataset_name") or "?"
    try:
        rows, cols = df.shape
        st.caption(f"📊 `{name}` — {rows} × {cols}")
    except Exception:
        pass

    # عرض الرسائل السابقة
    for idx, msg in enumerate(st.session_state["messages"]):
        _render_message(msg, idx)

    # صندوق الإدخال
    prompt = st.chat_input(t("ask_placeholder"), key="chat_input_main")
    if prompt:
        _handle_prompt(prompt)