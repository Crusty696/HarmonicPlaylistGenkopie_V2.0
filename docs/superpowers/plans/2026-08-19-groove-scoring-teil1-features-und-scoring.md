# Groove-Scoring Teil 1: Features und Scoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Groove, Bassdruck, Timbre und Mood als vier zusaetzliche Faktoren in die Playlist-Reihenfolge einrechnen, hinter einem Schalter, mit nachtraeglich aenderbaren Gewichten.

**Architecture:** Zwei neue, abhaengigkeitsarme Module: `hpg_core/groove.py` extrahiert beat-synchrone Rhythmusmuster (16 Slots pro Takt, verankert am `first_downbeat`), `hpg_core/transition_features.py` vergleicht zwei Tracks paarweise. `hpg_core/tolerances.py` laedt Gewichte aus JSON mit Nutzer-Override. Die Integration in `calculate_enhanced_compatibility` erfolgt hinter `TRANSITION_FEATURES_ENABLED`; bei ausgeschaltetem Schalter ist das Verhalten bit-identisch zum heutigen Stand.

**Tech Stack:** Python 3.12 (`.\venv312\Scripts\python.exe`), numpy, librosa 0.11, soundfile 0.14, PyQt6, pytest.

**Spec:** `docs/superpowers/specs/2026-08-19-groove-bass-timbre-scoring-design.md`

**Vorbedingung:** Alle Kommentare auf Deutsch. Einrueckung des jeweils bearbeiteten Files fortsetzen (`analysis.py`, `playlist.py`, `models.py` = 4 Leerzeichen; `dj_brain.py`, `genres.py` = 2 Leerzeichen; neue Dateien = 4 Leerzeichen).

**Testlauf durchgaengig:** `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q --no-cov`

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `hpg_core/groove.py` | Taktfaltung, Bassband, Synkopierung, Sub/Punch | neu |
| `hpg_core/transition_features.py` | vier Paar-Vergleiche, Kosinus-Helfer | neu |
| `hpg_core/tolerances.py` | JSON laden, Nutzer-Override, Defaults | neu |
| `hpg_core/data/transition_tolerances.json` | ausgelieferte Gewichte | neu |
| `tests/test_groove.py` | Taktfaltung, Feature-Extraktion | neu |
| `tests/test_transition_features.py` | Paar-Vergleiche, fehlende Felder | neu |
| `tests/test_tolerances.py` | Laden, Override, kaputtes JSON | neu |
| `tests/test_groove_scoring_integration.py` | Score-Integration, Umverteilung, Schalter | neu |
| `hpg_core/models.py` | fuenf neue Track-Felder | aendern |
| `hpg_core/config.py` | Schalter und Konstanten | aendern |
| `hpg_core/genres.py` | `GENRE_TRANSITION_TOLERANCES` + Drift-Pruefung | aendern |
| `hpg_core/analysis.py` | Aufruf in beiden Analysepfaden | aendern |
| `hpg_core/caching.py` | `CACHE_VERSION` 29 -> 30 | aendern |
| `hpg_core/playlist.py` | `TransitionMetrics`, gewichtete Summe | aendern |
| `main.py` | Advanced-Panel mit vier Reglern | aendern |

---

## Task 1: Taktfaltung (`fold_to_bar`)

Der Kern des gesamten Vorhabens. Eine Onset-Huellkurve wird auf einen Takt gefaltet: 16 Slots je ein Sechzehntel, verankert am ersten Downbeat.

**Files:**
- Create: `hpg_core/groove.py`
- Test: `tests/test_groove.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_groove.py`:

```python
"""Tests fuer die beat-synchrone Mustererkennung."""
import numpy as np
import pytest

from hpg_core.groove import BAR_SLOTS, fold_to_bar


def _envelope_with_peaks(peak_times, duration, sr_frames=100.0):
    """Baut eine Huellkurve mit Spitzen an den gegebenen Sekunden."""
    n = int(duration * sr_frames)
    env = np.zeros(n, dtype=float)
    times = np.arange(n) / sr_frames
    for t in peak_times:
        idx = int(round(t * sr_frames))
        if 0 <= idx < n:
            env[idx] = 1.0
    return env, times


def test_fold_to_bar_viertel_landen_auf_slot_0_4_8_12():
    # 120 BPM -> 0.5 s pro Beat, 2.0 s pro Takt. Zwei Takte, Viertel auf jeder Zaehlzeit.
    peaks = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    env, times = _envelope_with_peaks(peaks, duration=4.0)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0)

    assert len(pattern) == BAR_SLOTS
    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [0, 4, 8, 12]
    assert pytest.approx(sum(pattern), abs=1e-9) == 1.0


def test_fold_to_bar_offbeat_landet_auf_slot_2_6_10_14():
    # Offbeat-Achtel: 0.25 s nach jeder Zaehlzeit bei 120 BPM.
    peaks = [0.25, 0.75, 1.25, 1.75]
    env, times = _envelope_with_peaks(peaks, duration=2.0)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.0)

    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [2, 6, 10, 14]


def test_fold_to_bar_beruecksichtigt_downbeat_versatz():
    # Gleiche Viertel, aber das Raster beginnt erst bei 0.3 s.
    peaks = [0.3, 0.8, 1.3, 1.8]
    env, times = _envelope_with_peaks(peaks, duration=2.5)

    pattern = fold_to_bar(env, times, bpm=120.0, first_downbeat=0.3)

    belegt = [i for i, v in enumerate(pattern) if v > 0.0]
    assert belegt == [0, 4, 8, 12]


def test_fold_to_bar_leere_huellkurve_gibt_leere_liste():
    assert fold_to_bar(np.array([]), np.array([]), bpm=120.0, first_downbeat=0.0) == []


def test_fold_to_bar_ungueltige_bpm_gibt_leere_liste():
    env, times = _envelope_with_peaks([0.0], duration=1.0)
    assert fold_to_bar(env, times, bpm=0.0, first_downbeat=0.0) == []
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -v --no-cov`
Expected: FAIL mit `ModuleNotFoundError: No module named 'hpg_core.groove'`

- [ ] **Step 3: Minimale Implementierung**

`hpg_core/groove.py`:

```python
"""Beat-synchrone Mustererkennung fuer das Uebergangs-Scoring.

Reine Funktionen ohne Audio-Kontext-Abhaengigkeit: Huellkurve und Zeiten
rein, normiertes Muster raus. Damit bleiben die gelernten Toleranzen
ueberpruefbar (siehe Spec Abschnitt 4).
"""
from __future__ import annotations

import numpy as np

from .config import METER

# Ein 4/4-Takt hat 16 Sechzehntel — das ist die Aufloesung des Musters.
BAR_SLOTS = 16


def fold_to_bar(
    envelope: np.ndarray,
    times: np.ndarray,
    bpm: float,
    first_downbeat: float,
    slots: int = BAR_SLOTS,
) -> list[float]:
    """Faltet eine Huellkurve auf einen Takt und normiert auf Summe 1.

    Jeder Frame wird ueber seinen Zeitstempel einem der `slots` Sechzehntel
    zugeordnet, verankert am ersten Downbeat. Rueckgabe ist eine leere Liste,
    wenn kein belastbares Raster bestimmt werden kann.
    """
    if envelope is None or times is None:
        return []
    if len(envelope) == 0 or len(times) == 0 or len(envelope) != len(times):
        return []
    if bpm <= 0 or slots <= 0:
        return []

    bar_duration = (60.0 / bpm) * METER
    if bar_duration <= 0:
        return []
    slot_width = bar_duration / slots

    acc = np.zeros(slots, dtype=float)
    rel = np.mod(np.asarray(times, dtype=float) - float(first_downbeat), bar_duration)
    idx = np.floor(rel / slot_width).astype(int) % slots
    np.add.at(acc, idx, np.asarray(envelope, dtype=float))

    total = float(acc.sum())
    if total <= 0.0:
        return []
    return (acc / total).tolist()
```

- [ ] **Step 4: Test laufen lassen, Erfolg pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -v --no-cov`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/groove.py tests/test_groove.py
git commit -m "feat(groove): bar-synchronous onset folding"
```

---

## Task 2: Synkopierung und Bass-Kennwerte

**Files:**
- Modify: `hpg_core/groove.py`
- Test: `tests/test_groove.py`

- [ ] **Step 1: Failing Tests anhaengen**

