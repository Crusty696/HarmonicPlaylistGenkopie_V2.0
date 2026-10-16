# HPG: Quellen und dauerhaftes Wissen

Konsolidierung vom 04.10.2026. Diese Datei trennt Nutzervertraege, statisch
gepruefte Codefakten und offene Prueffragen. Sie ist keine Produktabnahme.

## Zuerst lesen

1. Aktueller Auftrag und AGENTS.md bestimmen Scope, Schutz und Nachweise.
2. MEMORY.md enthaelt Produktleitlinie und Quellen des Nutzers.
3. hpg-orientation und der passende Fachskill fuehren zum Code.
4. Fuer Implementierungsbehauptungen den aktuellen Code lesen. Fuer
   Laufzeitbehauptungen den passenden datierten Rohbeleg lesen.
5. docs/HOERTEST_NATIVE_2026-10-04.md ist ein datierter Bericht, kein
   automatisch gueltiger Nachweis fuer jeden spaeteren Build.
6. specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md enthält den aktuellen Auftrag
   und die datierten Umsetzungsscheiben; der neueste Stand steht am Ende.
   specs/AGENT_EXECUTION_INSTRUCTIONS.md ergänzt die Ausführungsregeln.

Historische Auftraege wie Rendern, Pushen, pausierte Analysen oder /goal
werden niemals durch Lesen einer alten Datei wieder zu aktiven Auftraegen.
Auslagerungen sind im Bereinigungsmanifest dokumentiert. Alte Originaltexte
liegen ausserhalb des Workspace in der lokalen Recovery-Sicherung; deren
Wiederherstellung macht ihre Aussagen nicht zu aktuellen Fakten.

## Erhaltene Nutzervertraege: Soll, kein Implementierungsbeweis

Aus den historischen Handoffs, docs/agent-memory und dem Session-Corpus vom
25.08. wurden folgende Anforderungen erhalten:

- HPG dient der Auswahl passender Trackpaarungen und Playlist-Reihenfolgen.
  Kernarbeit gehoert in die App; Hoertests und Training ergaenzen sie.
- Trackmerkmale individuell analysieren oder auslesen. Paarbewertung nutzt
  lokale Fensterwerte; keine globalen Track-Ersatzmesswerte unterschieben.
  Gemeinsame Gewichte und Toleranzen duerfen zentral sein.
- Musikalische Kompatibilitaet bedeutet nicht numerische Gleichheit.
  Unterschiedliche kompatible Rhythmen sind erlaubt; echte Groove-Konflikte
  sollen sperren. Fehlende erforderliche lokale Messungen nicht durch
  Gewichtsumverteilung kaschieren. Aktuelle ausdrueckliche Ausnahme:
  Unbekannte Vocals allein duerfen kein Paar sperren.
- Vor erneutem Rendern eine nachvollziehbare Uebersicht aller relevanten
  Parameter, Gewichte, Gates und Kriterien vorlegen.
- Individuelle Mixpunkt-Kandidaten statt universeller Cue-Positionen.
  Groove, Rhythmus, Harmonie, Bass/Subbass, Klangfarbe, Lautheit und weitere
  vereinbarte Faktoren beruecksichtigen. Praezision nicht still vereinfachen.
- Tatsaechliche Tempo- und Kick-/Beatphasensynchronitaet pruefen. Das
  Rekordbox-Grid allein beweist sie nicht. Eine Grenze vor dem Outro beweist
  nicht, in welcher realen Tracksektion der Mix-Out liegt.
- Hoertests: hoechstens fuenf Varianten pro Paar. Ein Einzelclip benoetigt
  eine Note, keinen relativen Gewinner. Note 1 darf nie bester Clip sein.
  Auch bei mehreren Clips muss kein bester moeglich bleiben.
- Startgewichte als Startgewichte kennzeichnen. Gescheiterter Holdout ist
  keine Kalibrierfreigabe. Neue Scores muessen keine Reihenfolge aendern.
- Originalmusik bleibt am Quellort, ausschliesslich lesend. Keine Kopien in
  Projekt, Git oder Sicherungen. Bestehende Bewertungen bewahren.
- Implementierung, automatischer Test, nativer Originaltrack-Ablauf und
  musikalische Bewertung sind getrennte Nachweise. EXE-Pfad und SHA-256
  muessen zum getesteten Build passen; frische Analyse und Cache getrennt.
