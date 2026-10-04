# Umsetzung des verifizierten Nutzerauftrags vom 04.10.2026

Verbindliche Spezifikation: Nutzerauftrag im Chat (alle acht Strategien verwenden
lokale Uebergangsanalyse; Hoertest nur mit Musikordnerwahl; geeignete lokale Modelle
und nachgewiesener RX-7800-XT-Betrieb). Keine Behauptung musikalischer Optimalitaet.

Aktueller Endstand und offene Folgepakete: `SESSION_HANDOFF_2026-10-04.md`.
Nachfolgende Abschnitte sind datierte Verlaufseintraege, keine automatische
Abnahme des spaeter erweiterten Quellstands. Cache46 und RAM-Receipt-v2 stehen
im aktuellen Code; MultiRoot hat nur23 RED-Vertragstests, noch keine API.

## Arbeitsvertrag und Schnittstellen

- Bestehendes Repository verwenden; keine weitere App-Kopie oder Worktree.
- Originalaudio nur am Quellort lesen. Keine Audioexporte fuer diese Umsetzung.
- Ein Product-Code-Schreiber gleichzeitig. Parallel: Recherche, Review,
  Testvorbereitung. Hauptagent koordiniert alle teuren Pruefungen.
- Neue Hörtestbasis besteht nur aus tief eingefrorenen, validierten Trackdaten
  des gewaehlten Ordners. Persistente eigene SQLite-Datei ausserhalb des Repos;
  keine Verbindung zur Produktivdatenbank. Alte CLI-Vertraege bleiben erhalten.
- Hoertest-Worker liefert den tatsaechlichen Snapshotpfad. Wiedereroeffnung
  validiert die Zuordnung und Hashbindung, statt den aktuellen Cache einzusetzen.
- Sortierung, Kettenplanung, Anzeige und Reorder verwenden dieselben eingefrorenen
  Kandidatenprofile und Auswahlpraeferenzen. Alle Track-Vorkommen bleiben erhalten.
- Keine erfundenen lokalen Merkmale, keine Gate-Lockerung, kein automatischer Fit.
- KI bleibt explizit Metadatenhilfe. Kein Audioverstehen aus Modellnamen ableiten.
- Keine globale GPU-Abschaltung, keine Modellinstallation oder Veraenderung
  der laufenden LM-Studio-Instanz waehrend Implementierung.

## Aufgaben und Nachweise

1. Hoertest: interne ordnerbegrenzte Metadatenbasis, dauerhafte Zuordnung,
   Ordnerdialog und Tooltips; isolierte Regressionen vor/nach Aenderung.
2. Scoring: lokale Bewertung waehrend aller Strategie-Suchen, konsistente
   Kettenbewertung, begrenzte Suche, Occurrence-Erhalt; gezielte Regressionen.
3. KI: ehrlicher Status, Eignungs-/GPU-Pruefung, keine ungeprueften automatischen
   Modellwechsel oder Downloads; isolierte Provider-/GUI-Regressionen.
4. Unabhaengiger Diffcheck, gezielte Integration, ein finaler Gesamtlauf.
   Native App-/Originalaudio-/GPU-Nachweise gesondert ausweisen.

## Fortschritt

- Ausgangspunkt: `50ea522`; Arbeitsverzeichnis zu Beginn sauber.
- TOR1: MIT AUFLAGEN. Gemeinsames Scoringziel, begrenzte Strategie-Suchraeume,
  Snapshot-Lebenszyklus und nachweisbare GPU-Zuordnung sind explizite Auflagen.
- Hoertest-Implementierung in Arbeit. Scoring-, GPU- und Testvorbereitung parallel.
- Ruling: Kein neuer Worktree; ausdruecklicher Nutzerwunsch gegen weitere Kopien.
- Ruling: AMD-Integrationsskill beschreibt Lemonade und wird nicht angewendet;
  ein Providerwechsel waere nicht der autorisierte LM-Studio-Auftrag.
