# HPG: Quellen und dauerhaftes Wissen

Quellenabgleich vom 26.10.2026. Diese Datei enthält Nutzerverträge und den
Weg zum aktuellen Code. Sie ist keine Produktabnahme.

## Einstieg und Quellenrang

1. Der aktuelle Nutzerauftrag bestimmt den Umfang; diese Datei enthält die
   dauerhaften Projektregeln.
2. [Produktleitlinie](../MEMORY.md), `hpg-orientation` und Fachskills führen zum Code.
3. Der [Refaktorierungs- und Nachweisprotokoll](superpowers/plans/2026-10-30-gesamtrefaktorierung.md)
   enthält die aktuellen Änderungen und datierten Prüfnachweise. Der
   [Gesamtstatus vom 09.11.2026](STATUSBERICHT_2026-11-09.md) bündelt den
   jüngsten Entwicklungsabgleich mit GitHub. Der
   [Quellen- und Nachweisstand](../PRODUCTION_STATUS.md) bewahrt den historischen
   Abgleich vom 26.10. samt damaliger Grenzen.
4. [Übergabe vom 20.10.](CHAT_UEBERGABE_2026-10-20.md) enthält die jüngste
   fachliche Chatübergabe, Rohbelegpfade und offene Fehler. Historische
   Fortsetzungsbefehle werden durch Lesen nicht zum aktuellen Auftrag.
5. [Deep-Analysis-Spezifikation](../specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md)
   bewahrt Ziele und datierte Umsetzungsgeschichte. Ihr älterer Beispielcode
   ist kein aktueller API-Vertrag. Der Kopf ordnet den Stand ein.
6. Allgemeine Ausführungsregeln stehen in dieser Datei; Deep-Analysis-
   Besonderheiten im [Fachskill](../.agents/skills/hpg-deep-analysis/SKILL.md).
   `.agents/skills/` ist der aktive Skill-Bestand.

## Aktive Arbeitsregeln

- Nutzerauftrag und lokaler Arbeitsbaum sind maßgeblich; bestehende Änderungen
  nicht ohne Auftrag verwerfen.
- Musikbibliothek, vorhandene Hörbewertungen, Cache und Coverage-Dateien sind
  Nutzerdaten und dürfen durch Tests oder Bereinigung nicht überschrieben werden.
- Projektbefehle verwenden `venv312`; Nachweise und Prüfumfang richten sich
  nach Auftrag und relevantem Fachskill. Einen Volltest nur ausführen, wenn er
  beauftragt oder für eine konkrete Änderung erforderlich ist.
- `.agents/skills/` ist der einzige aktive Skill-Bestand. Gelöschte
  `.claude/`- und `.codex/`-Spiegel werden nicht als Quellen vorausgesetzt.

## Aktuell im Quellcode verankert

- App-Version und Python-Mindestversion: `hpg_core/app_metadata.py`.
- Cache-Version und genaue Validierung: `hpg_core/caching.py`; keine alte
  Versionszahl aus einem Bericht als Sollwert übernehmen. Alte Datenbanken erhalten.
- `analysis.analyze_track` verbindet Cachepolitik, DSP-Merkmale, native Beats,
  Audio-Rasterprüfung, native Phrasen und lokale Mixpunkt-Kandidaten in beiden
  Analysepfaden. `cache_policy='fresh'` ist von Wiederverwendung zu unterscheiden.
- Native Beatpipeline: `hpg_core/ai_models/native_track_beats.py` und
  `native_beat_pipeline_worker.py`. Snapshot-Wiederverwendung prüft Quelle und
  Konfiguration; alte Audioausrichtung wird nicht ungeprüft übernommen.
- Native Reader: `hpg_core/ai_models/native_audio_reader.py`. Die alte Aussage
  „nur WAV/AIFF“ ist überholt: Der Factory-Vertrag enthält außerdem MP3, FLAC,
  AAC und M4A/MP4, mit gesonderter ALAC-Auswahl. Eine vorhandene Factory ist
  kein Laufzeitnachweis für jede Datei, Bitbreite oder Codecvariante.
- Native Taktposition darf nach Nutzerfreigabe bei verifiziertem nativen Grid
  für Playlist und Hörproben verwendet werden. `native_candidate` bleibt ein
  sichtbarer, nicht unabhängig musikalisch bestätigter Status. Verbraucher:
  `models.Track`, `native_track_beats.has_verified_grid` und
  `TransitionClipSpec.from_plan`. Confidence 1.0 allein ist kein Freigabevertrag.
- Preview-Stretch: `hpg_core/preview_stretch.py`, vorhandenes Pedalboard,
  gemischter Transientenmodus, langes FFT-Fenster und Kanalpegel-Rückskalierung.
  Die strikte Kick-/Beatprüfung mit 6 ms bleibt bestehen.
