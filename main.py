from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QStackedWidget,
    QFileDialog,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QMessageBox,
    QGroupBox,
    QSlider,
    QCheckBox,
    QTextEdit,
    QPlainTextEdit,
    QHeaderView,
    QFrame,
    QScrollArea,
    QStyledItemDelegate,
    QStyle,
    QRadioButton,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QThread,
    QUrl,
    QSize,
    QRect,
    QTimer,
    QObject,
)
from PyQt6.QtGui import (
    QColor,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import html as html_mod
import logging

# H1-Fix (Audit 2026-07-17): Modul-Logger — TransitionRenderWorker.run
# referenzierte `logger` ohne Definition (NameError im Fehlerpfad)
logger = logging.getLogger(__name__)


def resolve_transition_mix_points(transition) -> tuple[float, float, float]:
    """Loest die effektiven Mix-Punkte einer Transition auf.

    Paar-spezifische DJ-Brain-Werte (adjusted_*, Sentinel -1.0) haben Vorrang
    vor den per-Track-Werten. Audit 2026-07-17: vorher war dieses Muster
    dreifach kopiert (Render-Worker, Preview-Widget, Anzeige).

    Returns:
        (mix_out_a, mix_in_b, crossfade_seconds)
    """
    dj = transition.dj_rec
    mix_out = (
        dj.adjusted_mix_out_a
        if dj and dj.adjusted_mix_out_a >= 0.0
        else float(transition.from_track.mix_out_point or 0)
    )
    mix_in = (
        dj.adjusted_mix_in_b
        if dj and dj.adjusted_mix_in_b >= 0.0
        else float(transition.to_track.mix_in_point or 0)
    )
    crossfade = (
        dj.overlap_seconds
        if dj and dj.overlap_seconds > 0
        else float(transition.overlap or 16.0)
    )
    return mix_out, mix_in, crossfade
import os
import re
import sys
import tempfile
import multiprocessing  # CRITICAL: Required for freeze_support()

from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip
from hpg_core.ai_engine import fetch_ai_analysis
from hpg_core.parallel_analyzer import ParallelAnalyzer
from hpg_core.playlist import (
    generate_playlist,
    STRATEGIES,
    calculate_playlist_quality,
    calculate_enhanced_compatibility,
    compute_transition_recommendations,
    compute_set_timeline,
    get_set_timing_summary,
)
from hpg_core.exporters.m3u8_exporter import M3U8Exporter
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter
from hpg_core.caching import init_cache
from hpg_core.logging_config import setup_logging
from hpg_core.theme import (
    COLORS,
    GENRE_COLORS,
    GENRE_DEFAULT,
    RISK_STYLES,
    RISK_DEFAULT,
    RISK_LABELS,
    PHASE_COLORS,
    PHASE_LABELS,
    TRANSITION_TYPE_COLORS,
    TRANSITION_TYPE_LABELS,
    TRANSITION_TYPE_DESCRIPTIONS,
    score_color,
    html_style_block,
    apply_dark_theme,
    FONT_FAMILY,
)
from hpg_core.error_reporter import get_error_reporter
from hpg_core.playlist_security import validate_playlist_security, sanitize_playlist
import time
from datetime import datetime



class AIAnalysisWorker(QThread):
    """Worker thread for running AI analysis in the background."""
    ai_finished = pyqtSignal(str, dict)  # (track_path, metadata)

    def __init__(self, playlist: list, provider: str = None, model: str = None,
                 base_url: str = None, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.provider = provider
        self.model = model
        self.base_url = base_url  # Voller Endpoint vom ai_launcher (Port dynamisch)
        self._should_cancel = False

    def request_cancel(self):
        self._should_cancel = True

    def _ensure_ready(self):
        """
        Stellt sicher dass der Provider laeuft und ein Modell gewaehlt ist.
        Laeuft bereits im Worker-Thread → blockierend erlaubt, blockiert UI nicht.
        Wird nur aufgerufen wenn der Detect-Worker beim Start nichts geliefert hat
        (z.B. Server war aus) oder der Endpoint inzwischen weggefallen ist.
        """
        if self.base_url:
            return
        try:
            from hpg_core import ai_launcher
            status = ai_launcher.detect_and_start(
                preferred=self.provider, preferred_model=self.model
            )
            if status and status.running:
                self.base_url = status.base_url
                self.provider = status.name
                if status.active_model:
                    self.model = status.active_model
        except Exception:
            pass

    def run(self):
        import logging
        import os
        logger = logging.getLogger("hpg_core.ai_engine")
        self._ensure_ready()
        logger.info(f"Starting AI Mood Tagging using {self.provider} (Model: {self.model})...")
        for i, track in enumerate(self.playlist):
            if self._should_cancel:
                logger.info("AI Mood Tagging cancelled by user.")
                break
            try:
                filename = os.path.basename(track.filePath)
                logger.info(f"[{i+1}/{len(self.playlist)}] AI analyzing track: '{filename}'...")
                from hpg_core.ai_engine import fetch_ai_analysis
                ai_data = fetch_ai_analysis(
                    track, provider=self.provider, model=self.model, url=self.base_url
                )
                if ai_data:
                    self.ai_finished.emit(track.filePath, ai_data)
                else:
                    logger.warning(f"AI returned empty result for track '{filename}'.")
            except Exception as e:
                logger.error(f"Error during AI analysis for track '{os.path.basename(track.filePath)}': {e}")
        logger.info("AI Mood Tagging complete.")


class AIDetectWorker(QThread):
    """
    Erkennt & startet AI-Provider im Hintergrund (Ollama -> LM Studio),
    fragt real installierte Modelle ab. Blockiert die UI nie.
    """
    detected = pyqtSignal(object)  # AIProviderStatus oder None

    def __init__(self, preferred: str = None, preferred_model: str = None, parent=None):
        super().__init__(parent)
        self.preferred = preferred
        self.preferred_model = preferred_model

    def run(self):
        status = None
        try:
            from hpg_core import ai_launcher
            status = ai_launcher.detect_and_start(
                preferred=self.preferred, preferred_model=self.preferred_model
            )
        except Exception:
            status = None
        self.detected.emit(status)


class AITestWorker(QThread):
    """
    Worker thread for testing the AI provider connection and model response.
    Sends a test request and measures latency.
    """
    test_finished = pyqtSignal(bool, str, str, float)  # (success, response_or_error, model_name, latency)

    def __init__(self, provider: str, model: str, base_url: str, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.model = model
        self.base_url = base_url

    def run(self):
        import time
        import requests
        start_time = time.time()

        url = self.base_url
        if not url:
            if self.provider == "LM Studio":
                url = "http://localhost:1234/v1/chat/completions"
            else:
                url = "http://localhost:11434/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Respond with the word OK and nothing else."}
            ]
        }

        try:
            # timeout=(connect timeout, read timeout). Modell laden kann dauern, daher 30s.
            resp = requests.post(url, json=payload, timeout=(3.0, 30.0))
            resp.raise_for_status()
            resp_json = resp.json()
            latency = time.time() - start_time

            if "choices" in resp_json and len(resp_json["choices"]) > 0:
                response_content = resp_json["choices"][0]["message"]["content"].strip()
                responded_model = resp_json.get("model", self.model)
                self.test_finished.emit(True, response_content, responded_model, latency)
            else:
                self.test_finished.emit(False, "Keine 'choices' in der Antwort des Providers.", self.model, latency)
        except Exception as e:
            latency = time.time() - start_time
            self.test_finished.emit(False, str(e), self.model, latency)


class AIPullWorker(QThread):
    """
    Worker thread for pulling a model from Ollama in the background.
    """
    pull_finished = pyqtSignal(bool, str)  # (success, error_message)

    def __init__(self, model: str, parent=None):
        super().__init__(parent)
        self.model = model

    def run(self):
        try:
            from hpg_core import ai_launcher
            success = ai_launcher.ollama_pull(self.model)
            if success:
                self.pull_finished.emit(True, "")
            else:
                self.pull_finished.emit(False, f"Modell '{self.model}' konnte nicht geladen werden. Bitte stelle sicher, dass Ollama läuft und der Modellname korrekt ist.")
        except Exception as e:
            self.pull_finished.emit(False, str(e))


class AnalysisWorker(QThread):
    """Worker thread for running the analysis in the background."""

    progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    phase_changed = pyqtSignal(int, str)  # step_index, state ("inactive", "working", "completed")
    finished = pyqtSignal(list, dict)  # playlist, quality_metrics

    def __init__(
        self,
        folder_path,
        mode="Harmonic Flow",
        bpm_tolerance=3.0,
        advanced_params=None,
    ):
        super().__init__()
        self.folder_path = folder_path
        self.mode = mode
        self.bpm_tolerance = bpm_tolerance
        self.advanced_params = advanced_params or {}
        self.supported_formats = (".wav", ".aiff", ".mp3", ".flac")
        self._should_cancel = False

    def request_cancel(self):
        """Cooperative cancel — setzt Flag, das in run() geprueft wird."""
        self._should_cancel = True

    def run(self):
        """The main work of the thread - now with multi-core processing."""
        import logging
        logger = logging.getLogger("hpg_core.analysis")
        try:
            self.phase_changed.emit(0, "working")
            self.status_update.emit("Scanning for audio files...")
            logger.info(f"Scanning directory: {self.folder_path}")
            logger.info("Scanning for audio files...")

            # Scan for audio files
            audio_files = []
            for root, _, files in os.walk(self.folder_path):
                if self._should_cancel:
                    raise InterruptedError("Analysis cancelled by user")
                for file in files:
                    if file.lower().endswith(self.supported_formats):
                        audio_files.append(os.path.join(root, file))

            total_files = len(audio_files)
            if total_files == 0:
                self.phase_changed.emit(0, "inactive")
                self.status_update.emit(
                    "ERROR: No audio files found in selected folder!"
                )
                logger.error(f"No compatible audio files ({', '.join(self.supported_formats)}) found in selected folder!")
                self.finished.emit([], {})
                return

            self.phase_changed.emit(0, "completed")
            self.phase_changed.emit(1, "working")
            self.status_update.emit(
                f"Found {total_files} audio files. Starting analysis..."
            )
            logger.info(f"Scan complete: Found {total_files} audio files.")
            logger.info("Starting parallel feature extraction...")

            # Progress callback for parallel analyzer
            last_update_time = 0

            def progress_callback(current, total, status_msg):
                """Forward progress updates to GUI with throttling"""
                nonlocal last_update_time
                current_time = time.time() * 1000  # Convert to ms

                # Detail-Log ins Terminal schreiben
                import logging
                logger = logging.getLogger("hpg_core.parallel_analyzer")
                logger.info(f"[{current}/{total}] {status_msg}")

                # Throttle updates: Max every 100ms or on completion
                if (current_time - last_update_time > 100) or (current >= total):
                    float_percent = (current / total) * 100.0
                    self.progress.emit(int(float_percent * 100))
                    self.status_update.emit(status_msg)
                    last_update_time = current_time

                # Cooperative cancel check
                if self._should_cancel:
                    raise InterruptedError("Analysis cancelled by user")

            # Use ParallelAnalyzer for multi-core processing with smart scaling
            try:
                analyzer = (
                    ParallelAnalyzer()
                )  # Auto-detect optimal core count (smart scaling)
                analyzed_tracks = analyzer.analyze_files(
                    audio_files, progress_callback=progress_callback
                )
            except InterruptedError:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit("Analysis cancelled.")
                self.finished.emit([], {})
                return
            except Exception as e:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit(f"ERROR during analysis: {str(e)}")
                get_error_reporter().log_error(
                    "analysis", str(e), {"folder": self.folder_path}
                )
                self.finished.emit([], {})
                return

            # Security-Gate: defekte Eintraege und Tracks ueber den Limits
            # (Dateigroesse/Dauer) entfernen, Playlist-Groesse deckeln
            pre_count = len(analyzed_tracks)
            analyzed_tracks = sanitize_playlist(analyzed_tracks)
            if len(analyzed_tracks) < pre_count:
                removed = pre_count - len(analyzed_tracks)
                self.status_update.emit(
                    f"WARNING: {removed} Track(s) durch Security-Filter entfernt (defekt oder ueber Limits)."
                )
                logger.warning(f"Security-Filter entfernte {removed} von {pre_count} Tracks.")
            if analyzed_tracks and not validate_playlist_security(analyzed_tracks):
                self.status_update.emit(
                    "WARNING: Playlist verletzt Security-Limits -- Details im Log."
                )

            if not analyzed_tracks:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit("ERROR: No tracks were successfully analyzed.")
                self.finished.emit([], {})
                return

            logger.info(f"Feature extraction complete: {len(analyzed_tracks)} tracks successfully analyzed.")
            self.phase_changed.emit(1, "completed")
            self.phase_changed.emit(2, "working")
            self.status_update.emit(
                f"Analyzed {len(analyzed_tracks)} tracks. Generating playlist..."
            )
            logger.info(f"Generating playlist using mode: '{self.mode}' (BPM Tolerance: {self.bpm_tolerance})...")

            try:
                sorted_playlist = generate_playlist(
                    analyzed_tracks,
                    mode=self.mode,
                    bpm_tolerance=self.bpm_tolerance,
                    advanced_params=self.advanced_params,
                )
            except Exception as e:
                self.phase_changed.emit(2, "inactive")
                self.status_update.emit(f"ERROR generating playlist: {str(e)}")
                logger.error(f"Playlist generation failed: {e}")
                get_error_reporter().log_error(
                    "playlist_generation", str(e), {"mode": self.mode}
                )
                self.finished.emit([], {})
                return

            if not sorted_playlist:
                self.phase_changed.emit(2, "inactive")
                self.status_update.emit(
                    "ERROR: Playlist generation returned empty result."
                )
                logger.error("Playlist generation returned an empty result.")
                self.finished.emit([], {})
                return

            logger.info(f"Playlist successfully generated with {len(sorted_playlist)} tracks.")
            self.phase_changed.emit(2, "completed")
            self.phase_changed.emit(3, "working")
            # Calculate quality metrics
            self.status_update.emit("Calculating quality metrics...")
            logger.info("Calculating transition quality metrics...")
            try:
                quality_metrics = calculate_playlist_quality(
                    sorted_playlist, self.bpm_tolerance
                )
            except Exception as e:
                self.status_update.emit(f"Warning: Quality metrics failed: {str(e)}")
                logger.warning(f"Failed to calculate quality metrics: {e}")
                quality_metrics = {}

            overall_score = quality_metrics.get("overall_score", 0.0)
            logger.info(f"Quality analysis complete. Overall playlist score: {overall_score:.2f}%")
            logger.info(f"Analysis process complete! {len(sorted_playlist)} tracks ready.")
            self.phase_changed.emit(3, "completed")
            self.status_update.emit(
                f"Complete! {len(sorted_playlist)} tracks in playlist."
            )
            self.finished.emit(sorted_playlist, quality_metrics)

        except InterruptedError:
            self.status_update.emit("Analysis cancelled.")
            self.finished.emit([], {})
        except Exception as e:
            self.status_update.emit(f"FATAL ERROR: {str(e)}")
            self.finished.emit([], {})


