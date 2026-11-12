# HPG Entwicklungsstand

**Stand:** 12.11.2026
**Branch:** `codex/gesamtrefaktorierung`
**Ausgangsrevision der heutigen Artefaktprüfung:** `ead15b2dcb4b663fda68aab91ad874c135e533b7` (lokaler und entfernter Branch gleich)

## Aktuelle Vollsuite

- Der serielle Standardlauf nach Korrektur der zwei veralteten UI-Textassertions
  bestand **6.718 Tests; 46 `slow`-Tests abgewählt; 0 Fehler in 2.337,11 s
  (38:57)** mit `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
  -n 0 --no-cov`. Die reparierten Rekordbox-/Genre-Tooltip-Tests sind im
  Gesamtstand enthalten. Der vorherige Lauf hatte 6.716 bestanden und genau
  diese zwei veralteten Wortlautassertions beanstandet. Coverage wurde bei
  diesem seriellen Nachweis nicht berechnet; der konfigurierte Standardlauf
  mit Coverage/xdist ist davon getrennt.

## Geprüfte Fortschritte

- Der CLI-Einzel-Fit publizierte `gewichte.json` bisher mit permissivem
  `json.dumps` und direktem `write_text`: nicht-endliche JSON-Zahlen waren
  möglich und ein abgebrochener Schreibvorgang konnte eine Teil-Datei lassen.
  Der neue Create-only-Writer serialisiert mit `allow_nan=False`, fsync und
  atomarem Hardlink; vorhandene Ausgaben bleiben unverändert. Der bestehende
  CLI/native Rundlauf plus No-clobber- und NaN-Regressionen bestanden **3/3 in
  0,54 s** (`venv312`, `-n 0 --no-cov`).
- Ein gemeinsamer Artefakt-Vertragslauf bestand **18/18 in 10,48 s** (`venv312`, `-n 0 --no-cov`): vier Producer-Modi sowie Single-/Kandidaten-/Dreinoten-Fit, Proposal-Rundlauf, Kandidaten-Audit, Ratingsreport und lokale/portable Blindtest-Referenzen. Synthetische Quellen; kein Coverage-, Slow-Test-, Originalmusik- oder manueller Usability-Nachweis.
- Der gespeicherte In-App-Übergangsratings-Satz wurde zusätzlich geprüft: `test_ram_rating_persists_metadata_reopens_and_rejects_changed_source` bestand **1/1 in 6,15 s**; Persistenz, Wiederöffnung und Ablehnung veränderter Quelldaten sind abgedeckt.
- Der private Snapshot-Vertrag `association.json` ist nun für beide Producerformen explizit geprüft: Einquellen-v1 mit exakten Rootfeldern und Wiederöffnung bestand **1/1 in 0,22 s**, Mehrquellen-v2 mit Schema-/Roundtrip **1/1 in 0,24 s**; für v2 bestehen zusätzlich Strict-Negativtests.
- Der GUI-Button „Bericht / Vorschlag speichern“ wurde auf dem aktuellen Checkout verifiziert: `test_csv_single_real_fit_without_cache_audio_preserves_old_output` bestand **2/2 in 7,21 s**. Beide Varianten laden den exportierten JSON-Vorschlag zurück und validieren ihn; eine vorhandene `gewichte.json` bleibt unverändert. Synthetische CSV, keine Audioanalyse.
- Der aktuelle Frozen-Build wurde gemäß Task-7-Methode isoliert unter
  `%TEMP%\hpg-final-build-8db92de2cc2f42cab91a6e4e869efa58` erstellt; bestehende
  `build/`, `dist/` und Root-EXE wurden nicht angetastet. Die EXE bestand den
  isolierten `--hpg-native-smoke` mit Exitcode 0 und Report `ok=true`: native
  Imports/Formulare, Spawn-Initializer, Cache-Reaping/Cleanup, RAM-Render und
  isolierter Fit-Ablehnungsfall. EXE-SHA256:
  `23F3BDE1A3667F9A3CEE344720EC09EC344EFF73184B6C62F1AA3D3F825B13F1`.
  Das belegt den Frozen-Smoke, nicht die GUI-Usability oder Gesamt-App-Abnahme.
