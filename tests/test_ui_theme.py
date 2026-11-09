from ui.theme import build_theme_css


def test_build_theme_css_includes_rtl_and_widget_styles():
    css = build_theme_css("ar")
    assert "Between Data" in css
    assert "direction: rtl" in css
    assert "stButton" in css or ".stButton" in css
    assert "stFileUploader" in css or "fileUploader" in css.lower()
    assert "background" in css.lower()
