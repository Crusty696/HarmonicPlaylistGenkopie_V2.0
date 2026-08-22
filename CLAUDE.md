# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# HPG - Harmonic Playlist Generator (v3.7.2)

## Projekt-Skills zuerst laden

Fuer dieses Repo existieren projekt-lokale Experten-Skills mit dem
verifizierten Ist-Stand. Sie liegen unter `.claude/skills/` (Claude Code)
bzw. `.agents/skills/` (Codex). Bei HPG-Arbeit zuerst `hpg-orientation`
laden, danach den fachlich passenden Skill:

`hpg-orientation`, `hpg-debugging`, `hpg-audio-analysis`,
`hpg-mixpoint-engineering`, `hpg-playlist-scoring`, `hpg-genres`,
`hpg-cache-persistence`, `hpg-parallel-performance`, `hpg-qt-gui`,
`hpg-transition-render`, `hpg-rekordbox`, `hpg-testing-verification`,
`hpg-release-build`, `hpg-audit-optimize`.

Regel: Statusdokumente sind Hypothesen, der Code ist die Wahrheit. Jede
Behauptung aus einem Markdown vor Gebrauch im Code nachpruefen.

## Waechter vor jedem Commit (PFLICHT)

Der Subagent `hpg-waechter` (`.claude/agents/hpg-waechter.md`) prueft an
ZWEI Toren. Er prueft ausschliesslich und schreibt nie Code.

**Tor 1, VOR der Umsetzung**: das Vorhaben — welche Dateien, welche
Funktionen, welche Konstanten, welcher Anlass. Hier faellt auf, was es gar
nicht gibt, was es schon gibt und was ueber den Auftrag hinausgeht. Das ist
das wichtigere Tor: eine Rueckweisung kostet hier Minuten, nach der Umsetzung
kostet sie die Umsetzung.

**Tor 2, VOR dem Commit**: der Diff gegen das, was an Tor 1 vereinbart wurde.

Er faengt genau die Fehlerklassen, die in diesem Projekt an Tests
vorbeigelaufen sind: erfundene Code-Referenzen, Scope-Ausweitung,
unbeauftragte Umbenennungen und GUI-Aenderungen, an den Code angepasste
Tests, verletzte Invarianten (HPG-001, Mixpoint-Regeln, beide Analysepfade,
CACHE_VERSION), unbelegte Behauptungen in Kommentaren und Commit-Texten,
sowie zurueckgestellte und dann vergessene Aufgaben.

Sein Urteil lautet DURCHGEWUNKEN, MIT AUFLAGEN oder ZURUECKGEWIESEN. Bei
ZURUECKGEWIESEN wird nicht committet, sondern nachgebessert. Berichte eines
Subagenten gelten als Hypothese, nicht als Beleg — auch seine.


## Projektarchitektur

```
main.py                    # PyQt6 GUI (5351 Zeilen, Stand 2026-08-21),
                           # QThread-Worker-Muster
hpg_core/                  # Core analysis modules
  models.py                # Track-Dataclass, Camelot-Map, TrackSection
  analysis.py              # Audio-Analyse (librosa): BPM, Key, Energy, Sections
  downbeat.py              # Downbeat- und Phrasen-Anker
  config.py                # Alle konfigurierbaren Konstanten
  genres.py                # Single Source of Truth: 9 kanonische Genres + Drift-Validierung
  caching.py               # SQLite-Cache (WAL), CACHE_VERSION 34
  parallel_analyzer.py     # ProcessPoolExecutor fuer Multi-Core Analyse
  genre_classifier.py      # Genre-Erkennung (regelbasiert, kein ML)
  structure_analyzer.py    # Track-Struktur (Intro/Breakdown/Drop/Outro)
  dj_brain.py              # Genre-spezifische Mix-Logik, Mixpoints
  rekordbox_phrases.py     # PSSI-Phrasen aus ANLZ lesen (reine Funktionen)
  mix_candidates.py        # Mixpunkt-Kandidaten je Track: Gates, Kappung, lokale Messung
  pair_candidates.py       # Paarung/Bewertung der Kandidaten: Paar-Gates, Score, Blenden, Rang (Teil 2)
  candidate_preferences.py # Lader fuer data/candidate_preferences.json (Hoertest-Fit, Teil 3)
  candidate_choices.py     # Kandidaten-Wahl je Paar (%LOCALAPPDATA%\HPG\candidate_choices.json, Teil 4)
  playlist.py              # Playlist-Generierung und Scoring (STRATEGIES)
  transition_features.py   # Paarweise Uebergangs-Vergleiche (Groove/Bass/Timbre/Mood, je [0,1] oder None)
  groove.py                # Beat-synchrone Mustererkennung fuer das Uebergangs-Scoring
  tolerances.py            # Laedt Uebergangs-Toleranzen: Defaults, mitgeliefertes JSON, Override
  data/                    # transition_tolerances.json, candidate_preferences.json (beide {} ausgeliefert)
  mix_analysis.py          # Mix-Analyse: Uebergaenge in DJ-Mixen finden, Kennzahlen (reine Funktionen)
  transition_renderer.py   # Uebergangs-Preview (Crossfade, EQ, Limiter)
  rekordbox_importer.py    # Rekordbox-Datenbank Import (optional)
  ai_engine.py             # Optionales lokales LLM (nur Mood/Subgenre, kein Audio)
  ai_launcher.py           # Erkennung/Start von Ollama bzw. LM Studio
  theme.py                 # Farben und Styles der GUI
  playlist_security.py     # Pfad-Sanitizing und Playlist-Validierung
  resource_limits.py       # Groessen-/Dauer-/Anzahl-Limits
  error_reporter.py        # JSON-Fehlersenke logs/error_report.json
  logging_config.py        # Logging-Setup
  app_metadata.py          # APP_VERSION, MIN_PYTHON (Single Source)
  exporters/               # m3u8, Rekordbox XML Export
tests/                     # pytest (1832 Tests gesammelt, gemessen 2026-08-21 (pytest --collect-only))
tools/                     # Hilfsskripte (Manual Test, Genre Check, Cache Inspection,
                           # kandidaten_messen.py / paar_kandidaten_messen.py / playlist_kandidaten_messen.py
                           # fuer Mixpunkt-Kandidaten)
docs/                      # Dokumentationen, Algorithmus-Erklaerungen, Quick-Start
docs/archive/              # Erledigte Plaene und historische Dokumente
```