An `tests/test_groove.py` anhaengen:

```python
from hpg_core.groove import bass_punch_from_band, syncopation_from_pattern


def test_syncopation_null_bei_reinen_vierteln():
    pattern = [0.0] * 16
    for slot in (0, 4, 8, 12):
        pattern[slot] = 0.25
    assert syncopation_from_pattern(pattern) == pytest.approx(0.0)


def test_syncopation_eins_bei_reinem_offbeat():
    pattern = [0.0] * 16
    for slot in (2, 6, 10, 14):
        pattern[slot] = 0.25
    assert syncopation_from_pattern(pattern) == pytest.approx(1.0)


def test_syncopation_haelfte_bei_gleichverteilung_auf_on_und_off():
    pattern = [0.0] * 16
    for slot in (0, 4, 8, 12, 2, 6, 10, 14):
        pattern[slot] = 0.125
    assert syncopation_from_pattern(pattern) == pytest.approx(0.5)


def test_syncopation_leeres_muster_gibt_null():
    assert syncopation_from_pattern([]) == 0.0


def test_bass_punch_hoch_bei_spitzen_niedrig_bei_teppich():
    spitzen = np.zeros(1000)
    spitzen[::100] = 1.0
    teppich = np.full(1000, 0.5)

    assert bass_punch_from_band(spitzen) > bass_punch_from_band(teppich)
    assert bass_punch_from_band(teppich) == pytest.approx(1.0, abs=0.05)


def test_bass_punch_leeres_signal_gibt_null():
    assert bass_punch_from_band(np.array([])) == 0.0
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'syncopation_from_pattern'`

- [ ] **Step 3: Implementierung anhaengen**

An `hpg_core/groove.py` anhaengen:

```python
# Zaehlzeiten und die dazwischenliegenden Achtel im 16-Slot-Raster.
ON_BEAT_SLOTS = (0, 4, 8, 12)
OFF_BEAT_SLOTS = (2, 6, 10, 14)


def syncopation_from_pattern(pattern: list[float]) -> float:
    """Anteil der Offbeat-Energie an der Energie auf dem Achtel-Raster.

    0.0 = alles auf den Zaehlzeiten, 1.0 = alles dazwischen. Slots ausserhalb
    des Achtel-Rasters (Sechzehntel) bleiben unberuecksichtigt, weil sie die
    Frage "gerade oder offbeat" nicht beantworten.
    """
    if not pattern or len(pattern) < BAR_SLOTS:
        return 0.0
    on = sum(pattern[s] for s in ON_BEAT_SLOTS)
    off = sum(pattern[s] for s in OFF_BEAT_SLOTS)
    total = on + off
    if total <= 0.0:
        return 0.0
    return float(off / total)


def bass_punch_from_band(band_envelope: np.ndarray) -> float:
    """Crest-Faktor des Bassbands: Spitze durch Mittelwert.

    Ein durchgehender Sub-Teppich liefert Werte nahe 1.0, ein punchy
    Kick-Bass deutlich mehr. Die Spitze wird als 95. Perzentil genommen,
    damit einzelne Ausreisser das Ergebnis nicht bestimmen.
    """
    if band_envelope is None or len(band_envelope) == 0:
        return 0.0
    arr = np.asarray(band_envelope, dtype=float)
    mean = float(np.mean(np.abs(arr)))
    if mean <= 0.0:
        return 0.0
    peak = float(np.percentile(np.abs(arr), 95))
    return peak / mean
```

- [ ] **Step 4: Test laufen lassen, Erfolg pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -v --no-cov`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/groove.py tests/test_groove.py
git commit -m "feat(groove): syncopation and bass crest factor"
```

---

## Task 3: Feature-Extraktion aus Audio (`extract_groove`)

Bindet die reinen Funktionen an echtes Audio und nutzt dabei den bestehenden `FeatureCache`.

**Files:**
- Modify: `hpg_core/groove.py`
- Test: `tests/test_groove.py`

- [ ] **Step 1: Failing Test anhaengen**

An `tests/test_groove.py` anhaengen:

```python
from hpg_core.analysis import FeatureCache
from hpg_core.groove import GrooveFeatures, extract_groove


def _click_track(bpm=120.0, sr=22050, bars=8, offbeat=False):
    """Erzeugt ein Klick-Signal auf den Zaehlzeiten (oder dazwischen)."""
    beat = 60.0 / bpm
    dauer = bars * 4 * beat
    y = np.zeros(int(dauer * sr), dtype=np.float32)
    versatz = beat / 2.0 if offbeat else 0.0
    t = versatz
    while t < dauer:
        i = int(t * sr)
        if i + 200 < len(y):
            # kurzer Bass-Impuls bei 50 Hz
            n = np.arange(200)
            y[i:i + 200] += (np.sin(2 * np.pi * 50 * n / sr) * np.exp(-n / 40.0)).astype(np.float32)
        t += beat
    return y, sr


def test_extract_groove_liefert_muster_fuer_klick_track():
    y, sr = _click_track()
    features = extract_groove(y, sr, bpm=120.0, first_downbeat=0.0)

    assert isinstance(features, GrooveFeatures)
    assert len(features.groove_pattern) == BAR_SLOTS
    assert len(features.bass_pattern) == BAR_SLOTS
    assert features.sub_energy > 0.0
    assert features.bass_punch > 0.0


def test_extract_groove_trennt_gerade_von_offbeat():
    y_gerade, sr = _click_track(offbeat=False)
    y_offbeat, _ = _click_track(offbeat=True)

    gerade = extract_groove(y_gerade, sr, bpm=120.0, first_downbeat=0.0)
    off = extract_groove(y_offbeat, sr, bpm=120.0, first_downbeat=0.0)

    assert gerade.syncopation < 0.35
    assert off.syncopation > 0.65


def test_extract_groove_nutzt_uebergebenen_feature_cache():
    y, sr = _click_track()
    cache = FeatureCache(y, sr)
    cache.get_onset_strength()  # vorbelegen

    features = extract_groove(y, sr, bpm=120.0, first_downbeat=0.0, feature_cache=cache)

    assert len(features.groove_pattern) == BAR_SLOTS


def test_extract_groove_ohne_bpm_liefert_leere_muster():
    y, sr = _click_track()
    features = extract_groove(y, sr, bpm=0.0, first_downbeat=0.0)

    assert features.groove_pattern == []
    assert features.bass_pattern == []
    assert features.syncopation == 0.0
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'GrooveFeatures'`

- [ ] **Step 3: Implementierung anhaengen**

An `hpg_core/groove.py` anhaengen. Der Import von `FeatureCache` erfolgt lazy in der Funktion, um einen Zirkelimport mit `analysis.py` zu vermeiden.

```python
from dataclasses import dataclass, field

import librosa

from .config import HOP_LENGTH

# Frequenzgrenzen der Baender in Hz.
SUB_LOW, SUB_HIGH = 20.0, 60.0
BASS_HIGH = 150.0


@dataclass
class GrooveFeatures:
    """Ergebnis der Groove-Extraktion eines Tracks oder Ausschnitts."""

    groove_pattern: list[float] = field(default_factory=list)
    bass_pattern: list[float] = field(default_factory=list)
    syncopation: float = 0.0
    sub_energy: float = 0.0
    bass_punch: float = 0.0


def _band_envelope(
    magnitude: np.ndarray, freqs: np.ndarray, low: float, high: float
) -> np.ndarray:
    """Summiert die STFT-Magnitude eines Frequenzbands je Frame."""
    maske = (freqs >= low) & (freqs < high)
    if not np.any(maske):
        return np.zeros(magnitude.shape[1], dtype=float)
    return magnitude[maske, :].sum(axis=0)


def extract_groove(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    feature_cache=None,
    hop_length: int = HOP_LENGTH,
) -> GrooveFeatures:
    """Extrahiert Rhythmusmuster und Bass-Kennwerte aus einem Signal.

    Nutzt den uebergebenen FeatureCache, wenn dessen Signal identisch ist —
    Onset und STFT sind die teuren Operationen und liegen dort meist schon
    vor (siehe Spec Abschnitt 5.4).
    """
    if y is None or len(y) == 0 or sr <= 0:
        return GrooveFeatures()

    passend = (
        feature_cache is not None
        and getattr(feature_cache, "y", None) is not None
        and len(feature_cache.y) == len(y)
    )

    if passend:
        onset = feature_cache.get_onset_strength(hop_length)
        magnitude = feature_cache.get_stft_magnitude(hop_length=hop_length)
    else:
        onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
        magnitude = np.abs(librosa.stft(y, hop_length=hop_length))

    times = librosa.frames_to_time(
        np.arange(len(onset)), sr=sr, hop_length=hop_length
    )
    freqs = librosa.fft_frequencies(sr=sr, n_fft=(magnitude.shape[0] - 1) * 2)

    bass_env = _band_envelope(magnitude, freqs, SUB_LOW, BASS_HIGH)
    sub_env = _band_envelope(magnitude, freqs, SUB_LOW, SUB_HIGH)

    # Die Bass-Huellkurve kann durch abweichende Frame-Zahl minimal laenger
    # oder kuerzer sein als die Onset-Huellkurve — auf die kuerzere kappen.
    n = min(len(onset), len(bass_env), len(times))
    groove_pattern = fold_to_bar(onset[:n], times[:n], bpm, first_downbeat)
    bass_pattern = fold_to_bar(bass_env[:n], times[:n], bpm, first_downbeat)

    gesamt = float(magnitude.sum())
    sub_energy = float(sub_env.sum() / gesamt) if gesamt > 0.0 else 0.0

    return GrooveFeatures(
        groove_pattern=groove_pattern,
        bass_pattern=bass_pattern,
        syncopation=syncopation_from_pattern(bass_pattern or groove_pattern),
        sub_energy=sub_energy,
        bass_punch=bass_punch_from_band(bass_env),
    )
```

