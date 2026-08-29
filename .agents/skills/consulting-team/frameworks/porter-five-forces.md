# Porter's Five Forces

Klassisches Strategie-Framework für Markt-/Business-Themen. Nur laden wenn relevant.

## Definition

Michael Porter (HBS). Bewertet die strategische Attraktivität einer Branche/eines Marktes durch 5 Kräfte:

1. **Rivalität unter bestehenden Wettbewerbern** — wie hart konkurrieren die Player?
2. **Bedrohung durch neue Marktteilnehmer** — wie hoch sind die Eintrittsbarrieren?
3. **Verhandlungsmacht der Lieferanten** — können Lieferanten Preise diktieren?
4. **Verhandlungsmacht der Kunden** — können Kunden Preise drücken?
5. **Bedrohung durch Ersatzprodukte** — gibt es Substitute, die das Problem anders lösen?

## Wann laden

- Build vs Buy Entscheidung (besonders bei SaaS-Tools)
- Markt-/Industrie-Themen
- Konkurrenz-Analyse
- Geschäftsmodell-Reviews

**Nicht** für rein technische/interne Themen — da ist Porter Overkill.

## Anwendung — Beispiel

**Plan:** Eigenes Prompt-Management-Tool für PB Studio bauen statt Langfuse/Promptfoo nutzen

**Porter-Analyse:**

1. **Rivalität:** Hoch — Langfuse, LiteLLM, Promptfoo, Helicone, mehrere etablierte Player
2. **Neue Marktteilnehmer:** Sehr hoch — fast jede AI-Infra-Firma launcht so etwas, Eintrittsbarrieren niedrig
3. **Lieferanten-Macht:** Mittel — abhängig von LLM-Providern (Anthropic, OpenAI), die ihre Preise/APIs diktieren
4. **Kunden-Macht:** N/A für PB Studio (nur David als Kunde)
5. **Substitute:** Hoch — selbst-gebaute Lösung mit JSON-Files + Git ist legitimer Substitute

**Conclusion:** Markt-Dynamik spricht *gegen* Eigenbau. Externe Player investieren mehr R&D als ein Solo-Entwickler. **Strategic recommendation:** existierendes Tool nutzen, nicht selbst bauen — *außer* es gibt einen PB-Studio-spezifischen Use-Case, den keiner abdeckt.

## Output (durch Senior Partner oder Analyst)

```
PORTER FIVE FORCES:
- Rivalität: [niedrig/mittel/hoch]. Grund: [...]
- Eintrittsbarrieren: [niedrig/mittel/hoch]
- Lieferanten: [niedrig/mittel/hoch]
- Kunden: [N/A oder Bewertung]
- Substitute: [niedrig/mittel/hoch]
Strategische Implikation: [...]
```

## Anti-Pattern

❌ Porter bei rein technischen Themen anwenden (z.B. "soll ich asyncio oder QRunnable nutzen?")
❌ Alle 5 Kräfte gleich gewichten — in der Praxis dominieren oft 1-2
❌ Generische Aussagen ("Markt ist kompetitiv") ohne konkrete Player

## Light-Version: Build vs Buy

Bei Solo-Entwickler-Setups (wie David's) ist die volle Porter-Analyse oft Overkill. Light-Version:

1. **Substitute:** Existiert ein etabliertes Tool, das 80% deines Use-Cases abdeckt?
2. **Eintrittsbarrieren:** Wie viel R&D müsstest du selbst leisten?
3. **Strategischer Vorteil:** Was bringt dir der Eigenbau, was Substitute nicht bringen?

Wenn 1 = ja, 2 = mittel/hoch, 3 = nichts spezifisches: **buy/use**, nicht **build**.
