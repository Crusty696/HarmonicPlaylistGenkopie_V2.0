"""
HPG Theme — "Ink Navy Gold": tiefes Navy + sattes Gold, gedaempft/edel.

Design-Philosophie:
  - Font: Cascadia Code / Consolas (Monospace) — technischer DAW-Look
  - border-radius: 0px ueberall (flat, keine abgerundeten Ecken)
  - Kompaktes Padding (4-6px) — keine luftigen Abstaende
  - Tiefes Ink-Navy (#0c1430) fuer Hintergruende
  - Sattes Gold (#d6ac44) als Primaer-Akzent
  - Gedaempftes Stahlblau (#6f8fc4) als Sekundaer-Akzent
  - Gedaempfte Status-Farben (kein Neon)
  - 1px solid Borders — duenn, kaum sichtbar

Stellt bereit:
  - COLORS, GENRE_COLORS, RISK_STYLES  — Farbkonstanten
  - get_app_stylesheet()               — Globale QSS
  - apply_dark_theme(app)              — QPalette + QSS anwenden
  - score_color(value)                 — Dynamische Score-Farbe
  - html_style_block()                 — CSS fuer HTML in QTextEdit
"""

from PyQt6.QtGui import QPalette, QColor

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
  # Hintergruende — tiefes Ink-Navy (Ink Navy Gold Theme)
  "bg_main":       "#0c1430",   # Hauptfenster (kraeftiges tiefes Navy)
  "bg_panel":      "#0f1832",   # Sidebar, Panels
  "bg_card":       "#141d3a",   # Cards, Gruppenboxen
  "bg_card2":      "#182342",   # Cards zweite Ebene (etwas heller)
  "bg_input":      "#0d1730",   # Eingabefelder, Tabellen-Basis
  "bg_table_alt":  "#111c38",   # Alternierende Zeilen
  "bg_hover":      "#1b284a",   # Hover-State
  "bg_selected":   "#22305a",   # Selektion (helleres Navy, Gold-Border via border_active)
  "bg_tooltip":    "#182342",   # Tooltips
  "bg_sidebar":    "#0a1128",   # Sidebar (dunkelster Navy-Ton)
  "bg_toolbar":    "#0f1832",   # Toolbar oben

  # Text (warme Creme-Weiss-Hierarchie auf Navy)
  "text_primary":   "#e3e6ee",  # Haupttext
  "text_secondary": "#8592b0",  # Labels, Meta (blaugrau)
  "text_bright":    "#ffffff",  # Ueberschriften, aktive Elemente
  "text_dim":       "#586080",  # Deaktiviert, Hints

  # Primaer-Akzent: sattes Gold (Farbton 43 Grad, wie abgestimmt)
  "accent_primary":      "#d6ac44",  # Aktive Elemente, Primary Buttons
  "accent_primary_dim":  "#b8922f",  # Hover-Variante (etwas dunkler)
  "accent_primary_bg":   "#2a2410",  # Dezenter Gold-Hintergrund
  "accent_primary_glow": "#e9cf86",  # Extra-hell fuer Glow-Effekte

  # Sekundaer-Akzent: gedaempftes Stahlblau (komplementaer zu Gold)
  "accent_secondary":     "#6f8fc4",  # Genre-Badges, Tab-Akzente
  "accent_secondary_dim": "#557aac",  # Hover
  "accent_secondary_bg":  "#14213f",  # Dezenter blauer Hintergrund

  # Status-Farben (gedaempft, kein Neon)
  "accent_success": "#7bb091",  # Gedaempftes Gruen
  "accent_warning": "#e0b34a",  # Amber (distinkt vom Primaer-Gold)
  "accent_danger":  "#d47472",  # Gedaempftes Rot

  # Borders — Navy-Linien, Gold als Aktiv/Fokus
  "border":         "#26314f",  # Subtile 1px Linien
  "border_active":  "#d6ac44",  # Aktiver Border = Gold
  "border_focus":   "#d6ac44",  # Focus = Gold
  "border_danger":  "#d47472",
  "border_success": "#7bb091",
}

# ──────────────────────────────────────────────────────────────
# Genre-Farben — Neon auf Dark, neutrale Hintergruende
# Tupel: (Textfarbe, Hintergrundfarbe)
# ──────────────────────────────────────────────────────────────

