"""
HPG Cyberpunk DAW Theme — Ableton-Flat, Neon Gruen + Neon Violett.

Design-Philosophie:
  - Font: Cascadia Code / Consolas (Monospace) — technischer DAW-Look
  - border-radius: 0px ueberall (Ableton-Flat, keine abgerundeten Ecken)
  - Kompaktes Padding (4-6px) — keine luftigen Abstaende
  - Warme Grau-Toene (kein Blau-Grau) fuer Hintergruende
  - Neon Gruen (#00E676) als Primaer-Akzent
  - Neon Violett (#7C4DFF) als Sekundaer-Akzent
  - 1px solid Borders — duenn, kaum sichtbar

Stellt bereit:
  - COLORS, GENRE_COLORS, RISK_STYLES  — Farbkonstanten
  - get_app_stylesheet()               — Globale QSS
  - apply_dark_theme(app)              — QPalette + QSS anwenden
  - score_color(value)                 — Dynamische Score-Farbe
  - html_style_block()                 — CSS fuer HTML in QTextEdit
"""

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

# ──────────────────────────────────────────────────────────────
# Schriftarten — Monospace fuer DAW-Look
# ──────────────────────────────────────────────────────────────

# Primaer UI-Font — Monospace = technischer DAW-Charakter
FONT_FAMILY = "'Cascadia Code', 'Consolas', 'JetBrains Mono', monospace"
# Datenwerte (BPM, Key, Timestamps) — gleiche Monospace-Familie
FONT_FAMILY_DATA = "'Cascadia Code', 'Consolas', 'JetBrains Mono', monospace"

FONT_SIZE = "13px"
FONT_SIZE_SMALL = "12px"
FONT_SIZE_HEADER = "14px"

# ──────────────────────────────────────────────────────────────
# Farb-Palette (Cyberpunk DAW — warmes Dunkelgrau + Neon)
# ──────────────────────────────────────────────────────────────

COLORS = {
  # Hintergruende — warme neutrale Grautöne (kein Blau!)
  "bg_main":       "#141414",   # Hauptfenster (fast schwarz, warm)
  "bg_panel":      "#1e1e1e",   # Sidebar, Panels
  "bg_card":       "#262626",   # Cards, Gruppenboxen
  "bg_card2":      "#2a2a2a",   # Cards zweite Ebene (etwas heller)
  "bg_input":      "#1a1a1a",   # Eingabefelder, Tabellen-Basis
  "bg_table_alt":  "#1f1f1f",   # Alternierende Zeilen
  "bg_hover":      "#2d2d2d",   # Hover-State
  "bg_selected":   "#2a3a2a",   # Selektion (leichter Gruen-Schimmer)
  "bg_tooltip":    "#333333",   # Tooltips
  "bg_sidebar":    "#111111",   # Sidebar (dunkelster Ton)
  "bg_toolbar":    "#1a1a1a",   # Toolbar oben

  # Text (Weiss-Hierarchie — neutral, kein Blau-Tint)
  "text_primary":   "#e0e0e0",  # Haupttext
  "text_secondary": "#888888",  # Labels, Meta
  "text_bright":    "#ffffff",  # Ueberschriften, aktive Elemente
  "text_dim":       "#555555",  # Deaktiviert, Hints

  # Primaer-Akzent: Neon Gruen
  "accent_primary":      "#00E676",  # Aktive Elemente, Primary Buttons
  "accent_primary_dim":  "#00C853",  # Hover-Variante (etwas dunkler)
  "accent_primary_bg":   "#0a2e1a",  # Dezenter gruener Hintergrund
  "accent_primary_glow": "#69FF9F",  # Extra-hell fuer Glow-Effekte

  # Sekundaer-Akzent: Neon Violett
  "accent_secondary":     "#7C4DFF",  # Genre-Badges, Tab-Akzente
  "accent_secondary_dim": "#651FFF",  # Hover
  "accent_secondary_bg":  "#1a0a3a",  # Dezenter violetter Hintergrund

  # Status-Farben
  "accent_success": "#00E676",  # Neon Gruen (= Primaer)
  "accent_warning": "#FFD740",  # Neon Gold
  "accent_danger":  "#FF5252",  # Neon Rot

  # Borders — neutral grau, kaum sichtbar
  "border":         "#2a2a2a",  # Subtile 1px Linien
  "border_active":  "#00E676",  # Aktiver Border = Neon Gruen
  "border_focus":   "#00E676",  # Focus = Neon Gruen (statt Blau!)
  "border_danger":  "#FF5252",
  "border_success": "#00E676",
}

