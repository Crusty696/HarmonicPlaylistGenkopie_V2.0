# Native Hörtest-Funktionen – Prüfstand 2026-10-04

## Aktueller Nachweisstand und Wiederverwendung

Der Standard-Gesamtlauf vom 2026-10-04 (Start 07:41 Uhr) endete nach
1.012,86 s mit **Exit 1: 4.760 bestanden, zwei fehlgeschlagen**. Gemessene
Coverage: **85,36 %**, Mindestgrenze 70 % erfüllt. Befehl:
`venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`.
Die bestehende pytest-Konfiguration wählt `slow` ab; die separaten
Originalquellen-Proben sind unten dokumentiert.

Beide Fehler betreffen nach genehmigten Produktänderungen veraltete
Testerwartungen: `test_config_imports` erwartet noch 60 statt 180 Sekunden;
`test_refresh_resets_cancelled_before_ranking_but_preserves_active_run[cancelled]`
erwartet den separat gespeicherten KI-Schalter `ai_enabled=False` noch nicht.
Die Korrektur ändert ausschließlich diese Erwartungen samt Begründung.
State-, Ownership- und fachliche Prüfungen bleiben erhalten. Genau die zwei
fehlgeschlagenen Node-IDs wurden anschließend mit `-n 0 --no-cov --tb=short -q`
nachgeprüft: **zwei bestanden in 0,56 s, Exit 0**. Es gab keinen erneuten
Gesamtlauf und keine Neumessung der Coverage. Diese Ergebnisse ergänzen den
oben dokumentierten fehlgeschlagenen Gesamtlauf.

Auch die sieben nativen End-to-End-Fälle sind im Standardlauf bestanden.
Der längste davon, `test_real_producer_audit_native_fit_confirm_apply_actual_ranking`,
dauerte 237,38 s. Er belegt Vorbereitung, Audit, echten Fit, Bestätigung,
Speicherung, Reload und Neuberechnung mit synthetischen Bewertungen.
Scores ändern sich; die Trackreihenfolge bleibt gleich. Die Audioquellen
dieser Fixture sind synthetisch und mehrfach hart verlinkt. Das ist kein
Training mit Nutzerbewertungen und kein Nachweis musikalischer Qualität.

Nach Nutzerauftrag werden die 4.760 bestandenen unveränderten Fälle sowie
gültige Originalanalysen und Build-Proben weiterverwendet. Diese reine
Test-/Dokumentationskorrektur löst keinen neuen Gesamt-, Audio- oder Buildlauf
aus. Der fehlgeschlagene Gesamtlauf bleibt als solcher dokumentiert;
gezielte Nachtests werden separat ergänzt. Referenzbindungen:

- Algorithmus, 47 Dateien: `f6e5948204e1aac630d9ad3e709eeccbdf85c87f64a3812211e4dc71b3c3b8a9`.
- `main.py`: `d564eb276f421c7269213bcb442593bbab95b36482c34578d2ae25478328b010`.
- `HPG.spec`: `069d060ff3539ee3d9599803e79a05a1e8383b03c287da48c354aed78f01ba5a`.
- Kandidaten-EXE: `07bbb91df0a74b8c457156ab1de368b5c9b8496d0528055c8a2e8fc1583aa3d4`;
  absoluter Pfad und bereits ausgeführter Frozen-Smoke unten.

Für neue relevante Änderungen müssen die tatsächlich betroffenen Nachweise
erneuert werden. Der Original-Playlistbefund bleibt offen: drei geplante
und 22 ungeplante Grenzen, keine vollständige musikalische Freigabe.

Die normale EXE wurde am 2026-10-04 anschließend tatsächlich aktualisiert:
`C:\Users\david\Documents\HarmonicPlaylistGenerator_V2.0\HarmonicPlaylistGenerator.exe`.
Ihr vom Hauptagenten nachgelesener SHA-256 stimmt mit dem oben genannten,
bereits getesteten Kandidaten überein; Größe 178.659.892 Bytes. Ein weiterer
Build oder Smoke-Lauf war für die byteidentische Veröffentlichung nicht
erforderlich. Die normale GUI wurde dabei nicht gestartet.
Die alte EXE bleibt im bereits vorhandenen Backup erhalten:
`E:\99_Archiv_&_Backups\Projekt_Backups\HPG_Sicherung_2026-09-27\repositories\current-backup-apps-3.7.2\HarmonicPlaylistGenerator.exe`,
SHA-256 `aa34b1261d7113218caf8048d6b9818a82954d2d437f08b0d511a3e389fa0e26`.
Es entstand keine weitere Projekt- oder Musiksicherung. Die folgenden
historischen Prüfabschnitte beschreiben jeweils den damaligen Zwischenstand.

## Bedienung und Datenregel

Im bestehenden QUALITY-Bereich:

