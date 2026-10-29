"""
utils/i18n.py — الترجمات ودعم الاتجاه (RTL/LTR)
Translations and RTL/LTR support for the Streamlit UI.

الاستخدام:
    from utils.i18n import t, get_lang, rtl_css
    st.title(t("app_title"))
    st.write(t("rows_cols", rows=100, cols=5))
"""
from __future__ import annotations

from typing import Any

DEFAULT_LANG = "ar"
SUPPORTED_LANGS: dict[str, str] = {"ar": "العربية", "en": "English"}
RTL_LANGS = {"ar"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ar": {
        # --- عام ---
        "app_title": "محلل البيانات الذكي",
        "app_subtitle": "ارفع ملفك، اكتب طلبك، ودع الذكاء الاصطناعي يحلّل بياناتك.",
        "tab_chat": "💬 المحادثة",
        "tab_dashboard": "📊 لوحة المعلومات",
        "under_construction": "🚧 الوحدة `{module}` (الدالة `{func}`) قيد التطوير.",
        "module_load_error": "❌ تعذّر تحميل الوحدة `{module}`.",
        "db_error": "❌ تعذّر الاتصال بقاعدة بيانات الذاكرة.",
        # --- الشريط الجانبي ---
        "sidebar_title": "⚙️ لوحة التحكم",
        "language": "اللغة",
        "upload_file": "ارفع ملف بيانات",
        "upload_help": "الصيغ المدعومة: CSV, XLSX, XLS",
        "file_loaded": "✅ تم تحميل الملف: {name}",
        "file_error": "❌ تعذّرت قراءة الملف: {error}",
        "file_already_known": "ℹ️ هذا الملف رُفع سابقاً، وتم استرجاع سجلّه.",
        "no_file": "لم يتم رفع ملف بعد. ارفع ملفاً من الشريط الجانبي للبدء.",
        "rows_cols": "{rows} صف × {cols} عمود",
        "preview": "معاينة البيانات",
        "columns": "الأعمدة",
        # --- معلومات الملف (جديد) ---
        "rows_label": "صفوف",
        "cols_label": "أعمدة",
        "remove_file": "🗑️ حذف الملف",
        # --- تأكيدات (جديد) ---
        "delete_confirm": "⚠️ هل أنت متأكد؟ لا يمكن التراجع.",
        "confirm_delete": "نعم، احذف",
        # --- الجلسات ---
        "sessions": "الجلسات",
        "new_session": "➕ جلسة جديدة",
        "session_name": "اسم الجلسة",
        "default_session_name": "جلسة {ts}",
        "current_session": "الجلسة الحالية",
        "delete_session": "🗑️ حذف الجلسة",
        "clear_chat": "🧹 مسح المحادثة",
        # --- المحادثة ---
        "ask_placeholder": "اكتب طلبك هنا... مثال: لخّص المبيعات حسب الشهر",
        "thinking": "🤔 جاري التفكير...",
        "generating_code": "✍️ جاري توليد الكود...",
        "executing": "⚙️ جاري تنفيذ الكود...",
        "success": "✅ تم التنفيذ بنجاح",
        "failed": "❌ فشل التنفيذ",
        "show_code": "عرض الكود",
        "explanation": "الشرح",
        "results": "النتائج",
        "output": "المخرجات",
        "figures": "الرسوم البيانية",
        "execution_time": "زمن التنفيذ: {seconds}",
        "no_code_returned": "لم يُرجع النموذج أي كود قابل للتنفيذ.",
        "variables_title": "المتغيّرات الناتجة",
        "head_note": "عرض أول {shown} من {total}",
        "figure_error": "⚠️ تعذّر عرض أحد الرسوم.",
        "no_visible_output": "نُفّذ الكود بنجاح لكن لا توجد مخرجات ظاهرة (استخدم print أو أنشئ متغيّراً/رسماً).",
        "unsafe_code": "⚠️ تم رفض الكود لأسباب أمنية: {reason}",
        "llm_auth_error": "🔑 مفتاح API غير صالح. تحقق من ملف .env",
        "llm_rate_limit": "⏳ تم تجاوز حد الطلبات. حاول بعد قليل.",
        "llm_timeout": "⌛ انتهت مهلة الاتصال بالنموذج.",
        "llm_error": "❌ خطأ في الاتصال بالنموذج: {error}",
        "rate_this": "قيّم هذه النتيجة",
        "helpful": "👍 مفيدة",
        "not_helpful": "👎 غير مفيدة",
        "thanks_feedback": "شكراً على تقييمك!",
        # --- لوحة المعلومات ---
        "dash_title": "📊 إحصائيات المشروع",
        "total_operations": "إجمالي العمليات",
        "success_rate": "نسبة النجاح",
        "total_datasets": "الملفات المرفوعة",
        "total_sessions": "الجلسات",
        "recent_operations": "آخر العمليات",
        "top_requests": "أكثر الطلبات تكراراً",
        "no_operations": "لا توجد عمليات مسجّلة بعد.",
        "auth.email": "البريد الإلكتروني",
        "auth.password": "كلمة المرور",
        "auth.display_name": "اسم العرض",
        "auth.login": "تسجيل الدخول",
        "auth.register": "إنشاء حساب",
        "auth.verify": "تفعيل الحساب",
        "auth.reset_password": "استعادة كلمة المرور",
        "auth.request_reset": "طلب استعادة",
        "auth.change_password": "تغيير كلمة المرور",
        "auth.current_password": "كلمة المرور الحالية",
        "auth.new_password": "كلمة المرور الجديدة",
        "auth.verification_code": "رمز التفعيل",
        "auth.auth_intro": "أنشئ حسابك أو سجل الدخول للمتابعة.",
        "auth.invalid_email": "البريد الإلكتروني غير صالح.",
        "auth.invalid_credentials": "بيانات الدخول غير صحيحة.",
        "auth.email_unverified": "الحساب غير مفعّل. يرجى تفعيل البريد الإلكتروني أولاً.",
        "auth.account_locked": "الحساب مُغلق مؤقتاً بسبب محاولات فاشلة. حاول مرة أخرى لاحقاً.",
        "auth.invalid_code": "رمز التفعيل غير صالح أو منتهي الصلاحية.",
        "auth.check_email": "إذا كان البريد صحيحاً، راجع بريدك الإلكتروني.",
        "auth.signup_closed": "التسجيل مغلق حالياً بالدعوة فقط.",
        "auth.password_policy": "كلمة المرور يجب أن تكون 10 أحرف على الأقل، ولا تساوي أو تحتوي على جزء البريد الإلكتروني.",
        "auth.registration_success": "تم إنشاء الحساب بنجاح. تحقق من بريدك الإلكتروني.",
        "auth.email_verified": "تم تفعيل الحساب بنجاح.",
        "auth.login_success": "تم تسجيل الدخول بنجاح.",
        "auth.password_reset": "تمت إعادة تعيين كلمة المرور.",
        "auth.password_changed": "تم تغيير كلمة المرور بنجاح.",
        "auth.code_sent": "تم إرسال الرمز بنجاح.",
        "auth.cooldown": "انتظر قليلاً قبل طلب رمز جديد.",
        "auth.resend_code": "إعادة إرسال الرمز",
        "auth.resend_hint": "إذا لم تستلم الرمز، يمكنك إعادة إرساله من علامة التفعيل.",
        "auth.logout": "تسجيل الخروج",
        "auth.admin_bootstrap_missing": "ADMIN_EMAIL / ADMIN_PASSWORD غير مُعدّتين.",
        "auth.admin_bootstrap_failed": "فشل إنشاء المسؤول: {reason}",
        "auth.admin_bootstrap_failed_password_policy": "فشل إنشاء المسؤول: كلمة المرور لا تفي بالسياسة (10 أحرف على الأقل، ويجب ألا تحتوي على اسم البريد الإلكتروني).",
        "auth.admin_bootstrap_failed_invalid_email": "فشل إنشاء المسؤول: تنسيق البريد الإلكتروني غير صالح.",
        "auth.admin_bootstrap_failed_db_error": "فشل إنشاء المسؤول: خطأ في قاعدة البيانات.",
    },
    "en": {
        # --- General ---
        "app_title": "AI Data Analyst",
        "app_subtitle": "Upload your file, type your request, and let AI analyze your data.",
        "tab_chat": "💬 Chat",
        "tab_dashboard": "📊 Dashboard",
        "under_construction": "🚧 Module `{module}` (function `{func}`) is under construction.",
        "module_load_error": "❌ Failed to load module `{module}`.",
        "db_error": "❌ Could not connect to the memory database.",
        # --- Sidebar ---
        "sidebar_title": "⚙️ Control Panel",
        "language": "Language",
        "upload_file": "Upload a data file",
        "upload_help": "Supported formats: CSV, XLSX, XLS",
        "file_loaded": "✅ File loaded: {name}",
        "file_error": "❌ Could not read the file: {error}",
        "file_already_known": "ℹ️ This file was uploaded before; its history was restored.",
        "no_file": "No file uploaded yet. Upload one from the sidebar to begin.",
        "rows_cols": "{rows} rows × {cols} columns",
        "preview": "Data preview",
        "columns": "Columns",
        # --- File info (new) ---
        "rows_label": "Rows",
        "cols_label": "Columns",
        "remove_file": "🗑️ Remove file",
        # --- Confirmations (new) ---
        "delete_confirm": "⚠️ Are you sure? This cannot be undone.",
        "confirm_delete": "Yes, delete",
        # --- Sessions ---
        "sessions": "Sessions",
        "new_session": "➕ New session",
        "session_name": "Session name",
        "default_session_name": "Session {ts}",
        "current_session": "Current session",
        "delete_session": "🗑️ Delete session",
        "clear_chat": "🧹 Clear chat",
        # --- Chat ---
        "ask_placeholder": "Type your request... e.g. summarize sales by month",
        "thinking": "🤔 Thinking...",
        "generating_code": "✍️ Generating code...",
        "executing": "⚙️ Running code...",
        "success": "✅ Executed successfully",
        "failed": "❌ Execution failed",
        "show_code": "Show code",
        "explanation": "Explanation",
        "results": "Results",
        "output": "Output",
        "figures": "Charts",
        "execution_time": "Execution time: {seconds}",
        "no_code_returned": "The model did not return any executable code.",
        "variables_title": "Resulting variables",
        "head_note": "Showing first {shown} of {total}",
        "figure_error": "⚠️ Could not display one of the charts.",
        "no_visible_output": "Code ran successfully but produced no visible output (use print, or create a variable/chart).",
        "unsafe_code": "⚠️ Code rejected for safety reasons: {reason}",
        "llm_auth_error": "🔑 Invalid API key. Check your .env file.",
        "llm_rate_limit": "⏳ Rate limit exceeded. Try again shortly.",
        "llm_timeout": "⌛ The model request timed out.",
        "llm_error": "❌ Model connection error: {error}",
        "rate_this": "Rate this result",
        "helpful": "👍 Helpful",
        "not_helpful": "👎 Not helpful",
        "thanks_feedback": "Thanks for your feedback!",
        # --- Dashboard ---
        "dash_title": "📊 Project statistics",
        "total_operations": "Total operations",
        "success_rate": "Success rate",
        "total_datasets": "Uploaded files",
        "total_sessions": "Sessions",
        "recent_operations": "Recent operations",
        "top_requests": "Most frequent requests",
        "no_operations": "No operations recorded yet.",
        "auth.email": "Email",
        "auth.password": "Password",
        "auth.display_name": "Display name",
        "auth.login": "Log in",
        "auth.register": "Register",
        "auth.verify": "Verify account",
        "auth.reset_password": "Reset password",
        "auth.request_reset": "Request reset",
        "auth.change_password": "Change password",
        "auth.current_password": "Current password",
        "auth.new_password": "New password",
        "auth.verification_code": "Verification code",
        "auth.auth_intro": "Create your account or sign in to continue.",
        "auth.invalid_email": "The email address is invalid.",
        "auth.invalid_credentials": "Invalid credentials.",
        "auth.email_unverified": "This account is not verified yet. Please verify your email first.",
        "auth.account_locked": "This account is temporarily locked due to repeated failed attempts. Try again later.",
        "auth.invalid_code": "The verification code is invalid or expired.",
        "auth.check_email": "If the information is valid, check your email.",
        "auth.signup_closed": "Registration is currently by invitation only.",
        "auth.password_policy": "Password must be at least 10 characters and must not equal or contain the email local part.",
        "auth.registration_success": "Account created successfully. Check your email.",
        "auth.email_verified": "Account verified successfully.",
        "auth.login_success": "Logged in successfully.",
        "auth.password_reset": "Password reset successfully.",
        "auth.password_changed": "Password changed successfully.",
        "auth.code_sent": "Code sent successfully.",
        "auth.cooldown": "Please wait a moment before requesting a new code.",
        "auth.resend_code": "Resend code",
        "auth.resend_hint": "If you did not receive the code, you can resend it from the verification step.",
        "auth.logout": "Log out",
        "auth.admin_bootstrap_missing": "ADMIN_EMAIL / ADMIN_PASSWORD are not configured.",
        "auth.admin_bootstrap_failed": "Admin bootstrap failed: {reason}",
        "auth.admin_bootstrap_failed_password_policy": "Admin bootstrap failed: password does not meet policy (min 10 chars, must not contain the email name)",
        "auth.admin_bootstrap_failed_invalid_email": "Admin bootstrap failed: email format is invalid.",
        "auth.admin_bootstrap_failed_db_error": "Admin bootstrap failed: database error.",
    },
}


