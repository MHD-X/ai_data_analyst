# Audit fix: sandbox security regression tests for blocked code paths.
import pandas as pd
import pytest

from core.code_executor import CodeExecutor, UnsafeCodeError

BAD_SNIPPETS = [
    "x = _sys.modules['os']",
    "print(().__class__.__bases__)",
    "print(open('.env').read())",
    "import pandas as pd\npd.read_csv('/etc/passwd')",
    "getattr(df, 'to_pickle')('x')",
    "df.to_csv('leak.csv')",
    "df.query('a > 1')",
    "import pandas as pd\npd.io.common.os.system('id')",
]


@pytest.mark.parametrize("snippet", BAD_SNIPPETS)
def test_dangerous_code_is_rejected(snippet):
    executor = CodeExecutor(timeout=10, allowed_modules=("pandas", "numpy", "plotly"))
    with pytest.raises(UnsafeCodeError):
        executor._static_check(snippet)


@pytest.mark.parametrize("snippet", [
    "print(df['a'].sum())",
    "import pandas as pd\nprint(pd.to_datetime(df['a']))",
    "out = df.to_csv()\nprint(out)",
    "for _ in range(3):\n    pass",
])
def test_normal_analysis_code_is_allowed(snippet):
    executor = CodeExecutor(timeout=10, allowed_modules=("pandas", "numpy", "plotly"))
    executor._static_check(snippet)


def test_secrets_not_inherited(monkeypatch):
    for key in ("LLM_API_KEY", "DATABASE_URL", "AUTH_SECRET", "SMTP_PASSWORD", "ADMIN_PASSWORD"):
        monkeypatch.setenv(key, "TOPSECRET")
    assert all("TOPSECRET" not in value for value in CodeExecutor._child_env().values())


def test_column_names_with_quotes_are_not_spliced_into_code():
    df = pd.DataFrame({"a'] + 1 + df['": [1, 2, 3]})
    code = "print(df['a'])"
    assert CodeExecutor()._rewrite_dataframe_column_references(code, df) == code
