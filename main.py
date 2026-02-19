from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QPushButton, QLabel, QStackedWidget, QFileDialog, QProgressBar,
                            QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, QMessageBox,
                            QGroupBox, QSlider, QCheckBox, QTabWidget, QTextEdit, QSplitter,
                            QHeaderView, QFrame, QGridLayout, QScrollArea, QToolTip)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QBrush
import html as html_mod
import os
import sys
import multiprocessing  # CRITICAL: Required for freeze_support()

from hpg_core.models import Track
from hpg_core.analysis import analyze_track
from hpg_core.parallel_analyzer import ParallelAnalyzer
from hpg_core.playlist import (
    generate_playlist,
    STRATEGIES,
    calculate_playlist_quality,
    calculate_enhanced_compatibility,
    EnergyDirection,
    compute_transition_recommendations,
    compute_set_timeline,
    get_set_timing_summary,
)
from hpg_core.exporters.m3u8_exporter import M3U8Exporter
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter
import shelve
from hpg_core.caching import init_cache, CACHE_FILE
import json
import time
from datetime import datetime

class AnalysisWorker(QThread):
    """Worker thread for running the analysis in the background."""
    progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    finished = pyqtSignal(list, dict)  # playlist, quality_metrics

    def __init__(self, folder_path, mode="Harmonic Flow Enhanced", bpm_tolerance=3.0, advanced_params=None):
        super().__init__()
        self.folder_path = folder_path
        self.mode = mode
        self.bpm_tolerance = bpm_tolerance
        self.advanced_params = advanced_params or {}
        self.supported_formats = ('.wav', '.aiff', '.mp3', '.flac')
        self._should_cancel = False

    def request_cancel(self):
        """Cooperative cancel — setzt Flag, das in run() geprueft wird."""
        self._should_cancel = True

    def run(self):
        """The main work of the thread - now with multi-core processing."""
        try:
            self.status_update.emit("Scanning for audio files...")

            # Scan for audio files
            audio_files = []
            for root, _, files in os.walk(self.folder_path):
                for file in files:
                    if file.lower().endswith(self.supported_formats):
                        audio_files.append(os.path.join(root, file))

            total_files = len(audio_files)
            if total_files == 0:
                self.status_update.emit("ERROR: No audio files found in selected folder!")
                self.finished.emit([], {})
                return

            self.status_update.emit(f"Found {total_files} audio files. Starting analysis...")

            # Progress callback for parallel analyzer
            last_update_time = 0

            def progress_callback(current, total, status_msg):
                """Forward progress updates to GUI with throttling"""
                nonlocal last_update_time
                current_time = time.time() * 1000  # Convert to ms

                # Throttle updates: Max every 100ms or on completion
                if (current_time - last_update_time > 100) or (current >= total):
                    self.progress.emit(int((current / total) * 100))
                    self.status_update.emit(status_msg)
                    last_update_time = current_time

                # Cooperative cancel check
                if self._should_cancel:
                    raise InterruptedError("Analysis cancelled by user")

            # Use ParallelAnalyzer for multi-core processing with smart scaling
            try:
                analyzer = ParallelAnalyzer()  # Auto-detect optimal core count (smart scaling)
                analyzed_tracks = analyzer.analyze_files(audio_files, progress_callback=progress_callback)
            except InterruptedError:
                self.status_update.emit("Analysis cancelled.")
                self.finished.emit([], {})
                return
            except Exception as e:
                self.status_update.emit(f"ERROR during analysis: {str(e)}")
                self.finished.emit([], {})
                return

            if not analyzed_tracks:
                self.status_update.emit("ERROR: No tracks were successfully analyzed.")
                self.finished.emit([], {})
                return

            self.status_update.emit(f"Analyzed {len(analyzed_tracks)} tracks. Generating playlist...")

            try:
                sorted_playlist = generate_playlist(
                    analyzed_tracks,
                    mode=self.mode,
                    bpm_tolerance=self.bpm_tolerance,
                    advanced_params=self.advanced_params
                )
            except Exception as e:
                self.status_update.emit(f"ERROR generating playlist: {str(e)}")
                self.finished.emit([], {})
                return

            if not sorted_playlist:
                self.status_update.emit("ERROR: Playlist generation returned empty result.")
                self.finished.emit([], {})
                return

            # Calculate quality metrics
            self.status_update.emit("Calculating quality metrics...")
            try:
                quality_metrics = calculate_playlist_quality(sorted_playlist, self.bpm_tolerance)
            except Exception as e:
                self.status_update.emit(f"Warning: Quality metrics failed: {str(e)}")
                quality_metrics = {}

            self.status_update.emit(f"Complete! {len(sorted_playlist)} tracks in playlist.")
            self.finished.emit(sorted_playlist, quality_metrics)

        except InterruptedError:
            self.status_update.emit("Analysis cancelled.")
            self.finished.emit([], {})
        except Exception as e:
            self.status_update.emit(f"FATAL ERROR: {str(e)}")
            self.finished.emit([], {})