def _render_clip_subprocess_wrapper(args):
    """
    Hilfsfunktion zum Rendern eines Transition-Clips in einem separaten Prozess.
    Muss auf Modulebene liegen, damit sie fuer multiprocessing pickelbar ist.
    """
    spec, out_path = args
    from hpg_core.transition_renderer import render_transition_clip
    render_transition_clip(spec, out_path)
    return out_path


class TransitionRenderWorker(QThread):
    """
    Rendert alle Transition-Preview-Clips nacheinander im Hintergrund.
    Emittiert pro fertigem Clip ein Signal damit die UI sofort aktualisiert werden kann.
    """

    clip_ready = pyqtSignal(int, str)  # (index, wav_pfad)
    clip_error = pyqtSignal(int, str)  # (index, fehler_text)
    # Audit 2026-07-17: tote Signale all_done/progress entfernt (nie connected)

    def __init__(self, transitions: list, parent=None):
        super().__init__(parent)
        # transitions: Liste von TransitionRecommendation-Objekten
        self._transitions = transitions
        self._should_cancel = False
        self._temp_files: list[str] = []  # Fuer Cleanup
        import uuid
        self._run_id = uuid.uuid4().hex[:8]

    def request_cancel(self):
        """Kooperatives Cancel — setzt Flag das in run() geprueft wird."""
        self._should_cancel = True

    def get_temp_files(self) -> list[str]:
        return self._temp_files.copy()

    def run(self):
        from concurrent.futures import ProcessPoolExecutor
        from concurrent.futures.process import BrokenProcessPool

        for i, transition in enumerate(self._transitions):
            if self._should_cancel:
                break
            try:
                # Temp-Ausgabedatei im System-Temp-Verzeichnis
                tmp_dir = tempfile.gettempdir()
                out_path = os.path.join(tmp_dir, f"hpg_preview_{self._run_id}_{i:03d}.wav")
                self._temp_files.append(out_path)

                # TransitionClipSpec aus TransitionRecommendation aufbauen
                mix_out, mix_in, crossfade = resolve_transition_mix_points(transition)
                spec = TransitionClipSpec(
                    track_a_path=transition.from_track.filePath,
                    track_b_path=transition.to_track.filePath,
                    mix_out_sec=mix_out,
                    mix_in_sec=mix_in,
                    crossfade_sec=crossfade,
                    transition_type=transition.transition_type or "smooth_blend",
                    bpm_a=float(transition.from_track.bpm or 120.0),
                    bpm_b=float(transition.to_track.bpm or 120.0),
                    # Downbeat-Feature 2026-07-17: exaktes Beat-Alignment
                    first_downbeat_a=float(getattr(transition.from_track, "first_downbeat", 0.0) or 0.0),
                    first_downbeat_b=float(getattr(transition.to_track, "first_downbeat", 0.0) or 0.0),
                )

                # Sicheres Rendern in einem Subprozess, um C-Level Abstuerze abzufangen
                render_success = False
                try:
                    with ProcessPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(_render_clip_subprocess_wrapper, (spec, out_path))
                        # Timeout grosszuegig fuer lange Trance/Progressive-Blends (bis 64s Crossfade)
                        future.result(timeout=60.0)
                        render_success = True
                except (BrokenProcessPool, RuntimeError) as pool_err:
                    logger.error(f"Render-Prozess abgestuerzt bei Clip {i}: {pool_err}")
                    get_error_reporter().log_error(
                        "transition_render_crash", str(pool_err), {"clip": i}
                    )
                    self.clip_error.emit(i, "Format-Absturz (Datei beschaedigt)")
                except TimeoutError:
                    logger.error(f"Render-Timeout bei Clip {i}")
                    self.clip_error.emit(i, "Zeitueberschreitung")
                except Exception as render_err:
                    logger.error(f"Fehler bei Transition-Render {i}: {render_err}")
                    get_error_reporter().log_error(
                        "transition_render", str(render_err), {"clip": i}
                    )
                    self.clip_error.emit(i, f"Fehler: {render_err}")

                if render_success:
                    self.clip_ready.emit(i, out_path)

            except Exception as e:
                self.clip_error.emit(i, str(e))

    def cleanup(self):
        """Loescht alle temporaeren WAV-Dateien."""
        for path in self._temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self._temp_files.clear()


class TransitionPreviewWidget(QWidget):
    """
    Player-Widget fuer einen einzelnen Transitions-Preview-Clip.
    Zeigt: Play/Stop-Button, Fortschritts-Slider, Zeitanzeige, 
    proportionale Visualisierung von Track A/B/Mix sowie genaue Mix-Punkte.
    Ist deaktiviert bis set_wav_path() aufgerufen wird.
    """

    def __init__(self, index: int, transition, parent=None):
        super().__init__(parent)
        self._index = index
        self._tr = transition
        self._wav_path: str | None = None
        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.85)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Titel-Label
        self._title_label = QLabel(f"▶ Hör-Vorschau Übergang {self._index + 1}")
        self._title_label.setStyleSheet("QLabel { font-size: 11px; font-weight: bold; color: #8b949e; }")
        layout.addWidget(self._title_label)

        # 2. Segmentierter Balken
        from_track = self._tr.from_track
        to_track = self._tr.to_track

        mix_out, mix_in, crossfade = resolve_transition_mix_points(self._tr)

        t_type = getattr(self._tr, "transition_type", "blend")
        t_label = TRANSITION_TYPE_LABELS.get(t_type, t_type)

        def truncate_filename(name, max_len=18):
            if len(name) <= max_len:
                return name
            return name[:max_len-3] + "..."

        from_name = truncate_filename(from_track.fileName)
        to_name = truncate_filename(to_track.fileName)

        self.segments_layout = QHBoxLayout()
        self.segments_layout.setSpacing(2)
        self.segments_layout.setContentsMargins(0, 2, 0, 2)
        
        self.lbl_a = QLabel(f"A: {from_name}\n(Out: {mix_out:.1f}s)")
        self.lbl_a.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_a.setStyleSheet(f"""
            QLabel {{
                background-color: #1E3A8A; 
                color: #93C5FD; 
                font-size: 10px; 
                font-weight: bold;
                border: 1px solid #3B82F6;
                border-radius: 4px;
                padding: 4px 6px;
            }}
        """)
        self.lbl_a.setToolTip(f"Track A: {from_track.fileName}\nSpielt von 0s bis 30s in dieser Vorschau.\nÜbergang startet bei Sekunde {mix_out:.1f} des Original-Tracks A.")
        
        self.lbl_mix = QLabel(f"⇄ MIX ({crossfade:.1f}s)\n{t_label}")
        self.lbl_mix.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_mix.setStyleSheet(f"""
            QLabel {{
                background-color: #5B21B6; 
                color: #DDD6FE; 
                font-size: 10px; 
                font-weight: bold;
                border: 1px solid #8B5CF6;
                border-radius: 4px;
                padding: 4px 6px;
            }}
        """)
        self.lbl_mix.setToolTip(f"Mischbereich (Crossfade) für {crossfade:.1f} Sekunden.\nSpielt von 30.0s bis {30.0+crossfade:.1f}s in dieser Vorschau.")
        
        self.lbl_b = QLabel(f"B: {to_name}\n(In: {mix_in:.1f}s)")
        self.lbl_b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_b.setStyleSheet(f"""
            QLabel {{
                background-color: #064E3B; 
                color: #A7F3D0; 
                font-size: 10px; 
                font-weight: bold;
                border: 1px solid #10B981;
                border-radius: 4px;
                padding: 4px 6px;
            }}
        """)
        self.lbl_b.setToolTip(f"Track B: {to_track.fileName}\nSpielt ab Sekunde {30.0+crossfade:.1f} der Vorschau bis zum Ende.\nÜbergang startet bei Sekunde {mix_in:.1f} des Original-Tracks B.")
        
        # Proportionale Weiten: 30s vor dem Mix, crossfade Sekunden mixen, 30s nach dem Mix
        self.segments_layout.addWidget(self.lbl_a, 300)
        self.segments_layout.addWidget(self.lbl_mix, int(crossfade * 10))
        self.segments_layout.addWidget(self.lbl_b, 300)
        
        layout.addLayout(self.segments_layout)

        # 3. Kontrollzeile: Play-Button + Slider + Zeit
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(28, 28)
        self._play_btn.setEnabled(False)  # Erst aktivieren wenn clip_ready
        self._play_btn.setToolTip("Preview abspielen / pausieren")

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setValue(0)
        self._slider.setEnabled(False)

        self._time_label = QLabel("—")
        self._time_label.setMinimumWidth(90)
        self._time_label.setStyleSheet("QLabel { font-size: 11px; color: #8b949e; }")

        ctrl_layout.addWidget(self._play_btn)
        ctrl_layout.addWidget(self._slider, 1)
        ctrl_layout.addWidget(self._time_label)

        layout.addLayout(ctrl_layout)

        # 4. Info-Struktur-Zeile
        self._info_timeline_label = QLabel(
            f"Vorschau-Struktur: 0:00-0:30: Nur Track A | 0:30-{30.0+crossfade:.1f}s: Mix ({t_label}) | ab {30.0+crossfade:.1f}s: Nur Track B"
        )
        self._info_timeline_label.setStyleSheet("QLabel { font-size: 10px; color: #8b949e; font-style: italic; }")
        layout.addWidget(self._info_timeline_label)

    def _connect_signals(self):
        self._play_btn.clicked.connect(self._toggle_play)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)
        # sliderMoved statt valueChanged — verhindert Feedback-Loop beim Drag
        self._slider.sliderMoved.connect(self._on_slider_moved)

    def set_wav_path(self, path: str):
        """Aufgerufen wenn TransitionRenderWorker clip_ready emittiert."""
        self._wav_path = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._play_btn.setEnabled(True)
        self._slider.setEnabled(True)
        self._time_label.setText("0:00 / –:––")

    def set_error(self, msg: str):
        """Fehlermeldung anzeigen, Play-Button bleibt deaktiviert."""
        self._time_label.setText("Fehler")
        self._title_label.setText(f"{self._title_label.text()} ⚠")
        self._title_label.setToolTip(msg)

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_btn.setText("▶")
        else:
            self._player.play()
            self._play_btn.setText("⏸")

    def _on_position_changed(self, pos_ms: int):
        dur_ms = self._player.duration()
        if dur_ms > 0:
            # Slider-Wert setzen ohne sliderMoved auszuloesen
            self._slider.blockSignals(True)
            self._slider.setValue(int(pos_ms * 1000 / dur_ms))
            self._slider.blockSignals(False)
        pos_s = pos_ms // 1000
        self._time_label.setText(f"{pos_s // 60}:{pos_s % 60:02d} / {self._fmt_dur()}")

    def _on_duration_changed(self, dur_ms: int):
        self._time_label.setText(f"0:00 / {self._fmt_dur()}")

    def _fmt_dur(self) -> str:
        d = self._player.duration() // 1000
        return f"{d // 60}:{d % 60:02d}"

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._play_btn.setText("▶")
            self._slider.blockSignals(True)
            self._slider.setValue(0)
            self._slider.blockSignals(False)

    def _on_error(self, error, error_string: str):
        self._play_btn.setEnabled(False)
        self._time_label.setText("Fehler")

    def _on_slider_moved(self, value: int):
        """Seek wenn Nutzer den Slider zieht."""
        dur_ms = self._player.duration()
        if dur_ms > 0:
            self._player.setPosition(int(value * dur_ms / 1000))

    def stop_and_reset(self):
        """Playback stoppen und Slider zuruecksetzen."""
        self._player.stop()
        self._play_btn.setText("▶")