- RED: drei KI-Statusfaelle und elf lokale Scoringfaelle schlugen erwartungsgemaess fehl.
- GREEN: diese 14 Regressionen bestanden nach Status-/Scoringkorrektur (1,70 s).
- Bestehende Scoringintegration: 353 bestanden, vier fehlgeschlagen (8,42 s).
  Drei Erwartungen verlangten ausdruecklich den alten Trackscore statt des
  lokalen Scores; ein Context-Test mockte die abgeloeste reine Harmonikfunktion.
  Ruling: Erwartungen gemaess Nutzervertrag korrigiert; KI-Neutralitaet,
  Rang-2-Wahl, eigene Legacy-Trackscore-API und Parameterweitergabe bleiben geprueft.
- Hoertest-Schreibauftrag zuerst versehentlich an read-only Waechter gegeben;
  kein Code entstand dort. Korrigiert: schreibberechtigter GUI-Agent implementiert.
- Noch keine Gesamtabnahme, kein Build und kein Originalaudio-/GPU-Laufnachweis.

## Verifizierte Ergaenzungen (10:47 Uhr, lokaler Rechner)

- LM Studio 0.4.25+1, Vulkan-Runtime `llama.cpp-win-x86_64-vulkan-avx2` 2.51.0.
  Lokales App-Bundle `resources/app/.webpack/main/index.js`: Funktionen
  `_0x4c77da` (Device-ID nach visibleDevices), `_0x4e35a4` (disabledGpus)
  und `_0x5db268` (nach deaktivierten GPUs) vom Rechercheagenten und Hauptagenten
  gelesen. SDK-Eingaben sind Survey-Geraete-IDs; LM Studio nummeriert intern um.
  RX-ID 1, iGPU-ID 0, visibleDevices [1,0]. Keine doppelte Umnummerierung in HPG.
  Survey und Schaetzung sind explizit an denselben Host/Port gebunden.
- Echte eigene Instanz des bereits installierten
  `qwen2.5-moe-2x1.5b-deepseek-uncensored-censored-4b` geladen und danach entladen.
  Readback: ratio=1, mainGpu=1, disabledGpus=[0], gpuStrictVramCap=true,
  offloadKVCacheToGpu=true, contextLength=2048. Fremde Instanzen nicht entladen.
- Zweiter, getrennter Inferenznachweis: eigene Instanz
  `hpg-d7f0ee29d2874e6ea33b0a038251c556`, Modellprozess PID 6532;
  13 passive Windows-GPU-Messungen waehrend synthetischer Schemaanfrage.
  RX-LUID 0x12E34 (Survey little-endian 342e010000000000): Compute-Zaehler
  ungleich null, dedizierter Prozessspeicher maximal 2226876416 Bytes.
  iGPU-LUID 0x11547: beobachtete Engine-Zaehler null, 118784 Bytes Kontextspeicher.
  Zaehlerwert nicht als Prozent interpretieren. Dies belegt GPU-Nutzung in
  diesem Messfenster, weder alle Layer noch alle Modelle oder musikalische Eignung.
- Schemaanfrage dieses Modells fehlgeschlagen: keine parsebare JSON-Antwort;
  Serverlog meldet 400 Tokens und Toolcalls. Kein automatischer Wiederholungsversuch.
  Eigene Testinstanz danach entladen. Kein Audio gesendet, keine Musikdatei angelegt.
- SDK 1.5.0 unterdrueckt Progress-Callback-Exceptions. HPG prueft Cancel nach
  Rueckkehr des Ladeaufrufs und bereinigt ausschliesslich seine UUID-Instanz.
  Sofortiger Ladeabbruch ist damit NICHT nachgewiesen. Kein scheinbarer
  Runtime-Beweis-Helfer bleibt ungenutzt im Produktcode.
- Private Hoertest-Snapshots: Fehler vor Publikation bereinigen nur eigene bekannte
  Metadaten; nach Publikation bleiben Satz und DB erhalten, Bindungsfehler sichtbar.
  Neue Vorbereitung validiert Dateien/Cache erneut, statt alte GUI-Snapshots zu nutzen.
  Hoertest-Analyse umgeht unnoetige LLM- und Playlist-Laeufe.
- Lokale Kettensuche: Einstieg und alle Occurrences bleiben erhalten; maximal
  32 zulaessige Tauschversuche mit maximal sieben Tracks/Fenster, feste Aussenanker,
  gerichteter Rankingcache, abschliessender globaler DP. Kein N!-Optimalitaetsanspruch.
