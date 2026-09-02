---
name: hpg-mixpoint-engineering
description: Use when touching HPG mix points — mix_in_point/mix_out_point, Phrasen-Quantisierung, phrase_anchor/first_downbeat, calculate_genre_aware_mix_points, calculate_paired_mix_points, align_ai_mix_points, adjusted_mix_out_a/adjusted_mix_in_b, DJRecommendation oder Transition-Timing. Vor jedem Lesen oder Aendern dieser Logik.
---

# HPG Mixpoint Engineering

## Das Grundgesetz

Ein Track hat **einen Anker** und **ein Gitter**. Jeder Zeitpunkt, der in
`Track.mix_in_point` / `mix_out_point` oder in einen `TransitionPlan` landet,
muss auf diesem Gitter liegen.

```
grid  = seconds_per_bar(bpm) * profile.phrase_unit      # METER = 4
mix_in  = quantize_to_grid(t, grid, anchor, "ceil")     # nie VOR dem Ereignis
mix_out = quantize_to_grid(t, grid, anchor, "floor")    # nie NACH dem Ereignis
```

`quantize_to_grid` [models.py:50] ist die einzige erlaubte Quantisierung fuer
`Track.mix_in_point`/`mix_out_point`. Fuer das unregelmaessige PSSI-Gitter
(Phrasenlaengen variieren) kommt zusaetzlich `quantize_to_points`
[mix_candidates.py] dazu — gleiche `ceil`/`floor`-Toleranz
(`QUANTIZE_TOLERANCE_SEC`), aber gegen eine sortierte Punktliste statt gegen
ein festes Raster. Keine Inline-Formeln, keine `round(x, 2)` innerhalb der
Kette — gerundet wird erst an der Anzeige-/Exportgrenze (R9/N15).

## Zwei Anker, zwei Aufgaben — nicht verwechseln

| Anker | Feld | Wofuer |
|---|---|---|
| Takt-Anker | `Track.first_downbeat` | wo die "1" liegt; Untergrenze `min_mix_in` |
| Phrasen-Anker | `Track.phrase_anchor` | das **Gitter** (`anchor`-Parameter) |

`phrase_anchor` [models.py:226] liefert `first_phrase` nur, wenn **alle drei**
Gates halten:

```python
first_phrase >= 0.0                          # -1.0 = nicht geschaetzt
and downbeat_confidence > 0.0                # kein erfundenes Raster
and phrase_confidence >= PHRASE_CONFIDENCE_MIN   # config.py:34, = 0.25
```

sonst `first_downbeat`.

**Warum getrennt (AUDIT-FIX R3):** `phrase_anchor` kann bis zu
`phrase_unit - 1` Bars hinter dem ersten Downbeat liegen (~28 s bei 16-Bar-
Phrasen). Wuerde `min_mix_in` daran haengen, wandert die Untergrenze mit und
das Mix-Fenster kollabiert in den Notfall-Prozent-Pfad. Deshalb nimmt
`calculate_genre_aware_mix_points` den `first_downbeat` als eigenen Parameter.

## Wer setzt Track-Mixpoints (Stand heute: 3 Quellen)

| # | Quelle | Ort | Bedingung |
|---|---|---|---|
| A | `calculate_genre_aware_mix_points` | dj_brain.py:109 | Sections vorhanden |
| B | `analyze_structure_and_mix_points` | analysis.py:1197 | **reine Fassade** — RMS-Aktivitaet -> 3 Pseudo-Sektionen -> delegiert an A |
| C | Rekordbox-Cue-Vorschlag | analysis.py | gerichteter manueller Cue; nach `align_ai_mix_points` nur Uebernahme, wenn das finale Paar den harten Vertrag ohne Sonderrechte erfuellt |

Zugewiesen wird **nur** im `Track(...)`-Konstruktor [analysis.py:1947 und
:2364]. Es gibt kein `track.mix_in_point = ...` irgendwo im Produktivcode
(per grep verifiziert).

**Korrektur gegenueber aelteren Notizen:** Es gibt **keinen** vierten
LLM-Schreibpfad mehr. Der AI-Auto-Apply-Block wurde entfernt; `ai_engine`
liefert Mixpoints nur mit `"mixpoints_advisory": True` [ai_engine.py:132] und
verwirft sie ganz, wenn `outro_covered` falsch ist [ai_engine.py:118].
"Letzter Schreibzugriff gewinnt" gilt nicht mehr.

## Paar-Ebene (ueberschreibt den Track NICHT)

