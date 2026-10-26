---
name: hpg-deep-analysis-artifacts
description: Untersucht lokale Rekordbox-Modellartefakte und DLL-Schnittstellen für HPG mit reproduzierbarer Evidenz; trennt Exportnamen, Tensorformen, ABI, Vorverarbeitung und Modellsemantik.
---

# Rekordbox-Artefakte und Schnittstellen

Lies `hpg-orientation`, `hpg-rekordbox` und Phase A der Deep-Analysis-Spezifikation.
Die Installation ist Untersuchungsquelle. Pfade/Versionen lokal feststellen,
nicht den Beispielpfad übernehmen. Installationsdateien und Originalmusik unverändert lassen.

## Belegvertrag

Liefere dem Hauptagenten den Inhalt eines Manifests zur Ablage außerhalb des Repos:
absoluter Pfad, Größe, SHA-256,
Dateiversion soweit vorhanden, tatsächlich erkanntes Format, Untersuchungswerkzeug,
Befehl, Rohbeleg und offene Fragen. Keine Modelle oder Audiodateien ins Repo kopieren.
Decke die in Phase A genannten Stem-, Beat-, Cue-, Embedding-, Energie-, Genre-
und Normalisierungsartefakte ab; fehlende Dateien bleiben ausdrücklich fehlend.

Unterscheide für jede Aussage:
gefunden; statisch inspiziert; Schnittstelle rekonstruiert; erfolgreich inferiert;
Semantik unabhängig validiert. Keine Stufe impliziert die nächste.

## ABI vor Aufruf

Eine PE-Exporttabelle beweist Namen, nicht Parameter, Aufrufkonvention, Rückgabetyp,
Handle-Lifecycle, Bufferlayout, Ownership oder Threadsicherheit.
Keine aus Abschnitt 8 übernommenen `ctypes.argtypes/restype` ausführen.
Rekonstruiere fehlende Verträge aus verfügbaren Headern, Call-Sites oder lokaler
Artefaktanalyse. Verweise auf konkrete Rohstellen. Unbekanntes bleibt unbekannt.
Erst bei belegtem vollständigem Aufrufvertrag einen begrenzten separaten
Probeprozess planen: Timeout, Exitcode/Crashbeleg, Speichergrenze, Cleanup.
Keine DLL probeweise im GUI- oder Analysehauptprozess laden.

## Tensorvertrag vor Semantik

Pro Tensor Name, dtype, Rank, statische/dynamische Dimensionen erfassen.
Sample-Rate, Kanäle, Normierung, Fensterlänge, Hop, Padding, Zeitursprung,
Ausgabeeinheiten und Labelmapping brauchen eigene Belege.
59049 Samples belegen keine Sample-Rate; 50 Tags belegen keine Phrasengrenzen.
`output_1/output_2` belegen keine Beat-/Downbeat-Bedeutung.
Ein SavedModel belegt weder einen nutzbaren DLL-C-Export noch DirectML-Ausführung.

Übergabe an `hpg-inference`: vollständiger belegter Input/Output- und Lifecyclevertrag,
Artefakthash, ungelöste Felder und kleinster reproduzierbarer Probeplan.
Technische Unklarheit löst gezielte weitere Forschung aus; sie verwirft das
Rekordbox-Integrationsziel nicht. Keine erfundene Ersatzschnittstelle.
