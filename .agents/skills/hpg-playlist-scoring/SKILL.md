---
name: hpg-playlist-scoring
description: Use when working on HPG playlist generation or scoring — die 8 Strategien, calculate_compatibility / calculate_enhanced_compatibility, Camelot-Punktetabelle, BPM-Hard-Gate und Half/Double, harmonic_strictness, scoring_context, calculate_playlist_quality, TransitionPlan, predict_transition_type oder SetTimeline.
---

# HPG Playlist & Scoring

## Die 8 Strategien

`STRATEGIES` [playlist.py:1864] — Harmonic Flow · Warm-Up · Cool-Down ·
Peak-Time · Energy Wave · Genre Flow · Consistent · Context Flow.

`STRATEGY_ALIASES` [playlist.py:1902] haelt alte Namen gueltig:
`Harmonic Flow Enhanced` -> `Harmonic Flow`, `Peak-Time Enhanced` ->
`Peak-Time`, `Emotional Journey` -> `Context Flow`. `generate_playlist` loest
sie auf. Alte Doku nennt 10-11 Strategien — das ist ueberholt.

## Zwei Score-Ebenen

| Funktion | Skala | Rolle |
|---|---|---|
| `calculate_compatibility` [:501] | 0-100 | **reine Harmonik** |
| `calculate_enhanced_compatibility` [:256] | `TransitionMetrics` | Harmonik + BPM-Smoothness + Energy-Flow + Genre + KI-Bonus |

Der KI-Bonus wird **nur** im Enhanced-Pfad addiert (F05). Wer ihn zusaetzlich
in `calculate_compatibility` addiert, zaehlt doppelt und verfaelscht
`predict_transition_type` und die Qualitaetsanzeige.

## Camelot-Punktetabelle (`_calculate_compatibility_inner` [:399])

Reihenfolge der Zweige ist bindend — der erste Treffer gewinnt:

| Relation | Score | Bedingung |
|---|---|---|
| BPM-Gate | `0` | `effective_bpm_diff > bpm_tolerance` -> sofort raus |
| kein/ungueltiger Camelot-Code | `10` | mit Half/Double-Penalty |
| gleiche Tonart | `100` | |
| `A -> B`, gleiche Zahl | `90` | relativ Moll->Dur, Energy Boost |
| `B -> A`, gleiche Zahl | `85` | Dur->Moll, Energy Drop |
| `+-1`, gleicher Modus | `80` | Quintschritt, **fest** |
| `+2`, gleicher Modus | `75` | * `loose_factor` |
| `+4`, gleicher Modus | `70` | * `loose_factor`, nur `allow_experimental` |
| `+7`, gleicher Modus | `65` | * `loose_factor`, nur `allow_experimental` |
| diagonal (`+-1`, Modus wechselt) | `60` | * `loose_factor` |
| Rest | `max(5, 15 - strictness)` | |

`loose_factor = max(0.4, min(1.0, 1.0 - (strictness - 7) * 0.08))` —
**Obergrenze 1.0** (F03). Vorher ging der Faktor bis 1.2: bei niedriger
Strictness stieg `+4` damit auf 84 und ueberholte den sicheren `+-1`-Move
(feste 80). Der `+-1`-Wert ist bewusst **nicht** skaliert — er ist die
Rang-Obergrenze der lockeren Techniken. Wuerde man ihn mitskalieren, faellt er
bei `strictness > 7` unter die riskanteren Zweige und die Rangordnung
100 > 90/85 > 80 > 75 > 70 > 65 > 60 bricht zusammen.

Alle Scores werden zusaetzlich mit `penalty = BPM_HALF_DOUBLE_PENALTY = 0.85`
multipliziert, wenn die Relation nicht `direct` ist.

**Rechenbeispiel:** 8A/140 gegen 10A/140 -> `+2`-Zweig ->
`int(75 * 1.0 * 1.0)` = **75**. 8A/140 gegen 8A/70 -> `effective_bpm_diff`
liefert `(0.0, "half")`, Gate passiert, gleiche Tonart -> `int(100 * 0.85)` =
**85**.

## effective_bpm_diff [models.py:110]

