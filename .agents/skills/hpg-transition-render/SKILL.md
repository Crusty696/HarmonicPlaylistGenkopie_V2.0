---
name: hpg-transition-render
description: Use when working on the HPG transition preview audio — render_transition_clip, TransitionClipSpec, Crossfade/Equal-Power, pro_eq_swap und EQ-Baender, Time-Stretch, Beat-Phase-Alignment, Limiter/LUFS im Renderer, oder wenn eine Preview verstimmt, leise, uebersteuert oder gar nicht klingt.
---

# HPG Transition Renderer

## Kette

```
compute_transition_recommendations   playlist.py:1459   -> TransitionPlan
  -> TransitionRenderWorker.run      main.py:685
     -> ProcessPoolExecutor(max_workers=1)   << Isolation
        -> _render_clip_subprocess_wrapper   transition_renderer.py:313
           -> render_transition_clip         transition_renderer.py:114
              -> sf.write(..., subtype="PCM_16")
```

**Warum Subprozess:** librosa/scipy/soundfile koennen auf C-Ebene abstuerzen.
Im Kindprozess wird daraus ein `BrokenProcessPool`, den der Worker faengt —
die App ueberlebt. Nie in den GUI- oder Analyse-Thread zurueckbauen.

`TransitionClipSpec.from_plan(plan, from_track, to_track)` [:83] ist der
**einzige** erlaubte Weg vom Plan zur Render-Spec: keine zweite
Timing-Berechnung. Wer Timing anpassen will, aendert den Plan.

## Ladefenster

```
Track A: start = mix_out_sec - pre_roll (30 s), dauer = pre_roll + cf
Track B: start = mix_in_sec - 1 Takt,           dauer = lead + cf + post_roll (30 s)
```

Der **Takt-Vorlauf bei B** (N-02) ist kein Zufall: das Bar-Alignment schiebt B
um bis zu einen Takt; ohne Vorlauf wuerden bis zu 2 Beats vom Anfang von
`seg_b` verworfen — genau der Drop-Einsatz, auf den die Analyse den Mix-In
gelegt hat.

`cf_sec = min(max(0.0, spec.crossfade_sec), MAX_TRANSITION_OVERLAP_SECONDS)`
mit `MAX_TRANSITION_OVERLAP_SECONDS = 64.0` [config.py:9]. Die untere Klemme
auf 0 ist Pflicht: ein degenerierter Plan (`overlap <= 0`) ergab sonst
negative Frame-Zahlen und einen `sosfiltfilt`-Crash.

## Time-Stretch — Semantik merken

`librosa.effects.time_stretch`: **rate > 1.0 = schneller.**

```python
rate = spec.bpm_a / target_bpm_b     # B wird auf A gezogen
```

Half/Double wird **relativ** erkannt: `half_double_tolerance = bpm_a * 0.04`
(DJ-Pitchfader erlaubt ~3-4 %). Ein absolutes 10-BPM-Fenster loeste frueher
falsch aus. Die Phasen-Umrechnung `phase_b / applied_stretch_rate` folgt
derselben Semantik — wer `rate` aendert, muss sie mitdenken.

## Beat-Alignment

`first_downbeat_a/b` kommen aus der Analyse. `0.0` ist dabei ein **legitimer**
Anker (Track startet auf der "1"), kein "unbekannt".

**Zwei getrennte Zuverlaessigkeiten (Stand 2026-08-14):**

- `downbeat_reliable_*` = `downbeat_confidence >= DOWNBEAT_RELIABLE_MIN` (0.30).
  Erlaubt **Beat**-Phasen-Alignment auch fuer die Eigenschaetzung. Die Schwelle
  ist an 35 Tracks mit ANLZ-Ground-Truth kalibriert: alle Verletzer der
  1/8-Beat-Grenze liegen bei <= 0.241, der schlechteste Zugelassene bei 0.391.
- `bar_phase_reliable_*` = `downbeat_confidence == 1.0`, also ausschliesslich
  Rekordbox-Beatgrid. Nur damit ist **Takt**-Alignment erlaubt.

Der Split ist gemessen noetig: die Eigenschaetzung trifft die Beat-Phase gut
(0 von 12 ueber 1/8 Beat), die TAKT-Phase lag aber bei 4 von 12 um ganze Beats
daneben — und die Konfidenz trennt das nicht. Wer behauptet, auf Takt 1 zu
liegen, braucht das Referenz-Beatgrid.

Ohne verlaesslichen Anker schaetzt `_estimate_first_beat` [:328] aus dem
Segment. Die eigene Downbeat-Schaetzung ist fuer sample-genaues Alignment zu
ungenau (30-380 ms Phasenfehler) und wird hier bewusst nicht verwendet.

## Uebergangstypen

`smooth_blend` · `bass_swap` · `breakdown_bridge` · `drop_cut` ·
`filter_ride` · `halftime_switch` · `echo_out` · `cold_cut` · `pro_eq_swap`.
Gewaehlt von `predict_transition_type` [playlist.py:1223].

