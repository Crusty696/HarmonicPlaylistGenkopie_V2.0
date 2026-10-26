---
name: hpg-rekordbox
description: Use when working on HPG Rekordbox integration — RekordboxImporter, master.db, pyrekordbox, ANLZ/PQTZ-Beatgrid, get_first_downbeat, Cue-Points und Cue-Override, rekordbox_signature, Fast-Path, oder den Rekordbox-XML-Export.
---

# HPG Rekordbox

## Zwei Richtungen

**Import** (`hpg_core/rekordbox_importer.py`): liest die lokale
Rekordbox-`master.db` ueber `pyrekordbox`. Liefert BPM, Key, Genre, Dauer,
Cues und den ANLZ-Beatgrid. Optional — fehlt `pyrekordbox` oder die DB,
bleibt die Audioanalyse mit DSP und den verfuegbaren nativen Adaptern
moeglich; einzelne Faehigkeiten behalten ihre eigenen Modell-/Grid-Gates.

**Export** (`hpg_core/exporters/rekordbox_xml_exporter.py`): schreibt
Collection + Playlist mit BPM, Key, TEMPO-Beatgrid und POSITION_MARK-Cues.

`get_rekordbox_importer()` [hpg_core/rekordbox_importer.py] ist ein Singleton — nicht pro Track neu
instanziieren, der Cache-Aufbau scannt die ganze DB.

## Fast-Path

Liefert der Importer BPM, nimmt `analyze_track` den Fast-Path: BPM/Key/Genre
aus der DB, librosa nur `LIBROSA_FAST_PATH_DURATION = 360` s fuer Energy und
Genre-Features, `key_confidence = 1.0`. Laufzeitvorteile am konkreten Bestand
messen; eine feste Beschleunigung ist kein allgemeiner Vertrag.

## Mehrdeutigkeit: lieber nichts als falsch

Die reale lokale `master.db` hatte 2665 Content-Zeilen mit 77 doppelten
normalisierten Pfaden und 60 mehrdeutigen Basenames. Der Importer loest das
so — `_build_track_cache` [hpg_core/rekordbox_importer.py]:

| Fall | Verhalten |
|---|---|
| gleicher Pfad, **widerspruechliche** Felder (`_track_data_conflicts` [hpg_core/rekordbox_importer.py]) | Pfad landet in `_ambiguous_paths`, `get_track_data` liefert `None` |
| gleicher Pfad, ein Record klar besser analysiert (`_track_data_quality` [hpg_core/rekordbox_importer.py]) | besserer Record gewinnt (z. B. gegen BPM `0`) |
| gleicher Basename an anderem Pfad | kein Identitaetsbeweis -> keine Rekordbox-Daten fuer Analyse, Signatur oder ANLZ |

`get_statistics()` und `get_available_count()` zaehlen nur eindeutige Pfade.
`get_track_data` bevorzugt exakte, nicht widerspruechliche Pfade. Fehlt ein
exakter Pfadtreffer, ist seit Cache 67 nur der unten beschriebene streng
gepruefte Volume-Rebind zulaessig. Ein eindeutiger Dateiname allein beweist
keine Byteidentitaet; ein Basename-Fallback bleibt ausgeschlossen. **Regel:
bei Zweifel `None` zurueckgeben.**

Bei einem reinen Laufwerkswechsel kann der Importer seit Cache 67 nach einem
konservativen `volume_rebind` suchen: gleicher normalisierter Pfadrest und
genau ein Kandidat, dazu direkte Mutagen-Tags plus Dateigröße und Länge. ISRC,
Titel, Künstler und Bytes müssen exakt übereinstimmen; die auf ganze Sekunden
gerundeten Längen dürfen höchstens 1 s abweichen. Fehlende
Werte bedeuten Ablehnung. Das ist Metadaten-Korroboration, kein Byteidentitäts-
oder musikalischer Ground-Truth-Beweis. Diagnose und Signatur führen die
Matchart; sämtliche Grid-/Phrasenfreigaben bleiben unverändert.