- Unabhaengige Waechterpruefung auf Anforderung; kein Vorab- oder Commitgate.
  Die Spiegel unter `.agents/agents` und `.claude/agents` synchron halten.
- Historisch dokumentierte Kommunikationspraeferenz: Antworten mit :-) enden.

## Quellen fuer den laufenden Auftrag

Die aktuelle Deep-Analysis-/Rekordbox-Arbeitsmatrix ist `specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md`. Verbindliche Arbeitsregeln stehen in `AGENTS.md` und den passenden Skills unter `.agents/skills/`; sie werden hier nicht dupliziert.

Die Prioritaet ist Beat-/Downbeat- und Phrasen-/Cue-Analyse samt Nutzung in Playlist und Hoerproben. Stems und Embeddings sind in der ersten Ausbaustufe zurueckgestellt, sofern sie keine notwendige Abhaengigkeit sind. Keine Track-Felder auf Vorrat hinzufuegen.

Klarstellung zu Cache-Version 85: `reference_constant_offset` bezeichnet einen stabil gemessenen Zeitversatz zwischen Audio-Beatphase und Rekordbox-Grid. Ein phasenbereinigter Modellvergleich erkennt eine mögliche Taktrotation zunächst nur als Kandidat. Seit Cache 81 darf der aktive HPG-Audioanker nach drei disjunkten Bestätigungsfenstern je Modell, separater Audiophasenbestätigung und verifiziertem Gesamtgrid korrigiert werden. Rekordbox-Rohticks bleiben unverändert; Beatphase und musikalische Takt-1-Genauigkeit bleiben getrennte Aussagen.
Der aktuelle Code setzt `CACHE_VERSION = 92` in `hpg_core/caching.py`. Version 72 lässt bei schwacher Phrasenphasen-Konfidenz die Audio-Novelty-Messung im bestätigten Beatgrid die Genre-Prior-Phrasenlänge bestimmen; Fast- und Vollpfad nutzen anschließend dieselbe `structure.phrase_unit` für Mixpunkte, Kandidaten und Track. Version 73 speichert deren Herkunft (`audio_novelty`, `genre_prior` oder `configured`); der Fast- und Vollpfad kennzeichnen genreprofilbasierte Einheiten ausdrücklich als `genre_prior`, externe explizite Werte bleiben `configured`. Version 74 speichert zusätzlich besten Kandidaten, rohe Novelty-Korrelation und Ranking-Abstand zum Zweitkandidaten. Version 75 führt diese Werte im Messdiagnose-Schema v6 und bindet sie in der Cachevalidierung an die Trackfelder. Diagnoseversion 6 behält die Sperre für gemessene Taktrotationen aus Schema 5 bei. Version 76 korrigiert die Herkunft für genreprofilbasierte Einheiten auch bei expliziter interner Weitergabe; Diagnoseform und Mixverhalten bleiben gleich. Version 77 verlangt fuer neuronale Taktanker dieselben drei nicht ueberlappenden audio-bestaetigten Quellfenster fuer beide Modelle. Der persistierte Kandidat folgt dem fruehesten bestaetigten Fenster und die aktive Konfidenz ist das Minimum aller bestaetigten Fenster. Version 78 uebernimmt eine Rekordbox-Taktrotation nur nach sechs bestaetigten Modell-/Audiofenstern und verifiziertem Gesamtgrid. Version 79 persistiert `reference_constant_offset`, wenn die Rekordbox-Taktpositionsdiagnose einen konstanten Grid-Offset erkennt; das bleibt reine Diagnose ohne Grid-/Ankerkorrektur oder Sync-Freigabe. Version 80 vergleicht Modellbeats für die Taktpositionsdiagnose mit um den gemessenen Offset phasenprojizierten PQTZ-Ticks; ein Rotationstreffer bleibt zunächst Kandidat. Version 81 erlaubt die Übernahme nur nach drei disjunkten Bestätigungsfenstern je Modell, separater Audiophasenbestätigung und verifiziertem Gesamtgrid; Rekordbox-Rohticks und Sync-Regeln bleiben unverändert. Cache 85 erlaubt bei reiner konstanter Zeitverschiebung ohne Bar-Rotation einen zeitkorrigierten Audioanker nur nach disjunkter Modell-/Audiophasenbestätigung und verifiziertem Gesamtgrid; Cache 86 verwirft diese Korrektur, wenn sie den Anker über eine Bar-Grenze wickeln würde; Cache 87 verwendet die wirksame Phrase-Unit auch in der Mix-In/Out-Kandidatensuche und den Intro-/Outro-Guards; Cache 88 verwendet den Median aller sechs konsistenten Tempoausgaben als Modellkandidat und behält DSP-Refinement sowie verifiziertes Gesamtgrid als Gates; Cache 89 speichert Tempo-Status, Grund, Modellmedian, Audioverfeinerung und Modellstreuung im Diagnose-Schema v7; Cache 90 erhält sechs Modell-BPM-Werte mit Modell-ID und Fensterstart; der v7-Cachevalidator bindet Median und Spread rechnerisch an die gespeicherten Einzelwerte und erzwingt bei übernommenem Tempo dieselbe 2%-Grenze; Rekordbox-Rohticks und Bar-Labels bleiben unverändert. Der korrigierte Anker bleibt Audioherkunft; PSSI und Rekordbox-Render-Sync werden nicht freigegeben. Er kann Beat-Alignment versorgen, aber keine Renderer-Taktphase freigeben; `strict_beat_sync` bleibt aktiv. `audio_novelty` wird nur nach tatsaechlicher Novelty-Messung gesetzt, nie ueber eine explizite Herkunftsangabe. Das Tail-Fenster erbt nur `genre_prior`; die zusammengefuehrte Track-Struktur behaelt die Herkunft des Head-Fensters. `effective_track_phrase_unit` vereinheitlicht Phrasenraster in Mixpunkten, Kandidaten und Playlist-Ketten: `audio_novelty` und `configured` benötigen gültige Werte; sonst gilt das wirksame Genreprofil. Cache 83 berechnet die Phrasenphase nach einer durch Audio-Novelty geänderten Phrase-Unit neu und quantisiert bei bestätigtem Ankerwechsel die Strukturfenster erneut. Cache 84 verwirft bei fehlgeschlagener Neuquantisierung auch den neuen Phasebeleg. `SUPPORTED_PHRASE_UNITS` definiert zentral 8/16/32; ungültige externe Mixpunktwerte werden nicht quantisiert und erzeugen keine Track-Kandidaten oder manuellen Cue-Freigaben. Die Scores sind nicht kalibrierte Wahrscheinlichkeiten. Das Messpanel zeigt Phrasenlänge, Herkunft und verfügbare Rohwerte. Bei gesperrtem oder unbestätigtem Raster bleibt der Genre-Prior erhalten. Version 71 ergänzt die eindeutige ANLZ-Gruppenzuordnung für PSSI/PQTZ-Phrasen; mehrdeutige Dateigruppen liefern keine Phrase-Daten. Version 70 sperrt bei einer schema-v5-validierten, einheitlichen Nichtnull-Taktrotation die PSSI-/Phrasenausgaben, Mixpunkte und Kandidaten sowie Takt-1-/Cue-Export; Beatanker und Beat-Sync bleiben erhalten. Eine verifizierte DSP-Baseline wird bei schwacher Phrase-Konfidenz durch die vorhandene Audio-Beatmodell-Arbitration geprüft; verifizierte Rekordbox-Referenzen bleiben priorisiert, außer eine vollständige audio-bestätigte Modell-Taktrotation aus Version 78 korrigiert Takt 1. Der letzte dokumentierte frische Originaltrack-Lauf verwendete Cache-Version 57 und ist kein Cache-Reuse-Beleg fuer Version 76. Die Änderungen sind nicht durch Laufzeit- oder Testnachweise bestätigt. Produktivcache und WAL/SHM-Dateien bleiben geschuetzt.

