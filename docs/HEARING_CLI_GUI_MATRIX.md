# Hörtest-Werkzeuge: CLI- und GUI-Matrix

**Stand:** 11.11.2026
**Codebasis:** Branch `codex/gesamtrefaktorierung`, Quellstand `227faac9d0598b93544ba6468381dd20465bbc07`.
**Delta zum vorherigen Prüfsnapshot `3707d71e`:** spätere `main.py`-Änderungen ergänzen initiale Leerzustände und den GUI-Zustandswechsel. `hpg_core/hearing_panel.py`, `hpg_core/hearing_workflow.py`, `tools/rate_transitions.py` und die Hörtest-Serverpfade blieben unverändert; die unten genannten Verträge wurden gegen diesen aktuellen Stand nachgeprüft.
**Zweck:** Werkzeugverhalten, Nutzeraktionen, absichtliche Unterschiede und Regressionen direkt gegeneinander abgleichen. CLI-Optionen, die Pfade/Prozesse für Entwickler steuern, werden nicht als fehlende Nutzerfunktion gewertet, wenn die App sie kontrolliert ableitet.

## Satzvorbereitung

CLI-Parser: `tools/rate_transitions.py prepare`. GUI: `HearingPrepareDialog` → `PrepareConfig` → `hpg_core.hearing_workflow.create_set` → derselbe interne Producer-Namespace.

| CLI-Option | GUI-Feld oder Verhalten | Modus / Abgrenzung | Beleg |
|---|---|---|---|
| `--anzahl` | „Übergänge“ / Anzahl-Feld | Einzel und Kandidaten; Dramaturgie verwendet die feste Pool-/Variantenkonfiguration | `test_prepare_form_config_and_producer_namespace_parity`; `test_namespace_has_exact_ui_to_parser_mapping` |
| `--out` | App legt den Satzordner privat über `managed_config` an | Kein frei überschreibbarer Pfad im Erstellungsdialog; bestehende Ziele werden abgelehnt | `tests/test_hearing_workflow.py`; `tests/test_hearing_managed.py`; `test_prepare_lehnt_jedes_vorhandene_ziel_vor_cachezugriff_ab` |
| `--bpm-toleranz` | BPM-Toleranz | Alle Satztypen | `test_prepare_form_config_and_producer_namespace_parity` |
| `--energy-direction {auto,up,down,maintain}` | Energieverlauf | Einzel und Kandidaten; Dramaturgie deaktiviert das Feld, weil der Producer die Option nicht verwendet | `test_prepare_form_maps_modes_and_disables_ineffective_fields` |
| `--harmonic-strictness 1..10` | Harmonie-Strenge | Kandidaten; in Einzel/Dramaturgie deaktiviert | `test_prepare_form_exposes_all_effective_candidate_options`; `test_namespace_has_exact_ui_to_parser_mapping` |
| `--allow-experimental {true,false}` | Experimentelle Harmoniebeziehungen erlauben | Kandidaten; sonst deaktiviert | dieselben Kandidaten-Options- und Namespace-Tests |
| `--cache` | automatisch an Analyse-Snapshot gebunden | In der App kein beliebiger Cache-Pfad beim Erstellen; alter Cache wird bei Fit/Audit gesondert gewählt | `test_prepare_form_config_and_producer_namespace_parity`; `test_fit_dialog_does_not_ignore_required_or_supplied_bad_cache` |
| `--seed` | Zufallsseed | Einzel und Kandidaten; Standard wird aus `rate_transitions.STANDARD_SEED` übernommen; Dramaturgie deaktiviert es | `test_prepare_form_maps_modes_and_disables_ineffective_fields`; `test_namespace_has_exact_ui_to_parser_mapping` |
| `--nur-genre` | Genre-Auswahl „Alle“ oder kanonisches Genre | Einzel und Kandidaten; Dramaturgie deaktiviert; entspricht dem Producer-Filter „beide Tracks tragen Genre“ | `test_prepare_form_config_and_producer_namespace_parity` |
| `--modus {einzel,kandidaten,dramaturgie}` | Satztyp-Auswahl Einzel/Kandidaten/Dreinoten-Pilot/Dramaturgie | Dreinoten-Pilot ist Kandidatenmodus mit anderem Ratingschema (`three_notes=True`), kein vierter Producer | `test_prepare_form_maps_modes_and_disables_ineffective_fields`; `test_prepare_form_config_and_producer_namespace_parity` |
| `--sequenz-tracks` | Tracks im Dramaturgie-Pool | Nur Dramaturgie; sonst deaktiviert | `test_prepare_form_maps_modes_and_disables_ineffective_fields` |
| `--uebergaenge-pro-variante` | Übergänge pro Dramaturgie-Variante | Nur Dramaturgie; sonst deaktiviert | derselbe Modus-/Optionsvertrag |
| `--max-versionen-pro-paar` | Versionen pro Paar | Nur Kandidaten | `test_prepare_form_exposes_all_effective_candidate_options` |
| `--dreinoten-pilot` | Modus „Dreinoten-Pilot“ | Schaltet beim Kandidatenproducer das Schema `track_note`, `technik_note`, `gesamt_note`; normaler Kandidatenmodus bleibt unverändert | `test_prepare_form_maps_modes_and_disables_ineffective_fields`; `test_three_note_schema_starts_seeded_candidate_fit_worker` |
| `--tracks-einmalig` | „Jeden Track im Durchgang höchstens einmal“ | Nur Kandidaten | `test_prepare_form_exposes_all_effective_candidate_options` |
| `--auswahlprofil` | Datei wählen | Nur Kandidaten; JSON wird vor Workerstart geprüft und beim Producer erneut validiert | `test_prepare_form_selection_profile_file_picker`; `test_prepare_form_rejects_bad_selection_profile_before_config_or_worker` |
| `--workers 1..4` | Suchprozesse | Nur Kandidaten | Kandidaten-Optionsmatrix und Namespace-Parität |
| `--transition-type-modus {kontrolliert,produktion}` | Übergangstyp-Modus | Nur Kandidaten | Kandidaten-Optionsmatrix und Namespace-Parität |
| Original-Musikordner | App-only Pflichtauswahl | Erzeugt gebundene Quellreferenzen und nötigen Analyse-Snapshot; Originale bleiben am Quellort | `test_prepare_form_config_and_producer_namespace_parity`; `tests/test_hearing_managed.py` |

