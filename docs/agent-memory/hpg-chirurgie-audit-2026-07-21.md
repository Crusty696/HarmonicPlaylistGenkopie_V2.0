---
name: hpg-chirurgie-audit-2026-07-21
description: "Chirurgisches 6-Agenten-Zeilen-Audit 2026-07-21 — 4 HIGH + 5 MED + 9 LOW echte Bugs gefixt, Suite 1322 grün"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7a768d28-20fe-43d3-9919-b330a425f734
---

Am 2026-07-21 tiefes chirurgisches Audit des GESAMTEN Codes: 6 parallele Audit-Agenten (je Subsystem, jede Zeile), jeder Fund selbst im Code verifiziert vor Fix. Commit feb7127. Suite 1322 grün, Coverage-Gate bestanden, E2E- + Render-Smoke grün.

**4 HIGH (echte Korrektheits-Bugs, vom vorherigen Audit übersehen):**
- `playlist._sort_peak_time`: `_prepare_track_metrics` liefert Input-Reihenfolge; combined_score wurde berechnet aber NIE zum Sortieren genutzt → Peak-Strategie ordnete nach Ladereihenfolge statt Energie. Fix: `sorted(scored_tracks, key=lambda x: x[1])` vor zip mit waveform_positions.
- `main._cleanup_existing_previews`: `disconnect(self._on_clip_ready)` schlug fehl (Signal an Lambda gebunden) → TypeError verschluckt → `finished→_on_preview_worker_finished` blieb verbunden → feuerte auf inzwischen NEUEM _render_worker → deleteLater auf laufendem QThread → Crash. Fix: alle Signale generisch `.disconnect()`.
- `analysis.py` (~1173): Sektionen jenseits geladenem y (Fast-Path 360s, Track-Outro >360s) bekamen harte 0.0-Freq → `dj_brain out_sec_data.get('avg_bass', track_a.avg_bass)` nutzte 0.0 statt Track-Fallback am Mix-Out. Fix: Track-Averages VOR Loop, else-Zweig erbt sie.
- `rekordbox_importer` (~166): pyrekordbox `DjmdContent.FolderPath` IST der volle Pfad (Docstring verifiziert), nicht der Ordner. `os.path.join(FolderPath, FileName)` → Doppel-Name → Exact-Path-Lookup immer tot, Basename-Fallback-Kollision → falsche BPM/Key/Cues bei gleichnamigen Dateien. Fix: FolderPath direkt. Test-Fixture FakeContent auf reale Semantik umgestellt.

**5 MEDIUM:** predict_transition_type ohne scoring_context (HPG-001-Restleck); genres._validate_genre_tables Cross-Paar-Loophole (Selbst-Paare machten Set-Check trivial); caching._quarantine_cache_row Connection-Leak (`with sqlite3` schließt nicht); transition_renderer crossfade/pre/post <0 → linspace/sosfiltfilt-Crash; rekordbox_xml_exporter ein Duplikat riss Gesamt-Export.

**9 LOW:** ZeroDivision bpm_tolerance==0; ai_engine None-Prompt-Format; ollama_pull Leak bei cancel_check-Fehler; dj_brain Half/Double-Advice+Risk ohne 2.0-Gate; structure 0s-Sektion; analysis 2-Cue cue_in==cue_out; StatusBarWidget-QSS; LM-Studio-Port "not running"; toter logging elif.

**Bewusst NICHT gefixt (dokumentiert):** analysis Track-Averages aus truncated y (elektronische Tracks: Kopf repräsentativ genug); _COMPAT_CACHE global (Generierung läuft nur im Main-Thread, keine echte Nebenläufigkeit); main.py Aux-Worker-Leak (bounded, frei bei Close); error_reporter cross-process (Kinder melden keine Fehler via Reporter).

**Why:** User wollte chirurgisch genaues Audit des gesamten Codes.

**How to apply:** Adversariale Parallel-Agenten + Selbst-Verifikation jedes Funds fand echte Bugs, die 2 vorherige Audits übersahen (v.a. Peak-Time, Rekordbox-Pfad). Siehe [[hpg-fullstack-audit-2026-07-20]], [[hpg-audit-2026-07-17]], [[hpg-venv312-environment]].
