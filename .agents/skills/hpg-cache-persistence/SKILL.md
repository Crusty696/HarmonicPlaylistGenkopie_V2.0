---
name: hpg-cache-persistence
description: Use when an HPG code change has no visible effect, or when working on caching.py — CACHE_VERSION, Cache-Key, hpg_cache_v*.db, SQLite/WAL, file_lock, Quarantaene korrupter Zeilen, rekordbox_signature oder Track-Serialisierung.
---

# HPG Cache & Persistence

## Erste Frage bei "mein Fix wirkt nicht"

**Cache-Hit.** `analyze_track` fragt den Cache vor Decode und Audio-Features,
aber nach Pfad-/Ressourcenpruefung, echter Audiodauer und Ermittlung der
Rekordbox-Daten samt Signatur [analysis.py:1659-1702]. Ein geaenderter
Algorithmus liefert weiter die alten Werte, solange Cache-Key und Version
passen.

## CACHE_VERSION — wo und wann

`CACHE_VERSION = 44` in **`hpg_core/caching.py`** — nicht in `config.py`.
Das ist ein haeufiger Fehlgriff.

Die Version steckt im **Dateinamen**: `hpg_cache_v44.db`. Ein Bump erzeugt
also eine neue DB; zusaetzlich filtert der Read auf die Version und raeumt
stale Rows auf.

**Stand 34 (2026-08-21):** fuenf neue Listenfelder auf `Track` —
`phrases`, `cue_points`, `phrase_grid`, `mix_in_candidates`,
`mix_out_candidates` — alle in `TRACK_LIST_FIELDS`. Alte Rows kennen die
Felder nicht und lieferten stillschweigend leere Listen statt der
Kandidaten; erst eine Neuanalyse (durch den Bump erzwungen) fuellt sie.

**Stand 37 (2026-08-25):** persistierter Beatgrid-Pruefstatus, vollstaendige
Rekordbox-PQTZ-Signatur und strenge `None`-Semantik fuer unbekannte lokale
Kick-, Vocal- und Strukturmessungen. Cache 34–36 ist dafuer veraltet.

**Stand 38 (2026-08-26):** BPM-lose Rekordbox-Eintraege behalten nach der
Librosa-Tempoermittlung validierte RB-Keys, Cues und PSSI-Phrasen. Die
Rekordbox-Signatur umfasst auch die daraus abgeleiteten PSSI-Phrasen. Cache 37
darf diesen geaenderten Analysevertrag nicht maskieren.

**Stand 39 (2026-08-26):** Jede Cache-Zeile muss den expliziten Vertrag aus
60 `Track`-Feldern und je 28 Feldern pro Mix-Kandidat vollstaendig erfuellen.
Vor dem Schreiben entsteht ein tiefer, vom lebenden `Track` losgeloester
Snapshot; NaN/Inf werden feldabhaengig als `None`, leerer lokaler Vektor oder
`0.0` nur fuer die beiden Top-Level-Fingerprints normalisiert. Harte
Pflichtmessungen bleiben ungueltig statt stillschweigend repariert zu werden.
Fast-Path und BPM-loser Vollpfad bestimmen Analyse-Phrasenenden mit der echten
endlichen Dateidauer. Der parameterlose Signaturaufruf verwendet weiterhin die
endliche positive Rekordbox-Dauer beziehungsweise `0.0`; diese RB-Phrasen
bleiben Teil der Signatur. Dauerabhaengige Memo-Keys trennen beide Verwendungen.
Cache 38 erfuellt diesen Vertrag nicht sicher.

**Stand 40 (2026-08-26):** Im Rekordbox-Fast-Path ist die framegenaue
Audiodauer autoritativ. Ganzzahlig gekuerzte Rekordbox-Dauern duerfen gueltige
Cues nicht hinter das Trackende verschieben; Cues werden vor Kandidatenbildung
und Persistenz gegen die echte Dateidauer geprueft. Alte v39-Zeilen koennen
abweichende Dauern sowie Cue- und Kandidatenwerte enthalten.

**Stand 41 (2026-08-26):** Die ID3-BPM-Faktorpruefung erkennt auch 3/4- und
4/3-Fehltaggings. Korrekturen sind strikt an ein bekanntes kanonisches
ID3-Genre gebunden; einen genreuebergreifenden Union-Fallback gibt es nicht.
Alte v40-Zeilen koennen falsche BPM, Phrasenraster, Mixpunkte und Kandidaten
enthalten. Artist, Titel und Genre werden fuer AIFF feldweise aus Easy-Tags und
bei fehlenden Werten aus rohen `TPE1`-/`TIT2`-/`TCON`-Frames ergaenzt.

**Stand 42 (2026-08-26):** Gerichtete manuelle Rekordbox-Cues behalten ihre
Provenienz und Prioritaet, duerfen aber weder Track-Mixpunkte noch lokale
Kandidaten oder Paar-Gates ueber Intro-/Outro-Grenzen hinwegsetzen. Alte
v41-Zeilen koennen grenzverletzende Mixpunkte und Kandidaten enthalten.