Misst **immer im Tempo-Raum von bpm1** (Track A bleibt laufen):
`|b1-b2|` direct, `|b1-b2*2|` half, `|b1-b2/2|` double, `min()` gewinnt.
Gespiegelte Kandidaten sind bewusst raus (F01) — sonst war das Gate bei
Half/Double doppelt so lax. `BPM_HALF_DOUBLE_ENABLED=False` schaltet auf
reines `direct`.

## scoring_context — die HPG-001-Regel

`resolve_scoring_context(mode, advanced_params)` [playlist.py:1909] liefert
genau die Scoring-Parameter, die die gewaehlte Strategie beim Sortieren
wirklich nutzt (Strategien ohne `harmonic_strictness` liefern `{}`).

**Anzeige, Reorder, Preview, Quality und Empfehlungen muessen exakt diesen
Kontext durchreichen.** Sonst optimiert die Sortierung gegen ein anderes Ziel
als die Zahl, die der Nutzer sieht. `calculate_playlist_quality(tracks,
bpm_tolerance, scoring_context)` [:1649] mittelt denselben erweiterten Score.

## Caches

`_COMPAT_CACHE` und `_ENHANCED_COMPAT_CACHE` sind Modul-Globals, die nur
waehrend `generate_playlist`/`benchmark` gesetzt sind. Direkte API-Aufrufe
laufen bewusst ungecacht. Cache-Key nutzt `_track_cache_key` (Track-Identitaet),
nicht Deep-Compare — `Track` ist `@dataclass(eq=False)` mit `__eq__`/`__hash__`
ueber `track_id` [models.py:135].

## Transition-Ebene

`predict_transition_type` [:1223] waehlt aus: `smooth_blend`, `bass_swap`,
`breakdown_bridge`, `drop_cut`, `filter_ride`, `halftime_switch`, `echo_out`,
`cold_cut`, `pro_eq_swap`. `compute_transition_recommendations` [:1459] baut
daraus `TransitionRecommendation` + `TransitionPlan` (der **eine** Timing-
Vertrag Richtung Renderer und Anzeige).

`SetTimeline` / `compute_set_timeline` [:2172] liefert die Zeitleisten-Ansicht
(Phasen, Peak-Track, Energie-Kurve).

## Camelot-Tabelle als reine Funktion (2026-08-22)

`models.camelot_relation_score(code_a, code_b, *, harmonic_strictness=7,
allow_experimental=True, penalty=1.0) -> int` traegt die Punktetabelle oben;
`_calculate_compatibility_inner` prueft nur noch das BPM-Gate und delegiert
(`penalty` = `BPM_HALF_DOUBLE_PENALTY` bei half/double). Dieselbe Tabelle
bewertet in `hpg_core/pair_candidates.py` die lokalen `camelot_lokal` der
Mixpunkt-Kandidaten. `playlist._get_camelot_components` bleibt, weil
`tests/test_compatibility.py` es von dort importiert.

## Kandidaten-Gewichte (2026-08-22)

`genres._TOLERANCE_DEFAULTS` traegt neben den acht Track-Gewichten
(`*_weight`, Summe 1.0, unveraendert) zehn `kandidaten_*_weight`
(harmonic .140, bpm .106, energy .106, genre .106, groove .264, bass .070,
timbre .044, mood .044, loudness .060, structure .060; Summe 1.0, von
`_validate_genre_tables` geprueft) fuer die Paar-Bewertung der Kandidaten —
STARTWERTE. Seit Teil 4: `tolerances.write_override_kandidaten(gewichte)`
schreibt die uebergebenen `kandidaten_*_weight` und skaliert die uebrigen auf
Summe 1.0 (GUI-Regler "Lautheit (Kandidaten)"); `write_override` (Track-Regler)
erhaelt vorhandene Kandidaten-Schluessel. Eine Hoertest-Praeferenz
(`candidate_preferences`) fuer das Genre hat Vorrang vor den Toleranzen.

## Kandidatenpfad in der App (Teil 4, gebaut 2026-08-22)