# Gedaempfte Genre-Hues auf einheitlich navy-getoentem Hintergrund —
# distinkt, aber ohne Neon (passt zu Ink Navy Gold).
GENRE_COLORS = {
  "Psytrance":      ("#c98fd6", "#1c1836"),  # Gedaempftes Magenta-Violett
  "Tech House":     ("#6f9fd6", "#141f3a"),  # Stahlblau
  "Progressive":    ("#7bc4a0", "#12233a"),  # Gedaempftes Mint
  "Melodic Techno": ("#5fc4c4", "#12283a"),  # Gedaempftes Cyan
  "Techno":         ("#9fb0c0", "#161f34"),  # Blaugrau-Neutral
  "Deep House":     ("#d6a95c", "#241f10"),  # Gedaempftes Gold-Orange
  "Trance":         ("#a58fd6", "#1a1836"),  # Gedaempftes Violett
  "Drum & Bass":    ("#d47472", "#2a1420"),  # Gedaempftes Rot
  "Minimal":        ("#b0c46f", "#1c2418"),  # Gedaempftes Olive-Lime
}

# Standard-Farbe fuer unbekannte Genres
GENRE_DEFAULT = ("#8592b0", "#141d3a")

# ──────────────────────────────────────────────────────────────
# Risk-Styles fuer Mix Tips (bg_color, accent_color)
# ──────────────────────────────────────────────────────────────

RISK_STYLES = {
  "low":        ("#12233a", "#7bb091"),  # Gedaempftes Gruen
  "medium-low": ("#1c2418", "#b0c46f"),  # Gedaempftes Olive-Lime
  "medium":     ("#241f10", "#e0b34a"),  # Amber
  "high":       ("#2a1420", "#d47472"),  # Gedaempftes Rot
}
RISK_DEFAULT = ("#141d3a", "#8592b0")

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
  "intro":    "#7bb091",  # Gedaempftes Gruen
  "warmup":   "#9bc4a6",  # Helles Salbei
  "build":    "#e0b34a",  # Amber
  "peak":     "#d47472",  # Gedaempftes Rot
  "sustain":  "#a58fd6",  # Gedaempftes Violett
  "cooldown": "#6f9fd6",  # Stahlblau
}

PHASE_LABELS = {
  "intro":    "Intro \u2014 Sanfter Einstieg",
  "warmup":   "Warm-up \u2014 Behutsam anheizen",
  "build":    "Build-Up \u2014 Steigende Energie",
  "peak":     "Peak \u2014 Hoechste Intensitaet",
  "sustain":  "Sustain \u2014 Energie halten",
  "cooldown": "Cooldown \u2014 Ausklang",
}

# ──────────────────────────────────────────────────────────────
# Transition-Type Farben
# ──────────────────────────────────────────────────────────────

# Transition-Typ Beschreibungen fuer UI
TRANSITION_TYPE_LABELS: dict[str, str] = {
    "smooth_blend": "Smooth Blend",
    "bass_swap": "Bass Swap",
    "pro_eq_swap": "Pro EQ Swap",
    "breakdown_bridge": "Breakdown Bridge",
    "drop_cut": "Drop Cut",
    "filter_ride": "Filter Ride",
    "halftime_switch": "Halftime Switch",
    "echo_out": "Echo Out",
    "cold_cut": "Cold Cut",
}