- Teststand: 58 fokussierte Vertragsfaelle bestanden (2,53 s), darunter SDK-Mocks,
  Budget-/Nichtverlusttests, private Snapshots und KI-Schema. Zusaetzlich neun native
  synthetische Hearing-Integrationstests bestanden. Kein nativer Originalaudio-Lauf,
  keine aktualisierte EXE und noch kein finaler Gesamtlauf auf diesem Stand.

## Nachpruefung und Korrekturen (11:26 Uhr)

- Gesamtsuite auf dem eingefrorenen Zwischenstand: 4807 bestanden, 9 fehlgeschlagen,
  1055,81 s, Coverage 85,54 %. Kein gruener Gesamtabschluss daraus abgeleitet.
- Echter Produktfehler: `compute_adjacent_transition_metrics` verwendete noch
  Ganztrackwerte fuer den ausgewaehlten lokalen Kandidaten. Jetzt derselbe lokale
  Metrikadapter wie Ordering und Result. Die explizite Legacy-Trackscore-API bleibt.
- Vier alte lokale Score-Erwartungen verlangten einen positiven Ganztrackersatz
  ohne qualifizierten Kandidaten beziehungsweise einen vom Kandidaten abweichenden
  Score. Auf den autorisierten lokalen Vertrag korrigiert; Legacy gesondert geprueft.
- Context-Fatigue: gemessene lokale Fixture-Scores 98 (Techno/Techno) und 96
  (Techno/Tech House). Der vorhandene Context-Wechselvorteil ist nur 1,8 Punkte.
  Keine willkuerliche Gewichtserhoehung, sondern isolierte Regler-Unit-Tests mit
  kontrollierten lokalen Scores; reale lokale Integration separat behalten.
- Prepare-Shutdown-Test: Fake-Dialog akzeptiert jetzt wie der echte Dialog
  `folder=`. Shutdown-Assertions unveraendert.
- Native synthetische Smoke-Abnahme: im Volllauf Initializer-Timeout bei 30 s;
  derselbe einzelne Test ohne Budget-/Produktkorrektur bestanden (33,61 s gesamt).
  Parallelbelastungs-Stabilitaet bleibt ein offener Hinweis, nicht als geloest behauptet.
- 40 neue Anker-/Wave-/Strategieguard-Regressionen bestanden. Unterschiedliche
  Aussenanker, None-Anker, Ablehnung von Ankeropfern und Seitenfenster geprueft.
- KI: explizite Provider-/LM-Katalogauswahl darf nicht heimlich wechseln.
  Neue Sessionregistry bindet Ergebnis an Endpoint, Katalog, echten Schema-/Prompt-
  Vertrag und exakte SDK-Load-Konfiguration. Schluessel vor HTTP eingefroren.
  Bekannte Antwortfehler sperren erneute Analyse vor Laden; expliziter Test darf
  neu qualifizieren. Transport-/GPU-/Cancel-/DB-Fehler sind keine Schemafehler.
  Keine persistente Modellzertifizierung; Neustart bedeutet erneut ungeprueft.
- Ein alter Test-Dummy mockte nach Provider-Routing-Aenderung die falsche Funktion.
  Unerwuenschter realer Ollama-Start-/Pullversuch fuer `model` wurde protokolliert;
  Testlauf beendet und Dummy korrigiert. Anschliessend kein Ollama-Prozess mehr.
  In Standard- sowie beiden konfigurierten Ollama-Modellverzeichnissen keine seit
  dem Versuch neu geschriebenen Dateien gefunden. Keine Installation behauptet.
- Nachpruefungen: 345 bestanden/1 deselected in17,24 s (GUI/AI/Hearing/Scoring);
  anschliessend 521 bestanden in15,28 s (voller betroffener Scoring-/KI-Teilumfang).
  Ein direkter QThread-Unit-Test musste den Cancel-Zustand mocken: Qt ignoriert
  requestInterruption bei nicht gestarteten Threads. Gezielte drei Fehlerklassen
  danach bestanden; keine Produktlockerung dafuer.
