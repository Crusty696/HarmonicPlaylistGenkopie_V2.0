# Hörtest-Werkzeuge vollständig in HPG integrieren – Umsetzungsplan

> **Historischer Anforderungsplan, Statusstand 11.11.2026:** Die Funktions- und
> Architekturvorgaben bleiben erhalten. Die ursprünglichen Checkboxen und die
> GUI-Matrix stammen aus dem 27.09.2026 und sind nicht vollständig gegen den
> heutigen Code abgeglichen. Sie sind kein aktueller Fertigstellungsnachweis;
> siehe [Entwicklungsbericht](../../STATUSBERICHT_2026-11-11.md).

> **Arbeitsweise:** Aufgaben einzeln prüfen und umsetzen. Die früheren
> `superpowers:*`-Skillverweise sind historische Entwurfsangaben, keine
> aktuellen Projekt-Skills; maßgeblich sind `.agents/skills/hpg-*`.

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
6. Launcher-Inventar: Im sauberen Baseline-HEAD existiert **keine** `tools/hoertest_launcher.py` und keine `Start_Hoertest.bat`/`Hoertest*.bat` (Dateiinventar per `rg --files`). Frühere Launcher-/BAT-Verweise stammen nicht aus diesem verifizierten Checkout und werden daher nicht als Ist-Funktion oder Paritätsanforderung behauptet. Neue App-Aktionen beschränken sich auf nachweislich vorhandene Producer-/Rating-/Audit-/Blindtestfunktionen.
7. Frozen-Dispatch in `main.py`: keine vorhandenen Hearing-CLI-Tool-Dispatches in diesem Baseline-Checkout als App-Integration voraussetzen. Die App muss nachweisen, dass neue intern benötigte Module paketiert starten; CLI-Dateien bleiben optional kompatible Entwicklerwege.

### Verbindliche Werkzeug-zu-App-Matrix

Die Matrix ist gegen `HEAD=37859670a5743d2fe4086194d2e9042f08077444` im isolierten Worktree erstellt. „Neu“ bedeutet, dass es im GUI keinen Ersatz gibt; es darf nicht als bereits implementiert ausgegeben werden. Bestehende Testnamen sind konkrete Regressionen. Neue Tests sind Anforderungen an die Implementierung und müssen vor Produktionsänderungen ergänzt werden.

