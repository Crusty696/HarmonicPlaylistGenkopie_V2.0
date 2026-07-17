# Feature Plan: Transition Audio Preview

**Status:** Bereit zur Implementierung
**Datum:** 2026-02-28
**Ziel:** Nach der Playlist-Generierung kann der User jeden Übergang in der Playlist anhören — er hört Track A (letzten Abschnitt), dann beide Tracks zusammen (den Crossfade-Mix), dann Track B (ersten Abschnitt). Pro Übergang eine WAV-Datei, abspielbar direkt in der App.

---

## 1. Verifizierende Erkenntnisse (Research-Phase)

### Technologie-Stack — BESTÄTIGT, KEIN NEUES PIP-INSTALL

| Aufgabe | Bibliothek | Status |
|---------|-----------|--------|
| Audio-Segment laden | `soundfile 0.13.1` | ✅ bereits installiert (librosa-Dep) |
| Lowpass/Highpass-Filter | `scipy.signal.butter + sosfiltfilt` | ✅ scipy 1.17.0 vorhanden |
| Numpy-Array-Mischen | `numpy 2.3.5` | ✅ vorhanden |
| WAV-Export | `soundfile.write()` | ✅ PCM_16, 44100Hz Stereo |
| Playback in PyQt6 | `QMediaPlayer + QAudioOutput` | ✅ PyQt6 6.10.2, FFmpeg-Plugin vorhanden |

**PyQt6 FFmpeg-DLLs** (in `site-packages/PyQt6/Qt6/bin/`):
- `avcodec-61.dll`, `avformat-61.dll`, `avutil-59.dll`, `swresample-5.dll`, `swscale-8.dll`
- `ffmpegmediaplugin.dll` + `windowsmediaplugin.dll` in `plugins/multimedia/`
- `QMediaPlayer` hat: `positionChanged`, `durationChanged`, `errorOccurred`, `setPosition()`

**Bewusst NICHT verwendet:**
- `pydub` — overhead ohne Mehrwert, braucht ffmpeg für MP3
- `sounddevice` — threading-Problem auf Windows+PyQt6 (WASAPI-Konflikt)
- `pedalboard` — optional für später (bessere Filterqualität), jetzt nicht nötig

---

## 2. Was der User sehen/hören soll

Nach der Playlist-Generierung erscheint in der **MixTips-Ansicht** pro Übergang:

```
┌─────────────────────────────────────────────────────────────┐
│  Übergang 3: "Orbital - Halcyon" → "Underworld - Born Slippy"│
│                                                             │
│  [▶ Vorschau]  [■]   ████████░░░░░░░░  0:23 / 1:15         │
│                                                             │
│  Track A: letzte 30s  |  Crossfade: 16s  |  Track B: 30s   │
│  Status: Bereit       Typ: bass_swap      Risk: Mittel      │
└─────────────────────────────────────────────────────────────┘
```

Der Clip ist aufgebaut als:
- **0:00 - 0:30**: Nur Track A (letzter Abschnitt vor dem Mix-Out-Punkt)
- **0:30 - 0:46**: Crossfade (beide Tracks + EQ-Bass-Swap)
- **0:46 - 1:15**: Nur Track B (erster Abschnitt ab Mix-In-Punkt)

---

## 3. Datenfluss

```
Playlist-Generierung abgeschlossen
          │
          ▼
TransitionRecommendation (bereits vorhanden in models.py):
  - from_track.filePath           (Track A Pfad)
  - to_track.filePath             (Track B Pfad)
  - from_track.mix_out_point      (float, Sekunden)
  - to_track.mix_in_point         (float, Sekunden)
  - overlap                       (float, Sekunden = Crossfade-Dauer)
  - transition_type               (str: bass_swap, smooth_blend, ...)
          │
          ▼
TransitionRenderWorker(QThread)
  → transition_renderer.render_transition_clip()
  → Speichert WAV in tempfile.gettempdir() / "hpg_preview_{i}.wav"
  → Emittiert: clip_ready(index, wav_path) oder clip_error(index, error_msg)
          │
          ▼
MixTipsPanel
  → Empfängt clip_ready Signal
  → Aktiviert Play-Button für den jeweiligen Übergang
  → QMediaPlayer.setSource(QUrl.fromLocalFile(wav_path))
  → Slider und Zeitanzeige via positionChanged / durationChanged
```

