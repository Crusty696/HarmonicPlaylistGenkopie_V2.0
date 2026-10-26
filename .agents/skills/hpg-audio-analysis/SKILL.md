---
name: hpg-audio-analysis
description: Use when working on HPG audio analysis — librosa loading, BPM/Key/Energy/Brightness/Danceability features, Track-Struktur und Sektionen, Coverage-Luecken, LUFS, key_confidence, Downbeat- und Phrasen-Schaetzung, oder wenn Analysewerte fuer lange Tracks unplausibel wirken.
---

# HPG Audio Analysis

## Einstieg

`analysis.analyze_track(file_path) -> Track | None` [hpg_core/analysis.py] ist die
**einzige** oeffentliche Analyse-Funktion. Sie macht Limits, Cache, Decode,
Features, Struktur und Mixpoints in einem Zug. Rueckgabe `None` heisst
"uebersprungen"; ungueltige Aufrufparameter koennen dagegen Exceptions ausloesen.

`analyze_track(file_path, *, cache_policy="reuse")` und
`ParallelAnalyzer.analyze_files(..., cache_policy="reuse")` akzeptieren
`reuse` oder `fresh`. `fresh` umgeht den persistenten Track-Cache beim Lesen und
Schreiben; `analysis_origin` ist nur ein Laufzeitattribut (`fresh`/`cache`) und
wird nicht als Trackfeld serialisiert. Verwaltete Hoertests uebergeben es separat
und speichern Herkunft in der privaten `hpg_analysis_origin`-Tabelle. Ungueltige
Policies sind Aufruffehler und werfen `ValueError`.

## Zwei Pfade, ein Vertrag

| | Fast-Path | Voll-Path |
|---|---|---|
| Bedingung | `rekordbox_data and rekordbox_data.bpm` | sonst |
| BPM/Key-Basis | Rekordbox-Metadaten | Tag-BPM mit Audio-Faktorpruefung oder DSP; Key aus Chroma |
| Native Uebernahme | `_prepare_native_beats` und `analyze_track_phrases` | dieselben nativen Vertraege |
| Decode | `LIBROSA_FAST_PATH_DURATION = 360` s | `LIBROSA_MAX_DURATION = 600` s |
| Geschwindigkeit | laufabhaengig, separat messen | laufabhaengig, separat messen |

Beide muenden in dieselbe Struktur-/Mixpoint-Kette. **Wer einen Pfad aendert,
muss den anderen mitaendern** — historisch die haeufigste Fehlerquelle
(Fast-Path-Einrueckungsbug liess Tracks ohne Key still verschwinden).

## Native Analyse und DSP-Fenster

Native Analyse ist in beiden Pfaden angebunden und kann nach bestandenen
Vertraegen Tempo/Anker liefern. Quellgebundene native Snapshots koennen
wiederverwendet werden; Audioausrichtung und Konfiguration erneut validieren.
Native Reader-Factorys und Modellfenster stehen in `hpg_core/ai_models/`.
Die folgenden Decode-Grenzen betreffen die librosa-Merkmalsfenster, nicht
pauschal alle nativen Analyseergebnisse oder die vollstaendige LUFS-Messung.

## DSP-Decode-Deckel

`y` deckt bei langen Tracks nur das begrenzte DSP-Fenster ab. Ein 12-Minuten-Track wird bei 600 s
abgeschnitten. Damit Outro und Mix-Out trotzdem echt sind, gibt es ein
**zweites Fenster**:

`analyze_structure_windows()` [hpg_core/analysis.py]
- Head = das bereits geladene `y`
- Tail = separater Offset-Load der letzten `LIBROSA_TAIL_DURATION = 180` s
- Luecke dazwischen wird als Section `label="unanalysed"` eingefuegt — sie
  wird **nicht** weginterpoliert
- Rueckgabe `(structure, coverage, outro_covered)`; `outro_covered` ist
  `tail_end >= duration - 1.0`

**Fenster-Artefakt-Regel** (B7/N1) [hpg_core/analysis.py]: der Section-Labeler
markiert die letzte Section eines Fensters immer als Outro-Kandidat. Endet das
Fenster nicht am Track-Ende, wird `outro` zu `main` degradiert. Ohne das zog
der Outro-Scanner in `dj_brain` den Mix-Out in die Track-Mitte (reproduziert:
480-s-Track -> Mix-Out bei 34 %).

## outro_covered — wer prueft es, wer nicht

Aktuelle direkte Konsumenten:
- `_gate_gruende_basis` / globaler Early Return [hpg_core/pair_candidates.py] — lokales Paar-Gate und globaler Early Return;
  die Playlist uebernimmt diesen Guard mittelbar ueber das Kandidaten-Ranking
- `mixpunkte_gueltig` [hpg_core/ai_engine.py] — nur die advisory KI-Mixpunkte werden auf `None`
  gesetzt; Mood und Subgenre bleiben erhalten
- `_cue_export_allowed` [hpg_core/exporters/rekordbox_xml_exporter.py] — Cue-Export verweigert