| Belegtes Werkzeugverhalten | Direkte App-/Service-Aktion | Modus/Grenze | Testbeleg |
|---|---|---|---|
| `rate_transitions.py prepare --modus einzel` rendert Einzelübergänge; `--anzahl`, `--out`, BPM/Energy/Harmonie, `--allow-experimental`, `--seed`, `--nur-genre`, Cache/Workers/Transitiontyp steuern fachlich relevante Fälle | „Satz erstellen → Einzel“; GUI-Konfiguration an bestehenden Producer-Service, Status und Zielpfad anzeigen | nur tatsächlich für Einzel verwendete Optionen aktivieren; kein Überschreiben, Staging+atomarer Publish | Bestand: `test_prepare_einzel_schreibt_faktoren_und_plan_audit_vom_aktiven_kandidaten`, `test_renderfehler_hinterlaesst_weder_partial_noch_ziel`, `test_prepare_wrapper_veraendert_vorhandenen_zielsatz_nicht`; neu: GUI-Konfigurations-Roundtrip und Worker-Lifecycle |
| `prepare --modus kandidaten` erzeugt gerankte Kandidaten; optional `--dreinoten-pilot`; Optionen: Anzahl/Seed/Genre/Cache, `--tracks-einmalig`, `--auswahlprofil`, `--workers`, `--transition-type-modus`, BPM/Energy/Harmonie und Versionsgrenzen, soweit Producer sie annimmt | „Satz erstellen → Kandidaten“ mit nativen Optionen; Dreinoten-Schalter; derselbe `rank_pair_candidates`-/Renderpfad | aktueller Cache erforderlich; fachlich irrelevante Einzel-/Dramaturgieoptionen ausblenden | Bestand: `test_prepare_kandidaten_ruft_das_zentrale_ranking`, `test_prepare_kandidaten_nutzt_explizite_fuenf_gerankte_versionen`, `test_prepare_untererfuellung_publiziert_keinen_teilsatz`, `test_cacheaenderung_verwirft_gesamtes_staging`; neu: vollständige GUI-Optionsabbildung |
| `prepare --modus dramaturgie`: Track-Sequenz, Übergänge pro Variante, maximale Versionen, Strategy-/Parameter-Matrix, optional Genre/Seed/Cache/Worker gemäß Parser | „Satz erstellen → Dramaturgie“ mit eigener Sequenz-/Variantenkonfiguration | kein Kandidaten-Replay-Audit vortäuschen; kein Fitmodus für Dramaturgie behaupten | Bestand: `test_dramaturgie_matrix_ist_exakt_aus_strategies_und_parameteralternativen`, `test_prepare_dramaturgie_bindet_snapshot_context_plan_manifest_und_csv`, `test_prepare_dramaturgie_finale_pruefung_bleibt_fail_closed`; neu: GUI-Konfiguration und Schema-Fortsetzung |
| Server GET `/`, `/index.html`, `/reihenfolge`, `/noten`, `/daten`, `/daten-dramaturgie`, `/clips/...` inkl. Range; POST `/note`, `/bester`, `/transition-note`, `/dramaturgie-note` | nativer Hörtest-Player, Clipnavigation, Speichern/Ändern/Löschen, Bestwahl, alle modusspezifischen Bewertungsdimensionen; gleicher Parser-/Merge-Service; optional Serverstart für Remote | Loopback-only; vorhandene CSV-Schemas und explizite Null-Löschung bewahren; niemals fremde Portprozesse beenden | Bestand Server u. a. `test_dramaturgie_server_liefert_reihenfolge_und_speichert_urteile_getrennt`, `test_post_unbekanntes_paar_ist_keine_falsche_erfolgsmeldung`, `test_kandidaten_note_loescht_nur_mit_explizitem_null_und_bereinigt_wahl`, `test_parallele_noten_gehen_nicht_verloren`; neu: native GUI → identischer fachlicher CSV-Zustand für Einzel/Kandidat/Dreinoten/Dramaturgie |
| `audit_candidate_set.py --set-dir --cache --report`: Kandidatensatz gegen exakten Cache/Manifest/Render/Audit prüfen, Report atomar schreiben | „Kandidaten validieren/auditieren“; strukturierte Befunde und Reportpfad darstellen | nur Kandidaten; Report darf nicht existieren/mit Satz oder Cache kollidieren; read-only bzgl. Satz/Cache | Bestand: `tests/test_audit_candidate_set.py` insbesondere `test_vollstaendiger_stretch_fall_ist_read_only`, `test_manifest_cache_fingerprint_muss_exakt_stimmen`; neu: Service-/GUI-Ergebnis und Reportkollision |
| `fit --modus einzel --dir [--seed] [--genre...]`: menschliche Noten → Diagnose/`gewichte.json` | „Auswertung → Einzel-Fit“; Bericht laden, Stichprobe/Unsicherheit anzeigen | Entwurf/Diagnose; ändert aktive Gewichte nicht | Bestand: `test_datenlage_zu_duenn_bei_vierzig_bewertungen`, `test_gewicht_nur_fuer_faktoren_deren_intervall_die_null_nicht_enthaelt`; neu: GUI bindet angezeigten Status an Ergebnisdatei |
| `fit --modus kandidaten --dir --cache --audit-report [--seed] [--genre...]`: Satz-/Cache-/Auditbindung, vollständige Ratings, Holdout/Gates; atomarer Präferenz-Apply oder Entwurf; optional Dreinoten-Bericht | „Auswertung → Kandidaten-Fit“; erfolgreicher gebundener Audit zwingend, Bericht/Vorschau, explizite Apply-Bestätigung, Ranking-Refresh | nur bei allen bestehenden Gates; Fit ist kein Audio-LLM-Training | Bestand: `test_fit_bindet_nichtleeren_erfolgsreport_an_manifest_csv_wav_cache_und_build`, `test_fit_verwirft_gueltigen_satzwechsel_waehrend_fit`, `tests/test_candidate_preferences.py`, `tests/test_e2e_kandidaten_app.py::test_happy_path_publiziert_erst_vollstaendiges_ergebnis`; neu: Zustimmung/Abbruch/Ranking-Refresh |
| Blindtest-Preparierer prüft Manifest/Clips und erzeugt neutrale öffentliche Session plus separaten geheimen Schlüssel | „Blindtest vorbereiten“; Quelle, Ziel und separater Schlüsselpfad ausdrücklich auswählen | vorhandenes Werkzeug bietet keine Rating-, Entblindungs- oder Statistikfunktion | Bestand: `test_prepare_copies_neutral_clips_and_separates_key`, `test_prepare_refuses_to_overwrite_existing_session`, `test_prepare_rejects_clip_outside_manifest_root`; neu: GUI-Pfade und keine Schlüssel-Leaks |
| Kein Launcher/BAT im sauberen Baseline-Checkout; Webserver-CLI existiert in `tools/hoertest_server.py` | kein Launcher-Verhalten erfinden; App-intern wählen/öffnen/stoppen nur eigene optional gestartete Serverinstanz | „fremde Prozesse beenden“ ist keine verifizierte Ist-Funktion und wird nicht migriert | neu: Schutz vor fremder Portbelegung; `tools/hoertest_server.py` Vertragstests |
| `HPG.spec` paketiert aktuell `main.py` plus fest gelistete Hidden Imports/Assets; neue importierte Module müssen Frozen-Analyse bestehen | Desktop-Ablauf direkt in der HPG; CLI nur als kompatibler Entwickleradapter | keine Abhängigkeit des regulären App-Betriebs von externem `python.exe` oder Projektpfad | neu: Frozen-Import-/Smoke-Tests für jeden intern benötigten Service |

**Prepare-Optionen, einzeln am Parser und an `befehl_prepare*` in `tools/rate_transitions.py` abgeglichen:**

| CLI-Option | Einzel | Kandidaten | Dramaturgie | GUI-Vertrag/Test |
|---|---|---|---|---|
| `--anzahl` | Zahl zu rendernder Paare/Clips | Zahl vollständiger Paare | nicht verwendet | Modusabhängige Anzahl/Limit; `test_hearing_prepare_options_roundtrip_by_mode` |
| `--out` | Pflicht-Ziel, atomare Veröffentlichung | Pflicht-Ziel, atomare Veröffentlichung | Pflicht-Ziel, atomare Veröffentlichung | Dialog „neuer, nicht existierender Zielordner“; `test_hearing_prepare_refuses_existing_target_without_changes` |
| `--bpm-toleranz` | Ranking/Gates/Render | Ranking/Gates/Snapshot | Poolfilter und Playlist-Scoring | Numerisches validiertes Feld; Roundtrip |
| `--energy-direction` | Kandidatenpaar-Auswahl und Renderplan | Ranking/Snapshot | nicht verwendet; Dramaturgie-Strategien folgen ihren eigenen festen Varianten | Auswahl auto/up/down/maintain nur Einzel/Kandidat; Roundtrip |
| `--harmonic-strictness` | im Einzel-Producer nicht gelesen | im Kandidaten-Scoring-Snapshot eingefroren | nicht verwendet | nur Kandidatenfeld; Manifest/Audit Regression |
| `--allow-experimental` | im Einzel-Producer nicht gelesen | im Kandidaten-Scoring-Snapshot eingefroren | nicht verwendet | nur Kandidatenfeld; Manifest/Audit Regression |
| `--cache` | Track-Lader nutzt angegebenen Cache | strikter Cache-Fingerprint und Track-Lader | strikter Cache-Fingerprint und Track-Lader | Cache-Auswahl fortgeschritten; nur existierende validierte DB |
| `--seed` | deterministische Maximin-Auswahl | deterministische Auswahl/Clipreihenfolge | Parser vorhanden, in Dramaturgie-Implementierung nicht gelesen | Für angewandte Modi; Dramaturgie deaktiviert mit Erklärung; bestehende deterministische Tests |
| `--nur-genre` | Vorfilter | Kandidatenfilter | nicht gelesen | Nur Einzel/Kandidat |
| `--modus` | `einzel` Dispatcherzweig | `kandidaten` Dispatcherzweig | `dramaturgie` Dispatcherzweig | vierter Modusfehler; Modus-GUI-Test |
| `--sequenz-tracks` | nicht gelesen | nicht gelesen | Trackpool-Größe | nur Dramaturgie |
| `--uebergaenge-pro-variante` | nicht gelesen | nicht gelesen | renderbare Übergänge je Variante | nur Dramaturgie |
| `--max-versionen-pro-paar` | nicht gelesen | begrenzt aktive gerenderte Ränge je Paar | nicht gelesen | nur Kandidat |
| `--dreinoten-pilot` | nicht gelesen | aktiviert Drei-Noten-Schema | nicht gelesen (Dramaturgie nutzt separates Sequenzschema und eigene Übergangsnoten) | nur Kandidat; Schema-Kompatibilitätstest |
| `--tracks-einmalig` | nicht gelesen | verwirft Paare mit bereits benutztem Track | nicht gelesen | nur Kandidat |
| `--auswahlprofil` | nicht gelesen | lädt lokales Profil, beeinflusst Reihenfolge/Selektion | nicht gelesen | Kandidatenmodus; Profilpfad klar als lokale Eingabe gekennzeichnet |
| `--workers` | nicht gelesen | Parallelität der Kandidatensuche (1–4) | nicht gelesen | nur Kandidaten; kontrollierte Workergrenzen |
| `--transition-type-modus` | nicht gelesen | `kontrolliert` oder produktive Typentscheidung | nicht gelesen | nur Kandidaten; Manifest-/Replay-Tests |