---

## 4. Neue Datei: `hpg_core/transition_renderer.py`

**Zweck:** Reine Berechnung — keine GUI, keine Qt-Imports.

### 4.1 Aufbau

```python
"""
hpg_core/transition_renderer.py

Rendert einen Transition-Preview-Clip als WAV-Datei.
Verwendet: scipy.signal (EQ-Filter) + soundfile (I/O) + numpy (Mix)
Keine neuen pip-Abhaengigkeiten noetig.
"""

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt
from dataclasses import dataclass
from pathlib import Path
import tempfile
import os


@dataclass
class TransitionClipSpec:
    """Parameter fuer einen Transition-Preview-Clip."""
    track_a_path: str          # Voller Dateipfad zu Track A
    track_b_path: str          # Voller Dateipfad zu Track B
    mix_out_sec: float         # Position in Track A, wo Crossfade beginnt
    mix_in_sec: float          # Position in Track B, wo Crossfade beginnt
    crossfade_sec: float       # Laenge des Crossfade-Bereichs (Sekunden)
    transition_type: str       # "bass_swap", "smooth_blend", etc.
    pre_roll_sec: float = 30.0 # Sekunden von Track A VOR dem Crossfade
    post_roll_sec: float = 30.0# Sekunden von Track B NACH dem Crossfade
    bass_cutoff_hz: float = 200.0
    target_sr: int = 44100


def render_transition_clip(spec: TransitionClipSpec, output_path: str) -> str:
    """Hauptfunktion: rendert den Clip und speichert als WAV."""
    ...  # Details in 4.2

def _load_segment(path, start_sec, duration_sec, target_sr=44100) -> np.ndarray:
    """Laedt ein Audio-Segment als float32 (frames, 2) Array."""
    ...  # Details in 4.3

def _make_sos(cutoff_hz, sr, btype, order=4) -> np.ndarray:
    """Butter-Filter als SOS."""
    return butter(order, cutoff_hz, btype=btype, fs=sr, output='sos')

def _apply_bass_swap(seg_a, seg_b, crossfade_frames, sr, bass_cutoff_hz) -> np.ndarray:
    """Bass-Swap EQ Crossfade zwischen seg_a und seg_b."""
    ...  # Details in 4.4
```

### 4.2 `render_transition_clip()` — vollständige Logik

