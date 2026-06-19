# Second-Order Effects

Frage: Was passiert *durch* den Plan — indirekt, eine Iteration später?

## Definition

- **First-Order:** Direkte Konsequenz des Plans
- **Second-Order:** Konsequenz *der Konsequenz*

Beispiel:
- First-Order: "Pacing wird auf asyncio umgestellt → UI freezet nicht mehr"
- Second-Order: "Codebase hat jetzt zwei Threading-Patterns → nächste Dev-Hire muss beide lernen → Onboarding-Zeit steigt"

## Workflow

Für jeden Haupt-Vorteil des Plans: "Und dann?"

1. Was passiert direkt? (First-Order)
2. Was passiert dadurch in 1 Monat? (Second-Order)
3. Was passiert dadurch in 6 Monaten? (Third-Order)

Stoppe bei dem Punkt, wo die Effekte spekulativ werden (typisch: Second oder Third).

## Anwendung im Skill

**Senior Partner** und **Risk Officer** nutzen das bei systemischen/organisatorischen Themen.

Nicht jedes Finding braucht Second-Order. Aber bei strategischen Plänen: Pflicht.

## Beispiel

**Plan:** Multi-Persona Consulting-Skill einführen (dieser Skill hier 😉)

**First-Order:**
- Antworten werden kritischer
- Mehr Token-Verbrauch pro Frage

**Second-Order:**
- User trifft bessere Entscheidungen (Vorteil)
- User wird auch bei trivialen Fragen kritisch durchleuchtet (Nachteil → Trigger-Disziplin nötig)
- User fängt an, sich auf den Skill zu verlassen statt selbst zu denken (Risiko → Skill darf User nicht passivieren)

**Third-Order:**
- Über Wochen: User wird besser im Pre-Mortem-Denken auch ohne Skill (positiv)
- Oder: User wird abhängig (negativ — Mitigation: Skill ermutigt eigenständiges Denken in Open Questions)

## Häufige Second-Order-Effekte (Checkliste)

- **Org/Team:** Wer muss das warten? Welches Skill-Set wird neu nötig?
- **User-Behavior:** Wie verändert sich Nutzungsverhalten?
- **Tech-Debt:** Was zahlt man später für die jetzige Entscheidung?
- **Optionalität:** Werden zukünftige Wege offen gehalten oder geschlossen?
- **Cultural:** Welche Norm wird etabliert ("wir machen jetzt immer so")?

## Anti-Pattern

❌ Pure First-Order-Analyse: "Plan hat Pros A, B, C und Cons X, Y, Z." — fehlende Second-Order
❌ Spekulation 4+ Iterationen tief: Confidence wird LOW, Wert sinkt
❌ Second-Order ohne P×Impact: alle indirekten Effekte werden gleich gewichtet

## Spezial-Frage: Was wird *gewöhnt*?

Eine besondere Form von Second-Order: was wird durch den Plan zur *Norm*?

Wenn jeder Pacing-Bug mit "neuer Stack-Wahl" gelöst wird → Norm: "bei Bugs, Stack wechseln" → schlechte Codebase-Stabilität.

Wenn jede Feature-Idee durch den Consulting-Skill geht → Norm: "kein eigenes Denken" → Skill passiviert User.

Norm-Etablierung ist ein wichtiger Second-Order-Effekt, der oft übersehen wird.
