# HPG — Quellenstand statt pauschaler Produktionsfreigabe

Aktueller Arbeitsstand: 16.10.2026, Cache104. Maßgebliche Umsetzungsmatrix und
datierte Belege: [Deep-Analysis-Auftrag](specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md).
Native Beats/Takt/Phrasen, Stem-/Embedding-Metadaten, Playlist-Vorschau und
XML-Export sind angebunden. Ein normaler GUI-Vorschaulauf mit zwei Originalen
lieferte einen RAM-Clip; dessen musikalische Abnahme steht aus. Weitere native
Readerformate, unabhängige Qualitätsreferenzen und die Wächterprüfung bleiben offen.
Kein neuer EXE-Build und keine vollständige Produktfreigabe.

## Historische Befunde bis zur nativen Gesamtpipeline

Cache-Nachtrag vom 13.10.2026: Cache-Version 96 in hpg_core/caching.py.
Die Feintempokorrektur im Vollpfad verwendet einen festen 32-s-Abschnitt
und drei getrennte 16-s-Prueffenster. Nur ein bestaetigter Kandidat darf ein
nicht bestaetigtes bisheriges Tempo ersetzen; der Rekordbox-Fast-Path bleibt
unveraendert. Das ist keine unabhaengige Bestaetigung der musikalischen Eins.
Vollstaendige Beat-Energiefenster mit anteiligen Rand-Samples und gueltigen
lokalen Nachbarn verhindern die belegten kuenstlichen Lautheitsakzente.
Downbeat-Merkmale verwenden bei eindeutiger Beatzuordnung dieselbe Fold-Phase
wie der abschliessende Anker. Widerspruechliche Zuordnungen behalten die
bisherigen Featurezeiten; Synchronpruefungen und Grenzwerte bleiben erhalten.
Die Struktur im Vollpfad verwendet das gemeinsame BPM-Raster statt des
abweichenden Medians hopgerasterter Beatintervalle. Die korrigierte Zuordnung
physischer Beats zur Taktphase bleibt erhalten.
Der begrenzte Downbeat-Tempo-Retry bleibt bestehen. Er wird nur
bei inkommensurablem Erstversuch und nach unveraenderter Konfidenz- und
Drei-Fenster-Pruefung uebernommen. Alte Cachedateien bleiben erhalten.

## Einstieg

- [Quellen und dauerhaftes Wissen](docs/PROJECT_KNOWLEDGE.md)
- [Aktueller Auftrag und offene Grenzen](specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md)
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
