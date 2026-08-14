---
name: hpg-cache-persistence
description: Use when an HPG code change has no visible effect, or when working on caching.py — CACHE_VERSION, Cache-Key, hpg_cache_v*.db, SQLite/WAL, file_lock, Quarantaene korrupter Zeilen, rekordbox_signature oder Track-Serialisierung.
---

# HPG Cache & Persistence

## Erste Frage bei "mein Fix wirkt nicht"

**Cache-Hit.** `analyze_track` fragt den Cache, *bevor* irgendetwas gerechnet
wird [analysis.py:1322]. Ein geaenderter Algorithmus liefert weiter die alten
Werte, solange die Datei unveraendert ist.

## CACHE_VERSION — wo und wann

`CACHE_VERSION = 28` in **`hpg_core/caching.py`** — nicht in `config.py`.
Das ist ein haeufiger Fehlgriff.

Die Version steckt im **Dateinamen**: `hpg_cache_v28.db`. Ein Bump erzeugt
also eine neue DB; zusaetzlich filtert der Read auf die Version und raeumt
stale Rows auf.

**Bump ist Pflicht, wenn sich der Analyse-Output aendert:** Mixpoint-Formel,
Quantisierung, Sektions-Labeling, Genre-Regeln, neue/geaenderte Track-Felder,
Downbeat-/Phrase-Schaetzung. Ohne Bump maskieren alte Werte den Fix — und ein
Reviewer sieht gruene Tests bei kaputtem Produktivverhalten.

Die Kommentarhistorie ueber der Konstante dokumentiert jeden Bump mit Grund.
Neue Bumps in diesem Stil ergaenzen.

## Speicherort

```
CACHE_FILE = HPG_CACHE_FILE                       # Env, hoechste Prioritaet
           | HPG_CACHE_DIR/hpg_cache_v28.db       # Env
           | %LOCALAPPDATA%\HPG\hpg_cache_v28.db  # Standard Windows
           | ~/.hpg/hpg_cache_v28.db              # Fallback
LOCK_FILE  = <cache ohne .db> + ".lock"
```

Alles wird **absolut aufgeloest** — relative Pfade erzeugten sonst
CWD-abhaengige Split-Brain-DBs. Fuer Tests: `HPG_CACHE_FILE` setzen, nie die
Produktiv-DB anfassen.

## Cache-Key

`generate_cache_key(file_path, source_signature)` [caching.py:363]:

```
normcase(abspath(normpath(pfad))) - st_size - st_mtime - st_mtime_ns - st_ctime_ns
[ - source-<rekordbox_signature> ]
```

`rekordbox_signature` ist wichtig: Rekordbox-BPM/Key/Cues koennen sich
**ohne** Aenderung der Audiodatei aendern. Deshalb wird die Signatur *vor* dem
Cache-Lookup geholt [analysis.py:1313].

Der Key enthaelt **keinen** Algorithmus-Hash. Deshalb ist der `CACHE_VERSION`-
Bump der einzige Weg, Code-Aenderungen zu invalidieren.

## Robustheit

- SQLite mit WAL, `PRAGMA foreign_keys=ON`, Retry auf BUSY/LOCKED
  (`SQLITE_RETRY_DELAYS`), `file_lock` mit `CACHE_LOCK_TIMEOUT = 15.0`
- `validate_track_dict` [:112] + `_validate_finite_values` — NaN/Inf und
  Typfehler fliegen als `CacheValidationError`
- ungueltige Zeile beim Lesen -> `_quarantine_cache_row_on_connection`,
  Zeile wird aus `cache` entfernt, Funktion liefert `None` (= Miss,
  Neuanalyse)
- bestaetigt korrupte DB -> `_quarantine_corrupt_cache` [:231]

## Geschuetzte Dateien

`hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`, `track_cache.*` — **nie
editieren oder loeschen ohne Ankuendigung**. Zum Inspizieren gibt es
`tools/_inspect_cache.py` und `tools/_check_cache.py` (read-only).

## Neues Track-Feld hinzufuegen

1. Feld in `models.Track` mit sinnvollem Sentinel (`-1.0` wenn `0.0` gueltig
   waere)
2. `track_to_dict` / `dict_to_track` [:265/:290] pruefen — sie sind die
   Serialisierungsgrenze
3. `validate_track_dict` erweitern, falls numerisch/endlich
4. `CACHE_VERSION` bumpen + Kommentar
5. Alt-Cache-Verhalten testen: was liefert das Feld fuer Rows ohne den Wert?

## Common Mistakes

- `CACHE_VERSION` in `config.py` suchen.
- Bump vergessen -> "Fix wirkt nicht", stundenlanges Falschdebuggen.
- Produktiv-DB im Test benutzen statt `HPG_CACHE_FILE`.
- Sentinel `0.0` waehlen fuer ein Feld, bei dem `0.0` ein gueltiger Wert ist.
