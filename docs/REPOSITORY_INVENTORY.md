# Repository-Inventar und Pruefumfang

Lokaler Gesamtbestand vom 26.10.2026 nach Zusammenfuehrung der GitHub-Arbeit,
Ausgangscommit `2ca3b64cfd52553b801955815a82fd3d18851dc1`.
Die anschliessenden Dokumentkorrekturen sind im Bereinigungsbericht beschrieben.

## Vollstaendigkeit der lokalen Erfassung

- 43664 Dateieintraege und 10130 besuchte Verzeichnisse.
- Keine Fehler beim Lesen der Metadaten; keine Begrenzung/Abschneidung des Scans.
- 2579 Verzeichnisverknuepfungen/Junctions erfasst,
  deren Ziele nicht verfolgt wurden; `.git` als eigener Metadatenbereich ausgeschlossen.
- 522 versionierte Dateien. Die detaillierten relativen Pfade und
  Metadaten stehen in der externen `inventory.json`.
- 188 versionierte Dokument-, Anweisungs-, Starter-, Konfigurations- und
  Buildtextdateien wurden als Pruefkorpus erfasst, einschliesslich beider
  Skillspiegel, Codex-Rollen, HTML, BAT, PS1, YAML und TOML.

Verzeichniszahlen dieses Scans sind keine Anzahl fachlich gepruefter Dokumente.
Dateimetadaten, Quellenabgleich, Tests und musikalische Abnahme bleiben getrennt.

## Erhaltene Bereiche

Projektquellen und eigene Anweisungen wurden rekursiv geprueft. Der lokale
Bestand umfasst ausserdem die virtuelle Umgebung, generierte Bytecode-Dateien,
Testtemporaerdateien, historische Auditlaeufe und Validierungsartefakte.
Diese werden im Inventar erfasst, nicht als aktuelle Produktanleitung behandelt.
Ihre Fremd-/Rohinhalte werden nicht umgeschrieben. Originalmusik, DB-/Cache-,
WAL-/SHM-, Lock-/Coverage-Dateien und Claude-Autopilot-Artefakte sind geschuetzt.

Die drei HTML-Visualisierungen sind am sichtbaren Einstieg als historische
Entwuerfe gekennzeichnet. Die PNG-Systemkarte ist im aktuellen Flussdokument
als historische Illustration eingeordnet. Die zwei Sessionnotizen unter
memory/ sind datierte Quellen, keine aktuellen Ausfuehrungsanweisungen.
Zurueckgezogene VERITAS-Berichte und deren UNGUELTIG-Kennzeichnung bleiben erhalten.

## Aktuelle Quellen und Werkzeuge

- [README](../README.md): Benutzeranleitung und fuenf vorhandene BAT-Einstiege.
- [Projektwissen](PROJECT_KNOWLEDGE.md): Nutzervertraege und Archivwegweiser.
- [Bereinigungsbericht](CLEANUP_2026-10-26.md): Schritte, Sicherungen und Grenzen.
- `tools/repo_inventory.py`: lesender Git-/Dateimetadatenbericht;
  `--deep-local` erfasst auch lokale ignorierte Unterordner. Bei Verwendung
  die Ausgabe `truncated` und Fehlerliste pruefen. Die aktuelle Abschluss-
  erfassung wurde separat ohne Mengenlimit und mit expliziter Windows-
  Reparse-Erkennung ausgefuehrt; das ist kein Laufzeitnachweis dieses Werkzeugs.

Die zuvor genannten Bestandszahlen von Commit 63ea758a waren historisch.
Die GitHub-Bereinigung entfernte benchmark_rekordbox.py und zwei alte
Testbeispiele; die M3U8-Regression liegt in tests/test_exporters.py.
Der Bericht vom 04.10. ist extern archiviert, sein damaliges JSON-Manifest
bleibt datierter Nachweis. Kein Link auf eine nicht mehr vorhandene Anleitung.

## Pruefunterlagen

`E:\AI\HPG-cleanup-recovery\2026-10-26-final-audit` enthaelt Inventar,
Dokumentliste, Originalsicherungen, Aenderungsmanifest und Pruefergebnisse.
Diese Bestandsaufnahme ist keine Fehlerfreiheits-, Laufzeit- oder Musikabnahme.
