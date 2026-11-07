# HPG: Gesamtrefaktorierung und funktionale Überarbeitung

Stand: 30.10.2026. Bestätigter Entwurf gemäß Umsetzungsprotokoll;
keine Implementierungs- oder Abnahmebehauptung. Den aktuellen Arbeits- und
Prüfstand führt der [Refaktorierungsplan](../plans/2026-10-30-gesamtrefaktorierung.md).

## Auftrag und Entscheidungen

Der Nutzer beauftragt die Gesamtrefaktorierung einschließlich Fachlogik und
Oberfläche und nennt Analyse, Playlist, Übergänge und Bedienung als Umfang.
Die folgenden konkreten Verbesserungen und die Reihenfolge gehören zum
laut Umsetzungsprotokoll am 30.10.2026 vollständig bestätigten Entwurf.

Ziel ist eine wartbare App, in der der Weg von der Trackauswahl zum geprüften
Set verständlich ist und alle Ansichten denselben Ergebnisstand verwenden.
Python 3.12, PyQt6 und die vorhandenen Analyse- und Renderverfahren bleiben
die technische Grundlage. Es werden keine neuen Abhängigkeiten benötigt.

## Quellenprüfung

Ausgangscommit: `95a7edbe75c1af466090585ea68f7bf206388f08`.
Der Arbeitsbaum war vor dieser Dokumentänderung sauber.
Die AST-Prüfung mit dem Projektinterpreter ergab:

| Datei | Zeilen | Konkret untersuchte Struktur |
|---|---:|---|
| main.py | 9104 | Worker, Panels und MainWindow gemeinsam; MainWindow 3115 Zeilen |
| hpg_core/analysis.py | 4940 | analyze_track 1231 Zeilen, Cache und zwei Analysepfade |
| hpg_core/playlist.py | 4679 | Scoring, Result-Vertrag, Strategien und Timeline |
| hpg_core/caching.py | 1736 | validate_track_dict 309 Zeilen |
| hpg_core/transition_renderer.py | 1636 | Spec, Validierung, Rendering und DSP-Helfer |
| hpg_core/pair_candidates.py | 1669 | Kandidatenvertrag, Gates und Ranking |

178 Testdateien wurden gefunden; das ist keine Testausführung.
PlaylistPanel definiert Spaltenbeschriftungen, Tooltips, Breiten und
Delegate-Indizes getrennt. pair_candidates importiert Genreauflösung sowie
combine_weighted und VOCAL_CLASH_PENALTY aus playlist innerhalb von Funktionen.
MainWindow bereitet mehrere neue Views vor deren gemeinsamer Veröffentlichung
vor. Deren Fehler- und Rollback-Semantik ist bei einem Umbau zu erhalten.
Diese Befunde belegen Kopplung und Größe, keine Laufzeitfehler.

## Vorgehensweisen

Empfohlen: schrittweiser Umbau innerhalb der bestehenden Anwendung. Jede
strukturelle Auslagerung bewahrt zunächst das Verhalten; funktionale Änderungen
folgen mit eigenen Akzeptanzkriterien. Öffentliche Einstiegspunkte bleiben
kompatibel. Dies erlaubt die Zuordnung von Regressionen zu einer Etappe.

Alternative: vollständiger Ersatz der Anwendung. Damit müssten native
Integration, Worker-Lebenszyklen, Persistenz und sämtliche Ergebnisverbraucher
neu nachgewiesen werden. Für den vorhandenen Funktionsumfang ist der Aufwand
ohne belegten Zusatznutzen erheblich höher; deshalb nicht empfohlen.

Eine bloße Aufteilung großer Dateien würde den gewünschten funktionalen und
sichtbaren Verbesserungen nicht genügen.

