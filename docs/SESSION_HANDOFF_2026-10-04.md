# HPG: Session-Uebergabe 04.10.2026

## Auftrag, Prioritaet und ehrlicher Stand

Dieser Bericht ermoeglicht die Fortsetzung ohne Chatvorwissen. Der Nutzer
beendete die laufende Umsetzung zugunsten einer vollstaendigen Zusammenfassung,
lokalen Sicherung durch Commit und Push sowie synchronisierter Dokumentation.
Das ist ein **Entwicklungszwischenstand, keine vollstaendige Produktabnahme**.
Der gesamte freigegebene Plan ist NICHT fertig. Vor einem neuen Arbeitslauf
aktuellen Nutzerauftrag erfragen/lesen; die alte Autonomie nicht aus einem
historischen Dokument als neue Anweisung ableiten.

Projekt: `C:\Users\david\Documents\HarmonicPlaylistGenerator_V2.0`.
Branch beim Checkpoint: `main`, Upstream `origin/main`.
Remote: `https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0.git`.
Ausgangscommit dieser Umsetzung: `50ea5222e92867436f63472da494868d50703f23`.
Ankerforschung separat gespeichert: `1b7a06ae4fbd39a2098642f249562d375be3dc31`.
Der abschliessende Session-Commit wird anhand von `git log -1` ermittelt,
nicht durch einen selbstreferenziellen erfundenen Hash in dieser Datei.

Einstieg: AGENTS.md, docs/PROJECT_KNOWLEDGE.md, diese Uebergabe,
docs/superpowers/plans/2026-10-04-sammlung-training.md und relevante Skills.
docs/IMPLEMENTATION_2026-10-04.md dokumentiert den vorherigen Teil dieser
Umsetzung; seine zeitlich frueheren offenen Punkte nicht als heutigen Iststand
uebernehmen. Alte Statusberichte sind keine Freigabe des aktuellen Builds.

## Wozu die App gedacht ist

HPG soll grosse Musiksammlungen anhand individueller Audioanalysen,
Rekordbox-Referenzen und lokaler Mix-In-/Mix-Out-Fenster untersuchen. Ziel sind
gut passende gerichtete Trackpaare und die bestmoegliche gefundene Playlist-
Reihenfolge nach Klang, Groove, Rhythmus, Energie, BPM, Harmonie, Bassdruck,
Klangfarbe, Lautheit, Struktur und weiteren vereinbarten Messwerten. Sie soll
manuelles Ausprobieren sehr vieler Paarungen ersetzen, neue Ideen finden und
alte mit neuer Musik kombinieren. Ein blosses Vorbereiten von Uebergaengen
oder ein externer Zweit-Workflow reicht nicht: die Funktionen muessen aus der
App erreichbar sein und dort in Playlistplanung, Hoertests und Training wirken.

Das Zusatzwerkzeug unter tools ist ein zusaetzlicher Daten-/Bewertungsweg,
kein Ersatz fuer fehlende App-Funktionalitaet. Gemeinsame interne Dienste sind
erwuenscht, ein zweiter widerspruechlicher Producer nicht. Kein N!-Versprechen:
alle Permutationen von 2400 Tracks exakt durchzusuchen wird nicht zugesagt.
Unsichere Messungen bedeuten nicht automatisch musikalische Unvertraeglichkeit.
Vocals registrieren reicht; unbekannte Vocals allein duerfen kein Paar sperren.

LM Studio/Ollama sind bereits optionale Einbindungen. Die langfristige Idee
ist ein austauschbares lokal betreibbares Modell mit echtem Audio-/Musikverstehen.
Der aktuelle Metadaten-LLM-Pfad beweist diese Faehigkeit NICHT. Keine Modell-
Eignung aus Namen ableiten. RX 7800 XT mit 16 GB VRAM statt iGPU war ausdruecklich
verlangt; vorhandene GPU-/Schema-Nachweise sind modell- und laufgebunden.

## Unverletzliche Schutz- und Arbeitsregeln

- Originalmusik, Tags und ID3 unveraendert am Quellort lassen. Niemals kopieren,
  verschieben, umbenennen, loeschen, zurueckschreiben oder in Git, Projektkopien,
  Backup beziehungsweise Recovery-Snapshots aufnehmen. Nur lesend analysieren
  und source-direkt abspielen. Keine dauerhaften oder temporaeren Hoertest-WAVs
  als neuer Arbeitsablauf; Playback/Audit bei Bedarf im RAM.
- Rekordbox-DB und ANLZ ausschliesslich lesen; keine WAL-/SHM-/Journalwrites.
  Eigene Indizes, Snapshots, Ratings und Praeferenzen gehoeren unter
  `%LOCALAPPDATA%\HPG`, nicht in die Sammlung oder Git.
- Bestehende wertvolle Dirty-Aenderungen bewahren. Keine neue Worktree-/App-
  Kopie. `Claude-Autopilot-v5/`, `Claude-Autopilot-v6/` und ZIP nie anfassen/stagen.