**Stand 43 (2026-08-27):** Mehrdeutige Audio-Keys werden vollstaendig geleert;
Rekordbox-Beatgrids brauchen fuer Persistenz und Export den verifizierten
Referenzvertrag. PSSI-Grenzen und KI-Metadaten werden strikt validiert.

**Stand 44 (2026-08-27):** Ein nicht erfuellbares Phrasenraster liefert fuer
Mix-In und Mix-Out den expliziten Sentinel statt eines Bar-Fallbacks. Alte
v43-Zeilen koennen semantisch veraltete Fallback-Mixpunkte enthalten.

**Bump ist Pflicht, wenn sich der Analyse-Output aendert:** Mixpoint-Formel,
Quantisierung, Sektions-Labeling, Genre-Regeln, neue/geaenderte Track-Felder,
Downbeat-/Phrase-Schaetzung. Ohne Bump maskieren alte Werte den Fix — und ein
Reviewer sieht gruene Tests bei kaputtem Produktivverhalten.

Die Kommentarhistorie ueber der Konstante dokumentiert jeden Bump mit Grund.
Neue Bumps in diesem Stil ergaenzen.

## Speicherort

```
CACHE_FILE = HPG_CACHE_FILE                       # Env, hoechste Prioritaet
           | HPG_CACHE_DIR/hpg_cache_v44.db       # Env
           | %LOCALAPPDATA%\HPG\hpg_cache_v44.db  # Standard Windows
           | ~/.hpg/hpg_cache_v44.db              # Fallback
LOCK_FILE  = <cache ohne .db> + ".lock"
```

Alles wird **absolut aufgeloest** — relative Pfade erzeugten sonst
CWD-abhaengige Split-Brain-DBs. Fuer Tests: `HPG_CACHE_FILE` setzen, nie die
Produktiv-DB anfassen.

## Cache-Key

`generate_cache_key(file_path, source_signature)` [caching.py:754]:

```
normcase(abspath(normpath(pfad))) - st_size - st_mtime - st_mtime_ns - st_ctime_ns
[ - source-<rekordbox_signature> ]
```

`rekordbox_signature` ist wichtig: Rekordbox-BPM/Key/Cues koennen sich
**ohne** Aenderung der Audiodatei aendern. Deshalb wird die Signatur *vor* dem
Cache-Lookup geholt [analysis.py:1693-1702].

Der Key enthaelt **keinen** Algorithmus-Hash. Deshalb ist der `CACHE_VERSION`-
Bump der einzige Weg, Code-Aenderungen zu invalidieren.

## Robustheit

- SQLite mit WAL, `PRAGMA foreign_keys=ON`, Retry auf BUSY/LOCKED
  (`SQLITE_RETRY_DELAYS`), `file_lock` mit `CACHE_LOCK_TIMEOUT = 15.0`
- `validate_track_dict` prueft alle 60 Pflichtfelder; jeder Mix-Kandidat muss
  alle 28 Vertragsfelder mit gueltigen Typen, Wertebereichen und Listen haben
- `track_to_dict` erstellt ausschliesslich den tief losgeloesten Snapshot
- `cache_track` ruft danach `_normalize_cache_snapshot` fuer die explizit
  tolerierte feldabhaengige NaN/Inf-Semantik und `validate_track_dict` fuer
  alle harten Vertragspruefungen auf; Fehler werden als
  `CacheValidationError` abgewiesen
- ungueltige Zeile beim Lesen -> `_quarantine_cache_row_on_connection`,
  Zeile wird aus `cache` entfernt, Funktion liefert `None` (= Miss,
  Neuanalyse)
- bestaetigt korrupte DB -> `_quarantine_corrupt_cache` [caching.py:628]

## Geschuetzte Dateien

`hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`, `track_cache.*` — **nie
editieren oder loeschen ohne Ankuendigung**. Zum Inspizieren gibt es
`tools/_inspect_cache.py` und `tools/_check_cache.py` (read-only).

## Neues Track-Feld hinzufuegen

1. Feld in `models.Track` mit sinnvollem Sentinel (`-1.0` wenn `0.0` gueltig
   waere)
2. `track_to_dict` / `dict_to_track` [caching.py:676/681] pruefen — sie sind die
   Serialisierungsgrenze
3. `validate_track_dict` erweitern, falls numerisch/endlich
4. `CACHE_VERSION` bumpen + Kommentar
5. Alt-Cache-Verhalten testen: was liefert das Feld fuer Rows ohne den Wert?

## Common Mistakes

- `CACHE_VERSION` in `config.py` suchen.
- Bump vergessen -> "Fix wirkt nicht", stundenlanges Falschdebuggen.
- Produktiv-DB im Test benutzen statt `HPG_CACHE_FILE`.
- Sentinel `0.0` waehlen fuer ein Feld, bei dem `0.0` ein gueltiger Wert ist.
