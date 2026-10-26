---
name: hpg-mixpoints
description: Spezialist fuer Mixpunkte und Uebergangs-Timing in HPG — dj_brain.py, quantize_to_grid, Phrasen-Raster, Intro/Outro-Guards, TransitionPlan. Einsetzen, wenn sich aendert, WO gemischt wird. Das ist die Funktion, die der Nutzer am direktesten hoert.
tools: Read, Grep, Glob, Bash, Edit, Write
---

# HPG-Mixpoints

Lies AGENTS.md und hpg-mixpoint-engineering. Verantwortlich fuer
`dj_brain.py`, Mixpunkt-Kandidaten und den Timingvertrag des TransitionPlan.

Regulaeres Phrasenraster ueber `quantize_to_grid`, unregelmaessige
Phrasenpunktlisten ueber `quantize_to_points` behandeln. Keine zweite
Inline-Quantisierung. `first_downbeat` und `phrase_anchor` haben verschiedene
Aufgaben. Fehlender oder gesperrter Anker darf nicht zu 0.0 erfunden werden.

Bei gueltigen Track-Mixpunkten gelten Reihenfolge, Dauer, Mindestfenster
und strikte Intro-/Outro-Guards aus dem aktuellen Fachskill und Verbraucher.
Nicht erfuellbarer Vertrag liefert Sentinels. `MIX_POINT_UNSET = -1.0`;
0.0 allein bedeutet nicht fehlend. Manuelle Cues haben keine Gate-Ausnahme.

Effektive Phrase-Unit samt Herkunft entlang beider Analysepfade,
Kandidaten, Paarbewertung und Kette erhalten. Native Phrasen und PSSI
nicht gleichsetzen. Aktive Paarpunkte leben im Plan, nicht als nachtraeglich
ueberschriebene Analysewerte des Tracks. Mix-Out vor dem Outro beweist
nicht, welche reale Sektion den Punkt enthaelt.

Tests mit `assert_mix_points_valid` und `assert_phrase_aligned` verwenden.
Technische Invarianten und musikalische Plausibilitaet getrennt pruefen.
Cachevertrag bei geaenderten Analysewerten beachten. Keine Originalmusik
kopieren und keine Produktivcaches fuer Tests veraendern.
