# Groove-Scoring Teil 2: Kalibrierung aus DJ-Mixen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die geratenen Startgewichte aus Teil 1 durch Werte ersetzen, die aus echten DJ-Mixen gemessen sind — je Genre eigene Toleranzen und Gewichte.

**Architecture:** `tools/mix_mining.py` laedt einen Mix, findet die Uebergangsstellen ueber Neuheitsdetektion, spart die Blend-Zone aus und misst je ein stabiles Fenster davor und dahinter mit **derselben** `hpg_core/groove.py`, die auch in der App laeuft. Aus den Deltas echter Uebergaenge gegen Zufallspaare aus demselben Mix entstehen Gewichte (Trennschaerfe) und Toleranzen (Perzentile). Ein Holdout-Mix je Genre prueft das Ergebnis.

**Tech Stack:** Python 3.12 (`.\venv312\Scripts\python.exe`), numpy, librosa 0.11, soundfile 0.14, yt-dlp 2026.06.09, ffmpeg 6.1.1, pytest.

**Spec:** `docs/superpowers/specs/2026-08-19-groove-bass-timbre-scoring-design.md`, Abschnitte 10 und 11.

**Vorbedingung:** Teil 1 vollstaendig umgesetzt, `hpg_core/groove.py` vorhanden, Sammlung analysiert. Kommentare auf Deutsch, 4 Leerzeichen Einrueckung. Skripte unter `tools/` muessen den Parent-Pfad zu `sys.path` hinzufuegen.

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `tools/mix_mining.py` | CLI: Mix laden, minen, Kennzahlen schreiben | neu |
| `hpg_core/mix_analysis.py` | reine Funktionen: Uebergaenge finden, Deltas, Statistik | neu |
| `tests/test_mix_analysis.py` | Tests der reinen Funktionen | neu |
| `hpg_core/data/transition_tolerances.json` | gelernte Werte (aus `{}` befuellt) | aendern |

Die Trennung ist bewusst: alles Testbare liegt in `hpg_core/mix_analysis.py`, `tools/mix_mining.py` enthaelt nur Beschaffung, CLI und Dateiausgabe.

---

## Task 1: Uebergangserkennung

**Files:**
- Create: `hpg_core/mix_analysis.py`
- Test: `tests/test_mix_analysis.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_mix_analysis.py`:

```python
"""Tests fuer die Mix-Analyse (Uebergangserkennung und Statistik)."""
import numpy as np
import pytest

from hpg_core.mix_analysis import find_transitions


def _zwei_abschnitte(sr=22050, dauer_je=60.0):
    """Baut ein Signal aus zwei klar verschiedenen Klanghaelften."""
    n = int(dauer_je * sr)
    t = np.arange(n) / sr
    # erste Haelfte: tief, 80 Hz. zweite Haelfte: hell, 2000 Hz.
    a = (0.5 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)
    b = (0.5 * np.sin(2 * np.pi * 2000 * t)).astype(np.float32)
    return np.concatenate([a, b]), sr


def test_find_transitions_findet_den_wechsel_in_der_mitte():
    y, sr = _zwei_abschnitte()

    stellen = find_transitions(y, sr, min_abstand_s=20.0)

    assert len(stellen) >= 1
    # Der Wechsel liegt bei 60 s; Toleranz 8 s.
    assert any(abs(s - 60.0) < 8.0 for s in stellen)


def test_find_transitions_haelt_mindestabstand_ein():
    y, sr = _zwei_abschnitte()

    stellen = find_transitions(y, sr, min_abstand_s=20.0)

    for erste, zweite in zip(stellen, stellen[1:]):
        assert zweite - erste >= 20.0


def test_find_transitions_homogenes_signal_findet_nichts():
    sr = 22050
    t = np.arange(int(120 * sr)) / sr
    y = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    stellen = find_transitions(y, sr, min_abstand_s=20.0)

    assert stellen == []


def test_find_transitions_zu_kurzes_signal_gibt_leer():
    assert find_transitions(np.zeros(1000, dtype=np.float32), 22050) == []
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -v --no-cov`
Expected: FAIL mit `ModuleNotFoundError: No module named 'hpg_core.mix_analysis'`

- [ ] **Step 3: Implementierung**

`hpg_core/mix_analysis.py`:

