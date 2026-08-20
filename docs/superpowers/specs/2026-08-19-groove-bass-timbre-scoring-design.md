# Groove-, Bass-, Timbre- und Mood-Scoring fuer die Playlist-Reihenfolge

Design-Spec · 2026-08-19 · HPG v3.7.2

## 1. Problem

Die Reihenfolge einer HPG-Playlist entsteht heute weitgehend aus vier
Faktoren, aber nicht einheitlich. `calculate_enhanced_compatibility`
(`hpg_core/playlist.py:291`, nicht `:256`) ist **nicht** die einzige
Zielfunktion beim Sortieren: Genre Flow (`playlist.py:1096`) und Context Flow
(`playlist.py:1941`) nutzen stattdessen `calculate_compatibility` (reine
Harmonik), Energy Wave nutzt gar keine Kompatibilitaetsfunktion. Von den 8
Strategien konsumieren nur Harmonic Flow und Consistent die acht Faktoren
voll; Warm-Up, Cool-Down, Peak-Time und Genre Flow nachrangig/teilweise;
Energy Wave und Context Flow gar nicht. Fuer die Strategien, die
`calculate_enhanced_compatibility` nutzen, verteilen sich die Gewichte mit
`GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2` so:

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

**Nicht verifizierbar** (nicht erneut geprueft, hier nur wiedergegeben statt
geloescht): `first_downbeat` liegt fuer die Sammlung flaechendeckend vor.
Stichprobe von 120 zufaelligen Tracks gegen
`RekordboxImporter.get_first_downbeat()`: 120 Treffer, 0 Fehlschlaege,
`downbeat_confidence = 1.0` aus dem Rekordbox-ANLZ-Beatgrid.

Das ist die Voraussetzung des gesamten Designs. Ein beat-synchrones
Rhythmusmuster, das um einen halben Beat verschoben gemessen wird, ist
Rauschen. Ohne verlaessliche Eins waere Groove-Matching nicht umsetzbar.

### 1.3 Sammlung

**Nicht verifizierbar** (Sammlungsstatistik und ID3-Verteilung nicht erneut
geprueft, hier nur wiedergegeben statt geloescht): 2480 Tracks in der
Rekordbox-`master.db` (2477 mit BPM, 2480 mit Key, 2467 mit Cues).

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

Im Cache lagen zum Zeitpunkt der urspruenglichen Fassung dieser Spec
(`hpg_cache_v29.db`) 53 analysierte Tracks; diese Angabe ist **veraltet**, der
Cache ist seither weitergelaufen und die Version hat sich geaendert (siehe
Abschnitt 12). Eine vollstaendige Analyse der Sammlung hat nie stattgefunden.

## 2. Ziel

Die Reihenfolge soll zusaetzlich davon abhaengen, wie gut zwei Tracks
rhythmisch, im Bassdruck, im Klangcharakter und in der Stimmung
zusammenpassen. Die Gewichte dieser Faktoren **sollten** aus echten DJ-Mixen
gelernt werden, nicht geraten, und fuer alle 9 kanonischen Genres separat
bestimmt sein. **Das ist nicht umgesetzt**: der Kalibrierungsversuch (Abschnitt
10/11) ist gescheitert, alle 9 Genres tragen aktuell identische, ungemessene
Defaultwerte. Das Ziel bleibt richtig, das bisherige Ergebnis war negativ —
siehe "Was das Vorhaben gelehrt hat" am Ende dieser Spec.

## 3. Nicht-Ziele

- Kein XML-Import. Rekordbox-Daten kommen weiterhin aus `master.db`.
- Keine Aenderung an `predict_transition_type`. Dass Groove-Daten spaeter auch
  die Technikwahl verbessern koennten, ist Folgearbeit, nicht Teil dieser Spec.
- Kein maschinelles Lernmodell im Auslieferungsstand. Gelernt werden Gewichte
  und Schwellwerte, keine trainierten Modelle.
- Keine Aenderung der Mixpoint-Berechnung selbst.

## 4. Architektur

Fuenf neue Module (nicht drei, wie eine fruehere Fassung dieser Spec sagte),
bewusst klein und ohne Abhaengigkeit nach oben. Zusaetzlich zu den drei
urspruenglich geplanten kamen `hpg_core/tolerances.py` und
`hpg_core/mix_analysis.py` dazu:

