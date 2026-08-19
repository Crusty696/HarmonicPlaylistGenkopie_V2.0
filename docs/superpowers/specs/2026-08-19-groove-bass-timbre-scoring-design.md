# Groove-, Bass-, Timbre- und Mood-Scoring fuer die Playlist-Reihenfolge

Design-Spec · 2026-08-19 · HPG v3.7.2

## 1. Problem

Die Reihenfolge einer HPG-Playlist entsteht ausschliesslich aus vier Faktoren.
`calculate_enhanced_compatibility` (`hpg_core/playlist.py:256`) ist die einzige
Zielfunktion beim Sortieren; mit `GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2` verteilen
sich ihre Gewichte so:

| Faktor | Gewicht | Datenquelle |
|---|---|---|
| Harmonik (Camelot) | 0,352 | `camelotCode` |
| BPM-Smoothness | 0,224 | `bpm` |
| Energy-Flow | 0,224 | `energy` (ein Skalar 0-100) |
| Genre-Kompatibilitaet | 0,200 | Genre-Label |

Dazu additiv der KI-Bonus und der Vocal-Clash-Abzug, danach das BPM-Hard-Gate.

Ob zwei Tracks sich rhythmisch beissen, ob der Bassdruck springt, ob der
Klangcharakter fremd wirkt oder die Stimmung bricht, hat **keinen Einfluss auf
die Reihenfolge**. Der Nutzer benennt genau diese vier Punkte als die
tatsaechlich hoerbaren Fehler seiner Playlists.

### 1.1 Verifizierter Ist-Zustand

Konsumenten-Zaehlung in `hpg_core/playlist.py`:

```
bass_intensity      0     avg_mids            0
avg_bass            2     avg_highs           0
percussive_ratio    0     spectral_flatness   0
timbre_fingerprint  0     mfcc_fingerprint    0
brightness          0     danceability        0
lufs                0     phrase_unit         0
```

Die beiden `avg_bass`-Treffer sind Anzeige, kein Scoring.

Zwei paarweise Vergleiche existieren bereits, laufen aber ins Leere:
`_calculate_texture_similarity(timbre_fingerprint_a, b)` und die
Perkussivitaets-Regel aus `percussive_ratio` in `dj_brain.py:537-546`. Ihre
Ergebnisse landen als `texture_score` und `rhythm_advice` im
`DJRecommendation`-Objekt, das nur **angezeigt** wird. Der Regelkreis zum
Score, nach dem sortiert wird, ist offen.

### 1.2 Ausgangslage, die das Vorhaben traegt

`first_downbeat` liegt fuer die Sammlung flaechendeckend vor. Stichprobe von
120 zufaelligen Tracks gegen `RekordboxImporter.get_first_downbeat()`:
120 Treffer, 0 Fehlschlaege, `downbeat_confidence = 1.0` aus dem
Rekordbox-ANLZ-Beatgrid.

Das ist die Voraussetzung des gesamten Designs. Ein beat-synchrones
Rhythmusmuster, das um einen halben Beat verschoben gemessen wird, ist
Rauschen. Ohne verlaessliche Eins waere Groove-Matching nicht umsetzbar.

### 1.3 Sammlung

2480 Tracks in der Rekordbox-`master.db` (2477 mit BPM, 2480 mit Key, 2467 mit
Cues).

Die Genre-Verteilung stammt aus dem XML-Export `Sammlung-rekordbox-2026.xml`
(2476 Tracks), da `master.db` das ID3-Genre nicht in gleicher Form
bereitstellt. Die Differenz von 4 Tracks ist fuer die Verteilung
unerheblich.

| ID3-Genre | Tracks | Anteil |
|---|---|---|
| Psy-Trance | 1357 | 54,8 % |
| Progressive House | 433 | 17,5 % |
| Techno (Peak Time / Driving) | 230 | 9,3 % |
| Melodic House & Techno | 192 | 7,8 % |
| Tech House | 125 | 5,0 % |
| Minimal / Deep Tech | 58 | 2,3 % |
| Deep House | 41 | 1,7 % |
| uebrige (Electronica 14, Loop Samples 8, House 6, Dance/Electro Pop 4, ohne Genre 3, Trance 2, Drum & Bass 2, Indie Dance 1) | 40 | 1,6 % |

Im aktuellen Cache (`hpg_cache_v29.db`) liegen 53 analysierte Tracks. Eine
vollstaendige Analyse der Sammlung hat nie stattgefunden.