Gesamtprojekt bedeutet Prüfung aller produktiven Bereiche, nicht Änderung
jeder Datei. Rekordbox-Import und Export werden auf Vertragskonsistenz und
Fehlerdiagnose geprüft, ParallelAnalyzer und native Inferenz auf Zuständigkeit,
Abbruch und Ressourcenfreigabe, Renderer auf die Trennung von Planvalidierung,
Prozesssteuerung und DSP. Bereits klar getrennte Module bleiben unverändert,
wenn die Prüfung keinen begründeten Änderungsbedarf ergibt. Buildkonfiguration,
Startskripte und Dokumentation werden an tatsächliche Importänderungen angepasst;
Werkzeuge werden auf kompatible Einstiegspunkte geprüft.

Fachliche Verbesserung beginnt mit aktueller Reproduktion von Defekten gegen
die bestehenden Verträge. Nachgewiesene Defekte werden mit Regression korrigiert.
Zusätzliche Änderungen an Messverfahren, Suchalgorithmen oder DSP erhalten vor
Umsetzung eigene messbare Kriterien und Vergleichsdaten. Die allgemeine
Beauftragung allein begründet keine beliebige Änderung musikalischer Gewichte.

## Zielstruktur und Etappen

### 1. Gemeinsame Grundlagen und Playlist-Tabelle

Reine gewichtete Kombination und gemeinsam benötigte Scoring-Konstanten in
ein kleines, Qt-freies Modul hpg_core/scoring_primitives.py verschieben.
Genreauflösung aus ihrer vorhandenen zuständigen Quelle verwenden. Alte
Importe aus playlist durch kompatible Re-Exporte erhalten. Vorher sämtliche
Verbraucher einschließlich Tests und Werkzeuge prüfen; keine Änderung an
Gewichten, Reihenfolgen, Rundung oder Regeln für fehlende Faktoren.

Für die Playlist-Tabelle eine gemeinsame Spaltenbeschreibung unter
hpg_core/ui/playlist_columns.py einführen. Titel, Tooltip, Breite und
Spaltenidentität an einer Stelle führen; Population und Reorder verwenden
dieselben Identitäten. Zunächst Reihenfolge und sichtbare Werte erhalten.

Akzeptanz: bestehende Scoring-Ergebnisse einschließlich fehlender Komponenten
bleiben gleich; Kandidatenbewertung benötigt diese Hilfen nicht mehr aus
playlist. Alle 16 Tabellenspalten bleiben nach Laden, KI-Ergänzung und Reorder
korrekt zugeordnet; doppelte Trackvorkommen behalten ihre Identität.

### 2. Ergebnisvertrag und Ablaufsteuerung

Result-Typen und unveränderliche Snapshots aus playlist in ein eigenständiges
Modul überführen, bevor Strategien und Timeline getrennt werden. Abhängigkeiten
zuvor prüfen, insbesondere Typidentität, Serialisierung, private Imports und
Monkeypatch-Ziele bestehender Tests. Keine Rückimporte in die Fassade.

MainWindow schrittweise auf Darstellung und Signalverdrahtung begrenzen.
Worker und Ergebnisveröffentlichung erhalten eigene zuständige Module.
RunState, Source-Guards, kooperativer Abbruch, QThread.finished-Cleanup und
atomare Veröffentlichung einschließlich Rollback bleiben verbindlich.

Akzeptanz: Kandidatenwechsel und Reorder veröffentlichen entweder einen
vollständigen konsistenten neuen Stand oder erhalten den alten. Verspätete
Worker-Ergebnisse verändern keinen neueren Lauf. Vorschau, Tabelle, Quality,
Timeline und Export verwenden dieselben aktiven TransitionPlans.

### 3. Analyse und Cache

analyze_track bleibt öffentlicher Einstieg. Vorprüfung/Quellidentität,
Metadaten, Audiofenster, Merkmalsextraktion und gemeinsame Track-Finalisierung
werden in klar benannte Schritte getrennt. Fast- und Vollpfad behalten ihre
unterschiedlichen Eingaben, verwenden aber dieselben fachlichen Abschlussregeln.
Cachezugriff und Serialisierungsvalidierung werden getrennt strukturiert.

