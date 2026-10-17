"""
core/llm_client.py — عميل الذكاء الاصطناعي الموحّد
Unified LLM client supporting Reka, DeepSeek, GLM, and custom OpenAI-compatible endpoints.
"""
from __future__ import annotations

import json
import time
import logging
from typing import Any, Iterator

import requests

from config import CONFIG

logger = logging.getLogger(__name__)


# ============================================================
# استثناءات مخصصة
# ============================================================
class LLMError(Exception):
    """خطأ عام في عميل LLM."""


class LLMAuthError(LLMError):
    """مفتاح API غير صالح."""


class LLMRateLimitError(LLMError):
    """تجاوز حد الطلبات."""


class LLMTimeoutError(LLMError):
    """انتهت المهلة."""


# ============================================================
# الفئة الرئيسية
# ============================================================
class LLMClient:
    """
    عميل موحّد للتواصل مع أي LLM يدعم OpenAI-compatible API.
    يدعم: Reka, DeepSeek, GLM, وأي endpoint مخصص.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key or CONFIG.llm.api_key
        self.base_url = (base_url or CONFIG.llm.base_url).rstrip("/")
        self.model = model or CONFIG.llm.model
        self.temperature = (
            temperature if temperature is not None else CONFIG.llm.temperature
        )
        self.max_tokens = max_tokens or CONFIG.llm.max_tokens
        self.timeout = timeout or CONFIG.llm.timeout

        if not self.api_key:
            raise LLMAuthError("❌ LLM_API_KEY غير موجود. تحقق من ملف .env")

    # --------------------------------------------------------
    # بناء الترويسات
    # --------------------------------------------------------
    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # --------------------------------------------------------
    # بناء جسم الطلب
    # --------------------------------------------------------
    def _build_payload(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        **overrides: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        payload.update(overrides)
        return payload

    # --------------------------------------------------------
    # نقطة النهاية
    # --------------------------------------------------------
    def _chat_endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    # --------------------------------------------------------
    # معالجة الأخطاء
    # --------------------------------------------------------
    def _handle_response_error(self, resp: requests.Response) -> None:
        status = resp.status_code
        try:
            body = resp.json()
            detail = (
                body.get("error", {}).get("message")
                or body.get("message")
                or str(body)
            )
        except Exception:
            detail = resp.text[:500]

        if status == 401:
            raise LLMAuthError(f"❌ مفتاح API غير صالح (401): {detail}")
        if status == 429:
            raise LLMRateLimitError(f"⚠️ تجاوزت حد الطلبات (429): {detail}")
        if status >= 500:
            raise LLMError(f"❌ خطأ في الخادم ({status}): {detail}")
        raise LLMError(f"❌ فشل الطلب ({status}): {detail}")

    # --------------------------------------------------------
    # الطلب الرئيسي (non-stream)
    # --------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, str]],
        retries: int = 2,
        **overrides: Any,
    ) -> str:
        """
        يرسل طلب دردشة ويعيد نص الرد الكامل.
        """
        payload = self._build_payload(messages, stream=False, **overrides)
        headers = self._build_headers()

        last_error: Exception | None = None
        for attempt in range(1, retries + 2):
            try:
                resp = requests.post(
                    self._chat_endpoint(),
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    self._handle_response_error(resp)

                data = resp.json()
                return self._extract_content(data)

            except (LLMAuthError, LLMRateLimitError):
                raise
            except requests.Timeout as e:
                last_error = e
                logger.warning(
                    "⏱️ مهلة الطلب (محاولة %d/%d)", attempt, retries + 1
                )
            except requests.RequestException as e:
                last_error = e
                logger.warning(
                    "🌐 خطأ شبكة (محاولة %d/%d): %s", attempt, retries + 1, e
                )
            except LLMError as e:
                last_error = e
                logger.warning(
                    "⚠️ خطأ LLM (محاولة %d/%d): %s", attempt, retries + 1, e
                )

            if attempt <= retries:
                time.sleep(1.5 * attempt)

        raise LLMError(f"❌ فشل الطلب بعد {retries + 1} محاولات: {last_error}")

# ============ نهاية الجزء 1/2 — أكمل بالجزء التالي ============
  # --------------------------------------------------------
    # الطلب المتدفق (stream)
    # --------------------------------------------------------
    def stream_chat(
        self,
        messages: list[dict[str, str]],
        **overrides: Any,
    ) -> Iterator[str]:
        """
        يرسل طلب دردشة ويعيد الرد كتدفق chunks.
        """
        payload = self._build_payload(messages, stream=True, **overrides)
        headers = self._build_headers()

        try:
            with requests.post(
                self._chat_endpoint(),
                headers=headers,
                json=payload,
                timeout=self.timeout,
                stream=True,
            ) as resp:
                if resp.status_code != 200:
                    self._handle_response_error(resp)

                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        yield delta

        except requests.Timeout as e:
            raise LLMTimeoutError(f"⏱️ انتهت المهلة: {e}") from e
        except requests.RequestException as e:
            raise LLMError(f"🌐 خطأ شبكة: {e}") from e

    # --------------------------------------------------------
    # استخراج المحتوى من استجابة OpenAI-compatible
    # --------------------------------------------------------
    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, list):
                # بعض المزودين يعيدون قائمة أجزاء
                return "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return content or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"❌ استجابة غير متوقعة من LLM: {data}") from e

    # --------------------------------------------------------
    # اختبار الاتصال
    # --------------------------------------------------------
    def test_connection(self) -> tuple[bool, str]:
        """
        اختبار سريع للاتصال بالمزود.
        يعيد (نجاح؟, رسالة).
        """
        try:
            reply = self.chat(
                [{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=10,
                temperature=0.0,
            )
            return True, f"✅ الاتصال ناجح — رد الموديل: {reply.strip()[:50]}"
        except LLMAuthError as e:
            return False, f"❌ مشكلة في المفتاح: {e}"
        except LLMRateLimitError as e:
            return False, f"⚠️ تجاوزت الحد: {e}"
        except LLMTimeoutError as e:
            return False, f"⏱️ انتهت المهلة: {e}"
        except LLMError as e:
            return False, f"❌ خطأ: {e}"
        except Exception as e:
            return False, f"❌ خطأ غير متوقع: {e}"


# ============================================================
# نسخة عامة جاهزة (Singleton)
# ============================================================
_default_client: LLMClient | None = None


def get_client() -> LLMClient:
    """يعيد نسخة واحدة مشتركة من العميل (Lazy Singleton)."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def reset_client() -> None:
    """يعيد تعيين العميل (مفيد عند تغيير الإعدادات)."""
    global _default_client
    _default_client = None


# ============================================================
# اختبار مباشر عند تشغيل الملف
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print("=" * 60)
    print("🧪 اختبار عميل LLM")
    print("=" * 60)
    print(f"Provider : {CONFIG.llm.provider}")
    print(f"Model    : {CONFIG.llm.model}")
    print(f"Base URL : {CONFIG.llm.base_url}")
    print("-" * 60)

    try:
        client = LLMClient()
        ok, message = client.test_connection()
        print(message)

        if ok:
            print("-" * 60)
            print("🧠 اختبار رد عربي:")
            reply = client.chat(
                [
                    {
                        "role": "system",
                        "content": "أنت مساعد ذكي مختصر جداً.",
                    },
                    {
                        "role": "user",
                        "content": "قل لي جملة واحدة فقط: ما هو تحليل البيانات؟",
                    },
                ],
                max_tokens=100,
            )
            print(reply)

    except LLMAuthError as e:
        print(f"❌ فشل التهيئة: {e}")
        print("💡 تأكد من ملف .env وأن LLM_API_KEY صحيح")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")