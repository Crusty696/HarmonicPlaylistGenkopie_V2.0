from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QPushButton, QLabel, QStackedWidget, QFileDialog, QProgressBar,
                            QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, QMessageBox,
                            QGroupBox, QSlider, QCheckBox, QTabWidget, QTextEdit, QSplitter,
                            QHeaderView, QFrame, QGridLayout, QScrollArea, QToolTip)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QBrush
import os
import sys

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
)
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

    def run(self):
        """The main work of the thread - now with multi-core processing."""
        self.status_update.emit("Scanning for audio files...")

        # Scan for audio files
        audio_files = []
        for root, _, files in os.walk(self.folder_path):
            for file in files:
                if file.lower().endswith(self.supported_formats):
                    audio_files.append(os.path.join(root, file))

        total_files = len(audio_files)
        self.status_update.emit(f"Found {total_files} audio files. Starting analysis...")

        # Progress callback for parallel analyzer
        def progress_callback(current, total, status_msg):
            """Forward progress updates to GUI"""
            self.progress.emit(int((current / total) * 100))
            self.status_update.emit(status_msg)

        # Use ParallelAnalyzer for multi-core processing
        analyzer = ParallelAnalyzer(max_workers=6)  # Use up to 6 cores as requested
        analyzed_tracks = analyzer.analyze_files(audio_files, progress_callback=progress_callback)

        if not analyzed_tracks:
            self.status_update.emit("No tracks were successfully analyzed.")
            self.finished.emit([], {})
            return

        self.status_update.emit("Generating playlist...")
        sorted_playlist = generate_playlist(analyzed_tracks, mode=self.mode, bpm_tolerance=self.bpm_tolerance)

        # Calculate quality metrics
        self.status_update.emit("Calculating quality metrics...")
        quality_metrics = calculate_playlist_quality(sorted_playlist, self.bpm_tolerance)

        self.finished.emit(sorted_playlist, quality_metrics)


