import pandas as pd

from ui.dashboard import build_dashboard_analysis


def test_build_dashboard_analysis_returns_anomalies_and_narrative():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=24, freq="W"),
            "value": [10, 11, 12, 11, 10, 11, 13, 12, 15, 14, 10, 9, 16, 15, 14, 18, 17, 16, 19, 21, 20, 18, 17, 30],
        }
    )

    bundle = build_dashboard_analysis(df, date_col="date", value_col="value", freq="W", horizon=4)

    assert bundle is not None
    assert bundle["metric"] == "value"
    assert bundle["result"] is not None
    assert len(bundle["narrative"]) > 20
    assert bundle["anomalies"] is not None
    assert bundle["facts"] is not None
    assert bundle["facts"].anomaly_count >= 0