```python
"""Mix-Analyse: Uebergaenge finden und Kennzahlen daraus gewinnen.

Reine Funktionen ohne Dateizugriff — die Beschaffung liegt in
tools/mix_mining.py. Grundlage der Kalibrierung (Spec Abschnitt 10).
"""
from __future__ import annotations

import numpy as np
import librosa

from .config import HOP_LENGTH

# Ein DJ-Mix blendet ueber; die Blend-Zone selbst ist unbrauchbar, weil dort
# beide Tracks uebereinanderliegen und jede Messung ein Mischwert waere.
BLEND_HALBBREITE_S = 20.0
# Laenge des stabilen Fensters vor bzw. hinter der Blend-Zone.
FENSTER_S = 30.0
# Ein Track im Mix ist selten kuerzer als das.
MIN_ABSTAND_S = 60.0


def find_transitions(
    y: np.ndarray,
    sr: int,
    min_abstand_s: float = MIN_ABSTAND_S,
    schwelle: float = 2.5,
) -> list[float]:
    """Findet Uebergangsstellen ueber Neuheit in Timbre und Bassband.

    Rueckgabe sind Sekundenpositionen, aufsteigend, mit Mindestabstand.
    Leere Liste, wenn das Signal zu kurz ist oder keine Stelle die Schwelle
    erreicht (homogenes Material).
    """
    if y is None or sr <= 0:
        return []
    dauer = len(y) / float(sr)
    if dauer < 2 * min_abstand_s:
        return []

    # Grobe Aufloesung genuegt und haelt lange Mixe bezahlbar.
    hop = HOP_LENGTH * 8
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
    mfcc = (mfcc - mfcc.mean(axis=1, keepdims=True)) / (
        mfcc.std(axis=1, keepdims=True) + 1e-9
    )

    # Neuheit = Abstand aufeinanderfolgender Timbre-Vektoren, geglaettet.
    diff = np.linalg.norm(np.diff(mfcc, axis=1), axis=0)
    fenster = max(3, int(5.0 * sr / hop))
    kern = np.ones(fenster) / fenster
    novelty = np.convolve(diff, kern, mode="same")

    if novelty.size == 0 or novelty.std() <= 0:
        return []
    z = (novelty - novelty.mean()) / novelty.std()

    zeiten = librosa.frames_to_time(np.arange(len(z)), sr=sr, hop_length=hop)
    kandidaten = [(float(z[i]), float(zeiten[i])) for i in range(len(z)) if z[i] >= schwelle]
    kandidaten.sort(reverse=True)  # staerkste zuerst

    gewaehlt: list[float] = []
    for _, t in kandidaten:
        if all(abs(t - g) >= min_abstand_s for g in gewaehlt):
            gewaehlt.append(t)
    return sorted(gewaehlt)
```

- [ ] **Step 4: Test laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -v --no-cov`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/mix_analysis.py tests/test_mix_analysis.py
git commit -m "feat(mix): detect transition points via timbre novelty"
```

---

## Task 2: Fenster-Paare und Deltas

**Files:**
- Modify: `hpg_core/mix_analysis.py`
- Test: `tests/test_mix_analysis.py`

- [ ] **Step 1: Failing Test anhaengen**

```python
from hpg_core.mix_analysis import TransitionSample, deltas_between, window_bounds


def test_window_bounds_spart_blendzone_aus():
    vor, nach = window_bounds(600.0, dauer=1200.0)

    assert vor[1] <= 600.0 - 20.0
    assert nach[0] >= 600.0 + 20.0
    assert vor[1] - vor[0] == pytest.approx(30.0)
    assert nach[1] - nach[0] == pytest.approx(30.0)


def test_window_bounds_am_rand_gibt_none():
    assert window_bounds(5.0, dauer=1200.0) is None
    assert window_bounds(1195.0, dauer=1200.0) is None


def test_deltas_between_identische_seiten_sind_null():
    gerade = [0.0] * 16
    for s in (0, 4, 8, 12):
        gerade[s] = 0.25
    a = TransitionSample(groove_pattern=gerade, bass_pattern=gerade,
                         sub_energy=0.3, bass_punch=3.0, brightness=50.0,
                         timbre=[1.0, 2.0, 3.0])
    d = deltas_between(a, a)

    assert d["groove_sim"] == pytest.approx(1.0)
    assert d["sub_delta"] == pytest.approx(0.0)
    assert d["brightness_delta"] == pytest.approx(0.0)
    assert d["timbre_sim"] == pytest.approx(1.0)


def test_deltas_between_offbeat_gegen_gerade_ist_unaehnlich():
    gerade = [0.0] * 16
    offbeat = [0.0] * 16
    for s in (0, 4, 8, 12):
        gerade[s] = 0.25
    for s in (2, 6, 10, 14):
        offbeat[s] = 0.25
    a = TransitionSample(groove_pattern=gerade, bass_pattern=gerade,
                         sub_energy=0.3, bass_punch=3.0, brightness=50.0,
                         timbre=[1.0, 0.0])
    b = TransitionSample(groove_pattern=offbeat, bass_pattern=offbeat,
                         sub_energy=0.3, bass_punch=3.0, brightness=50.0,
                         timbre=[0.0, 1.0])

    d = deltas_between(a, b)

    assert d["groove_sim"] < 0.2
    assert d["timbre_sim"] < 0.2
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'TransitionSample'`

