from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from config import CONFIG, get_setting
from core.db import (  # noqa: F401
    DBConnection,
    connect_database,
    execute_sql_script,
    get_database_backend,
    get_database_url,
    get_schema_sql,
    normalize_database_url,
)
from core.email_sender import send_already_registered_email, send_code_email
from utils.helpers import now_iso

logger = logging.getLogger(__name__)


def _strip_wrapping_quotes(value: str) -> str:
    value = (value or "").strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _is_valid_email(email: str) -> bool:
    if not email:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _auth_secret() -> str:
    secret = (get_setting("AUTH_SECRET", "") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("AUTH_SECRET is missing or shorter than 32 characters.")
    return secret


def _hash_code(code: str) -> str:
    return hmac.new(_auth_secret().encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_code_hash(code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(_hash_code(code), stored_hash)


def _password_hasher() -> PasswordHasher:
    return PasswordHasher()


def _hash_password(password: str) -> str:
    return _password_hasher().hash(password)


def _verify_password(stored_hash: str, password: str) -> bool:
    try:
        return bool(_password_hasher().verify(stored_hash, password))
    except VerifyMismatchError:
        return False
    except Exception:
        return False


@dataclass
class AuthResult:
    ok: bool
    message_key: str
    user: dict[str, Any] | None = None
    code: str | None = None


class AuthStore:
    def __init__(self, db_path: str | Path | None = None, database_url: str | None = None) -> None:
        if db_path is not None and database_url is None:
            self.database_url = ""
            self.backend = "sqlite"
        else:
            configured = getattr(CONFIG.memory, "database_url", "") or ""
            self.database_url = normalize_database_url(database_url or configured or get_database_url() or "")
            self.backend = get_database_backend(self.database_url)
        self.db_path = Path(db_path or CONFIG.memory.db_path)
        if self.backend == "sqlite":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        if self.backend == "postgresql":
            return connect_database(database_url=self.database_url)
        return connect_database(db_path=self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            execute_sql_script(conn, get_schema_sql(self.backend))
            conn.commit()

    @staticmethod
    def _user_payload(user_row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user_row.get("id"),
            "email": user_row.get("email"),
            "display_name": user_row.get("display_name"),
            "role": user_row.get("role", "user"),
            "is_active": int(user_row.get("is_active", 1)),
            "email_verified": int(user_row.get("email_verified", 0)),
            "must_change_password": int(user_row.get("must_change_password", 0)),
        }

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        email = _normalize_email(email)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1",
                (email,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def _latest_code_record(self, email: str, purpose: str) -> dict[str, Any] | None:
        user = self.get_user_by_email(email)
        if user is None:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM email_codes WHERE user_id = ? AND purpose = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (user["id"], purpose),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def _cooldown_remaining(self, email: str, purpose: str) -> int:
        row = self._latest_code_record(email, purpose)
        if row is None:
            return 0
        created_at = row.get("created_at")
        if not created_at:
            return 0
        created_dt = datetime.fromisoformat(created_at)
        elapsed = (datetime.utcnow() - created_dt).total_seconds()
        return max(0, 60 - int(elapsed))

    def _issue_code_for_user(self, email: str, purpose: str) -> str:
        user = self.get_user_by_email(email)
        if user is None:
            raise ValueError("User does not exist.")
        with self._connect() as conn:
            conn.execute(
                "UPDATE email_codes SET used = 1 WHERE user_id = ? AND purpose = ? AND used = 0",
                (user["id"], purpose),
            )
            code = str(secrets.randbelow(1_000_000)).zfill(6)
            code_hash = _hash_code(code)
            expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
            conn.insert(
                "INSERT INTO email_codes (user_id, purpose, code_hash, expires_at, attempts, used, created_at) VALUES (?, ?, ?, ?, 0, 0, ?)",
                (user["id"], purpose, code_hash, expires_at, now_iso()),
            )
            conn.commit()
        return code

    def _code_is_valid(self, email: str, code: str, purpose: str) -> bool:
        row = self._latest_code_record(email, purpose)
        if row is None:
            return False
        if int(row.get("used", 0)) == 1:
            return False
        if int(row.get("attempts", 0)) >= 5:
            return False
        expires_at = row.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
            return False
        return _verify_code_hash(code, row["code_hash"])

    def _consume_code_attempt(self, email: str, code: str, purpose: str) -> bool:
        row = self._latest_code_record(email, purpose)
        if row is None:
            return False
        attempts = int(row.get("attempts", 0)) + 1
        with self._connect() as conn:
            conn.execute(
                "UPDATE email_codes SET attempts = ? WHERE id = ?",
                (attempts, row["id"]),
            )
            conn.commit()
        return _verify_code_hash(code, row["code_hash"]) and attempts < 5

    def bootstrap_admin(self) -> dict[str, Any] | str | None:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
        if int(count) > 0:
            return None

        admin_email = _normalize_email(_strip_wrapping_quotes((get_setting("ADMIN_EMAIL", "") or "")))
        admin_password = _strip_wrapping_quotes((get_setting("ADMIN_PASSWORD", "") or ""))
        if not admin_email or not admin_password:
            logger.warning("Admin bootstrap skipped: ADMIN_EMAIL / ADMIN_PASSWORD are not configured")
            return "not_configured"

        if not _is_valid_email(admin_email):
            logger.warning("Admin bootstrap failed: invalid email format")
            return "invalid_email"

        local_part = admin_email.split("@", 1)[0].lower()
        if not admin_password or len(admin_password) < 10 or admin_password.lower() == local_part or local_part in admin_password.lower():
            logger.warning(
                "Admin bootstrap failed: password does not meet policy (min 10 chars, must not contain the email name)"
            )
            return "password_policy"

        try:
            with self._connect() as conn:
                user_id = conn.insert(
                    "INSERT INTO users (email, password_hash, display_name, role, is_active, email_verified, must_change_password, failed_attempts, locked_until, created_at, last_login_at) VALUES (?, ?, ?, 'admin', 1, 1, 1, 0, NULL, ?, NULL)",
                    (admin_email, _hash_password(admin_password), "Admin", now_iso()),
                )
                conn.commit()
        except Exception:
            logger.warning("Admin bootstrap failed: database error while creating admin user", exc_info=True)
            return "db_error"

        return self.get_user_by_id(user_id)

    def register(self, email: str, password: str, display_name: str) -> AuthResult:
        email = _normalize_email(email)
        if not _is_valid_email(email):
            return AuthResult(False, "auth.invalid_email")
        if get_setting("SIGNUP_OPEN", "0") != "1":
            return AuthResult(False, "auth.signup_closed")
        if not password or len(password) < 10:
            return AuthResult(False, "auth.password_policy")
        local_part = email.split("@", 1)[0]
        if password == email or password.lower() == local_part.lower() or local_part.lower() in password.lower():
            return AuthResult(False, "auth.password_policy")
        if self.get_user_by_email(email):
            try:
                send_already_registered_email(email)
            except Exception:
                pass
            return AuthResult(False, "auth.check_email")

        password_hash = _hash_password(password)
        with self._connect() as conn:
            user_id = conn.insert(
                "INSERT INTO users (email, password_hash, display_name, role, is_active, email_verified, must_change_password, failed_attempts, locked_until, created_at, last_login_at) VALUES (?, ?, ?, 'user', 1, 0, 0, 0, NULL, ?, NULL)",
                (email, password_hash, (display_name or "User").strip() or "User", now_iso()),
            )
            conn.commit()
        code = self._issue_code_for_user(email, "verify")
        try:
            send_code_email(email, "verify", code)
        except Exception:
            pass
        user = self.get_user_by_id(user_id)
        return AuthResult(True, "auth.registration_success", self._user_payload(user or {}), code=code)

    def verify_email(self, email: str, code: str) -> AuthResult:
        email = _normalize_email(email)
        user = self.get_user_by_email(email)
        if user is None:
            return AuthResult(False, "auth.invalid_credentials")
        if not self._code_is_valid(email, code, "verify"):
            self._consume_code_attempt(email, code, "verify")
            return AuthResult(False, "auth.invalid_code")
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET email_verified = 1 WHERE id = ?",
                (user["id"],),
            )
            conn.execute(
                "UPDATE email_codes SET used = 1 WHERE user_id = ? AND purpose = 'verify'",
                (user["id"],),
            )
            conn.commit()
        refreshed = self.get_user_by_id(user["id"])
        return AuthResult(True, "auth.email_verified", self._user_payload(refreshed or user))

    def login(self, email: str, password: str) -> AuthResult:
        email = _normalize_email(email)
        user = self.get_user_by_email(email)
        if user is None:
            # Same generic message and similar time to wrong-password path.
            _ = _hash_password("dummy-password-should-never-match")
            _verify_password(_hash_password("dummy-password-should-never-match"), password)
            return AuthResult(False, "auth.invalid_credentials")

        if int(user.get("is_active", 1)) != 1:
            return AuthResult(False, "auth.invalid_credentials")
        if user.get("locked_until"):
            try:
                if datetime.fromisoformat(user["locked_until"]) > datetime.utcnow():
                    return AuthResult(False, "auth.account_locked")
            except Exception:
                pass

        stored_hash = user.get("password_hash") or ""
        if not _verify_password(stored_hash, password):
            failed_attempts = int(user.get("failed_attempts", 0)) + 1
            lock_until = None
            if failed_attempts >= 5:
                lock_until = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                    (failed_attempts, lock_until, user["id"]),
                )
                conn.commit()
            return AuthResult(False, "auth.account_locked" if lock_until else "auth.invalid_credentials")

        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
                (now_iso(), user["id"]),
            )
            conn.commit()
        refreshed = self.get_user_by_id(user["id"])
        return AuthResult(True, "auth.login_success", self._user_payload(refreshed or user))

    def request_password_reset(self, email: str) -> AuthResult:
        email = _normalize_email(email)
        if not _is_valid_email(email):
            return AuthResult(False, "auth.check_email")
        user = self.get_user_by_email(email)
        if user is None:
            return AuthResult(False, "auth.check_email")
        if self._cooldown_remaining(email, "reset") > 0:
            return AuthResult(False, "auth.cooldown")
        code = self._issue_code_for_user(email, "reset")
        try:
            send_code_email(email, "reset", code)
        except Exception:
            pass
        return AuthResult(True, "auth.check_email")

    def reset_password(self, email: str, code: str, new_password: str) -> AuthResult:
        email = _normalize_email(email)
        if not _is_valid_email(email):
            return AuthResult(False, "auth.invalid_email")
        user = self.get_user_by_email(email)
        if user is None:
            return AuthResult(False, "auth.invalid_credentials")
        if not self._code_is_valid(email, code, "reset"):
            return AuthResult(False, "auth.invalid_code")
        if not new_password or len(new_password) < 10:
            return AuthResult(False, "auth.password_policy")
        local_part = email.split("@", 1)[0]
        if new_password == email or new_password.lower() == local_part.lower() or local_part.lower() in new_password.lower():
            return AuthResult(False, "auth.password_policy")
        password_hash = _hash_password(new_password)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (password_hash, user["id"]),
            )
            conn.execute(
                "UPDATE email_codes SET used = 1 WHERE user_id = ? AND purpose = 'reset'",
                (user["id"],),
            )
            conn.commit()
        return AuthResult(True, "auth.password_reset")

    def change_password(self, user_id: int, old_password: str, new_password: str) -> AuthResult:
        user = self.get_user_by_id(user_id)
        if user is None:
            return AuthResult(False, "auth.invalid_credentials")
        if not _verify_password(user.get("password_hash") or "", old_password):
            return AuthResult(False, "auth.invalid_password")
        if not new_password or len(new_password) < 10:
            return AuthResult(False, "auth.password_policy")
        local = (user["email"] or "").split("@", 1)[0]
        if new_password == user["email"] or new_password.lower() == local.lower() or local.lower() in new_password.lower():
            return AuthResult(False, "auth.password_policy")
        password_hash = _hash_password(new_password)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (password_hash, user_id),
            )
            conn.commit()
        return AuthResult(True, "auth.password_changed")

    def resend_code(self, email: str, purpose: str) -> AuthResult:
        email = _normalize_email(email)
        if not _is_valid_email(email):
            return AuthResult(False, "auth.check_email")
        if self._cooldown_remaining(email, purpose) > 0:
            return AuthResult(False, "auth.cooldown")
        user = self.get_user_by_email(email)
        if user is None:
            return AuthResult(False, "auth.check_email")
        code = self._issue_code_for_user(email, purpose)
        try:
            send_code_email(email, purpose, code)
        except Exception:
            pass
        return AuthResult(True, "auth.code_sent")