`pro_eq_swap` ist der Default fuer Techno / Tech House / Minimal / Psytrance:
3-Band-Trennung (Low/Mid bei 120 Hz, Mid/High bei 2500 Hz), **Bass hart am
Crossfade-Mittelpunkt getauscht** (kurze Rampe, nie zwei Basslines
gleichzeitig), Mitten und Hoehen per **Equal-Power (cos/sin)**.

**Equal-Power-Regel:** komplementaere *lineare* Amplituden-Envelopes erzeugen
in der Mitte ein -3,01-dB-Loch. Jede neue Blend-Kurve muss cos/sin sein — das
gilt fuer alle Baender ausser dem harten Bass-Swap.

Davon zu unterscheiden waere ein **gemessener Bandgain ueber der Blendkurve**:
liegt derselbe Faktor auf A und B, bleibt `fo^2 + fi^2 == 1` unberuehrt, der
Effekt ist signalunabhaengig und an den Blendenraendern neutral — das waere
keine N-01-Regression. **Aktuell gibt es keinen solchen Bandgain im Code.**

Ein Versuch dazu wurde am 2026-08-20 gebaut und wieder zurueckgebaut. Messung
an 275 Uebergaengen aus 13 DJ-Mixen (`tools/eq_verlauf_messen.py`, geclustert
nach Mix): das Mittenband liegt waehrend eines Uebergangs tiefer als davor und
danach (AUC 0.655 [0.601, 0.715], Hoehen 0.608 [0.551, 0.665], Sub 0.426
[0.380, 0.477] ohne Beleg). Die Absenkung ist aber **gleichmaessig**, keine
Mulde: die Differenz Blendenmitte gegen Blendenrand enthaelt in allen
Laengengruppen die Null. Lehre daraus: die Messbaender muessen die
Renderer-Crossover treffen (120/2500). Eine erste Fassung mass 250-2500 Hz und
lieferte scheinbar klare Werte, weil die Oktave 120-250 Hz fehlte — die der
Renderer aber mit anfassen wuerde.

## Pegel

Reihenfolge in `render_transition_clip` [:210-217]:
`_rms_normalize(seg_a)` -> `_rms_normalize(seg_b)` -> `_apply_lufs_delta(...)`.

- `normalize_rms` mit `normalize_target_db = -14.0` (dBRMS ueber die aktiven
  Frames, Gain geklemmt auf +12/-20 dB)
- `lufs_a`/`lufs_b` sind die **gemessenen** Track-LUFS (BS.1770), Sentinel
  `0.0`. Sie duerfen nur als **Delta A gegen B** wirken, nie als Absolutpegel.
- Limiter am Ende; auf Channel-Link und `nan_to_num` achten, sonst
  Stereo-Verzug bzw. NaN im Export.

### Gemessener Defekt: LUFS-Delta doppelt gezaehlt (2026-08-14)

`_apply_lufs_delta` bekommt die **Ganztrack**-LUFS. Zu diesem Zeitpunkt hat
`_rms_normalize` die beiden Segmente aber schon angeglichen — der Lautheits-
unterschied existiert nicht mehr. Das Delta wird also auf bereits gematchtes
Material angewandt und **erzeugt** eine Differenz, statt eine zu beheben.

Messung an zwei realen Tracks (Delta B-A):

```
roh geladen              +7.50 dB
nach _rms_normalize      +0.62 dB   <- schon gematcht
nach _apply_lufs_delta   -5.38 dB   <- wieder auseinandergezogen
```

Ueberkorrektur 6.62 dB (durch das `clip(..., -6, 6)` gedeckelt), im fertigen
92-s-Clip 9.83 dB Pegelabstand zwischen ausgehendem und eingehendem Track.

**Wer das anfasst:** die Korrektur muss auf der **Restdifferenz nach** der
RMS-Normalisierung beruhen (LUFS der normalisierten Segmente messen), oder
ganz entfallen — `_rms_normalize` allein trifft auf 0.62 dB genau. Nicht
einfach das Clamp aufweiten; das vergroessert den Fehler.

## Timeouts und Temp-Dateien

Render-Timeout im Worker (Crossfade bis 64 s braucht Luft). Jeder Worker legt
sein **eigenes** `mkdtemp`-Verzeichnis an und raeumt nur den eigenen Inhalt —
nie das globale Temp-Verzeichnis.

## Verifikation

`tests/test_transition_renderer.py` (1025 Zeilen) plus `e2e_check.py`, das
Peak, Pegelverhaeltnis Mitte-vs-Rand, Kanalabweichung und
Sample-Endlichkeit auf echtem Audio prueft. DSP-Aenderungen ohne diesen Lauf
sind nicht verifiziert.

## Common Mistakes

- Stretch-Rate invertieren (`target_bpm_b / bpm_a`) — historischer Bug, der
  den Fehler verdoppelte statt ihn zu beheben.
- Lineare statt Equal-Power-Envelopes.
- LUFS als Absolutpegel verwenden.
- `crossfade_sec` ungeklemmt aus dem Plan uebernehmen.
- Timing im Renderer nachrechnen statt `from_plan` zu nutzen.