Nicht gelesene Parser-Optionen werden im jeweiligen GUI-Modus nicht angeboten, weil sie dort wirkungslos wären. Gemeinsame `prepare`-Optionen `--bpm-toleranz`, `--energy-direction`, `--seed`, `--cache` sind nur dann anwendbar, wenn die jeweilige Implementierung sie tatsächlich liest; alle Felder erhalten konkrete Modustests. Fit-Optionen `--dir`, `--seed`, wiederholtes `--genre`, `--modus`, Kandidaten-`--cache`, Kandidaten-`--audit-report` erhalten getrennte Fit-Formulare; `--genre` wird bei Kandidaten bewusst nicht als Nutzerfilter ausgegeben, wenn der Code es ignoriert.

**Verbindliche Serviceverträge für die Umsetzung (alle neu, Qt-frei; der Ist-Code hat diese App-Service-APIs noch nicht):**

- `hpg_core.hearing_workflow.create_set(config: PrepareConfig, progress: Callable[[Progress], None] | None = None) -> PrepareResult`: validiert Modus/Optionen/Ziel vor Start; dieser Service besitzt genau eine sibling-staging-/atomare Publish-Grenze und ruft darin die unpublizierenden Producer-Innereien `_befehl_prepare_intern`, `_befehl_prepare_kandidaten_intern`, `_befehl_prepare_dramaturgie_intern` mit staging-Ziel auf. CLI-Wrapper delegieren an den Service; `_prepare_atomar` wird auf denselben Service umgestellt/als kompatible Hülle erhalten, aber keine verschachtelte Staging-Ebene. Ergebnisfelder `mode`, finaler `output_dir`, `clip_count`, `pair_count`, `manifest_path`, `warnings`; Fehler `HearingValidationError`, `HearingTargetExistsError`, `HearingOperationError`. Keine UI-Aufrufe von `argparse.Namespace` als dauerhafte API.
- `hpg_core.hearing_workflow.validate_set(path: Path, *, cache_path: Path | None = None, report_path: Path | None = None) -> SetValidationResult`: Kandidat: `audit_candidate_set.audit_set(set_dir, cache, render=...)`, Report über bestehende atomare Reportfunktion; Dramaturgie: `hoertest_server.validiere_dramaturgie_satz(path, pruefe_dateien=True)` plus Manifest/CSV-Schema; Einzel: **neu zu implementierender** strikt read-only Validator für Manifestversion/Dateiliste, kanonische CSV-Schemas/IDs/Clipcontainment und WAV-Existenz/-Hash gemäß vorhandenem Manifest. Gibt `mode`, `valid`, `errors`, `warnings`, `audit_report_path` aus; unpassende Cache-/Reportparameter werden kontrolliert abgelehnt. Es wird ausdrücklich nicht behauptet, ein Einzelvalidator existiere bereits.
- `hpg_core.hearing_workflow.apply_rating(path: Path, rating: RatingCommand) -> RatingResult`: `RatingCommand` identifiziert schemaabhängige `pair_id`/`clip_id`/dimension/value/best choice; ein zentraler Modusrouter validiert Werte, erlaubt 1–5 und nur schemaexplizites Löschen, prüft „best“ Regeln, liest/merged/schreibt die betroffenen CSVs atomar. Er nutzt und ggf. extrahiert die bestehenden `hoertest_server.merge_bewertungen`, `merge_kandidaten_bewertung`, CSV-Schema- und Write-Helfer; kein HTTP-/Subprozess. `RatingResult` gibt nur persistierten Zustand/Completion zurück. GUI und POST-Handler rufen denselben Kern auf.
- `hpg_core.hearing_workflow.run_fit(config: FitConfig, *, confirm_apply: bool = False) -> FitResult`: GUI muss vor Aufruf produktiven Kandidaten-Apply bestätigen; bei false wird nur ein Entwurf/Diagnose angefordert und aktive Präferenzen bleiben bitgleich. Nutzt bestehende Einzel-/Kandidaten-Fitlogik in `rate_transitions._fit`/`befehl_fit_kandidaten`, Audit-/Cache-Binding und `candidate_preferences.merge_user_preferences_atomically`; `FitResult` nennt Bericht-/Entwurfspfad, Gates, `applied`, betroffene Genres. Vorhandene CLI ruft denselben Fit-Kern mit ihrem bisherigen nicht-GUI-Vertrag auf; CLI-Paritätstests erhalten Datei-/Exitcodeverhalten.
- `hpg_core.hearing_workflow.prepare_blind_session(config: BlindSessionConfig) -> BlindSessionResult`: ruft bestehende `prepare_dj_blind_test.prepare(manifest, output_dir, key_path, seed, source_root)` auf; Ergebnis enthält öffentliche Session- und privaten Schlüsselpfad und validierte Zeilenzahl, niemals Schlüsselinhalt.
- `hpg_core.hearing_workflow.load_session(path: Path) -> HearingSession`: validiert/liest einen Satz in GUI-taugliche immutable Clip-/Variant-/Rating-Records; Einzel-, Kandidaten-/Dreinoten- und Dramaturgiepfad teilen Parser-/Schema-Router mit `hoertest_server`, ohne Kandidatenfaktoren in Bewertungsansichten offenzulegen.

