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

`quantize_to_grid` [models.py:25] ist die **einzige** erlaubte Quantisierung.
Keine Inline-Formeln, keine `round(x, 2)` innerhalb der Kette — gerundet wird
erst an der Anzeige-/Exportgrenze (R9/N15).

## Zwei Anker, zwei Aufgaben — nicht verwechseln

| Anker | Feld | Wofuer |
|---|---|---|
| Takt-Anker | `Track.first_downbeat` | wo die "1" liegt; Untergrenze `min_mix_in` |
| Phrasen-Anker | `Track.phrase_anchor` | das **Gitter** (`anchor`-Parameter) |

`phrase_anchor` [models.py:149] liefert `first_phrase` nur, wenn **alle drei**
Gates halten:

```python
first_phrase >= 0.0                          # -1.0 = nicht geschaetzt
and downbeat_confidence > 0.0                # kein erfundenes Raster
and phrase_confidence >= PHRASE_CONFIDENCE_MIN   # config.py:29, = 0.25
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
| A | `calculate_genre_aware_mix_points` | dj_brain.py:106 | Sections vorhanden |
| B | `analyze_structure_and_mix_points` | analysis.py:1019 | **reine Fassade** — RMS-Aktivitaet -> 3 Pseudo-Sektionen -> delegiert an A |
| C | Rekordbox-Cue-Override | analysis.py:1448 | Cues matchen Wortgrenzen-Regex, dann `align_ai_mix_points` |

Zugewiesen wird **nur** im `Track(...)`-Konstruktor [analysis.py:1666 und
:1928]. Es gibt kein `track.mix_in_point = ...` irgendwo im Produktivcode
(per grep verifiziert).

**Korrektur gegenueber aelteren Notizen:** Es gibt **keinen** vierten
LLM-Schreibpfad mehr. Der AI-Auto-Apply-Block wurde entfernt; `ai_engine`
liefert Mixpoints nur mit `"mixpoints_advisory": True` [ai_engine.py:123] und
verwirft sie ganz, wenn `outro_covered` falsch ist [ai_engine.py:108].
"Letzter Schreibzugriff gewinnt" gilt nicht mehr.

## Paar-Ebene (ueberschreibt den Track NICHT)

`calculate_paired_mix_points(track_a, track_b)` [dj_brain.py:627]
- Overlap = `min(Intro-Dauer B, Outro-Dauer A)`
- loest das Problem, dass ein per-Track-Mix-In den Partner nicht kennt
- quantisiert **immer** am Ende (B1) mit `anchor_a`/`anchor_b` aus
  `phrase_anchor`
- `duration <= 0` -> Track-Werte unveraendert lassen (N4)

`generate_dj_recommendation` [dj_brain.py:433] fuellt
`DJRecommendation.adjusted_mix_out_a` / `adjusted_mix_in_b` /
`overlap_seconds`, Sentinel `-1.0`.

Aufloesung zur Renderzeit: `resolve_transition_mix_points(transition)`
[main.py:174] — Prioritaet `plan` > `dj.adjusted_*` (nur bei `>= 0.0`) >
`track.mix_*_point` > Fallback 16.0 s. **Diese Funktion ist die einzige
erlaubte Aufloesung**; sie ersetzt drei frueher kopierte Varianten.

## Sentinel-Regel

`MIX_POINT_UNSET = -1.0` [config.py:21]. `0.0` ist ein **gueltiger** Mixpoint
(Track-Anfang).

```python
if mix_out >= 0.0:   # richtig
if mix_out > 0:      # FALSCH — verwirft den Mixpoint bei t=0
```

Anzeige: `format_mix_point_display` [main.py:208] zeigt `--:-- (- bars)` bei
negativem Wert.

## Invarianten (bei jeder Aenderung pruefen)

1. `0 <= mix_in < mix_out <= duration`
2. beide auf `anchor + k*grid`
3. `mix_out - mix_in >= 2 * grid` (`min_window`, 2 Phrasen)
4. `max_mix_out = min(outro_start, duration - grid)` — Mix-Out **auf** der
   Outro-Grenze ist DJ-Standard, nicht davor
5. Mixpoints nie innerhalb Intro/Outro (Spec:
   `docs/superpowers/specs/2026-03-11-mix-point-intro-outro-guard-design.md`)
6. Einheiten: Sekunden intern, Bars nur zur Anzeige
   (`mix_in_bars`/`mix_out_bars`), Samples nur im Renderer

Test-Helfer: `assert_mix_points_valid` [tests/conftest.py:216],
`assert_phrase_aligned` [tests/conftest.py:245].

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

## Kandidaten-Design (2026-08-21, genehmigt, noch nicht gebaut)

Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`.
Kern: pro Track `mix_in_candidates` / `mix_out_candidates` (`MixCandidate`
mit lokalen Messwerten an der Naht: Struktur/Neuheit, Rhythmus, Bass, Harmonie,
Klangfarbe, Energie/LUFS, Stimmung, Vocals, Provenienz/Confidence), Quellen
Rekordbox-Cues + PSSI-Phrasen + Analyzer, Paar-Bewertung mit ALLEN Faktoren,
BPM <= 2, beide Blendenlaengen, Hoertest als Kandidaten-Paarvergleich.
`Track.mix_in_point/mix_out_point` = Rang 1; Invarianten 1-6 und der
Intro/Outro-Guard gelten fuer JEDEN Kandidaten. Cue-Positionsheuristik
("2. Cue = In, letzter = Out") entfaellt mit der Umsetzung. CACHE_VERSION 34.
Nutzer-Auflage: exakt so, vollstaendig, keine Annahmen.

## Common Mistakes

- `> 0` statt `>= 0.0` gegen den Sentinel pruefen.
- `phrase_anchor` als Untergrenze fuer `min_mix_in` benutzen (R3).
- Neue Mixpoint-Quelle ohne `align_ai_mix_points`/`quantize_to_grid` einbauen.
- Inline `(60/bpm)*4` statt `seconds_per_bar()` — es gab 14 solche Kopien.
- Innerhalb der Kette runden.
- Mixpoint-Logik aendern ohne `CACHE_VERSION`-Bump -> Skill
  `hpg-cache-persistence`.
