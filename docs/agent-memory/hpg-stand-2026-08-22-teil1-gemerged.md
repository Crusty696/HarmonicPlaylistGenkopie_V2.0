---
name: hpg-stand-2026-08-22-teil1-gemerged
description: "Stand 2026-08-22 (Nacht): Kandidaten Teil 1–4 komplett auf main gemerged (2d1684b), Spec 2026-08-21 vollstaendig umgesetzt; offen nur Hoerproben (Checklisten Handoff Teil 3/4); /goal-Modus (autonom, Hoerproben nur Checkliste); Einstieg docs/HANDOFF-2026-08-22-stand-fuer-neuen-agenten.md"
metadata:
  node_type: memory
  type: project
  originSessionId: 261b9a6b-87fd-4d13-aa8d-3e85b22fb493
  modified: 2026-08-22T21:52:44.280Z
---

Stand 2026-08-22 (Nacht): Mixpunkt-Kandidaten **Teil 1** (Datenmodell, `f18815b`),
**Teil 2** (Paarung/Bewertung `pair_candidates.py`, `ca15013`), **Teil 3**
(Hoertest-Kandidatenmodus, `candidate_preferences.py`, `5ce9ddb`) und **Teil 4**
(App-Anbindung: `candidate_choices.py`, Kandidatenpfad + Kettenwahl per DP in
`playlist.py`, GUI-Kandidatentabelle mit Wahl, Regler Lautheit, BPM-Default 2.0,
Rekordbox-Export `HPG K<n>`, `tools/playlist_kandidaten_messen.py`; Merge
`2d1684b`) sind auf `main`. Je Teil ein Handoff
`docs/HANDOFF-2026-08-22-kandidaten-teilN.md` mit Messzahlen und Waechter-Urteilen
(Teil 4: Tor 1 und Tor 2 MIT AUFLAGEN, eingearbeitet; 20 Entscheidungen im Plan).
Suite auf main: 1871 passed. Endmessung Teil 4 (231 Tracks): 220/230 Paare mit
Kandidat, Intro/Outro-Verletzungen 0, Overlap-Abweichungen 0, Cue-Gate 2 =
Ketten-Neustarts, Score-Median 79 vs. 83, Generierung 51 s vs. 2 s ohne.

Offen sind NUR Hoerproben (Mensch): Checklisten in den Handoffs Teil 3 (Hoertest
Kandidatenmodus, `fit`, Uebernahme) und Teil 4 (App-Preview, Wahl-Klick,
Ketten-Neustarts, Regler, Rekordbox-Import der Cues).

Nutzer-Modus seit 2026-08-22 (`/goal`): 100 % autonom, keine Rueckfragen,
Hoerproben ueberspringen und auf einer finalen Checkliste dokumentieren,
Erfolgsmeldung erst, wenn alles komplett gebaut, getestet, gegengeprueft ist.

**Why:** Der Nutzer wechselt Sessions; ohne diesen Einstieg wuerde ein neuer
Agent Teile neu planen oder Entscheidungen (Entscheidung 1: Plan traegt Rang 1,
Track-Felder bleiben Analyse; Entscheidung 7: Wahl in Datei, nicht im
`scoring_context`; Kettenwahl) uebersehen.

**How to apply:** Zuerst `docs/HANDOFF-2026-08-22-stand-fuer-neuen-agenten.md`
lesen, dann Handoff Teil 4. Nichts aus der Spec ist mehr offen ausser Hoerproben;
neue Arbeit nur mit Waechter an beiden Toren, nach Merge `.agents/` → `.claude/`
spiegeln. Siehe [[hpg-kandidaten-design-vollstaendig-bauen]],
[[hpg-praezision-vor-einfachheit]].