Plan `docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil4-app.md`.
- `calculate_enhanced_compatibility`: tragen beide Tracks Kandidaten und liegt
  das Paar im BPM-Gate, liefert `_kandidaten_fuer_paar` (Modul-Cache
  `_PAIR_CANDIDATE_CACHE`, dauerhaft; `reset_pair_candidate_cache()` wird von
  `candidate_choices`, `candidate_preferences.reset_cache`, `tolerances.reset_cache`
  gerufen) die `PairCandidate`s in App-Reihenfolge; Rang 1 traegt
  `overall_score` (= `kandidat.score` + `ai_bonus`, BPM-Hard-Gate bleibt),
  `groove/bass/timbre/mood_match` = lokale Teilwerte, neue Felder
  `loudness_match`, `structure_match`, `kandidat` (Dict). Ohne Kandidaten:
  heutiger Pfad unveraendert.
- `compute_transition_recommendations`: nach DJ-Brain, vor Clamp setzt der
  aktive Kandidat `mix_out_a/mix_in_b/overlap`; `transition_type = "bass_swap"`
  bei `flags.bass_swap_pflicht`; `TransitionRecommendation.kandidaten` (alle,
  to_dict), `kandidat_aktiv` (Rang, 0 = keiner) und `kandidat_konsistent`.
  **Kettenwahl** `_kette_waehlen` (DP ueber die Paare): je Track muss der
  Mix-Out (Paar i) mindestens zwei Phrasen hinter dem Mix-In (Paar i−1) liegen
  (Toleranz `QUANTIZE_TOLERANCE_SEC`); maximale Score-Summe, gespeicherte Wahl
  mit `_WAHL_BONUS` = 10; ohne konsistenten Anschluss Neustart mit
  `kandidat_konsistent = False`. Der aktive Kandidat ist daher nicht zwingend
  Rang 1; `compatibility_score` der Karte stammt aus den Metriken (= Rang 1).
  Messung 2026-08-22 (231 Tracks): Cue-Gate-Verletzungen 73 → 2. **Track-Felder werden nicht
  mutiert** — "Rang 1" lebt im Plan; Leser: Preview, Timeline, Tabelle Mix-In/
  Out (`mixpunkte_fuer_tabelle`), `on_ai_finished`, Export.
- `rank_pair_candidates`/`select_pair_candidate` (pair_candidates): gespeicherte
  Wahl (`candidate_choices.hole`) nach vorn, Tiebreak `schema_rang` aus dem
  Hoertest, `bass_swap_geplant=True` (kein `KICK_KONFLIKT_ABZUG`, Flag bleibt).
- HPG-001: die Wahl liegt NICHT im `scoring_context`, sondern in der Datei —
  alle Konsumenten lesen sie auf demselben Weg (Abweichung vom Spec-Wortlaut,
  benannt im Handoff Teil 4). Sechster Konsument: Kandidatentabelle.
- Laufzeit: `build_pair_candidates` 3,3 ms Median je Paar (500 Paare, 2026-08-22,
  nach Optimierung; vorher 8,7 ms) — deshalb Cache + BPM-Gate vor dem
  Kandidatenpfad; Generierung Harmonic Flow 231 Tracks ~52 s (2 s ohne Kandidaten).
- Paar-Gates seit Teil 4 zusaetzlich `blende_ueber_b_ende`; `_outro_overlap_limit`
  rechnet mit `QUANTIZE_TOLERANCE_SEC` Spielraum vor dem Takt-Floor.
- Messwerkzeug: `tools/playlist_kandidaten_messen.py --cache` (vergleicht den
  aktiven Ketten-Kandidaten, Kennzahl `kette_neustarts`).
- App-BPM-Default 2.0 (main.py: Slider, `current_bpm_tolerance`,
  `AnalysisWorker`, `PlaylistPanel`); `playlist.py`-API-Defaults bleiben 3.0.

## Common Mistakes

- Score-Tabelle aendern, ohne `tests/test_compatibility.py` und
  `tests/test_scoring_contract.py` vorher zu lesen.
- KI-Bonus doppelt zaehlen.
- `scoring_context` in einem der fuenf Konsumenten vergessen.
- Neue Strategie ohne Eintrag in `STRATEGIES` **und** ohne Pruefung, welche
  Advanced-Parameter sie wirklich konsumiert (die UI graut nicht-genutzte
  Parameter ueber `apply_strategy_support` aus).
- `+-1` (80) ist fest — nie mit `loose_factor` multiplizieren.