1. **Hörtest erstellen:** vorhandenen Analyse-Cache, neuen Satzordner und ausdrücklich erlaubte Original-Musikordner wählen. Die App verwendet die internen Produzenten und speichert Metadaten, Quell-Fingerprints und vollständige Übergangs-Spezifikationen, keine Musikdateien.
2. **Satz öffnen / Sätze, Fortschritt:** Einzelordner direkt öffnen oder einen Suchordner mit seinen unmittelbaren Unterordnern anzeigen. Die Liste zeigt Bewertungsfortschritt, keinen Auditnachweis. Öffnen prüft Metadaten und Originalquellen im Hintergrund.
3. **In der App bewerten:** Einzel, Kandidaten, Dreinoten-Pilot und Dramaturgie haben native Notenfelder. Änderungen werden sofort über denselben Rating-Service wie im optionalen Server gespeichert. Explizites Löschen und Kandidatenwahl bleiben getrennte Aktionen. Dramaturgie bewertet einzelne Übergänge und Gesamtverlauf getrennt.
4. **Höransicht:** nur lesen. Bereits existierende Legacy-Clips direkt abspielen; neue Quellen-Sätze rendern den spezifizierten Übergang bei Bedarf in RAM. Wechsel und Schließen geben Player/Buffer frei und beenden ausschließlich die eigenen Renderprozesse.
5. **Kandidaten-Replay prüfen / Bewertungen auswerten:** Cache und Fit-Optionen wählen. Die Berechnung erfolgt intern in einem isolierten Kindprozess. Kandidaten werden auf einem gebundenen temporären Snapshot neu gerendert und auditiert. Die temporären Übergänge werden nach nachgewiesenem Prozessende entfernt; eine fehlgeschlagene Bereinigung zeigt den verbliebenen eigenen Pfad an. Originaltracks werden nicht kopiert.
6. **Ergebnis:** tatsächliche Audit-/Fit-Zustände und Diagnose ansehen; Bericht nur als neue JSON-Datei außerhalb Musik/Satz/Systemzustand speichern. Einzel-Fit ergibt einen eigenen Vorschlag. Nur gatebestandene Kandidatenpräferenzen können nach gesonderter Bestätigung übernommen werden. Persistenz, Reload und anschließende Ranking-Neuberechnung sind getrennte Zustände. Keine automatische Freigabe roter Gates.
7. **A/B-Blindsatz vorbereiten:** vorhandenes Manifest mit HPG-/Baseline-Clipreferenzen, expliziten Quellordner, neuen Sessionordner und separaten privaten Schlüssel wählen. Neue App-Ausgabe ist `hpg_local_ui_blind_refs` v1: neutrale UI-IDs ohne Audiokopien. Originalpfade bleiben in Metadaten sichtbar; daher **nicht metadatenblind und nicht portabel**. Kein neuer Bewertungs-/Entblindungs-/Statistikworkflow. Die zwei Veröffentlichungen sind nicht laufwerksübergreifend atomar; ein Absturz kann einen verwaisten Schlüssel hinterlassen.
8. **Einzel-CSV auswerten:** separaten Legacy-Einzelordner wählen, ohne den geöffneten Satz oder dessen Cachezuordnung zu wechseln. Der bestehende Einzel-Fit benötigt nur die beiden CSV-Eingaben; Cache ist optional. Der `clips`-Unterbaum wird weder durchsucht noch gelesen, gehasht oder kopiert. Vorhandene `gewichte.json` wird gegen Änderungen gebunden, aber nicht als neues Ergebnis übernommen. Kandidaten und Quellenmanifeste behalten ihre strengeren Bindungen. Dieser Einstieg ersetzt keine fehlende Wiedergabequelle.

Originalmusik bleibt am Quellort. Neue App-Sätze brauchen weder Tool-CLI noch Browser für den Kernablauf. Der Browser bleibt ein optionaler Legacy-/Remote-Kompatibilitätsweg und unterstützt die neuen virtuellen Quellen-Clips nicht; die App weist darauf hin. Bestehende Legacy-CLI-Ausgaben bleiben kompatibel, werden aber von der nativen App-Vorbereitung nicht benutzt.

## Funktions- und Optionenmatrix

