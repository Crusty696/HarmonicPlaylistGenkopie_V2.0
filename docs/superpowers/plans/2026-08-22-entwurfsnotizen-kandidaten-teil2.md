# Entwurfsnotizen fuer Plan "Mixpunkt-Kandidaten Teil 2 — Paarung und Bewertung"

Stand 2026-08-22. **Status: Entwurf des Agenten, vom Nutzer NICHT genehmigt.**
Grundlage: Spec Abschnitt 2 (`docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md:89-142`)
und das Faktenblatt `2026-08-22-faktenblatt-kandidaten-teil2.md`. Diese Notizen
legen fest, wie die in der Spec offen formulierten Stellen konkret gebaut
werden sollen. Jede hier getroffene Festlegung ist dem Nutzer bzw. dem
Waechter (Tor 1) vorzulegen, bevor der Plan geschrieben wird. Wo die Spec
keinen Zahlenwert nennt, ist der Wert als **Startwert** markiert — der
Hoertest (Teil 3) ersetzt ihn.

## 1. Modul und Datentyp

- Neues Modul `hpg_core/pair_candidates.py` (4 Leerzeichen, Kommentare
  Deutsch). Reine Funktionen ueber `Track` + `MixCandidate`; kein Audio-Zugriff
  (alle Messwerte liegen in den Kandidaten).
- `@dataclass PairCandidate`: `out_a: MixCandidate`, `in_b: MixCandidate`,
  `blend_bars: int`, `overlap_sec: float`, `score: float`,
  `teilwerte: dict[str, float | None]`, `flags: dict[str, bool]`
  (`bass_swap_pflicht`, `lange_blende_erlaubt`, `half_double`),
  `begruendung: str`, `rang: int = 0`, `bpm_relation: str`;
  `to_dict()`/`from_dict()` wie `MixCandidate` (Kandidaten als Dicts).
- Einstieg: `build_pair_candidates(track_a, track_b, *, energy_direction=None,
  harmonic_strictness=5, allow_experimental=False, tolerances=None)
  -> list[PairCandidate]` (sortiert, `rang` 1..n). Track-Kandidaten kommen aus
  `track_a.mix_out_candidates` / `track_b.mix_in_candidates` (Dicts →
  `MixCandidate.from_dict`).

## 2. Schritt 1 — harte Gates (Paar-Ebene)

| Gate (Spec) | Umsetzung | Konstante (config.py) |
|---|---|---|
| BPM ≤ 2.0 effektiv | `effective_bpm_diff(bpm_a, bpm_b)` → (diff, rel); `diff <= PAAR_BPM_MAX` | `PAAR_BPM_MAX = 2.0` |
| Half/Double: kurzer Cut ≤ 16 Bars, Penalty 0.85 | bei rel ≠ direct: `blend_bars = min(blend_bars, PAAR_HALF_DOUBLE_MAX_BARS)`, Score × `BPM_HALF_DOUBLE_PENALTY` (0.85, vorhanden) | `PAAR_HALF_DOUBLE_MAX_BARS = 16` |
| Pitch ≤ 4 % | `diff / bpm_a <= PAAR_PITCH_MAX` (im Tempo-Raum von A, wie `effective_bpm_diff`) | `PAAR_PITCH_MAX = 0.04` |
| `out_A + overlap <= outro_start_A` | `overlap = blend_bars * seconds_per_bar(bpm_a)`; `outro_start_A = _get_outro_start_from_sections(track_a.sections, duration_a)`; **Ausnahme wie Teil 1:** `"benannter_cue" in out_a.schema` schlaegt den Guard (dann nur `out_a.t + overlap <= duration_a`) | — |
| `in_B >= intro_end_B` | `_get_intro_end_from_sections(track_b.sections)`; Ausnahme benannter Cue analog | — |
| Coverage | `section_label != "unanalysed"` beidseitig; Out nur bei `track_a.outro_covered` | — |
| Gitter | `abs(q - t) <= QUANTIZE_TOLERANCE_SEC` mit `q = quantize_to_points(t, track.phrase_grid, ...)` falls `phrase_grid`, sonst `quantize_to_grid(t, grid_sec, phrase_anchor, "round")` | vorhanden |

Offene Frage an den Nutzer: Gilt die Benannter-Cue-Ausnahme (Abschnitt 1)
auch fuer den Blenden-Guard auf Paar-Ebene? Entwurf: ja (konsistent mit
Teil 1). Alternative: nein (Blende muss immer vor dem Outro enden).

## 3. Schritt 2 — Teilwerte (alle aus `*_lokal`, je [0,1] oder None)