Service-Tests werden konkret benannt: `tests/test_hearing_workflow.py::test_create_set_routes_modes_and_preserves_cli_artifacts`, `::test_create_set_rejects_existing_target_without_changes`, `::test_validate_set_has_distinct_single_candidate_and_dramaturgy_contracts`, `::test_apply_rating_matches_server_schema_for_each_mode`, `::test_apply_rating_rejects_invalid_or_ambiguous_clear`, `::test_fit_without_confirmation_never_changes_candidate_preferences`, `::test_fit_result_is_bound_to_report_and_preference_state`, `::test_blind_session_keeps_private_key_outside_public_tree`, `::test_load_session_never_exposes_candidate_factors`. Neue GUI-Datei `tests/test_main_window.py` wird im Baseline nicht behauptet vorhanden; sie ist explizit neu anzulegen. Zusätzliche parametrische Assertions pro Prepare-Option-/Modus-Paar erhalten IDs `test_prepare_option_<field>_<mode>` und prüfen `PrepareConfig`-Wert gegen Producer-Aufruf oder deaktivierten Modusgrund. Server-Handler-Regressions prüfen, dass Refactor dieselben Statuscodes/CSV-Inhalte erzeugt.

## Geplante Dateien und Verantwortungen

- **Ändern `main.py`:** Hörtest-Arbeitsbereich, Formulare, Satz-/Moduszustand, native In-App-Bewertung, GUI-Aktionen, QThread/QProcess-Lebenszyklus und verständliche Ergebnisanzeige. Keine DSP-/Fit-Algorithmen hier duplizieren.
- **Neu `hpg_core/hearing_workflow.py` und fokussierte Service-Module (nach Aufgabe 1):** importierbare Producer-/Audit-/Fit-/Blindtest-Orchestrierung ohne Qt, mit typisierten Konfigurationen/Resultaten; die jeweilige bestehende Algorithmik wird dorthin verlagert oder daraus aufgerufen, nicht dupliziert.
- **Ändern Tool-CLI-Dateien:** Parser/CLI bleiben rückwärtskompatible Adapter, die dieselben Services aufrufen. Kein GUI-Subprocess zu diesen CLI-Dateien für lokale Set-Erstellung, Audit, Fit oder Blindtest.
- **Optionaler Remote-Server:** darf als App-eigener Prozess für Smartphone-Browser bedient werden; nicht nötig für native Bewertung am Desktop.
- **Neu `tests/test_main_window.py`:** Baseline besitzt nur `tests/test_gui_display.py`; neue Hearing-GUI-Widget-/Signal-/Qt-Lifecycle-Tests kommen in eine neu anzulegende Datei.
- **Neu/erweitern Tests für Hearing-Services und Tools:** Verträge, Schemas, nicht-destruktive Fehlerpfade, Fit-Bindung und blindes A/B.
- **Ändern `docs/QUICK_START.txt` oder passende Nutzerdoku:** nur nach real implementierter UI; CLI-Bedienung als optionales Diagnose-/Entwicklerverfahren kennzeichnen.
- **Nicht Teil ohne gesonderte Anforderung:** neue Blindtest-Rating-/Entblindungs-/Statistikpipeline; das heutige Blindtesttool kann nur Sessions vorbereiten.

## Aufgaben

**Ausführungsreihenfolge und Parallelität:** Aufgabe 1 ist zwingendes Gate. Danach Aufgaben 2–6 als getrennte Teilbereiche planen; parallel dürfen nur unabhängige Code-/Testarbeitspakete laufen. `main.py`-Änderungen werden serialisiert (ein Integrator), weil Panels, Worker-Lifecycle und Slots dort zusammenlaufen. Tool-/Service-Tests und Frozen-Packaging-Inventar können unabhängig vorbereitet werden. Nie zwei volle pytest-Läufe parallel. Pro Aufgabe: vorab unabhängiger Read-only-Wächter, gezielter Test, Wächter-Findings beheben, Regression; nach Integration der vollen Änderung Abschluss-Wächter und vollständige Suite. Kein Commit ohne user/repo-prozessgemäße Freigabe.

**Testdateien:** vorhandene Regressionen: `tests/test_rate_transitions.py`, `tests/test_hoertest_server.py`, `tests/test_audit_candidate_set.py`, `tests/test_prepare_dj_blind_test.py`, `tests/test_gui_display.py`, `tests/test_candidate_preferences.py`, `tests/test_pair_candidates.py`, `tests/test_e2e_kandidaten_app.py`. Neu anzulegen: `tests/test_hearing_workflow.py` und `tests/test_main_window.py`.

### Task 1 / Aufgabe 1: Tool-zu-App-Abdeckungsmatrix und GUI-Informationsarchitektur

**Dateien:** keine Produktionsänderung; Plan-/Inventargrundlage, danach Dokumentation.

**Schnittstellen:** Liefert Tabelle `Werkzeugfunktion → bestehende API/CLI → GUI-Aktion → Testbeleg`, einschließlich aller Optionen oben.

