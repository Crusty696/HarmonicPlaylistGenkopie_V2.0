# Harmonic Playlist Generator (HPG) v3.7.2

Windows-App auf Basis von PyQt6 zur Vorbereitung harmonischer DJ-Sets.
HPG analysiert ausgewählte Musik, bewertet Trackpaarungen und Mixpunkte,
erstellt eine Playlist und macht geplante Übergänge als Vorschau hörbar.
Die Ergebnisse lassen sich als M3U8 oder Rekordbox-XML exportieren.

Quellenabgleich: 26.10.2026. **Der Entwicklungsstand besitzt keine vollständige
Produkt- oder musikalische Abnahme.** Offene Fehler, Testresultate und datierte
App-Belege stehen im [Quellen- und Nachweisstand](PRODUCTION_STATUS.md).

## Start aus dem Projekt

Voraussetzung: Python 3.12.1+ innerhalb der 3.12-Serie und die vorhandene
Projektumgebung `venv312`. Keine automatische Installation durch diese Anleitung.

```bat
venv312\Scripts\python.exe main.py
```

Alternativ `Start.bat` verwenden. Neue Umgebungen werden mit Python 3.12
angelegt und den Pins in [requirements.txt](requirements.txt) entsprechend
eingerichtet; Installationen benötigen im Agentenauftrag eine ausdrückliche Freigabe.

## Arbeitsablauf

1. Musikordner auswählen; Originaldateien bleiben am Quellort.
2. Analysieren oder passende vorhandene Analysen wiederverwenden. Frische
   Analyse und Cache-Nutzung sind unterschiedliche Abläufe.
3. Strategie und Toleranzen wählen, Playlist erzeugen.
4. Geplante Übergänge, Messdiagnosen und hörbare Vorschauen in der App prüfen.
   Nicht jedes Nachbarpaar besitzt automatisch einen zulässigen Übergang.
5. Playlist und freigegebene Mixpunktdaten exportieren.

## Analyse und Vorschau

- Tempo, Tonart/Camelot, Energie, Lautheit, Groove, Bass und Klangmerkmale.
- Native Beat-/Takt-/Phrasenanalyse mit geprüfter Herkunft und Audio-Rasterprüfung;
  DSP-Merkmalsfenster und optionale Rekordbox-Metadaten ergänzen den Ablauf.
- Lokale Mixpunkt-Kandidaten und gemeinsame Kettenwahl für benachbarte Tracks.
- Ein gemeinsames `PlaylistGenerationResult` mit `TransitionPlan`-Daten für
  Oberfläche, Vorschau und Export.
- Tempoanpassung der Vorschau über das vorhandene Pedalboard; strikte
  Kick-/Beat-Synchronprüfung bleibt erhalten.
- Optionale LLM-Metadaten über LM Studio/Ollama sind standardmäßig deaktiviert.
  Dieser Text-LLM-Pfad hört kein Audio; native Audioanalyse ist davon getrennt.

Technische Freigabe einer nativen Taktposition ist keine unabhängige musikalische
Bestätigung. Interne Scores sind keine Wahrscheinlichkeiten für einen guten Mix.

## Optionale lokale LLM-Metadaten

Die KI-Auswahl ist beim GUI-Start deaktiviert. Die Voreinstellungen in
`hpg_core/config.py` sind LM Studio, `granite-4.0-h-tiny`, maximal 400 Tokens
und 120 Sekunden Timeout (Quellenabgleich 26.10.2026). Diese Einstellungen
beweisen weder einen laufenden Server noch lokale Modellverfügbarkeit.
Providerstart und Antwortverarbeitung stehen in `hpg_core/ai_launcher.py`
und `hpg_core/ai_engine.py`. Der [Datenvertrag](docs/DATA_AND_VALIDATION_CONTRACT.md)
trennt Metadaten von Audioanalyse und musikalischer Qualität.

## Starter und Entwicklungswerkzeuge

| Datei | Zweck |
|---|---|
| `Start.bat` | App aus der Projektumgebung starten |
| `build.bat` | EXE bauen; auch von CI verwendet |
| `build_installer.bat` | Installer aus der vorhandenen EXE bauen; auch von CI verwendet |
| `Start_Hoertest.bat` | optionaler separater Hörtest-Manager |
| `manual_test.bat` | optionaler technischer Einzeltrack-Bericht; aktuellen Quellordner mit `--folder` angeben und Testcache isolieren |