class AdvancedParametersWidget(QWidget):
    """Widget for algorithm-specific advanced parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 8, 8, 8)

        # Energy Direction Control
        energy_group = QGroupBox("Energy Direction (Context Flow)")
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
            lambda v: self.peak_position_label.setText(f"Peak Position: {v}%")
        )

        energy_layout.addWidget(self.peak_position_label)
        energy_layout.addWidget(self.peak_position_slider)

        layout.addWidget(energy_group)

        # AI Provider Selection — Auto-Detect & Auto-Start (Ollama / LM Studio)
        # Vom ai_launcher erkannte Werte; vom Detect-Worker befuellt.
        self.detected_base_url = None
        self.detected_provider = None
        self.detected_active_model = None
        self._ai_detect_worker = None

        self.provider_group = QGroupBox("AI Intelligence Provider")
        provider_outer = QVBoxLayout(self.provider_group)
        provider_outer.setSpacing(8)

        # Row 1: Radios (Ollama / LM Studio)
        radio_layout = QHBoxLayout()
        self.ollama_radio = QRadioButton("Ollama")
        self.lmstudio_radio = QRadioButton("LM Studio")

        from hpg_core import config as hpg_config
        if hpg_config.AI_PROVIDER == "LM Studio":
            self.lmstudio_radio.setChecked(True)
        else:
            self.ollama_radio.setChecked(True)

        # Connect signals to automatically refresh when switching provider
        self.ollama_radio.toggled.connect(lambda checked: self.refresh_ai_providers() if checked else None)
        self.lmstudio_radio.toggled.connect(lambda checked: self.refresh_ai_providers() if checked else None)

        radio_layout.addWidget(self.ollama_radio)
        radio_layout.addWidget(self.lmstudio_radio)
        provider_outer.addLayout(radio_layout)

        # Row 2: Model Selection Label & ComboBox
        model_layout = QHBoxLayout()
        model_label = QLabel("Active AI Model:")
        self.model_combo = QComboBox()
        # Platzhalter bis Detect fertig ist
        self.model_combo.addItems(hpg_config.AI_MODELS_AVAILABLE)
        if hpg_config.AI_MODEL in hpg_config.AI_MODELS_AVAILABLE:
            self.model_combo.setCurrentText(hpg_config.AI_MODEL)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo, 1)
        provider_outer.addLayout(model_layout)

        # Row 3: Status label
        self.ai_status_label = QLabel("AI: noch nicht geprueft")
        self.ai_status_label.setWordWrap(True)
        self.ai_status_label.setStyleSheet("font-size: 11px;")
        provider_outer.addWidget(self.ai_status_label)

        # Row 4: Buttons (AI erkennen / starten + Modell testen)
        btn_layout = QHBoxLayout()
        self.ai_refresh_btn = QPushButton("AI erkennen / starten")
        self.ai_refresh_btn.clicked.connect(self.refresh_ai_providers)

        self.test_ai_btn = QPushButton("Modell testen")
        self.test_ai_btn.clicked.connect(self.test_ai_connection)
        self.test_ai_btn.setEnabled(False) # Initial deaktiviert, bis AI bereit ist

        btn_layout.addWidget(self.ai_refresh_btn)
        btn_layout.addWidget(self.test_ai_btn)
        provider_outer.addLayout(btn_layout)

        layout.addWidget(self.provider_group)

        # Auto-Detect beim Start (nicht-blockierend, kurz verzoegert bis UI steht)
        QTimer.singleShot(300, self.refresh_ai_providers)


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
            lambda v: self.harmony_label.setText(f"Harmonic Strictness: {v}/10")
        )

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
            lambda v: self.genre_weight_label.setText(f"Genre Similarity Weight: {v}%")
        )

        genre_layout.addWidget(self.genre_weight_label)
        genre_layout.addWidget(self.genre_weight)

        layout.addWidget(genre_group)

    # ----- AI Provider Auto-Detect / Auto-Start -----

    def refresh_ai_providers(self):
        """Startet den Hintergrund-Detect-Worker (kein UI-Block)."""
        if self._ai_detect_worker and self._ai_detect_worker.isRunning():
            return
        preferred = "LM Studio" if self.lmstudio_radio.isChecked() else "Ollama"
        preferred_model = self.model_combo.currentText().strip() or None

        self.ai_status_label.setText("AI: suche & starte Provider ...")
        self.ai_refresh_btn.setEnabled(False)

        self._ai_detect_worker = AIDetectWorker(
            preferred=preferred, preferred_model=preferred_model
        )
        self._ai_detect_worker.detected.connect(self._on_ai_detected)
        self._ai_detect_worker.start()

    def _on_ai_detected(self, status):
        """Befuellt UI mit erkanntem Provider + real installierten Modellen."""
        self.ai_refresh_btn.setEnabled(True)

        if not status or not getattr(status, "running", False):
            self.ai_status_label.setText(
                "AI: kein Provider erreichbar (Ollama/LM Studio nicht installiert/gestartet)"
            )
            self.detected_base_url = None
            self.test_ai_btn.setEnabled(False)
            return

        self.test_ai_btn.setEnabled(True)

        # Provider-Radio passend setzen (Signale blockieren, um unendliche Worker-Loops zu vermeiden)
        self.lmstudio_radio.blockSignals(True)
        self.ollama_radio.blockSignals(True)
        if status.name == "LM Studio":
            self.lmstudio_radio.setChecked(True)
        else:
            self.ollama_radio.setChecked(True)
        self.lmstudio_radio.blockSignals(False)
        self.ollama_radio.blockSignals(False)

        # Combo mit echten Modellen fuellen
        if status.models:
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItems(status.models)
            if status.active_model and status.active_model in status.models:
                self.model_combo.setCurrentText(status.active_model)
            self.model_combo.blockSignals(False)

        # Erkannte Werte merken (vom AIAnalysisWorker genutzt)
        self.detected_base_url = status.base_url
        self.detected_provider = status.name
        self.detected_active_model = status.active_model or self.model_combo.currentText()

        # Port aus Endpoint extrahieren fuer Statusanzeige
        port = ""
        m = re.search(r":(\d+)/", status.base_url or "")
        if m:
            port = f" :{m.group(1)}"
        self.ai_status_label.setText(
            f"AI bereit — {status.name}{port} · {len(status.models)} Modelle · "
            f"aktiv: {self.detected_active_model}"
        )

    def _on_model_changed(self, model_name):
        """Wird aufgerufen, wenn der Benutzer ein anderes Modell auswaehlt."""
        if not model_name:
            return
        self.detected_active_model = model_name
        provider = "LM Studio" if self.lmstudio_radio.isChecked() else "Ollama"
        port = ""
        if self.detected_base_url:
            m = re.search(r":(\d+)/", self.detected_base_url)
            if m:
                port = f" :{m.group(1)}"
        
        num_models = self.model_combo.count()
        self.ai_status_label.setText(
            f"AI bereit — {provider}{port} · {num_models} Modelle · "
            f"aktiv: {self.detected_active_model}"
        )

    def test_ai_connection(self):
        """Sendet eine Test-Anfrage an den ausgewaehlten Provider."""
        provider = "LM Studio" if self.lmstudio_radio.isChecked() else "Ollama"
        model = self.model_combo.currentText().strip()
        if not model:
            QMessageBox.warning(self, "Modell testen", "Bitte waehle zuerst ein Modell aus.")
            return

        self.test_ai_btn.setEnabled(False)
        self.ai_refresh_btn.setEnabled(False)
        self.ai_status_label.setText("AI: Testanfrage laeuft...")

        base_url = self.detected_base_url
        self._test_worker = AITestWorker(provider, model, base_url, parent=self)
        self._test_worker.test_finished.connect(self._on_test_finished)
        self._test_worker.start()

    def _on_test_finished(self, success, response_text, responded_model, latency):
        """Verarbeitet das Ergebnis des AI-Verbindungstests."""
        self.test_ai_btn.setEnabled(True)
        self.ai_refresh_btn.setEnabled(True)

        provider = "LM Studio" if self.lmstudio_radio.isChecked() else "Ollama"
        port = ""
        if self.detected_base_url:
            m = re.search(r":(\d+)/", self.detected_base_url)
            if m:
                port = f" :{m.group(1)}"

        # Statustext aktualisieren
        num_models = self.model_combo.count()
        self.ai_status_label.setText(
            f"AI bereit — {provider}{port} · {num_models} Modelle · "
            f"aktiv: {responded_model}"
        )

        if success:
            QMessageBox.information(
                self,
                "AI-Verbindungstest erfolgreich",
                f"Echte Antwort vom lokalen LLM erhalten!\n\n"
                f"Provider: {provider}\n"
                f"Modell: {responded_model}\n"
                f"Antwort: \"{response_text}\"\n"
                f"Antwortzeit (Latenz): {latency:.2f} s\n\n"
                f"Du kannst jetzt mit der Playlist-Generierung beginnen!"
            )
        else:
            # Pruefen, ob das Modell auf Ollama fehlt
            is_not_found = False
            if provider == "Ollama":
                err_lower = response_text.lower()
                if "not found" in err_lower or "404" in err_lower or "does not exist" in err_lower:
                    is_not_found = True

            if is_not_found:
                reply = QMessageBox.question(
                    self,
                    "Modell herunterladen?",
                    f"Das Modell '{responded_model}' wurde auf deinem Ollama-Server nicht gefunden.\n\n"
                    f"Möchtest du, dass die App das Modell automatisch über Ollama herunterlädt (pull)?\n"
                    f"(Dies kann je nach Modellgröße und Internetgeschwindigkeit 2-10 Minuten dauern. "
                    f"Die App bleibt währenddessen bedienbar, der Fortschritt wird angezeigt.)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._start_model_pull(responded_model)
                    return

            QMessageBox.critical(
                self,
                "AI-Verbindungstest fehlgeschlagen",
                f"Fehler beim Testen des Providers {provider}!\n\n"
                f"Fehlerbeschreibung:\n{response_text}\n\n"
                f"Dauer: {latency:.2f} s\n\n"
                f"Bitte ueberpruefe, ob {provider} gestartet ist und das Modell '{responded_model}' geladen werden kann."
            )

    def _start_model_pull(self, model):
        """Startet den Download des Modells über Ollama im Hintergrund."""
        self.test_ai_btn.setEnabled(False)
        self.ai_refresh_btn.setEnabled(False)
        self.ai_status_label.setText(f"AI: Lade '{model}' herunter (bitte warten)...")

        self._pull_worker = AIPullWorker(model, parent=self)
        self._pull_worker.pull_finished.connect(self._on_pull_finished)
        self._pull_worker.start()

    def _on_pull_finished(self, success, error_msg):
        """Verarbeitet das Ende des Model-Downloads."""
        self.test_ai_btn.setEnabled(True)
        self.ai_refresh_btn.setEnabled(True)

        if success:
            self.ai_status_label.setText("AI: Download abgeschlossen. Teste Verbindung...")
            # Nach erfolgreichem Pull automatisch erneut testen
            self.test_ai_connection()
            # Nach erfolgreichem Pull die Modellliste aktualisieren
            self.refresh_ai_providers()
            QMessageBox.information(
                self,
                "Download erfolgreich",
                f"Das Modell '{self._pull_worker.model}' wurde erfolgreich heruntergeladen und installiert!\n\n"
                f"Der Verbindungstest wird nun automatisch gestartet. Sobald dieser erfolgreich ist, kannst du beginnen!"
            )
        else:
            self.ai_status_label.setText("AI bereit (Fehler beim Download)")
            QMessageBox.critical(
                self,
                "Download fehlgeschlagen",
                f"Fehler beim Herunterladen des Modells über Ollama!\n\n"
                f"Details:\n{error_msg}"
            )

    def get_parameters(self):
        """Return current parameter values as dict."""
        return {
            "energy_direction": self.energy_direction.currentText(),
            "peak_position": self.peak_position_slider.value(),
            "harmonic_strictness": self.harmonic_strictness.value(),
            "allow_experimental": self.allow_experimental.isChecked(),
            "genre_mixing": self.genre_mixing.isChecked(),
            "genre_weight": self.genre_weight.value() / 100.0,
        }


# ══════════════════════════════════════════════════════════════════
# PHASE 2: Neue Layout-Widgets (Sidebar, Toolbar, StatusBar, Panels)
# ══════════════════════════════════════════════════════════════════


class SidebarWidget(QWidget):
    """Vertikale Navigation — Ableton-inspiriert, 72px breit."""

    nav_changed = pyqtSignal(int)

    NAV_ITEMS = [
        ("LIB", "LIBRARY"),
        ("PL", "PLAYLIST"),
        ("MIX", "MIX TIPS"),
        ("TL", "TIMELINE"),
        ("QA", "QUALITY"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(72)
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

        for i, (icon, label) in enumerate(self.NAV_ITEMS):
            btn = QPushButton()
            btn.setFixedSize(72, 56)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(label)
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
        self.setFixedHeight(40)
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
        self.info_label = QLabel("No folder selected")
        self.info_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-family: {FONT_FAMILY};
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.info_label, 1)

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
        self.generate_btn = QPushButton("GENERATE")
        self.generate_btn.setObjectName("btn_primary")
        self.generate_btn.setFixedHeight(28)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.clicked.connect(self.generate_clicked.emit)
        self.generate_btn.setToolTip("Playlist generieren (Strg+G)")
        layout.addWidget(self.generate_btn)

        self.export_btn = QPushButton("EXPORT")
        self.export_btn.setObjectName("btn_secondary")
        self.export_btn.setFixedHeight(28)
        self.export_btn.setEnabled(False)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.clicked.connect(self.export_clicked.emit)
        self.export_btn.setToolTip("Playlist exportieren (Strg+E)")
        layout.addWidget(self.export_btn)

    def set_info(self, text):
        self.info_label.setText(text)

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
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-family: {FONT_FAMILY};
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.status_label, 1)

        # Progress-Bar (konstant sichtbar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(240)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setRange(0, 10000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0.00%")
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS["bg_card"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
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
        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.setObjectName("btn_danger")
        self.cancel_btn.setFixedHeight(20)
        self.cancel_btn.setFixedWidth(60)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
        self.cancel_btn.hide()
        layout.addWidget(self.cancel_btn)

    def set_status(self, text):
        self.status_label.setText(text)

    def set_progress(self, value):
        self.progress_bar.setValue(value)
        percentage = value / 100.0
        self.progress_bar.setFormat(f"{percentage:.2f}%")

    def show_progress(self):
        """Analyse gestartet — Progress und Cancel sichtbar."""
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0.00%")
        self.cancel_btn.show()

    def hide_progress(self):
        """Analyse beendet — Progress und Cancel verstecken."""
        self.cancel_btn.show()


class QtLogSignalEmitter(QObject):
    log_written = pyqtSignal(str, str)


import logging

class QtLoggingHandler(logging.Handler):
    def __init__(self, emitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname
            if level in ("ERROR", "CRITICAL"):
                color = "#FF3333"
            elif level == "WARNING":
                color = "#FFCC00"
            elif level == "DEBUG":
                color = "#A0A0A0" # Dezentes Hellgrau für Traces/Debugs
            else:
                color = "#00FF66" # Hellgrün für INFO
            self.emitter.log_written.emit(msg, color)
        except Exception:
            self.handleError(record)


# Globale Variable für den Logging-Emitter
global_log_emitter = QtLogSignalEmitter()


class ShortcutsHelpWidget(QGroupBox):
    """Small widget displaying keyboard shortcuts in a clean grid/list layout."""
    
    def __init__(self, parent=None):
        super().__init__("Keyboard Shortcuts", parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        shortcuts = [
            ("Ctrl+G", "Generate Playlist"),
            ("Ctrl+E", "Export Playlist"),
            ("1 - 5", "Switch Navigation Panels"),
            ("Space", "Play / Pause Preview")
        ]
        
        for key, desc in shortcuts:
            row = QHBoxLayout()
            
            key_lbl = QLabel(key)
            key_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {COLORS["bg_sidebar"]};
                    color: {COLORS["accent_primary"]};
                    font-family: "Consolas", "Courier New", monospace;
                    font-weight: bold;
                    font-size: 11px;
                    border: 1px solid {COLORS["border"]};
                    border-radius: 3px;
                    padding: 2px 6px;
                    min-width: 50px;
                }}
            """)
            key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"QLabel {{ color: {COLORS['text_secondary']}; font-size: 11px; }}")
            
            row.addWidget(key_lbl)
            row.addWidget(desc_lbl, 1)
            layout.addLayout(row)


