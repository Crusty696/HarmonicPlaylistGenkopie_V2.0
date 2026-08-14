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

## Common Mistakes

- Score-Tabelle aendern, ohne `tests/test_compatibility.py` und
  `tests/test_scoring_contract.py` vorher zu lesen.
- KI-Bonus doppelt zaehlen.
- `scoring_context` in einem der fuenf Konsumenten vergessen.
- Neue Strategie ohne Eintrag in `STRATEGIES` **und** ohne Pruefung, welche
  Advanced-Parameter sie wirklich konsumiert (die UI graut nicht-genutzte
  Parameter ueber `apply_strategy_support` aus).
- `+-1` (80) ist fest — nie mit `loose_factor` multiplizieren.
