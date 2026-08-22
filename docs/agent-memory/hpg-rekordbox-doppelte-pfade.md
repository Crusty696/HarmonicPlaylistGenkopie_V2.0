---
name: hpg-rekordbox-doppelte-pfade
description: Davids Rekordbox-Collection fuehrt dieselben Tracks doppelt; analysiert ist nur der Ordner "neue Psy-Trance, Progressive nur Beatport musik"
metadata:
  type: project
---

Davids Rekordbox-Collection enthaelt dieselben Tracks unter zwei Pfaden. Nur
einer davon ist analysiert (Stand 2026-08-15):

- `D:\neue Psy-Trance, Progressive nur Beatport musik\` — 1400 Dateien, 903 mit
  BPM, 879 mit ANLZ-Beatgrid, **kein** Record ohne BPM. Das ist der brauchbare
  Bestand fuer Fast-Path- und Beatgrid-Messungen.
- `D:\beatport_tracks_2025-08\` — Zweitkopien derselben Tracks, Records
  existieren, aber mit `BPM=0` und ohne Analyse.

Fuer HPG-Laeufe auf echten Daten immer den erstgenannten Ordner nehmen. Laeuft
man gegen `beatport_tracks_2025-08`, faellt die Pipeline still auf librosa
zurueck und die Rekordbox-Akzeptanzzahlen sehen kaputt aus, obwohl der Importer
korrekt arbeitet.

**Warum:** Der Basename-Index des Importers liefert bei mehrdeutigen Basenames
`None` — er verweigert die Zuordnung bewusst, statt zu raten. Das sah in der
Messung wie "Importer findet nichts" aus, war aber die Duplikat-Abwehr.

**How to apply:** Vor jedem Realdaten-Lauf pruefen, ob der Zielordner
analysierte Rekordbox-Records hat (BPM != 0), nicht nur ob Records existieren.
BPM steht in Rekordbox als Ganzzahl x100 (14200 = 142,00 BPM).

Siehe auch [[hpg-venv312-environment]].
