---
name: hpg-deep-analysis-runtime
description: Plant und prüft HPG-Modellinferenz über DirectML und CPU samt Prozessgrenzen, Abbruch, Speicher, Datenabdeckung und gemeinsamem Vertrag beider Analysepfade.
---

# HPG Inferenzlaufzeit

Lies `hpg-orientation`, `hpg-parallel-performance` und den belegten
Artefaktvertrag aus `hpg-deep-analysis-artifacts`.
Ohne vollständigen Input-/Outputvertrag nur Forschung, keine Produktanbindung.

## Umgebung und Provider

Bestandsversionen und Paketkonflikte zuerst aus venv312 und Requirements lesen.
Paketmatrix der Spezifikation ist eine zu prüfende Ausgangsangabe.
Für Experimente eine separate Python-3.12-Umgebung und festen Paketstand vorsehen.
Produkt-venv und Requirements nicht nebenbei aktualisieren. Installation/Inferenz
müssen zum aktuellen Auftrag gehören; reine Vorbereitung führt sie nicht aus.

Prüfe DirectML anhand der zur installierten Runtime passenden Primärdokumentation.
Erfasse Sessionoptionen, Provideroptionen, tatsächlich verwendete Provider und
CPU-Fallback. Provider-Verfügbarkeit allein beweist keine GPU-Ausführung.
CPU- und DirectML-Läufe getrennt mit gleichen Eingaben messen; Toleranzen vorab
aus dem numerischen Vertrag ableiten. Für andere Formate deren tatsächliche Runtime
verwenden; TensorFlow nicht ohne Laufnachweis als DirectML-fähig bezeichnen.
Keine CUDA-/NVIDIA-Abhängigkeit einführen.

## Prozess- und Datenvertrag

Vor Eingriff in den Pool Initializer, Spawn-Verhalten, Abbruch und Shutdown lesen.
Sessions/Native-Handles nicht pro Track neu laden oder zwischen Prozessen teilen,
ohne den Lebenszyklus explizit festzulegen. Keine unbegrenzte Sessionvermehrung pro Worker.
RAM/VRAM-Budget, Parallelitätsgrenze, Batching, Timeout, Cancel und Teardown definieren.
Native ABI-Probes isolieren; kein Qt-Hauptthread-Block.

Für jedes Ergebnis Modellhash, Vorverarbeitungsversion, Quelle, Provider,
Zeitursprung, Zeitraster, Coverage, Fehlerstatus und Unsicherheit definieren.
Head/Tail-Lücken nicht interpolieren oder als gemessen darstellen.
Stems und Hör-Audio nur flüchtig im Speicher; keine Originalaudio-Kopien.
Fehlendes Modell/Provider, Timeout, NaN, ungültige Dimensionen und unvollständige
Abdeckung müssen diagnostizierbar bleiben und den bestehenden DSP-Fallback erhalten.

## Produktintegration erst als geprüfte Scheibe

Fast-Path und Vollpfad auf denselben Ergebnisvertrag abbilden.
Mit `hpg-analyse` Einhängestellen, mit `hpg-cache` Sentinels/Pflichtfelder/
Serialisierung/Invalidierung abstimmen. Kein vorgezogener Cache-Bump.
Modellwerte überschreiben verifizierte Referenzen nicht anhand maximaler Confidence.
Arbitration separat festlegen und testen. Synchronsperren unverändert lassen.

Nachweise getrennt liefern: Sessionaufbau, echte Inferenz, Fehlerfallback,
Cancel/Timeout, Ressourcennutzung, beide Analysepfade, Cache-Roundtrip.
Ein erfolgreicher Nulltensor-Smoke-Test beweist keine Audioqualität.



## Nativer Phrasenpfad (15.10.2026)
`hpg_core/ai_models/native_phrase_adapter.py` bindet einen hashgepinnten
Rekordbox-EXE-Ausschnitt über einen separaten Einmalprozess ein. Der bestehende
serielle Cue-Broker beendet vorher seine ONNX/TF-Lane; keine gleichzeitigen
4-GiB-Modellbudgets. Fast-/Vollpfad teilen diesen Aufruf. `native_phrase_analysis`
bleibt getrennt von importiertem PSSI; Cache 99 validiert Herkunft und aktive
`phrase_grid`-Quelle. Native Kandidaten heißen `native_phrase`, erhalten keinen
PSSI-Konfidenzbonus. PSSI hat Vorrang. Nur technisch bestätigte und nicht
Takt-gesperrte Grids; bestehende Synchron-/Coverage-Gates bleiben erforderlich.
`HPG_NATIVE_PHRASE=0` deaktiviert den nativen Weg. Bekannte Tonarten verwenden die ausgelesene native Tabelle; unbekannte Tonarten
verwenden ausdrücklich den belegten Unknown-Fallback 0. Der Cache bindet diese
Herkunft an die Track-Tonart. Das letzte Ende stammt aus Header[6] des nativen
Generators, auf das bestätigte einsbasierte Beatraster abgebildet. Der einzelne native Original-WAV-Lauf ist kein Nachweis der
musikalischen Qualität oder des vollständigen App-Ablaufs. Aktueller Belegstand
steht im Auftrag, nicht in einer duplizierten Statusliste hier.