## 2. Ziel

Die Reihenfolge soll zusaetzlich davon abhaengen, wie gut zwei Tracks
rhythmisch, im Bassdruck, im Klangcharakter und in der Stimmung
zusammenpassen. Die Gewichte dieser Faktoren werden **aus echten DJ-Mixen
gelernt**, nicht geraten, und sind fuer alle 9 kanonischen Genres separat
bestimmt.

## 3. Nicht-Ziele

- Kein XML-Import. Rekordbox-Daten kommen weiterhin aus `master.db`.
- Keine Aenderung an `predict_transition_type`. Dass Groove-Daten spaeter auch
  die Technikwahl verbessern koennten, ist Folgearbeit, nicht Teil dieser Spec.
- Kein maschinelles Lernmodell im Auslieferungsstand. Gelernt werden Gewichte
  und Schwellwerte, keine trainierten Modelle.
- Keine Aenderung der Mixpoint-Berechnung selbst.

## 4. Architektur

Drei neue Module, bewusst klein und ohne Abhaengigkeit nach oben:

| Datei | Zweck | Abhaengigkeiten |
|---|---|---|
| `hpg_core/groove.py` | beat-synchrone Mustererkennung, reine Funktionen | numpy, librosa |
| `hpg_core/transition_features.py` | paarweise Vergleiche, reine Funktionen | `models`, `genres` |
| `tools/mix_mining.py` | Kalibrierung, laeuft offline und nie in der App | `groove`, yt-dlp, ffmpeg |

Erweitert werden: `models.py` (Felder), `analysis.py` (Aufruf),
`playlist.py` (Score), `genres.py` (Toleranzen), `config.py` (Schalter,
Defaults), `caching.py` (`CACHE_VERSION`).

Der Schnitt ist so gelegt, dass `groove.py` und `transition_features.py` ohne
Audio-Kontext testbar sind: Muster rein, Zahl raus. Das ist die Bedingung
dafuer, dass die gelernten Werte ueberpruefbar bleiben.

## 5. Feature-Extraktion (`hpg_core/groove.py`)

### 5.1 Kernmechanismus

Die Onset-Staerke wird auf **einen Takt gefaltet**: 16 Slots je ein
Sechzehntel, verankert am `first_downbeat`, gemittelt ueber alle Takte des
analysierten Fensters. Ergebnis ist ein 16-stelliger, L1-normierter Vektor —
der Rhythmus-Fingerabdruck. Dasselbe getrennt fuer alles unter 150 Hz.

16 Slots, weil ein 4/4-Takt genau 16 Sechzehntel hat; bei 140 BPM entspricht
das 1,71 s pro Takt. Die Mittelung ueber viele Takte macht das Muster robust
gegen einzelne Ausreisser.

Gemittelt wird **nur ueber Sektionen mit Beat** (`main`, `drop`). Ein
Breakdown ohne Drums wuerde das Muster sonst verwaessern.

### 5.2 Neue Track-Felder

```python
groove_pattern: list = field(default_factory=list)   # 16 Slots, L1-normiert
bass_pattern:   list = field(default_factory=list)   # 16 Slots, nur <150 Hz
syncopation:    float = 0.0                          # 0-1, Offbeat-Energieanteil
sub_energy:     float = 0.0                          # 20-60 Hz, relativ zur Gesamtenergie
bass_punch:     float = 0.0                          # Crest-Faktor des Bassbands
```

`sub_energy` und `bass_punch` werden **zweifach** gefuehrt: als Trackmittel in
den obigen Feldern (Anzeige, Fallback) und zusaetzlich je Sektion in den
Section-Dicts von `Track.sections` (Abschnitt 5.3). Das Scoring nutzt die
Sektionswerte; die Trackmittel greifen nur, wenn fuer die betreffende Sektion
kein Wert vorliegt.

### 5.3 Bewusste Asymmetrie: Groove track-weit, Bass sektionsweise

Der Groove eines Tracks ist ueber seine Laenge weitgehend stabil, der
Bassdruck nicht — Intro und Drop unterscheiden sich massiv. Da die Sektionen
in `Track.sections` bereits `avg_bass` tragen (`dj_brain.py:1337` nutzt das),
kommt `sub_energy` dort daneben.

