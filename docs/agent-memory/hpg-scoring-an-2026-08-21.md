---
name: hpg-scoring-an-2026-08-21
description: "TRANSITION_FEATURES_ENABLED seit 2026-08-21 AN mit Groove 0.30 (verteilt, nicht aus Harmonik allein); Startwerte, Hoertest soll sie ersetzen"
metadata: 
  node_type: memory
  type: project
  originSessionId: cd653385-4f77-4ce3-ac65-f85e435be7bd
  modified: 2026-08-21T01:17:17.085Z
---

Am 2026-08-21 wurde `TRANSITION_FEATURES_ENABLED` auf True gesetzt (commit
7caf50e auf main) mit groove 0.30 / harmonic 0.16 / bpm,energy,genre je
0.12. Der Nutzer entschied sich nach Messung fuer "Weg 2" (an + Groove
hoeher) und gegen "Weg 3" (erst Hoertest, dann an) — Anlass war, dass die
App Paare mit unpassendem Rhythmus waehlte.

**Why:** Schalter an mit den alten Defaults (groove 0.12) machte die
Playlist messbar NICHT besser (groove-Median 0.90 -> 0.89). Erst ab 0.30
kippte es. "0.30 allein aus Harmonik" kostete ein Drittel der
Tonart-Treffer — verworfen. Die Verteilung ueber vier Faktoren war der
Kompromiss.

**How to apply:** Die 0.30 sind Startwerte, keine gemessenen. Wenn der
Hoertest (Music\HPG-Psytrance, Music\HPG-Hoertest) genug Noten hat,
Gewichte daraus schaetzen und die Tabelle in genres.py ersetzen. Melodic
Techno verliert mit dem Schalter die Haelfte der Camelot-Treffer — dort
evtl. eigener Genre-Eintrag. Siehe [[hpg-groove-scoring-2026-08-20]] fuer
den Vorlauf und docs/HANDOFF-2026-08-21-scoring-an.md fuer Details.
