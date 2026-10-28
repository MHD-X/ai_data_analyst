import pandas as pd

from core.memory import MemoryStore
from core.prompts import build_dataframe_context, parse_llm_response, validate_generated_code
from core.security import mask_df_for_llm, safe_filename
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
