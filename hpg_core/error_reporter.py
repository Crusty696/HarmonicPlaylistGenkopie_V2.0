"""
ErrorReporter - Persistenter JSON-Fehler-Sink fuer die GUI.

Sammelt Fehler aus Workern/Handlern in logs/error_report.json,
begrenzt auf die letzten MAX_ENTRIES Eintraege (Rotation).
Thread-safe via Lock (Worker-Threads schreiben parallel).
"""
import json
import logging
import os
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path

from . import logging_config

logger = logging.getLogger(__name__)

# Rotation: nur die letzten N Fehler behalten, Datei waechst nicht unbegrenzt
MAX_ENTRIES = 200


class ErrorReporter:
    def __init__(self, log_dir=None):
        resolved_log_dir = logging_config.LOG_DIR if log_dir is None else Path(log_dir)
        self.error_log_file = resolved_log_dir / "error_report.json"
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
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    encoding='utf-8',
                    dir=self.error_log_file.parent,
                    prefix=f".{self.error_log_file.name}.",
                    suffix='.tmp',
                    delete=False,
                ) as f:
                    temp_path = Path(f.name)
                    json.dump(errors, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, self.error_log_file)
            except OSError as e:
                logger.error(f"Fehlerprotokoll nicht schreibbar: {e}")
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass

    def get_recent_errors(self, count=10):
        """Gibt die letzten Fehler zurueck (neueste zuletzt)."""
        if count <= 0:
            return []
        with self._lock:
            return self._read_errors()[-count:]

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