## Satzsuche, Validierung und Bewertung

| Werkzeug/API | GUI-Aktion | Vertragsgrenze / Status | Testbelege |
|---|---|---|---|
| `hearing_discovery.discover_sets(root)` | **Sätze / Fortschritt** wählt explizite Wurzel; liest Wurzel und direkte Unterordner; Tabelle filtert Ordner, Typ, Fortschritt, Status und Fehler | Fortschritt ist kein Quellen-/Auditnachweis. Öffnen lädt und validiert danach vollständig im Hintergrund. Links und tiefere Ordner werden nicht verfolgt. | `test_discovery_rows_then_full_load_only_after_finished`; `test_hearing_set_browser_search_filters_and_clears_hidden_selection` |
| Legacy Einzel-CSV: `hearing_calibration.validate_set` | **Satz öffnen**, Einzel-CSV-Auswertung | Prüft CSV-Schema, eindeutige IDs, 1:1-Zuordnung und Wertebereiche; traversiert dabei keine Clip-Unterordner | `tests/test_hearing_calibration.py`; `tests/test_hearing_browser_integration.py` |
| Quellreferenz Einzel/Kandidaten/Dramaturgie: `hearing_sources.load_source_session` mit getrennten Modusvalidatoren | **Satz öffnen** und Rating-Fortsetzung | Modusspezifische Manifest-/Metadatenprüfung; Quellen- und Audio-Bindung bleibt getrennt von Replay-Audit | `tests/test_hearing_sources.py`; `tests/test_hearing_browser_integration.py`; `test_service_uses_real_internal_producers_with_source_sink` prüft die Loaderannahme echter interner Producer-Ausgaben für Einzel/Kandidaten/Dreinoten |
| `tools.audit_candidate_set` (`--set-dir`, `--cache`, `--report`) | **Kandidaten-Replay prüfen** | Schreibt keine Originalclips, Ratings oder Cache. App zeigt Replay-Ergebnis und Integritätsbindung; persistente Reportdatei ist optionaler Export, keine Voraussetzung des nativen Vorschlagsflusses | `tests/test_audit_candidate_set.py`; `test_audit_dialog_completion_reports_replay_without_fit` |

### Native und Browser-Bewertung

Native GUI-Ratings und HTTP-POSTs verwenden beide `hpg_core.hearing_ratings.save_rating`. GUI: **In der App bewerten**, **Bewerten im Browser**. Jede Note wird sofort gespeichert. Vor Rating/Bestwahl bindet der Worker die Quellen erneut; noch nicht erfolgreich gerenderte Clips sind nicht bewertbar.

