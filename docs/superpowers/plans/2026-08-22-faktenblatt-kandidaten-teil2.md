# Faktenblatt fuer Plan "Mixpunkt-Kandidaten Teil 2 — Paarung und Bewertung"

Stand: 2026-08-22, verifiziert an `main` HEAD `f18815b` (nach Merge Teil 1)
durch zwei Lese-Subagenten (`hpg-scoring`, `hpg-mixpoints`). Zweck: der
Planschreiber fuer Teil 2 (Spec Abschnitt 2,
`docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md:89-142`)
braucht diese Zeilenreferenzen. **Vor Gebrauch jede Zeile erneut pruefen** —
Zeilennummern verschieben sich mit jedem Commit.

---

## A. Was es NICHT gibt (muss Teil 2 bauen)

- Kein `PairCandidate`, kein Paarungsmodul, kein Paar-Score auf
  Kandidatenebene (Grep in `hpg_core/`, `main.py`, `tests/` leer).
- Kein `blend_bars`-Feld irgendwo; `TransitionPlan.overlap` ist Sekunden.
- Kein Pitch-/Stretch-Gate (4 %) in `config.py`/`playlist.py`/`dj_brain.py`.
  Einzige Stellen: Renderer `transition_renderer.py:183`
  `half_double_tolerance = spec.bpm_a * 0.04` (nur Half/Double-Erkennung) und
  Stretch-Clamp `rate = max(0.92, min(1.08, raw_rate))` (:208).
- Kein 2-BPM-Gate in der App; nur Hoertest-Tool
  `tools/rate_transitions.py:81` `STANDARD_BPM_TOLERANZ = 2.0` (Kommentar
  :76-80 "in der App noch NICHT umgesetzt"). App-Default 3.0: `main.py:508`,
  `:2708-2709` (Slider 1–15, Wert 3), `:2933`, `:3081`, `:4299`;
  Funktions-Defaults `playlist.py:1481, 1727, 1742`.
- Keine Lautheits-/Struktur-Faktoren im Scoring; `lufs` nur in
  `dj_brain._gain_advice` (:1047) und Protokollspalte `lufs_delta`.
- Kein `transition_bars` in `GENRE_TRANSITION_TOLERANCES` (nur in
  `GENRE_MIX_PROFILES`).
- `transition_features`-Funktionen lesen keine `*_lokal`-Felder, alles
  trackweit. Keine freie Funktion `camelot_score(code_a, code_b)` — die
  Camelot-Tabelle lebt nur in `playlist._calculate_compatibility_inner`
  (:508-603) und liest Tracks.
- Keine Funktion "Sekunden je Phrase"; Formel inline
  `grid_sec = (60/bpm) * METER * phrase_unit` (`mix_candidates.py:508`) bzw.
  `models.seconds_per_bar(bpm, meter=METER)` (:75-82) × phrase_unit.
- Blenden-Outro-Guard (`out_A + overlap <= outro_start_A`) existiert NICHT in
  `dj_brain`; nur `playlist._clamp_transition_overlap` (:1319-1358) +
  `_outro_overlap_limit` (:1361-1400). `calculate_paired_mix_points` prueft
  keine Coverage.
- BPM-Formel heute `exp(-bpm_diff / max(tol/2, 1e-9))` (`playlist.py:352-359`)
  = `exp(-diff/1.5)` bei tol 3.0 — die Spec verlangt `exp(-diff/1.0)`.

## B. `hpg_core/mix_candidates.py` (530 Z., 4 Leerzeichen)

- `SCHEMA_PRIORITAET` :35-37 `("benannter_cue","pssi_phrase","auto_cue","analyzer","sektion","energie_neuheit")`; `PROVENANCE_JE_SCHEMA` :39-43.
- `MixCandidate` :46-93, Felder (Typ, Default):
  `t: float` (Pflicht) · `schema: list=[]` · `provenance: str=""` · `confidence: float=0.0` ·
  `section_label: str=""` · `phrase_label: str=""` · `neuheit: float|None` · `traegt_allein: bool|None` ·
  `groove_pattern_lokal: list` · `bass_pattern_lokal: list` · `syncopation_lokal: float|None` · `percussive_ratio_lokal: float|None` ·
  `sub_energy` · `bass_punch` · `bass_rms_dbfs` (alle float|None) · `kick_aktiv: bool|None` ·
  `camelot_lokal: str=""` · `key_confidence_lokal: float|None` ·
  `timbre_fingerprint_lokal: list` · `brightness_lokal: int|None` · `flatness_lokal: float|None` · `avg_mids_lokal: float|None` · `avg_highs_lokal: float|None` ·
  `energy_lokal: int|None` · `energy_trend: str=""` (`"rising"/"falling"/...` aus `_trend` :357) · `lufs_lokal: float|None` ·
  `mood: dict={}` (Schluessel `pssi_mood`, `brightness`, `flatness`, `key_mode` = "Major"/"Minor"; :445, :451-452) · `vocal_aktiv_lokal: bool|None`.
  `to_dict()` :87-88 (`asdict`), `from_dict(d)` :90-93.