```python
def render_transition_clip(spec: TransitionClipSpec, output_path: str) -> str:
    """
    Struktur des Output-Clips:
        [pre_roll]  |  [crossfade]  |  [post_roll]
        Track A      beides          Track B

    Lade-Strategie:
        Track A: start = mix_out_sec - pre_roll_sec, duration = pre_roll_sec + crossfade_sec
        Track B: start = mix_in_sec,                duration = crossfade_sec + post_roll_sec
    """
    sr = spec.target_sr
    cf_sec = min(spec.crossfade_sec, 32.0)  # Max 32s Crossfade (Sicherheit)

    # Segmente laden
    a_start = max(0.0, spec.mix_out_sec - spec.pre_roll_sec)
    a_dur   = spec.pre_roll_sec + cf_sec
    b_start = max(0.0, spec.mix_in_sec)
    b_dur   = cf_sec + spec.post_roll_sec

    seg_a = _load_segment(spec.track_a_path, a_start, a_dur, sr)
    seg_b = _load_segment(spec.track_b_path, b_start, b_dur, sr)

    cf_frames  = int(cf_sec * sr)
    pre_frames = int(spec.pre_roll_sec * sr)
    post_frames= int(spec.post_roll_sec * sr)

    # Sicherstellen: Segmente sind lang genug
    def _ensure_len(arr, n):
        if len(arr) < n:
            pad = np.zeros((n - len(arr), 2), dtype=np.float32)
            return np.concatenate([arr, pad])
        return arr[:n]

    seg_a = _ensure_len(seg_a, pre_frames + cf_frames)
    seg_b = _ensure_len(seg_b, cf_frames + post_frames)

    # Clip-Teile aufbauen
    # Teil 1: Pre-Roll — nur Track A (keine Bearbeitung)
    part_pre   = seg_a[:pre_frames]

    # Teil 2: Crossfade — EQ-Mix der letzten cf_frames von A + ersten cf_frames von B
    a_cf = seg_a[pre_frames:]                  # (cf_frames, 2)
    b_cf = seg_b[:cf_frames]                   # (cf_frames, 2)
    part_cf = _apply_eq_crossfade(
        a_cf, b_cf, cf_frames, sr,
        spec.bass_cutoff_hz, spec.transition_type
    )

    # Teil 3: Post-Roll — nur Track B (keine Bearbeitung)
    part_post  = seg_b[cf_frames:]

    # Zusammenfuegen
    mixed = np.concatenate([part_pre, part_cf, part_post], axis=0)

    # Soft-Limiter (kein hartes Clipping)
    peak = np.max(np.abs(mixed))
    if peak > 0.95:
        mixed = (mixed * 0.95 / peak)

    # Exportieren
    sf.write(output_path, mixed.astype(np.float32), samplerate=sr, subtype='PCM_16')
    return output_path
```

### 4.3 `_load_segment()` — Details

```python
def _load_segment(path: str, start_sec: float, duration_sec: float,
                  target_sr: int = 44100) -> np.ndarray:
    """
    Laedt nur den benoetigten Abschnitt (kein volles File im RAM).
    soundfile unterstuetzt: WAV, FLAC, AIFF nativ.
    MP3 wird von soundfile NICHT unterstuetzt → Fallback via librosa.
    Gibt immer (frames, 2) float32 zurueck (Mono wird gedoppelt).
    """
    path = str(path)

    # soundfile-Pfad (WAV, FLAC, AIFF)
    try:
        with sf.SoundFile(path) as f:
            sr_file = f.samplerate
            start_frame = int(start_sec * sr_file)
            num_frames  = int(duration_sec * sr_file)
            f.seek(max(0, start_frame))
            audio = f.read(num_frames, dtype='float32', always_2d=True)
    except sf.LibsndfileError:
        # Fallback fuer MP3: librosa (langsamer, aber korrekt)
        import librosa
        y, sr_file = librosa.load(path, sr=None, mono=False,
                                   offset=start_sec, duration=duration_sec)
        if y.ndim == 1:
            y = np.stack([y, y], axis=0)
        audio = y.T.astype(np.float32)  # (frames, channels)

    # Mono → Stereo
    if audio.ndim == 1:
        audio = audio[:, np.newaxis]
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        audio = audio[:, :2]  # Auf Stereo beschraenken

    # Sample-Rate-Konvertierung wenn noetig (Ausnahme, meist 44100)
    if sr_file != target_sr:
        import librosa
        # librosa.resample erwartet (channels, frames), gibt (channels, frames)
        audio = librosa.resample(audio.T, orig_sr=sr_file, target_sr=target_sr).T

    return audio.astype(np.float32)
```

### 4.4 `_apply_eq_crossfade()` — EQ-Typen

