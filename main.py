import html as html_mod
import importlib
import logging
import multiprocessing

# Windowed Frozen-Build (console=False): sys.stdout/stderr sind None. Der
# multiprocessing-Fehlerhandler schreibt dorthin und crasht sonst mit
# "'NoneType' object has no attribute 'write'". Auf einen Null-Sink umleiten.
# MUSS vor freeze_support() stehen: im gefrorenen Worker fuehrt freeze_support()
# die Ziel-Funktion aus und beendet den Prozess per sys.exit() — Code dahinter
# wird im Worker nie erreicht, der Patch liefe sonst nur im GUI-Hauptprozess.
import sys as _sys


class _NullWriter:
    """Verwirft jede Ausgabe (kein Speicherwachstum wie StringIO)."""

    def write(self, _data):
        return len(_data) if _data else 0

    def flush(self):
        pass


if _sys.stdout is None:
    _sys.stdout = _NullWriter()
if _sys.stderr is None:
    _sys.stderr = _NullWriter()

# PyInstaller muss eingefrorene Multiprocessing-Worker vor Qt- und Audio-Imports
# in den Worker-Einstieg umleiten. Andernfalls initialisieren sie die GUI- und
# Native-Audio-Stacks und können auf Windows mit einem C-Level-Crash abbrechen.
multiprocessing.freeze_support()

import os
import re
import sys
import tempfile
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime
from enum import Enum

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
    QAbstractItemView,
    QFrame,
    QScrollArea,
    QStyledItemDelegate,
    QStyle,
    QRadioButton,
    QToolTip,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QThread,
    QUrl,
    QSize,
    QRect,
    QRectF,
    QPointF,
    QTimer,
    QObject,
    QEvent,
)
from PyQt6.QtGui import (
    QColor,
    QKeySequence,
    QShortcut,
    QTextCursor,
    QCursor,
    QPainter,
    QPen,
    QBrush,
    QFont,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from hpg_core.transition_renderer import TransitionClipSpec, _render_clip_subprocess_wrapper
from hpg_core.downbeat import DOWNBEAT_RELIABLE_MIN, REFERENCE_BEATGRID_CONFIDENCE
from hpg_core.parallel_analyzer import ParallelAnalyzer
from hpg_core.models import get_camelot_components, seconds_to_bars
from hpg_core.playlist import (
    STRATEGIES,
    calculate_playlist_quality,
    calculate_enhanced_compatibility,
    compute_transition_recommendations,
    compute_set_timeline,
    get_set_timing_summary,
    resolve_scoring_context,
    SUPPORTED_STRATEGY_PARAMETERS,
)
from hpg_core.exporters.m3u8_exporter import M3U8Exporter
from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter
from hpg_core.caching import init_cache
from hpg_core.logging_config import setup_logging
from hpg_core.theme import (
    COLORS,
    GENRE_COLORS,
    GENRE_DEFAULT,
    PHASE_COLORS,
    PHASE_LABELS,
    TRANSITION_TYPE_COLORS,
    TRANSITION_TYPE_LABELS,
    TRANSITION_TYPE_DESCRIPTIONS,
    TRANSITION_SCORE_TEXT,
    score_color,
    transition_score_style,
    html_style_block,
    apply_dark_theme,
    FONT_FAMILY,
)
from hpg_core.error_reporter import get_error_reporter
from hpg_core.resource_limits import sanitize_playlist as apply_resource_limits
# AUDIT-FIX F1 (2026-07-24): hpg_config war nur lokal in init_ui importiert;
# refresh_ai_providers() referenzierte es als Global -> NameError beim Aktivieren
# der KI-Checkbox (Button blieb dauerhaft deaktiviert). Import jetzt auf Modulebene.
from hpg_core import config as hpg_config
from hpg_core import candidate_choices

# H1-Fix (Audit 2026-07-17): Modul-Logger — TransitionRenderWorker.run
# referenzierte `logger` ohne Definition (NameError im Fehlerpfad)
logger = logging.getLogger(__name__)


class RunState(str, Enum):
    """Einzige Wahrheit fuer den Lebenszyklus eines Analyse-Laufs."""

    IDLE = "idle"
    AUDIO = "audio"
    AI = "ai"
    PLAYLIST = "playlist"
    PREVIEW = "preview"
    CANCELLING = "cancelling"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    CANCELLED = "cancelled"


ACTIVE_RUN_STATES = {
    RunState.AUDIO,
    RunState.AI,
    RunState.PLAYLIST,
    RunState.PREVIEW,
    RunState.CANCELLING,
}


def map_phase_progress(percent: float, start: float, end: float) -> int:
    """Mappt lokale 0..100-Prozente monoton in einen globalen Abschnitt."""
    bounded = max(0.0, min(100.0, float(percent)))
    return int(round(start + (end - start) * bounded / 100.0))


def resolve_transition_mix_points(transition) -> tuple[float, float, float]:
    """Loest die effektiven Mix-Punkte einer Transition auf.

    Paar-spezifische DJ-Brain-Werte (adjusted_*, Sentinel -1.0) haben Vorrang
    vor den per-Track-Werten. Audit 2026-07-17: vorher war dieses Muster
    dreifach kopiert (Render-Worker, Preview-Widget, Anzeige).

    Returns:
        (mix_out_a, mix_in_b, crossfade_seconds)
    """
    plan = getattr(transition, "plan", None)
    if plan is not None:
        return plan.mix_out_a, plan.mix_in_b, plan.overlap
    dj = transition.dj_rec
    track_mix_out = float(getattr(transition.from_track, "mix_out_point", -1.0))
    track_mix_in = float(getattr(transition.to_track, "mix_in_point", -1.0))
    mix_out = (
        dj.adjusted_mix_out_a
        if dj and dj.adjusted_mix_out_a >= 0.0
        else max(0.0, track_mix_out)
    )
    mix_in = (
        dj.adjusted_mix_in_b
        if dj and dj.adjusted_mix_in_b >= 0.0
        else max(0.0, track_mix_in)
    )
    crossfade = (
        dj.overlap_seconds
        if dj and dj.overlap_seconds > 0
        else float(transition.overlap or 16.0)
    )
    return mix_out, mix_in, crossfade


def format_mix_point_display(seconds: float, bars: int) -> str:
    """Formatiert Mixpunkte; der Schema-Sentinel wird als nicht gesetzt gezeigt."""
    if seconds < 0:
        return "--:-- (- bars)"
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d} ({bars} bars)"


# Kuerzel der zehn Teilwerte eines PairCandidate (Reihenfolge wie
# hpg_core.pair_candidates.FAKTOREN) fuer die Kandidatentabelle.
_TEILWERT_KUERZEL = (
    ("harmonic", "H"), ("bpm", "T"), ("energy", "E"), ("genre", "G"), ("groove", "Gr"),
    ("bass", "B"), ("timbre", "K"), ("mood", "S"), ("loudness", "L"), ("structure", "St"),
)


def kandidat_teilwerte_kurz(teilwerte: dict) -> str:
    """Teilwerte als Kurzform "H .75 T 1.0 ... L - St .07" (None -> "-")."""
    teile = []
    for name, kuerzel in _TEILWERT_KUERZEL:
        wert = teilwerte.get(name) if teilwerte else None
        if wert is None:
            text = "-"
        elif float(wert) >= 1.0:
            text = "1.0"
        else:
            text = f"{float(wert):.2f}"[1:]   # ".75"
        teile.append(f"{kuerzel} {text}")
    return " ".join(teile)


def mixpunkte_fuer_tabelle(index: int, track, recs) -> tuple:
    """Mix-In/Mix-Out fuer die Tabellenzeile `index`: aus der Empfehlung des
    Paars (Rang-1-Kandidat, Plan) wenn vorhanden, sonst Track-Wert (Analyse).
    Rueckgabe (mix_in, quelle_in, mix_out, quelle_out)."""
    mix_in = float(getattr(track, "mix_in_point", -1.0))
    mix_out = float(getattr(track, "mix_out_point", -1.0))
    quelle_in = quelle_out = "Analyse"
    recs = list(recs or [])
    if 0 < index <= len(recs):
        rec = recs[index - 1]
        plan = getattr(rec, "plan", None)
        rang = int(getattr(rec, "kandidat_aktiv", 0) or 0)
        if plan is not None and rang > 0:
            mix_in, quelle_in = float(plan.mix_in_b), f"Kandidat Rang {rang}"
    if index < len(recs):
        rec = recs[index]
        plan = getattr(rec, "plan", None)
        rang = int(getattr(rec, "kandidat_aktiv", 0) or 0)
        if plan is not None and rang > 0:
            mix_out, quelle_out = float(plan.mix_out_a), f"Kandidat Rang {rang}"
    return mix_in, quelle_in, mix_out, quelle_out


def _mixpunkt_items(index: int, track, recs) -> tuple:
    """Zwei QTableWidgetItems (Mix-In, Mix-Out) mit Quelle als Tooltip."""
    mix_in, q_in, mix_out, q_out = mixpunkte_fuer_tabelle(index, track, recs)
    bpm = float(getattr(track, "bpm", 0.0) or 0.0)

    def bars(sek, fallback):
        if sek < 0:
            return fallback
        return seconds_to_bars(sek, bpm) if bpm > 0 else fallback

    in_item = QTableWidgetItem(format_mix_point_display(mix_in, bars(mix_in, getattr(track, "mix_in_bars", 0))))
    out_item = QTableWidgetItem(format_mix_point_display(mix_out, bars(mix_out, getattr(track, "mix_out_bars", 0))))
    in_item.setToolTip(f"Quelle: {q_in}")
    out_item.setToolTip(f"Quelle: {q_out}")
    return in_item, out_item



class AIAnalysisWorker(QThread):
    """Worker thread for running AI analysis in the background."""
    ai_finished = pyqtSignal(str, dict)  # (track_path, metadata)
    progress = pyqtSignal(int, int)      # (current_track_index, total_tracks)
    failed = pyqtSignal(str)

    def __init__(self, playlist: list, provider: str = None, model: str = None,
                 base_url: str = None, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.provider = provider
        self.model = model
        self.base_url = base_url  # Voller Endpoint vom ai_launcher (Port dynamisch)
        self._should_cancel = False
        self.failure_reason = ""

    def request_cancel(self):
        self._should_cancel = True
        self.requestInterruption()

    def _ensure_ready(self):
        """
        Stellt sicher dass der Provider laeuft und ein Modell gewaehlt ist.
        Laeuft bereits im Worker-Thread → blockierend erlaubt, blockiert UI nicht.
        Wird nur aufgerufen wenn der Detect-Worker beim Start nichts geliefert hat
        (z.B. Server war aus) oder der Endpoint inzwischen weggefallen ist.
        """
        if self.base_url:
            return True
        try:
            from hpg_core import ai_launcher
            status = ai_launcher.detect_and_start(
                preferred=self.provider,
                preferred_model=self.model,
                cancel_check=self.isInterruptionRequested,
            )
            if status and status.running:
                self.base_url = status.base_url
                self.provider = status.name
                if status.active_model:
                    self.model = status.active_model
        except Exception as exc:
            logging.getLogger("hpg_core.ai_engine").error(
                "AI provider setup failed: %s", exc
            )
        return bool(self.base_url and self.provider and self.model)

    def _fail(self, reason):
        self.failure_reason = reason
        self.failed.emit(reason)

    def run(self):
        import logging
        import os
        logger = logging.getLogger("hpg_core.ai_engine")
        if not self._ensure_ready():
            self._fail("Kein einsatzbereiter KI-Provider oder kein Modell verfuegbar.")
            self.progress.emit(len(self.playlist), len(self.playlist))
            return
        logger.info(f"Starting AI Mood Tagging using {self.provider} (Model: {self.model})...")
        total_tracks = len(self.playlist)
        for i, track in enumerate(self.playlist):
            if self._should_cancel:
                logger.info("AI Mood Tagging cancelled by user.")
                break
            self.progress.emit(i, total_tracks)
            try:
                from hpg_core.ai_engine import ai_metadata_matches, fetch_ai_analysis
                if ai_metadata_matches(track, self.provider, self.model):
                    logger.info(
                        "[%s/%s] Passende KI-Metadaten bereits vorhanden; uebersprungen.",
                        i + 1,
                        total_tracks,
                    )
                    continue
                filename = os.path.basename(track.filePath)
                logger.info(f"[{i+1}/{total_tracks}] AI analyzing track: '{filename}'...")
                ai_data = fetch_ai_analysis(
                    track, provider=self.provider, model=self.model, url=self.base_url
                )
                if ai_data and not self._should_cancel:
                    # Cache-I/O kann auf einen extern gehaltenen SQLite-Lock bis
                    # zum Timeout warten. Es bleibt deshalb im AI-Worker und darf
                    # niemals den Qt-GUI-Thread blockieren.
                    track.ai_metadata = ai_data
                    try:
                        from hpg_core.caching import generate_cache_key, cache_track
                        cache_key = generate_cache_key(
                            track.filePath,
                            getattr(track, "rekordbox_signature", ""),
                        )
                        if cache_key:
                            cache_track(cache_key, track)
                    except Exception as cache_exc:
                        logger.warning(
                            "KI-Metadaten konnten nicht gecacht werden fuer '%s': %s",
                            filename,
                            cache_exc,
                        )
                    self.ai_finished.emit(track.filePath, ai_data)
                else:
                    reason = (
                        f"KI-Verarbeitung bei '{filename}' gestoppt: Provider- oder "
                        "Schemafehler. Bereits erzeugte Ergebnisse bleiben erhalten."
                    )
                    logger.warning(reason)
                    self._fail(reason)
                    break
            except Exception as e:
                reason = f"KI-Verarbeitung gestoppt: {e}"
                logger.error(reason, exc_info=True)
                self._fail(reason)
                break
        self.progress.emit(total_tracks, total_tracks)
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
                preferred=self.preferred,
                preferred_model=self.preferred_model,
                cancel_check=self.isInterruptionRequested,
            )
        except Exception:
            status = None
        # HPG-003: bei Abbruch (App-Close) kein Signal mehr in die sterbende UI
        if self.isInterruptionRequested():
            return
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

            # HPG-003: bei Abbruch (App-Close) kein Signal mehr emittieren
            if self.isInterruptionRequested():
                return
            if "choices" in resp_json and len(resp_json["choices"]) > 0:
                response_content = resp_json["choices"][0]["message"]["content"].strip()
                responded_model = resp_json.get("model", self.model)
                self.test_finished.emit(True, response_content, responded_model, latency)
            else:
                self.test_finished.emit(False, "Keine 'choices' in der Antwort des Providers.", self.model, latency)
        except Exception as e:
            latency = time.time() - start_time
            if self.isInterruptionRequested():
                return
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
            # HPG-003: cancel_check macht den bis zu 30-minuetigen Pull abbrechbar
            success = ai_launcher.ollama_pull(
                self.model, cancel_check=self.isInterruptionRequested
            )
            if self.isInterruptionRequested():
                return
            if success:
                self.pull_finished.emit(True, "")
            else:
                self.pull_finished.emit(False, f"Modell '{self.model}' konnte nicht geladen werden. Bitte stelle sicher, dass Ollama läuft und der Modellname korrekt ist.")
        except Exception as e:
            if self.isInterruptionRequested():
                return
            self.pull_finished.emit(False, str(e))


