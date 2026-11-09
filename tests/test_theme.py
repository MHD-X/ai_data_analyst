import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME_FILE = ROOT / "ui" / "theme.py"
APP_FILE = ROOT / "app.py"
I18N_FILE = ROOT / "utils" / "i18n.py"
CONFIG_FILE = ROOT / ".streamlit" / "config.toml"

FORBIDDEN_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})|rgba?\(|linear-gradient\s*\(")


def test_no_forbidden_color_literals_in_theme_css() -> None:
    files = [THEME_FILE, APP_FILE, I18N_FILE]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not FORBIDDEN_RE.search(text), f"Forbidden CSS color literal found in {path}"


def test_streamlit_config_has_expected_theme_values() -> None:
    config = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    theme = config["theme"]
    expected = {
        "base": "light",
        "primaryColor": "#2563EB",
        "backgroundColor": "#F6F8FB",
        "secondaryBackgroundColor": "#EEF2F7",
        "textColor": "#1E293B",
        "font": "sans serif",
    }
    assert theme == expected