# ──────────────────────────────────────────────────────────────
# Genre-Farben — Neon auf Dark, neutrale Hintergruende
# Tupel: (Textfarbe, Hintergrundfarbe)
# ──────────────────────────────────────────────────────────────

GENRE_COLORS = {
  "Psytrance":      ("#E040FB", "#2a0a3a"),  # Neon Magenta
  "Tech House":     ("#448AFF", "#0a1a3a"),  # Neon Blau
  "Progressive":    ("#69F0AE", "#0a2a1a"),  # Neon Mint
  "Melodic Techno": ("#18FFFF", "#0a2a2a"),  # Neon Cyan
  "Techno":         ("#B0BEC5", "#1a1a1a"),  # Silber-Neutral
  "Deep House":     ("#FFAB40", "#2a1a0a"),  # Neon Orange
  "Trance":         ("#B388FF", "#1a0a3a"),  # Neon Violett-Hell
  "Drum & Bass":    ("#FF5252", "#2a0a0a"),  # Neon Rot
  "Minimal":        ("#C6FF00", "#1a2a0a"),  # Neon Lime
}

# Standard-Farbe fuer unbekannte Genres
GENRE_DEFAULT = ("#888888", "#1e1e1e")

# ──────────────────────────────────────────────────────────────
# Risk-Styles fuer Mix Tips (bg_color, accent_color)
# ──────────────────────────────────────────────────────────────

RISK_STYLES = {
  "low":        ("#0a2e1a", "#00E676"),  # Neon Gruen
  "medium-low": ("#1a2a0a", "#C6FF00"),  # Neon Lime
  "medium":     ("#2a1a0a", "#FFD740"),  # Neon Gold
  "high":       ("#2a0a0a", "#FF5252"),  # Neon Rot
}
RISK_DEFAULT = ("#1e1e1e", "#888888")

# ──────────────────────────────────────────────────────────────
# DJ-freundliche Risk-Labels
# ──────────────────────────────────────────────────────────────

RISK_LABELS = {
  "low":        "Smooth",
  "medium-low": "Solid",
  "medium":     "Aufpassen",
  "high":       "Riskant",
}

# ──────────────────────────────────────────────────────────────
# Energie-Phasen-Farben (fuer Set Timing)
# ──────────────────────────────────────────────────────────────

PHASE_COLORS = {
  "intro":    "#00E676",  # Neon Gruen
  "build":    "#FFD740",  # Neon Gold
  "peak":     "#FF5252",  # Neon Rot
  "sustain":  "#7C4DFF",  # Neon Violett
  "cooldown": "#18FFFF",  # Neon Cyan
}

PHASE_LABELS = {
  "intro":    "Intro \u2014 Sanfter Einstieg",
  "build":    "Build-Up \u2014 Steigende Energie",
  "peak":     "Peak \u2014 Hoechste Intensitaet",
  "sustain":  "Sustain \u2014 Energie halten",
  "cooldown": "Cooldown \u2014 Ausklang",
}

# ──────────────────────────────────────────────────────────────
# Transition-Type Farben
# ──────────────────────────────────────────────────────────────

TRANSITION_TYPE_COLORS = {
  "smooth_blend":      "#00E676",  # Neon Gruen
  "bass_swap":         "#448AFF",  # Neon Blau
  "breakdown_bridge":  "#FFD740",  # Neon Gold
  "drop_cut":          "#FF5252",  # Neon Rot
  "filter_ride":       "#18FFFF",  # Neon Cyan
  "halftime_switch":   "#B388FF",  # Neon Violett-Hell
  "echo_out":          "#7C4DFF",  # Neon Violett
  "cold_cut":          "#B0BEC5",  # Silber
}


# ──────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────────────────────

def score_color(value: float) -> str:
  """Farbe fuer einen Score-Wert (0.0 - 1.0 oder 0 - 100)."""
  if value > 1.0:
    value = value / 100.0
  if value >= 0.8:
    return COLORS["accent_success"]
  elif value >= 0.6:
    return COLORS["accent_warning"]
  return COLORS["accent_danger"]


