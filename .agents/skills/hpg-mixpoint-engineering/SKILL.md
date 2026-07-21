---
name: hpg-mixpoint-engineering
description: Use when working on Mix-In/Mix-Out-Punkte, Phrase-Alignment, Übergangs-Rendering, DJRecommendation, adjusted_mix_out_a/adjusted_mix_in_b, calculate_genre_aware_mix_points, calculate_paired_mix_points oder Transition-Preview im HPG-Projekt — vor jedem Lesen/Ändern dieser Logik.
---

# HPG Mixpoint Engineering

## Overview

Mixpoints (Sekunden, `Track.mix_in_point`/`mix_out_point`, [models.py:61-62](hpg_core/models.py)) werden von **vier konkurrierenden Pfaden** gesetzt. Es gibt keinen Prioritäts-Mechanismus — letzter Schreibzugriff gewinnt. Änderungen an einem Pfad brechen leicht die anderen.

## Die 4 Berechnungspfade (Reihenfolge = zeitlich)

| # | Pfad | Ort | Bedingung |
|---|------|-----|-----------|
| A | Genre-aware (primär) | `calculate_genre_aware_mix_points` [dj_brain.py:263-316](hpg_core/dj_brain.py:263) | Genre != "Unknown" und Sections vorhanden ([analysis.py:777](hpg_core/analysis.py:777)) |
| B | RMS-Fallback | `analyze_structure_and_mix_points` [analysis.py:545-686](hpg_core/analysis.py:545) | sonst; fixe 8-Bar-Phrasen |
| C | Rekordbox-Cue-Override | [analysis.py:793-805](hpg_core/analysis.py:793) | Cues mit "IN"/"START" bzw. "OUT"/"END" im Namen überschreiben A/B |
| D | AI/LLM-Override | `fetch_ai_analysis` [ai_engine.py:9](hpg_core/ai_engine.py:9) → [main.py:3130-3146](main.py:3130) | zur Laufzeit; mutiert Track in-place, persistiert in SQLite-Cache |

Zusätzlich **paarweise zur Renderzeit** (überschreibt Track NICHT):
- `calculate_paired_mix_points(track_a, track_b)` [dj_brain.py:676-755](hpg_core/dj_brain.py:676)
- `generate_dj_recommendation` [dj_brain.py:496](hpg_core/dj_brain.py:496) → `DJRecommendation.adjusted_mix_out_a/adjusted_mix_in_b/overlap_seconds` (Sentinel-Default `-1.0`)

## Invarianten (bei jeder Änderung prüfen)

1. **Phrase-Alignment**: `mix_in = ceil(t/grid)*grid` (NACH Intro), `mix_out = floor(t/grid)*grid` (VOR Outro). `grid = seconds_per_bar * phrase_unit`. [dj_brain.py:290-294](hpg_core/dj_brain.py:290)
2. `phrase_unit` ist genre-abhängig: Psytrance/Trance=16, sonst 8 (`GENRE_PHRASE_UNITS` [structure_analyzer.py:62-72](hpg_core/structure_analyzer.py:62)).
3. `0 <= mix_in < mix_out <= duration` — Test-Helper: `assert_mix_points_valid` [tests/conftest.py:186](tests/conftest.py:186), `assert_phrase_aligned` [:215](tests/conftest.py:215).
4. Mixpoints dürfen nie in Intro/Outro-Sektionen liegen (Design-Spec: docs/superpowers/specs/2026-03-11-mix-point-intro-outro-guard-design.md).
5. Einheiten: Sekunden für Zeitpunkte, Bars nur für Anzeige (`mix_in_bars`/`mix_out_bars`), Samples nur intern im Renderer.

## Rendering-Kette

`compute_transition_recommendations` [playlist.py:1290](hpg_core/playlist.py:1290) → `TransitionRenderWorker.run` [main.py:439](main.py:439) → subprocess (`ProcessPoolExecutor(max_workers=1)`, 30s-Timeout, fängt C-Crashes) → `render_transition_clip` [transition_renderer.py:65](hpg_core/transition_renderer.py:65).

Prioritätslogik im Worker ([main.py:483-498](main.py:483)): `dj.adjusted_*` > `track.mix_*_point` > Fallback 16.0s Overlap. Renderer: Crossfade max 32s, Stretch-Rate geclamped 0.85–1.15, Pre-Roll 30s.

## Historie gefixter Bugs (2026-07-16, alle mit Regressionstests / Suite 1433 grün)

| Fix | Ort |
|-----|-----|
| Sentinel vereinheitlicht auf `>= 0.0` (0.0 = legitimer Mixpoint, -1.0 = Sentinel) | main.py 486/491/585/590/2481, playlist.py:1360 |
| AI/LLM-Mixpoints phrase-quantisiert via `align_ai_mix_points()` (ceil in / floor out, Bar-Fallback, Epsilon) | dj_brain.py, main.py AI-Override |
| Prozent-Guards (0.4/0.6) durch sektions-/phrasenbasierte Grenzen ersetzt (min_window = 2 Phrasen) | dj_brain.py `calculate_genre_aware_mix_points` |
| Fallback-BPM 140.0 → `config.DEFAULT_BPM` | dj_brain.py |
| None-Guard `_section_covers()` im Bass-Kollisions-Check | dj_brain.py `_assess_transition_risks` |
| Halftime-Toleranz: absolut 10 BPM → relativ 4% (DJ-Pitchfader-Praxis) | transition_renderer.py |
| Crossfade-Cap 32s→64s + Render-Timeout 30s→60s (Trance blendet 32-64 Bars) | transition_renderer.py:76, main.py |
| Genre-Profile recherche-basiert: Techno transition (16,32), Trance (32,64) | dj_brain.py GENRE_MIX_PROFILES |

