from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from config import get_setting

logger = logging.getLogger(__name__)


def _smtp_config() -> dict[str, Any]:
    host = (get_setting("SMTP_HOST", "") or "").strip()
    port = int(get_setting("SMTP_PORT", "587") or 587)
    user = (get_setting("SMTP_USER", "") or "").strip()
    password = (get_setting("SMTP_PASSWORD", "") or "").strip()
    sender = (get_setting("SMTP_FROM", "") or "").strip()
    security = (get_setting("SMTP_SECURITY", "starttls") or "starttls").strip().lower()
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "sender": sender,
        "security": security if security in {"starttls", "ssl"} else "starttls",
    }


def build_email_html(subject: str, body: str) -> str:
    safe_subject = subject.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
    <html dir="rtl" lang="ar">
      <body style="font-family:Tahoma,Arial,sans-serif; direction:rtl; text-align:right; padding:24px; color:#111;">
        <div style="max-width:520px; margin:0 auto; border:1px solid #ddd; border-radius:12px; padding:24px; background:#fafafa;">
          <h2 style="margin-top:0;">{safe_subject}</h2>
          <p style="line-height:1.7; white-space:pre-wrap;">{safe_body}</p>
        </div>
      </body>
    </html>
    """


def send_email(subject: str, to_email: str, body: str, *, html_body: str | None = None) -> dict[str, Any]:
    cfg = _smtp_config()
    if not cfg["host"] or not cfg["sender"]:
        return {"ok": False, "error": "SMTP is not configured."}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = cfg["sender"]
    message["To"] = to_email
    message.set_content(body, subtype="plain", charset="utf-8")
    if html_body is None:
        html_body = build_email_html(subject, body)
    message.add_alternative(html_body, subtype="html")

    try:
        if cfg["security"] == "ssl":
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15) as smtp:
                if cfg["user"]:
                    smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(message)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
                smtp.starttls()
                if cfg["user"]:
                    smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(message)
        return {"ok": True, "error": ""}
    except Exception as exc:  # pragma: no cover - depends on SMTP runtime
        logger.warning("SMTP send failed: %s", type(exc).__name__)
        return {"ok": False, "error": f"SMTP send failed: {type(exc).__name__}"}


def send_code_email(to_email: str, purpose: str, code: str) -> dict[str, Any]:
    label = "تفعيل الحساب" if purpose == "verify" else "إعادة تعيين كلمة المرور"
    subject = f"{label} | Between Data"
    body = (
        f"رمز التحقق الخاص بك هو: {code}\n\n"
        "يُسمح به لمدة 10 دقائق فقط. إذا لم تكن أنت من طلب هذا الرمز، تجاهل هذه الرسالة."
    )
    html_body = build_email_html(subject, body)
    return send_email(subject, to_email, body, html_body=html_body)


def send_already_registered_email(to_email: str) -> dict[str, Any]:
    subject = "Between Data | لديك حساب بالفعل"
    body = (
        "لقد قمت بالتسجيل سابقاً. إذا كنت تريد إعادة تعيين كلمة المرور، استخدم خيار استعادة كلمة المرور."
    )
    return send_email(subject, to_email, body, html_body=build_email_html(subject, body))


def send_reset_link_email(to_email: str, code: str) -> dict[str, Any]:
    return send_code_email(to_email, "reset", code)


__all__ = [
    "build_email_html",
    "send_already_registered_email",
    "send_code_email",
    "send_email",
    "send_reset_link_email",
]