- [ ] Jeden CLI-Parser, Server-Endpunkt, Satzvalidator, Auditor und Fit-Ausgang direkt gegen aktuellen Code aufnehmen.
- [ ] Für jede Option als GUI-Feld, bewusst ausgeschlossene Entwickleroption oder nicht unterstützten Punkt klassifizieren; Ausschluss begründen und dem Nutzer sichtbar machen.
- [ ] Festlegen, wie Satzliste, Typ, Parameter, Status, Bewertung öffnen, Audit, Fit-Bericht und Blindtest im bestehenden QUALITY-Bereich erreichbar sind.
- [ ] Wächter-Read-only-Prüfung des Inventars; offene Paritätslücken vor Implementation schließen.

**Abnahmekriterium:** Commitfähige Paritätsmatrix benennt für jeden existierenden CLI-Parameter, Satztyp, Bewertungsdimension, HTTP-Routenverhalten und Fit-Ausgang den App-Ersatz sowie konkrete Testfunktion(en). Nicht vorhandene Launcher-/BAT-Funktionen werden ausdrücklich nicht als Ist-Verhalten behauptet. Toolverhalten, das absichtlich nicht migriert wird, steht explizit als nicht benötigter Admin-/Diagnosepfad darin. Auflistung ist per `--help`, Route-Handler und Erfolgs-/Fehlerpfad im Code belegt.

**Mindest-Tests für Matrix:** Parser-Optionstests in vorhandener `tests/test_rate_transitions.py`; Route-/Schema-Matrix in vorhandener `tests/test_hoertest_server.py`; Audit-Vertrag in vorhandener `tests/test_audit_candidate_set.py`; In-App-Auswahl/Actions/Signals in neu anzulegender `tests/test_main_window.py`; Serviceverträge in neu anzulegender `tests/test_hearing_workflow.py`. Neue parametrische Assertions `test_prepare_option_<field>_<mode>` pro wirksamem Feld/Modus prüfen den tatsächlichen Producer-Aufruf; für nicht verwendete Flags prüfen sie deaktivierte UI und erklärten Grund. Die IDs und erwarteten Werte sind die oben aufgeführte Optionsmatrix; dieselben Testfälle vergleichen CLI- und Service-Artefaktschema.

### Task 2 / Aufgabe 2: Satzverwaltung und Erzeugung aller Satztypen

**Dateien:** `main.py`, falls erforderlich Service-Schnittstelle(n), GUI-/Service-Tests.

**Schnittstellen:** GUI-Formular erzeugt validierte Konfiguration für Einzel, Kandidaten, Dreinoten und Dramaturgie; QThread ruft importierbaren Hearing-Service direkt auf und emittiert Fortschritt/Endergebnis. CLI ruft denselben Service auf.

- [x] Tests für Moduswahl und vollständige Option-zu-Argument-Zuordnung schreiben; Widgets begrenzen Eingaben, Auswahlprofil wird vor Konfiguration validiert und Service-Rangegrenzen werden vor Producerstart geprüft. Belege: `tests/test_hearing_panel.py` Modus-/Optionsmatrix, `tests/test_hearing_workflow.py::test_config_rejects_invalid_values_before_staging`.
- [x] GUI-Werte über `HearingPrepareDialog` → `PrepareConfig` → Producer-Namespace für Einzel, Kandidaten, Dreinoten und Dramaturgie durchgehend geprüft; deaktivierte Modusfelder und fachlich wirksame Defaults abgebildet. Belege: `tests/test_hearing_panel.py::test_prepare_form_config_and_producer_namespace_parity`, `test_prepare_form_maps_modes_and_disables_ineffective_fields`, `tests/test_hearing_workflow.py::test_namespace_has_exact_ui_to_parser_mapping` (22 gezielte Tests bestanden, 11.11.2026).
- [x] Auswahlprofil kann über Datei-Dialog gewählt werden; JSON-Vertrag wird vor Analyse/Workerstart validiert und vom Producer erneut geprüft. Belege: `tests/test_hearing_panel.py::test_prepare_form_selection_profile_file_picker`, `test_prepare_form_rejects_bad_selection_profile_before_config_or_worker`.
- [ ] Satzverwaltung mit Suche/Auswahl, Erkennung des Formats und Fortschritt für vorhandene Ordner ergänzen.
- [x] Erzeugungsoptionen aus dem CLI zugänglich machen: Anzahl, Genre, BPM/Energy/Harmonie, Seed, Track-Einmaligkeit, Auswahlprofil, Worker, Transitiontyp, Versionslimit und Dramaturgie-Parameter; GUI→Service-Zuordnung für alle vier Modi getestet. Cache und Zielpfad bleiben absichtlich von der App verwaltet.
- [ ] Bestehende Sätze nur lesend öffnen; Service erzeugt neue Ausgabe in genau einer atomaren sibling-staging-Grenze, validiert und veröffentlicht; vorhandene Ziele nie überschreiben. Quellreferenz-Sätze verwenden `hpg_core.hearing_sources.load_source_session` mit getrennten Modi `_single_metadata`, `_candidate_metadata` und `_dramaturgy_metadata`. Legacy-Einzel-CSV nutzt `hpg_core.hearing_calibration.validate_set` für Schema, eindeutige Paar-IDs, 1:1-Bindung und Wertebereiche; der Clips-Unterordner bleibt dabei unberührt.
- [ ] GUI-Fortschritt/Abbruch/QThread-Cleanup testen; Einzel-CSV mit `validate_set`, Quellreferenz-Einzel, Kandidat und Dramaturgie mit ihren jeweils eigenen Validatoren lesbar.

**Abnahmekriterium:** Die GUI kann jeden unterstützten Satzmodus samt fachlich relevanten Parametern erzeugen und bestehende Läufe fortsetzen, ohne CLI-Bedienung.

**Testbelege:** parametrisiert pro `modus` und Optionsgruppe; CLI-Service und GUI erzeugen denselben Manifest-/CSV-Vertrag; Zieldatei existiert/Permission denied/fehlende Tracks/kein Kandidatenpaar bleiben ohne Teilpublikation; cancel und close lassen Worker vollständig enden. Einzel nutzt den neuen `validate_set`-Einzelvalidator, Kandidaten/Dramaturgie ihre vorhandenen Validatoren. Bestehende Producer-Tests bleiben maßgebliche Algorithmen-Regression.