| Faktor | Formel (Entwurf) | Startwerte |
|---|---|---|
| Harmonie | Camelot-Tabelle auf `camelot_lokal` → neue reine Funktion `camelot_relation_score(code_a, code_b, *, harmonic_strictness, allow_experimental, penalty) -> int` in `playlist.py`, **herausgeloest** aus `_calculate_compatibility_inner` (:548-601), die sie danach selbst aufruft (Refactor, bestehende Tests `test_compatibility.py`/`test_scoring_contract.py` bleiben unveraendert = Schutz). Wert = score/100; **Gewicht** × `min(key_confidence_lokal_a, key_confidence_lokal_b)`; fehlt `camelot_lokal` → None | — |
| BPM | `exp(-diff / PAAR_BPM_SKALA)` innerhalb des Gates | `PAAR_BPM_SKALA = 1.0` (Spec) |
| Energie | `diff = in_b.energy_lokal - out_a.energy_lokal`; Richtung wie `calculate_enhanced_compatibility` :362-371 (UP/DOWN/MAINTAIN, sonst `1-|diff|/100`); widerspricht `in_b.energy_trend` der Richtung (UP & "falling", DOWN & "rising") → × `ENERGIE_TREND_WIDERSPRUCH` | `ENERGIE_TREND_WIDERSPRUCH = 0.8` |
| Genre | `get_genre_compatibility(genre_a, genre_b)` (Unknown ×0.5 eingebaut) | — |
| Groove/Rhythmus | `roh = 0.6*cos(bass_pattern_lokal) + 0.4*cos(groove_pattern_lokal)` (`cosine_similarity`, `BASS_PATTERN_SHARE`), `_spreize(roh, groove_sim_floor)`; × `(1 - min(1, |Δsyncopation_lokal| / SYNCOPATION_DELTA_MAX))`; beide `percussive_ratio_lokal > PERCUSSIVE_HOCH` → `- PERCUSSIVE_ABZUG`; beide `< PERCUSSIVE_NIEDRIG` → Flag `lange_blende_erlaubt` (kein Score-Effekt; Flag fuer Blendenwahl/Anzeige) | `SYNCOPATION_DELTA_MAX = 0.5`, `PERCUSSIVE_HOCH = 0.7`, `PERCUSSIVE_NIEDRIG = 0.3`, `PERCUSSIVE_ABZUG = 0.10` |
| Bassdruck + Bass-Rhythmus | `0.6*_normiert(Δsub_energy, bass_delta_max) + 0.4*_normiert(Δbass_punch, DEFAULT_PUNCH_DELTA_MAX)`; × `(1 - min(1, |Δbass_rms_dbfs| / BASS_RMS_DELTA_MAX_DB))`; beide `kick_aktiv` → Flag `bass_swap_pflicht` **und** `- KICK_KONFLIKT_ABZUG` (Spec "sonst Abzug": ohne Bass-Swap-Punkt laufen zwei Kicks; der Abzug gilt, solange der Uebergangstyp kein Bass-Swap/EQ-Swap ist — das entscheidet Teil 4 ueber `predict_transition_type`; im reinen Paar-Score ist der Abzug immer aktiv, Flag sichtbar) | `BASS_RMS_DELTA_MAX_DB = 6.0`, `KICK_KONFLIKT_ABZUG = 0.15` |
| Klangfarbe | `cos(timbre_fingerprint_lokal)`; × `(1 - min(1, (|Δavg_mids|+|Δavg_highs|)/2 / MIDS_HIGHS_DELTA_MAX))` | `MIDS_HIGHS_DELTA_MAX` — **vor dem Plan messen**: Einheit von `analyze_frequency_bands` (Anteile? dB?) an den 231 Tracks aus `kandidaten_v34.json` ablesen |
| Stimmung | `0.7*_normiert(Δbrightness_lokal, brightness_delta_max) + 0.3*_normiert(Δflatness_lokal, DEFAULT_FLATNESS_DELTA_MAX)`; `mood.key_mode` verschieden → `- MODE_SWITCH_PENALTY` (0.15, vorhanden); `mood.pssi_mood` beide vorhanden und verschieden → `- PSSI_MOOD_ABZUG` | `PSSI_MOOD_ABZUG = 0.10` |
| Lautheit (neu) | `1 - min(1, |Δlufs_lokal| / LUFS_DELTA_MAX_DB)` (0 dB → 1.0, ≥ 3 dB → 0) | `LUFS_DELTA_MAX_DB = 3.0` (Spec) |
| Struktur (neu) | `0.5*neuheit_b + 0.5*(1 if traegt_allein_b else 0)`; Label-Paar: `out_a.section_label in ("outro","breakdown")` oder `out_a.phrase_label in ("Outro","Down")` **und** `in_b.phrase_label == "Chorus"` oder `in_b.section_label == "drop"` → `+ STRUKTUR_LABEL_BONUS` (geklemmt auf 1) | `STRUKTUR_LABEL_BONUS = 0.10` |
| Vocals | beide `vocal_aktiv_lokal` → additiv `- VOCAL_CLASH_PENALTY` (0.06, vorhanden) auf den Gesamtscore | — |

Kombination: `playlist.combine_weighted(teilwerte, gewichte)` (None → Umverteilung,
nie 0). Gesamtscore in [0,1], danach Half/Double × 0.85 und Vocal-Abzug.

## 4. Gewichte

