# Altlasten-Audit HPG V2.0 — Duplikate, toter Code, Datei-Leichen

**Datum:** 2026-07-17
**Methode:** 3 parallele Audit-Agenten (Toter Code per Symbol-Referenzanalyse, Duplikat-Logik, Datei-/Repo-Inventar) + manuelle Verifikation.

## ABGEARBEITET (gleicher Tag, Suite danach 1195 grün)

- **Disk (~876 MB):** venv/ (defekt), Root-EXE, Caches v11-v13, .coverage, Debug-/Log-Artefakte, __pycache__, .pytest_cache, leeres scripts/ — gelöscht.
- **Konfig:** Start.bat → venv312; Versionen einheitlich 3.7.0 (version_info.txt, build_installer.bat, build.bat, QUICK_START); CLAUDE.md-Struktur aktualisiert; PRODUCTION_STATUS.md auf Stand 2026-07-17/Cache v14.
- **Doku:** INTELLIGENTES_SCORING_SYSTEM.md gelöscht; PLAN/TODO/ACT.md + plans/ + docs/plans/ nach docs/archive/ verschoben.
- **Toter Code entfernt:** profiling.py (ganzes Modul) + Test; MFCC-Similarity-Block in playlist.py (4 Funktionen) + Test; 13 tote Config-Konstanten (9× *_BPM_RANGE, GENRE_ID3_OVERRIDE, AI_ENABLED, LOG_TO_FILE/CONSOLE, CACHE_LOCK_TIMEOUT); 2 tote Signale im TransitionRenderWorker; ungenutzte models.TrackSection-Duplikat-Dataclass. `benchmark_algorithms` bewusst behalten (getestet, nützlich).
- **Konsolidiert:** `seconds_per_bar`/`get_camelot_components`/`effective_bpm_diff` zentral in models.py (dj_brain-Kopie ignorierte vorher das BPM_HALF_DOUBLE_ENABLED-Flag — gefixt); hartkodierte `* 4` durch METER ersetzt (dj_brain, playlist ×2, main); GENRE_PHRASE_UNITS wird aus GENRE_MIX_PROFILES abgeleitet (Doppelpflege weg); base_genre_compatibility gelöscht — einzige Quelle ist die DJ-Brain-Matrix; Mixpoint-Resolution in main.py als `resolve_transition_mix_points()` extrahiert (vorher 3× kopiert).
- **Nachtrag (gleicher Tag): zentrales `hpg_core/genres.py` umgesetzt.** Alle Genre-Tabellen (GENRE_PROFILES, ID3_GENRE_MAP, GENRE_MIX_PROFILES, GENRE_COMPATIBILITY) leben jetzt in einer Datei mit `_validate_genre_tables()` beim Import — Inkonsistenzen (vergessenes Genre, falsches ID3-Ziel, ungültige phrase_unit) schlagen sofort als Fehler auf statt still zu driften. Alte Module re-exportieren (keine API-Brüche), structure_analyzer leitet GENRE_PHRASE_UNITS direkt aus genres.py ab. 17 neue Tests (tests/test_genres.py) inkl. Drift-Erkennungs-Negativtests. Suite 1212 grün.
- **Bewusst NICHT umgesetzt** (UX-/Risiko-Entscheidung, dokumentiert): Strategien-Zusammenlegung 11→8 (entfernt sichtbare Auswahloptionen), Mixpoint-Pfad-B-Entkernung (viele direkte Tests, eigener Umbau-Plan), Track-Felder brightness/danceability/etc. behalten (Zukunfts-Features), Tabellen-Update-Helper (Kosmetik).

---

## Executive Summary

