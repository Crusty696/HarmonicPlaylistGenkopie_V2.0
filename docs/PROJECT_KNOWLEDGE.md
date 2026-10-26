# HPG: Quellen und dauerhaftes Wissen

Quellenabgleich vom 26.10.2026. Diese Datei enthält Nutzerverträge und den
Weg zum aktuellen Code. Sie ist keine Produktabnahme.

## Einstieg und Quellenrang

1. Aktueller Nutzerauftrag und [AGENTS.md](../AGENTS.md) bestimmen den Umfang.
2. [Produktleitlinie](../MEMORY.md), `hpg-orientation` und Fachskills führen zum Code.
3. [Quellen- und Nachweisstand](../PRODUCTION_STATUS.md) trennt Implementierung,
   alte Testresultate, Originaltrack-Läufe und musikalische Bewertung.
4. [Übergabe vom 20.10.](CHAT_UEBERGABE_2026-10-20.md) enthält die jüngste
   fachliche Chatübergabe, Rohbelegpfade und offene Fehler. Historische
   Fortsetzungsbefehle werden durch Lesen nicht zum aktuellen Auftrag.
5. [Deep-Analysis-Spezifikation](../specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md)
   bewahrt Ziele und datierte Umsetzungsgeschichte. Ihr älterer Beispielcode
   ist kein aktueller API-Vertrag. Der Kopf ordnet den Stand ein.
6. Allgemeine Ausführungsregeln stehen in AGENTS.md, Deep-Analysis-Besonderheiten
   im [Fachskill](../.agents/skills/hpg-deep-analysis/SKILL.md). Keine zusätzliche Regelkopie.

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
Historische HTML-Visualisierungen und memory-Sessionnotizen sind als solche
gekennzeichnet; ihre Beispiele erzeugen keine heutigen Arbeitsauftraege.
Die Sicherung vom 04.10. und `cleanup-manifest-2026-10-04.json` bleiben erhalten.

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
