# Rekordbox Deep Analysis und Taktzuverlaessigkeit – integrierter Implementierungsplan

> **Stand 16.10.2026: Umsetzung beauftragt und technisch integriert; keine vollständige Produkt- oder musikalische Abnahme.** Der folgende Vorbereitungstext ist historisch. Aktuelle Nachweise und Grenzen stehen am Dokumentende. Nutzerauftrag umfasst inzwischen native Beat-/Takt-/Phrasenverarbeitung, Stems, Embeddings und Produktanbindung. Keine Stem-Wiederholung, keine Wiederholung gültiger Tests und kein EXE-Build vor Funktionsnachweisen.
> Diese Fassung fuehrt den urspruenglichen Plan aus diesem Dokument mit der laufenden Takt-/Downbeat-Diagnose zusammen. Der Plan verbindet die Taktkorrektur mit der verbindlichen Integration von Rekordbox-Analyse, ONNX/DirectML, neuronalen Phrasen, Stems und Audio-Embeddings. Produktcode, Cache und EXE wurden fuer diese Planrevision nicht geaendert.
>
> **Repository:** `C:\Users\david\Documents\HarmonicPlaylistGenerator_V2.0`
> **Runtime:** Python 3.12 / `venv312`. Die urspruengliche Spezifikation nennt AMD RX 7800 XT und DirectML-only; der tatsaechliche GPU-/DirectML-Laufzeitstatus ist fuer diese Revision nicht live verifiziert.
> **Arbeitsregel:** Originalmusik bleibt am Quellort und wird nur lesend analysiert/abgespielt. Keine Audio-Kopien, persistierten Audio-Hoertestclips, Cache-Manipulation oder EXE-Builds in diesem Plan-Audit.

## 0. Vorbereitung und Migrationsauftrag (14.10.2026)

**Ursprünglicher Vorbereitungsauftrag:** Mit diesem Auftrag vertraut machen, das Projekt vorbereiten
und benötigte Skills/Subagenten erstellen. Präzisierung: sowohl bestehende
Analyseverfahren als auch bestehende Skills/Agenten durch die hier beschriebenen
Verfahren ersetzen oder optimieren. Dieser Vorbereitungsschritt legt Zuständigkeiten
und überprüfbare Ablösekriterien fest; er ist noch keine Produktimplementierung.

### Beleggrenze der technischen Ausgangsangaben

Die als „verifiziert“ bezeichneten Modellangaben in Phase A, die Paketmatrix in
Abschnitt 7.1 und die Beispiele in Abschnitt 8 werden bei der Vorbereitung **nicht
als nachgewiesene Laufzeitverträge übernommen**. Die zugrundeliegenden Rohbelege
sind je Aussage erst zuzuordnen und zu prüfen. Die Integrationsziele bleiben erhalten.

- DLL-Exportnamen beweisen weder Argumenttypen, Rückgabetypen, Buffer-Ownership noch
  sichere Initialisierung. Kein ctypes-Aufruf allein nach den Beispielsignaturen.
- Tensorformen beweisen weder Sample-Rate/Normalisierung noch Labelsemantik.
  `output_1`/`output_2` sind ohne zusätzlichen Beleg keine Beat-/Downbeat-Zuordnung.
- SavedModel und eine vorhandene DLL beweisen keine nutzbare C-API oder DirectML-Ausführung.
- Paketversionsbereiche und Nulltensor-Beispiele sind keine Kompatibilitäts- oder
  Qualitätsnachweise. Erst isoliert und reproduzierbar prüfen, dann integrieren.

### Zuständigkeiten und Wiederverwendung

Einstieg: `.agents/skills/hpg-deep-analysis/SKILL.md`. Drei Fachskills ergänzen ihn:
`hpg-deep-analysis-artifacts`, `hpg-deep-analysis-runtime`,
`hpg-deep-analysis-evaluation`. Die Inhalte werden unter `.claude/skills/` gespiegelt.

Neue Rollen: `hpg-rb-artifacts` für Artefakt-/ABI-Verträge, `hpg-inference` für
Provider und Lifecycle, `hpg-evaluation` für Referenz- und Ablösekriterien.
Bestehende Analyse-, Rekordbox-, Cache-, Mixpoint-, Scoring-, Render-, Statistik-,
Test- und GUI-Rollen werden weiterverwendet und bei belegten Widersprüchen optimiert.
Der Hauptagent koordiniert; `hpg-waechter` prüft unabhängig.

