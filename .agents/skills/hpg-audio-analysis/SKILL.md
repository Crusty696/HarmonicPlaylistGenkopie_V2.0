---
name: hpg-audio-analysis
description: Use when working on HPG audio analysis — librosa loading, BPM/Key/Energy/Brightness/Danceability features, Track-Struktur und Sektionen, Coverage-Luecken, LUFS, key_confidence, Downbeat- und Phrasen-Schaetzung, oder wenn Analysewerte fuer lange Tracks unplausibel wirken.
---

# HPG Audio Analysis

## Einstieg

`analysis.analyze_track(file_path) -> Track | None` [analysis.py:1282] ist die
**einzige** oeffentliche Analyse-Funktion. Sie macht Limits, Cache, Decode,
Features, Struktur und Mixpoints in einem Zug. Rueckgabe `None` heisst
"uebersprungen" — nie eine Exception nach oben.

## Zwei Pfade, ein Vertrag

| | Fast-Path | Voll-Path |
|---|---|---|
| Bedingung | `rekordbox_data and rekordbox_data.bpm` | sonst |
| BPM/Key | aus Rekordbox-DB, `key_confidence = 1.0` | librosa + Chroma |
| Decode | `LIBROSA_FAST_PATH_DURATION = 360` s | `LIBROSA_MAX_DURATION = 600` s |
| Speed | ~12x schneller | Referenz |

Beide muenden in dieselbe Struktur-/Mixpoint-Kette. **Wer einen Pfad aendert,
muss den anderen mitaendern** — historisch die haeufigste Fehlerquelle
(Fast-Path-Einrueckungsbug liess Tracks ohne Key still verschwinden).

## Der Decode-Deckel ist der wichtigste Fakt

`y` deckt **nie** den ganzen Track ab. Ein 12-Minuten-Track wird bei 600 s
abgeschnitten. Damit Outro und Mix-Out trotzdem echt sind, gibt es ein
**zweites Fenster**:

`analyze_structure_windows()` [analysis.py:1181]
- Head = das bereits geladene `y`
- Tail = separater Offset-Load der letzten `LIBROSA_TAIL_DURATION = 180` s
- Luecke dazwischen wird als Section `label="unanalysed"` eingefuegt — sie
  wird **nicht** weginterpoliert
- Rueckgabe `(structure, coverage, outro_covered)`; `outro_covered` ist
  `tail_end >= duration - 1.0`

**Fenster-Artefakt-Regel** [analysis.py:1236, B7/N1]: der Section-Labeler
markiert die letzte Section eines Fensters immer als Outro-Kandidat. Endet das
Fenster nicht am Track-Ende, wird `outro` zu `main` degradiert. Ohne das zog
der Outro-Scanner in `dj_brain` den Mix-Out in die Track-Mitte (reproduziert:
480-s-Track -> Mix-Out bei 34 %).

## outro_covered — wer prueft es, wer nicht

Nur zwei Stellen im Code:
- `ai_engine.py:108` — LLM-Mix-Out wird mit `ValueError` verworfen
- `exporters/rekordbox_xml_exporter.py:346` — Cue-Export verweigert

**Nicht** geprueft in `playlist.py`, `dj_brain.py`, `transition_renderer.py`,
m3u8-Export und GUI-Anzeige. Wer dort neue Mix-Out-Konsumenten baut, muss den
Guard selbst setzen — verifiziert per `grep -rn outro_covered`.

## FeatureCache

`FeatureCache(y, sr)` [analysis.py:48] ist ein lazy, track-lokaler Cache fuer
MFCC/RMS/STFT/Chroma/Centroid/Flatness/Contrast/Onset/HPSS. Er wird durch
Genre-Klassifikation, Downbeat, Phrase und Struktur durchgereicht.
Neue Feature-Berechnung? **Erst pruefen, ob der Cache sie schon hat.**

**HPSS ist die teuerste Operation der ganzen Analyse.** Gemessen an einem
410-s-Track (2026-08-14): vor der Konsolidierung 14 Aufrufe = 37,2 s von
47,2 s Gesamtlaufzeit (78,8 %). Ursache waren drei Stellen, die den Cache
umgingen. Nach dem Fix: 2 Aufrufe (je einer fuer Head- und Tail-Fenster),
12,9 s, `analyze_track` 22,6 s — Faktor 2,09.

Wer hier etwas anfasst, muss den Cache durchreichen:
- `analyze_rhythm_complexity(y, sr, feature_cache, sample_range=(s, e))` —
  fuer Sektionen den **Ausschnitt** der Track-HPSS nehmen, nicht neu rechnen.
  Die spektrale Flachheit muss dabei weiter auf dem Ausschnitt gerechnet
  werden; der Cache-Wert gilt fuer den ganzen Track.
- `_compute_bass_percussion_novelty(..., feature_cache=...)`
  [structure_analyzer.py] — nutzt `get_hpss()[1]`, wenn die Signallaenge zur
  Cache-Laenge passt.

