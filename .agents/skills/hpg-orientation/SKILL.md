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
main.AnalysisWorker.run              [main.py:489]
  1 os.walk + Realpath-Containment (Symlink-Ausbruch verworfen)
    + Deckel SECURITY_MAX_PLAYLIST_SIZE (1000)
  2 ParallelAnalyzer.analyze_files   [parallel_analyzer.py]
      pro Datei: analysis.analyze_track  [analysis.py:1282]
        a Groessen-/Dauerlimit (500 MB / 7200 s)
        b Rekordbox-Signatur -> Cache-Key -> SQLite-Lookup   << CACHE HIER
        c Miss -> Fast-Path (Rekordbox-BPM/Key, librosa 360 s)
                  oder Voll-Path (librosa 600 s + 180 s Tail)
        d Downbeat -> Phrasen-Anker -> Struktur -> Mixpoints
        e Cue-Override (Rekordbox) -> cachen
  3 apply_resource_limits (Ressourcenfilter)
  4 analysis_done -> MainWindow.analysis_finished  [main.py:4446]
  5 playlist.generate_playlist (8 Strategien)
  6 playlist.compute_transition_recommendations -> TransitionPlan
  7 optional AIAnalysisWorker (LLM, nur Mood/Subgenre, kein Audio)
  8 TransitionRenderWorker -> Preview-WAV / Exporter
```

## Wo liegt was

| Thema | Datei | Einstieg |
|---|---|---|
| GUI, alle Worker, Panels | `main.py` (4868 Z.) | `MainWindow.init_ui` :3992 |
| Track-Datenmodell, Camelot, Anker | `hpg_core/models.py` | `class Track` :128 |
| Audio-Analyse | `hpg_core/analysis.py` | `analyze_track` :1282 |
| Mixpoints, DJ-Empfehlungen | `hpg_core/dj_brain.py` | :106, :433, :627 |
| Strategien + Scoring | `hpg_core/playlist.py` | `STRATEGIES` :1864 |
| Genre-Tabellen (SSoT) | `hpg_core/genres.py` | `CANONICAL_GENRES` :21 |
| Cache | `hpg_core/caching.py` | `CACHE_VERSION` :39 |
| Preview-DSP | `hpg_core/transition_renderer.py` | `render_transition_clip` :114 |
| Rekordbox-Import | `hpg_core/rekordbox_importer.py` | :59 |
| Export | `hpg_core/exporters/` | m3u8, Rekordbox-XML |

**GUI-Navigation** (`SidebarWidget.NAV_ITEMS`, main.py:1817): LIBRARY ·
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

## Doku ist NICHT die Wahrheit

Dieses Repo hat massive Doku-Drift. Diese Aussagen sind **falsch**, immer im
Code nachsehen:

- `CLAUDE.md` / `AGENTS.md`: "main.py ~1600 Zeilen" — real 4868.
- `docs/QUICK_START.txt`: nennt 10 Strategien mit alten Namen ("Emotional
  Journey", "Surprise me"), eine Datei `ui/main_window.py` (existiert nicht)
  und "961 Tests". Real: 8 Strategien, kein `ui/`-Paket.
- `AUDIT_SKILL-TEAM_2026-07-24.md` und `FULLSTACK_AUDIT_*` sind **Snapshots**;
  ihre Befunde sind grossteils gefixt. Nicht als offene Punkte behandeln.

Regel: Statusdokumente liefern Hypothesen, der Code liefert Fakten.