class AnalysisProgressWidget(QWidget):
    """Widget showing a 5-step status indicator, progress bar, and a live terminal log view."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        
        # 1. 5 Steps Horizontal QFrames
        steps_layout = QHBoxLayout()
        steps_layout.setSpacing(4)
        
        self.steps = []
        step_labels = [
            "📁 SCAN",
            "🔊 AUDIO",
            "🎛️ SORT",
            "📊 QUALITY",
            "🤖 AI MOODS"
        ]
        
        for i, text in enumerate(step_labels):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(4, 6, 4, 6)
            
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #FFFFFF;")
            frame_layout.addWidget(lbl)
            
            # Default state: inactive (gray)
            frame.setStyleSheet(self._get_step_style("inactive"))
            
            steps_layout.addWidget(frame, 1)
            self.steps.append(frame)
            
        layout.addLayout(steps_layout)
        
        # 2. Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 10000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(42)
        self.progress_bar.setFormat("0.00%")
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS["bg_card"]};
                border: 2px solid {COLORS["border"]};
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
                font-family: {FONT_FAMILY};
                font-size: 16px;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS["accent_primary"]};
            }}
        """)
        layout.addWidget(self.progress_bar)
        
        # 3. Live Terminal
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setMaximumBlockCount(1000)
        self.terminal.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0E0E0E;
                color: #DDDDDD;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                border: 1px solid {COLORS["border"]};
                padding: 5px;
            }}
        """)
        self.terminal.setMinimumHeight(180)
        layout.addWidget(self.terminal)

    def _get_step_style(self, state):
        if state == "inactive":
            return f"QFrame {{ background-color: #2D2D2D; border: 1px solid {COLORS['border']}; border-radius: 2px; }}"
        elif state == "working":
            return f"QFrame {{ background-color: #D4AF37; border: 1px solid #FFD700; border-radius: 2px; }}"
        elif state == "completed":
            return f"QFrame {{ background-color: #00FF66; border: 1px solid #33FF33; border-radius: 2px; }}"
        return ""

    def set_step_status(self, step_idx, state):
        """state can be 'inactive', 'working', 'completed'"""
        if 0 <= step_idx < len(self.steps):
            self.steps[step_idx].setStyleSheet(self._get_step_style(state))
            lbl = self.steps[step_idx].layout().itemAt(0).widget()
            if state == "completed":
                lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #000000;")
            elif state == "working":
                lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #000000;")
            else:
                lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #FFFFFF;")
                
    def set_progress(self, value):
        self.progress_bar.setValue(value)
        percentage = value / 100.0
        self.progress_bar.setFormat(f"{percentage:.2f}%")
                
    def reset_steps(self):
        for i in range(len(self.steps)):
            self.set_step_status(i, "inactive")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0.00%")

    def append_log(self, text, color=None):
        if color:
            self.terminal.appendHtml(f'<span style="color: {color};">{text}</span>')
        else:
            self.terminal.appendPlainText(text)
        self.terminal.moveCursor(QTextCursor.MoveOperation.End)


class LibraryPanel(QWidget):
    """Library-Panel — Ordner-Auswahl, Strategie, Parameter."""

    folder_selected = pyqtSignal(str)
    start_analysis = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.current_folder = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(16)

        # Linke Seite — Hauptsteuerung
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # Ordner-Auswahl (kein GroupBox — kompakter)
        section_label = QLabel("MUSIC LIBRARY")
        section_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-family: {FONT_FAMILY};
                font-size: 10px;
                font-weight: bold;
                padding-bottom: 4px;
            }}
        """)
        left_layout.addWidget(section_label)

        self.info_label = QLabel(
            "Drag and drop your music folder here\nor click the button below."
        )
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet(
            f"QLabel {{ color: {COLORS['text_secondary']}; font-size: 13px; padding: 28px 20px; "
            f"border: 2px dashed {COLORS['border']}; border-radius: 0px; "
            f"background-color: {COLORS['bg_card']}; }}"
        )
        self.info_label.setToolTip(
            "Waehle den Ordner mit deinen Audio-Dateien.\n"
            "Unterstuetzte Formate: WAV, AIFF, MP3, FLAC\n"
            "Unterordner werden automatisch durchsucht."
        )
        left_layout.addWidget(self.info_label)

        self.select_folder_button = QPushButton("Select Music Folder")
        self.select_folder_button.setMinimumHeight(36)
        self.select_folder_button.setObjectName("btn_secondary")
        self.select_folder_button.setToolTip(
            "Oeffnet einen Dialog zur Ordner-Auswahl (WAV, AIFF, MP3, FLAC)"
        )
        left_layout.addWidget(self.select_folder_button)

        # Strategie
        strategy_label = QLabel("STRATEGY")
        strategy_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-family: {FONT_FAMILY};
                font-size: 10px;
                font-weight: bold;
                padding-top: 8px;
                padding-bottom: 4px;
            }}
        """)
        left_layout.addWidget(strategy_label)

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(list(STRATEGIES.keys()))
        self.strategy_combo.setCurrentText("Harmonic Flow")
        self.strategy_combo.setToolTip(
            "Waehle den Algorithmus fuer die Playlist-Generierung.\n"
            "Harmonic Flow und Peak-Time nutzen Look-Ahead bzw. Smoothing."
        )
        left_layout.addWidget(self.strategy_combo)

        self.strategy_description = QLabel()
        self.strategy_description.setWordWrap(True)
        self.strategy_description.setStyleSheet(
            f"QLabel {{ color: {COLORS['text_secondary']}; font-size: 10px; }}"
        )
        self._update_strategy_description()
        self.strategy_combo.currentTextChanged.connect(
            self._update_strategy_description
        )
        left_layout.addWidget(self.strategy_description)

        # BPM Tolerance — Kompakte Zeile
        bpm_label = QLabel("BPM TOLERANCE")
        bpm_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_secondary"]};
                font-family: {FONT_FAMILY};
                font-size: 10px;
                font-weight: bold;
                padding-top: 8px;
                padding-bottom: 4px;
            }}
        """)
        left_layout.addWidget(bpm_label)

        bpm_row = QHBoxLayout()
        self.bpm_tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.bpm_tolerance_slider.setRange(1, 15)
        self.bpm_tolerance_slider.setValue(3)
        self.bpm_tolerance_slider.setToolTip(
            "Maximale BPM-Differenz zwischen aufeinanderfolgenden Tracks.\n"
            "±3 BPM empfohlen. Half/Double-Time wird automatisch erkannt."
        )
        self.bpm_value_label = QLabel("±3")
        self.bpm_value_label.setFixedWidth(30)
        self.bpm_value_label.setStyleSheet(
            f"QLabel {{ color: {COLORS['accent_primary']}; font-weight: bold; }}"
        )
        self.bpm_tolerance_slider.valueChanged.connect(
            lambda v: self.bpm_value_label.setText(f"±{v}")
        )
        bpm_row.addWidget(self.bpm_tolerance_slider, 1)
        bpm_row.addWidget(self.bpm_value_label)
        left_layout.addLayout(bpm_row)

        # Generate-Button
        self.start_button = QPushButton("GENERATE PLAYLIST")
        self.start_button.setObjectName("btn_primary")
        self.start_button.setMinimumHeight(44)
        self.start_button.setToolTip(
            "Startet die Audio-Analyse und Playlist-Generierung.\n"
            "Multi-Core-Verarbeitung: nutzt alle verfuegbaren CPU-Kerne."
        )
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_analysis.emit)
        left_layout.addWidget(self.start_button)

        # Progress & Terminal Widget
        self.progress_widget = AnalysisProgressWidget()
        left_layout.addWidget(self.progress_widget)

        # Rechte Seite — Advanced Parameters (feste Spalte)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.advanced_params = AdvancedParametersWidget()
        right_layout.addWidget(self.advanced_params)

        self.shortcuts_help = ShortcutsHelpWidget()
        right_layout.addWidget(self.shortcuts_help)
        right_layout.addStretch()

        right.setFixedWidth(400)

        main_layout.addWidget(left, 1)
        main_layout.addWidget(right, 0)

    def _update_strategy_description(self):
        strategy = self.strategy_combo.currentText()
        descriptions = {
            "Harmonic Flow": "Harmonic mixing (Camelot wheel) with look-ahead optimization and backtracking.",
            "Peak-Time": "Peak arrangement with adjustable peak position and harmonic smoothing.",
            "Genre Flow": "Smooth transitions between similar genres while maintaining energy.",
            "Energy Wave": "Alternating high/low energy creates dynamic listening experience.",
            "Warm-Up": "Gradual BPM increase from low to high energy.",
            "Cool-Down": "Gradual BPM decrease from high to low energy.",
            "Consistent": "Minimal BPM/energy jumps with harmonic compatibility.",
            "Context Flow": "Set-phase aware: target energy per phase (Energy Direction presets), trend continuation, genre fatigue, no clone tracks back-to-back.",
        }
        self.strategy_description.setText(
            descriptions.get(strategy, "No description available.")
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            path = os.path.normpath(path)
            if os.path.isdir(path):
                self.set_folder_path(path)
                break

    def set_folder_path(self, path):
        """Programmatically set folder path."""
        if os.path.isdir(path):
            # W8: Pruefen ob Ordner lesbar ist
            if not os.access(path, os.R_OK):
                self.info_label.setText(f"No read permission: {os.path.basename(path)}")
                self.info_label.setStyleSheet(
                    f"QLabel {{ color: {COLORS['accent_danger']}; font-size: 13px; padding: 20px 28px; "
                    f"border: 2px solid {COLORS['accent_danger']}; border-radius: 0px; "
                    f"background-color: {COLORS['bg_card']}; }}"
                )
                return
            self.current_folder = path
            self.folder_selected.emit(path)
            self.start_button.setEnabled(True)
            self.info_label.setText(f"✓  {os.path.basename(path)}")
            self.info_label.setStyleSheet(
                f"QLabel {{ color: {COLORS['accent_success']}; font-size: 13px; padding: 20px 28px; "
                f"border: 2px solid {COLORS['border_active']}; border-radius: 0px; "
                f"background-color: {COLORS['accent_primary_bg']}; }}"
            )

    def get_advanced_parameters(self):
        return self.advanced_params.get_parameters()

    def get_current_settings(self):
        return {
            "folder": self.current_folder,
            "strategy": self.strategy_combo.currentText(),
            "bpm_tolerance": float(self.bpm_tolerance_slider.value()),
            "advanced_params": self.get_advanced_parameters(),
        }


class EnergyBarDelegate(QStyledItemDelegate):
    """Rendert Energy-Werte als visuellen Neon-Balken (Cyberpunk DAW-Stil)."""

    def paint(self, painter, option, index):
        value = index.data()
        try:
            energy = int(value)
        except (TypeError, ValueError):
            super().paint(painter, option, index)
            return

        painter.save()

        # Hintergrund: Selektion oder Standard
        if option.state & QStyle.StateFlag.State_Selected:
            bg = QColor(COLORS["bg_selected"])
        else:
            bg = QColor(COLORS["bg_input"])
        painter.fillRect(option.rect, bg)

        # Balken-Bereich: leichte vertikale Einrueckung fuer sauberes Look
        bar_rect = option.rect.adjusted(2, 5, -2, -5)
        ratio = max(0.0, min(1.0, energy / 100.0))
        filled_width = int(bar_rect.width() * ratio)

        # Hintergrund des Balkens (dunkel)
        painter.fillRect(bar_rect, QColor(COLORS["border"]))

        # Farbkodierung je Energie-Level
        if energy >= 75:
            bar_color = QColor(COLORS["accent_primary"])  # Neon Gruen
        elif energy >= 50:
            bar_color = QColor(COLORS["accent_warning"])  # Gelb-Gold
        else:
            bar_color = QColor(COLORS["accent_secondary"])  # Neon Violett

        # Gefuellter Balken-Anteil
        filled_rect = QRect(bar_rect.x(), bar_rect.y(), filled_width, bar_rect.height())
        painter.fillRect(filled_rect, bar_color)

        # Zahl als Text zentriert darueber
        painter.setPen(QColor(COLORS["text_bright"]))
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(energy))

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(60, 24)