# ============ اللغة الحالية ============
def get_lang() -> str:
    """يعيد اللغة الحالية من session_state، أو الافتراضية من CONFIG."""
    lang = None
    try:
        import streamlit as st

        lang = st.session_state.get("lang")
    except Exception:
        pass
    if lang in SUPPORTED_LANGS:
        return lang  # type: ignore[return-value]
    try:
        from config import CONFIG

        if CONFIG.ui.default_language in SUPPORTED_LANGS:
            return CONFIG.ui.default_language
    except Exception:
        pass
    return DEFAULT_LANG


def is_rtl(lang: str | None = None) -> bool:
    return (lang or get_lang()) in RTL_LANGS


def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """يترجم المفتاح. إن لم يوجد يرجع للإنجليزية ثم للمفتاح نفسه."""
    lang = lang or get_lang()
    text = TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["en"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


# ============ CSS للاتجاه ============
_FONT = "'Cairo', 'Segoe UI', Tahoma, sans-serif"

_RTL_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
.stApp {{ font-family: {_FONT}; }}
.stApp, [data-testid="stSidebar"], [data-testid="stChatMessage"],
[data-testid="stMarkdownContainer"], [data-testid="stAlert"],
[data-testid="stExpander"], [data-testid="stFileUploader"],
[data-testid="stMetric"] {{ direction: rtl; text-align: right; }}
[data-testid="stChatInput"] textarea {{ direction: rtl; text-align: right; }}
[data-baseweb="tab-list"] {{ direction: rtl; }}
/* الكود والجداول والرسوم تبقى LTR */
pre, code, [data-testid="stCode"], [data-testid="stDataFrame"],
[data-testid="stTable"], .js-plotly-plot {{ direction: ltr !important; text-align: left !important; }}
"""

_LTR_CSS = f"""
.stApp {{ font-family: {_FONT}; }}
"""


def rtl_css(lang: str | None = None) -> str:
    """يعيد وسم <style> مناسباً للغة الحالية."""
    css = _RTL_CSS if is_rtl(lang) else _LTR_CSS
    return f"<style>{css}</style>"