def _get_store(db_path: str | Path | None = None, database_url: str | None = None) -> AuthStore:
    return AuthStore(db_path=db_path, database_url=database_url)


def register(email: str, password: str, display_name: str, *, store: AuthStore | None = None) -> AuthResult:
    store = store or _get_store()
    return store.register(email, password, display_name)


def verify_email(email: str, code: str, *, store: AuthStore | None = None) -> AuthResult:
    store = store or _get_store()
    return store.verify_email(email, code)


def login(email: str, password: str, *, store: AuthStore | None = None) -> AuthResult:
    store = store or _get_store()
    return store.login(email, password)


def request_password_reset(email: str, *, store: AuthStore | None = None) -> AuthResult:
    store = store or _get_store()
    return store.request_password_reset(email)


def reset_password(email: str, code: str, new_password: str, *, store: AuthStore | None = None) -> AuthResult:
    store = store or _get_store()
    return store.reset_password(email, code, new_password)


def change_password(user_id: int, old: str, new: str, *, store: AuthStore | None = None) -> AuthResult:
    store = store or _get_store()
    return store.change_password(user_id, old, new)


def resend_code(email: str, purpose: str, *, store: AuthStore | None = None) -> AuthResult:
    store = store or _get_store()
    return store.resend_code(email, purpose)


__all__ = [
    "AuthResult",
    "AuthStore",
    "change_password",
    "login",
    "register",
    "request_password_reset",
    "resend_code",
    "reset_password",
    "verify_email",
]