- [ ] **Step 4: Test laufen lassen, Erfolg pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -v --no-cov`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/groove.py tests/test_groove.py
git commit -m "feat(groove): extract patterns and bass metrics from audio"
```

---

## Task 4: Track-Felder und Cache-Version

**Files:**
- Modify: `hpg_core/models.py` (nach dem Block `Audio Feature Extensions (Phase 3)`)
- Modify: `hpg_core/caching.py:80`
- Test: `tests/test_groove.py`

- [ ] **Step 1: Failing Test anhaengen**

An `tests/test_groove.py` anhaengen:

```python
from hpg_core.caching import CACHE_VERSION
from hpg_core.models import Track


def test_track_hat_groove_felder_mit_defaults():
    t = Track(filePath="x.mp3", fileName="x.mp3")

    assert t.groove_pattern == []
    assert t.bass_pattern == []
    assert t.syncopation == 0.0
    assert t.sub_energy == 0.0
    assert t.bass_punch == 0.0


def test_cache_version_ist_30():
    assert CACHE_VERSION == 30
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -k "groove_felder or cache_version" -v --no-cov`
Expected: FAIL mit `AttributeError: 'Track' object has no attribute 'groove_pattern'`

- [ ] **Step 3: Felder ergaenzen**

In `hpg_core/models.py` direkt nach `timbre_fingerprint: list = field(default_factory=list)` einfuegen:

```python
    # Groove-Features (2026-08-19): beat-synchrone Rhythmusmuster, verankert
    # am first_downbeat. Leere Liste = nicht bestimmt (z. B. downbeat_confidence
    # 0.0); das Scoring verteilt das Gewicht dann um, statt zu bestrafen.
    groove_pattern: list = field(default_factory=list)  # 16 Slots, L1-normiert
    bass_pattern: list = field(default_factory=list)    # 16 Slots, nur <150 Hz
    syncopation: float = 0.0    # 0-1, Offbeat-Anteil im Achtel-Raster
    sub_energy: float = 0.0     # 20-60 Hz, Anteil an der Gesamtenergie
    bass_punch: float = 0.0     # Crest-Faktor des Bassbands
```

In `hpg_core/caching.py:80`:

```python
CACHE_VERSION = 30
```

- [ ] **Step 4: Tests laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py tests/test_caching.py -v --no-cov`
Expected: alle passed. Falls ein Cache-Test die Versionsnummer hart erwartet, dort ebenfalls auf 30 ziehen.

- [ ] **Step 5: Serialisierung pruefen**

Run:
```bash
.\venv312\Scripts\python.exe -c "from hpg_core.caching import CacheManager; from hpg_core.models import Track; t=Track(filePath='a.mp3',fileName='a.mp3'); t.groove_pattern=[0.1]*16; import dataclasses; print(sorted(f.name for f in dataclasses.fields(t))[:5])"
```
Expected: Feldliste wird ausgegeben, kein Fehler. Die Serialisierung in `caching.py` arbeitet ueber `dataclasses.fields`; neue Felder werden damit automatisch mitgeschrieben. Sollte `caching.py` eine explizite Feldliste fuehren, die neuen fuenf Namen dort ergaenzen.

- [ ] **Step 6: Commit**

```bash
git add hpg_core/models.py hpg_core/caching.py tests/test_groove.py
git commit -m "feat(models): add groove fields, bump cache to v30"
```

---

## Task 5: Anbindung in beiden Analysepfaden

**Achtung:** `analyze_track` hat zwei Pfade — Rekordbox-Fast-Path und Voll-Path. Historisch haeufigste Fehlerquelle ist, nur einen davon zu aendern.

**Files:**
- Modify: `hpg_core/analysis.py` (nach der Struktur-/Mixpoint-Kette, vor dem `Track`-Aufbau)
- Test: `tests/test_groove.py`

- [ ] **Step 1: Failing Test anhaengen**

```python
def test_groove_wird_nur_bei_belastbarem_downbeat_berechnet():
    """downbeat_confidence 0.0 heisst: kein Raster, also kein Muster."""
    from hpg_core.analysis import compute_groove_fields

    y, sr = _click_track()
    mit = compute_groove_fields(y, sr, bpm=120.0, first_downbeat=0.0,
                                downbeat_confidence=1.0, feature_cache=None)
    ohne = compute_groove_fields(y, sr, bpm=120.0, first_downbeat=0.0,
                                 downbeat_confidence=0.0, feature_cache=None)

    assert len(mit.groove_pattern) == BAR_SLOTS
    assert ohne.groove_pattern == []
    assert ohne.syncopation == 0.0
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -k downbeat -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'compute_groove_fields'`

- [ ] **Step 3: Helfer in `analysis.py` ergaenzen**

In `hpg_core/analysis.py` nach der Definition von `analyze_frequency_bands` einfuegen:

```python
def compute_groove_fields(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    downbeat_confidence: float,
    feature_cache: FeatureCache | None = None,
) -> GrooveFeatures:
    """Groove-Features berechnen, aber nur auf belastbarem Taktraster.

    Ein Muster auf einem erfundenen Raster ist schlechter als gar keins —
    deshalb Abbruch bei downbeat_confidence 0.0 (Spec Abschnitt 13).
    """
    if downbeat_confidence <= 0.0 or bpm <= 0:
        return GrooveFeatures()
    try:
        return extract_groove(
            y, sr, bpm, first_downbeat, feature_cache=feature_cache
        )
    except Exception as exc:  # Groove darf die Analyse nie kippen
        logger.warning(f"Groove-Extraktion fehlgeschlagen: {exc}")
        return GrooveFeatures()
```

Import oben in `analysis.py` ergaenzen:

```python
from .groove import GrooveFeatures, extract_groove
```

- [ ] **Step 4: Test laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove.py -k downbeat -v --no-cov`
Expected: PASS

- [ ] **Step 5: Beide Pfade verdrahten**

In `hpg_core/analysis.py` an **beiden** Stellen, an denen der `Track` gebaut wird (Fast-Path und Voll-Path), vor dem Konstruktoraufruf einfuegen:

```python
    groove = compute_groove_fields(
        y, sr, bpm_wert, first_downbeat, downbeat_confidence,
        feature_cache=feature_cache,
    )
```

und im `Track(...)`-Aufruf ergaenzen:

```python
        groove_pattern=groove.groove_pattern,
        bass_pattern=groove.bass_pattern,
        syncopation=groove.syncopation,
        sub_energy=groove.sub_energy,
        bass_punch=groove.bass_punch,
```

`bpm_wert` ist im Fast-Path `rekordbox_data.bpm`, im Voll-Path die gemessene BPM. Beide Stellen mit `grep -n "Track(" hpg_core/analysis.py` verifizieren.

- [ ] **Step 6: Verdrahtung beider Pfade pruefen**

