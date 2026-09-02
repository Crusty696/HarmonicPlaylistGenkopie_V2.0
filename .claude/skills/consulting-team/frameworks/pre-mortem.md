# Pre-Mortem (Gary Klein)

Risk Officer's Pflicht-Tool. "Stell dir vor, der Plan ist gescheitert — was ist passiert?"

## Definition

Klassisches Post-Mortem fragt **nach** dem Failure. Pre-Mortem fragt **vor** dem Failure — durch mentales Reisen in die Zukunft.

Studien (Klein 2007, Kahneman) zeigen: Pre-Mortem identifiziert 30-50% mehr Failure-Modes als normale Risiko-Analyse, weil die Frame-Bedingung ("es ist *bereits* gescheitert") die kognitiven Bias überwindet, die Optimismus auf Pläne legt.

## Workflow

### Schritt 1: Zeit-Frame setzen
"Es ist 3 Monate später. Der Plan ist katastrophal gescheitert. Headline: '[Project] failed.'"

### Schritt 2: Brainstorm
Generiere 5-7 plausible Geschichten, wie es zum Scheitern kam. **Wichtig:** Annehmen, dass es *bereits* gescheitert ist — nicht "könnte" scheitern.

### Schritt 3: Priorisieren
Pro Failure-Mode bewerten:
- **P (Wahrscheinlichkeit):** niedrig / mittel / hoch
- **Impact:** niedrig / mittel / hoch (Reversibilität, Umfang, User-Schaden)
- **Severity = P × Impact**

Top 2-3 in den Report.

### Schritt 4: Mitigation
Pro Top-Failure-Mode: konkrete Counter-Proposal.

## Anwendung — Beispiel

**Plan:** PB Studio Pacing auf asyncio umstellen

**Pre-Mortem:**
"Es ist 6 Wochen später. Pacing-Refactor ist gescheitert. Headline: 'asyncio-Migration crashed App'."

**Failure-Modes generiert:**
1. Race-Condition zwischen asyncio-Loop und Qt-Event-Loop → UI freeze trotz Refactor (P: hoch, Impact: hoch)
2. RAM-Overflow bei langen Mixes ohne Backpressure (P: mittel, Impact: hoch)
3. Doppel-Wartung weil nur Pacing migriert, andere Worker bleiben QThread (P: hoch, Impact: mittel)
4. Wechsel kostete 2 Wochen, Stem-Separation-UI-Release verzögert sich (P: hoch, Impact: hoch)
5. Junior-Dev kann Codebase nicht mehr warten (P: niedrig, Impact: mittel)
6. asyncio + AMD-ROCm-Calls haben undokumentierte Konflikte (P: niedrig, Impact: hoch)

**Top 3 priorisiert:**
- #1 (P:hoch × I:hoch = 🔴)
- #4 (P:hoch × I:hoch = 🔴)
- #2 (P:mittel × I:hoch = 🟠)

## Anti-Pattern

❌ Generischer Pessimismus: "irgendwas kann schiefgehen"
❌ Nur Tech-Failures: vergisst Org/Priorität/User-Impact
❌ Keine P×I-Gewichtung: alles ist gleich kritisch → nichts ist kritisch

## Spezial-Frage: Was würde der Plan-Autor *nicht* sehen?

Bias-Awareness: Wer den Plan geschrieben hat, hat blinde Flecken. Pre-Mortem sucht gezielt nach Failure-Modes *außerhalb* der Komfortzone des Plans:

- Technisch-Plan → Pre-Mortem fragt: was an *Org/Priorität* geht schief?
- Strategisch-Plan → Pre-Mortem fragt: was an *Implementierung/Stack* geht schief?
- Bottom-Up-Plan → Pre-Mortem fragt: was an *strategischer Konsistenz* geht schief?