Persistente Codex-Rollen liegen als Standalone-TOML unter `.codex/agents/` mit
`name`, `description`, `developer_instructions`, entsprechend der
[offiziellen Agentendokumentation](https://developers.openai.com/codex/subagents).
Dateivalidierung beweist keine Aktivierung in einer laufenden Sitzung. Bei fehlendem
Katalogeintrag den Rollenvertrag ausdrücklich an einen verfügbaren Agenten übergeben.

### Migrationsmatrix: bestehende Verfahren verbessern oder ablösen

| Bereich | Bestehenden Vertrag zuerst lesen | Ziel und Ablösekriterium | Verantwortlich |
|---|---|---|---|
| Beat-/Taktphase | `analysis.py`, `downbeat.py`, `tempo_refinement.py` | Neuronale Ergebnisse nach unabhängig belegter Beat- UND Bar-Qualität übernehmen; Sync-Gates bleiben | hpg-analyse, hpg-inference |
| Phrasen/Struktur/Cues | `rekordbox_phrases.py`, `structure_analyzer.py`, `mix_candidates.py` | Modellgrenzen mit belegten Labels/Zeitbezug; PSSI nur bei verifiziertem Grid; keine doppelte Anchor-Entscheidung | hpg-rekordbox, hpg-analyse, hpg-mixpoints |
| Vocal/Bass/Drum-Merkmale | `analysis.py`, `pair_candidates.py` | Lokale Stem-Kurven ersetzen/verbessern Merkmale erst nach Coverage-/Nutzenbeleg; unbekannte Vocals sperren nicht | hpg-analyse, hpg-scoring |
| Klangvergleich | `pair_candidates.py`, `transition_features.py` | Embeddings gegen bestehende Merkmale ablatieren; redundante Faktoren nicht doppelt gewichten | hpg-scoring, hpg-statistik |
| Laufzeit/Persistenz | `parallel_analyzer.py`, `models.py`, `caching.py` | Gemeinsamer Ergebnisvertrag beider Pfade, kontrollierter Lifecycle und Cache-Roundtrip | hpg-inference, hpg-cache |
| Preview/Export/App | `transition_renderer.py`, `exporters/`, `main.py` | Gleicher geprüfter Paarplan bis Wiedergabe/Export; GUI nur mit konkretem Akzeptanzpunkt | hpg-render, hpg-rekordbox, hpg-gui |
| Skills/Agenten | Bestehende Fachverträge und aktuelle Codebelege | Veraltete Aussagen in place korrigieren, Spiegel synchron halten; neue Rollen nur für fehlende Zuständigkeiten | Hauptagent, hpg-waechter |

Diese Matrix ist ein Arbeitsauftrag, keine Behauptung bereits erfolgter Ablösung.
Je Scheibe zuerst exakte Dateien, Eingaben, Referenzen, numerische Mindestwerte,
Regression und Rückfallverhalten festlegen. Keine dauerhaften Doppelimplementierungen.
Die DSP-Baseline bleibt für Vergleich und den in Phase B geforderten Fehlerfallback.

Nächste Arbeit: vorhandene Rohbelege/Hashes zuordnen, Modellmanifest und ABI-/Tensorvertrag
erstellen, Referenzkohorte und Ablösekriterien definieren, danach eine kleine
isolierte Inferenzscheibe vorbereiten. Produktintegration folgt ihrem eigenen
Prüfvertrag. Technische, native und musikalische Nachweise bleiben getrennt.

### Ausführungsstand nach ausdrücklichem Zielauftrag (14.10.2026)

Der Nutzer hat inzwischen die vollständige funktionale Umsetzung autorisiert.
Priorität 1 ist der Analyse-/Rekordbox-Umbau; Playlistverbesserung und zuverlässige
Hörproben-Erstellung/Bewertung gehören zum Gesamtziel. Der frühere Status
„Vorbereitung“ beschreibt den vorherigen Arbeitsschritt, nicht die aktuelle Freigabe.
Zusätzlicher Ausführungsvertrag: `AGENT_EXECUTION_INSTRUCTIONS.md`.

**Aktuelle Nutzerpriorisierung (14.10.2026, nach Statusbericht):** Stems und
Embeddings werden für die erste Ausbaustufe zurückgestellt, sofern sie keine
notwendige Abhängigkeit des Analyse-/Rekordbox-Umbaus sind. Die bereits erhobenen
Artefaktbelege bleiben erhalten; daraus folgt kein weiterer Implementierungsauftrag
für diese beiden Merkmalsgruppen in der ersten Ausbaustufe. Vorrang haben Beat-,
Downbeat-, Phrasen-/Cue-Analyse und deren Verwendung für Playlist und Hörproben.
Track-Felder und Cache werden nur soweit angepasst, wie diese aktiven Analysewerte,
ihre Herkunft und die Invalidierung veralteter Ergebnisse es erfordern. Keine
Stem-/Embedding-Felder auf Vorrat. Die entsprechenden ursprünglichen Planpunkte
bleiben dokumentiert, gelten aber als zurückgestellt und nicht als erledigt.

| Scheibe | Aktueller Nachweis | Noch offen |
|---|---|---|
| ONNX-Laufzeitbasis | `onnx_engine.py`: Lazy Import, gemeinsame Sperre, Prozess-/Modellidentität, LRU2, DirectML/CPU-Diagnostik; 34 gezielte Tests der damaligen Scheibe bestanden; inzwischen über gemeinsamen Dienst angeschlossen | Schlussprüfung im vollständigen App-Ablauf |
| Dependencies | ORT DirectML 1.21.0 und TensorFlow CPU 2.16.2 installiert; NumPy 1.26.4 unverändert; Paket-/Änderungsmanifest in `beat-predictor-final-state.json` | Schlussprüfung gesamter Anwendung |
| SampleCNN-Smoke | Gepinntes lokales Modell; endliche Formen [1,50]/[1,512] auf CPU und DML; Profil mit 25 DML-Knotenereignissen | Gerät-0-Zuordnung zur RX 7800 XT und musikalischer Nutzen |
| Artefaktverträge | Lokale Rekordbox-Version 7.2.19; Modelle statisch gelesen und gehasht | Call-Sites/Vorverarbeitung/Outputsemantik vollständig rekonstruieren |
| Cue-Adapter und Strukturanschluss | Der Cue-Regressor erhält vorhandene Kandidaten und erzeugt selbst keine. Ohne PSSI erzeugt `structure_analyzer._pick_boundaries` bereits Audio-Novelty-Sektionsgrenzen; `mix_candidates.collect_candidate_times` kann Sektionsgrenzen als Mixkandidaten nutzen. Die Phrasenlänge und Quantisierung hängen am gewählten Phrase-Raster. | Semantische Cue-/Phrasenlabels aus Nicht-PSSI-Kandidaten, unabhängige Label-/Qualitätsmessung und native Produktabnahme. Vorhandene DSP-Sektionsgrenzen nicht als neuronale PSSI-Grenzen ausgeben. |
| Begrenzte Windows-Modellprozesse | `process_runtime.py`: Lazy Spawn, privater Bytes-Transport, Job-Zuweisung vor Handlerimport, Deadline/Cancel und begrenztes Cleanup; 21 gezielte Tests; gemeinsamer Dienst für direkte Analyse und Analysepool angeschlossen | Vollständiger App-Nachweis; CPython-Vorbereitung liegt vor eigener Job-/Watchdog-Absicherung |
| Beatdecoder | Vierer-Takt-Viterbi, getrennte Beat-/Bar-Diagnosen, ausdrücklich unverifiziert; 45 Tests bestanden, danach zwei zusätzliche Pflichtfälle separat bestanden | Bekannte Tempoaliasfälle; Übernahmevertrag und unabhängige Beat-/Bar-Genauigkeit |
| Beatadapter | Modell7/8 separat auf CPU; gepinnte Artefakte, 44100-Hz-Eingang, 100-fps-Aktivierungen; 30 Tests und echte kontrollierte synthetische Modellprobe bestanden | Native Modellwahl und Gleichheit zum nativen Audioreader nicht vollständig bewiesen |
| Audio-Prüfung externer Beatereignisse | Optionales `external_beats` in bestehender Downbeatfunktion; nur beobachtete Ereignisse, physische Nummerierung und Audio-Voting bestätigen Modellrotation; 28 gezielte Tests bestanden. Sechs synthetische Standardfälle liefern identische Ergebnisse und Diagnosen wie die gesicherte Vorversion (`downbeat-external-*`, `downbeat-default-parity.*`) | Inzwischen über gemeinsamen Track-Resolver angeschlossen; unabhängige Qualitätsmessung und vollständiger nativer Ablauf bleiben offen |
| Gemeinsamer Cue-/Beatdienst und Persistenz | Beide Produzenten, lazy direkte Tracksession, gemeinsame Deadline/Lane, getrennte Modellresultate, höchstens drei 16-s-Quellfenster bei 44100 Hz; Schema 2 / Cache 54; zunächst 54 Tests und echte Cue→Beat→Cue-Probe bestanden. Zwei anschließende Schema-Befunde durch 2 RED / 12 gezielte GREEN-Tests korrigiert und unabhängig nachgeprüft | Keine Anchor-/BPM-/Scoring-Übernahme in dieser Scheibe; frühere 54 Tests und echte Probe nicht nachträglich als neuer Gesamtlauf ausgegeben |
| Tatsächliche neuronale Ankerübernahme | Gemeinsamer Resolver in beiden Analysepfaden: RB-Vorrang, geprüfte DSP-Baseline, lokale Audio-Bestätigung externer Beats, drei nicht überlappende Fenster je Modell, modellübergreifende 6-ms-Taktprüfung und abschließendes Gesamtgrid. Phrasen/Struktur/Mixpoints erhalten den gewählten Anker; Diagnose-Schema 2 / damals Cache 55. Producer-RED, anschließend 31 gezielte Tests; nach strikterer Typprüfung und ergänzt geprüfter Weitergabe/Gates sieben Ankertests bestanden (`neural-anchor-*`); TOR2 DURCHGEWUNKEN | Cue-Rohscores sind inzwischen in der Kandidatenauswahl angebunden (siehe separate Zeile); Originaltrack-/App-/Hör-/EXE-Abnahme und unabhängige musikalische Qualitätsmessung offen; spätere BPM-Übernahme in der nächsten Zeile. |
| Audio-bestätigte Modell-BPM-Übernahme | Beide Analysepfade entscheiden vor Genre und Rhythmusmerkmalen. Verifiziertes ursprüngliches RB-Grid hat Vorrang; sonst müssen Modell 7 und 8 in drei getrennten Fenstern übereinstimmen, und Audio-Refiner sowie Gesamtgrid bestätigen das Tempo. Ursprünglicher RB-Prüfversuch bleibt separat; effektives BPM erreicht Track, Struktur und Mixpunkte. Damals Cache 56. Producer-RED (120 statt 125 BPM), danach 11 gezielte Tests; nach Cache-Bump erneut 11 bestanden (`neural-bpm-*`). Fachliches TOR2 ohne Produktdefekt, Urteil MIT AUFLAGEN wegen fehlender unabhängiger TOR1-Schlussfreigabe. | Kein unabhängiger Genauigkeits-/Originaltrack-/App-/Hörnachweis; historisches TOR1 nicht rückwirkend als Freigabe darstellen. Spätere Cue-Übernahme in der nächsten Zeile. |
| Cue-Rohscores in der Kandidatenauswahl | Der Scoreauftrag bindet die ursprüngliche PSSI-Identität, RB-Quellsignatur und Modell-/Vorverarbeitungsidentität. Head-/Tail-Widerspruch, ungültige Bindung und Quantisierungskollision bleiben neutral. Erfolgreiche Scores ordnen nur gleichrangige bewertete PSSI-Plätze vor der Acht-Kandidaten-Grenze; manuelle und unbewertete Plätze sowie alle Gates bleiben unverändert. Historischer Cache-57-Stand: ein RED, danach fünf gezielte Tests mit beiden Produzenten und Cache-Roundtrip. Manifest: `frozen_for_TOR2`; zugehöriger Bericht: TOR2 offen. Diese Laufbelege gelten wegen Hashabweichungen in drei von vier Quellen nicht als aktueller Test-/Freigabenachweis. | Musikalischer Nutzen, Originaltrack-/App-/Hör- und unabhängiger Qualitätsnachweis offen; Rohscores sind keine Wahrscheinlichkeiten. |

### Konstanter Zeitversatz im Rekordbox-Beatgrid — Kandidat und Bestätigung

Die bestehende Dreifensterprüfung klassifiziert ein Rekordbox-Grid mit stabilem Phasenfehler über 6 ms als `mismatch` und kann den Befund als `consistent_offset` beschreiben. Die Trackdiagnose verwendet dafür `reference_constant_offset`. Cache 80 vergleicht Modellbeats zusätzlich mit PQTZ-Ticks, die um den gemessenen Audio-minus-Grid-Phasenmittelpunkt projiziert sind. Dieser Vergleich verwendet dieselben Quellfenster wie die Offsetmessung; `offset_compensated` bleibt deshalb zunächst nur ein Kandidat.

Cache 81 ergänzt eine getrennte Bestätigung: HPG sucht drei Audiofenster, die keines der Offset-/Kandidatenfenster überlappen. Model 7 und Model 8 müssen in allen drei Fenstern BPM und beobachtete Beats liefern. Ein separater lokaler Downbeat-Schätzer bestätigt jedes Modellfenster gegen die phasenprojizierte Taktposition; jedes muss innerhalb 6 ms liegen. Das aus genau diesen getrennten Fenstern gebildete Gesamtgrid muss ebenfalls verifiziert sein. Fehlen drei disjunkte Fenster oder scheitert ein Gate, bleibt der Kandidat gesperrt und der Audiofallback aktiv. Cache 86 verwirft reine Rotation-0-Korrektur, wenn der signed Offset den aktiven Anker über eine Bar-Grenze wickeln würde. Cache 85 erlaubt zusätzlich eine reine Zeitkorrektur bei Rotation 0: dieselben drei disjunkten Bestätigungsfenster pro Modell müssen die phasenprojizierte Referenz jeweils innerhalb 6 ms bestätigen, danach muss das getrennte B-Gesamtgrid verifiziert sein. Bei Erfolg entsteht `model_audio_phase_offset`; Roh-PQTZ-Ticks, Bar-Labels, PSSI-Freigabe und `strict_beat_sync` bleiben unverändert. Der technische Beatnachweis bestätigt keine unabhängige musikalische Takt-1-Wahrheit.

Bei vollständiger Bestätigung darf nur der aktive, abgeleitete HPG-Audioanker um Zeitversatz und Taktrotation angepasst werden. Rekordbox-Rohticks bleiben unverändert; der Anker bleibt Audioherkunft, Rekordbox-PSSI und Rekordbox-Render-Sync werden nicht freigegeben, und `strict_beat_sync` bleibt aktiv. Ohne unabhängige, musikalisch geprüfte Takt-1-Referenzen ist dies ein technischer Audio-/Modellnachweis, keine musikalische Genauigkeitsabnahme.
**Workflow-Implementierung 14.10.2026 — frischere Hörproben-Snapshots, unvalidiert:**
Der Standard-Hörproben-Dialog ruft den vorhandenen `AnalysisWorker` nun mit
`cache_policy="fresh"` auf. Normale Analyseläufe behalten `reuse`; der Worker
übergibt die Policy an `ParallelAnalyzer`. Der Hörprobenauftrag wird vor dem
Threadstart an genau diesen Worker gebunden, damit auch sehr kurze oder leere
Scans keinen Abschluss vor der Auftragsregistrierung senden. So stammen
verwaltete Hörproben-Snapshots aus dem gerade angeforderten Analyseablauf und
nicht still aus dem Track-Cache. Die Kohortenanalyse lehnt ausserdem pro Track
`cache`- und `unknown`-Herkunft trotz angeforderter Frische ab, statt den Satz
als vollstaendig zu markieren. Das Einfrieren des Standarddialogs lehnt
`cache`- oder `unknown`-Herkunft ab. Es wurden keine Tests, Prüfungen oder
Audioabläufe ausgeführt. Beim späteren Laden wird eine vorhandene
Herkunftstabelle gegen die vollständige Trackpfadmenge des privaten Snapshots
abgeglichen; fehlende oder fremde Herkunftszeilen lassen den Ladevorgang
fehlschlagen statt einen unvollständigen Status anzuzeigen. Statuszeile und
Bewertungsdialog zeigen den aufgelösten Herkunftsstatus einschließlich
`unknown` an. Frühere positive Cache-Versionen bleiben für das Öffnen und
Bewerten quellgebundener Sätze zulässig; aktuelle Trackanalyse und Kalibrierung
behalten ihre jeweilige strengere Versionsvalidierung.

Die Hörproben-Snapshots serialisieren den vollständigen validierten Track:
`beatgrid_source`, aktiven Anker und `measurement_diagnostics` bleiben darin
enthalten; die Laufzeit-Herkunft `analysis_origin` wird separat gespeichert.
`validate_track_dict` verlangt, dass Quelle, Anker, Konfidenz und Gridstatus
der aktiven Diagnose mit den Trackfeldern übereinstimmen. Damit bleibt ein
Version-78-`model_audio_rotation`-Anker als Audioherkunft erhalten und kann
beim Laden nicht als unveränderte Rekordbox-Referenz erscheinen. Dieser
Datenfluss ist quellenbasiert beschrieben und hier nicht neu validiert.

**Phrasenlängen-Scheibe 14.10.2026 — implementiert, unvalidiert:** Bei
bestätigtem Beatgrid und schwacher erster Phrasenphase lassen beide Analysepfade
die Audio-Novelty-Messung die Genre-Prior-Phrasenlänge bestimmen. Das Head-
Fenster wählt die Einheit; das Tail übernimmt sie, damit keine zwei Raster in
einem Track gemischt werden. Die Phrase bleibt am bestätigten Downbeat
verankert, solange ihre Phase schwach ist. Gesperrte oder unbestätigte Raster
behalten den Genre-Prior. Der Track speichert `phrase_unit_source` als
`audio_novelty`, `genre_prior` oder `configured`; `CACHE_VERSION` ist dafür auf
77 erhöht. Genreprofilwerte behalten auch bei interner expliziter Weitergabe
die Herkunft `genre_prior`; externe explizite Einheiten bleiben `configured`.
`audio_novelty` darf ausschliesslich nach tatsaechlicher Messung entstehen; ein expliziter Herkunftsparameter kann diesen Messbeleg nicht vortaeuschen. Das Tail-Fenster uebernimmt `genre_prior`, waehrend die zusammengefuehrte Track-Struktur weiterhin die Herkunft des Head-Fensters fuehrt.
Messdiagnose-Schema v6 speichert Phrasenlänge, Herkunft, besten
Kandidaten, rohe Novelty-Korrelation und Ranking-Abstand zum Zweitkandidaten;
die Cachevalidierung bindet diese Werte an die Trackfelder und behält in
Version 6 die Rotationssperre aus Schema 5 bei. `audio_novelty`
erfordert dort ein verifiziertes Grid und einen belastbaren aktiven Downbeat-
Anker. Das sind keine
kalibrierten Wahrscheinlichkeiten. Das Messpanel zeigt sie ohne Neuanalyse.
Die Paar-Mixpunktberechnung verwendet die gemessene Track-Einheit, wenn ihre
Herkunft `audio_novelty` ist; Genre-Prior-Fälle bleiben profilgesteuert. Es
wurden keine Tests oder Laufzeitnachweise ausgeführt.
Das vorhandene Messdiagnose-Panel zeigt Phrasenlänge und Herkunft zusammen mit
der gespeicherten Beat-/Takt-Diagnose an; es berechnet dabei nichts neu.

Der Nutzer hat am 14.10.2026 bestätigt, keine selbst geprüften Takt-1- oder
Phrasenmarkierungen bereitzustellen. Eine unabhängige Referenzkohorte fehlt daher
weiterhin. Technische Tests, Audio-Konsistenz und Modellübereinstimmung ersetzen
keine musikalische Genauigkeitsmessung. Zusätzliche Rohbelege:
`beat-decoder-{green,required-cases}.txt`, `beat-predictor-signature-green.txt`,
`beat-integration-{manifest.json,report.md,green.txt}`, `beat-validator-{red,green}.txt` und
`beat-service-real-smoke.{py,txt}` im unten genannten externen Belegverzeichnis.

Rohbelege dieses Schritts: `%TEMP%/hpg-deep-implementation-20261014/`
(`onnx-red.txt`, `onnx-green.txt`, `samplecnn-smoke.stdout.txt`, `pip-install.json`,
`model-artifacts.md`, `research-abi/`). Keine Vollsuite oder Hörtests in dieser
Entwicklungsscheibe; kein Cache-Bump vor tatsächlicher Änderung des Analysevertrags.

Die erste unabhängige Nachprüfung fand einen Outputvertragsfehler: endliche,
aber falsch geformte/typisierte Ausgaben wurden akzeptiert. Regression vor Fix:
15 fehlgeschlagen/19 bestanden; danach dieselben 34 Tests bestanden. Die korrigierte
Laufzeit prüft Anzahl, Typen und Dimensionen einschließlich gemeinsamer Symbole.
Eine erneute SampleCNN-Nulltensorprobe lieferte wieder endliche [1,50]/[1,512].
Belege: `onnx-output-red.txt`, `onnx-output-green.txt`,
`samplecnn-outputfix.stdout.txt`, `onnx-outputfix-source-hashes.json`.

Weitere begrenzte Forschungsnachweise, ohne Änderung der Produktanalyse:

- TOR 2 hat die korrigierte ONNX-Basis freigegeben; Bericht
  `onnx-tor2-outputfix.md` formal validiert.
- `samplecnn-profile.stdout.txt`: 25 Knotenereignisse mit DirectML-Provider.
  Gerät-0-Zuordnung zur RX 7800 XT bleibt ungeprüft. Expliziter CPU-Lauf ebenfalls
  endlich (`samplecnn-cpu.stdout.txt`); noch keine musikalische Genauigkeitsabnahme.
- `beat-probe.stdout.txt`: Modell 7 läuft mit TensorFlow CPU 2.16.2 in separater
  Forschungsumgebung. Nullinput [1,44100] liefert endliche [101,314]/[101,2].
  Samplerate und Klassenbedeutung folgen daraus nicht.
- `cue-model-smoke.stdout.txt`: DOUBLE-Nullinput [1,3085] liefert endliches [1,1].
  Native Featurefolge: 10+3 Onehot-Spalten, danach sechs 512er-Vektoren;
  Endauswahlfilter weiterhin offen; Kategorien inzwischen unten präzisiert
  (`research-cue/FINDINGS.md`).
- Offizielles `demucs3_0002.zip` anhand des EXE-Versionsparsers ermittelt und nur
  extern extrahiert (`research-abi/ZIP-URL-PROOF.txt`,
  `demucs-extracted-manifest.json`). `demucs-load.stdout.txt` belegt isoliertes
  Laden und `IsInitialized=false`. Danach CPU-ORT- und DML-Initialisierungszweig
  separat mit `PreOperation`/`AtIndexSeparatedBass` ausgeführt: je acht endliche
  Nullausgaben, Exit 0 (`demucs-index.*`, `demucs-index-dml.*`). Synthetische
  Nullbuffer, keine Stemlabel-/Trennqualitäts- oder Geschwindigkeitsabnahme.
- Cue-Kategorien und Reihenfolge sind inzwischen statisch geschlossen:
  rohe PSSI-`kind` 1..10, `mood` 1..3; zuerst deren 13 Onehotwerte, danach sechs
  chronologische 512er-Features ohne Pooling. Kleine native Kontexte sind nicht
  als gültiger Modellvertrag übernommen. Belege: `research-cue/PSSI-ONEHOT-CONTRACT.md`
  und `FEATURE-SEQUENCE-CONTRACT.md`. Adapter: `cue-adapter-green.txt`,
  `cue-adapter-smoke.stdout.txt`, `cue-tor1.md`, `cue-tor2.md`, `cue-source-hashes.json`.
- Struktur-Core: `cue-structure-green.txt`, `cue-structure-smoke.*`,
  `cue-structure-tor1.md`, `cue-structure-tor2.md`, `cue-structure-source-hashes.json`.
  Anschluss-RED 14 fehlgeschlagen, abschließend 18 bestanden. Ein zusätzlicher
  NaN-BPM-Fehler wurde gegen den vorherigen Guard retrospektiv reproduziert;
  dies ist kein vor der Korrektur ausgeführter TDD-Nachweis.

**Implementierungsnachtrag 14.10.2026 — Taktpositions-Nutzungssperre; nicht validiert:**
Bei einer Schema-v5-Diagnose `candidate_rotation` mit Modell 7 und Modell 8 in
denselben drei Fenstern und einheitlicher Nichtnullrotation sperren beide Analysepfade
jetzt PSSI-/Cue-
Nutzung, Phrase-Anker/-Grid, Mixpunkte und Mixkandidaten. `Track.phrase_anchor`
liefert in diesem Zustand `None`; Pairing und DJ Brain brechen vor einer
Phrasenquantisierung ab. Der Renderer behaelt Beat-Confidence und
`strict_beat_sync`, setzt aber die Taktphasenfreigabe zurueck. Der Rekordbox-
XML-Export unterdrueckt `Battito=1` und Cue-Punkte, auch bei extern uebergebenen
Mixpunkten. Der Rohanker und BPM bleiben unveraendert. Cache-Version 71 enthaelt
zusaetzlich die eindeutige ANLZ-Gruppenzuordnung fuer PSSI/PQTZ-Phrasen; bei
mehrdeutigen Gruppen entstehen keine Phrase-Daten. Die vorherige
Cachevalidierung verlangt weiter leere Phrase-/Mixausgaben; Projektwissen sowie
die Cache-, Mixpoint-, Rekordbox- und Renderer-Skill-Spiegel beschreiben den
Vertrag. Diagnoseansicht und Tabellen-Tooltip zeigen den persistierten
Rekordbox-Referenzversuch mit signiertem Zentrum „Audio minus Grid“ getrennt
vom aktiven Grid/Audioanker und benennen ihn als Grund fuer die Audioankerwahl;
damit bleibt ein konstanter Zeitversatz sichtbar, auch wenn der Audio-Fallback
ein eigenes verifiziertes Raster liefert.

Tests, Prüfskripte und Hörläufe wurden auf ausdrückliche Nutzeranweisung nicht
ausgeführt. Der Codezustand ist deshalb **implementiert, aber unvalidiert**;
kein Laufzeit-, Originaltrack-, Cache-Reuse- oder musikalischer Nutzenbeleg
folgt daraus. Diese Rotationssperre behandelt weder einen zeitlichen
Beatphasenversatz wie 16,3 ms als bestätigte Taktrotation noch korrigiert sie
ein solches Grid automatisch. Bereits bestehender Resolver verwirft ein
Rekordbox-Grid, das die 6-ms-/Drei-Fenster-Prüfung nicht besteht, und verwendet
den Audiozweig; dessen unabhängige musikalische Genauigkeit bleibt offen.

**Nächste abhängige Arbeit:** Den verbundenen Analyse-, Playlist- und Hörprobenablauf
  mit frischen Originaltracks und isoliertem Cache prüfen. Die gemeinsame Taktanker-,
  Tempo- und Cue-Kandidatenentscheidung sind technisch angeschlossen; Beatphase und musikalische
  Takt-1 bleiben getrennte Größen. Die Modellfenster selbst sind kein unabhängiger
  Holdout. Cue-Rohscores wirken nur innerhalb der bestehenden Phrasen-/Coverage-/Mixpoint-Gates.
  Referenz- und Abnahmekriterien vor Qualitätsauswertung festlegen; fehlende Labels
  offen halten. Danach vollständigen nativen Originaltrack-Ablauf einschließlich
  Playlist und Hörproben nachweisen. Die Gesamtphase bleibt offen.

**Statische Korrekturen zu den bisherigen Ausgangsangaben:** Cue-Prediction ist
ein TreeEnsembleRegressor mit DOUBLE-Rang-2-Input und Featurezugriffen bis Index 3084;
die Featurefolge ist inzwischen oben belegt, Vorverarbeitungsgleichheit und Qualität
bleiben ungeprüft. Die Beat-SavedModels liefern
`output_1` mit Form [-1,-1] und `output_2` mit Form [-1,2]; deren musikalische
Bedeutung ist dadurch nicht belegt. SampleCNNs 59049 Samples belegen allein keine
Samplingrate. `demucs3Initialize` liest mehrere Argumentpositionen; der argumentlose
Beispielaufruf darf nicht als tatsächlicher ABI-Vertrag verwendet werden.

## 1. Ziel und Grenzen

HPG soll aus Track-Auswahl und Analyse belastbare Empfehlungen fuer Reihenfolge, Mix-In/Mix-Out und Uebergaenge erzeugen. Beat-Phase (Kick/Beat-Synchronitaet), Taktphase (welcher Beat ist die "1"), Phrasenphase, Tempo und Mixpunktqualitaet sind getrennte Messgroessen. Ein Erfolg in einer Groesse darf keinen anderen Vertrag ersetzen.

Der urspruengliche Wunsch nach Rekordbox-aehnlicher Deep Analysis bleibt vollstaendig erhalten:

1. Rekordbox-Metadaten/ANLZ weiter verwenden, wo sie eindeutig, lesbar und unabhaengig gegen Audio pruefbar sind.
2. Neuronale bzw. ONNX-basierte Beatgrid-/Phrasen- und Strukturmerkmale auch fuer Tracks ohne geeignete Rekordbox-Daten integrieren; vor ihrer Nutzung fuer Entscheidungen Qualitaet messen und kalibrieren.
3. Stem-Energie fuer Vocals, Bass und Drums sowie Embeddings als zusaetzliche lokale Paarmerkmale integrieren. Ihren messbaren DJ-Nutzen gegen DSP-Baselines pruefen und Gewichte/Gates anhand der Ergebnisse kalibrieren, ohne die bestehenden Sync-Gates zu ersetzen.
4. GPU-Beschleunigung ueber DirectML und CPU-Fallback untersuchen, ohne CUDA/NVIDIA-Abhaengigkeit einzufuehren.
5. Beide Analysepfade, Cache, Paarbewertung, Playlist, Preview/Render und Rekordbox-Export konsistent halten.
6. Den bestehenden strikten Beat-Sync-Vertrag unveraendert lassen. Kein Planpunkt darf Confidence-, Fenster-, Phasenfehler-, Pair-Gate- oder Renderer-Schwellen lockern.

**Verbindliches Projektziel:** Dies ist ein privates HPG-Forschungsprojekt. Rekordbox-Analyse soll in HPG integriert werden, damit die Beat-, Takt- und Phrasenprobleme beseitigt werden. Die Rekordbox-Modelle und -Artefakte aus der lokalen Installation sind deshalb primaere Untersuchungsgegenstaende dieses Plans. Ihre tatsaechliche Verfuegbarkeit, Dateiformate, Inputs/Outputs, Modell-Laufzeit und technische Kopplung sind offene technische Aufgaben, keine Gruende, das Integrationsziel zu verwerfen. Ungeklaerte Schnittstellen werden durch gezielte lokale Artefaktanalyse und Experimente untersucht; gefundene Erkenntnisse werden mit reproduzierbaren Tests und Messungen abgesichert.

## 2. Aktueller Codevertrag und harte Invarianten

Die folgenden Punkte sind im aktuellen Quellcode geprueft, aber sie sind keine Aussage ueber musikalische Richtigkeit:

- `analysis.analyze_track` hat einen Rekordbox-Fast-Path und einen Librosa-Vollpfad. Beide bauen Downbeat-, Phrasen-, Struktur- und Mixpunktdaten. Ein Analysealgorithmus, der einen Pfad aendert, muss beide Pfade abdecken.
- Rekordbox-PQTZ/ANLZ wird eingelesen und ein `beat == 1`-Tick als Referenzkandidat verwendet. Das ANLZ-Grid wird gegen drei getrennte Audiofenster geprueft. Nur Status `verified` setzt den Referenzanker auf Konfidenz 1.0 und erlaubt den aktuellen PSSI-Phrasenpfad.
- Das audioeigene Downbeat-Voting schaetzt Bar-Phase; die Fold-Messung schaetzt Sub-Beat/Kick-Phase. Diese sind nicht austauschbar. Die Analyse validiert ein Grid ueber mindestens drei Fenster, hoechstens 6 ms Phasenfehler und die bestehenden Tempo-/Intervallregeln.
- `TransitionClipSpec.from_plan` behaelt `strict_beat_sync=True`. Beat-Alignment-Verlaesslichkeit und Referenz-Taktphase sind getrennte Flags; erkannte Taktunsicherheit ist kein Grund, Sync zu erzwingen oder eine Pruefung zu umgehen.
- Paar-Gates, Render-Validierung und Rekordbox-XML-Export behalten ihre bestehenden Sperren. Bei fehlender oder unsicherer Messung wird das Ergebnis als unbekannt/abgelehnt ausgewiesen; es wird nicht durch Scoring-Renormierung erfunden.
- Analysewert-Aenderungen erfordern einen gezielten Cache-Bump. Aktuell ist `CACHE_VERSION = 90`; Version 72 ermoeglicht die Audio-Novelty-Phrasenlaenge bei schwacher Phrase im bestaetigten Beatgrid. Version 73 persistiert deren Herkunft; Version 74 Rohkorrelation und Ranking-Abstand; Version 75 bindet sie im Diagnose-Schema v6 an den Cachevertrag; Version 76 korrigiert Genreprofil-Herkunft bei interner expliziter Weitergabe, ohne Messschema oder Mixverhalten zu aendern. Version 77 verlangt vor neuronaler Taktanker-Uebernahme dieselben drei nicht ueberlappenden Quellfenster fuer Model7 und Model8, jeweils audio-bestaetigt. Der persistierte Kandidat muss dem fruehesten bestaetigten Fenster entsprechen; aktive Konfidenz ist die niedrigste bestaetigte Fensterkonfidenz. Version 78 uebernimmt eine Rekordbox-Taktrotation nur, wenn alle sechs Modell-/Audiofenster und das abschliessende Gesamtgrid bestaetigt sind. Version 79 persistiert `reference_constant_offset`, wenn die Rekordbox-Taktpositionsdiagnose einen konstanten Grid-Offset erkennt. Version 80 ergänzt den versatzbereinigten Modell-/PQTZ-Taktpositionsvergleich. Version 81 erlaubt die Übernahme einer Taktrotation nur mit drei disjunkten Zusatzfenstern je Modell, separater Audiophasenbestätigung und verifiziertem Gesamtgrid; Rekordbox-Rohticks und Sync-Regeln bleiben unverändert. Version 82 vereinheitlicht die Phrase-Unit-Auflösung in Mixpunkten, Kandidatenraster und Playlist-Ketten: gemessene Novelty- und konfigurierte Einheiten gelten nur mit gültigem Wert; Genre-Prior, fehlende Herkunft und ungültige Werte verwenden das wirksame Genreprofil. `effective_track_phrase_unit` ist gemeinsame Quelle. Version 87 verwendet diese Phrase-Unit auch innerhalb der Mix-In/Out-Kandidatensuche und deren Intro-/Outro-Guards, nicht nur bei der abschliessenden Quantisierung. Version 88 verwendet den Median der sechs Tempoausgaben als Modellkandidat; DSP-Refinement und Gesamtgrid bleiben Übernahme-Gates. Version 89 persistiert Status, Grund, Modellmedian, Audioverfeinerung und Modellstreuung der Tempoentscheidung im Messschema v7. Version 90 erhält dazu die sechs Modell-BPM-Werte samt Modell-ID und Fensterstart; der Cachevertrag bindet Median und Spread an genau diese Einzelwerte und validiert übernommenes Tempo gegen die bestehende 2%-Grenze. Cache 85 erlaubt bei reiner `consistent_offset`-Phase ohne Bar-Rotation die Übernahme eines zeitkorrigierten Audioankers nur nach disjunkter Modell-/Audiophasenbestätigung und verifiziertem B-Gesamtgrid. Der neue Diagnoseweg ändert keine Rekordbox-Rohticks, Bar-Labels oder Sync-Gates; ohne Rotation bleibt die Bar-Position getrennt bewertet. Der korrigierte Anker ist Audioherkunft; Rekordbox-PSSI und Rekordbox-Render-Sync erhalten dadurch keine Freigabe. Er kann Beat-Alignment versorgen, aber keine Renderer-Taktphase freigeben; `strict_beat_sync` bleibt aktiv.
- Modellinferenz darf nicht den Qt-Hauptthread blockieren. Das konkrete sichere Einhaengen in den Prozess-/Worker-Lebenszyklus muss im Implementierungsdesign geprueft werden; die alte pauschale Alternative "ProcessPool oder QThread" ist kein fertiger Ausfuehrungsvertrag.
- Source-Audio bleibt read-only. Frische Analyse wird mit isoliertem externen Cache von Cache-Wiederverwendung getrennt nachgewiesen. Keine Produktivcache-Loeschung.

## 3. Takt-/Downbeat-Arbeit: Diagnose und Ziele

### 3.1 Belegstand dieser Planrevision

Ein isolierter, source-direct Holdout von 24 Tracks lief durch `analysis.analyze_track`: 24/24 lieferten Analyseobjekte, keine Analyse-Ausnahme; 23/24 gespeicherte Beatgrid-Vergleiche waren `mismatch`, 1/24 `verified`. 14/24 hatten audioeigene Downbeat-Konfidenz mindestens 0.30. Ein einziger Track hatte einen exakten Rekordbox-Pfad-Match; dessen Vergleichsbarkeit mit gleichem Tempo war vorhanden. Quellhashes und Produktivcaches blieben unveraendert, der Code war waehrenddessen unveraendert.

Dieser Lauf beweist **nicht**, dass 23 von 24 Takten musikalisch falsch sind: Der Validator prueft die Uebereinstimmung von BPM plus erster Phase mit der audioeigenen Fold-Messung in drei Fenstern; er ist keine unabhaengige musikalische Ground Truth. Ebenso beweist die Konfidenz >= 0.30 keine richtige Takt-"1". Der Lauf enthielt nur einen exakten RB-Pfadvergleich und kann die RB-Referenz daher nicht fuer 24 Tracks bewerten.

Vorherige Fresh30-/synthetische Diagnosen zeigten getrennte Ursachen: Tracker-Tempo inkommensurabel, schwaches Bar-Voting und schwacher Fold-Lock. Ein expliziter BPM-Retry allein hob bei synthetischem Fehltempo Confidence an, bestand aber die bestehende Mehrfensterpruefung nicht; daher muessen beide Gates erhalten bleiben. Diese historischen Messungen muessen vor spaeterer Implementierung anhand der referenzierten Rohbelege und Hashes wiederverwendet oder bei geaendertem Code gezielt erneuert werden.

### 3.2 Erforderliche Analyse- und Produktverbesserungen

1. **Fehlerursachen messbar trennen:** BPM-/Beatintervall-Mismatch, Beatphasenfehler, Bar-Vote-Ambiguitaet, Fold-Lock-Schwund, zu wenige Beats/Fenster, Decode-/Coverage-Fehler, RB-Mehrdeutigkeit und PSSI-/ANLZ-Lesefehler erhalten getrennte Status-/Diagnosefelder mit Messwert, Quelle und betroffenen Fenstern.
2. **Unabhaengige Referenzkohorten:** Fuer jede Evaluation Quelldateiidentitaet/Fingerprint, Genre/Tempo-Klasse, exakte Rekordbox-Pfadzuordnung, Analysemodus und Code-/Testhash festhalten. Mehrdeutige Basenames nicht als Ground Truth zaehlen. Tracks ohne unabhaengige Taktlabelung getrennt berichten.
3. **Taktphase gegen Kickphase validieren:** Getrennte Metriken fuer Beat-/Kick-Ausrichtung und Bar-"1"-Klassifikation. Erforderlich sind mehrere Genres/Produktionen und manuelle oder anderweitig unabhaengige Referenzen; Rekordbox allein ist eine zu pruefende Referenz und kein ungeprueftes Orakel.
4. **Keine Gate-Aenderung:** Vorher-/Nachher-Regressionen muessen die bestehende Confidence-Grenze, drei getrennte Fenster, 6-ms-Grenze, Tempo-/Gridpruefung, Pair-Rejection und Renderer-Strict-Sync explizit sichern. Abgelehnte Kandidaten bleiben abgelehnt.
5. **Nur begrenzte Wiederherstellung:** Ein Retry ist nur fuer klar diagnostizierte Ursachen zulaessig. Kandidatenuebernahme erfordert unabhaengige Kandidatenpruefung im gesamten Track/Fenstervertrag; ein hohes internes Voting allein genuegt nicht. BPM-Tags, modellconfidence und Transformationstabilitaet sind keine Ground Truth.
6. **Erklaerbare Nutzeranzeige:** Statt eines einzelnen "Taktanfang unsicher" werden Hauptursache, Messbeleg und Konsequenz angezeigt, zum Beispiel: "Beatphase stabil, Takt-1 unklar; keine Phrasenquantisierung" oder "Tempo-Raster widerspricht Audio; Uebergang gesperrt". Anzeige muss Daten aus persistierten Diagnosen beziehen und Unbekanntes explizit so nennen.
7. **End-to-end Konsistenz:** Analyseanker -> phrase_anchor/Struktur -> Mixpunktkandidaten -> Paarplan -> Render-Clip muessen denselben gemessenen Vertrag verwenden. Der Plan wird nicht als geloest markiert, bis Originaltracks frisch analysiert, Playlist und Paare in der App bewertet, betroffene Uebergaenge gerendert und in der App abspielbar sind.

## 4. Urspruengliche Deep-Analysis-Anforderungen, vollstaendig erhalten und neu geordnet

### Phase A — Lokale Rekordbox-Analyse untersuchen und Integrationsschnittstellen festlegen

> Belegstatus: Die folgenden technischen Ausgangsangaben unterliegen Abschnitt 0.
> Die Kennzeichnung „verifiziert“ ersetzt keinen zugeordneten und geprüften Rohbeleg.

Rekordbox und die mitgelieferte Analyse sind die primaere Forschungs- und Integrationsquelle dieses privaten HPG-Projekts. Diese Phase bestimmt den konkreten technischen Anschluss; sie ist kein Rechte- oder No-Go-Gate.

- Jede urspruenglich aufgefuehrte Komponente (Demucs3/Spleeter/DirectML/ONNX Runtime, `detect_beat/model7`/`model8`, `samplecnn.onnx`, `cue_prediction_model_no_abs_position.onnx`, `cnn_embedding.onnx`, `model_energy.onnx`, `model_genre.onnx`, `umap_embedder.onnx`) lokal auffinden und Version, Format, Inputs/Outputs, Runtime, Aufrufbarkeit, Ressourcenbedarf und Kopplung untersuchen.
- **Verifizierte Stem C-ABI Schnittstellen (PE32+ Export-Tabelle):**
  - `Demucs3.dll`: Saubere ungemangelte C-Exportfunktionen:
    `demucs3Initialize`, `demucs3Finalize`, `demucs3IsInitialized`, `demucs3PreOperation`, `demucs3PostOperation`, `demucs3CancelOperation`, `demucs3OperationAtIndexOtherWithBass`, `demucs3OperationAtIndexSeparatedBass`, `demucs3OperationAtOnceOtherWithBass`, `demucs3OperationAtOnceSeparatedBass`. Diese koennen direkt via Python `ctypes` oder `cffi` angebunden werden!
  - `Spleeter.dll`: Analoge C-Exportfunktionen: `spleeterInitialize`, `spleeterFinalize`, `spleeterIsInitialized`, `spleeterPreOperation`, `spleeterPostOperation`, `spleeterCancelOperation`, `spleeterOperationAtIndexOtherWithBass`, `spleeterOperationAtIndexSeparatedBass`, `spleeterOperationAtOnceOtherWithBass`, `spleeterOperationAtOnceSeparatedBass` (sowie interne `TFWrapper`-Klassen).
- **Verifizierte ONNX Graph- & Tensor-Signaturen (Protobuf Wire-Inspektion):**
  - `samplecnn.onnx`: Input `waveform` mit Form `['batch_size', 59049]` (59049 Samples = exakt $3^{10}$ Samples, die klassische SampleCNN-Fenstergroesse bei 22050 Hz = ca. 2,67 s Roh-Audio!); Outputs `tags` `['batch_size', 50]` und `features` `['batch_size', 512]`.
  - `cue_prediction_model_no_abs_position.onnx`: Input `input`, Output `variable` mit Form `[1]`.
  - `cnn_embedding.onnx`: Input `signal` `['channels', 'samples']` plus STFT-Parameter `frame_step` `[1]`, `frame_length` `[1]`, `pads` `[4]`; Outputs `output` `['Sigmoidoutput_dim_0', 50]` und `features` (Reshape).
  - `model_energy.onnx`: Input `input_features` `[64]`; Output `danceability` `[1]`.
  - `model_genre.onnx`: Input `input_features` `[66]`; Outputs `output_label` und `output_probability`.
  - `umap_embedder.onnx`: Input `input_1` `['unk__6', 64]`; Output `dense_6` `['unk__7', 2]` (2D-Projektionskoordinaten).
  - `norm_before_umap.onnx` / `norm_after_umap.onnx`: Feature-Normalisierung fuer 64 bzw. 2 Dimensionen.
- **Verifizierte TensorFlow SavedModel Beatgrid-Signaturen (Protobuf MetaGraphDef):**
  - `models/detect_beat/model7` & `model8`: Signatur `serving_default` mit Methode `tensorflow/serving/predict`.
    - Input: `fltp` (Name: `serving_default_fltp:0`, Floating-Point Audio PCM Signal).
    - Outputs: `output_1` (Name: `StatefulPartitionedCall:0`, Onset-/Beat-Aktivierungsfunktion) und `output_2` (Name: `StatefulPartitionedCall:1`, Downbeat-/Takt-Aktivierungsfunktion). Beide Modelle koennen via `tf.saved_model.load()` oder `tensorflow_cc.dll` C-API direkt inferiert werden.
- `onnxruntime-directml` unter Python 3.12 und `DmlExecutionProvider` praktisch pruefen; CPU-Fallback separat testen. Bei Nicht-ONNX-Modellen die tatsaechliche Runtime und sichere Prozessgrenze untersuchen. GPU-/Provider-Ergebnisse als echte Laufzeitbeobachtung festhalten.
- Pro Modell Inputs, Tensorformen, Sampling/Resampling, Normalisierung, Outputs, Einheiten, Zeitbezug, Ressourcenbedarf und Fallback spezifizieren. Kein Platzhaltermodul als integriert deklarieren.

### Phase B — Gemeinsame Inferenzlaufzeit und zwei Analysepfade

- Auf Basis der in Phase A gefundenen Rekordbox-Analysepipeline die Laufzeit unter `hpg_core/ai_models/` entwerfen und integrieren. Fuer ONNX Providerordnung: DirectML, sofern vorhanden und nachgewiesen, danach CPU. Modelle mit anderer Runtime bekommen den passenden Adapter. Beim Modellfehler bleibt die bestehende Librosa/DSP-Auswertung crashfrei verfuegbar; die Rekordbox-Integration bleibt dabei weiterhin Ziel und Fehlerursache/fehlende Zusatzmerkmale werden sichtbar protokolliert.
- Thread-/Prozesssicherheit, Model-Lifecycle, ParallelAnalyzer-Worker, RAM-/GPU-Grenzen, Cancellation/Timeout, Modellversion und Diagnostik spezifizieren. Kein Qt-Hauptthread-Block.
- Inputs fuer Waveform/Spektrogramm dokumentieren: Mono/Mehrkanal, Sample-Rate/Resampling, Normierung, Ausschnitt-/Tail-Abdeckung, Tensorformen und Einheiten. Fensterluecken duerfen nie interpoliert/versteckt werden.
- Fast-Path (Rekordbox-Metadaten zuerst) und Vollpfad (Librosa) muenden in einen gemeinsamen, testbaren Track-Vertrag. Ein Modell darf RB-Quelle nicht ungeprueft ueberstimmen; Diskrepanzen bleiben sichtbar.
- Bei neuen persistierten Track-Feldern: Model-Sentinels, `TRACK_REQUIRED_FIELDS`, Listen-/Dict-Validierung, JSON roundtrip, Cache-Bump und Altcache-Verhalten spezifizieren. Kein fixer Zielwert 53 vor konkretem Vertrag.

### Phase C — Neuronale Beatgrid-, Downbeat-, Phrasen- und Cue-Erkennung

- Beatgridmodell und Cue/Phrasenmodell getrennt spezifizieren und messen; ein Struktur-Cue-Modell ist nicht automatisch ein Beatgridmodell.
- Segment-/Grenzwahrscheinlichkeiten mit Zeitstempeln/Sekunden, Labeldefinition, Konfidenzkalibrierung und Unsicherheitsausgabe definieren. Intro-Ende, Breakdown, Drop und Outro-Beginn brauchen getrennte Label- und Referenzvertraege.
- PSSI-ANLZ bleibt nur dann Referenzquelle, wenn Pfad/Content-ID/Tag-Mapping eindeutig und die zugrundeliegenden Beatpunkte geprueft sind. PSSI wird nicht als universelle Ground Truth und nicht bei nicht verifiziertem Grid als gesicherte Phrase markiert.
- Modell gegen unabhaengig gelabelte Referenzen sowie aktuelle audioeigene Baseline messen: Downbeat-Fehler in ms/Beats, Beat-F1/Continuity, Bar-Phase accuracy, Phrase-boundary F1/zeitlicher Fehler und Coverage. Vorab Datenpartition und Mindestwerte registrieren; Trainings-/Tuningtracks vom Holdout trennen.
- Abweichung RB vs. Modell vs. Audio behalten, nicht mittels confidence max()/Mittelwert verstecken. Nur ein explizit definierter und getesteter Arbitration-Vertrag darf einen Downbeat-/Phrase-Anchor an Konsumenten geben.

### Phase D — Stem-Analyse, lokale Uebergangsmerkmale und Bass-Swap

- Vocal/Bass/Drum-Kurven wie urspruenglich gefordert implementieren (z. B. 1-s- oder taktweise Kurven), nachdem die Modelle lokal eingebunden und CPU-/DirectML-Lauf sowie Datenabdeckung praktisch gemessen wurden. Pro Kurve Modell, Zeitraster, Skala, Kalibrierung, None-/Fehlerzustand und Latenz dokumentieren.
- Lokale Energie darf nicht mit globalem Trackmittel ersetzt werden. Mix-Out-Audio von Track A und Mix-In-Audio von B werden auf die konkrete Paar-/Kandidatenzeit abgebildet.
- Vocal Gate aus Originalplan (gleichzeitiges `vocal_energy > 0.4`) als **zu validierende Hypothese** behalten: Schwelle/Fenster gegen manuelle Ueberlagerungsurteile und false-reject/false-accept bewerten. Bis dahin keine harte Sperre und keine Gleichsetzung mit dem bestehenden groben `vocal_instrumental`-Label. Unbekannte Vocals allein sperren kein Paar.
- Bass-Swap als Ereignis-/Zeitintervall definieren und auf Takt-/Beatgrenzen abbilden; "exakter Downbeat, an dem Bass A stoppt und B beginnt" ist nur behauptbar, wenn beide lokalen Stem-Signale das Ereignis mit quantifiziertem Zeitfehler tragen. Vorher Empfehlung/Flag statt garantierter Tatsache.
- Scoring, harte Gates und Mixpoint-Auswahl getrennt halten. Modellscore kann bestehende Synchron-/Coverage-/Intro-/Outro-/Phrasengates nicht ueberstimmen.

### Phase E — Audio-Embedding und Klangkompatibilitaet

- `cnn_embedding.onnx`/UMAP-Anforderung aus dem Originalplan bleibt erhalten; Modell, Input und Zweck werden an der lokalen Rekordbox-Installation untersucht und reproduzierbar charakterisiert. UMAP-Projektion ist Visualisierung/Geometrie, nicht automatisch ein kompatibler Score.
- Embeddings pro Track oder lokalem Kandidatenfenster definieren, normalisieren und im Cache versioniert speichern. Vergleich nur mit Kosinusmass fuer normalisierte Vektoren; fehlende/ungueltige Vektoren nicht als Distanz 0 ausgeben.
- Zusaetzlichen Klangfarbenfaktor in `pair_candidates` nur nach abgetrennter Holdout-Evaluation, Korrelation/Redundanzpruefung gegen aktuelle Timbre-/Mood-Scores sowie blindem Hoertest aktivieren. Gewicht als Startwert markieren und ein-/ausschaltbare Ablation behalten.
- Keine Aenderung der acht Playlist-Strategien, Strategieziele oder GUI ausserhalb des angeforderten Analyse-/Scoring-Vertrags ohne eigenen Akzeptanzpunkt.

### Phase F — Produktintegration und Nutzerworkflow

- Analysequelle/Status/Confidence/Abdeckung und Abweichungen in Library-/Playlist-Diagnosen verstaendlich ausgeben. "Rekordbox" bedeutet Herkunft, nicht automatisch bestaetigte Korrektheit.
- Paarbewertung erklaert Track-Passung, Technik/Synchronitaet und Gesamtwirkung getrennt. Abgelehnte Uebergaenge bleiben sichtbar mit konkretem Grund und werden nicht gerendert.
- Vor jedem Preview-Render Renderbarkeit sicherstellen. Ein groesserer Hoertestsatz wird nur aus erfolgreich gerenderten, vollstaendigen und abspielbaren Varianten publiziert; keine Synchronpruefung lockern und Originalaudio nicht in einen persistenten Hoertestdatensatz kopieren.
- Vollstaendiger nativer Nachweis: Originaltracks am Quellort auswaehlen, isoliert frisch analysieren, Paare bewerten, Playlist erzeugen, betroffene Uebergaenge in der App rendern/abspielen und Ergebnis anwenden/exportieren. Cache-Reuse separat pruefen. Menschliche Klangbeurteilung separat ausweisen.

## 5. Umsetzungsetappen und Abnahmetore

1. **TOR 0 – Bestand und Referenzdaten:** Manifest/Kohorten/Rohbelege/Hashes wiederverwenden; unabhaengige Takt-/Kick-/Phrasenlabels und Modellrechte klaeren. Ohne Referenzdaten nur Fehlerursachen und technische Konsistenz, keine Accuracy-Freigabe.
2. **TOR 1 – Pruefvertrag und unabh. Waechter:** Akzeptanzkriterien, Invarianten, exakt erlaubte Dateien, Regressionen und Modellquellen fuer diesen konkreten Patch; read-only Urteil vor Produktcode.
3. **TOR 2 – Kleine technische Scheiben:** Je Ursache/Modell enger RED/GREEN-Test, dann beide Analysepfade, Cache roundtrip, Paar-/Mixpoint- und Renderer-No-loosening-Tests. Keine parallelen vollen pytest-Laeufe; fuer Schlussbeleg Projekt-Volltest nach `AGENTS.md`.
4. **TOR 3 – Isolierte Multi-Genre-Holdouts:** Frische Analyse gegen unabhaengige Ground Truth, mit getrenntem Resultat fuer Audio-only und exakte RB-Zuordnung. Vorher festgelegte Genauigkeits-/Coverage-/Laufzeit-/Ressourcenwerte. Keine Kalibrierung auf Holdout.
5. **TOR 4 – Native App und abspielbarer Hoersatz:** Quelltrackfluss bis zu Preview-Wiedergabe in der tatsaechlichen App belegen. Renderfehler nach Grund klassifizieren; nur erfolgreich komplett gerenderte Varianten aufnehmen. Bewertungen bleiben menschliche musikalische Evidenz.
6. **TOR 5 – Doku/Cache/Release:** Skills und Projektwissen aktualisieren; Cache-Bump nur nach tatsaechlichem persistiertem Vertragswechsel. Unveraenderte/ungueltige Kandidaten weiter fail-closed. Build/EXE erst nach funktionalen Nachweisen; exakter EXE-Pfad und SHA-256 separat belegen.
7. **TOR 6 – Unabhaengige Abschlusspruefung:** Waechter prueft exakten Diff und Nachweise. Status je Punkt: implementiert, automatisch getestet, mit frischen Originaltracks nativ geprueft, musikalisch bewertet. Kein pauschales "alles geloest".

## 6. Anforderungsinventar aus der urspruenglichen Spezifikation

Kein Punkt der alten Spezifikation wird still verworfen:

| Alte Anforderung | Zielabschnitt |
|---|---|
| AMD/DirectML ohne CUDA; CPU-Fallback | 1, Phase A/B |
| Rekordbox-Fast-Path und Librosa-Vollpfad konsistent | 2, Phase B |
| 360-s/600-s Head und 180-s Tail, Outro-Coverage | 2, Phase B; vorhandene Fensterregeln bleiben erhalten |
| Track-Felder Stem Vocal/Bass, neurale Phrasen und Embedding | Phase B/D/E mit Sentinels/Validierung/Cachevertrag |
| DirectML ONNX Engine, thread-safe Batch | Phase A/B mit Worker-, Timeout- und Lifecycle-Nachweis |
| SampleCNN und Cue-Prediction, Resampling und Grenzzeiten | Phase C |
| Vocal-Kollision >0.4 | Phase D, bis Validierung Hypothese statt Gate |
| Bass-Swap am Downbeat | Phase D, Ereignis mit Messunsicherheit |
| CNN-Embedding / Kosinus-Score | Phase E |
| `analysis.py`, `structure_analyzer.py`, `downbeat.py`, `dj_brain.py`, `pair_candidates.py`, `models.py`, `caching.py`, `rekordbox_importer.py`, Requirements | jeweilige Phasen; exakte Patchdateien nach TOR 1 festzulegen |
| Kein Qt-Hauptthread, Genre-SSoT schuetzen, HPG-001/Mixpoint-Vertrag | 2, B, F; `main.py` nur bei gesondertem GUI-Akzeptanzpunkt |
| CACHE_VERSION 53 | ersetzt durch bedingte Regel: naechste Version erst bei nachgewiesenem Cachevertrag festlegen |

## 7. Historischer Code-Abgleich dieses Plans (13.10.2026)

Die folgende Tabelle hält den damaligen Abgleich fest und ist kein aktueller
Code- oder Laufzeitstatus. Neuere Scheiben und offene Punkte stehen in der
Ausführungsmatrix weiter oben. "Vorhanden" hiess Teilfunktion existiert, nicht
dass die umfassende Plananforderung erfüllt war.

| Punkt | Codebeleg / Beobachtung | Status gegen integrierten Plan |
|---|---|---|
| Rekordbox-Metadaten-Fast-Path | `hpg_core/analysis.py` `analyze_track`; `hpg_core/rekordbox_importer.py` | Vorhanden |
| Audio-Vollpfad | `analysis.py` sammelt Beatfenster, `cue_service.py` fuehrt model7/model8 aus, `_resolve_track_anchor` arbitriert sie vor dem gemeinsamen Structure-/Mixpoint-Ablauf | Beatmodell-Kandidaten sind integriert; musikalische Genauigkeit und native Laufzeitabnahme offen |
| ANLZ/PQTZ/beat==1 | `rekordbox_importer.py` `get_beatgrid`, `_extract_beatgrid_from_anlz` | Vorhanden; externe Ground-Truth-Qualitaet nicht bewiesen |
| PSSI-Phrasen | `rekordbox_phrases.py`; Import nur bei verifiziertem Rekordbox-Grid. `cue_predictor.py` wertet bereitgestellte Kandidaten aus, erzeugt keine Grenzen | Teilweise; keine unabhaengige Phrase-Qualitaetsmessung |
| Tempo-/Downbeat-Retry | `tempo_refinement.py`, `downbeat.py`, `analysis.py` (Dateien/Tests teils dirty oder untracked im aktuellen Worktree) | Vorhandene aktuelle Arbeit; laut aktivem Holdout weiterhin hohe Ablehnungsrate, kein Accuracy-Nachweis |
| 24-Track Holdout | Externes `Independent24-current` Resultat: 24/24 Analyseobjekte, 23 mismatch, 1 verified, 14 confidence >= .30, 1 exakter RB-Pfadvergleich; Quellen/Produktivcache/Code unveraendert | Laufnachweis nur fuer technische Pipeline; nicht Ground Truth oder musikalische Abnahme |
| Vollstaendige Fehlerursachenanzeige | Diagnosefelder fuer Downbeat/Grid existieren; GUI- und Nutzererklaerungsabgleich nicht vollstaendig in diesem Read-only Planvergleich | Teilweise/unabgeglichen |
| Beatphase vs. Taktphase | getrennte Diagnose-/Rendererflags und strengere Bar-Reliability erkennbar | Teilweise; kohortenweite Bar-1-Referenzmessung offen |
| Strict beat sync / Drei-Fenster / 6 ms | in `downbeat.py` und `transition_renderer.py` gefunden; drei Fenster, max 6 ms, `strict_beat_sync=True` | Vorhandener Vertrag; muss gegen jeden kuenftigen Diff regressionsgesichert bleiben |
| Stem-Modell / `stem_analyzer.py` | `hpg_core/stem_analyzer.py` fehlt | Offen |
| ONNX/DirectML-Laufzeit | `hpg_core/ai_models/onnx_engine.py` implementiert DirectML/CPU-Auswahl und Fallback; die Live-Ausfuehrung ist mit diesem Quellstand nicht belegt | Code vorhanden; Provider- und Hardwarelauf offen |
| SampleCNN / Cue-Phrase Modell | `cue_predictor.py`/`cue_service.py` und `structure_analyzer.py` werten Kandidaten aus; der Predictor erzeugt keine neuen Phrasengrenzen | Teilweise; Modellnutzen und unabhaengige Qualitaet offen |
| Audio-Embeddings | `embedding_predictor.py` vorhanden; ein gespeichertes `Track.audio_embedding`-Feld bzw. vollstaendige Analyse-/Cache-/Scoring-Pipeline ist hier nicht belegt | Teilweise; Ende-zu-Ende-Integration offen |
| Vocal gate >0.4 | keine Stem-Zeitkurve/Schwelle in Paar-Gates; bestehendes `vocal_instrumental` ist grobes Tracklabel | Offen; Schwelle nicht validiert |
| Bass-Swap-Zeitereignis | aktuelle lokale Bass-/Kick-Merkmale vorhanden, aber kein aus Stem-Zeitkurven belegter exakter Swap-Zeitpunkt | Offen |
| Cache-Regel | `hpg_core/caching.py` deklariert aktuell `CACHE_VERSION = 90`; Track- und Messdiagnosen enthalten Phrase-Unit-Provenienz. Stem-/Embedding-Felder sind damit nicht automatisch integriert | Cache-/Diagnosevertrag vorhanden; Stem-/Embedding-Integration offen |
| Voller nativer Fresh-analysis-to-playback Nachweis fuer den Plan | In diesem Turn nicht ausgefuehrt | Offen |
| EXE-Build / EXE-Lauf | absichtlich nicht Teil dieser Planaenderung | Zurueckgestellt bis funktionale Tore bestanden |

### Konkrete Reihenfolge der naechsten technischen Arbeit

Fortsetzungsstand 15.10.2026 nach ungeplantem Neustart. Die bisherige Reihenfolge
in diesem Absatz stammte aus dem historischen Planvergleich. Sie darf die bereits
angebundene Modelllaufzeit nicht erneut hinter eine allgemeine Holdout-Diagnose
stellen. Vorhandene Änderungen bewahren; kein Neustart der Implementierung.

1. Die vorhandene gemeinsame Modellanbindung weiterführen. `cue_service.py`
   enthält Cue- und Beat-Aufträge, einen seriellen Broker, Generation-Abbruch,
   Deadlines und einen isolierten Modellprozess. Das ist ein gelesener
   Codebefund, kein aktueller Laufzeitnachweis. Fehlende Funktionsnachweise
   anhand der konkreten Integrationsstelle bearbeiten, sobald deren Ausführung
   vom geltenden Nutzerauftrag gedeckt ist; keine pauschalen Wiederholungsläufe.
2. Die offene Phrasenanforderung ausdrücklich erhalten: `cue_predictor.py`
   bewertet bereits vorhandene PSSI-Kandidaten mit `start_s`, `kind` und `mood`.
   Sein Rohscore erzeugt keine neuen Grenzen oder Strukturklassen und ist keine
   kalibrierte Wahrscheinlichkeit. Die Novelty-basierte Struktur in
   `structure_analyzer.py` schließt deshalb nicht automatisch die neuronale
   Phrasenanforderung. Für deren Umsetzung fehlt ein belegter Vertrag für
   Grenzerzeugung und Labels; keine Klassen oder Modellbedeutungen erfinden.
3. Die angeschlossenen Analyse-, Cache-, Playlist- und Hörprobenverträge anhand
   der nächsten konkreten fehlenden Anforderung vervollständigen. Vor einer
   weiteren Änderung vorhandenen Code und zugehörige Belege verwenden; reine
   Statusmeldungen und Neustarts begründen keine Neuanalyse oder Cache-Erhöhung.
4. Technische Funktionsnachweise und musikalische Abnahme getrennt behandeln.
   Unabhängige Takt-1-/Phrasenlabels fehlen weiterhin. Das verhindert eine
   belegte Qualitätszusage oder Confidence-Kalibrierung, nicht sämtliche
   weiteren Implementierungsarbeiten. Rekordbox-Grids sind keine unabhängige
   musikalische Ground Truth. Holdout-Zuordnung und Fehlerexport bleiben
   Aufgaben der späteren Evaluation, keine pauschale Vorbedingung jeder Änderung.
5. Stems und Embeddings bleiben gemäß Nutzerpriorisierung zurückgestellt,
   solange keine notwendige Abhängigkeit der priorisierten Analyse belegt ist.
   Native Originaltrack-Abnahme und EXE-Freigabe bleiben offen; alle noch
   ungeprüften Änderungen bleiben als unvalidiert gekennzeichnet.

### 7.1 Lückenlose Abhängigkeiten-Matrix (Python 3.12 / venv312)

> Vorläufige Ausgangsmatrix: Kompatibilität und Provider-Ausführung sind gemäß
> Abschnitt 0 separat zu prüfen; hieraus keine Installation in die Produkt-venv ableiten.

Vor Implementierung müssen die zusätzlichen Pakete mit festen Versionen in `requirements.txt` bzw. einer `requirements-ai.txt` definiert sein, ohne bestehende Pins (`numpy==1.26.4`, `numba==0.67.0`, `librosa==0.11.0`) zu brechen:

| Komponente | Benötigtes Paket | Getestete / Erforderliche Version | Zweck & Besonderheiten |
|---|---|---|---|
| **ONNX Runtime (DirectML)** | `onnxruntime-directml` | `>=1.19.0, <=1.21.0` | GPU-Inferenz für AMD Radeon RX 7800 XT via DirectX 12. Funktioniert mit `numpy==1.26.4`. |
| **ONNX Spezifikation** | `onnx` | `>=1.16.0` | Validierung der `.onnx`-Modelle & Shape-Inferenz (optional zur Entwicklungszeit). |
| **Audio-Resampling** | `soxr` oder `samplerate` | (bereits via `librosa`) | Schnelles Resampling auf 22.050 Hz für `samplecnn.onnx`. |
| **C-ABI Bindings** | `ctypes` (Standardbibliothek) | Python 3.12 Built-in | Aufruf von `Demucs3.dll` und `Spleeter.dll` C-Exportfunktionen ohne externe Compiler. |
| **TensorFlow SavedModel** | `tensorflow` (Optional/Headless) | `>=2.16.0, <2.17.0` (oder C-API über `tensorflow_cc.dll`) | Für `model7`/`model8` SavedModel Inferenz unter CPU/DirectML. |
| **Array-Kompatibilität** | `numpy==1.26.4` | **Gesperrt / Fester Pin** | Darf keinesfalls auf NumPy 2.x aktualisiert werden, da `numba==0.67.0` und `librosa` sonst brechen. |

## 8. Konkrete Implementierungs-Beispiele (Referenz-Code für Agenten)

> Unvalidierte Beispiele, keine freigegebenen Aufrufvorlagen. Vor Ausführung gelten
> die ABI-, Vorverarbeitungs- und Semantikprüfungen aus Abschnitt 0.

### Beispiel 1: Demucs3 C-ABI Aufruf via `ctypes` (Stems)
```python
import ctypes
import numpy as np

# Demucs3.dll direkt laden
demucs = ctypes.CDLL(r"C:\Program Files\rekordbox\rekordbox 7.2.19\Demucs3.dll")

# Signaturen definieren
demucs.demucs3Initialize.argtypes = []
demucs.demucs3Initialize.restype = ctypes.c_int

demucs.demucs3IsInitialized.argtypes = []
demucs.demucs3IsInitialized.restype = ctypes.c_bool

demucs.demucs3Finalize.argtypes = []
demucs.demucs3Finalize.restype = ctypes.c_int

# Initialisieren
if not demucs.demucs3IsInitialized():
    status = demucs.demucs3Initialize()
    assert status == 0, f"Demucs init failed with code {status}"
```

### Beispiel 2: DirectML ONNX Inferenz für SampleCNN (Phrasen)
```python
import onnxruntime as ort
import numpy as np
import librosa

# DirectML Session für AMD Radeon RX 7800 XT aufbauen
providers = [
    ("DmlExecutionProvider", {"device_id": 0}),
    "CPUExecutionProvider"
]
session = ort.InferenceSession(
    r"C:\Program Files\rekordbox\rekordbox 7.2.19\models\detect_cue_model\samplecnn.onnx",
    providers=providers
)

# Audio laden & auf 22.050 Hz / 59.049 Samples (ca. 2.67s) bringen
# y, _ = librosa.load("track.wav", sr=22050, mono=True)
chunk = np.zeros((1, 59049), dtype=np.float32) # batch_size=1, samples=59049

# Inferenz ausführen
outputs = session.run(["tags", "features"], {"waveform": chunk})
tags_prob, latent_features = outputs[0], outputs[1]
# tags_prob hat Shape (1, 50), latent_features hat Shape (1, 512)
```

### Beispiel 3: TensorFlow SavedModel Beatgrid-Inferenz (`model7` / `model8`)
```python
import tensorflow as tf
import numpy as np

# Modell laden (SavedModel Format)
beat_model = tf.saved_model.load(
    r"C:\Program Files\rekordbox\rekordbox 7.2.19\models\detect_beat\model7"
)
infer = beat_model.signatures["serving_default"]

# Audio PCM Signal übergeben (Tensor Name: fltp)
audio_input = tf.convert_to_tensor(np.zeros((1, 44100 * 10), dtype=np.float32), dtype=tf.float32)

# Outputs abrufen: output_1 = Beat/Onset Aktivierung, output_2 = Downbeat Takt-1 Aktivierung
res = infer(fltp=audio_input)
beat_activation = res["output_1"].numpy()
downbeat_activation = res["output_2"].numpy()
```

## 9. Verbindliche Definition von "erledigt"

Das Ziel "Taktproblem behoben" ist erst erreicht, wenn unabhaengige Mehrgenre-Ground-Truth eine vorab festgelegte Genauigkeit fuer Beatphase UND Bar-/Taktphase belegt, Wiederholungsanalyse und Cache getrennt stimmen, beide Analysepfade denselben Vertrag halten, Pairing/Render/Preview in der nativen App mit frischen Quelltracks vollstaendig nachgewiesen sind und kein striktes Gate gelockert wurde. Die ONNX-, Phrase-, Stem-, Bass-Swap- und Embedding-Anforderungen aus dem Ursprungsplan brauchen zusaetzlich jeweils eigenen technischen Integrations-, Daten-, Regression- und Nutzenbeleg. EXE bleibt danach ein separater Build-/Pfad-/SHA-256-Nachweis.

## Implementierungsdelta 15.10.2026 — Rotationsbestätigung isoliert, unvalidiert

Bei einem zunächst verifizierten Rekordbox-Grid wurden Taktrotations-Kandidaten
zuvor mit Modell- und Audiobelegen aus denselben Quellfenstern bestätigt. Das
Gegenüberstellen verschiedener Verfahren machte diese Fenster nicht unabhängig.
`analysis.py` wählt nun drei zusätzliche Fenster außerhalb sowohl der drei
Referenz- als auch der drei Modellkandidatenfenster. Beide Modelle und die
Audio-Downbeat-Prüfung müssen sie bestätigen; ein getrenntes Gesamtgrid bleibt
Pflicht. Überlappende Ausschlussfenster werden vereinigt. Fehlen disjunkte
Fenster, bleibt der Rekordbox-Anker aktiv. Das gilt zusätzlich zum bereits
isolierten Zeitversatzpfad. `CACHE_VERSION` steigt auf 91, damit alte
Anchor-Ergebnisse
nicht wiederverwendet werden. Rekordbox-Rohticks und Sync-Gates bleiben gleich.
Auf Nutzeranweisung wurden keine Tests oder Laufzeitprüfungen ausgeführt; diese
Änderung ist implementiert, aber unvalidiert.

## Implementierungsdelta 15.10.2026 — Begrenztes Cue-Batching, ungetestet

Phase B: `cue_predictor.py` verarbeitet bis zu vier gültige PSSI-Kandidaten
gemeinsam. Ein Batch enthält höchstens 24 SampleCNN-Fenster mit je 59049
Samples. Die sechs chronologischen Merkmalsfenster eines Kandidaten bleiben
zusammen; danach erhält der Cue-Regressor bis zu vier Zeilen mit je 3085
Spalten. Reihenfolge, Onehot-Kategorien und kandidatenbezogene Coverage
bleiben erhalten. Ein fehlgeschlagener Batch liefert für seine Kandidaten
`model_error`; es gibt keine automatische Einzelwiederholung.

Die Vorverarbeitungskennung ist `hpg-cue-22050-librosa-soxr-hq-floor-batch4-v2`.
Der vorhandene Modell-Fingerprint verwendet diese Kennung. Kein neues
Trackfeld und keine vorsorgliche globale Cache-Version wurden hinzugefügt.
Dies ist eine Implementierung der begrenzten Batch-Inferenz, kein Nachweis
höherer Geschwindigkeit oder unveränderter numerischer Ergebnisse.

Für die gebündelte Testsession nach dem Bau: Einzel- und Vierer-Batches
auf CPU/DirectML vergleichen, Restbatch und Duplikate abdecken, Reihenfolge,
Padding/Coverage und isolierte Fehlerausgabe prüfen sowie den geänderten
Fingerprint im Analyse-/Cachefluss nachweisen. In dieser Scheibe wurde kein
Test, Import-Smoke, Modelllauf oder Audioablauf gestartet.

Offene Phrasenschnittstelle: Die REA-Anbindung konnte das lokale Rekordbox-EXE
öffnen, aber keine String-/Disassembleranalyse anbieten: Ghidra und IDA waren
für diesen Anbieter nicht konfiguriert. Es wurde keine Toolinstallation
gestartet. Dieser Werkzeugbefund beweist nicht, dass der Phrasengenerator
fehlt; dessen belegter Aufrufvertrag bleibt offen.

## Implementierungsdelta 15.10.2026 — RAM-Budget der Modelllaufzeit, ungetestet

Phase B: Der gemeinsame Cue-/Beat-Prozess erhält vor dem GO-Handshake ein
Windows-Job-Limit für zugesicherten Speicher. Das konfigurierbare Startbudget
`MODEL_PROCESS_MEMORY_LIMIT_BYTES` beträgt 4 GiB. Es ist keine Messung des
Bedarfs und kein VRAM-Limit. Der vorhandene Kill-on-close-Vertrag bleibt aktiv.
Andere Aufrufer von `OwnedModelProcess` behalten ohne explizites Budget ihren
bisherigen Vertrag. Ungültige Bytewerte werden vor dem Prozessstart abgewiesen.
Der Analyse-Modellfingerprint enthält das Budget, weil eine Budgetänderung
den Erfolg der Zusatzanalyse beeinflussen kann. Scheitert die Job-Einrichtung,
wird kein Modellauftrag freigegeben; bestehende Fehler-/DSP-Fallbacks bleiben
zuständig. Eine Speicherüberschreitung ist bislang nicht gesondert von anderen
Modell- oder Prozessfehlern klassifiziert.

Abschließende Testsession: Job-Zuweisung vor Modellimport, tatsächliche
Speicherbegrenzung, Cleanup bei Überschreitung, DSP-Fallback und Fingerprint-
Invalidierung nachweisen. Keine Tests oder Modellläufe in dieser Scheibe.

Phrasenschnittstelle weiter eingegrenzt: statische Rohbefunde unter
`%TEMP%/hpg-deep-implementation-20261014/research-phrase/FINDINGS.md` führen
vom SongStructureAnalyze-Logger zu den internen Zustandsfunktionen
RVA `0x12cf990` und `0x12cfaf0`. Vollständiger Objekt-/Buffer-/Labelvertrag
noch offen; kein DLL-Aufruf und keine fertige Phrasenanbindung daraus ableiten.

## Implementierungsdelta 15.10.2026 — PSSI-Strukturgrenzen, ungetestet

Verifizierte PSSI-Intervalle werden jetzt in `analyze_structure` als
Strukturgrenzen verwendet, statt ausschließlich Cue-Scores und Mixkandidaten
zu liefern. Beide Analysepfade reichen die vorhandenen Phrasen über den
gemeinsamen Head-/Tail-Ablauf weiter. Absolute PSSI-Zeiten werden auf das
jeweilige Audiofenster bezogen; außerhalb ihrer tatsächlichen Intervallabdeckung
bleiben DSP-Grenzen erhalten. Ungültige, überlappende oder ungeprüfte
Phrasencontainer lassen die DSP-Grenzen unverändert. Übernommene Grenzen werden
nicht nochmals auf das Genre-Raster oder auf Hundertstelsekunden gerundet.

Energie, Trend und Abschnittslabel werden weiterhin aus dem jeweiligen
Audiofenster ermittelt. Diese Integration behauptet weder neue neuronale
Phrasengrenzen noch kalibrierte Strukturklassen. Die bestehenden Audio-
Coverage-Lücken bleiben im gemeinsamen Fensterablauf bestehen.
`CACHE_VERSION = 92` invalidiert frühere Sektions-/Mixpunktwerte.

Für die gemeinsame Testsession: beide Analysepfade, Head/Tail-Ursprung,
PSSI-Teildeckung, ungültige/überlappende Intervalle, gesperrte Referenz,
ungerundete Grenzen, neue Sektionsenergie und Cache-Reuse nachweisen.
Es wurden keine Tests, Modell- oder Hörläufe gestartet.







### Native Phrasenschnittstelle — Forschungsstand 15.10.2026

Nutzerentscheidung: native Rekordbox-Schnittstelle weiter rekonstruieren,
keine eigene HPG-Ersatz-Phrasenerzeugung. Ghidra ist inzwischen eingerichtet;
der frühere fehlende Decompiler ist kein aktueller Werkzeugblocker mehr.
Konstruktor, Initialisierung, zwei Audiopässe, Destruktor, PCM16/Float32-
Pegelvertrag und wesentliche Ergebnisfelder wurden statisch rekonstruiert.
Externe Forschungsadapter `E:\AI\tools\hpg-reverse-toolchain\native_phrase_worker.py`
und `native_phrase_adapter.py` sind geschrieben, **nicht ausgeführt und nicht
an den Produktpfad angeschlossen**. Sie besitzen Prozess-/Speicher-/Zeitgrenzen,
Quellenidentität und Gridkontrollen; dies ist noch kein Funktionsnachweis.
Rohbelege und Restlücken stehen in
`%LOCALAPPDATA%\Temp\hpg-deep-implementation-20261014\research-phrase\FINDINGS.md`.
Offen bleiben insbesondere die vollständige native Laufzeitfreigabe, native
Endesemantik und HPG-Key-Mapping. Der Nutzer hat die unabhängige
Wächterprüfung ausdrücklich auf den Abschluss verschoben; Priority-Service
bleibt verboten.

Produktanbindung 15.10.2026: `native_phrase_worker.py` und
`native_phrase_adapter.py` unter `hpg_core/ai_models/` sind jetzt angeschlossen.
Der serielle Broker beendet seine ONNX/TF-Lane vor dem nativen Einmalprozess;
4 GiB, höchstens 180 Sekunden und die vorhandene Generation/Abbruch-Deadline
gelten. Beide Analysepfade speichern `Track.native_phrase_analysis` separat
von importiertem PSSI. Native Grenzen gelangen in gedeckte Head-/Tail-Sektionen
und als `native_phrase` in Mix-Kandidaten; `phrase_grid` folgt der aktiven
Quelle. PSSI bleibt vorrangig. Native Herkunft erhält keinen PSSI-Konfidenzbonus.
Cache 93 bindet den neuen Vertrag und den Native-Modus an den Modellfingerprint.
Der Key verwendet vorerst den belegten nativen Unknown-Fallback Index 0;
das letzte Phrasenende verwendet ausdrücklich die HPG-Dateidauer. Keine
behauptete native Key-Konversion oder Endesemantik.

Laufzeitnachweis 15.10.2026: Der isolierte Worker lieferte über den echten
Broker auf einem Original-WAV in 4,593 Sekunden 23 native Phrasen (44100 Hz,
16259478 Frames). SHA-256 der Quelldatei vor/nach identisch. Der dafür
vorgegebene Grid-Kandidat war ausdrücklich nicht audiovalidiert: Dieser Lauf
belegt native Ausführung und Ergebniserzeugung, keine musikalische Güte oder
vollständige App-Abnahme. Rohbeleg: `research-phrase/native-first-runtime.json`
im oben genannten externen Forschungsordner.

Der Pfad ist nun standardmäßig für die hashgeprüfte EXE aktiviert und mit
`HPG_NATIVE_PHRASE=0` abschaltbar. Fehlende/andere EXE, unbestätigtes Raster,
Taktkonflikt oder bevorzugtes PSSI starten keinen nativen Prozess. Der Worker
kontrolliert den Hash erneut unmittelbar vor dem Laden.

Gebündelte Regression: 636 bestanden, sechs Testfehler im ersten Lauf;
die sechs betrafen Mock-Signaturen, veraltete Dataclass-Feldzahl und eine
ungeeignete neue Kandidaten-Testgeometrie. Nach Korrektur bestanden 18 gezielte
Nachtests einschließlich neuer Audio-/Rekordbox-Gridfälle. Kein RED/GREEN für
einen Produktfehler daraus behaupten. Abschluss-Volltest läuft separat;
unabhängiger Wächter, vollständiger nativer App-Ablauf und musikalische
Bewertung bleiben offen. Installation und Originalmusik unverändert.


### Aktualisierter Nutzerauftrag (15.10.2026)
Stems und Embeddings sind wieder ausdrücklich zur Implementierung beauftragt.
Reihenfolge: offene Fehler und native Rekordbox-Anbindung fertigstellen,
danach Stem- und Embedding-Integration. Zuerst implementieren, anschließend
nur betroffene Tests; bestandene Nachweise nicht ohne Änderungsgrund wiederholen.
Die frühere Zurückstellung gilt damit nur noch für die Reihenfolge, nicht
als Ausschluss aus dem Lieferumfang. Wächter bleibt auf Abschluss verschoben;
Priority-Service bleibt verboten.

### Fortsetzung: Tonartbindung und Implementierung vor Tests (15.10.2026)

Native Key-Tabelle aus dem gepinnten EXE-Caller und UTF-16-Ausgabestrings
rekonstruiert. `native_key.py` bildet bekannte HPG-Tonarten auf native Indizes ab.
Fast-/Vollpfad übergeben diese Zuordnung; unbekannte Tonarten bleiben ausdrücklich
als nativer Fallback 0 markiert. Snapshot v2 und Cache 94 binden die Herkunft an
die Track-Tonart. Die Taktpositions-Nutzungssperre berücksichtigt nun auch das
bereits vorhandene Diagnoseschema 7. Diese Änderungen sind noch ungetestet.

Der zuvor gestartete Volltest wurde zugunsten der nun erweiterten Implementierung
bei etwa 97 Prozent beendet. Er hatte bereits Fehlschläge; kein bestandener
Volltest und kein vollständiger Fehlerbericht. Rohlog bleibt in
`%TEMP%/hpg-native-phrase-full.log`. Veraltete Executor-Testdoubles akzeptieren
jetzt Deadline und Cache-Policy des bestehenden Produktaufrufs; noch kein Nachtest.
Die vorherigen gezielten Ergebnisse gelten nur für ihren damaligen Quellstand.
Native Terminalfeld-Semantik, verbleibende Fehler, Stem-/Embedding-Integration
und nachfolgende Abnahme bleiben offen.


### Fortsetzung: native Endgrenze und zusätzliche Merkmale (15.10.2026)

Die native Endgrenze ist statisch geklärt: Headerfeld 6 ist die rechte Grenze
im selben einsbasierten Beatraster wie die Phrasenstarts. Snapshot v3 bindet
`terminal_beat` und `native_terminal_beat`; kein Ersatz durch das Dateiende.
Rohbeleg: `research-phrase/NATIVE-TERMINAL-CONTRACT.md` im externen Forschungsordner.
Cache 96 umfasst Tonartbindung, Terminalgrenze und Stem-/Embeddingfelder.

Stem- und Embedding-Worker sind über den seriellen Modellbroker an beide
Analysepfade angebunden. Gespeichert werden lokale RMS-Kurven und normierte
64-dimensionale Embeddings mit Herkunft und Zeitabdeckung. Audiodaten werden
nicht gespeichert. HPG-eigene Vorverarbeitung und Aggregation sind ausdrücklich
keine Behauptung bitgleicher Rekordbox-Ergebnisse. Paarmerkmale bleiben bis zur
Kalibrierung diagnostisch und verändern keine Gewichte oder Synchron-Gates.

Ein begrenzter Brokerlauf am Originaltrack lieferte gültige Embeddings in
1,89 Sekunden und gültige Stems in 170,891 Sekunden. SHA-256 vorher/nachher
identisch. Rohbeleg: `research-phrase/deep-features-runtime.json`. Dies belegt
Modellausführung, nicht den vollständigen Appablauf oder musikalischen Nutzen.
Der Stem-Lauf liegt nahe am gesamten Trackbudget von 180 Sekunden: Zusatzjobs
lassen nun fünf Sekunden Rückgabezeit; Embeddings laufen vor Stems. Bei Ablauf
bleibt die Basisanalyse erhalten, fehlende Stems bleiben ausdrücklich unbekannt.
Die vollständige Stem-Verfügbarkeit im normalen Analysebudget ist noch offen.

Gezielte Regression des erweiterten Stands: zunächst 473 bestanden, eine neue
Cache-Fixture fehlerhaft. Danach 67 Fehler und 20 bestandene Fälle aus vorher
bekannten Fehlschlägen plus dieser Fixture. Nach Anpassung von Cache-Policy-,
Snapshot- und Diagnose-Doubles bestanden 24 von 26 betroffenen Fällen; die zwei
Tempo-Fixtures wurden anschließend korrigiert. Weitere gezielte Nachtests:
9 bestanden, zwei verbleibende Fixturefehler inzwischen bearbeitet, Nachweis offen.
Kein bestandener Volltest, keine abgeschlossene unabhängige Prüfung oder native
App-Abnahme behauptet. Verbleibende Fehler weiterhin anhand ihrer Verträge beheben.


### Konkrete Integrationskorrekturen und Nachweise (15.10.2026)

Drei Produktfehler korrigiert: fehlendes Rekordbox-Tempo (0, nichtendliche oder
ungültige Werte) wird im Referenzversuch als unbekannt normalisiert;
Cache-Snapshots enthalten ausschließlich Track-Dataclassfelder, keine transiente
`analysis_origin`; das Diagnoseschema akzeptiert jetzt den gemessenen Median
auch bei `phase_pattern=aligned`, verlangt dabei weiterhin höchstens 6 ms.
Der letzte Fehler verwarf zuvor auch vollständig gemessene, verifizierte Grids.
Gezielt bestanden acht Fälle für Referenztempo/Snapshot und drei Fälle für
Aligned-Diagnose inklusive echter Fastpath-PSSI-Pipeline. Ein anschließend
sichtbarer fehlender Kandidat gehörte zur fehlenden Downbeat-Freigabe einer Fixture.

DSP-Pipeline-Fixtures verwenden jetzt ausdrücklich keine lokal installierten
optionalen Modelle. Verfügbare Rekordbox-Installationen dürfen ihre Erwartungen
nicht unbemerkt ändern oder schwere Modellläufe starten. Separate Modelltests
und der Originaltrack-Brokerbeleg bleiben bestehen. Zwölf von siebzehn zuvor
fehlgeschlagenen Analysefällen bestanden nach Fixturekorrektur. Veraltete
Erwartungen an Rekordbox-Herkunft nach Audiowechsel, Mixfreigabe bei Mismatch
und Phraseneinheit 0 werden an die bestehenden strengen Verträge angepasst;
keine Produkt-Gates abgesenkt. Weitere Nachweise und offene Fehler bleiben offen.

### Modellwarteschlange und Trackbudget (15.10.2026)

Das Trackbudget berücksichtigt nun die seriellen Zusatzmodelle: bei einem
Worker und beiden aktivierten Merkmalen 390 Sekunden, bei vier Workern maximal
870 Sekunden. Ohne Zusatzmodelle bleibt das Basisbudget erhalten. Einzelne
Stem-/native Aufrufe bleiben auf 180 Sekunden begrenzt, Embeddings auf 30 Sekunden.
Der Client wartet innerhalb der Trackdeadline auf READY; erst danach beginnt
das einzelne Ausführungsbudget. Der Broker validiert und erzwingt dieses Budget.
Zusatzmerkmale lassen fünf Sekunden Rückgabezeit für den fertigen Basistrack.
Speichergrenzen und Generation-Abbruch bleiben erhalten.

Die vier neuen Budgetfälle und der simulierte Queue-Fall bestanden; Rohlog:
`%TEMP%/hpg-model-budget.log`. Der kombinierte Nachtest wurde beim anschließend
begonnenen Audiointegrationsteil abgebrochen, ist also kein vollständig
bestandener Lauf. Die zuletzt ergänzte Übergabe des 30-Sekunden-Embeddinglimits
braucht noch ihren betroffenen Nachweis. Vollständiger nativer Appablauf,
unabhängige Prüfung und musikalische Verbesserung bleiben unbewiesen.

Gezielte Fortsetzung: Die Übergabe der Embedding-/Stem-Limits und drei zuvor
korrigierte Analyseverträge bestanden gemeinsam (4 Fälle, 13,02 s;
`%TEMP%/hpg-integration-contract-final.log`). Die kontrollierte Diagnose-Fixture
verwendet jetzt konsistente Frame-Zeit-Konvertierung. Ihr letztes ausgerichtetes
Beatfenster endet bei 16,1 s ausserhalb der 16-s-Eingabe und darf nicht abstimmen;
die Rampen-Fixture erwartet deshalb Klasse 2 statt Klasse 3. Das ist kein
musikalischer Referenztrack. Vier Fälle bestanden im anschliessenden Lauf;
die verbliebene doppelte Alt-Erwartung wurde danach korrigiert und nachgewiesen.
Die paarspezifische Empfehlung verwendet in ihrer Fixture ausdrücklich die
konfigurierten acht Takte statt des Genre-Priors. Beide letzten Fälle bestanden
in `%TEMP%/hpg-pair-contract-retest.log`. Die gleiche Herkunft wurde in der
synthetischen Hörproben-Fixture ergänzt; deren vollständiger Nachtest steht aus.

### Wandernder interner Tracker-Lag (15.10.2026)

Interne Trackerzeiten dürfen bei erhaltenen lokalen Beatnummern über eine
Rundungsgrenze wandern. Die Featureausrichtung schätzt dafür einen gemeinsamen
Zelloffset aus dem Median der Ursprünge; einzelne Beatnummern werden nicht
umetikettiert. Eine Driftspanne von mindestens einem ganzen Beat bleibt
abgelehnt. Externe Beatpositionen behalten die bisherige strikte Zuordnung.
Fold-, Voting-, Grid- und Renderer-Grenzen bleiben bestehen. Cache 97 erzwingt
für die geänderten Analysewerte eine neue Version, ohne alte Dateien zu löschen.

Gezielter Nachweis: 61 Fälle bestanden in 5,57 Sekunden, darunter die drei zuvor
fehlgeschlagenen Synthesefälle mit bekannter Takt-Eins und wanderndem Tracker-Lag,
Featuregrid-Randfälle und externe Beatpositionen. Rohlog:
`%TEMP%/hpg-tracker-lag-fix.log`. Das belegt diese Regressionen, noch keine
musikalische Verbesserung auf unabhängigen Originaltracks oder App-Abnahme.

### Disjunkte Rotationsbestätigung und Hörprobenfortsetzung (15.10.2026)

Die beiden alten Rotationstest-Fixtures belegen nun tatsächlich drei zusätzliche
Fenster ausserhalb der Modellkandidaten- und Referenzfenster. Der positive Fall
erwartet den autorisierten Audioanker; eine schwache der sechs Bestätigungen
verhindert die Übernahme. Beide Fälle und der Cacheversionsvertrag bestanden
(3 Fälle, 3,60 s; `%TEMP%/hpg-disjoint-rotation-retest.log`). Kontrollierte
Modell-/Audioantworten belegen hier den Integrationsvertrag, keine Modellgüte.

Der synthetische Hörproben-Pilot mit einem Paar bestand nach Ergänzung der
explizit konfigurierten Phraseneinheit (1 Fall, 3,90 s;
`%TEMP%/hpg-hearing-pilot-retest.log`). Der vollständige betroffene GUI-/Fit-Test
wurde anschliessend unter `%TEMP%/hpg-hearing-bridge-retest.log` gestartet;
dieser Start ist noch kein Erfolgsnachweis.

Der GUI-/Fit-Test ist inzwischen abgeschlossen: 1 bestanden in 150,22 s,
64 synthetische Paare und 128 Varianten. Kein Originaltrack-Nachweis daraus.

### Originaltrack-Ablauf und lokaler DSP-Retry (15.10.2026)

`tools/verify_deep_original_flow.py` führt zwei ausdrücklich angegebene Quellen
mit eigenem Cache durch Analyse, Cache-Reuse, Playlist und RAM-Renderer. Er legt
keine Audiodateien ab und behauptet keinen sichtbaren GUI-/Hörnachweis.
Erster Lauf: `%TEMP%/hpg-original97-20261015-run1/report.json`, Rohlog
`%TEMP%/hpg-original97-run1.log`. Never Die und You Never Alone lieferten in
203,156 bzw. 240,266 Sekunden gültige Stems/Embeddings; beide privaten Cache-Hits
bestätigt und Quellhashes unverändert. Beide Taktanker blieben unbestätigt;
keine Mixkandidaten und kein Render. Exit 1 ist ausdrücklich kein Gesamterfolg.

Die DSP-Schätzung scheiterte am langen Tracker-Raster. Cache 98 ergänzt nur
bei `fold_alignment` einen begrenzten Retry mit drei getrennten lokalen Fenstern
bei 20/50/80 Prozent. Alle müssen zuverlässige, auf höchstens 6 ms gleiche
Taktphasen liefern; zusätzlich muss die bisherige Gesamtgridprüfung bestehen.
Vier gezielte Vertragsfälle bestanden (`%TEMP%/hpg-local-retry-contract.log`).
Nur der betroffene DSP-Teil wurde danach an denselben Originalquellen erneut
ausgeführt, ohne Modellinferenz. Never Die bestätigt Anker 0,016295652 s bei
Konfidenz 0,661 inklusive Gesamtgrid; You Never Alone bleibt abgelehnt.
Rohbeleg `delta98-downbeat.json` im genannten Laufordner; beide Quellhashes
unverändert. Die vollständige Analyse/Playlist/Preview-Kette mit Cache 98 ist
noch nicht bewiesen; gespeicherte Cache-97-Tracks werden nicht umetikettiert.

You Never Alone: gezielte lokale Nachmessung ohne neue Modell-/Stem-Läufe
belegt einen Taktphasenwiderspruch. Das erste 16-s-Fenster enthält nur 14 aktive
Beats; Mitte und spätes Fenster liefern um einen Beat verschiedene Einsen.
Energiegestützte Fensterwahl vor dem Voting beseitigt den Widerspruch nicht:
82/171/255 s enthalten jeweils 36 aktive Beats, liefern aber Phasen
0,449354/0,449254/1,319209 s. Auch eine Länge von 16 Takten stabilisiert nicht
alle drei Fenster. Beide experimentellen Änderungen wurden zurückgenommen;
kein gelöster Taktfehler behauptet. Rohbefunde `you-never-alone-local-windows.json`,
`you-never-alone-active-windows.json`, `you-never-alone-16bar-windows.json`
im Original97-Laufordner. Nächste offene Ursache ist die Taktphasenbewertung,
nicht bloss ein globaler Zeitversatz. Die vollständige Originaltrack-Kette
bleibt offen; keine bestandenen Modellläufe wiederholt.


### Cache99: Originalanalyse und renderbarer Reservekandidat (15./16.10.2026)

Bei internem Trackerdrift bildet downbeat.py das Audio-Raster aus BPM/Fold neu,
jedoch nur nach drei disjunkten verifizierten Audiofenstern. Externe Beatnummern
bleiben unveraendert; Taktvoting und 6-ms-Grenze bleiben erforderlich.
Drei neue Rasterregressionen bestanden, ausserdem der betroffene Ablehnungsfall.
Die unabhaengige musikalische Takt-Eins der Originale bleibt unannotiert.

Originalbeleg: %TEMP%/hpg-original99-20261015-run1/report.json.
Never Die: Anker 0.0161 s, Konfidenz 0.953, 19 native Phrasen.
You Never Alone: Anker 0.0144 s, Konfidenz 0.760, 23 native Phrasen.
Beide Grids verified; isolierte Cache-Hits und unveraenderte Quell-SHA256.
Analysezeiten 98.953 und 109.391 s. Stems/Embeddings wurden NICHT wiederholt:
HPG_FEATURE_REUSE_REPORT bindet explizite Wiederverwendung an Quellhash,
Modellfingerprint und unveraenderten Produzentencode. Fuenf neue Vertragsfaelle
bestanden. Bei Konflikt kein stiller teurer Ersatzlauf. Frische DSP-/Struktur-
Analyse mit wiederverwendeten Zusatzmerkmalen ist kein neuer Stem-Nachweis.

Der erste Playlist-Render wurde durch den unveraenderten strengen Renderer
abgelehnt; report.json bleibt Exit-1-Beleg. Auch die anderen 11 normalen
Kandidaten und 11 Kandidaten der Gegenrichtung scheiterten am Kick-Sync.
Eine begrenzte Suchraumdiagnose mit bis zu 30 Kombinationen fand Rang 22:
You Never Alone mix-out 132.188 s, Never Die mix-in 67.842 s, 32 Takte,
55.652184429327285 s nominelle Blende (massgeblich ist die gespeicherte Spec).
RAM-Render erfolgreich: 5,100,261 Frames bei 44,100 Hz, endlich, Peak 1.0.
Beleg candidate-delta-reserve.json; keine WAV-Datei geschrieben.
Diese Suchraumdiagnose ist KEIN automatischer Produktfallback.

pair_candidates bewahrt jetzt eine explizite, noch gueltige Reservewahl vor
Score-Kappung (maximal eine zusaetzliche Kombination); alle Qualitaets- und
Auditpruefungen bleiben aktiv. Neue Regression bestanden. Normale
rebuild_result_for_order-Produktfunktion liefert mit expliziter Reihenfolge
und dieser Wahl exakt die bereits gerenderte Spec: reserve-product-binding.json.
Kein erneutes Rendern fuer diesen Gleichheitsnachweis. generate_playlist_result
allein kann wegen der geaenderten Scores eine andere Reihenfolge waehlen.

Offen: automatische Reserveauswahl im normalen App-/Hoerprobenablauf,
sichtbare native App-Nutzung und menschliche musikalische Bewertung.
Wächter weiterhin bis Abschluss verschoben; kein EXE-Build, kein Gesamtabschluss.


### Begrenzte Reserve-API (16.10.2026, implementiert, noch ungeprueft)

pair_candidates akzeptiert jetzt max_combinations zwischen 1 und 30; Standard
bleibt unveraendert. Das Diagnosewerkzeug verwendet diesen Parameter statt
einer globalen Konstantenaenderung. render_selection.render_with_reserve baut
nach BeatSyncError qualifizierte Alternativen mit rebuild_result_for_order auf,
prueft den tatsaechlich ausgewaehlten Plan und liefert Playlistzustand, Spec,
RAM-Audio und Ablehnungsbelege gemeinsam. Identische Specs werden innerhalb
eines Auftrags nicht doppelt gerendert. Andere Fehler brechen ab; Abbruchpunkte
liegen vor/nach jedem Render. Kein Modellaufruf, keine Audiopersistenz.

Noch nicht an GUI-Worker angeschlossen und noch nicht getestet. Fuer den
naechsten Schritt: MainWindow._publiziere_generation_result publiziert den
Gesamtzustand atomar; MixTipsPanel._start_next_preview verwendet bisher
TransitionRenderWorker mit Dateiausgabe. TransitionPreviewWidget besitzt nur
set_wav_path. RAM-Playback mit QBuffer/setSourceDevice ist bereits in
hearing_panel.py vorhanden. Eine Reserve darf erst mit passendem aktualisiertem
Playlistzustand sichtbar werden; veraltete Workerresultate sind zu verwerfen.

### Native Vorschau und abgelehnte musikalische Bewertung (16.10.2026)

Die Reserve ist inzwischen ueber RenderSelectionWorker isoliert an die GUI
angebunden. MainWindow publiziert den neuen Playlistzustand zusammen mit den
passenden Mixpunkten; QBuffer/QMediaPlayer spielt WAV-Bytes ausschliesslich im
RAM. Sechs neue Kontrollfluss-Tests bestanden, anschliessend ein neuer Test
fuer den korrigierten Erfolgszaehler. Die sichtbare App verwendete vorhandene
Originaltrack-Analysesnapshots: keine frische Ordnerauswahl/GUI-Analyse.
GUI-Beleg: %TEMP%/hpg-original99-gui-20261016-a/gui-events.json.
Die Vorschau lief sichtbar bis 0:36; das beweist Abspielen, keine Musikqualitaet.

Der Nutzer bewertet genau diesen Uebergang als insgesamt unbrauchbar:
Beats auseinander, musikalisch falsch/zu lang, Ton verzerrt/stockend/beschaedigt.
Diese Abnahme ist NEGATIV. Cache99 und das bisherige Render-Gate beweisen
keine musikalisch korrekte Takt-Eins. Beide bar_phase_reliable-Felder waren false.

Gezielte Reproduktion des abgelehnten Clips (keine Stem-/Modellwiederholung):
- Nach EQ Peak 0.722, nach Lautheitsregelung 1.421, erst danach Limiter 1.0.
- Die drei Kickmessfenster bestanden, dazwischen wurden aber bis 23.855 ms
  relativer Korrelationsversatz und ein nicht messbarer Abschnitt gefunden.
  Diese Werte sind Korrelationsmessungen, keine unabhaengigen Attack-Labels.

Renderer korrigiert: fensterweiser kanalgekoppelter Headroom begrenzt den
Lautheitsgain vor dem Limiter; die positive Fenstermittelung bleibt erhalten.
Zusaetzliche lueckenlose Fenster pruefen die gesamte Blende nach der globalen
Korrektur. Die 6-ms-Grenze und Korrelationsschwelle bleiben unveraendert.
Vier neue gezielte Regressionen bestanden (zwei Headroom-/Stereo-Faelle,
zwei Faelle mit/ohne lokalen Versatz zwischen den bisherigen Stichproben).
Originalclip nach Headroom-Fix: Peak 0.95000017 statt 1.42063224.
Nach Sync-Fix wird derselbe schlechte Clip bei 22.609 s korrekt abgelehnt.
Belege im Original99-Laufordner: rejected-preview-dsp-stages.json,
rejected-preview-after-headroom.json, rejected-preview-sync-regression.json.
Keine Audiokopie, keine neue Vollanalyse, keine bestandenen Stem-Laeufe wiederholt.

Weiter offen: musikalisch geeignete Auswahl und Takt-Eins fuer diese Originale,
erneute positive Hoerabnahme, voller nativer Analyse-/Bewertungsablauf sowie
abschliessende unabhaengige Pruefung. Die noch laufende GUI enthaelt die neuesten
Renderer-Fixes nicht. Kein Gesamtabschluss und kein EXE-Build.

### Modell-Taktpruefung und fenstergebundene Zusatzmerkmale (16.10.2026)

Codebefund: Hohe DSP-Phrasenkonfidenz fuehrte bisher in _resolve_track_anchor
zu baseline_preferred, bevor vorhandene Modellpositionen gegen Audio geprueft
wurden. Das Original99-Ergebnis von You Never Alone zeigt genau diesen Pfad.
Cache 100 entfernt diesen vorzeitigen Abbruch fuer erfolgreiche vorhandene
Decoderfenster. Die Cache99-Rasterrettung bleibt erhalten; alle Audio-,
Modellkonsistenz- und Gesamtgrid-Gates bleiben erforderlich. Zwei neue
Regressionen bestanden: konsistent bestaetigte Modelle werden auch bei starker
Baseline uebernommen; widerspruechliche Modelle werden nicht uebernommen.

Gezielter echter Resolverlauf mit Originalaudio und bereits gespeicherten
Modellfenstern (keine neue Inferenz, keine Stems, keine komplette Neuanalyse):
2.891 s; weiterhin DSP-Anker 0.0144 bei 0.76. Vier externe Votes wurden wegen
external_vote_conflict, zwei wegen fewbeats verworfen. Entscheidung jetzt
insufficient_evidence statt baseline_preferred. Das beweist die Integration,
keine geloeste musikalische Takt-Eins. Beleg: Original99-Laufordner/
you-never-alone-anchor100.json. Kein Cache99-Track wurde umetikettiert.

Weiterer behobener Integrationsfehler: build_pair_candidates kopierte die
Deep-Feature-Fenster der kurzen Blende auf die lange. Zusatzmerkmale werden
jetzt je tatsaechlicher Blendenlaenge aus vorhandenen Kurven berechnet.
Ein neuer gezielter Test bestanden; Scores/Gewichte bleiben unveraendert,
unkalibrierte Zusatzmerkmale bleiben affects_score=False.

Acht bisher ungepruefte Reservevarianten (Rang 23-30) ebenfalls abgelehnt.
Kein bereits bestandener Render/Stem wiederholt. Rohbeleg:
untried-reserve-after-user-rejection.json im Original99-Laufordner.
Der negative musikalische Befund bleibt offen; keine weitere beliebige
Reserveausweitung als Ersatz fuer die Takt-/Phrasenkorrektur.

### Vorschau-Worker: Abschluss und Abbruch (16.10.2026)

RenderSelectionWorker veroeffentlichte eine empfangene Auswahl bisher vor
Pruefung des Kindprozessabschlusses. Ein spaeterer Crash oder erzwungenes
Terminate konnte dadurch mit erfolgreichem Ergebnis zusammenfallen.
Jetzt wird erst nach sauberem Exitcode 0, innerhalb des Zeitlimits und ohne
Abbruch veroeffentlicht. Setup-Fehler laufen ueber clip_error; ungueltige
Zeitlimits werden vor Workerinitialisierung abgelehnt. Ein Abbruch vor Start
legt keinen Prozess an. Abgebrochene Ergebnisse werden verworfen.

Zwoelf neue kontrollierte Lifecycle-Faelle bestanden in 0.20 s:
sauberer Exit, Crash nach Antwort, haengender Prozess, Abbruch, verspaetete
Antwort, Abbruch vor Start, Setupfehler und fuenf ungueltige Zeitlimits.
Diese Tests verwenden Prozess-Doubles, keine Originalaudio-/Stem-Laeufe.
Sie beweisen die Steuerlogik, keinen neuen nativen Hoerablauf. Eine frueher
beobachtete schlechte Tonqualitaet ist damit nicht als verursacht/behoben belegt.
Die Frage nach einer eindeutigen musikalischen Takt-Eins bleibt offen.

### Nutzerpraezisierung und native Beat-Rekonstruktion (16.10.2026)

Der Nutzer soll kein Beatgrid selbst verschieben oder eine Takt-Eins liefern
muessen. Er beauftragt ausdruecklich die Rekonstruktion der Rekordbox-Verarbeitung
mit REA und eine moeglichst originalgetreue Nutzung in HPG. Die fehlende manuelle
Taktreferenz ist keine Voraussetzung fuer weitere Implementierungsarbeit.
Musikalische Qualitaetsparitaet bleibt separat nachzuweisen.

REA open_binary identifiziert die installierte rekordbox.exe als x86_64 PE mit
SHA256 c9ed23e974c51c75e2ec069fbd2679a3dbe606be9e79e9cbbd13d6418ab11c37.
Der MCP-Ghidra-Provider hat keine konfigurierte Installation. Die bereits
vorhandene lokale Ghidra12.1.4/JDK25-Toolchain und das Projekt HPGPhrase wurden
stattdessen read-only mit -noanalysis weiterverwendet. Ein Start mit normalem
Benutzerprofil scheiterte am Felix-Cache; das vorhandene isolierte Toolprofil
funktioniert. Keine Engine neu installiert, keine Installation gepatcht.

Neue statische Rohbelege ausserhalb des Repos:
E:/AI/tools/hpg-reverse-toolchain/beat-raw-strings-20261016.txt
E:/AI/tools/hpg-reverse-toolchain/beat-static-xrefs-20261016.txt
E:/AI/tools/hpg-reverse-toolchain/beat-callers-20261016.txt
E:/AI/tools/hpg-reverse-toolchain/beat-contract-20261016/function-*.c

- Modellpfade model7/model8 bei VA143cdc9b0/143cdc9d0; beide Referenzen in
  Funktion RVA1f8d330 durch dekompilierte Aufrufstellen bestaetigt.
- RTTI-Name .?AVRNNDownBeatTrackingObservationModel@madmom@@ bei VA145e3a620.
  Der Name allein beweist noch keine konkrete Algorithmuskonfiguration.
- Native Viterbi-Fehlermeldung bei VA143824d00, Referenz in RVA12b2e20.
  Diese Funktion wurde dekompiliert; Matrix-/Puffervertrag noch unvollstaendig.
- Direktaufrufer RVA1297d60 ruft RVA12b2e20 fuer Objekte mit Schrittweite0x1b8
  auf, sammelt Pfade und Skalarwerte und waehlt danach einen Pfadindex ueber
  RVA12ad1f0. Bedeutung/Parameter dieser Auswahl sind noch zu rekonstruieren.
- RVA1211d20 ist ein Singleton-Zugriff; Modellpfade werden vom untersuchten
  Initialisierungspfad in dessen Felder +0xa8/+0xb0 geschrieben.

Naechste konkrete Luecken: Konstruktion des nativen Decoderzustands, Bedeutung
aller Parameter von RVA1297d60, Aufrufer mit echten Parametern, Auswahlfunktion
RVA12ad1f0, Tensor-zu-Decoder- und Ergebnis-zu-Beatgrid-Konvertierung. Erst dann
Adapter/Port anschliessen. Der bisherige HPG-Decoder ist eigener 4/4-Viterbi-Code;
seine Paritaet zur nativen Verarbeitung ist nicht bewiesen. Keine native
Beatfunktion ausgefuehrt, keine Musik-/Stem-/Testwiederholungen in diesem Schritt.


### Native Beatdecoder-Anbindung (16.10.2026, Fortsetzung)

Implementiert: `native_beat_worker.py` bindet RVA 0x1297d60 der gepinnten
Rekordbox-EXE direkt ein. Der vorhandene NativeImage-Lader wird wiederverwendet.
Aufrufstelle 0x12ac107..0x12ac16b belegt die Parameter: Meter [4], min/max
70/180 BPM, num_tempi 60, transition_lambda 100, observation_lambda 16,
threshold Float32 0.05, correct=true, fps=100. Float32-Matrix: 40 Bytes,
rows+4, columns+8, size+12, data+24, ownership+32. Native Freigabe RVA12add90.
Argmax RVA12ad1f0 nimmt bei Gleichstand den ersten Index. Vtable-Observation
RVA12ae6e0. Statische Rohbelege: beat-contract-20261016/function-*.c und
beat-callsite-abi-20261016.txt im bestehenden externen Reverse-Toolroot.

`cue_service.py` verwendet nun `native_beat_decoder.py`; keine nachtraegliche
HPG-Barrotation. Nicht exportierte Likelihood/Rotationsscores bleiben null/leer.
Native Ausgabe weiterhin verified=false, vorhandene Audio-/Synchronisationsgates
bleiben bestehen. Cache101 trennt den neuen Vertrag. Der ersetzte HPG-Viterbi-
Decoder und seine algorithmusspezifischen Tests wurden aus dem Produkt entfernt;
Forschungsbaseline unter Toolroot/legacy-hpg-beat-decoder[-tests]-20261016.py.
Die neuen Tests pruefen native Herkunft, unveraenderte Positionen und ABI.

Ausgefuehrt: nativer isolierter Smoke mit 1200 Aktivierungsframes, 24 erwartete
Beatpositionen korrekt, 2.75s; TEMP/hpg-native-beat-smoke-20261016.json.
Gezielte Integration: 42 bestanden, drei veraltete Erwartungen (Cache99 und
Baseline-ohne-Modellvergleich) korrigiert, nur diese drei nachgetestet: bestanden.
Neue Adaptertests: 8 bestanden. Logs TEMP/hpg-native-beat-integration-20261016.log,
*-integration-retry-20261016.log und *-adapter-tests-20261016.log. Kein Volltest.

Original You Never Alone: ausschliesslich erste16s source-direct gelesen,
beide Beatmodelle und nativer Decoder im begrenzten Prozess, 13.985s.
Beide first_downbeat=0.4300000071525574; native Peakmedian-BPM model7
139.53478469154203, model8 137.93105262638653. Source-Stat unveraendert.
Rohbeleg TEMP/hpg-native-beat-original-20261016.json. Kein Stem-Lauf,
keine vollstaendige Trackanalyse, keine neue Playlist/Hoerprobe/GUI-Abnahme.
Gleiches native Endgrid wie Rekordbox bleibt unbewiesen: die hoehere Verarbeitung
RVA12a8ef0 teilt Audio in Fenster; ihre Aufrufer und die finale Gridanpassung
werden weiter rekonstruiert. Ein nativer Decoder beweist keine gesamte Paritaet.


Nachtrag derselben Umsetzung: `native_beat_grid.py` ruft jetzt auch RVA1295b40
(beatList) und RVA1296a80 (Tempoaggregation) auf. ABI an1295591..12955bd belegt.
Ordered-json wird im begrenzten Kind gelesen: Arrayelement16Bytes,
Objekteintrag48Bytes (MSVCString32 + JSON16); Freigabe RVA11f0540.
Native BPM-Einheit ist BPM*100 (Konstanten580013c=100,58002e4=60000).
Ein anfaenglicher Adapterfehler verwarf13953 als ungueltige BPM und beendete den
Owner. Nach korrekter Division durch100 lief derselbe Gridnachweis erfolgreich.
Dies war kein bewiesener nativer Absturz; die Zwischenmeldung Prozessabbruch
beschrieb nur das vom Parent beobachtete Kindende. Kein Modell erneut gestartet.
TEMP/hpg_native_grid_probe_20261016-fixed.log und gleichnamige JSON ohne -fixed:
vorhandene Original-Decoderzeiten beiderModelle -> je37nativeGridzeilen,
BPM139.53/136.36. ErsterTakt1beide430ms. NativeGrid setzt davor Beat4 bei0/10ms.
HPG verwendet jetzt native msec/numBar sowie native BPMaggregation, keinen eigenen
Intervallmedian.11gezielte Tests fuer diesen geaenderten Anschluss bestanden,
TEMP/hpg-native-grid-integration-20261016.log. VorherigeErgebnisse nicht als
vollstaendigen Nachweis der spaeteren Erweiterung darstellen.

Weitere statische Aufruferkette:128ecd0 ruft1294100 (Reader/Modellfenster), danach
11db800 ueber param_1[0x13], liest BPM mit11db860, Count11db890 und Daten11db8c0.
Diese nachgelagerte Endgrid-Verarbeitung ist noch nicht rekonstruiert/angebunden.
Die momentan integrierte beatList ist daher noch kein Beweis des finalen
Rekordbox-Beatgrids oder einer geloesten musikalischen Taktabweichung.

### Fortsetzung 16.10.2026: vollständige native Beatfolge und Audio-Zeitkorrektur

Dieser Abschnitt ersetzt die früheren Zwischenstände zu fehlender Endgrid-Anbindung und `msec` als Zeitquelle.

Implementiert: gepinnte native TensorFlow-Bibliothek mit 29 IAT-Imports; Original-60s-Fensteraufteilung RVA12a8ef0; beatList RVA1295b40; native DSP-Endkorrektur über11db800 und Getter11db860/890/8c0. Native Sampleposition `pos/44100` ist maßgeblich: extrapolierte `msec`-Werte können falsch skaliert sein. Isolierte Einmalprozesse; native Diagnoseausgaben in eigenem TEMP-Verzeichnis. Rekonstruierter Eingabebereich: PCM16, Stereo,44100Hz, höchstens20Minuten, Modell7. Vollständige Reader-/Modellwahl-Parität bleibt offen.

Konkreter Never-Die-Fehler: native Floatzeiten an180s werden auf dieselbe Sampleposition7938000 gerundet. Die rohe beatList enthält dadurch doppelte Positionen und BPM-Sentinel INT_MIN. RVA128ecd0 reicht diese signed-int32-Tripel unverändert an die native Endkorrektur. HPG hatte sie vorher verworfen. Nur der interne Rohvertrag erlaubt sie jetzt; fertige Grids müssen weiterhin strikt aufsteigend und taktzyklisch sein. Originalbeleg TEMP/hpg_native_never_die_raw_grid_20261016.json; korrigierter Endlauf TEMP/hpg_never_die_final_20261016.json:745Beats,138BPM. Vorhandene Modellresultate wiederverwendet.

You Never Alone: vollständige native Endkorrektur liefert848Beats,138BPM, erste1bei225/44100s. Audio-Fold meldet zunächst konsistent8.4–10.6ms Versatz. Native Rohdaten bleiben unverändert; optionale `audio_alignment` speichert separat gemessene Zeitkorrektur und sechs disjunkte Audiofenster. Bestätigungsfenster werden vor ihrer Phasenmessung anhand regelmäßiger nativer Modellbeats gewählt; Breaks mit unregelmäßigen Rohbeats sind keine Kickreferenz. Kein Taktrotationstausch, maximal Viertelbeatkorrektur, unveränderte6ms-Grenze. Gespeicherte Messungen werden gegen Grid und Zeitkorrektur rechnerisch validiert. Audioherkunft heißt `native_rekordbox_audio_offset`; kein importiertes PSSI wird vorgetäuscht. Cache104 trennt diesen Vertrag.

Originalfensterbelege: TEMP/hpg_native_corrected_audio_gate_20261016.json (You Never Alone, Bestätigung76/160/295s, maximal0.160ms), TEMP/hpg_never_die_corrected_audio_gate_20261016.json (Never Die,65/181/259s, maximal0.424ms). Das ist ein technischer Phasennachweis, keine unabhängige musikalische Takt-1-Abnahme. Native Ergebnisherkunft und unveränderte Taktzahlen werden jetzt auch im Renderer berücksichtigt; zuvor behandelte er nur DB-importierte Rekordbox-Grids als Referenz.

Stem-/Embedding-Wiederverwendung bleibt an Quellhash, unveränderte fünf Audio-/Modellproduzenten und Modellkonfiguration gebunden. Der reine Brokertransport ist keine Ergebnisberechnung; neue Beat-Routen dort erzwingen keinen Stem-Neulauf. Beide vorhandenen Original-Metadatensätze aus TEMP/hpg-original97-20261015-run1 wurden erfolgreich gelesen, keine Stem-Inferenz.

Gezielte Regressionen: TEMP/hpg-native-grid-regressions-20261016.log zunächst9bestanden/7fehlgeschlagen wegen eines ungenauen synthetischen Sample-Rasters; Fixture korrigiert, ausschließlich7fehlgeschlagene Tests nachgetestet, alle bestanden (TEMP/hpg-native-grid-regressions-retry-20261016.log). Frühere447Integrationstests nicht wiederholt. Neuer vollständiger Produkt-API-Lauf mit Originalen und wiederverwendeten Zusatzmerkmalen: TEMP/hpg-original104-20261016-run1; Ergebnis noch ausstehend. Keine EXE-/GUI-/musikalische Abnahme behaupten.

Abschluss dieser Fehlerscheibe16.10.2026:
- Produktlauf `TEMP/hpg-original104-20261016-run1/report.json`: beide Originale frisch analysiert, Grid verified, native Phrasen ok, Stems/Embeddings aus belegtem Lauf97 wiederverwendet, isolierte Cache-Schreib-/Lesewege erfolgreich. Ursprünglicher Render scheiterte; dieser Bericht bleibt unverändert als Fehlerbeleg erhalten.
- Weitere Ursache im Renderer: bei138BPM liefern zwei Millisekunden-gerundete Mixpunkte einen Phasenrest von2Samples. Der bisherige floor-Schnitt nahm dadurch nur2statt76696Vorlaufsamples weg und verschob den Einsatz um1.739s. Bei maximal1ms plus2Sample-Rundungen bleibt nun der nominale Einsatz erhalten; anschließende6ms-Prüfung unverändert.
- Native Modellfolgen schließen unregelmäßige Blendfenster vor dem Rendern aus. Zusätzlich bleibt die bestehende Mindestblende8Takte als native Alternative verfügbar; Genrewerte und Untergrenze nicht verändert.
- Für bekannte Taktreferenzen prüft der Renderer lokale Audio-Attacks gegen das Referenzgrid statt Bassklangähnlichkeit per Kreuzkorrelation. Peak-Suche innerhalb des Viertelbeats nach der erwarteten Attack; Attackzeit wird weiterhin frei gemessen. Jede4Beatregion muss pro Quelle innerhalb6ms bleiben; nach globaler relativer Korrektur muss auch jeder Paarrest unter6ms liegen. Fehlende Messbarkeit bleibt Fehler. Ohne bekannte Taktreferenz bleibt der bisherige Korrelationspfad bestehen. Das ist Referenzkonsistenz, keine unabhängige Takt-1-Ground-Truth.
- Neue Regressionen insgesamt21native/grid/renderer-Fälle plus5betroffene Feature-Reuse-Fälle bestanden, über getrennte Läufe; keine bestandenen Fälle ohne relevante Änderung erneut ausgeführt. Belege: `hpg-native-grid-regressions[-retry]-20261016.log`, `hpg-native-candidate-gap-20261016.log`, `hpg-native-rounding-20261016.log`, `hpg-native-reference-renderer-20261016.log`, `hpg-native-short-blend-20261016.log` inTEMP. Keine Vollsuite.
- Tatsächlicher GUI-Erfolg: `TEMP/hpg-native104-gui-run6/gui-events.json`: normaler Vorschau-Worker, drei verworfene Kandidaten, dann13,913s/8TakteBlende NeverDie229,581s -> YouNeverAlone132,189s;73,913sGesamtclip/13038304RAM-Bytes, `gui_cache_ready=true`, `strict_beat_sync=true`, beide Taktreferenzen aktiv. Die App übernimmt den neu aufgebauten Playlistzustand und das dazugehörige RAM-Audio gemeinsam. App bleibt zur Hörbewertung geöffnet, keine Audiodatei gespeichert.
- Aktueller Beleg mit Quell-/Codehashes und unveränderten Originalen: `TEMP/hpg-original104-20261016-run1/completion-native-preview.json`. GUI nutzt die frischen Analyse-Snapshots; kein erneuter GUI-Ordnerimport behauptet. Fehlgeschlagene GUI-Versuche1–5 bleiben als solche erhalten;6belegt den korrigierten Stand.
- Offen: menschliche musikalische Bewertung, unabhängiger Wächter (Priority-Service bleibt verboten), über diese beiden Quellen hinausgehende Formate/Readerparität. Kein EXE-Build, kein pauschaler Gesamtabschluss des Deep-Analysis-Auftrags.

### Produktanbindung und Export, 16.10.2026

Implementiert: `native_track_beats.has_verified_grid` vereint die bisherige native Snapshot-/Ankerfreigabe für Renderer und XML-Export. Der Export übernimmt jetzt auch native Grids mit separat bestätigter Audio-Zeitkorrektur. BPM, Anker, Herkunft, Evidenz und Status müssen übereinstimmen; eine Taktpositionssperre verhindert weiterhin den Export. Kein Cache-Bump: gespeicherte Daten und Analyseberechnung wurden in dieser Ergänzung nicht geändert.

Die bestehende Messdiagnose benennt beide nativen Ankerarten, trennt Herkunftskonfidenz von musikalischer Genauigkeit und zeigt validierte native Phrasen-, Stem- und Embedding-Verfügbarkeit. Abdeckung, fehlende Kalibrierung und unbestätigtes Stem-Ausführungsgerät bleiben sichtbar. Keine neuen Ansichten oder Bedienelemente. Im Kandidatenvorfilter verworfene native Beatfenster liefern jetzt einen konkreten Ablehnungsgrund; erfolgreich qualifizierte Paare erhalten keine pauschale Warnung.

Neue Nachweise, keine Wiederholung bisher bestandener Fälle:
- `tests/test_native_product_completion.py`: 11 neue Fälle bestanden; Herkunft/Korrektur/Anker/BPM/Sperren beim Export, verständliche Diagnose, ungültige Payloads, vollständige und teilweise Kandidatenablehnung. Log: `TEMP/hpg-product-completion-tests-20261016.log`.
- `TEMP/hpg-native104-export-20261016/report.json`: tatsächliche XML- und M3U8-Exporter mit vorhandenen frischen Originaltrack-Snapshots und den Mixpunkten des erfolgreichen GUI-Plans. Zwei Tracks, zwei TEMPO-Grids, Mix-Cues nach XML-Readback korrekt. Metadaten ausschließlich im TEMP-Ausgabeordner; keine Audio-/Stem-/Modell-/Renderwiederholung. Kein neuer GUI-Exportklick behauptet.

Verbleibende Grenzen des Gesamtauftrags:
- Native Gesamtpipeline ist auf PCM16/Stereo/44100Hz, Modell7 und höchstens20Minuten beschränkt. Reader-/Modellwahl-Parität für weitere Eingaben ist nicht implementiert; dafür bleibt der vorhandene Fehlerfallback.
- Unabhängige Takt-/Phrasenlabels, Holdout-Qualitätsnachweis, blinde Hörbewertung und kalibrierte Stem-/Embedding-Gewichte fehlen. Daher bleiben Vocal-Schwelle und Klangfaktor diagnostisch, wie Phasen D/E verlangen. Automatische technische Erfolge ersetzen diese Freigabe nicht.
- Neuer Originalclip wurde im normalen GUI-Worker erzeugt und in RAM geladen, aber nach dem früheren negativen Nutzerurteil noch nicht erneut musikalisch abgenommen. Der vollständige frische GUI-Import bis menschlicher Bewertung bleibt offen.
- Unabhängige Wächter-Abschlussprüfung fehlt. Verfügbare Subagenten bieten ausschließlich den vom Nutzer ausgeschlossenen Priority-Service. Eine eigene Sichtung ist kein Ersatz. Kein neuer Volltest und kein EXE-Build.

Git-Auftrag: Änderungen sollen als nachvollziehbarer Entwicklungsstand gesichert werden, nicht als Release oder vollständige Abnahme. Das konfigurierte GitHub-Repository ist öffentlich. Originalmusik, Modelle, DLLs, private Rohbelege, Cachedateien und die lokale Chatübergabe gehören nicht in den Commit.

Commitfreigabe16.10.2026: Der Nutzer hat für diesen vorbereiteten Entwicklungsstand ausdrücklich „Einmalige Ausnahme: committen und pushen“ ohne unabhängige Wächterprüfung erlaubt. Das ersetzt keine fachliche Prüfung und ist keine dauerhafte Aufhebung des Wächtervertrags. Öffentliches Zielrepository wurde dabei ausdrücklich benannt; private Rohbelege, Modelle, Musik und die lokale Chatübergabe bleiben ausgeschlossen.


## Umsetzung 16.10.2026: nativer Reader und konfigurierte Modellwahl, Cache105

Implementiert: `native_audio_reader.py` verwendet die gepinnten WAV-/AIFF-Factories (RVA2cdda20/2cdd910), den nativen Dateistream, PCM-Decoder und Resampler (RVA1113330). Der synchrone native Lesemodus0 ersetzt die außerhalb der App unvollständige asynchrone Vorladekoordination. Keine Audio-Kopie, keine Änderung der Installation oder Originaldateien. Systemimporte werden explizit gebunden; die beiden aus RVA11236f9/112373c belegten privaten Resampler-Sperren werden initialisiert. Externe Codecplugins und der globale App-Factoryaufbau sind nicht übernommen.

`native_beat_selection.py` setzt den rekonstruierten Konfigurationsvertrag um: 3 verwendet Modell8/Einzelfenster, 4 Modell7/Fensterverkettung, 2 das native gespeicherte Modusbit aus RVA11db7d0. `HPG_NATIVE_BEAT_MODE` hat HPG-Default2 (Übernahme des nativen Modusbits); dies behauptet keinen Rekordbox-Default oder eine Zuordnung zu UI-Bezeichnungen. Die bisherige Entscheidung anhand der Tracklänge ist entfernt. Die DSP-Voranalyse, Modusübernahme und Endkorrektur laufen mit dem Reader im selben begrenzten Kindprozess. Modell8 verwendet das native Startfenster, begrenzt auf60s und die verfügbare Quelldauer. Ein Ereignis genau am Fensterende ist zulässig; Ereignisse darüber bleiben abgelehnt.

Cache105 und der Dienstfingerprint binden Readervertrag, Quell-/Ausgabezeitbasis, Modus und ausgewähltes Modell. Alte Snapshots sind keine Nachweise für den neuen Berechnungspfad. Die ursprünglichen Roh-Modellbeats bleiben als solche erhalten; die Audio-, Paar- und Renderfreigaben werden nicht abgeschwächt.

Ausgeführte gezielte Nachweise:
- 31 Vertragsfälle bestanden: erster Lauf29 bestanden/1 fehlgeschlagen (Testumgebung hatte native Analyse deaktiviert), genau dieser Fall nach expliziter Testaktivierung bestanden, danach1 neuer Grenzfalltest bestanden. Logs `TEMP/hpg-reader-selection-tests-20261016.log`, `TEMP/hpg-reader-selection-retest-20261016.log`, `TEMP/hpg-reader-endpoint-test-20261016.log`. Keine Wiederholung der bestandenen Fälle.
- Reader: synthetisches PCM16-WAV/AIFF zunächst samplegenau, 48kHz-Mono nach Initialisierung der nativen Resampler-Sperren erfolgreich. Der anschließend am vollständigen Original-WAV entdeckte Vorladefehler wurde durch den synchronen nativen Dateimodus behoben. Danach gesamtes Original-WAV samplegenau gegenüber PCM-Referenz, maximaler Fehler0: `TEMP/hpg-reader-proof-jzyb0tku/report.json`. Neue48kHz-Mono-Prüfung nach dieser relevanten Lesemodusänderung erfolgreich: `TEMP/hpg-reader-proof-zacd2rh3/report.json`. Frühere Teilbelege ersetzen diese Nachweise nicht.
- Original-WAV „You Never Alone“, Modell7/Modus4: `TEMP/hpg-native-reader-beat-20261016-run2.json`,12.687s,137.93BPM, erster nativer Taktanker1.3s, Original-SHA unverändert. Diese geänderten Werte sind ein technischer Laufbeleg, keine Verbesserung oder Freigabe der Taktposition.
- Original-AIFF „Never Die“, Modell8/Modus3: `TEMP/hpg-native-reader-model8-20261016-run3.json`,7.719s,138BPM, erster nativer Taktanker1.7385034013605443s, Original-SHA unverändert. Vorherige Modell8-Läufe scheiterten an der zu strengen60s-Endgrenze; Rohbelege bleiben erhalten.

Grenzen: zusätzliche Naht-/Grenznachverarbeitung des gesamten RVA1294100-Wrappers ist weiterhin nicht vollständig übernommen. Deshalb keine vollständige1:1-Rekordbox-Parität behaupten. Modus2 ist im Auswahlvertrag getestet; kein zusätzlicher Original-Modelllauf dafür. Neue Werte sind noch nicht im vollständigen GUI-Analyse-/Playlist-/Hörprobenablauf freigegeben. Musikalische Abnahme und unabhängiger Wächter fehlen. Keine Stem-Läufe, kein EXE-Build, kein Volltest. Die einmalige Commitausnahme galt dem bereits veröffentlichten vorherigen Entwicklungsstand; die jetzigen Änderungen sind noch nicht committed.

### Fortsetzung 16.10.2026: Cache108, zusätzliche Beatbelege und Attack-Messung

Die einzelne automatische Ablehnung meldete ausschließlich `blocked by policy`.
Ein weitergehender Grund ist nicht verfügbar. Der abgelehnte Vorschlag,
Bestätigungsfenster ohne Modellbeobachtung freizugeben, wurde nicht ausgeführt.

Stattdessen liefert beim 60s-Modell8 ein zusätzlicher originaler Modell7-Lauf
modellbeobachtete Beats des ganzen Tracks. Ausgewähltes Endgrid und Taktnummern
bleiben unverändert. Herkunft, Modellhashes, Zeitabdeckung und Beatfolge werden
validiert. Sechs disjunkte Audiofenster werden vor ihrer Phasenmessung anhand
regelmäßiger Modellbeats gewählt; keine Auswahl nach erfolgreichem Restfehler.

Die neue native Audio-Phasenmessung erfasst kurze breitbandige Anschläge oberhalb
300Hz statt den zeitlich variablen Basskörper. Die native Referenz beschränkt
nur die Ereignisfamilie; der gemessene Attack wird nicht auf das Grid gesetzt.
Rausch- und Stilleprüfung sowie die unveränderte 6ms-Grenze bleiben erforderlich.
Legacy-Analysen behalten ihre bisherige Messung. Renderer und native Analyse
tragen die Messmethode explizit weiter; musikalische Takt-1-Abnahme bleibt separat.

Neue Tests: vier Herkunfts-/Abdeckungsfälle, vier Attack-Fälle und zwei neue
Rendererfälle bestanden. Keine zuvor bestandenen Tests erneut ausgeführt.
Originalreader Harmonise: vollständiger Vergleich mit SoundFile, maximale
Sampleabweichung0 (TEMP/hpg-reader-proof-z4cdtd_e/report.json).
Der vollständige Produktlauf108 ist unter TEMP/hpg-original108-native-run1
angelegt; sein Ergebnis ist bei diesem Eintrag noch ausstehend. Keine Stem-Läufe,
keine EXE, keine unabhängige Wächter- oder musikalische Freigabe.

Abschluss der konkreten Fehlerkette, Cache109:
- Feste innere Quantile20/50/80% für Kalibrierung,10/35/65% für zusätzliche
  Bestätigungen; jeweils nächstes modellbeobachtetes regelmäßiges Fenster,
  sechs disjunkte Abschnitte, Auswahl ohne Kenntnis der Audio-Restfehler.
  Der zwischenzeitlich untersuchte schwächere Attack-Rauschzweig wurde verworfen.
- Native Kandidaten erhalten vor dem Ranking dieselbe lokale Vier-Beat-Attack-
  Prüfung wie der Renderer. Nur boolesche Ergebnisse im begrenzten RAM-LRU;
  Quellidentität verhindert Wiederverwendung nach einer Dateiänderung.
- Harmonic Flow durchsucht Pools bis6Tracks vollständig. Jede gerichtete
  Paarbewertung wird einmal berechnet. Damit geht eine durchgehende Kette vor
  einem höher bewerteten Einzelübergang mit anschließender Sackgasse.
- Quellreferenzformat2 speichert die Messmethode pro Deck. Laden, Discovery und
  Kandidatenaudit unterscheiden explizit Format1/2; alte Referenzen erhalten
  weiterhin ihre ursprüngliche Bass-Fold-Methode.

Produktnachweis TEMP/hpg-original109-completed/report.json, Exit0: Never Die
frisch analysiert; erfolgreiche Analyse-Snapshots von You Never Alone und
Harmonise aus Lauf108 ausdrücklich wiederverwendet. Alle3 native_rekordbox,
Grid verified, native Phrasen ok. Maximale Grid-Restfehler0.674/0.580/2.832ms.
Alle Original-SHA256 gleich. Keine Stem-Inferenz, keine Originalkopien.
Playlist You Never Alone → Never Die → Harmonise; beide RAM-Render erfolgreich,
115.652s und73.913s, endliche Samples, keine Reserve-Ablehnung.

GUI-Nachweis TEMP/hpg-native109-gui/gui-events.json: beide Clips geladen,
Index0/1, gui_cache_ready=true, rejected=0. Qt protokolliert beide WAV-Streams.
Das ist eine sichtbare Vorschau aus belegten Analyse-Snapshots, kein erneuter
GUI-Ordnerimport und keine menschliche musikalische Bewertung.
Neue gezielte Tests der ergänzten Verträge/Messungen/Reihenfolge erfolgreich;
keine zuvor bestandenen Testfälle erneut gestartet. Kein Volltest, kein EXE.
Unabhängiger Wächter, Commit/Push und musikalische Abnahme bleiben offen.

### Wächterkorrekturen 16.10.2026

Unabhängiger schreibgeschützter CLI-Review mit gpt-6-sol, service_tier=default,
reasoning_effort=medium: zwei Befunde. Die Default-Angabe ist auf Modus2
korrigiert. Das lokale Audio-Gate wird bei verifiziertem nativen Raster nun
auch ohne optionale model_beats ausgeführt, bevor die Modellprüfung zurückkehrt.
Der neue Regressionstest tests/test_native_candidate_missing_beats.py schlug
vorher fehl und bestand danach (1 Fall, 0,62s; TEMP/hpg-waechter109-gate-green.log).
Kein bestandener Test wiederholt, keine Stem-Inferenz, kein EXE-Build.
Der gespeicherte Analysevertrag bleibt Cache109; korrigiert wurde die
Kandidatenprüfung, nicht der persistierte Analyseoutput. Frühere Originalbelege
bleiben datiert; kein neuer Original- oder musikalischer Nachweis behauptet.
TOR1 wurde auf ausdrücklichen Nutzerwunsch auf den Abschluss verschoben;
eine historische Vorabfreigabe wird nicht nachträglich behauptet.

Nachprüfung: beide Erstbefunde behoben; kein konkretes Risiko im geprüften
Commitumfang. Bericht: docs/WAECHTER_CACHE109_2026-10-16.md. Urteil MIT AUFLAGEN
wegen fehlendem TOR1 nach Nutzeraufschub. Der Formularvalidator meldet nur
dieses fehlende TOR1-Urteil; keine formal vollständige Wächterfreigabe behauptet.
Der aktuelle Nutzerauftrag autorisiert Commit und Push des Entwicklungsstands.
Musikalische Abnahme, Gesamtfreigabe und EXE bleiben davon getrennt offen.