- Caveman zuerst laden; knapp Deutsch schreiben, aber Unsicherheit nie kuerzen.
  HPG-Skills und unabhaengige read-only Reviews vor Umsetzung/Commit verwenden.
- Absicht, aktuelle Beobachtung, ausgefuehrte Tests und subjektive musikalische
  Bewertung getrennt melden. Kein "alles funktioniert" aus gruenen Mocks.
- Guel­tige unveraenderte Tests wiederverwenden. Wiederholungen brauchen einen
  konkreten Fehler, relevante Aenderung oder fehlenden Nachweis. Ein Hauptagent
  koordiniert teure Laeufe; nie zwei volle pytest-Laeufe parallel, relevante
  Dateien waehrend eines codegebundenen Laufes einfrieren.
- Zentrales Hirn: vor Befehlen/Aenderungen `POST http://localhost:3000/recall`
  mit `{"frage":"konkrete Aufgabe","limit":3}`; nach geloesten Problemen
  `POST /remember` mit text, agentName Codex und kind regel/fehler/architektur/
  hardware/setup. Endpoint in dieser Session benutzt und Speichern bestaetigt.

## Umgebung und sichere Befehle

- PowerShell, Python 3.12.10: `venv312\Scripts\python.exe`.
- Aktueller Quellvertrag: APP_VERSION 3.7.2, CACHE_VERSION 46. Neues strikt
  validiertes Trackfeld measurement_diagnostics; Cache45-Belege sind historisch.
  Standardcache: `%LOCALAPPDATA%\HPG\hpg_cache_v46.db`. Originalcache nie fuer
  Tests loeschen/umbauen. Isolierte Umleitung mit HPG_CACHE_FILE/HPG_CACHE_DIR.
- Start.bat ruft das aktuelle main.py mit venv312 auf. Vorhandene EXE ist
  **nicht neu gebaut oder auf aktuellem Stand abgenommen**. Keine neue EXE
  behaupten, bevor absoluter Pfad, SHA256, Build und nativer Lauf gebunden sind.
- Abschluss-Vollsuite bei spaeterer Produktabnahme:
  `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`.
  pytest.ini enthaelt bereits -n auto und Coverage-Gate 70 Prozent.
- Kleine isolierte Modulpruefung: `-B -m pytest <konkrete Tests> --noconftest
  -n 0 --no-cov -p no:cacheprovider --tb=short -q --color=no`; das ist KEINE
  Coverage-/Gesamtabnahme. Befehl, Exit, JUnit und relevante Hashes festhalten.
- Python-Code fuer PowerShell `-c` als single-quoted Here-String in eigener
  Taskvariable uebergeben. Verschachtelte Quote-Escapes verursachten SyntaxError.
- Nicht komplette JSONL-Matchzeilen aus alten Sessions ausgeben: einzelne
  Zeilen enthalten sehr grosse Kontexte. Exakte ordinal suchen, JSON parsen,
  nur benoetigte status/exit/command/stdout-Felder ausgeben.
- Windows os.path.isfile hat einen nativen Schnellpfad. Nur os.stat zu mocken
  reicht fuer RAM-Statfixtures nicht; isfile im Test explizit mappen. Keine
  Produktregel fuer einen fehlerhaften Mock abschwaechen.

## Quellen und tatsaechlich gelesene Daten

Originalmusik:

1. `F:\beatport_tracks_2026-04`
2. `F:\neue techno sammlung nur beatport musik`
3. `F:\neue Psy-Trance, Progressive nur Beatport musik`
4. `F:\HPG-Melodic-Techno-v45-Analyse-2026-09-14`
5. Zusaetzlich genannt: `E:\02_Musik_&_Medien\Musik_&_Audio\Audio_Clips` (DJ-Sets).

Rekordbox: `F:\PIONEER\Master\master.db` und Unterordner mit ANLZ.
Aktuelle get_config-Probe: rekordbox7 liefert diesen db_path, rekordbox6 keinen.
Geschuetztes get_content().all() las 2693 Records, davon 2490 mit AnalysisDataPath.
DB 71401472 Bytes, mtime_ns 1791115112711145700,
SHA256 `d40ce07bb1292540907402638bfeeeb494f5e5e19a22ceadaa9a1deb28487715`
vor/nach identisch, WAL/SHM/Journal abwesend. Erst .all() materialisiert die
Query; len(Query) war ein frueherer fehlerhafter Probeaufruf ohne DB-Abfrage.

Stat-only Inventar der vier F-Musikroots: 2631 Eintraege, kein Fehler/Abbruch.
Dies beweist weder Audioqualitaet noch eindeutige Rekordbox-Identitaet.
Mapperpilot: 26/26 Tracks des ersten Roots nur per Basename, NICHT exact;
26 positive Beatgrids, 26 positive Phrasen, Signaturen vorhanden, keine
Detailfehler. 78 gelesene ANLZ-Dateien und DB-Familie SHA/size/mtime unveraendert.
Parser warnt PVDI unsupported; PQTZ/PSSI konnten gelesen werden. Ein eindeutiger
Dateiname beweist keine Byte-/Audioidentitaet zum historischen FolderPath.
Auch Byteidentitaet allein beweist keine korrekte Gridphase. Kein weiterer
Vollscan der Platten E/D/F ist fuer die Fortsetzung dieser Pakete erforderlich.

