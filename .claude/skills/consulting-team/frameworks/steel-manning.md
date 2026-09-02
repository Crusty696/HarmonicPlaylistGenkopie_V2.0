# Steel-Manning

Devil's Advocate's Pflicht-Tool. Die *stärkste* Form der Gegenposition formulieren.

## Definition

**Straw-Man:** Schwache Version der Gegenposition. Leicht zu schlagen. Wertlos.

**Steel-Man:** Stärkste Version der Gegenposition. Schwer zu schlagen. Diagnostisch wertvoll.

Wenn der Steel-Man die Original-Position schlägt → die Original-Position ist schwach.

## Workflow

### Schritt 1: Position identifizieren
Was ist die These des Plans? (eine Aussage, falsifizierbar)

Beispiel: "PB Studio Pacing soll auf asyncio umgestellt werden."

### Schritt 2: Naive Gegenposition (Straw-Man)
Was ist die *schwächste* Gegenposition? (zur Kalibrierung, nicht im Output)

Beispiel: "asyncio ist neu und unbekannt." → schwach, leicht zu schlagen.

### Schritt 3: Steel-Man konstruieren
Was wäre das *stärkste* Argument einer Person, die das Gegenteil vertritt?

Steel-Man-Konstruktion folgt 4 Heuristiken:
1. **Annahmen prüfen:** Welche Annahme des Original-Plans ist die wackligste?
2. **Priorisierung:** Ist der Plan überhaupt die richtige Sache *jetzt*?
3. **Reframing:** Adressiert der Plan das richtige Problem?
4. **Alternative Pfade:** Gibt es einen 10×-Impact-Pfad bei 0.3×-Aufwand?

### Schritt 4: Steel-Man bewerten
Wenn die Steel-Man-Position überzeugender wirkt als die Original-Position → 🔴 Critical Finding für den Plan.

Wenn nicht → genau erklären, *warum* das Original trotzdem stärker ist.

## Beispiel

**Original-Position:** PB Studio Pacing soll auf asyncio umgestellt werden.

**Straw-Man (NICHT nutzen):**
> "asyncio ist neu und das Team kennt es nicht."

→ Schwach. Lerne-eben.

**Steel-Man:**
> "Pacing-Refactor adressiert ein Symptom (UI-Freeze), nicht die Ursache (fehlende Backpressure + Worker-Architektur). Mit minimalem Hotfix (Semaphor + max-queue-size) ist das Freezing-Symptom in 1 Tag weg — bei 0 Pattern-Bruch und 0 Migrations-Risiko. Refactor jetzt = falsche Priorität, weil Stem-Separation-UI seit 3 Monaten Roadmap-blockierend ist."

→ Stark. Greift Priorisierung *und* technische Notwendigkeit an. Schwer zu schlagen.

## Heuristik: Wer könnte das tatsächlich sagen?

Stell dir vor: ein erfahrener Engineer, der den Plan-Autor respektiert, aber nicht zustimmt. Was würde *die Person* sagen?

Wenn die Antwort generisch ist ("Aufwand", "Risiko", "neu") → noch nicht Steel-Man.
Wenn die Antwort *konkret* und *unausweichlich* ist → Steel-Man erreicht.

## Anti-Pattern

❌ Generische Gegenargumente ("könnte teuer sein", "ist riskant")
❌ Position, die nur ein Anfänger vertreten würde
❌ Strohmann-Versuche im "Steel-Man"-Gewand

## Sonderfall: Plan ist tatsächlich robust

Wenn nach ernsthaftem Steel-Man-Versuch keine starke Gegenposition möglich ist:

**Das ist ein legitimer Output.** Explizit sagen:

> "Steel-Man versucht auf 4 Achsen (Annahmen, Priorisierung, Reframing, Alternative). Keine starke Gegenposition gefunden. Plan ist robust. Severity: 🟢. Confidence: HIGH."

Kein erzwungenes Meckern. Aber dieser Output ist selten — wenn er *häufig* vorkommt, ist der Devil's Advocate zu nachsichtig.

## Calibration

Über 10 Reviews verteilt sollte der Devil's Advocate:
- ~70% einen substantiellen Steel-Man finden (🟠/🔴 Severity)
- ~20% einen moderaten finden (🟡 Severity)
- ~10% bestätigen, dass der Plan robust ist (🟢)

Wenn die Verteilung anders aussieht: Re-Calibration nötig.
