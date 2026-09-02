# SCQA — Situation, Complication, Question, Answer

Minto Pyramid Principle (McKinsey). Strukturiert das Problem-Statement und das Argument.

## Definition

- **Situation:** Was ist der Status quo? (was alle akzeptieren)
- **Complication:** Was hat sich geändert / was läuft schief?
- **Question:** Welche Entscheidung steht an? (die Frage, die der Plan beantworten will)
- **Answer:** Die Empfehlung (kommt aus dem Synthesizer)

## Anwendung im Skill

**Engagement Manager** nutzt SCQA in Phase 0 für die Auftragsklärung:

```
Auftrag (SCQA):
  S: [Status quo]
  C: [Was hat sich geändert / Problem]
  Q: [Entscheidung, die ansteht]
  → Team antwortet mit A
```

## Beispiel

**S:** PB Studio Pacing-Modul nutzt aktuell QThread-Worker für Audio-Analyse-Pipeline
**C:** UI freezet bei langen Mixes (>30min), User-Beschwerden, Roadmap-Risiko
**Q:** Soll der Worker auf asyncio umgestellt werden, oder gibt es einen besseren Fix?
**A:** *(kommt vom Team via Synthesizer)*

## Warum SCQA

Zwingt den Engagement Manager, das Problem präzise zu formulieren bevor das Team analysiert. Wenn S/C/Q unklar sind → Team analysiert die falsche Frage.

## Anti-Pattern

❌ Q ohne C: "Sollen wir asyncio nutzen?" — ohne Problem-Kontext nichts zu entscheiden
❌ C ohne konkrete Beobachtung: "Es gibt Probleme" — nicht falsifizierbar
❌ S = aktueller-Plan: nein, S ist *Status quo*, nicht der Vorschlag

## Wenn S/C/Q unklar

Engagement Manager fragt **einmal** beim User nach. Wenn der nicht antwortet: Best-Guess mit explizit dokumentierter Annahme.