TRANSITION_TYPE_DESCRIPTIONS: dict[str, str] = {
    "smooth_blend": (
        "Langer EQ-Blend ueber 16-32 Bars.\n"
        "Beide Tracks laufen parallel, Bass und\n"
        "Mids werden sanft uebergeblendet."
    ),
    "bass_swap": (
        "Schneller Bass-Tausch an einem Phrase-Anfang.\n"
        "Bass vom ausgehenden Track cutten,\n"
        "gleichzeitig Bass vom eingehenden Track reinbringen."
    ),
    "pro_eq_swap": (
        "Profi 3-Band-Isolator EQ Transition.\n"
        "Baesse werden in der Mitte (Phrasengrenze) getauscht,\n"
        "Mitten komplementaer gedrosselt (-6 dB Rule),\n"
        "Hoehen asymmetrisch und phasenrein uebergeblendet."
    ),
    "breakdown_bridge": (
        "Transition ueber den Breakdown eines Tracks.\n"
        "Nutze den ruhigen Teil um BPM oder\n"
        "Energie-Unterschiede zu ueberbruecken."
    ),
    "drop_cut": (
        "Harter Schnitt direkt am Drop.\n"
        "Der neue Track startet mit voller Energie\n"
        "fuer maximalen Impact auf dem Dancefloor."
    ),
    "filter_ride": (
        "Filter-basierter Uebergang.\n"
        "Highpass/Lowpass Filter nutzen um\n"
        "melodische Elemente ein- und auszublenden."
    ),
    "halftime_switch": (
        "Half/Double-Time Wechsel.\n"
        "Tempo-Verhaeltnis 2:1 — der Beat aendert sich,\n"
        "aber der Groove bleibt kompatibel.\n"
        "Am besten am Breakdown oder Build-Up."
    ),
    "echo_out": (
        "Echo/Delay-basierter Ausklang.\n"
        "Den ausgehenden Track mit Echo/Delay\n"
        "ausklingen lassen, waehrend der neue Track\n"
        "langsam eingeblendet wird."
    ),
    "cold_cut": (
        "Harter Cut ohne Blend.\n"
        "Die Tracks passen harmonisch nicht zusammen —\n"
        "kurzer Stop oder Effekt, dann neuer Track starten."
    ),
}

TRANSITION_TYPE_COLORS = {
  "smooth_blend":      "#7bb091",  # Gedaempftes Gruen
  "bass_swap":         "#6f9fd6",  # Stahlblau
  "pro_eq_swap":       "#d68fa8",  # Gedaempftes Rosa
  "breakdown_bridge":  "#e0b34a",  # Amber
  "drop_cut":          "#d47472",  # Gedaempftes Rot
  "filter_ride":       "#5fc4c4",  # Gedaempftes Cyan
  "halftime_switch":   "#a58fd6",  # Gedaempftes Violett
  "echo_out":          "#8f7fd6",  # Violett-Blau
  "cold_cut":          "#9fb0c0",  # Blaugrau
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


def get_7_scale_color(value: float) -> str:
  """
  Liefert eine feine 7-stufige Farbskala fuer Scores/Kompatibilitaeten (0.0 bis 1.0).
  Unterstuetzt edle HSL-Farben von Dunkelrot bis Dunkelgruehn.
  """
  # HIGH-Fix: NaN wuerde ueber min(1.0, nan)==1.0 faelschlich als "Exzellent"
  # gruen angezeigt (NaN-Vergleiche sind immer False). Ein undefinierter Score
  # ist der schlechteste Fall — konsistent zu score_color().
  if value != value:  # NaN
    return "#ff3b30"
  if value > 1.0:
    value = value / 100.0
  value = max(0.0, min(1.0, value))

  if value >= 0.90:
    return "#0f5223"  # Dunkelgruen (Exzellent)
  elif value >= 0.80:
    return "#248a3d"  # Gruen (Sehr passend)
  elif value >= 0.70:
    return "#5cd65c"  # Hellgruen (Milde harmonisch)
  elif value >= 0.55:
    return "#e6c300"  # Gelb (Neutral / Kompatibel)
  elif value >= 0.40:
    return "#ff8c00"  # Orange (Mittel-Kontrast)
  elif value >= 0.25:
    return "#ff4500"  # Orange-Rot (Kontrastierend)
  else:
    return "#ff3b30"  # Dunkelrot / Rot (Starker Kontrast)


def get_texture_label(value: float) -> str:
  """
  Uebersetzt den nackten Texture-Similarity Wert (0.0 bis 1.0) 
  in eine fuer DJs verstaendliche, qualitative Bezeichnung.
  """
  if value != value:  # NaN -> undefinierter Klang = schlechtester Fall
    return "Klang: Discord"
  value = max(0.0, min(1.0, value))
  if value >= 0.85:
    return "Klang: Identisch"
  elif value >= 0.70:
    return "Klang: Aehnlich"
  elif value >= 0.55:
    return "Klang: Harmonisch"
  elif value >= 0.40:
    return "Klang: Passend"
  elif value >= 0.25:
    return "Klang: Kontrast"
  else:
    return "Klang: Discord"  # Unruhiger Kontrast