Beim Paar-Vergleich wird deshalb **Outro von A gegen Intro von B** gemessen,
nicht Trackmittel gegen Trackmittel. Ob zwei Tracks im Durchschnitt aehnlich
basslastig sind, ist fuer den Uebergang irrelevant; es zaehlt, was an der
Nahtstelle passiert.

### 5.4 Rechenaufwand

`FeatureCache` (`analysis.py:48`) haelt Onset, STFT und HPSS bereits vor —
genau die teuren Operationen, die hier gebraucht werden. Die Extraktion greift
auf vorhandene Matrizen zu. Regel aus dem Bestand: **erst pruefen, ob der
Cache die Groesse schon hat**, nie neu rechnen. Der Laengenvergleich
`len(feature_cache.y) == len(y)` bleibt die Sicherung dafuer, dass die
gecachte Matrix zum Signal gehoert.

Fuer das Tail-Fenster wird wie im Bestand ein eigener `FeatureCache` gebaut;
Head-Matrizen passen nicht auf Tail-Samples.

Erwartung: die Analyse wird durch die neuen Felder nicht spuerbar langsamer.
Die Neuanalyse der Sammlung ist trotzdem noetig, weil die Felder neu sind.

## 6. Paar-Vergleich (`hpg_core/transition_features.py`)

Vier reine Funktionen, jeweils Rueckgabe in [0, 1]:

| Funktion | Berechnung |
|---|---|
| `groove_match(a, b)` | Kosinus-Aehnlichkeit von `groove_pattern` und `bass_pattern`, gewichtet zusammengefasst |
| `bass_continuity(a, b)` | Differenz von `sub_energy` und `bass_punch` an der Nahtstelle (Outro A / Intro B), gegen die Genre-Toleranz normiert |
| `timbre_match(a, b)` | Kosinus-Aehnlichkeit der `timbre_fingerprint` (nutzt die bestehende Logik aus `dj_brain.py:1382`) |
| `mood_match(a, b)` | kombiniert `brightness`, `spectral_flatness` und den Dur/Moll-Wechsel aus `keyMode` |

Alle vier bekommen den Genre-Kontext uebergeben, da die Toleranzen
genre-spezifisch sind (Abschnitt 9).

## 7. Scoring-Integration

### 7.1 Formel

Der Score bleibt eine gewichtete Summe, erweitert von vier auf acht Faktoren.
Die Gewichte summieren sich pro Genre auf 1,0:

```
overall = w_harm*harmonic + w_bpm*bpm_smoothness + w_energy*energy_flow + w_genre*genre_compat
        + w_groove*groove_match + w_bass*bass_continuity
        + w_timbre*timbre_match + w_mood*mood_match
```

KI-Bonus, Vocal-Clash-Abzug und BPM-Hard-Gate bleiben unveraendert danach.
Insbesondere gilt weiterhin: `bpm_diff > bpm_tolerance` setzt `overall_score`
hart auf 0. Kein neuer Faktor darf einen unmixbaren Sprung retten.

### 7.2 Startgewichte vor der Kalibrierung

Der neue Block bekommt zusammen 30 %; die bestehenden vier behalten ihre
Verhaeltnisse zueinander und werden auf 70 % gestaucht.

| Faktor | heute | Start neu |
|---|---|---|
| Harmonik | 0,352 | 0,246 |
| BPM | 0,224 | 0,157 |
| Energy | 0,224 | 0,157 |
| Genre | 0,200 | 0,140 |
| Groove | — | 0,120 |
| Bass-Kontinuitaet | — | 0,080 |
| Timbre | — | 0,050 |
| Mood | — | 0,050 |

Groove bekommt innerhalb des neuen Blocks das meiste Gewicht, weil er als
einziger **harte** Fehler erzeugt: ein Rhythmuskonflikt ruiniert einen
Uebergang hoerbar, waehrend fremdes Timbre oder ein Helligkeitssprung ihn nur
weniger elegant machen.

Diese Zahlen sind ausdruecklich der Startpunkt. Sie werden durch die in
Abschnitt 10 gemessenen ersetzt.

### 7.3 Fehlende Werte: Umverteilung statt Bestrafung

Ein Track aus altem Cache oder mit `analysis_degraded` hat kein
`groove_pattern`. Regel: ein fehlender Faktor wird **nicht mit 0 bewertet** —
das waere eine stille Bestrafung —, sondern aus der Summe genommen und sein
Gewicht anteilig auf die verfuegbaren Faktoren umverteilt. Ein Track ohne
Groove-Daten wird damit genau wie heute behandelt, nicht schlechter.

