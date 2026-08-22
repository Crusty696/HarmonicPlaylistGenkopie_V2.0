# Handoff 2026-08-22: Mixpunkt-Kandidaten Teil 2 — Paarung und Bewertung gebaut

Vorheriger Stand: `docs/HANDOFF-2026-08-22-kandidaten-teil1.md` (Teil 1 abgeschlossen,
Realmessung). Plan: `docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil2-paarung.md`
(Waechter Tor 1: MIT AUFLAGEN, eingearbeitet; Tor 2 vor dem Merge).
Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md` Abschnitt 2.

## Was gebaut wurde (Branch `kandidaten-teil2`)

- `hpg_core/pair_candidates.py` (neu): `PairCandidate`, `pair_gate_reasons`,
  `blend_bars_options`, `score_pair` (zehn Teilwerte, Flags), `dedupe_and_cap`,
  `begruendung_aus_teilwerten`, `build_pair_candidates`. Reine Funktionen, kein
  Audio, nichts am Track veraendert (kein CACHE_VERSION-Bump).
- `hpg_core/models.py`: `camelot_relation_score` (Camelot-Tabelle als reine
  Funktion); `hpg_core/playlist.py` delegiert nach dem BPM-Gate (Verhalten
  unveraendert, Bestandstests unveraendert gruen).
- `hpg_core/genres.py`: zehn `kandidaten_*_weight` (Summe 1.0, validiert).
- `hpg_core/config.py`: Block "Paarung und Bewertung" (Gates, Startwerte,
  gemessene Normierungen).
- `tools/paar_kandidaten_messen.py` (`--cache` | `--json-tracks`).
- Tests: `tests/test_pair_candidates.py` (26), `tests/test_tools_paar_kandidaten_messen.py` (2),
  Ergaenzungen in `tests/test_config.py`, `tests/test_models.py`.
- Doku: `CLAUDE.md`, `.agents/skills/hpg-mixpoint-engineering/SKILL.md`,
  `.agents/skills/hpg-playlist-scoring/SKILL.md` (nach Merge nach `.claude/` spiegeln).

Suite im Worktree (HEAD `d5bb8d0`): **1816 passed, 25 warnings, 77 s, Exit 0**
(Coverage-Gate 70 bestanden).

## Die elf Entscheidungen (Spec offen, im Plan festgehalten)

1. Guard-Ausnahme nur fuer manuelle Cues mit `CUE_IN_PATTERN`/`CUE_OUT_PATTERN`
   (`_guard_frei` ueber `track.cue_points` + `mix_candidates._quantize`); "Drop 2"
   behaelt den Guard.
2. Pitch-Bedarf = `diff / bpm_a` (unter dem 2-BPM-Gate ab 50 BPM nie aktiv —
   Messung: Gate-Grund `pitch` nie ausgeloest).
3. Eigene Schluessel `kandidaten_*_weight` (Track-Gewichte unveraendert);
   Startwerte proportional gestaucht (0.140/0.106/0.106/0.106/0.264/0.070/0.044/0.044/0.060/0.060).
4. Harmonie-Gewicht x min(`key_confidence_lokal`).
5. Half/Double x 0.85 einmal auf den Gesamtscore, Blende <= 16 Takte.
6. Beide `kick_aktiv` → Flag `bass_swap_pflicht` + `KICK_KONFLIKT_ABZUG` 0.15 auf den
   Bass-Teilwert (Teil 4: bei Bass-/EQ-Swap entfaellt der Abzug).
7. Beide `percussive_ratio_lokal < 0.3` → Flag `lange_blende_erlaubt`, kein Score-Effekt.
8. Blende mindestens `MIN_TRANSITION_BARS` (8), sonst entfaellt die Laenge.
9. Dedupe: |dt| < Phrase − Toleranz beidseitig, gleiches Hauptschema, gleiche Blende;
   Vertreter verschiedener Schemata auf demselben Punkt werden vereinigt.
10. Rang-Tiebreak: Schema-Prioritaet out, in, kuerzere Blende.
11. Startwerte markiert; drei Normierungen gemessen (s. u.).

## Messung (Pflicht aus Plan Task 8)

`tools/paar_kandidaten_messen.py --json-tracks kandidaten_v34.json` auf den 231
Tracks der Teil-1-Messung, alle Permutationen innerhalb `PAAR_BPM_MAX`:

| Kennzahl | Wert |
|---|---|
| Paare im BPM-Gate | 14 186 |
| davon mit PairCandidates | 14 082 (99,3 %) |
| PairCandidates je Paar, Median | 12 (= 6 Kombinationen x 2 Blenden, Kappung greift) |
| Gate-Gruende | keine (alle Kombinationen bestehen — Teil 1 hat Intro/Outro, Coverage und Gitter schon erzwungen; `blend_bars_options` klemmt vor dem Gate) |
| Rang-1-Schema Out | pssi_phrase 13 237, sektion 778, analyzer 61, benannter_cue 6 |
| Rang-1-Schema In | pssi_phrase 13 243, sektion 759, analyzer 80 |
| Rang-1-Score, Median | 0.651 |
| Blendenlaengen (alle Kandidaten) | 32: 59 960, 16: 54 394, 64: 15 285, 8: 8 964; dazwischen Deckelwerte (Outro-Deckel auf ganze Takte) |
| Laufzeit | ~2 000 Paare / 18 s |

Gemessene Normierungen (Teil-1-Messung, 3 664 Kandidaten, paarweise Differenzen
innerhalb 2 BPM, p90): `BASS_RMS_DELTA_MAX_DB = 7.0`, `SYNCOPATION_DELTA_MAX = 0.3`,
`MIDS_HIGHS_DELTA_MAX = 5.0` (Details `docs/HANDOFF-2026-08-22-kandidaten-teil1.md`).

Befund: Rang 1 ist fast immer eine PSSI-Phrasengrenze — bei gleichem Score
entscheidet die Schema-Prioritaet (Tiebreak, Entscheidung 10); die Teilwerte
streuen innerhalb eines Paars wenig. Das ist genau das, was der Hoertest
(Teil 3) kalibrieren soll.

## Offen fuer Teil 3/4 (Waechter Tor 1, Auflage 7 — nicht vergessen)

- (a) GUI-Regler `main.py:1562-1567` und Hoertest-Fit `tools/rate_transitions.py`
  schreiben nur die alten `*_weight` — `kandidaten_*_weight` muessen in Teil 3
  (Fit → `candidate_preferences.json`) und Teil 4 (Regler "Lautheit") angebunden
  werden; `tolerances.write_override` summiert alle uebergebenen Schluessel gegen
  1.0 (die zehn Kandidaten-Gewichte duerfen nicht in diese Summe).
- (b) `KICK_KONFLIKT_ABZUG` entfaellt in Teil 4 bei Bass-/EQ-Swap (Score wird
  uebergangstyp-abhaengig); Flag `bass_swap_pflicht` soll dort den Uebergangstyp
  waehlen.
- (c) `blend_bars` ist kein Score-Merkmal (Docstring `score_pair`).
- (d) Pitch-Gate rechnerisch nie aktiv (Spec-Gate, bleibt).
- (e) Teil-1-Startwerte `KICK_AKTIV_*` markieren fast nie einen Kick (82/3664) —
  Hoertest/Teil 3 pruefen.
- Rang-1 → `Track.mix_in_point/mix_out_point`, `calculate_enhanced_compatibility`,
  `scoring_context`, GUI, Export, App-BPM-Default 2.0: Teil 4.
