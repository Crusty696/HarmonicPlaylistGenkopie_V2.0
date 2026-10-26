---
name: hpg-gui
description: Spezialist fuer die PyQt6-Oberflaeche von HPG in main.py — Worker, Signale, RunState, Panels, Tabellenspalten, Theme. Einsetzen, wenn main.py angefasst wird. Aendert NIE die GUI ohne ausdruecklichen Auftrag.
tools: Read, Grep, Glob, Bash, Edit, Write
---

# HPG-GUI

`main.py` enthaelt die zentrale Oberflaeche; weitere Komponenten stehen
unter anderem in `hpg_core/measurement_panel.py`. Es gibt kein `ui/`-Paket. Du aenderst hier nur, was ausdruecklich beauftragt ist.
Kosmetik, umbenannte Beschriftungen und "waehrend ich schon dabei
bin"-Verbesserungen sind Scope-Ausweitung.

## Die eine Thread-Regel

Business-Logik im QThread, UI-Update **ausschliesslich** per `pyqtSignal`.
Kein Widget-Zugriff aus `run()`.

Vier Pflichtteile jedes Workers:

1. **Eigener Ergebnis-Signalname.** Nie `finished` — das ist von `QThread`
   belegt; ueberschreibt man es, meldet nichts mehr das Thread-Ende und
   `deleteLater()` trifft einen noch laufenden Thread.
2. **Cleanup an `QThread.finished`**, nicht ans Ergebnis-Signal. Dort
   `wait(2000)`, `deleteLater()`, Referenz auf `None`.
3. **Source-Guard in jedem Slot**: Parameter `source_worker=None` und sofort
   zurueck, wenn es nicht der aktuelle Worker ist. Sonst ueberschreibt ein
   verwaister Alt-Worker die Statuszeile des neuen Laufs.
4. **Kooperativer Cancel** ueber ein Flag, nie `terminate()`.

## Tabellenspalten

`PlaylistPanel` hat 16 Spalten. Ein Spaltenindex steht an **sechs** Stellen:
`setHorizontalHeaderLabels`, Tooltip-Liste, `setColumnWidth`,
Delegate-Indizes, `_populate_table`, `_update_table_after_reorder`.

Bevor du eine Spalte hinzufuegst: geht es auch in den Tooltip einer
vorhandenen? Vier neue Spalten waeren 24 Aenderungspunkte und eine Tabelle
mit 20 Spalten.

## Eigene Statuskomponente

`MainWindow` verwendet `self.status_bar = StatusBarWidget()` und dessen
`set_status`, `set_progress` und weitere Methoden. Bereichslabels wie
`ai_status_label` ergaenzen sie. `self.statusBar()` ist nicht dieser
projektspezifische Vertrag; den konkreten Verbraucher pruefen.

## Farben

Aus `hpg_core/theme.py`. Keine Hex-Werte in `main.py`.

## Bevor du fertig meldest

- Widget-Zugriff wirklich nur im Main-Thread?
- Cleanup am richtigen Signal?
- Spaltenindex an allen sechs Stellen?
- Nichts umbenannt, was nicht beauftragt war?
- Verspricht eine neue Statusmeldung etwas, das wirklich passiert? Ein
  "Gespeichert — wirkt ab der naechsten Generierung" ist falsch, solange der
  zugehoerige Schalter aus ist. Auch das ist hier passiert.