| Datei | Zweck | Abhaengigkeiten |
|---|---|---|
| `hpg_core/groove.py` | beat-synchrone Mustererkennung, reine Funktionen | numpy, librosa |
| `hpg_core/transition_features.py` | paarweise Vergleiche, reine Funktionen | `.models`, `.tolerances` |
| `hpg_core/tolerances.py` | Laden/Validieren der Genre-Toleranzen und -Gewichte | `.genres` |
| `hpg_core/mix_analysis.py` | Hilfsfunktionen fuer die Mix-Kalibrierung | `.groove` |
| `tools/mix_mining.py` | Kalibrierung, laeuft offline und nie in der App | `groove`, `mix_analysis`, yt-dlp, ffmpeg |

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
der Rhythmus-Fingerabdruck. Dasselbe getrennt fuer das Band 20-150 Hz;
unter 20 Hz ist ausgeschlossen.

16 Slots, weil ein 4/4-Takt genau 16 Sechzehntel hat; bei 140 BPM entspricht
das 1,71 s pro Takt. Die Mittelung ueber viele Takte macht das Muster robust
gegen einzelne Ausreisser.

Vorgesehen ist, dass **nur ueber Sektionen mit Beat** (`main`, `drop`)
gemittelt wird — ein Breakdown ohne Drums wuerde das Muster sonst
verwaessern. **Status: nicht umgesetzt** in der urspruenglichen Fassung
dieser Spec; ein paralleler Auftrag baut die Sektionsfilterung gerade nach,
siehe Commit-Historie.

### 5.2 Neue Track-Felder

```python
groove_pattern: list = field(default_factory=list)   # 16 Slots, L1-normiert
bass_pattern:   list = field(default_factory=list)   # 16 Slots, nur <150 Hz
syncopation:    float = 0.0                          # 0-1, Offbeat-Energieanteil
sub_energy:     float = 0.0                          # 20-60 Hz, relativ zur Gesamtenergie
bass_punch:     float = 0.0                          # Crest-Faktor des Bassbands
```

Vorgesehen ist, dass `sub_energy` und `bass_punch` **zweifach** gefuehrt
werden: als Trackmittel in den obigen Feldern (Anzeige, Fallback) und
zusaetzlich je Sektion in den Section-Dicts von `Track.sections` (Abschnitt
5.3). Das Scoring soll die Sektionswerte nutzen; die Trackmittel sollen nur
greifen, wenn fuer die betreffende Sektion kein Wert vorliegt. **Status: nicht
umgesetzt** in der urspruenglichen Fassung dieser Spec; wird gerade
nachgebaut, siehe Commit-Historie.

### 5.3 Bewusste Asymmetrie: Groove track-weit, Bass sektionsweise

Der Groove eines Tracks ist ueber seine Laenge weitgehend stabil, der
Bassdruck nicht — Intro und Drop unterscheiden sich massiv. Da die Sektionen
in `Track.sections` bereits `avg_bass` tragen (`dj_brain.py:1337` nutzt das),
kommt `sub_energy` dort daneben.

Beim Paar-Vergleich soll deshalb fuer den Bass **Outro von A gegen Intro von
B** gemessen werden, nicht Trackmittel gegen Trackmittel — ob zwei Tracks im
Durchschnitt aehnlich basslastig sind, ist fuer den Uebergang irrelevant; es
zaehlt, was an der Nahtstelle passiert. **Status:** in der urspruenglichen
Fassung dieser Spec verglichen sowohl `bass_continuity` als auch `mood_match`
ausschliesslich Trackmittel gegen Trackmittel — keines der beiden nutzte die
Nahtstelle. Fuer den Bass wird die Nahtstellen-Messung gerade nachgebaut
(siehe Commit-Historie); fuer `mood_match` bleibt es bewusst beim Trackmittel,
diese Aussage gilt nur fuer den Bass.

### 5.4 Rechenaufwand

`FeatureCache` (`analysis.py:53`) haelt Onset, STFT und HPSS bereits vor —
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
| `bass_continuity(a, b)` | Differenz von `sub_energy` und `bass_punch` an der Nahtstelle (Outro A / Intro B); `bass_punch` wird gegen die feste Modulkonstante `DEFAULT_PUNCH_DELTA_MAX` normiert, **nicht** gegen die Genre-Toleranztabelle — sie ist darueber nicht uebersteuerbar |
| `timbre_match(a, b)` | Kosinus-Aehnlichkeit der `timbre_fingerprint`; nutzt **nicht** die Logik aus `dj_brain.py:1382`, sondern eine eigene `cosine_similarity` in `transition_features.py:43`, die semantisch abweicht (die `dj_brain`-Variante verwirft den MFCC-Koeffizienten 0 und klemmt nicht auf [0,1]) |
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

