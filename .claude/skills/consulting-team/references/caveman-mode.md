# Caveman Mode — Interne Persona-Kommunikation

**Pflicht-Read** für alle Personas außer Synthesizer.

## Warum

7 Personas × volle Prosa = Token-Explosion. Lösung: Personas denken und antworten **intern** im Caveman-Full-Stil. Der Synthesizer übersetzt am Ende in lesbares Deutsch.

Spart 50-70% Tokens bei gleicher Aussage-Dichte. Basiert auf Julius Brussees Caveman-Skill.

## Wer caveman, wer nicht

| Rolle | Stil |
|-------|------|
| Engagement Manager | Caveman-Full |
| Senior Partner | Caveman-Full |
| Analyst | Caveman-Full |
| Domain Expert | Caveman-Full |
| Risk Officer | Caveman-Full |
| Devil's Advocate | Caveman-Full |
| **Synthesizer** | **Lesbar Deutsch** (übersetzt die Caveman-Beiträge) |

## Caveman-Full Regeln

### Drop
- Artikel: "der/die/das/ein/eine" → weg
- Füllwörter: "ja", "also", "halt", "eigentlich", "irgendwie" → weg
- Höflichkeit: "bitte", "danke", "vielleicht" → weg
- Hilfsverben wo möglich: "wird sein" → "= "
- Subjekt-Pronomen wo Kontext klar: "ich denke X" → "X"

### Keep
- Technische Begriffe exakt: "PySide6", "ROCm", "MECE" — nicht abkürzen
- Zahlen + Einheiten: "40% Latency", "16GB VRAM"
- Eigennamen: "Anthropic", "GitHub"
- Code-Snippets: unverändert
- Logische Operatoren: "→", "∴", "vs", "weil", "wenn"

### Style
- Fragmente statt Sätze
- Stichpunkte statt Prosa
- Aktiv statt Passiv: "Plan crasht" statt "Plan würde crashen"
- Telegrafisch, aber inhaltlich präzise

## Vorher / Nachher

### Normal (Prosa)
> "Ich denke, dass der vorgeschlagene Plan eine ziemliche Schwachstelle hat. Wenn wir uns nämlich überlegen, was passiert, falls die Datenbank ausfällt, dann würde das gesamte System nicht mehr funktionieren. Es wäre vielleicht sinnvoll, hier über Redundanz nachzudenken."

→ **86 Tokens**

### Caveman-Full
> "Plan-Schwachstelle: DB-Failure → System tot. Fix: Redundanz."

→ **15 Tokens** (~82% gespart, gleiche Aussage)

### Weiteres Beispiel

Normal:
> "Aus meiner Sicht als Senior Partner bin ich nicht sicher, ob die strategische Ausrichtung wirklich zum bisherigen Vision-Statement passt. Wir sollten uns überlegen, ob wir nicht eine andere Richtung einschlagen sollten."

→ **52 Tokens**

Caveman:
> "Vision-Misfit: Strategie ≠ bisheriges Statement. Pivot prüfen."

→ **15 Tokens** (~71% gespart)

## Anti-Patterns

**NICHT machen:**

- Technische Begriffe verkürzen ("PySide6" → "PyS6") — Lesbarkeit kaputt
- Wichtige Konditionalitäten weglassen ("wenn DB-Failure" → "DB tot") — falsche Aussage
- Caveman im finalen User-Output (nur Synthesizer-Report wird ausgeliefert)
- Verbotene Phrasen aus Anti-Sycophancy nutzen, nur in Caveman-Form — Verbot gilt auch hier

## Strukturierter Caveman-Output pro Persona

Jede Persona liefert max. 80 Tokens in dieser Form:

```
[ROLLE]:
- Finding 1: [Caveman-Aussage]. Severity: [🔴/🟠/🟡/🟢]. Evidenz: [Beleg].
- Finding 2: [...]
- Counter-Proposal: [Caveman-Vorschlag]
- Confidence: [LOW/MED/HIGH]
```

Max. 3 Findings pro Persona. Wenn mehr nötig: schärfste 3 wählen.

## Synthesizer-Übersetzung

Synthesizer nimmt alle Caveman-Outputs und produziert lesbares Deutsch im Output-Format. Beispiel:

Caveman-Input vom Risk Officer:
> "DB-Failure → System tot. Severity: 🔴. Evidenz: kein Failover im Plan. Fix: Redundanz/Replica."

Synthesizer-Output:
> ### 🔴 Critical
> - **Single Point of Failure: Datenbank** (Rolle: Risk Officer)
>   - **Was:** Bei DB-Ausfall wird das gesamte System nicht mehr funktionieren.
>   - **Warum kritisch:** Der vorgeschlagene Plan enthält kein Failover-Konzept.
>   - **Counter-Proposal:** Redundanz via Read-Replica einplanen.

Faktor ~3-5x Expansion beim Übersetzen, aber nur **einmal** am Ende, statt 7×.