- Oeffentlich: `normalize_cues` :96-131 · `quantize_to_points(t, points, mode)` :134-153 · `passes_track_gates(t, seite, *, intro_end, outro_start, duration, grid)` :156-169 · `collect_candidate_times(...)` :236-293 (Out-Seite leer ohne `outro_covered` :247-249; `unanalysed` verworfen :266-268; Kappung :281-287) · `measure_candidate_window(file_path, cand, *, bpm, first_downbeat, downbeat_confidence, grid_sec, duration, sections, pssi_mood=None)` :404-483 (Fenster `±grid_sec*KANDIDATEN_FENSTER_PHRASEN`) · `candidate_confidence(...)` :486-494 · `build_track_candidates(file_path, *, bpm, duration, first_downbeat, downbeat_confidence, phrase_confidence, phrase_anchor, phrase_unit, sections, phrases, cues, analyzer_in, analyzer_out, outro_covered) -> tuple[list[dict], list[dict]]` :497-530 (liefert Dicts!).
- Private Helfer: `_cos_dist` :366-373 (Distanz, numpy), `_section_at` :179-188 (Zwilling von `dj_brain.section_dict_at_time`, Kommentar "bei Aenderung beide anpassen"), `_phrase_at` :191-196, `_kick_aktiv(bass_pattern, bass_rms_dbfs)` :350-354 (`bass_rms_dbfs >= KICK_AKTIV_MIN_DBFS` und On-Beat-Summe `>= KICK_AKTIV_ONBEAT_MIN`).
- `traegt_allein` = `_kick_aktiv` auf `y_nach` (:464-469), None→False. `neuheit` = `_neuheit` :383-407 (Mittel aus Rhythmus-/Laut-/Timbre-/Harmonie-Sprung vor/nach t, 0..1).
- Einheiten lokal: `energy_lokal` 0–100 (`calculate_energy`), `brightness_lokal` int (`calculate_brightness`), `avg_mids_lokal`/`avg_highs_lokal` aus `analyze_frequency_bands` (Anteile, 3 Dezimalen), `bass_rms_dbfs` dBFS, `lufs_lokal` LUFS short-term.
- Cache: `caching.py:162-166` `TRACK_LIST_FIELDS` enthaelt `phrases, cue_points, phrase_grid, mix_in_candidates, mix_out_candidates`; `CACHE_VERSION = 34` (:107).

## C. `hpg_core/models.py` (4 Leerzeichen)

`CAMELOT_MAP` :9-18 (A = Moll, B = Dur) · `QUANTIZE_TOLERANCE_SEC = 0.05` :42 · `quantize_to_grid(t, grid, anchor=0.0, mode="round")` :45-72 · `seconds_per_bar(bpm, meter=METER)` :75-82 · `seconds_to_bars` :85-101 · `bars_to_seconds` :104-106 · `get_camelot_components(code) -> (int, str)` :112-120 · `effective_bpm_diff(bpm1, bpm2) -> (diff, "direct"|"half"|"double")` :123-152 (im Tempo-Raum von bpm1) · Track-Felder: `mix_in_point/mix_out_point` :222-223, `first_downbeat` :229, `downbeat_confidence` :230, `first_phrase` :238, `phrase_confidence` :239, `key_confidence` :243, `lufs` :246, `sections` :258, `phrase_unit` :259, `outro_covered` :285, `analysis_coverage` :282-287, **`phrases` :292, `cue_points` :293, `phrase_grid` :294, `mix_in_candidates` :295, `mix_out_candidates` :296** (Listen von Dicts); Property `phrase_anchor` :176-199; `key_to_camelot(track)` :298-302. `unanalysed` ist KEIN Feld, sondern Sektions-Label (`analysis.py:1406/1457`).