class AdvancedParametersWidget(QWidget):
    """Widget for algorithm-specific advanced parameters."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Energy Direction Control
        energy_group = QGroupBox("Energy Direction (Emotional Journey)")
        energy_group.setToolTip(
            "Steuert den Energie-Verlauf der Playlist.\n"
            "Bestimmt, wie sich die Intensitaet der Tracks\n"
            "ueber die gesamte Playlist entwickelt."
        )
        energy_layout = QVBoxLayout(energy_group)

        self.energy_direction = QComboBox()
        self.energy_direction.addItems(["Auto", "Build Up", "Cool Down", "Maintain"])
        self.energy_direction.setCurrentText("Auto")
        self.energy_direction.setToolTip(
            "Auto: Algorithmus waehlt automatisch den besten Verlauf\n"
            "Build Up: Energie steigt kontinuierlich (Opening → Peak)\n"
            "Cool Down: Energie faellt ab (Peak → Closing)\n"
            "Maintain: Energie bleibt auf gleichem Level"
        )
        energy_layout.addWidget(QLabel("Energy Flow Direction:"))
        energy_layout.addWidget(self.energy_direction)

        # Peak Position Control
        self.peak_position_slider = QSlider(Qt.Orientation.Horizontal)
        self.peak_position_slider.setRange(40, 80)
        self.peak_position_slider.setValue(70)
        self.peak_position_slider.setToolTip(
            "Wo soll der energetische Hoehepunkt der Playlist liegen?\n"
            "40% = frueh (kurzes Warm-Up)\n"
            "70% = klassisch (langes Build-Up, kurzes Cool-Down)\n"
            "80% = spaet (maximale Spannung bis zum Ende)"
        )
        self.peak_position_label = QLabel("Peak Position: 70%")
        self.peak_position_slider.valueChanged.connect(
            lambda v: self.peak_position_label.setText(f"Peak Position: {v}%"))

        energy_layout.addWidget(self.peak_position_label)
        energy_layout.addWidget(self.peak_position_slider)

        layout.addWidget(energy_group)

        # Harmonic Strictness
        harmony_group = QGroupBox("Harmonic Mixing")
        harmony_group.setToolTip(
            "Einstellungen fuer harmonisches Mixing.\n"
            "Harmonisches Mixing nutzt den Camelot-Wheel,\n"
            "um Tracks mit kompatiblen Tonarten zu verbinden."
        )
        harmony_layout = QVBoxLayout(harmony_group)

        self.harmonic_strictness = QSlider(Qt.Orientation.Horizontal)
        self.harmonic_strictness.setRange(1, 10)
        self.harmonic_strictness.setValue(7)
        self.harmonic_strictness.setToolTip(
            "Wie streng soll die harmonische Kompatibilitaet sein?\n"
            "1-3: Locker – erlaubt groessere Tonart-Spruenge\n"
            "4-6: Moderat – bevorzugt kompatible Tonarten\n"
            "7-10: Streng – nur perfekte Camelot-Matches"
        )
        self.harmony_label = QLabel("Harmonic Strictness: 7/10")
        self.harmonic_strictness.valueChanged.connect(
            lambda v: self.harmony_label.setText(f"Harmonic Strictness: {v}/10"))

        harmony_layout.addWidget(self.harmony_label)
        harmony_layout.addWidget(self.harmonic_strictness)

        self.allow_experimental = QCheckBox("Allow Experimental Transitions")
        self.allow_experimental.setChecked(True)
        self.allow_experimental.setToolTip(
            "Erlaubt kreative Tonart-Wechsel jenseits des Camelot-Wheels.\n"
            "Aktiviert: Auch Energy-Boost und Mood-Change Uebergaenge moeglich\n"
            "Deaktiviert: Nur sichere Camelot-kompatible Uebergaenge"
        )
        harmony_layout.addWidget(self.allow_experimental)

        layout.addWidget(harmony_group)

        # Genre Mixing
        genre_group = QGroupBox("Genre Flow")
        genre_group.setToolTip(
            "Steuert, wie Genres in der Playlist gemischt werden.\n"
            "Die App erkennt automatisch das Genre jedes Tracks\n"
            "und kann aehnliche Genres bevorzugt zusammen sortieren."
        )
        genre_layout = QVBoxLayout(genre_group)

        self.genre_mixing = QCheckBox("Enable Genre Transitions")
        self.genre_mixing.setChecked(True)
        self.genre_mixing.setToolTip(
            "Aktiviert: Genre-Aehnlichkeit fliesst in die Playlist-Sortierung ein\n"
            "Deaktiviert: Genre wird ignoriert, nur BPM/Key/Energy zaehlen"
        )
        genre_layout.addWidget(self.genre_mixing)

        self.genre_weight = QSlider(Qt.Orientation.Horizontal)
        self.genre_weight.setRange(0, 100)
        self.genre_weight.setValue(30)
        self.genre_weight.setToolTip(
            "Wie stark soll Genre-Aehnlichkeit die Sortierung beeinflussen?\n"
            "0%: Genre wird komplett ignoriert\n"
            "30%: Moderate Gewichtung (empfohlen)\n"
            "100%: Genre ist der wichtigste Faktor"
        )
        self.genre_weight_label = QLabel("Genre Similarity Weight: 30%")
        self.genre_weight.valueChanged.connect(
            lambda v: self.genre_weight_label.setText(f"Genre Similarity Weight: {v}%"))

        genre_layout.addWidget(self.genre_weight_label)
        genre_layout.addWidget(self.genre_weight)

        layout.addWidget(genre_group)

    def get_parameters(self):
        """Return current parameter values as dict."""
        return {
            'energy_direction': self.energy_direction.currentText(),
            'peak_position': self.peak_position_slider.value(),
            'harmonic_strictness': self.harmonic_strictness.value(),
            'allow_experimental': self.allow_experimental.isChecked(),
            'genre_mixing': self.genre_mixing.isChecked(),
            'genre_weight': self.genre_weight.value() / 100.0
        }


class StartView(QWidget):
    """Enhanced View 1: Start screen with folder selection and advanced controls."""
    folder_selected = pyqtSignal(str)
    strategy_selected = pyqtSignal(str)
    bpm_tolerance_changed = pyqtSignal(float)
    advanced_params_changed = pyqtSignal(dict)
    start_analysis = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.current_folder = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # Left side - Basic controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Folder selection
        folder_group = QGroupBox("Music Library")
        folder_layout = QVBoxLayout(folder_group)

        self.info_label = QLabel("📁 Drag and drop your music folder here\nor click the button below.")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("QLabel { color: #666; font-size: 12px; padding: 20px; border: 2px dashed #ccc; border-radius: 8px; }")
        self.info_label.setToolTip(
            "Waehle den Ordner mit deinen Audio-Dateien.\n"
            "Unterstuetzte Formate: WAV, AIFF, MP3, FLAC\n"
            "Unterordner werden automatisch durchsucht."
        )
        folder_layout.addWidget(self.info_label)

        self.select_folder_button = QPushButton("📂 Select Music Folder")
        self.select_folder_button.setMinimumHeight(40)
        self.select_folder_button.setToolTip("Oeffnet einen Dialog zur Ordner-Auswahl (WAV, AIFF, MP3, FLAC)")
        folder_layout.addWidget(self.select_folder_button)

        left_layout.addWidget(folder_group)

        # Strategy selection
        strategy_group = QGroupBox("Playlist Strategy")
        strategy_layout = QVBoxLayout(strategy_group)

        self.strategy_combo = QComboBox()
        # Sort strategies with enhanced ones first
        enhanced_strategies = [k for k in STRATEGIES.keys() if "Enhanced" in k]
        basic_strategies = [k for k in STRATEGIES.keys() if "Enhanced" not in k]
        all_strategies = enhanced_strategies + basic_strategies
        self.strategy_combo.addItems(all_strategies)
        self.strategy_combo.setCurrentText("Harmonic Flow Enhanced")
        self.strategy_combo.currentIndexChanged.connect(self._emit_strategy_selection)
        self.strategy_combo.setToolTip(
            "Waehle den Algorithmus fuer die Playlist-Generierung.\n"
            "'Enhanced'-Varianten nutzen Look-Ahead und Backtracking\n"
            "fuer bessere Ergebnisse. Details stehen in der Beschreibung unten."
        )

        strategy_layout.addWidget(QLabel("Algorithm:"))
        strategy_layout.addWidget(self.strategy_combo)

        # Add strategy descriptions
        self.strategy_description = QLabel()
        self.strategy_description.setWordWrap(True)
        self.strategy_description.setStyleSheet("QLabel { color: #666; font-size: 10px; }")
        self._update_strategy_description()
        self.strategy_combo.currentTextChanged.connect(self._update_strategy_description)
        strategy_layout.addWidget(self.strategy_description)

        left_layout.addWidget(strategy_group)

        # BPM Tolerance
        bpm_group = QGroupBox("BPM Tolerance")
        bpm_layout = QVBoxLayout(bpm_group)

        self.bpm_tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.bpm_tolerance_slider.setRange(1, 15)
        self.bpm_tolerance_slider.setValue(3)
        self.bpm_tolerance_slider.setToolTip(
            "Maximale BPM-Differenz zwischen aufeinanderfolgenden Tracks.\n"
            "±3 BPM: Streng – nur sehr aehnliches Tempo (empfohlen)\n"
            "±6 BPM: Moderat – leichte Tempo-Wechsel erlaubt\n"
            "±10+ BPM: Locker – grosse Tempo-Spruenge moeglich\n\n"
            "Half/Double-Time wird automatisch erkannt:\n"
            "z.B. 140 BPM ↔ 70 BPM gelten als kompatibel."
        )
        self.bpm_label = QLabel("±3 BPM")
        self.bpm_tolerance_slider.valueChanged.connect(self._update_bpm_label)
        self.bpm_tolerance_slider.valueChanged.connect(self._emit_bpm_tolerance_changed)

        bpm_layout.addWidget(self.bpm_label)
        bpm_layout.addWidget(self.bpm_tolerance_slider)

        left_layout.addWidget(bpm_group)

        # Start button
        self.start_button = QPushButton("🎵 Generate Playlist")
        self.start_button.setMinimumHeight(50)
        self.start_button.setToolTip(
            "Startet die Audio-Analyse und Playlist-Generierung.\n"
            "Alle Tracks werden analysiert (BPM, Key, Energy, Genre, MFCC)\n"
            "und dann nach dem gewaehlten Algorithmus sortiert.\n\n"
            "Multi-Core-Verarbeitung: nutzt alle verfuegbaren CPU-Kerne."
        )
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.start_button.setEnabled(False)  # Enabled when folder selected
        self.start_button.clicked.connect(self.start_analysis.emit)
        left_layout.addWidget(self.start_button)

        # Right side - Advanced parameters
        right_widget = QScrollArea()
        self.advanced_params = AdvancedParametersWidget()
        right_widget.setWidget(self.advanced_params)
        right_widget.setWidgetResizable(True)
        right_widget.setMaximumWidth(350)

        # Add to main layout
        main_layout.addWidget(left_widget, 1)
        main_layout.addWidget(right_widget, 0)

    def _update_strategy_description(self):
        """Update strategy description based on selection."""
        strategy = self.strategy_combo.currentText()
        descriptions = {
            "Harmonic Flow Enhanced": "Advanced harmonic mixing with look-ahead optimization and backtracking to avoid local optima. Best for professional DJ sets.",
            "Harmonic Flow": "Basic harmonic mixing using Camelot wheel. Good for maintaining musical coherence.",
            "Peak-Time Enhanced": "Multi-peak arrangement with harmonic smoothing. Perfect for club sets and dance floors.",
            "Peak-Time": "Single peak arrangement building energy to a climax. Great for parties.",
            "Emotional Journey": "Four-phase progression (Opening → Building → Peak → Resolution). Creates emotional storytelling.",
            "Genre Flow": "Smooth transitions between similar genres while maintaining energy. Good for mixed collections.",
            "Energy Wave": "Alternating high/low energy creates dynamic listening experience.",
            "Warm-Up": "Gradual BPM increase from low to high energy. Perfect for opening sets.",
            "Cool-Down": "Gradual BPM decrease from high to low energy. Ideal for closing sets.",
            "Consistent": "Minimal BPM/energy jumps with harmonic compatibility. Smooth background listening."
        }
        description = descriptions.get(strategy, "No description available.")
        self.strategy_description.setText(description)

    def _update_bpm_label(self, value):
        self.bpm_label.setText(f"±{value} BPM")

    def _emit_strategy_selection(self):
        self.strategy_selected.emit(self.strategy_combo.currentText())

    def _emit_bpm_tolerance_changed(self, value):
        self.bpm_tolerance_changed.emit(float(value))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            # Normalize path separators for cross-platform consistency
            path = os.path.normpath(path)
            if os.path.isdir(path):
                self.set_folder_path(path)
                break

    def set_folder_path(self, path):
        """Programmatically set folder path."""
        if os.path.isdir(path):
            # W8: Pruefen ob Ordner lesbar ist
            if not os.access(path, os.R_OK):
                self.info_label.setText(f"⚠️ No read permission: {os.path.basename(path)}")
                self.info_label.setStyleSheet("QLabel { color: #e53935; font-size: 12px; padding: 20px; border: 2px solid #e53935; border-radius: 8px; }")
                return
            self.current_folder = path
            self.folder_selected.emit(path)
            self.start_button.setEnabled(True)
            self.info_label.setText(f"📁 Selected: {os.path.basename(path)}")
            self.info_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 12px; padding: 20px; border: 2px solid #4CAF50; border-radius: 8px; }")

    def get_advanced_parameters(self):
        """Get advanced parameters from the widget."""
        return self.advanced_params.get_parameters()

    def get_current_settings(self):
        """Get all current settings."""
        return {
            'folder': self.current_folder,
            'strategy': self.strategy_combo.currentText(),
            'bpm_tolerance': float(self.bpm_tolerance_slider.value()),
            'advanced_params': self.get_advanced_parameters()
        }


class EnhancedAnalysisView(QWidget):
    """Enhanced View 2: Analysis screen with better progress feedback."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Title
        title = QLabel("🎵 Analyzing Your Music Collection")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("QLabel { font-size: 18px; font-weight: bold; margin-bottom: 20px; }")
        layout.addWidget(title)

        # Progress bar with enhanced styling
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimumHeight(30)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #ccc;
                border-radius: 15px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 13px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Status label with better styling
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("QLabel { color: #666; font-size: 12px; margin-top: 10px; }")
        layout.addWidget(self.status_label)

        # Time estimate
        self.time_label = QLabel("")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("QLabel { color: #999; font-size: 10px; }")
        layout.addWidget(self.time_label)

        # Cancel button
        self.cancel_button = QPushButton("Cancel Analysis")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                margin-top: 20px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        self.cancel_button.setToolTip(
            "Bricht die laufende Analyse ab.\n"
            "Bereits analysierte Tracks bleiben im Cache\n"
            "und muessen nicht erneut analysiert werden."
        )
        layout.addWidget(self.cancel_button)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self, text):
        self.status_label.setText(text)