## Implementierte Pakete und begrenzte Belege

- **Readonly Rekordbox:** rekordbox_readonly.py, Importerhook. Windows-Lesehandles
  pro materialisierter Operation; immutable/query_only SQLCipher/SQLite; unsichere
  Writer/WAL geschlossen ablehnen. Verbindung vor Handles schliessen. Fehlende
  optionale ANLZ-Ordner bleiben leer, korruptes EXT verhindert DAT-Fallback nicht.
  Reader/Importer 169 Tests, 6.27 s. Originalbefehl in Session ordinal27341 gelesen;
  kein Wiederholungslauf. Spaeterer memo-only get_track_read_status unterscheidet
  ok/missing/error/unverified ohne erneuten ANLZ-Zugriff: 147 Tests, 5.81 s,
  temporaere echte SQLite-/SQLCipher-Strecken; enges Review bestanden.
- **Sammlungsinventar:** collection_index/jobs/panel; rekursiv, stat-only,
  unbegrenzter Index, deduplizierte Roots, transaktioneller Rollback, eigenes
  striktes JSON. Parentlose Worker/LIVE_WORKERS bis echtem finished.
  Basis60 Tests/2.89 s. Main-Dialogreferenz und Parentclose konkret RED/GREEN:
  zehn Main-Integrationstests/1.01 s; keine native Vollabnahme daraus.
- **Zuordnung:** collection_rekordbox.py, 31 Tests plus mtime-Delta. Exact/
  basename/ambiguous/missing/unavailable, Vorhandensein nicht Genauigkeit.
  collection_mapping_state.py: eigenes versioniertes atomares JSON, exakte
  Index-/Cachebindung, Unknown-Preserve; 94 Tests/2.66 s, Main TOR2 bestanden.
  Native Save/Load: 48 Tests/1.29 s, Hashfreeze und JUnit gelesen. Geladene Werte
  immer saved_not_fresh, stale/Cancel/Close-Guards. Reviewer findet keinen
  Produktfehler, aber ein Test prueft spaetes Cancel ohne gueltige Ausgangsroots;
  Kontrollfall plus vollstaendige Roots als offene Testverbesserung festhalten.
- **Messdiagnosen:** downbeat.py explizite Gruende/Windowwerte ohne neue Gates;
  48 Tests/2.86 s. measurement_contract.py, Track/analysis/cache46: 381 Tests
  plus zwei Decode-/Schemafaelle; enger Review bestanden. Keine neue komplette
  Originalaudio-Abnahme beider Analysepfade behaupten.
  MeasurementDialog zeigt nur aktuelle Tracks, alte/leere Diagnose unknown,
  2500 RAM-Tracks mit Details nur fuer Auswahl: elf Tests/2.52 s. Main-Anschluss
  zwei Faelle/0.81 s plus Signalnachtest/0.97 s. Keine Playlist als Ersatzquelle.
- **Lokale Ankerforschung5A:** anchor_research.py; plan/evaluate/run, frozen
  Source-/Build-/Parameterbindungen, Budget, Reuse ohne Decoder, drei lokale
  Fenster, getrennte Beat-/Takt-/Phrasenevidenz. Vier Beatverschiebungen sind
  nur Hypothesen, kein bewiesener Takt. 74 Tests/0.60 s mit echter Faltung auf
  synthetischen RAM-Signalen; Main TOR2 bestanden. Hash:
  `9B78FA30BBE84CDF795D8D7D3D84B235290E2DFFD9ECB823D5FF81346409D70C`.
  Reader injiziert; Callerhash ist kein Kern-Quellnachweis. Sicherheitsfehler
  muessen AnchorResearchError ausloesen und den ganzen Lauf abbrechen.
- **Kohortenkern8A:** hearing_cohorts.py; gesamter Index, Auswahl max1000,
  seedgebundene Roundrobin-Strata Genre/Tempo10/Energiequartile/Beatgridstatus.
  Stale Features werden unbekannt, Track bleibt waehlbar. Vollstaendiger
  Eingangs-/Feature-/Kontextdigest; kein Ratingreuse. Zwei erste Tests/0.52 s,
  danach25 Deltatests/1.20 s, Hashfreeze. Bool-Version vorher konkret RED,
  strikter gebundener Vergleich korrigiert. TOR2 kein Produktbefund, formale
  historische Beleggrenzen offen; kein Wiederholungslauf nur fuer Review.