| Werkzeugfunktion | Native App / interner Vertrag | Gezielter Testbeleg |
| --- | --- | --- |
| Einzel vorbereiten | `HearingPrepareDialog`, `HearingPrepareWorker`, `create_set` | `test_hearing_native_integration.py`: echter interner Producer, Worker, Laden, Noten, erneutes Öffnen |
| Kandidaten / Dreinoten vorbereiten | gleicher Service, modusspezifische Parameter | gleicher Integrationstest, `test_hearing_producer_sink.py`, `test_hearing_workflow.py` |
| Dramaturgie vorbereiten | gespeicherter Scoring-Snapshot, Struktur-/Quellenvalidator, getrennte Ratings | gleicher Integrationstest, `test_hearing_sources.py`: spätere Kalibrierung darf eingefrorenen Satz nicht ungültig machen |
| `out/cache/anzahl/bpm-toleranz/seed/energy-direction/nur-genre` | passende Formularfelder; wirkungslose Felder deaktiviert | `test_prepare_form_maps_modes_and_disables_ineffective_fields`, `test_prepare_form_exposes_all_effective_candidate_options`, `test_namespace_has_exact_ui_to_parser_mapping` |
| `harmonic-strictness/allow-experimental/max-versionen-pro-paar/tracks-einmalig/auswahlprofil/workers/transition-type-modus` | nur Kandidaten; Pilot als eigener Auswahlpunkt | `test_prepare_form_exposes_all_effective_candidate_options`, `test_namespace_has_exact_ui_to_parser_mapping`; Formular-/Parametervertrag, nicht musikalische Wirksamkeit aller Optionen |
| `sequenz-tracks/uebergaenge-pro-variante` | nur Dramaturgie | `test_prepare_form_maps_modes_and_disables_ineffective_fields`, `test_namespace_has_exact_ui_to_parser_mapping`, `test_service_uses_real_dramaturgy_producer_without_audio` |
| Noten, explizites Löschen, Paarwahl | `HearingRatingDialog` + `hearing_ratings.save_rating`; gemeinsame Serialisierung/Validierung | `test_hearing_ratings.py`, `test_hearing_panel.py`, unveränderte Serverregressionen |
| Direktes Abspielen / Übergang | Legacy-Datei direkt, Quellen-Spec über eigenen Spawn-Worker → RAM → Qt | `test_hearing_playback.py`, `test_hearing_smoke.py` |
| Kandidaten-Audit und Fit | `HearingCalibrationWorker` → gebundener Snapshot, bestehende Auditor-/Fit-Funktionen | `test_hearing_calibration.py`; synthetischer Auditor-Vertrag ersetzt dabei DSP/Ranking und ist kein realer Klangnachweis |
| Einzel-Fit Seed/Genres | `HearingFitDialog` + interner Einzel-Fit, eigenes Ergebnis | `test_hearing_calibration.py`: echter Spawn mit zu wenig Bewertungen lehnt ab, produktive Präferenzen unverändert |
| Vorschlag / aktive Übernahme | strikte Zustandsmatrix, Operations-ID, SHA-Bindungen, getrennte Bestätigung und Refresh | `test_hearing_calibration.py`, `test_hearing_native_integration.py` |
| Satzliste / Wiederaufnahme | `discover_sets`, `HearingDiscoveryWorker`, explizit gewählter Root, full Load danach | `test_hearing_discovery.py`; keine automatische Plattensuche |
| Blindvorbereitung | `prepare_blind_references`, `HearingBlindWorker`, vier Pfade + optionaler Seed | `test_hearing_blind.py`; ursprüngliche CLI-Regression unverändert |
| Bestehende Blindreferenzen erneut prüfen | eigene QUALITY-Aktion, `HearingBlindCheckWorker`, vorhandener `load_blind_references`; nur Integritätsstatus | `test_blind_check_button_slow_actual_worker_no_modal_or_state_change`, `test_blind_check_real_worker_validates_without_disclosing_or_writing`; keine neue Bewertung, Statistik oder Entblindung |
| Optionaler Remote-Server | eigener QProcess, Loopback-Port, HTTP-Bereitschaft mit exaktem Launch-Token | `test_main_window.py` enthält Ownership-/Retry-Verträge; kein Ersatz für native Funktionen |

## Ausgeführte technische Prüfungen

Diese Zahlen stammen aus einzelnen Entwicklungsprüfungen mit `--no-cov -n 0`, sind überlappend und dürfen nicht addiert werden:

- 103 bestanden: Kalibrierungs-Schutzfälle, Blindreferenzen, Discovery (7,29 s).
- 84 bestanden: Kalibrierung, Release-Metadaten, Run-Lifecycle, native Vier-Modi-Integration (8,02 s).
- 75 bestanden: Kalibrierung mit strikter Zustandsmatrix und Quellen-/Dramaturgievalidierung (15,60 s).
- 5 bestanden: tatsächlicher isolierter Source-Smoke aus fremdem Arbeitsordner und abgewiesene Diagnoseargumente (6,43 s).
- Source-Smoke: alle neun nativen Module importiert; echte Qt-Formulare; tatsächlicher Spawn-DSP in RAM, 16.000 Stereo-Frames bei 8 kHz, endlich und nicht stumm; keine zusätzliche WAV/MP3; synthetische Originalquellen unverändert.
- Zwischenstand vor den abschließenden GUI-/CSV-/Buildkorrekturen: exakter Gesamtbefehl `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`, Exit 0, 4.559 bestanden in 920,28 s, Coverage 84,44 %. Kein Abschlussbeleg für danach geänderten Code.
- Abschließende Entwicklungsslices: GUI/native Integration 112 bestanden (7,16 s); CSV-Service/Panel/Jobs/Apply 99 bestanden (10,74 s). Überlappende Prüfungen, keine addierte Gesamtzahl.
- Supplemental Source-Smoke: unabhängiger Prüfer führt zehn Fälle aus, Exit 0, 8,30 s. Zusätzlich tatsächlicher Kalibrierungs-Child mit reinen synthetischen CSVs und `cache=None`. Erwartete Ablehnung mangels Bewertungen (`fit_status=rejected`) ist ein Transport-/Isolationsnachweis, kein erfolgreicher Fit. Snapshot bereinigt, isolierte Preferences unverändert, keine zusätzliche Audioausgabe.

