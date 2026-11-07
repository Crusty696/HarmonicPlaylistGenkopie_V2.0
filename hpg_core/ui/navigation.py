"""Gemeinsame Navigation, Aktionen und Laufstatus der Anwendung."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from ..theme import COLORS, FONT_FAMILY, score_color
from ..run_state import RunState, RUN_STATE_GUIDANCE

class SidebarWidget(QWidget):
    """Vertikale Navigation — Ableton-inspiriert, 72px breit."""

    nav_changed = pyqtSignal(int)

    NAV_ITEMS = [
        ("LIB", "Bibliothek"),
        ("PL", "Playlist"),
        ("MIX", "Übergänge"),
        ("TL", "Zeitlinie"),
        ("QA", "Qualität"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(104)
        self.current_index = 0
        self.buttons = []
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            SidebarWidget {{
                background-color: {COLORS["bg_sidebar"]};
                border-right: 1px solid {COLORS["border"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        sidebar_tips = {
            "Bibliothek": "Bibliothek / Import:\nOrdner einlesen, Parameter einstellen, Audio-Features & KI-Analyse starten.",
            "Playlist": "Generierte Playlist:\nTabelle mit Tonarten (Camelot), Tempo (BPM), Uebergangstypen und KI-Stimmungen.",
            "Übergänge": "Misch-Empfehlungen & Vorschau:\nDetaillierte Uebergangs-Tipps (EQ, Filter) und 70s-Audio-Previews abspielen.",
            "Zeitlinie": "Visuelle Playlist-Zeitleiste:\nVerlauf von Energie, BPM und Tonartkompatibilitaet ueber die gesamte Playlist.",
            "Qualität": "Playlist-Qualitaetsanalyse:\nMetriken fuer harmonischen Fluss, Tempo-Stetigkeit, Energie-Verlauf und Genre-Mix."
        }

        for i, (icon, label) in enumerate(self.NAV_ITEMS):
            btn = QPushButton()
            btn.setFixedSize(104, 56)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(sidebar_tips.get(label, label))
            btn.clicked.connect(lambda checked, idx=i: self._on_nav_click(idx))
            self.buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Initiale Ansicht
        self._update_styles()

    def _on_nav_click(self, index):
        if index != self.current_index:
            self.current_index = index
            self._update_styles()
            self.nav_changed.emit(index)

    def set_active(self, index):
        """Programmatisch aktiven Tab setzen + Signal emittieren."""
        if 0 <= index < len(self.buttons):
            self.current_index = index
            self._update_styles()
            self.nav_changed.emit(index)

    def _update_styles(self):
        for i, btn in enumerate(self.buttons):
            icon, label = self.NAV_ITEMS[i]
            is_active = i == self.current_index

            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {COLORS["accent_primary_bg"]};
                        color: {COLORS["accent_primary"]};
                        border: none;
                        border-left: 3px solid {COLORS["accent_primary"]};
                        border-radius: 0px;
                        font-family: {FONT_FAMILY};
                        font-size: 11px;
                        font-weight: 600;
                        padding: 6px 2px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background-color: {COLORS["bg_hover"]};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {COLORS["text_dim"]};
                        border: none;
                        border-left: 3px solid transparent;
                        border-radius: 0px;
                        font-family: {FONT_FAMILY};
                        font-size: 11px;
                        font-weight: normal;
                        padding: 6px 2px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background-color: {COLORS["bg_hover"]};
                        color: {COLORS["text_primary"]};
                        border-left: 3px solid {COLORS["border"]};
                    }}
                """)
            # Text manuell setzen (QSS hat kein text-transform)
            btn.setText(f"{icon}\n{label}")