- **Kohortenanalysedienst8B:** hearing_collection.py nutzt bestehenden
  ParallelAnalyzer exakt mit ausgewählten Pfaden, keine positionsweise
  Fehlerzuordnung. Fremde/duplizierte Results abweisen; Ressourcen/Modi/Schema
  pruefen; fehlende Results generisch melden. Stat/Reparse vor/nach, kein SHA-
  oder Frisch/Cachehit-Versprechen. Immutable JSON-Snapshots, kein eigener
  Writer; bestehender Analyzer kann eigenen Cache nutzen. Neue19 Tests:
  nach Umstellung auf reine .fixture-Metadaten zuerst13 bestanden/6 Fixture-
  Fehler (Windows isfile); nur diese6 danach bestanden/0.53 s. Produkt unveraendert.
  JUnit: TEMP/hpg-cohort-analysis-fixture-delta.xml und -fixture-fix.xml.
  Kein unabhaengiges TOR2 und kein nativer Anschluss bislang.

## Noch nicht erledigt: verbindlicher Fortsetzungsplan

Alle zwoelf Pakete im Plan getrennt behandeln; keine Haken aus Testzahlen ableiten.

1. Aktuelle Quellen, Gitstand und hier beschriebene Freeze-/Reviewbelege lesen.
   Noch offene Reviews und Testkontrollfaelle abschliessen, ohne Vollanalysen zu
   wiederholen. Nachfolgende Abschlussnachtraege beachten.
2. Lokaler Ankerforschung5B: realer readonly Fensterleser, Sourcehash/-Statbinding
   und Algorithmusbindung, eigener Worker/konkreter nativer Button. Kein DSP
   allein beim Oeffnen. Pilot zwei explizite Tracks, je hoechstens drei Fenster;
   Quellenfehler fatal, keine Audioausgabe. Separates Review vor Umsetzung.
3. Research6: versionierter Zweck regular/research in Workflow, Source- und
   Kandidatenmanifest, Loader, Playback/Audit. Ein Producer, keine mutierten
   Track-Konfidenzen und keine pauschale allow_experimental-Umdeutung.
   Musikalische und technische Zulassung trennen; strikte Synchronisation,
   Zeit-/Coverage-/Stretch-/Blenden-Gates im ersten Schnitt erhalten.
   Nicht abspielbare Variante als technischen Ausschluss zeigen.
4. Bewertungen7: unrated/rated/unassessable je Dimension; Paarentscheidung
   pending/winner/none_suitable/unassessable. Keine automatische Note1 oder
   negatives Lernbeispiel fuer fehlende/unbeurteilbare Werte. Alte gewaehlt=0
   bedeutet historisch Keine-Beste, nicht erfundene None-Suitable-Aussage.
   Schema gemeinsam durch Writer, native/HTTP-UI, Loader, Audit und Fit fuehren.
5. Sammlungstraining8: nativer Count-/Seed-/Pooldialog, mehrere Roots, exakte
   kleine Kohorte; Quellen vor Analyse erneut pruefen. Nicht normalen
   start_analysis missbrauchen: der Ordnerscanner endet noch bei1000, auch
   sanitize_playlist deckelt. Neue reine Kerne sind noch nicht GUI-verbunden.
   MultiRoot privateSnapshots/association getrennt versionieren. Analysedienst
   durch hearing_worker-Lebenszyklus anschliessen, Vorbereitung erst nach
   echtem Threadende und vollstaendigem Snapshot. Rating-/Variantenreuse braucht
   Source+Spec+Buildbindung, nicht bloss gleichen Pfad/Seed.
6. Kalibrierung9: RAM-Receipt-Ein-Durchlauf-Umstellung siehe Nachtrag. Native
   SourceSpec == unabhaengig ProducerReplaySpec vor DSP; eine echte PCM-Ausgabe,
   Digest/Metadaten/drei Kick-Lags. Kein erfundenes ReferenzPCM-Feld. Legacy
   weiterhin einReplay gegen vorhandenes readonlyWAV-PCM. Gemeinsamer strikter
   Validator in Fit/Proposal/Export/Apply, nur purpose=regular. Research ist
   keine automatische Kalibrierfreigabe. Fit bleibt isoliert, Apply bewusst.
   Erkannte Trackversionen gegen Train/Holdout-Leak gruppieren, Baseline der
   bestehenden Gewichte zusaetzlich zur Zufallsbasis pruefen; bisher nur
   Pfadholdout und Zufallsbasis gelesen. Rollback und sichtbare Unsicherheit
   gehoeren weiter zum Auftrag.
7. Skalierung10: gerichtete Paarergebnisse versioniert wiederverwenden, kleine
   Sequenzen, Pause/Fortsetzung identischer Kontext, stale invalidieren. Keine
   Millionen Audioübergaenge fuer die Sammlung rendern.
8. Abschluss11/12 erst nach Produktfreeze: ein begruendeter Volltest mit Coverage,
   danach vollstaendiger Originaltrack-Nativfluss in isoliertem leeren Zustand:
   Index, frische Analyse, Paarbewertung, Playlist, Hoertest, echte Rating-
   Persistenz/Reload. Subjektive Noten vom Menschen, niemals Harness-Fantasie.
   Originalsize/mtime/SHA und keine Audiokopien im Output pruefen. EXE bauen,
   absoluten Pfad/SHA an denselben geprueften Build binden und nativ pruefen.