### 7.4 HPG-001: scoring_context

Die vier neuen Faktoren laufen ueber denselben `scoring_context` wie die
bestehenden, und zwar in allen fuenf Konsumenten: Anzeige, Reorder, Preview,
`calculate_playlist_quality` und Empfehlungen. Sortiert die Playlist nach acht
Faktoren, waehrend die angezeigte Qualitaetszahl nur vier kennt, optimiert die
App gegen ein anderes Ziel als das, was der Nutzer sieht.

`TransitionMetrics` bekommt vier neue Felder (`groove_match`,
`bass_continuity`, `timbre_match`, `mood_match`), die auch in der GUI sichtbar
werden.

### 7.5 Schalter

`TRANSITION_FEATURES_ENABLED` in `config.py`. Bei `False` muss das Verhalten
**bit-identisch** zum heutigen Stand sein. Ohne diesen Schalter laesst sich
nicht beurteilen, ob die Aenderung die Reihenfolge verbessert.

## 8. Konfiguration und nachtraegliche Anpassbarkeit

Gewichte und Toleranzen sind **Daten, keine Konstanten im Quelltext**.

- Gelernte Werte: `hpg_core/data/transition_tolerances.json`, mitgeliefert.
- Nutzer-Override: `%LOCALAPPDATA%\HPG\transition_tolerances.json` schlaegt die
  mitgelieferte Datei. Damit ueberlebt eine Anpassung Updates und die EXE.
- Fehlt die Datei oder ist ihr JSON kaputt, greifen die eingebauten Defaults.
  Ein defektes JSON darf den Start nicht verhindern; der Fehler geht nach
  `logs/error_report.json`.
- GUI: Panel in den Advanced-Einstellungen mit Reglern fuer die vier neuen
  Gewichte und einem Reset auf die gelernten Werte.

**Wichtiger Nebeneffekt:** Features liegen im Cache, Gewichte ausserhalb. Eine
Gewichtsaenderung erfordert deshalb **keine** Neuanalyse, nur ein
Neuberechnen der Scores — Sekunden statt Minuten. `CACHE_VERSION` bleibt davon
unberuehrt.

Beim Aendern der Gewichte muss `_ENHANCED_COMPAT_CACHE` verworfen werden,
sonst zeigt die App alte Zahlen.

## 9. Genre-Toleranzen

Neue Tabelle `GENRE_TRANSITION_TOLERANCES` in `hpg_core/genres.py`, ein
Eintrag je kanonischem Genre:

```python
groove_weight, bass_weight, timbre_weight, mood_weight   # Gewichte
groove_sim_floor        # Aehnlichkeit, unter der es Abzug gibt
bass_delta_max          # akzeptierter Sub-Sprung in dB
brightness_delta_max    # akzeptierter Helligkeitssprung
```

Genre-spezifische Kalibrierung ist kein Feinschliff, sondern notwendig: im
Psy-Trance ist ein durchlaufender Offbeat-Bass die Norm und ein Wechsel des
Bassmusters mitten im Blend ein Fehler; in Progressive House sind lange
Filter-Blends ueber wechselnde Grooves genau das Stilmittel. Dieselbe
gemessene Groove-Differenz bedeutet in einem Genre "geht nicht" und im anderen
"genau richtig". Ein globaler Toleranzwert wuerde beide Genres gleichzeitig
falsch bedienen.

`genres.py` wirft beim Import einen `ValueError`, wenn die Genre-Tabellen
inkonsistent sind. Die Drift-Validierung **muss die neue Tabelle mit
abdecken**, sonst kann ein Genre stillschweigend ohne Toleranzen dastehen.

Vetos (harte Ausschluesse statt Abzug) werden strukturell vorbereitet, aber
standardmaessig nicht scharf geschaltet. Ein Genre bekommt ein Veto nur, wenn
das Mix-Mining zeigt, dass echte DJs diesen Uebergang dort praktisch nie
machen.

## 10. Kalibrierung (`tools/mix_mining.py`)

### 10.1 Material

Pro Genre 2-3 Mixe von 60-120 Minuten, was rund 30-60 Uebergaenge je Mix
ergibt. Quellen: eigene Mixe des Nutzers und oeffentliche DJ-Mixe. Tracklisten
liegen nicht vor und werden auch nicht benoetigt (Abschnitt 10.4).

