"""
ErrorReporter - Persistenter JSON-Fehler-Sink fuer die GUI.

Sammelt Fehler aus Workern/Handlern in logs/error_report.json,
begrenzt auf die letzten MAX_ENTRIES Eintraege (Rotation).
Thread-safe via Lock (Worker-Threads schreiben parallel).
"""
import json
import logging
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Rotation: nur die letzten N Fehler behalten, Datei waechst nicht unbegrenzt
MAX_ENTRIES = 200


class ErrorReporter:
    def __init__(self, log_dir="logs"):
        self.error_log_file = Path(log_dir) / "error_report.json"
        self._lock = threading.Lock()
        try:
            self.error_log_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Konnte Log-Verzeichnis nicht anlegen: {e}")

    def log_error(self, error_type, message, details=None):
        """Loggt einen Fehler mit Zeitstempel; Stack-Trace nur wenn gerade eine Exception aktiv ist."""
        error_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': error_type,
            'message': message,
            'details': details or {},
            'stack_trace': traceback.format_exc() if sys.exc_info()[0] is not None else None,
        }

        with self._lock:
            errors = self._read_errors()
            errors.append(error_entry)
            errors = errors[-MAX_ENTRIES:]
            try:
                with open(self.error_log_file, 'w', encoding='utf-8') as f:
                    json.dump(errors, f, indent=2, ensure_ascii=False)
            except OSError as e:
                logger.error(f"Fehlerprotokoll nicht schreibbar: {e}")

    def get_recent_errors(self, count=10):
        """Gibt die letzten Fehler zurueck (neueste zuletzt)."""
        with self._lock:
            return self._read_errors()[-count:]

    def clear_errors(self):
        """Loescht alle Fehlermeldungen."""
        with self._lock:
            try:
                with open(self.error_log_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                logger.info("Fehlerprotokoll geloescht")
            except OSError as e:
                logger.error(f"Fehler beim Loeschen des Fehlerprotokolls: {e}")

    def _read_errors(self):
        """Liest bestehende Eintraege; korrupte/fehlende Datei ergibt leere Liste."""
        try:
            with open(self.error_log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []


# Prozessweiter Singleton -- Worker und GUI teilen denselben Reporter
_instance = None
_instance_lock = threading.Lock()


def get_error_reporter():
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ErrorReporter()
    return _instance
