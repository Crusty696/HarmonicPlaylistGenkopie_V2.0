# HPG — Quellenstand statt pauschaler Produktionsfreigabe

Statischer Quellenabgleich: 04.10.2026. App-Version 3.7.2 aus
hpg_core/app_metadata.py, Cache-Version 46 aus hpg_core/caching.py.
Diese Angaben sind keine Laufzeit-, Build- oder musikalische Abnahme.

## Einstieg

- [Quellen und dauerhaftes Wissen](docs/PROJECT_KNOWLEDGE.md)
- [Aktuelle Session-Uebergabe und offene Arbeit](docs/SESSION_HANDOFF_2026-10-04.md)
- [Verbindliche Arbeits- und Nachweisregeln](AGENTS.md)
- [Datierter nativer Hoertest-Bericht](docs/HOERTEST_NATIVE_2026-10-04.md)
- [Bereinigungsnachweis](docs/CLEANUP_2026-10-04.md)

Historische Testzahlen, Serverzustaende, Cache-Zeilen und Branch-Hashes wurden
hier entfernt. Den aktuellen Git- und Laufzustand direkt pruefen. Vorhandene
Testbelege nur innerhalb ihrer nachgewiesenen Eingaben und Hashes verwenden.
Der native Bericht trennt einen fehlgeschlagenen Gesamtlauf von gezielten
Nachtests; daraus darf kein neuer gruener Gesamtlauf gemacht werden.

Die fruehere Bereinigung aenderte keine Produktlogik. Die anschliessende
Implementierung hat den Quellstand erweitert; genaue Paketbelege und offene
Luecken stehen in der Session-Uebergabe. Keine aktuelle Gesamtabnahme oder
neue EXE-Freigabe behauptet. Ein gespeicherter Zwischenstand ist kein Release.
Die Mehrordner-Hoertest-Persistenz und der native Einstieg aus dem
Sammlungsdialog sind inzwischen implementiert und gezielt getestet. Der
vollstaendige Originalmusik-Hoertest samt menschlicher Bewertung und die
Abnahme der weiteren Planpakete stehen weiter aus. Ein isolierter Pilot mit
zwei unveraenderten Originaltracks erzeugte einen Satz mit fuenf Varianten;
zwei lieferten WAV-Bytes im RAM, drei scheiterten an der Kickphasenpruefung.
Neue Noten fuer RAM-Clips sind im nativen Dialog nun an erfolgreiches
Rendern gebunden. Alte Noten sind dadurch aber nicht aus dem Fit entfernt;
die abgewiesenen Varianten bleiben technisch unhoerbar. Der
Sammlungs-Einstieg ist daher kein zuverlaessig voll nutzbarer Trainingsablauf.
