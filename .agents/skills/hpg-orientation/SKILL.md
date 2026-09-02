---
name: hpg-orientation
description: Use when starting any work on the HPG / Harmonic Playlist Generator repo and the module layout, data flow, user purpose or "which file owns this" is not yet clear — also when a doc, README or CLAUDE.md statement needs to be checked against the code.
---

# HPG Orientation

## Was die App ist

**Harmonic Playlist Generator v3.7.2** — Windows-Desktop-Tool (PyQt6) fuer DJs
elektronischer Musik. Kein Auto-DJ, kein Player: ein **Set-Vorbereitungs-Tool**.

Nutzer waehlt einen Musikordner. Die App analysiert jede Datei, sortiert die
Tracks zu einem Set, erklaert jeden Uebergang und rendert ihn zum Anhoeren,
und exportiert das Ergebnis in die DJ-Software.

Zielgenres (aus `genres.CANONICAL_GENRES`): Psytrance, Tech House, Progressive,
Melodic Techno, Techno, Deep House, Trance, Drum & Bass, Minimal.

## Der echte Datenfluss

Cache-Lookup passiert **vor** der Analyse, nicht danach. Mixpoints entstehen
**innerhalb** von `analyze_track`, nicht in einem spaeteren Schritt.

```
main.AnalysisWorker.run              [main.py]
  1 os.walk + Realpath-Containment (Symlink-Ausbruch verworfen)
    + Deckel SECURITY_MAX_PLAYLIST_SIZE (1000)
  2 ParallelAnalyzer.analyze_files   [hpg_core/parallel_analyzer.py]
      pro Datei: analysis.analyze_track  [hpg_core/analysis.py]
        a Groessen-/Dauerlimit (500 MB / 7200 s)
        b Rekordbox-Signatur -> Cache-Key -> SQLite-Lookup   << CACHE HIER
        c Miss -> Fast-Path (Rekordbox-BPM/Key, librosa 360 s)
                  oder Voll-Path (librosa 600 s + 180 s Tail)
        d Downbeat -> Phrasen-Anker -> Struktur -> Mixpoints
        e Cue-Override (nur benannte Cues, Rekordbox)
        f Mixpunkt-Kandidaten (PSSI-Phrasen, Cues, Sektionen, Analyzer)
          -> cachen
  3 apply_resource_limits (Ressourcenfilter)
  4 analysis_done -> MainWindow.analysis_finished  [main.py]
  5 playlist.generate_playlist (8 Strategien)
  6 playlist.compute_transition_recommendations -> TransitionPlan
  7 optional AIAnalysisWorker (LLM, nur Mood/Subgenre, kein Audio)
  8 TransitionRenderWorker -> Preview-WAV / Exporter
```

## Wo liegt was

| Thema | Datei | Einstieg |
|---|---|---|
| GUI, alle Worker, Panels | `main.py` | `MainWindow.init_ui` |
| Track-Datenmodell, Camelot, Anker | `hpg_core/models.py` | `class Track` |
| Audio-Analyse | `hpg_core/analysis.py` | `analyze_track` |
| Mixpoints, DJ-Empfehlungen | `hpg_core/dj_brain.py` | `calculate_genre_aware_mix_points`, `generate_dj_recommendation`, `calculate_paired_mix_points` |
| Strategien + Scoring | `hpg_core/playlist.py` | `STRATEGIES` |
| Genre-Tabellen (SSoT) | `hpg_core/genres.py` | `CANONICAL_GENRES` |
| Cache | `hpg_core/caching.py` | `CACHE_VERSION` |
| PSSI-Phrasen | `hpg_core/rekordbox_phrases.py` | `phrases_from_anlz` |
| Mixpunkt-Kandidaten | `hpg_core/mix_candidates.py` | `build_track_candidates` |
| Preview-DSP | `hpg_core/transition_renderer.py` | `render_transition_clip` |
| Rekordbox-Import | `hpg_core/rekordbox_importer.py` | `class RekordboxImporter` |
| Export | `hpg_core/exporters/` | m3u8, Rekordbox-XML |

**GUI-Navigation** (`SidebarWidget.NAV_ITEMS` [main.py]): LIBRARY ·
PLAYLIST · MIX TIPS · TIMELINE · QUALITY, Umschalten per Ctrl+1..5.

## Welcher Skill fuer welche Frage

| Aufgabe | Skill |
|---|---|
| librosa, Features, Coverage, LUFS, Key | `hpg-audio-analysis` |
| Mix-In/Out, Phrasen, Anker, Quantisierung | `hpg-mixpoint-engineering` |
| Strategien, Camelot-Scores, Timeline | `hpg-playlist-scoring` |
| Genre hinzufuegen/aendern | `hpg-genres` |
| "Fix wirkt nicht", Cache, Sentinels | `hpg-cache-persistence` |
| Worker, Timeouts, Analyse-Speed | `hpg-parallel-performance` |
| QThread, Signale, Panels, Theme | `hpg-qt-gui` |
| Crossfade, EQ, Preview klingt falsch | `hpg-transition-render` |
| Rekordbox-DB, ANLZ, Cues, XML | `hpg-rekordbox` |
| Tests starten, Baseline, Gates | `hpg-testing-verification` |
| EXE, Installer, Versions-Bump, CI | `hpg-release-build` |
| Audit, tote/doppelte Strukturen | `hpg-audit-optimize` |
| Voll-/Delta-/Release-Audit mit Evidenzpflicht | `hpg-veritas` |

## Doku ist NICHT die Wahrheit

Dieses Repo hat massive Doku-Drift. Diese Aussagen sind **falsch**, immer im
Code nachsehen:

- `CLAUDE.md` / `AGENTS.md` enthielten frueher stark veraltete Groessenangaben.
  Zeilenzahlen, Testanzahl und Coverage stehen bewusst nirgends mehr in den
  Skills — sie veralten mit jedem Commit. Vor Gebrauch selbst messen.
- `docs/QUICK_START.txt` nannte frueher 10 Strategien, `ui/main_window.py` und
  eine laengst ueberholte Testzahl. Korrigiert: 8 Strategien, kein `ui/`-Paket.
- `AUDIT_SKILL-TEAM_2026-07-24.md` und `FULLSTACK_AUDIT_*` sind **Snapshots**;
  ihre Befunde sind grossteils gefixt. Nicht als offene Punkte behandeln.

Regel: Statusdokumente liefern Hypothesen, der Code liefert Fakten.
