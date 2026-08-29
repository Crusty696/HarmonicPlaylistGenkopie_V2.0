"""Zeigt alle gecachten Track-Eintraege mit BPM/Genre (SQLite-Cache, read-only).

Aufruf: python tools/_inspect_cache.py [pfad_zur_cache_db]
Ohne Argument wird der aktuelle Cache-Pfad aus hpg_core.caching genutzt.
"""

import json
import sqlite3
import sys
from pathlib import Path

# UTF-8 erzwingen ohne den Stream zu detachen (robust bei geschlossener Pipe)
try:
  sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
  pass
sys.path.insert(0, str(Path(__file__).parent.parent))

from hpg_core.caching import CACHE_FILE, CACHE_VERSION  # noqa: E402


def main() -> int:
  cache_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(CACHE_FILE)
  if not cache_path.exists():
    print(f"Cache-Datei nicht gefunden: {cache_path}")
    return 1

  # Read-only oeffnen, damit das Tool niemals in den Cache schreibt
  uri = f"file:{cache_path.as_posix()}?mode=ro"
  conn = sqlite3.connect(uri, uri=True)
  try:
    total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    print(f"Cache-Datei: {cache_path} (erwartete Version: {CACHE_VERSION})")
    print(f"Cache-Eintraege gesamt: {total}\n")
    print(f"{'BPM':>7}  {'Genre-Audio':<22}  {'Key':<14}  Dateiname")
    print("-" * 90)

    for key, filepath, data_json in conn.execute(
      "SELECT key, filepath, data FROM cache ORDER BY filepath"
    ):
      # Meta-Zeile (speichert die Cache-Version, kein Track) ueberspringen
      if key == "version":
        continue
      try:
        data = json.loads(data_json) if data_json else {}
      except (TypeError, ValueError):
        print(f"{'?':>7}  {'<defekter JSON-Eintrag>':<22}  {'':<14}  {key[:55]}")
        continue
      bpm = data.get("bpm", "?")
      genre = data.get("detected_genre") or data.get("genre") or "?"
      key_note = data.get("keyNote", "?")
      key_mode = data.get("keyMode", "?")
      fname = data.get("fileName") or Path(filepath or key).name
      print(f"{bpm:>7}  {str(genre):<22}  {key_note} {str(key_mode):<10}  {str(fname)[:55]}")
  finally:
    conn.close()
  return 0


if __name__ == "__main__":
  sys.exit(main())
