from __future__ import annotations

import pandas as pd

from core.memory import MemoryStore


def test_memory_scopes_sessions_and_datasets_to_user(tmp_path):
    mem = MemoryStore(db_path=tmp_path / "memory.db")

    user_a = 101
    user_b = 202

    session_a = mem.create_session("User A session", user_id=user_a)
    session_b = mem.create_session("User B session", user_id=user_b)

    df_a = pd.DataFrame({"amount": [1, 2]})
    df_b = pd.DataFrame({"amount": [9, 10]})

    dataset_a = mem.save_dataset(
        filename="a.csv",
        file_path=tmp_path / "a.csv",
        rows=len(df_a),
        cols=len(df_a.columns),
        columns_info={"amount": "int"},
        session_id=session_a,
        user_id=user_a,
    )
    dataset_b = mem.save_dataset(
        filename="b.csv",
        file_path=tmp_path / "b.csv",
        rows=len(df_b),
        cols=len(df_b.columns),
        columns_info={"amount": "int"},
        session_id=session_b,
        user_id=user_b,
    )

    assert mem.list_sessions(user_id=user_a)[0].id == session_a
    assert mem.list_sessions(user_id=user_b)[0].id == session_b
    assert [d.id for d in mem.list_datasets(user_id=user_a)] == [dataset_a]
    assert [d.id for d in mem.list_datasets(user_id=user_b)] == [dataset_b]
    assert mem.get_dataset_by_hash("", user_id=user_a) is None
