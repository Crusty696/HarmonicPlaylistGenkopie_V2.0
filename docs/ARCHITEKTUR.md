# Modulgrenzen und Datenfluss

Die öffentliche API bleibt über `hpg_core.analysis`, `hpg_core.playlist`,
`hpg_core.caching`, `hpg_core.transition_renderer` und `main` erreichbar.
Ausgelagerte Typen werden dort re-exportiert, damit bestehende Verbraucher
und gespeicherte Python-Objekte ihre bekannten Einstiegspunkte behalten.
Neue interne Verbraucher sollen möglichst die zuständigen Module importieren.

| Verantwortung | Zuständiges Modul |
|---|---|
| Qt-Worker für Analyse, Playlist, KI und Render | `hpg_core/app_workers.py` |
| Laufzustände, Fortschrittsabbildung und Meldungstypen | `hpg_core/run_state.py` |
| Navigation, gemeinsame Aktionen und Status | `hpg_core/ui/navigation.py` |
| Atomare Prepare-/Commit-Veröffentlichung und Ressourcenfreigabe | `hpg_core/ui/result_publication.py` |
| Spaltenidentitäten, Titel, Breiten und Tooltips | `hpg_core/ui/playlist_columns.py` |
| Lesende Track-/Übergangsdetails | `hpg_core/ui/track_details.py` |
| Validierte Messdiagnose für beide Ansichten | `hpg_core/measurement_panel.py` |
| Unveränderliche Result-Snapshots und TransitionPlan | `hpg_core/playlist_results.py` |
| Strategiealgorithmen mit expliziten Bewertungsdiensten | `hpg_core/playlist_strategies.py` |
| Konsistente Kandidatenkettenwahl | `hpg_core/candidate_path.py` |
| Gewichtete Kombination und gemeinsamer Vocal-Abzug | `hpg_core/scoring_primitives.py` |
| Set-Zeiten aus aktiven Übergangsplänen | `hpg_core/set_timeline.py` |
| Qt-freie Techniknamen und Hinweise zum aktiven Kandidaten | `hpg_core/transition_notes.py` |
| Audiomerkmalscache je Track und Fenster | `hpg_core/feature_cache.py` |
| Gemeinsamer Analyseabschluss mit Persistenzvertrag | `hpg_core/analysis_pipeline.py` |
| Reine Prüfung des persistierten Trackvertrags | `hpg_core/cache_validation.py` |
| Plan-zu-Render-Spec und deren Validierung | `hpg_core/transition_spec.py` |

`main.py` enthält weiterhin die konkreten Panels und MainWindow als
Zusammenbau der Anwendung. Die kompatiblen Analyse-/Render-Worker dort binden
die App-Dienste; die Workerimplementierung greift nicht auf Fenster zu.
Der Veröffentlichungsbaustein bekommt Widget-Fabriken vom Fenster und
importiert `main` nicht zurück.

`playlist.py` orchestriert Bewertung und Ergebnisaufbereitung. Die Strategien
bekommen über `StrategyServices` explizit die aktuelle Zielfunktion und
Hilfsfunktionen. Weder Strategiemodul noch Result-Typen importieren die Fassade
zurück. Die Kandidatenbewertung bezieht Genreauflösung aus `genres` und ihre
gemeinsamen Bewertungsgrundlagen aus `scoring_primitives`.

`analyze_track` übernimmt Eingabeprüfung, Quellidentität und Cachepolitik und
wählt danach `_analyze_rekordbox_path` oder `_analyze_audio_path`. Diese beiden
Funktionen erhalten ihre Eingaben explizit und bleiben wegen ihrer gemeinsamen
DSP-Helfer im Analysemodul. Beide rufen denselben Abschluss auf. `fresh`
persistiert keine Trackdaten, `reuse` übernimmt nur gültige Kernanalysen in den
Cache. Die reine Datenvalidierung öffnet keine SQLite-Verbindung.

Der Renderer erhält seine unveränderten Zeitwerte ausschließlich über
`TransitionClipSpec.from_plan`. Das Spec-Modul lädt kein Audio. Der eigentliche
Renderer behält Decoder, Stretch, Beatprüfung, EQ und Pegelverarbeitung; seine
Ausführung bleibt prozessisoliert. Diese Aufteilung ändert keine musikalischen
Grenzwerte und ist keine musikalische Qualitätsabnahme.

Die Playlist zeigt zunächst Kernspalten. „Alle Messspalten anzeigen“ blendet
die weiteren vorhandenen Spalten ein. „Details anzeigen“ schaltet den rechten
Detailbereich um. Die Auswahl wird über die konkrete Trackinstanz zugeordnet,
damit doppelte Vorkommen und Reorder nicht den falschen Übergang beschreiben.
Messdiagnosen werden vor Darstellung validiert; die Ansicht startet keine
Neuanalyse. Ungeplante Grenzen bleiben als solche sichtbar.

## Prüfweg

Der Projektinterpreter folgt `docs/PROJECT_KNOWLEDGE.md`; Testoptionen stehen
in `pytest.ini`.
`tools/run_refactor_checks.ps1` ist ein optionaler Windows-Aufruf mit isolierter
Coverage, eindeutigen Logs und Quell-/Testhashes. `-Full` führt die Tests mit
den unveränderten Projektoptionen aus; ohne den Schalter ist es ein gezielter
Entwicklungslauf ohne Coverage. Ein Log oder eine Modulaufteilung ersetzt weder
die native App-Prüfung mit Originaltracks noch ein Hörurteil.