### 10.2 Beschaffung: kein Umwandeln

HPG laedt Audio ueber `librosa.load` und `sf.blocks`
(`analysis.py:1431`, `:476`). Gemessen: libsndfile 1.2.2, soundfile 0.14.0,
librosa 0.11.0. Lesbar sind unter anderem WAV, AIFF, FLAC, MP3 und OGG
(Vorbis **und** Opus).

Lokale Dateien werden daher **direkt** gelesen. Es findet keine Umwandlung
statt.

Einschraenkung nur bei YouTube: libsndfile liest die Container `.m4a` und
`.webm` nicht, und librosa 0.11 hat den audioread-Fallback nicht mehr. Der
Codec ist dort meist Opus, und Opus wird gelesen — nur im Ogg-Container. Es
genuegt deshalb ein Umpacken von webm nach ogg per
`yt-dlp -f bestaudio -x --audio-format opus`. Das ist ein Container-Wechsel
ohne Neukodierung: verlustfrei, in Sekunden erledigt. Bei einem MP4-Video wird
nur die Audiospur geholt, das Video gar nicht erst geladen.

### 10.3 Uebergaenge finden

Neuheitsdetektion auf Timbre und Bassband. Ein DJ-Mix hat Blends, keine
Schnitte — die Blend-Zone selbst wird deshalb **ausgespart** und je ein
stabiles Fenster davor und dahinter gemessen. Im Blend liegen beide Tracks
uebereinander; dort gemessene Features waeren Mischwerte und damit wertlos.

Auf diese Fenster laeuft **exakt dieselbe** `groove.py` wie in der App. Das
ist Bedingung, nicht Bequemlichkeit: wuerden Kalibrierung und Anwendung
unterschiedlich messen, waeren die gelernten Zahlen nicht uebertragbar.

### 10.4 Von Verteilungen zu Zahlen

Pro erkanntem Uebergang fallen vier Deltas an: Groove-Aehnlichkeit,
Sub-Sprung in dB, Helligkeitssprung, Timbre-Aehnlichkeit.

**Toleranzen** kommen direkt aus den Perzentilen. Was in 90 % der echten
Uebergaenge eines Genres eingehalten wird, ist die Grenze fuer dieses Genre.

**Gewichte** kommen aus der Trennschaerfe. Jeder echte Uebergang wird gegen
Zufallspaare aus demselben Mix-Pool gestellt. Ein Faktor, der echte
Uebergaenge zuverlaessig von zufaelligen trennt, beschreibt eine echte
DJ-Entscheidung und bekommt hohes Gewicht; ein Faktor, der bei beiden gleich
aussieht, misst nichts und bekommt wenig.

Das funktioniert **ohne jede Trackliste**: der Mix liefert Positiv- und
Negativbeispiele aus sich selbst heraus.

### 10.5 Speicher und Rechtliches

Nach der Extraktion werden die Mix-Audios geloescht. Was bleibt, sind
Kennzahlen pro Uebergang — keine Kopien. Downloads von YouTube widersprechen
deren Nutzungsbedingungen; die Entscheidung darueber liegt beim Nutzer und ist
hier dokumentiert, nicht bewertet.

### 10.6 Reihenfolge

Alle 9 kanonischen Genres bekommen einen Toleranzsatz. Die Reihenfolge der
Bearbeitung richtet sich nach dem Anteil an der Sammlung: Psytrance,
Progressive, Techno, Melodic Techno, Tech House zuerst (zusammen 94,4 %),
danach Minimal, Deep House, Trance, Drum & Bass.

Fuer Trance und Drum & Bass enthaelt die Sammlung derzeit je 2 Tracks, fuer
Deep House 41 und Minimal 58. Ihre Toleranzen wirken sich vorerst auf kaum
eine Playlist aus und werden fuer den Bestandsaufbau vorgehalten. Der Aufwand
je zusaetzlichem Genre ist nach dem ersten gering, weil die Pipeline dieselbe
bleibt und nur anderes Material bekommt.

## 11. Validierung

Pro Genre bleibt **ein Mix vom Lernen ausgeschlossen** (Holdout). Auf diesem
muss gelten: echte Uebergaenge erhalten einen hoeheren Score als Zufallspaare.
Trifft das nicht zu, taugen die gelernten Werte fuer dieses Genre nichts und
werden nicht eingebaut — der Befund wird berichtet statt kaschiert.

