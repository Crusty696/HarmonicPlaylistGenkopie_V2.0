# HPG: Arbeitsregeln für Agenten

Diese Datei ergänzt README, Code und Fach-Dokumentation um verbindliche
Arbeitsregeln. Aktuelle Nutzeranweisungen bestimmen den Auftrag.

## Einstieg und Quellen

- Aktuellen Auftrag und [Projektwissen](docs/PROJECT_KNOWLEDGE.md) lesen.
  Vor nichttrivialen Änderungen [hpg-orientation](.agents/skills/hpg-orientation/SKILL.md)
  und den passenden Fachskill laden; weitere Quellen aufgabenbezogen lesen.
  Codex-Skills: `.agents/skills/`, Claude-Spiegel: `.claude/skills/`;
  Fachrollen: `.agents/agents/`. Die Invarianten betroffener Fachskills prüfen.
- Aussagen zur Implementierung im aktuellen Code, Laufzeitaussagen im passenden
  datierten Rohbeleg prüfen. Dateinamen, Statusdokumente und Erinnerungen sind
  kein Funktionsnachweis. Ungeprüftes als ungeprüft kennzeichnen.
- Historische Session-Aufträge nicht automatisch fortsetzen. Vor dem Entfernen
  alter Quellen relevante Erkenntnisse erhalten; keine parallelen Statuskopien.
  Architektur, Strategien, Versionen und Pipeline im Code bzw. Fachskill nachlesen,
  statt sie hier als veraltbare Zweitbeschreibung zu führen.

## Schutz und Umfang

- Nur den beauftragten Bereich ändern. Vorhandene fremde Änderungen bewahren.
  `Claude-Autopilot-v5/`, `Claude-Autopilot-v6/` und `Claude-Autopilot-v6.zip`
  sind Benutzerartefakte: niemals ändern, verschieben, stagen oder committen.
- Originalmusik ausschließlich am Quellort lesen und abspielen. Niemals kopieren,
  verschieben, umbenennen, löschen oder in Projekt, Git oder Sicherungen aufnehmen.
- Produktivcache nicht für Tests verändern oder löschen; Testzustand isolieren.
  Bestehende Cache-, Datenbank-, Lock- und Coverage-Dateien sind geschützt,
  insbesondere `hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`, `*.coverage`.
- Unbekannte Vocals allein dürfen kein Paar sperren.
- Bereits autorisierte sichere Schritte autonom ausführen. Keine zusätzlichen
  Routinefreigaben; notwendige Sicherheits-/Scope-Rückfragen und unabhängige
  Prüfungen bleiben bestehen.

## Umsetzung und unabhängige Prüfung

- Unabhängige, schreibgeschützte Wächterprüfungen nach
  [hpg-waechter](.agents/agents/hpg-waechter.md) erfolgen auf Anforderung.
  Es gibt keine verpflichtende Vorab- oder Commitprüfung; ein früheres
  Wächterurteil ist keine Voraussetzung für Umsetzung oder Commit.
- Parallel nur unabhängige Recherche, Reviews oder Testvorbereitung. Ein
  Verantwortlicher je teurem Lauf; keine doppelten Test-/Build-Aufträge und
  niemals zwei vollständige pytest-Läufe gleichzeitig. Während codegebundener
  Langtests die relevanten Dateien einfrieren.
- Projektinterpreter `venv312\Scripts\python.exe` verwenden: Python 3.12,
  Mindestversion gemäß `hpg_core/app_metadata.py`, kein Wechsel auf 3.13+.
- Einrückung der jeweiligen Datei fortsetzen, keine Tabs; Kommentare auf Deutsch.
  UI-Updates nur im Main-Thread. Skripte in `tools/` müssen den Projekt-Parent
  in `sys.path` aufnehmen.

## Nachweise und Testaufwand

- Anforderungen in prüfbare Akzeptanzkriterien und passende Regressionen übersetzen.
  Reproduzierbaren Fehler vor dem Fix und denselben Test danach nachweisen.
  Erwartungen nicht abschwächen, außer bei ausdrücklich geändertem Nutzervertrag
  mit dokumentierter Begründung. Ist Reproduktion nicht möglich, Diagnosebeleg und Grenze nennen;
  kein RED/GREEN erfinden.
- Vor Wiederholungen vorhandene Ergebnisse anhand relevanter Quell-/Test-/Build-
  Hashes, Eingaben, Umgebung, Befehl, Ergebnis und Einschränkungen prüfen.
  Gültige Nachweise weiterverwenden. Jeder neue Lauf braucht einen konkreten
  Grund (Änderung, Fehler oder Nachweislücke) und den kleinsten geeigneten Umfang;
  beides vorher festhalten. Neuer Chat, Zusammenfassung oder Statusbericht
  allein rechtfertigen keine Wiederholung. Kosten, Tokens und Zeit berücksichtigen.
- Testerwartungen vor teuren Läufen gegen den Vertrag prüfen: Ein neuer Score
  muss die Reihenfolge nicht ändern. Reine Dokumentationsänderungen erfordern
  keinen Build, Volltest oder Audioanalyselauf. Bei ausschließlich korrigierten
  veralteten Erwartungen und unverändertem Produktcode, Abhängigkeiten und
  relevanter Umgebung genügen betroffene Nachtests; weiterreichende Fixture-
  oder Teständerungen brauchen entsprechend breitere Prüfung.
- Erforderlicher Abschluss-Volltest:
  `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`.
  `pytest.ini` ist maßgeblich für Parallelisierung und Coverage; `--no-cov`
  nur im lokalen Entwicklungszyklus. Die obigen begründeten Ausnahmen von
  Wiederholungen bleiben wirksam. Gezielte Nachtests getrennt vom Volllauf
  und dessen Coverage ausweisen; einen fehlgeschlagenen Volllauf nie nachträglich
  als bestanden darstellen.
- Betroffenen nativen Ablauf mit Originaltracks nachweisen: auswählen, frisch
  analysieren, Paare bewerten, Playlist erstellen und Ergebnisse direkt in der
  App verwenden. Werkzeug-, DSP- oder Mock-Tests ersetzen das nicht. Frische
  Analyse und Cache-Wiederverwendung getrennt prüfen; fehlende Schritte nennen.
- Status getrennt melden: implementiert, automatisch getestet, vollständiger
  nativer Originaltrack-Ablauf, musikalisch bewertet. Absicht, Laufzeitbeobachtung
  und ausgeführten Nachweis trennen; kein Status beweist den nächsten.
  Kein Abschluss ohne passenden Test-/Prüfbeleg, keine pauschale Fehlerfreiheit
  oder ungeprüfte musikalische Optimalität zusagen.
- EXE erst nach Funktionsnachweisen bauen. Genau die auszuliefernde/gestartete
  Version prüfen und über absoluten EXE-Pfad plus SHA-256 zuordnen. Quellcode-Test,
  Build-Erfolg und EXE-Lauf sind getrennte Belege; historische Tests keine Abnahme.
