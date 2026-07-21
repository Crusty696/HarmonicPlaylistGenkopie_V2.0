---
name: hpg-audit-optimize
description: Use when auditing, reviewing, optimizing or cleaning up the HPG codebase — Code-Review, Performance-Analyse, tote Konstanten, Modul-Duplikate, Batch-Größen, librosa-Speicher, Doku-Widersprüche, Release-/Produktionsreife-Check.
---

# HPG Audit & Optimize

## Overview

Bekannte Baustellen-Landkarte für Audits. Erst hier prüfen, dann neu suchen — spart Doppelarbeit. Stand: 2026-07-16, verifiziert durch 3 unabhängige Explorationen.

## Status 2026-07-17 (Runde 4): Strategien-Merge 11→8 + Pfad-B-Konsolidierung

Strategien 11→8: "Harmonic Flow"/"Peak-Time" nutzen die Enhanced-Implementierungen (Plain-Varianten gelöscht, Half/Double-bewusster BPM-Fallback in Lookahead portiert); "Emotional Journey" ging in "Context Flow" auf (energy_direction-Presets Build Up/Cool Down/Maintain formen die Zielenergie-Kurve). Alte Namen via `STRATEGY_ALIASES` weiter gültig (generate_playlist löst auf). Davor: Mixpoint-Pfad-B-Konsolidierung (research-basiert, nur noch EINE Quantisierungslogik, CACHE_VERSION 15, DJ_BRAIN_ENABLED entfernt — Details docs/plans/2026-07-17-mixpoint-pfad-b-konsolidierung.md). Suite **1188 grün**. Alle großen Konsolidierungs-Punkte aus dem Altlasten-Audit sind damit ERLEDIGT.

## Status 2026-07-17 (Runde 3): genres.py Single Source of Truth

`hpg_core/genres.py` erstellt: alle Genre-Tabellen zentral (GENRE_PROFILES, ID3_GENRE_MAP, GENRE_MIX_PROFILES, GENRE_COMPATIBILITY) + `_validate_genre_tables()` beim Import (Drift-Schutz). dj_brain/genre_classifier re-exportieren, structure_analyzer leitet GENRE_PHRASE_UNITS daraus ab. Neues Genre hinzufügen = NUR in genres.py pflegen; Validierung erzwingt Vollständigkeit. tests/test_genres.py (17 Tests). Suite 1212 grün. Offen: Strategien 11→8, Mixpoint-Pfad-B-Entkernung.

## Status 2026-07-17 (Runde 2): Altlasten-Bereinigung

Altlasten-Audit + autonome Bereinigung (docs/ALTLASTEN_AUDIT_2026-07-17.md): ~876 MB Disk-Altlasten weg (defektes venv/, Root-EXE, Caches v11-v13); Start.bat→venv312-Fix; Versionen einheitlich 3.7.0; toter Code entfernt (profiling.py, MFCC-Similarity-Block, 13 Config-Konstanten, 2 Signale, models.TrackSection-Duplikat); zentrale Helfer in models.py (`seconds_per_bar`, `get_camelot_components`, `effective_bpm_diff` — dj_brain respektiert jetzt BPM_HALF_DOUBLE_ENABLED); GENRE_PHRASE_UNITS aus GENRE_MIX_PROFILES abgeleitet; base_genre_compatibility gelöscht; `resolve_transition_mix_points()` in main.py. Suite **1195 grün** (51 Tests gehörten zu gelöschtem totem Code). Bewusst offen: Strategien 11→8, Mixpoint-Pfad-B-Entkernung, zentrales genres.py (Aufwand L).

## Status 2026-07-17: Doppel-Audit + Komplett-Fix

