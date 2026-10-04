# Hörtest-Werkzeuge vollständig in HPG integrieren – Umsetzungsplan

> **Für agentische Umsetzung:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`. Aufgaben einzeln ausführen und abhaken.

**Ziel:** Alle Hörtest-Funktionen, die die vorhandenen Zusatzwerkzeuge tatsächlich bereitstellen, sind vollständig und ohne separaten Werkzeug-Workflow direkt in der HPG-App nutzbar. Menschliche Bewertungen bleiben menschliche Eingaben. „Fit“ bezeichnet die vorhandene statistische Kalibrierung von Kandidaten-Präferenzen, nicht das Trainieren eines Audio-LLM oder ein autonom lernendes Modell.

**Architektur:** Die App bekommt einen vollständigen Hörtest-Arbeitsbereich mit typisierten Satzmodi, Parametern, Fortschritt, Satzprüfung, nativer Bewertung in der App und Fit. Die fachliche Logik wird in intern importierbare Services überführt, die sowohl die GUI als auch die bisherigen CLI-Einstiege verwenden. Im normalen App-Ablauf werden weder `rate_transitions.py` noch Auditor/Blindtest-Skript als externe CLI-Prozesse gestartet; das wäre nur ein neues GUI-Frontend vor dem alten Werkzeug, keine Integration. GUI und optionaler mobiler Browser nutzen dieselben Rating-Schemata und Validierungs-/Speicherfunktionen. Der Launcher ist für lokalen Ablauf nicht erforderlich; CLI bleibt bis zum Paritätsnachweis erhalten und danach Entwickler-/Diagnoseweg.

**Tech Stack:** Python 3.12, PyQt6, QThread/QProcess, bestehende `tools/rate_transitions.py`, `tools/hoertest_server.py`, `tools/audit_candidate_set.py`, `tools/prepare_dj_blind_test.py`, HPG-Cache und pytest.

**Spezifikation:** Nutzeranforderung aus dem Gespräch vom 2026-09-27; verifizierte CLI-, Webserver-, Audit- und App-Schnittstellen. Dieser Plan enthält ausdrücklich nur Funktionalität, die im Ist-Werkzeug belegt ist; mögliche zusätzliche Blindtest-Auswertung ist als neue, separat freizugebende Funktion gekennzeichnet. Dies ist keine Implementierung und keine Behauptung bereits erreichter Parität.

## Globale Vorgaben

- Projekt-venv ausschließlich Python 3.12: `venv312\Scripts\python.exe`.
- Die vorhandenen DSP-, Kandidaten-, Scoring-, Rendering-, Rating-, Audit- und Fit-Logiken nicht duplizieren.
- Bestehende CLI-Aufrufe/Satzformate rückwärtskompatibel halten.
- Normale App-Funktionalität darf nicht davon abhängen, dass externe Tool-CLI, BAT, separates Python oder Projektdateipfade gestartet werden. Bestehende CLI wird dünner Adapter über denselben internen Service, den die GUI direkt importiert.
- UI nur im Hauptthread aktualisieren; Worker-Ergebnisse über eigene Signale und Source-Guards zustellen.
- Keine vorhandenen Ziele, Hörtest-Sätze, Bewertungsdateien, Schlüsseldateien, Cache-/DB-/Lock-/Coverage-Dateien überschreiben oder löschen.
- Explizite Bestätigung vor jedem Fit, der `candidate_preferences` wirksam ändern kann.
- Klarer Unterschied in UI und Doku: Hörtest-Bewertungen sind menschliche Labels; `fit --modus einzel` schreibt `gewichte.json` als Diagnose/Entwurf und übernimmt nicht automatisch App-Gewichte; Kandidaten-Fit kann unter Gates `candidate_preferences` ändern. Keine Aussage „Modell trainiert“ für reine Präferenzkalibrierung.
- In-App-Bewertung ist Pflicht für Vollparität; Browser/Server ist optionaler Remote-Zugang zur selben Session, kein Ersatz für native Bedienung.
- Keine Aussage „Werkzeug nicht mehr nötig“, bevor alle Inventarpunkte durch GUI-Funktion und Tests abgedeckt sind.
- Vor jeder nichttrivialen Umsetzung `hpg-orientation` und zuständige Fach-Skills laden; vor Umsetzung und Commit unabhängigen Read-only-Wächterdurchgang nach `.agents/agents/hpg-waechter.md` absolvieren.
- Abschlusslauf: `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`; Cache-/DB-/Lock-/Coverage-Dateien bleiben unangetastet.

## Review-Fokus

- Bestehender Satz, vorhandene Ratings oder belegter Port: App verweigert überschreibende/ungefragte Eingriffe und beendet nur eigene Prozesse (Tests in Aufgaben 2–4).
- Ungültiger, veralteter oder unvollständiger Satz/Audit: Fit ist gesperrt, konkrete Ursache wird angezeigt (Aufgaben 2, 4, 5).
- Einzel-, Kandidaten-, Dreinoten- und Dramaturgie-Schema: jeweilige Eingaben, Fortschritt und Validierung stimmen mit Server/CLI überein (Aufgaben 1–4).
- Abbruch, Fenster schließen, Worker-Fehler oder veraltetes Signal: keine Thread-Leiche, falsche Statusmeldung oder halb publizierter Satz (Aufgaben 2–4).
- Fit nicht belastbar/keine Übernahme erlaubt: Diagnose/Entwurf wird angezeigt und produktive Präferenzen bleiben unverändert (Aufgabe 5).

---

## Bestandsinventar – Funktionsumfang, der Parität erhalten muss

Inventarquelle ist der aktuelle Code, nicht alte Statusdokumente:

1. `tools/rate_transitions.py prepare`: `einzel`, `kandidaten`, `dramaturgie`; Kandidatenmodus mit optionalem `--dreinoten-pilot`; `--anzahl`, `--out`, `--bpm-toleranz`, `--energy-direction`, `--harmonic-strictness`, `--allow-experimental`, `--cache`, `--seed`, `--nur-genre`, `--sequenz-tracks`, `--uebergaenge-pro-variante`, `--max-versionen-pro-paar`, `--tracks-einmalig`, `--auswahlprofil`, `--workers`, `--transition-type-modus`.
2. `tools/hoertest_server.py`: lokal nur an `127.0.0.1`; Formate Einzel, Kandidat, Dreinoten, Dramaturgie; GET `/`, `/index.html`, `/reihenfolge`, `/noten`, `/daten`, `/daten-dramaturgie`, `/clips/...`; POST `/note`, `/bester`, `/transition-note`, `/dramaturgie-note`; Range-Streaming und sofortiges Speichern/Wiederaufnahme über existierende CSVs. Das sind Ist-Protokolle, nicht alles separate GUI-Seiten.
3. `tools/audit_candidate_set.py`: ausschließlich strenger Kandidatensatz-Audit mit exakt gebundenem Cache/Manifest/Algorithmus und Render-Replay. Er ist **keine** generische Prüfung für Einzel- oder Dramaturgiesätze. Kandidaten-Fit verlangt den passenden erfolgreichen Report.
4. `tools/rate_transitions.py fit`: Einzelmodus erzeugt `gewichte.json` und Diagnose, aber aktiviert keine Nutzerpräferenzen; Kandidatenmodus validiert Audit-/Cache-/Satzbindung und Ratings, berechnet Holdout/Diagnosen und kann nur bei Gates Kandidatenpräferenzen atomar übernehmen. Kandidaten-Dreinoten-Auswertung hat zusätzliche Freigabegates. Optionen: `--dir`, `--seed`, wiederholbares `--genre`, `--modus`, Kandidaten-`--cache`, Kandidaten-`--audit-report`.
5. `tools/prepare_dj_blind_test.py`: validiert Manifest, Pfadroot, Clip-Dauer/Format/Hash, erzeugt neutrale A/B-Clips und trennt öffentliche Session und geheimen Schlüssel. Das Skript stellt **keine** Rating-Erfassung, Entblindung oder statistische Auswertung bereit. Eine solche Blindtest-End-to-End-Funktion ist nicht Teil der Ist-Parität; separat spezifizieren/freigeben, falls gewünscht.
6. `tools/hoertest_launcher.py`: sucht nur direkte Unterordner an Desktop/Projekt, zeigt Fortschritt/Schema, erlaubt manuelle Pfadwahl und startet den Server. Der Launcher beendet nur seinen selbst gestarteten Serverprozess; fremde Prozesse am Standardport bleiben unberührt. Vollparität erfordert in der App Satzsuche über einen benutzergewählten Root (rekursiv nur nach ausdrücklicher Auswahl), Fortschrittsanzeige und Serverstart.
7. `Start_Hoertest.bat` und Frozen-Dispatch in `main.py`: derzeit separate Startpfade. Die App muss nachweisen, dass sie alle intern benötigten Funktionen paketiert startet; die BAT wird nach Paritätsbeleg nur optionaler Kompatibilitätsweg.

## Geplante Dateien und Verantwortungen

- **Ändern `main.py`:** Hörtest-Arbeitsbereich, Formulare, Satz-/Moduszustand, native In-App-Bewertung, GUI-Aktionen, QThread/QProcess-Lebenszyklus und verständliche Ergebnisanzeige. Keine DSP-/Fit-Algorithmen hier duplizieren.
- **Neu `hpg_core/hearing_workflow.py` und fokussierte Service-Module (nach Aufgabe 1):** importierbare Producer-/Audit-/Fit-/Blindtest-Orchestrierung ohne Qt, mit typisierten Konfigurationen/Resultaten; die jeweilige bestehende Algorithmik wird dorthin verlagert oder daraus aufgerufen, nicht dupliziert.
- **Ändern Tool-CLI-Dateien:** Parser/CLI bleiben rückwärtskompatible Adapter, die dieselben Services aufrufen. Kein GUI-Subprocess zu diesen CLI-Dateien für lokale Set-Erstellung, Audit, Fit oder Blindtest.
- **Optionaler Remote-Server:** darf als App-eigener Prozess für Smartphone-Browser bedient werden; nicht nötig für native Bewertung am Desktop.
- **Ändern/erweitern `tests/test_main_window.py`:** GUI-Bindings und Qt-Lifecycle.
- **Neu/erweitern Tests für Hearing-Services und Tools:** Verträge, Schemas, nicht-destruktive Fehlerpfade, Fit-Bindung und blindes A/B.
- **Ändern `docs/QUICK_START.txt` oder passende Nutzerdoku:** nur nach real implementierter UI; CLI-Bedienung als optionales Diagnose-/Entwicklerverfahren kennzeichnen.
- **Nicht Teil ohne gesonderte Anforderung:** neue Blindtest-Rating-/Entblindungs-/Statistikpipeline; das heutige Blindtesttool kann nur Sessions vorbereiten.

## Aufgaben

**Ausführungsreihenfolge und Parallelität:** Aufgabe 1 ist zwingendes Gate. Danach Aufgaben 2–6 als getrennte Teilbereiche planen; parallel dürfen nur unabhängige Code-/Testarbeitspakete laufen. `main.py`-Änderungen werden serialisiert (ein Integrator), weil Panels, Worker-Lifecycle und Slots dort zusammenlaufen. Tool-/Service-Tests und Frozen-Packaging-Inventar können unabhängig vorbereitet werden. Nie zwei volle pytest-Läufe parallel. Pro Aufgabe: vorab unabhängiger Read-only-Wächter, gezielter Test, Wächter-Findings beheben, Regression; nach Integration der vollen Änderung Abschluss-Wächter und vollständige Suite. Kein Commit ohne user/repo-prozessgemäße Freigabe.

**Testdateien als Startpunkte (Ist-Bestand verifizieren, nicht blind annehmen):** `tests/test_rate_transitions.py`, `tests/test_hoertest_server.py`, `tests/test_audit_candidate_set.py`, `tests/test_prepare_dj_blind_test.py`, `tests/test_main_window.py`, `tests/test_candidate_preferences.py`, `tests/test_pair_candidates.py`, `tests/test_e2e_kandidaten_app.py`; neue native UI-/Service-Tests dort ergänzen, wo fachliche Zuständigkeit klar ist.

### Aufgabe 1: Tool-zu-App-Abdeckungsmatrix und GUI-Informationsarchitektur

**Dateien:** keine Produktionsänderung; Plan-/Inventargrundlage, danach Dokumentation.

**Schnittstellen:** Liefert Tabelle `Werkzeugfunktion → bestehende API/CLI → GUI-Aktion → Testbeleg`, einschließlich aller Optionen oben.

- [ ] Jeden CLI-Parser, Server-Endpunkt, Satzvalidator, Auditor und Fit-Ausgang direkt gegen aktuellen Code aufnehmen.
- [ ] Für jede Option als GUI-Feld, bewusst ausgeschlossene Entwickleroption oder nicht unterstützten Punkt klassifizieren; Ausschluss begründen und dem Nutzer sichtbar machen.
- [ ] Festlegen, wie Satzliste, Typ, Parameter, Status, Bewertung öffnen, Audit, Fit-Bericht und Blindtest im bestehenden QUALITY-Bereich erreichbar sind.
- [ ] Wächter-Read-only-Prüfung des Inventars; offene Paritätslücken vor Implementation schließen.

**Abnahmekriterium:** Commitfähige Paritätsmatrix benennt für jeden CLI-Parameter, Satztyp, Bewertungsdimension, HTTP-Routenverhalten, Fit-Ausgang und Launcher-Nutzerfunktion den App-Ersatz sowie konkrete Testfunktion(en). Toolverhalten, das absichtlich nicht migriert wird, steht explizit als nicht benötigter Admin-/Diagnosepfad darin. Auflistung ist per `--help`, Route-Handler und Erfolgs-/Fehlerpfad im Code belegt.

**Mindest-Tests für Matrix:** Parser-Optionstests in `tests/test_rate_transitions.py`; Route-/Schema-Matrix in `tests/test_hoertest_server.py`; Audit-Vertrag in `tests/test_audit_candidate_set.py`; In-App-Auswahl/Actions/Signals in `tests/test_main_window.py`. Aufgabe 1 liefert die tatsächlich vorhandenen konkreten Testnamen und fügt fehlende hinzu.

### Aufgabe 2: Satzverwaltung und Erzeugung aller Satztypen

**Dateien:** `main.py`, falls erforderlich Service-Schnittstelle(n), GUI-/Service-Tests.

**Schnittstellen:** GUI-Formular erzeugt validierte Konfiguration für Einzel, Kandidaten, Dreinoten und Dramaturgie; QThread ruft importierbaren Hearing-Service direkt auf und emittiert Fortschritt/Endergebnis. CLI ruft denselben Service auf.

- [ ] Tests für Moduswahl und vollständige Option-zu-Argument-Zuordnung schreiben; ungültige Grenzwerte vor Workerstart ablehnen.
- [ ] Satzverwaltung mit Suche/Auswahl, Erkennung des Formats und Fortschritt für vorhandene Ordner ergänzen.
- [ ] Erzeugungsoptionen aus dem CLI zugänglich machen: Anzahl, Genre, BPM/Energy/Harmonie, Seed, Track-Einmaligkeit, Auswahlprofil, Worker, Transitiontyp, Versionslimit und Dramaturgie-Parameter.
- [ ] Bestehende Sätze nur lesend öffnen; neue Ausgabe atomar in eigenem Staging erzeugen, validieren und veröffentlichen; vorhandene Ziele nie überschreiben.
- [ ] GUI-Fortschritt/Abbruch/QThread-Cleanup testen; kompletter Satz jeweils mit dem vorhandenen Tool-Validator lesbar.

**Abnahmekriterium:** Die GUI kann jeden unterstützten Satzmodus samt fachlich relevanten Parametern erzeugen und bestehende Läufe fortsetzen, ohne CLI-Bedienung.

**Testbelege:** parametrisiert pro `modus` und Optionsgruppe; CLI-Service und GUI erzeugen denselben Manifest-/CSV-Vertrag; Zieldatei existiert/Permission denied/fehlende Tracks/kein Kandidatenpaar bleiben ohne Teilpublikation; cancel und close lassen Worker vollständig enden. Bestehende Producer-Tests bleiben maßgebliche Algorithmen-Regression.

### Aufgabe 3: Native In-App-Bewertung, Remote-Browser und Satzfortsetzung

**Dateien:** `main.py`, nötigenfalls importierbare Server-Schnittstelle, Qt-/Server-Integrationstests.

**Schnittstellen:** In-App-Rating nutzt denselben validierten Speicher-/Merge-Pfad wie `HoertestHandler`; der vorhandene Loopback-Server bleibt optionaler Remote-Client desselben Satzes. GUI zeigt nie eine zweite, divergierende Ratinglogik.

- [ ] Tests pro Satzschema für Status/Completeness und Ratingsfortschreibung ergänzen.
- [ ] In der App für jeden Modus alle aktuell möglichen Nutzeraktionen nativ anbieten: Clip abspielen/wechseln, 1–5-Noten; Kandidaten „bester“ markieren und Bewertungsdimensionen; Dramaturgie-Transition- und Varianten-Noten. Bereits vorhandene DSP-Preview-/Playback-Komponenten wiederverwenden, keine zweite Audioengine bauen.
- [ ] GUI und optionalen Remote-Browser mit denselben Satz-/Rating-Servicefunktionen verbinden; Bestehende CSV-Schemata, sofortiges Speichern, `zeit`-Felder, Wahlregeln und Fortsetzung unverändert erfüllen.
- [ ] Satz wählen, optional Remote-Rating starten, Browser öffnen, URL/Status/Port anzeigen, Server stoppen und später denselben Satz fortsetzen in der GUI bereitstellen.
- [ ] Keine fremden Prozesse am Port beenden; freien Loopback-Port reservieren und gebundene `QProcess`-Instanz mit begrenzter Retry-Logik verwalten.
- [ ] Contract-Tests je Bewertungsdimension und HTTP-Aktion (GET `/daten*`, Range `/clips`, POST `/note`, `/bester`, `/transition-note`, `/dramaturgie-note`) plus native UI-Aktion auf denselben erwarteten CSV-Zustand.
- [ ] Stale-Signale, Fenster schließen, Serverfehler und Nutzerabbruch testen.

**Abnahmekriterium:** Alle Bewertungen können innerhalb der Desktop-App ohne externen Browser/Launcher/CLI vollständig erstellt, geändert und fortgesetzt werden. Remote-Browser bleibt optional und interoperabel.

**Testbelege:** jede GUI-Bewertung wird mit Handler-Merge verglichen: gleiche Eingabe → byte-/schema-konsistenter fachlicher CSV-Zustand; zurücksetzen/ändern, Pause/Resume, „bester“ mit verbotener Note, dreinotige Felder und Dramaturgie-Varianten/-Transitions je eigene Tests. Native Playback nutzt die App-Audioausgabe und darf Qt-Hauptthread nicht blockieren; Qt-Playback-API/Abhängigkeit erst in Aufgabe 1 feststellen.

### Aufgabe 4: Audit/Validierung und vollständige Fit-Vorprüfung

**Dateien:** `main.py`, falls erforderlich Audit-Service-Schnittstelle, GUI-/Audit-Tests.

**Schnittstellen:** Kandidaten-Audit-Service nimmt exakte Satz-/Cache-/Report-Pfade und gibt strukturierten Report/Fehler zurück. Einzel- und Dramaturgiesätze benutzen ihre jeweiligen vorhandenen Struktur-/Schema-Validatoren, nicht `audit_candidate_set.py`. Fit-Voraussetzungen je Modus folgen dem jeweiligen CLI-Vertrag. GUI ruft diese Services direkt auf, nicht per CLI-Subprocess.

- [ ] Tests für Kandidaten-Audit-Erfolg, strukturierten Fehlerreport, Report-Kollision, Cachebindung, Cache-WAL/Änderung und während des Audits veränderten Satz schreiben.
- [ ] Tests für Einzel- und Dramaturgie-Schema-/Manifest-Validierung getrennt ergänzen; nicht vorgeben, dafür gäbe es denselben vollständigen Replay-Audit.
- [ ] Audit-Ergebnis und Warnungen im Hörtestbereich lesbar darstellen; Auditdatei getrennt vom Satz und Cache anlegen.
- [ ] Vollständigkeits-/Schema-/Paarwahl-Prüfung für jeden Fit-Modus an vorhandene Validatoren binden.
- [ ] Kandidaten-Fit bis zum abgeschlossenen, erfolgreichen Satz-Audit deaktivieren; Audit-Report nicht vom Nutzer versehentlich verwechselbar machen.
- [ ] Keine Schreiboperation am Audio, Cache oder existierenden Ratings während des Audits nachweisen.

**Abnahmekriterium:** Kandidaten-Fit kann nicht ohne passenden erfolgreichen Audit starten. Für Modi ohne diesen Audit existiert eine dokumentierte, getestete, modusspezifische Freigabeprüfung; UI kennzeichnet deren geringeren/anderen Prüfstatus klar.

**Testbelege:** erfolgreicher Kandidatenreport bindet finalen absoluten Satzpfad, Manifest-/CSV-Fingerprints und Cache; mutierte Bewertung, Manifest, Cache, WAL oder ersetzter Report verhindert Fit. Einzel-/Dramaturgie-Tests prüfen nur die dafür vorhandene Satzvalidierung und dürfen keinen Kandidaten-Replay vortäuschen.

### Aufgabe 5: Fit, Trainingsergebnis und transparente Übernahme

**Dateien:** `main.py`, gegebenenfalls Service-Schnittstelle, Fit-/GUI-Regressionstests.

**Schnittstellen:** Fit-Service liefert typisiertes Resultat samt Report/Entwurf und Übernahmestatus. Produktive Präferenzen werden nur durch den existierenden atomaren Kandidatenpräferenz-Pfad verändert. CLI und GUI verwenden denselben Service.

- [ ] Tests für Einzel- und Kandidatenmodus, Seed/Genre, unzureichende/unausgewogene Stichprobe, nicht-identifizierbare Merkmale, `uebernahme_erlaubt=False`, Dreinoten-Gates und atomare Fehlerfälle schreiben.
- [ ] Fitparameter aus CLI sinnvoll im GUI anbieten; doppeldeutige `--genre`/`--nur-genre`-Bedeutungen getrennt beschriften.
- [ ] Vor möglicher Änderung an produktiven Gewichten konkrete Bestätigung zeigen; Abbrechen muss Präferenzen byte-identisch belassen.
- [ ] Ergebnisse aus realen Ausgabedateien rendern: Einzelmodus `gewichte.json` (nur Diagnose/Entwurf); Kandidatenmodus `dreinoten_fit_bericht.json` und tatsächlicher Override-/Entwurfsstatus. Keine Statusableitung aus leerer CLI-Ausgabe oder mtime-Heuristik.
- [ ] Einzel-Fit nicht als direkt produktiv wirksam darstellen: falls Übernahme in App erwünscht, eigener expliziter, validierter Import-/Apply-Schritt mit Vorschau, atomarer Persistenz und Rollback-Test ergänzen; Standard bleibt Entwurf.
- [ ] Kandidaten-Fit: Datengrundlage, Holdout-/Track-Trennung, Baseline, Unsicherheit/Identifizierbarkeit, Gates, Entscheidung und geänderte Genres anzeigen.
- [ ] Nach tatsächlicher Übernahme Präferenz-Cache/Rankingzustand gezielt invalidieren und neu berechnen; testen, dass neue Kandidatenrankings aktive Gewichte verwenden und alte Results nicht still veraltet bleiben.

**Abnahmekriterium:** UI nennt operation „Präferenz-Fit/Kalibrierung“, nicht Modelltraining. Nutzer kann belegen, welche Ratings einflossen, welcher Bericht entstand und ob aktive App-Gewichte wirklich geschrieben und vom Ranking neu geladen wurden.

**Testbelege:** bestehende `tests/test_rate_transitions.py` Fitfälle plus `tests/test_candidate_preferences.py` atomare Persistenz und `tests/test_pair_candidates.py`/`tests/test_e2e_kandidaten_app.py` Rangwirkung. Neue GUI-Tests prüfen exakte Resultatdatei-/Statusbindung, Zustimmung Nein/Ja, Fehler beim Schreiben und Ranking-Refresh. Fit ist nicht abbrechbar, sofern der bestehenden CLI kein kooperatives Cancel-Vertrag hinzugefügt und getestet wurde; GUI muss währenddessen Schließen sicher behandeln.

### Aufgabe 6: Blindtest-Session-Erstellung in der App (nur Ist-Funktion)

**Dateien:** `main.py`, `tools/prepare_dj_blind_test.py` (nur Service/API falls nötig), Blindtest-/GUI-Tests.

**Schnittstellen:** GUI ruft einen intern importierbaren Blindtest-Service mit validiertem Manifest, erlaubtem Quellroot, neuem Sessionordner und getrenntem Schlüsselpfad auf; CLI ruft denselben Service auf. Ergebnis: öffentliche `blind_session.csv`/Clips und private Zuordnung. Bewertungsimport/Entblindung sind keine vorhandenen Werkzeugfunktionen.

- [ ] Tests für Pfadcontainment, doppelte/identische Clips, Dauer-/Samplerateabweichung, vorhandene Session und getrennten Schlüssel schreiben.
- [ ] App führt Prüfung und Session-Erstellung aus; öffentliche Session und geheimer Zuordnungsschlüssel bleiben physisch getrennt.
- [ ] App zeigt klare Ausgabeorte und trennt öffentliche Session von privatem Schlüssel; Schlüssel darf nie in öffentlichem Sessionordner, Browser oder Logs landen.
- [ ] Nutzer kann Session abschließen/Dateien auf Integrität prüfen; keine Entblindung oder Statistik behaupten, weil das Werkzeug diese Funktion nicht implementiert.
- [ ] Optionaler Folgeschritt nur nach separater Spezifikation: Import `validation/dj_blind_test_template.csv`, Zuordnungsprüfung per Schlüssel, Ausschlussregeln und aggregierte Auswertung. Nicht ungefragt mit Trainingslabels/Präferenz-Fit vermischen.

**Abnahmekriterium:** Die vorhandene Blindtest-Session-Erstellung ist per App vollständig verfügbar; Plan verspricht keine nicht existente Bewertung/Auswertung. Eine spätere Entblindungsfunktion erhält eigenes Konzept und Tests.

**Testbelege:** bestehende `tests/test_prepare_dj_blind_test.py` bleibt Producer-Vertrag; GUI-Tests prüfen nur sichere Parameterweitergabe, unabhängige Zielpfade und Fehlerdarstellung. Kein Real-Musiklauf als automatisierter Test und kein geheimes Mapping im Screenshot/Log.

### Aufgabe 7: Werkzeugparität, Packaging und Ende-zu-Ende-Verifikation

**Dateien:** Tool-/GUI-Tests, Packaging-/Nutzerdokumentation, gegebenenfalls `main.py`.

**Schnittstellen:** Paritätsmatrix aus Aufgabe 1 plus reproduzierbare end-to-end Session.

- [ ] Automatisierte Vertrags- und Golden-Master-Tests vergleichen CLI und GUI-Serviceausgaben für gleiche Testdaten/Parameter sowie Rundreisen jedes CSV/JSON-Schemas.
- [ ] Frozen-Build testen: Import/Dispatch jedes benötigten Producers, des Kandidaten-Audits, Rating-Service, optionalen Servers und Blindtest-Preparers; Ressourcen-/Template-/Static-Dateien auffindbar; keine Abhängigkeit auf externen Projektpfad oder `python.exe`.
- [ ] E2E ohne Nutzerdaten mit isoliertem Temp-Cache/Fixtures: jeden Satztyp erstellen → schema-validieren → nativ bewerten → schließen/fortsetzen → Fit/Entwurf prüfen; Kandidatensatz zusätzlich auditieren → erlaubten Apply testen → Präferenzwirkung auf Ranking prüfen.
- [ ] Separater manueller Usability-Check: App-Start, lokalen Hörtest in App bedienen, Pause/Wechsel/Speichern/Resume, Fehler verständlich; menschliches Audio-Urteil bleibt explizit außerhalb automatisierter Qualitätsbehauptungen.
- [ ] Unabhängiger Wächter-Read-only-Durchgang vor Umsetzung und Abschlussreview nach Umsetzung, Findings beheben und erneut prüfen.
- [ ] Erst danach vollständigen Pflicht-Testlauf `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q` und Build-/Smokeprüfung ausführen.
- [ ] Schnellstart aktualisieren und Zusatzwerkzeug erst dann als optionalen Diagnose-/Entwicklerweg bezeichnen, wenn die Matrix lückenlos ist.

**Abnahmekriterium:** Alle Inventarpunkte sind über App-Aktionen erreichbar, getestete CLI/App-Parität ist belegt, Gesamt-Testlauf und Packaging-Smokecheck bestehen. Bis dahin gilt das Zusatzwerkzeug weiterhin als erforderlich.

**Frozen-Dispatch-Korrektur:** Der aktuelle Dispatch in `main.py` kennt `rate_transitions.py`, `audit_candidate_set.py` und `hoertest_server.py`; er kennt `prepare_dj_blind_test.py` nicht als `--hpg-tool`. Nach Service-Extraktion braucht lokale GUI-Erstellung keinen Tool-Dispatch. Optionaler Remote-Server braucht einen getesteten App-eigenen Startpfad. CLI-Dispatch kann für Diagnose/Fallback ergänzt werden, ist aber kein Ersatz für direkte Service-Integration.

**Verifikationsbefehle:** gezielte Suiten je Aufgabe mit `venv312\Scripts\python.exe -m pytest <betroffene Testdateien> --tb=short -q --no-cov`; genau ein vollständiger Abschlusslauf `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`. Build-/Smoke-Befehl wird aus aktuellem Release-Skill/Buildskript ermittelt und in Aufgabe 1 der Matrix festgehalten; keine erfundene Build-Kommandos.

## Ergebnis der gründlichen Planprüfung (2026-09-27)

- **Korrigiert – native Verwendung:** vorher schlug der Plan als Kern nur Browserstart vor. Das hätte die eigentliche App weiterhin vom Zusatzwerkzeug/Webserver abhängig gelassen. Jetzt verlangt er natives Bewerten/Abspielen/Speichern/Fortsetzen; Server nur optional für Remote.
- **Korrigiert – Audit-Scope:** `audit_candidate_set.py` ist Kandidaten-spezifisch. Für Einzel/Dramaturgie sind eigene vorhandene Validatorverträge zu nutzen; nicht einen Audit für alle Modi vorspiegeln.
- **Korrigiert – Blindtest-Scope:** `prepare_dj_blind_test.py` erzeugt Session und getrennten Schlüssel, aber keine Bewertungs-, Entblindungs- oder Statistikpipeline. Import/Auswertung ist explizit separater, noch nicht beauftragter Umfang.
- **Korrigiert – Lernbegriff:** Einzel-Fit produziert `gewichte.json`, Kandidaten-Fit kann gated `candidate_preferences` aktivieren. Beides ist Präferenzkalibrierung, kein Audio-LLM-Training. Aktive Übernahme muss an tatsächlicher Ausgabe und nachfolgendem Ranking-Reload belegt werden.
- **Korrigiert – Nachweis:** leere CLI-stdout-/mtime-Heuristik ist kein gültiger Fit-Erfolgsbeleg. UI muss strukturierte Berichte/Dateien und tatsächlichen Override-Zustand lesen.
- **Korrigiert – Launcher:** rekursive Laufwerkssuche ist kein bestehendes Launcher-Verhalten; nur explizit gewählte Roots durchsuchen und fremde Prozesse nie beenden.
- **Verbleibend für Umsetzung:** Aufgabe 1 muss für jede Parser-Option/Route konkrete App-Aktion und konkreten Testnamen dokumentieren; Implementierung darf nicht mit dem bisherigen 8-Test-Satz als Vollparitätsbeleg verwechselt werden.
- **Nicht destruktive Nachweise:** existierende Ziele, Satz-/Cache-Bindung, WAL, getrennte Blindtestschlüssel, fremder Portprozess und Fit ohne Zustimmung bleiben Tests.
- **Grenze:** geänderter Plan, keine Feature-Implementierung. Das aktuell sichtbare GUI-Feature deckt noch nicht die gesamte Werkzeugparität.
