# Unabhängiges Validierungs- und DJ-Blindtest-Protokoll

Stand: 2026-07-20

## Beweisgrenze

Dieses Protokoll erzeugt keine Labels und keine Qualitätsbehauptung. Labels müssen von Personen oder Quellen stammen, die nicht aus HPG-Ausgaben abgeleitet wurden. Dateinamen gelten nur dann als Ground Truth, wenn ihre Herkunft und Qualität unabhängig belegt ist.

## Track-Korpus

Mindestens 100 legal verfügbare, reale Tracks aus den tatsächlich unterstützten Formaten WAV, AIFF, FLAC und MP3. Für Genre-Aussagen mindestens 20 Tracks je bewerteter Klasse. Jede adjudizierte Zeile in `validation/ground_truth_template.csv` braucht eine stabile `track_id`, den SHA-256 des Audios, Quelle, zwei Annotatoren, Adjudikator und Status (`draft`, `adjudicated`, `excluded`). Audio-Dateien selbst werden wegen Lizenz- und Datenschutzrisiken nicht ins Repository aufgenommen.

- BPM: Referenz aus verifiziertem Beatgrid oder manueller Tap-/Grid-Prüfung durch zwei Annotatoren.
- Key: unabhängige musikalische Prüfung; enharmonische Schreibweisen vor der Auswertung normalisieren.
- Genre: kuratiertes Label mit dokumentierter Taxonomie; Mehrdeutigkeiten in `notes` festhalten.
- Sections und Cues: Zeiten in Sekunden, durch zwei DJs markiert und bei Abweichungen adjudiziert.

Vorhersagen werden gemäß `validation/predictions_template.json` mit deaktiviertem Rekordbox-Fast-Path aus exakt den gehashten Audiodateien erzeugt:

```powershell
venv312\Scripts\python.exe tools\run_ground_truth_predictions.py `
  --ground-truth validation\ground_truth.csv `
  --output validation\predictions.json
```

`--allow-rekordbox` ist ein separater, ausdrücklich zu kennzeichnender Fast-Path-Versuch und darf nicht mit der Eigenanalyse-Messung vermischt werden. Anschließend erfolgt die Auswertung:

```powershell
venv312\Scripts\python.exe tools\evaluate_ground_truth.py `
  --ground-truth validation\ground_truth.csv `
  --predictions validation\predictions.json `
  --output validation\metrics.json
```

Nur `adjudicated`-Zeilen fließen in Metriken ein. Fehlende Labels und Vorhersagen werden als Coverage ausgewiesen und niemals als korrekt gezählt; Accuracy-Werte dürfen nur zusammen mit ihrer Prediction-Coverage berichtet werden. BPM wird zusätzlich half-/double-time-tolerant bewertet. Key-Ergebnisse unterscheiden exakt, relative Dur/Moll, Quinte, falsch und ungültig. Sektionsgrenzen werden mit ±2 Sekunden und maximalem Eins-zu-eins-Matching bewertet. Der Ergebnisbericht enthält die Hashes beider Eingabedateien sowie die vom Prediction-Dokument gelieferte App-/Commit-/Konfigurationsprovenienz.

## Verblindeter DJ-Hörtest

Für mindestens 30 Übergangspaare werden zwei lautheitsangepasste Clips gleicher Länge erzeugt: HPG und eine vorab definierte Baseline. Eine dritte Person randomisiert A/B und verwahrt den Schlüssel. Die Evaluatoren sehen weder Algorithmusname noch interne Scores und verwenden `validation/dj_blind_test_template.csv`.

Ein Manifest mit `pair_id,hpg_clip,baseline_clip` wird ohne Überschreiben in neutrale Dateinamen kopiert:

```powershell
venv312\Scripts\python.exe tools\prepare_dj_blind_test.py `
  --manifest validation\blind_pairs.csv `
  --output-dir validation\blind_session_001 `
  --key-output C:\private\blind_session_001_key.csv
```

Nur `blind_session.csv` und den Ordner `clips` an Evaluatoren geben. Die separat erzeugte Schlüsseldatei bleibt bis zum Abschluss getrennt verwahrt. Das Werkzeug balanciert die HPG-Seite bis auf höchstens ein Paar, randomisiert die Paarreihenfolge und re-encodiert beide Kandidaten metadatenfrei als PCM-WAV. Es verweigert unterschiedliche Dauer (mehr als 10 ms), Samplerate oder Kanalzahl. Die Lautheitsanpassung muss vorab erfolgen und wird von diesem Werkzeug nicht als LUFS-Messung bestätigt.

Jeder Clip wird von mindestens drei DJs über dieselbe Abhörkette bewertet. Primärer Endpunkt ist die erzwungene A/B-Präferenz; Smoothness, Phrase Alignment, Energy Flow und Clash-Freiheit (1–5) sind sekundär. Reihenfolge und Kandidatenseite werden ausbalanciert. Abgebrochene oder technisch fehlerhafte Sessions werden mit Grund ausgeschlossen, nicht ersetzt. Erst nach Abschluss aller Bewertungen wird entblindet und die Präferenz mit Konfidenzintervall berichtet.

Die statistische Aggregation und das Konfidenzintervall sind noch nicht automatisiert; sie müssen vor einer Qualitätsbehauptung separat implementiert oder unabhängig ausgewertet und dokumentiert werden.

## Nicht abgedeckt

Der automatisierte Test ersetzt keine Langzeitnutzung, keine Prüfung auf allen Audio-Treibern/Codecs und kein unabhängiges Hörurteil. Ohne ausgefülltes, adjudiziertes Korpus und abgeschlossenen Blindtest bleibt musikalische Korrektheit unbewiesen.
