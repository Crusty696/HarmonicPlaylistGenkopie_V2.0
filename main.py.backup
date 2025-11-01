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
from hpg_core.playlist import generate_playlist, STRATEGIES, calculate_playlist_quality, calculate_enhanced_compatibility, EnergyDirection
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

    def __init__(self, folder_path, mode="Harmonic Flow", bpm_tolerance=3.0):
        super().__init__()
        self.folder_path = folder_path
        self.mode = mode
        self.bpm_tolerance = bpm_tolerance
        self.supported_formats = ('.wav', '.aiff', '.mp3', '.flac')

    def run(self):
        """The main work of the thread."""
        self.status_update.emit("Scanning for audio files...")
        
        audio_files = []
        for root, _, files in os.walk(self.folder_path):
            for file in files:
                if file.lower().endswith(self.supported_formats):
                    audio_files.append(os.path.join(root, file))
        
        total_files = len(audio_files)
        analyzed_tracks = []
        
        for i, file_path in enumerate(audio_files):
            if not os.path.exists(file_path):
                self.status_update.emit(f"Error: File not found at {os.path.basename(file_path)}. Skipping.")
                self.progress.emit(int(((i + 1) / total_files) * 100))
                continue
            track = analyze_track(file_path)
            if track:
                analyzed_tracks.append(track)
            else:
                self.status_update.emit(f"Error analyzing {os.path.basename(file_path)}. Skipping.")
            self.progress.emit(int(((i + 1) / total_files) * 100))

        self.status_update.emit("Generating playlist...")
        sorted_playlist = generate_playlist(analyzed_tracks, mode=self.mode, bpm_tolerance=self.bpm_tolerance)

        # Calculate quality metrics
        quality_metrics = calculate_playlist_quality(sorted_playlist, self.bpm_tolerance)
        self.status_update.emit("Calculating quality metrics...")

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
    """View 1: Start screen with folder selection."""
    folder_selected = pyqtSignal(str)
    strategy_selected = pyqtSignal(str)
    bpm_tolerance_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.info_label = QLabel("Drag and drop your music folder here or click the button below.")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

        self.select_folder_button = QPushButton("Select Music Folder")
        layout.addWidget(self.select_folder_button)

        self.strategy_label = QLabel("Select Playlist Strategy:")
        self.strategy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.strategy_label)

        self.strategy_combo = QComboBox(self)
        self.strategy_combo.addItems(STRATEGIES.keys())
        self.strategy_combo.setCurrentText("Harmonic Flow") # Default selection
        self.strategy_combo.currentIndexChanged.connect(self._emit_strategy_selection)
        layout.addWidget(self.strategy_combo)

        self.bpm_tolerance_label = QLabel("BPM Tolerance:")
        self.bpm_tolerance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.bpm_tolerance_label)

        self.bpm_tolerance_spinbox = QSpinBox(self)
        self.bpm_tolerance_spinbox.setRange(0, 10) # Example range
        self.bpm_tolerance_spinbox.setSingleStep(1) # Example step
        self.bpm_tolerance_spinbox.setValue(3) # Default value
        self.bpm_tolerance_spinbox.valueChanged.connect(self._emit_bpm_tolerance_changed)
        layout.addWidget(self.bpm_tolerance_spinbox)

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
            if os.path.isdir(path):
                self.folder_selected.emit(path)
                break