def html_style_block() -> str:
  """CSS-Block fuer HTML-Inhalte in QTextEdit (Cyberpunk DAW Theme)."""
  c = COLORS
  return f"""
  <style>
    body, p, li, td, th {{
      color: {c["text_primary"]};
      font-family: {FONT_FAMILY};
      font-size: 13px;
      line-height: 1.55;
    }}
    h3 {{
      color: {c["text_bright"]};
      margin: 14px 0 6px 0;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    h4 {{
      color: {c["accent_primary"]};
      margin: 10px 0 4px 0;
      font-size: 12px;
      font-weight: 600;
    }}
    table {{
      border-collapse: collapse;
      margin: 6px 0;
      width: 100%;
    }}
    td, th {{
      padding: 4px 8px;
      border-bottom: 1px solid {c["border"]};
    }}
    th {{
      color: {c["text_secondary"]};
      font-weight: 600;
      text-align: left;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      background: {c["bg_card"]};
    }}
    .peak-row {{
      background: rgba(255, 215, 64, 0.08);
    }}
    .alt-row {{
      background: {c["bg_table_alt"]};
    }}
    hr {{
      border: none;
      border-top: 1px solid {c["border"]};
      margin: 10px 0;
    }}
    .dim {{
      color: {c["text_dim"]};
      font-size: 11px;
    }}
    b, strong {{
      color: {c["text_bright"]};
      font-weight: 600;
    }}
    a {{
      color: {c["accent_primary"]};
      text-decoration: none;
    }}
    code {{
      background: {c["bg_card"]};
      color: {c["accent_primary_glow"]};
      padding: 1px 5px;
      font-family: {FONT_FAMILY_DATA};
      font-size: 12px;
    }}
    .badge {{
      display: inline-block;
      padding: 1px 6px;
      font-size: 11px;
      font-weight: 600;
    }}
  </style>
  """


# ──────────────────────────────────────────────────────────────
# Globale QSS — Cyberpunk DAW: 0px radius, Monospace, kompaktes Padding
# ──────────────────────────────────────────────────────────────

