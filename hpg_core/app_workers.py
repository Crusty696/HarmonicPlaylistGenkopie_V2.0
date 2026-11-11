"""Qt-Worker ohne Abhängigkeit von Fenstern oder Panels."""
from __future__ import annotations

import importlib
import logging
import os
import tempfile
import threading
import time
from collections import Counter
from copy import deepcopy
from PyQt6.QtCore import QThread, pyqtSignal
from . import config as hpg_config
from .caching import VALID_ANALYSIS_MODES
from .parallel_analyzer import ParallelAnalyzer
from .resource_limits import sanitize_playlist as apply_resource_limits
from .error_reporter import get_error_reporter
from .run_state import AnalysisIssue
from .transition_renderer import BeatSyncError, TransitionClipSpec, _render_clip_subprocess_wrapper

logger = logging.getLogger(__name__)

class AIAnalysisWorker(QThread):
    """Worker thread for running AI analysis in the background."""
    ai_finished = pyqtSignal(str, dict)  # (track_path, metadata)
    progress = pyqtSignal(int, int)      # (current_track_index, total_tracks)
    failed = pyqtSignal(str)

    def __init__(self, playlist: list, provider: str = None, model: str = None,
                 base_url: str = None, parent=None, cache_policy: str = "reuse"):
        super().__init__(parent)
        if cache_policy not in {"reuse", "fresh"}:
            raise ValueError("cache_policy muss 'reuse' oder 'fresh' sein")
        self.cache_policy = cache_policy
        self.playlist = playlist
        self.provider = provider
        self.model = model
        self.base_url = base_url  # Voller Endpoint vom ai_launcher (Port dynamisch)
        self._should_cancel = False
        self.failure_reason = ""
        self._request_model = model

    def request_cancel(self):
        self._should_cancel = True
        self.requestInterruption()

    def _ensure_ready(self):
        """
        Stellt sicher dass der Provider laeuft und ein Modell gewaehlt ist.
        Laeuft bereits im Worker-Thread → blockierend erlaubt, blockiert UI nicht.
        LM Studio wird auch bei vorhandenem Endpoint vor jeder Analyse geprueft.
        Inventarerkennung allein bestaetigt weder GPU-Konfiguration noch Eignung.
        """
        try:
            from hpg_core import ai_launcher
            if not (self.base_url and self.provider and self.model):
                if self.provider:
                    if self.provider not in {"LM Studio", "Ollama"}:
                        raise ValueError("Unbekannter KI-Provider")
                    status = ai_launcher.prepare_provider(
                        self.provider, preferred_model=self.model,
                        cancel_check=self.isInterruptionRequested)
                else:
                    status = ai_launcher.detect_and_start(
                        preferred_model=self.model,
                        cancel_check=self.isInterruptionRequested)
                if not status or not status.running or not status.active_model:
                    return False
                if self.provider and status.name != self.provider:
                    raise ValueError("Ausgewählter KI-Provider nicht verfügbar; kein automatischer Wechsel")
                if self.model and status.active_model != self.model:
                    raise ValueError("Ausgewähltes Modell nicht verfügbar; kein automatischer Wechsel")
                if status and status.running:
                    self.base_url = status.base_url
                    self.provider = status.name
                    if status.active_model:
                        self.model = status.active_model
            if not (self.base_url and self.provider and self.model):
                return False
            self._request_model = self.model
            if self.provider == "LM Studio":
                from hpg_core.lmstudio_runtime import prepare_gpu_model
                self._request_model = prepare_gpu_model(
                    self.model, self.base_url,
                    cancel_check=self.isInterruptionRequested,
                )
        except InterruptedError:
            raise
        except Exception as exc:
            logging.getLogger("hpg_core.ai_engine").error(
                "AI provider setup failed: %s", exc
            )
            self.failure_reason = str(exc)
            return False
        return bool(self.base_url and self.provider and self.model)

    def _fail(self, reason):
        self.failure_reason = reason
        self.failed.emit(reason)

    def run(self):
        import logging
        import os
        logger = logging.getLogger("hpg_core.ai_engine")
        if self._should_cancel or self.isInterruptionRequested():
            return
        try:
            ready = self._ensure_ready()
        except InterruptedError:
            logger.info("AI Mood Tagging cancelled during provider setup.")
            return
        if self._should_cancel or self.isInterruptionRequested():
            return
        if not ready:
            if self._should_cancel or self.isInterruptionRequested():
                logger.info("AI Mood Tagging cancelled during provider setup.")
                return
            self._fail(self.failure_reason or "Kein einsatzbereiter KI-Provider oder kein Modell verfuegbar.")
            self.progress.emit(len(self.playlist), len(self.playlist))
            return
        logger.info(f"Starting AI Mood Tagging using {self.provider} (Model: {self.model})...")
        total_tracks = len(self.playlist)
        cancelled = False
        failed = False
        for i, track in enumerate(self.playlist):
            if self._should_cancel or self.isInterruptionRequested():
                logger.info("AI Mood Tagging cancelled by user.")
                cancelled = True
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
                from hpg_core.caching import generate_cache_key, merge_cached_ai_metadata
                # Antwort an den Quellstand vor der Anfrage binden, niemals an
                # eine inzwischen ausgetauschte Datei mit demselben Pfad.
                cache_key = generate_cache_key(
                    track.filePath, getattr(track, "rekordbox_signature", ""),
                )
                logger.info(f"[{i+1}/{total_tracks}] AI analyzing track: '{filename}'...")
                ai_data = fetch_ai_analysis(
                    track,
                    provider=self.provider,
                    model=self.model,
                    url=self.base_url,
                    cancel_check=self.isInterruptionRequested,
                    **({"request_model": self._request_model} if self.provider == "LM Studio" else {}),
                )
                if self._should_cancel or self.isInterruptionRequested():
                    logger.info("AI Mood Tagging cancelled by user.")
                    cancelled = True
                    break
                if ai_data:
                    # Cache-I/O kann auf einen extern gehaltenen SQLite-Lock bis
                    # zum Timeout warten. Es bleibt deshalb im AI-Worker und darf
                    # niemals den Qt-GUI-Thread blockieren.
                    try:
                        if not cache_key:
                            raise RuntimeError("kein sicherer Cache-Key")
                        if self.cache_policy == "fresh":
                            # Frische Analyse schreibt absichtlich keinen Track-Cache.
                            # Vor der Publikation trotzdem die Quelle erneut binden.
                            persisted = generate_cache_key(
                                track.filePath, getattr(track, "rekordbox_signature", ""),
                            ) == cache_key
                        else:
                            persisted = merge_cached_ai_metadata(
                                cache_key, track.filePath, ai_data,
                                expected_source_key=cache_key,
                            )
                    except Exception as cache_exc:
                        reason = (
                            f"KI-Metadaten fuer '{filename}' konnten nicht "
                            f"persistiert werden: {cache_exc}"
                        )
                        logger.error(reason)
                        self._fail(reason)
                        failed = True
                        break
                    if persisted is not True:
                        current_source_key = generate_cache_key(
                            track.filePath, getattr(track, "rekordbox_signature", ""),
                        )
                        if current_source_key != cache_key:
                            reason = (
                                "Quelldatei geändert; KI-Antwort verworfen. "
                                "Track erneut analysieren."
                            )
                        else:
                            reason = (
                                f"KI-Metadaten fuer '{filename}' konnten nicht "
                                "bestaetigt persistiert werden."
                            )
                        logger.error(reason)
                        self._fail(reason)
                        failed = True
                        break

                    # Der bestaetigte Cache-Commit ist die atomare Grenze. Auch
                    # ein waehrend des DB-Wartens eingetroffener Cancel darf das
                    # bereits persistierte Ergebnis nicht im Arbeitsspeicher
                    # beziehungsweise in der GUI unsichtbar lassen.
                    track.ai_metadata = ai_data
                    self.ai_finished.emit(track.filePath, ai_data)
                    if self._should_cancel or self.isInterruptionRequested():
                        logger.info("AI Mood Tagging cancelled after persisted result.")
                        cancelled = True
                        break
                else:
                    reason = (
                        f"KI-Verarbeitung bei '{filename}' gestoppt: Provider- oder "
                        "Schemafehler. Bereits erzeugte Ergebnisse bleiben erhalten."
                    )
                    logger.warning(reason)
                    self._fail(reason)
                    failed = True
                    break
            except InterruptedError:
                logger.info("AI Mood Tagging cancelled by user.")
                cancelled = True
                break
            except Exception as e:
                reason = f"KI-Verarbeitung gestoppt: {e}"
                logger.error(reason, exc_info=True)
                self._fail(reason)
                failed = True
                break
        if not cancelled and not failed:
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
            if self.preferred:
                status = ai_launcher.prepare_provider(
                    self.preferred, preferred_model=self.preferred_model,
                    cancel_check=self.isInterruptionRequested,
                )
            else:
                status = ai_launcher.detect_and_start(
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
        if self.isInterruptionRequested():
            return
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
                {"role": "system", "content": hpg_config.AI_SYSTEM_PROMPT},
                {"role": "user", "content": "Track: Technischer Metadaten-Test. Genre: Techno. BPM: 130. Energy: 60. Duration: 300s. Intro 0-32s, Hauptteil 32-268s, Outro 268-300s. Liefere das definierte Metadatenschema. Kein Audio wurde uebertragen."}
            ]
        }

        try:
            from hpg_core.ai_engine import AI_JSON_SCHEMA, decode_ai_response, validate_ai_completion
            from hpg_core.models import Track
            qualification_key = None
            if self.provider == "LM Studio":
                from hpg_core.lmstudio_runtime import prepare_gpu_model, instance_qualification_key
                payload["model"] = prepare_gpu_model(
                    self.model, url, cancel_check=self.isInterruptionRequested,
                    explicit_retest=True)
                qualification_key = instance_qualification_key(payload["model"])
            payload.update(temperature=0, seed=0, max_tokens=hpg_config.AI_MAX_TOKENS,
                           response_format={"type": "json_schema", "json_schema": AI_JSON_SCHEMA})
            # timeout=(connect timeout, read timeout). Modell laden kann dauern, daher 30s.
            if self.isInterruptionRequested():
                return
            resp = requests.post(url, json=payload, timeout=(3.0, 30.0))
            resp.raise_for_status()
            latency = time.time() - start_time

            # HPG-003: bei Abbruch (App-Close) kein Signal mehr emittieren
            if self.isInterruptionRequested():
                return
            resp_json = decode_ai_response(
                resp, self.provider, self.model, request_model=payload["model"],
                url=url, qualification_key=qualification_key)
            validate_ai_completion(
                resp_json, Track(filePath="hpg-schema-probe", fileName="Schema-Test", duration=300.),
                self.provider, self.model, request_model=payload["model"], url=url,
                qualification_key=qualification_key)
            self.test_finished.emit(True, "Metadatenschema gültig. Kein Nachweis für Audioverstehen oder musikalische Qualität.", self.model, latency)
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
        self.provider = "Ollama"
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

    _create_analyzer = staticmethod(ParallelAnalyzer)
    _filter_tracks = staticmethod(apply_resource_limits)
    _error_reporter = staticmethod(get_error_reporter)

    progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    phase_changed = pyqtSignal(int, str)  # step_index, state ("inactive", "working", "completed")
    # AUDIT-FIX T1 (2026-07-24): eigenes Ergebnis-Signal, das NICHT das
    # eingebaute QThread.finished ueberschreibt. Vorher gab es kein Signal mehr,
    # das das echte Thread-Ende meldete -> deleteLater() konnte aus dem selbst
    # emittierten Signal heraus einen noch laufenden QThread zerstoeren
    # ("QThread: Destroyed while thread is still running").
    analysis_done = pyqtSignal(list, dict)  # playlist, quality_metrics
    analysis_issues = pyqtSignal(object)  # tuple[AnalysisIssue, ...]
    rekordbox_coverage = pyqtSignal(object)  # RekordboxCoverage

    def __init__(self, folder_path, *, cache_policy="reuse"):
        super().__init__()
        if type(cache_policy) is not str or cache_policy not in {"reuse", "fresh"}:
            raise ValueError("cache_policy muss 'reuse' oder 'fresh' sein")
        self.folder_path = folder_path
        self.cache_policy = cache_policy
        self.supported_formats = hpg_config.SUPPORTED_AUDIO_EXTENSIONS
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
            self.status_update.emit("Audiodateien werden gesucht …")
            logger.info(f"Scanning directory: {self.folder_path}")
            logger.info("Audiodateien werden gesucht …")

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
                    f"Hinweis: Suche auf {hpg_config.SECURITY_MAX_PLAYLIST_SIZE} Titel begrenzt."
                )

            total_files = len(audio_files)
            if total_files == 0:
                self.phase_changed.emit(0, "inactive")
                self.status_update.emit(
                    "Keine Audiodateien im ausgewählten Ordner gefunden."
                )
                logger.error(f"No compatible audio files ({', '.join(self.supported_formats)}) found in selected folder!")
                self.analysis_done.emit([], {})
                return

            self.phase_changed.emit(0, "completed")
            self.phase_changed.emit(1, "working")
            self.status_update.emit(
                f"{total_files} Audiodateien gefunden. Analyse startet …"
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
                    self._create_analyzer()
                )  # Auto-detect optimal core count (smart scaling)
                analyzed_tracks = analyzer.analyze_files(
                    audio_files,
                    progress_callback=progress_callback,
                    cancel_callback=lambda: self._should_cancel,
                    cache_policy=self.cache_policy,
                )
            except InterruptedError:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit("Analyse abgebrochen.")
                self.analysis_done.emit([], {})
                return
            except Exception as e:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit(f"Fehler bei der Analyse: {str(e)}")
                self._error_reporter().log_error(
                    "analysis", str(e), {"folder": self.folder_path}
                )
                self.analysis_done.emit([], {})
                return

            if self._should_cancel:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit("Analyse abgebrochen.")
                self.analysis_done.emit([], {})
                return

            invalid_analysis_tracks = [
                track
                for track in analyzed_tracks
                if getattr(track, "analysis_mode", "") not in VALID_ANALYSIS_MODES
            ]
            issues = [
                AnalysisIssue(
                    (
                        "rekordbox_decode_degraded"
                        if getattr(track, "analysis_mode", "")
                        == "rekordbox_degraded"
                        else "invalid_analysis_mode"
                    ),
                    str(getattr(track, "filePath", "") or ""),
                    (
                        "Audio-Decode fehlgeschlagen; Track wurde sicher ausgeschlossen."
                        if getattr(track, "analysis_mode", "")
                        == "rekordbox_degraded"
                        else (
                            "Ungueltiger Analysemodus "
                            f"{getattr(track, 'analysis_mode', '')!r}; "
                            "Track wurde sicher ausgeschlossen."
                        )
                    ),
                )
                for track in invalid_analysis_tracks
            ]
            if issues:
                for issue in issues:
                    logger.error(
                        "Track wegen ungueltigem Analyseergebnis ausgeschlossen: %s",
                        issue.path,
                    )
                analyzed_tracks = [
                    track
                    for track in analyzed_tracks
                    if getattr(track, "analysis_mode", "") in VALID_ANALYSIS_MODES
                ]
            # Ressourcenfilter: defekte Eintraege und Tracks ueber den Limits
            # (Dateigroesse/Dauer) entfernen, Playlist-Groesse deckeln
            tracks_before_resource_filter = list(analyzed_tracks)
            pre_count = len(analyzed_tracks)
            analyzed_tracks = self._filter_tracks(analyzed_tracks)
            retained_by_identity = Counter(id(track) for track in analyzed_tracks)
            resource_excluded = []
            for track in tracks_before_resource_filter:
                track_identity = id(track)
                if retained_by_identity[track_identity]:
                    retained_by_identity[track_identity] -= 1
                else:
                    resource_excluded.append(track)
            issues.extend(
                AnalysisIssue(
                    "resource_limit_excluded",
                    str(getattr(track, "filePath", "") or ""),
                    "Track wurde durch den Ressourcenfilter ausgeschlossen "
                    "(defekt oder ueber Limits).",
                )
                for track in resource_excluded
            )
            if len(analyzed_tracks) < pre_count:
                removed = pre_count - len(analyzed_tracks)
                self.status_update.emit(
                    f"Hinweis: {removed} Titel durch Ressourcenfilter entfernt (defekt oder über Grenzwerten)."
                )
                logger.warning(f"Ressourcenfilter entfernte {removed} von {pre_count} Tracks.")

            try:
                self.analysis_issues.emit(tuple(issues))
            except Exception as exc:
                # Der Diagnosekanal darf den sicherheitsrelevanten Filter nie
                # rueckgaengig machen oder den restlichen Lauf abbrechen.
                logger.error("Analysebefunde konnten nicht gemeldet werden: %s", exc)

            if not analyzed_tracks:
                self.phase_changed.emit(1, "inactive")
                self.status_update.emit("Keine Titel erfolgreich analysiert. Fehlerhinweise prüfen.")
                self.analysis_done.emit([], {})
                return

            logger.info(f"Feature extraction complete: {len(analyzed_tracks)} tracks successfully analyzed.")
            self._report_rekordbox_coverage(analyzed_tracks)
            self.phase_changed.emit(1, "completed")
            self.status_update.emit(
                f"Audioanalyse für {len(analyzed_tracks)} Titel abgeschlossen. Playlist wird vorbereitet …"
            )
            self.analysis_done.emit(analyzed_tracks, {})

        except InterruptedError:
            self.status_update.emit("Analyse abgebrochen.")
            self.analysis_done.emit([], {})
        except Exception as e:
            self.status_update.emit(f"Analysefehler: {str(e)}")
            self.analysis_done.emit([], {})