class PlaylistPanel(QWidget):
    """Playlist-Tabelle mit Quality-Header und Drag-Drop."""

    export_clicked = pyqtSignal()
    preview_clicked = pyqtSignal()
    restart_clicked = pyqtSignal()
    playlist_reordered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.playlist = []
        self.quality_metrics = {}
        self.transition_recommendations = []
        self.bpm_tolerance = 3.0
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Quality-Metrics Header (horizontale Badges)
        self.quality_widget = QWidget()
        self.quality_layout = QHBoxLayout(self.quality_widget)
        self.quality_layout.setContentsMargins(4, 4, 4, 4)
        self.quality_layout.setSpacing(0)
        layout.addWidget(self.quality_widget)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(16)
        self.table.setHorizontalHeaderLabels(
            [
                "#",
                "Track Name",
                "Artist",
                "Duration",
                "BPM",
                "Key",
                "Camelot",
                "Energy",
                "Genre",
                "Genre %",
                "Mix In",
                "Mix Out",
                "Bass %",
                "Texture",
                "Transition Score", "AI Insights",
            ]
        )

        # Tooltips fuer Spaltenheader
        header_tooltips = [
            "Position in der Playlist.\nDrag & Drop zum Umsortieren.",
            "Dateiname des Audio-Tracks.",
            "Interpret (aus ID3-Tag oder Dateiname).",
            "Gesamtlaenge des Tracks (Minuten:Sekunden).",
            "Beats Per Minute – das Tempo des Tracks.",
            "Musikalische Tonart (z.B. C Major, A Minor).",
            "Camelot-Code fuer harmonisches Mixing.",
            "Energie-Level des Tracks (0-100).",
            "Automatisch erkanntes Genre.",
            "Konfidenz der Genre-Erkennung (0-100%).",
            "Mix-In-Punkt: Dynamisch berechneter Startpunkt für den Mix (nach Intro).",
            "Mix-Out-Punkt: Dynamisch berechneter Endpunkt für den Mix (vor Outro).",
            "Bass %: Subbass-Anteil (20-150Hz) für Genre-Flow und EQing.",
            "Textur: Klangliche Ähnlichkeit für fließende Übergänge.",
            "Kompatibilität zum vorherigen Track (0-100%).",
        ]
        for col, tip in enumerate(header_tooltips):
            item = self.table.horizontalHeaderItem(col)
            if item:
                item.setToolTip(tip)

        # Drag-and-Drop
        self.table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Spaltenbreiten
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 70)
        self.table.setColumnWidth(7, 60)
        self.table.setColumnWidth(8, 100)
        self.table.setColumnWidth(9, 60)
        self.table.setColumnWidth(10, 70)
        self.table.setColumnWidth(11, 70)

        # rowsMoved Signal
        self.table.model().rowsMoved.connect(self._on_rows_moved)

        # EnergyBarDelegate fuer visuelle Energie-Anzeige (Spalte 7)
        self._energy_delegate = EnergyBarDelegate(self.table)
        self.table.setItemDelegateForColumn(7, self._energy_delegate)

        layout.addWidget(self.table, 1)

        # Drag-Info
        drag_info = QLabel(
            "Drag and drop rows to reorder. Transition scores update automatically."
        )
        drag_info.setStyleSheet(
            f"QLabel {{ color: {COLORS['text_dim']}; font-size: 10px; font-style: italic; }}"
        )
        layout.addWidget(drag_info)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.export_button = QPushButton("EXPORT PLAYLIST")
        self.export_button.setObjectName("btn_primary")
        self.export_button.setMinimumHeight(36)
        self.export_button.setToolTip(
            "Exportiert die Playlist als M3U oder Rekordbox XML."
        )
        self.export_button.clicked.connect(self.export_clicked.emit)

        self.preview_button = QPushButton("PREVIEW TRANSITIONS")
        self.preview_button.setObjectName("btn_secondary")
        self.preview_button.setMinimumHeight(36)
        self.preview_button.setToolTip("Zeigt eine Vorschau der Uebergaenge.")
        self.preview_button.clicked.connect(self.preview_clicked.emit)

        self.restart_button = QPushButton("START OVER")
        self.restart_button.setObjectName("btn_secondary")
        self.restart_button.setMinimumHeight(36)
        self.restart_button.setToolTip("Zurueck zur Library. Playlist geht verloren.")
        self.restart_button.clicked.connect(self.restart_clicked.emit)

        btn_layout.addWidget(self.export_button)
        btn_layout.addWidget(self.preview_button)
        btn_layout.addWidget(self.restart_button)
        layout.addLayout(btn_layout)

    def set_playlist_data(
        self,
        playlist,
        quality_metrics,
        transition_recommendations=None,
        bpm_tolerance=3.0,
    ):
        """Playlist-Daten setzen und Tabelle fuellen."""
        self.playlist = playlist
        self.quality_metrics = quality_metrics
        self.bpm_tolerance = bpm_tolerance
        if transition_recommendations is None:
            self.transition_recommendations = compute_transition_recommendations(
                playlist, bpm_tolerance=self.bpm_tolerance
            )
        else:
            self.transition_recommendations = transition_recommendations

        self._update_quality_display()
        self._populate_table()

    def _update_quality_display(self):
        """Quality-Metriken als horizontale Badges."""
        while self.quality_layout.count():
            child = self.quality_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.quality_metrics:
            return

        metrics = [
            ("OVERALL", self.quality_metrics.get("overall_score", 0)),
            ("HARMONY", self.quality_metrics.get("harmonic_flow", 0)),
            ("ENERGY", self.quality_metrics.get("energy_consistency", 0)),
            ("BPM", self.quality_metrics.get("bpm_smoothness", 0)),
        ]

        metric_tooltips = {
            "OVERALL": "Gesamtqualitaet der Playlist (0-100%).",
            "HARMONY": "Harmonischer Flow — Camelot-Kompatibilitaet.",
            "ENERGY": "Energie-Konsistenz — smoothe Uebergaenge.",
            "BPM": "BPM-Smoothness — sanfte Tempo-Wechsel.",
        }

        for name, value in metrics:
            badge = QWidget()
            badge_layout = QVBoxLayout(badge)
            badge_layout.setContentsMargins(12, 2, 12, 2)
            badge_layout.setSpacing(0)
            badge.setToolTip(metric_tooltips.get(name, ""))

            score_lbl = QLabel(f"{value:.0%}")
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            score_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 16px;
                    font-weight: 700;
                    color: {score_color(value)};
                    font-family: {FONT_FAMILY};
                }}
            """)

            name_lbl = QLabel(name)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 10px;
                    font-weight: 500;
                    color: {COLORS["text_secondary"]};
                    font-family: {FONT_FAMILY};
                    letter-spacing: 1px;
                }}
            """)

            badge_layout.addWidget(score_lbl)
            badge_layout.addWidget(name_lbl)
            self.quality_layout.addWidget(badge)

        self.quality_layout.addStretch()

    def _populate_table(self):
        """Tabelle mit Performance-Optimierung befuellen."""
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self.playlist))

        for i, track in enumerate(self.playlist):
            transition_score = 0
            if i > 0:
                prev_track = self.playlist[i - 1]
                compatibility = calculate_enhanced_compatibility(
                    prev_track, track, self.bpm_tolerance
                )
                transition_score = int(compatibility.overall_score * 100)

            detected_genre = getattr(track, "detected_genre", "Unknown") or "Unknown"
            genre_confidence = getattr(track, "genre_confidence", 0.0) or 0.0

            items = [
                QTableWidgetItem(str(i + 1)),
                QTableWidgetItem(track.fileName),
                QTableWidgetItem(track.artist),
                QTableWidgetItem(
                    f"{int(track.duration // 60)}:{int(track.duration % 60):02d}"
                ),
                QTableWidgetItem(f"{track.bpm:.1f}"),
                QTableWidgetItem(f"{track.keyNote} {track.keyMode}"),
                QTableWidgetItem(track.camelotCode),
                QTableWidgetItem(str(track.energy)),
            ]

            for col, item in enumerate(items):
                item.setData(Qt.ItemDataRole.UserRole, track.filePath)
                self.table.setItem(i, col, item)

            # Genre-Badge
            genre_item = QTableWidgetItem(detected_genre)
            fg_color, bg_color = GENRE_COLORS.get(detected_genre, GENRE_DEFAULT)
            genre_item.setForeground(QColor(fg_color))
            genre_item.setBackground(QColor(bg_color))
            self.table.setItem(i, 8, genre_item)

            # Genre Confidence
            conf_item = QTableWidgetItem(
                f"{genre_confidence * 100:.0f}%" if genre_confidence > 0 else "-"
            )
            self.table.setItem(i, 9, conf_item)

            # Mix In / Mix Out
            mix_in_item = QTableWidgetItem(
                f"{int(track.mix_in_point // 60):02d}:{int(track.mix_in_point % 60):02d} ({track.mix_in_bars} bars)"
            )
            mix_out_item = QTableWidgetItem(
                f"{int(track.mix_out_point // 60):02d}:{int(track.mix_out_point % 60):02d} ({track.mix_out_bars} bars)"
            )
            self.table.setItem(i, 10, mix_in_item)
            self.table.setItem(i, 11, mix_out_item)

            # Advanced Features (Phase 3)
            bass_val = getattr(track, 'avg_bass', 0)
            bass_item = QTableWidgetItem(f"{bass_val:.0f}%")
            self.table.setItem(i, 12, bass_item)
            
            # Texture Match Score
            texture_val = 0.0
            if i > 0:
                from hpg_core.dj_brain import _calculate_texture_similarity
                texture_val = _calculate_texture_similarity(
                    getattr(self.playlist[i-1], 'timbre_fingerprint', []),
                    getattr(track, 'timbre_fingerprint', [])
                )
            
            if i > 0:
                from hpg_core.theme import get_7_scale_color, get_texture_label
                texture_text = get_texture_label(texture_val)
                texture_item = QTableWidgetItem(texture_text)
                texture_item.setForeground(QColor(get_7_scale_color(texture_val)))
            else:
                texture_item = QTableWidgetItem("-")
            
            self.table.setItem(i, 13, texture_item)

            # Transition-Score (moved to column 14)
            from hpg_core.theme import get_7_scale_color
            score_item = QTableWidgetItem(f"{transition_score}%")
            score_item.setBackground(QColor(get_7_scale_color(transition_score / 100)))
            score_item.setForeground(QColor("white"))
            self.table.setItem(i, 14, score_item)

        self.table.setUpdatesEnabled(True)

    def _on_rows_moved(self, *args):
        """Drag-and-Drop Reorder Handler."""
        if not self.playlist:
            return

        # W2: O(N) Dict-Lookup statt O(N2) verschachtelter Loop
        track_by_name = {t.fileName: t for t in self.playlist}
        reordered_playlist = []
        for i in range(self.table.rowCount()):
            track_name_item = self.table.item(i, 1)
            if track_name_item:
                track = track_by_name.get(track_name_item.text())
                if track:
                    reordered_playlist.append(track)

        self.playlist = reordered_playlist
        self._update_table_after_reorder()
        self.playlist_reordered.emit()

    def _update_table_after_reorder(self):
        """Nummerierung, Textur-Klangwerte und Transition-Scores fehlerfrei aktualisieren."""
        for i in range(self.table.rowCount()):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

            transition_score = 0
            texture_val = 0.0
            if i > 0 and i < len(self.playlist):
                prev_track = self.playlist[i - 1]
                current_track = self.playlist[i]
                compatibility = calculate_enhanced_compatibility(
                    prev_track, current_track, self.bpm_tolerance
                )
                transition_score = int(compatibility.overall_score * 100)
                
                # Textur nach Reordering ebenfalls neu berechnen
                from hpg_core.dj_brain import _calculate_texture_similarity
                texture_val = _calculate_texture_similarity(
                    getattr(prev_track, 'timbre_fingerprint', []),
                    getattr(current_track, 'timbre_fingerprint', [])
                )

            # Spalte 13: Textur-Klangwert aktualisieren
            if i > 0:
                from hpg_core.theme import get_7_scale_color, get_texture_label
                texture_text = get_texture_label(texture_val)
                texture_item = QTableWidgetItem(texture_text)
                texture_item.setForeground(QColor(get_7_scale_color(texture_val)))
            else:
                texture_item = QTableWidgetItem("-")
            self.table.setItem(i, 13, texture_item)

            # Spalte 14: Transition-Score aktualisieren (Korrektur des Spaltenbugs!)
            from hpg_core.theme import get_7_scale_color
            score_item = QTableWidgetItem(f"{transition_score}%")
            score_item.setBackground(QColor(get_7_scale_color(transition_score / 100)))
            score_item.setForeground(QColor("white"))
            self.table.setItem(i, 14, score_item)

        # Quality neu berechnen
        self.quality_metrics = calculate_playlist_quality(
            self.playlist, self.bpm_tolerance
        )
        self._update_quality_display()
        self.transition_recommendations = compute_transition_recommendations(
            self.playlist, bpm_tolerance=self.bpm_tolerance
        )