- Echter AITestWorker mit installiertem `granite-4.0-h-tiny`: Metadatenschema
  bestanden in45,6446 s; eigene Instanz `hpg-2cab4e656b1a4651a4a8989fe49584e3`
  danach entladen. Kein Download, kein Audio, keine musikalische Qualifikation.
- Isolierter nativer Qt-Lauf auf 26 Original-AIFF gestartet: leere eigene DB,
  regulare MainWindow-/Analyse-/Playlist-Worker, danach Ordner-Hoertestvorbereitung
  und regulaerer HearingLoadWorker zum Rating-Dialog. Vorher/Nachher SHA256 und
  Audioexport-Inventur vorgesehen; Abschlussbericht noch ausstehend.

## Nativer Originalnachweis und bewusst offene Qualitaetsgrenze

Der programmatisch bediente native Qt-Lauf (offscreen, keine Bedienung einer
laufenden Benutzerinstanz) ist abgeschlossen: 689,30 s, 26/26 Original-AIFF ohne
Analyse-Issues, 26 sichtbare Ergebniszeilen. Leerer isolierter Cache; alle Tracks
nutzen `rekordbox_fast_tail` (Rekordbox-Metadaten plus eigene Audiomessungen).
Dies ist kein Voll-Librosa-ohne-Rekordbox-Nachweis.

- 5 von 25 Kanten geplant, 20 ungeplant. Keine vollstaendig mischbare Playlist
  oder musikalische Optimalitaet daraus abgeleitet.
- Derselbe Ordner danach ueber den nativen Prepare-Dialog: automatische private
  Metadatenbasis, dauerhafte Hashzuordnung, 2 Paare/7 Quellenreferenzen, echter
  HearingLoadWorker und nativer Rating-Dialog. Keine Note erfunden, keine Wiedergabe
  oder musikalische Abnahme in diesem Lauf; Satz ist nicht auditiert.
- Vorher/Nachher-Groesse, mtime und SHA256 aller 26 Originale identisch.
  Keine Dateien in den unterstuetzten Audioformaten im Testausgabeordner angelegt.
- Bericht: `%LOCALAPPDATA%/Temp/hpg-validation-0ebd4bce-a32d-40ec-befb-2c1246b91774/native-originals/report.json`.
  Core-Fingerprint `74cde0f5efce62671ff2ebaefe37f50d58dea107b55ea8d9bdc456d885fb8652`;
  main.py SHA256 `f26c3913342fae4fc468505c5213147013c5fb68619d4d5686f042f92317f707`.

Read-only-Ursachenauswertung derselben Snapshotdaten, ohne erneuten Audiolauf:

- Alle 26 gespeicherten Beatgrid-Pruefungen melden `mismatch`. 18 Tracks haben
  Audio-Downbeat-Konfidenz unter der unveraenderten Schwelle0,30 (zwoelf0,0;
  sechs0,029..0,175), acht darueber (0,555..0,924).
- `mix_candidates.py` misst Bassenergie/-Punch auch ohne sicheren Anker. Es
  unterdrueckt aber die beatgebundenen Groove-/Bassmuster, Kick-Zustaende und
  `traegt_allein`. Die fehlenden Bass-/Struktur-Qualitaetsfaktoren sind daher
  ueberwiegend Folge derselben Ankerunsicherheit, nicht drei unabhaengige Ausfaelle.
- 650 gerichtete Paarpruefungen: 334 ausserhalb2BPM, 293 ohne vollstaendig
  qualifizierten Kandidaten, 23 qualifizierte gerichtete Paare zwischen sieben
  Tracks. Der achte rhythmisch verwertbare Track liegt mit127BPM ausserhalb dieses
  Verbunds (140/142BPM). Obergrenze daher sechs geplante Nachbarkanten; fuenf erreicht.
  Ob die sechste zeitlich konsistent erreichbar ist, ist nicht nachgewiesen.
- Hearing hat ein zusaetzliches Harmonie-Gate; seine18 ausgewaehlten Paarmoeglichkeiten
  sind nicht ungeprueft mit den23 gerichteten App-Kanten gleichzusetzen.
