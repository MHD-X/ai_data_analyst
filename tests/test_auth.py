import pytest

from core.auth import AuthStore, login, register, request_password_reset, reset_password
from core.db import DBConnection


@pytest.fixture
def auth_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "a" * 32)
    monkeypatch.setenv("SIGNUP_OPEN", "1")
    db_path = tmp_path / "auth.sqlite3"
    return AuthStore(db_path=db_path)


def test_password_policy_and_hashing(auth_store):
    result = register("user@example.com", "short", "User", store=auth_store)
    assert result.ok is False
    assert result.message_key == "auth.password_policy"

    result = register("user@example.com", "user@example.com", "User", store=auth_store)
    assert result.ok is False
    assert result.message_key == "auth.password_policy"

    result = register("user@example.com", "StrongPass123", "User", store=auth_store)
    assert result.ok is True
    assert result.user["email"] == "user@example.com"
    assert "password_hash" not in result.user

    user = auth_store.get_user_by_email("user@example.com")
    assert user["password_hash"]
    assert user["password_hash"] != "StrongPass123"
    assert user["password_hash"].startswith("$argon2id$")


def test_verification_code_expiry_attempts_and_cooldown(auth_store):
    result = register("test@example.com", "StrongPass123", "Tester", store=auth_store)
    assert result.ok is True
    code = auth_store._issue_code_for_user("test@example.com", "verify")
    assert len(code) == 6

    assert auth_store._code_is_valid("test@example.com", code, "verify") is True
    assert auth_store._code_is_valid("test@example.com", "000000", "verify") is False

    good = auth_store.verify_email("test@example.com", code)
    assert good.ok is True
    assert auth_store.verify_email("test@example.com", code).ok is False

    # Attempt limit and cooldown.
    reset_code = auth_store._issue_code_for_user("test@example.com", "reset")
    for _ in range(5):
        auth_store._consume_code_attempt("test@example.com", reset_code, "reset")
    assert auth_store._code_is_valid("test@example.com", reset_code, "reset") is False
    assert auth_store._cooldown_remaining("test@example.com", "reset") >= 0


def test_login_throttling_and_generic_messages(auth_store):
    register("login@example.com", "StrongPass123", "Login User", store=auth_store)

    for _ in range(5):
        login("login@example.com", "WrongPass123", store=auth_store)

    locked = login("login@example.com", "StrongPass123", store=auth_store)
    assert locked.ok is False
    assert locked.message_key in {"auth.account_locked", "auth.invalid_credentials"}

    unknown = login("missing@example.com", "WrongPass123", store=auth_store)
    assert unknown.ok is False
    assert unknown.message_key == "auth.invalid_credentials"


def test_register_existing_email_is_neutral(auth_store):
    first = register("dup@example.com", "StrongPass123", "User", store=auth_store)
    assert first.ok is True

    second = register("dup@example.com", "OtherPass456", "Another", store=auth_store)
    assert second.ok is False
    assert second.message_key == "auth.check_email"


def test_request_reset_and_change_password(auth_store):
    register("reset@example.com", "StrongPass123", "Reset User", store=auth_store)
    req = request_password_reset("reset@example.com", store=auth_store)
    assert req.ok is True

    code = auth_store._latest_code_record("reset@example.com", "reset")["code_hash"]
    assert code

    reset = reset_password("reset@example.com", "000000", "NewPass456", store=auth_store)
    assert reset.ok is False
    assert reset.message_key == "auth.invalid_code"

    reset_code = auth_store._issue_code_for_user("reset@example.com", "reset")
    reset = reset_password("reset@example.com", reset_code, "NewPass456", store=auth_store)
    assert reset.ok is True
    assert login("reset@example.com", "StrongPass123", store=auth_store).ok is False
    assert login("reset@example.com", "NewPass456", store=auth_store).ok is True


def test_bootstrap_admin_rejects_weak_password_and_returns_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "weak")
    monkeypatch.setenv("AUTH_SECRET", "d" * 32)
    monkeypatch.setenv("SIGNUP_OPEN", "1")
    store = AuthStore(db_path=tmp_path / "admin_weak.sqlite3")

    reason = store.bootstrap_admin()
    assert reason == "password_policy"
    assert store.get_user_by_email("admin@example.com") is None


def test_bootstrap_admin_missing_variables_return_not_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("AUTH_SECRET", "e" * 32)
    store = AuthStore(db_path=tmp_path / "admin_missing.sqlite3")

    reason = store.bootstrap_admin()
    assert reason == "not_configured"
    with store._connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
    assert int(count) == 0


def test_bootstrap_admin_creates_first_user(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_EMAIL", ' "admin@example.com" ')
    monkeypatch.setenv("ADMIN_PASSWORD", ' "StrongPass123" ')
    monkeypatch.setenv("AUTH_SECRET", "b" * 32)
    monkeypatch.setenv("SIGNUP_OPEN", "1")
    store = AuthStore(db_path=tmp_path / "admin.sqlite3")
    admin = store.bootstrap_admin()
    assert admin is not None
    assert admin["role"] == "admin"
    assert admin["email_verified"] == 1
    assert admin["must_change_password"] == 1

    second = store.bootstrap_admin()
    assert second is None
    with store._connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
    assert int(count) == 1


def test_signup_open_flag_controls_registration(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_SECRET", "c" * 32)
    monkeypatch.setenv("SIGNUP_OPEN", "0")
    store = AuthStore(db_path=tmp_path / "invite.sqlite3")
    result = register("invite@example.com", "StrongPass123", "Invite", store=store)
    assert result.ok is False
    assert result.message_key == "auth.signup_closed"

    monkeypatch.setenv("SIGNUP_OPEN", "1")
    result = register("invite2@example.com", "StrongPass123", "Invite", store=store)
    assert result.ok is True


def test_dbconnection_postgres_sql_has_matching_placeholders():
    class FakeCursor:
        def __init__(self):
            self.sql = None
            self.params = None

        def execute(self, sql, params=()):
            self.sql = sql
            self.params = params
            return self

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def execute(self, sql, params=()):
            self.cursor_obj.execute(sql, params)
            return self.cursor_obj

    fake = FakeConn()
    conn = DBConnection(fake, "postgresql")
    sql = "SELECT * FROM users WHERE email = ? AND password_hash = ?"
    params = ("one@example.com", "hash")
    conn.execute(sql, params)
    executed_sql = fake.cursor_obj.sql
    assert "?" not in executed_sql
    assert executed_sql.count("%s") == len(params)
    assert fake.cursor_obj.params == params