```python
def _apply_eq_crossfade(
    seg_a: np.ndarray,  # (cf_frames, 2) float32 — Track A im Crossfade-Bereich
    seg_b: np.ndarray,  # (cf_frames, 2) float32 — Track B im Crossfade-Bereich
    cf_frames: int,
    sr: int,
    bass_cutoff_hz: float,
    transition_type: str,
) -> np.ndarray:
    """
    Wendet EQ-basierten Crossfade an.
    Fader-Envelope: linear 1.0 → 0.0 (Track A) und 0.0 → 1.0 (Track B).
    """
    fo = np.linspace(1.0, 0.0, cf_frames, dtype=np.float32)[:, np.newaxis]  # fade_out
    fi = np.linspace(0.0, 1.0, cf_frames, dtype=np.float32)[:, np.newaxis]  # fade_in

    if transition_type == "bass_swap":
        # Bass (Tief) und Hoehen trennen, Bass versetzt faden
        sos_lp = _make_sos(bass_cutoff_hz, sr, 'low')
        sos_hp = _make_sos(bass_cutoff_hz, sr, 'high')
        # Hoehen: normaler Crossfade
        mixed = sosfiltfilt(sos_hp, seg_a, axis=0) * fo + \
                sosfiltfilt(sos_hp, seg_b, axis=0) * fi
        # Bass von Track A bleibt laenger, Bass von Track B kommt spaeter
        bass_a_fo = np.linspace(1.0, 0.0, cf_frames, dtype=np.float32)
        bass_a_fo = np.clip(bass_a_fo * 1.5, 0.0, 1.0)[:, np.newaxis]  # spaeter abfaden
        bass_b_fi = np.clip(fi * 1.5 - 0.5, 0.0, 1.0)                  # spaeter einblenden
        mixed += sosfiltfilt(sos_lp, seg_a, axis=0) * bass_a_fo + \
                 sosfiltfilt(sos_lp, seg_b, axis=0) * bass_b_fi

    elif transition_type == "filter_ride":
        # Hochpass auf Track A (hoher Cutoff, der ueber Zeit abfaellt)
        # → "Filter-Sweep"-Sound beim Ausblenden
        cutoffs = np.linspace(2000.0, bass_cutoff_hz, cf_frames)
        # Simplified: fester Filter + normaler Crossfade
        sos_hp_a = _make_sos(800.0, sr, 'high')
        mixed = sosfiltfilt(sos_hp_a, seg_a, axis=0) * fo + seg_b * fi

    else:
        # smooth_blend, drop_cut, breakdown_bridge, echo_out, cold_cut, halftime_switch:
        # Alle als einfacher linearer Crossfade (korrekt und safe)
        mixed = seg_a * fo + seg_b * fi

    return mixed.astype(np.float32)
```

---

## 5. Neue Klasse in `main.py`: `TransitionRenderWorker(QThread)`

**Zweck:** Läuft alle Render-Jobs in einem Background-Thread, emittiert Fortschritt pro Clip.

```python
class TransitionRenderWorker(QThread):
    """
    Rendert alle Transition-Preview-Clips nacheinander im Hintergrund.
    Emittiert pro fertigem Clip ein Signal.
    """
    clip_ready   = pyqtSignal(int, str)   # (index, wav_pfad)
    clip_error   = pyqtSignal(int, str)   # (index, fehler_text)
    all_done     = pyqtSignal()
    progress     = pyqtSignal(int, int)   # (aktuell, gesamt)

    def __init__(self, transitions: list, parent=None):
        super().__init__(parent)
        # transitions: Liste von TransitionRecommendation-Objekten
        self._transitions = transitions
        self._should_cancel = False
        self._temp_files: list[str] = []  # Fuer Cleanup

    def request_cancel(self):
        self._should_cancel = True

    def get_temp_files(self):
        return self._temp_files.copy()

    def run(self):
        total = len(self._transitions)
        for i, transition in enumerate(self._transitions):
            if self._should_cancel:
                break
            self.progress.emit(i + 1, total)
            try:
                # Temp-Datei anlegen
                tmp_dir = tempfile.gettempdir()
                out_path = os.path.join(tmp_dir, f"hpg_preview_{i:03d}.wav")
                self._temp_files.append(out_path)

                # Spec aus TransitionRecommendation aufbauen
                spec = TransitionClipSpec(
                    track_a_path    = transition.from_track.filePath,
                    track_b_path    = transition.to_track.filePath,
                    mix_out_sec     = float(transition.from_track.mix_out_point or 0),
                    mix_in_sec      = float(transition.to_track.mix_in_point or 0),
                    crossfade_sec   = float(transition.overlap or 16.0),
                    transition_type = transition.transition_type or "smooth_blend",
                )

                render_transition_clip(spec, out_path)
                self.clip_ready.emit(i, out_path)

            except Exception as e:
                self.clip_error.emit(i, str(e))

        self.all_done.emit()

    def cleanup(self):
        """Loescht alle temporaeren WAV-Dateien."""
        for path in self._temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self._temp_files.clear()
```