- Playlist-Ergebnis: `playlist.generate_playlist_result` erzeugt ein
  `PlaylistGenerationResult`; Kettenwahl, GUI, Preview und Export müssen die
  darin festgehaltenen Pläne gemeinsam verwenden. Die acht Strategien stehen
  in `playlist.STRATEGIES`, ihre Details im aktuellen Code.
- Stems/Embeddings besitzen eigene Module unter `hpg_core/ai_models/`.
  Ihre Existenz ist weder ein Auftrag für neue Läufe noch ein Qualitätsnachweis.

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

## Neueste fachliche Entscheidungen aus dem Projektchat

Quelle: „HPG Deep Analysis & Rekordbox Integration“, Übergabe 20.10.2026.
Der Bereinigungsauftrag vom 26.10. startet diese Produktarbeit nicht erneut.

- Fertige Analysen und gültige Tests wiederverwenden; keine Stem-/Embedding-
  Wiederholung und kein neuer EXE-Build zur Dokumentationsbereinigung.
- Für W einen bereits analysierten geeigneten Partner nutzen; die vereinbarte
  2-BPM-Grenze nicht auf 8 erweitern. Für Deep Sky wurden nur fehlende native
  Beat-/Takt-/Phrasendaten freigegeben, keine vollständige Neuanalyse.
- Die Übergabe nennt 26 technisch verifizierte Grids, Hörproben für 16 der
  ursprünglich 17 gesperrten Tracks und sieben ungeplante Gesamtplaylist-Grenzen.
  Das sind datierte Ergebnisse, keine neue Messung vom 26.10.
- Deep-Sky-Provenienz im gespeicherten Trackdatensatz war noch ungültig.
  Vorhandene Ergebnisse erhalten; Details und genaue Datenpfade in der Übergabe.
- Der Gesamtlauf vom 20.10. scheiterte mit 76 Fehlern bei 6319 bestandenen Fällen.
  Spätere gezielte Tests machen diesen Lauf nicht nachträglich grün.

## Erhaltene Erkenntnisse aus der Bereinigung

Die alten Welle-1/2/4-Skripte waren manuelle Audit-Reproduktionen außerhalb
der pytest-Sammlung. Ihre Szenarien betreffen Intro-/Outro-Grenzen,
Tempoverhältnisse, Harmonik, Key-Konfidenz sowie EQ-/Limiter-Verhalten.
Die passenden heutigen Testmodule sind über den Testskill auffindbar;
eine vollständige Gleichwertigkeit aller historischen Checks wird nicht behauptet.
Der frühere Rekordbox-Mikrobenchmark benutzte künstliche String-Datensätze und
eine Mock-Datenbank; er war kein echter DB- oder Geschwindigkeitsnachweis.

Die Auditnotizen vom 27.08. nennen mögliche Mixpoint-, Cache-Key-, Logging-,
Release- und Testlücken. Das sind historische Prüfhinweise, keine aktuelle
Fehlerliste und keine durch Archivierung behobenen Fehler. Originaltexte mit
Hashes bleiben extern erhalten. Der zurückgezogene VERITAS-Lauf bleibt
einschließlich seiner Ungültigkeitskennzeichnung am bisherigen Ort.

[Bereinigungsnachweis und Sicherung](CLEANUP_2026-10-26.md).
Der [lokale Inventarbericht](REPOSITORY_INVENTORY.md) grenzt die abschliessende
Dokument-/Anweisungspruefung vom Laufzeit- und Musiknachweis ab.
Die drei ueberholten HTML-Visualisierungen wurden am 08.11.2026 entfernt;
die aktuelle Flussbeschreibung bleibt der fachliche Einstieg.
Die Sicherung vom 04.10. und `cleanup-manifest-2026-10-04.json` bleiben erhalten.

## Offene Fragen und Grenzen


- Historische Berichte nennen Bugs und Tests. Ihre Entfernung erklaert
  keinen Bug fuer behoben. Wiederaufnahme nur mit aktueller Reproduktion.
- Der aktuelle Mixpoint-Vertrag verlangt mindestens zwei Phrasen zwischen
  Mix-In und Mix-Out (`analysis._valid_final_mix_pair`,
  `mix_candidates.passes_track_gates`, `hpg-mixpoint-engineering`). Die
  Vier-Phrasen-Beschreibung in `tests/test_mix_points_root.py` ist eine
  historische Beschreibung eines engeren Testfalls, kein allgemeines Gate.
  Bei einer fachlichen Aenderung beide aktiven Pfade und den Test erneut pruefen.
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

## Historisches Archiv

Die am 26.10. zusätzlich konsolidierten 23 Dokumente liegen bytegenau unter:
`E:\AI\HPG-cleanup-recovery\2026-10-26-document-consolidation\originals`.
Der bisherige relative Projektpfad bleibt darunter erhalten. `manifest.json`
enthält Pfade, Gründe und SHA-256; `archive-index.json` enthält Abschnittstitel
und Belegverweise. Der [Bereinigungsbericht](CLEANUP_2026-10-26.md) ordnet beide
Bereinigungsschritte ein. Historische Unterlagen sind keine neuen Arbeitsaufträge.

