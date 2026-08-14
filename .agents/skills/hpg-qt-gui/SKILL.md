---
name: hpg-qt-gui
description: Use when working on the HPG PyQt6 GUI in main.py — QThread-Worker, pyqtSignals, RunState, Worker-Lifecycle und "Destroyed while thread is still running", Panels/Delegates/Tabellenspalten, Theme-Farben, Shortcuts, Fortschrittsanzeige oder UI-Freezes.
---

# HPG Qt / GUI

## Architektur

`main.py` (4868 Zeilen) enthaelt **alles**: Worker, Widgets, Panels,
MainWindow. Es gibt kein `ui/`-Paket (alte Doku behauptet das).

Fuenf Panels in einem `QStackedWidget`, umgeschaltet von `SidebarWidget`
[:1812]: LIBRARY(0) PLAYLIST(1) MIX TIPS(2) TIMELINE(3) QUALITY(4).
Shortcuts: `Ctrl+G` generieren, `Ctrl+E` exportieren, `Ctrl+1..5` Panel
[`_setup_shortcuts` :4036].

## Die eine Thread-Regel

**Business-Logik im QThread, UI-Update ausschliesslich per `pyqtSignal`.**
Kein Widget-Zugriff aus `run()`, kein manuelles Marshalling.

Worker in main.py: `AnalysisWorker` [:457], `AIAnalysisWorker` [:216],
`AIDetectWorker`, `AITestWorker`, `AIPullWorker`, `DependencyCheckWorker`,
`TransitionRenderWorker` [:632], Peak-Worker fuer die Wellenform.

## Worker-Muster (vier Pflichtteile)

```python
class MyWorker(QThread):
    progress = pyqtSignal(int)
    work_done = pyqtSignal(list, dict)   # NIE "finished" nennen

    def run(self):
        try:
            ...
            self.work_done.emit(result, meta)
        except Exception as e:
            self.work_done.emit([], {})   # Worker werfen nie nach oben
```

1. **Eigener Ergebnis-Name.** `AnalysisWorker` heisst das Signal
   `analysis_done` [:468]. `finished` ist von `QThread` belegt; ueberschreibt
   man es, meldet nichts mehr das echte Thread-Ende und `deleteLater()` trifft
   einen noch laufenden Thread ("QThread: Destroyed while thread is still
   running").
2. **Cleanup an `QThread.finished` haengen**, nicht ans Ergebnis-Signal:
   `worker.finished.connect(lambda w=worker: self._cleanup(w))`, dort
   `worker.wait(2000)` + `worker.deleteLater()` + Referenz auf `None`
   [`_cleanup_analysis_worker` :4202].
3. **Source-Guard in jedem Slot.** Jeder Callback nimmt `source_worker=None`
   und kehrt sofort zurueck, wenn `source_worker is not self.worker`. Ohne das
   ueberschreibt ein verwaister Alt-Worker die Statuszeile des neuen Laufs.
4. **Kooperativer Cancel**: `request_cancel()` setzt ein Flag, `run()` prueft
   es und wirft `InterruptedError`. Nie `terminate()` als Normalweg.

## RunState — die einzige Wahrheit

`RunState` [:144]: IDLE · AUDIO · AI · PLAYLIST · PREVIEW · CANCELLING ·
SUCCESS · PARTIAL · ERROR · CANCELLED. `ACTIVE_RUN_STATES` [:160] = AUDIO,
AI, PLAYLIST, PREVIEW, CANCELLING.

- `_set_run_state` [:4100] koppelt die Reorder-Sperre an den Zustand (nur
  waehrend `AI` gesperrt)
- `_run_is_active` [:4110] prueft Zustand **und** alle mutierenden Worker
  inklusive `mix_tips_panel._render_worker` — `RunState.PREVIEW` wird nie
  gesetzt, ohne den Worker-Check galte ein laufender Preview-Render als
  inaktiv
- `_finish_run` [:4125] stellt in **jedem** terminalen Pfad dieselbe UI her

Neue Terminalpfade immer ueber `_finish_run` fuehren.

## Fortschritt

Audio-Analyse = 0-80 %, KI = 80-95 %, Rest Playlist/Preview. Mapping ueber
`map_phase_progress(percent, start, end)` [:168]. Die Slots pruefen den
`run_state`, bevor sie den Balken anfassen. Updates sind auf 100 ms gedrosselt.

## Peak-Worker / Wellenform

`_PEAK_WORKERS` ist ein Modul-Set; `stop_peaks(wait_ms)` [:811] macht
`requestInterruption()` + `wait()` und faengt `RuntimeError` (C++-Objekt schon
weg). Aufgerufen aus `_cleanup_existing_previews` und `closeEvent`. Ein
laufender QThread darf **nie** per GC/`deleteLater` sterben.

## Panels und Tabelle

`PlaylistPanel` [:2642] hat **16 Spalten** (0-15): # · Track Name · Artist ·
Duration · BPM · Key · Camelot · Energy · Genre · Genre % · Mix In · Mix Out ·
Bass % · Texture · Passung(14) · AI Insights(15). Spalte 7 nutzt
`EnergyBarDelegate`, Spalte 14 `TransitionScoreDelegate`. Wer eine Spalte einfuegt, muss
`setHorizontalHeaderLabels`, die Tooltip-Liste, `setColumnWidth`, die
Delegate-Indizes, `_populate_table` **und** `_update_table_after_reorder`
anfassen — der Spaltenindex steht an sechs Stellen.

Farben und Labels kommen aus `hpg_core/theme.py` (`COLORS`, `GENRE_COLORS`,
`PHASE_*`, `TRANSITION_TYPE_*`, `TRANSITION_SCORE_STYLES`,
`transition_score_style`, `score_color`, `get_7_scale_color`). Keine
Hex-Farben in `main.py` hartkodieren.

## Fehler sichtbar machen

`get_error_reporter().log_error(...)` in Worker-Exception-Pfaden; Sink ist
`logs/error_report.json`, Rotation 200 Eintraege. Ein globaler `excepthook`
[:4831] faengt den Rest.

## Common Mistakes

- UI aus `run()` anfassen.
- Ergebnis-Signal `finished` nennen.
- Cleanup ans Ergebnis-Signal statt an `QThread.finished` haengen.
- Source-Guard vergessen -> Statuszeile flackert zwischen Laeufen.
- Grosse WAV-Datei im GUI-Thread lesen -> sichtbarer Freeze; in den Worker.
- Neue Spalte nur an einer Stelle eintragen.