### Task 3 / Aufgabe 3: Native In-App-Bewertung, Remote-Browser und Satzfortsetzung

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

### Task 4 / Aufgabe 4: Audit/Validierung und vollständige Fit-Vorprüfung

**Dateien:** `main.py`, falls erforderlich Audit-Service-Schnittstelle, GUI-/Audit-Tests.

**Schnittstellen:** Kandidaten-Audit-Service bindet Satz-/Cache-/Quell-/Build-Fingerprints und liefert einen strukturierten RAM-Receipt; Dramaturgie nutzt `hoertest_server.validiere_dramaturgie_satz`; Source-Einzel nutzt `load_source_session`/`_single_metadata`, Legacy-Einzel `hearing_calibration.validate_set`. Diese Prüfungen bleiben getrennt; kein Modus wird als Kandidaten-Replay-Audit ausgegeben. GUI ruft importierbare Services direkt auf, nicht per CLI-Subprocess.

- [x] Kandidaten-Audit-Erfolg und -Fehler, Binding, Cachefamilie/WAL, Mutationen während Audit, Source-/Legacy-Einzelvalidator und isolierter Audit-Fit sind durch `tests/test_audit_candidate_set.py`, `tests/test_hearing_calibration.py`, `tests/test_hearing_sources_phase_v2.py` und `tests/test_hearing_ratings.py` abgedeckt; keinen Kandidatenbericht ohne erfolgreichen RAM-Audit akzeptieren.
- [x] Kandidaten-Fit ist UI-seitig bis zur vollständigen Ratingprüfung freigegeben und Service-seitig an erfolgreiches Audit-Receipt und Fit-Binding gebunden; Apply validiert und prüft Binding erneut.
- [x] Audit verändert keine Originalclips, Ratings, Quellen oder Cache; Kandidaten-Audit rendert in RAM und verifiziert Fingerprints.
- [x] Separater Auditdialog zeigt erfolgreiches Replay, ausdrücklich nicht ausgeführten Fit, Cache-/Build-/Quell-/Datei-Bindung und Integritätsdigest; Audit- und Fit-Completion bleiben getrennt und Close-sicher. Geprüft in `tests/test_hearing_calibration.py` und `tests/test_hearing_browser_integration.py`.
- [ ] Nachweis der Report-Kollision/Publikation nur dann ergänzen, wenn ein persistenter Auditbericht weiterhin Produktanforderung ist; aktueller nativer Pfad verwendet gebundenen Vorschlag und optionalen Export.

**Abnahmekriterium:** Kandidaten-Fit kann nicht ohne passenden erfolgreichen Audit starten. Für Modi ohne diesen Audit existiert eine dokumentierte, getestete, modusspezifische Freigabeprüfung; UI kennzeichnet deren geringeren/anderen Prüfstatus klar.

**Testbelege:** `tests/test_audit_candidate_set.py`, `tests/test_hearing_calibration.py`, `tests/test_hearing_sources_phase_v2.py`, `tests/test_hearing_ratings.py` prüfen RAM-Receipt, Bindung, Mutation, modusspezifische Schema-Prüfung und den Nichtschreibvertrag. Der aktuelle Vertrag speichert keinen separaten Auditbericht; Auditdetails liegen im Integritäts-gebundenen Vorschlag und optionalen Export.

### Task 5 / Aufgabe 5: Fit, Trainingsergebnis und transparente Übernahme

**Dateien:** `main.py`, gegebenenfalls Service-Schnittstelle, Fit-/GUI-Regressionstests.

**Schnittstellen:** Einzelmodus liefert gebundene `gewichte.json`-Diagnose als Entwurf; Kandidatenmodus liefert vollständigen `CandidateFitResult`, Gates, Audit-Binding und atomaren Apply-Status. Produktive Präferenzen ändern sich nur nach ausdrücklicher Bestätigung; Ranking-Refresh verwendet danach neuen Scoring-Context.

- [x] Einzel-/Kandidaten-Fit, Seed/Einzel-Genre, schlechte Datenlage, Identifizierbarkeit, Gateablehnung und atomare Präferenzpersistenz besitzen bestehende Kern- und fokussierte GUI-Tests; die vollständige neue Fit-Matrix für alle Modi bleibt offen.
- [x] Einzel-Fit zeigt Stichprobe, Klassen, Datenlage/Grund, aktive Faktoren, Koeffizienten und Bootstrapintervalle als ausdrücklich inaktiven Entwurf.
- [x] Kandidaten-Fit zeigt Genre-Gates, Holdout/Train, Baseline, AUC, Identifizierbarkeit, Intervalle, neue Gewichte und Rangfolge; vollständiger maschinenlesbarer Fitbericht bleibt sichtbar/exportierbar.
- [x] Explizite Apply-Bestätigung, atomare Persistenz, Cache-Reset, neuer Scoring-Context, Playlist-Neuberechnung und Fehlerstatus sind durch vorhandene Services und fünf gezielte MainWindow-Regressionen geprüft.
- [ ] GUI-Modus-/Option-Matrix vervollständigen: Seed/Genre und alle Satztypen abbilden; Kandidaten-`--genre` nicht als wirkungsvollen Filter anbieten; jede wirksame Option gegen CLI-Serviceausgabe testen.
- [x] Dreinoten-Pilot anhand des CSV-Schemas im Fitdialog sichtbar kennzeichnen; Fit bleibt Vorschlag, bestandene Gates brauchen vor Apply eine zweite Ja-Bestätigung. Ja/Nein, Modusübergabe, deaktivierte irrelevante Genreoptionen/Audit-Seed und unveränderten Normal-Kandidatenpfad in `tests/test_hearing_browser_integration.py`; Dialogtext in `tests/test_hearing_calibration.py` geprüft (10 gezielte Tests bestanden, 11.11.2026).
- [ ] Produktive Apply-Zustimmung mit realem gültigem gatebestandenem Kandidatenvorschlag einschließlich Ja/Nein, Persistenzfehler und Ranking-Rangwirkung in isolierter E2E-Fixture vollständig nachweisen.
  - [x] Ja/Nein mit demselben digest-validierten Vorschlag, echtem Apply-Worker, isolierter atomarer Persistenz, echtem Preference-Reload und ausgelöstem Ranking-Refresh; absichtlicher Schreibfehler bleibt `persisted=False`.
  - [ ] Statistisch real bestandenes Genre-Gate mit echten Fitdaten nachweisen; die aktuelle E2E setzt nur den Gate-Ausgang deterministisch ein und belegt daher nicht die Gate-Qualität.