## D. `hpg_core/transition_features.py` (195 Z., 4 Leerzeichen)

`cosine_similarity(a, b) -> float|None` :44-53 (auf [0,1] geklemmt) · `_spreize(wert, boden)` :56-68 · `_normiert(delta, maximum)` :71-75 · `groove_match(a, b, genre)` :78-94 (`0.6*cos(bass_pattern)+0.4*cos(groove_pattern)`, `BASS_PATTERN_SHARE=0.6` :17, dann `_spreize(roh, groove_sim_floor)`) · `bass_continuity` :141-165 (`0.6*sub_sim+0.4*punch_sim`, Nahtwerte `_naht_werte` :97-138) · `timbre_match` :168-170 · `mood_match` :173-195 (`0.7*hell_sim+0.3*flach_sim`, **`MODE_SWITCH_PENALTY = 0.15`** :41, angewendet :193-194). Defaults :32-38: `DEFAULT_SUB_DELTA_MAX=0.50`, `DEFAULT_PUNCH_DELTA_MAX=1.4`, `DEFAULT_GROOVE_SIM_FLOOR=0.65`, `DEFAULT_BRIGHTNESS_DELTA_MAX=60.0`, `DEFAULT_FLATNESS_DELTA_MAX=0.15`. Umverteilung bei None liegt NICHT hier, sondern `playlist.combine_weighted` (:278-295).

## E. `hpg_core/genres.py` (gemischte Einrueckung: Tabellen 2, Funktionen 4)

`GenreMixProfile` :289-297 (`transition_bars: tuple[int,int]` :294) · `GENRE_MIX_PROFILES` :299-380: Psytrance (16,32), Tech House (8,16), Progressive (32,64), Melodic Techno (16,32), Techno (16,32), Deep House (32,64), Trance (32,64), DnB (8,16), Minimal (32,64); `DEFAULT_MIX_PROFILE` :384-392 (16,32) · `GENRE_COMPATIBILITY` :400-466 (45 Eintraege), Zugriff **`dj_brain.get_genre_compatibility(a, b)`** :48-86 (Unknown ×0.5: :61-64, :86), `dj_brain.get_mix_profile(genre)` :89-101 · `_TOLERANCE_DEFAULTS` :500-521 (harmonic .160, bpm .120, energy .120, genre .120, groove .300, bass .080, timbre .050, mood .050, `groove_sim_floor` .65, `bass_delta_max` .50, `brightness_delta_max` 60.0) · `GENRE_TRANSITION_TOLERANCES` :523-525 (je Genre identisch) · `_validate_genre_tables()` :530-596, prueft **Summe der acht `*_weight` == 1.0** (:585-594) — neue Gewichte muessen dort getrennt geprueft werden.
Vocals −0.06: `playlist.VOCAL_CLASH_PENALTY = 0.06` (:53, angewendet :465-469).

## F. `hpg_core/tolerances.py` (4 Leerzeichen)

`_MITGELIEFERT = hpg_core/data/transition_tolerances.json` :18 (**Inhalt `{}`**) · `_override_pfad()` :23-29 (`HPG_TOLERANCES_FILE` sonst `%LOCALAPPDATA%/HPG/transition_tolerances.json`) · `_merge` :32-41 · `load_tolerances()` :44-58 · `get_tolerances(genre)` :61-66 (Cache; unbekannt → `CANONICAL_GENRES[0]`) · `entferne_override` :69-83 · `reset_cache` :86-89 · `write_override(gewichte)` :92-113 (`alt_keys` hart :103).

## G. `hpg_core/playlist.py` (2631 Z., 4 Leerzeichen)