Git-Index ist sauber (141 Dateien, .gitignore deckt alles ab). Auf der Platte liegen aber **~875 MB Altlasten** (defektes venv, alter Build, alte Caches). Im Code: **~15 tote/nur-test-genutzte Funktionen, 13 tote Config-Konstanten, 2 tote Signale, ein komplett unverdrahtetes Modul (profiling.py)** sowie erhebliche **Duplikat-Logik** (15+ Kopien der `seconds_per_bar`-Berechnung, 6 parallele Genre-Wissensquellen, doppelte TrackSection-Dataclass). Kritischster Einzelfund: **`Start.bat` startet die App mit dem defekten Python-3.14-venv.**

---

## 1. Datei-/DB-Altlasten (Disk, alle gitignored)

### Sofort löschbar (~876 MB)

| Pfad | Größe | Begründung |
|---|---|---|
| `venv/` | **698 MB** | Python 3.14 — defekt (numba braucht <3.13). Verbindlich ist `venv312/` |
| `HarmonicPlaylistGenerator.exe` (Root) | **167 MB** | Build-Output, via `build.bat` regenerierbar |
| `hpg_cache_v11.db` / `v12` / `v13` | 8,8 MB | Alte Cache-Versionen; gültig ist nur `hpg_cache_v14.db` |
| `.coverage`, `hpg_debug_err.txt`, `logs/hpg.log`, `__pycache__/`, `.pytest_cache/`, `tools/desktop.ini` | ~1,1 MB | Regenerierbare Laufzeit-/Test-Artefakte |

Optional archivieren: `installer_output/HPG_v3.7.0_Setup.exe` (167 MB, Release-Artefakt).

### Konfig-Bugs (AKTUALISIEREN)

