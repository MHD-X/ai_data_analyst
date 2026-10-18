import pandas as pd

from utils.column_matcher import (
    friendly_missing_column_message,
    resolve_column,
    safe_get_column,
)


def test_resolve_column_exact_match():
    df = pd.DataFrame({"customer_id": [1, 2], "sale_total": [10, 20]})
    assert resolve_column(df, "customer_id") == "customer_id"


def test_resolve_column_typo_case_space_variants():
    df = pd.DataFrame({"Customer Name": ["A", "B"], "Sale Total": [10, 20]})
    assert resolve_column(df, "customer_name") == "Customer Name"
    assert resolve_column(df, "Customer   Name") == "Customer Name"
    assert resolve_column(df, "customer-name") == "Customer Name"


def test_resolve_column_underscore_and_extra_spaces():
    df = pd.DataFrame({"total_sales_amount": [1, 2]})
    assert resolve_column(df, "total sales amount") == "total_sales_amount"
    assert resolve_column(df, " total__sales__amount ") == "total_sales_amount"


def test_resolve_column_arabic_variants():
    df = pd.DataFrame({"إجمالي_المبيعات": [11, 22]})
    assert resolve_column(df, "اجمالي المبيعات") == "إجمالي_المبيعات"
    assert resolve_column(df, "اجمالي-المبيعات") == "إجمالي_المبيعات"


def test_resolve_column_ambiguous_prefers_best_score():
    df = pd.DataFrame({"customer_name": ["A"], "customername": ["B"]})
    assert resolve_column(df, "customer name") in {"customer_name", "customername"}


def test_missing_column_returns_none_and_friendly_message():
    df = pd.DataFrame({"customer_id": [1, 2], "region": ["x", "y"]})
    result = safe_get_column(df, "customer_name")
    assert result is None
    msg = friendly_missing_column_message("customer_name", df, lang="ar")
    assert "customer_name" in msg or "العمود" in msg


def test_empty_dataframe_returns_none():
    df = pd.DataFrame(columns=[])
    assert resolve_column(df, "anything") is None
    assert safe_get_column(df, "anything") is None


def test_missing_column_completely_missing():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    assert resolve_column(df, "nonexistent_column", cutoff=0.4) is None
