# Faktenblatt fuer Plan "Mixpunkt-Kandidaten Teil 4 — App"

Stand 2026-08-22, verifiziert am Branch `kandidaten-teil2` (enthaelt Teil 2) durch
Lese-Subagent `hpg-gui`. Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md:178-212`.
**Vor Gebrauch jede Zeile erneut pruefen.**

## 0. Eingang aus Teil 2 (`hpg_core/pair_candidates.py`)

`PairCandidate` :46-80 (`out_a, in_b, blend_bars, overlap_sec, score, teilwerte,
flags, begruendung, rang, bpm_relation`; Properties `t_out/t_in`; `to_dict/from_dict`);
`build_pair_candidates(track_a, track_b, *, energy_direction=None,
harmonic_strictness=7, allow_experimental=True, tolerances=None)` :506-540
(`[]` bei leerer Seite oder keinem Gate-Durchlass; Rang ab 1). Flags
`bass_swap_pflicht`, `lange_blende_erlaubt`, `half_double`, `benannter_cue`.
`_gewichte(tol)` liest `tol["kandidaten_<faktor>_weight"]` (Defaults
`genres.py:526-535`, Validierung :609-618). **Kein Import von
`pair_candidates` in `playlist.py`, `main.py`, `caching.py`, Exportern.**

## 1. `hpg_core/playlist.py` (4 Leerzeichen)

- `calculate_enhanced_compatibility(track1, track2, bpm_tolerance, energy_direction=None, **kwargs) -> TransitionMetrics` :313-493.
  Cache-Key `_enhanced_cache_key` :204-224 nimmt `kwargs` per `repr` auf (:216);
  `_ENHANCED_COMPAT_CACHE` :544. kwargs gehen an `_calculate_compatibility_inner`
  :347-349 (liest nur `harmonic_strictness`, `allow_experimental`). Scoring-Block
  :396-449 (`combine_weighted` :424-448), Altpfad :450-457, `ai_bonus` :459-460,
  Vocal-Clash :468-472, BPM-Hard-Gate :477-478. `TransitionMetrics` :105-120
  (kein Feld fuer Lautheit/Struktur/Kandidat), Erzeugung :480-491.
  `calculate_transition_objective` :495-503.
- `resolve_scoring_context` :2149-2169; `SCORING_PARAMETERS = {"harmonic_strictness","allow_experimental"}` :2119;
  `SUPPORTED_STRATEGY_PARAMETERS` :2121-2140; `STRATEGIES` :2104-2113; `STRATEGY_ALIASES` :2143-2147.
- `compute_adjacent_transition_metrics(playlist, bpm_tolerance=3.0, scoring_context=None)` :1659-1671.
- `compute_transition_recommendations(playlist, bpm_tolerance=3.0, default_overlap=12.0, scoring_context=None, transition_metrics=None)` :1674-1882:
  `configured_overlap` 4..64 :1699-1704; `_resolve_mix_points(current, effective_overlap)` :1720-1723
  (Funktion :1220-1250); `fade_out_start/fade_in_start/overlap` :1745-1747; DJ-Brain-Override
  :1768-1786 (`adjusted_mix_out_a/in_b >= 0`, `overlap = spb * dj_rec.transition_bars` :1781-1782);
  `_clamp_transition_overlap(...)` :1791-1801 (Funktion :1253-1291, `_outro_overlap_limit` :1294);
  `min(overlap, 64)` :1817; `predict_transition_type(..., **ctx)` :1837-1839; `fade_out_end` :1848-1850;
  `TransitionPlan(...)` :1852-1861 (Dataclass :146-163), `TransitionRecommendation(...)` :1862-1880 (:124-143).
  **Einstieg fuer Rang-1-PairCandidate: zwischen :1768 (nach DJ-Brain) und :1791 (Clamp)**
  `current_mix_out = t_out`, `next_mix_in = t_in`, `overlap = overlap_sec`.
- `predict_transition_type(from_track, to_track, bpm_tolerance=3.0, **kwargs) -> str` :1412-1510
  (`"bass_swap"` :1485/:1496 nur `hard_genres`); kwargs gehen auch an
  `calculate_compatibility` :1440-1442/:1457-1459 (Cache-Key!). Kein Flag `bass_swap_pflicht`.
- `calculate_playlist_quality(tracks, bpm_tolerance, scoring_context=None, transition_metrics=None)` :1885-1955.

## 2. `main.py` (4 Leerzeichen, 5351 Z.)

- `RunState` :145-157, `ACTIVE_RUN_STATES` :160-166, `_set_run_state` :4488-4490.
- `resolve_transition_mix_points(transition)` :175-206 (plan > dj_rec.adjusted_* > Track); `format_mix_point_display` :209-213.
- `TransitionRenderWorker` :693-887 (Signale `clip_ready(int,str)` :699, `clip_error` :700,
  `request_cancel` :716; `run()` :748 → `TransitionClipSpec.from_plan` :770-774, Fallback :776; Subprozess :813-830).
- `TransitionPreviewWidget` :1085-1312 (`_setup_ui` :1110, `resolve_transition_mix_points` :1125, Labels :1150-1166, `_crossfade_sec` :1175).
- `MixTipsPanel` :3426-3914: Karten (QFrame je Uebergang, kein Table);
  `set_recommendations` :3464-3472 → `_populate` :3481-3689 (`_card_layouts` :3681;
  `type_badge` :3562; Timing-Label aus `dj_rec.adjusted_*`/`rec.fade_*` :3572-3589);
  Preview `setup_transition_previews` :3691-3706, `_request_preview` :3708-3738,
  `_start_next_preview` :3740-3757 (`TransitionRenderWorker([...], self)` :3745),
  `_on_preview_worker_finished` :3759-3785, `_on_clip_ready` :3874, `_on_clip_error` :3894,
  `_preview_cache` LRU 8 :3443-3445. **Kein Kandidaten-Widget, kein "aktiver Kandidat".**
- `PlaylistPanel` :2920-3424: 16 Spalten :2951, Header :2952-2971 (10 "Mix In", 11 "Mix Out", 14 "Passung");
  `_populate_table` :3226 (Mix-In/Out :3275-3282 aus Track-Feldern); `_update_table_after_reorder`
  :3371-3423 (`calculate_playlist_quality` :3415, `compute_transition_recommendations` :3419-3423);
  `set_playlist_data(playlist, quality_metrics, transition_recommendations=None, bpm_tolerance=3.0, scoring_context=None)` :3076-3083.
- `TimelinePanel.set_timeline(playlist, transition_recommendations=None)` :3930-4065 (`rec.plan` → `compute_set_timeline` :3936-3942).
- Faktoren-Regler (`AdvancedParametersWidget`) :1549-1599: `QGroupBox("Uebergangs-Gewichte")` :1552;
  `transition_weight_sliders` :1561; Liste :1562-1567 (`groove_weight` 30, `bass_weight` 8,
  `timbre_weight` 5, `mood_weight` 5); Handler `_on_transition_weight_changed` :1610-1632
  (`write_override(gewichte)` :1625, `reset_cache()` :1629), Reset :1634-1659, `_lade_transition_regler` :1661-1676.
- BPM-Toleranz: Slider :2707-2709 (`setRange(1,15)`, `setValue(3)`), Tooltip :2710-2713, Label :2714,
  `get_current_settings()["bpm_tolerance"]` :2821-2827. Weitere 3.0-Defaults: `AnalysisWorker.__init__` :504-509,
  `PlaylistPanel.__init__` :2933, `set_playlist_data` :3081, `MainWindow.__init__` :4299; `playlist.py` :1415, :1661, :1676, :2175.
- **Keine Settings-Persistenz** (kein QSettings, kein `%LOCALAPPDATA%\HPG`-Helfer in `main.py`).
- Export: `export_playlist` :5032-5069, `_export_m3u8` :5071-5092 (`M3U8Exporter().export(self.playlist, ...)` :5073-5075),
  `_export_rekordbox_xml` :5094-5126 (:5096-5098). Nur `self.playlist`, keine Recommendations/Plans.
- `on_ai_finished(track_path, ai_data, source_worker=None)` :4676ff (Guards :4678-4681); Anbindung :4986-5004.
- Analyse-Lauf: `AnalysisWorker` :490 (`analysis_done` :501); Start :4607-4626; `_cleanup_analysis_worker` :4628-4640;
  `analysis_finished`: `resolve_scoring_context` :4794, `generate_playlist` :4797-4802,
  `compute_adjacent_transition_metrics` :4820, `calculate_playlist_quality` :4823,
  `compute_transition_recommendations` :4829, Verteilung :4842-4855 (`set_playlist_data`,
  `mix_tips_panel.set_recommendations` :4849, `setup_transition_previews` :4851, `timeline_panel.set_timeline` :4852);
  Reorder `_on_playlist_reordered` :5008-5030.
- Statusleiste: eigener `StatusBarWidget` :2287 (`set_status` :2369, `set_progress` :2383), `self.status_bar` :4415.

## 3. Exporter (4 Leerzeichen)

- `rekordbox_xml_exporter.py`: `export(playlist, output_path, playlist_name)` :90ff; Dedupe :118-133;
  Schleife :144 → `_add_track_to_collection(xml, track, idx)` :146-148/:210-212 (**ein** Track, kein Nachbar);
  `_add_cue_points(xml, rb_track, track)` :306-346 (`MIX IN` Num=0/-1 :324-325, `MIX OUT` Num=1/-1 :329-330,
  DROP/BREAKDOWN Num=-1 :333-340); `_cue_export_allowed(track)` :348-364. Fuer "HPG K1..K6" je Paar
  muss Nachbarinfo vor der Schleife (:144) bereitgestellt werden.
- `m3u8_exporter.py`: `export` :45ff, `mkstemp` :79, `for track in playlist` :91, keine Mixpunkte.
- `base_exporter.py`: `ExportReport` :12-36, `BaseExporter.export` :47.

## 4. `hpg_core/caching.py`

`_default_cache_file()` :111-123 (`HPG_CACHE_DIR` :113, `LOCALAPPDATA\HPG` :117-122, `~/.hpg`),
`HPG_CACHE_FILE` :108 — liefert nur den DB-Pfad. **`candidate_choices.json` existiert nicht**;
einzige vergleichbare Datei: `tolerances._override_pfad()` :22-28.

## 5. Tests

pytest-qt 4.5.0 (`requirements.txt:33`); `qtbot` in `tests/test_run_lifecycle.py` (:36, :64-66),
`tests/test_transition_weight_ui.py` (:23-31 `HPG_TOLERANCES_FILE`, `qtbot.addWidget`),
`tests/test_main_workers.py` (QApplication :516-520; GUI-frei :16-34 `resolve_transition_mix_points`
mit `SimpleNamespace`, :37-48 `worker.run()` direkt). Exporter: `tests/test_exporters.py` (:13-20,
`make_track` aus `tests/fixtures/track_factories`), `tests/test_rekordbox_xml_exporter.py`.
Playlist: `tests/test_playlist_quality.py`, `tests/test_playlist_strategies.py`.

## 6. Gewichte-Pfad Regler → Toleranzen

`main.py:1620-1625` → `tolerances.write_override(gewichte)` :92-113 (Summe < 1.0 :99-101;
skaliert nur `harmonic/bpm/energy/genre_weight` :103-110) → `_override_pfad()` :22-28;
`load_tolerances` :45-58, `get_tolerances` :61-66, `reset_cache` :86-89.
**Konsequenz fuer `kandidaten_loudness_weight`:** `write_override` summiert alle
uebergebenen Schluessel gegen 1.0 und skaliert nur die vier Alt-Schluessel — ein
`kandidaten_*`-Wert darf nicht in dieselbe Summe fallen; die zehn
`kandidaten_*`-Gewichte muessen separat auf 1.0 summieren (Validierung
`genres.py:609-618` gilt nur fuer Defaults). `_lade_transition_regler` :1673-1676
liest generisch; `pair_candidates._gewichte` liest `get_tolerances(genre)` — ein
Override wirkt dort direkt.

## 7. Einrueckung

4: `main.py`, `playlist.py`, `pair_candidates.py`, `tolerances.py`, `exporters/*.py`,
`tests/test_pair_candidates.py`, `tests/test_tolerances.py`. 2: `tests/test_main_workers.py`,
`test_run_lifecycle.py`, `test_playlist_quality.py`, `test_playlist_strategies.py`,
`test_exporters.py`, `test_rekordbox_xml_exporter.py`, `test_transition_weight_ui.py`,
`test_gui_display.py`, `genres.py` (Tabellen).

## Nicht existent (explizit)

QSettings/Settings-Persistenz; `%LOCALAPPDATA%\HPG`-Helfer in `main.py`;
`candidate_choices.json`; Kandidaten-Tabelle/aktiver Kandidat im `MixTipsPanel`;
`TransitionMetrics`-Felder fuer Lautheit/Struktur/Kandidat; `bass_swap_pflicht` in
`predict_transition_type`; Nachbartrack-Zugriff im XML-Exporter; Lautheit-Regler.