class MixTipsPanel(QWidget):
    """Mix-Empfehlungen als Scroll-Cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.transition_recommendations = []
        # Mapping: enumerate-Index → QVBoxLayout der jeweiligen Karte
        self._card_layouts: dict[int, QVBoxLayout] = {}
        # Mapping: enumerate-Index → TransitionPreviewWidget
        self._preview_widgets: dict[int, TransitionPreviewWidget] = {}
        # Aktiver Render-Worker (kann None sein)
        self._render_worker: TransitionRenderWorker | None = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container_layout.setContentsMargins(8, 8, 8, 8)
        self.container_layout.setSpacing(8)
        self.scroll.setWidget(self.container)

    def set_recommendations(self, recommendations):
        self.transition_recommendations = recommendations
        # W4: Batch-Update
        self.scroll.setUpdatesEnabled(False)
        try:
            self._populate()
        finally:
            self.scroll.setUpdatesEnabled(True)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _populate(self):
        self._clear_layout(self.container_layout)
        # Karten-Layout-Referenzen zuruecksetzen (neue Karten werden gleich angelegt)
        self._card_layouts = {}

        if not self.transition_recommendations:
            empty_label = QLabel("No transition tips available yet.")
            empty_label.setStyleSheet(
                f"QLabel {{ color: {COLORS['text_secondary']}; font-style: italic; margin: 12px; }}"
            )
            self.container_layout.addWidget(empty_label)
            self.container_layout.addStretch()
            return

        for card_index, rec in enumerate(self.transition_recommendations):
            bg_color, accent_color = RISK_STYLES.get(rec.risk_level, RISK_DEFAULT)

            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_color};
                    border-radius: 0px;
                    border: 1px solid {accent_color};
                    padding: 12px;
                }}
            """)

            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(6)

            # Titel
            from_genre = getattr(rec.from_track, "detected_genre", "") or ""
            to_genre = getattr(rec.to_track, "detected_genre", "") or ""
            title_text = (
                f"{rec.index + 1}. {rec.from_track.fileName} -> {rec.to_track.fileName}"
            )
            title = QLabel(title_text)
            title.setStyleSheet(
                f"QLabel {{ font-size: 13px; font-weight: bold; color: {COLORS['text_bright']}; }}"
            )
            card_layout.addWidget(title)

            # Genre-Badge Zeile
            if (
                from_genre
                and from_genre != "Unknown"
                and to_genre
                and to_genre != "Unknown"
            ):
                from_color = GENRE_COLORS.get(from_genre, GENRE_DEFAULT)[0]
                to_color = GENRE_COLORS.get(to_genre, GENRE_DEFAULT)[0]
                genre_label = QLabel(
                    f'<span style="color: {from_color}; font-weight: bold;">'
                    f"{html_mod.escape(str(from_genre))}</span>"
                    f" -> "
                    f'<span style="color: {to_color}; font-weight: bold;">'
                    f"{html_mod.escape(str(to_genre))}</span>"
                )
                genre_label.setStyleSheet("QLabel { font-size: 11px; }")
                card_layout.addWidget(genre_label)

            # Risk-Summary
            risk_display = RISK_LABELS.get(rec.risk_level, rec.risk_level)
            summary = QLabel(
                f"{risk_display} | Score {rec.compatibility_score}/100 | "
                f"BPM {rec.bpm_delta:+.1f} | Energy {rec.energy_delta:+d}"
            )
            summary.setStyleSheet(
                f"QLabel {{ color: {accent_color}; font-weight: 600; }}"
            )
            card_layout.addWidget(summary)

            # Transition-Typ Badge
            t_type = getattr(rec, "transition_type", "blend")
            t_label = TRANSITION_TYPE_LABELS.get(t_type, t_type)
            t_desc = TRANSITION_TYPE_DESCRIPTIONS.get(t_type, "")
            t_color = TRANSITION_TYPE_COLORS.get(t_type, COLORS["text_secondary"])
            type_badge = QLabel(f"Empfohlene Technik: {t_label}")
            type_badge.setToolTip(t_desc)
            type_badge.setStyleSheet(
                f"QLabel {{ color: {t_color}; font-weight: 600; font-size: 12px; "
                f"background-color: {COLORS['bg_input']}; "
                f"border-radius: 0px; padding: 4px 8px; }}"
            )
            card_layout.addWidget(type_badge)

            # Timing — paar-spezifische Werte wenn verfuegbar, sonst Standard
            dj_rec = rec.dj_rec
            if dj_rec and dj_rec.adjusted_mix_out_a >= 0.0:
                # Angepasste Mix-Points aus calculate_paired_mix_points()
                timing_text = (
                    f"Mix-Out A: {dj_rec.adjusted_mix_out_a:.1f}s | "
                    f"Mix-In B: {dj_rec.adjusted_mix_in_b:.1f}s | "
                    f"Overlap: {dj_rec.overlap_seconds:.1f}s "
                    f"(Fade out {rec.fade_out_start:.1f}s -> {rec.fade_out_end:.1f}s)"
                )
            else:
                timing_text = (
                    f"Fade out {rec.fade_out_start:.1f}s -> {rec.fade_out_end:.1f}s | "
                    f"Fade in starts {rec.fade_in_start:.1f}s | Mix entry {rec.mix_entry:.1f}s | "
                    f"Overlap {rec.overlap:.1f}s"
                )
            timing = QLabel(timing_text)
            timing.setStyleSheet(f"QLabel {{ color: {COLORS['text_secondary']}; }}")
            card_layout.addWidget(timing)

            # Notes in drei Kategorien aufsplitten
            notes_text = rec.notes or ""
            notes_parts = [p.strip() for p in notes_text.split(";") if p.strip()]

            dj_brain_parts = []
            desc_parts = []
            meta_parts = []

            for part in notes_parts:
                if part.startswith(
                    ("Mix:", "EQ:", "Transition:", "BPM:", "Key:", "Energy:")
                ):
                    dj_brain_parts.append(part)
                elif part.startswith("!"):
                    dj_brain_parts.append(part)
                elif part.startswith(
                    (
                        "Ideal:",
                        "Gut:",
                        "Smooth:",
                        "Riskant:",
                        "Mutig:",
                        "Standard:",
                        "OK:",
                        "Struktur:",
                    )
                ):
                    dj_brain_parts.append(part)
                elif part.startswith("[") and part.endswith("]"):
                    meta_parts.append(part)
                elif any(
                    kw in part
                    for kw in (
                        "Tonart",
                        "BPM",
                        "Energie",
                        "Harmoni",
                        "Sichere",
                        "Solide",
                        "Machbar",
                        "Push",
                        "stabil",
                        "steigt",
                        "faellt",
                        "Pitch",
                        "ueberblend",
                        "nahtlos",
                        "allein",
                        "mixbar",
                        "erfahren",
                        "Clash",
                    )
                ):
                    desc_parts.append(part)
                else:
                    meta_parts.append(part)

            # DJ Brain Mix-Technik
            if dj_brain_parts:
                dj_text = " | ".join(dj_brain_parts)
                dj_label = QLabel(dj_text)
                dj_label.setWordWrap(True)
                dj_label.setStyleSheet(
                    f"QLabel {{ color: {COLORS['accent_primary']}; font-weight: 600; "
                    f"background-color: {COLORS['bg_input']}; "
                    f"border-radius: 0px; padding: 4px 8px; }}"
                )
                card_layout.addWidget(dj_label)

            # Beschreibung
            if desc_parts:
                desc_text = " | ".join(desc_parts)
                desc_label = QLabel(desc_text)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet(
                    f"QLabel {{ color: {COLORS['text_primary']}; font-size: 12px; padding: 3px 0px; }}"
                )
                card_layout.addWidget(desc_label)

            # Meta-Info
            if meta_parts:
                meta_text = " | ".join(meta_parts)
                meta_label = QLabel(meta_text)
                meta_label.setWordWrap(True)
                meta_label.setStyleSheet(
                    f"QLabel {{ color: {COLORS['text_secondary']}; font-size: 11px; }}"
                )
                card_layout.addWidget(meta_label)

            # Karten-Layout merken fuer spaeteres Einhaengen des PreviewWidgets
            self._card_layouts[card_index] = card_layout

            self.container_layout.addWidget(card)

        self.container_layout.addStretch()

    # ------------------------------------------------------------------
    # Transition-Preview-Integration
    # ------------------------------------------------------------------

    def setup_transition_previews(self, transitions: list):
        """
        Erstellt TransitionPreviewWidget fuer jeden Uebergang und
        startet den TransitionRenderWorker im Hintergrund.
        Muss nach set_recommendations() aufgerufen werden.
        """
        self._cleanup_existing_previews()
        self._preview_widgets = {}

        for i, tr in enumerate(transitions):
            widget = TransitionPreviewWidget(i, tr, self)
            self._preview_widgets[i] = widget
            self._insert_preview_widget(i, widget)

        # Worker starten — rendert alle Clips sequenziell im Hintergrund
        self._render_worker = TransitionRenderWorker(transitions)
        self._render_worker.clip_ready.connect(self._on_clip_ready)
        self._render_worker.clip_error.connect(self._on_clip_error)
        self._render_worker.start()

    def _insert_preview_widget(self, index: int, widget: TransitionPreviewWidget):
        """Haengt das Preview-Widget an das card_layout des jeweiligen Uebergangs."""
        if index in self._card_layouts:
            self._card_layouts[index].addWidget(widget)

    def _cleanup_existing_previews(self):
        """Laufenden Worker stoppen, Widgets entfernen, Temp-Dateien loeschen."""
        if self._render_worker is not None:
            # Signale trennen, damit die UI des Panels nicht mehr beeinflusst wird
            try:
                self._render_worker.clip_ready.disconnect(self._on_clip_ready)
                self._render_worker.clip_error.disconnect(self._on_clip_error)
            except:
                pass

            self._render_worker.request_cancel()

            # Alten Thread asynchron im Hintergrund fertigstellen lassen,
            # um Freezes (durch blockierendes wait()) zu vermeiden.
            # Da dieser Thread eindeutige Dateinamen hat, gibt es keine Konflikte.
            old_worker = self._render_worker
            
            def clean_and_delete():
                try:
                    old_worker.cleanup()
                except:
                    pass
                old_worker.deleteLater()
                
            old_worker.finished.connect(clean_and_delete)
            self._render_worker = None
            
        self._preview_widgets = {}

    def _on_clip_ready(self, index: int, wav_path: str):
        """Aufgerufen wenn ein Clip fertig gerendert ist."""
        if index in self._preview_widgets:
            self._preview_widgets[index].set_wav_path(wav_path)

    def _on_clip_error(self, index: int, error_msg: str):
        """Aufgerufen wenn Rendering eines Clips fehlgeschlagen ist."""
        if index in self._preview_widgets:
            self._preview_widgets[index].set_error(error_msg)