`dj_brain.py`, `transition_renderer.py`, m3u8-Export und GUI-Anzeige pruefen das
Feld nicht direkt. Neue Mix-Out-Konsumenten brauchen einen eigenen Guard oder
muessen nachweislich ueber das PairCandidate-Gate laufen.

## FeatureCache

`FeatureCache(y, sr)` [hpg_core/analysis.py] ist ein lazy, track-lokaler Cache fuer
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
  [hpg_core/structure_analyzer.py] — nutzt `get_hpss()[1]`, wenn die Signallaenge zur
  Cache-Laenge passt.

Der Laengenvergleich `len(feature_cache.y) == len(y)` ist die Sicherung: nur
dann ist die gecachte HPSS wirklich die desselben Signals.

Fuer das Tail-Fenster wird bewusst ein **eigener** `FeatureCache(tail_audio,
sr)` gebaut — Head-Matrizen passen nicht auf Tail-Samples.

## Anker-Kette

Aktueller Einstieg: `_prepare_native_beats` und `_resolve_track_anchor` in
`analysis.py`. Native Uebernahme und ihre Provenienz sind zusaetzlich zur
unten beschriebenen DSP-/Referenz-Arbitration zu beachten. Native Taktposition
ist mit verifiziertem nativen Grid nutzbar, bleibt aber unabhaengig musikalisch
unbestaetigt; Details im Projektwissen und aktuellen Verbraucher-Code.

```
Genre -> phrase_unit (GENRE_PHRASE_UNITS, bei schwacher Phrase durch Novelty-Messung ersetzbar)
  -> first_downbeat  (verifiziertes Rekordbox-ANLZ oder Audio-DSP/Modellvertrag)
  -> first_phrase    (nur wenn downbeat_confidence > 0.0)
  -> phrase_anchor   (Track-Property, Gate PHRASE_CONFIDENCE_MIN = 0.25)
  -> analyze_structure_windows(anchor=phrase_anchor)
  -> Mixpoints
```

Bei einer Rekordbox-Taktrotation bleibt der Kandidat gesperrt, bis Model7 und
Model8 in drei getrennten Fenstern uebereinstimmen, sechs Audiofenster die
Kandidatenphase innerhalb 6 ms bestaetigen und das Gesamtgrid verifiziert ist.
Nur dann verwendet der gemeinsame Resolver den korrigierten Anker als
Audioherkunft. Beide Analysepfade muessen diese Herkunft weiterreichen;
Rekordbox-PSSI und Rekordbox-Render-Sync duerfen sie nicht als unveraenderten
ANLZ-Anker behandeln. Alle unbestaetigten Rotationen bleiben gesperrt.

Ein konstanter Rekordbox-Zeitversatz über 6 ms wird als
`reference_constant_offset` diagnostiziert. Der phasenbereinigte Modellvergleich
liefert nur einen Taktrotationskandidaten. Seit Cache 81 darf der aktive
HPG-Audioanker nach drei disjunkten Zusatzfenstern je Modell, separater
Audiophasenbestätigung und verifiziertem Gesamtgrid angepasst werden. Der
Rekordbox-Import bleibt unverändert; Beatphase allein beweist keine musikalische
Takt-1.

Details zu Quantisierung und Sentinels: Skill `hpg-mixpoint-engineering`.

Bei bestaetigtem Beatgrid und schwacher erster Phrasenphase darf die
Audio-Novelty-Messung im Head-Fenster die Genre-Prior-Phrasenlaenge ersetzen.
Das Raster bleibt am bestaetigten Downbeat verankert; das Tail verwendet die
vom Head gewaehlte Einheit. Gesperrte oder unbestaetigte Raster behalten den
Genre-Prior. Die Implementierung ist im Quellvertrag beschrieben. Vor einer
Laufzeit- oder Qualitaetsaussage passende datierte Nachweise pruefen.
Wenn Novelty eine andere Einheit als den Genre-Prior waehlt, berechnen beide
Analysepfade Phrasenphase und -konfidenz mit dieser finalen Einheit neu. Nur
ausreichende Konfidenz verschiebt den Anker vom bestaetigten Downbeat.
Bei einem solchen Ankerwechsel quantisieren beide Pfade ihre Strukturfenster
mit der finalen Einheit und Phase erneut; scheitert diese Neuberechnung, bleibt
der vorherige Anker aktiv.
`Track.phrase_unit_source` persistiert anschliessend die Herkunft als
`audio_novelty`, `genre_prior` oder `configured`.
Interne Genreprofil-Einheiten muessen auch bei expliziter Weitergabe als
`genre_prior` gekennzeichnet werden. Externe explizite Einheiten behalten den
Default `configured`. `audio_novelty` wird nur nach erfolgter Messung gesetzt;
ein Aufrufer kann diese Herkunft nicht per Parameter behaupten. Das Tail erbt
`genre_prior`; die zusammengefuehrte Struktur behaelt die Herkunft des Head.
Bei einer Kandidatenmessung speichert Track ausserdem besten Kandidaten,
Novelty-Rohkorrelation und Ranking-Abstand. Diese Werte sind nicht kalibriert.
Messdiagnose-Schema v6 fuehrt dieselben Werte und die Cachevalidierung gleicht
sie gegen die Trackfelder ab.