- [ ] **Step 3: Implementierung anhaengen**

```python
from dataclasses import dataclass, field

from .transition_features import cosine_similarity


@dataclass
class TransitionSample:
    """Messwerte eines stabilen Fensters neben einer Uebergangsstelle."""

    groove_pattern: list[float] = field(default_factory=list)
    bass_pattern: list[float] = field(default_factory=list)
    sub_energy: float = 0.0
    bass_punch: float = 0.0
    brightness: float = 0.0
    timbre: list[float] = field(default_factory=list)


def window_bounds(
    stelle: float, dauer: float,
    blend: float = BLEND_HALBBREITE_S, fenster: float = FENSTER_S,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Grenzen der stabilen Fenster vor und hinter einer Uebergangsstelle.

    None, wenn eines der Fenster nicht vollstaendig ins Signal passt — ein
    angeschnittenes Fenster wuerde verzerrte Kennzahlen liefern.
    """
    vor_ende = stelle - blend
    vor_start = vor_ende - fenster
    nach_start = stelle + blend
    nach_ende = nach_start + fenster
    if vor_start < 0.0 or nach_ende > dauer:
        return None
    return (vor_start, vor_ende), (nach_start, nach_ende)


def deltas_between(a: TransitionSample, b: TransitionSample) -> dict[str, float]:
    """Die vier Kennzahlen eines Uebergangs (Spec Abschnitt 10.4)."""
    groove_sim = cosine_similarity(a.bass_pattern, b.bass_pattern)
    if groove_sim is None:
        groove_sim = cosine_similarity(a.groove_pattern, b.groove_pattern)
    timbre_sim = cosine_similarity(a.timbre, b.timbre)
    return {
        "groove_sim": float(groove_sim) if groove_sim is not None else 0.0,
        "sub_delta": abs(a.sub_energy - b.sub_energy),
        "punch_delta": abs(a.bass_punch - b.bass_punch),
        "brightness_delta": abs(a.brightness - b.brightness),
        "timbre_sim": float(timbre_sim) if timbre_sim is not None else 0.0,
    }
```

- [ ] **Step 4: Test laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -v --no-cov`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/mix_analysis.py tests/test_mix_analysis.py
git commit -m "feat(mix): window extraction and transition deltas"
```

---

## Task 3: Trennschaerfe und Toleranzen

Der eigentliche Lernschritt. Echte Uebergaenge gegen Zufallspaare aus demselben Mix — das braucht keine Trackliste.

**Files:**
- Modify: `hpg_core/mix_analysis.py`
- Test: `tests/test_mix_analysis.py`

- [ ] **Step 1: Failing Test anhaengen**

