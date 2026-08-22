---
name: hpg-stand-2026-08-22-teil1-gemerged
description: "Stand 2026-08-22: Kandidaten Teil 1 auf main gemerged (f18815b), Teil 2 noch nicht geplant — Faktenblatt + Entwurfsnotizen liegen in docs/superpowers/plans/2026-08-22-*; Uebergabe an neuen Agenten ueber docs/HANDOFF-2026-08-22-stand-fuer-neuen-agenten.md"
metadata: 
  node_type: memory
  type: project
  originSessionId: 261b9a6b-87fd-4d13-aa8d-3e85b22fb493
  modified: 2026-08-22T15:57:45.890Z
---

Am 2026-08-22 wurde `kandidaten-teil1` (Datenmodell, CACHE_VERSION 34,
`mix_candidates.py`, `rekordbox_phrases.py`) per `--no-ff` auf `main`
gemerged (`f18815b`), Suite 1786 passed, Branch + Worktree entfernt, gepusht.
Nutzer-Anweisung danach: "erledige meine Anweisungen" = Plan Teil 1 Task 12
(Realmessung 231 Tracks, Handoff Teil 1), dann Teil 2/3/4 der Spec komplett
bauen; und "Uebergabe an anderen Agenten vorbereiten, gleicher Stand".

**Wo der naechste Agent einsteigt:**
- `docs/HANDOFF-2026-08-22-stand-fuer-neuen-agenten.md` (Pflichtlektuere,
  Lesereihenfolge), Memory-Kopie `docs/agent-memory/`.
- Teil 2 ist NICHT geplant. Vorarbeit: `docs/superpowers/plans/
  2026-08-22-faktenblatt-kandidaten-teil2.md` (Zeilenrefs, verifiziert) und
  `2026-08-22-entwurfsnotizen-kandidaten-teil2.md` (Entwurf, NICHT vom
  Nutzer genehmigt: eigene `kandidaten_*_weight`-Schluessel, Gates, Formeln,
  Startwerte). Naechster Schritt: offene Fragen daraus dem Nutzer stellen
  bzw. Waechter Tor 1, dann Plan nach writing-plans, Worktree, TDD.
- `.claude/` ist gitignored; Spiegel `.agents/` ist versioniert — nach Klon
  kopieren (Anleitung im Handoff Abschnitt 4).

**Why:** Der Nutzer wechselt Agenten/Sessions; ohne diese Ablage gingen
Faktenblatt und Entwurf verloren und der naechste Agent wuerde erneut
messen oder — schlimmer — annehmen.

**How to apply:** Vor Teil 2 die Entwurfsnotizen NICHT als genehmigt
behandeln. Messwerte aus der Kandidaten-Messung (Abschnitt 10 der Notizen)
ablesen, bevor Konstanten festgelegt werden. Siehe
[[hpg-kandidaten-design-vollstaendig-bauen]], [[hpg-praezision-vor-einfachheit]].