Funktionales Ziel: pro Track verständlich anzeigen, welche Analyseschritte
vorliegen, wo Messungen fehlen und weshalb ein Schritt fehlgeschlagen ist.
Vorhandene Messdiagnosen wiederverwenden; keine zweite Wahrheitsquelle anlegen.
Eine gezielte Wiederholung darf nur tatsächlich fehlende oder ungültige Schritte
erneuern und braucht eine nachgewiesene Abhängigkeitsprüfung. Bis diese existiert,
keinen vermeintlich sicheren Teil-Neuanalyseknopf anbieten.

Akzeptanz: fresh liest und schreibt keinen persistenten Track-Cache;
reuse prüft die Quellidentität. Beide Analysepfade erhalten Messfenster,
Herkunft und Sentinel-Semantik. Änderungen gespeicherter Werte benötigen
einen ausdrücklich getesteten Cacheversionsvertrag. Produktivdaten erhalten.

### 4. Playlist und Übergänge

Strategien, Kandidatenkettenwahl und Ergebnisaufbereitung separat strukturieren.
Ablehnungsgründe aus den vorhandenen Gates durchgehend zum sichtbaren Ergebnis
transportieren. Die Oberfläche unterscheidet fehlende Messung, unpassendes Paar
und technisch nicht ausführbaren Übergang und zeigt vorhandene Alternativen.

Funktionales Ziel: Der Nutzer kann erkennen, warum eine Grenze ungeplant ist,
welcher Kandidat aktiv ist und welche Änderung tatsächlich wirksam wurde.
Alternativen müssen dieselben Gates erfüllen. Kein impliziter Kandidatenwechsel
im Renderer, keine erfundenen Scores und keine Lockerung zur Erhöhung der
Anzahl geplanter Übergänge. Algorithmische Qualitätsoptimierung setzt einen
eigenen Vergleich mit realen Referenzen voraus; sie ist kein garantierter
Nebeneffekt der Refaktorierung.

Akzeptanz: unbekannte Vocals allein sperren nicht; fehlende erforderliche lokale
Faktoren werden nicht durch Umverteilung legitimiert. BPM-Grenze, Raster,
Intro-/Outro-Guards und 6-ms-Renderprüfung bleiben bestehen. Ein ungeplanter
Übergang wird nicht gerendert. Ablehnungsgrund und aktive Wahl stimmen über
Anzeige, Vorschau und Export überein.

### 5. Bedienung und sichtbare Oberfläche

Die vorhandenen Ansichten werden zu einem erkennbaren Arbeitsablauf verbunden:
Bibliothek auswählen, Analyse prüfen, Playlist bearbeiten, Übergänge prüfen,
exportieren. Kein zusätzlicher blockierender Assistent. Ein gemeinsamer
Statusbereich zeigt laufenden Schritt, Fortschritt, Abbruch und nächste Aktion.
Häufige Einstellungen bleiben unmittelbar erreichbar; Expertenparameter
werden zusammengefasst. Deutsche Beschriftungen werden konsistent verwendet.

Playlist: Kerninformationen zuerst; Messdetails und Begründungen in einer
Detailansicht. Die bestehende Kandidatenwahl bleibt erreichbar. Fehlende Daten
werden mit Text kenntlich gemacht und nicht allein farblich codiert.
Vor der sichtbaren Umsetzung ist ein konkreter Bildschirmaufbau auszuarbeiten;
dieser Entwurf legt noch keine Pixelmaße oder vollständige Gestaltung fest.

