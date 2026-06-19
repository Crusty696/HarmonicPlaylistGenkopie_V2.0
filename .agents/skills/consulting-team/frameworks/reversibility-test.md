# Reversibility Test — One-Way vs Two-Way Doors

Bezos' Heuristik: nicht jede Entscheidung hat gleichen Beweisbedarf.

## Definition

- **Two-Way Door:** Reversibel. Wenn falsch, billig zu korrigieren. Beispiel: ein Feature-Flag, ein A/B-Test, eine Library-Wahl mit gutem Abstraktions-Layer.
- **One-Way Door:** Nicht reversibel (oder sehr teuer). Beispiel: Stack-Wechsel auf Codebase-Ebene, öffentliches Commitment, Daten-Migration, Vendor-Lock-In.

## Konsequenz für die Beweislast

| Door | Beweislast für GO |
|------|---|
| Two-Way | Niedrig — schnell entscheiden, im Zweifel ausprobieren |
| One-Way | Hoch — viel Evidenz, mehrere unabhängige Pro-Argumente |

Bei One-Way Door + nur 1-2 Pro-Argumente → Recommendation = **MEHR-INFO**, nicht GO.

## Checkliste: Welche Door ist das?

Eine Entscheidung ist **One-Way Door** wenn mindestens eines davon zutrifft:

- [ ] Daten-Migration: alte Format → neues Format, alte Daten weg
- [ ] Stack-Wechsel der Codebase: viele Module betroffen
- [ ] Öffentliches Commitment: User/Partner/Investoren erwarten X
- [ ] Vendor-Lock-In: Abhängigkeit von einem Anbieter, schwer abzustreifen
- [ ] Org-Struktur: Team-Umbau, Hire/Fire
- [ ] Sicherheits-/Compliance-relevante Architektur-Entscheidungen
- [ ] Irreversibler Ressourcen-Einsatz (>1 Monat Engineering-Zeit ohne Reuse-Wert)

Sonst: **Two-Way Door** (Default-Annahme).

## Anwendung im Skill

**Engagement Manager** klassifiziert in Phase 0:
- "Reversibilität: [one-way / two-way]"

**Risk Officer** validiert in Phase 2 und sagt explizit:
- "Reversibilität-Check: Plan ist [one-way / two-way], weil [Grund]"

**Synthesizer** dokumentiert im Header des Reports.

## Beispiel

**Plan A:** PB Studio Pacing-Worker auf QRunnable umstellen
- Betrifft 1 Modul
- Code-Diff < 200 Zeilen
- Rollback via Git in 5 Minuten
→ **Two-Way Door.** Beweislast niedrig.

**Plan B:** PB Studio gesamten Stack von PyQt6 auf Tauri+Rust migrieren
- Betrifft gesamte Codebase
- Mehrere Monate Migration
- Skill-Wechsel für ganzes Team
- Rollback sehr teuer
→ **One-Way Door.** Beweislast hoch. Ohne mehrere unabhängige Pro-Argumente: **MEHR-INFO**, nicht GO.

## Anti-Pattern

❌ Alle Entscheidungen als gleich behandeln
❌ One-Way mit Daumen-hoch-Mentalität entscheiden ("klingt cool, machen wir")
❌ Two-Way mit Analyse-Paralyse ("ich brauche noch 5 Studien")

## Heuristik

> Two-Way Doors gehen schnell, One-Way Doors gehen langsam.

Wenn das Team in Two-Way-Door-Debatten festhängt: zu viel Analyse für die Entscheidungs-Größe.
Wenn das Team One-Way-Door-Decisions schnell durchwinkt: zu wenig Sorgfalt für die Tragweite.
