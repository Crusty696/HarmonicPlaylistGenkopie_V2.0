---
name: hpg-groove-scoring-2026-08-20
description: "Groove/Bass/Timbre/Mood-Scoring gebaut, Kalibrierung gescheitert — Branch feature/groove-scoring, Schalter aus, Handoff-Doku im Repo"
metadata: 
  node_type: memory
  type: project
  originSessionId: 602c084c-5127-4b2b-b848-63a0fe84aba7
  modified: 2026-08-20T01:13:29.012Z
---

Branch `feature/groove-scoring` (47 Commits, Suite 1658 gruen) ergaenzt die
Playlist-Zielfunktion um Groove, Bassdruck, Klangfarbe und Stimmung — hinter
`TRANSITION_FEATURES_ENABLED`, das auf `False` steht.

**Die Kalibrierung aus DJ-Mixen ist gescheitert und bleibt es vorerst.** Nach
Korrektur von vier methodischen Fehlern blieb ein Gewichtsbudget von 0,0121
(Psytrance) bzw. 0,0000 (Techno). Bindende Grenze ist die Zahl unabhaengiger
Mixe — 6 bis 8 vorhanden, noetig waeren 25 bis 30 je Genre.
`hpg_core/data/transition_tolerances.json` steht deshalb bewusst auf `{}`.

**Wichtigster Nebenbefund:** die Zahlen, die die Reihenfolge heute wirklich
bestimmen, sind ungemessen — `0.44/0.28/0.28` in `playlist.py` und
`GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2`, mal 36 handgesetzte
Genre-Kompatibilitaetswerte. Der gebaute Hoertest (`tools/rate_transitions.py`)
koennte genau die messen.

Vollstaendiger Stand mit offenen Punkten:
`docs/HANDOFF-2026-08-20-groove-scoring.md` im Repo.

Siehe auch [[hpg-waechter-und-agententeam]] und [[hpg-mixpoint-rundungsfehler]].