## Historische Ergebnisse nicht als aktuellen Abschluss verkaufen

Vor den neuen Paketen: 4868 Tests/1113.93 s/Coverage85.46 Prozent;
Nachtraege24+98 bestanden. Diese beweisen den jetzigen Produktstand NICHT.
Alter Originalpilot26: alle RBfasttail, 18 unsichere Downbeats, 26 Gridmismatch,
5 von25 Kanten geplant. 650 gerichtete Paare:334 BPM-Gate,293 ohne qualifizierte
Kandidaten,23 qualifiziert unter7 Tracks. Keine musikalische Inkompatibilitaet
daraus folgern. Zwei Hoertestpaare/sieben Referenzen, Ratingdialog geoeffnet,
kein menschliches Hoeren/Rating/Fit bewiesen. Synthetische Kalibrierung mit
Fake5/2-Noten ist nur technischer Test, kein musikalisches Trainingsergebnis.

GPU-Nachweis siehe IMPLEMENTATION: eigene Qwen-Instanz nutzte RX, iGPU-Engine0
im beobachteten Fenster, aber Qwen-Schema scheiterte. Granite4tiny bestand
spaeter einen Schema-AITestWorker. Kein universelles GPU-/Audioverstaendnis-
Versprechen; Produktion nicht ungefragt auf neues Modell umstellen.

## Wiederauffindbare Rohbelege und Agenten

Lokale TEMP-Belege (nicht in Git, ggf. spaeter nicht mehr vorhanden):
`hpg-readstatus-9864c46db03c41ee970bb201bfd29e8f`,
`hpg-mapping-state-67bfb8cb-fddb-4fa3-bc1b-6faa029ed4d9`,
`hpg-native-mapping-state-8770b536-90de-42f9-9948-aec8b98decff`,
`hpg-anchor5a-d70b4e41c4fc4898b31bce277ce86cb5`,
`hpg-measurement-panel-9a96d535-f49f-4f48-ada0-55eb534d8b06`,
`hpg-p9-ram-876ca90f-0208-4a75-a5bd-f79f8143f2f0-final.evidence.json`.
Session-Rohdaten liegen unter `E:\AI\.codex\sessions\2026\10\03`, relevante
Rollout-ID `01a0ffce-d327-7230-9889-b0794d63215d`. Reader169 Originaloutput
ordinal27341; Diagnose381 und zweiDelta ordinals27305/27306/27361/27362.
Nicht komplett scannen oder ausgeben, wenn engere Belege reichen.

Agenten dieser Session: Erdos (Reader/Importer/Anker), Leibniz (Collection/
MappingState/Viewer), Carver (Diagnose/RAMFit), Faraday (read-only Reviewer).
Alle wurden fuer den Checkpoint angehalten; nur Main fuehrt abschliessendes
Staging/Commit/Push aus. Kein neuer Agent darf alte Hintergrundschreibarbeit
unterstellen. Git/Dateistand und nachfolgende Nachtraege haben Vorrang.

## Abschlussnachtrag: massgeblicher eingefrorener Checkpoint

- Carvers Receipt/Input/Proposal-v2-Delta ist inzwischen implementiert:
  purpose=regular strikt gebunden; Native spec_verified_ram_replay mit einem
  echten Replay, zwei Segmentloads und drei gemessenen Lags im synthetischen
  DSP-Test; Legacy einReplay gegen vorhandenes PCM. Fit rendert nicht erneut.
  68 gezielte Tests bestanden, 31.46 s, Exit0. Main las JUnit68/0/0/0 und
  Evidencecommand/Exit unmittelbar, aktuelle fuenf Hashes entsprechen Freeze.
  Belege: TEMP/hpg-p9-receipt-v2-a0d82b40-27d1-4ba1-a071-63d82d585ab9.xml
  sowie gleichnamige .evidence.json. Finale unabhaengige TOR2-/Gesamt-/Original-
  App-/EXE-Abnahme weiterhin offen. Keine historische v1-Proposal-Migration.
- MultiRoot-Persistenz ist **nicht implementiert**. Nur23 neue RED-Vertragstests
  fuer managed_config_from_roots und association-v2 wurden vorbereitet:
  23failed,24deselected,1.26 s. Nicht als gruene Suite oder fertige API melden.
  Der WIP blieb absichtlich erhalten, Erwartungen nicht abgeschwaecht.
  TEMP/hpg-hearing-multiroot-a52cb3f8-5646-4e74-a1a6-102fb904ce12/red.xml.
  Separater bereits gepushter Commit:
  `a49d3eb08887e100b595c04108a562e25ed9dc3b`.
  Damit kann eine kommende Gesamtsuite derzeit an diesen23 RED-Tests scheitern.