Spec: Summe 1.0, je Genre in `GENRE_TRANSITION_TOLERANCES`, per JSON
ueberschreibbar, Startwerte. Die heutigen acht `*_weight` (Summe 1.0) werden
von `calculate_enhanced_compatibility` (Track-Ebene) benutzt — sie duerfen
durch Teil 2 **nicht** verschoben werden. Entwurf: eigene Schluessel
`kandidaten_<faktor>_weight` (zehn Stueck), Startwerte = die acht Spec-Werte
proportional um die zwei neuen Gewichte (je 0.06) gestaucht, gerundet,
Summe exakt 1.0:

| Schluessel | Wert |
|---|---|
| kandidaten_harmonic_weight | 0.140 |
| kandidaten_bpm_weight | 0.106 |
| kandidaten_energy_weight | 0.106 |
| kandidaten_genre_weight | 0.106 |
| kandidaten_groove_weight | 0.264 |
| kandidaten_bass_weight | 0.070 |
| kandidaten_timbre_weight | 0.044 |
| kandidaten_mood_weight | 0.044 |
| kandidaten_loudness_weight | 0.060 |
| kandidaten_structure_weight | 0.060 |

`_validate_genre_tables` bekommt eine zweite Summenpruefung ueber diese zehn
Schluessel. `tolerances.write_override` (`alt_keys` :103) muss die neuen
Schluessel kennen. **Alternative** (dem Nutzer nennen): dieselben acht
Schluessel fuer beide Ebenen + zwei neue, Summe 1.12, `combine_weighted`
renormiert — widerspricht "Summe 1.0", daher nicht Entwurf.

## 5. Schritt 3 — Blendenlaengen

`bars_kurz, bars_lang = get_mix_profile(genre_a).transition_bars`
(Tuple). Je Kombination zwei `PairCandidate`s. Outro-Deckel:
`max_bars = floor((outro_start_a - out_a.t) / seconds_per_bar(bpm_a))`
(ganze Takte); `blend_bars = min(bars, max_bars)`; ergibt `blend_bars < 1`
→ Kombination faellt am Blenden-Gate. Half/Double: zusaetzlich
`min(blend_bars, 16)`. Beide Laengen koennen nach dem Deckel gleich werden →
dann nur ein `PairCandidate` (Dedupe ueber `(t_out, t_in, blend_bars)`).

## 6. Schritt 4 — Kontrast/Dedupe

- Schluessel einer Kombination: `(out_a.t, in_b.t)`. Zwei Kombinationen
  gelten als gleich, wenn `|Δt_out| < grid_sec_a` **und** `|Δt_in| < grid_sec_b`
  **und** dasselbe Hauptschema (`schema[0]` nach `SCHEMA_PRIORITAET`) auf
  beiden Seiten → zusammenlegen, bester Score bleibt, `schema`-Listen
  vereinigt.
- Kappung: max. `PAAR_MAX_KOMBINATIONEN = 6` Zeitpunkt-Kombinationen (× 2
  Blenden = max. 12). Mindestens eine Kombination je **vorhandenem** Schema
  (Schema kommt in irgendeinem Out- oder In-Kandidaten vor): fehlt ein Schema
  in den Top 6, ersetzt die beste Kombination mit diesem Schema die
  schlechteste Top-6-Kombination, deren Schemata anderweitig vertreten sind.

## 7. Schritt 5 — Ausgabe und Begruendung

`rang` 1..n nach Score (Tiebreak: Schema-Prioritaet von out, dann in, dann
kuerzere Blende zuerst — **Startregel**). `begruendung` wird aus den
Teilwerten erzeugt (kein freier Text): je Faktor ein Satzfragment aus einer
festen Tabelle (`">= 0.8 stark"`, `"0.5–0.8 mittel"`, `"< 0.5 schwach"`,
`None "nicht messbar"`), dazu Flags ("Bass-Swap noetig", "Half/Double, Cut ≤
16 Takte", "benannter Cue").

## 8. Werkzeug und Messung (kein Produktcode)

`tools/paar_kandidaten_messen.py --cache`: liest alle Tracks aus
`hpg_cache_v34.db`, bildet alle Paare innerhalb `PAAR_BPM_MAX`, zaehlt je
Paar `PairCandidate`s, Gate-Ausfaelle je Grund, Schemaverteilung der Rang-1,
Median-Score; JSON-Ausgabe. Pflichtzahlen fuer den Handoff Teil 2.

## 9. Was Teil 2 NICHT tut (→ Teil 4)

`Track.mix_in_point/mix_out_point` = Rang 1, Anbindung an
`calculate_enhanced_compatibility`/`scoring_context`, GUI, Export,
App-BPM-Default 2.0, `transition_type`-Wahl aus `bass_swap_pflicht`.

## 10. Vor dem Plan noch zu messen (keine Annahmen)

- Einheit/Spanne `avg_mids_lokal`/`avg_highs_lokal` (→ `MIDS_HIGHS_DELTA_MAX`).
- Spanne `bass_rms_dbfs` und `lufs_lokal` paarweise (→ Plausibilitaet 6 dB / 3 dB).
- Anteil Kandidaten mit `camelot_lokal == ""` (→ wie oft Harmonie umverteilt wird).
Alles aus `kandidaten_v34.json` der Messung vom 2026-08-22 ablesbar
(Scratchpad der Session; bei Verlust: `tools/kandidaten_messen.py --cache`).