- **`Start.bat:8-10` nutzt `venv\Scripts\python.exe` — das DEFEKTE Py3.14-venv.** Muss auf `venv312\` zeigen. App startet darüber gar nicht.
- **Versions-Chaos:** `installer.iss` = 3.7.0, `version_info.txt` = 3.6.0, `build_installer.bat`-Kommentar = 3.6.0 → vereinheitlichen.
- `scripts/` ist **komplett leer**, wird aber in `CLAUDE.md` als „Build- und Utility-Skripte" beschrieben → Ordner löschen + CLAUDE.md korrigieren.

### Doku-Altlasten

| Datei | Empfehlung |
|---|---|
| `docs/INTELLIGENTES_SCORING_SYSTEM.md` (20 KB) | **LÖSCHEN** — beschreibt die am 2026-07-16 gelöschte Scoring-Schicht |
| `PRODUCTION_STATUS.md` | **AKTUALISIEREN** — nennt Cache-Version 12 (aktuell 14), Stand überholt |
| Root `PLAN.md` / `TODO.md` / `ACT.md` + `plans/advanced-audio-analysis.md` | **ARCHIVIEREN** — 4 Dateien zum selben, längst umgesetzten Plan |
| `plans/2026-05-19-llm-integration.md`, `plans/feat-transition-audio-preview.md`, `plans/research-audio-enhancement.md`, `docs/plans/2026-02-28-rekordbox-coverage.md`, `docs/superpowers/plans+specs (Mix-Point-Guard)` | **ARCHIVIEREN** — alle erledigt/implementiert |
| `docs/OPTIMIZATION_SUMMARY.md` + `docs/PERFORMANCE_OPTIMIZATION.md` | **PRÜFEN** — thematisch überlappend (beide 2026-05-19) |

Sauber: keine Backup-/`.orig`-Leichen, keine shelve-Reste, keine toten Test-Stubs, `requirements.txt`-Split ist gewollt, `tools/*.py` importieren alle existierende Module.

---

## 2. Toter Code (Symbol-Analyse)

### Komplett unverdrahtet

- **`hpg_core/profiling.py` — GANZES MODUL nur von Tests genutzt** (profile_function, TimerContext, AnalysisProfiler, track_memory, get_memory_usage_mb). Nirgends in der Pipeline verdrahtet.
- **Similarity/Clustering-Block in playlist.py** (find_similar_tracks, cluster_tracks_by_similarity, get_cluster_summary, mfcc_distance, benchmark_algorithms) — nur Tests; main.py nutzt stattdessen `dj_brain._calculate_texture_similarity`.

### 13 tote Config-Konstanten (config.py)

- **9× `*_BPM_RANGE`** (PSYTRANCE bis MINIMAL) — totes Duplikat der BPM-Ranges in `genre_classifier.GENRE_PROFILES`.
- `GENRE_ID3_OVERRIDE`, `AI_ENABLED`, `LOG_TO_FILE`, `LOG_TO_CONSOLE`, `CACHE_LOCK_TIMEOUT` — werden nirgends gelesen (Logging/Caching nutzen eigene Defaults bzw. Hardcodes).

### Tote Signale (main.py)

- `TransitionRenderWorker.all_done` — emittiert, nie connected.
- `TransitionRenderWorker.progress` — emittiert, nie connected (verwechselbar mit AnalysisWorker.progress).

### Nur-Tests-Symbole (Feature-Entscheidung: verdrahten oder mitsamt Tests löschen)

`transition_renderer.make_temp_output_path`, `logging_config.set_module_level` / `get_debug_logger`, `base_exporter._sanitize_filename`, `exporters/__init__.py`-Re-Exports.

### Track-Dataclass: write-only-Felder

| Feld | Status |
|---|---|
| `avg_mids`, `avg_highs`, `spectral_flatness` | **TOT** — nie gelesen, nicht mal in Tests |
| `mfcc_fingerprint` | nur vom toten Similarity-Block gelesen |
| `brightness`, `danceability`, `vocal_instrumental`, `genre_confidence`, `genre_source`, `phrase_unit`, `bass_intensity` | **NUR-TESTS/TOOLS** — in Live-App write-only (vermutlich für künftige Features vorgehalten) |
| ~~`ai_metadata`~~ | **KORREKTUR: LEBENDIG** — Agent-Fehlbefund; wird via `getattr` in `calculate_enhanced_compatibility` + `_apply_ai_bonus` gelesen (playlist.py:152/326) |

Lebendig: avg_bass, percussive_ratio, timbre_fingerprint, mix_*-Felder, energy, bpm, camelotCode, detected_genre, sections, duration.

---

## 3. Duplikat-Logik (Sync-Risiken)

### HOCH: `seconds_per_bar` — 15+ Kopien, keine zentrale Funktion

`60.0/bpm * METER` dupliziert in analysis.py (×4), dj_brain.py (×4, davon **Zeile 301 mit hartkodierter `4` statt METER**), structure_analyzer.py (×3), playlist.py (×2, hartkodierte `4`), transition_renderer.py, main.py:3193 (hartkodierte `4`).
→ Empfehlung: `seconds_per_bar(bpm)`-Helper in config/models, Aufwand M.

### HOCH: 6 parallele Genre-Wissensquellen

`GENRE_PROFILES` + `ID3_GENRE_MAP` (genre_classifier) / `GENRE_MIX_PROFILES` + `GENRE_COMPATIBILITY` (dj_brain) / `GENRE_PHRASE_UNITS` (structure_analyzer) / `base_genre_compatibility` (playlist).
- `phrase_unit` **doppelt gepflegt** (dj_brain-Profil UND structure_analyzer-Map) — aktuell konsistent, keine Kopplung.
- `base_genre_compatibility` vs. `GENRE_COMPATIBILITY` mit **abweichenden Werten** für dieselben Paare (Psytrance/Trance 0.6 vs. 0.75).
- Genre-Namen als Magic Strings in ~40 frozenset-Vergleichen.
→ Empfehlung: zentrales `genres.py` (eine Struktur pro Genre), `base_genre_compatibility` löschen. Aufwand L.

### MITTEL

- **Mixpoint-Pfad A vs. B**: Pfad B (`analyze_structure_and_mix_points`) ist bei `DJ_BRAIN_ENABLED=True` + Sektionen faktisch toter Fallback; Rest-Divergenz in Clamp-Logik (0.4/0.6-Prozente vs. sektionsbasiert). Bekanntes Konsolidierungs-Thema, Aufwand M.
- **Half/Double-Erkennung 3×**: playlist.effective_bpm_diff (respektiert `BPM_HALF_DOUBLE_ENABLED`) vs. dj_brain._effective_bpm_diff (**ignoriert das Flag**) vs. transition_renderer (eigene 4-%-Logik). Flag-Inkonsistenz. Aufwand S.
- **Doppelte `TrackSection`-Dataclass**: models.py (11 Felder, wird nie instanziiert) vs. structure_analyzer.py (6 Felder, wird genutzt). Aufwand S.
- **Energie-Skalen inkonsistent**: `Track.energy` (fixe 0.4-Skala) vs. `Section.avg_energy` (track-kalibriert seit heute) — gleiche Zahl, andere Bedeutung. Plus fast identische RMS-Threshold-Logik doppelt (analysis vs. structure_analyzer-Fallback).
- **Mixpoint-Resolution 3× kopiert in main.py** (Zeilen ~510/615/2515): identisches `dj.adjusted_* >= 0.0 else track.mix_*`-Muster → Helper extrahieren, Aufwand S.
- **Tabellen-Update-Logik 3×** in main.py (_populate_table / _update_table_after_reorder / AI-Handler) mit identischen Format-Strings.
- **Sortier-Strategien 11 Stück**, Konsolidierungs-Kandidaten: Peak-Time ↔ Peak-Time Enhanced (fast identische Ergebnisse), Harmonic Flow ↔ Enhanced (~90 % Code-Overlap), Context Flow ↔ Emotional Journey (zwei unabhängige Phasen-Engines). 11 → 7-8 möglich, Aufwand M.

### NIEDRIG

- Camelot-Parsing 2× (identisches Regex in playlist + dj_brain).
- Kompatibilitäts-Skalen 0-100 vs. 0-1: Layer, kein echtes Duplikat — seit heute beide mit BPM-Hard-Gate.
- Magic Numbers neben existierenden Konstanten: hartkodierte `0.2/0.8` neben `INTRO_MAX_PERCENTAGE/OUTRO_MIN_PERCENTAGE`, `mean*0.4` neben `RMS_THRESHOLD`, `120.0`-Literale neben `DEFAULT_BPM`.

---

## 4. Empfohlene Aufräum-Reihenfolge

1. **Quick Wins (risikofrei):** venv/ + Root-EXE + alte Caches löschen (~876 MB); `Start.bat` auf venv312 fixen; Versionsnummern auf 3.7.0 vereinheitlichen; leeres `scripts/` + CLAUDE.md-Referenz; `INTELLIGENTES_SCORING_SYSTEM.md` löschen; PRODUCTION_STATUS.md aktualisieren.
2. **Toter Code (mit Tests löschen oder verdrahten):** profiling.py, Similarity-Block, 13 Config-Konstanten, 2 tote Signale, tote Track-Felder (avg_mids/avg_highs/spectral_flatness). Achtung: Track-Felder-Entfernung → CACHE_VERSION bumpen.
3. **Konsolidierung (eigene Session, mit Tests):** `seconds_per_bar`-Helper + METER-Literale (S-M); Half/Double + Camelot-Parsing zentralisieren (S); TrackSection vereinheitlichen (S); Genre-Wissensquellen → `genres.py` (L); Mixpoint-Pfad B entkernen (M); Strategien 11→8 (M).
4. **Pläne/Doku archivieren:** erledigte plans/-Dateien + Root-Trio in `docs/archive/` verschieben.

---

*3 Audit-Agenten + manuelle Verifikation (ai_metadata-Fehlbefund korrigiert). Nichts verändert.*