- Agenten Erdos und Leibniz interpretierten den Handoff-Auftrag als eigenen
  Commit-/Push-Auftrag. Die zwei eng begrenzten bereits gepushten Commits
  1b7a06a und a49d3eb werden bewahrt, nicht zurueckgesetzt. Danach wurde
  ausschliessliche Git-Ownership beim Mainagenten nochmals klargestellt.
  Fuer naechste Parallelrunde Git-Mutationen ausdruecklich nur einem Agenten
  erlauben; Datei-Ownership allein verhindert Commit-Kollisionen nicht.
- Lebende Cachehinweise in AGENTS, CLAUDE, QUICK_START, Track-/Mixpoint-Fluss,
  PROJECT_KNOWLEDGE und PRODUCTION_STATUS sowie beiden Cache-Skillspiegeln
  auf46 synchronisiert. 37 Release-Metadatenpruefungen bestanden/5.28 s,
  TEMP/hpg-checkpoint-release-metadata.xml. Das ist kein Build-/Releasebeweis.
- Neuer Kohortenanalysedienst ist konservierter WIP mit gezielten Nachweisen,
  aber ohne TOR2 oder GUI-Anschluss. ProduktSHA
  `153AF9A0E1EE6BE218DD1CFF9C40AD67B3D5FD95820B4591DB49F6A5A633AB6B`,
  TestSHA `DF41F020144C4E0E36BBB71E5ED88875C7C704A5FB50CB67BC8A617F862DD56C`.
  Metadatenfixtures besitzen .fixture-Endung; .mp3-Pfade werden nur simuliert,
  keine echte Audioanalyse in diesen Tests behauptet.
- Der aktuelle Auftrag verlangt Sicherung und synchronisierten Zwischenstand,
  nicht die Fortsetzung zu Lasten verbleibender Kontextzeit. Deshalb kein
  vorgetaeuschter finaler Volltest oder neue EXE. Fruehere23-RED-,13/6-Fixture-
  und spaetere Nachtestbelege werden getrennt bewahrt, nicht zusammengerechnet
  und als angeblicher gruener Gesamtlauf verkauft.
- Enges unabhaengiges TOR2-Vorcommit-Review des Checkpoints: MIT AUFLAGEN,
  kein Blocker fuer diese WIP-Sicherung. Exakt 71 Quell-/Test-/Dokumentdateien,
  keine Audio-, Datenbank-, Cache-, Binaer- oder Autopilot-Artefakte im Index.
  Keine Produktfreigabe: offene Fachreviews und Abnahmen bleiben offen.
  Main pruefte die Syntax von 59 geaenderten/neuen Pythondateien und den
  staged Whitespace-Diff; beide bestanden. Vier eng definierte Secret-Muster
  fanden keinen Treffer, das ist keine vollstaendige Sicherheitspruefung.

## Fortsetzung nach dem ersten Checkpoint

Der Nutzer bestaetigte die Fortsetzung. Der erste Push wurde erneut direkt
gegen `origin/main` geprueft: lokaler und entfernter HEAD waren identisch
(`3f75422b07c4a2992467da8a2f76679d8ec30878`). Danach wurde das offene
Mehrordner-Persistenzpaket in `hpg_core/hearing_managed.py` umgesetzt:
`managed_config_from_roots`, private Snapshots ueber mehrere Quellroots,
Association-v2 mit strikter Manifestbindung und Abbruch nach geschlossenem
SQLite-Handle. Einordner-Saetze bleiben v1. Keine Quellmediendateien wurden
fuer diesen Pakettest geoeffnet oder geschrieben.

Erster gezielter Lauf: 40 fehlgeschlagen, weil eine neue Typpruefung konkrete
`WindowsPath`-Objekte ausschloss. Die Pruefung wurde auf `isinstance` korrigiert;
keine Testerwartung geaendert. Danach `tests/test_hearing_managed.py`:
47 bestanden/2.06 s. Angrenzend `test_hearing_jobs.py`,
`test_hearing_workflow.py`, `test_hearing_sources.py` und
`test_hearing_native_integration.py`: 92 bestanden/23.58 s. Beides sind
gezielte Laeufe mit `--noconftest -n 0 --no-cov`, keine Gesamtabnahme.
Unabhaengige TOR1- und TOR2-Pruefung: jeweils MIT AUFLAGEN. TOR2 fand keinen
konkreten Produktcodefehler; Vorbehalt betrifft die nicht unabhaengig
nachgelesenen Testausgaben und weiterhin fehlende Gesamt-/Original-/EXE-Probe.
Die Mehrordner-Persistenz ist damit implementiert, aber noch nicht mit dem
nativen Collection-Training-Dialog verbunden. Die weiteren Planpakete bleiben
offen; alte 23-RED-Belege sind historisch und durch den 47er-Nachtest ersetzt.

## Fortsetzung: nativer Sammlungs-Hoertest

Nach Commit `53f85ea` ist der CollectionDialog mit dem internen Hoertestablauf
verbunden. Nach geprueftem Inventar waehlt der Nutzer eine Trackanzahl (2 bis
1000), eine getrennte Obergrenze fuer Hoertestpaare, Seed und Modus
`kandidaten` oder `einzel`. Der Auftrag kopiert den gesamten Index in neue
unveraenderliche Tuple-/Entry-Werte. Der Dialog schliesst zuerst; erst nach
Rueckkehr aus `exec()` startet ein `HearingCohortWorker`.