- [x] Dreinoten-Gates/Deep-Feature-Abblation je Featuregruppe in der Ergebnisübersicht lesbar darstellen: Status/Grund, Train-/Holdout-Clips und Cluster, Baseline-/erweiterte AUC samt Delta und explizit kein Einfluss auf den Produkt-Score; GUI-Test in `tests/test_hearing_calibration.py`.

**Abnahmekriterium:** UI nennt operation „Präferenz-Fit/Kalibrierung“, nicht Modelltraining. Nutzer kann belegen, welche Ratings einflossen, welcher Bericht entstand und ob aktive App-Gewichte wirklich geschrieben und vom Ranking neu geladen wurden.

**Testbelege:** bestehende `tests/test_rate_transitions.py` Fitfälle plus `tests/test_candidate_preferences.py` atomare Persistenz und `tests/test_pair_candidates.py`/`tests/test_e2e_kandidaten_app.py` Rangwirkung. Neue GUI-Tests prüfen exakte Resultatdatei-/Statusbindung, Zustimmung Nein/Ja, Fehler beim Schreiben und Ranking-Refresh. Fit ist nicht abbrechbar, sofern der bestehenden CLI kein kooperatives Cancel-Vertrag hinzugefügt und getestet wurde; GUI muss währenddessen Schließen sicher behandeln.

### Task 6 / Aufgabe 6: Blindtest-Session-Erstellung in der App (nur Ist-Funktion)

**Dateien:** `main.py`, `tools/prepare_dj_blind_test.py` (nur Service/API falls nötig), Blindtest-/GUI-Tests.

**Schnittstellen:** GUI ruft einen intern importierbaren Blindtest-Service mit validiertem Manifest, erlaubtem Quellroot, neuem Sessionordner und getrenntem Schlüsselpfad auf; CLI ruft denselben Service auf. Ergebnis: öffentliche `blind_session.csv`/Clips und private Zuordnung. Bewertungsimport/Entblindung sind keine vorhandenen Werkzeugfunktionen.

**Implementierungsnachweis 11.11.2026:** Der Qualitätsbereich bietet lokale
Referenzen (bisheriger Default) oder portablen Export. Der Worker ruft
`tools.prepare_dj_blind_test.prepare` direkt auf. Er kopiert nur die Manifest-
Übergangsclips unter neutrale WAV-Namen; Originaltracks bleiben unverändert.
Die CSV-Integritätsprüfung bindet öffentliche Session, getrennten Schlüssel,
Zuordnung, PCM-16-WAVs, SHA-256 und Pfadcontainment. Der Export kann während
Hashing und 65.536-Frame-Audioblöcken kooperativ abgebrochen werden; unpubliziertes
Staging wird entfernt. Schlüsselpublikation nutzt atomaren No-Clobber-Link.
Nach letzter Änderung bestanden 11 fokussierte Tests; der letzte Volltest hatte
6.599/6.600 Tests grün, ein paralleler Smoke-Subprozessfehler bestand isoliert.
Der isolierte Frozen-Build samt Native-Smoke (`ok=true`) bestand.

- [ ] Tests für Pfadcontainment, doppelte/identische Clips, Dauer-/Samplerateabweichung, vorhandene Session und getrennten Schlüssel schreiben.
- [ ] App führt Prüfung und Session-Erstellung aus; öffentliche Session und geheimer Zuordnungsschlüssel bleiben physisch getrennt.
- [ ] App zeigt klare Ausgabeorte und trennt öffentliche Session von privatem Schlüssel; Schlüssel darf nie in öffentlichem Sessionordner, Browser oder Logs landen.
- [x] Nutzer kann Dateien der Session auf Integrität prüfen. Keine Entblindung oder Statistik behaupten, weil das Werkzeug diese Funktion nicht implementiert.
- [ ] Optionaler Folgeschritt nur nach separater Spezifikation: Import `validation/dj_blind_test_template.csv`, Zuordnungsprüfung per Schlüssel, Ausschlussregeln und aggregierte Auswertung. Nicht ungefragt mit Trainingslabels/Präferenz-Fit vermischen.

**Abnahmekriterium:** Die vorhandene Blindtest-Session-Erstellung ist per App vollständig verfügbar; Plan verspricht keine nicht existente Bewertung/Auswertung. Eine spätere Entblindungsfunktion erhält eigenes Konzept und Tests.

**Testbelege:** bestehende `tests/test_prepare_dj_blind_test.py` bleibt Producer-Vertrag; GUI-Tests prüfen nur sichere Parameterweitergabe, unabhängige Zielpfade und Fehlerdarstellung. Kein Real-Musiklauf als automatisierter Test und kein geheimes Mapping im Screenshot/Log.

### Task 7 / Aufgabe 7: Werkzeugparität, Packaging und Ende-zu-Ende-Verifikation

**Dateien:** Tool-/GUI-Tests, Packaging-/Nutzerdokumentation, gegebenenfalls `main.py`.

**Schnittstellen:** Paritätsmatrix aus Aufgabe 1 plus reproduzierbare end-to-end Session.

