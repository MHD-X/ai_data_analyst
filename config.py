"""
config.py — الإعدادات المركزية للمشروع
Central configuration for the AI Data Analyst platform.
"""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# تحميل متغيرات البيئة من .env (محلياً)
load_dotenv()


def get_setting(name: str, default: str = "") -> str:
    """يقرأ من Streamlit Secrets أولاً (السحابة) ثم من .env / البيئة (محلياً)."""
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


# ============ المسارات الأساسية ============
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
REPORTS_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "memory.db"

# إنشاء المجلدات إن لم تكن موجودة
for _p in (DATA_DIR, UPLOADS_DIR, REPORTS_DIR):
    _p.mkdir(parents=True, exist_ok=True)


# ============ إعدادات LLM ============
@dataclass
class LLMConfig:
    provider: str = get_setting("LLM_PROVIDER", "reka")
    api_key: str = get_setting("LLM_API_KEY", "")
    base_url: str = get_setting("LLM_BASE_URL", "https://api.reka.ai/v1")
    model: str = get_setting("LLM_MODEL", "reka-flash")
    temperature: float = float(get_setting("LLM_TEMPERATURE", "0.2"))
    max_tokens: int = int(get_setting("LLM_MAX_TOKENS", "4096"))
    timeout: int = int(get_setting("LLM_TIMEOUT", "20"))


# ============ إعدادات Sandbox ============
@dataclass
class SandboxConfig:
    timeout_seconds: int = 30
    max_memory_mb: int = 1024
    allowed_modules: tuple = (
        "pandas", "numpy", "plotly", "sklearn",
        "scipy", "statsmodels", "math", "statistics",
        "datetime", "json", "re", "collections",
        "itertools", "functools", "warnings", "random",
    )
    forbidden_builtins: tuple = (
        "open", "exec", "eval", "compile", "__import__",
        "input", "breakpoint", "globals", "locals",
        "vars", "dir", "getattr", "setattr", "delattr",
    )


# ============ إعدادات الذاكرة ============
@dataclass
class MemoryConfig:
    db_path: Path = DB_PATH
    max_few_shot_examples: int = 3
    similarity_threshold: float = 0.5


# ============ إعدادات الواجهة ============
@dataclass
class UIConfig:
    page_title: str = "Between Data"
    page_icon: str = "🧠"
    layout: str = "wide"
    default_language: str = "ar"   # ar | en


# ============ تجميع الإعدادات ============
@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    ui: UIConfig = field(default_factory=UIConfig)


CONFIG = AppConfig()


# ============ تحقق سريع ============
def validate_config() -> tuple[bool, list[str]]:
    """يتحقق من صحة الإعدادات، يعيد (is_valid, errors)."""
    errors: list[str] = []
    if not CONFIG.llm.api_key:
        errors.append("❌ LLM_API_KEY غير موجود (في .env محلياً أو في Streamlit Secrets على السحابة)")
    if not CONFIG.llm.base_url.startswith("http"):
        errors.append("❌ LLM_BASE_URL غير صالح")
    if CONFIG.llm.provider not in ("reka", "deepseek", "glm", "groq", "custom"):
        errors.append(f"⚠️ LLM_PROVIDER غير معروف: {CONFIG.llm.provider}")
    return (len(errors) == 0, errors)


if __name__ == "__main__":
    ok, errs = validate_config()
    print("✅ الإعدادات صحيحة" if ok else "\n".join(errs))
    print(f"Provider: {CONFIG.llm.provider}")
    print(f"Model:    {CONFIG.llm.model}")
    print(f"Base URL: {CONFIG.llm.base_url}")
    print(f"DB Path:  {CONFIG.memory.db_path}")