---

## 6. UI-Erweiterung: `TransitionPreviewWidget` in `MixTipsPanel`

**Wo:** In `main.py`, als eigene Widget-Klasse für jeden Übergang in der Scrollliste.

```python
class TransitionPreviewWidget(QWidget):
    """
    Player-Widget fuer einen einzelnen Transitions-Preview-Clip.
    Zeigt: Play/Stop-Button, Fortschritts-Slider, Zeitanzeige.
    """
    def __init__(self, index: int, transition_title: str, parent=None):
        super().__init__(parent)
        self._index = index
        self._wav_path: str | None = None
        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.85)

        self._setup_ui(transition_title)
        self._connect_signals()

    def _setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Titel
        self._title_label = QLabel(title)

        # Kontrollzeile: Play-Button + Slider + Zeit
        ctrl_layout = QHBoxLayout()
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(28, 28)
        self._play_btn.setEnabled(False)  # Erst aktivieren wenn clip_ready

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setValue(0)
        self._slider.setEnabled(False)

        self._time_label = QLabel("—")
        self._time_label.setMinimumWidth(80)

        ctrl_layout.addWidget(self._play_btn)
        ctrl_layout.addWidget(self._slider, 1)
        ctrl_layout.addWidget(self._time_label)

        layout.addWidget(self._title_label)
        layout.addLayout(ctrl_layout)

    def _connect_signals(self):
        self._play_btn.clicked.connect(self._toggle_play)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._slider.sliderMoved.connect(self._on_slider_moved)

    def set_wav_path(self, path: str):
        """Wird aufgerufen wenn TransitionRenderWorker clip_ready emittiert."""
        self._wav_path = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._play_btn.setEnabled(True)
        self._slider.setEnabled(True)
        self._time_label.setText("0:00 / –:––")

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_btn.setText("▶")
        else:
            self._player.play()
            self._play_btn.setText("⏸")

    def _on_position_changed(self, pos_ms: int):
        dur_ms = self._player.duration()
        if dur_ms > 0:
            self._slider.setValue(int(pos_ms * 1000 / dur_ms))
        pos_s = pos_ms // 1000
        self._time_label.setText(f"{pos_s // 60}:{pos_s % 60:02d} / {self._fmt_dur()}")

    def _on_duration_changed(self, dur_ms: int):
        self._time_label.setText(f"0:00 / {self._fmt_dur()}")

    def _fmt_dur(self) -> str:
        d = self._player.duration() // 1000
        return f"{d // 60}:{d % 60:02d}"

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._play_btn.setText("▶")
            self._slider.setValue(0)

    def _on_error(self, error, error_string: str):
        self._play_btn.setEnabled(False)
        self._time_label.setText(f"Fehler")

    def _on_slider_moved(self, value: int):
        dur_ms = self._player.duration()
        if dur_ms > 0:
            self._player.setPosition(int(value * dur_ms / 1000))

    def stop_and_reset(self):
        self._player.stop()
        self._play_btn.setText("▶")
```

---

## 7. Integration in `MixTipsPanel` / `MainWindow`

### 7.1 MixTipsPanel — neue Methoden

