# Sammlung und Training in der App: freigegebener Umsetzungsplan

> Ausfuehrung: autonom in dieser Sitzung, unabhaengige Aufgaben parallel,
> Fachreview vor und nach Produktcode. Nutzerfreigabe vom 04.10.2026.

Aktueller Zwischenstand: siehe `docs/SESSION_HANDOFF_2026-10-04.md`.
Mehrordner-Persistenz und nativer Einstieg vom Sammlungsdialog in die
Kohortenanalyse/Hoertest-Vorbereitung sind gezielt getestet. Die folgenden
Paket-Haken bleiben bewusst offen, bis alle Teilpflichten und die jeweils
erforderliche Produktabnahme belegt sind.

## Ziel und Grenzen

Die App verwaltet die gesamte ausgewaehlte Sammlung, verwendet die aktuelle
Rekordbox-Quelle, erklaert unsichere Messungen und bietet native Hoertests sowie
nachgewiesene Kalibrierung. Rund 2400 Tracks sind eine Nutzerangabe, kein bereits
verifiziertes Inventar. Regulaere Playlist-Groessenlimits bleiben getrennt vom
Bibliotheksindex. Eine optimale Reihenfolge aller Permutationen wird nicht zugesagt.

Originalaudio inklusive Tags ausschliesslich lesen. Niemals kopieren, verschieben,
umbenennen, loeschen oder zurueckschreiben. Rekordbox-Dateien ebenfalls nur lesen.
Eigene Indizes, Diagnosen, Bewertungen und Praeferenzen liegen unter LOCALAPPDATA/HPG.
Uebergangsplayback entsteht bei Bedarf im RAM. Keine dauerhaften Hoertest-Audiodateien.
Vorhandene uncommittete Umsetzung bleibt erhalten. Keine weitere Projektkopie.

## Arbeitspakete und Schnittstellen

- [ ] 1. Schreibgeschuetzter Rekordbox-Adapter.
  `hpg_core/rekordbox_readonly.py`: `open_rekordbox_readonly(path=None, *, key=None,
  unlock=True)` liefert schmalen Reader mit `query(model).options(...)`,
  `get_content(**kwargs)`, `read_anlz_files(id)`, `read_anlz_file(id, type)` und
  idempotentem `close()`. Windows-Schutzhandles sind an einzelne materialisierte
  Leseoperationen gebunden. DB-Verbindung vor Handles schliessen. Nichtleere WAL/
  Journale und nicht absicherbare Writer geschlossen ablehnen. Keine Secrets in
  URL, SQL-Trace oder Fehlermeldung. `ReadOnlyRekordboxError` verwirft Teilimporte.
  Importer-Hook und schmale Fehlerbehandlung in `rekordbox_importer.py`.
  Tests: `test_rekordbox_readonly.py`, vorhandene Importer-Tests unveraendert fachlich.
- [ ] 2. Sammlung ohne 1000-Track-Abbruch inventarisieren.
  `collection_index.py`: `scan_collection(roots, previous=None, cancel=None,
  progress=None)` liefert unveraenderlichen Index mit Pfad, Groesse, mtime und
  Status. Ueberlappende Roots deduplizieren; fehlende, geaenderte und unlesbare
  Quellen sichtbar machen. Persistenz atomar in eigenem validiertem JSON.
  `collection_jobs.py` und `collection_panel.py` besitzen eigenen nativen Dialog
  mit mehreren Musikordnern, Start, Abbruch und Fortsetzung. `main.py` verbindet
  den Dialog mit QUALITY. Tests: 2500 temporaere Inventarobjekte, keine echten
  Audiodateien erzeugen; native Thread-Lebensdauer und Fehlerpfade.
- [ ] 3. Rekordbox-Zuordnung der Sammlung anzeigen.
  Indexergebnisse mit dem abgesicherten Importer abgleichen; keine mehrdeutigen
  Basenames automatisch zuordnen. Counts fuer eindeutige, fehlende und mehrdeutige
  Metadaten sowie vorhandene Beatgrids/Phrasen getrennt darstellen. Quelldatenstand
  und Signatur speichern; bestaetigte Ursprungswerte nicht neu erfinden.
- [ ] 4. Messdiagnose je Track und Fenster.
  `downbeat.py`/`analysis.py`: Gruende fuer Null-/schwache Konfidenz, Tempo-Konflikt,
  fehlende rhythmische Aktivitaet, Grid-Phase und Decode-Fehler explizit erheben.
  Alte Messwerte liefern unbekannte Diagnose statt nachtraeglicher Ursachenbehauptung.
  Neue gespeicherte Analysefelder erfordern angepasste Track-Serialisierung und
  CACHE_VERSION. Beide Analysepfade pruefen. Diagnose im nativen Trainingsdialog.