## Noch separat nachzuweisen

Der nächste Zwischenstand-Volltest endete mit Exit 0: 4.653 bestanden in 947,21 s. Die anschließend nur lesend geladene Coverage dieses Laufs beträgt 83,31 %. Dieser Lauf liegt vor der neuen Vocal-Policy und der Ergebnisdialog-Korrektur und ist deshalb kein Abschlussbeleg für diese Änderungen. Ein eigener Nachtest der geänderten Paar-/Browser-/Main-/Lifecycle-Fälle liefert 239 bestanden in 5,79 s, Exit 0; das ist weiterhin ein gezielter Lauf ohne Coverage.

Die erste gebaute EXE scheiterte tatsächlich beim Import von QtWidgets mit einer DLL-Prozedurfehlermeldung. Nach Eingrenzung des Build-PATH wurde ein Zwischenstand-Kandidat gebaut und tatsächlich gestartet. Build und Betriebssystem-Aufruf enden mit Exit 0; der Frozen-Smoke dauert 47,875 s. Imports, native Formulare, Produktions-Initializer, RAM-DSP und CSV-Kalibrierungs-Child bestehen. Der Hauptagent hat Report und vollständige Hashes direkt gelesen beziehungsweise berechnet. Dieser Zwischenstand liegt vor der späteren Ranking-Refresh-/Hard-Chain-Korrektur und beweist nicht deren Build. Die bestehende Nutzer-EXE wurde noch nicht ersetzt.

Kandidat: `C:\Users\david\AppData\Local\Temp\hpg-candidate-build-08378203ab164efdb1340e50215d2769\dist\HarmonicPlaylistGenerator.exe`.

- EXE-SHA-256: `018948bb1363e879f604f3de715fc69273c53b3fc04e99e03eb6adcc44d50d6d`.
- Source-/Frozen-Algorithmus-Fingerprint (47 Dateien): `6cb2ad9d601678119df4eda91e91f5b1455da0fe2d587740878bac31bcde7025`.
- `main.py`-SHA-256: `2827adffeafabbabf68eb123466a5fc896341f9ce61ba8b43cf9f707e08bf481`.
- Harness: `C:\Users\david\AppData\Local\Temp\hpg-candidate-build-08378203ab164efdb1340e50215d2769\frozen-process.json`.
- Frozen-Report: `C:\Users\david\AppData\Local\Temp\hpg-candidate-frozen-smoke-hs_irokw\frozen-report.json`.

Der Initializer-Worker wurde nach erfolgreicher Probe vom Owner beendet (Exit -15); Prozessende und Temp-Bereinigung sind separat bestätigt. Das ist kein natürlicher Worker-Exit 0. Beide Build-TOCs enthalten jeweils 301 native DLL/PYD-Einträge ohne fremde Ursprünge. Die optionale TBB-Warnung bleibt bestehen; es wurde nichts nachinstalliert. Dieser Beleg ist keine musikalische oder vollständige GUI-Abnahme. Eine nachträgliche Produktivänderung würde die Build-Bindung ungültig machen.

Aktuelle Gesamt-Suite nach allen Korrekturen, menschliche vollständige Benutzerabnahme, unabhängige Abschlussreviews und Git-Sicherung sind noch offen. Die uninstrumentierte Produktionsanalyse, eine isolierte tatsächliche Main-App-Kette und der aktuelle Frozen-Smoke sind inzwischen separat belegt. Die Main-App-Probe ergibt allerdings keine durchgehend geplante Playlist; technische Publikation ist keine musikalische Freigabe. Die verbindlichen Erfolgsnachweis-Regeln stehen ergänzend in AGENTS.md; ihre Speicherung ist keine App-Abnahme.

Weitere datierte Entwicklungsbelege: ParallelAnalyzer-Slice 63 bestanden in 244,08 s, einschließlich tatsächlichem Zwei-Worker-JIT-Spawn; Scope ist Analyse-Lifecycle, kein 26-Track-Nachweis. Source-Smoke nach dem Initializer-Zusatz 29 bestanden in 37,18 s; Worker-Ende wird tatsächlich geprüft, der beobachtete Worker-Exit -15 ist eine Owner-Terminierung und kein natürlicher Exit 0. Zusätzliche Cancel-Charakterisierung 20 bestanden/10 abgewählt in 0,19 s, ohne neue Produktivänderung. Der eigene Hauptagent-Nachtest für Blind-, Browser-, Jobs-, Main- und Lifecycle-Fälle besteht 188 Tests in 7,27 s, Exit 0. Diese überlappenden Zahlen werden nicht addiert.