class EnhancedResultView(QWidget):
    """Enhanced View 3: Results screen with quality metrics and advanced features."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.playlist = []
        self.quality_metrics = {}
        self.transition_recommendations = []
        self.bpm_tolerance = 3.0
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Header with quality metrics
        header_layout = QHBoxLayout()

        # Title
        title = QLabel("🎵 Generated Playlist")
        title.setStyleSheet("QLabel { font-size: 18px; font-weight: bold; }")
        header_layout.addWidget(title)

        # Quality metrics display
        self.quality_widget = QWidget()
        self.quality_layout = QHBoxLayout(self.quality_widget)
        self.quality_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.quality_widget)

        main_layout.addLayout(header_layout)

        # Main content area with tabs
        self.tab_widget = QTabWidget()

        # Playlist tab
        playlist_tab = QWidget()
        playlist_layout = QVBoxLayout(playlist_tab)

        # Enhanced table with drag-and-drop
        self.table = QTableWidget()
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels([
            '#', 'Track Name', 'Artist', 'Duration', 'BPM', 'Key', 'Camelot',
            'Energy', 'Genre', 'Genre %', 'Mix In', 'Mix Out', 'Transition Score'
        ])

        # Tooltips fuer Spaltenheader
        header_tooltips = [
            "Position in der Playlist.\nDrag & Drop zum Umsortieren.",
            "Dateiname des Audio-Tracks.",
            "Interpret (aus ID3-Tag oder Dateiname).",
            "Gesamtlaenge des Tracks (Minuten:Sekunden).",
            (
                "Beats Per Minute – das Tempo des Tracks.\n"
                "Half/Double-Time wird automatisch erkannt:\n"
                "z.B. 140 BPM ↔ 70 BPM sind kompatibel."
            ),
            (
                "Musikalische Tonart (z.B. C Major, A Minor).\n"
                "Wird automatisch per Audio-Analyse erkannt."
            ),
            (
                "Camelot-Code fuer harmonisches Mixing.\n"
                "Kompatible Uebergaenge: gleiche Zahl,\n"
                "±1 auf dem Camelot-Wheel, oder A↔B Wechsel.\n"
                "Beispiel: 8A → 8A, 8A → 9A, 8A → 8B"
            ),
            (
                "Energie-Level des Tracks (0-100).\n"
                "Berechnet aus Lautstaerke, Onset-Rate und\n"
                "spektraler Energie. Hoeher = intensiver."
            ),
            (
                "Automatisch erkanntes Genre.\n"
                "Basiert auf BPM, Spektral-Features und\n"
                "ID3-Tags. 9 Genres: Psytrance, Tech House,\n"
                "Progressive, Melodic Techno, Techno,\n"
                "Deep House, Trance, Drum & Bass, Minimal."
            ),
            (
                "Konfidenz der Genre-Erkennung (0-100%).\n"
                "Hoeher = sicherer erkannt.\n"
                "Unter 30%: 'Unknown' als Genre."
            ),
            (
                "Mix-In-Punkt: Wo der naechste Track\n"
                "eingeblendet werden sollte (Zeit + Bars).\n"
                "Basiert auf Intro/Outro-Erkennung und\n"
                "Phrase-Alignment (8-Bar-Raster)."
            ),
            (
                "Mix-Out-Punkt: Wo dieser Track\n"
                "ausgeblendet werden sollte (Zeit + Bars).\n"
                "Der Uebergang zum naechsten Track\n"
                "beginnt hier."
            ),
            (
                "Kompatibilitaets-Score zum vorherigen Track (0-100%).\n"
                "Berechnet aus: Tonart-Kompatibilitaet, BPM-Differenz,\n"
                "Energie-Unterschied und Genre-Aehnlichkeit.\n\n"
                "Gruen (≥80%): Perfekter Uebergang\n"
                "Orange (≥60%): Guter Uebergang\n"
                "Rot (<60%): Schwieriger Uebergang"
            ),
        ]
        for col, tip in enumerate(header_tooltips):
            item = self.table.horizontalHeaderItem(col)
            if item:
                item.setToolTip(tip)

        # Enable drag and drop reordering
        self.table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # Configure table appearance
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Set column widths
        self.table.setColumnWidth(0, 40)   # #
        self.table.setColumnWidth(1, 180)  # Track Name
        self.table.setColumnWidth(2, 120)  # Artist
        self.table.setColumnWidth(3, 60)   # Duration
        self.table.setColumnWidth(4, 60)   # BPM
        self.table.setColumnWidth(5, 80)   # Key
        self.table.setColumnWidth(6, 70)   # Camelot
        self.table.setColumnWidth(7, 60)   # Energy
        self.table.setColumnWidth(8, 100)  # Genre
        self.table.setColumnWidth(9, 60)   # Genre %
        self.table.setColumnWidth(10, 70)  # Mix In
        self.table.setColumnWidth(11, 70)  # Mix Out

        # Connect row change signal to update numbering
        self.table.model().rowsMoved.connect(self._on_rows_moved)

        playlist_layout.addWidget(self.table)

        # Drag and drop instructions
        drag_info = QLabel("💡 Tip: Drag and drop rows to reorder tracks. Transition scores will update automatically.")
        drag_info.setStyleSheet("QLabel { color: #666; font-size: 10px; font-style: italic; margin: 5px; }")
        playlist_layout.addWidget(drag_info)

        # Buttons
        button_layout = QHBoxLayout()

        self.export_button = QPushButton("💾 Export as M3U Playlist")
        self.export_button.setMinimumHeight(40)
        self.export_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)

        self.preview_button = QPushButton("🎧 Preview Transitions")
        self.preview_button.setMinimumHeight(40)
        self.preview_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)

        self.restart_button = QPushButton("🔄 Start Over")
        self.restart_button.setMinimumHeight(40)
        self.restart_button.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #757575;
            }
        """)

        # Tooltips fuer Buttons
        self.export_button.setToolTip(
            "Exportiert die Playlist als M3U-Datei.\n"
            "M3U kann in Rekordbox, Traktor, Serato\n"
            "und den meisten Mediaplayern importiert werden."
        )
        self.preview_button.setToolTip(
            "Zeigt eine Vorschau der Uebergaenge zwischen\n"
            "aufeinanderfolgenden Tracks. Hilfreich um\n"
            "kritische Stellen vor dem Export zu pruefen."
        )
        self.restart_button.setToolTip(
            "Zurueck zum Startbildschirm.\n"
            "Die aktuelle Playlist geht verloren,\n"
            "analysierte Tracks bleiben im Cache."
        )

        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.preview_button)
        button_layout.addWidget(self.restart_button)
        playlist_layout.addLayout(button_layout)

        self.tab_widget.addTab(playlist_tab, "Playlist")

        # Analytics tab
        analytics_tab = QWidget()
        analytics_layout = QVBoxLayout(analytics_tab)

        self.analytics_text = QTextEdit()
        self.analytics_text.setReadOnly(True)
        analytics_layout.addWidget(self.analytics_text)

        self.tab_widget.addTab(analytics_tab, "Quality Analysis")

        # Mix recommendations tab
        mix_tab = QWidget()
        mix_layout = QVBoxLayout(mix_tab)

        self.mix_scroll = QScrollArea()
        self.mix_scroll.setWidgetResizable(True)
        mix_layout.addWidget(self.mix_scroll)

        self.mix_container = QWidget()
        self.mix_container_layout = QVBoxLayout(self.mix_container)
        self.mix_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.mix_scroll.setWidget(self.mix_container)

        self.tab_widget.addTab(mix_tab, "Mix Tips")

        # Set Timing tab
        timing_tab = QWidget()
        timing_layout = QVBoxLayout(timing_tab)

        self.timing_text = QTextEdit()
        self.timing_text.setReadOnly(True)
        timing_layout.addWidget(self.timing_text)

        self.tab_widget.addTab(timing_tab, "Set Timing")

        # Tooltips fuer Tab-Header
        self.tab_widget.setTabToolTip(0,
            "Die generierte Playlist mit allen Track-Details.\n"
            "Drag & Drop zum Umsortieren, Export als M3U."
        )
        self.tab_widget.setTabToolTip(1,
            "Detaillierte Qualitaets-Analyse der Playlist.\n"
            "Zeigt Scores fuer Harmonie, Energie und BPM-Flow\n"
            "sowie Verbesserungsvorschlaege."
        )
        self.tab_widget.setTabToolTip(2,
            "Konkrete Mix-Tipps fuer jeden Uebergang.\n"
            "Empfohlene Techniken, Cue-Points und\n"
            "Hinweise fuer schwierige Stellen."
        )
        self.tab_widget.setTabToolTip(3,
            "Zeitliche Planung des Sets.\n"
            "Zeigt Timeline, Peak-Position,\n"
            "Energie-Phasen und Ueberlappungen\n"
            "fuer ein realistisches DJ-Set."
        )

        main_layout.addWidget(self.tab_widget)

    def set_playlist_data(self, playlist, quality_metrics, transition_recommendations=None, bpm_tolerance=3.0):
        """Set playlist data and quality metrics."""
        self.playlist = playlist
        self.quality_metrics = quality_metrics
        self.bpm_tolerance = bpm_tolerance
        if transition_recommendations is None:
            self.transition_recommendations = compute_transition_recommendations(
                playlist, bpm_tolerance=self.bpm_tolerance
            )
        else:
            self.transition_recommendations = transition_recommendations

        # Update quality metrics display
        self._update_quality_display()

        # Populate table with performance optimization
        self.table.setUpdatesEnabled(False)  # Disable updates during population
        self.table.setRowCount(len(playlist))

        for i, track in enumerate(playlist):
            # Calculate transition score for this track
            transition_score = 0
            if i > 0:
                prev_track = playlist[i-1]
                compatibility = calculate_enhanced_compatibility(
                    prev_track, track, self.bpm_tolerance
                )
                transition_score = int(compatibility.overall_score * 100)

            # Genre-Daten vorbereiten
            detected_genre = getattr(track, 'detected_genre', 'Unknown') or 'Unknown'
            genre_confidence = getattr(track, 'genre_confidence', 0.0) or 0.0

            # Use faster item creation
            items = [
                QTableWidgetItem(str(i + 1)),
                QTableWidgetItem(track.fileName),
                QTableWidgetItem(track.artist),
                QTableWidgetItem(f"{int(track.duration // 60)}:{int(track.duration % 60):02d}"),
                QTableWidgetItem(f"{track.bpm:.1f}"),
                QTableWidgetItem(f"{track.keyNote} {track.keyMode}"),
                QTableWidgetItem(track.camelotCode),
                QTableWidgetItem(str(track.energy)),
            ]

            for col, item in enumerate(items):
                self.table.setItem(i, col, item)

            # Genre-Spalte mit Farb-Badge
            genre_colors = {
                "Psytrance": ("#9C27B0", "#F3E5F5"),       # Lila
                "Tech House": ("#1976D2", "#E3F2FD"),       # Blau
                "Progressive": ("#388E3C", "#E8F5E9"),      # Gruen
                "Melodic Techno": ("#00897B", "#E0F2F1"),   # Teal
            }
            genre_item = QTableWidgetItem(detected_genre)
            fg_color, bg_color = genre_colors.get(detected_genre, ("#757575", "#F5F5F5"))
            genre_item.setForeground(QColor(fg_color))
            genre_item.setBackground(QColor(bg_color))
            self.table.setItem(i, 8, genre_item)

            # Genre Confidence
            conf_item = QTableWidgetItem(f"{genre_confidence * 100:.0f}%" if genre_confidence > 0 else "-")
            self.table.setItem(i, 9, conf_item)

            # Mix In / Mix Out
            mix_in_item = QTableWidgetItem(f"{int(track.mix_in_point // 60):02d}:{int(track.mix_in_point % 60):02d} ({track.mix_in_bars} bars)")
            mix_out_item = QTableWidgetItem(f"{int(track.mix_out_point // 60):02d}:{int(track.mix_out_point % 60):02d} ({track.mix_out_bars} bars)")
            self.table.setItem(i, 10, mix_in_item)
            self.table.setItem(i, 11, mix_out_item)

            # Color-code transition score
            score_item = QTableWidgetItem(f"{transition_score}%")
            if transition_score >= 80:
                score_item.setBackground(QColor("#4CAF50"))  # Green
            elif transition_score >= 60:
                score_item.setBackground(QColor("#FF9800"))  # Orange
            else:
                score_item.setBackground(QColor("#f44336"))  # Red
            score_item.setForeground(QColor("white"))
            self.table.setItem(i, 12, score_item)
            
        self.table.setUpdatesEnabled(True)  # Re-enable updates
        # Update analytics
        self._update_analytics()
        self._update_mix_recommendations()
        self._update_set_timing()

    def _update_quality_display(self):
        """Update the quality metrics display."""
        # Clear existing widgets
        while self.quality_layout.count():
            child = self.quality_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.quality_metrics:
            return

        # Create quality metric labels
        metrics = [
            ("Overall", self.quality_metrics.get('overall_score', 0)),
            ("Harmony", self.quality_metrics.get('harmonic_flow', 0)),
            ("Energy", self.quality_metrics.get('energy_consistency', 0)),
            ("BPM Flow", self.quality_metrics.get('bpm_smoothness', 0))
        ]

        # Tooltips fuer Quality-Metriken
        metric_tooltips = {
            "Overall": (
                "Gesamtqualitaet der Playlist (0-100%).\n"
                "Gewichteter Durchschnitt aus Harmonie,\n"
                "Energie-Konsistenz und BPM-Flow.\n\n"
                "Gruen (≥80%): Exzellent\n"
                "Orange (≥60%): Gut\n"
                "Rot (<60%): Verbesserungswuerdig"
            ),
            "Harmony": (
                "Harmonischer Flow (0-100%).\n"
                "Misst wie gut die Tonarten aufeinanderfolgender\n"
                "Tracks zusammenpassen (Camelot-Kompatibilitaet).\n"
                "Hoeher = mehr Uebergaenge im gleichen Key-Bereich."
            ),
            "Energy": (
                "Energie-Konsistenz (0-100%).\n"
                "Misst ob die Energie-Level der Tracks\n"
                "sinnvoll aufeinander aufbauen.\n"
                "Hoeher = smoothere Energie-Uebergaenge."
            ),
            "BPM Flow": (
                "BPM-Smoothness (0-100%).\n"
                "Misst wie sanft die Tempo-Uebergaenge sind.\n"
                "Kleine BPM-Spruenge = hoher Score.\n"
                "Half/Double-Time wird beruecksichtigt."
            ),
        }

        for name, value in metrics:
            metric_widget = QWidget()
            metric_layout = QVBoxLayout(metric_widget)
            metric_layout.setContentsMargins(10, 5, 10, 5)

            # Tooltip fuer das gesamte Metrik-Widget
            metric_widget.setToolTip(metric_tooltips.get(name, ""))

            # Score
            score_label = QLabel(f"{value:.0%}")
            score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            score_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 16px;
                    font-weight: bold;
                    color: {'#4CAF50' if value >= 0.8 else '#FF9800' if value >= 0.6 else '#f44336'};
                }}
            """)

            # Name
            name_label = QLabel(name)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet("QLabel { font-size: 10px; color: #666; }")

            metric_layout.addWidget(score_label)
            metric_layout.addWidget(name_label)

            self.quality_layout.addWidget(metric_widget)

    def _update_analytics(self):
        """Update the analytics tab content."""
        if not self.quality_metrics:
            return

        analytics_text = f"""
