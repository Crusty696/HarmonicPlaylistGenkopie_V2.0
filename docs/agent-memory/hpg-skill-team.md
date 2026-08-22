---
name: hpg-skill-team
description: HPG hat 14 projekt-lokale Skills in .claude/skills/, gespiegelt nach .agents/skills/ fuer Codex — beide Seiten synchron halten
metadata:
  type: project
---

Das HPG-Projekt haelt sein Experten-Skill-Team **projekt-lokal** in
`.claude/skills/hpg-*` (14 Skills, Stand 2026-08-14). Dieselben Dateien liegen
gespiegelt unter `.agents/skills/hpg-*`, weil das Repo eine `AGENTS.md` fuer
Codex hat und beide Agenten denselben Wissensstand brauchen.

Wichtig: `.gitignore:69` ignoriert `.claude/` komplett — die Skills sind dort
NUR lokal. `.agents/` ist getrackt, der Spiegel ist also gleichzeitig die
einzige versionierte Kopie. Wer nur `.claude/skills` pflegt, verliert die
Arbeit beim naechsten frischen Klon.

**Why:** Vor dem Umbau existierten drei Skills doppelt in beiden Ordnern und
waren beide veraltet (Cache v11 statt v24, main.py "3500 Zeilen" statt 4868).
Ein Agent, der der stale Kopie folgt, debuggt gegen eine Realitaet, die es
nicht mehr gibt.

**How to apply:** Wird ein `hpg-*`-Skill geaendert, die Datei danach nach
`.agents/skills/<name>/SKILL.md` kopieren. Kein Skill dieses Projekts gehoert
nach `~/.claude/skills` — David will sie ausdruecklich nur fuer dieses Projekt
verfuegbar. Faktenpflege: jede Zahl im Skill gegen den Code pruefen, nie aus
den Markdown-Statusdateien uebernehmen ([[hpg-audit-2026-07-17]]).