- [ ] Automatisierte Vertrags- und Golden-Master-Tests vergleichen CLI und GUI-Serviceausgaben für gleiche Testdaten/Parameter sowie Rundreisen jedes CSV/JSON-Schemas.
- [x] Frozen-Build **nicht mit `build.bat`** ausführen: dieses Skript löscht `build/`, `dist/` und die Root-EXE, installiert/upgradet Packages und überschreibt die EXE. Stattdessen vorhandene Artefakte zuerst lesend inventarisieren und unberührt lassen; einmaliges eindeutiges Scratch-Verzeichnis außerhalb Repo und Original-Checkout anlegen, dann direkt mit dem bereits vorhandenen Python-3.12-Interpreter `C:\Users\david\Documents\HarmonicPlaylistGenerator_V2.0\venv312\Scripts\python.exe -m PyInstaller --noconfirm --distpath <scratch>\dist --workpath <scratch>\work HPG.spec` ausführen (kein `--clean`, da nur der neue Workpath verwendet wird). Damit sind existierende Buildziele nicht im Wirkpfad. Gebautes Ergebnis mit `--hpg-native-smoke <report.json>` und isoliertem `HPG_SMOKE_ROOT` prüfen; der Smoke-Dispatch läuft vor der GUI-Initialisierung, importiert die nativen Hearing-Services, erzeugt RAM-Audio und prüft Spawn-/Fit-/Cleanup-Verträge ohne Nutzer-Cache oder Musikdateien. Scratch-Pfad und EXE-Hash im [Entwicklungsbericht](../../STATUSBERICHT_2026-11-11.md) dokumentieren.
- [ ] E2E ohne Nutzerdaten mit isoliertem Temp-Cache/Fixtures: jeden Satztyp erstellen → schema-validieren → nativ bewerten → schließen/fortsetzen → Fit/Entwurf prüfen; Kandidatensatz zusätzlich auditieren → erlaubten Apply testen → Präferenzwirkung auf Ranking prüfen.
- [ ] Separater manueller Usability-Check: App-Start, lokalen Hörtest in App bedienen, Pause/Wechsel/Speichern/Resume, Fehler verständlich; menschliches Audio-Urteil bleibt explizit außerhalb automatisierter Qualitätsbehauptungen.
- [ ] Unabhängiger Wächter-Read-only-Durchgang vor Umsetzung und Abschlussreview nach Umsetzung, Findings beheben und erneut prüfen.
- [x] Vollständigen Pflicht-Testlauf `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q` und isolierte Build-/Smokeprüfung ausführen; Ergebnis siehe [Entwicklungsbericht](../../STATUSBERICHT_2026-11-11.md).
- [ ] Schnellstart aktualisieren und Zusatzwerkzeug erst dann als optionalen Diagnose-/Entwicklerweg bezeichnen, wenn die Matrix lückenlos ist.

**Abnahmekriterium:** Alle Inventarpunkte sind über App-Aktionen erreichbar, getestete CLI/App-Parität ist belegt, Gesamt-Testlauf und Packaging-Smokecheck bestehen. Bis dahin gilt das Zusatzwerkzeug weiterhin als erforderlich.

**Frozen-Dispatch-Korrektur:** Der aktuelle Dispatch in `main.py` kennt `rate_transitions.py`, `audit_candidate_set.py` und `hoertest_server.py`; er kennt `prepare_dj_blind_test.py` nicht als `--hpg-tool`. Nach Service-Extraktion braucht lokale GUI-Erstellung keinen Tool-Dispatch. Optionaler Remote-Server braucht einen getesteten App-eigenen Startpfad. CLI-Dispatch kann für Diagnose/Fallback ergänzt werden, ist aber kein Ersatz für direkte Service-Integration.

**Verifikationsbefehle:** gezielte Suiten je Aufgabe mit `venv312\Scripts\python.exe -m pytest <betroffene Testdateien> --tb=short -q --no-cov`; genau ein vollständiger Abschlusslauf `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`. Für Frozen-Verifikation ausschließlich den scratch-isolierten Aufruf aus Aufgabe 7 nutzen; `build.bat` ist für diese Umsetzung ausdrücklich ausgeschlossen, weil es fremde/vorhandene Artefakte löscht oder überschreibt.

## Ergebnis der gründlichen Planprüfung (2026-09-27)

- **Korrigiert – native Verwendung:** vorher schlug der Plan als Kern nur Browserstart vor. Das hätte die eigentliche App weiterhin vom Zusatzwerkzeug/Webserver abhängig gelassen. Jetzt verlangt er natives Bewerten/Abspielen/Speichern/Fortsetzen; Server nur optional für Remote.
- **Korrigiert – Audit-Scope:** `audit_candidate_set.py` ist Kandidaten-spezifisch. Dramaturgie hat `validiere_dramaturgie_satz`; für Einzel muss ein eigener Validator neu entstehen. Keinen Audit für alle Modi vorspiegeln.
- **Korrigiert – Blindtest-Scope:** `prepare_dj_blind_test.py` erzeugt Session und getrennten Schlüssel, aber keine Bewertungs-, Entblindungs- oder Statistikpipeline. Import/Auswertung ist explizit separater, noch nicht beauftragter Umfang.
- **Korrigiert – Lernbegriff:** Einzel-Fit produziert `gewichte.json`, Kandidaten-Fit kann gated `candidate_preferences` aktivieren. Beides ist Präferenzkalibrierung, kein Audio-LLM-Training. Aktive Übernahme muss an tatsächlicher Ausgabe und nachfolgendem Ranking-Reload belegt werden.
- **Korrigiert – Nachweis:** leere CLI-stdout-/mtime-Heuristik ist kein gültiger Fit-Erfolgsbeleg. UI muss strukturierte Berichte/Dateien und tatsächlichen Override-Zustand lesen.
- **Korrigiert – Launcher:** rekursive Laufwerkssuche ist kein bestehendes Launcher-Verhalten; nur explizit gewählte Roots durchsuchen und fremde Prozesse nie beenden.
- **Verbleibend für Umsetzung:** Aufgabe 1 muss für jede Parser-Option/Route konkrete App-Aktion und konkreten Testnamen dokumentieren; Implementierung darf nicht mit dem bisherigen 8-Test-Satz als Vollparitätsbeleg verwechselt werden.
- **Nicht destruktive Nachweise:** existierende Ziele, Satz-/Cache-Bindung, WAL, getrennte Blindtestschlüssel, fremder Portprozess und Fit ohne Zustimmung bleiben Tests.
- **Grenze:** geänderter Plan, keine Feature-Implementierung. Das aktuell sichtbare GUI-Feature deckt noch nicht die gesamte Werkzeugparität.