class AnalysisView(QWidget):
    """View 2: Analysis screen with progress bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar(self)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Analyzing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

class ResultView(QWidget):
    """View 3: Results screen with playlist table."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['#', 'Track Name', 'BPM', 'Key', 'Camelot'])
        layout.addWidget(self.table)

        self.export_button = QPushButton("Export as .m3u Playlist")
        layout.addWidget(self.export_button)

        self.restart_button = QPushButton("Start Over")
        layout.addWidget(self.restart_button)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Harmonic Playlist Generator")
        self.resize(800, 600)
        self.playlist = [] # To store the final playlist
        self.current_playlist_mode = "Harmonic Flow" # Default mode
        self.current_bpm_tolerance = 3.0 # Default BPM tolerance

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.start_view = StartView()
        self.analysis_view = AnalysisView()
        self.result_view = ResultView()

        self.stacked_widget.addWidget(self.start_view)
        self.stacked_widget.addWidget(self.analysis_view)
        self.stacked_widget.addWidget(self.result_view)

        self.stacked_widget.setCurrentWidget(self.start_view)

        # Connect signals
        self.start_view.select_folder_button.clicked.connect(self.select_folder)
        self.start_view.folder_selected.connect(self.start_analysis)
        self.start_view.strategy_selected.connect(self.set_playlist_strategy)
        self.start_view.bpm_tolerance_changed.connect(self.set_bpm_tolerance)
        self.result_view.restart_button.clicked.connect(self.restart_app)
        self.result_view.export_button.clicked.connect(self.export_playlist)

    def set_playlist_strategy(self, mode):
        self.current_playlist_mode = mode

    def set_bpm_tolerance(self, tolerance):
        self.current_bpm_tolerance = tolerance

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder_path:
            self.start_view.folder_selected.emit(folder_path)

    def start_analysis(self, folder_path):
        self.stacked_widget.setCurrentWidget(self.analysis_view)
        self.worker = AnalysisWorker(folder_path, mode=self.current_playlist_mode, bpm_tolerance=self.current_bpm_tolerance)
        self.worker.progress.connect(self.update_progress)
        self.worker.status_update.connect(self.update_status)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()

    def update_progress(self, value):
        self.analysis_view.progress_bar.setValue(value)

    def update_status(self, text):
        self.analysis_view.status_label.setText(text)

    def analysis_finished(self, playlist):
        self.playlist = playlist # Store the playlist
        self.result_view.table.setRowCount(len(self.playlist))
        for i, track in enumerate(self.playlist):
            self.result_view.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.result_view.table.setItem(i, 1, QTableWidgetItem(track.fileName))
            self.result_view.table.setItem(i, 2, QTableWidgetItem(str(track.bpm)))
            self.result_view.table.setItem(i, 3, QTableWidgetItem(f"{track.keyNote} {track.keyMode}"))
            self.result_view.table.setItem(i, 4, QTableWidgetItem(track.camelotCode))
        self.stacked_widget.setCurrentWidget(self.result_view)

    def export_playlist(self):
        if not self.playlist:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "", "M3U Playlist (*.m3u)")

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for track in self.playlist:
                        f.write(track.filePath + '\n')
                QMessageBox.information(self, "Export Successful", "Playlist exported successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Error exporting playlist: {e}")

    def restart_app(self):
        self.playlist = []
        self.stacked_widget.setCurrentWidget(self.start_view)

if __name__ == '__main__':
    # Clear shelve cache files before initializing for a clean integration test
    for ext in ['.bak', '.dat', '.dir', '.db']:
        if os.path.exists(CACHE_FILE + ext):
            os.remove(CACHE_FILE + ext)
    init_cache()

    # --- Integration Test --- #
    print("\n--- Starting Integration Test ---")
    real_aiff_files = [
        "C:/Users/david/Desktop/HarmonicPlaylistGenerator_v5/tests/test audio files/test_track.aiff",
        # Add more real AIFF file paths here if available
    ]
    # Use the same file multiple times if only one is available for testing playlist generation
    if len(real_aiff_files) < 3:
        dummy_file_paths = real_aiff_files * (3 // len(real_aiff_files) + 1)
    else:
        dummy_file_paths = real_aiff_files

    analyzed_dummy_tracks = []
    for path in dummy_file_paths:
        track = analyze_track(path)
        if track:
            analyzed_dummy_tracks.append(track)

    print(f"Analyzed {len(analyzed_dummy_tracks)} dummy tracks.")

    # Generate playlist with a specific mode and BPM tolerance
    generated_playlist = generate_playlist(analyzed_dummy_tracks, mode="Harmonic Flow", bpm_tolerance=5.0)

    print("Generated Playlist (Harmonic Flow):")
    for i, track in enumerate(generated_playlist):
        print(f"{i+1}. {track.fileName} - BPM: {track.bpm}, Key: {track.keyNote} {track.keyMode}, Camelot: {track.camelotCode}")
    print("--- Integration Test Finished ---\\n")
    # --- End Integration Test --- #

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())