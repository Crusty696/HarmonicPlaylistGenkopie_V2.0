# MECE — Mutually Exclusive, Collectively Exhaustive

McKinsey-Standard für Problem-Zerlegung. Engagement Manager nutzt das **immer**.

## Definition

Ein Issue-Tree ist MECE wenn:
- **ME (Mutually Exclusive):** Die Sub-Punkte überlappen nicht
- **CE (Collectively Exhaustive):** Die Sub-Punkte decken alles ab, nichts fehlt

## Anwendung

Bei einem komplexen Problem in 3-5 Sub-Fragen zerlegen, die zusammen das Problem komplett abdecken — ohne dass zwei Sub-Fragen sich überschneiden.

## Beispiel

**Problem:** "Soll ich PB Studio Pacing auf asyncio umstellen?"

**Schlechte Zerlegung (nicht MECE):**
- Ist asyncio besser? *(zu vage)*
- Sind die Performance-Werte gut? *(überschneidet mit "ist asyncio besser?")*
- Was sagen andere? *(überschneidet beides)*

**MECE-Zerlegung:**
1. **Technische Konsistenz** — passt asyncio zum existierenden Stack? (Domain Expert)
2. **Performance-Realität** — gibt es Benchmarks dafür? (Analyst)
3. **Strategische Priorität** — ist das die richtige Sache jetzt? (Senior Partner)
4. **Failure-Modes** — was geht im schlimmsten Fall schief? (Risk Officer)
5. **Beste Gegenposition** — wäre nichts-tun oder anders-tun besser? (Devil's Advocate)

Jede Sub-Frage hat einen klar abgegrenzten Bereich. Zusammen decken sie das Problem ab. **MECE.**

## Anti-Pattern

❌ Zu wenige Buckets (1-2): zu grob, ME ok aber CE nicht erfüllt
❌ Zu viele Buckets (>7): kognitiver Overload, oft mit Überlappungen
❌ Inkonsistente Abstraktions-Ebene: "Tech-Stack" und "Latency in ms" als Geschwister

## Check vor Abgabe

- Können zwei Buckets sich überlappen? → ME verletzt
- Gibt es einen wichtigen Aspekt, der in keinem Bucket landet? → CE verletzt
- Sind alle Buckets auf derselben Abstraktions-Ebene? → wenn nein, refactor

## Sweet Spot

3-5 Sub-Fragen ist ideal. Genug Granularität, aber noch kognitiv handhabbar.
