---
name: hpg-debugging
description: Use when something in HPG misbehaves at runtime — App startet nicht, Analyse haengt oder bricht ab, BrokenProcessPool, UI-Freeze oder Crash beim zweiten Lauf, Preview fehlt, Werte aendern sich trotz Codeaenderung nicht, ImportError, oder ein Worker meldet still einen Fehler.
---

# HPG Debugging

Einstiegspunkt bei Laufzeitproblemen. Diese Tabelle sagt, **wo** das Problem
sitzt; die Detailregeln stehen im jeweiligen Fach-Skill.

## Symptom → Ursache → Skill

| Symptom | Zuerst pruefen | Skill |
|---|---|---|
| Codeaenderung zeigt keine Wirkung, alte Analysewerte | Cache-Hit. `CACHE_VERSION` (caching.py:39) gebumpt? | `hpg-cache-persistence` |
| Mix-Out mitten im Track, Mixpoint off-grid | Anker/Gitter, Fenster-Artefakt, Notfall-Prozentpfad | `hpg-mixpoint-engineering` |
| Lange Tracks: Outro wirkt erfunden | `LIBROSA_MAX_DURATION` + Tail-Fenster, `outro_covered` | `hpg-audio-analysis` |
| `BrokenProcessPool` im Log | designtes Recovery. Welche Datei ist `[CRASHED/SKIPPED]`? | `hpg-parallel-performance` |
| Analyse haengt, kein Fortschritt | Per-Task-Timeout 60 s vs. Inaktivitaets-Deadline; blockiert ein `shutdown(wait=True)`? | `hpg-parallel-performance` |
| Abbruch wirkt nicht | `cancel_callback` bis in den Pool durchgereicht? | `hpg-parallel-performance` |
| "QThread: Destroyed while thread is still running" | Ergebnis-Signal heisst `finished`; Cleanup am falschen Signal | `hpg-qt-gui` |
| Statuszeile springt zwischen Laeufen | Source-Guard im Slot fehlt | `hpg-qt-gui` |
| UI-Freeze | Datei-I/O oder Rechnung im GUI-Thread | `hpg-qt-gui` |
| Preview fehlt oder ist stumm | `clip_error`-Signal, Render-Timeout, degenerierter Plan (`overlap <= 0`) | `hpg-transition-render` |
| Preview verstimmt / zu leise / uebersteuert | Stretch-Rate, Equal-Power, LUFS-vs-dBRMS | `hpg-transition-render` |
| Alle Tracks Camelot gleich oder Genre "Unknown" | Key-Fallback ohne Sentinel; `"Unknown"` ist truthy | `hpg-audio-analysis`, `hpg-genres` |
| `ValueError: Genre-Tabellen inkonsistent` beim Import | fehlende Cross-Paare — die Fehlermeldung listet sie | `hpg-genres` |
| Rekordbox-Track liefert keine Metadaten | mehrdeutiger Pfad/Basename → bewusst `None` | `hpg-rekordbox` |
| Playlist-Score passt nicht zur Anzeige | `scoring_context` nicht durchgereicht | `hpg-playlist-scoring` |
| numba/numpy-Fehler beim Start | falscher Interpreter — nur `venv312` | `hpg-testing-verification` |
| EXE verhaelt sich anders als der Quellcode | Hidden-Imports/Data-Files im `HPG.spec` | `hpg-release-build` |

## Grundregeln

**Worker werfen nie nach oben.** Sie melden per `status_update` und emittieren
ein leeres Ergebnis (`analysis_done.emit([], {})`). Wer nach einer Exception im
Terminal sucht, sucht falsch — in die Statuszeile und ins Log schauen.

**Logs:**
- `logs/hpg.log` (`logging_config.setup_logging`, Level ueber `config.LOG_LEVEL`)
- `logs/error_report.json` (`error_reporter`, Rotation 200 Eintraege)
- Terminal-Log der Analyse kommt aus `hpg_core.parallel_analyzer`

**Reproduzieren vor Reparieren.** Erst den Fehlfall als Test oder als kurzes
Skript festhalten, dann fixen. Bei Analyse-Themen: Cache vorher isolieren
(`HPG_CACHE_FILE`), sonst debuggt man gegen alte Werte.

**Geschuetzte Dateien:** `hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`,
`track_cache.*` — nie loeschen oder editieren ohne Ankuendigung. Zum Ansehen
`tools/_inspect_cache.py`.

## Common Mistakes

- Recovery-Mechanismen (BrokenProcessPool, `[TIMEOUT]`, `[CRASHED/SKIPPED]`)
  als Bug behandeln.
- Ohne Cache-Isolation debuggen.
- Mit System-Python statt `venv312` reproduzieren.
- Symptom im GUI fixen, obwohl die Ursache in der Analyse liegt.