| Serververtrag | GUI-Ersatz / Wirkung | Beleg |
|---|---|---|
| `GET /daten` | Einzel-, Kandidaten- und Dreinoten-Übersicht für Browser | `tests/test_hoertest_server.py` (GET-/Schemafälle) |
| `GET /daten-dramaturgie` | Dramaturgie-Varianten und Reihenfolge | `test_dramaturgie_server_liefert_reihenfolge_und_speichert_urteile_getrennt` |
| `GET /reihenfolge` | Dramaturgie-Reihenfolge | derselbe Dramaturgie-Servertest |
| `GET /noten` | Legacy-Kompatibilitätsantwort | `tests/test_hoertest_server.py` (Legacy-Routenfälle) |
| `GET /clips/<relativer-pfad>` inkl. HTTP Range | Browser-Audiowiedergabe; Pfadcontainment und Bereichsanfragen | `tests/test_hoertest_server.py` (Clip-/Range-/Fehlerfälle) |
| `POST /note` | Einzelnote; Kandidaten-/Dreinoten-Noten mit Dimension | `test_dreinoten_post_aendert_genau_eine_dimension_atomar`; `test_kandidaten_note_akzeptiert_exakte_json_ganzzahlgrenzen` |
| `POST /bester` | Beste Kandidatenvariante oder explizit „keine beste Variante“ | `tests/test_hoertest_server.py` (Winner-/No-winner-Verträge) |
| `POST /transition-note` | Dramaturgie-Übergangsdimension | `test_dramaturgie_server_liefert_reihenfolge_und_speichert_urteile_getrennt` |
| `POST /dramaturgie-note` | Dramaturgie-Sequenzdimension | derselbe Dramaturgie-Servertest |

Server-CLI: `--dir` wird durch den geöffneten Satz ersetzt; `--port` durch einen freien Loopback-Port; `--launch-token` durch die interne Startkennung der gebundenen `QProcess`-Instanz; `--cache` wird für alte Sätze optional explizit gewählt, sonst nutzt die App den zum Satz gebundenen Snapshot. Keine fremden Prozesse am Port werden beendet. Tests: `test_startkennung_bindet_launcher_an_eigenen_server`, `test_startkennung_auch_fuer_dramaturgie_server` und Server-Lifecycle-Fälle in `tests/test_hearing_browser_integration.py`.

Der optionale Konsolenweg `Start_Hoertest.bat` → `tools/hoertest_launcher.py` ist weiterhin vorhanden und getestet. Er findet direkte Hörtest-Unterordner auf Desktop/Projekt oder nimmt einen manuellen Pfad, zeigt schemaabhängigen Fortschritt, wählt einen freien Loopback-Port, startet `hoertest_server.py` mit eigenem Launch-Token, öffnet den Browser erst nach Bereitschaft und beendet ausschließlich den eigenen Serverprozess. Im Qualitätsbereich entspricht ihm die native Satzsuche plus **Bewerten im Browser**; dort werden Wurzel und Satz explizit gewählt und Prozess/URL innerhalb der App verwaltet. Der Konsolenlauncher bleibt ein optionaler Kompatibilitätsweg, kein fehlender Desktop-Featurepfad. Belege: `tests/test_hoertest_launcher.py` (Portkollision, Prozessbindung, Startfehler, Absturz, Browserfehler, Fortschritt und Schemaabgleich).

## Fit und Berichte

| CLI | GUI-Ersatz | Unterschied / Status | Belege |
|---|---|---|---|
| `rate_transitions.py fit --dir` | zuvor geöffneter Satz oder **Einzel-CSV auswerten** | Einzel-CSV-Auswertung verändert den geöffneten Satz nicht | `tests/test_hearing_browser_integration.py`; `tests/test_hearing_calibration.py` |
| `--modus {einzel,kandidaten}` | Modus aus Satzschema und App-Aktion | Dreinoten-Schema wird explizit erkannt, bleibt Kandidaten-Fit | `test_fit_dialog_explains_three_note_schema_and_disables_irrelevant_options`; `test_three_note_schema_starts_seeded_candidate_fit_worker` |
| `--seed` | Fit-Seed in erweiterten Optionen | Im Replay-only-Audit deaktiviert, da dort kein Fit läuft | `test_fit_dialog_maps_only_effective_genre_and_seed_options`; `test_fit_dialog_options_reach_calibration_worker`; `test_three_note_schema_starts_seeded_candidate_fit_worker` |
| `--genre` | Komma-getrennte Genres nur bei Einzel-Fit | Bei Kandidaten bedeutungslos und UI-seitig deaktiviert; Kandidaten berichten Genre-Gates/Rankings aus Daten | `test_fit_dialog_maps_only_effective_genre_and_seed_options`; `test_fit_dialog_options_reach_calibration_worker`; `test_gated_candidate_fit_apply_persists_and_refreshes_ranking_end_to_end` |
| `--cache` | optional bei Einzel, verpflichtend bei Kandidaten/Replay-Audit; alter Cache kann gewählt werden | Kein stiller Rückfall auf den aktuellen Cache | `test_fit_dialog_does_not_ignore_required_or_supplied_bad_cache`; `tests/test_hearing_browser_integration.py` |
| `--audit-report` | App erzeugt und reicht einen gebundenen RAM-Receipt weiter | Kandidaten-Fit ohne erfolgreichen, passenden Replay-Audit wird abgelehnt; App benötigt keine persistente Zwischenreportdatei | `test_fit_bindet_nichtleeren_erfolgsreport_an_manifest_csv_wav_cache_und_build`; Lifecycle-/Auditdialogtests |
| Einzel-Fit-Ausgabe | inaktiver, gebundener Gewichte-/Diagnoseentwurf | Kein automatisches Anwenden auf Produktivgewichte | `tests/test_hearing_calibration.py`; `tests/test_rate_transitions.py` |
| Kandidaten-Fit-Ausgabe | vollständiger `CandidateFitResult`, Gate-/Holdout-/Rankingbericht | Anwendung nur nach bestandenen Gates, erster Zustimmung und separater Zweitbestätigung; Persistenz/Ranking-Refresh separat nachgewiesen | `test_gated_candidate_fit_apply_persists_and_refreshes_ranking_end_to_end` |
| Dramaturgie-Fit | keine Fit-Aktion | Bewusster Ausschluss: Dramaturgie-Urteile haben keine implementierte Fit-/Gewichtssemantik | `HearingFitDialog`-Modusnachweis; Workflow-/Schema-Tests |