def get_app_stylesheet() -> str:
  """Erzeugt das globale QSS-Stylesheet fuer die App.

  Design-DNA: Cyberpunk DAW (Ableton-Flat).
  - font: Cascadia Code / Consolas (Monospace)
  - border-radius: 0px (ueberall, kein Rounding!)
  - Kompaktes Padding (4-6px)
  - Neutrale 1px Borders (#2a2a2a)
  - Neon Gruen (#00E676) als Focus/Akzent
  """
  c = COLORS
  return f"""
    /* === Basis === */
    QMainWindow, QWidget {{
      background-color: {c["bg_main"]};
      color: {c["text_primary"]};
      font-family: {FONT_FAMILY};
      font-size: {FONT_SIZE};
    }}

    /* === GroupBox === */
    QGroupBox {{
      background-color: {c["bg_card"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      margin-top: 14px;
      padding-top: 18px;
      font-weight: 600;
      color: {c["text_bright"]};
    }}
    QGroupBox::title {{
      subcontrol-origin: margin;
      left: 8px;
      padding: 0 4px;
      color: {c["text_secondary"]};
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }}

    /* === Buttons — Primary (objectName: btn_primary) === */
    QPushButton#btn_primary {{
      background-color: {c["accent_primary"]};
      color: #000000;
      border: none;
      border-radius: 0px;
      font-size: 13px;
      font-weight: 700;
      padding: 7px 18px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    QPushButton#btn_primary:hover {{
      background-color: {c["accent_primary_glow"]};
    }}
    QPushButton#btn_primary:pressed {{
      background-color: {c["accent_primary_dim"]};
    }}
    QPushButton#btn_primary:disabled {{
      background-color: {c["border"]};
      color: {c["text_dim"]};
    }}

    /* === Buttons — Secondary (objectName: btn_secondary) === */
    QPushButton#btn_secondary {{
      background-color: {c["bg_card"]};
      color: {c["text_primary"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      font-size: {FONT_SIZE_SMALL};
      font-weight: 500;
      padding: 5px 14px;
    }}
    QPushButton#btn_secondary:hover {{
      background-color: {c["bg_hover"]};
      border-color: {c["accent_primary"]};
      color: {c["text_bright"]};
    }}
    QPushButton#btn_secondary:pressed {{
      background-color: {c["bg_selected"]};
    }}

    /* === Buttons — Danger (objectName: btn_danger) === */
    QPushButton#btn_danger {{
      background-color: transparent;
      color: {c["accent_danger"]};
      border: 1px solid {c["accent_danger"]};
      border-radius: 0px;
      font-size: {FONT_SIZE_SMALL};
      font-weight: 500;
      padding: 5px 14px;
    }}
    QPushButton#btn_danger:hover {{
      background-color: {c["accent_danger"]};
      color: #000000;
    }}
    QPushButton#btn_danger:pressed {{
      background-color: #c53030;
    }}

    /* === Buttons — Generic (kein objectName) === */
    QPushButton {{
      background-color: {c["bg_card"]};
      color: {c["text_primary"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      padding: 5px 12px;
      font-size: {FONT_SIZE_SMALL};
      font-weight: 500;
    }}
    QPushButton:hover {{
      background-color: {c["bg_hover"]};
      border-color: {c["accent_primary"]};
      color: {c["text_bright"]};
    }}
    QPushButton:pressed {{
      background-color: {c["bg_selected"]};
    }}
    QPushButton:disabled {{
      background-color: {c["bg_panel"]};
      color: {c["text_dim"]};
      border-color: {c["bg_panel"]};
    }}

    /* === ComboBox === */
    QComboBox {{
      background-color: {c["bg_card"]};
      color: {c["text_primary"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      padding: 4px 8px;
      min-height: 24px;
      font-size: {FONT_SIZE_SMALL};
      selection-background-color: {c["bg_hover"]};
    }}
    QComboBox:hover {{
      border-color: {c["accent_primary"]};
    }}
    QComboBox:focus {{
      border-color: {c["border_focus"]};
    }}
    QComboBox::drop-down {{
      border: none;
      width: 18px;
    }}
    QComboBox QAbstractItemView {{
      background-color: {c["bg_card2"]};
      color: {c["text_primary"]};
      selection-background-color: {c["bg_hover"]};
      selection-color: {c["text_bright"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      padding: 2px;
      outline: none;
    }}

    /* === Slider === */
    QSlider::groove:horizontal {{
      height: 3px;
      background: {c["border"]};
      border-radius: 0px;
    }}
    QSlider::handle:horizontal {{
      background: {c["accent_primary"]};
      width: 12px;
      height: 12px;
      margin: -5px 0;
      border-radius: 0px;
      border: 1px solid {c["bg_main"]};
    }}
    QSlider::handle:horizontal:hover {{
      background: {c["accent_primary_glow"]};
    }}
    QSlider::sub-page:horizontal {{
      background: {c["accent_primary"]};
      border-radius: 0px;
    }}

    /* === SpinBox === */
    QSpinBox {{
      background-color: {c["bg_card"]};
      color: {c["text_primary"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      padding: 3px 6px;
      min-height: 22px;
    }}
    QSpinBox:focus {{
      border-color: {c["border_focus"]};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
      background: transparent;
      border: none;
    }}

    /* === CheckBox === */
    QCheckBox {{
      color: {c["text_primary"]};
      spacing: 6px;
      font-size: {FONT_SIZE_SMALL};
    }}
    QCheckBox::indicator {{
      width: 14px;
      height: 14px;
      border: 1px solid {c["border"]};
      border-radius: 0px;
      background-color: {c["bg_card"]};
    }}
    QCheckBox::indicator:checked {{
      background-color: {c["accent_primary"]};
      border-color: {c["accent_primary"]};
    }}
    QCheckBox::indicator:hover {{
      border-color: {c["accent_primary"]};
    }}

    /* === Table === */
    QTableWidget {{
      background-color: {c["bg_input"]};
      alternate-background-color: {c["bg_table_alt"]};
      color: {c["text_primary"]};
      gridline-color: {c["border"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      selection-background-color: {c["bg_selected"]};
      selection-color: {c["text_bright"]};
      font-size: {FONT_SIZE_SMALL};
    }}
    QTableWidget::item {{
      padding: 3px 6px;
      border: none;
    }}
    QTableWidget::item:hover {{
      background-color: {c["bg_hover"]};
    }}
    QHeaderView::section {{
      background-color: {c["bg_card"]};
      color: {c["text_secondary"]};
      font-weight: 600;
      font-size: 11px;
      padding: 5px 6px;
      border: none;
      border-bottom: 1px solid {c["border"]};
      border-right: 1px solid {c["border"]};
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }}

    /* === Tab Widget === */
    QTabWidget::pane {{
      border: 1px solid {c["border"]};
      border-radius: 0px;
      background-color: {c["bg_main"]};
      margin-top: -1px;
    }}
    QTabBar::tab {{
      background-color: transparent;
      color: {c["text_secondary"]};
      padding: 6px 14px;
      margin-right: 1px;
      border: none;
      border-bottom: 2px solid transparent;
      font-size: {FONT_SIZE_SMALL};
      font-weight: 500;
    }}
    QTabBar::tab:selected {{
      color: {c["text_bright"]};
      border-bottom: 2px solid {c["accent_primary"]};
    }}
    QTabBar::tab:hover:!selected {{
      background-color: {c["bg_hover"]};
      color: {c["text_primary"]};
    }}

    /* === TextEdit (HTML-Ansicht) === */
    QTextEdit {{
      background-color: {c["bg_input"]};
      color: {c["text_primary"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      padding: 8px;
      font-family: {FONT_FAMILY};
      font-size: {FONT_SIZE};
      line-height: 1.55;
    }}

    /* === LineEdit === */
    QLineEdit {{
      background-color: {c["bg_card"]};
      color: {c["text_primary"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      padding: 5px 8px;
      font-size: {FONT_SIZE_SMALL};
      selection-background-color: {c["bg_selected"]};
    }}
    QLineEdit:focus {{
      border-color: {c["border_focus"]};
    }}

    /* === ScrollArea === */
    QScrollArea {{
      background-color: transparent;
      border: none;
    }}

    /* === ProgressBar === */
    QProgressBar {{
      background-color: {c["border"]};
      border: none;
      border-radius: 0px;
      text-align: center;
      color: transparent;
      font-size: 0px;
      min-height: 4px;
      max-height: 4px;
    }}
    QProgressBar::chunk {{
      background-color: {c["accent_primary"]};
      border-radius: 0px;
    }}

    /* === ScrollBar (duenn, flat) === */
    QScrollBar:vertical {{
      background: transparent;
      width: 5px;
      margin: 0;
      border: none;
    }}
    QScrollBar::handle:vertical {{
      background: {c["border"]};
      border-radius: 0px;
      min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
      background: {c["text_secondary"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
      height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
      background: none;
    }}
    QScrollBar:horizontal {{
      background: transparent;
      height: 5px;
      border: none;
    }}
    QScrollBar::handle:horizontal {{
      background: {c["border"]};
      border-radius: 0px;
      min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
      background: {c["text_secondary"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
      width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
      background: none;
    }}

    /* === ToolTip === */
    QToolTip {{
      background-color: {c["bg_tooltip"]};
      color: {c["text_primary"]};
      border: 1px solid {c["border"]};
      border-radius: 0px;
      padding: 4px 8px;
      font-size: {FONT_SIZE_SMALL};
    }}

    /* === Label === */
    QLabel {{
      color: {c["text_primary"]};
    }}

    /* === Frame === */
    QFrame {{
      color: {c["text_primary"]};
    }}
    QFrame[frameShape="4"],
    QFrame[frameShape="5"] {{
      color: {c["border"]};
    }}

    /* === Splitter === */
    QSplitter::handle {{
      background: {c["border"]};
    }}
    QSplitter::handle:horizontal {{
      width: 1px;
    }}
    QSplitter::handle:vertical {{
      height: 1px;
    }}

    /* === Message Box === */
    QMessageBox {{
      background-color: {c["bg_panel"]};
    }}
    QMessageBox QLabel {{
      color: {c["text_primary"]};
      font-size: {FONT_SIZE};
    }}
  """


def apply_dark_theme(app) -> None:
  """QPalette + QSS anwenden."""
  c = COLORS

  palette = QPalette()
  palette.setColor(QPalette.ColorRole.Window,          QColor(c["bg_main"]))
  palette.setColor(QPalette.ColorRole.WindowText,      QColor(c["text_primary"]))
  palette.setColor(QPalette.ColorRole.Base,            QColor(c["bg_input"]))
  palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(c["bg_table_alt"]))
  palette.setColor(QPalette.ColorRole.Text,            QColor(c["text_primary"]))
  palette.setColor(QPalette.ColorRole.Button,          QColor(c["bg_card"]))
  palette.setColor(QPalette.ColorRole.ButtonText,      QColor(c["text_primary"]))
  palette.setColor(QPalette.ColorRole.Highlight,       QColor(c["accent_primary"]))
  palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
  palette.setColor(QPalette.ColorRole.Link,            QColor(c["accent_primary"]))
  palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(c["bg_tooltip"]))
  palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(c["text_primary"]))
  palette.setColor(QPalette.ColorRole.BrightText,      QColor(c["text_bright"]))
  palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text_dim"]))

  app.setPalette(palette)
  app.setStyleSheet(get_app_stylesheet())