`TransitionMetrics` :104-120 · `TransitionRecommendation` :123-142 · `TransitionPlan` (frozen) :145-162 (`mix_out_a, mix_in_b, fade_out_start, fade_out_end, overlap, transition_type, curve, eq_mode, tempo_ratio, target_sr`) · `EnergyDirection` :179-184 · **`combine_weighted(components, weights)` :278-295 (None faellt raus, Rest renormiert)** · `calculate_enhanced_compatibility(track1, track2, bpm_tolerance, energy_direction=None, **kwargs)` :312-491: BPM :352-359, Energie :362-371 (UP `min(1,max(0,diff)/50)`, DOWN, MAINTAIN `max(0,1-|diff|/50)`, sonst `/100`), Genre :378-390, Schalter `TRANSITION_FEATURES_ENABLED` :395, `combine_weighted` mit 8 Schluesseln :427-448, AI-Bonus :458-459, Vocal-Penalty :465-469, BPM-Hard-Gate :474-475 · `_calculate_compatibility_inner` :508-603 (Camelot-Tabelle: gleich 100 :548, A→B 90/B→A 85 :553-557, ±1 fest 80 :564-566, `loose_factor` :573, +2 75 :578-580, +4 70 :585-587, +7 65 :591-593, diagonal 60 :596-598, Rest :601; Half/Double `penalty` :545) · `resolve_scoring_context` :2215-2235 · Fuenf HPG-001-Konsumenten: Sortierung (`calculate_transition_objective` :494-501), Anzeige `main.py:3237`/`:5136-5142`, Reorder `main.py:4737-4749`, Quality `calculate_playlist_quality` :1951-2022, Empfehlungen `compute_transition_recommendations(playlist, bpm_tolerance=3.0, default_overlap=12.0, scoring_context=None, transition_metrics=None)` :1740-1949 (`main.py:4819-4847`) · `compute_adjacent_transition_metrics` :1725-1737 · Overlap: `_clamp_transition_overlap` :1319-1358, `_outro_overlap_limit` :1361-1400 (`MAX_TRANSITION_OVERLAP_SECONDS=64` config:9, `MIN_TRANSITION_BARS=8` config:14), `dj_rec.transition_bars` einzige DJ-Brain-Overlap-Quelle :1842-1850, `dj_rec.overlap_seconds = overlap` ueberschrieben :1866, Plan-Bau :1917-1926 · `predict_transition_type(from_track, to_track, bpm_tolerance=3.0, **kwargs)` :1478-1577.

## H. `hpg_core/dj_brain.py` (2 Leerzeichen, Drift auf 4/6 in Teilen)

`calculate_paired_mix_points(track_a, track_b) -> (adjusted_mix_out_a, adjusted_mix_in_b)` :662-833 (ungerundet; `duration<=0` → Track-Werte :702-706; `min_overlap = spb_b * max(8, transition_bars[0])` :722-723; Mix-In B `quantize_to_grid(intro_end_b, phrase_sec_b, anchor_b, "ceil")` :753-765; Outro-Guard A :779-791; finale Quantisierung :812-832) · `calculate_genre_aware_mix_points(sections, bpm, duration, genre, anchor=0.0, first_downbeat=None) -> (in, out, in_bars, out_bars)` :107-249 · `_get_intro_end_from_sections(sections) -> float` :613-631 · `_get_outro_start_from_sections(sections, duration) -> float` :634-659 · `_get_intro_end(track)` :579-610 · `section_dict_at_time(track, t)` :877-896 · `DJRecommendation` :420-459 (`adjusted_mix_out_a=-1.0` :455, `adjusted_mix_in_b=-1.0` :456, `overlap_seconds=0.0` :459; Sentinel Literal, nicht `MIX_POINT_UNSET`) · `generate_dj_recommendation` :462-575 · Half/Double-Kurzcut ≤16 Bars: `_dynamic_transition_bars` :1138-1142 (`base = min(base, 16)`), dann `max(8, round(base/4)*4)` :1149 · `_effective_bpm_diff` :913-920.

## I. `hpg_core/config.py`

`METER=4` :8 · `MAX_TRANSITION_OVERLAP_SECONDS=64.0` :9 · `MIN_TRANSITION_BARS=8` :14 · `MIX_POINT_UNSET=-1.0` :26 · `DEFAULT_BPM=120.0` :43 · `GAIN_DIFF_WARN_DB=3.0` :59 · `KEY_CONFIDENCE_UNCERTAIN=0.5` :64 · Kandidaten :66-86 (`KANDIDATEN_MIN_JE_SEITE=3`, `KANDIDATEN_MAX_JE_SEITE=8`, `KANDIDATEN_FENSTER_PHRASEN=1`, `KANDIDATEN_AUDIO_SR=22050`, `CUE_DEDUPE_SEC=2.0`, `KICK_AKTIV_MIN_DBFS=-35.0`, `KICK_AKTIV_ONBEAT_MIN=0.40`, `ENERGIE_TREND_SCHWELLE=10`, `ENERGIE_NEUHEIT_MIN=20`) · `GENRE_WEIGHT_WITH_DJ_BRAIN=0.2` :117, `GENRE_WEIGHT_WITHOUT_DJ_BRAIN=0.1` :118 · `BPM_HALF_DOUBLE_ENABLED=True` :146, `BPM_HALF_DOUBLE_PENALTY=0.85` :147 · `TRANSITION_FEATURES_ENABLED=True` :159.