class DependencyCheckWorker(QThread):
    """Prueft optionale Dienste ohne den GUI-Thread zu blockieren."""

    checked = pyqtSignal(bool, bool, bool)
    # (pedalboard_installed, ai_online, rekordbox_running)

    def __init__(self, provider: str, url: str, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.url = url

    def run(self):
        try:
            importlib.import_module("pedalboard")
            pedalboard_installed = True
        except (ImportError, OSError):
            pedalboard_installed = False

        ai_online = False
        try:
            import requests

            requests.get(
                self.url.replace("/chat/completions", ""),
                timeout=(0.3, 0.3),
            )
            ai_online = True
        except Exception:
            ai_online = False

        # Prozesspruefung gehoert in den Worker: psutil iteriert ueber alle
        # laufenden Prozesse und das darf den GUI-Thread nicht blockieren.
        try:
            from hpg_core.rekordbox_importer import is_rekordbox_running

            rekordbox_running = is_rekordbox_running()
        except Exception:
            rekordbox_running = False

        if not self.isInterruptionRequested():
            self.checked.emit(pedalboard_installed, ai_online, rekordbox_running)


class AnalysisWorker(QThread):
    """Worker thread for running the analysis in the background."""

    progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    phase_changed = pyqtSignal(int, str)  # step_index, state ("inactive", "working", "completed")
    # AUDIT-FIX T1 (2026-07-24): eigenes Ergebnis-Signal, das NICHT das
    # eingebaute QThread.finished ueberschreibt. Vorher gab es kein Signal mehr,
    # das das echte Thread-Ende meldete -> deleteLater() konnte aus dem selbst
    # emittierten Signal heraus einen noch laufenden QThread zerstoeren
    # ("QThread: Destroyed while thread is still running").
    analysis_done = pyqtSignal(list, dict)  # playlist, quality_metrics
    rekordbox_coverage = pyqtSignal(object)  # RekordboxCoverage

    def __init__(
        self,
        folder_path,
        mode="Harmonic Flow",
        bpm_tolerance=2.0,
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

    def _report_rekordbox_coverage(self, analyzed_tracks):
        """Meldet, wie viele Tracks Rekordbox-Daten nutzen konnten.

        Laeuft bewusst im Worker-Thread. Der Importer-Singleton existiert nur
        in den Analyse-Subprozessen — der erste Zugriff im GUI-Prozess liest
        die komplette Rekordbox-DB und wuerde die Oberflaeche einfrieren.
        """
        try:
            from hpg_core.rekordbox_importer import get_rekordbox_importer

            paths = [t.filePath for t in analyzed_tracks if getattr(t, "filePath", "")]
            coverage = get_rekordbox_importer().summarize_coverage(paths)
        except Exception as e:
            # Ein Diagnose-Fehler darf ein fertiges Analyseergebnis nie kippen.
            logger.warning(f"Rekordbox-Abdeckung nicht ermittelbar: {e}")
            return

        if coverage.degraded:
            logger.warning(
                "Rekordbox-Abdeckung: %d von %d Tracks ohne nutzbare Daten "
                "(%d unanalysiert, %d mehrdeutig) -> Librosa-Vollanalyse.",
                coverage.degraded, coverage.total,
                coverage.without_analysis, coverage.ambiguous,
            )
        self.rekordbox_coverage.emit(coverage)

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
            scan_root = os.path.realpath(self.folder_path)
            scan_limit_reached = False
            for root, _, files in os.walk(self.folder_path):
                if self._should_cancel:
                    raise InterruptedError("Analysis cancelled by user")
                for file in files:
                    if file.lower().endswith(self.supported_formats):
                        candidate = os.path.abspath(os.path.join(root, file))
                        real_candidate = os.path.realpath(candidate)
                        try:
                            inside_root = os.path.commonpath(
                                [scan_root, real_candidate]
                            ) == scan_root
                        except ValueError:
                            inside_root = False
                        if not inside_root:
                            logger.warning(
                                "Audio-Symlink ausserhalb des Scanroots uebersprungen: %s",
                                candidate,
                            )
                            continue
                        if len(audio_files) >= hpg_config.SECURITY_MAX_PLAYLIST_SIZE:
                            scan_limit_reached = True
                            break
                        audio_files.append(candidate)
                if scan_limit_reached:
                    break

            if scan_limit_reached:
                self.status_update.emit(
                    f"WARNING: Scan auf {hpg_config.SECURITY_MAX_PLAYLIST_SIZE} Tracks begrenzt."
                )

            total_files = len(audio_files)
            if total_files == 0:
                self.phase_changed.emit(0, "inactive")
                self.status_update.emit(
                    "ERROR: No audio files found in selected folder!"
                )
                logger.error(f"No compatible audio files ({', '.join(self.supported_formats)}) found in selected folder!")
                self.analysis_done.emit([], {})
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
                    self.progress.emit(int(float_percent))
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
                    audio_files,
                    progress_callback=progress_callback,
                    cancel_callback=lambda: self._should_cancel,
                )
            except InterruptedError:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit("Analysis cancelled.")
                self.analysis_done.emit([], {})
                return
            except Exception as e:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit(f"ERROR during analysis: {str(e)}")
                get_error_reporter().log_error(
                    "analysis", str(e), {"folder": self.folder_path}
                )
                self.analysis_done.emit([], {})
                return

            # Ressourcenfilter: defekte Eintraege und Tracks ueber den Limits
            # (Dateigroesse/Dauer) entfernen, Playlist-Groesse deckeln
            pre_count = len(analyzed_tracks)
            analyzed_tracks = apply_resource_limits(analyzed_tracks)
            if len(analyzed_tracks) < pre_count:
                removed = pre_count - len(analyzed_tracks)
                self.status_update.emit(
                    f"WARNING: {removed} Track(s) durch Ressourcenfilter entfernt (defekt oder ueber Limits)."
                )
                logger.warning(f"Ressourcenfilter entfernte {removed} von {pre_count} Tracks.")

            if not analyzed_tracks:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit("ERROR: No tracks were successfully analyzed.")
                self.analysis_done.emit([], {})
                return

            logger.info(f"Feature extraction complete: {len(analyzed_tracks)} tracks successfully analyzed.")
            self._report_rekordbox_coverage(analyzed_tracks)
            self.phase_changed.emit(1, "completed")
            self.status_update.emit(
                f"Audio-Analyse abgeschlossen. Starte KI-Veredelung fuer {len(analyzed_tracks)} Tracks..."
            )
            self.analysis_done.emit(analyzed_tracks, {})

        except InterruptedError:
            self.status_update.emit("Analysis cancelled.")
            self.analysis_done.emit([], {})
        except Exception as e:
            self.status_update.emit(f"FATAL ERROR: {str(e)}")
            self.analysis_done.emit([], {})


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
        self._temp_dir: str | None = None
        self._executor = None  # HPG-004: aktiver ProcessPoolExecutor (fuer Terminate)
        # HPG: schuetzt _executor + _should_cancel gegen TOCTOU-Race zwischen
        # request_cancel() (GUI-Thread) und run() (Worker-Thread).
        self._exec_lock = threading.Lock()
        import uuid
        self._run_id = uuid.uuid4().hex[:8]

    def request_cancel(self):
        """Kooperatives Cancel — setzt Flag und beendet laufende Child-Prozesse."""
        # HPG-004/H1-Fix: Flag setzen UND Executor terminieren unter demselben
        # Lock, den run() beim Setzen von self._executor haelt. Ohne Lock konnte
        # das Cancel genau im Fenster zwischen Executor-Konstruktion und
        # self._executor-Zuweisung verpuffen -> Render lief bis zum 60s-Timeout
        # weiter, App haengte beim Schliessen.
        with self._exec_lock:
            self._should_cancel = True
            self._terminate_executor(self._executor)

    @staticmethod
    def _terminate_executor(executor):
        """Beendet Child-Prozesse eines Executors hart und raeumt ihn ab."""
        if executor is None:
            return
        try:
            for proc in list(getattr(executor, "_processes", {}).values()):
                try:
                    proc.terminate()
                except Exception:
                    pass
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    def get_temp_files(self) -> list[str]:
        return self._temp_files.copy()

    def get_temp_dir(self) -> str | None:
        return self._temp_dir

    def run(self):
        from concurrent.futures import ProcessPoolExecutor
        from concurrent.futures.process import BrokenProcessPool

        try:
            self._temp_dir = tempfile.mkdtemp(prefix=f"hpg_preview_{self._run_id}_")
        except OSError as exc:
            logger.error("Privates Preview-Temp-Verzeichnis konnte nicht angelegt werden: %s", exc)
            if not self._should_cancel:
                for i in range(len(self._transitions)):
                    self.clip_error.emit(i, f"Temp-Verzeichnis nicht verfuegbar: {exc}")
            return

        for i, transition in enumerate(self._transitions):
            if self._should_cancel:
                break
            try:
                # Pro Render-Session ein privates Verzeichnis verwenden; kein
                # vorab angelegter Symlink im globalen Temp kann so ueberschrieben werden.
                out_path = os.path.join(self._temp_dir, f"preview_{i:03d}.wav")
                self._temp_files.append(out_path)

                plan = getattr(transition, "plan", None)
                if plan is not None:
                    spec = TransitionClipSpec.from_plan(
                        plan, transition.from_track, transition.to_track
                    )
                else:
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
                    # Downbeat-Feature 2026-07-17 / AUDIT-FIX D-03 (2026-08-14):
                    # Beat-Alignment ab der kalibrierten Schwelle
                    # DOWNBEAT_RELIABLE_MIN (auch Anker 0.0 ist legitim), die
                    # TAKT-Ebene nur mit Referenz-Beatgrid. Gleiche Logik wie
                    # in TransitionClipSpec.from_plan — Begruendung dort.
                    first_downbeat_a=float(getattr(transition.from_track, "first_downbeat", 0.0) or 0.0),
                    first_downbeat_b=float(getattr(transition.to_track, "first_downbeat", 0.0) or 0.0),
                    downbeat_reliable_a=(
                        getattr(transition.from_track, "downbeat_confidence", 0.0)
                        >= DOWNBEAT_RELIABLE_MIN
                    ),
                    downbeat_reliable_b=(
                        getattr(transition.to_track, "downbeat_confidence", 0.0)
                        >= DOWNBEAT_RELIABLE_MIN
                    ),
                    bar_phase_reliable_a=(
                        getattr(transition.from_track, "downbeat_confidence", 0.0)
                        == REFERENCE_BEATGRID_CONFIDENCE
                    ),
                    bar_phase_reliable_b=(
                        getattr(transition.to_track, "downbeat_confidence", 0.0)
                        == REFERENCE_BEATGRID_CONFIDENCE
                    ),
                    )

                # Sicheres Rendern in einem Subprozess, um C-Level Abstuerze abzufangen.
                # HPG-004: Executor manuell verwalten — bei Timeout/Cancel wird der
                # Child-Prozess terminiert statt beim Context-Exit blockierend zu warten.
                render_success = False
                executor = ProcessPoolExecutor(max_workers=1)
                # H1-Fix: Executor unter Lock veroeffentlichen. Kam das Cancel
                # bereits vor/waehrend der Konstruktion, sieht run() hier das Flag
                # und submittet gar nicht erst — sonst sieht request_cancel() den
                # Executor und terminiert ihn. Kein Race-Fenster mehr.
                with self._exec_lock:
                    if self._should_cancel:
                        self._terminate_executor(executor)
                        break
                    self._executor = executor
                try:
                    future = executor.submit(_render_clip_subprocess_wrapper, (spec, out_path))
                    # Timeout grosszuegig fuer lange Trance/Progressive-Blends (bis 64s Crossfade)
                    future.result(timeout=60.0)
                    render_success = True
                except (BrokenProcessPool, RuntimeError) as pool_err:
                    if self._should_cancel:
                        # Terminate durch request_cancel — kein echter Absturz
                        break
                    logger.error(f"Render-Prozess abgestuerzt bei Clip {i}: {pool_err}")
                    get_error_reporter().log_error(
                        "transition_render_crash", str(pool_err), {"clip": i}
                    )
                    self.clip_error.emit(i, "Format-Absturz (Datei beschaedigt)")
                except TimeoutError:
                    # L7-Fix: kein doppelter _terminate_executor — der finally-Block
                    # unten raeumt den Executor ohnehin ab.
                    logger.error(f"Render-Timeout bei Clip {i}")
                    self.clip_error.emit(i, "Zeitueberschreitung")
                except Exception as render_err:
                    logger.error(f"Fehler bei Transition-Render {i}: {render_err}")
                    get_error_reporter().log_error(
                        "transition_render", str(render_err), {"clip": i}
                    )
                    self.clip_error.emit(i, f"Fehler: {render_err}")
                finally:
                    with self._exec_lock:
                        self._executor = None
                    self._terminate_executor(executor)

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
        if self._temp_dir:
            try:
                os.rmdir(self._temp_dir)
            except OSError:
                pass
            else:
                self._temp_dir = None


# AUDIT-FIX N2 (2026-07-26): Laufende Peak-Worker werden auf Modulebene
# referenziert — bewusst NICHT als Kind des Widgets. Sonst zerstoert der
# Widget-Destruktor (START OVER / Playlist-Reorder entsorgt die Preview-
# Widgets per deleteLater) einen noch laufenden QThread:
# "QThread: Destroyed while thread is still running".
_PEAK_WORKERS: set = set()


def stop_peaks(wait_ms: int = 2000):
    """Stoppt alle laufenden Waveform-Peak-Worker sauber.

    Wird aus MixTipsPanel._cleanup_existing_previews() aufgerufen (deckt
    START OVER, Reorder und MainWindow.closeEvent ab). Worker, die nicht
    rechtzeitig enden, bleiben referenziert — ein laufender QThread darf
    nie per GC/deleteLater zerstoert werden.
    """
    for worker in list(_PEAK_WORKERS):
        try:
            worker.requestInterruption()
        except RuntimeError:
            # C++-Objekt bereits durch deleteLater() zerstoert
            _PEAK_WORKERS.discard(worker)
    for worker in list(_PEAK_WORKERS):
        try:
            if worker.wait(wait_ms):
                _PEAK_WORKERS.discard(worker)
        except RuntimeError:
            _PEAK_WORKERS.discard(worker)