class AdvancedParametersWidget(QWidget):
    """Widget for algorithm-specific advanced parameters."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Energy Direction Control
        energy_group = QGroupBox("Energy Direction (Emotional Journey)")
        energy_layout = QVBoxLayout(energy_group)

        self.energy_direction = QComboBox()
        self.energy_direction.addItems(["Auto", "Build Up", "Cool Down", "Maintain"])
        self.energy_direction.setCurrentText("Auto")
        energy_layout.addWidget(QLabel("Energy Flow Direction:"))
        energy_layout.addWidget(self.energy_direction)

        # Peak Position Control
        self.peak_position_slider = QSlider(Qt.Orientation.Horizontal)
        self.peak_position_slider.setRange(40, 80)
        self.peak_position_slider.setValue(70)
        self.peak_position_label = QLabel("Peak Position: 70%")
        self.peak_position_slider.valueChanged.connect(
            lambda v: self.peak_position_label.setText(f"Peak Position: {v}%"))

        energy_layout.addWidget(self.peak_position_label)
        energy_layout.addWidget(self.peak_position_slider)

        layout.addWidget(energy_group)

        # Harmonic Strictness
        harmony_group = QGroupBox("Harmonic Mixing")
        harmony_layout = QVBoxLayout(harmony_group)

        self.harmonic_strictness = QSlider(Qt.Orientation.Horizontal)
        self.harmonic_strictness.setRange(1, 10)
        self.harmonic_strictness.setValue(7)
        self.harmony_label = QLabel("Harmonic Strictness: 7/10")
        self.harmonic_strictness.valueChanged.connect(
            lambda v: self.harmony_label.setText(f"Harmonic Strictness: {v}/10"))

        harmony_layout.addWidget(self.harmony_label)
        harmony_layout.addWidget(self.harmonic_strictness)

        self.allow_experimental = QCheckBox("Allow Experimental Transitions")
        self.allow_experimental.setChecked(True)
        harmony_layout.addWidget(self.allow_experimental)

        layout.addWidget(harmony_group)

        # Genre Mixing
        genre_group = QGroupBox("Genre Flow")
        genre_layout = QVBoxLayout(genre_group)

        self.genre_mixing = QCheckBox("Enable Genre Transitions")
        self.genre_mixing.setChecked(True)
        genre_layout.addWidget(self.genre_mixing)

        self.genre_weight = QSlider(Qt.Orientation.Horizontal)
        self.genre_weight.setRange(0, 100)
        self.genre_weight.setValue(30)
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
        folder_layout.addWidget(self.info_label)

        self.select_folder_button = QPushButton("📂 Select Music Folder")
        self.select_folder_button.setMinimumHeight(40)
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
        self.bpm_label = QLabel("±3 BPM")
        self.bpm_tolerance_slider.valueChanged.connect(self._update_bpm_label)
        self.bpm_tolerance_slider.valueChanged.connect(self._emit_bpm_tolerance_changed)

        bpm_layout.addWidget(self.bpm_label)
        bpm_layout.addWidget(self.bpm_tolerance_slider)

        left_layout.addWidget(bpm_group)

        # Start button
        self.start_button = QPushButton("🎵 Generate Playlist")
        self.start_button.setMinimumHeight(50)
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
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            '#', 'Track Name', 'Artist', 'BPM', 'Key', 'Camelot', 'Energy', 'Mix In', 'Mix Out', 'Transition Score'
        ])

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
        self.table.setColumnWidth(3, 60)   # BPM
        self.table.setColumnWidth(4, 80)   # Key
        self.table.setColumnWidth(5, 70)   # Camelot
        self.table.setColumnWidth(6, 60)   # Energy
        self.table.setColumnWidth(7, 70)   # Mix In
        self.table.setColumnWidth(8, 70)   # Mix Out

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

        # Populate table
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

            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(track.fileName))
            self.table.setItem(i, 2, QTableWidgetItem(track.artist))
            self.table.setItem(i, 3, QTableWidgetItem(f"{track.bpm:.1f}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{track.keyNote} {track.keyMode}"))
            self.table.setItem(i, 5, QTableWidgetItem(track.camelotCode))
            self.table.setItem(i, 6, QTableWidgetItem(str(track.energy)))

            # Format mix points to MM:SS (Bar Nummer)
            mix_in_minutes = int(track.mix_in_point // 60)
            mix_in_seconds = int(track.mix_in_point % 60)
            formatted_mix_in = f"{mix_in_minutes:02d}:{mix_in_seconds:02d} ({track.mix_in_bars} bars)"

            mix_out_minutes = int(track.mix_out_point // 60)
            mix_out_seconds = int(track.mix_out_point % 60)
            formatted_mix_out = f"{mix_out_minutes:02d}:{mix_out_seconds:02d} ({track.mix_out_bars} bars)"

            self.table.setItem(i, 7, QTableWidgetItem(formatted_mix_in))
            self.table.setItem(i, 8, QTableWidgetItem(formatted_mix_out))

            # Color-code transition score
            score_item = QTableWidgetItem(f"{transition_score}%")
            if transition_score >= 80:
                score_item.setBackground(QColor("#4CAF50"))  # Green
            elif transition_score >= 60:
                score_item.setBackground(QColor("#FF9800"))  # Orange
            else:
                score_item.setBackground(QColor("#f44336"))  # Red
            score_item.setForeground(QColor("white"))

            self.table.setItem(i, 9, score_item)
                    # Update analytics
        self._update_analytics()
        self._update_mix_recommendations()

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

        for name, value in metrics:
            metric_widget = QWidget()
            metric_layout = QVBoxLayout(metric_widget)
            metric_layout.setContentsMargins(10, 5, 10, 5)

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

    def _clear_layout(self, layout):
        """Remove all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _update_mix_recommendations(self):
        """Populate the mix recommendations tab."""
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

            title = QLabel(f"{rec.index + 1}. {rec.from_track.fileName} → {rec.to_track.fileName}")
            title.setStyleSheet("QLabel { font-size: 13px; font-weight: bold; color: #333; }")
            card_layout.addWidget(title)

            summary = QLabel(
                f"Risk: {rec.risk_level.capitalize()} • Compatibility {rec.compatibility_score}% • "
                f"BPM Δ {rec.bpm_delta:+.1f} • Energy Δ {rec.energy_delta:+d}"
            )
            summary.setStyleSheet(f"QLabel {{ color: {accent_color}; font-weight: 600; }}")
            card_layout.addWidget(summary)

            timing = QLabel(
                f"Fade out {rec.fade_out_start:.1f}s → {rec.fade_out_end:.1f}s • "
                f"Fade in starts {rec.fade_in_start:.1f}s • Mix entry {rec.mix_entry:.1f}s • "
                f"Overlap {rec.overlap:.1f}s"
            )
            timing.setStyleSheet("QLabel { color: #555; }")
            card_layout.addWidget(timing)

            notes = QLabel(f"Notes: {rec.notes}")
            notes.setWordWrap(True)
            notes.setStyleSheet("QLabel { color: #444; }")
            card_layout.addWidget(notes)

            self.mix_container_layout.addWidget(card)

        self.mix_container_layout.addStretch()

    def _on_rows_moved(self, parent, start, end, destination, row):
        """Handle drag-and-drop reordering of tracks."""
        # Update the playlist order to match the table
        if not self.playlist:
            return

        # Reorder the playlist list to match the new table order
        reordered_playlist = []
        for i in range(self.table.rowCount()):
            # Get the track name from the table
            track_name_item = self.table.item(i, 1)
            if track_name_item:
                track_name = track_name_item.text()
                # Find the corresponding track in the playlist
                for track in self.playlist:
                    if track.fileName == track_name:
                        reordered_playlist.append(track)
                        break

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

            self.table.setItem(i, 9, score_item)

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
        self.setWindowTitle("Harmonic Playlist Generator v2.0")
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
        """Cancel the current analysis."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.restart_app()

    def analysis_finished(self, playlist, quality_metrics):
        """Handle analysis completion."""
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
        """Export playlist to M3U file."""
        if not self.playlist:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Playlist",
            f"playlist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m3u",
            "M3U Playlist (*.m3u)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for i, track in enumerate(self.playlist):
                        # Write extended info
                        duration = int(track.duration) if track.duration > 0 else -1
                        f.write(f"#EXTINF:{duration},{track.artist} - {track.title}\n")
                        f.write(track.filePath + '\n')

                QMessageBox.information(self, "Export Successful",
                                      f"Playlist exported successfully to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Error exporting playlist: {e}")

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
    # Clear shelve cache files before initializing for a clean integration test
    for ext in ['.bak', '.dat', '.dir', '.db']:
        if os.path.exists(CACHE_FILE + ext):
            os.remove(CACHE_FILE + ext)
    init_cache()

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle('Fusion')

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())