```python
from hpg_core.mix_analysis import discrimination_auc, learn_weights, tolerance_percentile


def test_discrimination_auc_perfekte_trennung_ist_eins():
    echt = [0.9, 0.95, 0.92]
    zufall = [0.1, 0.2, 0.15]
    assert discrimination_auc(echt, zufall, hoeher_ist_besser=True) == pytest.approx(1.0)


def test_discrimination_auc_keine_trennung_ist_halb():
    werte = [0.5, 0.5, 0.5]
    assert discrimination_auc(werte, werte, hoeher_ist_besser=True) == pytest.approx(0.5)


def test_discrimination_auc_umgekehrte_richtung():
    # Bei Abstaenden ist NIEDRIGER besser.
    echt = [0.1, 0.15]
    zufall = [0.8, 0.9]
    assert discrimination_auc(echt, zufall, hoeher_ist_besser=False) == pytest.approx(1.0)


def test_tolerance_percentile_nimmt_90er():
    werte = list(range(101))  # 0..100
    assert tolerance_percentile(werte, 90.0) == pytest.approx(90.0, abs=1.0)


def test_tolerance_percentile_leer_gibt_none():
    assert tolerance_percentile([], 90.0) is None


def test_learn_weights_summiert_auf_dreissig_prozent():
    # Groove trennt perfekt, der Rest gar nicht -> Groove bekommt das Meiste.
    auc = {"groove": 1.0, "bass": 0.5, "timbre": 0.5, "mood": 0.5}
    gewichte = learn_weights(auc, gesamt=0.30)

    assert sum(gewichte.values()) == pytest.approx(0.30)
    assert gewichte["groove"] > gewichte["bass"]
    assert all(w >= 0.0 for w in gewichte.values())


def test_learn_weights_ohne_trennschaerfe_verteilt_gleich():
    auc = {"groove": 0.5, "bass": 0.5, "timbre": 0.5, "mood": 0.5}
    gewichte = learn_weights(auc, gesamt=0.30)

    for wert in gewichte.values():
        assert wert == pytest.approx(0.075)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'discrimination_auc'`

- [ ] **Step 3: Implementierung anhaengen**

```python
def discrimination_auc(
    echte: list[float], zufaellige: list[float], hoeher_ist_besser: bool = True
) -> float:
    """Trennschaerfe als AUC: Anteil der Paare, die richtig geordnet sind.

    0.5 heisst "der Faktor unterscheidet echte Uebergaenge nicht von
    zufaelligen" und fuehrt spaeter zu geringem Gewicht (Spec 10.4).
    """
    if not echte or not zufaellige:
        return 0.5
    treffer = 0
    gesamt = 0
    for e in echte:
        for z in zufaellige:
            gesamt += 1
            if e == z:
                treffer += 0.5
            elif (e > z) == hoeher_ist_besser:
                treffer += 1
    return float(treffer / gesamt) if gesamt else 0.5


def tolerance_percentile(werte: list[float], perzentil: float = 90.0) -> float | None:
    """Grenze, die in `perzentil` Prozent der echten Uebergaenge gilt."""
    if not werte:
        return None
    return float(np.percentile(np.asarray(werte, dtype=float), perzentil))


def learn_weights(auc: dict[str, float], gesamt: float = 0.30) -> dict[str, float]:
    """Verteilt `gesamt` auf die Faktoren nach ihrer Trennschaerfe.

    Grundlage ist der Abstand zu 0.5 — ein Faktor, der nichts unterscheidet,
    bekommt nichts ueber den Gleichanteil hinaus.
    """
    if not auc:
        return {}
    ueberschuss = {k: max(0.0, v - 0.5) for k, v in auc.items()}
    summe = sum(ueberschuss.values())
    if summe <= 0.0:
        gleich = gesamt / len(auc)
        return {k: gleich for k in auc}
    return {k: gesamt * (v / summe) for k, v in ueberschuss.items()}
```

- [ ] **Step 4: Test laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -v --no-cov`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add hpg_core/mix_analysis.py tests/test_mix_analysis.py
git commit -m "feat(mix): learn weights from discrimination power"
```

---

## Task 4: CLI-Werkzeug

**Files:**
- Create: `tools/mix_mining.py`

- [ ] **Step 1: Werkzeug schreiben**

`tools/mix_mining.py`:

```python
"""Kalibriert die Uebergangs-Toleranzen aus echten DJ-Mixen.

Aufruf:
    python tools/mix_mining.py --genre Psytrance --mix pfad_oder_url [...] \
        --holdout pfad_oder_url --out kennzahlen_psytrance.json

Laedt YouTube-Quellen verlustfrei als Ogg/Opus (Container-Wechsel, keine
Neukodierung), misst die Uebergaenge und schreibt Kennzahlen als JSON.
Die Mix-Audios werden danach geloescht (Spec Abschnitt 10.5).
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import librosa
import numpy as np

from hpg_core.groove import extract_groove
from hpg_core.mix_analysis import (
    TransitionSample, deltas_between, discrimination_auc, find_transitions,
    learn_weights, tolerance_percentile, window_bounds,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("mix_mining")

SR = 22050
ZUFALLSPAARE_JE_MIX = 60


def beschaffen(quelle: str, ziel_dir: Path) -> Path | None:
    """Lokale Datei durchreichen, URL per yt-dlp als Ogg/Opus holen."""
    p = Path(quelle)
    if p.is_file():
        return p
    ziel = ziel_dir / "mix.%(ext)s"
    befehl = [
        "yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "opus",
        "-o", str(ziel), quelle,
    ]
    try:
        subprocess.run(befehl, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning(f"Download fehlgeschlagen fuer {quelle}: {exc}")
        return None
    treffer = list(ziel_dir.glob("mix.*"))
    return treffer[0] if treffer else None


def fenster_messen(y: np.ndarray, sr: int, start: float, ende: float) -> TransitionSample:
    """Misst ein stabiles Fenster mit derselben Logik wie die App."""
    a, b = int(start * sr), int(ende * sr)
    stueck = y[a:b]
    if len(stueck) == 0:
        return TransitionSample()

    tempo, _ = librosa.beat.beat_track(y=stueck, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    g = extract_groove(stueck, sr, bpm=bpm, first_downbeat=0.0)
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=stueck, sr=sr)))
    mfcc = librosa.feature.mfcc(y=stueck, sr=sr, n_mfcc=13)
    return TransitionSample(
        groove_pattern=g.groove_pattern,
        bass_pattern=g.bass_pattern,
        sub_energy=g.sub_energy,
        bass_punch=g.bass_punch,
        # Helligkeit auf 0-100 skaliert, analog zu Track.brightness
        brightness=min(100.0, centroid / 80.0),
        timbre=mfcc.mean(axis=1).tolist(),
    )


def mix_minen(pfad: Path) -> tuple[list[dict], list[TransitionSample]]:
    """Liefert die Deltas echter Uebergaenge und alle gemessenen Fenster."""
    y, sr = librosa.load(str(pfad), sr=SR, mono=True)
    dauer = len(y) / sr
    logger.info(f"{pfad.name}: {dauer/60:.1f} min geladen")

    echte, fenster = [], []
    for stelle in find_transitions(y, sr):
        grenzen = window_bounds(stelle, dauer)
        if grenzen is None:
            continue
        (v0, v1), (n0, n1) = grenzen
        a = fenster_messen(y, sr, v0, v1)
        b = fenster_messen(y, sr, n0, n1)
        echte.append(deltas_between(a, b))
        fenster.extend([a, b])

    logger.info(f"{pfad.name}: {len(echte)} Uebergaenge gemessen")
    return echte, fenster


def zufallspaare(fenster: list[TransitionSample], anzahl: int) -> list[dict]:
    """Negativbeispiele: beliebige Fensterpaare aus demselben Mix."""
    if len(fenster) < 2:
        return []
    rng = random.Random(42)
    out = []
    for _ in range(anzahl):
        a, b = rng.sample(fenster, 2)
        out.append(deltas_between(a, b))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--genre", required=True)
    ap.add_argument("--mix", action="append", required=True)
    ap.add_argument("--holdout")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    echte, fenster = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for quelle in args.mix:
            pfad = beschaffen(quelle, Path(tmp))
            if pfad is None:
                continue
            e, f = mix_minen(pfad)
            echte.extend(e)
            fenster.extend(f)

    if not echte:
        logger.error("Keine Uebergaenge gefunden — Abbruch")
        return 1

    zufall = zufallspaare(fenster, ZUFALLSPAARE_JE_MIX)

    auc = {
        "groove": discrimination_auc(
            [d["groove_sim"] for d in echte], [d["groove_sim"] for d in zufall], True),
        "bass": discrimination_auc(
            [d["sub_delta"] for d in echte], [d["sub_delta"] for d in zufall], False),
        "timbre": discrimination_auc(
            [d["timbre_sim"] for d in echte], [d["timbre_sim"] for d in zufall], True),
        "mood": discrimination_auc(
            [d["brightness_delta"] for d in echte],
            [d["brightness_delta"] for d in zufall], False),
    }
    gewichte = learn_weights(auc, gesamt=0.30)

    ergebnis = {
        "genre": args.genre,
        "uebergaenge": len(echte),
        "zufallspaare": len(zufall),
        "auc": auc,
        "gewichte": {f"{k}_weight": v for k, v in gewichte.items()},
        "toleranzen": {
            "groove_sim_floor": tolerance_percentile(
                [d["groove_sim"] for d in echte], 10.0),
            "bass_delta_max": tolerance_percentile(
                [d["sub_delta"] for d in echte], 90.0),
            "brightness_delta_max": tolerance_percentile(
                [d["brightness_delta"] for d in echte], 90.0),
        },
    }
    Path(args.out).write_text(json.dumps(ergebnis, indent=2), encoding="utf-8")
    logger.info(f"AUC: {auc}")
    logger.info(f"geschrieben: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Auf einem Mix probelaufen lassen**

Run (Pfad bzw. URL vom Nutzer):
```bash
.\venv312\Scripts\python.exe tools/mix_mining.py --genre Psytrance --mix "<pfad-oder-url>" --out kennzahlen_psytrance.json
```
Expected: Log meldet Ladedauer, Anzahl gefundener Uebergaenge (Groessenordnung 30-60 bei 60-120 min) und die AUC-Werte. Findet der Lauf unter 10 Uebergaenge, ist `schwelle` in `find_transitions` zu hoch — auf 2.0 senken und erneut laufen lassen.

- [ ] **Step 3: Commit**

```bash
git add tools/mix_mining.py
git commit -m "feat(tools): mix mining CLI for tolerance calibration"
```

---

## Task 5: Holdout-Validierung

**Files:**
- Modify: `tools/mix_mining.py`
- Test: `tests/test_mix_analysis.py`

- [ ] **Step 1: Failing Test anhaengen**

```python
from hpg_core.mix_analysis import holdout_passed