class _PeakWorker(QThread):
    """Dekodiert eine Preview-WAV und berechnet die Peak-Huellkurve.

    AUDIT-FIX T2 (2026-07-26): laeuft im Thread, weil das Einlesen der
    Preview-WAV (bis ~124 s, ~22 MB) den GUI-Thread sichtbar blockierte.
    Die Klasse liegt auf Modulebene wie alle anderen Worker der App —
    frueher wurde sie in WaveformWidget.load() definiert und damit bei
    JEDEM Aufruf als neues Klassenobjekt (eigenes pyqtSignal, eigenes
    QMetaObject) erzeugt.
    """

    done = pyqtSignal(object, float)  # (peaks|None, total_sec)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            # AUDIT-FIX N2: kooperativ abbrechbar — stop_peaks() bzw.
            # ein neuer load() setzt requestInterruption().
            if self.isInterruptionRequested():
                return
            import soundfile as sf
            import numpy as np
            data, sr = sf.read(self._path, dtype="float32", always_2d=True)
            # Nach dem (nicht unterbrechbaren) Dekodieren erneut pruefen
            if self.isInterruptionRequested():
                return
            mono = data.mean(axis=1)
            total = len(mono) / sr if sr else 0.0
            n_bars = 700
            chunk = max(1, len(mono) // n_bars)
            peaks = [float(np.abs(mono[i:i + chunk]).max())
                     for i in range(0, len(mono), chunk)]
            peak_max = max(peaks) if peaks else 1.0
            norm = [p / peak_max for p in peaks] if peak_max > 0 else peaks
            if self.isInterruptionRequested():
                return
            self.done.emit(norm, total)
        except Exception as exc:
            # AUDIT-FIX F9: nicht mehr stumm schlucken
            logging.getLogger(__name__).warning(
                "Waveform-Peaks konnten nicht geladen werden: %s", exc
            )
            if not self.isInterruptionRequested():
                self.done.emit(None, 0.0)


class WaveformWidget(QWidget):
    """Zeichnet den gerenderten Transition-Clip als Wellenform.

    Deck-Element des Ink-Navy-Gold-Designs: die Crossfade-Region ist gold
    hervorgehoben, ein Playhead folgt der Wiedergabe. So sieht der DJ, WO
    gemischt wird.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks = None       # Liste 0..1
        self._pos = 0.0          # Playhead 0..1
        self._cf_start = None    # Crossfade-Start 0..1
        self._cf_end = None
        # AUDIT-FIX N3: Generation-Counter — nur das Ergebnis der jeweils
        # letzten load()-Anfrage wird uebernommen (stale Worker ignoriert).
        self._peak_generation = 0
        # Text solange keine Peaks vorliegen (Ladehinweis oder Fehlermeldung)
        self._placeholder = "Wellenform wird geladen …"
        self.setMinimumHeight(58)

    def set_placeholder(self, text: str):
        """Text setzen, der statt der Wellenform gezeigt wird (z. B. Fehler)."""
        self._peaks = None
        self._cf_start = self._cf_end = None
        self._placeholder = text
        self.update()

    def load(self, wav_path: str, crossfade_sec: float, preroll_sec: float = 30.0):
        """Laedt Clip, berechnet Peak-Huellkurve + Crossfade-Bereich.

        AUDIT-FIX T2 (2026-07-26): Das Einlesen der Preview-WAV (bis ~124 s,
        ~22 MB) lief im GUI-Thread und blockierte die UI bei jedem Preview
        sichtbar. Jetzt laeuft das Dekodieren + die Peak-Berechnung in einem
        kurzen QThread; das Widget zeigt solange "Wellenform wird geladen …".
        """
        self._peaks = None
        self._cf_start = self._cf_end = None
        self._placeholder = "Wellenform wird geladen …"
        self.update()

        # AUDIT-FIX N1 (2026-07-26): Alten Worker nur noch unterbrechen —
        # KEIN isRunning()-Guard mehr. Der lief auf einer per deleteLater()
        # bereits zerstoerten C++-Instanz und crashte beim zweiten load()
        # mit RuntimeError. Stale-Ergebnisse blockt jetzt der
        # Generation-Counter (N3), nicht der isRunning-Check.
        self._peak_generation += 1
        generation = self._peak_generation
        old = getattr(self, "_peak_worker", None)
        if old is not None:
            try:
                old.requestInterruption()
            except RuntimeError:
                pass  # C++-Objekt bereits durch deleteLater() zerstoert
            self._peak_worker = None

        def _apply(peaks, total, _cf=crossfade_sec, _pre=preroll_sec,
                   _gen=generation):
            # AUDIT-FIX N3: nur Ergebnisse der aktuellen Generation
            # uebernehmen — ein alter Worker darf frisch berechnete
            # Peaks nicht mehr ueberschreiben.
            if _gen != self._peak_generation:
                return
            try:
                self._peaks = peaks
                if peaks and total > 0:
                    self._cf_start = min(1.0, _pre / total)
                    self._cf_end = min(1.0, (_pre + _cf) / total)
                self.update()
            except RuntimeError:
                pass  # Widget wurde inzwischen von Qt zerstoert

        # AUDIT-FIX N2: Worker OHNE Widget-Parent erzeugen und auf
        # Modulebene referenzieren — sonst zerstoert der Widget-Destruktor
        # (START OVER / Reorder) einen laufenden QThread.
        worker = _PeakWorker(wav_path)
        self._peak_worker = worker
        _PEAK_WORKERS.add(worker)
        worker.done.connect(_apply)
        worker.finished.connect(lambda w=worker: _PEAK_WORKERS.discard(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def set_position(self, pos_ms: int, dur_ms: int):
        self._pos = (pos_ms / dur_ms) if dur_ms else 0.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(COLORS["bg_input"]))
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawRect(0, 0, w - 1, h - 1)
        if not self._peaks:
            p.setPen(QColor(COLORS["text_dim"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       self._placeholder)
            p.end()
            return
        mid = h / 2.0
        # Crossfade-Region hinterlegen
        if self._cf_start is not None:
            x0 = self._cf_start * w
            x1 = self._cf_end * w
            cf = QColor(COLORS["accent_primary"])
            cf.setAlpha(28)
            p.fillRect(QRectF(x0, 0, x1 - x0, h), cf)
        n = len(self._peaks)
        steel = QColor(COLORS["accent_secondary"])
        gold = QColor(COLORS["accent_primary"])
        for i, v in enumerate(self._peaks):
            x = i / n * w
            bh = v * (h - 8)
            frac = i / n
            in_cf = (self._cf_start is not None
                     and self._cf_start <= frac <= self._cf_end)
            p.setPen(QPen(gold if in_cf else steel, 1))
            p.drawLine(QPointF(x, mid - bh / 2), QPointF(x, mid + bh / 2))
        # Playhead
        px = self._pos * w
        p.setPen(QPen(QColor(COLORS["text_bright"]), 1.5))
        p.drawLine(QPointF(px, 0), QPointF(px, h))
        p.end()


class TransitionPreviewWidget(QWidget):
    """
    Player-Widget fuer einen einzelnen Transitions-Preview-Clip.
    Zeigt: Play/Stop-Button, Fortschritts-Slider, Zeitanzeige,
    Wellenform mit Crossfade-Region sowie genaue Mix-Punkte.
    Ist deaktiviert bis set_wav_path() aufgerufen wird.
    """

    def __init__(self, index: int, transition, parent=None):
        super().__init__(parent)
        self._index = index
        self._tr = transition
        self._wav_path: str | None = None
        self._error_msg: str | None = None
        # M5-Fix: mit Qt-Parent erzeugen, damit Player/Output an der Widget-
        # Hierarchie haengen und bei deleteLater() mitzerstoert werden (sonst
        # haelt das offene Datei-Handle laenger als das Widget -> Windows-Lock).
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.85)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Titel-Label
        self._base_title = f"▶ Hör-Vorschau Übergang {self._index + 1}"
        self._title_label = QLabel(self._base_title)
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
        
        # Ink-Navy-Gold: A = Stahlblau, MIX = Gold, B = gedaempftes Gruen
        seg_style = (
            "QLabel {{ background-color: {bg}; color: {fg}; font-size: 10px; "
            "font-weight: bold; border: 1px solid {bd}; border-radius: 3px; "
            "padding: 4px 6px; }}"
        )
        self.lbl_a = QLabel(f"A: {from_name}\n(Out: {mix_out:.1f}s)")
        self.lbl_a.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_a.setStyleSheet(seg_style.format(
            bg=COLORS["accent_secondary_bg"], fg=COLORS["accent_secondary"],
            bd=COLORS["accent_secondary"]))
        self.lbl_a.setToolTip(f"Track A: {from_track.fileName}\nSpielt von 0s bis 30s in dieser Vorschau.\nÜbergang startet bei Sekunde {mix_out:.1f} des Original-Tracks A.")

        self.lbl_mix = QLabel(f"⇄ MIX ({crossfade:.1f}s)\n{t_label}")
        self.lbl_mix.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_mix.setStyleSheet(seg_style.format(
            bg=COLORS["accent_primary_bg"], fg=COLORS["accent_primary"],
            bd=COLORS["accent_primary"]))
        self.lbl_mix.setToolTip(f"Mischbereich (Crossfade) für {crossfade:.1f} Sekunden.\nSpielt von 30.0s bis {30.0+crossfade:.1f}s in dieser Vorschau.")

        self.lbl_b = QLabel(f"B: {to_name}\n(In: {mix_in:.1f}s)")
        self.lbl_b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_b.setStyleSheet(seg_style.format(
            bg="#12233a", fg=COLORS["accent_success"], bd=COLORS["accent_success"]))
        self.lbl_b.setToolTip(f"Track B: {to_track.fileName}\nSpielt ab Sekunde {30.0+crossfade:.1f} der Vorschau bis zum Ende.\nÜbergang startet bei Sekunde {mix_in:.1f} des Original-Tracks B.")

        # Proportionale Weiten: 30s vor dem Mix, crossfade Sekunden mixen, 30s nach dem Mix
        self.segments_layout.addWidget(self.lbl_a, 300)
        self.segments_layout.addWidget(self.lbl_mix, int(crossfade * 10))
        self.segments_layout.addWidget(self.lbl_b, 300)

        layout.addLayout(self.segments_layout)

        # Deck-Wellenform des gerenderten Clips (Crossfade gold hervorgehoben)
        self._crossfade_sec = crossfade
        self._waveform = WaveformWidget()
        layout.addWidget(self._waveform)

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
        self.clear_error()
        self._wav_path = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._play_btn.setEnabled(True)
        self._slider.setEnabled(True)
        self._time_label.setText("0:00 / –:––")
        # Deck-Wellenform aus dem gerenderten Clip laden
        self._waveform.load(path, getattr(self, "_crossfade_sec", 0.0))

    def set_error(self, msg: str):
        """Fehlermeldung anzeigen, Play-Button bleibt deaktiviert.

        Wird von MixTipsPanel._on_clip_error() aufgerufen. Das Widget bleibt
        stehen, damit der Nutzer sieht, WELCHER Uebergang fehlgeschlagen ist;
        ein Retry ueber den Karten-Button setzt es per clear_error() zurueck.
        """
        self._error_msg = msg
        self._wav_path = None
        self._play_btn.setEnabled(False)
        self._slider.setEnabled(False)
        self._slider.setValue(0)
        self._time_label.setText("Fehler")
        # Basistitel verwenden — sonst haengt jeder Fehlversuch ein ⚠ mehr an.
        self._title_label.setText(f"{self._base_title} ⚠ Render fehlgeschlagen")
        self._title_label.setToolTip(msg)
        self._waveform.set_placeholder(f"Render fehlgeschlagen: {msg}")

    def clear_error(self):
        """Fehleranzeige zuruecknehmen (neuer Render-Versuch laeuft)."""
        if getattr(self, "_error_msg", None) is None:
            return
        self._error_msg = None
        self._title_label.setText(self._base_title)
        self._title_label.setToolTip("")
        self._time_label.setText("—")
        self._waveform.set_placeholder("Wellenform wird geladen …")

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
        self._waveform.set_position(pos_ms, dur_ms)
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
        """Playback stoppen, Datei-Handle freigeben und Slider zuruecksetzen."""
        self._player.stop()
        # H2-Fix: Source loesen, damit das offene WAV-Handle freigegeben wird —
        # sonst schlaegt os.remove() unter Windows mit PermissionError fehl und
        # die Temp-Datei bleibt liegen (der Aufrufer loescht direkt danach).
        self._player.setSource(QUrl())
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
        self.energy_group = energy_group
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

        self.energy_strategy_hint = QLabel()
        self.energy_strategy_hint.setWordWrap(True)
        energy_layout.addWidget(self.energy_strategy_hint)

        layout.addWidget(energy_group)

        # AI Provider Selection — Auto-Detect & Auto-Start (Ollama / LM Studio)
        # Vom ai_launcher erkannte Werte; vom Detect-Worker befuellt.
        self.detected_base_url = None
        self.detected_provider = None
        self.detected_active_model = None
        self._ai_detect_worker = None
        self._test_worker = None
        self._pull_worker = None

        self.provider_group = QGroupBox("AI Intelligence Provider")
        provider_outer = QVBoxLayout(self.provider_group)
        provider_outer.setSpacing(8)

        self.ai_enabled_checkbox = QCheckBox("Optionale KI-Metadaten aktivieren")
        self.ai_enabled_checkbox.setChecked(False)
        self.ai_enabled_checkbox.setToolTip(
            "Optionales lokales LLM fuer Mood/Subgenre. Die Audioanalyse und "
            "Playlist-Erzeugung funktionieren vollstaendig ohne KI."
        )
        provider_outer.addWidget(self.ai_enabled_checkbox)

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
        model_label = QLabel("Lokales KI-Textmodell:")
        self.model_combo = QComboBox()
        self.model_combo.setPlaceholderText("KI erkennen, um Modelle zu laden")
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

        # Tooltips fuer AI Provider Widget
        self.provider_group.setToolTip("Konfiguriere deinen lokalen KI-Provider (Ollama oder LM Studio) fuer Mood- und Subgenre-Tags aus vorhandenen Track-Metadaten.")
        self.ollama_radio.setToolTip("Nutze Ollama als lokalen KI-Dienst. Läuft sehr stabil auf AMD-Grafikkarten unter Windows.")
        self.lmstudio_radio.setToolTip("Nutze LM Studio als lokalen KI-Dienst. Perfekt fuer detaillierte Modellkonfigurationen.")
        self.model_combo.setToolTip("Zeigt lokal verfuegbare Textmodelle. HPG sendet Metadaten, keine Audiodateien.")
        self.ai_refresh_btn.setToolTip("Sucht lokale KI-Instanzen und deren verfuegbare Textmodelle.")
        self.test_ai_btn.setToolTip("Fuehrt einen Test-Prompt aus, um die Antwortgeschwindigkeit und Richtigkeit des Modells zu pruefen.")

        self._ai_controls = [
            self.ollama_radio,
            self.lmstudio_radio,
            self.model_combo,
            self.ai_refresh_btn,
            self.test_ai_btn,
        ]
        self.ai_enabled_checkbox.toggled.connect(self._set_ai_enabled)
        self.ai_strategy_hint = QLabel()
        self.ai_strategy_hint.setWordWrap(True)
        provider_outer.insertWidget(1, self.ai_strategy_hint)
        self._set_ai_enabled(False)

        layout.addWidget(self.provider_group)

        # Harmonic Strictness
        harmony_group = QGroupBox("Harmonic Mixing")
        self.harmony_group = harmony_group
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

        self.harmony_strategy_hint = QLabel()
        self.harmony_strategy_hint.setWordWrap(True)
        harmony_layout.addWidget(self.harmony_strategy_hint)

        layout.addWidget(harmony_group)

        # Genre Mixing
        genre_group = QGroupBox("Genre Flow")
        self.genre_group = genre_group
        genre_group.setToolTip(
            "Steuert, wie Genres in der Playlist gemischt werden.\n"
            "Die App erkennt automatisch das Genre jedes Tracks\n"
            "und kann aehnliche Genres bevorzugt zusammen sortieren."
        )
        genre_layout = QVBoxLayout(genre_group)

        self.genre_mixing = QCheckBox("Enable Genre Transitions")
        self.genre_mixing.setChecked(True)
        self.genre_mixing.setToolTip(
            "Aktiviert: die Strategie Genre Flow sortiert nach Genre-Naehe\n"
            "Deaktiviert: Genre Flow faellt auf Harmonic Flow zurueck.\n"
            "Die Genre-Aehnlichkeit geht in beiden Faellen in den\n"
            "Uebergangs-Score ein — dieser Schalter aendert nur die Sortierung."
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

        self.genre_strategy_hint = QLabel()
        self.genre_strategy_hint.setWordWrap(True)
        genre_layout.addWidget(self.genre_strategy_hint)

        layout.addWidget(genre_group)

        # Uebergangs-Gewichte (Spec 2026-08-19). Gelten fuer alle Strategien,
        # die die erweiterte Zielfunktion nutzen — deshalb bewusst NICHT in
        # apply_strategy_support eingetragen und nie ausgegraut.
        weight_group = QGroupBox("Uebergangs-Gewichte")
        self.transition_weight_group = weight_group
        weight_group.setToolTip(
            "Wie stark Groove, Bassdruck, Klangfarbe und Stimmung\n"
            "die Reihenfolge beeinflussen. Aenderungen wirken ab der\n"
            "naechsten Generierung und erfordern KEINE Neuanalyse."
        )
        weight_layout = QVBoxLayout(weight_group)

        self.transition_weight_sliders = {}
        for schluessel, label, start in (
            ("groove_weight", "Groove", 30),
            ("bass_weight", "Bassdruck", 8),
            ("timbre_weight", "Klangfarbe", 5),
            ("mood_weight", "Stimmung", 5),
            # Kandidaten-Gewicht (Spec 2026-08-21 Abschnitt 4: "Faktoren-Regler um
            # Lautheit erweitern"); eigener Schluesselkreis kandidaten_*_weight.
            ("kandidaten_loudness_weight", "Lautheit (Kandidaten)", 6),
        ):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(start)  # Startgewicht * 100 aus Spec 7.2
            # Waehrend des Ziehens NICHT schreiben: valueChanged feuert bei
            # jeder Mausbewegung und wuerde die Override-Datei dutzendfach
            # neu schreiben. sliderReleased deckt die Maus ab, valueChanged
            # mit isSliderDown()-Guard die Tastatur und setValue().
            slider.sliderReleased.connect(self._on_transition_weight_changed)
            slider.valueChanged.connect(self._on_transition_weight_value_changed)
            self.transition_weight_sliders[schluessel] = slider
            weight_layout.addWidget(QLabel(f"{label}:"))
            weight_layout.addWidget(slider)

        # Eigenes Label: main.py hat KEINE QMainWindow-Statusleiste.
        self.transition_weight_status = QLabel("")
        self.transition_weight_status.setWordWrap(True)
        self.transition_weight_status.setStyleSheet("font-size: 11px;")
        weight_layout.addWidget(self.transition_weight_status)

        reset_button = QPushButton("Eigene Werte verwerfen")
        reset_button.clicked.connect(self._on_transition_weights_reset)
        weight_layout.addWidget(reset_button)

        # Regler aus dem wirksamen Stand befuellen — sonst zeigen sie die
        # hartkodierten Startwerte, waehrend real andere Gewichte gelten, und
        # der erste Klick schreibt einen ganz anderen Zustand (siehe
        # _lade_transition_regler). Bis 2026-08-21 wurde das nur im
        # Reset-Handler gerufen, nie beim Aufbau.
        self._lade_transition_regler()

        layout.addWidget(weight_group)

    def _on_transition_weight_value_changed(self) -> None:
        """Schreibt nur, wenn der Wert nicht gerade gezogen wird.

        Deckt Tastatureingabe und setValue() ab; beim Ziehen mit der Maus
        uebernimmt sliderReleased, damit nicht jede Zwischenposition auf die
        Platte geht.
        """
        if any(s.isSliderDown() for s in self.transition_weight_sliders.values()):
            return
        self._on_transition_weight_changed()

    def _on_transition_weight_changed(self) -> None:
        """Schreibt die Regler in die Override-Datei und verwirft den Cache.

        Gewichte liegen ausserhalb des Analyse-Caches — eine Aenderung kostet
        deshalb nur ein Neuberechnen der Scores, keine Neuanalyse. Die
        Kompatibilitaets-Caches in playlist.py sind ausserhalb von
        generate_playlist None und brauchen kein Zutun.
        """
        from hpg_core.tolerances import reset_cache, write_override, write_override_kandidaten

        gewichte = {
            schluessel: slider.value() / 100.0
            for schluessel, slider in self.transition_weight_sliders.items()
        }
        # Zwei Schluesselkreise in einer Datei: Track-Gewichte (*_weight) und
        # Kandidaten-Gewichte (kandidaten_*_weight) — getrennt normiert.
        track_gewichte = {k: v for k, v in gewichte.items() if not k.startswith("kandidaten_")}
        kandidaten_gewichte = {k: v for k, v in gewichte.items() if k.startswith("kandidaten_")}
        try:
            write_override(track_gewichte)
            if kandidaten_gewichte:
                write_override_kandidaten(kandidaten_gewichte)
        except ValueError as exc:
            self.transition_weight_status.setText(f"Gewichte ungueltig: {exc}")
            return
        reset_cache()
        self.transition_weight_status.setText(
            "Gespeichert — wirkt ab der naechsten Generierung." + self._praeferenz_hinweis()
        )

    @staticmethod
    def _praeferenz_hinweis() -> str:
        """Hoertest-Praeferenzen (candidate_preferences.json) schlagen den
        Kandidaten-Regler je Genre — das soll der Nutzer sehen."""
        try:
            from hpg_core.candidate_preferences import load_candidate_preferences
            genres = sorted(g for g, e in load_candidate_preferences().items() if e.get("gewichte"))
        except Exception:  # noqa: BLE001 - Hinweis ist Beiwerk
            return ""
        if not genres:
            return ""
        return (" Hoertest-Praeferenz aktiv fuer: " + ", ".join(genres)
                + " — der Lautheit-Regler wirkt dort nicht.")

    def _on_transition_weights_reset(self) -> None:
        """Verwirft die eigenen Regler-Werte; danach gilt wieder der Stand
        aus Code und mitgelieferter Datei.

        WICHTIG: hier darf NICHT geschrieben werden. Die Override-Datei
        liegt in der Ladekette UEBER den mitgelieferten Werten. Wer beim
        Zuruecksetzen schreibt, verdeckt die darunterliegende Stufe
        dauerhaft. Richtig ist: Override loeschen, Cache verwerfen, Regler aus
        dem dann wirksamen Stand neu befuellen.

        Stand 2026-08-21: die mitgelieferte Datei
        hpg_core/data/transition_tolerances.json ist leer ({}), gelernte
        Werte gibt es noch nicht — wirksam sind die Defaults aus genres.py.
        Der Knopf hiess bis dahin "Auf gelernte Werte zuruecksetzen" und
        versprach damit etwas, das es nicht gab.
        """
        from hpg_core.tolerances import entferne_override, get_tolerances, reset_cache

        entferne_override()
        reset_cache()
        self._lade_transition_regler()
        self.transition_weight_status.setText(
            "Eigene Werte verworfen — die Standard-Gewichte sind wieder aktiv."
        )

    def _lade_transition_regler(self) -> None:
        """Befuellt die Regler aus dem tatsaechlich wirksamen Stand.

        Ohne das zeigen die Regler ihre hartkodierten Startwerte, waehrend
        real die gelernten oder zuvor gespeicherten Gewichte gelten — der
        erste Klick wuerde dann ungewollt einen ganz anderen Zustand
        schreiben.
        """
        from hpg_core.genres import CANONICAL_GENRES
        from hpg_core.tolerances import get_tolerances

        wirksam = get_tolerances(CANONICAL_GENRES[0])
        for schluessel, slider in self.transition_weight_sliders.items():
            slider.blockSignals(True)
            slider.setValue(int(round(float(wirksam.get(schluessel, 0.0)) * 100)))
            slider.blockSignals(False)

    # ----- AI Provider Auto-Detect / Auto-Start -----

    def _set_ai_enabled(self, enabled):
        for control in self._ai_controls:
            control.setEnabled(enabled)
        if not enabled:
            self._set_ai_hint(False)
            self.test_ai_btn.setEnabled(False)
            self.ai_status_label.setText("KI deaktiviert (deterministischer Kernlauf)")
            return
        self._set_ai_hint(True)
        self.refresh_ai_providers()

    def _set_ai_hint(self, enabled):
        """Kennzeichnet den optionalen KI-Bereich eindeutig als aktiv oder gesperrt."""
        if enabled:
            self.ai_strategy_hint.setText(
                "<span style='color: #00E676;'>● AKTIV</span> "
                "Lokale KI kann konfiguriert werden."
            )
            self.provider_group.setStyleSheet(
                "QGroupBox { border: 1px solid #00E676; background: #0a2e1a; }"
                "QGroupBox::title { color: #00E676; }"
            )
        else:
            self.ai_strategy_hint.setText(
                "<span style='color: #FFD740;'>● OPTIONAL / GESPERRT</span> "
                "Aktiviere oben die KI-Metadaten, um Provider und Modell zu wählen."
            )
            self.provider_group.setStyleSheet(
                "QGroupBox { border: 1px solid #FFD740; background: #2a1a0a; }"
                "QGroupBox::title { color: #FFD740; }"
            )

    @staticmethod
    def _strategies_for_parameter(parameter):
        """Liefert die Strategien, welche einen Parameter tatsaechlich auswerten."""
        return [
            name for name, supported in SUPPORTED_STRATEGY_PARAMETERS.items()
            if parameter in supported
        ]

    def _cleanup_ai_worker(self, attr_name, worker):
        """Gibt eine beendete AI-Hilfsinstanz frei, wenn sie noch aktuell ist."""
        if getattr(self, attr_name, None) is not worker:
            return
        setattr(self, attr_name, None)
        try:
            worker.deleteLater()
        except RuntimeError:
            pass

    def _set_strategy_control_state(self, group, hint, controls, parameter, strategy):
        """Setzt Bedienbarkeit, Farbe und begruendenden Hinweis eines Bereichs."""
        enabled = parameter in SUPPORTED_STRATEGY_PARAMETERS.get(strategy, set())
        for control in controls:
            control.setEnabled(enabled)

        compatible = ", ".join(self._strategies_for_parameter(parameter))
        if enabled:
            hint.setText(
                "<span style='color: #00E676;'>● AKTIV</span> "
                f"Wird von <b>{strategy}</b> verwendet."
            )
            group.setStyleSheet(
                "QGroupBox { border: 1px solid #00E676; background: #0a2e1a; }"
                "QGroupBox::title { color: #00E676; }"
            )
        else:
            reason = (
                f"<span style='color: #FFD740;'>● IN DIESER STRATEGIE GESPERRT</span> "
                f"<b>{strategy}</b> wertet diese Einstellung nicht aus. "
                f"Verfügbar mit: {compatible}."
            )
            hint.setText(reason)
            group.setStyleSheet(
                "QGroupBox { border: 1px solid #FFD740; background: #2a1a0a; }"
                "QGroupBox::title { color: #FFD740; }"
            )

    def refresh_ai_providers(self):
        """Startet den Hintergrund-Detect-Worker (kein UI-Block)."""
        if not self.ai_enabled_checkbox.isChecked():
            return
        if self._ai_detect_worker and self._ai_detect_worker.isRunning():
            return
        preferred = "LM Studio" if self.lmstudio_radio.isChecked() else "Ollama"
        preferred_model = self.model_combo.currentText().strip() or hpg_config.AI_MODEL

        self.ai_status_label.setText("AI: suche & starte Provider ...")
        self.ai_refresh_btn.setEnabled(False)

        worker = AIDetectWorker(
            preferred=preferred, preferred_model=preferred_model, parent=self
        )
        self._ai_detect_worker = worker
        worker.detected.connect(
            lambda status, source=worker: self._on_ai_detected(status, source)
        )
        worker.finished.connect(
            lambda source=worker: self._cleanup_ai_worker(
                "_ai_detect_worker", source
            )
        )
        worker.start()

    def _on_ai_detected(self, status, source_worker=None):
        """Befuellt UI mit erkanntem Provider + real installierten Modellen."""
        if (
            source_worker is not None
            and source_worker is not self._ai_detect_worker
        ):
            return
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

        if not status.models:
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.setPlaceholderText("Keine verfuegbaren Modelle")
            self.model_combo.blockSignals(False)
            self.detected_base_url = status.base_url
            self.detected_provider = status.name
            self.detected_active_model = None
            self.test_ai_btn.setEnabled(False)
            self.ai_status_label.setText(
                f"AI bereit — {status.name}: keine verfuegbaren Modelle."
            )
            return

        # Combo mit den vom lokalen Provider gemeldeten Modellen fuellen
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
        if not self.ai_enabled_checkbox.isChecked():
            return
        if self._test_worker and self._test_worker.isRunning():
            return
        provider = "LM Studio" if self.lmstudio_radio.isChecked() else "Ollama"
        model = self.model_combo.currentText().strip()
        if not model:
            QMessageBox.warning(self, "Modell testen", "Bitte waehle zuerst ein Modell aus.")
            return

        self.test_ai_btn.setEnabled(False)
        self.ai_refresh_btn.setEnabled(False)
        self.ai_status_label.setText("AI: Testanfrage laeuft...")

        base_url = self.detected_base_url
        worker = AITestWorker(provider, model, base_url, parent=self)
        self._test_worker = worker
        worker.test_finished.connect(
            lambda success, response_text, responded_model, latency, source=worker:
            self._on_test_finished(
                success, response_text, responded_model, latency, source
            )
        )
        worker.finished.connect(
            lambda source=worker: self._cleanup_ai_worker("_test_worker", source)
        )
        worker.start()

    def _on_test_finished(
        self, success, response_text, responded_model, latency, source_worker=None
    ):
        """Verarbeitet das Ergebnis des AI-Verbindungstests."""
        if (
            source_worker is not None
            and source_worker is not self._test_worker
        ):
            return
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
        """Startet den Download des Modells ueber Ollama im Hintergrund."""
        if self._pull_worker and self._pull_worker.isRunning():
            return
        self.test_ai_btn.setEnabled(False)
        self.ai_refresh_btn.setEnabled(False)
        self.ai_status_label.setText(f"AI: Lade '{model}' herunter (bitte warten)...")

        worker = AIPullWorker(model, parent=self)
        self._pull_worker = worker
        worker.pull_finished.connect(
            lambda success, error_msg, source=worker: self._on_pull_finished(
                success, error_msg, source
            )
        )
        worker.finished.connect(
            lambda source=worker: self._cleanup_ai_worker("_pull_worker", source)
        )
        worker.start()

    def _on_pull_finished(self, success, error_msg, source_worker=None):
        """Verarbeitet das Ende des Model-Downloads."""
        if (
            source_worker is not None
            and source_worker is not self._pull_worker
        ):
            return
        self.test_ai_btn.setEnabled(True)
        self.ai_refresh_btn.setEnabled(True)
        model_name = getattr(
            source_worker or self._pull_worker, "model", "unbekannt"
        )

        if success:
            self.ai_status_label.setText("AI: Download abgeschlossen. Teste Verbindung...")
            # Nach erfolgreichem Pull automatisch erneut testen
            self.test_ai_connection()
            # Nach erfolgreichem Pull die Modellliste aktualisieren
            self.refresh_ai_providers()
            QMessageBox.information(
                self,
                "Download erfolgreich",
                f"Das Modell '{model_name}' wurde erfolgreich heruntergeladen und installiert!\n\n"
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
            "ai_enabled": self.ai_enabled_checkbox.isChecked(),
            "energy_direction": self.energy_direction.currentText(),
            "peak_position": self.peak_position_slider.value(),
            "harmonic_strictness": self.harmonic_strictness.value(),
            "allow_experimental": self.allow_experimental.isChecked(),
            "genre_mixing": self.genre_mixing.isChecked(),
            "genre_weight": self.genre_weight.value() / 100.0,
        }

    def apply_strategy_support(self, strategy):
        """Zeigt eindeutig, welche Einstellungen die Strategie auswertet."""
        self._set_strategy_control_state(
            self.energy_group,
            self.energy_strategy_hint,
            [self.energy_direction],
            "energy_direction",
            strategy,
        )
        peak_enabled = "peak_position" in SUPPORTED_STRATEGY_PARAMETERS.get(strategy, set())
        self.peak_position_slider.setEnabled(peak_enabled)
        self.peak_position_label.setEnabled(peak_enabled)
        self._set_strategy_control_state(
            self.harmony_group,
            self.harmony_strategy_hint,
            [self.harmonic_strictness, self.allow_experimental],
            "harmonic_strictness",
            strategy,
        )
        self._set_strategy_control_state(
            self.genre_group,
            self.genre_strategy_hint,
            [self.genre_mixing, self.genre_weight],
            "genre_mixing",
            strategy,
        )


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

        sidebar_tips = {
            "LIBRARY": "Bibliothek / Import:\nOrdner einlesen, Parameter einstellen, Audio-Features & KI-Analyse starten.",
            "PLAYLIST": "Generierte Playlist:\nTabelle mit Tonarten (Camelot), Tempo (BPM), Uebergangstypen und KI-Stimmungen.",
            "MIX TIPS": "Misch-Empfehlungen & Vorschau:\nDetaillierte Uebergangs-Tipps (EQ, Filter) und 70s-Audio-Previews abspielen.",
            "TIMELINE": "Visuelle Playlist-Zeitleiste:\nVerlauf von Energie, BPM und Tonartkompatibilitaet ueber die gesamte Playlist.",
            "QUALITY": "Playlist-Qualitaetsanalyse:\nMetriken fuer harmonischen Fluss, Tempo-Stetigkeit, Energie-Verlauf und Genre-Mix."
        }

        for i, (icon, label) in enumerate(self.NAV_ITEMS):
            btn = QPushButton()
            btn.setFixedSize(72, 56)
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

        # Hinweis-Label: bleibt stehen, auch wenn set_status() den Statustext
        # ueberschreibt. Fuer Befunde, die den Lauf nicht abbrechen, aber das
        # Ergebnis erklaeren (z. B. unanalysierte Rekordbox-Tracks).
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet(f"""
            QLabel {{
                color: #ffaa00;
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


class QtLogSignalEmitter(QObject):
    log_written = pyqtSignal(str, str)

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
            ("Ctrl+1 - Ctrl+5", "Switch Navigation Panels"),
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
        self.progress_bar.setRange(0, 100)
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
            return "QFrame { background-color: #D4AF37; border: 1px solid #FFD700; border-radius: 2px; }"
        elif state == "completed":
            return "QFrame { background-color: #00FF66; border: 1px solid #33FF33; border-radius: 2px; }"
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
        bounded = max(0, min(100, int(value)))
        self.progress_bar.setValue(bounded)
        self.progress_bar.setFormat(f"{bounded}%")
                
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
        # Spec 2026-08-21 Abschnitt 4: App-Default 2.0 (Gate des Hoertests und
        # der Paar-Kandidaten, PAAR_BPM_MAX); der Slider bleibt einstellbar.
        self.bpm_tolerance_slider.setValue(2)
        self.bpm_tolerance_slider.setToolTip(
            "Maximale BPM-Differenz zwischen aufeinanderfolgenden Tracks.\n"
            "±2 BPM (Gate des Hoertests und der Mix-Kandidaten). "
            "Half/Double-Time wird automatisch erkannt."
        )
        self.bpm_value_label = QLabel("±2")
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
            f"Multi-Core-Verarbeitung: nutzt bis zu "
            f"{hpg_config.PARALLEL_AUTO_MAX_WORKERS} parallele Analyseprozesse."
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
        self.advanced_params.apply_strategy_support(
            self.strategy_combo.currentText()
        )
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
        if hasattr(self, "advanced_params"):
            self.advanced_params.apply_strategy_support(strategy)

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


class TransitionScoreDelegate(QStyledItemDelegate):
    """Rendert die Uebergangs-Passung als deutliches, farbiges Badge."""

    def paint(self, painter, option, index):
        score = index.data(Qt.ItemDataRole.UserRole)
        if score is None:
            super().paint(painter, option, index)
            return

        try:
            score = float(score)
        except (TypeError, ValueError):
            super().paint(painter, option, index)
            return

        accent_color, _, _ = transition_score_style(score / 100.0)
        painter.save()

        cell_background = (
            COLORS["bg_selected"]
            if option.state & QStyle.StateFlag.State_Selected
            else COLORS["bg_input"]
        )
        painter.fillRect(option.rect, QColor(cell_background))
        painter.fillRect(option.rect.adjusted(3, 3, -3, -3), QColor(accent_color))

        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(TRANSITION_SCORE_TEXT))
        painter.drawText(
            option.rect,
            Qt.AlignmentFlag.AlignCenter,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(130, 24)


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
        self.bpm_tolerance = 2.0
        self.scoring_context = {}  # HPG-001: aktiver Scoring-Vertrag
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
                "Passung",
                "AI Insights",
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
            "Passung zum vorherigen Track: Farbe, Bewertung und Score (0-100%).",
            "Optionale KI-Beschreibung zu Stimmung und Charakter.",
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
        self.table.setColumnWidth(12, 65)
        self.table.setColumnWidth(13, 115)
        self.table.setColumnWidth(14, 130)

        # rowsMoved Signal
        self.table.model().rowsMoved.connect(self._on_rows_moved)

        # EnergyBarDelegate fuer visuelle Energie-Anzeige (Spalte 7)
        self._energy_delegate = EnergyBarDelegate(self.table)
        self.table.setItemDelegateForColumn(7, self._energy_delegate)
        self._transition_score_delegate = TransitionScoreDelegate(self.table)
        self.table.setItemDelegateForColumn(14, self._transition_score_delegate)

        layout.addWidget(self.table, 1)

        # Drag-Info
        self._drag_info_default = (
            "Drag and drop rows to reorder. Transition scores update automatically."
        )
        self._drag_info_style_default = (
            f"QLabel {{ color: {COLORS['text_dim']}; font-size: 10px; font-style: italic; }}"
        )
        self._drag_info = QLabel(self._drag_info_default)
        self._drag_info.setWordWrap(True)
        self._drag_info.setStyleSheet(self._drag_info_style_default)
        layout.addWidget(self._drag_info)

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
        bpm_tolerance=2.0,
        scoring_context=None,
    ):
        """Playlist-Daten setzen und Tabelle fuellen."""
        self.playlist = playlist
        self.quality_metrics = quality_metrics
        self.bpm_tolerance = bpm_tolerance
        # HPG-001: Scoring-Kontext merken, damit Tabelle/Reorder/Quality
        # denselben Vertrag nutzen wie die Generierung
        self.scoring_context = scoring_context or {}
        if transition_recommendations is None:
            self.transition_recommendations = compute_transition_recommendations(
                playlist,
                bpm_tolerance=self.bpm_tolerance,
                scoring_context=self.scoring_context,
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

    def _passung_tooltip(self, metrics) -> str:
        """Schluesselt den Passungs-Score in seine acht Faktoren auf.

        "nicht bestimmbar" statt 0 % ist wichtig: ein fehlender Faktor wird
        beim Scoring umverteilt, nicht bestraft. Eine 0 waere fuer den
        Nutzer nicht von einer schlechten Passung zu unterscheiden.
        """
        if metrics is None:
            return ""

        def fmt(wert, ist_prozent_0_100=False):
            if wert is None:
                return "nicht bestimmbar"
            prozent = wert if ist_prozent_0_100 else wert * 100
            return f"{prozent:.0f} %"

        zeilen = [
            "Passung im Detail:",
            f"Harmonik: {fmt(metrics.harmonic_score, ist_prozent_0_100=True)}",
            f"BPM: {fmt(metrics.bpm_smoothness)}",
            f"Energie: {fmt(metrics.energy_flow)}",
            f"Genre: {fmt(metrics.genre_compatibility)}",
            f"Groove: {fmt(metrics.groove_match)}",
            f"Bassdruck: {fmt(metrics.bass_continuity)}",
            f"Klangfarbe: {fmt(metrics.timbre_match)}",
            f"Stimmung: {fmt(metrics.mood_match)}",
        ]
        return "\n".join(zeilen)

    @staticmethod
    def _make_transition_score_item(score):
        """Erzeugt die einheitliche Passungsanzeige fuer eine Tabellenzeile."""
        if score is None:
            item = QTableWidgetItem("—")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setToolTip("Erster Track: kein vorheriger Uebergang.")
            return item

        accent_color, _, label = transition_score_style(score / 100.0)
        item = QTableWidgetItem(f"{int(score)}% · {label}")
        item.setData(Qt.ItemDataRole.UserRole, float(score))
        item.setBackground(QColor(accent_color))
        item.setForeground(QColor(TRANSITION_SCORE_TEXT))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setToolTip(f"{label}: {int(score)}% Passung zum vorherigen Track.")
        return item

    @staticmethod
    def _make_ai_insights_item(track):
        """Erzeugt die AI-Spalte aus dem persistierten Track-Zustand."""
        metadata = getattr(track, "ai_metadata", {}) or {}
        moods = metadata.get("moods", [])
        if isinstance(moods, list):
            text = ", ".join(str(mood) for mood in moods)
        else:
            text = str(moods)
        sub_genre = str(metadata.get("sub_genre", "") or "").strip()
        if sub_genre:
            text = f"[{sub_genre}] {text}".strip()
        item = QTableWidgetItem(text or "-")
        item.setToolTip(str(metadata.get("description", "") or ""))
        return item

    def _populate_table(self):
        """Tabelle mit Performance-Optimierung befuellen."""
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self.playlist))

        for i, track in enumerate(self.playlist):
            transition_score = 0
            compatibility = None
            if i > 0:
                prev_track = self.playlist[i - 1]
                compatibility = calculate_enhanced_compatibility(
                    prev_track, track, self.bpm_tolerance, **self.scoring_context
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

            # Mix In / Mix Out — Rang-1-Kandidat des Paars (Plan), sonst Analyse
            mix_in_item, mix_out_item = _mixpunkt_items(i, track, self.transition_recommendations)
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

            # Passung zum vorherigen Track (Spalte 14)
            score_item = self._make_transition_score_item(
                transition_score if i > 0 else None
            )
            tooltip = self._passung_tooltip(compatibility)
            if tooltip:
                score_item.setToolTip(tooltip)
            self.table.setItem(i, 14, score_item)

            # KI-Metadaten gehoeren zum Track und muessen auch nach einer
            # kompletten Tabellen-Neubevoelkerung sichtbar bleiben.
            self.table.setItem(i, 15, self._make_ai_insights_item(track))

        self.table.setUpdatesEnabled(True)

    def set_reorder_locked(self, locked: bool):
        """Sperrt/entsperrt das Drag&Drop-Reorder der Playlist.

        Waehrend der KI-Veredelung (RunState.AI) laeuft die Playlist-Generierung
        nach KI-Abschluss noch einmal komplett durch — eine in diesem Fenster
        manuell umsortierte Reihenfolge wuerde sonst kommentarlos ueberschrieben.
        Deshalb wird das Sortieren gesperrt und sichtbar gekennzeichnet.
        """
        if locked:
            self.table.setDragDropMode(QTableWidget.DragDropMode.NoDragDrop)
            self._drag_info.setText(
                "🔒 Sortieren gesperrt — die KI-Analyse laeuft noch. Die Reihenfolge "
                "wuerde sonst nach Abschluss ueberschrieben. Freigabe automatisch, "
                "sobald die KI-Veredelung fertig ist."
            )
            self._drag_info.setStyleSheet(
                f"QLabel {{ color: {COLORS['accent_warning']}; font-size: 10px; font-weight: bold; }}"
            )
        else:
            self.table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
            self._drag_info.setText(self._drag_info_default)
            self._drag_info.setStyleSheet(self._drag_info_style_default)

    def _on_rows_moved(self, *args):
        """Drag-and-Drop Reorder Handler."""
        if not self.playlist:
            return

        track_by_id = {t.track_id: t for t in self.playlist}
        reordered_playlist = []
        for i in range(self.table.rowCount()):
            track_name_item = self.table.item(i, 1)
            if track_name_item:
                row_id = os.path.normcase(
                    os.path.abspath(
                        os.path.normpath(
                            str(track_name_item.data(Qt.ItemDataRole.UserRole) or "")
                        )
                    )
                )
                track = track_by_id.get(row_id)
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
            compatibility = None
            if i > 0 and i < len(self.playlist):
                prev_track = self.playlist[i - 1]
                current_track = self.playlist[i]
                compatibility = calculate_enhanced_compatibility(
                    prev_track, current_track, self.bpm_tolerance,
                    **self.scoring_context
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

            # Spalte 14: Passung zum vorherigen Track aktualisieren
            score_item = self._make_transition_score_item(
                transition_score if i > 0 else None
            )
            tooltip = self._passung_tooltip(compatibility)
            if tooltip:
                score_item.setToolTip(tooltip)
            self.table.setItem(i, 14, score_item)

        # Quality neu berechnen — mit aktivem Scoring-Kontext (HPG-001)
        self.quality_metrics = calculate_playlist_quality(
            self.playlist, self.bpm_tolerance, self.scoring_context
        )
        self._update_quality_display()
        self.transition_recommendations = compute_transition_recommendations(
            self.playlist,
            bpm_tolerance=self.bpm_tolerance,
            scoring_context=self.scoring_context,
        )
        # Spalten 10/11 haengen seit Teil 4 vom Paar ab (Plan des aktiven
        # Kandidaten) — nach dem Umsortieren neu setzen (Waechter Tor 2 Teil 4)
        for i, track in enumerate(self.playlist[:self.table.rowCount()]):
            mix_in_item, mix_out_item = _mixpunkt_items(i, track, self.transition_recommendations)
            self.table.setItem(i, 10, mix_in_item)
            self.table.setItem(i, 11, mix_out_item)


class MixTipsPanel(QWidget):
    """Mix-Empfehlungen als Scroll-Cards."""

    preview_state_changed = pyqtSignal(bool)
    # Nutzer hat in der Kandidatentabelle einen Kandidaten gewaehlt: (Karten-Index, Rang)
    candidate_chosen = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.transition_recommendations = []
        # Mapping: enumerate-Index → QVBoxLayout der jeweiligen Karte
        self._card_layouts: dict[int, QVBoxLayout] = {}
        # Mapping: enumerate-Index → TransitionPreviewWidget
        self._preview_widgets: dict[int, TransitionPreviewWidget] = {}
        self._preview_buttons: dict[int, QPushButton] = {}
        self._preview_transitions = []
        self._preview_queue = deque(maxlen=8)
        self._preview_cache = OrderedDict()
        self._preview_cache_limit = 8
        self._preview_temp_dirs: set[str] = set()
        self._active_preview_index = None
        # Aktiver Render-Worker (kann None sein)
        self._render_worker: TransitionRenderWorker | None = None
        # Kandidatentabellen je Karte; Guard gegen Signal-Echo beim Fuellen
        self._kandidaten_tabellen: dict[int, QTableWidget] = {}
        self._tabelle_fuellt = False
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
        self._cleanup_existing_previews()
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
        self._kandidaten_tabellen = {}

        if not self.transition_recommendations:
            empty_label = QLabel("No transition tips available yet.")
            empty_label.setStyleSheet(
                f"QLabel {{ color: {COLORS['text_secondary']}; font-style: italic; margin: 12px; }}"
            )
            self.container_layout.addWidget(empty_label)
            self.container_layout.addStretch()
            return

        for card_index, rec in enumerate(self.transition_recommendations):
            accent_color, bg_color, fit_label = transition_score_style(
                rec.compatibility_score / 100.0
            )

            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_color};
                    border-radius: 0px;
                    border: 2px solid {accent_color};
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
            summary = QLabel(
                f"{fit_label} | Score {rec.compatibility_score}/100 | "
                f"BPM {rec.bpm_delta:+.1f} | Energy {rec.energy_delta:+d}"
            )
            summary.setStyleSheet(
                f"QLabel {{ color: {TRANSITION_SCORE_TEXT}; "
                f"background-color: {accent_color}; font-weight: 700; "
                f"padding: 5px 8px; }}"
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

            # Kandidatentabelle (Spec 2026-08-21 Abschnitt 4): alle PairCandidates
            # des Paars; Klick = Kandidat aktiv -> Preview, Timeline, Export folgen.
            kandidaten = list(getattr(rec, "kandidaten", []) or [])
            if kandidaten:
                tabelle = self._baue_kandidaten_tabelle(
                    card_index, kandidaten, int(getattr(rec, "kandidat_aktiv", 0) or 0)
                )
                self._kandidaten_tabellen[card_index] = tabelle
                card_layout.addWidget(tabelle)

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
    # Kandidatentabelle (Teil 4)
    # ------------------------------------------------------------------

    KANDIDATEN_SPALTEN = ("Rang", "Mix-Out A", "Mix-In B", "Blende", "Schema", "Score",
                          "Teilwerte", "Begruendung")

    def _baue_kandidaten_tabelle(self, card_index: int, kandidaten: list, aktiv: int) -> QTableWidget:
        tabelle = QTableWidget(len(kandidaten), len(self.KANDIDATEN_SPALTEN))
        tabelle.setHorizontalHeaderLabels(list(self.KANDIDATEN_SPALTEN))
        tabelle.verticalHeader().setVisible(False)
        tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabelle.setToolTip("Kandidaten fuer diesen Uebergang — Klick macht einen Kandidaten aktiv "
                           "(Preview, Timeline und Export folgen; die Wahl wird gemerkt).")
        tabelle.setStyleSheet(
            f"QTableWidget {{ background-color: {COLORS['bg_input']}; color: {COLORS['text_primary']}; "
            f"font-family: {FONT_FAMILY}; font-size: 11px; border: 0px; }}"
            f"QHeaderView::section {{ background-color: {COLORS['bg_input']}; "
            f"color: {COLORS['text_secondary']}; border: 0px; padding: 2px 4px; }}"
        )
        self._tabelle_fuellt = True
        try:
            for zeile, k in enumerate(kandidaten):
                schema_out = (k.get("out_a", {}).get("schema") or [""])[0]
                schema_in = (k.get("in_b", {}).get("schema") or [""])[0]
                werte = (
                    str(k.get("rang", zeile + 1)),
                    f"{float(k.get('t_out', 0.0)):.1f} s",
                    f"{float(k.get('t_in', 0.0)):.1f} s",
                    f"{int(k.get('blend_bars', 0))} Takte",
                    f"{schema_out} \u2192 {schema_in}",
                    f"{float(k.get('score', 0.0)):.2f}",
                    kandidat_teilwerte_kurz(k.get("teilwerte") or {}),
                    str(k.get("begruendung", "")),
                )
                for spalte, text in enumerate(werte):
                    item = QTableWidgetItem(text)
                    item.setData(Qt.ItemDataRole.UserRole, int(k.get("rang", zeile + 1)))
                    item.setToolTip(str(k.get("begruendung", "")))
                    tabelle.setItem(zeile, spalte, item)
                if int(k.get("rang", zeile + 1)) == aktiv:
                    tabelle.selectRow(zeile)
        finally:
            self._tabelle_fuellt = False
        tabelle.resizeColumnsToContents()
        tabelle.horizontalHeader().setStretchLastSection(True)
        zeilen_hoehe = tabelle.verticalHeader().defaultSectionSize()
        sichtbar = min(6, len(kandidaten))
        tabelle.setFixedHeight(tabelle.horizontalHeader().height() + zeilen_hoehe * sichtbar + 6)
        tabelle.itemSelectionChanged.connect(
            lambda requested=card_index, t=tabelle: self._on_kandidat_gewaehlt(requested, t)
        )
        return tabelle

    def _on_kandidat_gewaehlt(self, card_index: int, tabelle: QTableWidget) -> None:
        if self._tabelle_fuellt:
            return
        zeilen = tabelle.selectionModel().selectedRows() if tabelle.selectionModel() else []
        if not zeilen:
            return
        item = tabelle.item(zeilen[0].row(), 0)
        if item is None:
            return
        rang = item.data(Qt.ItemDataRole.UserRole)
        try:
            rang = int(rang)
        except (TypeError, ValueError):
            return
        self.candidate_chosen.emit(card_index, rang)

    def verwerfe_preview(self, index: int) -> None:
        """Gerenderte Vorschau eines Paars verwerfen (der Plan hat sich geaendert)."""
        path = self._preview_cache.pop(index, None)
        if path:
            self._remove_preview_path(path)
        widget = self._preview_widgets.get(index)
        if widget is not None:
            try:
                widget.clear_error()
            except RuntimeError:
                pass
        button = self._preview_buttons.get(index)
        if button:
            try:
                button.setEnabled(True)
                button.setText("Vorschau bei Bedarf rendern")
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # Transition-Preview-Integration
    # ------------------------------------------------------------------

    def setup_transition_previews(self, transitions: list):
        """
        Registriert On-Demand-Previews ohne Player oder Renderjobs anzulegen.
        """
        self._cleanup_existing_previews()
        self._preview_widgets = {}
        self._preview_buttons = {}
        self._preview_transitions = list(transitions)
        for index in range(len(self._preview_transitions)):
            button = QPushButton("Vorschau bei Bedarf rendern")
            button.clicked.connect(
                lambda checked=False, requested=index: self._request_preview(requested)
            )
            self._preview_buttons[index] = button
            if index in self._card_layouts:
                self._card_layouts[index].addWidget(button)

    def _request_preview(self, index: int):
        if index < 0 or index >= len(self._preview_transitions):
            return
        if index not in self._preview_widgets:
            widget = TransitionPreviewWidget(
                index, self._preview_transitions[index], self
            )
            self._preview_widgets[index] = widget
            self._insert_preview_widget(index, widget)
        else:
            # Retry nach Fehler: bestehendes Widget wiederverwenden und die
            # alte Fehleranzeige zuruecknehmen.
            try:
                self._preview_widgets[index].clear_error()
            except RuntimeError:
                pass  # Widget bereits von Qt zerstoert
        button = self._preview_buttons.get(index)
        if button:
            button.setEnabled(False)
            button.setText("Vorschau wird vorbereitet …")
        if index in self._preview_cache:
            path = self._preview_cache.pop(index)
            self._preview_cache[index] = path
            self._on_clip_ready(index, path)
            return
        if index != self._active_preview_index and index not in self._preview_queue:
            if len(self._preview_queue) >= self._preview_queue.maxlen:
                self._on_clip_error(index, "Render-Warteschlange ist voll")
                return
            self._preview_queue.append(index)
        self._start_next_preview()

    def _start_next_preview(self):
        if self._render_worker is not None or not self._preview_queue:
            return
        index = self._preview_queue.popleft()
        self._active_preview_index = index
        worker = TransitionRenderWorker([self._preview_transitions[index]], self)
        self._render_worker = worker
        self.preview_state_changed.emit(True)
        worker.clip_ready.connect(
            lambda _local, path, requested=index: self._on_clip_ready(requested, path)
        )
        worker.clip_error.connect(
            lambda _local, error, requested=index: self._on_clip_error(requested, error)
        )
        worker.finished.connect(
            lambda source=worker: self._on_preview_worker_finished(source)
        )
        worker.start()

    def _on_preview_worker_finished(self, source_worker=None):
        worker = source_worker or self._render_worker
        if worker is not self._render_worker:
            return
        self._render_worker = None
        self._active_preview_index = None
        if worker:
            # M3-Fix: verwaiste Temp-Dateien loeschen (fehlgeschlagene/teilweise
            # geschriebene Clips leaken sonst dauerhaft). NUR die, die NICHT als
            # fertige Preview im Cache gelandet sind — erfolgreiche Clips gehoeren
            # jetzt dem _preview_cache (LRU/Cleanup verwaltet sie), hier loeschen
            # wuerde dem User die gerade fertige Vorschau wegnehmen.
            active_paths = set(self._preview_cache.values())
            temp_dir = worker.get_temp_dir()
            if temp_dir:
                self._preview_temp_dirs.add(temp_dir)
            for path in worker.get_temp_files():
                if path not in active_paths:
                    self._remove_preview_path(path)
            if temp_dir and not any(
                os.path.dirname(path) == temp_dir for path in active_paths
            ):
                self._remove_preview_dir(temp_dir)
            worker.deleteLater()
        self._start_next_preview()
        if self._render_worker is None and not self._preview_queue:
            self.preview_state_changed.emit(False)

    def _remove_preview_dir(self, directory: str) -> None:
        if directory not in self._preview_temp_dirs:
            return
        try:
            os.rmdir(directory)
        except OSError:
            return
        self._preview_temp_dirs.discard(directory)

    def _remove_preview_path(self, path: str) -> None:
        directory = os.path.dirname(path)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            return
        self._remove_preview_dir(directory)

    def _insert_preview_widget(self, index: int, widget: TransitionPreviewWidget):
        """Haengt das Preview-Widget an das card_layout des jeweiligen Uebergangs."""
        if index in self._card_layouts:
            self._card_layouts[index].addWidget(widget)

    def _cleanup_existing_previews(self):
        """Laufenden Worker stoppen, Widgets entfernen, Temp-Dateien loeschen."""
        if self._render_worker is not None:
            # Audit-Fix 2026-07-21: ALLE Signale generisch trennen (ohne Slot-Arg).
            # Vorher wurde clip_ready/clip_error mit einem konkreten Slot getrennt,
            # der nie verbunden war (Signale haengen an Lambdas) -> TypeError
            # verschluckt, nichts getrennt; vor allem blieb 'finished' mit
            # _on_preview_worker_finished verbunden. Beendete sich dieser alte
            # Worker spaeter, feuerte finished -> _on_preview_worker_finished las
            # das inzwischen NEUE self._render_worker und rief deleteLater() auf
            # einem laufenden QThread -> "QThread destroyed while running"-Crash.
            for _sig in (
                self._render_worker.clip_ready,
                self._render_worker.clip_error,
                self._render_worker.finished,
            ):
                try:
                    _sig.disconnect()
                except (TypeError, RuntimeError):
                    pass

            self._render_worker.request_cancel()

            old_worker = self._render_worker

            if old_worker.isRunning():
                # Alten Thread asynchron im Hintergrund fertigstellen lassen,
                # um Freezes (durch blockierendes wait()) zu vermeiden.
                def clean_and_delete():
                    try:
                        old_worker.cleanup()
                    except OSError:
                        pass
                    old_worker.deleteLater()

                old_worker.finished.connect(clean_and_delete)
            else:
                old_worker.cleanup()
                old_worker.deleteLater()
            self._render_worker = None
            
        # AUDIT-FIX N2: laufende Waveform-Peak-Worker sauber stoppen, BEVOR
        # die Preview-Widgets (und damit die WaveformWidgets) entsorgt werden.
        stop_peaks()

        # H2-Fix: laufende Player stoppen und Datei-Handles freigeben, BEVOR die
        # zugehoerigen WAVs geloescht werden — sonst Windows-PermissionError.
        for _widget in self._preview_widgets.values():
            try:
                _widget.stop_and_reset()
                _widget.deleteLater()
            except RuntimeError:
                pass  # Widget bereits von Qt zerstoert
        self._preview_widgets = {}
        self._preview_buttons.clear()
        self._preview_queue.clear()
        self._active_preview_index = None
        for path in self._preview_cache.values():
            self._remove_preview_path(path)
        self._preview_cache.clear()
        for directory in list(self._preview_temp_dirs):
            self._remove_preview_dir(directory)
        self.preview_state_changed.emit(False)

    def _on_clip_ready(self, index: int, wav_path: str):
        """Aufgerufen wenn ein Clip fertig gerendert ist."""
        self._preview_cache[index] = wav_path
        while len(self._preview_cache) > self._preview_cache_limit:
            stale_index, stale_path = self._preview_cache.popitem(last=False)
            # H2-Fix: falls der verdraengte Clip noch in einem Player offen ist,
            # erst Handle freigeben, sonst os.remove -> Windows-PermissionError.
            stale_widget = self._preview_widgets.get(stale_index)
            if stale_widget is not None:
                try:
                    stale_widget.stop_and_reset()
                except RuntimeError:
                    pass
            self._remove_preview_path(stale_path)
        if index in self._preview_widgets:
            self._preview_widgets[index].set_wav_path(wav_path)
        button = self._preview_buttons.get(index)
        if button:
            button.setText("Vorschau geladen")

    def _on_clip_error(self, index: int, error_msg: str):
        """Aufgerufen wenn Rendering eines Clips fehlgeschlagen ist.

        Das Preview-Widget bleibt stehen und zeigt den Fehler an (statt
        entsorgt zu werden) — so ist sichtbar, WELCHER Uebergang gescheitert
        ist. Ein Retry ueber den Karten-Button nutzt dasselbe Widget weiter.
        """
        widget = self._preview_widgets.get(index)
        if widget is not None:
            try:
                widget.stop_and_reset()
                widget.set_error(error_msg)
            except RuntimeError:
                # Widget bereits von Qt zerstoert
                self._preview_widgets.pop(index, None)
        button = self._preview_buttons.get(index)
        if button:
            button.setEnabled(True)
            button.setText(f"Vorschau erneut rendern ({error_msg})")


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

    def set_timeline(self, playlist, transition_recommendations=None):
        """Timeline aus Playlist berechnen und als HTML rendern."""
        if not playlist:
            self.text_edit.setHtml("<p>Keine Playlist vorhanden.</p>")
            return

        plans = [
            rec.plan for rec in (transition_recommendations or [])
            if getattr(rec, "plan", None) is not None
        ]
        timeline = compute_set_timeline(
            playlist, transition_plans=plans or None
        )
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


class CamelotWheelWidget(QWidget):
    """Zeichnet das Camelot-Rad (A/B) mit dem Pfad des aktuellen Sets.

    Signature-Element des Ink-Navy-Gold-Designs: der harmonische Weg des Sets
    ist direkt auf dem Rad sichtbar — kurze Boegen = harmonisch, weite/rote
    Kanten = Sprung bzw. BPM-Clash.
    """

    def __init__(self, parent=None, bpm_tolerance: float = 6.0):
        super().__init__(parent)
        self._playlist = []
        self._bpm_tolerance = bpm_tolerance
        self.setMinimumHeight(300)

    def set_playlist(self, playlist, bpm_tolerance: float = None):
        self._playlist = list(playlist or [])
        if bpm_tolerance is not None:
            self._bpm_tolerance = bpm_tolerance
        self.update()

    @staticmethod
    def _key_color(num: int) -> QColor:
        """Camelot-Position -> gedaempfte Spektralfarbe (Ink-Navy-Gold-Ton)."""
        c = QColor()
        c.setHsl(int(((num - 1) % 12) * 30), 140, 150)  # Sat ~55%, Light ~59%
        return c

    def _edge_color(self, track_a, track_b) -> QColor:
        """Farbe der Set-Kante nach Uebergangs-Qualitaet."""
        try:
            metrics = calculate_enhanced_compatibility(
                track_a, track_b, self._bpm_tolerance
            )
            score = metrics.overall_score
        except Exception:
            score = 0.5
        if score <= 0.001:
            return QColor(COLORS["accent_danger"])
        if score >= 0.6:
            return QColor(COLORS["accent_success"])
        return QColor(COLORS["accent_warning"])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) / 2.0 - 22
        r_a = radius * 0.62   # innerer Ring (A / Moll)
        r_b = radius          # aeusserer Ring (B / Dur)

        # Ring-Linien
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r in (r_a, r_b):
            p.drawEllipse(QPointF(cx, cy), r, r)

        import math

        def pos(num, r):
            ang = ((num - 1) / 12.0) * 2 * math.pi - math.pi / 2
            return QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r)

        # Set-Positionen (nur A/B aus camelotCode)
        parsed = []
        for tr in self._playlist:
            code = getattr(tr, "camelotCode", "") or ""
            num, letter = get_camelot_components(code)
            if num:
                parsed.append((tr, num, letter))

        used_nodes = {(num, letter) for _, num, letter in parsed}

        def ring(letter):
            return r_b if letter == "B" else r_a

        # 24 Knoten zeichnen
        for num in range(1, 13):
            for r, letter in ((r_a, "A"), (r_b, "B")):
                pt = pos(num, r)
                col = self._key_color(num)
                used = (num, letter) in used_nodes
                if not used:
                    col.setAlpha(90)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(col))
                rad = 6.0 if used else 4.5
                p.drawEllipse(pt, rad, rad)
            # Zahl zwischen den Ringen
            lp = pos(num, (r_a + r_b) / 2.0)
            p.setPen(QColor(COLORS["text_secondary"]))
            f = QFont()
            f.setPointSize(7)
            p.setFont(f)
            p.drawText(QRectF(lp.x() - 10, lp.y() - 8, 20, 16),
                       Qt.AlignmentFlag.AlignCenter, str(num))

        # Set-Pfad (Kanten mit Pfeil-Farbe nach Qualitaet)
        for i in range(len(parsed) - 1):
            _, n1, letter1 = parsed[i]
            _, n2, letter2 = parsed[i + 1]
            p1, p2 = pos(n1, ring(letter1)), pos(n2, ring(letter2))
            col = self._edge_color(parsed[i][0], parsed[i + 1][0])
            pen = QPen(col, 2.0)
            if col.name() == QColor(COLORS["accent_danger"]).name():
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(p1, p2)

        # Reihenfolge-Badges auf dem tatsaechlich besuchten A-/B-Knoten
        for idx, (_, num, letter) in enumerate(parsed):
            pt = pos(num, ring(letter))
            p.setPen(QPen(self._key_color(num), 1.5))
            p.setBrush(QBrush(QColor(COLORS["bg_main"])))
            p.drawEllipse(pt, 8.5, 8.5)
            p.setPen(QColor(COLORS["text_bright"]))
            f = QFont()
            f.setPointSize(7)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(pt.x() - 10, pt.y() - 9, 20, 18),
                       Qt.AlignmentFlag.AlignCenter, str(idx + 1))

        # Zentrum-Label
        p.setPen(QColor(COLORS["text_dim"]))
        f = QFont()
        f.setPointSize(7)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(cx - 40, cy - 8, 80, 16),
                   Qt.AlignmentFlag.AlignCenter, "CAMELOT")
        p.end()


