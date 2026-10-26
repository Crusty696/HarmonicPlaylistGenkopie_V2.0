# HPG — Quellen- und Nachweisstand

Abgleich am 26.10.2026 mit dem lokalen Code und den Projektchats.
Quellstand: `9edc88029b2f85c911367760e2b701989e298210`; App v3.7.2,
Cache-Version 183 gemäß `hpg_core/caching.py`. Lokale Dokumentänderungen
sind zusätzlich vorhanden. Dies ist keine Release- oder musikalische Freigabe.

## Implementierung laut Code

Native Beat-/Takt-/Phrasenverarbeitung, Audio-Rasterprüfung, Snapshot-
Wiederverwendung und lokale Kandidaten sind in die Analyse eingebunden.
Native Reader-Factorys umfassen WAV/AIFF, MP3, FLAC, AAC und M4A/MP4;
ALAC wird gesondert erkannt. Die alte WAV/AIFF-only-Aussage vom 16.10. gilt
nicht mehr als aktuelle Implementierungsbeschreibung. Codecvarianten und
vollständige Wrapperparität benötigen weiterhin ihre jeweiligen Nachweise.

Native Taktposition kann mit verifiziertem nativen Grid für Playlist und
Hörproben verwendet werden; unabhängige musikalische Bestätigung wird dadurch
nicht behauptet. Tempoanpassung läuft über `hpg_core/preview_stretch.py`
mit dem vorhandenen Pedalboard. Die 6-ms-Kick-/Beatprüfung bleibt erhalten.

## Datierte Tests und Originaltrack-Belege

Der jüngste fachliche Chatstand ist in der
[Übergabe vom 20.10.2026](docs/CHAT_UEBERGABE_2026-10-20.md) erhalten.

- Volltest vom 20.10.: **76 fehlgeschlagen, 6319 bestanden**, 735,73 s.
  Die Schlusszeile in `%TEMP%/hpg-final-code-20261020-pytest.log` wurde am
  26.10. erneut gelesen. Dieser Lauf ist fehlgeschlagen und liegt vor späteren
  Rendereränderungen; er ist kein Abschlussbeleg des aktuellen Quellstands.
- Sechs gezielte Pitch-/Stereo-Stretch-Fälle bestanden laut Chatübergabe nach
  der letzten Rendereränderung. Hier nicht erneut ausgeführt und nicht als
  vollständige Suite ausgegeben.
- Laut Übergabe: 26/26 technische Beatgrids und native Phrasenanalysen;
  mindestens eine App-Hörprobe für 16/17 ursprünglich gesperrte Tracks.
  Die Gesamtplaylist enthält 18 geplante von 25 Grenzen.
- Existenz der 26er-Herkunftsdatei sowie der finalen Stretch-/Paarungs-GUI-
  Events am 26.10. geprüft. Keine erneute Audioanalyse oder musikalische Abnahme.
- Die drei Originaltracks aus Cache108/109 und ihre GUI-Events vom 16.10.
  bleiben ältere Teilbelege; Details in der Deep-Analysis-Spezifikation.

## Offene Arbeit

Deep Sky besitzt laut Übergabe native Ergebnisse, aber sein zusammengesetzter
Trackdatensatz scheiterte an der Diagnoseprovenienz. W hat deshalb noch keine
belegte neue Paarvorschau. Sieben Grenzen der Gesamtplaylist bleiben ungeplant;
separate erfolgreiche Paare beweisen keine lückenlose Gesamtplaylist.
Die 2-BPM-Grenze bleibt erhalten. Keine abgeschlossenen Analysen wiederholen.

Ein grüner Abschluss-Volltest des finalen Produktcodes, vollständige frische
native App-Abnahme samt Cache-Reuse, unabhängige musikalische Bewertung und
eine zu genau diesem Stand geprüfte EXE sind weiterhin nicht belegt.

## Quellen und Arbeitsregeln

- [Projektwissen](docs/PROJECT_KNOWLEDGE.md)
- [AGENTS.md](AGENTS.md)
- [Deep-Analysis-Spezifikation und Verlauf](specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md)
- [Historisches Archiv einschließlich Wächterbericht](docs/PROJECT_KNOWLEDGE.md#historisches-archiv)
- [Bereinigung vom 26.10.2026](docs/CLEANUP_2026-10-26.md)

Wächterprüfungen erfolgen auf Anforderung. Fehlende frühere Tore erzeugen
keine Nachholpflicht. Diese Regel ersetzt keine fachlichen Nachweise.