## Zeit-Einheiten — der teuerste Fehler

pyrekordbox liefert flache `PQTZAnlzTag.times` bereits in **Sekunden**; diese
Werte werden direkt als `float` uebernommen. Nur rohe Entry-Zeiten (`.time`)
und Cue-Werte (`InMsec`) sind Millisekunden und laufen durch
`_milliseconds_to_seconds` [hpg_core/rekordbox_importer.py] (`/1000.0`, gerundet auf 4 Stellen,
negative und nicht-endliche Werte -> `None`). Einheiten duerfen nicht aus der
Zahlengroesse geraten werden; die jeweilige pyrekordbox-Feldsemantik ist
verbindlich.

## ANLZ-Beatgrid

`get_first_downbeat(file_path)` [hpg_core/rekordbox_importer.py] -> `get_beatgrid(file_path)` [hpg_core/rekordbox_importer.py] ->
`_read_anlz_files(content_id)` [hpg_core/rekordbox_importer.py] -> `_extract_beatgrid_from_anlz` [hpg_core/rekordbox_importer.py]:
sucht in den ANLZ-Dateien die
Tags `PQTZ`, `PQT2`, `beat_grid`, `beats` und darin den ersten Tick mit
`beat == 1`. Zwei Tag-Formen werden unterstuetzt (flache Parallel-Listen
`.beats`/`.times` **und** iterierbare Entries mit `.beat`/`.time`) —
pyrekordbox liefert je nach Version unterschiedliche Formen; RB-01 war genau
hier ein still toter Pfad.

`_read_anlz_files` ist der gemeinsame Leser fuer alle ANLZ-Dateien
(DAT/EXT/2EX) eines Tracks — probiert `db.read_anlz_files(content_id)`, dann
`db.read_anlz_file(content_id, "DAT")`; beide `get_first_downbeat` und
`get_phrases` gehen darueber, damit es nur eine robuste Leseroutine gibt.

Ein ANLZ-Treffer ist zunaechst ein Referenzkandidat. Beide Analysepfade in
`analysis.py` setzen dessen `downbeat_confidence` nur bei
`beatgrid_validation.status == "verified"` auf 1.0. Andernfalls wird der
Audio-Anker ermittelt; die Abweichung bleibt diagnostizierbar. PSSI wird nur
bei Rekordbox-Quelle UND verifiziertem Grid uebernommen.
Nur vollständig mit Lesestatus `ok` importierte Phrasen werden weitergegeben.
In analysierten Audiofenstern bestimmen gültige PSSI-Intervalle auch die
Strukturgrenzen; außerhalb ihrer Abdeckung bleibt die DSP-Struktur erhalten.
Abschnittsenergie und Labels bleiben Audioauswertung, keine PSSI-Modelllabels.
`TransitionClipSpec.from_plan` trennt Beat- und Taktphasen-Verlaesslichkeit
und setzt `strict_beat_sync=True`. Ein verifiziertes Grid ist ein technischer
Vergleichsnachweis, keine unabhaengige musikalische Takt-1-Ground-Truth.
Ein verworfener Referenzversuch bleibt unter `anchor.reference.measurement`
persistiert. `_reference_grid_summary` in `measurement_panel.py` zeigt dessen
Phasenmuster und signierten Mittelpunkt getrennt vom aktiven Audio-Grid; ein
Zeitversatz wird dadurch nicht als Taktrotation oder automatische Gridkorrektur
ausgegeben.

Bei `reference_constant_offset` liegt ein als `consistent_offset` gemessener
Audio-minus-Grid-Phasenversatz über der 6-ms-Grenze vor. Ab Cache 85 darf HPG
bei reiner Zeitverschiebung ohne Bar-Rotation oder bei bestätigter Rotation
einen abgeleiteten Audioanker nur nach drei disjunkten Bestätigungsfenstern je
Model 7/8, separater lokaler Audiophasenprüfung und verifiziertem Gesamtgrid
übernehmen. Rekordbox-Rohticks und Bar-Labels bleiben unverändert. Der technische
Beatnachweis beweist keine unabhängige musikalische Takt-1-Zuordnung.
Rotation-0-Korrektur wird verworfen, wenn der signed Offset den Anker aus dem
aktuellen Bar-Intervall schieben würde; keine implizite Ein-Bar-Phasenverschiebung.

