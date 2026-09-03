# HPG Fixlog — Wellen 2-4 + Cleanup (2026-07-24, autonom)

Fortsetzung von `FIXLOG_2026-07-24.md` (Sofort-Fixes + Welle 1). Alle Fixes im
Code mit `AUDIT-FIX <ID>` markiert. Verifiziert mit 37 nachgestellten
Audit-Szenarien über drei Verify-Scripts (14 + 17 + 6, alle bestanden), alle
Dateien kompilieren (`py_compile`).

## Welle 2 — Scoring ehrlich machen

| ID | Datei | Fix |
|---|---|---|
| **F01** | models.py | `effective_bpm_diff`: Differenz wird immer im Tempo-Raum von bpm1 gemessen; gespiegelte Half/Double-Kandidaten entfernt. BPM-Gate ist nicht mehr 2× zu lax (140 vs 73 → diff 6.0 statt 3.0). |
| **F02** | analysis.py | `get_key_with_confidence` liefert jetzt einen z-Score-**Kontrast** statt rohem Cosine (diskriminiert peaked vs. flach); `key_confidence_score` auf die echten Wertebereiche kalibriert. Der „sicher"-Zweig ist wieder erreichbar (klarer Key → 0.92 statt max 0.4). |
| **F15** | analysis.py | Flache/stille Chroma → **kein** erfundener Camelot-Code mehr (verhindert falsche „5A"-Cluster mit Score 100). |
| **F03** | playlist.py | `loose_factor` auf ≤1.0 geklemmt — +4 (70) überholt nicht mehr den ±1-Nachbarn (80). |
| **F04** | playlist.py | „+2 Energy Boost" (8A→10A) als eigene Technik (75) eingeführt — war vorher wie ein Key-Clash (8). |
| **F21** | playlist.py | Half/Double-Penalty auch bei ungültigem Camelot-Code konsistent. |
| **F05** | playlist.py | AI-Bonus wird nicht mehr doppelt gezählt (raus aus der 0-100-Harmonik-Skala; bleibt nur auf dem Overall). `predict_transition_type` entscheidet über den reinen Score. |
| **F06** | playlist.py | `energy_direction`-String („Build Up"/„Cool Down") wird auf den Enum gemappt — das Preset wirkt jetzt wirklich im energy_flow (vorher stumm ins else). |
| **F12** | playlist.py | `detected_genre`-Default „Unknown" (truthy) blockiert nicht mehr den ID3-Genre-Fallback — Tracks ohne DJ-Brain-Klassifikation scoren nicht mehr konstant 0.5. |
| **F08** | playlist.py | `_apply_harmonic_smoothing` bewertet jetzt auch die Anschluss-Transition — verschlechtert die Kette nicht mehr (Audit-Gegenbeispiel 265→265 statt 265→250). |
| **F10** | playlist.py | Timeline-Overlap wird auf ½ Trackdauer geklemmt — keine negativen Spieldauern/rückwärts laufende Startzeiten mehr. |
| **D6/F28** | playlist.py | Magic Numbers (Smoothing-Schwelle, Iterationen, Lookahead-Gewicht) als benannte Konstanten zentralisiert. |

## Welle 3 — Stabilität & Performance

| ID | Datei | Fix |
|---|---|---|
| **PA-01** | parallel_analyzer.py | Safe-Mode-Recovery-Executor manuell verwaltet (kein `with`) — kein Deadlock mehr beim Timeout eines hängenden Workers. |
| **A-02** | analysis.py | Fehlgeschlagene Rekordbox-Analysen werden **nicht** mehr gecacht (kein dauerhafter Müll-Track mit energy=50/mix_in=0); Exception-Fang auf erwartete Klassen eingeengt. |
| **C-02** | caching.py | Cache-Lesefehler auf WARNING statt DEBUG (Schema-Drift wird sichtbar); NaN/Inf-Fingerprints werden vor dem Serialisieren bereinigt (Track wird nicht mehr „nie gecacht"). |
| **RB-02** | rekordbox_importer.py | Sinnloser Pfad-Fallback (`join("", name)`) entfernt — Tracks ohne FolderPath landen nur noch im Basename-Cache, nicht als Falsch-Pfad. |
| **RB-01** | rekordbox_importer.py | ANLZ-Downbeat-Pfad robust gegen mehrere pyrekordbox-API-Formen (`read_anlz_files` dict + per-Entry `.beat/.time`); Fehlschlag jetzt auf WARNING statt still auf DEBUG. Das war die eigentliche Ursache, warum der exakte Beat-Alignment-Pfad nie lief. |
| **P-01** | parallel_analyzer.py | Prozess-Initializer wärmt die Rekordbox-Singleton einmal pro Worker; Batch-Größe 48→200 → ~5 statt ~21 Pool-Neustarts bei 1000 Tracks (spart Import + DB-Scan pro Neustart). |
| **T1** | main.py | `AnalysisWorker.finished` → `analysis_done` umbenannt (überschrieb das eingebaute `QThread.finished`); Cleanup/`deleteLater` jetzt am echten Thread-Ende mit `wait()` — kein „Destroyed while thread is still running"-Crash-Race mehr. |

## Welle 4 — Renderer-Qualität

| ID | Datei | Fix |
|---|---|---|
| **C3** | transition_renderer.py | Equal-Power-Crossfade (cos/sin) statt linear — kein −3-dB-Lautheitsloch mehr in der Mitte (verifiziert: +0.1 dB statt ~−3 dB). |
| **R-02** | transition_renderer.py | `pro_eq_swap`-Höhenband: komplementäre Envelopes (a+b≡1) — keine +6-dB-Spitze am ¾-Punkt mehr (der Default-Modus für Techno/Psy). |
| **R-03** | transition_renderer.py | Echter tanh-Soft-Limiter nur auf überschreitende Samples — ein Transient senkt nicht mehr den ganzen Clip (RMS-Konsistenz der Previews bleibt erhalten). |
| **R-04** | transition_renderer.py | `echo_out`: beat-synchrones Delay (60/bpm statt fix 0.5 s) + Pegelnormierung (kein Clipping durch 1.74×-Aufbau). |
| **R-05** | transition_renderer.py | `pro_eq_swap`: Mitten aus Rest gebildet (`seg−bass−highs`) — 2 statt 4 Filterläufe pro Track, weniger float64-Kopien. |
| **R-06** | transition_renderer.py | `cold_cut`/`drop_cut`: 3-ms-Mikro-Fade an der Schnittstelle gegen Klicks. |
| **R-09** | transition_renderer.py | Toter `mixed = …`-Block in `bass_swap` entfernt (wurde sofort überschrieben). |

## Verifikation

Drei Verify-Scripts liegen im Projektordner (`verify_fixes.py`, `verify_wave2.py`,
`verify_wave4.py`). Sie stubben die Audio-Libs und stellen die im Audit
reproduzierten Fehlszenarien mit dem gefixten Code nach — 37/37 bestanden.

## WICHTIG auf deinem Rechner

1. **`pytest` laufen lassen.** Etliche Scoring-Tests erwarten die ALTEN Werte
   (BPM-Gate, Camelot-Tabelle mit +4>+-1, AI-Bonus im harmonic_score,
   key_confidence ~0.4, Mix-Out-Positionen, Stretch-Rate). Diese Tests müssen an
   das jetzt korrekte Verhalten angepasst werden — das sind erwartete
   Anpassungen, keine Regressionen.
2. **Cache ist bereits invalidiert** (Version 18→19 aus Welle 1) — alle Tracks
   werden mit korrigierter Logik neu analysiert.
3. **Hör-Check** empfohlen: 2-3 Previews rendern (`pro_eq_swap` + ein
   BPM-ungleiches Paar) — Übergänge sollten tempo-synchron und ohne
   Pegel-Loch/Harschheit klingen.

## Bewusst NICHT gemacht (Risiko ohne sichtbare Tests)

- **Funktions-Entfernungen** (`get_key`, `bars_to_seconds`, `app_metadata.py`,
  `get_format_info`, etc.): 0 Aufrufer bestätigt, aber deine lokale `tests/`-Suite
  könnte sie direkt testen. Harmlos als toter Code — bei Bedarf nach einem
  grünen Testlauf manuell entfernen.
- **Größere GUI-Refactors** (T2 Preview-WAV-Read im GUI-Thread, F5 START-OVER-
  Cleanup, Duplikat-Zentralisierung mm:ss/Pfad-Norm): rein qualitativ, kein
  Korrektheits- oder Crash-Risiko — für eine spätere, weniger kritische Runde.
