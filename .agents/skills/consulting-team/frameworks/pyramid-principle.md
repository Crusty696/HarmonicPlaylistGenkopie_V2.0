# Pyramid Principle (Barbara Minto)

Synthesizer-Pflicht. Strukturiert den finalen Report: Hauptaussage zuerst, dann Stützpfeiler.

## Definition

**Top-Down statt Bottom-Up.** Erst die Antwort, dann die Begründung, dann die Details.

## Struktur

```
           [Hauptaussage / Recommendation]
                       |
       ┌───────────────┼───────────────┐
       |               |               |
   [Pfeiler 1]    [Pfeiler 2]    [Pfeiler 3]
       |               |               |
   [Details]      [Details]       [Details]
```

## Anwendung im Skill

**Synthesizer** strukturiert den Report nach Pyramid Principle:

1. **Executive Summary (Spitze)** — Hauptaussage in 3-5 Sätzen, Recommendation drin
2. **Findings (Pfeiler)** — die 2-3 wichtigsten Findings, die die Recommendation stützen
3. **Details (Basis)** — Open Questions, Frameworks, Confidence

## Beispiel — Schlechte (Bottom-Up) vs Gute (Top-Down) Executive Summary

**Schlecht (Bottom-Up, narrativ):**
> "Wir haben uns das Pacing-Modul angeschaut. Domain Expert hat festgestellt, dass die Codebase QThread-Worker durchgängig nutzt. Der Analyst hat asyncio+Qt-Pitfalls in Qt-Docs gefunden. Risk Officer sieht Race-Conditions. Daher empfehlen wir GO-mit-Modifikation: QRunnable statt asyncio."

→ Konklusion am Ende. User muss durch alles scrollen.

**Gut (Top-Down, Pyramid):**
> "GO-mit-Modifikation: QRunnable + QThreadPool statt asyncio. Begründung in einem Satz: asyncio bricht Codebase-Konsistenz (3 Worker bereits in QThread) und schafft Race-Risiken mit Qt-Event-Loop, während QRunnable dasselbe UI-Freezing löst ohne Pattern-Bruch. Confidence: HIGH. Reversibilität: two-way door."

→ User weiß sofort: was, warum, mit welchem Vertrauen.

## Regeln

1. **Antwort zuerst** — nicht "wir kommen zu dem Schluss, dass..."
2. **3 Pfeiler max.** — wenn mehr als 3 Stützen → priorisieren
3. **Jeder Pfeiler ist eigenständig wahr** — wenn einer wegfällt, fällt nicht alles
4. **Parallel-Struktur** — alle Pfeiler auf derselben Abstraktions-Ebene

## Anti-Pattern

❌ "Insgesamt scheint der Plan einige interessante Aspekte zu haben, aber auch ein paar Risiken, die wir noch erläutern werden."

→ Keine Recommendation, keine Stützpfeiler, alles vage. **Skill-Failure.**

✓ "NO-GO. Drei Gründe: [1], [2], [3]."

## Check vor Abgabe

- Steht die Recommendation im ersten Satz der Executive Summary?
- Sind die Stützpfeiler explizit benannt?
- Sind sie unabhängig wahr?
- Ist Confidence + Reversibilität gesetzt?