Ein AIFF-Lauf vom 14.10.2026 liegt unter `%TEMP%/hpg-deep-implementation-20261014/native-rb-one-ea3a520c-7cd5-4f1c-a28f-173819c1469e/`. Rekordbox war geschlossen; Quellhash vor/nachher war identisch. Der Lauf verwendete einen privaten Cache und endete im Rekordbox-Fast-Path mit audio-bestaetigtem Raster. Das Rekordbox-Grid wurde wegen Phasenfehler abgelehnt; dadurch gab es fuer diesen Track keine PSSI-Phrasen. Das ist ein technischer Einzeltrackbeleg, keine allgemeine Qualitaets- oder Cache-Reuse-Abnahme.

Die native Hoerprobenstrecke nutzt Quellreferenzen und rendert Vorschauen bei Bedarf im RAM. Der Bewertungsdialog erlaubt Noten erst nach erfolgreichem Rendern. Automatische GUI-Tests verwenden fuer diesen Schritt synthetische Audio-Bytes; sie beweisen keine erfolgreiche Originaltrack-Wiedergabe oder musikalische Bewertung. Voller nativer Ablauf, Cache-Reuse und menschliches Urteil bleiben getrennte Nachweise.
## Am 04.10.2026 statisch geprueft (historischer Stand)