Vorgeschlagener verbindlicher Aufbau: links die vorhandenen fünf Ansichten
als Bibliothek, Playlist, Übergänge, Zeitlinie und Qualität; oben gemeinsame
Aktionen und Laufstatus. In der Playlist stehen Position, Titel, Interpret,
BPM, Camelot, Energie und Übergangsstatus im Mittelpunkt. Die übrigen bisherigen
Spalten bleiben über die Detailansicht bzw. eine erweiterte Tabellenansicht
erreichbar. Rechts zeigt ein ausblendbarer Detailbereich die ausgewählte
Trackinstanz oder Übergangsgrenze, Herkunft, Messlücken und Ablehnungsgründe.
In der Übergangsansicht stehen aktive Wahl und Kandidatenliste zusammen mit
der Vorschau; die Auswahl bleibt an die konkrete Grenze gebunden. Export bleibt
eine gemeinsame Aktion, keine zusätzliche sechste Navigationsseite.

Akzeptanz: Tastaturbedienung, Fokus, Reorder, Abbruch, Fehlerfälle und
Wiederanlauf funktionieren sichtbar. Während aktiver Arbeit bleiben gefährdende
Aktionen gesperrt. Ein Fehler bietet eine zutreffende nächste Handlung und
bewahrt vorhandene Ergebnisse. Reine Umbenennung gilt nicht als UX-Abnahme.

## Prüfung und Schutz

Vor jedem Lauf vorhandene Rohbelege auf Quell-/Testbindung und Umgebung prüfen.
Gezielte Charakterisierung vor Auslagerungen; Fehlerkorrekturen nur mit
Reproduktion oder ausdrücklich benannter Diagnosegrenze. Bestehende Erwartungen
nicht abschwächen, um neue Ergebnisse grün erscheinen zu lassen.

Relevante vorhandene Tests umfassen test_scoring_contract.py,
test_playlist_generation_result.py, test_preview_result_contract.py,
test_main_workers.py, test_main_window.py, test_gui_display.py,
test_analyze_track.py, test_analysis_coverage.py, test_cache_isolation.py und
test_transition_renderer.py. Ihre konkrete Eignung ist vor Umsetzung je
Teilaufgabe zu prüfen; eine Dateiliste belegt keine Abdeckung.

Abschluss-Volltest mit venv312/Scripts/python.exe -m pytest tests/ --tb=short -q
gemäß pytest.ini und Coverage-Gate. Cache, Coverage und temporäre Ergebnisse
isolieren; bestehende Dateien nicht überschreiben. Nur ein Verantwortlicher
für teure Läufe; keine parallelen vollständigen Tests.

Danach betroffenen Originaltrack-Ablauf direkt in der App prüfen: auswählen,
frisch analysieren, Paarbewertung, Playlist, Kandidatenwechsel, Vorschau und
Export. Cache-Reuse separat belegen. Originalmusik ausschließlich am Quellort
lesen. Vor Rendern Parameterübersicht gemäß Projektvertrag vorlegen.
Musikalische Bewertung braucht ein gesondertes Hörurteil.

Keine Installationen, kostenpflichtigen Aufrufe, Providerwechsel oder
Sicherheitsänderungen ohne Freigabe. Keine geschützten Benutzerartefakte,
Produktivcaches oder vorhandenen Bewertungen verändern. EXE erst nach den
Funktionsnachweisen und bei entsprechendem Auslieferungsauftrag.

## Abschlusskriterien und Grenzen

Jede Etappe dokumentiert Änderungen, automatische Prüfung, native App-Prüfung
und musikalische Bewertung getrennt. Ein erfolgreicher Test ersetzt keinen
anderen Nachweis. Bestehende historische Fehler gelten erst nach aktueller
Reproduktion und Prüfung als behoben. Die Gesamtarbeit ist erst abgeschlossen,
wenn alle vereinbarten Etappen umgesetzt und die jeweiligen Akzeptanzkriterien
belegt sind; dieses Dokument schließt den Auftrag nicht ab.

Noch auszuarbeiten: konkrete Importmigration und Funktionsgrenzen je Etappe,
Bildschirmgestaltung sowie geeignete Originaltracks und unveränderte
Vergleichsartefakte für die späteren App-Nachweise. Diese Details werden anhand
des aktuellen Codes und vorhandener Belege entschieden, ohne historische
Render- oder Analyseläufe automatisch fortzusetzen.