- Vorgesehen: gelernte Werte in `hpg_core/data/transition_tolerances.json`,
  mitgeliefert. **Status:** die mitgelieferte Datei ist `{}`. Der
  Lernversuch bestand das eigene Holdout-Gate (Abschnitt 11) in keinem Lauf;
  die gelernten Werte wurden zurueckgezogen (Commit `d661bac`). Aktiv sind
  die eingebauten Defaults.
- Nutzer-Override: `%LOCALAPPDATA%\HPG\transition_tolerances.json` schlaegt die
  mitgelieferte Datei. Damit ueberlebt eine Anpassung Updates und die EXE.
- Fehlt die Datei oder ist ihr JSON kaputt, greifen die eingebauten Defaults.
  Ein defektes JSON darf den Start nicht verhindern; `hpg_core/tolerances.py`
  protokolliert den Fehler nur per `logger.warning` — der `error_reporter`
  (`logs/error_report.json`) ist dort **nicht** eingebunden.
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
bass_delta_max          # akzeptierter Sub-Sprung als dimensionsloses Leistungsverhaeltnis, kein dB-Wert
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

Vetos (harte Ausschluesse statt Abzug) sind **nicht** strukturell vorbereitet
im Sinne einer funktionierenden Mechanik — vorbereitet ist lediglich ein
Dict-Schluessel `groove_veto_enabled` ohne jeden Leser. Ein Genre soll ein
Veto nur bekommen, wenn das Mix-Mining zeigt, dass echte DJs diesen Uebergang
dort praktisch nie machen.

## 10. Kalibrierung (`tools/mix_mining.py`)

### 10.1 Material

Pro Genre 2-3 Mixe von 60-120 Minuten, was rund 30-60 Uebergaenge je Mix
ergibt. Quellen: eigene Mixe des Nutzers und oeffentliche DJ-Mixe. Tracklisten
liegen nicht vor und werden auch nicht benoetigt (Abschnitt 10.4).

### 10.2 Beschaffung: kein Umwandeln

HPG laedt Audio ueber `librosa.load` (`analysis.py:1316`, `:1468`, `:1850`)
und `sf.blocks` (`analysis.py:513`). Gemessen: libsndfile 1.2.2, soundfile 0.14.0,
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

Auf diese Fenster **soll** exakt dieselbe `groove.py` laufen wie in der App —
das ist Bedingung, nicht Bequemlichkeit: wuerden Kalibrierung und Anwendung
unterschiedlich messen, waeren die gelernten Zahlen nicht uebertragbar.
**Das war nicht der Fall:** der Miner ankerte auf `librosa.beat_track`, die
Produktion auf den Rekordbox-ANLZ-Downbeat, und der Miner vergleicht
rotationsinvariant. Deshalb wurde `groove_weight` verworfen (Commit
`e64e488`) — siehe "Was das Vorhaben gelehrt hat" am Ende dieser Spec.

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

Alle 9 kanonischen Genres sollen einen gelernten Toleranzsatz bekommen. Die
Reihenfolge der Bearbeitung richtet sich nach dem Anteil an der Sammlung:
Psytrance, Progressive, Techno, Melodic Techno, Tech House zuerst (zusammen
94,4 %), danach Minimal, Deep House, Trance, Drum & Bass. **Status:** wie in
Abschnitt 2 und "Was das Vorhaben gelehrt hat" beschrieben, tragen aktuell
alle 9 Genres identische, ungemessene Defaults statt gelernter Werte.

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

**Status:** beim ersten Einbau wurde diese Regel nicht eingehalten — die
gelernten Werte gingen trotz rotem Holdout-Gate in den Code und wurden erst
spaeter zurueckgezogen (Commits `d661bac`, `e64e488`). Das gehoert als Lehre
in diese Spec, nicht wegretuschiert; siehe "Was das Vorhaben gelehrt hat" am
Ende.

Zusaetzlich der Nutzer-A/B ueber `TRANSITION_FEATURES_ENABLED`: gleiche
Trackauswahl, alte gegen neue Sortierung.