- Die konkreten Ursachen der zwoelf Null-Konfidenzen speichert der bestehende
  Snapshot nicht. Keine Behauptung, welches Detektordetail jeweils schuld ist.
  Analyse-/Downbeat-/Mixkandidaten-Code wurde in dieser Umsetzung nicht veraendert.

Die Integrationskorrekturen beseitigen diese bestehende Detektorgrenze nicht.
Keine Gates gesenkt, keine Konfidenzen erfunden, keine globale Freigabe der
musikalischen Analyse. Eine gezielte Audio-Anker-Diagnose/Kalibrierung bleibt offen.

## Abschlussreview: Grenzen und formale Pruefung

Der dokumentarische Review `review-final.md` im obigen Validierungsordner urteilt
MIT AUFLAGEN. Der ausgefuehrte Formatvalidator lehnt ihn mit Exitcode1 ab:
TOR2 verlangt ein DURCHGEWUNKENES TOR1; belegt ist MIT AUFLAGEN. Dieser Status
wurde nicht umdeklariert. Keine formale Gesamtfreigabe, kein Release-Commit.
Der Dokumentationsreviewer hat zuvor an Hearing mitgearbeitet; seine Pruefung
dieses Teils ist daher keine unabhaengige Autorenpruefung. Ein anderer Reviewer
prueft den Hearing-Diff separat schreibgeschuetzt. Keine erneute Audioanalyse.

## Gesamtlauf abgeschlossen; eng begrenzter Sicherheitsnachtrag

`pytest-final.log`: Standardkommando mit vier xdist-Workern, 4868 bestanden in
1113,93 s (18:33), Coverage85,46%, Exitcode0. Die Konfiguration schliesst `slow`
aus; kein Nachweis fuer diese abgewaehlten Tests. Auch der vorher unter Last
fehlgeschlagene Initializer-Smoke bestand in diesem Lauf. Daraus folgt keine
Garantie beliebiger Parallelbelastung.

Boyles unabhaengiger Hearing-Review fand danach eine fehlende Ownership-Identitaet
bei der Fehlerbereinigung: gleichnamig ersetzte regulare Dateien/Verzeichnisse
koennten entfernt werden. Zusaetzlich konnte das Association-finally eine bereits
vorhandene, nie selbst erstellte Tempdatei entfernen. Kein beobachteter Datenverlust.
Eng begrenzte Korrektur mit RED/GREEN-Regressionen gestartet. Obiger Gesamtlauf
gilt fuer den Stand VOR diesem Nachtrag, nicht ungeprueft fuer spaetere Aenderungen.

Der Nachtrag ist abgeschlossen: unveraenderlicher Ownership-Kontext mit Root-,
Verzeichnis- und Dateiidentitaet (Device/Inode/Birth/Typ) statt Besitz-Boolean.
Ersetzungen, fehlende Identitaet und unbekannte Journale verweigern Bereinigung;
kollidierende, nie selbst erstellte Association-Tempdateien bleiben erhalten.
Identitaetspruefung plus pfadbasierte Operation ist kein atomarer Anti-TOCTOU-Schutz.

- `ownership-red.log`: sechs Regressionen vor Fix fehlgeschlagen (0,39 s).
- `ownership-green.log`: 24 bestanden (5,05 s), inklusive der sechs Regressionen.
- `ownership-integration.log`: 98 native Hearing-/Browser-Integrationstests bestanden
  (7,65 s, Exitcode0); keine erneute Analyse der 26 Originaltracks.
- Unabhaengiger Boyle-Nachreview: vorheriger Ownership-Befund fuer diesen Umfang
  geschlossen, keine neuen statischen Befunde. Urteil bleibt MIT AUFLAGEN wegen
  begrenztem Pruefumfang; keine globale Produkt- oder musikalische Freigabe.

Betroffen vom Nachtrag: `hearing_managed.py`, `hearing_jobs.py`,
`test_hearing_managed.py`. Die native Originaltrack-Evidenz bleibt an den davor
geprueften Fingerprint gebunden; die Nachtests decken das anschliessende Delta ab.
Kein weiterer Volltest, Build, EXE-Austausch, Commit oder Push. `Start.bat` startet
den aktuellen Quellcode; die bestehende EXE enthaelt diese Umsetzung nicht.