def test_holdout_passed_bei_klarer_trennung():
    assert holdout_passed(echte_scores=[0.8, 0.85, 0.9],
                          zufall_scores=[0.3, 0.35, 0.4]) is True


def test_holdout_failed_ohne_trennung():
    assert holdout_passed(echte_scores=[0.5, 0.5],
                          zufall_scores=[0.5, 0.5]) is False


def test_holdout_failed_bei_umgekehrter_ordnung():
    assert holdout_passed(echte_scores=[0.2, 0.25],
                          zufall_scores=[0.8, 0.9]) is False
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -k holdout -v --no-cov`
Expected: FAIL mit `ImportError: cannot import name 'holdout_passed'`

- [ ] **Step 3: Implementierung anhaengen**

An `hpg_core/mix_analysis.py`:

```python
# Ab dieser AUC gilt die Trennung als belastbar genug fuer den Einbau.
HOLDOUT_AUC_MIN = 0.65


def holdout_passed(
    echte_scores: list[float], zufall_scores: list[float],
    schwelle: float = HOLDOUT_AUC_MIN,
) -> bool:
    """Prueft am zurueckgehaltenen Mix, ob echte Uebergaenge hoeher scoren.

    Faellt der Test durch, taugen die gelernten Werte fuer dieses Genre nicht
    und werden NICHT eingebaut (Spec Abschnitt 11).
    """
    return discrimination_auc(echte_scores, zufall_scores, True) >= schwelle
```

- [ ] **Step 4: In der CLI verdrahten**

In `main()` nach der Gewichtsberechnung ergaenzen:

```python
    if args.holdout:
        with tempfile.TemporaryDirectory() as tmp:
            pfad = beschaffen(args.holdout, Path(tmp))
            if pfad is not None:
                h_echte, h_fenster = mix_minen(pfad)
                h_zufall = zufallspaare(h_fenster, ZUFALLSPAARE_JE_MIX)
                bestanden = holdout_passed(
                    [d["groove_sim"] for d in h_echte],
                    [d["groove_sim"] for d in h_zufall],
                )
                ergebnis["holdout_bestanden"] = bestanden
                if not bestanden:
                    logger.warning(
                        f"Holdout fuer {args.genre} NICHT bestanden — "
                        f"gelernte Werte nicht einbauen"
                    )
```

Import ergaenzen: `holdout_passed` in die bestehende `from hpg_core.mix_analysis import (...)`-Zeile aufnehmen.

- [ ] **Step 5: Tests laufen lassen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_mix_analysis.py -v --no-cov`
Expected: 18 passed

- [ ] **Step 6: Commit**

```bash
git add hpg_core/mix_analysis.py tools/mix_mining.py tests/test_mix_analysis.py
git commit -m "feat(mix): holdout validation for learned tolerances"
```

---

## Task 6: Alle neun Genres kalibrieren

Reihenfolge nach Anteil an der Sammlung (Spec 10.6).

- [ ] **Step 1: Material je Genre vom Nutzer anfordern**

Pro Genre 2-3 Mixe (60-120 min) plus einen Holdout-Mix. Reihenfolge:
Psytrance, Progressive, Techno, Melodic Techno, Tech House, Minimal,
Deep House, Trance, Drum & Bass.