Seit Cache-Version 80 darf der Taktpositionsvergleich die Modellbeats für die
Diagnose gegen um den gemessenen Phasenmittelpunkt projizierte PQTZ-Ticks
abgleichen. Ein Treffer bleibt `candidate_rotation` und aktiviert die
vorhandene PSSI-/Mixpunkt-Sperre. Da derselbe Modellfenstersatz die
Offsetmessung und den Vergleich trägt, ist das keine unabhängige Bestätigung;
Grid, aktiver Anker und Sync-Freigabe ändern sich nicht.

Wenn die gespeicherte Schema-v5- oder -v6-Taktpositionsdiagnose einen
einheitlichen, gemessenen `candidate_rotation` ausweist, sperrt HPG vorsorglich
PSSI-/Phrasen-Nutzung und Mixausgaben. Die v6-Erweiterung um Phrase-Details
darf die Rotationssperre aus v5 nicht umgehen; Cachevalidierung und
Messanzeige verwenden denselben Helper. `_add_beat_grid` exportiert dann kein `Battito=1`;
`_cue_export_allowed` verwirft auch extern uebergebene Mixpunkte. Eine Rotation
wird nur uebernommen, wenn beide Modelle in allen drei Fenstern uebereinstimmen,
sechs Audiofenster die Kandidatenphase innerhalb 6 ms bestaetigen und das
Gesamtgrid verifiziert ist. Der aktive Anker bleibt dann Audioherkunft; PSSI
und Rekordbox-Render-Sync werden nicht freigegeben. Reine DSP-Bestaetigung hebt
die Sperre nicht auf.

Neuronale Beat-/Taktanker werden erst uebernommen, wenn **Model7 und Model8
jeweils** mindestens drei getrennte, audio-bestaetigte Fenster liefern und das
Gesamtgrid den bestehenden 6-ms-Vertrag besteht. Drei Fenster nur eines
Modells reichen nicht.

Fuer neuronale Rekordbox-Integration zuerst `hpg-deep-analysis` verwenden.
DLL-/Modellvertraege gehoeren zu `hpg-deep-analysis-artifacts`; DB-/ANLZ-/Cue-
und Exportvertraege bleiben hier. Bestehende Verfahren anhand belegter
Abloesekriterien optimieren oder ersetzen, keine doppelte Dauerimplementierung.

**Vertrag:** der Importer liefert ausschliesslich den **Takt**-Anker
`first_downbeat`. Der Phrasen-Anker entsteht downstream — Skill
`hpg-mixpoint-engineering`.

## PSSI-Phrasen (`get_phrases` [hpg_core/rekordbox_importer.py])

`get_phrases(file_path, *, duration=None)`, memoisiert je
`(content_id, effective_duration)`: Als effektive Dauer gilt zuerst die
explizite endliche positive Dateidauer, danach die endliche positive
Rekordbox-Dauer, sonst `0.0`. Die Funktion holt ueber `_read_anlz_files` die
EXT-Datei mit dem `PSSI`-Tag und die DAT-Datei mit dem `PQTZ`-Tag und delegiert
an `rekordbox_phrases.phrases_from_anlz`. Leer, wenn kein Rekordbox-Eintrag,
keine EXT-Datei oder kein PSSI-Tag vorliegt.

Der Importer behaelt Typ und erkennbaren ANLZ-Dateistamm aus
`read_anlz_files` im gemeinsamen Snapshot. Er verbindet EXT/PSSI und DAT/PQTZ
nur bei gleichem Stamm. Fehlt der Stamm auf einer Seite, ist die Verbindung nur
bei genau einem passenden EXT- und einem passenden DAT-Kandidaten erlaubt.
Mehrdeutige Kandidaten bleiben ohne Phrase-Daten; sie werden nicht nach
Listenreihenfolge oder durch unsichere Kreuzpaarung zusammengesetzt. Ein
einzelnes anonymes Kombinationsobjekt mit beiden Tags bleibt als Reader-Fallback
zulaessig.