class TimelinePanel(QWidget):
    """Set Timing — HTML Timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

    def set_timeline(self, playlist):
        """Timeline aus Playlist berechnen und als HTML rendern."""
        if not playlist:
            self.text_edit.setHtml("<p>Keine Playlist vorhanden.</p>")
            return

        timeline = compute_set_timeline(playlist)
        summary = get_set_timing_summary(timeline)

        phase_colors = PHASE_COLORS
        phase_labels = PHASE_LABELS

        html = f"{html_style_block()}<h3>Set Timeline</h3>"

        # Uebersicht
        overflow = summary.get("overflow_seconds", 0)
        overflow_sign = "+" if overflow > 0 else ""
        html += f"""
      <table style="margin: 10px 0; border-collapse: collapse;">
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Gesamtzeit:</td>
          <td style="padding: 4px 12px;">{summary["total_time"]}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Zielzeit:</td>
          <td style="padding: 4px 12px;">{summary["target_time"]}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Abweichung:</td>
          <td style="padding: 4px 12px;">{overflow_sign}{overflow:.0f}s ({summary["overflow"]})</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Peak Track:</td>
          <td style="padding: 4px 12px;">{html_mod.escape(str(summary.get("peak_track", "-")))}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Peak bei:</td>
          <td style="padding: 4px 12px;">{summary.get("peak_time", "-")}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Tracks:</td>
          <td style="padding: 4px 12px;">{summary["track_count"]}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; font-weight: bold;">Ø Dauer/Track:</td>
          <td style="padding: 4px 12px;">{summary["avg_track_duration"]}</td>
        </tr>
      </table>
      """

        # Phasen-Uebersicht
        phase_breakdown = summary.get("phase_breakdown", {})
        if phase_breakdown:
            html += "<h4>Energie-Phasen</h4>"
            html += "<table style='margin: 8px 0; border-collapse: collapse;'>"
            for phase, count in phase_breakdown.items():
                color = phase_colors.get(phase, COLORS["text_secondary"])
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
            f"<tr style='background: {COLORS['bg_panel']}; font-weight: bold;'>"
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
            color = phase_colors.get(phase, COLORS["text_secondary"])

            peak_marker = " *" if entry.is_peak else ""
            bg = (
                COLORS["bg_selected"]
                if entry.is_peak
                else (COLORS["bg_table_alt"] if i % 2 else COLORS["bg_card"])
            )

            overlap_str = (
                f"{entry.overlap_with_next:.0f}s"
                if entry.overlap_with_next > 0
                else "—"
            )
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
        html += f"<p style='color: {COLORS['text_secondary']}; font-size: 11px;'>"
        html += "* = Peak Track | Overlap = Uebergangszeit zum naechsten Track"
        html += "</p>"

        self.text_edit.setHtml(html)


class AnalyticsPanel(QWidget):
    """Quality Analysis — HTML Bericht."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

    def set_analytics(self, quality_metrics):
        """Analytics-HTML aus Quality-Metriken generieren."""
        if not quality_metrics:
            self.text_edit.setHtml("<p>Keine Analyse-Daten vorhanden.</p>")
            return

        html = f"""{html_style_block()}
<h3>Playlist Quality Analysis</h3>

<h4>Overall Scores</h4>
<ul>
<li><b>Overall Quality:</b> {quality_metrics.get("overall_score", 0):.1%}</li>
<li><b>Harmonic Flow:</b> {quality_metrics.get("harmonic_flow", 0):.1%}</li>
<li><b>Energy Consistency:</b> {quality_metrics.get("energy_consistency", 0):.1%}</li>
<li><b>BPM Smoothness:</b> {quality_metrics.get("bpm_smoothness", 0):.1%}</li>
</ul>

<h4>Detailed Metrics</h4>
<ul>
<li><b>Average Harmonic Score:</b> {quality_metrics.get("avg_harmonic_score", 0):.1f}/100</li>
<li><b>Average Energy Jump:</b> {quality_metrics.get("avg_energy_jump", 0):.1f}</li>
<li><b>Average BPM Jump:</b> {quality_metrics.get("avg_bpm_jump", 0):.1f}</li>
</ul>

<h4>Recommendations</h4>
"""

        overall_score = quality_metrics.get("overall_score", 0)
        if overall_score >= 0.8:
            html += "<p><b>Excellent playlist!</b> Great flow for DJ sets.</p>"
        elif overall_score >= 0.6:
            html += "<p><b>Good playlist.</b> Minor improvements possible.</p>"
        else:
            html += "<p><b>Consider adjustments.</b> Try a different algorithm or adjust BPM tolerance.</p>"

        if quality_metrics.get("harmonic_flow", 0) < 0.6:
            html += "<p>Try increasing harmonic strictness or using 'Harmonic Flow'..</p>"
        if quality_metrics.get("energy_consistency", 0) < 0.6:
            html += "<p>Consider 'Context Flow' or 'Energy Wave' for better energy flow.</p>"
        if quality_metrics.get("bpm_smoothness", 0) < 0.6:
            html += (
                "<p>Try increasing BPM tolerance or using 'Consistent' algorithm.</p>"
            )

        self.text_edit.setHtml(html)