class AnalyticsPanel(QWidget):
    """Quality Analysis — Camelot-Rad + HTML Bericht."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Signature: Camelot-Rad mit Set-Pfad (Ink Navy Gold)
        self.wheel = CamelotWheelWidget()
        self.wheel.setFixedHeight(320)
        layout.addWidget(self.wheel)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit, 1)

    def set_analytics(self, quality_metrics, playlist=None, bpm_tolerance=6.0):
        """Analytics: Camelot-Rad fuellen + HTML aus Quality-Metriken generieren."""
        self.wheel.set_playlist(playlist or [], bpm_tolerance)
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


class ToolTipEventFilter(QObject):
    """
    Globaler EventFilter, der Tooltips unendlich lange (bis zu 10 Minuten) 
    anzeigt, solange die Maus still auf dem Widget verweilt.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ToolTip:
            if isinstance(obj, QWidget) and obj.toolTip():
                # Zeige den Tooltip manuell an der Cursor-Position mit 600.000 ms (10 Minuten)
                QToolTip.showText(QCursor.pos(), obj.toolTip(), obj, QRect(), 600000)
                return True
        return super().eventFilter(obj, event)


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
        self.analyzed_raw_tracks = []
        self.quality_metrics = {}
        self.current_playlist_mode = "Harmonic Flow"
        self.current_bpm_tolerance = 2.0
        self.current_scoring_context = {}  # HPG-001: aktiver Scoring-Vertrag
        self.worker = None
        self.ai_worker = None
        self._dependency_worker = None
        self.run_state = RunState.IDLE
        self._run_settings = None
        self._run_id = 0
        self._close_pending = False

        self.init_ui()
        self.connect_signals()
        self.check_dependencies_and_warn()

    def check_dependencies_and_warn(self):
        """Prueft optionale Dienste im Hintergrund und aktualisiert danach die UI."""
        if self._dependency_worker and self._dependency_worker.isRunning():
            return
        ai_provider = hpg_config.AI_PROVIDER
        url = (
            hpg_config.AI_API_URL_LMSTUDIO
            if ai_provider == "LM Studio"
            else hpg_config.AI_API_URL_OLLAMA
        )
        worker = DependencyCheckWorker(ai_provider, url, parent=self)
        self._dependency_worker = worker
        worker.checked.connect(
            lambda pedalboard_installed, ai_online, rekordbox_running,
            source=worker:
            self._on_dependencies_checked(
                pedalboard_installed, ai_online, rekordbox_running,
                ai_provider, source
            )
        )
        worker.finished.connect(
            lambda source=worker: self._cleanup_dependency_worker(source)
        )
        worker.start()

    def _cleanup_dependency_worker(self, worker):
        if self._dependency_worker is not worker:
            return
        self._dependency_worker = None
        try:
            worker.deleteLater()
        except RuntimeError:
            pass

    def _on_dependencies_checked(
        self, pedalboard_installed, ai_online, rekordbox_running,
        ai_provider, source_worker=None
    ):
        if (
            source_worker is not None
            and source_worker is not self._dependency_worker
        ):
            return
        warnings = []
        if not pedalboard_installed:
            warnings.append("• Spotify-Pedalboard fehlt: Frequenzweichen (EQ-Swap) werden ueber eine Scipy-Alternative berechnet. Der echte Dynamik-Compressor ist inaktiv.")
        if not ai_online:
            # M4-Fix: Hinweis passend zum gewaehlten Provider statt hardcodiert Ollama
            port = "1234" if ai_provider == "LM Studio" else "11434"
            warnings.append(f"• Lokaler KI-Server ({ai_provider}) ist offline: Optionale KI-Moods und Subgenres werden nicht ergaenzt; deterministische Mixing-Tips bleiben verfuegbar. Bitte starten Sie {ai_provider} auf Port {port}.")
        if rekordbox_running:
            # Rekordbox checkpointet sein WAL erst beim Beenden nach master.db.
            # Waehrend es laeuft, liest HPG einen aelteren Stand.
            warnings.append("• Rekordbox laeuft: HPG liest die Datenbank erst nach dem Beenden von Rekordbox aktuell. Frisch analysierte Tracks fehlen dann noch und werden neu berechnet. Fuer aktuelle Metadaten Rekordbox schliessen.")

        if warnings:
            warn_text = "System-Hinweis: Einige Dienste sind eingeschraenkt (Fuer Details hier hovern)"
            self.status_bar.set_status(warn_text)
            self.status_bar.setToolTip("\n".join(warnings))
            # Audit-Fix 2026-07-21: status_bar ist ein StatusBarWidget(QWidget),
            # KEIN QStatusBar -> der alte QStatusBar-Selektor matchte nie, die
            # orange Warnfarbe erschien nicht. Korrekter Widget-Typ.
            self.status_bar.setStyleSheet("StatusBarWidget { background-color: #2b1f1a; color: #ffaa00; font-weight: bold; }")

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
        """Keyboard Shortcuts fuer Generierung, Export und Sidebar-Navigation."""
        # Ctrl+G → Playlist generieren
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self.start_analysis)
        # Ctrl+E → Export
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self.export_playlist)
        # Ctrl+1..5 → Sidebar-Panel direkt anwaehlen
        for i in range(5):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(
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
        self.mix_tips_panel.preview_state_changed.connect(
            self._on_preview_state_changed
        )
        self.mix_tips_panel.candidate_chosen.connect(self._on_candidate_chosen)

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

    def _set_run_state(self, state: RunState) -> None:
        """Setzt den zentralen Pipelinezustand."""
        self.run_state = state
        # Reorder-Sperre zentral an den Zustand koppeln: nur waehrend der
        # KI-Veredelung (RunState.AI) gesperrt, jeder Uebergang weg davon
        # (PLAYLIST/CANCELLED/ERROR) gibt das Sortieren automatisch wieder frei.
        panel = getattr(self, "playlist_panel", None)
        if panel is not None:
            panel.set_reorder_locked(state == RunState.AI)

    def _run_is_active(self) -> bool:
        """Beruecksichtigt Zustand und alle mutierenden Hauptworker."""
        worker_alive = bool(self.worker and self.worker.isRunning())
        ai_alive = bool(self.ai_worker and self.ai_worker.isRunning())
        # Den Worker zusaetzlich zum Zustand pruefen, damit auch das kurze Fenster
        # zwischen Threadstart und Preview-State sicher als aktiv gilt.
        render_worker = getattr(getattr(self, "mix_tips_panel", None), "_render_worker", None)
        render_alive = bool(render_worker and render_worker.isRunning())
        return (
            self.run_state in ACTIVE_RUN_STATES
            or worker_alive or ai_alive or render_alive
        )

    def _on_preview_state_changed(self, active: bool) -> None:
        """Spiegelt On-Demand-Rendering in RunState und Cancel-UI."""
        if active:
            if self.run_state not in {
                RunState.AUDIO,
                RunState.AI,
                RunState.PLAYLIST,
                RunState.CANCELLING,
            }:
                self._set_run_state(RunState.PREVIEW)
                self.status_bar.show_progress()
                self.status_bar.set_progress(0)
                self.status_bar.set_status("Transition-Vorschau wird gerendert...")
            return
        if self.run_state == RunState.CANCELLING:
            if not (self.worker and self.worker.isRunning()) and not (
                self.ai_worker and self.ai_worker.isRunning()
            ):
                self._finish_run(RunState.CANCELLED, "Vorschau abgebrochen.")
        elif self.run_state == RunState.PREVIEW:
            self._finish_run(RunState.SUCCESS, "Transition-Vorschau bereit.")

    def _finish_run(self, state: RunState, status: str) -> None:
        """Stellt die UI in jedem terminalen Pfad deterministisch wieder her."""
        self._set_run_state(state)
        self.library_panel.start_button.setEnabled(True)
        self.toolbar.set_generate_enabled(True)
        self.status_bar.hide_progress()
        self.status_bar.set_status(status)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder_path:
            self.library_panel.set_folder_path(folder_path)

    def start_analysis(self):
        """Analyse starten — Progress in StatusBar, aktueller Content bleibt."""
        # H2-Fix: Doppelstart-Schutz — Ctrl+G umgeht den deaktivierten Button;
        # ohne Guard wuerde der laufende Worker verwaisen (zweiter ProcessPool)
        if self._run_is_active():
            self.status_bar.set_status("Analyse laeuft bereits...")
            return

        settings = self.library_panel.get_current_settings()

        if not settings["folder"]:
            QMessageBox.warning(
                self, "No Folder Selected", "Please select a music folder first."
            )
            return

        advanced = self.library_panel.advanced_params
        # Ein Lauf verwendet einen unveraenderlichen Snapshot. Aenderungen an
        # Controls waehrend der Audioanalyse gelten erst fuer den naechsten Lauf.
        self._run_settings = {
            "folder": settings["folder"],
            "strategy": settings["strategy"],
            "bpm_tolerance": settings["bpm_tolerance"],
            "advanced_params": dict(settings["advanced_params"]),
            "ai_provider": advanced.detected_provider or (
                "LM Studio" if advanced.lmstudio_radio.isChecked() else "Ollama"
            ),
            "ai_model": advanced.model_combo.currentText(),
            "ai_base_url": advanced.detected_base_url,
        }
        settings = self._run_settings

        # Buttons deaktivieren
        self.library_panel.start_button.setEnabled(False)
        self.toolbar.set_generate_enabled(False)

        # StatusBar: Progress zeigen
        self.status_bar.show_progress()
        self.status_bar.set_status("Starting analysis...")
        # Befund des Vorlaufs verwerfen — er gilt fuer einen anderen Ordner.
        self.status_bar.clear_hint()

        # Progress und Steps initialisieren
        self.library_panel.progress_widget.reset_steps()
        self.library_panel.progress_widget.set_step_status(0, "working")

        # Ein neuer Lauf darf bei einem spaeteren Fehler keine alte Playlist
        # weiter exportierbar lassen.
        self.playlist = []
        self.analyzed_raw_tracks = []
        self.quality_metrics = {}
        self.current_scoring_context = {}
        self.toolbar.set_export_enabled(False)
        self.playlist_panel.set_playlist_data([], {})
        self.mix_tips_panel.set_recommendations([])
        self.timeline_panel.set_timeline([], [])
        self.analytics_panel.set_analytics({}, [])

        # Worker erstellen und starten
        self._run_id += 1
        self._set_run_state(RunState.AUDIO)
        self.worker = AnalysisWorker(
            folder_path=settings["folder"],
            mode=settings["strategy"],
            bpm_tolerance=settings["bpm_tolerance"],
            advanced_params=settings["advanced_params"],
        )

        # Worker-Signale an StatusBar & progress_widget (skaliert auf 80%)
        self.worker.progress.connect(self._on_audio_progress)
        self.worker.phase_changed.connect(self.library_panel.progress_widget.set_step_status)
        self.worker.status_update.connect(self.status_bar.set_status)
        self.worker.rekordbox_coverage.connect(self._on_rekordbox_coverage)
        # AUDIT-FIX T1 (2026-07-24): Ergebnis ueber analysis_done; Cleanup erst
        # beim ECHTEN QThread.finished (Thread ist dann garantiert beendet).
        self.worker.analysis_done.connect(self.analysis_finished)
        current_worker = self.worker
        current_worker.finished.connect(
            lambda worker=current_worker: self._cleanup_analysis_worker(worker)
        )

        self.worker.start()

    def _cleanup_analysis_worker(self, source_worker=None):
        """AUDIT-FIX T1: raeumt den AnalysisWorker sicher auf, NACHDEM der
        QThread wirklich beendet ist (an QThread.finished gebunden)."""
        worker = source_worker or self.worker
        if worker is None or (source_worker is not None and worker is not self.worker):
            return
        try:
            worker.wait(2000)
        except Exception:
            pass
        worker.deleteLater()
        if worker is self.worker:
            self.worker = None

    def _on_audio_progress(self, percent):
        # Audio-Analyse nimmt die ersten 80% des Fortschritts ein
        if self.run_state not in {RunState.AUDIO, RunState.CANCELLING}:
            return
        scaled = map_phase_progress(percent, 0, 80)
        self.status_bar.set_progress(scaled)
        self.library_panel.progress_widget.set_progress(scaled)

    def _on_ai_progress(self, current, total):
        if total > 0 and self.run_state in {RunState.AI, RunState.CANCELLING}:
            percent = int((current / total) * 100)
            # AI-Analyse nimmt die verbleibenden 20% ein
            scaled = map_phase_progress(percent, 80, 95)
            self.status_bar.set_progress(scaled)
            self.library_panel.progress_widget.set_progress(scaled)
            self.status_bar.set_status(f"KI-Anreicherung laeuft... ({current}/{total} Tracks)")

    def cancel_analysis(self):
        """Analyse abbrechen — cooperative shutdown."""
        if not self._run_is_active():
            return
        self._set_run_state(RunState.CANCELLING)
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.request_cancel()
        render_worker = getattr(self.mix_tips_panel, "_render_worker", None)
        if render_worker and render_worker.isRunning():
            render_worker.request_cancel()

        self.status_bar.set_status("Abbruch angefordert; laufender Schritt wird beendet...")


    def on_ai_finished(self, track_path, ai_data, source_worker=None):
        """Update the playlist table with AI data."""
        if source_worker is not None and source_worker is not self.ai_worker:
            return
        if self.run_state == RunState.CANCELLING:
            return
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

        # Der Worker hat Metadaten und Cache bereits ausserhalb des GUI-Threads
        # aktualisiert. Hier wird nur noch der sichtbare Zustand synchronisiert.
        found_track = None
        found_row = -1
        
        # Zeile finden
        for row in range(self.playlist_panel.table.rowCount()):
            item = self.playlist_panel.table.item(row, 1) # Artist/Title column has filePath in UserRole
            if item and item.data(Qt.ItemDataRole.UserRole) == track_path:
                found_row = row
                break

        for track in self.analyzed_raw_tracks:
            if track.filePath == track_path:
                track.ai_metadata = ai_data
                found_track = track
                break

        if found_row != -1 and found_track:
            # 1. Update AI Insights column (col 15)
            ai_item = self.playlist_panel._make_ai_insights_item(found_track)
            self.playlist_panel.table.setItem(found_row, 15, ai_item)
            
            # 2. Update Mix In / Mix Out columns (col 10 & 11) — Rang-1-Kandidat
            #    des Paars (Plan) vor dem Analysewert, wie in _populate_table
            mix_in_item, mix_out_item = _mixpunkt_items(
                found_row, found_track, self.playlist_panel.transition_recommendations
            )
            self.playlist_panel.table.setItem(found_row, 10, mix_in_item)
            self.playlist_panel.table.setItem(found_row, 11, mix_out_item)
            
            # 3. Passung fuer diesen und den naechsten Track neu berechnen (Spalte 14)
            from hpg_core.playlist import calculate_enhanced_compatibility
            
            # HPG-001: Scoring-Kontext des Panels wiederverwenden
            scoring_context = getattr(self.playlist_panel, "scoring_context", {})
            # Recalculate for current row (compatibility to previous track)
            if found_row > 0:
                prev_track = self.playlist[found_row - 1]
                metrics = calculate_enhanced_compatibility(prev_track, found_track, self.playlist_panel.bpm_tolerance, **scoring_context)
                score = int(metrics.overall_score * 100)
                score_item = self.playlist_panel._make_transition_score_item(score)
                self.playlist_panel.table.setItem(found_row, 14, score_item)

            # Recalculate for next row (compatibility of next track to current track)
            if found_row < len(self.playlist) - 1:
                next_track = self.playlist[found_row + 1]
                metrics = calculate_enhanced_compatibility(found_track, next_track, self.playlist_panel.bpm_tolerance, **scoring_context)
                score = int(metrics.overall_score * 100)
                score_item = self.playlist_panel._make_transition_score_item(score)
                self.playlist_panel.table.setItem(found_row + 1, 14, score_item)
                
    def on_ai_worker_finished(
        self, source_worker=None, ai_completed=True, finalize=True
    ):
        """Erzeugt die Playlist und aktualisiert alle abhaengigen Ansichten."""
        if source_worker is not None and source_worker is not self.ai_worker:
            return
        ai_failure = getattr(source_worker, "failure_reason", "") if source_worker else ""
        if self.ai_worker:
            self.ai_worker.deleteLater()
            self.ai_worker = None
        if self.run_state == RunState.CANCELLING:
            self.library_panel.progress_widget.reset_steps()
            self._finish_run(RunState.CANCELLED, "Analysis cancelled.")
            return
        self._set_run_state(RunState.PLAYLIST)
        self.library_panel.progress_widget.set_step_status(
            4, "completed" if ai_completed else "inactive"
        )
        self.library_panel.progress_widget.set_step_status(2, "working")
        self.library_panel.progress_widget.set_progress(95)
        self.status_bar.set_progress(95)
        
        # 1. Playlist zum ersten Mal generieren, jetzt wo alle Audio- und AI-Features da sind!
        settings = self._run_settings or self.library_panel.get_current_settings()
        mode = settings["strategy"]
        bpm_tolerance = settings["bpm_tolerance"]
        advanced_params = settings["advanced_params"]
        
        from hpg_core.playlist import generate_playlist
        
        # Wir speichern das aktuelle Profil
        self.current_playlist_mode = mode
        self.current_bpm_tolerance = bpm_tolerance
        # HPG-001: EINEN Scoring-Kontext fuer Generierung, Anzeige, Reorder,
        # Preview, Quality und Empfehlungen festhalten
        self.current_scoring_context = resolve_scoring_context(mode, advanced_params)

        try:
            self.playlist = generate_playlist(
                self.analyzed_raw_tracks,
                mode=mode,
                bpm_tolerance=bpm_tolerance,
                advanced_params=advanced_params
            )
        except Exception as e:
            import logging
            logger = logging.getLogger("hpg_core.playlist")
            logger.error(f"Playlist generation failed: {e}")
            self._finish_run(RunState.ERROR, f"ERROR generating playlist: {str(e)}")
            return

        if not self.playlist:
            self._finish_run(RunState.ERROR, "ERROR: Playlist generation returned empty result.")
            return

        self.library_panel.progress_widget.set_step_status(2, "completed")
        self.library_panel.progress_widget.set_step_status(3, "working")

        # 2. Metriken und Transition-Empfehlungen berechnen — mit demselben
        # Scoring-Kontext wie die Generierung (HPG-001)
        scoring_context = self.current_scoring_context
        _, _, transition_plan = self._berechne_uebergaenge(bpm_tolerance, scoring_context)
        self.library_panel.progress_widget.set_step_status(3, "completed")
        self.library_panel.progress_widget.set_progress(100)
        self.status_bar.set_progress(100)

        # 3. Daten an alle Panels verteilen
        self._verteile_uebergaenge(transition_plan, bpm_tolerance, scoring_context)

        # 4. Toolbar & Status aktualisieren
        overall = self.quality_metrics.get("overall_score", 0)
        self.toolbar.set_export_enabled(True)
        self.toolbar.set_info(f"{len(self.playlist)} tracks | {mode}")
        self.status_bar.set_status(
            f"Complete — {len(self.playlist)} tracks, Quality {overall:.0%}"
        )
        
        # Automatisch zum Playlist-Panel wechseln
        self.sidebar.set_active(1)

        if finalize:
            final_state = RunState.PARTIAL if ai_failure else RunState.SUCCESS
            final_message = (
                f"Playlist fertig; KI-Anreicherung unvollstaendig: {ai_failure}"
                if ai_failure
                else f"Complete — {len(self.playlist)} tracks, Quality {overall:.0%}"
            )
            self._finish_run(final_state, final_message)

    def _on_rekordbox_coverage(self, coverage):
        """Zeigt an, wenn Tracks ohne Rekordbox-Daten analysiert wurden.

        Ohne diesen Hinweis sieht ein Lauf gegen unanalysierte Collection-Tracks
        identisch zu einem sauberen Lauf aus — nur langsamer und ohne
        Rekordbox-Beatgrid.
        """
        if not coverage.available or not coverage.degraded:
            return

        lines = [
            f"{coverage.degraded} von {coverage.total} analysierten Tracks "
            f"konnten keine Rekordbox-Daten nutzen und wurden komplett neu "
            f"berechnet (ohne Rekordbox-Beatgrid)."
        ]
        if coverage.without_analysis:
            lines.append("")
            lines.append(
                f"• {coverage.without_analysis} Track(s) stehen in der "
                f"Collection, sind dort aber nicht analysiert. In Rekordbox "
                f"analysieren, Rekordbox schliessen, Lauf wiederholen."
            )
            for name in coverage.examples_without_analysis:
                lines.append(f"    – {name}")
        if coverage.ambiguous:
            lines.append("")
            lines.append(
                f"• {coverage.ambiguous} Track(s) haben mehrdeutige "
                f"Rekordbox-Eintraege (mehrere Records mit widerspruechlichen "
                f"Werten). HPG verwirft solche Daten bewusst, statt zu raten."
            )
            for name in coverage.examples_ambiguous:
                lines.append(f"    – {name}")
        if coverage.not_in_collection:
            lines.append("")
            lines.append(
                f"{coverage.not_in_collection} weitere(r) Track(s) sind gar "
                f"nicht in Rekordbox — das ist erwartet und kein Fehler."
            )

        self.status_bar.set_hint(
            f"Rekordbox: {coverage.degraded}/{coverage.total} ohne Daten",
            "\n".join(lines),
        )

    def analysis_finished(self, playlist, quality_metrics):
        """Audio-Analyse fertig — bereite KI-Veredelung vor, bevor die Playlist generiert wird."""
        # Audio-Analyse fertig -> Fortschritt steht bei 80% (Rest ist KI-Anreicherung)
        self.status_bar.set_progress(80)
        self.library_panel.progress_widget.set_progress(80)

        # AUDIT-FIX T1 (2026-07-24): NUR die Ergebnis-/Fortschritts-Signale
        # trennen. deleteLater() passiert NICHT mehr hier (der Thread laeuft
        # noch), sondern in _cleanup_analysis_worker beim echten QThread.finished.
        if self.worker:
            try:
                self.worker.progress.disconnect()
                self.worker.status_update.disconnect()
                self.worker.analysis_done.disconnect()
            except TypeError:
                pass

        if self.run_state == RunState.CANCELLING:
            self.library_panel.progress_widget.reset_steps()
            self._finish_run(RunState.CANCELLED, "Analysis cancelled.")
            return

        # Leere Playlist? Fehler anzeigen.
        if not playlist:
            self.library_panel.progress_widget.reset_steps()
            self._finish_run(RunState.ERROR, "Analysis returned no results.")
            return

        # Speichere die analysierten Roh-Tracks
        self.analyzed_raw_tracks = playlist

        ap = self.library_panel.advanced_params
        run_settings = self._run_settings or self.library_panel.get_current_settings()
        ai_enabled = run_settings["advanced_params"].get("ai_enabled", False)

        # Die deterministische Playlist steht immer sofort zur Verfuegung.
        self.on_ai_worker_finished(
            ai_completed=False,
            finalize=not ai_enabled,
        )
        if not ai_enabled or self.run_state in {RunState.ERROR, RunState.CANCELLED}:
            return

        # Optionale KI-Daten werden anschliessend als Overlay angereichert.
        self._set_run_state(RunState.AI)
        self.status_bar.show_progress()
        self.library_panel.progress_widget.set_progress(80)
        self.status_bar.set_progress(80)
        provider = run_settings.get("ai_provider") or ap.detected_provider or (
            "LM Studio" if ap.lmstudio_radio.isChecked() else "Ollama"
        )
        model = run_settings.get("ai_model") or ap.model_combo.currentText()
        base_url = run_settings.get("ai_base_url") or ap.detected_base_url
        
        # Der AI-Worker analysiert alle rohen, importierten Tracks, um deren Moods/Subgenres einzusammeln!
        self.ai_worker = AIAnalysisWorker(
            self.analyzed_raw_tracks, provider=provider, model=model, base_url=base_url
        )

        # Phase 5: AI MOODS in Arbeit
        self.library_panel.progress_widget.set_step_status(4, "working")

        current_ai_worker = self.ai_worker
        self.ai_worker.ai_finished.connect(
            lambda path, data, worker=current_ai_worker: self.on_ai_finished(
                path, data, worker
            )
        )
        self.ai_worker.progress.connect(self._on_ai_progress)
        # AUDIT-FIX N6/T10 (2026-07-26): Source-Guard wie bei den anderen
        # Slots — ein verwaister (bereits abgeloester) AI-Worker darf die
        # Statuszeile nicht mehr ueberschreiben.
        self.ai_worker.failed.connect(
            lambda message, worker=current_ai_worker: (
                self.status_bar.set_status(message)
                if worker is self.ai_worker
                else None
            )
        )
        self.ai_worker.finished.connect(
            lambda worker=current_ai_worker: self.on_ai_worker_finished(worker)
        )
        self.ai_worker.start()


    def _berechne_uebergaenge(self, bpm_tolerance, scoring_context):
        """Metriken, Quality und Empfehlungen fuer self.playlist — EIN Scoring-
        Kontext (HPG-001). Liefert (transition_metrics, quality_metrics, plan)."""
        # Lokaler Import wie in analysis_finished: Tests patchen hpg_core.playlist.*
        from hpg_core.playlist import (
            calculate_playlist_quality,
            compute_adjacent_transition_metrics,
            compute_transition_recommendations,
        )

        transition_metrics = compute_adjacent_transition_metrics(
            self.playlist, bpm_tolerance, scoring_context
        )
        self.quality_metrics = calculate_playlist_quality(
            self.playlist,
            bpm_tolerance,
            scoring_context,
            transition_metrics=transition_metrics,
        )
        transition_plan = compute_transition_recommendations(
            self.playlist,
            bpm_tolerance,
            scoring_context=scoring_context,
            transition_metrics=transition_metrics,
        )
        self.playlist_panel.quality_metrics = self.quality_metrics
        self.playlist_panel.transition_recommendations = transition_plan
        return transition_metrics, self.quality_metrics, transition_plan

    def _verteile_uebergaenge(self, transition_plan, bpm_tolerance, scoring_context):
        """Empfehlungen an Tabelle, Mix-Tips, Previews, Timeline, Analytics, Toolbar."""
        self.playlist_panel.set_playlist_data(
            self.playlist,
            self.quality_metrics,
            transition_recommendations=transition_plan,
            bpm_tolerance=bpm_tolerance,
            scoring_context=scoring_context,
        )
        self.mix_tips_panel.set_recommendations(transition_plan)
        # Transition-Audio-Previews rendern (Hintergrund-Worker)
        self.mix_tips_panel.setup_transition_previews(transition_plan)
        self.timeline_panel.set_timeline(self.playlist, transition_plan)
        self.analytics_panel.set_analytics(
            self.quality_metrics, self.playlist, self.current_bpm_tolerance
        )
        overall = self.quality_metrics.get("overall_score", 0)
        self.toolbar.set_quality(overall)

    def _on_candidate_chosen(self, index: int, rang: int) -> None:
        """Klick in der Kandidatentabelle: Wahl je Paar merken, Uebergaenge neu
        berechnen und verteilen (Preview, Timeline, Export folgen)."""
        recs = list(self.playlist_panel.transition_recommendations or [])
        if index < 0 or index >= len(recs):
            return
        rec = recs[index]
        kandidat = next((k for k in (getattr(rec, "kandidaten", []) or []) if int(k.get("rang", 0)) == int(rang)), None)
        if kandidat is None:
            return
        candidate_choices.merke(
            rec.from_track.filePath, rec.to_track.filePath,
            t_out=float(kandidat["t_out"]), t_in=float(kandidat["t_in"]),
            blend_bars=int(kandidat["blend_bars"]),
        )
        self.mix_tips_panel.verwerfe_preview(index)
        _, _, plan = self._berechne_uebergaenge(self.current_bpm_tolerance, self.current_scoring_context)
        self._verteile_uebergaenge(plan, self.current_bpm_tolerance, self.current_scoring_context)
        self.status_bar.set_status(
            f"Kandidat Rang {rang} fuer Uebergang {index + 1}\u2192{index + 2} gewaehlt — "
            "Preview, Timeline und Export folgen."
        )

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
        self.timeline_panel.set_timeline(
            self.playlist, self.playlist_panel.transition_recommendations
        )
        self.analytics_panel.set_analytics(
            self.quality_metrics, self.playlist, self.current_bpm_tolerance
        )

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
                # AUDIT-FIX F2 (2026-07-24): fehlende .xml-Endung ergaenzen —
                # ohne Endung ist die Datei fuer Rekordbox' XML-Import unsichtbar.
                if not file_lower.endswith(".xml"):
                    file_path += ".xml"
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
            report = exporter.export(self.playlist, file_path, playlist_name)

            message = (
                f"M3U8 Playlist exported!\n\n"
                f"Location: {file_path}\n"
                f"Tracks: {report.tracks_written}\n"
                f"Compatible with Rekordbox, Serato, Traktor."
            )
            if report.status == "partial":
                QMessageBox.warning(
                    self,
                    "Export teilweise abgeschlossen",
                    message + "\n\n" + "\n".join(report.errors),
                )
            else:
                QMessageBox.information(self, "Export Successful", message)
        except Exception as e:
            raise Exception(f"M3U8 export failed: {e}")

    def _export_rekordbox_xml(self, file_path: str):
        try:
            exporter = RekordboxXMLExporter()
            playlist_name = f"HPG - {self.current_playlist_mode}"
            report = exporter.export(
                self.playlist, file_path, playlist_name,
                transitions=self.playlist_panel.transition_recommendations,
            )

            message = (
                f"Location: {file_path}\nTracks: {report.tracks_written}\n"
                f"Cues: {report.cues_written}\nBeatgrids: {report.beatgrids_written}"
            )
            if report.status == "partial":
                QMessageBox.warning(
                    self,
                    "Export teilweise abgeschlossen",
                    message + "\n\n" + "\n".join(report.errors),
                )
            else:
                QMessageBox.information(self, "Export Successful", message)
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

        # HPG-001: gleicher Scoring-Kontext wie Generierung/Anzeige
        scoring_context = getattr(self, "current_scoring_context", {})
        transitions_info = "Transition Analysis:\n\n"
        for i in range(len(self.playlist) - 1):
            current = self.playlist[i]
            next_track = self.playlist[i + 1]
            compatibility = calculate_enhanced_compatibility(
                current, next_track, self.current_bpm_tolerance, **scoring_context
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
            self.cancel_analysis()
            self.status_bar.set_status("Neustart nach Abschluss des Abbruchs erneut ausloesen.")
            return
        if self.ai_worker and self.ai_worker.isRunning():
            self.cancel_analysis()
            self.status_bar.set_status("Neustart nach Abschluss des Abbruchs erneut ausloesen.")
            return
        advanced = self.library_panel.advanced_params
        for name in ("_ai_detect_worker", "_test_worker", "_pull_worker"):
            auxiliary = getattr(advanced, name, None)
            if auxiliary and auxiliary.isRunning():
                auxiliary.requestInterruption()
                self.status_bar.set_status(
                    "Neustart nach Abschluss des Abbruchs erneut ausloesen."
                )
                return
        if self._dependency_worker and self._dependency_worker.isRunning():
            self._dependency_worker.requestInterruption()
            self.status_bar.set_status(
                "Neustart nach Abschluss des Abbruchs erneut ausloesen."
            )
            return

        self.playlist = []
        self.quality_metrics = {}
        # AUDIT-FIX F5 (2026-07-26): START OVER raeumt jetzt WIRKLICH auf.
        # Vorher blieben die alte Playlist-Tabelle, Mix-Tips-Karten (inkl.
        # lebender QMediaPlayer + Temp-WAVs), Timeline und Analytics sichtbar
        # stehen — und "PREVIEW TRANSITIONS" arbeitete auf alten Empfehlungen.
        self.analyzed_raw_tracks = []
        self.current_scoring_context = {}
        try:
            self.playlist_panel.set_playlist_data([], {})
        except Exception:
            pass
        try:
            self.mix_tips_panel._cleanup_existing_previews()
            self.mix_tips_panel.set_recommendations([])
        except Exception:
            pass
        try:
            self.timeline_panel.set_timeline([], [])
        except Exception:
            pass
        try:
            self.analytics_panel.set_analytics({}, [])
        except Exception:
            pass
        self._set_run_state(RunState.IDLE)
        # AUDIT-FIX N7 (2026-07-26): Auch Progress-Steps/-Badges und den
        # Playlist-Modus zuruecksetzen — sonst zeigt das Progress-Widget
        # nach START OVER noch den alten Lauf und Exporte wuerden den
        # alten Modus im Namen tragen.
        try:
            self.library_panel.progress_widget.reset_steps()
        except Exception:
            pass
        self.current_playlist_mode = "Harmonic Flow"
        self.toolbar.set_export_enabled(False)
        self.toolbar.quality_badge.hide()
        self.toolbar.set_info("No folder selected")
        self.status_bar.set_status("Ready")
        self.sidebar.set_active(0)
        self.content_stack.setCurrentIndex(0)

    def closeEvent(self, event):
        """M3: Worker sauber beenden beim Schliessen."""
        running_workers = []
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            running_workers.append(self.worker)
        # H4-Fix: auch den AI-Tagging-Worker beenden — sonst Crash/Hang
        # ("QThread destroyed while running") beim App-Close waehrend Tagging
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.request_cancel()
            running_workers.append(self.ai_worker)

        advanced = self.library_panel.advanced_params
        for name in ("_ai_detect_worker", "_test_worker", "_pull_worker"):
            auxiliary = getattr(advanced, name, None)
            if auxiliary and auxiliary.isRunning():
                auxiliary.requestInterruption()
                running_workers.append(auxiliary)

        if self._dependency_worker and self._dependency_worker.isRunning():
            self._dependency_worker.requestInterruption()
            running_workers.append(self._dependency_worker)

        # HPG-004: Preview-Render-Worker in den Close-Lifecycle aufnehmen —
        # request_cancel terminiert dessen Child-Prozess, Thread endet schnell
        render_worker = getattr(self.mix_tips_panel, "_render_worker", None)
        if render_worker and render_worker.isRunning():
            render_worker.request_cancel()
            running_workers.append(render_worker)

        if running_workers:
            # H2-Fix: nicht unbegrenzt pollen. Reagiert ein Worker nicht auf
            # Cancel (z.B. AnalysisWorker mitten in einem langen Librosa-Call,
            # AITestWorker in requests.post), wuerde die App sonst nie schliessen.
            # Nach ~5s (50 x 100ms) die verbliebenen Threads hart terminieren.
            self._close_attempts = getattr(self, "_close_attempts", 0) + 1
            if self._close_attempts > 50:
                logger.warning(
                    "Worker reagieren nicht auf Cancel — erzwinge Terminate beim Schliessen"
                )
                for w in running_workers:
                    try:
                        if w is render_worker:
                            # Erst Child-Prozesse beenden, dann den Qt-Thread.
                            TransitionRenderWorker._terminate_executor(
                                getattr(w, "_executor", None)
                            )
                        w.terminate()
                        w.wait(2000)
                    except Exception:
                        pass
                self.mix_tips_panel._cleanup_existing_previews()
                event.accept()
                return
            self._close_pending = True
            self._set_run_state(RunState.CANCELLING)
            self.status_bar.set_status("Beende laufende Hintergrundarbeit...")
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        # Transition-Render-Worker stoppen und Temp-Dateien loeschen
        self.mix_tips_panel._cleanup_existing_previews()
        event.accept()


if __name__ == "__main__":
    # Logging initialisieren (MUSS vor allen anderen Modulen passieren)
    setup_logging(hpg_config.LOG_LEVEL)

    # Qt-Logging-Handler hinzufügen
    qt_handler = QtLoggingHandler(global_log_emitter)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    qt_handler.setFormatter(formatter)
    logging.getLogger().addHandler(qt_handler)

    # MED-Fix: globales Sicherheitsnetz. Eine unbehandelte Exception in einem
    # Qt-Slot beendet unter PyQt6 sonst still den ganzen Prozess. Stattdessen mit
    # vollem Traceback loggen (via qt_handler auch in der GUI-Logansicht sichtbar),
    # damit der Fehler auffaellt und die App weiterlaeuft statt zu verschwinden.
    import traceback as _traceback

    def _global_excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("hpg").critical(
            "Unbehandelte Exception:\n%s",
            "".join(_traceback.format_exception(exc_type, exc_value, exc_tb)),
        )

    sys.excepthook = _global_excepthook

    # Only clear cache if explicitly requested or on major version changes
    # Automatic clearing on every start is inefficient and can cause locking issues
    # init_cache() already handles version-based clearing safely with file locks
    init_cache()

    if len(sys.argv) >= 3 and sys.argv[1] == "--worker-smoke":
        smoke_paths = sys.argv[2:]
        smoke_tracks = ParallelAnalyzer(
            max_workers=min(len(smoke_paths), 4)
        ).analyze_files(smoke_paths)
        sys.exit(0 if len(smoke_tracks) == len(smoke_paths) else 1)

    app = QApplication(sys.argv)

    # Globaler EventFilter, um Tooltips unendlich lange anzuzeigen (Kundenwunsch)
    tooltip_filter = ToolTipEventFilter(app)
    app.installEventFilter(tooltip_filter)

    # Set application style
    app.setStyle("Fusion")
    apply_dark_theme(app)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())