- Der aktuelle Checkout enthält `Start_Hoertest.bat`,
  `tools/hoertest_launcher.py` und `tests/test_hoertest_launcher.py`.
  Eine widersprechende historische Inventaraussage im Hörtest-Plan wurde
  berichtigt; die CLI-/GUI-Matrix beschreibt den Launcher bereits als
  optionalen Kompatibilitätsweg.
- Der Vier-Modi-Producervergleich prüft jetzt zusätzlich das exakte
  Dateiinventar und CSV-Spaltenfolgen der CLI-Ausgabe und des nativen
  Quellsatzes für Einzel, Kandidaten, Dreinoten und Dramaturgie. Der gezielte
  Lauf bestand **4/4 in 5,70 s** mit `-n 0 --no-cov`; die Fixtures sind
  synthetisch. Eine gemeinsame Golden-Master-Rundreise aller JSON-Artefakte
  bleibt offen.
- Die erfolgreiche CLI-Publikation eines Kandidaten-Auditreports hat jetzt
  einen direkten Vertragstest für exakte Root- und Satzbindungsfelder.
  `test_vollstaendiger_stretch_fall_ist_read_only` bestand **1/1 in 0,48 s**.
  Der Test nutzt synthetische Cache-/Trackdaten und kopiert Fixture-Render;
  Produktionsranking und Renderer sind damit nicht neu qualifiziert.
- Eine gezielte JSON-Schema-Auswahl für Fit, Proposal, Blindtest, Quellmanifest
  und Dramaturgie-Kontext bestand **20/20 in 9,43 s** (`-n 0 --no-cov`).
  Zusammen mit den Producer- und Audit-Tests bleiben die Gesamt-Golden-Master-
  Rundreise und JSON-Versionen außerhalb dieser Auswahl offen. Die serielle Standard-Testauswahl bestand am 12.11.2026 mit 6.718 Tests; 46 `slow`-Tests waren abgewählt und Coverage wurde nicht berechnet.
- Kandidatenmanifest und Reihenfolge sind zusätzlich mit Producer-Rootschema,
  gebundenem Seed/Shuffle, kanonischer CSV-Reihenfolge und Duplicate-Key-
  Abweisung abgedeckt; gezielter Lauf **8/8 in 0,70 s** (`-n 0 --no-cov`).
- Das In-App-Rating-Artefakt `transition_ratings.json` ist jetzt mit exakten
  Producer-Rootfeldern und Version `hpg_transition_ratings_v1` geprüft. Der
  separate Diagnose-CLI-Test validiert JSON-Ausgabe, Dateihash, Read-only-
  Verhalten und Ablehnung zusätzlicher Felder. Beide Tests bestanden **2/2 in
  4,93 s** (`venv312`; xdist-Standardeinstellung, acht Worker).
- Beim CLI-Einlesen wurde ein realer Strict-JSON-Fehler gefunden und behoben:
  `_lade_json_strikt` akzeptierte doppelte Feldnamen. Der Loader weist diese
  jetzt mit `object_pairs_hook` ab; Producer- und Report-Tests bestehen samt
  Duplikatfall **2/2 in 4,73 s** (`venv312`; xdist-Standardeinstellung, acht Worker).
- Das Hörtest-Artefaktinventar wurde im Umsetzungsplan getrennt nach
  Prepare-, Fit-, Audit- und Blindtest-Ausgaben ergänzt. Eine gemeinsame
  versionsübergreifende Schema-Fixture aller JSON-Artefakte bleibt offen.
- Der frühere Native-Smoke-`ok=true` im Task-6-Abschnitt ist ausdrücklich als Nachweis eines damaligen Quellstands markiert. Der spätere Build hatte einen abweichenden Algorithmus-Fingerprint; dieser Stand wurde inzwischen isoliert neu gebaut und per Native-Smoke geprüft (Nachweis oben).
- Statische Packaging-Verdrahtung geprüft: `main.py` dispatcht
  `--hpg-native-smoke` an `hpg_core.hearing_smoke.run`; der Smoke importiert
  die Hearing-Services. Diese referenzieren die benötigten Module unter
  `tools/`; `HPG.spec` nimmt `tools/rate_transitions.py` und die
  `hpg_core`-Quellen in die Builddaten auf. Das zeigt Quell-/Smoke-Abdeckung,
  beweist für sich weder Frozen-Importauflösung noch GUI-Laufzeit. Der isolierte aktuelle Frozen-Build und Native-Smoke sind oben nachgewiesen; die GUI-Laufzeit bleibt offen.

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

