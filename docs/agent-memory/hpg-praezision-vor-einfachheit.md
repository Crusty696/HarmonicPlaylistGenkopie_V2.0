---
name: hpg-praezision-vor-einfachheit
description: "Nutzer-Regel 2026-08-21: immer den praeziseren Weg empfehlen, nicht den einfacheren. Mix-Kandidaten: ALLE Parameter gewichtet (Groove, Rhythmus, Harmonie, Lautheit, BPM max 2 Unterschied) — in Bewertung UND Auswahl, ausnahmslos."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1c6bec25-3d10-4d63-8737-1657e093464b
  modified: 2026-08-21T16:41:44.573Z
---

Der Nutzer hat am 2026-08-21 (Design-Runde Mixpunkt-Kandidaten) mit Nachdruck
gesagt: **Ich soll nicht immer den einfacheren, weniger praezisen Weg
empfehlen.** Er waehlte Weg 2 (Kandidaten pro Track vorberechnen, mehr
Praezision, auch wenn Schema-Aenderungen eine Neuanalyse kosten).

Und: Bei der Auswahl und Bewertung von Uebergaengen/Kandidaten muss
**ausnahmslos alles** einfliessen und gewichtet werden — Groove, Rhythmus,
Harmonie (Tonart muss passen), Lautheit/Lautstaerke, und **BPM-Unterschied
maximal 2** zwischen den Tracks — zusammen mit allen anderen Parametern.
Nichts davon darf "spaeter" oder "erst mal weglassen" sein.

**Why:** Ich hatte dreimal hintereinander die sparsamere Option empfohlen
(Fallback-Ketten, 3 Kandidaten, Kandidaten on-the-fly). Der Nutzer will
Qualitaet des Mixes, nicht Rechenzeit oder Einfachheit. Er erwartet, dass
diese Regel nie wieder vergessen wird.

Nachtrag (gleicher Abend): **Bassdruck und der Takt/Rhythmus von Bass und
Subbass** muessen analysiert und in die Kandidaten-Gewichtung einbezogen
werden; Harmonie und Klangfarbe muessen in JEDEM Design-Abschnitt sichtbar
auftauchen — der Nutzer prueft das und moniert jedes Fehlen.

**How to apply:**
- Bei Optionen die praezisere/vollstaendigere zuerst und als Empfehlung
  nennen; Aufwand benennen, aber nicht als Grund dagegen.
- Jede Kandidaten-/Uebergangsbewertung: Groove + Rhythmus + Harmonie +
  Lautheit + BPM (harte Grenze 2 BPM, heute ist STANDARD_BPM_TOLERANZ im
  Hoertest 6.0 und in der App konfigurierbar — anpassen!) + alle weiteren
  Scoring-Faktoren, gewichtet. Keine Teilmenge.
- Entscheidungen aus der Design-Runde: C (Hoertest + App), B (Rekordbox-
  Cues/Phrasen + HPG-Analyzer als Kandidatenquellen), A+B (benannte
  Schemata mit Kontrast/Dedupe), C (beide Blendenlaengen als eigene
  Kandidaten), C (Genre-Rangfolge lernen + Wahl pro Paar merken), Weg 2
  (Kandidaten pro Track vorberechnet, CACHE_VERSION-Bump bei
  Schema-Aenderung).

Siehe [[hpg-mixpunkte-individuell-cues-phrasen]].