Dieser Worker nutzt `select_cohort` und `analyze_cohort` mit dem bestehenden
ParallelAnalyzer. Veraltete oder unvollstaendige Auswahl/Analyse gibt keinen
Teil-Satz frei. Die Analyse darf den bestehenden Cache verwenden; der Modus
fresh versus Cachehit ist hier noch nicht separat nachgewiesen. Nach echtem
`QThread.finished` und erneuter Cancel-/Close-Pruefung erstellt die App einen
privaten Mehrordner-Snapshot und startet den bestehenden `HearingPrepareWorker`.
Die normale Analyse ist gegen einen laufenden Kohorten-/Prepare-Worker gesperrt;
ein normaler Cancel-Aufruf leitet den Hoertestabbruch weiter, ohne einen falschen
normalen RunState zu setzen. Quellmusik bleibt am Originalort.

Erster Integrationslauf: 81 bestanden, ein Fehler im alten Testdummy ohne das
neue Signal. Der Dummy erhielt nur die neue Schnittstelle; Produkterwartungen
blieben. Danach 108 bestanden/7.76 s. Unabhaengiges TOR2 wies zwei konkrete
Punkte zurueck: mutable Indexeingabe und Cancel-Routing. Beide wurden im Code
korrigiert. Ein echter Qt-Modaltest und echte QThread-Tests fuer Ergebnis vor
`finished` und spaetes Cancel kamen hinzu. Ein Testcleanup musste nach
`deleteLater()` ein bereits geloeschtes QObject beachten; keine Produktregel
geweicht. Finaler gezielter Fuenfdateien-Lauf: 113 bestanden/7.45 s,
`--noconftest -n 0 --no-cov`. Nachpruefung TOR2: MIT AUFLAGEN, beide
Produktbefunde geschlossen. Kein voller Originalmusiklauf, keine menschliche
Hoerbewertung, keine Gesamtsuite/Coverage- oder EXE-Abnahme fuer diesen Stand.
Weitere Planpakete, darunter Research6, vollstaendige Ratings7, kalibrierter
Holdout9 und Sequenzskalierung10, bleiben offen.

### Originalmusik-Pilot nach diesem gezielten Testlauf

Ein isolierter frischer Lauf mit zwei AIFF-Originaltracks aus
`F:\beatport_tracks_2026-04` durch die echte `MainWindow`-Kohorten- und
Prepare-Kette analysierte beide Tracks und schrieb einen Kandidatensatz mit
einem Paar und fuenf Quellenreferenzen. Der Satz liegt nur im privaten
Temp/Testprofil unter
`C:\Users\david\AppData\Local\Temp\hpg-native-cohort-3feee0849124417a81d15ee5f03f129b\HPG\hearing_sets\8780c886-5db0-4cd4-b0e3-754ef41a1ffa\set`.
`HearingLoadWorker` oeffnete ihn wieder: ein Paar, fuenf Clips, zwei
Quellenreferenzen, keine gespeicherten Clip-Audiodateien. SHA-256 und Groesse
beider Quelltracks waren vor und nach dem Pilot identisch. Das ist ein
Originalquellen-Pipelinebeleg, aber kein UI-Klick- oder EXE-Beleg.

Beim echten RAM-Rendering der fuenf Clips lieferten Variante 2 und 3
WAV-Bytes im Speicher; Variante 1, 4 und 5 scheiterten an
`BeatSyncError: Kickphase nicht in Anfang, Mitte und Ende messbar`. Der
Sicherheitsgrenzwert wurde nicht gelockert. Der Bewertungsdialog zeigt den
Renderfehler in diesem Checkpoint nur an; neue Noten sind noch moeglich.
Die damals berichtete gleiche WAV-Dauer von 43.042 s fuer beide Varianten
ist **nicht** als gebundener Dauerbeleg verwendbar: Variante 2 hat laut
gespeichertem Manifest 54.085 s Crossfade plus Vor- und Nachlauf. Der
fruehere Pilot-Output muss erst exakt den Clip-IDs zugeordnet werden; kein
erneuter Audio-Lauf allein zur Klärung dieser Dokumentationsabweichung.
Der Satz ist **nicht** als vollstaendig anhoerbarer Hoertest oder als
Trainingsfreigabe zu deklarieren. Keine menschliche Hoerqualitaet wurde
geprueft.

### Fortsetzung: Bewertungsschutz bei RAM-Hoerproben

