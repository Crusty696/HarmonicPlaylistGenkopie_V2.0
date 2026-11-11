# HPG Entwicklungsstand

**Stand:** 12.11.2026
**Branch:** `codex/gesamtrefaktorierung`
**Ausgangsrevision vor dieser Fortsetzung:** `e313c7cb3cdba860cded64151fc0b11956a192fc` (lokaler und entfernter Branch gleich)

## Geprüfte Fortschritte

- Drei unabhängige, rein statische VERITAS-Pässe über Anwendung, Analyse,
  Playlist, GUI/Worker, Export, Build, Installer, Tests, CI und aktive
  Projektdokumentation sind abgeschlossen. Kein Produktfehler wurde in zwei
  Pässen bestätigt.
- Pass 3 meldete einen Installer-Namenskonflikt. Der getrennte Verifikator
  verwarf ihn: Der Release-Workflow stoppt vor dem Installer-Build, wenn der
  Tag nicht `APP_VERSION` entspricht. Der aktuelle Stand `3.7.2` ist in
  `hpg_core/app_metadata.py`, `installer.iss`, `build_installer.bat` und
  `tests/test_release_metadata.py` konsistent. Der Einzelpass-Befund bleibt
  unbestätigt und ist kein nachgewiesener Fehler.
- Die früher offene Produktintegration der Feintempo-Schätzung ist im aktuellen
  Code vorhanden. `_refine_audio_tempo` setzt im Vollpfad den Kandidaten erst
  nach Bestätigung in drei getrennten Audiofenstern ein. Beide gezielten
  Module `tests/test_tempo_refinement.py` und
  `tests/test_analysis_tempo_refinement.py` bestanden mit **52/52 Tests** in
  86,15 s. Die Fixtures sind synthetisch; daraus folgt keine Qualitätsaussage
  für Originalmusik.
- Das KI-Hirn wurde vor der Arbeit abgefragt. Eine veraltete Erinnerung über
  fehlende Tempo-Integration wurde nach Code- und Testabgleich berichtigt.
- Aktive Arbeitsdateien und die Deep-Analysis-Spezifikation verwiesen noch auf
  die entfernte `AGENTS.md`. Diese Verweise zeigen jetzt auf
  `docs/PROJECT_KNOWLEDGE.md`; datierte historische Übergaben bleiben erhalten.

## Fertigstellung noch nicht belegt

- Die letzte dokumentierte Vollsuite mit 6.679 bestandenen Tests liegt vor den
  jüngsten Änderungen. Ein aktueller Vollsuite-Lauf fehlt.
- Ein Frozen-Build aus genau diesem aktuellen Quellstand und dessen sichtbarer
  GUI-Smoke fehlen.
- Eine gezielte manuelle Frozen-GUI-Prüfung vom 11.11. deckt den Kandidaten-
  Hörtest ab: isolierten Satz öffnen, beide Varianten im RAM rendern und
  abspielen, eine Note speichern und nach erneutem Laden wiederfinden. Die
  temporäre Testnote wurde entfernt. Nicht abgedeckt sind alle vier Satzmodi,
  manuelle Pause-/Fehlerpfade, ein vollständiger Fit-/Exportablauf und eine
  musikalische Abnahme mit Originalmusik. Der vollständige manuelle
  Abnahmepunkt bleibt daher offen.
- Der aktuelle Hörtest-Plan nennt als verbleibenden maschinenprüfbaren Punkt
  einen Golden-Master-Lauf mit unveränderter CLI-Bindungsprüfung und allen
  publizierten CSV-/JSON-Schemas. Die vorhandenen Producer-/Sitzungs- und
  Fit-Rundreisen belegen Teilverträge, nicht diesen Gesamtvertrag.
- Zwei zusätzliche Kandidatenpfade schließen einen Teil dieser Lücke: Die
  Tests für normalen Kandidaten- und Dreinoten-Fit erzeugen jeweils einen
  persistenten CLI-Auditbericht, lassen den CLI-Fit mit unveränderter
  Binding-Validierung laufen und vergleichen den publizierten JSON-Bericht mit
  dem nativen Fit-Ergebnis. Der gezielte Lauf bestand **2/2** am 12.11.2026.
  Quellen, Cache und Renderer sind synthetisch; andere Artefakt-Schemas und die
  vollständige Golden-Master-Matrix bleiben offen.
- Der Einzel-Fit-Rundlauf ist zusätzlich geschlossen:
  `test_single_fit_cli_output_matches_native_report_and_roundtrips` vergleicht
  das echte CLI-`gewichte.json` mit dem nativen Einzel-Fit-Bericht und validiert
  den wieder eingelesenen Vorschlag; **1/1** gezielt bestanden. Fixture nutzt
  synthetische CSVs ohne Cache und Audiodateien.
- Die statische VERITAS-Prüfung ersetzt keine dynamischen Laufzeit-, Audio- oder
  Build-Nachweise. Der Wissens-Sync wurde nicht angewandt: Sein Dry-Run plante
  externe Wiki-Änderungen für einen verworfenen Einzelpass-Befund.

## Arbeitsbaum und Veröffentlichung

- Neun bereits lokale Änderungen bleiben unangetastet und uncommittet:
  `.agents/skills/hpg-veritas/references/active-learnings.md`, die Löschungen
  von `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, drei HTML-Dokumenten und zwei
  historischen Memory-Dateien.
- In diesem Fortsetzungsschritt wurde kein Produktcode geändert.
- Der Statusbericht wurde als `a3a22816` committed und gepusht. Die anschließende
  Referenzbereinigung wird als eigener Dokumentationsschritt veröffentlicht.

## Belege

- VERITAS-Pässe und Verifikator:
  `tools/audit/runs/veritas-app-completion-2026-11-12/`
- Tempo-Implementierung: `hpg_core/tempo_refinement.py`, `hpg_core/analysis.py`
- Gezielte Regressionen: `tests/test_tempo_refinement.py`,
  `tests/test_analysis_tempo_refinement.py`
- Projektweite Anforderungen und Nachweisgrenzen: `docs/PROJECT_KNOWLEDGE.md`