Run:
```bash
.\venv312\Scripts\python.exe -c "import re; s=open('hpg_core/analysis.py',encoding='utf-8').read(); print('compute_groove_fields Aufrufe:', s.count('compute_groove_fields(') - 1)"
```
Expected: `2` — je einer pro Pfad. Bei `1` fehlt ein Pfad.

- [ ] **Step 7: Volle Suite laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q --no-cov`
Expected: keine neuen Fehlschlaege gegenueber der Baseline von 1389 Tests.

- [ ] **Step 8: Commit**

```bash
git add hpg_core/analysis.py tests/test_groove.py
git commit -m "feat(analysis): compute groove fields in both analysis paths"
```

---

## Task 6: Paar-Vergleiche

**Files:**
- Create: `hpg_core/transition_features.py`
- Test: `tests/test_transition_features.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_transition_features.py`:

```python
"""Tests fuer die paarweisen Uebergangs-Vergleiche."""
import pytest

from hpg_core.models import Track
from hpg_core.transition_features import (
    bass_continuity,
    cosine_similarity,
    groove_match,
    mood_match,
    timbre_match,
)


def _track(**kwargs) -> Track:
    t = Track(filePath=kwargs.pop("path", "a.mp3"), fileName="a.mp3")
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


def _gerade():
    p = [0.0] * 16
    for s in (0, 4, 8, 12):
        p[s] = 0.25
    return p


def _offbeat():
    p = [0.0] * 16
    for s in (2, 6, 10, 14):
        p[s] = 0.25
    return p


def test_cosine_similarity_identisch_ist_eins():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_ist_null():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_leer_ist_none():
    assert cosine_similarity([], [1.0]) is None


def test_groove_match_gleiches_muster_ist_hoch():
    a = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    b = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    assert groove_match(a, b, "Psytrance") > 0.95


def test_groove_match_offbeat_gegen_gerade_ist_niedrig():
    a = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    b = _track(groove_pattern=_offbeat(), bass_pattern=_offbeat())
    assert groove_match(a, b, "Psytrance") < 0.2


def test_groove_match_ohne_muster_ist_none():
    a = _track(groove_pattern=[], bass_pattern=[])
    b = _track(groove_pattern=_gerade(), bass_pattern=_gerade())
    assert groove_match(a, b, "Psytrance") is None


def test_bass_continuity_gleicher_druck_ist_hoch():
    a = _track(sub_energy=0.30, bass_punch=3.0)
    b = _track(sub_energy=0.30, bass_punch=3.0)
    assert bass_continuity(a, b, "Psytrance") > 0.95


def test_bass_continuity_grosser_sprung_ist_niedrig():
    a = _track(sub_energy=0.05, bass_punch=1.2)
    b = _track(sub_energy=0.50, bass_punch=6.0)
    assert bass_continuity(a, b, "Psytrance") < 0.5


def test_bass_continuity_ohne_werte_ist_none():
    a = _track(sub_energy=0.0, bass_punch=0.0)
    b = _track(sub_energy=0.0, bass_punch=0.0)
    assert bass_continuity(a, b, "Psytrance") is None


def test_timbre_match_ohne_fingerprint_ist_none():
    a = _track(timbre_fingerprint=[])
    b = _track(timbre_fingerprint=[1.0, 2.0])
    assert timbre_match(a, b, "Psytrance") is None


def test_timbre_match_identisch_ist_hoch():
    fp = [1.0, 2.0, 3.0, 4.0]
    assert timbre_match(_track(timbre_fingerprint=fp),
                        _track(timbre_fingerprint=fp), "Psytrance") > 0.95


def test_mood_match_gleiche_stimmung_ist_hoch():
    a = _track(brightness=50, spectral_flatness=0.05, keyMode="Minor")
    b = _track(brightness=52, spectral_flatness=0.05, keyMode="Minor")
    assert mood_match(a, b, "Psytrance") > 0.9


def test_mood_match_heller_sprung_ist_niedriger():
    a = _track(brightness=10, spectral_flatness=0.02, keyMode="Minor")
    b = _track(brightness=95, spectral_flatness=0.02, keyMode="Major")
    assert mood_match(a, b, "Psytrance") < 0.5


def test_mood_match_ohne_brightness_ist_none():
    a = _track(brightness=0, spectral_flatness=0.0)
    b = _track(brightness=0, spectral_flatness=0.0)
    assert mood_match(a, b, "Psytrance") is None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_transition_features.py -v --no-cov`
Expected: FAIL mit `ModuleNotFoundError: No module named 'hpg_core.transition_features'`

- [ ] **Step 3: Implementierung**

`hpg_core/transition_features.py`:

```python
"""Paarweise Uebergangs-Vergleiche fuer das Playlist-Scoring.

Jede Funktion liefert einen Wert in [0, 1] oder None. None heisst
ausdruecklich "nicht bestimmbar" — das Scoring verteilt das Gewicht dann um,
statt den Uebergang zu bestrafen (Spec Abschnitt 7.3).
"""
from __future__ import annotations

import math

from .models import Track
from .tolerances import get_tolerances

# Anteil des Bassmusters am Groove-Vergleich. Der Bass traegt die Entscheidung
# "offbeat oder gerade" und wiegt deshalb schwerer als das Gesamt-Onset.
BASS_PATTERN_SHARE = 0.6

# Sprungbreiten, ab denen der jeweilige Faktor auf 0 faellt, falls das Genre
# keine gelernten Werte hat.
DEFAULT_SUB_DELTA_MAX = 0.25
DEFAULT_PUNCH_DELTA_MAX = 4.0
DEFAULT_BRIGHTNESS_DELTA_MAX = 60.0
DEFAULT_FLATNESS_DELTA_MAX = 0.15

# Abzug, wenn der Tongeschlecht-Wechsel die Stimmung kippt.
MODE_SWITCH_PENALTY = 0.15


def cosine_similarity(a, b) -> float | None:
    """Kosinus-Aehnlichkeit zweier Vektoren, auf [0, 1] geklemmt."""
    if not a or not b or len(a) != len(b):
        return None
    punkt = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0.0 or nb <= 0.0:
        return None
    return max(0.0, min(1.0, punkt / (na * nb)))


def _normiert(delta: float, maximum: float) -> float:
    """Wandelt einen Absolutabstand in eine Aehnlichkeit in [0, 1]."""
    if maximum <= 0.0:
        return 1.0
    return max(0.0, 1.0 - abs(delta) / maximum)