- [ ] 5. Gezielt lokale Anker pruefen.
  Nur fehlende oder widerspruechliche Messstellen nachuntersuchen; vorhandene
  gueltige Features wiederverwenden. Rekordbox-Raster, Audio-Beatphase und Takt/
  Phrasenposition getrennt bewerten. Alternative Anker bleiben Hypothesen bis
  sie den gemeinsamen Gitter- und Kettenvertrag erfuellen. Keine globalen Gates
  senken. Pilot mit bekannten 26 Problemtracks, danach breitere Stichprobe.
- [ ] 6. Experimentelle native Hoertests.
  Erweiterung des bestehenden Hearing-Workflows, kein zweiter Producer.
  Regulaere und experimentelle Saetze besitzen expliziten Vertragsstatus.
  Unvollstaendige musikalische Messungen duerfen Forschungsvarianten erzeugen;
  technische Grenzen (existierende Quelle, endliche Zeiten, Coverage, Blendenlaenge,
  Wiedergabesicherheit) bleiben hart. Keine experimentelle Variante automatisch
  als regulaerer TransitionPlan oder Kalibrierungsfreigabe behandeln.
- [ ] 7. Bewertungen fuer Trainingszwecke vervollstaendigen.
  Native Wiedergabe, Noten, beste Variante, keine passende Variante und nicht
  beurteilbar. Bewertungen an Quelle, Kandidatenparameter und Algorithmusversion
  binden; fehlende Noten nicht als schlechte Noten interpretieren. Erforderliche
  Schemata gemeinsam mit Rating-Persistenz und Loader versionieren.
- [ ] 8. Informative kleine Trainingsrunden waehlen.
  Genre-, Tempo-, Energie- und Messqualitaetsbereiche abdecken. Bereits bewertete
  unveraenderte Varianten wiederverwenden; neue musikalische Kombinationen sowie
  gute/schlechte/unsichere Beispiele anbieten. Umfang bleibt einstellbar. Eingaben
  und Auswahlseed einfrieren; Aufwand und ausgelassene Moeglichkeiten anzeigen.
- [ ] 9. Kalibrierung und Nachweis verbessern.
  Bestehenden Fit/Apply nutzen. Trainings- und Prueftracks samt erkannten Versionen
  trennen; grenzuebergreifende Paare ausschliessen. Bestehenden Stand als Baseline
  neben Zufallsbasis pruefen. Zu kleine oder nicht informative Daten ablehnen.
  Experimentelle Datensaetze nicht still in regulaere Gewichtsuebernahme mischen.
  Vorschlag, Unsicherheit, Datenumfang und Rueckkehr zum vorherigen Stand nativ zeigen.
  Der bestehende native Kandidaten-Audit erzeugt derzeit temporaere Replay-WAVs
  in seinem isolierten Operationsordner. Dieser gelesene Ist-Stand erfuellt den
  Zielvertrag RAM-only noch nicht. Quellreferenz-Audit und Fit muessen gemeinsam
  auf RAM-Replay umgestellt werden; ein reiner Verzicht auf den Audit ist verboten.
- [ ] 10. Sequenzen und Skalierung pruefen.
  Wiederverwendbare Trackmessungen und gerichtete Paarergebnisse versionieren.
  Kleine Sequenzen zur Bewertung der Paar- und Kettenwirkung verwenden.
  Pause/Fortsetzung mit identischem Kontext; veraltete Ergebnisse klar invalidieren.
  Nicht alle 5.757.600 gerichteten Paare einer 2400er-Sammlung als Audio rendern.
- [ ] 11. Integrierte Abnahme.
  Nach jedem Codepaket gezielte Regressionen, vor Abschluss genau ein begruendeter
  Gesamtlauf. Kein gleichzeitiger Volltest. Originaltrack-Ablauf mit isoliertem
  leeren Zustand: Index, frische Analyse, Paarbewertung, Playlist, Hoertest, Rating-
  Persistenz und Reload. Subjektive Noten stammen vom Nutzer, niemals vom Harness.
  Originalgroesse/mtime/SHA und Ausgabeverzeichnis auf Audiokopien pruefen.
