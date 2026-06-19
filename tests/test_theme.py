import pytest
from unittest.mock import MagicMock
from PyQt6.QtGui import QPalette, QColor
from hpg_core.theme import apply_dark_theme, COLORS, get_app_stylesheet

def test_apply_dark_theme():
    mock_app = MagicMock()

    apply_dark_theme(mock_app)

    # Verify setPalette was called
    mock_app.setPalette.assert_called_once()

    # Get the palette that was passed to setPalette
    args, _ = mock_app.setPalette.call_args
    palette = args[0]

    # Assert type
    assert isinstance(palette, QPalette)

    # Verify some key colors are set correctly based on COLORS
    assert palette.color(QPalette.ColorRole.Window).name() == QColor(COLORS["bg_main"]).name()
    assert palette.color(QPalette.ColorRole.WindowText).name() == QColor(COLORS["text_primary"]).name()
    assert palette.color(QPalette.ColorRole.Base).name() == QColor(COLORS["bg_input"]).name()
    assert palette.color(QPalette.ColorRole.AlternateBase).name() == QColor(COLORS["bg_table_alt"]).name()
    assert palette.color(QPalette.ColorRole.Text).name() == QColor(COLORS["text_primary"]).name()
    assert palette.color(QPalette.ColorRole.Button).name() == QColor(COLORS["bg_card"]).name()
    assert palette.color(QPalette.ColorRole.ButtonText).name() == QColor(COLORS["text_primary"]).name()
    assert palette.color(QPalette.ColorRole.Highlight).name() == QColor(COLORS["accent_primary"]).name()
    assert palette.color(QPalette.ColorRole.HighlightedText).name() == QColor("#000000").name()
    assert palette.color(QPalette.ColorRole.Link).name() == QColor(COLORS["accent_primary"]).name()
    assert palette.color(QPalette.ColorRole.ToolTipBase).name() == QColor(COLORS["bg_tooltip"]).name()
    assert palette.color(QPalette.ColorRole.ToolTipText).name() == QColor(COLORS["text_primary"]).name()
    assert palette.color(QPalette.ColorRole.BrightText).name() == QColor(COLORS["text_bright"]).name()
    assert palette.color(QPalette.ColorRole.PlaceholderText).name() == QColor(COLORS["text_dim"]).name()

    # Verify setStyleSheet was called with correct string
    mock_app.setStyleSheet.assert_called_once()

    args, _ = mock_app.setStyleSheet.call_args
    stylesheet = args[0]

    assert type(stylesheet) == str
    assert len(stylesheet) > 0
    assert stylesheet == get_app_stylesheet()


def test_apply_dark_theme_with_none():
    with pytest.raises(AttributeError):
        apply_dark_theme(None)

def test_score_color_from_theme():
    # Adding a quick test for score_color if it's not tested yet
    from hpg_core.theme import score_color
    assert score_color(0.9) == COLORS["accent_success"]
    assert score_color(0.7) == COLORS["accent_warning"]
    assert score_color(0.5) == COLORS["accent_danger"]
    assert score_color(90) == COLORS["accent_success"] # scales 90 * 0.01 = 0.9

def test_apply_dark_theme_with_all_roles():
    from PyQt6.QtGui import QPalette
    mock_app = MagicMock()

    apply_dark_theme(mock_app)

    args, _ = mock_app.setPalette.call_args
    palette = args[0]

    # Let's ensure no basic role throws an error or is unmapped
    roles = [
        QPalette.ColorRole.Window,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Base,
        QPalette.ColorRole.AlternateBase,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.Button,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.Highlight,
        QPalette.ColorRole.HighlightedText,
        QPalette.ColorRole.Link,
        QPalette.ColorRole.ToolTipBase,
        QPalette.ColorRole.ToolTipText,
        QPalette.ColorRole.BrightText,
        QPalette.ColorRole.PlaceholderText
    ]

    for role in roles:
        # If any of these wasn't set or causes error, it fails here
        assert palette.color(role).isValid()

def test_get_app_stylesheet():
    from hpg_core.theme import get_app_stylesheet

    stylesheet = get_app_stylesheet()

    assert isinstance(stylesheet, str)
    assert len(stylesheet) > 0

    # Check that it contains key CSS sections and color references
    assert "QMainWindow" in stylesheet
    assert "QWidget" in stylesheet
    assert "QTableWidget" in stylesheet
    assert "QPushButton" in stylesheet

    # Check that SOME colors from COLORS got formatted into the string
    assert COLORS["bg_main"] in stylesheet
    assert COLORS["accent_primary"] in stylesheet

def test_html_style_block():
    from hpg_core.theme import html_style_block

    html = html_style_block()

    assert isinstance(html, str)
    assert "<style>" in html
    assert "body" in html
    assert "table" in html