- app_metadata.py: APP_VERSION 3.7.2, MIN_PYTHON 3.12.1.
- caching.py: CACHE_VERSION 46 nach Diagnose-Erweiterung. playlist.py
  registriert acht Strategien. Alte Cache-45-Belege bleiben historisch.
- transition_features.mood_match verarbeitet brightness. Lokale Kandidaten
  verwenden in pair_candidates._teil_timbre avg_mids_lokal/avg_highs_lokal
  und in _teil_mood lokale Helligkeit. Die alte pauschale Aussage, diese
  Merkmale seien nur Diagnosewerte, darf nicht fortgeschrieben werden.
- rekordbox_phrases.phrases_from_anlz verarbeitet PSSI. Alte Aussage
  PSSI ungenutzt ist keine aktuelle Implementierungsbeschreibung.
- tests/test_release_metadata.py liest PRODUCTION_STATUS.md. Dieser Pfad
  bleibt erhalten, statt durch Bereinigung einen Testvertrag zu brechen.
- Zwei Dateien mit Endung .exe im Projektroot enthielten Textprotokolle,
  keine Programme. Historische Analyseausgaben und AI-Timeouts darin
  belegen weder den aktuellen Build noch einen vollstaendigen App-Ablauf.

Diese Fakten wurden durch Quellenlesen festgestellt, nicht durch einen neuen
Produktlauf. Exakte Entfernungen und Originalhashes: cleanup-manifest-2026-10-04.json.

## Offene Fragen und Grenzen

- Historische Berichte nennen Bugs und Tests. Ihre Entfernung erklaert
  keinen Bug fuer behoben. Wiederaufnahme nur mit aktueller Reproduktion.
- Historische Aussagen zur Mindestlaufzeit von zwei Phrasen widersprechen
  einander. Dies wird nicht durch Dokumentationsbereinigung entschieden:
  aktuellen Auftrag, Fachvertrag und betroffenen Code gemeinsam pruefen.
- Fehlen einer Datei namens test_ai_engine.py beweist keine fehlende
  AI-Testabdeckung. Abdeckung waere am konkreten Verhalten zu untersuchen.
- Historische Modellbenchmarks, Hardwareempfehlungen, Serverzustaende,
  Trackzahlen, Git-Hashes und Testzahlen sind keine heutigen Messungen.
- Fast-Path-Vergleiche mit Rekordbox-Metadaten beweisen keine unabhaengige
  Eigenanalyse-Genauigkeit. Doppelte Basenames/abweichende Pfade koennen
  absichtlich ohne Zuordnung bleiben; tatsaechliche Records pruefen.
- Alte Kritik an einem 30-Paare-Hoertestsatz ist eine historische Warnung:
  vorhandene Bewertungen nicht ungeprueft als Trainingsgrundlage behandeln.
- Transformationsstabilitaet eines Kickdetektors beweist keine Kick-Ground-
  Truth. Vorhandene validation-Rohbelege bleiben erhalten; keine Neuabnahme.
- Der zurueckgezogene VERITAS-Lauf vom 03.09. bleibt mitsamt UNGUELTIG.md
  als historische Evidenz erhalten. Seine Befunde sind keine bestaetigten
  aktuellen Fehler und duerfen nicht als solche synchronisiert werden.
- Generierte No-update-Erinnerungen liefern keine neue Fachinformation.
  Beschraenkter Sessionzugriff (sessions.visibility=tree) beweist keine
  vollstaendige Chatabdeckung. Automatisch erzeugte Reflexionen sind keine
  primaere Quelle und duerfen diese Regeln nicht ueberschreiben.