- [ ] 12. Auslieferung und Dokumentation.
  Implementierung, Tests, nativer Ablauf und musikalische Qualitaet getrennt
  berichten. EXE nur als aktuell ausgeben, wenn Build und native EXE-Pruefung mit
  absolutem Pfad/SHA gebunden sind. Keine Datenbanken/Audio/Benutzerartefakte stagen.
  Noch offene Aufgaben bleiben sichtbar; keine pauschale Vollfunktionszusage.

## Parallelisierung und Testkosten

Adapter, Sammlung und Messdiagnose koennen nach gemeinsamen Schnittstellen
unabhaengig bearbeitet werden. Hauptagent besitzt Integrationsstellen in main.py.
Pruefer schreiben keinen Produktcode. Teststand vor langen Laeufen einfrieren.
Logs, Eingangssignaturen und Codebindung fuer Wiederverwendung bewahren.
Bekannte Befehlsprobleme vor Ausfuehrung im zentralen Hirn nachsehen.

## Laufender Nachweisstand 04.10.2026

Session auf ausdruecklichen Nutzerauftrag als Zwischenstand beendet und
gesichert. Massgeblicher Abschlussnachtrag: `docs/SESSION_HANDOFF_2026-10-04.md`.
Die folgenden Paketbelege bleiben Verlauf; offene Aufgaben nicht als erledigt
markieren. MultiRoot nur23 RED-Tests, Receipt-v2 inzwischen68 Deltafaelle gruen.

Keine Gesamtfertigmeldung: Die folgenden Paketbelege ersetzen weder einen
aktuellen Gesamttest noch einen vollstaendigen nativen Originaltrack-Ablauf.

- Reader/Importer: 169 gezielte Tests bestanden, 6,27 Sekunden, Exit 0.
  Original-CommandExecution in Session-JSONL (ordinal 27341) unabhaengig gelesen;
  kein Wiederholungslauf. Reader-Review bestaetigt behobene ANLZ-Regressionen.
  Historisches Vier-Dateien-Hashmanifest fehlt; diese Nachweisgrenze bleibt offen.
- Collection-Core/Dialog inklusive Wiederladen: 60 Tests bestanden, 2,89 Sekunden.
  Read-only-Review findet keinen Produktfehler; historische Laufhashbindung fehlt.
- Main-Anschluss: sieben Qt-Integrationstests bestanden, 0,63 Sekunden.
  Review meldet noch fehlende Freigabe der Dialogreferenz nach unerwartetem
  Modalende und einen unvollstaendigen Elternfenster-Schliesstest. Nicht abgenommen.
- Downbeat-Core: 48 Tests bestanden, 2,86 Sekunden; unabhaengig DURCHGEWUNKEN
  fuer diesen engen Bereich. Bestehende Schwellen und DSP-Aufrufe unveraendert.
- Diagnose-Persistenz: CACHE_VERSION 46, streng versioniertes Diagnosefeld.
  381 fokussierte Tests und zwei zusaetzliche Decode-/Schemafaelle bestanden.
  Unabhaengiges Review und beide Diagnose-Pipeline-Nachweise noch offen.
- Echte Quelle F:/PIONEER/Master/master.db: geschuetztes get_content().all()
  liest 2693 Datensaetze, davon 2490 mit AnalysisDataPath. Datenbank-SHA256
  d40ce07bb1292540907402638bfeeeb494f5e5e19a22ceadaa9a1deb28487715,
  Groesse 71401472 und mtime_ns 1791115112711145700 vor/nach identisch.
  WAL/SHM/Journal vor/nach abwesend. Kein gemeinsamer DB-/ANLZ-Snapshot zugesagt.
  Ein vorausgehender Probeaufruf benutzte faelschlich len(query) und fuehrte
  noch keine Datenbankabfrage aus; erst .all() belegt den realen Lesezugriff.
- Rekursives stat-only Inventar der vier bekannten F:-Musikordner:
  2631 Eintraege, keine Fehler, nicht abgebrochen. Keine Audioinhalte geoeffnet,
  kein Inventar gespeichert, keine musikalische Analyse daraus abgeleitet.
- Native Kalibrierung: bestehender temporaerer WAV-Replay bleibt eine bekannte
  Luecke. RAM-only Audit/Fit wird gemeinsam geplant; Gates nicht entfernen.

### Nachtrag: Diagnoseanzeige und Rekordbox-Zuordnung

- Main-Dialogreferenz nach unerwartetem Modalende korrigiert: drei echte
  QThread-Regressionen zuerst fehlgeschlagen, danach zehn Main-Integrationstests
  bestanden (1,01 Sekunden). Workerende geht der Referenzfreigabe voraus.
