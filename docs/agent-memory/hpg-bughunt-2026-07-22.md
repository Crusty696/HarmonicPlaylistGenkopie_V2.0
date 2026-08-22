---
name: hpg-bughunt-2026-07-22
description: "Große Multi-Agenten-Bug-Hunt am 2026-07-22 — 20+ Fixes über 4 Runden, 2 Funde offen (User-Intent)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 05c5b1d4-8907-401c-b56a-d54757ca71e6
  modified: 2026-07-22T13:01:34.123Z
---

Am 2026-07-22 große Bug-Hunt (User-Goal "such weiter bis keine mehr"). 4 Runden: 8 forensic-investigator-Agenten + Audio-Fuzzer + pyflakes-Linter (3 Methoden). Alle Kernmodule + Support + GUI abgedeckt. Suite danach 1319 grün (+4 neue Regressionstests).

**Auslöser:** PyInstaller-Frozen-Crash — `_render_clip_subprocess_wrapper` lag in `main.py`/`__main__`, `freeze_support()` dispatcht spawn-Child bevor Funktion definiert → AttributeError + `NoneType.write`. Fix: Wrapper nach `hpg_core/transition_renderer.py` verschoben, `_NullWriter` VOR `freeze_support()`.

**Gefixt (Auswahl):** rekordbox_xml_exporter Doppel-URI (CRIT, alle Tracks unauffindbar — roher Pfad an `add_track`, pyrekordbox encoded selbst); transition_renderer pre_frames-Clamp (CRIT, stiller Crossfade bei mix_out<pre_roll) + `_rms_normalize` leeres Segment; main.py TOCTOU-Lock `_executor`, Windows-File-Lock WAV-Löschen, closeEvent Terminate-Fallback; dj_brain Phrasen- statt Bar-Quantisierung in `calculate_paired_mix_points` (Invariante 1); analysis convolve-IndexError kurze Tracks + NaN-Guards; parallel_analyzer Oversubscription; m3u8 atomic-write; theme `get_7_scale_color(nan)`.

**Beide Intent-Funde nach User-Entscheidung erledigt:**
1. Reorder-Verlust: Drag&Drop während KI-Analyse jetzt GESPERRT + sichtbar gekennzeichnet (goldenes Warn-Label). Zentral an `RunState.AI` gekoppelt in `_set_run_state`; `PlaylistPanel.set_reorder_locked()`. Freigabe automatisch bei Übergang weg von AI.
2. DnB-BPM-Gate: User wollte KEINE BPM-only-Einteilung. Genre-Klassifikation ist ohnehin multi-feature (BPM 35%, Spektrum/Rhythmus/Dynamik/Bass 65% + ID3). Einzige BPM-only-Stelle war das DnB-Hard-Gate (genre_classifier.py:330, score=0 bei bpm<grenze). Umgebaut zu weichem Malus: `scores["Drum & Bass"] *= DNB_LOW_BPM_PENALTY` (0.5) statt Kill. Schwelle `DNB_MINIMUM_BPM=160.0`. Starke DnB-Merkmale können Track knapp unter 160 dennoch gewinnen lassen; Halftime-Fehler weiter gedämpft.

**Bewusst verworfene false-positives:** `overlap_seconds > 0` (default 0.0, korrekt), `_resolve_mix_points >= 0` (Fallback-Kontext), atomic-`.part`-write (neuer Leak). Siehe [[hpg-mixpoint-engineering]] für Invarianten.

Abgeschlossen + released: 3 Commits (e6a7dab Bug-Fixes, ff767a6 LOW-Cleanups [logging-encoding/m3u8-UNC/ai-toter-code/config], 661681a main.py-MEDs [_run_is_active zaehlt render_worker, sys.excepthook-Sicherheitsnetz]). GitHub-Release **v3.7.0** (Latest) mit .exe als Direkt-Download-Asset. Frozen-Build via `.exe --worker-smoke` verifiziert (exit 0). Repo: Crusty696/HarmonicPlaylistGenkopie_V2.0.

Nur noch reine Kosmetik offen (kein Defekt): quantize_to_grid mode-Validierung, Bar-Rundungs-Inkonsistenz, rekordbox DB-Connection-Singleton-close.

Verwandt: [[hpg-chirurgie-audit-2026-07-21]], [[hpg-venv312-environment]], [[hpg-mixpoint-engineering]].