Der Laengenvergleich `len(feature_cache.y) == len(y)` ist die Sicherung: nur
dann ist die gecachte HPSS wirklich die desselben Signals.

Fuer das Tail-Fenster wird bewusst ein **eigener** `FeatureCache(tail_audio,
sr)` gebaut — Head-Matrizen passen nicht auf Tail-Samples.

## Anker-Kette (Reihenfolge zwingend)

```
Genre -> phrase_unit (GENRE_PHRASE_UNITS)
  -> first_downbeat  (Rekordbox-ANLZ conf 1.0, sonst estimate_first_downbeat)
  -> first_phrase    (nur wenn downbeat_confidence > 0.0)
  -> phrase_anchor   (Track-Property, Gate PHRASE_CONFIDENCE_MIN = 0.25)
  -> analyze_structure_windows(anchor=phrase_anchor)
  -> Mixpoints
```

Details zu Quantisierung und Sentinels: Skill `hpg-mixpoint-engineering`.

## BPM aus ID3-Tags: der Faktor ist das Problem, nicht die Praezision

Fehlt Rekordbox, liefert der ID3-Tag die BPM. Der Tag ist praezise, aber sein
**Oktav-/Faktor-Fehler ist haeufig**: gemessen widersprach er bei 23 von 52
Tracks der Rekordbox-Analyse, ein Track stand mit 69 BPM im Tag bei real 138.

`analyze_track` prueft deshalb den Faktor gegen das Audio. Korrigiert wird nur,
wenn **alle vier** Bedingungen halten:

1. ein Vielfaches aus (0.5, 2/3, 1.5, 2) passt besser als 1
2. der Tag liegt >8 % neben dem gemessenen Tempo
3. das Vielfache trifft das gemessene Tempo auf <=6 %
4. der Tag liegt **ausserhalb** des kanonischen Genre-BPM-Bereichs und das
   korrigierte Tempo **innerhalb** (ohne ID3-Genre: Vereinigungsbereich aller
   `GENRE_PROFILES`, aktuell 118-180)

**Warum Bedingung 4 unverzichtbar ist:** `librosa.beat.beat_track` kann
vollkommen stabil falsch liegen. An einem echten 140-BPM-Track liefert es ueber
vier verschiedene 60-s-Fenster konstant 92.3 BPM — Streuung 0.0, exakt das
Verhaeltnis 2/3. Eine Stabilitaets- oder Mehrfachmessung kann "Tag falsch" und
"Messung falsch" also **nicht** unterscheiden; nur die Genre-Plausibilitaet
kann es.

**Der Rekordbox-Pfad bekommt diese Pruefung bewusst NICHT.** Dort ist der
BPM-Wert nutzergepflegt und verlaesslicher als die Messung — derselbe
Pyramid-Track haette sonst seine korrekten 140 BPM auf ~93 "korrigiert"
bekommen.

## Sentinels und Konfidenzen

| Feld | "nicht bestimmt" | Anmerkung |
|---|---|---|
| `mix_in_point` / `mix_out_point` | `-1.0` (`MIX_POINT_UNSET`) | `0.0` ist gueltig |
| `first_phrase` | `-1.0` | Phase `0.0` ist gueltig |
| `key_confidence` | `0.0` | `1.0` = Rekordbox-Key |
| `lufs` | `0.0` + `lufs_status` | EBU R128, Referenz `LUFS_REFERENCE = -18.0` |

`lufs_status` kennt `complete`, `invalid` und `error`. Historie: bis 2026-08-14
lieferte `_integrated_loudness_from_blocks` fuer 24 von 52 Tracks NaN, weil die
Blockzahl aufgerundet wurde und der letzte 400-ms-Block nicht mehr ins Signal
passte — sichtbar nur als `invalid` mit `lufs = 0.0`, ohne Fehlermeldung. Wer
an der Blockschleife arbeitet: jeder gezaehlte Block muss vollstaendig im
Signal liegen, und das Ergebnis gegen `pyloudnorm.Meter.integrated_loudness`
gegenpruefen (Abweichung sollte <0.01 dB sein).
| `downbeat_confidence` | `0.0` | `1.0` = ANLZ-Beatgrid |

## Fehlerpfad

Schlaegt der Decode fehl, wird `analysis_degraded` gesetzt. Ein Track mit
erfundenen Werten darf **nicht** normal gecacht werden — pruefe das, bevor du
neue Fehlerpfade hinzufuegst (Altbefund A-02: transienter Fehler wurde als
Muell-Track dauerhaft gecacht).

## Common Mistakes

- Annehmen, `y` enthalte den ganzen Track. Tut es nie.
- Tail-Fenster beim Aendern der Struktur-Logik vergessen.
- Feature direkt neu berechnen statt `FeatureCache` zu fragen.
- Nur einen der beiden Analyse-Pfade anfassen.
- Analyse-Output aendern, ohne `CACHE_VERSION` zu bumpen -> Skill
  `hpg-cache-persistence`.