2-Runden-Audit (6 Agenten) mit Fokus DJ-Fähigkeiten, ALLE Findings gefixt, Suite **1246 grün**, `CACHE_VERSION = 14`. Details: docs/AUDIT_BERICHT_2026-07-17.md. Highlights: Fast-Path-Einrückungsbug (Tracks ohne Key verschwanden still) + Fast-Path-Doppel-Load gefixt; Cue-Override validiert+quantisiert; Beat-Phase-Alignment im Preview-Renderer (neu); BPM-Hard-Gate in calculate_enhanced_compatibility; SSM-Speicher-Bombe (1,3 GB/Track) via MFCC-Dezimierung (MAX_SSM_FRAMES=3000); direktionale Relative-Major/Minor-Scores (A→B 90, B→A 85); harmonic_strictness wirkt jetzt (loose_factor); Rekordbox-XML exportiert HotCues+Sektions-Cues+TEMPO. Bewusst offen: Sprachmix Advice-Texte, Enhanced-%-Anzeige vs. Sort-Score, Techno-Flat-Energy-Labeling, echte Downbeat-Erkennung/LUFS/Key-Confidence (Features).

## Status 2026-07-16: Blocker gefixt

Gefixt (Suite 1433 grün mit venv312/Python 3.12): config.py-SyntaxError, build.bat (script-validator, 3/3 Runs), main.py-ImportError (tote Cache-/Security-/ErrorReporter-Imports entfernt), alle Mixpoint-Bugs (siehe hpg-mixpoint-engineering), installer.iss Cache-Cleanup-Patterns (.db/.db-wal/.db-shm/.lock), BATCH_SIZE worker-aware (`max(worker_count*2, total//4)`, Cap 48), setup_production_logging (Placebo) entfernt.

**Umgebung: NUR `venv312\Scripts\python.exe` nutzen** — altes `venv/` ist Python 3.14 mit kaputtem numpy.

## Zusätzlich gefixt (Runde 2, 2026-07-16, Suite 1428 grün)

security.py gelöscht (Zombie); error_reporter.py neu (utf-8, Rotation MAX_ENTRIES=200, Lock, Singleton `get_error_reporter()`) + verdrahtet in main.py-Exception-Handlern; playlist_security verdrahtet als Security-Gate in AnalysisWorker.run (sanitize + validate + Status-Feedback), sanitize droppt jetzt auch Oversize/Überlänge; 16 tote Config-Konstanten gelöscht, test_config.py neu; `DJ_BRAIN_ENABLED` verdrahtet (analysis.py, beide Pfade); `BARS_PER_PHRASE` verdrahtet (analysis.py); Rekordbox-XML-Export: `get_playlist()` warf auf frischem XML IMMER ValueError → `add_playlist_folder().add_playlist()` (empirisch verifiziert); playlist.py `_sort_genre_flow` Additions-Bug (Scores >1.0) gefixt; `get_genre_compatibility`/`get_mix_profile` case-insensitiver Fallback; CACHE_VERSION 11→12 (Dateinamen jetzt abgeleitet) wegen geänderter Mixpoint-Logik.

## Offene Punkte

| Prio | Problem | Ort |
|------|---------|-----|
| ERLEDIGT | Tote "Intelligent Scoring"-Schicht (7 Module + 10 Test-Dateien) 2026-07-16 GELÖSCHT. Mehrwert-Konzepte (Set-Phasen-Zielenergie, Trend-Fortführung, Genre-Fatigue, Repetition-/Cliff-Penalty) portiert als Strategie **"Context Flow"** (`_sort_context_flow`, playlist.py, vor STRATEGIES). Wichtig: Harmonik-Modell der alten Schicht war musikalisch falsch (bestrafte 8A↔8B) — Context Flow nutzt stattdessen calculate_compatibility als Basis + BPM-Hard-Gate | playlist.py `_sort_context_flow` |
| MITTEL | Mixpoint-Logik-Duplikat konsolidieren: `analyze_structure_and_mix_points` als Fallback entkernen → Pseudo-Sektionen bauen → `calculate_genre_aware_mix_points` mit DEFAULT_MIX_PROFILE. Danach CACHE_VERSION erneut bumpen | analysis.py:545 vs dj_brain.py:263 |
| NIEDRIG | `harmonic_strictness` wirkt nur im Fallback-Zweig, reguläre Match-Kategorien ignorieren ihn | playlist.py:228-287 |
| NIEDRIG | Doku-Sync: PRODUCTION_STATUS.md & Co. beschreiben teils nicht-existente Features | *.md Root |