Zusaetzlich der Nutzer-A/B ueber `TRANSITION_FEATURES_ENABLED`: gleiche
Trackauswahl, alte gegen neue Sortierung.

## 12. Cache und Migration

`CACHE_VERSION` steigt von 29 auf 30. Alte Eintraege werden dadurch nicht mehr
gelesen.

Der Nutzer wuenscht zusaetzlich das Loeschen der Altdateien in
`C:\Users\david\AppData\Local\HPG\` (25 Dateien, `hpg_cache_v18` bis `v29`
samt `-wal`, `-shm`, `.lock`, zusammen 1,46 MB). Das ist eine irreversible
Aktion und wird **unmittelbar vor dem ersten vollen Analyselauf** ausgefuehrt,
nicht frueher — vorher geloescht waeren die 53 vorhandenen Tracks zweimal
umsonst gerechnet. Musikdateien und die Rekordbox-Datenbank bleiben unberuehrt.

Anschliessend laeuft eine vollstaendige Analyse der Sammlung (2480 Tracks).
Auf 16 Kernen und ueberwiegend im Rekordbox-Fast-Path ist mit einer
Groessenordnung von 15-40 Minuten zu rechnen.

Die Umverteilungsregel aus 7.3 bleibt trotz des Loeschens im Code: sie deckt
Tracks ab, deren Analyse degradiert ist, nicht nur Altbestaende.

## 13. Fehlerbehandlung

- Fehlendes oder leeres `groove_pattern`: Faktor faellt weg, Gewicht wird
  umverteilt (7.3). Kein Abbruch, keine Bestrafung.
- `first_downbeat` ohne Konfidenz (`downbeat_confidence == 0.0`): kein
  Groove-Pattern berechnen. Ein Muster auf erfundenem Raster ist schlechter als
  gar keins.
- Defektes `transition_tolerances.json`: Defaults greifen, Fehler nach
  `logs/error_report.json`, App startet normal.
- `mix_mining.py` bei nicht ladbarer Datei: Mix ueberspringen, Grund
  protokollieren, restliche Mixe weiterverarbeiten.
- Analyse-Fehler behalten das bestehende Verhalten: `analysis_degraded` setzen,
  Track nicht als gueltig cachen.

## 14. Tests

- `tests/test_groove.py`: synthetische Muster mit feststehendem Erwartungswert.
  Ein konstruierter Offbeat-Bass gegen einen Straight-Bass muss niedrige
  Aehnlichkeit liefern; identische Muster muessen 1,0 liefern.
- `tests/test_transition_features.py`: die vier Paar-Funktionen, inklusive der
  Faelle mit fehlenden Feldern.
- Contract-Test: alle fuenf `scoring_context`-Konsumenten sehen dieselben acht
  Faktoren.
- Regressionstest: bei `TRANSITION_FEATURES_ENABLED = False` ist das Ergebnis
  bit-identisch zum heutigen Stand.
- Drift-Test: `GENRE_TRANSITION_TOLERANCES` deckt alle 9 kanonischen Genres ab
  und wird von der bestehenden Validierung in `genres.py` erfasst.
- Die bestehende Baseline bleibt gruen: 1506 passed, Coverage 77,29 % (gemessen 2026-08-19). Der Abschlusslauf laeuft mit Coverage, nicht mit --no-cov.

Aufruf: `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`

## 15. Umsetzungsreihenfolge

1. `groove.py` mit Tests, ohne Anbindung.
2. Track-Felder, `analysis.py`-Anbindung, `CACHE_VERSION` 30.
3. `transition_features.py` mit Tests, ohne Anbindung.
4. Genre-Tabelle mit den Startgewichten aus 7.2, Drift-Validierung.
5. Scoring-Integration hinter `TRANSITION_FEATURES_ENABLED`, alle fuenf
   `scoring_context`-Konsumenten, Regressionstest.
6. JSON-Datei, Override-Pfad, GUI-Panel.
7. Altdateien loeschen, volle Analyse der Sammlung.
8. `mix_mining.py`, Mixe je Genre, Toleranzen und Gewichte lernen.
9. Holdout-Validierung, gelernte Werte einsetzen, A/B durch den Nutzer.

Schritte 1-6 aendern das Verhalten der App nicht, solange der Schalter aus ist.