Der native Bewertungsdialog sperrt jetzt neue Noten fuer einen `spec`-Clip,
bis derselbe Clip in der aktuellen Ansicht erfolgreich im RAM gerendert wurde.
Ein aktueller Renderfehler sperrt wieder; veraltete Worker-/Generationssignale
haben keine Wirkung. Bestwahl und Sequenznoten setzen erfolgreiche Renderings
aller Varianten der Gruppe voraus. Diese strengere Gruppenregel ist bewusst:
"beste" oder "keine beste" ist ohne technisch beurteilbare Alternativen
nicht belastbar. Vorhandene Noten bleiben sichtbar und
unveraendert; Legacy-Clips ohne `spec` behalten das bisherige Verhalten.
Auch ein `spec`-Clip mit einem `path` darf den RAM-Renderer nicht umgehen.
Die reine Hoeransicht besitzt nun einen Dialog-internen `read_only`-Guard.
Weder Render-Refresh noch direkter Handleraufruf darf dort Noten schreiben.

Das ist nur ein Schutz gegen **neue** falsche Bewertungen in diesem Dialog.
Alte Noten koennen weiterhin gespeichert sein und vom Fit gelesen werden;
technische Nichtbeurteilbarkeit ist noch kein persistierter Fit-Ausschluss.
Ein erfolgreiches Rendering belegt weder Audioausgabe am Benutzergeraet noch
menschliches Anhoeren oder musikalische Qualitaet. Die drei BeatSyncError
bleiben offen; an Renderer-Grenzwerten wurde nichts geaendert.

Gezielte Qt-Regression: zwei neue Schutztests waren vor dem Fix rot, danach
23 Dialogtests bestanden. Der erste angrenzende Integrationslauf meldete vier
Fehler, weil die alten Testablaeufe ohne Rendering bewerteten. Sie wurden auf
synthetische RAM-Erfolgssignale vor der Bewertung umgestellt; kein Produkt-Gate
wurde gelockert. Der erneute Viermodus-Nachtest bestand mit 4/4; die zwei
Schutztests nach der letzten Guard-Anpassung mit 2/2. Danach bestand ein
gezielter Siebenerlauf mit 3 Dialog-Schutztests einschliesslich `read_only`
und 4 nativen Integrationsmodi; ein weiterer gezielter Viererlauf pruefte
zusaetzlich den `spec`-plus-`path`-Bypass. Die dabei verwendete
Stille-WAV ist ausschliesslich RAM-Testnutzlast und kein Musik- oder
Audioqualitaetsbeleg. Kein erneuter Originalmusiklauf, kein Gesamttest und
keine EXE-Abnahme in dieser Fortsetzung.
Ein weiterer gezielter Test bestaetigte 1/1: Erst nach zwei erfolgreichen
Renderereignissen ist eine Bestwahl schreibbar; ein nachfolgender aktueller
Renderfehler sperrt neue Noten und die Gruppenentscheidung wieder. Bereits
gespeicherte Noten oder Sieger werden dadurch nicht still geloescht.
Der vorhandene Lauf benutzte
`.\venv312\Scripts\python.exe -B -m pytest tests/test_hearing_panel.py -k group_best_choice_requires_all_rendered_and_error_revokes_it --noconftest -n 0 --no-cov -p no:cacheprovider --tb=short -q --color=no -o log_cli=false`;
Exitcode 0, `1 passed, 25 deselected in 0.23s`. SHA-256 der getesteten
`tests/test_hearing_panel.py`:
`358d914fc87f409f1adea32b9513e4696f6df8cd843019ebb75d1b6d8f357c65`.

### Fortsetzung: regionale Kickphasen-Diagnose

Der Renderer nennt bei einem bestehenden `BeatSyncError` nun die tatsaechlich
fehlenden Messregionen (`Anfang`, `Mitte`, `Ende`) und unterscheidet vor/nach
Korrektur. Bei falscher Anzahl Messwerte meldet er stattdessen ein ungueltiges
Messformat. Grundlage sind nur die schon vorhandenen drei Messwerte; keine
zusaetzliche Analyse, keine neue WAV und keine geaenderte Freigabeschwelle.
Drei neue Regressionen waren vor der Textaenderung rot; danach bestanden
die drei neuen Tests und die zwei angrenzenden Format-/Drift-Tests (5/5,
`--noconftest -n 0 --no-cov`). Die alte Pilotmeldung enthaelt diese
Regionsinformation noch nicht. Deshalb ist weiterhin unbekannt, welches
Fenster der drei Originalmusik-Varianten wirklich ausfiel. Ein neuer
Originalmusiklauf allein fuer die Meldung wurde nicht gestartet.
Vorhandener GREEN-Lauf:
`.\venv312\Scripts\python.exe -B -m pytest tests/test_transition_renderer.py -k 'unmessbare_region or stille_unmessbare_fenster_werden_im_strict_pfad_abgelehnt or drift_nach_korrektur_wird_abgelehnt' --noconftest -n 0 --no-cov -p no:cacheprovider --tb=short -q --color=no -o log_cli=false`;
Exitcode 0, `5 passed, 163 deselected in 0.71s`. Getestete SHA-256:
`transition_renderer.py` `4928436027a4e16453eb128aedc8c1a2cb81a98591069d6a32c428ff14a2bf30`,
`test_transition_renderer.py` `32f8ce177666c8e72f3b592e49f63f2677dfdc8712b16d53f67c1d5006340015`.