<h3>Playlist Quality Analysis</h3>

<h4>Overall Scores</h4>
<ul>
<li><b>Overall Quality:</b> {self.quality_metrics.get('overall_score', 0):.1%}</li>
<li><b>Harmonic Flow:</b> {self.quality_metrics.get('harmonic_flow', 0):.1%}</li>
<li><b>Energy Consistency:</b> {self.quality_metrics.get('energy_consistency', 0):.1%}</li>
<li><b>BPM Smoothness:</b> {self.quality_metrics.get('bpm_smoothness', 0):.1%}</li>
</ul>

<h4>Detailed Metrics</h4>
<ul>
<li><b>Average Harmonic Score:</b> {self.quality_metrics.get('avg_harmonic_score', 0):.1f}/100</li>
<li><b>Average Energy Jump:</b> {self.quality_metrics.get('avg_energy_jump', 0):.1f}</li>
<li><b>Average BPM Jump:</b> {self.quality_metrics.get('avg_bpm_jump', 0):.1f}</li>
</ul>

<h4>Recommendations</h4>
"""

        # Add recommendations based on scores
        overall_score = self.quality_metrics.get('overall_score', 0)
        if overall_score >= 0.8:
            analytics_text += "<p><b>Excellent playlist!</b> This playlist has great flow and should work well for DJ sets.</p>"
        elif overall_score >= 0.6:
            analytics_text += "<p><b>Good playlist.</b> Minor improvements could be made, but this should work well.</p>"
        else:
            analytics_text += "<p><b>Consider adjustments.</b> You might want to try a different algorithm or adjust BMP tolerance.</p>"

        # Specific recommendations
        if self.quality_metrics.get('harmonic_flow', 0) < 0.6:
            analytics_text += "<p>• Try increasing harmonic strictness or using 'Harmonic Flow Enhanced' algorithm.</p>"

        if self.quality_metrics.get('energy_consistency', 0) < 0.6:
            analytics_text += "<p>• Consider using 'Emotional Journey' or 'Energy Wave' for better energy flow.</p>"

        if self.quality_metrics.get('bpm_smoothness', 0) < 0.6:
            analytics_text += "<p>• Try increasing BPM tolerance or using 'Consistent' algorithm.</p>"

        self.analytics_text.setHtml(analytics_text)

    def _update_set_timing(self):
      """Update the Set Timing tab with timeline data."""
      if not self.playlist:
        self.timing_text.setHtml("<p>Keine Playlist vorhanden.</p>")
        return

      timeline = compute_set_timeline(self.playlist)
      summary = get_set_timing_summary(timeline)

      # Farben fuer Energie-Phasen
      phase_colors = {
        "intro": "#2196F3",     # Blau
        "build": "#FF9800",     # Orange
        "peak": "#f44336",      # Rot
        "sustain": "#9C27B0",   # Lila
        "cooldown": "#4CAF50",  # Gruen
      }
      phase_labels = {
        "intro": "Intro — Sanfter Einstieg",
        "build": "Build-Up — Steigende Energie",
        "peak": "Peak — Hoechste Intensitaet",
        "sustain": "Sustain — Energie halten",
        "cooldown": "Cooldown — Ausklang",
      }

      # Header
      html = "<h3>⏱ Set Timeline</h3>"

      # Uebersicht
      overflow = summary.get("overflow_seconds", 0)
      overflow_sign = "+" if overflow > 0 else ""
      html += f"""
      <table style="margin: 10px 0; border-collapse: collapse;">
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Gesamtzeit:</td>
          <td style="padding: 4px 12px;">{summary['total_time']}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Zielzeit:</td>
          <td style="padding: 4px 12px;">{summary['target_time']}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Abweichung:</td>
          <td style="padding: 4px 12px;">{overflow_sign}{overflow:.0f}s ({summary['overflow']})</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Peak Track:</td>
          <td style="padding: 4px 12px;">{html_mod.escape(str(summary.get('peak_track', '-')))}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Peak bei:</td>
          <td style="padding: 4px 12px;">{summary.get('peak_time', '-')}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Tracks:</td>
          <td style="padding: 4px 12px;">{summary['track_count']}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Ø Dauer/Track:</td>
          <td style="padding: 4px 12px;">{summary['avg_track_duration']}</td>
        </tr>
      </table>
      """

      # Phasen-Uebersicht
      phase_breakdown = summary.get("phase_breakdown", {})
      if phase_breakdown:
        html += "<h4>Energie-Phasen</h4>"
        html += "<table style='margin: 8px 0; border-collapse: collapse;'>"
        for phase, count in phase_breakdown.items():
          color = phase_colors.get(phase, "#666")
          label = phase_labels.get(phase, phase)
          html += (
            f"<tr>"
            f"<td style='padding: 3px 10px;'>"
            f"<span style='color: {color}; font-weight: bold;'>●</span></td>"
            f"<td style='padding: 3px 10px;'>{label}</td>"
            f"<td style='padding: 3px 10px; text-align: right;'>"
            f"{count} Track{'s' if count != 1 else ''}</td>"
            f"</tr>"
          )
        html += "</table>"

      # Timeline-Details
      html += "<h4>Timeline</h4>"
      html += (
        "<table style='margin: 8px 0; border-collapse: collapse; width: 100%;'>"
        "<tr style='background: #f0f0f0; font-weight: bold;'>"
        "<td style='padding: 5px 8px;'>#</td>"
        "<td style='padding: 5px 8px;'>Track</td>"
        "<td style='padding: 5px 8px;'>Start</td>"
        "<td style='padding: 5px 8px;'>Ende</td>"
        "<td style='padding: 5px 8px;'>Dauer</td>"
        "<td style='padding: 5px 8px;'>Overlap</td>"
        "<td style='padding: 5px 8px;'>Phase</td>"
        "</tr>"
      )

      for i, entry in enumerate(timeline.entries):
        start_m = int(entry.start_time // 60)
        start_s = int(entry.start_time % 60)
        end_m = int(entry.end_time // 60)
        end_s = int(entry.end_time % 60)
        dur_m = int(entry.playing_duration // 60)
        dur_s = int(entry.playing_duration % 60)
        phase = entry.energy_phase
        color = phase_colors.get(phase, "#666")

        peak_marker = " ⭐" if entry.is_peak else ""
        bg = "#fff3e0" if entry.is_peak else ("#f9f9f9" if i % 2 else "#fff")

        overlap_str = f"{entry.overlap_with_next:.0f}s" if entry.overlap_with_next > 0 else "—"
        html += (
          f"<tr style='background: {bg};'>"
          f"<td style='padding: 4px 8px;'>{i + 1}</td>"
          f"<td style='padding: 4px 8px;'>{html_mod.escape(str(entry.track.title))}{peak_marker}</td>"
          f"<td style='padding: 4px 8px;'>{start_m}:{start_s:02d}</td>"
          f"<td style='padding: 4px 8px;'>{end_m}:{end_s:02d}</td>"
          f"<td style='padding: 4px 8px;'>{dur_m}:{dur_s:02d}</td>"
          f"<td style='padding: 4px 8px;'>{overlap_str}</td>"
          f"<td style='padding: 4px 8px;'>"
          f"<span style='color: {color}; font-weight: bold;'>"
          f"{phase.capitalize()}</span></td>"
          f"</tr>"
        )

      html += "</table>"

      # Legende
      html += "<hr>"
      html += "<p style='color: #888; font-size: 11px;'>"
      html += "⭐ = Peak Track (hoechste Energie + optimale Position) | "
      html += "Overlap = Uebergangszeit zum naechsten Track"
      html += "</p>"

      self.timing_text.setHtml(html)

    def _clear_layout(self, layout):
        """Remove all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _update_mix_recommendations(self):
        """Populate the mix recommendations tab."""
        # W4: Batch-Update — verhindert Flackern bei vielen Widgets
        self.mix_scroll.setUpdatesEnabled(False)
        try:
            self._update_mix_recommendations_inner()
        finally:
            self.mix_scroll.setUpdatesEnabled(True)

    def _update_mix_recommendations_inner(self):
        """Inner method — creates mix recommendation widgets."""
        self._clear_layout(self.mix_container_layout)

        if not self.transition_recommendations:
            empty_label = QLabel("No transition tips available yet. Generate a playlist to view mix guidance.")
            empty_label.setStyleSheet("QLabel { color: #666; font-style: italic; margin: 12px; }")
            self.mix_container_layout.addWidget(empty_label)
            self.mix_container_layout.addStretch()
            return

        risk_styles = {
            "low": ("#e8f5e9", "#43a047"),
            "medium-low": ("#f1f8e9", "#7cb342"),
            "medium": ("#fff8e1", "#fb8c00"),
            "high": ("#ffebee", "#e53935"),
        }

        for rec in self.transition_recommendations:
            bg_color, accent_color = risk_styles.get(rec.risk_level, ("#eceff1", "#546e7a"))

            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_color};
                    border-radius: 8px;
                    border: 1px solid {accent_color};
                    padding: 12px;
                }}
            """)

            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(6)

            # Genre-Info im Titel wenn verfuegbar
            from_genre = getattr(rec.from_track, 'detected_genre', '') or ''
            to_genre = getattr(rec.to_track, 'detected_genre', '') or ''
            title_text = f"{rec.index + 1}. {rec.from_track.fileName} -> {rec.to_track.fileName}"
            title = QLabel(title_text)
            title.setStyleSheet("QLabel { font-size: 13px; font-weight: bold; color: #333; }")
            card_layout.addWidget(title)

            # Genre-Badge Zeile wenn Genre vorhanden
            if from_genre and from_genre != 'Unknown' and to_genre and to_genre != 'Unknown':
                genre_colors = {
                    "Psytrance": "#9C27B0", "Tech House": "#1976D2",
                    "Progressive": "#388E3C", "Melodic Techno": "#00897B",
                }
                from_color = genre_colors.get(from_genre, "#757575")
                to_color = genre_colors.get(to_genre, "#757575")
                genre_label = QLabel(
                    f'<span style="color: {from_color}; font-weight: bold;">{from_genre}</span>'
                    f' -> '
                    f'<span style="color: {to_color}; font-weight: bold;">{to_genre}</span>'
                )
                genre_label.setStyleSheet("QLabel { font-size: 11px; }")
                card_layout.addWidget(genre_label)

            # DJ-freundliche Risk-Labels statt technische Begriffe
            risk_labels = {
                "low": "✅ Smooth",
                "medium-low": "👍 Solid",
                "medium": "⚠️ Aufpassen",
                "high": "🔴 Riskant",
            }
            risk_display = risk_labels.get(rec.risk_level, rec.risk_level)
            summary = QLabel(
                f"{risk_display} | Score {rec.compatibility_score}/100 | "
                f"BPM {rec.bpm_delta:+.1f} | Energy {rec.energy_delta:+d}"
            )
            summary.setStyleSheet(f"QLabel {{ color: {accent_color}; font-weight: 600; }}")
            card_layout.addWidget(summary)

            # Transition-Typ Badge
            from hpg_core.playlist import TRANSITION_TYPE_LABELS, TRANSITION_TYPE_DESCRIPTIONS
            t_type = getattr(rec, 'transition_type', 'blend')
            t_label = TRANSITION_TYPE_LABELS.get(t_type, t_type)
            t_desc = TRANSITION_TYPE_DESCRIPTIONS.get(t_type, '')
            type_colors = {
                "smooth_blend": "#43a047", "bass_swap": "#1976D2",
                "breakdown_bridge": "#FF8F00", "drop_cut": "#D32F2F",
                "filter_ride": "#00897B", "halftime_switch": "#7B1FA2",
                "echo_out": "#5C6BC0", "cold_cut": "#546E7A",
            }
            t_color = type_colors.get(t_type, "#757575")
            type_badge = QLabel(f"🎚️ Empfohlene Technik: {t_label}")
            type_badge.setToolTip(t_desc)
            type_badge.setStyleSheet(
                f"QLabel {{ color: {t_color}; font-weight: bold; font-size: 12px; "
                f"background-color: rgba(0, 0, 0, 0.05); "
                f"border-radius: 4px; padding: 4px 8px; }}"
            )
            card_layout.addWidget(type_badge)

            timing = QLabel(
                f"Fade out {rec.fade_out_start:.1f}s -> {rec.fade_out_end:.1f}s | "
                f"Fade in starts {rec.fade_in_start:.1f}s | Mix entry {rec.mix_entry:.1f}s | "
                f"Overlap {rec.overlap:.1f}s"
            )
            timing.setStyleSheet("QLabel { color: #555; }")
            card_layout.addWidget(timing)

            # Notes in drei Kategorien aufsplitten:
            # 1. DJ Brain Mix-Technik (Mix:, EQ:, Transition:, !)
            # 2. DJ-Beschreibung (Tonart, BPM, Energie, Gesamtbewertung)
            # 3. Genre-Pair und Struktur-Infos
            notes_text = rec.notes or ""
            notes_parts = [p.strip() for p in notes_text.split(";") if p.strip()]

            dj_brain_parts = []  # Mix-Technik vom DJ Brain
            desc_parts = []      # Aussagekraeftige Beschreibung
            meta_parts = []      # Genre-Pair, Struktur

            for part in notes_parts:
                if part.startswith(("Mix:", "EQ:", "Transition:")):
                    dj_brain_parts.append(part)
                elif part.startswith("!"):
                    dj_brain_parts.append(part)
                elif part.startswith(("Ideal:", "Gut:", "Smooth:", "Riskant:",
                                      "Mutig:", "Standard:", "OK:", "Struktur:")):
                    # Structure-Notes vom DJ Brain
                    dj_brain_parts.append(part)
                elif part.startswith("[") and part.endswith("]"):
                    meta_parts.append(part)
                elif any(kw in part for kw in (
                    "Tonart", "BPM", "Energie", "Harmoni",
                    "Sichere", "Solide", "Machbar",
                    "Push", "stabil", "steigt", "faellt",
                    "Pitch", "ueberblend", "nahtlos", "allein", "mixbar",
                    "erfahren", "Clash",
                )):
                    desc_parts.append(part)
                else:
                    meta_parts.append(part)

            # DJ Brain Mix-Technik (blau hervorgehoben)
            if dj_brain_parts:
                dj_text = " | ".join(dj_brain_parts)
                dj_label = QLabel(f"🎛️ {dj_text}")
                dj_label.setWordWrap(True)
                dj_label.setStyleSheet(
                    "QLabel { color: #1565C0; font-weight: 600; "
                    "background-color: rgba(25, 118, 210, 0.08); "
                    "border-radius: 4px; padding: 4px 6px; }"
                )
                card_layout.addWidget(dj_label)

            # Aussagekraeftige Beschreibung (prominent angezeigt)
            if desc_parts:
                desc_text = " | ".join(desc_parts)
                desc_label = QLabel(desc_text)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet(
                    "QLabel { color: #333; font-size: 12px; "
                    "padding: 3px 0px; }"
                )
                card_layout.addWidget(desc_label)

            # Meta-Info (Genre-Pair, Struktur - dezent)
            if meta_parts:
                meta_text = " | ".join(meta_parts)
                meta_label = QLabel(meta_text)
                meta_label.setWordWrap(True)
                meta_label.setStyleSheet("QLabel { color: #777; font-size: 11px; }")
                card_layout.addWidget(meta_label)

            self.mix_container_layout.addWidget(card)

        self.mix_container_layout.addStretch()

    def _on_rows_moved(self, parent, start, end, destination, row):
        """Handle drag-and-drop reordering of tracks."""
        # Update the playlist order to match the table
        if not self.playlist:
            return

        # W2: O(N) Dict-Lookup statt O(N²) verschachtelter Loop
        track_by_name = {t.fileName: t for t in self.playlist}
        reordered_playlist = []
        for i in range(self.table.rowCount()):
            track_name_item = self.table.item(i, 1)
            if track_name_item:
                track = track_by_name.get(track_name_item.text())
                if track:
                    reordered_playlist.append(track)

        # Update the playlist
        self.playlist = reordered_playlist

        # Update numbering and recalculate transition scores
        self._update_table_after_reorder()

    def _update_table_after_reorder(self):
        """Update table numbering and transition scores after reordering."""
        for i in range(self.table.rowCount()):
            # Update row number
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

            # Recalculate transition score
            transition_score = 0
            if i > 0 and i < len(self.playlist):
                prev_track = self.playlist[i-1]
                current_track = self.playlist[i]
                compatibility = calculate_enhanced_compatibility(
                    prev_track, current_track, self.bpm_tolerance
                )
                transition_score = int(compatibility.overall_score * 100)

            # Update transition score with color coding
            score_item = QTableWidgetItem(f"{transition_score}%")
            if transition_score >= 80:
                score_item.setBackground(QColor("#4CAF50"))  # Green
            elif transition_score >= 60:
                score_item.setBackground(QColor("#FF9800"))  # Orange
            else:
                score_item.setBackground(QColor("#f44336"))  # Red
            score_item.setForeground(QColor("white"))

            self.table.setItem(i, 12, score_item)

        # Recalculate overall quality metrics for the reordered playlist
        self.quality_metrics = calculate_playlist_quality(self.playlist, self.bpm_tolerance)
        self._update_quality_display()
        self.transition_recommendations = compute_transition_recommendations(
            self.playlist, bpm_tolerance=self.bpm_tolerance
        )
        self._update_mix_recommendations()
        self._update_analytics()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Harmonic Playlist Generator v3.0")
        self.resize(1200, 800)
        self.playlist = []
        self.quality_metrics = {}
        self.current_playlist_mode = "Harmonic Flow Enhanced"
        self.current_bpm_tolerance = 3.0
        self.worker = None

        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # Create views
        self.start_view = StartView()
        self.analysis_view = EnhancedAnalysisView()
        self.result_view = EnhancedResultView()

        # Add views to stack
        self.stacked_widget.addWidget(self.start_view)
        self.stacked_widget.addWidget(self.analysis_view)
        self.stacked_widget.addWidget(self.result_view)

        # Start with the start view
        self.stacked_widget.setCurrentWidget(self.start_view)

    def connect_signals(self):
        # Start view signals
        self.start_view.select_folder_button.clicked.connect(self.select_folder)
        self.start_view.folder_selected.connect(self.folder_selected)
        self.start_view.strategy_selected.connect(self.set_playlist_strategy)
        self.start_view.bpm_tolerance_changed.connect(self.set_bpm_tolerance)
        self.start_view.start_analysis.connect(self.start_analysis)

        # Analysis view signals
        self.analysis_view.cancel_button.clicked.connect(self.cancel_analysis)

        # Result view signals
        self.result_view.restart_button.clicked.connect(self.restart_app)
        self.result_view.export_button.clicked.connect(self.export_playlist)
        self.result_view.preview_button.clicked.connect(self.preview_transitions)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder_path:
            self.start_view.set_folder_path(folder_path)

    def folder_selected(self, folder_path):
        """Handle folder selection."""
        pass  # StartView handles this internally now

    def set_playlist_strategy(self, mode):
        self.current_playlist_mode = mode

    def set_bpm_tolerance(self, tolerance):
        self.current_bpm_tolerance = tolerance

    def start_analysis(self):
        """Start the analysis process."""
        settings = self.start_view.get_current_settings()

        if not settings['folder']:
            QMessageBox.warning(self, "No Folder Selected", "Please select a music folder first.")
            return

        # K2: Start-Button deaktivieren um Doppelklick zu verhindern
        self.start_view.start_button.setEnabled(False)

        # W3: Progress-Bar zuruecksetzen
        self.analysis_view.progress_bar.setValue(0)

        # Switch to analysis view
        self.stacked_widget.setCurrentWidget(self.analysis_view)

        # Create and start worker
        self.worker = AnalysisWorker(
            folder_path=settings['folder'],
            mode=settings['strategy'],
            bpm_tolerance=settings['bpm_tolerance'],
            advanced_params=settings['advanced_params']
        )

        # Connect worker signals
        self.worker.progress.connect(self.analysis_view.update_progress)
        self.worker.status_update.connect(self.analysis_view.update_status)
        self.worker.finished.connect(self.analysis_finished)

        self.worker.start()

    def cancel_analysis(self):
        """Cancel the current analysis with cooperative shutdown."""
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            # Warte bis zu 5s auf sauberes Beenden
            if not self.worker.wait(5000):
                # Fallback: harter Terminate nur wenn cooperative cancel nicht greift
                self.worker.terminate()
                self.worker.wait()
        self.start_view.start_button.setEnabled(True)
        self.restart_app()

    def analysis_finished(self, playlist, quality_metrics):
        """Handle analysis completion."""
        # K2: Start-Button wieder aktivieren
        self.start_view.start_button.setEnabled(True)

        self.playlist = playlist
        self.quality_metrics = quality_metrics

        # Compute mix recommendations
        transition_plan = compute_transition_recommendations(
            playlist, bpm_tolerance=self.current_bpm_tolerance
        )

        # Update result view
        self.result_view.set_playlist_data(
            playlist,
            quality_metrics,
            transition_recommendations=transition_plan,
            bpm_tolerance=self.current_bpm_tolerance
        )

        # Switch to result view
        self.stacked_widget.setCurrentWidget(self.result_view)

    def export_playlist(self):
        """Export playlist in M3U8 or Rekordbox XML format."""
        if not self.playlist:
            QMessageBox.warning(self, "No Playlist", "No playlist to export. Please analyze audio files first.")
            return

        # Let user choose export format
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Playlist",
            f"HPG_Playlist_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "M3U8 Playlist (*.m3u8);;Rekordbox XML (*.xml);;All Files (*.*)"
        )

        if not file_path:
            return  # User cancelled

        try:
            # Determine format from filter or extension
            file_lower = file_path.lower()

            if selected_filter.startswith("Rekordbox") or file_lower.endswith('.xml'):
                # Export as Rekordbox XML
                self._export_rekordbox_xml(file_path)
            else:
                # Export as M3U8 (default)
                if not file_lower.endswith('.m3u8'):
                    file_path += '.m3u8'
                self._export_m3u8(file_path)

        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                               f"Failed to export playlist:\n{str(e)}\n\n"
                               f"Please check file permissions and try again.")

    def _export_m3u8(self, file_path: str):
        """Export playlist as M3U8 format."""
        try:
            exporter = M3U8Exporter()
            playlist_name = f"HPG - {self.current_playlist_mode}"
            exporter.export(self.playlist, file_path, playlist_name)

            QMessageBox.information(
                self, "Export Successful",
                f"M3U8 Playlist exported successfully!\n\n"
                f"Location: {file_path}\n"
                f"Tracks: {len(self.playlist)}\n"
                f"Format: M3U8 (Universal Compatible)\n\n"
                f"✅ Compatible with:\n"
                f"   • Rekordbox 5.x, 6.x, 7.x\n"
                f"   • Serato DJ Pro\n"
                f"   • Traktor Pro 3\n"
                f"   • Most DJ Software"
            )
        except Exception as e:
            raise Exception(f"M3U8 export failed: {e}")

    def _export_rekordbox_xml(self, file_path: str):
        """Export playlist as Rekordbox XML format."""
        try:
            exporter = RekordboxXMLExporter()
            playlist_name = f"HPG - {self.current_playlist_mode}"
            exporter.export(self.playlist, file_path, playlist_name)

            QMessageBox.information(
                self, "Export Successful",
                f"Rekordbox XML exported successfully!\n\n"
                f"Location: {file_path}\n"
                f"Tracks: {len(self.playlist)}\n"
                f"Format: Rekordbox XML (Professional)\n\n"
                f"✅ Included Metadata:\n"
                f"   • BPM & Key (Camelot → Rekordbox)\n"
                f"   • Mix In/Out Points (Memory Cues)\n"
                f"   • Artist, Title, Genre\n"
                f"   • Full track paths\n\n"
                f"📥 Import into Rekordbox:\n"
                f"   File → Import → rekordbox xml"
            )
        except ImportError:
            QMessageBox.critical(
                self, "Library Missing",
                "pyrekordbox library is not installed!\n\n"
                "Install with:\n"
                "pip install pyrekordbox\n\n"
                "Falling back to M3U8 export..."
            )
            # Fallback to M3U8
            m3u8_path = file_path.replace('.xml', '.m3u8')
            self._export_m3u8(m3u8_path)
        except Exception as e:
            raise Exception(f"Rekordbox XML export failed: {e}")

    def preview_transitions(self):
        """Show transition preview dialog."""
        if not self.playlist:
            return

        # This could open a dialog showing transition analysis
        # For now, show a simple message with transition info
        if len(self.playlist) < 2:
            QMessageBox.information(self, "Preview", "Need at least 2 tracks to show transitions.")
            return

        transitions_info = "Transition Analysis:\n\n"
        for i in range(len(self.playlist) - 1):
            current = self.playlist[i]
            next_track = self.playlist[i + 1]
            compatibility = calculate_enhanced_compatibility(current, next_track, self.current_bpm_tolerance)

            transitions_info += f"{i+1} → {i+2}: {os.path.basename(current.fileName)} → {os.path.basename(next_track.fileName)}\n"
            transitions_info += f"   Score: {compatibility.overall_score:.1%} (Harmonic: {compatibility.harmonic_score}/100)\n"
            transitions_info += f"   BPM: {current.bpm:.1f} → {next_track.bpm:.1f}\n"
            transitions_info += f"   Key: {current.camelotCode} → {next_track.camelotCode}\n\n"

        msg = QMessageBox(self)
        msg.setWindowTitle("Transition Preview")
        msg.setText("Transition Analysis")
        msg.setDetailedText(transitions_info)
        msg.exec()

    def restart_app(self):
        """Restart the application."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.playlist = []
        self.quality_metrics = {}
        self.stacked_widget.setCurrentWidget(self.start_view)


if __name__ == '__main__':
    # CRITICAL: Required for PyInstaller + multiprocessing on Windows
    # This MUST be the first line to prevent infinite process spawning
    multiprocessing.freeze_support()

    # Only clear cache if explicitly requested or on major version changes
    # Automatic clearing on every start is inefficient and can cause locking issues
    # init_cache() already handles version-based clearing safely with file locks
    pass

    init_cache()

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle('Fusion')

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())