class ToolbarWidget(QWidget):
    """Obere Toolbar — App-Titel, Infos, Quick-Actions."""

    generate_clicked = pyqtSignal()
    export_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            ToolbarWidget {{
                background-color: {COLORS["bg_toolbar"]};
                border-bottom: 1px solid {COLORS["border"]};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)

        # Links: App-Titel
        from hpg_core import __version__ as hpg_version
        self.title_label = QLabel(f"HPG v{hpg_version}")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["accent_primary"]};
                font-family: {FONT_FAMILY};
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        layout.addWidget(self.title_label)

        # Mitte: Dynamische Info
        self.info_label = QLabel("Kein Ordner ausgewählt")
        self.info_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-family: {FONT_FAMILY};
                font-size: 11px;
            }}
        """)
        workflow_layout = QVBoxLayout()
        workflow_layout.setSpacing(2)
        workflow_layout.addWidget(self.info_label)
        self.workflow_label = QLabel(RUN_STATE_GUIDANCE[RunState.IDLE])
        self.workflow_label.setWordWrap(True)
        self.workflow_label.setAccessibleName("Aktueller Arbeitsschritt und nächste Aktion")
        workflow_layout.addWidget(self.workflow_label)
        layout.addLayout(workflow_layout, 1)

        # Quality-Badge (anfangs versteckt)
        self.quality_badge = QLabel("")
        self.quality_badge.setFixedHeight(24)
        self.quality_badge.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_bright"]};
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: 600;
                padding: 2px 10px;
                border-radius: 0px;
            }}
        """)
        self.quality_badge.hide()
        layout.addWidget(self.quality_badge)

        # Quick-Buttons
        self.generate_btn = QPushButton("GENERIEREN")
        self.generate_btn.setObjectName("btn_primary")
        self.generate_btn.setFixedHeight(28)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.clicked.connect(self.generate_clicked.emit)
        self.generate_btn.setToolTip("Playlist generieren (Strg+G)")
        layout.addWidget(self.generate_btn)

        self.export_btn = QPushButton("EXPORTIEREN")
        self.export_btn.setObjectName("btn_secondary")
        self.export_btn.setFixedHeight(28)
        self.export_btn.setEnabled(False)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.clicked.connect(self.export_clicked.emit)
        self.export_btn.setToolTip("Playlist exportieren (Strg+E)")
        layout.addWidget(self.export_btn)

    def set_info(self, text):
        self.info_label.setText(text)

    def set_run_state(self, state):
        self.workflow_label.setText(RUN_STATE_GUIDANCE.get(state, "Status unbekannt"))

    def set_quality(self, score):
        """Quality-Badge mit dynamischer Farbe anzeigen."""
        color = score_color(score)
        self.quality_badge.setText(f"Q: {score:.0%}")
        self.quality_badge.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_bright"]};
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: 600;
                padding: 2px 10px;
                border-radius: 0px;
                background-color: {color};
            }}
        """)
        self.quality_badge.show()

    def set_generate_enabled(self, enabled):
        self.generate_btn.setEnabled(enabled)

    def set_export_enabled(self, enabled):
        self.export_btn.setEnabled(enabled)


class StatusBarWidget(QWidget):
    """Untere Status-Leiste — Progress, Status-Text, Cancel."""

    cancel_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            StatusBarWidget {{
                background-color: {COLORS["bg_sidebar"]};
                border-top: 1px solid {COLORS["border"]};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # Status-Text
        self.status_label = QLabel("Bereit")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-family: {FONT_FAMILY};
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.status_label, 1)

        # Hinweis-Label: bleibt stehen, auch wenn set_status() den Statustext
        # ueberschreibt. Fuer Befunde, die den Lauf nicht abbrechen, aber das
        # Ergebnis erklaeren (z. B. unanalysierte Rekordbox-Tracks).
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["accent_warning"]};
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        self.hint_label.hide()
        layout.addWidget(self.hint_label)

        # Progress-Bar (konstant sichtbar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(240)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0.00%")
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS["bg_card"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                text-align: center;
                color: {COLORS["text_bright"]};
                font-family: {FONT_FAMILY};
                font-size: 12px;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS["accent_primary"]};
            }}
        """)
        layout.addWidget(self.progress_bar)

        # Cancel-Button (anfangs versteckt)
        self.cancel_btn = QPushButton("ABBRUCH")
        self.cancel_btn.setObjectName("btn_danger")
        self.cancel_btn.setFixedHeight(20)
        self.cancel_btn.setFixedWidth(60)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
        self.cancel_btn.hide()
        layout.addWidget(self.cancel_btn)

    def set_status(self, text):
        self.status_label.setText(text)

    def set_hint(self, text, tooltip=""):
        """Dauerhafter Hinweis neben dem Statustext."""
        self.hint_label.setText(text)
        self.hint_label.setToolTip(tooltip or text)
        self.hint_label.setVisible(bool(text))

    def clear_hint(self):
        self.hint_label.clear()
        self.hint_label.setToolTip("")
        self.hint_label.hide()

    def set_progress(self, value):
        bounded = max(0, min(100, int(value)))
        self.progress_bar.setValue(bounded)
        self.progress_bar.setFormat(f"{bounded}%")

    def show_progress(self):
        """Analyse gestartet — Progress und Cancel sichtbar."""
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0.00%")
        self.cancel_btn.show()

    def hide_progress(self):
        """Analyse beendet — Progress und Cancel verstecken."""
        self.cancel_btn.hide()