- [ ] **Step 2: Je Genre laufen lassen**

```bash
.\venv312\Scripts\python.exe tools/mix_mining.py --genre Psytrance \
  --mix "<mix1>" --mix "<mix2>" --mix "<mix3>" \
  --holdout "<holdout>" --out kennzahlen_psytrance.json
```

Expected je Lauf: mindestens 30 Uebergaenge, `holdout_bestanden: true`.

- [ ] **Step 3: Ergebnisse zusammenfuehren**

Run:
```bash
.\venv312\Scripts\python.exe -c "
import json, glob
from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES

daten = {}
for pfad in glob.glob('kennzahlen_*.json'):
    r = json.load(open(pfad, encoding='utf-8'))
    if not r.get('holdout_bestanden', False):
        print(f\"UEBERSPRUNGEN (Holdout gescheitert): {r['genre']}\")
        continue
    eintrag = dict(GENRE_TRANSITION_TOLERANCES[r['genre']])
    eintrag.update(r['gewichte'])
    for k, v in r['toleranzen'].items():
        if v is not None:
            eintrag[k] = v
    # bestehende vier auf den Rest skalieren, Summe bleibt 1.0
    neu = sum(r['gewichte'].values())
    alt_keys = ('harmonic_weight','bpm_weight','energy_weight','genre_weight')
    alt_summe = sum(GENRE_TRANSITION_TOLERANCES[r['genre']][k] for k in alt_keys)
    for k in alt_keys:
        eintrag[k] = GENRE_TRANSITION_TOLERANCES[r['genre']][k] / alt_summe * (1.0 - neu)
    daten[r['genre']] = eintrag

fehlend = set(CANONICAL_GENRES) - set(daten)
if fehlend:
    print('ohne gelernte Werte, behalten Defaults:', sorted(fehlend))
json.dump(daten, open('hpg_core/data/transition_tolerances.json','w',encoding='utf-8'), indent=2)
print(f'{len(daten)} Genres geschrieben')
"
```

- [ ] **Step 4: Gewichtssumme pruefen**

Run: `.\venv312\Scripts\python.exe -m pytest tests/test_tolerances.py -v --no-cov`
Expected: alle passed — insbesondere `test_gewichte_summieren_auf_eins` gegen die neuen Werte.

- [ ] **Step 5: Volle Suite**

Run: `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q --no-cov`
Expected: keine neuen Fehlschlaege.

- [ ] **Step 6: Commit**

```bash
git add hpg_core/data/transition_tolerances.json
git commit -m "feat(scoring): calibrated tolerances from real DJ mixes"
```

---

## Task 7: A/B durch den Nutzer

- [ ] **Step 1: Vergleich vorbereiten**

Dieselbe Trackauswahl zweimal generieren:
1. `TRANSITION_FEATURES_ENABLED = False` -> Playlist als `ab_alt.m3u8` exportieren
2. `TRANSITION_FEATURES_ENABLED = True` -> Playlist als `ab_neu.m3u8` exportieren

- [ ] **Step 2: Unterschied beziffern**

Run:
```bash
.\venv312\Scripts\python.exe -c "
alt = [l.strip() for l in open('ab_alt.m3u8',encoding='utf-8') if l.strip() and not l.startswith('#')]
neu = [l.strip() for l in open('ab_neu.m3u8',encoding='utf-8') if l.strip() and not l.startswith('#')]
gleich = sum(1 for a,b in zip(alt,neu) if a==b)
print(f'{gleich} von {len(alt)} Positionen unveraendert')
"
```

Eine Playlist, die sich gar nicht aendert, deutet auf zu geringe Gewichte oder fehlende Groove-Daten hin — dann Abdeckung aus Teil 1 Task 12 Step 6 pruefen.

- [ ] **Step 3: Urteil des Nutzers einholen**

Beide Playlists anhoeren lassen. Bei Bedarf Gewichte ueber die Regler aus Teil 1 Task 11 nachziehen — das kostet keine Neuanalyse.

---

## Abschluss

Nach Task 7 ist jede Zahl im Scoring entweder aus echten Mixen gemessen oder vom Nutzer bewusst gesetzt. Faktoren, deren Holdout scheiterte, behalten die Startgewichte und sind in `hpg_core/data/transition_tolerances.json` durch ihr Fehlen erkennbar.
