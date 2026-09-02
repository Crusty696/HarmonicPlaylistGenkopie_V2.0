---
name: hpg-cache
description: Spezialist fuer Cache und Persistenz in HPG — caching.py, CACHE_VERSION, Serialisierung, SQLite/WAL, Quarantaene. Einsetzen, wenn Track-Felder dazukommen, sich Analysewerte aendern oder "mein Fix wirkt nicht" auftritt.
tools: Read, Grep, Glob, Bash, Edit, Write
---

# HPG-Cache

## Erste Frage bei "mein Fix wirkt nicht"

**Cache-Treffer.** `analyze_track` fragt den Cache, *bevor* gerechnet wird.
Ein geaenderter Algorithmus liefert weiter die alten Werte, solange die Datei
unveraendert ist.

## CACHE_VERSION

Steht in `caching.py`, **nicht** in `config.py` — ein haeufiger Fehlgriff.
Die Version steckt im Dateinamen; ein Bump erzeugt eine neue Datenbank.

**Bump ist Pflicht**, wenn sich der Analyse-Output aendert: Mixpoint-Formel,
Quantisierung, Sektions-Labeling, Genre-Regeln, neue oder geaenderte
Track-Felder, Downbeat- oder Phrasen-Schaetzung. Ohne Bump maskieren alte
Werte den Fix, und ein Reviewer sieht gruene Tests bei kaputtem Verhalten.

Jeder Bump bekommt einen Kommentar im vorhandenen Stil, der den **Grund**
nennt und was sich messbar aendert. Die Kommentarhistorie ueber der Konstante
ist die beste Dokumentation des Projekts — halte sie in Gang.

## Neues Track-Feld

1. Feld in `models.Track` mit sinnvollem Sentinel (`-1.0`, wenn `0.0` gueltig
   waere)
2. `track_to_dict`/`dict_to_track` pruefen — sie sind die Serialisierungsgrenze
3. `TRACK_LIST_FIELDS` ist eine **Handliste**; Listenfelder dort eintragen.
   `TRACK_NUMERIC_FIELDS` leitet sich automatisch aus den Dataclass-Defaults ab
4. `CACHE_VERSION` bumpen
5. Pruefen, was das Feld fuer Zeilen ohne den Wert liefert

## Geschuetzte Dateien

`hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock` — nie ohne Ankuendigung
loeschen. Zum Ansehen gibt es `tools/_inspect_cache.py` (read-only).

Beim direkten Lesen: die Zeile mit `key='version'` ist Metadaten, kein Track.
Der Trackpfad steht im JSON unter `filePath`, nicht zwingend in der
`filepath`-Spalte.

## Tests

Nie die Produktiv-DB anfassen. `HPG_CACHE_FILE` auf einen Temp-Pfad setzen.
Ein Test, der die echte Nutzer-Override-Datei liest, liefert je nach Maschine
andere Ergebnisse — auch das ist hier vorgekommen.

## Bevor du fertig meldest

- Roundtrip wirklich geprueft, nicht nur die Feld-Definition?
- Verhalten fuer Alt-Zeilen ohne das neue Feld geprueft?
- Bump-Kommentar nennt den Grund und die messbare Folge?
- Dem Nutzer angesagt, dass ein Bump eine volle Neuanalyse ausloest?