Erhaltene Erkenntnisse und Nachweisgrenzen:

- Die Intro-/Outro- und Kandidatendesigns begründen individuelle lokale Mixpunkte,
  phrasengerechte Quantisierung, explizite Sentinels und gemeinsame Pläne für
  Vorschau/Export. Exakte aktuelle Mindestfenster und Gates im Fachvertrag und
  Code prüfen; widersprüchliche historische Zahlen nicht ungeprüft übernehmen.
- Das Scoringdesign verlangt denselben wirksamen Bewertungskontext entlang der
  App. Die heutige Reihenfolge/Kandidatenkette steht in der einzigen
  [Fachbeschreibung](TRACKAUSWAHL-UND-MIXPOINT-FLUSS.md), nicht in alten Beispieltabellen.
- Die Hörtestpläne behandeln Vorbereitung, native Bewertung, Replay-Audit,
  Kalibrierung/Apply und Ranking als getrennte Schritte. Synthetische Labels oder
  Hardlinks sind keine unabhängigen musikalischen Referenzen. Ein erfolgreicher
  Teilpfad beweist keine vollständige Fit-/Apply-/Ranking-Kette.
- Die Berichte vom 04.10. enthalten datierte RAM-Render-, Cache-Reuse-, Worker-
  und App-Teilbelege sowie fehlgeschlagene Gesamtläufe. Die 26er-Analysebelege
  betrafen den Rekordbox-Fast-Path und beweisen keinen zusätzlichen Vollpfad.
  Tabellenpublikation, technische Renderbarkeit und menschliche Hörabnahme bleiben
  getrennt. Die zugehörigen exakten Temp-Pfade sind im Archivindex erhalten.
- Unbekannte Vocals bleiben unbekannt und sperren allein kein Paar; das ist
  keine allgemeine Lockerung der übrigen Qualitäts-/Timingbedingungen.
- Der Wächterbericht Cache109 beschreibt behobene damalige Einzelbefunde und
  aufgehobene TOR-Auflagen. Er erzeugt keine aktuelle Freigabe- oder Nachholpflicht.
- Das Qualitätsjournal hält auch widerlegte Diagnosen, fehlende unabhängige
  Messungen und offene Fragen fest. Archivierung bestätigt weder diese Befunde
  noch deren Behebung. Bei Wiederaufnahme Originalabschnitt und aktuellen Code prüfen.

Die jüngste Chatübergabe vom 20.10., die Deep-Analysis-Spezifikation und der
zurückgezogene VERITAS-Lauf samt Ungültigkeitskennzeichnung bleiben im Projekt.

## Konsolidierte historische Sessionnotizen (08.11.2026)

Die redundanten Sessionnotizen vom 25.08. und 19.09. wurden nach gesicherter
Inhaltsprüfung entfernt. Ihre alten Fortsetzungsaufträge und Laufzeitangaben
sind keine aktuellen Arbeitsaufträge oder Abnahmen. Ergänzend zu den obigen
Verträgen bleiben folgende fachliche Hinweise erhalten:

- Beatmatching verlangt gleiches effektives Tempo und passende Kickphase.
  Doppelschläge, Galoppieren und Drift sind technische Fehler; das importierte
  Grid muss auch in den tatsächlich verwendeten Mixbereichen stimmen.
- Lautheit und klangliche Ausgewogenheit über Vorlauf, Übergang und Nachlauf
  betrachten, nicht ausschließlich anhand eines kurzen Introausschnitts.
  Historisch wurde für Psytrance der 3-Band-EQ-Swap verlangt. Die damaligen
  numerischen Pegel-/Gatewerte sind keine ungeprüft zu übernehmenden aktuellen
  Konstanten; maßgeblich sind heutiger Code und Fachvertrag.
- Hörproben dürfen im Browser nicht durch veraltete Audiocaches ersetzt werden;
  Bewertungen müssen erhalten bleiben. Historische technische Rendernachweise
  ersetzen kein menschliches Hörurteil.
- Ein in einer Sandbox unsichtbarer Basisinterpreter beweist keine fehlende
  Python-Installation. Vor Neuinstallation die native Projektumgebung prüfen.
  Source-Start und gebündelte EXE haben unterschiedliche Laufzeitabhängigkeiten.

Historische Hörtestorte zur Wiederverwendung vorhandener Bewertungen:
`C:\Users\david\Music\HPG-Psytrance-Kandidaten-30Paare-2026-08-25` und
`C:\Users\david\Desktop\HPG-Techno-Prog-Melodic-50`. Existenz und heutiger
Bewertungsstand wurden bei dieser Dokumentbereinigung nicht neu geprüft.
