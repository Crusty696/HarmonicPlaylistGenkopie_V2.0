"""
Zentrales Logging-Setup fuer HPG.

Verwendung in jedem Modul:
    import logging
    logger = logging.getLogger(__name__)

Einmalig beim App-Start:
    from hpg_core.logging_config import setup_logging
    setup_logging()          # INFO-Level, Konsole + Datei
    setup_logging("DEBUG")   # Volle Debug-Ausgabe
"""

import logging
import logging.handlers
import sys
from pathlib import Path

# === Konfiguration ===
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "hpg.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB pro Datei
LOG_BACKUP_COUNT = 3  # 3 Backup-Dateien behalten
DEFAULT_LEVEL = "INFO"

# Module mit eigenem Log-Level (fuer gezielte Diagnose)
MODULE_LEVELS = {
  "hpg_core.analysis": "INFO",
  "hpg_core.caching": "INFO",
  "hpg_core.parallel_analyzer": "INFO",
  "hpg_core.genre_classifier": "INFO",
  "hpg_core.structure_analyzer": "INFO",
  "hpg_core.dj_brain": "INFO",
  "hpg_core.playlist": "INFO",
  "hpg_core.rekordbox_importer": "INFO",
  "hpg_core.exporters": "INFO",
}


class _CompactFormatter(logging.Formatter):
  """Kompaktes Format: [LEVEL] modul: nachricht"""

  LEVEL_TAGS = {
    "DEBUG": "[DEBUG]",
    "INFO": "[INFO]",
    "WARNING": "[WARN]",
    "ERROR": "[ERROR]",
    "CRITICAL": "[CRIT]",
  }

  def format(self, record):
    # Kurzname: hpg_core.analysis -> analysis
    short_name = record.name
    if short_name.startswith("hpg_core."):
      short_name = short_name[9:]
    elif short_name.startswith("hpg_core.exporters."):
      short_name = short_name[9:]

    tag = self.LEVEL_TAGS.get(record.levelname, f"[{record.levelname}]")
    msg = record.getMessage()

    if record.exc_info and not record.exc_text:
      record.exc_text = self.formatException(record.exc_info)

    result = f"{tag} {short_name}: {msg}"
    if record.exc_text:
      result += f"\n{record.exc_text}"
    return result


class _FileFormatter(logging.Formatter):
  """Ausfuehrliches Format fuer Logdatei mit Zeitstempel."""

  def __init__(self):
    super().__init__(
      fmt="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
    )


def setup_logging(level=None, log_to_file=True, log_to_console=True):
  """
  Initialisiert das Logging-System.

  Args:
      level: Log-Level als String ("DEBUG", "INFO", "WARNING", "ERROR")
             oder None fuer DEFAULT_LEVEL
      log_to_file: Ob in Datei geloggt wird (RotatingFileHandler)
      log_to_console: Ob auf stderr geloggt wird
  """
  level = level or DEFAULT_LEVEL
  numeric_level = getattr(logging, level.upper(), logging.INFO)

  # Root-Logger konfigurieren
  root = logging.getLogger()
  root.setLevel(logging.DEBUG)  # Niedrigstes Level, Handler filtern

  # Alte Handler entfernen (bei wiederholtem Aufruf)
  for handler in root.handlers[:]:
    root.removeHandler(handler)
    handler.close()

  # Konsolen-Handler (stderr, damit stdout frei bleibt)
  if log_to_console:
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(numeric_level)
    console.setFormatter(_CompactFormatter())
    root.addHandler(console)

  # Datei-Handler (mit Rotation)
  if log_to_file:
    LOG_DIR.mkdir(exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
      LOG_FILE,
      maxBytes=LOG_MAX_BYTES,
      backupCount=LOG_BACKUP_COUNT,
      encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Alles in die Datei
    file_handler.setFormatter(_FileFormatter())
    root.addHandler(file_handler)

  # Modul-spezifische Levels setzen
  for module_name, module_level in MODULE_LEVELS.items():
    mod_logger = logging.getLogger(module_name)
    mod_logger.setLevel(getattr(logging, module_level.upper(), numeric_level))

  # Externe Bibliotheken ruhigstellen
  logging.getLogger("librosa").setLevel(logging.WARNING)
  logging.getLogger("numba").setLevel(logging.WARNING)
  logging.getLogger("audioread").setLevel(logging.WARNING)
  logging.getLogger("matplotlib").setLevel(logging.WARNING)
  logging.getLogger("PIL").setLevel(logging.WARNING)

  logger = logging.getLogger(__name__)
  logger.info(f"Logging initialisiert (Level: {level})")
  if log_to_file:
    logger.debug(f"Log-Datei: {LOG_FILE}")

  return root


def set_module_level(module_name, level):
  """
  Aendert den Log-Level eines einzelnen Moduls zur Laufzeit.

  Beispiel:
      set_module_level("hpg_core.analysis", "DEBUG")
  """
  mod_logger = logging.getLogger(module_name)
  mod_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_debug_logger(name):
  """
  Shortcut fuer Module: Erstellt Logger und gibt ihn zurueck.

  Verwendung:
      from hpg_core.logging_config import get_debug_logger
      logger = get_debug_logger(__name__)
  """
  return logging.getLogger(name)
