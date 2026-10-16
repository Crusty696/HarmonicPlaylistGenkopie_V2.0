---
name: hpg-deep-analysis
description: Koordiniert die Vorbereitung und schrittweise Ablösung oder Optimierung bestehender HPG-Analyse durch Rekordbox-Modelle, neuronale Merkmale und DirectML gemäß Deep-Analysis-Spezifikation.
---

# HPG Deep Analysis

Lies zuerst `hpg-orientation`, den aktuellen Nutzerauftrag und
`specs/REKORDBOX_DEEP_ANALYSIS_INTEGRATION.md`. Das Dokument beschreibt Ziele;
Beispielcode und behauptete Signaturen sind ohne Rohbeleg keine getestete Schnittstelle.
Eine reine Vorbereitungsanfrage erteilt keine automatische Freigabe zur gesamten
Produktimplementierung. Wenn der aktuelle Nutzer die vollständige Umsetzung
ausdrücklich freigibt, ist das der Arbeitsauftrag: autonom im spezifizierten
Umfang implementieren und den Status der Nachweise getrennt ausweisen.

## Bestand gezielt weiterentwickeln

Der Rekordbox-Referenzanker wird nur bei `verified` aus der Drei-Fenster-
Beatgridprüfung übernommen (`EXACT_BEAT_SYNC_TOLERANCE_SECONDS = 0.006` in
`downbeat.py`). Bei `mismatch`, darunter `consistent_offset`, geht
`_resolve_track_anchor` in den Audiozweig und behält den Rekordbox-Versuch in
der Diagnose. Das verschiebt oder überschreibt den Rekordbox-Rohanker nicht und
beweist nicht die musikalische Genauigkeit des Audioankers.

Ordne jede Anforderung einer vorhandenen Funktion und einem Verantwortlichen zu.
Entscheide anhand des Codes und der Messung: wiederverwenden, optimieren oder ersetzen.
Keine parallele Dauerimplementierung derselben Aufgabe. Die bisherige DSP-Analyse
bleibt Vergleichsbasis und begründeter Fehlerfallback, bis ein Ersatz seinen Vertrag
und Nutzen belegt. Ein Modellfehler darf keinen erfundenen Analysewert erzeugen.

Führe je Arbeitsscheibe eine kompakte Matrix im bestehenden Spezifikationsdokument:
Anforderung, bisherige Zuständigkeit, Zielverfahren, Ablösekriterium, erlaubte Dateien,
Regression, technischer Nachweis, unabhängige Qualitätsmessung, offener Punkt.
Keine ungemessenen Prozentziele erfinden. Numerische Abnahmekriterien vor Evaluation
festlegen und ungeklärte Anforderungen als offen ausweisen.

## Arbeit verteilen

- Artefakte/ABI: `hpg-rb-artifacts`, Skill `hpg-deep-analysis-artifacts`.
- Provider/Lifecycle: `hpg-inference`, Skill `hpg-deep-analysis-runtime`.
- Referenz- und Ablationsvertrag: `hpg-evaluation`, Skill `hpg-deep-analysis-evaluation`.
- Vorhandene Fachrollen bleiben zuständig: `hpg-rekordbox` für DB/ANLZ/Export,
  `hpg-analyse` für Analyse, `hpg-cache` für Persistenz,
  `hpg-mixpoints` für Zeitpunkte, `hpg-scoring` für Reihenfolge,
  `hpg-render` für Preview, `hpg-statistik` für Messrechnung,
  `hpg-tests` für Regression, `hpg-gui` für ausdrücklich beauftragte Oberfläche.
- `hpg-waechter` prüft unabhängig vor Umsetzung und am abschließenden Diff.

Jeder Schreibauftrag nennt exakte Dateien und Akzeptanzkriterien.
Agenten teilen denselben Workspace: fremde Änderungen bewahren, keine Reverts.
Nur unabhängige Recherche/Review/Testvorbereitung parallelisieren.
Ein Verantwortlicher führt teure Tests; relevante Dateien währenddessen einfrieren.
Neue Rollen müssen im aktuellen Agentenkatalog sichtbar sein. Andernfalls einen
verfügbaren Agenten mit dem ausdrücklich geladenen Rollenvertrag beauftragen;
Dateierstellung ist kein Beweis für Hotload.

## Übergaben und Invarianten

Jede Übergabe nennt Rohbelegpfad, Hash, Version, Befehl, Ergebnis und Beweisgrenze.
Unterscheide Absicht, Beobachtung und ausgeführten Nachweis. Ältere Skill-/Agententexte
sind keine Autorität gegen aktuellen Code: insbesondere Rekordbox-Herkunft nicht
automatisch als verifiziertes Grid oder richtige Takt-1 behandeln.

Beide Analysepfade und alle Konsumenten gemeinsam verfolgen. Änderungen am
Analyse-/Persistenzvertrag mit `hpg-cache` planen; keine feste Cache-Zielversion.
Strict-Sync, Confidence-, Drei-Fenster-, Phasenfehler- und Paar-Gates nicht lockern.
Eine Taktrotationsübernahme benötigt drei zusätzliche Bestätigungsfenster, die
sowohl mit den Rekordbox-Referenzfenstern als auch mit den Modellkandidatenfenstern
disjunkt sind. Kandidatenfenster dürfen nicht nochmals als Bestätigung zählen;
fehlen unabhängige Fenster, bleibt der bestehende Anker aktiv.
Unbekannte Vocals allein sperren kein Paar. Originalmusik nur am Quellort lesen;
keine persistenten Stems oder Hörclips. GPU-Ziel DirectML, CPU-Fallback separat.

Abschlussstatus pro Anforderung: vorbereitet, implementiert, automatisch getestet,
frisch mit Originaltracks nativ geprüft, Cache-Reuse geprüft, musikalisch bewertet.
EXE-Build und EXE-Lauf erst nach funktionalen Nachweisen separat behandeln.
Für reine Skill-/Dokumentationsarbeit reichen passende Struktur-/Verhaltensprüfungen;
keinen Produktvolltest oder Audioholdout allein dafür starten.
