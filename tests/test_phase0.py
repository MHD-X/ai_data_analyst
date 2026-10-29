import pandas as pd

from core.memory import MemoryStore
from core.prompts import build_dataframe_context, parse_llm_response, validate_generated_code
from core.security import mask_df_for_llm, redact_text, safe_filename, save_encrypted
from core.audit_config import build_audit_config


def test_build_audit_config_detects_columns():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "customer_id": list(range(1, 11)),
            "amount": [10, 12, 15, 18, 20, 21, 19, 17, 22, 25],
            "customer_name": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        }
    )
    cfg = build_audit_config(df)
    assert "date" in cfg.date_cols
    assert "amount" in cfg.numeric_cols
    assert cfg.id_col == "customer_id"


def test_mask_df_for_llm_redacts_pii_before_context():
    df = pd.DataFrame({"customer_name": ["Alice", "Bob"], "total": [100, 200]})
    masked = mask_df_for_llm(df)
    assert masked["customer_name"].tolist() == ["<MASKED>", "<MASKED>"]

    context = build_dataframe_context(df)
    assert "Alice" not in context
    assert "<MASKED>" in context


def test_safe_filename_is_stable_and_safe():
    name = safe_filename("../bad name.csv")
    assert name.endswith(".csv")
    assert "/" not in name
    assert "bad name" not in name


def test_memory_list_datasets_and_feedback_works(tmp_path):
    mem = MemoryStore(db_path=tmp_path / "memory.db")
    session_id = mem.create_session("demo")
    dataset_id = mem.save_dataset(
        filename="sample.csv",
        file_path=str(tmp_path / "sample.csv"),
        rows=2,
        cols=2,
        columns_info={"one": "int"},
        session_id=session_id,
        file_hash="abc123",
    )
    assert mem.list_datasets(session_id=session_id)[0].id == dataset_id

    operation_id = mem.log_operation(
        user_request="email alice@example.com and phone +966500000000",
        generated_code="print('hello')",
        result_summary="ok",
        success=True,
        dataset_id=dataset_id,
        session_id=session_id,
    )
    mem.add_feedback(operation_id, 5, "Great")
    feedback = mem.get_feedback_for_operation(operation_id)
    assert feedback[0].rating == 5
    assert feedback[0].comment == "Great"


def test_parse_llm_response_and_validate_generated_code():
    text = """Here is the code:

```python
import pandas as pd
avg = df['amount'].mean()
print(avg)
```

Explanation: This calculates the average amount.
"""
    parsed = parse_llm_response(text)
    assert parsed.has_code is True
    assert "avg = df['amount'].mean()" in parsed.code

    ok, problems = validate_generated_code(parsed.code)
    assert ok is True
    assert problems == []


def test_audit_valid_rows_feed_forecast_input():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=5, freq="D"),
            "amount": [10, 12, 15, 18, 20],
            "customer_id": [1, 1, 2, 2, 3],
            "customer_name": ["Alice", "Bob", "Charlie", "Dana", "Eli"],
        }
    )
    df.loc[2, "date"] = "bad-date"
    cfg = build_audit_config(df)
    report = __import__("core.data_audit", fromlist=["audit_dataframe"]).audit_dataframe(df, cfg)
    assert len(report.valid) == report.valid_rows
    assert report.valid_rows < len(df)
    assert len(report.valid) == len(report.valid.index)


def test_dashboard_analysis_excludes_three_invalid_dates():
    df = pd.DataFrame(
        {
            "date": [
                "2024-01-01", "bad-date", "2024-01-03", "2024-01-05",
                "bad-date", "2024-01-07", "2024-01-09", "bad-date", "2024-01-11"
            ],
            "sales": [10, 20, 30, 40, 50, 60, 70, 80, 90],
        }
    )
    bundle = __import__("ui.dashboard", fromlist=["build_dashboard_analysis"]).build_dashboard_analysis(
        df,
        date_col="date",
        value_col="sales",
        freq="D",
        horizon=2,
    )
    assert bundle["audit"].valid_rows == 6
    assert len(bundle["audit"].valid) == 6
    assert bundle["audit"].quarantined_rows == 3


def test_dashboard_analysis_audit_error_falls_back_to_full_df(monkeypatch):
    import ui.dashboard as dashboard

    def boom(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(dashboard, "audit_dataframe", boom)
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-03", "2024-01-05", "2024-01-07", "2024-01-09"],
            "sales": [10, 20, 30, 40, 50],
        }
    )
    bundle = dashboard.build_dashboard_analysis(df, date_col="date", value_col="sales", freq="D")
    assert bundle["audit_error"] == "audit failed"
    assert bundle["rows_total"] == len(df)
    assert bundle["rows_used"] == len(df)


def test_safe_filename_hash_before_encryption(tmp_path):
    raw = b"customer_name,email\nAlice,alice@example.com\n"
    name = "../bad name.csv"
    safe = safe_filename(name)
    assert safe.endswith(".csv")
    assert "/" not in safe
    assert "bad name" not in safe

    encrypted = save_encrypted(raw, name)
    assert encrypted.exists()
    assert encrypted.name != name
    assert encrypted.name.startswith("file") or "bad" not in encrypted.name.lower()


def test_redact_text_before_logging(tmp_path):
    mem = MemoryStore(db_path=tmp_path / "memory.db")
    session_id = mem.create_session("demo")
    text = "email alice@example.com and phone +966500000000"
    redacted = redact_text(text)
    assert "alice@example.com" not in redacted
    assert "+966500000000" not in redacted

    op_id = mem.log_operation(
        user_request=text,
        generated_code="print('alice@example.com +966500000000')",
        result_summary="ok",
        success=True,
        session_id=session_id,
    )
    op = mem.get_operation(op_id)
    assert "alice@example.com" not in op.user_request
    assert "+966500000000" not in op.user_request
    assert "alice@example.com" not in op.generated_code
    assert "+966500000000" not in op.generated_code