def groove_match(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Rhythmische Passung aus Gesamt- und Bassmuster."""
    onset_sim = cosine_similarity(track_a.groove_pattern, track_b.groove_pattern)
    bass_sim = cosine_similarity(track_a.bass_pattern, track_b.bass_pattern)

    if onset_sim is None and bass_sim is None:
        return None
    if bass_sim is None:
        return onset_sim
    if onset_sim is None:
        return bass_sim
    return BASS_PATTERN_SHARE * bass_sim + (1.0 - BASS_PATTERN_SHARE) * onset_sim


def bass_continuity(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Kontinuitaet des Bassdrucks an der Nahtstelle."""
    if track_a.sub_energy <= 0.0 and track_b.sub_energy <= 0.0:
        return None

    tol = get_tolerances(genre)
    sub_max = tol.get("bass_delta_max", DEFAULT_SUB_DELTA_MAX)

    sub_sim = _normiert(track_a.sub_energy - track_b.sub_energy, sub_max)
    punch_sim = _normiert(
        track_a.bass_punch - track_b.bass_punch, DEFAULT_PUNCH_DELTA_MAX
    )
    return 0.6 * sub_sim + 0.4 * punch_sim


def timbre_match(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Klangfarbliche Passung aus dem MFCC-Fingerabdruck."""
    return cosine_similarity(track_a.timbre_fingerprint, track_b.timbre_fingerprint)


def mood_match(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Stimmungs-Passung aus Helligkeit, Flachheit und Tongeschlecht."""
    if track_a.brightness <= 0 and track_b.brightness <= 0:
        return None

    tol = get_tolerances(genre)
    hell_max = tol.get("brightness_delta_max", DEFAULT_BRIGHTNESS_DELTA_MAX)

    hell_sim = _normiert(
        float(track_a.brightness - track_b.brightness), hell_max
    )
    flach_sim = _normiert(
        track_a.spectral_flatness - track_b.spectral_flatness,
        DEFAULT_FLATNESS_DELTA_MAX,
    )
    score = 0.7 * hell_sim + 0.3 * flach_sim

    if track_a.keyMode and track_b.keyMode and track_a.keyMode != track_b.keyMode:
        score = max(0.0, score - MODE_SWITCH_PENALTY)
    return score
```

- [ ] **Step 4: Test laufen lassen** (schlaegt noch an `tolerances` fehl — das ist Task 7)

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_transition_features.py -v --no-cov`
Expected: FAIL mit `ModuleNotFoundError: No module named 'hpg_core.tolerances'`. Weiter mit Task 7, dann erneut laufen lassen.

---

## Task 6b: Sektionsbezogener Bassdruck

Spec Abschnitt 5.3: gemessen wird die **Nahtstelle**, nicht das Trackmittel. Ob zwei Tracks im Schnitt aehnlich basslastig sind, ist fuer den Uebergang irrelevant — es zaehlt, was im Outro von A und im Intro von B passiert.

**Files:**
- Modify: `hpg_core/analysis.py` (Sektions-Dicts)
- Modify: `hpg_core/transition_features.py` (`bass_continuity`)
- Test: `tests/test_transition_features.py`

- [ ] **Step 1: Failing Test anhaengen**

```python
def test_bass_continuity_nutzt_sektionswerte_statt_trackmittel():
    """Outro von A gegen Intro von B — Trackmittel sind irrelevant."""
    # Trackmittel identisch, Nahtstelle aber weit auseinander.
    a = _track(sub_energy=0.30, bass_punch=3.0)
    a.sections = [
        {"label": "intro", "start": 0.0, "end": 30.0, "sub_energy": 0.05},
        {"label": "outro", "start": 300.0, "end": 360.0, "sub_energy": 0.55},
    ]
    b = _track(sub_energy=0.30, bass_punch=3.0)
    b.sections = [
        {"label": "intro", "start": 0.0, "end": 30.0, "sub_energy": 0.05},
        {"label": "outro", "start": 300.0, "end": 360.0, "sub_energy": 0.55},
    ]

    # Outro A (0.55) gegen Intro B (0.05) -> grosser Sprung, trotz gleicher Mittel
    mit_sektionen = bass_continuity(a, b, "Psytrance")

    a.sections = []
    b.sections = []
    ohne_sektionen = bass_continuity(a, b, "Psytrance")

    assert mit_sektionen < ohne_sektionen


def test_bass_continuity_faellt_auf_trackmittel_ohne_sektionen():
    a = _track(sub_energy=0.30, bass_punch=3.0)
    b = _track(sub_energy=0.30, bass_punch=3.0)
    a.sections = []
    b.sections = []
    assert bass_continuity(a, b, "Psytrance") > 0.95
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_transition_features.py -k sektions -v --no-cov`
Expected: FAIL — beide Werte sind gleich, weil `bass_continuity` die Sektionen nicht ansieht.

- [ ] **Step 3: Sektionswerte in `analysis.py` schreiben**

Dort, wo die Section-Dicts gebaut werden (dieselbe Stelle, an der `avg_bass` je Sektion gesetzt wird — mit `grep -n "avg_bass" hpg_core/analysis.py` finden), je Sektion ergaenzen:

```python
        # Bassdruck je Sektion — der Uebergang misst die Nahtstelle,
        # nicht das Trackmittel (Spec 5.3).
        s_start = int(section["start"] * sr)
        s_ende = min(len(y), int(section["end"] * sr))
        if s_ende > s_start:
            s_groove = extract_groove(
                y[s_start:s_ende], sr, bpm_wert, 0.0, feature_cache=None
            )
            section["sub_energy"] = s_groove.sub_energy
            section["bass_punch"] = s_groove.bass_punch
```

- [ ] **Step 4: Sektions-Zugriff in `transition_features.py`**

`bass_continuity` ersetzen durch:

```python
def _naht_werte(track: Track, rolle: str) -> tuple[float, float]:
    """Bassdruck an der Nahtstelle; Trackmittel als Rueckfallebene.

    rolle "out" = letzte Sektion (Track laeuft aus),
    rolle "in"  = erste Sektion (Track kommt herein).
    """
    sektionen = [s for s in (track.sections or []) if isinstance(s, dict)]
    if sektionen:
        s = sektionen[-1] if rolle == "out" else sektionen[0]
        sub = s.get("sub_energy")
        punch = s.get("bass_punch")
        if sub is not None and punch is not None:
            return float(sub), float(punch)
    return track.sub_energy, track.bass_punch


def bass_continuity(track_a: Track, track_b: Track, genre: str) -> float | None:
    """Kontinuitaet des Bassdrucks an der Nahtstelle (Outro A / Intro B)."""
    sub_a, punch_a = _naht_werte(track_a, "out")
    sub_b, punch_b = _naht_werte(track_b, "in")

    if sub_a <= 0.0 and sub_b <= 0.0:
        return None

    tol = get_tolerances(genre)
    sub_max = tol.get("bass_delta_max", DEFAULT_SUB_DELTA_MAX)

    sub_sim = _normiert(sub_a - sub_b, sub_max)
    punch_sim = _normiert(punch_a - punch_b, DEFAULT_PUNCH_DELTA_MAX)
    return 0.6 * sub_sim + 0.4 * punch_sim
```

- [ ] **Step 5: Tests laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_transition_features.py -v --no-cov`
Expected: 16 passed

- [ ] **Step 6: Volle Suite**

Run: `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q --no-cov`
Expected: keine neuen Fehlschlaege.

- [ ] **Step 7: Commit**

```bash
git add hpg_core/analysis.py hpg_core/transition_features.py tests/test_transition_features.py
git commit -m "feat(scoring): measure bass continuity at the seam, not track mean"
```

---

## Task 7: Genre-Toleranzen und JSON-Override

**Files:**
- Modify: `hpg_core/genres.py` (Tabelle + `_validate_genre_tables`)
- Create: `hpg_core/tolerances.py`
- Create: `hpg_core/data/transition_tolerances.json`
- Test: `tests/test_tolerances.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_tolerances.py`:

```python
"""Tests fuer das Laden der Uebergangs-Toleranzen."""
import json

import pytest

from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES
from hpg_core.tolerances import get_tolerances, load_tolerances


def test_alle_kanonischen_genres_haben_toleranzen():
    assert set(GENRE_TRANSITION_TOLERANCES) == set(CANONICAL_GENRES)


def test_gewichte_summieren_auf_eins():
    for genre, werte in GENRE_TRANSITION_TOLERANCES.items():
        summe = sum(
            werte[k] for k in (
                "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
                "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
            )
        )
        assert summe == pytest.approx(1.0, abs=1e-6), f"{genre}: {summe}"


def test_get_tolerances_unbekanntes_genre_faellt_auf_default():
    werte = get_tolerances("Gibt Es Nicht")
    assert "groove_weight" in werte


def test_override_datei_schlaegt_default(tmp_path, monkeypatch):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text(
        json.dumps({"Psytrance": {"groove_weight": 0.42}}), encoding="utf-8"
    )
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert werte["Psytrance"]["groove_weight"] == 0.42
    # nicht ueberschriebene Schluessel bleiben erhalten
    assert "harmonic_weight" in werte["Psytrance"]


def test_kaputtes_json_faellt_auf_defaults_ohne_ausnahme(tmp_path, monkeypatch):
    datei = tmp_path / "transition_tolerances.json"
    datei.write_text("{ das ist kein json", encoding="utf-8")
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))

    werte = load_tolerances()

    assert set(werte) == set(CANONICAL_GENRES)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_tolerances.py -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'GENRE_TRANSITION_TOLERANCES'`

- [ ] **Step 3: Tabelle in `genres.py` ergaenzen**

An `hpg_core/genres.py` vor `_validate_genre_tables` einfuegen (2 Leerzeichen Einrueckung beachten). Startgewichte aus Spec 7.2, fuer alle 9 Genres zunaechst identisch:

```python
# Uebergangs-Toleranzen je Genre (Spec 2026-08-19, Abschnitt 9).
# Die Gewichte summieren je Genre auf 1.0. Bis zur Kalibrierung aus echten
# DJ-Mixen (Teil 2) tragen alle Genres dieselben Startwerte.
_TOLERANCE_DEFAULTS = {
  "harmonic_weight": 0.246,
  "bpm_weight": 0.157,
  "energy_weight": 0.157,
  "genre_weight": 0.140,
  "groove_weight": 0.120,
  "bass_weight": 0.080,
  "timbre_weight": 0.050,
  "mood_weight": 0.050,
  "groove_sim_floor": 0.35,
  "bass_delta_max": 0.25,
  "brightness_delta_max": 60.0,
  "groove_veto_enabled": False,
}