```python
# In MixTipsPanel:

def setup_transition_previews(self, transitions: list):
    """
    Wird aufgerufen wenn Playlist generiert wurde.
    Erstellt TransitionPreviewWidget fuer jeden Übergang.
    Startet TransitionRenderWorker.
    """
    # Alte Widgets aufraumen
    self._cleanup_existing_previews()

    self._preview_widgets: dict[int, TransitionPreviewWidget] = {}

    for i, tr in enumerate(transitions):
        title = f"Übergang {i+1}: {tr.from_track.title} → {tr.to_track.title}"
        widget = TransitionPreviewWidget(i, title, self)
        self._preview_widgets[i] = widget
        # Widget in bestehende Scrollarea einfuegen (nach dem bestehenden Mix-Tip-Card)
        self._insert_preview_widget(i, widget)

    # Worker starten
    self._render_worker = TransitionRenderWorker(transitions)
    self._render_worker.clip_ready.connect(self._on_clip_ready)
    self._render_worker.clip_error.connect(self._on_clip_error)
    self._render_worker.progress.connect(self._on_render_progress)
    self._render_worker.start()

def _on_clip_ready(self, index: int, wav_path: str):
    if index in self._preview_widgets:
        self._preview_widgets[index].set_wav_path(wav_path)

def _on_clip_error(self, index: int, error_msg: str):
    # Fehlermeldung im Widget anzeigen (Play-Button bleibt deaktiviert)
    pass

def _on_render_progress(self, current: int, total: int):
    # In StatusBar: "Rendering Übergänge: 3/12..."
    self._status_bar.showMessage(f"Rendere Übergang-Previews: {current}/{total}...")
```

### 7.2 MainWindow — Cleanup

```python
# In MainWindow.closeEvent() oder wenn neue Playlist generiert wird:
def _cleanup_transition_previews(self):
    """Temporaere WAV-Dateien loeschen wenn App geschlossen wird."""
    if hasattr(self, '_render_worker') and self._render_worker:
        self._render_worker.request_cancel()
        self._render_worker.wait(3000)  # Max 3s warten
        self._render_worker.cleanup()   # WAV loeschen
```

---

## 8. Dateien und Änderungen

| Datei | Aktion | Umfang |
|-------|--------|--------|
| `hpg_core/transition_renderer.py` | **NEU** | ~200 Zeilen |
| `main.py` | **ERWEITERN** | +150 Zeilen (TransitionRenderWorker, TransitionPreviewWidget, MixTipsPanel-Methoden) |
| `requirements.txt` | **KEINE Änderung** | scipy + soundfile schon drin |
| `tests/test_transition_renderer.py` | **NEU** | ~80 Zeilen |

---

## 9. Implementierungs-Reihenfolge (Phase 3)

### Schritt 1: `hpg_core/transition_renderer.py` erstellen
- `TransitionClipSpec` Dataclass
- `_load_segment()` — soundfile + librosa-Fallback für MP3
- `_make_sos()` — Butterworth-Filter
- `_apply_eq_crossfade()` — bass_swap + smooth_blend + Fallback
- `render_transition_clip()` — Hauptfunktion

### Schritt 2: Standalone testen
- Skript `scripts/test_transition_renderer.py`:
  ```python
  # Testet mit echten Tracks aus D:\beatport_tracks_2025-08
  spec = TransitionClipSpec(track_a_path="...", track_b_path="...", ...)
  render_transition_clip(spec, "test_preview.wav")
  # Öffne test_preview.wav in VLC/Windows Media Player — hörbar prüfen
  ```

### Schritt 3: Unit-Tests `tests/test_transition_renderer.py`
- Test mit synthetischen Numpy-Arrays (kein echtes Audiomaterial nötig)
- Testen: Mono→Stereo-Konvertierung, Padding bei zu kurzem Segment, Soft-Limiter

### Schritt 4: `TransitionRenderWorker` in `main.py` hinzufügen
- Imports: `from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip`
- Worker-Klasse implementieren
- In `MainWindow` einbinden: Worker beim Schließen aufräumen

### Schritt 5: `TransitionPreviewWidget` implementieren
- Imports: `from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput`
- Widget mit Play/Pause, Slider, Zeitanzeige
- Styling: Theme-Farben aus `COLORS` dict