Die durchgehende positive Fit-/Apply-/Ranking-Kette ist weiterhin offen. Vier numerische Machbarkeitstests bestehen mit vorab festgelegtem Seed und unveränderten statistischen Gates. Zusätzlich durchläuft ein echter synthetischer Producer-Satz mit 64 disjunkten Trackpfadpaaren und 128 Clips den tatsächlichen Replay-Audit und nativen Fit. Seine CSV-Teilwerte werden gegen `score_pair` geprüft; keine Scorer-/Audit-/Gate-Ergebnisse werden ersetzt. Labels sind absichtlich synthetisch. Hardlinks auf eine eigene Testquelle ergeben getrennte Pfade, aber keine unabhängigen musikalischen Aufnahmesessions oder Nutzerpräferenzen.

Diese echte Brücke deckte eine GUI-Lücke auf: `_refresh_hearing_ranking` übergab `ai_enabled` an den strikten Scoring-Vertrag und startete deshalb keinen Ranking-Worker. Eine kleine unveränderte Regression war vor dem minimalen Fix rot (ein Fehler, sechs abgewählt, 0,74 s); danach grün (ein bestanden, sechs abgewählt, 0,78 s), mit echtem Worker und Generationsergebnis. Der Fix kopiert und validiert Advanced-Werte wie im normalen Start, hält KI-Metadaten separat und weist andere unbekannte Schlüssel weiterhin ab. Der vollständige bestätigte Apply-/Ranking-Nachtest läuft separat. Der vorherige Frozen-Kandidat bindet nicht den danach geänderten `main.py`-Stand; ein neuer Build ist erforderlich.

## Originalquellen: DSP versus Playlist-Zulässigkeit

Die reale Trackanalyse hat im ersten Zweierlauf keinen gültigen Übergang geliefert und endete vor DSP; das ist kein positiver Playlist-E2E-Nachweis. Ein separater technischer DSP-Lauf mit Originalfenstern von Hallucination Generation → Dance with Me hat dagegen zwei Übergangstypen in RAM berechnet und als PCM-16 kodiert/dekodiert, ohne Audioausgabe auf Platte: je 87,042 s Stereo bei 44.100 Hz, alle Samples endlich, Sample-Peak 0,999786; `pro_eq_swap` −13,98 LUFS, `smooth_blend` −14,20 LUFS. Maximale Rest-Kickabweichung 0,204 ms bei unveränderter 6-ms-Grenze. Sechs technische Prüfungen bestanden; Quellpfade, Größen und SHA-256 blieben unverändert. Das ist kein menschliches Hörurteil und kein Inter-Sample-True-Peak-Nachweis.

Die gezielte Kandidatendiagnose vor der Policy-Korrektur zeigt: Die lokale Vocal-Messung ist vorhanden, aber ein Fenster liefert den ausdrücklich unsicheren Zustand `unknown`. Dieser wird zu `vocal_aktiv_lokal=None` und erfüllte nicht das damalige Paar-Gate mit zwei eindeutigen Bools. Die ausdrückliche Nutzerentscheidung vom 04.10.2026 macht diese Information optional: Der Produktivdiff entfernt ausschließlich die beiden Vocals-Pflichtzeilen; `None` bleibt unbekannt, der bekannte beidseitige Vocal-Clash-Abzug bleibt 0,06. Die Regression war zunächst rot (5 fehlgeschlagen, 18 bestanden); danach bestanden 118 Paar-Tests. Andere Mess-, BPM-, Grid-, Kick-, Coverage- und Score-Gates bleiben erhalten. Ein zulässiger Original-Playlistlauf nach dieser Änderung ist separat nachzuweisen.

Menschliche Hörbewertung und die musikalisch beste Reihenfolge sind grundsätzlich kein Ergebnis dieser automatisierten technischen Tests.

Nach der Vocal-Korrektur wurde mit den zwei isoliert erhaltenen Track-Cachezeilen ein neuer Satz über den nativen `create_set`-Dienst erstellt: ein Paar mit einem publizierten Kandidaten, vollständige Originalquellen- und Snapshot-Bindung geprüft. Der eingefrorene Ranking-Vertrag liefert zwölf gültige Kandidaten für Hallucination Generation → Dance with Me; Score 0,8025088226707545 bei unveränderter Mindestgrenze 0,70. Der gewählte Übergang verwendet 461,415 s → 189,311 s, 16 Takte und `pro_eq_swap`; Vocal-Status bleibt `True`/`None`. `load_session` und `render_wav_bytes` berechnen den Übergang tatsächlich in RAM: 43,042 s, Stereo, 44.100 Hz, Peak 0,889008, endliche Samples. Original- und Analyse-Cache-Fingerprints bleiben unverändert; kein Audioartefakt im Proberoot. Das beweist native Erzeugung und Wiedergabeberechnung, noch nicht Replay-Audit, vollständige GUI-Bedienung oder musikalische Qualität.

