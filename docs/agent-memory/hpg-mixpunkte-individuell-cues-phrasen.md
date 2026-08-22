---
name: hpg-mixpunkte-individuell-cues-phrasen
description: "Nutzer-Grundsatz: Mixpunkte sind pro Track individuell, pro Paar mehrere gute Optionen — keine Einheitsregel suchen. Cues markieren Chorus-Starts, Rekordbox-Phrasen (PSSI) liegen lesbar unter D:\\PIONEER\\Master\\share, HPG nutzt sie noch nicht."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1c6bec25-3d10-4d63-8737-1657e093464b
  modified: 2026-08-21T02:47:48.085Z
---

Der Nutzer hat am 2026-08-21 (mehrfach, mit Nachdruck) gesagt: **Wo
gemischt wird, ist bei jedem Track individuell und jedes Mal anders, und
es gibt pro Paar mehr als eine gut klingende Moeglichkeit.** Es gibt keine
Regel wie "Mix-In = Cue 2" oder "Mix-Out = letzter Chorus", die fuer alle
gilt. Ausserdem: kein DJ mischt im Intro oder Outro.

**Why:** Ich hatte zweimal nach EINER Regel gefragt ("wo soll in Phrasen
gemischt werden"). Das ist die falsche Frage. Ein Einheits-Algorithmus
trifft den Geschmack nicht, deshalb landen Mixpunkte hoerbar falsch.

**How to apply:**
- Nicht nach einer festen Regel fragen oder eine bauen. Stattdessen pro
  Paar KANDIDATEN anbieten (Cues, Phrasengrenzen) und den Nutzer/Hoertest
  waehlen lassen; gelernt wird hoechstens eine Praeferenzverteilung.
- Fakten (gemessen 2026-08-21, 77 Psy-Tracks): jeder Track hat 6-11
  Rekordbox-Cues, fast alle unbenannt, **gesetzt auf Chorus/Drop-Starts**.
  HPG-Heuristik (analysis.py ~1672) nimmt Cue 2 = Mix-In, letzter Cue =
  Mix-Out; die floor-Quantisierung zieht den Mix-Out Median 21 s (eine
  Phrase) vor den Cue, die Blende laeuft dann ueber den Cue hinaus.
- Der eigene structure_analyzer raet Intro/Outro viel zu kurz (Psy: Intro-
  Ende Median 28 s, Outro 22 s; real 2-4 Phrasen).
- Rekordbox-Phrasen (PSSI-Tag: Intro/Up/Chorus/Down/Outro, mood 1=High)
  liegen in `D:\PIONEER\Master\share\PIONEER\USBANLZ\<AnalysisDataPath>\
  ANLZ0000.EXT` (4844 Dateien), pyrekordbox `AnlzFile.parse_file` liest
  sie; `AnalysisDataPath` aus master.db Content. HPG liest aus ANLZ nur
  PQTZ (Beatgrid), PSSI noch nicht. Der Nutzer will die Phrasen "dabei
  haben".
- Hoertest seit 2026-08-21: feste 3-Band-EQ-Blende (pro_eq_swap), alle
  Altnoten verworfen; mobiler Ordner `Music\HPG-Hoertest-Mobil`.

Siehe [[hpg-mixpoint-rundungsfehler]], [[hpg-scoring-an-2026-08-21]],
[[hpg-rekordbox-doppelte-pfade]].