## Duplikate & tote Strukturen

- `hpg_core/security.py` vs. `hpg_core/playlist_security.py` — fast identische Klone (validate_playlist_security/sanitize_playlist/validate_track_security). playlist_security nutzt config-Konstanten + Typen → behalten; security.py definiert Konstanten lokal neu → Kandidat für Löschung. Erst prüfen welches main.py wirklich importiert.
- Tote Config-Konstanten [config.py:19-37](hpg_core/config.py:19): `MIX_POINT_BUFFER`, `MIN_MIX_DURATION`, `MIX_IN_MAX_PERCENTAGE`, `MIX_OUT_MIN_PERCENTAGE`, `FALLBACK_MIX_IN/OUT`, `RUPTURES_*`, `ONSET_THRESHOLD`, `CENTROID_THRESHOLD` — Code nutzt stattdessen hartkodierte Faktoren (0.15/0.4/0.6/0.85). Aufräumen = entweder Konstanten verdrahten oder löschen.
- `test_isolated_scoring.py` (Root) — leerer Stub (`...`).
- Doppelte Mixpoint-Logik: `analyze_structure_and_mix_points` (analysis.py) vs. `calculate_genre_aware_mix_points` (dj_brain.py) mit divergierenden Konstanten.
- Duplizierte Magic Number `50.0` (Section-Fallback-Energie) in dj_brain.py:341/364/421.

## Performance-Hebel

- Rekordbox Fast-Path [analysis.py:732-752](hpg_core/analysis.py:732): `LIBROSA_FAST_PATH_DURATION=360s`, ~12× schneller — bei Optimierung nicht kaputt machen.
- MFCC-Wiederverwendung aus `classify_genre()` [analysis.py:812](hpg_core/analysis.py:812) — Doppelberechnung vermeiden (M1-Audit-Fix).
- Worker-Scaling [parallel_analyzer.py:20-54](hpg_core/parallel_analyzer.py:20): <5 Dateien → 1 Worker (Windows-Spawn-Overhead), ab 20+ voll.
- Fragwürdig: `BATCH_SIZE = min(24, max(1, total//4))` [parallel_analyzer.py:126](hpg_core/parallel_analyzer.py:126) — bei 4 Tracks Batch=1, zerstört Parallelität. Prüfen/benchmarken.
- Test-Suite: Ziel ~15-20s (docs/PERFORMANCE_OPTIMIZATION.md); `performance_fixtures.py` statt echter Audio-Generierung nutzen.

## Doku-Widersprüche (nicht blind vertrauen)

- PRODUCTION_STATUS.md/IMPROVEMENTS_SUMMARY.md behaupten "produktionsreif" — widerspricht AUDIT_REPORT.md (Build blockiert) und defekten Arbeitskopien.
- PRODUCTION_README.md sagt Python 3.8+, AUDIT_REPORT verlangt 3.10-3.12 (numba <3.13).
- installer.iss:73 löscht `hpg_cache_*.dbm*` (shelve-Ära) — aktueller Cache ist `hpg_cache_v11.db` (SQLite) → Uninstall-Cleanup greift nicht.

## Audit-Vorgehen

1. Blocker-Tabelle oben gegen aktuellen `git status`/Code abgleichen (kann inzwischen gefixt sein).
2. Verhalten IMMER im Code verifizieren, nie aus den .md-Statusdateien übernehmen.
3. Bei Mixpoint-Themen: Skill hpg-mixpoint-engineering laden. Bei Laufzeitfehlern: hpg-debugging.
4. Nach Fixes: Tests mit Python 3.12 (Pfad siehe hpg-debugging), `CACHE_VERSION` erhöhen falls Analyse-Output sich ändert.

## Common Mistakes

- Statusdokumenten glauben statt Code lesen.
- security.py-Duplikat "reparieren" statt konsolidieren.
- Cache-Versionierung vergessen → alte Analysewerte maskieren den Fix.
