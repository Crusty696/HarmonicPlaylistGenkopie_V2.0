---
name: hpg-deep-analysis-evaluation
description: Definiert unabhängige HPG-Referenzen und Ablösekriterien für neuronale Beats, Phrasen, Stems und Embeddings; prüft Holdout, Ablation und musikalische Beweisgrenzen.
---

# HPG Deep-Analysis-Evaluation

Lies `hpg-orientation`, den aktuellen Auftrag und Phasen C bis F der Spezifikation.
Diese Rolle entwirft Referenz-/Abnahmeverträge; statistische Berechnungen bleiben
bei `hpg-statistik`, Regressionen bei `hpg-tests`.

## Referenzen und Ablösung

Dokumentiere vor Tuning: bisheriges Verfahren, Kandidat, Zielmetrik, Mindestwert,
zulässige Verschlechterung, Ressourcenbudget und Entscheidung optimieren/ersetzen.
Fehlende Mindestwerte ausdrücklich offen lassen; Hauptagent und zuständige Fachrolle
legen sie anhand des dokumentierten Nutzervertrags vor der Auswertung fest,
bevor ein Ergebnis als bestanden gilt. Keine Schwellen nach Holdout-Ergebnis anpassen.
DSP-Baseline, Kandidat und Ablation auf identischer eingefrorener Kohorte vergleichen.

Trenne Tuning und Holdout nach Trackidentität; Duplikate und Varianten nicht auf
beide Partitionen verteilen. Manifest enthält Quellpfad/Fingerprint, Genre/Tempo,
Labelherkunft, exakte RB-Zuordnung, Modell-/Code-/Testhash und Analysemodus.
Mehrdeutige Basenames, BPM-Tags und Confidence sind keine unabhängige Ground Truth.
Unverifizierte RB-Grids nicht als PSSI-/Takt-1-Wahrheit verwenden.
Originale bleiben source-direct/read-only.

## Getrennte Qualitätsfragen

- Beat/Kick: Zeitfehler, Beat-F1/Continuity und Coverage; Halb-/Doppeltempo separat.
- Takt-1: Bar-Phase accuracy gegen unabhängige Labels; nicht durch Beatphase ersetzen.
- Phrase/Cue: Labelvertrag, Grenz-F1 und Zeitfehler je Strukturklasse.
- Stems: lokale Vocal/Bass/Drum-Kurven an tatsächlichen Kandidatenzeiten;
  Zeitabdeckung, Skala und Unsicherheit. Vocal-Schwelle 0.4 bleibt Hypothese.
  Fehlende Vocals allein sperren kein Paar.
- Bass-Swap: Zeitintervall und Fehler gegen beide lokalen Signale, kein exakter
  Zeitpunkt allein aus einem Beatgrid.
- Embeddings: Vektorgültigkeit/Normierung, Modellversion, Kosinusvergleich;
  Zusatznutzen und Redundanz zu vorhandenen Merkmalen durch Ablation/blinden Hörtest.
  UMAP-Koordinaten sind nicht automatisch ein Kompatibilitätsscore.

## Nachweismatrix

Fehlergründe und Ablehnungen erhalten. Nicht nur erfolgreiche Tracks auswerten.
Keine Confidence-/Sync-/Coverage-/Renderer-Grenze für bessere Erfolgsquoten lockern.
Vor Wiederholung vorhandene Hashes/Eingaben/Umgebung/Ergebnis auf Gültigkeit prüfen.

Technische Regression, unabhängige Modellgenauigkeit, nativer frischer App-Ablauf,
Cache-Reuse und menschliches Hörurteil bleiben getrennte Spalten.
`CohortAnalysisResult.analysis_origins` weist je Quellpfad `fresh`, `cache` oder
`unknown` aus; `analysis_origin` fasst als `fresh`, `cache`, `mixed` oder
`unknown` zusammen. `unknown` bleibt offen und darf weder als frische Analyse
noch als Cache-Reuse ausgegeben werden. Herkunft ist kein Trackfeld und keine
Cache-Zeile: verwaltete Hoertest-Snapshots speichern sie getrennt in
`hpg_analysis_origin`, gebunden durch den Hash der privaten Cachedatei.
`freeze_tracks` und Cohort-Snapshots fuehren sie separat vom Track-JSON weiter;
`write_snapshot` entpackt den Track unveraendert. Vorbereitung und spaeteres
Oeffnen melden die gespeicherte Herkunft; alte Snapshots bleiben `unknown`.
`HearingCohortWorker` und der Standard-Hörproben-Dialog fordern `cache_policy="fresh"`:
der erste Pfad analysiert die Auswahl direkt, der zweite setzt den bestehenden
`AnalysisWorker` für diesen Auftrag auf frisch. Track-Cache wird weder
gelesen noch beschrieben. Der Standarddialog friert nur Tracks mit Herkunft
`fresh` ein; `cache` oder `unknown` verhindert die Hörprobenvorbereitung. Direkte
`analyze_cohort`-Aufrufe behalten `reuse` als
Standard und muessen `fresh` ausdruecklich anfordern. Damit ist die Kohorten-
Vorbereitung vom persistenten Track-Cache getrennt.
Beim späteren Öffnen muss eine vorhandene Herkunftstabelle exakt dieselben
Trackpfade wie der private Snapshot abdecken; alte Sätze ohne Tabelle bleiben
`unknown`. Statuszeile und Bewertungsdialog zeigen `fresh`, `cache`, `mixed`
oder `unknown` verständlich an; der Dialog darf bei alten Sätzen keine frische
Analyse suggerieren. Ältere positive Cache-Versionen dürfen für das Öffnen und
Bewerten hashgebundener Quell-Sätze bestehen bleiben; aktuelle Analyse- und
Kalibrierungsläufe behalten ihre strengere Cache-Versionsprüfung.
Native Kette: Quelltracks auswählen, frisch analysieren, Paare bewerten, Playlist
erstellen, Preview rendern/abspielen, anwenden/exportieren.
Fehlende Schritte nicht als bestanden zählen. EXE ist ein späterer eigener Nachweis.