Eine weitere frische Probe vor der Vocal-Policy-Korrektur analysierte vier Originaltracks und bewertete zwölf gerichtete Paare: null zulässige Kanten. Hallucination Generation → Dance with Me erreichte 0,802509, wurde aber wegen fehlender eindeutiger lokaler Vocal-Messung abgewiesen. Zwei weitere Paare lagen über 0,70 und scheiterten ebenfalls am Vocal-Vertrag. Alle vier seriellen Analysen gelangten zum Ergebnis; überprüfte Originale blieben unverändert. Dieses historische Ergebnis wird nicht nachträglich als erfolgreicher Lauf umetikettiert.

## Produktionsanalyse: reproduzierter Fehler und begrenzte Mitigation

Der tatsächliche Zwei-Worker-ParallelAnalyzer wurde separat ausgeführt und zeigte Access Violations; betroffene JIT-Artefakte lösten anschließend auch in Einzelprozessen einen solchen Absturz aus. Der genaue Entstehungsmechanismus ist nicht bewiesen, insbesondere kein abschließend nachgewiesener Concurrency-Race.

Eine vollständige instrumentierte Probe des ParallelAnalyzer mit eigenen PID-/UUID-JIT-Caches pro Worker und ausschließlich im Diagnose-Elternprozess auf 180 s gesetztem Timeout liefert 2/2 Originaltracks, Exit 0, ohne Recovery, AV oder externe Deadline. Futures einschließlich Start/Initializer benötigten 103,828 und 105,937 s; der Analyzer insgesamt 106,625 s. Die beiden Downbeat-Tupel stimmen exakt mit den vorherigen Kontrollmessungen überein. Originalgrößen und SHA-256 blieben unverändert; der eigene Temp-Root enthält keine Audiodateien und die Worker sind beendet. Die Produktionsgrenze war dabei weiterhin 60 s.

Diese historische Diagnose war noch kein Produktionsnachweis. Der anschließende Produktivdiff übernimmt Worker-lokale PID-/UUID-JIT-Caches, verzögerte Analyseimporte und eine Standard-Taskdeadline von 180 s. Haupt- und Recovery-Pool benutzen denselben Ownership-/Shutdown-Vertrag. Nur eigene Temp-Daten werden nach bestätigtem Worker-Ende entfernt; unbestätigte Endzustände behalten den Pfad mit Warnung.

Die anschließende uninstrumentierte Probe ruft den tatsächlichen `ParallelAnalyzer()` ohne Monkeypatch oder Konfigurationsüberschreibung auf: 26 Original-AIFFs aus `F:\beatport_tracks_2026-04`, automatisch vier Worker und eigener anfangs leerer Analyse-Cache. Der frische Lauf liefert 26/26 Ergebnisse in 639,172 s (äußerer Prozess 639,422 s, Exit 0). Die getrennte Wiederholung aus diesem Cache liefert ebenfalls 26/26 in 13,953 s (äußerer Prozess 14,156 s, Exit 0). Original-Fingerprints und eingefrorene Produktivdateien bleiben unverändert. Im eigenen Proberoot liegen keine Audiodateien; eigene Poolroots und Kindprozesse sind am Ende entfernt. Der Cache enthält 26 Trackzeilen plus Versionsmarker.

Direkt vom Hauptagenten geprüfte Belege: `C:\Users\david\AppData\Local\Temp\hpg-production26-4w1_f7cf\final-report.json`, `fresh-result.json`, `cache_hit-result.json` und `fresh-raw.log`. Sämtliche Ergebnisse verwenden `rekordbox_fast_tail`; diese Probe belegt nicht zusätzlich den Librosa-Vollpfad. Der Erstlauf wird nicht durch Cache-Erfolg ersetzt. Dies belegt die Produktionsanalyse dieser 26 Dateien, nicht jedes Musikformat, menschliche GUI-Bedienung oder musikalisch beste Reihenfolge.

## Aktuelle native Originalquellen-Proben und offener Playlistbefund