- Measurement-Persistenz unabhaengig DURCHGEWUNKEN. Diagnoseanzeige ebenfalls
  unabhaengig DURCHGEWUNKEN fuer ihren Zwei-Dateien-Scope: elf Tests bestanden
  (2,52 Sekunden), darunter 2500 RAM-Tracks mit je 100 Fenstern; nur Details des
  ausgewaehlten Tracks werden als Widgets aufgebaut. Eingangsobjekte bleiben
  unveraendert. Zwei Main-Anschlussfaelle bestaetigen aktuell analysierte Tracks
  und ausdruecklich keinen Playlist-Fallback (0,81 Sekunden); Signal nach
  AnalyticsPanel-Wechsel separat bestanden (0,97 Sekunden).
- Mapper: 31 Tests bestanden, danach ein begruendetes mtime-Validierungsdelta.
  Der Importer unterscheidet jetzt bestaetigte Abwesenheit und unbekannte oder
  fehlgeschlagene Detailauswertung durch einen reinen Memo-Lesestatus.
  147 Importertests bestanden (5,81 Sekunden), echte temporaere SQLite-/SQLCipher-
  Readerstrecken enthalten. Enges unabhaengiges Review abgeschlossen; keine
  Repository-Vollsuite daraus ableiten.
- Mapping-UI: native Tabelle zeigt Matchart, BPM-/Key-Vorhandensein, echte Counts,
  Signatur und unbekannte Details. Eigener Importer wird vor Ergebnisemission
  geschlossen. Der erste 24er-Dialoglauf hatte 23 bestandene Tests und einen
  Testzugriff auf einen bereits ordnungsgemaess geloeschten QObject. Nachtest
  der korrigierten Test-Lebensdauer: zwei bestanden (0,27 Sekunden).
  Spaeterer Reviewbefund zu Cancel zwischen Emission und GUI-Slot wurde als
  konkrete Regression reproduziert und behoben. Sieben gezielte Nachtests
  bestanden (0,21 Sekunden); Quell-/Testhashes vor/nach identisch. Unabhaengiges
  Review bestaetigt die Korrekturen, kein pauschaler gruener 24er-Lauf behauptet.
- Originalpilot mit dem aktuellen Mapper, ohne Audioanalyse: 26/26 Zuordnungen
  ausschliesslich per Basename, NICHT per exaktem Quellpfad. Bei allen 26 sind
  Beatgrid und Phrasen positiv, Signaturen vorhanden, keine Detailfehler.
  78 gelesene ANLZ-Dateien sowie DB-Familie anhand SHA256/Groesse/mtime vor/nach
  unveraendert. Basename-Match belegt allein keine Audioidentitaet zur historischen
  Rekordbox-Pfadangabe. Parser meldet nicht unterstuetzten PVDI-Tag; PQTZ/PSSI
  konnten dennoch ausgelesen werden. Kein nativer Analyse-/Hoer-/Trainingsbeleg.
- Aktuelle get_config-Probe: rekordbox7 verweist auf F:/PIONEER/Master/master.db,
  rekordbox6 liefert keinen db_path. Die automatische Quelle ist damit fuer
  diesen Lauf unmittelbar geprueft.
- Mappinganzeige ist derzeit nur RAM. Eigene versionierte Persistenz ist ein
  separat freigegebener Folgeauftrag. Der neue State-Kern ist inzwischen
  implementiert und eng unabhaengig DURCHGEWUNKEN: 94 Tests bestanden,
  aktuelle Produkt-/Testhashes gleich dem Freeze. Eigene atomische JSON,
  strikte Index-/Cachebindung, unbekannte Dateien erhalten; keine Original-
  Audio-/DB-Zugriffe. Geladene Beobachtung heisst saved_not_fresh. Der native
  Save-/Load-Anschluss wird separat umgesetzt; noch kein nativer Gesamtbeleg.
- Tiefere Codepruefung bestaetigt eine noch offene Trainingsgrenze:
  `_prepare_hearing_set()` verwendet weiterhin `start_analysis()` und dessen
  `AnalysisWorker`. Der Ordnerscan endet bei SECURITY_MAX_PLAYLIST_SIZE (1000),
  danach deckelt auch sanitize_playlist. Das neue 2631er-Inventar aendert dies
  nicht. Paket 8 muss kleine explizite Teilmengen aus der ganzen Sammlung
  waehlen; das normale Playlistlimit wird nicht pauschal aufgehoben.