Die beiden Zusatzstarter sind für den normalen App-Start nicht erforderlich.
Der native Hörtest verwendet Quellreferenzen und RAM-Wiedergabe. Kein
Kopieren von Originalmusik und keine musikalische Abnahme allein durch Qt-Laden.

## Strategien

8 sorting strategies — kanonische Namen aus `hpg_core/playlist.py::STRATEGIES`:

| Strategie | Zielrichtung |
|---|---|
| Harmonic Flow | harmonische Paarungen und nutzbare Übergangskette |
| Warm-Up | steigendes Tempo |
| Cool-Down | fallendes Tempo |
| Peak-Time | Verlauf mit einstellbarer Peak-Position |
| Energy Wave | wechselnder Energieverlauf |
| Genre Flow | Genregruppen und passende Verbindungen |
| Consistent | geringe Tempo-/Energiesprünge |
| Context Flow | Energieziel, Verlauf und Genrekontext |

Details: [Playlist-Entscheidungen und Mixpunkte](docs/TRACKAUSWAHL-UND-MIXPOINT-FLUSS.md).

## Formate und native Voraussetzungen

Die Dateiauswahl wird durch `SUPPORTED_AUDIO_EXTENSIONS` in `hpg_core/config.py`
festgelegt: WAV/WAVE, AIFF/AIF, MP3, FLAC/FLA, MP4/M4A/AAC, OGG und WMA.
Eine akzeptierte Endung garantiert keinen erfolgreichen Decoder für jede Datei.
Die nativen Rekordbox-Factorys besitzen einen engeren, separat geprüften Vertrag
in `hpg_core/ai_models/native_audio_reader.py`; OGG/WMA gehören nicht zu dieser
Factoryliste. Modell-/DLL-Artefakte müssen zur geprüften lokalen Umgebung passen.

## Quellen finden

| Bereich | Quelle |
|---|---|
| GUI und Worker | `main.py` |
| Analyse und Datenmodell | `hpg_core/analysis.py`, `models.py` |
| Native Modelle, Reader und Prozesse | `hpg_core/ai_models/` |
| Persistenz und Cacheversion | `hpg_core/caching.py` |
| Playlist und Mixpunktbewertung | `playlist.py`, `pair_candidates.py`, `dj_brain.py` in `hpg_core/` |
| Vorschau | `hpg_core/transition_renderer.py`, `preview_stretch.py` |
| Export | `hpg_core/exporters/` |
| Prüfungen und Hilfswerkzeuge | `tests/`, `tools/` |
| Arbeitsregeln und Fachskills | `AGENTS.md`, `.agents/skills/` |

[Projektwissen](docs/PROJECT_KNOWLEDGE.md) enthält erhaltene Entscheidungen.
[Jüngste fachliche Übergabe](docs/CHAT_UEBERGABE_2026-10-20.md) enthält die offenen
Deep-Sky-/W- und Gesamtplaylist-Fragen. Historische Aufträge nicht automatisch starten.

## Tests und Builds

Der Abschluss-Volltest für entsprechende Produktänderungen lautet:

```bat
venv312\Scripts\python.exe -m pytest tests/ --tb=short -q
```

`pytest.ini` bestimmt Parallelisierung und Coverage; der Standard waehlt
Tests mit Marker `slow` ab. Vorhandene gültige Belege
wiederverwenden; Dokumentationsausnahmen und Schutzregeln stehen in AGENTS.md.
Testzustände isolieren, Produktivcache und vorhandene Coverage-Dateien erhalten.

`build.bat`, `HPG.spec` und `build_installer.bat` beschreiben die Buildwege.
Ein Build erfolgt erst nach Funktionsnachweisen und im beauftragten Umfang.
Die vorhandene EXE ist durch ihre bloße Existenz nicht diesem Quellstand zugeordnet;
Abnahme benötigt absoluten EXE-Pfad, SHA-256 und ausgeführten EXE-Nachweis.

## Lizenz

[MIT License](LICENSE). Veröffentlichungen und deren zugehörige Belege sind im
[Repository](https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0) zu prüfen;
diese lokale Quellenpflege bestätigt keine aktuelle Online-Releaseversion.