`get_track_signature` ruft `get_phrases(file_path)` bewusst parameterlos auf;
die mit Rekordbox-Dauer beziehungsweise `0.0` abgeleiteten Phrasen bleiben
Teil der Rekordbox-Signatur. Fast-Path und BPM-loser Vollpfad uebergeben dagegen
jeweils die echte `file_duration`, damit Analyse-Phrasenenden am Audiosignal
enden. Die getrennten Memo-Keys verhindern, dass beide Verwendungen einander
vergiften.
Beim Signatur-Neuaufbau werden `_anlz_cache` und `_anlz_files_by_kind` gemeinsam
verworfen; Beatgrid und Phrasen der neuen Signatur stammen danach aus demselben
frisch eingelesenen Snapshot. Die Aenderung fuegt kein persistiertes Track-Feld
hinzu; die bereits signaturgebundene Phrasenausgabe bestimmt Cache-Invalidierung.

`phrases_from_anlz` (`hpg_core/rekordbox_phrases.py`) liest die Phrasengrenzen
aus PSSI und die Zeiten aus dem PQTZ-Beatgrid: `entry.beat` ist ein
**1-basierter Index** in die PQTZ-Beatliste (verifiziert an 699 von 2475
EXT-Dateien; 0-basiert passt nie; der erste Eintrag liegt im Vollbestand
(2470 DAT) in 677 Faellen auf beatnum 2, 74x auf 3, 70x auf 4). Zwei
Label-Tabellen je nach PSSI-`mood`:
`PHRASE_LABELS_HIGH` (mood 1: Intro/Up/Down/Chorus/Outro) und
`PHRASE_LABELS_MIDLOW` (mood 2/3: Intro/Verse 1-6/Bridge/Chorus/Outro).
Rohe Beatgrid-Floats, keine Rundung — dieselbe 3-ms-Falle wie beim
Mix-In-Rundungsfehler (`hpg-mixpoint-engineering`).

Der lokale Cue-Phrasen-Regressor bewertet vorhandene PSSI-Kandidaten; er erzeugt
keine eigenen Phrasengrenzen. `score_phrase_candidates` verlangt
`verified_grid is True`. Ein roher Modellscore ist weder Wahrscheinlichkeit
noch musikalisches Label und darf nur innerhalb der bestehenden
Kandidaten-/Tie-Break-Regel wirken. Audio-only oder korrigierte Audioanker
liefern deshalb keine Rekordbox-PSSI-Kandidaten an diesen Pfad.

## Cue-Override (liegt in analysis.py, nicht im Importer)

`CUE_IN_PATTERN` / `CUE_OUT_PATTERN` [hpg_core/mix_candidates.py], angewendet
in `analyze_track` [hpg_core/analysis.py]. Wortgrenzen-Regex, **nicht** Substring:

```
IN : \b(MIX[- ]?IN|IN|START)\b
OUT: \b(MIX[- ]?OUT|OUT|OUTRO|END)\b
```

`INTRO` markiert den Intro-START und ist bewusst **kein** Mix-In.
`BREAKDOWN` darf kein OUT ausloesen. Erster Treffer gewinnt (deterministisch).
Nur **benannte** Cues (`provenance == "manual"`) zaehlen.