## Key-Confidence + LUFS ERLEDIGT (2026-07-17)

`Track.key_confidence` (Essentia-Muster: strength=Pearson-r des Gewinners + margin=(max−max2)/max; `get_key_with_confidence`/`key_confidence_score` in analysis.py; Zweitkandidat-Nachbar-Logik: Quinte/relative = quasi-sicher, MIREX-Fehlerklassen; Rekordbox-Key = 1.0, 0.0 = Alt-Cache-Sentinel). `Track.lufs` (EBU R128 Integrated via pyloudnorm/DeMan, neue Dependency; Sentinel 0.0; Referenz LUFS_REFERENCE=-18 = ReplayGain 2.0). `DJRecommendation.gain_advice` (+Risk-Notes bei Key-Konfidenz <0.5 bzw. LUFS-Diff ≥3 dB). Renderer bewusst unverändert (lokale RMS-Segment-Angleichung = Mix-Moment-Matching). Bewusst KEINE Ranking-Änderung durch key_confidence. CACHE_VERSION 17. Plan: docs/plans/2026-07-17-key-confidence-lufs.md.

## Downbeat-Erkennung ERLEDIGT (2026-07-17)

`Track.first_downbeat` (+ `downbeat_confidence`) verankert das gesamte Phrasen-Raster — vorher rasterte alles arithmetisch ab t=0. Quellen: (1) Rekordbox-ANLZ-Beatgrid (PQTZ-Tag, `rekordbox_importer.get_first_downbeat`, Konfidenz 1.0), (2) eigene Schätzung `hpg_core/downbeat.py` (Phase-Voting nach Vande Veire EURASIP 2018: Bass-Onsets + Chroma-Novelty + Loudness-Akzent über 4 Hypothesen, Bass-Onset-Snap-Feintuning). Zentrale Quantisierung: `models.quantize_to_grid(t, grid, anchor, mode)` — anchor=0.0 ist bit-identisch zum Altverhalten. Verankert: calculate_genre_aware_mix_points (+_find-Helfer), align_ai_mix_points, calculate_paired_mix_points-Guards, structure_analyzer-Grenzen, Renderer-Beat-Alignment (exakt aus Grids statt Laufzeit-Schätzung, `TransitionClipSpec.first_downbeat_a/b`), XML-Export `Inizio`. Bars-Anzeige zählt weiterhin ab t=0 (dokumentierte Entscheidung). CACHE_VERSION 16. Plan: docs/plans/2026-07-17-downbeat-erkennung.md.

## Pfad-B-Konsolidierung ERLEDIGT (2026-07-17)

`analyze_structure_and_mix_points` ist jetzt reine Fassade: RMS-Aktivitätserkennung (Glättung 4-Takt-Fenster, Schwelle 0.4×Track-Max nach Zehren arXiv 2007.08411) + Suchfenster-Pruning (Mix-In erste 20%, Mix-Out letzte 25% nach Bittner ISMIR 2017) → 3 Pseudo-Sektionen (intro/main/outro) → delegiert an `calculate_genre_aware_mix_points`. **Nur noch EINE Quantisierungs-/Clamp-Logik.** Signatur: `genre`-Parameter statt `phrase_unit` (Profil liefert das Gitter). `DJ_BRAIN_ENABLED` entfernt (schaltete nichts mehr), `INTRO_MAX_PERCENTAGE`/`OUTRO_MIN_PERCENTAGE` ersetzt durch `MIX_IN_SEARCH_WINDOW_PCT`/`MIX_OUT_SEARCH_WINDOW_PCT`. Pfad A verbessert: `max_mix_out` bis zur Outro-GRENZE (Mix-Out auf der Grenze = DJ-Standard) + Re-Quantisierung aufs Phrasen-Gitter nach Clamps. bpm<=0 wirft weiterhin ValueError (Fassaden-Vertrag). CACHE_VERSION 15. Plan+Research: docs/plans/2026-07-17-mixpoint-pfad-b-konsolidierung.md.

## Noch offen

| Punkt | Detail |
|-------|--------|
| Mix-Out nah am Track-Ende | `calculate_paired_mix_points` Limit nur `duration - 1 Bar`. |

## DJ-Praxis-Referenz (Web-Recherche 2026-07, 26 Quellen)

Techno: 16 Bars Standard-Blend, 32 Sweet Spot; Bass-Swap hart auf Phrasengrenze (Lows 2-4 Bars, Mids bis 16). Psytrance: Dark 8-16, Full-On 16-32, Progressive 32-64 Bars; Intros/Outros 32-64 Bars sind Werkzeug. Uplifting Trance: 32-64+, bis 120 Bars. Nie zwei Basslines gleichzeitig. Pitch max ±3-4%. Loops als Fallback bei kurzen Intros. Quellen: DJ TechTools, Psynews, Crossfader, Digital DJ Tips.

## Common Mistakes

- Sentinel-Check gegen `> 0` statt `>= 0.0` schreiben — verwirft Mixpoint bei t=0.
- Neue Mixpoint-Quelle hinzufügen ohne Phrase-Quantisierung (siehe AI-Override-Bug).
- Section-Dict-Felder ohne `None`-Guard vergleichen.
- Magische Faktoren ändern, ohne beide Pfade (A und B) zu synchronisieren.
- Bars und Sekunden verwechseln — `seconds_per_bar = 60/bpm * 4` (METER=4).