## BPM aus ID3-Tags: der Faktor ist das Problem, nicht die Praezision

Fehlt Rekordbox-BPM, liefert ein vorhandener ID3-/AIFF-Tag die BPM. Artist,
Titel und Genre werden feldweise aus Easy-Tags und bei dort fehlenden Werten
aus rohen `TPE1`-/`TIT2`-/`TCON`-Frames ergaenzt via `_mutagen_text_value` [hpg_core/analysis.py]. Der
Tag bleibt praezise, kann aber einen Oktav-/Faktorfehler enthalten.

`analyze_track` prueft deshalb den Faktor gegen das Audio. Korrigiert wird nur,
wenn **alle vier** Bedingungen halten:

1. ein Vielfaches aus (0.5, 2/3, 3/4, 4/3, 1.5, 2) passt besser als 1
2. der Tag liegt >8 % neben dem gemessenen Tempo
3. das Vielfache trifft das gemessene Tempo auf <=6 %
4. `match_id3_genre` erkennt ein kanonisches ID3-Genre, der Tag liegt
   **ausserhalb** und das korrigierte Tempo **innerhalb** genau dessen
   BPM-Bereichs

Fehlt das ID3-Genre oder ist es unbekannt, bleibt der Tag unveraendert. Es gibt
ausdruecklich keinen genreuebergreifenden Union-Fallback — siehe
`_correct_id3_bpm_factor` [hpg_core/analysis.py].

**Warum Bedingung 4 unverzichtbar ist:** `librosa.beat.beat_track` kann
vollkommen stabil um einen einfachen Faktor falsch liegen. Eine Stabilitaets-
oder Mehrfachmessung kann "Tag falsch" und "Messung falsch" deshalb nicht
allein unterscheiden; nur der kanonische Bereich eines bekannten ID3-Genres
darf als Schiedsrichter dienen.

**Der Rekordbox-Pfad bekommt diese Pruefung bewusst NICHT.** Dort ist der
BPM-Wert nutzergepflegt und verlaesslicher als die Messung.

## Sentinels und Konfidenzen

| Feld | "nicht bestimmt" | Anmerkung |
|---|---|---|
| `mix_in_point` / `mix_out_point` | `-1.0` (`MIX_POINT_UNSET`) | `0.0` ist gueltig |
| `first_phrase` | `-1.0` | Phase `0.0` ist gueltig |
| `key_confidence` | `0.0` | `1.0` = Rekordbox-Key |
| `lufs` | `0.0` + `lufs_status` | EBU R128, Angleichung nur relativ |

`lufs_status` kennt `complete`, `invalid` und `error`. Historie: bis 2026-08-14
lieferte `_integrated_loudness_from_blocks` fuer 24 von 52 Tracks NaN, weil die
Blockzahl aufgerundet wurde und der letzte 400-ms-Block nicht mehr ins Signal
passte — sichtbar nur als `invalid` mit `lufs = 0.0`, ohne Fehlermeldung. Wer
an der Blockschleife arbeitet: jeder gezaehlte Block muss vollstaendig im
Signal liegen, und das Ergebnis gegen `pyloudnorm.Meter.integrated_loudness`
gegenpruefen (Abweichung sollte <0.01 dB sein).
| `downbeat_confidence` | `0.0` | Herkunft und verifiziertes Grid separat pruefen; 1.0 allein ist keine Freigabe |

## Fehlerpfad

Schlaegt der Decode fehl, wird `analysis_degraded` gesetzt. Ein Track mit
erfundenen Werten darf **nicht** normal gecacht werden — pruefe das, bevor du
neue Fehlerpfade hinzufuegst (Altbefund A-02: transienter Fehler wurde als
Muell-Track dauerhaft gecacht).

## Common Mistakes

- Annehmen, `y` enthalte bei langen Tracks den ganzen Track; DSP-Deckel beachten.
- Tail-Fenster beim Aendern der Struktur-Logik vergessen.
- Feature direkt neu berechnen statt `FeatureCache` zu fragen.
- Nur einen der beiden Analyse-Pfade anfassen.
- Analyse-Output aendern, ohne `CACHE_VERSION` zu bumpen -> Skill
  `hpg-cache-persistence`.


Tempo-Arbitration: Alle sechs model7/model8-BPM-Werte muessen die bestehende Intervalltoleranz erfuellen. Der Kandidat ist ihr Median; DSP-Refinement, Fold-Lock und verifiziertes Gesamtgrid bleiben Uebernahme-Gates. Messschema v7 speichert Status, Ablehnungsgrund, Modellmedian, verfeinertes Tempo, Spread und Einzelwerte mit Fensterherkunft.