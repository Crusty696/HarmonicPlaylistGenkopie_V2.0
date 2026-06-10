# Output-Format — Synthesizer Report Template

Der finale, dem User sichtbare Output. Strikt diese Struktur — keine Abweichung.

## Template

```markdown
# Consulting Team Review

> **Auftrag:** [1 Satz, was beurteilt wurde]
> **Reversibilität:** [one-way door / two-way door]

## Executive Summary

[3-5 Sätze, Pyramid Principle: Hauptaussage zuerst, dann 2-3 Stützpfeiler.
Muss klar sein, ob GO / NO-GO / GO-mit-Mod / MEHR-INFO.
Confidence-Level explizit nennen.]

## Findings

### 🔴 Critical
[null bis n Findings. Jedes:]
- **[Finding-Name]** (Rolle: X)
  - **Was:** [1-2 Sätze, was das Problem ist]
  - **Warum kritisch:** [Evidenz: Zahl, Logik, Beobachtung am Artefakt, externe Quelle]
  - **Counter-Proposal:** [konkrete Alternative, nicht "denk drüber nach"]

### 🟠 High
[gleiche Struktur]

### 🟡 Medium
[gleiche Struktur]

### 🟢 Low
[gleiche Struktur, sparsam einsetzen]

## Steel-Man Gegenposition

[Devil's Advocate liefert die *stärkste* Form der Gegenposition in 3-5 Sätzen.
Nicht Stroh-Mann. Wenn die Gegenposition stärker wirkt als die Original-Idee:
das muss in die Recommendation einfließen.]

## Open Questions

[3-5 konkrete Fragen, die der User klären muss bevor die Entscheidung fällt.
Format: "Frage? — Warum wichtig."]

1. [Frage]? — [Warum wichtig]
2. ...

## Recommendation

**[GO / NO-GO / GO-mit-Modifikation / MEHR-INFO]**

- **Confidence:** [LOW / MEDIUM / HIGH]
- **Reversibilität:** [one-way door / two-way door]
- **Begründung:** [1-2 Sätze, max.]

[Bei GO-mit-Modifikation: explizit listen welche Modifikation(en)]
```

## Severity-Definitionen

| Stufe | Bedeutung |
|-------|-----------|
| 🔴 Critical | Plan scheitert mit hoher Wahrscheinlichkeit, oder irreversibler Schaden |
| 🟠 High | Significant risk, blockiert Erfolg ohne Fix |
| 🟡 Medium | Verschlechtert Outcome, fixable post-launch |
| 🟢 Low | Nice-to-fix, keine Erfolgsblockade |

**Mindestens 1 🟠 High oder 🔴 Critical pro Review** — sonst war die Analyse zu oberflächlich.

## Confidence-Definitionen

- **HIGH:** Mehrere unabhängige Belege, Domain-Expert ist sicher, Analyst hat Daten
- **MEDIUM:** Reasoning ist solide, aber Belege haben Lücken
- **LOW:** Vermutung-basiert, viele Open Questions offen

## Recommendation-Definitionen

- **GO** — Plan ist tragfähig, Modifikationen optional
- **GO-mit-Modifikation** — Plan ist tragfähig *nach* expliziten Fixes
- **NO-GO** — Plan sollte verworfen werden
- **MEHR-INFO** — Analyse kann nicht abgeschlossen werden ohne weitere Daten/Klärung

## Reversibilität

- **two-way door** — Entscheidung kann später ohne große Kosten revidiert werden
- **one-way door** — Schwer/teuer zu revidieren (Stack-Wechsel, öffentliches Commitment, Architektur)

Bei one-way door: höhere Beweislast für GO. Lieber MEHR-INFO als unsicheres GO.

## Anti-Pattern (NICHT so)

❌ "Insgesamt ein sehr durchdachter Plan mit einigen interessanten Aspekten und ein paar Punkten zum Überlegen."

→ Floskeln, keine Severity, keine Counter-Proposals. **Skill-Failure.**

❌ "Es gibt einige Risiken, die man bedenken könnte."

→ Vage, keine Confidence, keine Belege. **Skill-Failure.**

## Beispiel-Output (Mini)

```markdown
# Consulting Team Review

> **Auftrag:** Bewertung des Plans, PB Studio Pacing-Modul auf Async-Worker umzustellen
> **Reversibilität:** two-way door

## Executive Summary

GO-mit-Modifikation. Async-Refactor löst das Freezing-Problem (Critical), aber der vorgeschlagene Ansatz ignoriert die existierende QThread-Worker-Pattern und führt zu Doppel-Implementierung. Empfehlung: Async-Pattern in den bestehenden Worker integrieren, nicht ersetzen. Confidence: MEDIUM.

## Findings

### 🔴 Critical
- **Doppel-Implementierung von Threading-Patterns** (Rolle: Domain Expert)
  - **Was:** Plan führt asyncio ein, obwohl QThread-Worker bereits etabliert ist
  - **Warum kritisch:** Cross-Thread-Signal/Slot-Routing wird komplex, Race-Conditions wahrscheinlich
  - **Counter-Proposal:** QRunnable + QThreadPool nutzen, asyncio nur im FastAPI-Backend

### 🟠 High
- **Kein Backpressure-Mechanismus** (Rolle: Risk Officer)
  - **Was:** Bei langen Mixes (>60min) füllt sich die Queue ohne Drosselung
  - **Warum kritisch:** RAM-Overflow auf 32GB-Systemen wahrscheinlich
  - **Counter-Proposal:** Semaphor + max-queue-size = 4

## Steel-Man Gegenposition

Ein klarer Schnitt auf asyncio würde die Codebase vereinheitlichen und langfristig Wartung vereinfachen. QThread ist Qt5-Era, asyncio ist Python-nativ und besser dokumentiert. Wenn ohnehin größerer Refactor ansteht, jetzt der richtige Moment. Aber: nur valide wenn das Vereinheitlichungs-Ziel explizit ist — sonst Doppelmigration.

## Open Questions

1. Ist Vereinheitlichung auf asyncio strategisches Ziel? — Entscheidet ob Counter-Proposal oder Steel-Man richtig ist
2. Wie groß ist der Anteil langer Mixes (>60min)? — Bestimmt Backpressure-Priorität
3. Existieren Benchmarks zur aktuellen Worker-Performance? — Ohne Baseline schwer zu validieren

## Recommendation

**GO-mit-Modifikation**

- **Confidence:** MEDIUM
- **Reversibilität:** two-way door
- **Begründung:** Pacing-Refactor ist nötig, aber Threading-Doppelung muss raus. Backpressure-Mechanik einbauen.

Modifikationen:
1. QRunnable + QThreadPool statt asyncio im Pacing-Modul
2. Semaphor mit max-queue-size = 4
3. Benchmark vor + nach Refactor zur Validierung
```

So sieht ein guter Output aus. Spezifisch, mit Belegen, mit konkreten Counter-Proposals, mit klarer Recommendation.