### Laufende Designentscheidungen: keine redundanten Audiolaeufe

- Native Kandidatenkalibrierung wird auf einen tatsaechlichen RAM-Replay
  umgestellt. Unabhaengiges TOR1: MIT AUFLAGEN. Publizierter SourceSpec muss
  vor DSP dem unabhaengig rekonstruierten Producer-Spec entsprechen. Quellen,
  Build, Cache, Manifest und Ratings bleiben vor/nach gebunden. PCM-Metadaten,
  Replay-Digest und drei tatsaechliche Kick-Lags bleiben verpflichtend.
  Der zweite identische Renderer-Aufruf waere nur ein Determinismusvergleich,
  kein unabhaengiger musikalischer Referenznachweis. Neue explizite Receipt-
  Version nennt deshalb spec_verified_ram_replay und erfindet kein Referenz-
  PCM-Feld. Legacy-WAV bleibt ein RAM-Replay gegen vorhandenes readonly PCM.
  Normaler Fit, Vorschlagsexport und Apply akzeptieren nur regulaeren Zweck.
  Umsetzung und Delta-Nachweise stehen noch aus.
- Lokale Ankerforschung erhaelt einen isolierten Kern mit unveraenderlichen
  Eingaben, expliziter Source-/Build-/Parameterbindung und Fensterbudget.
  Beat-, Takt- und Phrasenevidenz bleiben getrennt. Wiederverwendung nur bei
  passender Bindung; alternative Phase algebraisch bewerten, nicht erneut
  identisches Audio messen. Kein Track-/Gate-/Coverage-Ueberschreiben.
  Zwei-Dateien-Kern implementiert und eng unabhaengig DURCHGEWUNKEN:
  74 gezielte Tests bestanden (0,60 Sekunden), einschliesslich echter Faltung
  auf synthetischen RAM-Samples. JUnit/Exitcode und Vor-/Nachlaufhashbindung
  direkt geprueft, aktueller Code stimmt mit Freeze ueberein. Nativer Anschluss,
  realer Quellenleser und Research-Producer bleiben anschliessende Aufgaben.
  Uebergebene Hashes sind kein selbst vom Forschungskern erbrachter
  Identitaetsnachweis. Leser-Sicherheitsfehler muessen den Lauf abbrechen,
  nicht als gewoehnlicher Decodefehler in einem abgeschlossenen Bericht enden.
- Neuer RAM-Kohortenkern betrachtet alle Inventareintraege, aber begrenzt die
  Auswahl am bestehenden Playlistlimit. Seedgebundene Strata verwenden Genre,
  explizite 10-BPM-Baender, vier Energiebaender und expliziten Beatgridstatus;
  dies ist keine Gesamtanalysequalitaet. Veraltete Features werden unbekannt,
  der Track bleibt waehlbar. Zwei erste Tests bestanden; danach 25 neue
  Deltafaelle (1,20 Sekunden), identische Vor-/Nachlaufhashes. Ein Bool im
  vorherigen Versionsfeld wurde als konkrete Regression reproduziert und
  durch strikten gebundenen Vergleich korrigiert. Enges TOR2 noch offen.
  Noch keine native Trainingsauswahl oder Varianten-/Bewertungswiederverwendung.
- Gelesener Fit-Iststand: `holdout_nach_tracks_mit_diagnose` trennt aktuell nach
  Pfad und verwirft grenzuebergreifende Paare. `_fit_kandidaten_genre` prueft
  gegen Zufallsbasis. Die im Plan verlangte Gruppierung erkannter Trackversionen
  und Gegenpruefung der vorhandenen Baseline sind dadurch noch nicht belegt.
  RAM-only Audit allein schliesst dieses Arbeitspaket deshalb nicht ab.

App-EXE nicht neu gebaut oder als aktuell abgenommen. Alte Gesamttestbelege
beweisen die nachfolgenden Aenderungen nicht.

## Ausgangsbelege

Vorheriger Gesamtlauf: 4868 bestanden, Coverage85,46%; spaeterer Ownership-Nachtrag
24 plus98 gezielte Tests. Diese Ergebnisse beweisen keine nachfolgenden Aenderungen.
Originalpilot: 26 Tracks analysiert, 5/25 geplante Kanten; 18 unsichere Downbeatanker.
Aktuelle Rekordbox-Konfiguration: F:/PIONEER/Master; Fileinventar allein beweist
noch keine eindeutige Zuordnung oder musikalische Korrektheit.