Die Positionsheuristik fuer unbenannte Hot-/Memory-Cues ("2. Cue = Mix-In,
letzter = Mix-Out") ist entfernt (Spec 2026-08-21) — unbenannte Cues sind
jetzt Kandidaten (`mix_candidates.py`), kein Override mehr. Damit entfaellt
auch der zugehoerige Intro-Guard `cue_in_verwerfen`; die Funktion bleibt im
Modul, wird im Produktivpfad aber nicht mehr gerufen.

Uebernommen wird nur bei `0 <= in < out <= duration`, und **immer** durch
`align_ai_mix_points(..., anchor=phrase_anchor)` quantisiert.

## Cache-Invalidierung

`get_track_signature(file_path)` [hpg_core/rekordbox_importer.py] geht in den Cache-Key ein. Rekordbox-
Metadaten aendern sich ohne Aenderung der Audiodatei — ohne Signatur liefert
der Cache still alte BPM/Key/Cues. Siehe `hpg-cache-persistence`.

## Export

`export()` [hpg_core/exporters/rekordbox_xml_exporter.py] legt die Playlist ueber
`add_playlist_folder("HPG Playlists").add_playlist(...)` an — `get_playlist()`
wirft auf frischem XML immer `ValueError`. `_add_beat_grid` [hpg_core/exporters/rekordbox_xml_exporter.py] schreibt
`TEMPO` mit `Inizio=first_downbeat`. `_add_cue_points` [hpg_core/exporters/rekordbox_xml_exporter.py] schreibt
POSITION_MARKs, aber nur wenn `_cue_export_allowed` [hpg_core/exporters/rekordbox_xml_exporter.py] haelt
(`outro_covered` und `duration > 0`).

## Verifikation

`tests/test_rekordbox_importer.py` deckt Pfadkonflikte,
analysierte-vs-unanalysierte Duplikate und mehrdeutige Basenames ab.
`tests/test_rekordbox_xml_exporter.py` den Export. Fuer echte DB-Laeufe gezielte
Read-only-Rekordbox-Pruefungen mit `hpg_core/rekordbox_readonly.py` und echten
Testdaten verwenden und quellgebunden dokumentieren. Der ehemalige
Root-Mockbenchmark war kein DB-Lauf und wurde archiviert.

## Common Mistakes

- Flache `PQTZAnlzTag.times` erneut durch 1000 teilen oder rohe Entry-/Cue-
  Millisekunden ohne `_milliseconds_to_seconds` uebernehmen.
- Bei Mehrdeutigkeit "den ersten Treffer" nehmen.
- Cue-Namen per Substring matchen.
- Cue-Override roh setzen ohne Quantisierung.
- Die entfernte Positionsheuristik ("2. Cue = Mix-In") wiederbeleben statt
  `mix_candidates.py` zu erweitern.
- Neuen Importer pro Track bauen statt `get_rekordbox_importer()`.
- Nur eine ANLZ-Tag-Form unterstuetzen.

## XML-Export mit Kandidaten (Teil 4, gebaut 2026-08-22)

`RekordboxXMLExporter.export(playlist, path, name, transitions=None)`: mit
Empfehlungen schreibt `_kandidaten_punkte` je Playlist-Position MIX OUT aus
`transitions[i].plan.mix_out_a`, MIX IN aus `transitions[i-1].plan.mix_in_b`
(nur bei `kandidat_aktiv > 0`), dazu Memory-Cues `HPG K<n> OUT|IN <schema>`
(`_kandidaten_cues`: n je Seite fortlaufend 1..6 nach Dedupe gleicher
Zeitpunkte — nicht `PairCandidate.rang`). `_cue_export_allowed(track, mix_in,
mix_out)` prueft die effektiven Punkte; Gate `outro_covered` bleibt.

## Native Gesamtanalyse und Export (16.10.2026)

`native_track_beats.has_verified_grid` prüft den nativen Snapshot samt optionaler
Audio-Zeitkorrektur sowie die Übereinstimmung mit aktivem Tempo und Anker.
Renderer und XML-Export verwenden dieselbe Freigabe; Taktpositionssperren bleiben
wirksam. Native Herkunft wird nicht als DB-Import oder musikalische Ground Truth
bezeichnet. Die bestehende Messdiagnose zeigt Herkunft und Zusatzmerkmalsabdeckung.
Details und Nachweisgrenzen stehen im Deep-Analysis-Auftrag, nicht in einer zweiten
Statusliste. Originalquellen und native Modellartefakte werden nicht versioniert.