# ══════════════════════════════════════════════════════════════════
# MainWindow — Sidebar-Layout mit 5 Content-Panels
# ══════════════════════════════════════════════════════════════════


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from hpg_core import __version__ as hpg_version
        self.setWindowTitle(f"Harmonic Playlist Generator v{hpg_version}")
        self.resize(1100, 750)
        self.playlist = []
        self.quality_metrics = {}
        self.current_playlist_mode = "Harmonic Flow"
        self.current_bpm_tolerance = 3.0
        self.worker = None
        self.ai_worker = None

        self.init_ui()
        self.connect_signals()
        self.check_dependencies_and_warn()

    def check_dependencies_and_warn(self):
        """Ueberprueft wichtige Abhaengigkeiten und warnt den Benutzer aktiv vor eingeschraenkten System-Diensten."""
        pedalboard_installed = True
        try:
            import pedalboard
        except ImportError:
            pedalboard_installed = False

        import requests
        from hpg_core import config
        
        ai_provider = config.AI_PROVIDER
        url = config.AI_API_URL_LMSTUDIO if ai_provider == "LM Studio" else config.AI_API_URL_OLLAMA
        
        ai_online = False
        try:
            # Schneller Verbindungs-Check mit 0.3s Timeout
            requests.get(url.replace("/chat/completions", ""), timeout=0.3)
            ai_online = True
        except Exception:
            ai_online = False

        warnings = []
        if not pedalboard_installed:
            warnings.append("• Spotify-Pedalboard fehlt: Frequenzweichen (EQ-Swap) werden ueber eine Scipy-Alternative berechnet. Der echte Dynamik-Compressor ist inaktiv.")
        if not ai_online:
            # M4-Fix: Hinweis passend zum gewaehlten Provider statt hardcodiert Ollama
            port = "1234" if ai_provider == "LM Studio" else "11434"
            warnings.append(f"• Lokaler KI-Server ({ai_provider}) ist offline: Der AI-Layer ist inaktiv. Moods und Mixing-Tips bleiben leer. Bitte starten Sie {ai_provider} auf Port {port}.")

        if warnings:
            warn_text = "System-Hinweis: Einige Dienste sind eingeschraenkt (Fuer Details hier hovern)"
            self.status_bar.set_status(warn_text)
            self.status_bar.setToolTip("\n".join(warnings))
            self.status_bar.setStyleSheet("QStatusBar { background-color: #2b1f1a; color: #ffaa00; font-weight: bold; }")

    def init_ui(self):
        # Zentrales Widget
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar links
        self.sidebar = SidebarWidget()
        main_layout.addWidget(self.sidebar)

        # Rechte Seite: Toolbar + Content + StatusBar
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Toolbar
        self.toolbar = ToolbarWidget()
        right_layout.addWidget(self.toolbar)

        # Content-Stack (5 Panels statt 3 Views)
        self.content_stack = QStackedWidget()

        self.library_panel = LibraryPanel()
        self.playlist_panel = PlaylistPanel()
        self.mix_tips_panel = MixTipsPanel()
        self.timeline_panel = TimelinePanel()
        self.analytics_panel = AnalyticsPanel()

        self.content_stack.addWidget(self.library_panel)  # Index 0
        self.content_stack.addWidget(self.playlist_panel)  # Index 1
        self.content_stack.addWidget(self.mix_tips_panel)  # Index 2
        self.content_stack.addWidget(self.timeline_panel)  # Index 3
        self.content_stack.addWidget(self.analytics_panel)  # Index 4

        right_layout.addWidget(self.content_stack, 1)

        # StatusBar
        self.status_bar = StatusBarWidget()
        right_layout.addWidget(self.status_bar)

        main_layout.addLayout(right_layout, 1)
        self.setCentralWidget(central)

    def _setup_shortcuts(self):
        """Keyboard Shortcuts: Ctrl+G, Ctrl+E, Tasten 1-5 fuer Sidebar-Navigation."""
        # Ctrl+G → Playlist generieren
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self.start_analysis)
        # Ctrl+E → Export
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self.export_playlist)
        # Tasten 1-5 → Sidebar-Panel direkt anwaehlen
        for i in range(5):
            QShortcut(QKeySequence(str(i + 1)), self).activated.connect(
                lambda idx=i: self.sidebar.set_active(idx)
            )

    def connect_signals(self):
        self._setup_shortcuts()

        # Sidebar → Content-Stack
        self.sidebar.nav_changed.connect(self._on_nav_changed)

        # Logging-Signal mit dem Live-Terminal verbinden
        global_log_emitter.log_written.connect(
            self.library_panel.progress_widget.append_log
        )

        # Library-Panel
        self.library_panel.select_folder_button.clicked.connect(self.select_folder)
        self.library_panel.folder_selected.connect(self._on_folder_selected)
        self.library_panel.strategy_combo.currentTextChanged.connect(
            self._set_playlist_strategy
        )
        self.library_panel.bpm_tolerance_slider.valueChanged.connect(
            lambda v: self._set_bpm_tolerance(float(v))
        )
        self.library_panel.start_analysis.connect(self.start_analysis)

        # Toolbar Quick-Actions
        self.toolbar.generate_clicked.connect(self.start_analysis)
        self.toolbar.export_clicked.connect(self.export_playlist)

        # StatusBar
        self.status_bar.cancel_clicked.connect(self.cancel_analysis)

        # Playlist-Panel
        self.playlist_panel.export_clicked.connect(self.export_playlist)
        self.playlist_panel.preview_clicked.connect(self.preview_transitions)
        self.playlist_panel.restart_clicked.connect(self.restart_app)
        self.playlist_panel.playlist_reordered.connect(self._on_playlist_reordered)

    def _on_nav_changed(self, index):
        self.content_stack.setCurrentIndex(index)

    def _on_folder_selected(self, path):
        """Folder ausgewaehlt — Toolbar aktualisieren."""
        folder_name = os.path.basename(path)
        self.toolbar.set_info(f"Folder: {folder_name}")
        self.toolbar.set_generate_enabled(True)

    def _set_playlist_strategy(self, mode):
        self.current_playlist_mode = mode

    def _set_bpm_tolerance(self, tolerance):
        self.current_bpm_tolerance = tolerance

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder_path:
            self.library_panel.set_folder_path(folder_path)

    def start_analysis(self):
        """Analyse starten — Progress in StatusBar, aktueller Content bleibt."""
        # H2-Fix: Doppelstart-Schutz — Ctrl+G umgeht den deaktivierten Button;
        # ohne Guard wuerde der laufende Worker verwaisen (zweiter ProcessPool)
        if self.worker is not None and self.worker.isRunning():
            self.status_bar.set_status("Analyse laeuft bereits...")
            return

        settings = self.library_panel.get_current_settings()

        if not settings["folder"]:
            QMessageBox.warning(
                self, "No Folder Selected", "Please select a music folder first."
            )
            return

        # Buttons deaktivieren
        self.library_panel.start_button.setEnabled(False)
        self.toolbar.set_generate_enabled(False)

        # StatusBar: Progress zeigen
        self.status_bar.show_progress()
        self.status_bar.set_status("Starting analysis...")

        # Progress und Steps initialisieren
        self.library_panel.progress_widget.reset_steps()
        self.library_panel.progress_widget.set_step_status(0, "working")

        # Worker erstellen und starten
        self.worker = AnalysisWorker(
            folder_path=settings["folder"],
            mode=settings["strategy"],
            bpm_tolerance=settings["bpm_tolerance"],
            advanced_params=settings["advanced_params"],
        )

        # Worker-Signale an StatusBar & progress_widget
        self.worker.progress.connect(self.status_bar.set_progress)
        self.worker.progress.connect(self.library_panel.progress_widget.set_progress)
        self.worker.phase_changed.connect(self.library_panel.progress_widget.set_step_status)
        self.worker.status_update.connect(self.status_bar.set_status)
        self.worker.finished.connect(self.analysis_finished)

        self.worker.start()

    def cancel_analysis(self):
        """Analyse abbrechen — cooperative shutdown."""
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            if not self.worker.wait(5000):
                self.worker.terminate()
                self.worker.wait()

        self.library_panel.start_button.setEnabled(True)
        self.toolbar.set_generate_enabled(True)
        self.status_bar.hide_progress()
        self.status_bar.set_status("Analysis cancelled.")
        self.library_panel.progress_widget.reset_steps()


    def on_ai_finished(self, track_path, ai_data):
        """Update the playlist table with AI data."""
        # Moods extrahieren
        moods = ai_data.get("moods", [])
        if isinstance(moods, list):
            mood_str = ", ".join(str(m) for m in moods)
        else:
            mood_str = str(moods)

        # Sub-Genre voranstellen falls vorhanden (z.B. "[Peak-time Techno] dark, driving")
        sub_genre = ai_data.get("sub_genre", "")
        if sub_genre:
            mood_str = f"[{sub_genre}] {mood_str}".strip()

        # Logge den Erfolg
        import logging
        import os
        logger = logging.getLogger("hpg_core.ai_engine")
        logger.info(f"AI result for '{os.path.basename(track_path)}': {mood_str}")

        # Speichere die ai_metadata im Track-Objekt und im Cache!
        from hpg_core.caching import generate_cache_key, cache_track
        
        found_track = None
        found_row = -1
        
        # Zeile finden
        for row in range(self.playlist_panel.table.rowCount()):
            item = self.playlist_panel.table.item(row, 1) # Artist/Title column has filePath in UserRole
            if item and item.data(Qt.ItemDataRole.UserRole) == track_path:
                found_row = row
                break

        for track in self.playlist:
            if track.filePath == track_path:
                track.ai_metadata = ai_data
                
                # Check for AI recommended mix points
                ai_mix_in = ai_data.get("mix_in_time")
                ai_mix_out = ai_data.get("mix_out_time")
                
                try:
                    if ai_mix_in is not None and ai_mix_out is not None:
                        val_in = float(ai_mix_in)
                        val_out = float(ai_mix_out)
                        
                        if 0 <= val_in < val_out <= track.duration and val_out > 0:
                            # AI-Werte aufs Phrasen-Gitter quantisieren (DJ-Konvention:
                            # Mix-In ceil nach Intro, Mix-Out floor vor Outro)
                            from hpg_core.dj_brain import align_ai_mix_points
                            val_in, val_out = align_ai_mix_points(
                                val_in, val_out, track.bpm, track.duration,
                                getattr(track, "phrase_unit", 8) or 8,
                                anchor=getattr(track, "first_downbeat", 0.0) or 0.0,
                            )
                            track.mix_in_point = round(val_in, 2)
                            track.mix_out_point = round(val_out, 2)

                            # Recalculate bars
                            from hpg_core.config import METER
                            seconds_per_bar = (60.0 / track.bpm) * METER if track.bpm > 0 else 2.0
                            track.mix_in_bars = int(round(track.mix_in_point / seconds_per_bar))
                            track.mix_out_bars = int(round(track.mix_out_point / seconds_per_bar))
                            logger.info(f"AI updated mix points for '{os.path.basename(track_path)}': in={track.mix_in_bars} bars, out={track.mix_out_bars} bars")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse AI mix points: {e}")
                
                # Persist to SQLite Cache
                cache_key = generate_cache_key(track.filePath)
                if cache_key:
                    cache_track(cache_key, track)
                found_track = track
                break

        if found_row != -1 and found_track:
            # 1. Update AI Insights column (col 15)
            ai_item = QTableWidgetItem(mood_str)
            ai_item.setToolTip(ai_data.get("description", ""))
            self.playlist_panel.table.setItem(found_row, 15, ai_item)
            
            # 2. Update Mix In / Mix Out columns (col 10 & 11)
            mix_in_item = QTableWidgetItem(
                f"{int(found_track.mix_in_point // 60):02d}:{int(found_track.mix_in_point % 60):02d} ({found_track.mix_in_bars} bars)"
            )
            mix_out_item = QTableWidgetItem(
                f"{int(found_track.mix_out_point // 60):02d}:{int(found_track.mix_out_point % 60):02d} ({found_track.mix_out_bars} bars)"
            )
            self.playlist_panel.table.setItem(found_row, 10, mix_in_item)
            self.playlist_panel.table.setItem(found_row, 11, mix_out_item)
            
            # 3. Recalculate Transition Score for this track and the next track (col 14)
            from hpg_core.playlist import calculate_enhanced_compatibility, calculate_playlist_quality, compute_transition_recommendations
            from hpg_core.theme import get_7_scale_color
            
            # Recalculate for current row (compatibility to previous track)
            if found_row > 0:
                prev_track = self.playlist[found_row - 1]
                metrics = calculate_enhanced_compatibility(prev_track, found_track, self.playlist_panel.bpm_tolerance)
                score = int(metrics.overall_score * 100)
                score_item = QTableWidgetItem(f"{score}%")
                score_item.setBackground(QColor(get_7_scale_color(score / 100)))
                score_item.setForeground(QColor("white"))
                self.playlist_panel.table.setItem(found_row, 14, score_item)
                
            # Recalculate for next row (compatibility of next track to current track)
            if found_row < len(self.playlist) - 1:
                next_track = self.playlist[found_row + 1]
                metrics = calculate_enhanced_compatibility(found_track, next_track, self.playlist_panel.bpm_tolerance)
                score = int(metrics.overall_score * 100)
                score_item = QTableWidgetItem(f"{score}%")
                score_item.setBackground(QColor(get_7_scale_color(score / 100)))
                score_item.setForeground(QColor("white"))
                self.playlist_panel.table.setItem(found_row + 1, 14, score_item)
                
            # M1-Fix: KEINE Gesamtmetrik-Neuberechnung pro Track — das Signal
            # feuert pro AI-Ergebnis und calculate_playlist_quality ist O(n);
            # on_ai_worker_finished rechnet am Ende ohnehin einmal komplett

    def on_ai_worker_finished(self):
        """AI Analysis beendet — Phase 5 abschliessen und UI-Panels einmalig aktualisieren."""
        self.library_panel.progress_widget.set_step_status(4, "completed")
        
        # 4. Gesamtmetriken neu berechnen und UI-Panels updaten
        from hpg_core.playlist import calculate_playlist_quality, compute_transition_recommendations
        self.playlist_panel.quality_metrics = calculate_playlist_quality(self.playlist, self.playlist_panel.bpm_tolerance)
        self.playlist_panel.transition_recommendations = compute_transition_recommendations(self.playlist, self.playlist_panel.bpm_tolerance)
        
        # Badges im PlaylistPanel aktualisieren
        self.playlist_panel._update_quality_display()
        
        # Andere Panels aktualisieren
        self._on_playlist_reordered()

    def analysis_finished(self, playlist, quality_metrics):
        """Analyse fertig — Daten an alle Panels verteilen."""
        # Buttons wieder aktivieren
        self.library_panel.start_button.setEnabled(True)
        self.toolbar.set_generate_enabled(True)
        self.status_bar.hide_progress()

        # M4: Worker-Signale trennen und aufraeumen
        if self.worker:
            try:
                self.worker.progress.disconnect()
                self.worker.status_update.disconnect()
                self.worker.finished.disconnect()
            except TypeError:
                pass
            self.worker.deleteLater()
            self.worker = None
        # H3-Fix: ai_worker hier NICHT auf None setzen — sonst verwaist ein noch
        # laufender AI-Worker (QThread destroyed while running) und der
        # isRunning()-Check weiter unten waere toter Code

        # Leere Playlist? Fehler anzeigen.
        if not playlist:
            self.status_bar.set_status("Analysis returned no results.")
            self.library_panel.progress_widget.reset_steps()
            return

        self.playlist = playlist
        self.quality_metrics = quality_metrics

        # Transition-Empfehlungen berechnen
        transition_plan = compute_transition_recommendations(
            playlist, bpm_tolerance=self.current_bpm_tolerance
        )

        # Daten an alle Panels verteilen
        self.playlist_panel.set_playlist_data(
            playlist,
            quality_metrics,
            transition_recommendations=transition_plan,
            bpm_tolerance=self.current_bpm_tolerance,
        )
        self.mix_tips_panel.set_recommendations(transition_plan)
        # Transition-Audio-Previews rendern (Hintergrund-Worker)
        self.mix_tips_panel.setup_transition_previews(transition_plan)
        self.timeline_panel.set_timeline(playlist)
        self.analytics_panel.set_analytics(quality_metrics)

        # Toolbar aktualisieren
        overall = quality_metrics.get("overall_score", 0)
        self.toolbar.set_quality(overall)
        self.toolbar.set_export_enabled(True)
        self.toolbar.set_info(f"{len(playlist)} tracks | {self.current_playlist_mode}")

        # StatusBar
        self.status_bar.set_status(
            f"Complete — {len(playlist)} tracks, Quality {overall:.0%}"
        )

        # Automatisch zum Playlist-Panel wechseln
        self.sidebar.set_active(1)
        
        # AI Analysis starten
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.request_cancel()
            self.ai_worker.wait()
            
        ap = self.library_panel.advanced_params
        provider = ap.detected_provider or (
            "LM Studio" if ap.lmstudio_radio.isChecked() else "Ollama"
        )
        model = ap.model_combo.currentText()
        # base_url vom Auto-Detect (LM-Studio-Port dynamisch). Wenn None, startet der
        # Worker den Provider selbst nach (ensure_ready im Worker-Thread).
        base_url = ap.detected_base_url
        self.ai_worker = AIAnalysisWorker(
            playlist, provider=provider, model=model, base_url=base_url
        )

        # Phase 5: AI MOODS in Arbeit
        self.library_panel.progress_widget.set_step_status(4, "working")

        self.ai_worker.ai_finished.connect(self.on_ai_finished)
        self.ai_worker.finished.connect(self.on_ai_worker_finished)
        self.ai_worker.start()


    def _on_playlist_reordered(self):
        """Nach Drag-Drop: Quality und andere Panels aktualisieren."""
        self.playlist = self.playlist_panel.playlist
        self.quality_metrics = self.playlist_panel.quality_metrics

        # Mix-Tips und Timeline aktualisieren
        self.mix_tips_panel.set_recommendations(
            self.playlist_panel.transition_recommendations
        )
        # Transition-Audio-Previews nach Drag-Drop neu rendern
        self.mix_tips_panel.setup_transition_previews(
            self.playlist_panel.transition_recommendations
        )
        self.timeline_panel.set_timeline(self.playlist)
        self.analytics_panel.set_analytics(self.quality_metrics)

        # Toolbar aktualisieren
        overall = self.quality_metrics.get("overall_score", 0)
        self.toolbar.set_quality(overall)

    def export_playlist(self):
        """Playlist exportieren — M3U8 oder Rekordbox XML."""
        if not self.playlist:
            QMessageBox.warning(
                self,
                "No Playlist",
                "No playlist to export. Analyze audio files first.",
            )
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Playlist",
            f"HPG_Playlist_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "M3U8 Playlist (*.m3u8);;Rekordbox XML (*.xml);;All Files (*.*)",
        )

        if not file_path:
            return

        try:
            file_lower = file_path.lower()
            if selected_filter.startswith("Rekordbox") or file_lower.endswith(".xml"):
                self._export_rekordbox_xml(file_path)
            else:
                if not file_lower.endswith(".m3u8"):
                    file_path += ".m3u8"
                self._export_m3u8(file_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export playlist:\n{str(e)}",
            )

    def _export_m3u8(self, file_path: str):
        try:
            exporter = M3U8Exporter()
            playlist_name = f"HPG - {self.current_playlist_mode}"
            exporter.export(self.playlist, file_path, playlist_name)

            QMessageBox.information(
                self,
                "Export Successful",
                f"M3U8 Playlist exported!\n\n"
                f"Location: {file_path}\n"
                f"Tracks: {len(self.playlist)}\n"
                f"Compatible with Rekordbox, Serato, Traktor.",
            )
        except Exception as e:
            raise Exception(f"M3U8 export failed: {e}")

    def _export_rekordbox_xml(self, file_path: str):
        try:
            exporter = RekordboxXMLExporter()
            playlist_name = f"HPG - {self.current_playlist_mode}"
            exporter.export(self.playlist, file_path, playlist_name)

            QMessageBox.information(
                self,
                "Export Successful",
                f"Rekordbox XML exported!\n\n"
                f"Location: {file_path}\n"
                f"Tracks: {len(self.playlist)}\n"
                f"Import: File -> Import -> rekordbox xml",
            )
        except ImportError:
            QMessageBox.critical(
                self,
                "Library Missing",
                "pyrekordbox not installed! Falling back to M3U8...",
            )
            # L2-Fix: nur die Endung ersetzen, nicht jedes ".xml" im Pfad
            m3u8_path = os.path.splitext(file_path)[0] + ".m3u8"
            self._export_m3u8(m3u8_path)
        except Exception as e:
            raise Exception(f"Rekordbox XML export failed: {e}")

    def preview_transitions(self):
        """Transition Preview Dialog."""
        if not self.playlist:
            return

        if len(self.playlist) < 2:
            QMessageBox.information(
                self, "Preview", "Need at least 2 tracks to show transitions."
            )
            return

        transitions_info = "Transition Analysis:\n\n"
        for i in range(len(self.playlist) - 1):
            current = self.playlist[i]
            next_track = self.playlist[i + 1]
            compatibility = calculate_enhanced_compatibility(
                current, next_track, self.current_bpm_tolerance
            )

            transitions_info += (
                f"{i + 1} -> {i + 2}: "
                f"{os.path.basename(current.fileName)} -> "
                f"{os.path.basename(next_track.fileName)}\n"
            )
            transitions_info += (
                f"   Score: {compatibility.overall_score:.1%} "
                f"(Harmonic: {compatibility.harmonic_score}/100)\n"
            )
            transitions_info += f"   BPM: {current.bpm:.1f} -> {next_track.bpm:.1f}\n"
            transitions_info += (
                f"   Key: {current.camelotCode} -> {next_track.camelotCode}\n\n"
            )

        msg = QMessageBox(self)
        msg.setWindowTitle("Transition Preview")
        msg.setText("Transition Analysis")
        msg.setDetailedText(transitions_info)
        msg.exec()

    def restart_app(self):
        """Zurueck zum Library-Panel, Playlist verwerfen."""
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            if not self.worker.wait(5000):
                self.worker.terminate()
                self.worker.wait()

        self.playlist = []
        self.quality_metrics = {}
        self.toolbar.set_export_enabled(False)
        self.toolbar.quality_badge.hide()
        self.toolbar.set_info("No folder selected")
        self.status_bar.set_status("Ready")
        self.sidebar.set_active(0)
        self.content_stack.setCurrentIndex(0)

    def closeEvent(self, event):
        """M3: Worker sauber beenden beim Schliessen."""
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            if not self.worker.wait(3000):
                self.worker.terminate()
                self.worker.wait()
        # H4-Fix: auch den AI-Tagging-Worker beenden — sonst Crash/Hang
        # ("QThread destroyed while running") beim App-Close waehrend Tagging
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.request_cancel()
            if not self.ai_worker.wait(3000):
                self.ai_worker.terminate()
                self.ai_worker.wait()
        # Transition-Render-Worker stoppen und Temp-Dateien loeschen
        self.mix_tips_panel._cleanup_existing_previews()
        event.accept()


if __name__ == "__main__":
    # CRITICAL: Required for PyInstaller + multiprocessing on Windows
    # This MUST be the first line to prevent infinite process spawning
    multiprocessing.freeze_support()

    # Logging initialisieren (MUSS vor allen anderen Modulen passieren)
    from hpg_core import config as hpg_config
    setup_logging(hpg_config.LOG_LEVEL)

    # Qt-Logging-Handler hinzufügen
    qt_handler = QtLoggingHandler(global_log_emitter)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    qt_handler.setFormatter(formatter)
    logging.getLogger().addHandler(qt_handler)

    # Only clear cache if explicitly requested or on major version changes
    # Automatic clearing on every start is inefficient and can cause locking issues
    # init_cache() already handles version-based clearing safely with file locks
    pass

    init_cache()

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")
    apply_dark_theme(app)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())