`calculate_paired_mix_points(track_a, track_b)` [dj_brain.py:702]
- Overlap = `min(Intro-Dauer B, Outro-Dauer A)`
- loest das Problem, dass ein per-Track-Mix-In den Partner nicht kennt
- quantisiert **immer** am Ende (B1) mit `anchor_a`/`anchor_b` aus
  `phrase_anchor`
- `duration <= 0` -> Track-Werte unveraendert lassen (N4)

`generate_dj_recommendation` [dj_brain.py:500] fuellt
`DJRecommendation.adjusted_mix_out_a` / `adjusted_mix_in_b` /
`overlap_seconds`, Sentinel `-1.0`.

Aufloesung zur Renderzeit: `resolve_transition_mix_points(transition)`
[main.py:177] — Prioritaet `plan` > `dj.adjusted_*` (nur bei `>= 0.0`) >
`track.mix_*_point` > Fallback 16.0 s. **Diese Funktion ist die einzige
erlaubte Aufloesung**; sie ersetzt drei frueher kopierte Varianten.

## Sentinel-Regel

`MIX_POINT_UNSET = -1.0` [config.py:26]. `0.0` ist ein **gueltiger** Mixpoint
(Track-Anfang).

```python
if mix_out >= 0.0:   # richtig
if mix_out > 0:      # FALSCH — verwirft den Mixpoint bei t=0
```

Anzeige: `format_mix_point_display` [main.py:211] zeigt `--:-- (- bars)` bei
negativem Wert.

## Invarianten (bei jeder Aenderung pruefen)

1. `0 <= mix_in < mix_out <= duration`
2. beide auf `anchor + k*grid`
3. `mix_out - mix_in >= 2 * grid` (`min_window`, 2 Phrasen)
4. Mix-In strikt `> intro_end + QUANTIZE_TOLERANCE_SEC`, Mix-Out strikt
   `< outro_start - QUANTIZE_TOLERANCE_SEC`; Grenze und Sicherheitsband sind
   ausgeschlossen
5. Mixpoints nie innerhalb Intro/Outro, auch nicht bei manuellen Cues (Spec:
   `docs/superpowers/specs/2026-03-11-mix-point-intro-outro-guard-design.md`)
6. Einheiten: Sekunden intern, Bars nur zur Anzeige
   (`mix_in_bars`/`mix_out_bars`), Samples nur im Renderer

Test-Helfer: `assert_mix_points_valid` [tests/conftest.py:218],
`assert_phrase_aligned` [tests/conftest.py:247].

## phrase_unit

Kommt aus `GENRE_MIX_PROFILES[genre].phrase_unit`, erlaubt sind nur 8/16/32
(erzwungen von `_validate_genre_tables`). Psytrance/Trance = 16, sonst
ueberwiegend 8. Ableitung fuer den Struktur-Analyzer:
`GENRE_PHRASE_UNITS` [structure_analyzer.py]. Details: Skill `hpg-genres`.

## Notfall-Pfade

Kollabiert das Fenster (`max_mix_out - min_mix_in < min_window`), greifen
Prozent-Fallbacks `duration * 0.15 / 0.85`. Auch die werden seit N5
nachtraeglich aufs Gitter quantisiert, sofern das gueltig bleibt. Wer diese
Pfade anfasst: das Ergebnis muss weiterhin Invariante 1 und 2 erfuellen.

## DJ-Praxis-Referenz (Recherche 2026-07, 26 Quellen)

Techno 16 Bars Standard-Blend, 32 Sweet Spot, Bass-Swap hart auf der
Phrasengrenze. Psytrance: Dark 8-16, Full-On 16-32, Progressive 32-64.
Uplifting Trance 32-64+. Nie zwei Basslines gleichzeitig. Pitch max +-3-4 %.