## 12. Cache und Migration

`CACHE_VERSION` sollte von 29 auf 30 steigen. **Status:** der Stand ist
seither weitergelaufen, `CACHE_VERSION` steht inzwischen bei 31 und steigt
gerade auf 32. Alte Eintraege werden bei jedem Versionssprung nicht mehr
gelesen.

Das Loeschen der Altdateien in `C:\Users\david\AppData\Local\HPG\` (frueher
als offen beschrieben, 25 Dateien `hpg_cache_v18` bis `v29` samt `-wal`,
`-shm`, `.lock`, zusammen 1,46 MB) **ist inzwischen erledigt**. Musikdateien
und die Rekordbox-Datenbank blieben davon unberuehrt.

Anschliessend laeuft eine vollstaendige Analyse der Sammlung (2480 Tracks).
**Nicht verifizierbar** (Laufzeitangabe nicht erneut geprueft, hier nur
wiedergegeben statt geloescht): auf 16 Kernen und ueberwiegend im
Rekordbox-Fast-Path ist mit einer Groessenordnung von 15-40 Minuten zu
rechnen.

Die Umverteilungsregel aus 7.3 bleibt trotz des Loeschens im Code: sie deckt
Tracks ab, deren Analyse degradiert ist, nicht nur Altbestaende.

## 13. Fehlerbehandlung

- Fehlendes oder leeres `groove_pattern`: Faktor faellt weg, Gewicht wird
  umverteilt (7.3). Kein Abbruch, keine Bestrafung.
- `first_downbeat` ohne Konfidenz (`downbeat_confidence == 0.0`): kein
  Groove-Pattern berechnen. Ein Muster auf erfundenem Raster ist schlechter als
  gar keins.
- Defektes `transition_tolerances.json`: Defaults greifen, Fehler geht **nicht**
  nach `logs/error_report.json` — `hpg_core/tolerances.py` protokolliert nur
  per `logger.warning` (siehe Abschnitt 8), App startet normal.
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
- Die bestehende Baseline bleibt gruen. **Nicht verifizierbar** (Testzahl
  nicht erneut geprueft, hier nur wiedergegeben statt geloescht): 1506
  passed, Coverage 77,29 % (gemessen 2026-08-19). Der Abschlusslauf laeuft mit
  Coverage, nicht mit --no-cov.

Aufruf: `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`

## 15. Umsetzungsreihenfolge

1. `groove.py` mit Tests, ohne Anbindung.
2. Track-Felder, `analysis.py`-Anbindung, `CACHE_VERSION`-Bump (geplant 30,
   tatsaechlich inzwischen bei 31, steigt gerade auf 32).
3. `transition_features.py` mit Tests, ohne Anbindung.
4. Genre-Tabelle mit den Startgewichten aus 7.2, Drift-Validierung.
5. Scoring-Integration hinter `TRANSITION_FEATURES_ENABLED`, alle fuenf
   `scoring_context`-Konsumenten, Regressionstest.
6. JSON-Datei, Override-Pfad, GUI-Panel.
7. Altdateien loeschen, volle Analyse der Sammlung.
8. `mix_mining.py`, Mixe je Genre, Toleranzen und Gewichte lernen.
9. Holdout-Validierung, gelernte Werte einsetzen, A/B durch den Nutzer.

Schritte 1-6 aendern das Verhalten der App nicht, solange der Schalter aus ist.

## 16. Was das Vorhaben gelehrt hat

- Die Kalibrierung scheiterte nicht an der Zahl der Uebergaenge, sondern an
  der Zahl unabhaengiger Mixe (6-8 Cluster). Noetig waeren grob 25-30 je
  Genre.
- Die Zahlen, die die Reihenfolge heute tatsaechlich bestimmen, sind
  ungemessen: `0.44/0.28/0.28` in `playlist.py:413-415` und
  `GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2`, multipliziert mit 36 handgesetzten
  Genre-Kompatibilitaetswerten. Fast alle gemessenen Zahlen des Repos liegen
  dagegen hinter einem Schalter, der auf `False` steht.
- Ein Rundungsfehler in `quantize_to_grid` verschob Mixpunkte um eine volle
  Phrase (27 s bei 16-Bar-Phrasen); gefunden nicht durch Tests, sondern beim
  Hoeren des ersten Clips (Commit `839ba41`).