- Die serielle Standard-Testauswahl bestand am 12.11.2026 mit 6.718 Tests; 46 `slow`-Tests waren abgewählt. Coverage wurde nicht berechnet. Konfigurierter Coverage-Gate und Slow-Auswahl sind daher nicht nachgewiesen.
- Der Frozen-Build und Native-Smoke sind am 12.11.2026 in isoliertem Scratch nachgewiesen. Das ist kein sichtbarer GUI-Smoke und ersetzt nicht die manuelle Usability-Abnahme.
- Eine gezielte manuelle Frozen-GUI-Prüfung vom 11.11. deckt den Kandidaten-
  Hörtest ab: isolierten Satz öffnen, beide Varianten im RAM rendern und
  abspielen, eine Note speichern und nach erneutem Laden wiederfinden. Die
  temporäre Testnote wurde entfernt. Nicht abgedeckt sind alle vier Satzmodi,
  manuelle Pause-/Fehlerpfade, ein vollständiger Fit-/Exportablauf und eine
  musikalische Abnahme mit Originalmusik. Der vollständige manuelle
  Abnahmepunkt bleibt daher offen.
- Die automatisierten Artefaktverträge sind jetzt über getrennte fokussierte
  Producer-, Fit-, Rating- und Blindtest-Worker-Rundreisen abgedeckt. Einzel-
  und Kandidaten-Fitberichte werden zwischen CLI und nativem Pfad verglichen;
  normale Kandidaten- und Dreinoten-Fits laufen mit echter CLI-Bindungsprüfung.
  Die Fixtures sind synthetisch und ersetzen keinen vollständigen Lauf, keine
  reale Audioabnahme und keinen manuellen Test aller GUI-Pfade.
- Zwei zusätzliche Kandidatenpfade schließen einen Teil dieser Lücke: Die
  Tests für normalen Kandidaten- und Dreinoten-Fit erzeugen jeweils einen
  persistenten CLI-Auditbericht, lassen den CLI-Fit mit unveränderter
  Binding-Validierung laufen und vergleichen den publizierten JSON-Bericht mit
  dem nativen Fit-Ergebnis. Der gezielte Lauf bestand **2/2** am 12.11.2026.
  Quellen, Cache und Renderer sind synthetisch.
- Der Einzel-Fit-Rundlauf ist zusätzlich geschlossen:
  `test_single_fit_cli_output_matches_native_report_and_roundtrips` vergleicht
  das echte CLI-`gewichte.json` mit dem nativen Einzel-Fit-Bericht und validiert
  den wieder eingelesenen Vorschlag; **1/1** gezielt bestanden. Fixture nutzt
  synthetische CSVs ohne Cache und Audiodateien.
- Der Dreinoten-GUI-Fitpfad wurde als echte E2E-Folge ergänzt:
  synthetischer Producer, menschliche Testnoten, GUI-Fitworker, RAM-Audit und
  gebundener Fitbericht bestanden **1/1** am 12.11.2026 (13,71 s). Bei einem
  unabhängigen Paar bleibt das Übernahme-Gate korrekt geschlossen; der Test
  belegt keine Gewichtsübernahme. Zusammen mit dem Kandidaten-Apply-E2E, dem
  Einzel-Fit-Draft und dem Vier-Modi-Resume sind die automatisierten
  Teilpfade einzeln belegt; der Dreinoten-Applypfad ist jetzt im GUI-Vertrag getestet, aber sein positives Gate ist injiziert; die numerische Gateberechnung ist getrennt getestet. Laut Matrix ist Dramaturgie-Fit bewusst nicht vorgesehen.