Es gibt kein `ui/`-Paket, keinen `GUI/`-Ordner und kein `theme.py` im
Wurzelverzeichnis — die gesamte GUI liegt in `main.py`, das Theme in
`hpg_core/theme.py`.

## Playlist-Strategien

Genau 8, registriert in `hpg_core/playlist.py` (`STRATEGIES`):
Harmonic Flow, Warm-Up, Cool-Down, Peak-Time, Energy Wave, Genre Flow,
Consistent, Context Flow. GUI-Default: Harmonic Flow.

Drei Altnamen bleiben ueber `STRATEGY_ALIASES` gueltig (gespeicherte
Settings, Cache-Metadaten): "Harmonic Flow Enhanced" -> Harmonic Flow,
"Peak-Time Enhanced" -> Peak-Time, "Emotional Journey" -> Context Flow.

## Python-Pfad (WICHTIG!)

- Python 3.12 zwingend, mindestens 3.12.1 (`MIN_PYTHON` in
  `hpg_core/app_metadata.py`). Kein 3.13+ — numba unterstuetzt es nicht.
- Projekt-venv: `.\venv312\Scripts\python.exe` (aktuell Python 3.12.10).

## Tests ausfuehren

```bash
.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
```

`pytest.ini` setzt bereits `-n auto`, Coverage auf `hpg_core` und `main`
sowie `--cov-fail-under=70`. Fuer schnelle Laeufe `--no-cov` anhaengen.

## Coding-Konventionen

- Einrueckung: die des bearbeiteten Files fortsetzen. `main.py`,
  `hpg_core/analysis.py` und `hpg_core/playlist.py` nutzen 4 Leerzeichen,
  neuere Dateien wie `hpg_core/theme.py` und neuere Tests 2. Keine Tabs.
- Kommentare auf **Deutsch**
- UI-Updates NUR im Main-Thread
- Hilfsskripte aus `tools/` muessen den Parent-Pfad zu `sys.path` hinzufuegen

## Geschuetzte Dateien (NICHT editieren)

- `hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`, `*.coverage` —
  Cache-/System-Dateien. Der Laufzeit-Cache liegt ausserhalb des Repos unter
  `%LOCALAPPDATA%\HPG\hpg_cache_v34.db` (ueberschreibbar mit `HPG_CACHE_DIR`
  bzw. `HPG_CACHE_FILE`).

## Analyse-Pipeline

1. **Cache-Lookup** (Rekordbox-Signatur -> Cache-Key) — passiert **vor** der Analyse.
2. **Rekordbox Fast-Path**: Nutzt existierende Metadaten (BPM/Key/Beatgrid).
3. **Vollstaendige Librosa-Analyse**: Volle Audio-Analyse falls Metadaten fehlen.
4. Downbeat -> Phrasen-Anker -> Struktur -> Mixpoints entstehen innerhalb von
   `analyze_track`, nicht in einem spaeteren Schritt.
5. Mixpunkt-Kandidaten (PSSI-Phrasen, Cues, Sektionen, Analyzer) entstehen in
   `analyze_track` nach den Mixpunkten; Cue-Positionsheuristik entfernt
   (Spec 2026-08-21).
6. Paar-Kandidaten (`pair_candidates.rank_pair_candidates`) entstehen beim
   Paaren zweier Tracks (reine Funktionen, Modul-Cache in `playlist`); in der
   App traegt der beste `PairCandidate` den Paar-Score
   (`calculate_enhanced_compatibility`) und den `TransitionPlan` (Mix-Out,
   Mix-In, Blende) — Track-Felder `mix_in_point/mix_out_point` bleiben
   Analyse-Werte. Wahl je Paar: `candidate_choices.json`; App-BPM-Default 2.0.