## Kandidaten Teil 1 (gebaut 2026-08-21)

Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`.
Pro Track `mix_in_candidates` / `mix_out_candidates`: Listen von
`MixCandidate` (`hpg_core/mix_candidates.py`) mit lokalen Messwerten im
Fenster +-1 Phrase um `t` (Struktur/Neuheit, Rhythmus, Bass, Harmonie,
Klangfarbe, Energie/LUFS, Stimmung/Vocals) plus `schema`, `provenance`,
`confidence`. Beide Analysepfade rufen `build_track_candidates` ueber den
Helfer `_kandidaten_berechnen` in `analysis.py`, **nach** den
Track-Mixpoints; Fehler dort kippen die Analyse nie (leere Listen).

**Sechs Schemata** (Nutzer-Entscheidung B), Prioritaet in
`SCHEMA_PRIORITAET`: `benannter_cue` > `pssi_phrase` > `auto_cue` >
`analyzer` > `sektion` > `energie_neuheit`.

**Gates** (`passes_track_gates`, je Kandidat): Intro/Outro-Guard,
`unanalysed`-Sektionen ausgeschlossen (Coverage), Quantisierung auf das
Gitter mit `QUANTIZE_TOLERANCE_SEC` = 0.05 s Toleranz (PSSI-Gitter via
`quantize_to_points`, sonst `quantize_to_grid`), Mindestfenster 2 Phrasen zur
jeweils anderen Seite. Gerichtete manuelle Cues bleiben der IN-/OUT-Seite
zugeordnet; das Richtungsflag ist nur Herkunftsinformation. Nach der
Quantisierung durchlaufen alle Quellen dieselben Gates, ohne Cue-Ausnahme.

**Kappung** auf `KANDIDATEN_MAX_JE_SEITE` (config.py, = 8): sortiert nach
Prioritaet, dann Schema-Anzahl (mehr Quellen am selben Gitterpunkt gewinnen),
dann Zeit — In-Seite frueh zuerst, Out-Seite spaet zuerst (der Tiebreak folgt
der musikalischen Rolle: Out-Punkte nahe am Outro ueberleben eher).

Cue-Positionsheuristik ("2. Cue = Mix-In, letzter = Mix-Out") ist entfernt.
`Track.mix_in_point`/`mix_out_point` bleiben in Teil 1 weiterhin Analyzer +
benannter Cue nach demselben harten Vertrag — die Rang-1-Auswahl aus der Paar-Bewertung ist
Teil 2/4. Dieser historische Teil-1-Bump fuehrte zu CACHE_VERSION 34;
aktuell ist CACHE_VERSION 42.

## Kandidaten Teil 2 (gebaut 2026-08-22) — Paarung und Bewertung

Modul `hpg_core/pair_candidates.py`, Plan
`docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil2-paarung.md`.
`build_pair_candidates(track_a, track_b, *, energy_direction=None,
harmonic_strictness=7, allow_experimental=True, tolerances=None)` liefert
sortierte `PairCandidate`s (`out_a`, `in_b`, `blend_bars`, `overlap_sec`,
`score`, `teilwerte`, `flags`, `begruendung`, `rang`, `bpm_relation`).
Reine Funktionen, kein Audio, **nichts wird am Track veraendert** (kein
CACHE_VERSION-Bump); `Track.mix_in_point/mix_out_point` bleiben bis Teil 4
unveraendert.

- **Gates** (`pair_gate_reasons`, Gruende stabil benannt): `bpm` (effektiv
  > `PAAR_BPM_MAX` 2.0), `pitch` (`diff/bpm_a` > 4 %, unter dem 2-BPM-Gate
  rechnerisch nie aktiv), `coverage` (`unanalysed`), `outro_covered`,
  `blende_im_outro` (`out_a.t + blend <= Outro-Start`), `in_im_intro`,
  `in_ausserhalb`, `gitter_out/gitter_in` (PSSI-Gitter bzw. Phrasenraster,
  `QUANTIZE_TOLERANCE_SEC`). `out_im_outro`, `in_im_intro` und
  `blende_im_outro` gelten auch fuer gerichtete manuelle Cues;
  `_ist_benannter_cue` setzt ausschliesslich ein Herkunfts-/Begruendungsflag.
- **Blenden** (`blend_bars_options`): `get_mix_profile(genre_a).transition_bars`
  (beide), Outro-Deckel auf ganze Takte, Half/Double `<= 16`, unter
  `MIN_TRANSITION_BARS` (8) entfaellt die Laenge.
- **Score** (`score_pair`): zehn Teilwerte je [0,1] oder None — harmonic
  (`models.camelot_relation_score` auf `camelot_lokal`, Gewicht x
  min(`key_confidence_lokal`)), bpm (`exp(-diff/1.0)`), energy (Richtung +
  `energy_trend`), genre, groove (0.6 Bass/0.4 Onset, `_spreize`, Syncopation,
  percussive > 0.7 Abzug / < 0.3 Flag), bass (sub/punch, `bass_rms_dbfs`,
  beide `kick_aktiv` -> Flag `bass_swap_pflicht` + Abzug), timbre (+ Mitten/
  Hoehen-Delta), mood (+ Dur/Moll -0.15, PSSI-mood), loudness (|dLUFS| 0 -> 1,
  >= 3 dB -> 0), structure (`neuheit`, `traegt_allein`, Label-Bonus).
  Kombination `playlist.combine_weighted` mit `kandidaten_*_weight` (zehn,
  Summe 1.0, `genres._TOLERANCE_DEFAULTS`, JSON-Override); Half/Double x 0.85
  einmal auf den Gesamtscore; Vocals beidseitig -0.06. `combine_weighted` kann
  intern fehlende Werte renormieren, aber `rank_pair_candidates` akzeptiert
  nur Kandidaten mit allen zehn endlichen lokalen Teilwerten. Renormierung
  kann also keinen unvollstaendig gemessenen `TransitionPlan` retten.
  KI-Metadaten beeinflussen weder `PairCandidate.score` noch
  `TransitionMetrics.overall_score`; `ai_bonus` bleibt immer 0.0.
  `blend_bars` ist kein
  Score-Merkmal (Spec Abschnitt 1: widerlegt).
- **Dedupe/Kappung** (`dedupe_and_cap`): gleiche Kombination = |dt| < Phrase -
  Toleranz beidseitig, gleiches Hauptschema, gleiche Blende; max.
  `PAAR_MAX_KOMBINATIONEN` 6 Zeitpunkt-Kombinationen x 2 Blenden; je
  vorhandenem Schema mindestens eine Kombination; Vertreter verschiedener
  Schemata auf demselben Punkt werden vereinigt.
- **Begruendung** nur aus Teilwerten/Flags (`begruendung_aus_teilwerten`).
- Alle neuen Zahlen ausser Spec-Werten sind STARTWERTE (`config.py`, Block
  "Paarung und Bewertung"); der Hoertest (Teil 3) ersetzt sie.
- Messung: `tools/paar_kandidaten_messen.py --cache | --json-tracks <json>`.
- Gewichtsquelle in `score_pair` (Teil 3): explizites `tolerances` > Praeferenzen
  aus `hpg_core/candidate_preferences.py` (Hoertest-Fit) > `get_tolerances(genre)`.
- Teil 4 (App): `rank_pair_candidates`/`select_pair_candidate` — gespeicherte
  Wahl (`candidate_choices`) nach vorn, Tiebreak `schema_rang` (auch fuer das
  Hauptschema), `bass_swap_geplant=True`; "Rang 1" lebt im `TransitionPlan`,
  `Track.mix_in_point/mix_out_point` bleiben Analyse-Werte (Abweichung vom
  Spec-Wortlaut, benannt).
- Teil 4 (App, Fortsetzung): Kettenwahl `playlist._kette_waehlen` (DP, Mix-Out
  von Paar i mindestens zwei Phrasen hinter dem Mix-In von Paar i−1 desselben
  Tracks, `kandidat_konsistent`); neues Paar-Gate `blende_ueber_b_ende`;
  `_outro_overlap_limit` mit `QUANTIZE_TOLERANCE_SEC` vor dem Floor;
  `KICK_KONFLIKT_ABZUG` entfaellt bei `bass_swap_geplant=True`; alle fuenf
  sichtbaren Regler (Groove, Bassdruck, Klangfarbe, Stimmung, Lautheit) sind
  `kandidaten_*_weight` und beeinflussen nur Mixpoint-Kandidaten. Die anderen
  fuenf Kandidatengewichte stammen aus Hoertestpraeferenzen oder den
  Toleranzvorgaben. Die Wahl
  liegt in `candidate_choices.json`, NICHT im `scoring_context` (Entscheidung 7).
  Teile 1–4 sind gebaut; offen sind nur Hoerproben (Handoff Teil 4).

Der App-Regler `bpm_tolerance` (1–2 BPM) ist das aeussere Gate fuer den
`TransitionPlan`; `PAAR_BPM_MAX = 2.0` bleibt die absolute Obergrenze. Eine
Nachbarkante ausserhalb des eingestellten Gates bleibt sichtbar als
`UNGEPLANT` mit Score 0 und darf nicht gerendert werden.

## Common Mistakes

- `> 0` statt `>= 0.0` gegen den Sentinel pruefen.
- `phrase_anchor` als Untergrenze fuer `min_mix_in` benutzen (R3).
- Neue Mixpoint-Quelle ohne `align_ai_mix_points`/`quantize_to_grid` einbauen.
- Inline `(60/bpm)*4` statt `seconds_per_bar()` — es gab 14 solche Kopien.
- Innerhalb der Kette runden.
- Mixpoint-Logik aendern ohne `CACHE_VERSION`-Bump -> Skill
  `hpg-cache-persistence`.
- In `pair_candidates` `playlist` auf Modulebene importieren (Importzyklus ab
  Teil 4) — nur lazy in Funktionen.
- `"benannter_cue" in schema` oder ein passendes IN/OUT-Muster als
  Guard-Ausnahme lesen — es gibt keine Cue-Sonderrechte.