- Der Dreinoten-Applypfad besteht jetzt gezielt **1/1 in 8,55 s**:
  echter synthetischer Producer, RAM-Audit/Fit, Ergebnisdialog, zweite
  Bestätigung, Apply-Worker und Präferenzpersistenz/-Reload. Das positive
  Gate-Update ist injiziert. Numerische positive/negative Gatefälle bestanden
  separat **4/4 in 2,26 s**. Keine echte statistische oder musikalische Gateaussage.
- Der unabhängige Abschlussreview prüfte read-only alle vier Dateien seit `ead15b2`;
  zwei überzogene Plan-Haken wurden korrigiert und nachgeprüft. Dramaturgie-Fit ist
  bewusst ausgeschlossen. Der Apply-Vertrag nutzt injizierte Gatewerte; eine
  durchgehend numerisch bestandene Gate-bis-Apply-Folge bleibt offen.
- Die statische VERITAS-Prüfung ersetzt keine dynamischen Laufzeit-, Audio- oder
  Build-Nachweise. Der Wissens-Sync wurde nicht angewandt: Sein Dry-Run plante
  externe Wiki-Änderungen für einen verworfenen Einzelpass-Befund.

## Arbeitsbaum und Veröffentlichung

- Neun bereits lokale Änderungen bleiben unangetastet und uncommittet:
  `.agents/skills/hpg-veritas/references/active-learnings.md`, die Löschungen
  von `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, drei HTML-Dokumenten und zwei
  historischen Memory-Dateien.
- In diesem Fortsetzungsschritt wurde kein Produktcode geändert. Commit
  `c90c5e4a` ergänzt Inventar-Assertions im Producer-Paritätstest und
  korrigiert/erweitert den Hörtest-Plan. AST-Parse und `git diff --check`
  bestanden; `pytest --collect-only --no-cov` sammelte **4/4** Varianten in
  0,10 s. Testkörper und Laufzeitverhalten wurden nicht ausgeführt.
- Der Dreinoten-GUI-Fitworker wurde in `0c88d8eb` ergänzt; `ccd1c929` klärte den Build-Status, `7bb79cca` öffnete überzogene Artefakt-/E2E-Haken und `b7742ccc` benannte den noch offenen Dreinoten-Apply-Nachweis. Vor diesem Statusabgleich stimmten lokaler und entfernter Branch auf `b7742ccc` überein.
- Die Folgecommits 1d019e64 und 6e390ac9 synchronisierten Status und unabhängige Prüfung; 44fdfa92 ergänzt den Dreinoten-Apply-Test. Nach dessen Push stimmten lokaler und entfernter Branch bei 44fdfa92 überein.
- `368d3076` dokumentierte den Apply-Push; `c90c5e4a` ergänzt das Artefaktinventar. `git ls-remote` bestätigte danach lokal und remote `c90c5e4abc3fed76c7b24ec17ccf97d2dd5d160b`.
- `ad2026f3` ergänzt die CSV-Spaltenfolgen, `c7abf2d` dokumentiert die statische Packaging-Prüfung. Vor dieser Statuskorrektur bestätigte `git ls-remote` lokal und remote `c7abf2d1191a54bd52e5d6b255af1d961be0592c`.
- Der Producer-Contract-Test lief anschließend seriell **4/4 in 5,70 s**; er prüft exaktes Dateiinventar, CSV-Spaltenfolgen und bestehende CLI-/native Producer-Parität. Der Test ist synthetisch und ersetzt keine Vollsuite oder Originalmusik-Abnahme.
- Der Audit-Erfolgsreport-Contract lief **1/1 in 0,48 s**; geändert wurde nur der Testvertrag, kein Produktcode.
- Die ausgewählte Fit-/Proposal-/Blindtest-/Manifest-Schemafolge lief **20/20 in 9,43 s**. Alle Testdaten sind synthetisch; kein Originalmusikpfad wurde benutzt.
- Kandidatenmanifest-/Reihenfolge-Regressionsfolge bestand **8/8 in 0,70 s**; kein Produktcode geändert.
- Der Ratings-Producer-/Diagnose-CLI-Vertrag bestand **2/2 in 4,93 s** mit
  Pytests xdist-Standardeinstellung (acht Worker). Die
  Planinventur wurde um das Artefakt ergänzt; Commits `112c449f` und `85983c9`
  sind auf `codex/gesamtrefaktorierung` gepusht und der Remote entsprach zuletzt
  `85983c98bc5bb0685a84b41300c68e45b00e6dce`.
- `_lade_json_strikt` wird zusätzlich für Kandidaten-/Dramaturgiemanifeste und
  Auditberichte verwendet; deren Lesewege profitieren ebenfalls von der
  Duplikatschlüssel-Abweisung. Bugfix-Commit `03a230d5` ist gepusht; lokaler
  und entfernter Branch stehen auf `03a230d5f62c0b0fe0be30564cf6c14572a08e12`.
- Kandidaten-Fit-Regressionsfälle prüfen nun beide kritischen Leser (Manifest
  und Audit-Report) mit doppelten Feldern. Die zwei synthetischen Fälle
  bestanden seriell **2/2 in 0,35 s** (`-n 0 --no-cov`).
- Der separate CLI-Kandidaten-Auditor hatte dieselbe Parserlücke in eigenen
  Lesern für `kandidaten_manifest.json` und `reihenfolge.json`. Beide lesen
  jetzt mit Duplicate-Key-Hook; direkte Fail-closed Regressionen bestanden
  seriell **2/2 in 0,36 s** (`-n 0 --no-cov`).
- Der lokale Hörtest-Server wies doppelte JSON-Schlüssel in einem POST bisher
  nicht ab; zwei `pair_id`-Felder konnten dadurch die bewertete Zeile
  verschieben. Dramaturgie-Manifest und HTTP-POST verwenden jetzt ebenfalls
  den Duplikat-Hook. CSV-Unverändertheit nach POST-Ablehnung und Manifestfehler
  bestanden **2/2 in 0,72 s** (`-n 0 --no-cov`).
- Die native Kandidaten-Hörvorschau las `reihenfolge.json` noch permissiv.
  Sie nutzt nun `hearing_sources.strict_json_bytes`; doppelter Paar-Schlüssel
  wird abgewiesen und die gültige Reihenfolge bleibt erhalten. Regression und
  Normalfall bestanden seriell **2/2 in 0,56 s** (`-n 0 --no-cov`).
- Das GUI-Auswahlprofil nutzte ebenfalls Standard-JSON-Parsing. Es wird jetzt
  mit `hearing_sources.strict_json_bytes` gelesen. Doppelte Felder und andere
  ungültige Profile werden vor Workerstart abgewiesen (**5/5 in 0,39 s**),
  gültige Kandidatenprofile funktionieren weiter (**1/1 in 0,16 s**); seriell
  mit `-n 0 --no-cov` geprüft.
- Der als strikt bezeichnete Track-Cache-JSON-Leser verwirft doppelte Felder
  jetzt ebenfalls. Die Cache-Vertragsregression mit manipuliertem Duplikat-
  Datensatz bestand seriell **1/1 in 0,59 s** (`-n 0 --no-cov`).
- Persistierte Kandidatengewichte und Mixpunkt-Auswahlen verwenden nun
  Duplicate-Key-Prüfung: lesender Fallback protokolliert mehrdeutige Dateien,
  atomare Schreibpfade lehnen sie ohne Änderung ab. Negativfälle bestanden
  **7/7 in 0,50 s**; gültige Rundreisen **2/2 in 0,10 s** (`-n 0 --no-cov`).
- Playlist-Toleranz-Overrides verwenden jetzt denselben Fail-closed-Vertrag.
  Mehrdeutige Dateien fallen lesend auf Genre-Defaults zurück und bleiben bei
  Schreibversuchen unverändert; gültiger Override bleibt funktionsfähig.
  Gezielte Fälle bestanden seriell **5/5 in 0,18 s** (`-n 0 --no-cov`).

## Belege

- VERITAS-Pässe und Verifikator:
  `tools/audit/runs/veritas-app-completion-2026-11-12/`
- Tempo-Implementierung: `hpg_core/tempo_refinement.py`, `hpg_core/analysis.py`
- Gezielte Regressionen: `tests/test_tempo_refinement.py`,
  `tests/test_analysis_tempo_refinement.py`
- Projektweite Anforderungen und Nachweisgrenzen: `docs/PROJECT_KNOWLEDGE.md`