## J. `main.py` / Renderer / Exporter

`resolve_transition_mix_points(transition)` `main.py:175-205` (plan > dj.adjusted_* ≥ 0 > Track > 16.0) · Leser: `TransitionRenderWorker.run` :693/:771-777 (`TransitionClipSpec.from_plan` :773), `TransitionPreviewWidget` :1085/:1125, `PlaylistPanel._populate_table` :3276/3279, `MixTipsPanel._populate` :3426/:3573-3585, `TimelinePanel.set_timeline` :3930/:3936-3941, `MainWindow.on_ai_finished` :4725/4728, `_export_m3u8` :5071-5075, `_export_rekordbox_xml` :5094-5098 · `TransitionClipSpec` `transition_renderer.py:50-135`, `from_plan(cls, plan, from_track, to_track)` :98-135 · Exporter: `RekordboxXMLExporter._add_cue_points(xml, rb_track, track)` `rekordbox_xml_exporter.py:306-346` (`MIX IN` Num=0/-1 :324-325, `MIX OUT` Num=1/-1 :329-330, Drop/Breakdown Memory :334-341), Gate `_cue_export_allowed` :348-364; `M3U8Exporter.export` `m3u8_exporter.py:45-50` (keine Cues); `BaseExporter.export` `base_exporter.py:47`.

## K. Hoertest-Tool `tools/rate_transitions.py`

`NEUE_FAKTOREN` :67, `KLASSISCHE_FAKTOREN` :71, `ALLE_FAKTOREN` :72, `ZUSATZ_SPALTEN` :74 · `STANDARD_BPM_TOLERANZ=2.0` :81, `SCORING_BPM_TOLERANZ=3.0` :86, `MIN_HARMONIC_SCORE=60` :87, `MIN_OVERALL_SCORE=0.70` :99, `MIN_GROOVE=0.5` :102, `HOERTEST_TRANSITION_TYPE="pro_eq_swap"` :108, `CROSSFADE_SEK=32.0` :121, `PRE_ROLL_SEK=8.0` :122, `POST_ROLL_SEK=8.0` :123 · `_faktoren_vollstaendig` :622-647 · `sammle_kandidaten(tracks, bpm_toleranz=...)` :650-699 (trackweite Paare) · `befehl_prepare` :861-957, `merkmale.csv` Spalten :928-932 (`pair_id, *ALLE_FAKTOREN, crossfade_sek, overall_score, lufs_delta, track_a, track_b`), `bewertung.csv` :926 · `rendere_paar` :772ff, `geplanter_overlap` :723. **Heute nur Track-Paare, keine Kandidaten-Paare.**

## L. Tests

`tests/test_mix_candidates.py` (4 Leerzeichen, keine Fixtures; `_sections()` :65-74, `_kick_track(tmp_path, ...)` :167-182; `MixCandidate(t=30.0, schema=["sektion"])` :187) · `tests/test_transition_features.py` (4; autouse `feste_toleranzen(monkeypatch)` :14-35; `_track(**kwargs)` :38-42; `_gerade()/_offbeat()` :45-56) · `tests/conftest.py` (2): `assert_mix_points_valid(track, tolerance_bars=2)` :218-244, `assert_phrase_aligned(bars, bars_per_phrase=8)` :247-252; Fixture `default_track` :143-146; Factory `make_track(**overrides)` in `tests/fixtures/track_factories.py:8` · `tests/test_dj_brain.py` (ueberwiegend 4, teils 2).

## M. Einrueckung

4: `transition_features.py`, `tolerances.py`, `playlist.py`, `mix_candidates.py`, `main.py`, `transition_renderer.py`, `exporters/*.py`, `tests/test_transition_features.py`, `tests/test_mix_candidates.py`. 2: `dj_brain.py`, `tests/conftest.py`. Gemischt: `genres.py` (Tabellen 2, Funktionen 4).