class PlaylistGenerationWorker(QThread):
    """Erzeugt Playlist und TransitionResult ohne Zugriff auf GUI-Widgets."""

    generation_done = pyqtSignal(object)
    generation_failed = pyqtSignal(str)

    def __init__(
        self,
        tracks,
        *,
        mode,
        bpm_tolerance,
        advanced_params,
        scoring_context,
        candidate_choice_snapshot,
        ai_failure="",
        finalize=True,
        parent=None,
    ):
        super().__init__(parent)
        self.tracks = tuple(tracks)
        self.mode = str(mode)
        self.bpm_tolerance = float(bpm_tolerance)
        self.advanced_params = deepcopy(advanced_params)
        self.scoring_context = deepcopy(scoring_context)
        self.candidate_choice_snapshot = deepcopy(candidate_choice_snapshot)
        self.ai_failure = str(ai_failure or "")
        self.finalize_run = bool(finalize)

    def request_cancel(self):
        self.requestInterruption()

    def run(self):
        if self.isInterruptionRequested():
            return
        try:
            from hpg_core.playlist import generate_playlist_result

            tracks_snapshot = deepcopy(self.tracks)
            if self.isInterruptionRequested():
                return
            result = generate_playlist_result(
                list(tracks_snapshot),
                mode=self.mode,
                bpm_tolerance=self.bpm_tolerance,
                advanced_params=self.advanced_params,
                scoring_context=self.scoring_context,
                candidate_choice_snapshot=self.candidate_choice_snapshot,
                cancel_check=self.isInterruptionRequested,
            )
        except InterruptedError:
            return
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.generation_failed.emit(str(exc))
            return
        if not self.isInterruptionRequested():
            self.generation_done.emit(result)


class TransitionRenderWorker(QThread):
    _error_reporter = staticmethod(get_error_reporter)

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
                if plan is None:
                    self.clip_error.emit(i, "Nicht geplant: kein ausführbarer Übergangsplan")
                    continue
                spec = TransitionClipSpec.from_plan(
                    plan, transition.from_track, transition.to_track
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
                except BeatSyncError as sync_err:
                    if self._should_cancel:
                        break
                    logger.info("Preview wegen Beat-Synchronitaet abgelehnt: %s", sync_err)
                    self._error_reporter().log_error(
                        "transition_render_rejected", str(sync_err), {"clip": i}
                    )
                    self.clip_error.emit(i, f"Vorschau abgelehnt: {sync_err}")
                except (BrokenProcessPool, RuntimeError) as pool_err:
                    if self._should_cancel:
                        # Terminate durch request_cancel — kein echter Absturz
                        break
                    logger.error(f"Render-Prozess abgestuerzt bei Clip {i}: {pool_err}")
                    self._error_reporter().log_error(
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
                    self._error_reporter().log_error(
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
