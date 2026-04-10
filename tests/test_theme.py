import sys
from unittest.mock import MagicMock, patch

# Setup mocks for all potential missing dependencies to prevent import errors
mock_qtgui = MagicMock()
mock_qtcore = MagicMock()
mock_numpy = MagicMock()
mock_librosa = MagicMock()
mock_mutagen = MagicMock()
mock_scipy = MagicMock()
mock_soundfile = MagicMock()

# QPalette.ColorRole is used in apply_dark_theme
class MockColorRole:
    Window = 1
    WindowText = 2
    Base = 3
    AlternateBase = 4
    Text = 5
    Button = 6
    ButtonText = 7
    Highlight = 8
    HighlightedText = 9
    Link = 10
    ToolTipBase = 11
    ToolTipText = 12
    BrightText = 13
    PlaceholderText = 14

mock_qtgui.QPalette.ColorRole = MockColorRole

with patch.dict(sys.modules, {
    'PyQt6.QtGui': mock_qtgui,
    'PyQt6.QtCore': mock_qtcore,
    'numpy': mock_numpy,
    'librosa': mock_librosa,
    'mutagen': mock_mutagen,
    'scipy': mock_scipy,
    'scipy.signal': MagicMock(),
    'soundfile': mock_soundfile,
}):
    # Also need to mock hpg_core components that might be imported by __init__ and depend on numpy etc.
    sys.modules['hpg_core.analysis'] = MagicMock()
    sys.modules['hpg_core.playlist'] = MagicMock()
    sys.modules['hpg_core.parallel_analyzer'] = MagicMock()
    sys.modules['hpg_core.models'] = MagicMock()

    from hpg_core.theme import (
        COLORS, FONT_FAMILY, score_color, html_style_block,
        get_app_stylesheet, apply_dark_theme
    )

def test_score_color():
    """Testet die score_color Logik mit verschiedenen Werten."""
    print("Running test_score_color...")
    # Teste 0.0 - 1.0 Bereich
    assert score_color(0.85) == COLORS["accent_success"]
    assert score_color(0.65) == COLORS["accent_warning"]
    assert score_color(0.4) == COLORS["accent_danger"]

    # Teste Grenzfaelle
    assert score_color(0.8) == COLORS["accent_success"]
    assert score_color(0.6) == COLORS["accent_warning"]
    assert score_color(0.59) == COLORS["accent_danger"]

    # Teste Skalierung (0 - 100)
    assert score_color(90) == COLORS["accent_success"]
    assert score_color(70) == COLORS["accent_warning"]
    assert score_color(50) == COLORS["accent_danger"]
    print("test_score_color passed!")

def test_html_style_block():
    """Testet ob html_style_block einen validen CSS-String mit erwarteten Selektoren liefert."""
    print("Running test_html_style_block...")
    css = html_style_block()
    assert isinstance(css, str)
    assert "<style>" in css
    assert "</style>" in css
    assert "body" in css
    assert "h3" in css
    assert "h4" in css
    assert "table" in css
    assert ".peak-row" in css
    assert ".alt-row" in css
    assert ".badge" in css
    assert COLORS["text_primary"] in css
    assert FONT_FAMILY in css
    print("test_html_style_block passed!")

def test_get_app_stylesheet():
    """Testet ob get_app_stylesheet ein QSS mit den wichtigen Selektoren liefert."""
    print("Running test_get_app_stylesheet...")
    qss = get_app_stylesheet()
    assert isinstance(qss, str)
    assert "QMainWindow" in qss
    assert "QGroupBox" in qss
    assert "QPushButton#btn_primary" in qss
    assert "QPushButton#btn_secondary" in qss
    assert "QPushButton#btn_danger" in qss
    assert "QComboBox" in qss
    assert "QTableWidget" in qss
    assert "QProgressBar" in qss
    assert "QScrollBar:vertical" in qss
    assert "QMessageBox" in qss

    # Pruefe ob Farben aus COLORS verwendet werden
    assert COLORS["bg_main"] in qss
    assert COLORS["accent_primary"] in qss
    print("test_get_app_stylesheet passed!")

def test_apply_dark_theme():
    """Testet ob apply_dark_theme die App-Methoden korrekt aufruft."""
    print("Running test_apply_dark_theme...")
    app = MagicMock()
    apply_dark_theme(app)

    assert app.setPalette.called
    assert app.setStyleSheet.called

    # Pruefe ob das Stylesheet aus get_app_stylesheet gesetzt wurde
    expected_qss = get_app_stylesheet()
    app.setStyleSheet.assert_called_with(expected_qss)
    print("test_apply_dark_theme passed!")

if __name__ == "__main__":
    try:
        test_score_color()
        test_html_style_block()
        test_get_app_stylesheet()
        test_apply_dark_theme()
        print("\nALL TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