### Schritt 6: In `MixTipsPanel` integrieren
- `setup_transition_previews()` aufrufen wenn Playlist fertig
- Worker-Signale verbinden
- Preview-Widgets in bestehende Scroll-Area einfügen

### Schritt 7: End-to-End-Test
- App starten → Ordner wählen → Playlist generieren
- Warten bis StatusBar "Rendering..." zeigt
- Pro Übergang: Play-Button anklicken, Qualität prüfen
- App schließen → Temp-Dateien gelöscht?

---

## 10. Edge Cases und Lösungen

| Edge Case | Lösung |
|-----------|--------|
| `mix_out_point = None` (nicht gesetzt) | Fallback: letzte 30s der Track-Länge schätzen |
| Track kürzer als pre_roll_sec | `_ensure_len()` mit Null-Padding |
| MP3-Datei (soundfile kann es nicht) | librosa-Fallback in `_load_segment()` |
| Verschiedene Sample-Rates (z.B. 48kHz) | librosa.resample() in `_load_segment()` |
| Clipping (Peak > 1.0) | Soft-Limiter: `mixed * 0.95 / peak` |
| Render-Worker wird gecancelt | `_should_cancel` Flag, Cleanup in `cleanup()` |
| WAV-Datei bereits geöffnet (Player läuft noch) | Player zuerst stoppen, dann Datei löschen |
| Fehler beim Rendern (Datei nicht lesbar) | `clip_error` Signal, Play-Button bleibt disabled |

---

## 11. Was NICHT gemacht wird (bewusste Entscheidungen)

- **Kein Echtzeit-Routing** durch DJM-450 — zu komplex (= Traktor nachbauen)
- **Keine Waveform-Visualisierung** — nett, aber nicht nötig für MVP
- **Keine MP3-Export-Option** — WAV reicht, kein ffmpeg-Exec nötig
- **Kein Auto-Play** — User klickt manuell, keine Überraschungen
- **Kein Speichern der Previews** — nur temporäre Dateien (werden beim Schließen gelöscht)
- **Kein Volumen-Normalisierung** per Loudness-Standard (EBU R128) — Soft-Limiter reicht
- **pedalboard** nicht jetzt — könnte später für bessere Filterqualität hinzugefügt werden

---

## 12. Akzeptanz-Kriterien

1. `pytest tests/ --tb=short -q` → **1023 Tests grün** (keine Regression)
2. `python hpg_core/transition_renderer.py` → kein Crash, WAV-Datei erzeugt
3. Standalone-Render-Test mit echten Tracks: WAV ist hörbar, kein Clipping, kein Kratzen
4. App starten → Ordner `D:\beatport_tracks_2025-08` → Playlist → MixTips → Play-Buttons erscheinen schrittweise
5. Play-Button klicken → Audio startet, Slider bewegt sich, Zeitanzeige läuft
6. Crossfade hörbar: Track A läuft, dann beide zusammen (kein hartes Cut), dann nur Track B
7. Stop → Slider zurück auf 0
8. App schließen → `%TEMP%\hpg_preview_*.wav` nicht mehr vorhanden

---

## 13. Benötigte Zeit (ehrliche Schätzung)

| Schritt | Aufwand |
|---------|---------|
| transition_renderer.py | 2-3h |
| Test-Skript + Unit-Tests | 1h |
| TransitionRenderWorker | 1h |
| TransitionPreviewWidget | 2h |
| MixTipsPanel-Integration | 1-2h |
| End-to-End-Test + Debugging | 2-4h |
| **Gesamt** | **~10-13h Arbeit** |

Der größte Unsicherheitsfaktor: Wie gut klingt der Bass-Swap wirklich mit echten Tracks?
Butterworth-Filter sind gut, aber professionelle DJs nutzen Linkwitz-Riley-Filter.
Das kann mit `pedalboard` nachgerüstet werden, ohne die Architektur zu ändern.
