---
name: hpg-parallel-performance
description: Use when HPG analysis is slow, hangs, or crashes workers — ParallelAnalyzer, Worker-Anzahl, BrokenProcessPool, Per-Task-Timeout, Haenger-Deadline, Cancel, Batch-Groesse, oder wenn Performance-Optimierungen an der Analyse-Pipeline geplant sind.
---

# HPG Parallel & Performance

## Worker-Anzahl (`get_optimal_worker_count` [parallel_analyzer.py:30])

```
explizites config.PARALLEL_MAX_WORKERS  -> min(cpu_count, wert)
sonst max_workers = min( max(min(6, cpu), cpu // 2),
                         config.PARALLEL_AUTO_MAX_WORKERS )   # = 4
dann Workload-Skalierung:
  < 5 Dateien   -> 1     (Windows-Spawn-Overhead frisst den Gewinn)
  < 10 Dateien  -> 2
  < 20 Dateien  -> min(cpu, max(4, max_workers // 2))
  >= 20         -> max_workers
```

**Die harte Obergrenze ist 4** [config.py:108], unabhaengig von der Kernzahl.
Grund im Docstring: mehr als vier parallele native Audio-Decoder fuehren unter
Windows zu C-Level-Abstuerzen des Pools. Beispiele: 8 Dateien / 16 Kerne -> 2
Worker; 200 Dateien / 16 Kerne -> 4 Worker.

Wer diese Grenze anhebt, muss mit realen grossen AIFF/WAV testen, nicht mit
Fixtures.

## In-Flight-Fenster — der Kern des Timeout-Vertrags

`BATCH_SIZE = min(200, max(worker_count * 2, total // 4))` [:168], aber
**hoechstens `worker_count` Futures gleichzeitig eingereiht** (`submit_available`
[:219]). Ohne das war `future.result(timeout=...)` wirkungslos: die Futures
waren beim Aufruf laengst fertig oder standen noch in der Queue.

Zwei unabhaengige Uhren:

| Uhr | Konstante | Bedeutung |
|---|---|---|
| Per-Task | `PARALLEL_ANALYSIS_TIMEOUT = 60` s | Laufzeit **eines** aktiven Futures. Ueberschritten -> `[TIMEOUT]`, Pool terminieren |
| Haenger | `min(PARALLEL_HANG_DEADLINE_MAX = 900, TIMEOUT * worker + 30)` | **Inaktivitaets**-Deadline: nur wenn gar kein Future mehr fertig wird. Waechst nicht mit der Batch-Groesse (N-04) |

## Recovery ist Design, kein Bug

- `BrokenProcessPool` -> Pool als kaputt markieren, terminieren, restliche
  Dateien einzeln in einem **wiederverwendeten** Recovery-Executor
  (`max_workers=1`, [:382]) nachfahren
- crasht auch der: diese eine Datei wird `[CRASHED/SKIPPED]` (Track `None`)
- Logzeile lesen und fragen *welche Datei* korrupt ist — nicht den Mechanismus
  reparieren

`_worker_init` [:74] waermt Imports im Kindprozess vor. Ohne den zahlte jeder
neue Pool librosa-Import + Rekordbox-DB-Scan.

## Cancel

`analyze_files(..., cancel_callback=...)`; `AnalysisWorker.request_cancel`
setzt nur ein Flag. Der Pool pollt kooperativ (`wait(..., timeout=0.5)`) und
ruft `_terminate_executor_processes` [:21]. Wer einen neuen langlaufenden
Pfad baut, muss das Callback durchreichen — sonst haengt Abbruch.

## Performance-Hebel (mit Messung, nicht mit Gefuehl)

1. `FeatureCache` benutzen statt neu rechnen (HPSS/STFT waren 7-11x/Track)
2. Rekordbox-Fast-Path nicht kaputtmachen (~12x) — Skill `hpg-rekordbox`
3. `_COMPAT_CACHE`/`_ENHANCED_COMPAT_CACHE` in `generate_playlist`
4. `LOOKAHEAD_TOP_K = 8` begrenzt die Harmonic-Flow-Rekursion
5. `MAX_SSM_FRAMES = 3000` [structure_analyzer.py] deckelt die
   Self-Similarity-Matrix (~72 MB); ohne das gab es 1,3 GB/Track

Messen: `tests/performance_fixtures.py` (vor-analysierte Tracks, kein Audio
noetig) und `benchmark_rekordbox.py`. Fuer echte Audio-Laeufe
`tools/validation_run.py`.

## Vor jeder Speicher-Optimierung

Limits im Blick behalten: `SECURITY_MAX_FILE_SIZE` 500 MB,
`SECURITY_MAX_TRACK_DURATION` 7200 s, `SECURITY_MAX_PLAYLIST_SIZE` 1000.
LUFS wird ueber `sf.blocks` gemessen — nicht auf Voll-Decode zurueckbauen.

## Common Mistakes

- Worker-Cap 4 "optimieren" ohne Windows-Test mit grossen Lossless-Dateien.
- Mehr Futures einreihen als Worker -> Per-Task-Timeout wird wieder blind.
- Timeout innerhalb `with ProcessPoolExecutor(...)` werfen: `__exit__` macht
  `shutdown(wait=True)` und wartet auf den haengenden Worker (GUI friert ein).
  Executor manuell verwalten.
- `BrokenProcessPool` als Bug behandeln.