`rate_transitions.py transition-ratings-report --file --seed` ist ein read-only Entwicklerbericht für Deep-Feature-Analyse; er hat keine eigene native GUI-Aktion. **Messdiagnosen anzeigen** ist eine andere Funktion: sie zeigt Messungen analysierter Tracks (`hpg_core.measurement_panel`) und ist kein Ersatz für `transition-ratings-report`. Keine Training- oder Produktgewichtsänderung wird daraus behauptet.

## Kandidaten-Audit und Blindtest

| CLI | GUI-Ersatz | Status / Sicherheit | Testbelege |
|---|---|---|---|
| `audit_candidate_set.py --set-dir --cache --report` | **Kandidaten-Replay prüfen** | Satz wird aus aktuellem Pfad geladen; Auditbericht wird im Dialog angezeigt und kann exportiert werden. Audit endet vor Fit. | `tests/test_audit_candidate_set.py`; `test_audit_dialog_completion_reports_replay_without_fit` |
| `prepare_dj_blind_test.py --manifest --output-dir --key-output [--source-root]` | **A/B-Blindsatz vorbereiten** | Dialog bietet lokale Referenzen oder portablen Clip-Kopiervorgang; Seed optional; öffentliche Session und privater Schlüssel haben getrennte Pfade/Endungen. Kein Bewertungsimport oder Entblindung behauptet. | `test_blind_form_maps_portable_copy_and_csv_key`; `test_blind_form_rejects_wrong_key_extension`; `test_blind_form_exact_mapping_real_worker_preserves_ordinary_set`; `tests/test_prepare_dj_blind_test.py` |
| Kein entsprechender CLI-Unterbefehl | **A/B-Integrität prüfen** | GUI prüft vorhandene lokale Referenz-JSON oder portable CSV-Session mit separatem Schlüssel read-only. Keine Ratings oder Statistik. | `tests/test_hearing_blind.py`; `tests/test_hearing_browser_integration.py` |

## Verifikationsgrenze

Die Parser-Hilfe wurde direkt ausgeführt für `prepare`, `fit`, `transition-ratings-report`, `hoertest_server`, `prepare_dj_blind_test` und `audit_candidate_set`; `prepare --help` wurde am 11.11.2026 erneut gegen die Tabelle geprüft. Routepfade und Aktionen wurden gegen `tools/hoertest_server.py`, `tools/hoertest_launcher.py`, `hpg_core/hearing_ratings.py`, `hpg_core/hearing_panel.py`, `hpg_core/hearing_workflow.py` und die in den Tabellen genannten Regressionstests abgeglichen. `audit` ist **kein** `rate_transitions.py`-Subkommando; der Kandidaten-Audit ist das separate `tools/audit_candidate_set.py`-Werkzeug.

Die Matrix belegt Implementierung und Testverdrahtung, aber keine vollständige manuelle Audio-/Usability-Abnahme aller Modi. Im aktuellen Frozen-Build (SHA-256 `54109AC5DC376B877912839BD310D6BB55E030910B85ECA619F2CCF7BEB7CD9D`) wurde am 11.11.2026 mit isoliertem AppData und synthetischen WAVs ein vorbereiteter Einzelsatz geöffnet, RAM-Playback gestartet, eine Testnote gespeichert und nach Dialogschluss plus erneutem Öffnen wieder geladen (`Bewertet: 1/1`, `Vorhandene Noten geladen`). Die Testnote wurde anschließend ausschließlich aus dem temporären Fixture entfernt. Das prüft den manuellen Einzelsatz-/Playback-/Save-/Reload-Pfad, nicht die übrigen Modi, Fit, Export, Originalmusik oder musikalische Qualität. Der unabhängige Read-only-Review der Matrix und der Gesamtabschlussreview bleiben offen.