GENRE_TRANSITION_TOLERANCES: dict[str, dict] = {
  genre: dict(_TOLERANCE_DEFAULTS) for genre in CANONICAL_GENRES
}
```

In `_validate_genre_tables` bei den uebrigen Pruefungen ergaenzen:

```python
  if set(GENRE_TRANSITION_TOLERANCES) != canonical:
    problems.append(
      f"GENRE_TRANSITION_TOLERANCES-Genres != CANONICAL_GENRES: "
      f"fehlend={sorted(canonical - set(GENRE_TRANSITION_TOLERANCES))}, "
      f"ueberzaehlig={sorted(set(GENRE_TRANSITION_TOLERANCES) - canonical)}"
    )
  for genre, werte in GENRE_TRANSITION_TOLERANCES.items():
    summe = sum(
      werte[k] for k in (
        "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
        "groove_weight", "bass_weight", "timbre_weight", "mood_weight",
      )
    )
    if abs(summe - 1.0) > 1e-6:
      problems.append(f"Gewichte von {genre} summieren auf {summe}, nicht 1.0")
```

- [ ] **Step 4: Loader schreiben**

`hpg_core/tolerances.py`:

```python
"""Laedt die Uebergangs-Toleranzen: Defaults, mitgeliefertes JSON, Override.

Gewichte sind Daten, keine Konstanten im Quelltext (Spec Abschnitt 8). Eine
Aenderung erfordert keine Neuanalyse, nur ein Neuberechnen der Scores.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

from .genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES

logger = logging.getLogger(__name__)

_MITGELIEFERT = Path(__file__).parent / "data" / "transition_tolerances.json"

_cache: dict[str, dict] | None = None


def _override_pfad() -> Path:
    """Nutzer-Override; HPG_TOLERANCES_FILE hat Vorrang (auch fuer Tests)."""
    explizit = os.environ.get("HPG_TOLERANCES_FILE")
    if explizit:
        return Path(explizit)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(basis) / "HPG" / "transition_tolerances.json"


def _merge(ziel: dict[str, dict], quelle: dict) -> None:
    """Uebernimmt nur bekannte Genres und ueberschreibt einzelne Schluessel."""
    for genre, werte in (quelle or {}).items():
        if genre in ziel and isinstance(werte, dict):
            ziel[genre].update(werte)


def load_tolerances() -> dict[str, dict]:
    """Defaults, darueber das mitgelieferte JSON, darueber der Override.

    Ein defektes JSON darf den Start nicht verhindern — der Fehler wird
    protokolliert und die bis dahin gueltigen Werte bleiben bestehen.
    """
    werte = copy.deepcopy(GENRE_TRANSITION_TOLERANCES)
    for pfad in (_MITGELIEFERT, _override_pfad()):
        try:
            if pfad.is_file():
                _merge(werte, json.loads(pfad.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning(f"Toleranz-Datei {pfad} nicht lesbar: {exc}")
    return werte


def get_tolerances(genre: str) -> dict:
    """Toleranzen eines Genres; unbekannte Genres bekommen das erste kanonische."""
    global _cache
    if _cache is None:
        _cache = load_tolerances()
    return _cache.get(genre) or _cache[CANONICAL_GENRES[0]]


def reset_cache() -> None:
    """Verwirft den Toleranz-Cache — nach dem Aendern von Gewichten aufrufen."""
    global _cache
    _cache = None
```

- [ ] **Step 5: Mitgeliefertes JSON anlegen**

`hpg_core/data/transition_tolerances.json` — vor der Kalibrierung bewusst leer, damit die Defaults aus `genres.py` gelten:

```json
{}
```

- [ ] **Step 6: Tests laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_tolerances.py tests/test_transition_features.py -v --no-cov`
Expected: alle passed (5 + 14 = 19)

- [ ] **Step 7: Commit**

```bash
git add hpg_core/genres.py hpg_core/tolerances.py hpg_core/data/transition_tolerances.json hpg_core/transition_features.py tests/test_tolerances.py tests/test_transition_features.py
git commit -m "feat(scoring): genre transition tolerances with JSON override"
```

---

## Task 8: Gewichtete Summe mit Umverteilung

**Files:**
- Modify: `hpg_core/config.py`
- Modify: `hpg_core/playlist.py:90-98` (`TransitionMetrics`) und `:256` (`calculate_enhanced_compatibility`)
- Test: `tests/test_groove_scoring_integration.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_groove_scoring_integration.py`:

```python
"""Tests fuer die Integration der vier neuen Faktoren ins Scoring."""
import pytest

from hpg_core.playlist import combine_weighted


def test_combine_weighted_alle_vorhanden():
    komponenten = {"a": 1.0, "b": 0.0}
    gewichte = {"a": 0.5, "b": 0.5}
    assert combine_weighted(komponenten, gewichte) == pytest.approx(0.5)


def test_combine_weighted_verteilt_fehlende_um():
    # b fehlt -> a traegt allein, Ergebnis ist a selbst, nicht a*0.5
    komponenten = {"a": 1.0, "b": None}
    gewichte = {"a": 0.5, "b": 0.5}
    assert combine_weighted(komponenten, gewichte) == pytest.approx(1.0)


def test_combine_weighted_umverteilung_bleibt_proportional():
    komponenten = {"a": 1.0, "b": 0.0, "c": None}
    gewichte = {"a": 0.2, "b": 0.6, "c": 0.2}
    # verfuegbar: a=0.2, b=0.6 -> Summe 0.8 -> (0.2*1.0 + 0.6*0.0)/0.8 = 0.25
    assert combine_weighted(komponenten, gewichte) == pytest.approx(0.25)


def test_combine_weighted_alles_fehlt_gibt_null():
    assert combine_weighted({"a": None}, {"a": 1.0}) == 0.0
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove_scoring_integration.py -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'combine_weighted'`

- [ ] **Step 3: Konstanten und Helfer ergaenzen**

In `hpg_core/config.py` ergaenzen:

```python
# Groove-/Bass-/Timbre-/Mood-Scoring (Spec 2026-08-19).
# False = bit-identisches Verhalten zum Stand vor der Erweiterung.
TRANSITION_FEATURES_ENABLED = False
```

In `hpg_core/playlist.py` vor `calculate_enhanced_compatibility` einfuegen:

```python
def combine_weighted(
    components: dict[str, float | None], weights: dict[str, float]
) -> float:
    """Gewichtete Summe; fehlende Komponenten werden umverteilt.

    Ein Faktor mit Wert None ist "nicht bestimmbar" und wird NICHT mit 0
    bewertet — das waere eine stille Bestrafung fuer Tracks ohne Groove-Daten
    (Spec Abschnitt 7.3). Stattdessen faellt er samt Gewicht aus der Summe,
    und die verbleibenden Gewichte werden auf 1.0 renormiert.
    """
    verfuegbar = {k: v for k, v in components.items() if v is not None}
    if not verfuegbar:
        return 0.0
    gewicht_summe = sum(weights.get(k, 0.0) for k in verfuegbar)
    if gewicht_summe <= 0.0:
        return 0.0
    roh = sum(weights.get(k, 0.0) * float(v) for k, v in verfuegbar.items())
    return roh / gewicht_summe
```

- [ ] **Step 4: Test laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove_scoring_integration.py -v --no-cov`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/config.py hpg_core/playlist.py tests/test_groove_scoring_integration.py
git commit -m "feat(scoring): weighted combination with redistribution"
```

---

## Task 9: Integration in `calculate_enhanced_compatibility`

**Files:**
- Modify: `hpg_core/playlist.py:90-98` und `:256-390`
- Test: `tests/test_groove_scoring_integration.py`

- [ ] **Step 1: Failing Test anhaengen**

```python
from hpg_core.models import Track
from hpg_core.playlist import calculate_enhanced_compatibility


def _paar():
    a = Track(filePath="a.mp3", fileName="a.mp3")
    a.bpm, a.camelotCode, a.energy, a.detected_genre = 140.0, "8A", 60, "Psytrance"
    b = Track(filePath="b.mp3", fileName="b.mp3")
    b.bpm, b.camelotCode, b.energy, b.detected_genre = 140.0, "8A", 62, "Psytrance"
    return a, b


def test_metrics_hat_vier_neue_felder():
    a, b = _paar()
    m = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0)
    for feld in ("groove_match", "bass_continuity", "timbre_match", "mood_match"):
        assert hasattr(m, feld)


def test_schalter_aus_ist_identisch_zum_altstand(monkeypatch):
    """Bei ausgeschaltetem Schalter darf sich der Score nicht bewegen."""
    import hpg_core.playlist as pl

    a, b = _paar()
    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", False)
    ohne = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    # bekannter Altwert: Harmonik 100, BPM-Diff 0, Energy-Diff 2, Genre gleich
    erwartet = (0.8 * 0.44) * 1.0 + (0.8 * 0.28) * 1.0 + (0.8 * 0.28) * 0.98 + 0.2 * 1.0
    assert ohne == pytest.approx(min(1.0, erwartet), abs=1e-6)


def test_schalter_an_beruecksichtigt_groove(monkeypatch):
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    gerade = [0.0] * 16
    for s in (0, 4, 8, 12):
        gerade[s] = 0.25
    offbeat = [0.0] * 16
    for s in (2, 6, 10, 14):
        offbeat[s] = 0.25

    a, b = _paar()
    a.groove_pattern, a.bass_pattern = gerade, gerade
    b.groove_pattern, b.bass_pattern = gerade, gerade
    passend = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    b.groove_pattern, b.bass_pattern = offbeat, offbeat
    beissend = calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score

    assert passend > beissend


def test_bpm_hard_gate_bleibt_wirksam(monkeypatch):
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    a, b = _paar()
    b.bpm = 175.0
    assert calculate_enhanced_compatibility(a, b, bpm_tolerance=6.0).overall_score == 0.0
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove_scoring_integration.py -v --no-cov`
Expected: FAIL mit `AttributeError: 'TransitionMetrics' object has no attribute 'groove_match'`

- [ ] **Step 3: `TransitionMetrics` erweitern**

In `hpg_core/playlist.py:90-98`:

```python
class TransitionMetrics:
    """Metrics for evaluating track transitions."""

    harmonic_score: int
    bpm_smoothness: float
    energy_flow: float
    genre_compatibility: float
    overall_score: float
    ai_bonus: float = 0.0
    # Groove-Erweiterung 2026-08-19; None = nicht bestimmbar (Umverteilung).
    groove_match: float | None = None
    bass_continuity: float | None = None
    timbre_match: float | None = None
    mood_match: float | None = None
```

- [ ] **Step 4: Score-Berechnung umbauen**

In `hpg_core/playlist.py` den Block `# Overall weighted score` ersetzen. Der alte Pfad bleibt **wortgleich** erhalten, damit `TRANSITION_FEATURES_ENABLED = False` bit-identisch rechnet:

```python
    groove_val = bass_val = timbre_val = mood_val = None

    if TRANSITION_FEATURES_ENABLED:
        tol = get_tolerances(genre_a)
        groove_val = groove_match(track1, track2, genre_a)
        bass_val = bass_continuity(track1, track2, genre_a)
        timbre_val = timbre_match(track1, track2, genre_a)
        mood_val = mood_match(track1, track2, genre_a)
        overall_score = combine_weighted(
            {
                "harmonic": harmonic_score / 100.0,
                "bpm": bpm_smoothness,
                "energy": energy_flow,
                "genre": genre_compatibility,
                "groove": groove_val,
                "bass": bass_val,
                "timbre": timbre_val,
                "mood": mood_val,
            },
            {
                "harmonic": tol["harmonic_weight"],
                "bpm": tol["bpm_weight"],
                "energy": tol["energy_weight"],
                "genre": tol["genre_weight"],
                "groove": tol["groove_weight"],
                "bass": tol["bass_weight"],
                "timbre": tol["timbre_weight"],
                "mood": tol["mood_weight"],
            },
        )
    else:
        # Unveraenderter Altpfad — Referenz fuer den Regressionstest.
        overall_score = (
            (remaining * 0.44) * (harmonic_score / 100.0)
            + (remaining * 0.28) * bpm_smoothness
            + (remaining * 0.28) * energy_flow
            + genre_weight * genre_compatibility
        )
```

Imports oben in `playlist.py` ergaenzen:

```python
from .config import TRANSITION_FEATURES_ENABLED
from .tolerances import get_tolerances
from .transition_features import (
    bass_continuity, groove_match, mood_match, timbre_match,
)
```

Im `TransitionMetrics(...)`-Aufruf am Ende der Funktion ergaenzen:

```python
        groove_match=groove_val,
        bass_continuity=bass_val,
        timbre_match=timbre_val,
        mood_match=mood_val,
```

- [ ] **Step 5: Cache-Verhalten pruefen (keine Aenderung noetig)**

`_enhanced_cache_key` (`playlist.py:181`) bleibt **unveraendert**. Begruendung, die per Code nachzuvollziehen ist: `_ENHANCED_COMPAT_CACHE` (`playlist.py:500`) ist ein Modul-Global, das nur waehrend `generate_playlist`/`benchmark` gesetzt und danach wieder auf `None` gestellt wird. Weder der Schalter noch die Gewichte koennen sich innerhalb eines einzelnen Laufs aendern, also kann der Cache keine zwei Staende mischen.

Verifizieren:

```bash
grep -n "_ENHANCED_COMPAT_CACHE" hpg_core/playlist.py
```
Expected: Zuweisungen nur innerhalb von `generate_playlist`/`benchmark`, ausserhalb `None`. Trifft das nicht zu, muss `TRANSITION_FEATURES_ENABLED` doch in den Schluessel — dann diesen Schritt entsprechend nachziehen.

- [ ] **Step 6: Tests laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove_scoring_integration.py -v --no-cov`
Expected: 8 passed

- [ ] **Step 7: Volle Suite — Regressionsnachweis**

Run: `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q --no-cov`
Expected: 1389+ passed, 0 failed. Jeder Fehlschlag hier bedeutet, dass der Altpfad nicht bit-identisch ist.

- [ ] **Step 8: Commit**

```bash
git add hpg_core/playlist.py tests/test_groove_scoring_integration.py
git commit -m "feat(scoring): wire groove/bass/timbre/mood into enhanced compatibility"
```

---

## Task 10: scoring_context in allen fuenf Konsumenten

Die HPG-001-Regel: Anzeige, Reorder, Preview, Quality und Empfehlungen muessen denselben Kontext sehen wie die Sortierung.

**Files:**
- Modify: `hpg_core/playlist.py` (`resolve_scoring_context:1909`, `calculate_playlist_quality:1649`)
- Test: `tests/test_groove_scoring_integration.py`

- [ ] **Step 1: Failing Contract-Test anhaengen**

```python
def test_alle_konsumenten_sehen_dieselben_faktoren(monkeypatch):
    """HPG-001: Sortierung und Qualitaetsanzeige duerfen nicht divergieren."""
    import hpg_core.playlist as pl

    monkeypatch.setattr(pl, "TRANSITION_FEATURES_ENABLED", True)
    a, b = _paar()
    gerade = [0.0] * 16
    for s in (0, 4, 8, 12):
        gerade[s] = 0.25
    for t in (a, b):
        t.groove_pattern = t.bass_pattern = gerade
        t.timbre_fingerprint = [1.0, 2.0, 3.0]
        t.brightness = 50

    paar_score = pl.calculate_enhanced_compatibility(
        a, b, bpm_tolerance=6.0
    ).overall_score
    quality = pl.calculate_playlist_quality([a, b], bpm_tolerance=6.0)

    assert quality == pytest.approx(round(paar_score * 100), abs=1)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove_scoring_integration.py -k konsumenten -v --no-cov`
Expected: FAIL — die Qualitaetszahl weicht ab, weil sie den Altpfad rechnet.

- [ ] **Step 3: Kontext durchreichen**

`calculate_playlist_quality` ruft `calculate_enhanced_compatibility` bereits auf; sicherstellen, dass `scoring_context` unveraendert weitergereicht wird und kein eigener Score nachgebaut wird. Mit

```bash
grep -n "scoring_context" hpg_core/playlist.py main.py
```

alle Fundstellen pruefen: jede muss denselben Dict an `calculate_enhanced_compatibility` weitergeben.

- [ ] **Step 4: Test laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_groove_scoring_integration.py -v --no-cov`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/playlist.py tests/test_groove_scoring_integration.py
git commit -m "fix(scoring): propagate context to all five consumers"
```

---

## Task 11: GUI-Panel fuer die Gewichte

**Files:**
- Modify: `main.py` (Advanced-Einstellungen)

- [ ] **Step 1: Panel ergaenzen**

Im Advanced-Bereich vier `QSlider` (0-100, Schrittweite 1) fuer Groove, Bass, Timbre, Mood plus einen `QPushButton` "Zuruecksetzen". UI-Aenderungen ausschliesslich im Main-Thread.

```python
        self.groove_slider = QSlider(Qt.Orientation.Horizontal)
        self.groove_slider.setRange(0, 100)
        self.groove_slider.setValue(12)  # entspricht Gewicht 0.120
        self.groove_slider.valueChanged.connect(self._on_transition_weight_changed)
```

analog fuer `bass_slider` (8), `timbre_slider` (5), `mood_slider` (5).

- [ ] **Step 2: Handler schreiben**

```python
    def _on_transition_weight_changed(self) -> None:
        """Schreibt die Regler in die Override-Datei und verwirft den Cache.

        Gewichte liegen ausserhalb des Analyse-Caches — eine Aenderung kostet
        deshalb nur ein Neuberechnen der Scores, keine Neuanalyse. Die
        Kompatibilitaets-Caches in playlist.py sind ausserhalb von
        generate_playlist None und brauchen kein Zutun.
        """
        from hpg_core.tolerances import reset_cache, write_override
        try:
            write_override({
                "groove_weight": self.groove_slider.value() / 100.0,
                "bass_weight": self.bass_slider.value() / 100.0,
                "timbre_weight": self.timbre_slider.value() / 100.0,
                "mood_weight": self.mood_slider.value() / 100.0,
            })
        except ValueError as exc:
            # Summe >= 1.0: Regler wuerden die bestehenden Faktoren ausloeschen
            self.statusBar().showMessage(f"Gewichte ungueltig: {exc}", 5000)
            return
        reset_cache()
        self.statusBar().showMessage(
            "Gewichte gespeichert — bei der naechsten Generierung wirksam", 5000
        )
```

Der Hinweis in der Statusleiste ist bewusst so formuliert: die Playlist wird **nicht** automatisch neu sortiert. Ein Umsortieren unter den Fuessen des Nutzers waere ueberraschend, und `main.py` hat keine bestehende Methode dafuer, die hier wiederverwendet werden koennte.

- [ ] **Step 3: `write_override` in `tolerances.py` ergaenzen**

```python
def write_override(gewichte: dict[str, float]) -> None:
    """Schreibt Gewichte fuer alle Genres in die Override-Datei.

    Die vier neuen Gewichte werden gesetzt, die vier bestehenden anteilig so
    skaliert, dass die Summe 1.0 bleibt.
    """
    neu_summe = sum(gewichte.values())
    if neu_summe >= 1.0:
        raise ValueError(f"Neue Gewichte summieren auf {neu_summe}, muss < 1.0 sein")
    rest = 1.0 - neu_summe
    basis = GENRE_TRANSITION_TOLERANCES[CANONICAL_GENRES[0]]
    alt_summe = sum(
        basis[k] for k in ("harmonic_weight", "bpm_weight", "energy_weight", "genre_weight")
    )
    daten = {}
    for genre in CANONICAL_GENRES:
        eintrag = dict(gewichte)
        for k in ("harmonic_weight", "bpm_weight", "energy_weight", "genre_weight"):
            eintrag[k] = basis[k] / alt_summe * rest
        daten[genre] = eintrag
    pfad = _override_pfad()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Test schreiben und laufen lassen**

An `tests/test_tolerances.py` anhaengen:

```python
def test_write_override_haelt_summe_bei_eins(tmp_path, monkeypatch):
    from hpg_core.tolerances import reset_cache, write_override

    datei = tmp_path / "transition_tolerances.json"
    monkeypatch.setenv("HPG_TOLERANCES_FILE", str(datei))
    write_override({"groove_weight": 0.20, "bass_weight": 0.10,
                    "timbre_weight": 0.05, "mood_weight": 0.05})
    reset_cache()

    werte = load_tolerances()
    summe = sum(werte["Psytrance"][k] for k in (
        "harmonic_weight", "bpm_weight", "energy_weight", "genre_weight",
        "groove_weight", "bass_weight", "timbre_weight", "mood_weight"))
    assert summe == pytest.approx(1.0, abs=1e-6)
```

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_tolerances.py -v --no-cov`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add main.py hpg_core/tolerances.py tests/test_tolerances.py
git commit -m "feat(gui): sliders for transition weights"
```

---

## Task 12: Cache loeschen und Sammlung analysieren

**Diese Aufgabe ist irreversibel und erfordert ausdrueckliche Zustimmung des Nutzers vor der Ausfuehrung.**

- [ ] **Step 1: Zustimmung einholen**

Dem Nutzer melden:

> ACHTUNG: Ich loesche 25 Dateien in `C:\Users\david\AppData\Local\HPG\` (`hpg_cache_v18` bis `v29` samt `-wal`, `-shm`, `.lock`, zusammen 1,46 MB). Verlust: 53 analysierte Tracks. Musikdateien und die Rekordbox-Datenbank bleiben unberuehrt. Fortfahren?

Ohne ausdrueckliches Ja nicht ausfuehren.

- [ ] **Step 2: Bestand dokumentieren**

Run:
```bash
ls -la /c/Users/david/AppData/Local/HPG/ > /tmp/hpg_cache_inventory_vor_loeschung.txt
cat /tmp/hpg_cache_inventory_vor_loeschung.txt
```

- [ ] **Step 3: Loeschen**

Run:
```bash
rm -f /c/Users/david/AppData/Local/HPG/hpg_cache_v*.db /c/Users/david/AppData/Local/HPG/hpg_cache_v*.db-wal /c/Users/david/AppData/Local/HPG/hpg_cache_v*.db-shm /c/Users/david/AppData/Local/HPG/hpg_cache_v*.lock
ls -la /c/Users/david/AppData/Local/HPG/
```
Expected: Verzeichnis leer.

- [ ] **Step 4: Schalter aktivieren**

In `hpg_core/config.py`:

```python
TRANSITION_FEATURES_ENABLED = True
```

- [ ] **Step 5: Volle Analyse anstossen**

Die App starten und die Sammlung analysieren lassen. Erwartung: 2480 Tracks, Groessenordnung 15-40 Minuten auf 16 Kernen.

- [ ] **Step 6: Abdeckung pruefen**

Run:
```bash
.\venv312\Scripts\python.exe -c "
import sqlite3, json, os
p = os.path.join(os.environ['LOCALAPPDATA'], 'HPG', 'hpg_cache_v30.db')
c = sqlite3.connect('file:' + p + '?mode=ro', uri=True)
gesamt = c.execute('select count(*) from cache').fetchone()[0]
mit = 0
for (blob,) in c.execute('select value from cache'):
    try:
        if json.loads(blob).get('groove_pattern'):
            mit += 1
    except Exception:
        pass
print(f'{mit} von {gesamt} Tracks mit Groove-Muster')
"
```
Expected: Der weit ueberwiegende Teil hat ein Muster. Ein hoher Anteil ohne Muster deutet auf fehlende `downbeat_confidence` hin und muss untersucht werden, bevor Teil 2 beginnt.

- [ ] **Step 7: Commit**

```bash
git add hpg_core/config.py
git commit -m "feat(scoring): enable transition features by default"
```

---

## Abschluss Teil 1

Nach Task 12 laeuft die App mit acht Scoring-Faktoren und den Startgewichten aus Spec 7.2. Die Reihenfolge beruecksichtigt Groove, Bassdruck, Timbre und Mood — die Gewichte sind aber noch geraten.

Teil 2 (`docs/superpowers/plans/2026-08-19-groove-scoring-teil2-kalibrierung.md`) ersetzt sie durch gemessene Werte aus echten DJ-Mixen.

**A/B-Vergleich fuer den Nutzer:** `TRANSITION_FEATURES_ENABLED` in `hpg_core/config.py` auf `False` setzen, dieselbe Trackauswahl generieren, vergleichen, zurueckstellen.
