---
name: hpg-waechter-und-agententeam
description: "David will einen pruefenden Waechter VOR jeder Umsetzung, nicht erst danach — plus zehn projekt-spezifische Subagenten"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 602c084c-5127-4b2b-b848-63a0fe84aba7
  modified: 2026-08-20T01:13:39.814Z
---

David hat ausdruecklich einen uebergeordneten Pruefer verlangt, der
verhindert, dass Fehler eingebaut werden, Umbenennungen passieren, die GUI
ohne Auftrag geaendert wird oder ploetzlich ein neuer Weg eingeschlagen wird.

**Sein entscheidender Zusatz:** „er darf aber nicht erst eingreifen wenn es
schon eingebaut wurde oder noch spaeter."

**Warum:** Ein Pruefer am Ende dokumentiert nur. Ist der Diff fertig, ist der
Aufwand versenkt, die Tests sind angepasst, und eine Rueckweisung kostet mehr
als das Durchwinken — sie wird dann in der Praxis nicht ausgesprochen. Genau
das war in der Sitzung vom 2026-08-20 passiert.

**Wie anwenden:** `hpg-waechter` (`.agents/agents/`, gespiegelt nach
`.claude/agents/`) prueft an zwei Toren. Tor 1 **vor** der Umsetzung gegen das
Vorhaben — existieren die genannten Funktionen, gibt es die Faehigkeit schon,
was geht ueber den Auftrag hinaus. Tor 2 vor dem Commit gegen den Diff. Er hat
bewusst **kein** Edit- und Write-Werkzeug. Die Pflicht steht in `CLAUDE.md`.

Dazu neun fachliche Agenten: `hpg-analyse`, `hpg-scoring`, `hpg-mixpoints`,
`hpg-gui`, `hpg-cache`, `hpg-render`, `hpg-rekordbox`, `hpg-statistik`,
`hpg-tests`. Jeder traegt die Fehler seines Gebiets, die real passiert sind —
nicht allgemeine Ratschlaege.

`.claude/` ist gitignored; `.agents/` ist der versionierte Spiegel des Repos.

Siehe auch [[hpg-groove-scoring-2026-08-20]].