Ein neuer Einzelpaar-Satz mit aktuellem Algorithmus-Fingerprint besteht native Vorbereitung, tatsächlichen `HearingCalibrationWorker` (Audit-only: 4,109 s, `audit_passed=true`, Exit 0) und tatsächlichen `HearingAudioWorker` (1,781 s, Exit 0). Der Übergang Hallucination Generation → Dance with Me bleibt 43,042 s Stereo/44.100 Hz, alle Samples endlich, Peak 0,889008. Kein Fit oder Apply wird aus diesem Einzelpaar abgeleitet. Belege liegen unter `C:\Users\david\AppData\Local\Temp\hpg-private-jit-full-cjjh5ea7\native-audit-u57b12o2\`.

Die isolierte tatsächliche `MainWindow.start_analysis`-Kette mit dem erhaltenen Testcache durchläuft `AnalysisWorker`, Main-Routing, `PlaylistGenerationWorker` und Tabellenpublikation in 18,719 s, Exit 0. Sie zeigt 26 Rohtracks und 26 Playlist-/Tabellenzeilen. Der damalige Result enthält aber nur fünf geplante und zwanzig ungeplante Grenzen; Quality 17 %. Beide Nachbarn von Dance with Me (189,311 s Mix-In, 54,100 s Mix-Out) und Telemetry (109,742 s, 54,885 s) besitzen tatsächlich aktive Pläne. Das ist kein Analysewert-Fallback. Auch Hallucination Generation hat ein zu kleines Mitteltrackfenster (Mix-In gleich Mix-Out: 380,289 s).

Report: `C:\Users\david\AppData\Local\Temp\hpg-production26-4w1_f7cf\native-main-fqbac7n2\main-chain-report.json`. Originale und Testcache bleiben unverändert; keine verbleibenden eigenen Kindprozesse, JIT-Pools oder Audiodateien. Technisches `success` und passende Tabellenbeschriftungen beweisen keine durchgehend ausführbare oder musikalisch beste Playlist. Die aktuelle Kandidaten-EXE ist deshalb noch nicht als finale Gesamtlösung freigegeben.

Der konkrete Core-Defekt wird danach isoliert reproduziert: `_select_snapshot_path` ließ ein negatives `_candidate_link_consistent` nur als Flag stehen und zählte die unspielbare Kombination weiter als geplant. Nach unabhängiger Vorprüfung (TOR1: DURCHGEWUNKEN) verwerfen zwei zusätzliche Codezeilen genau diese Kombination vor Zustandsbildung. Validator, Zwei-Phrasen-Fenster, Gates, Gewichte, Auswahlprioritäten und Trackvorkommen bleiben unverändert. Fünf Timing-/Alternativregressionen waren vorher rot, danach grün; die Result-Datei liefert 164 bestanden in 2,84 s. Der Metadaten-Repro mit tatsächlichen Kandidatensnapshots wählt für Dance den zulässigen Mix-Out 405,650 s und lässt den unmöglichen Telemetry-Anschluss ungeplant. Das ist kein Audio- oder Klangnachweis. Die historische Legacy-Erwartung einer aktiven inkonsistenten zweiten Kante wurde nach gesonderter Vorprüfung ausdrücklich korrigiert und begründet. Der eigene fokussierte Nachtest von Result, Legacy, Browser, Main und Lifecycle besteht 314 Tests in 9,56 s, Exit 0, ohne Coverage.

Ein getrenntes Ranking aller 650 gerichteten Originalpaare ergibt nur 23 zulässige Kanten. Sie betreffen sieben Tracks; neunzehn Tracks sind vollständig isoliert. Von den zwanzig ungeplanten Nachbarn fehlen siebzehn verlässliche lokale Groove-/Bass-/Strukturmessungen; drei verletzen das BPM-Gate. Bei achtzehn der neunzehn isolierten Tracks liegt die Downbeat-Konfidenz unter 0,30, wodurch bestimmte lokale Messungen ausdrücklich unbekannt bleiben. Deshalb ist eine zulässige Gesamtfolge aller 26 Tracks mit diesen Daten und unveränderten Gates unmöglich. Die Kettenkorrektur erfindet weder Messwerte noch eine Vollplaylist. Diagnose und Graphbeleg: `C:\Users\david\AppData\Local\Temp\hpg-chain-diagnosis-c3e558ddc30e493582a2588db806867c\diagnosis.json` und `graph-summary.json`. Die Ursache der schwachen Messbasis und eine erneute native Main-Probe bleiben separat zu prüfen.

## Wiederholung nach Ranking-Refresh und Hard-Chain-Fix

Aktueller Source-/Frozen-Fingerprint (47 Dateien): `f6e5948204e1aac630d9ad3e709eeccbdf85c87f64a3812211e4dc71b3c3b8a9`. Aktueller `main.py`-SHA-256: `d564eb276f421c7269213bcb442593bbab95b36482c34578d2ae25478328b010`.

Die tatsächliche isolierte Main-Cachechain besteht erneut in 20,563 s, Exit 0. Alle 26 Track-Metadaten und 23 Kandidatensnapshots bleiben identisch. Ergebnis: drei geplante und 22 ungeplante Grenzen. Der einzige beidseitig geplante Anschluss, Dance, nutzt nun 189,311 s Mix-In und 405,650 s Mix-Out (Rang 7); 216,339 s Abstand erfüllen das Zwei-Phrasen-Fenster von 54,085 s. Hallucination- und Telemetry-Ausgänge sind tatsächlich nicht ausgewählt. Keine benachbarten aktiven Pläne verletzen den Kettenvertrag. Die GUI meldet dennoch technisch `success` und „Complete — 26 tracks, Quality 11%“; das ist keine ausführbare vollständige Playlist. Report unter `C:\Users\david\AppData\Local\Temp\hpg-production26-4w1_f7cf\native-main-_5fo21wm\main-chain-report.json` vom Hauptagenten direkt gelesen.

Neues natives Einzelpaar-Manifest am gleichen Freeze: Vorbereitung 2,078 s, Audit-only 4,515 s, RAM-Playback 2,328 s, jeweils Exit 0. Audit und Playback bestehen; Originale und private Analyse-Caches unverändert, Threads/Prozesse beendet, Scratch leer, keine verbliebenen Audiodateien. Audit-Binding und RAM-Metriken direkt vom Hauptagenten gelesen: 1.898.163 Frames/44.100 Hz/Stereo, 43,042 s, Peak 0,889008, vollständig endlich. Reports unter `C:\Users\david\AppData\Local\Temp\hpg-private-jit-full-cjjh5ea7\native-audit-0e7jzxhu\`. Kein Fit oder Apply wird aus diesem Einzelpaar behauptet.

Der neue Kandidat `C:\Users\david\AppData\Local\Temp\hpg-chain-candidate-build-da8c60ce9bb74a3aa9d87f2e06aa81d7\dist\HarmonicPlaylistGenerator.exe` hat SHA-256 `07bbb91df0a74b8c457156ab1de368b5c9b8496d0528055c8a2e8fc1583aa3d4`. Build Exit 0; tatsächlicher EXE-Smoke OS-Exit 0 in 44,203 s. Frozen-Fingerprint stimmt mit dem aktuellen Source-Fingerprint überein. Imports, Forms, Initializer, RAM-DSP und CSV-Fit-Child bestehen. Initializer-Worker 25520 wird vom Owner mit Exit -15 beendet; Reaping, privater Cache vor/nach Beat-Import, unveränderte Parent-Umgebung und entfernte Temp-Root sind im Report separat bestätigt. Der Hauptagent hat EXE-Hash, Harness und Frozen-Report direkt geprüft: `frozen-process.json` im Buildroot und `C:\Users\david\AppData\Local\Temp\hpg-chain-frozen-smoke-4pocyzyb\frozen-report.json`. Keine finale Release- oder Musikfreigabe; Nutzer-EXE weiterhin unverändert.

Die separate ANLZ-/Metadatenprobe meldet bei allen 26 Ergebnissen `rekordbox/mismatch` mit drei geprüften Fenstern, 15,969–218,123 ms Phasenfehler. Achtzehn Downbeat-Konfidenzen liegen unter 0,30, zwölf sind null. Kein übersehener bereits verifizierter Quellanker ist nachgewiesen. Aktuelle F:-Dateien werden über Basename-Fallback zu D:-Records zugeordnet; deren Audioidentität ist nicht bewiesen. Eine neue Kalibrierung oder Gate-Lockerung ist daraus nicht gerechtfertigt.

Die getrennte tatsächliche Vollanalyse von Hallucination und Dance ohne Rekordbox besteht 2/2 in 164,532 s (äußerer Prozess 166,000 s, Exit 0). `HPG_DISABLE_REKORDBOX=1` gilt nur im eigenen Prozessumfeld, der neue Testcache ist vor Start leer. Tatsächlicher unveränderter `ParallelAnalyzer()` skaliert für zwei Eingaben auf einen Worker; dies ist kein Vier-Worker-Full-Nachweis und unter Hintergrundlast kein Benchmark. Beide Ergebnisse verwenden `librosa_full_or_tail`, Quelle `audio`, leere Rekordbox-Signatur, BPM 142, Camelot 11A, vollständig erfasstes Outro und LUFS-Status `complete`, je elf Sections und acht In-/acht Out-Kandidaten. Originale und aktuelle Source-/Main-Hashes unverändert, eigener Prozessbaum beendet, keine Audioartefakte. Die Grid-Abweichung tritt auch ohne Rekordbox auf; alte Datenzuordnung erklärt sie daher nicht allein. Hauptagent liest Report und Supervisor direkt unter `C:\Users\david\AppData\Local\Temp\hpg-full-original-pair-327vne0u\`.

Ein zusätzlicher tatsächlicher Full-Versuch untersucht Eternal, nach den erhaltenen Track-/Graphdaten eines der neunzehn Isolate: 1/1 Ergebnis, 99,031 s (außen 100,437 s, Exit 0). Die Konfidenz bleibt null und Groove-/Bass-Pattern fehlen weiterhin. Das Log meldet ID3-BPM 97 gegenüber Audio-Gegenprobe 136,0; der bestehende Prior-Pfad behält 97. Weder 136 als Ground Truth noch eine konkrete Reparatur ist dadurch bewiesen. Full ist für diese Quelle kein nachgewiesener Ersatz für die fehlenden Messwerte. Keine Produktänderung, erfundene Konfidenz oder Gate-Lockerung; eigener Prozessbaum beendet, Original unverändert, keine Audioartefakte. Belege unter `C:\Users\david\AppData\Local\Temp\hpg-full-isolate-one-s_bk488o\`.
