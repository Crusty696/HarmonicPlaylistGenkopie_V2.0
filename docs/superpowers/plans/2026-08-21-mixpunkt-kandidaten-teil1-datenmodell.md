# Mixpunkt-Kandidaten Teil 1 (Datenmodell) — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeder analysierte Track traegt Rekordbox-Phrasen (PSSI), Cues mit Provenienz, ein Phrasengitter und je 3–8 Mix-In-/Mix-Out-Kandidaten mit lokalen Messwerten an der Naht — persistiert in Cache-Version 34. Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`, Abschnitt 1.

**Architecture:** Zwei neue Module: `hpg_core/rekordbox_phrases.py` (PSSI-Leser, reine Funktionen ueber pyrekordbox-AnlzFile-Objekte) und `hpg_core/mix_candidates.py` (Dataclass `MixCandidate`, Schemata-Erzeugung, Gates, Quantisierung, lokale Messung). `analysis.py` ruft beides in BEIDEN Pfaden (Rekordbox-Fast-Path, Voll-Pfad) auf; `models.Track` bekommt fuenf Listenfelder; `caching.py` validiert sie und bumpt `CACHE_VERSION` 33 → 34. Die Cue-Positionsheuristik ("2. Cue = In, letzter = Out") entfaellt laut Spec; benannte Cues bleiben Override. `Track.mix_in_point/mix_out_point` bleiben in Teil 1 das Ergebnis von `calculate_genre_aware_mix_points` + benanntem Cue (Rang-1-Zuweisung aus der Paar-Bewertung ist Teil 2/4).

**Tech Stack:** Python 3.12 (`.\venv312\Scripts\python.exe`), librosa, numpy, scipy, pyloudnorm, pyrekordbox 0.4.4, pytest (`-n auto`, `--no-cov` fuer schnelle Laeufe).

**Auflagen des Nutzers:** genau so wie in der Spec, vollstaendig, keine Annahmen; jede Zahl gemessen oder als Startwert markiert. Waechter `hpg-waechter` an Tor 1 (Vorhaben) und Tor 2 (Diff) vor jedem Commit.

**Vorab verifizierte Fakten (2026-08-21; alle 2475 EXT-Dateien unter `D:\PIONEER\Master\share\PIONEER\USBANLZ`, Waechter-Nachmessung):**
- `AnlzFile.parse_file(<ANLZ0000.EXT>).get_tag("PSSI").content` hat `mood`, `end_beat`, `entries[]` mit `index, beat, kind, k1, k2, k3, fill, beat_fill`.
- `entry.beat` ist ein **1-basierter Index in die PQTZ-Beatliste** (`ANLZ0000.DAT`, `get_tag("PQTZ").get()` → `(beats, bpms, times)`); Zeit = `times[beat-1]` (0-basiert passt in 0 Faellen). Phrasenstarts liegen auf Takt-1, Ausnahme: der erste Eintrag (beat=1) liegt im Vollbestand (2470 DAT) in 677 Faellen auf beatnum 2, 74× auf 3, 70× auf 4 (Beatgrid beginnt nicht auf der 1).
- Mood-Verteilung: 2370× mood 1, 93× mood 2, 9× mood 3. Mood 1 nutzt Kinds {1,2,3,5,6}; Kind 1 ist in 2370/2370 der erste, Kind 6 in 2370/2370 der letzte Eintrag → 1 Intro, 2 Up, 3 Down, 5 Chorus, 6 Outro.
- Mood 2/3: Kind 1 in 100/102 der erste, **Kind 10 in 100/102 der letzte** Eintrag → Zuordnung 1 Intro, 2–7 Verse 1–6, 8 Bridge, 9 Chorus, 10 Outro (Beat-Link-Schema, durch eigene Daten an Anfang/Ende gestuetzt; Verse/Bridge/Chorus dazwischen NICHT aus eigenen Daten pruefbar — so im Code kommentieren). Unbekannte Kinds (>10) werden "Unbekannt(n)" beschriftet und geloggt.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| Create `hpg_core/rekordbox_phrases.py` | PSSI → `list[dict]` Phrasen (start_s, end_s, label, mood, kind, fill), Label-Tabellen, `phrase_grid` aus Phrasenstarts |
| Create `hpg_core/mix_candidates.py` | `MixCandidate`, `CUE_IN_PATTERN/CUE_OUT_PATTERN`, Cue-Normalisierung mit Provenienz, Schemata, Gates, `quantize_to_points`, Dedupe/Kappung, `measure_candidate_window`, `build_track_candidates` |
| Modify `hpg_core/rekordbox_importer.py` | `_read_anlz_files(content_id)` als wiederverwendbarer Helfer, `get_phrases(file_path)` |
| Modify `hpg_core/models.py` | Track-Felder `phrases`, `cue_points`, `phrase_grid`, `mix_in_candidates`, `mix_out_candidates` |
| Modify `hpg_core/caching.py` | `CACHE_VERSION = 34`, `TRACK_LIST_FIELDS` + 5 Namen |
| Modify `hpg_core/config.py` | neue Konstanten (Fenster, Gates, Startwerte) |
| Modify `hpg_core/analysis.py` | beide Pfade: Phrasen/Cues/Kandidaten berechnen, Cue-Heuristik entfernen |
| Create `tools/kandidaten_messen.py` | Regressionsmessung ueber gecachte Tracks (Kandidatenzahl, Schemata, Analysezeit) |
| Tests | `tests/test_rekordbox_phrases.py`, `tests/test_mix_candidates.py`, Ergaenzungen in `tests/test_caching.py`, `tests/test_models.py`, `tests/test_cue_intro_guard.py`, `tests/test_analyze_track.py` |

Einrueckung: `analysis.py`, `models.py`, `caching.py`, `config.py`, `rekordbox_importer.py` nutzen 4 Leerzeichen; `dj_brain.py` 2. Neue Module: 4. Tests: wie die jeweils bestehende Datei. Kommentare Deutsch.

---

### Task 0: Waechter Tor 1

- [ ] **Step 1: Vorhaben pruefen lassen**

Subagent `hpg-waechter` mit dem Vorhaben: Dateien/Funktionen/Konstanten aus der Tabelle oben, Anlass Spec Abschnitt 1, ausdruecklich: Cue-Heuristik entfaellt (Tests in `tests/test_cue_intro_guard.py`, die NUR die Heuristik pruefen, werden auf die neue Quelle `mix_candidates.normalize_cues` umgestellt — das ist beauftragt, keine Anpassung an den Code). Erwartung: DURCHGEWUNKEN oder MIT AUFLAGEN; Auflagen vor Task 1 einarbeiten.

---

### Task 1: Konstanten in `config.py`

**Files:**
- Modify: `hpg_core/config.py` (nach `KEY_CONFIDENCE_UNCERTAIN`, Zeile ~64)
- Test: `tests/test_config.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_config.py — anhaengen
def test_kandidaten_konstanten_vorhanden_und_plausibel():
    from hpg_core import config
    assert config.KANDIDATEN_MAX_JE_SEITE == 8
    assert config.KANDIDATEN_MIN_JE_SEITE == 3
    assert config.KANDIDATEN_FENSTER_PHRASEN == 1
    assert config.CUE_DEDUPE_SEC == 2.0
    assert config.KICK_AKTIV_MIN_DBFS == -35.0
    assert config.KICK_AKTIV_ONBEAT_MIN == 0.40
    assert config.ENERGIE_TREND_SCHWELLE == 10
    assert config.ENERGIE_NEUHEIT_MIN == 20
    assert config.KANDIDATEN_AUDIO_SR == 22050
```

- [ ] **Step 2: Run → FAIL** `.\venv312\Scripts\python.exe -m pytest tests/test_config.py -q --no-cov` → `AttributeError: ... KANDIDATEN_MAX_JE_SEITE`

- [ ] **Step 3: Konstanten**

```python
# === Mixpunkt-Kandidaten (Spec 2026-08-21, Abschnitt 1) ===
# Anzahl Kandidaten je Seite (Mix-In / Mix-Out) nach Dedupe und Kappung.
KANDIDATEN_MIN_JE_SEITE = 3
KANDIDATEN_MAX_JE_SEITE = 8
# Messfenster fuer lokale Werte: +-1 Phrase um den Kandidaten.
KANDIDATEN_FENSTER_PHRASEN = 1
# Audio fuer lokale Merkmale (wie alle uebrigen librosa-Merkmale, mono).
# LUFS wird davon getrennt in nativer Samplerate/Kanalzahl gemessen.
KANDIDATEN_AUDIO_SR = 22050
# Cues naeher als 2 s gelten als Duplikat (bisher inline in analysis.py).
CUE_DEDUPE_SEC = 2.0
# kick_aktiv: Bass-RMS (<=160 Hz) ueber dieser Schwelle UND On-Beat-Anteil
# des lokalen Bassmusters ueber KICK_AKTIV_ONBEAT_MIN. STARTWERTE, nicht
# gemessen — der Hoertest (Teil 3) prueft sie.
KICK_AKTIV_MIN_DBFS = -35.0
KICK_AKTIV_ONBEAT_MIN = 0.40
# energy_trend: |Energie nach - Energie vor| >= Schwelle → rising/falling.
ENERGIE_TREND_SCHWELLE = 10
# Schema "energie_neuheit": Sektionsgrenze zaehlt, wenn der Energiesprung
# zwischen den Nachbarsektionen mindestens so gross ist (0-100-Skala).
ENERGIE_NEUHEIT_MIN = 20
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add hpg_core/config.py tests/test_config.py && git commit -m "feat(config): Konstanten fuer Mixpunkt-Kandidaten"`

---

### Task 2: PSSI-Leser `hpg_core/rekordbox_phrases.py`

**Files:**
- Create: `hpg_core/rekordbox_phrases.py`
- Test: `tests/test_rekordbox_phrases.py`

- [ ] **Step 1: Failing tests (Fake-Tag-Objekte, kein Rekordbox noetig)**

```python
"""Tests fuer den PSSI-Phrasenleser (Rekordbox ANLZ0000.EXT)."""
from types import SimpleNamespace

import numpy as np
import pytest

from hpg_core.rekordbox_phrases import (
    PHRASE_LABELS_HIGH, PHRASE_LABELS_MIDLOW, phrases_from_anlz,
    phrase_grid_from_phrases,
)


class _Tag:
    def __init__(self, content):
        self.content = content


class _Pqtz:
    def __init__(self, times):
        self._times = np.asarray(times, dtype=float)

    def get(self):
        n = len(self._times)
        beats = np.array([(i % 4) + 1 for i in range(n)], dtype=np.int8)
        return beats, np.full(n, 128.0), self._times


class _Anlz:
    def __init__(self, tags):
        self._tags = tags

    def get_tag(self, key):
        if key not in self._tags:
            raise KeyError(key)
        return self._tags[key]


def _entry(index, beat, kind, fill=0, beat_fill=0):
    return SimpleNamespace(index=index, beat=beat, kind=kind, k1=0, k2=0, k3=0,
                           fill=fill, beat_fill=beat_fill)


def _beatgrid(n_beats, spb=0.46875):  # 128 BPM
    return [i * spb for i in range(n_beats)]


def test_mood_high_labels():
    assert PHRASE_LABELS_HIGH == {1: "Intro", 2: "Up", 3: "Down", 5: "Chorus", 6: "Outro"}
    assert PHRASE_LABELS_MIDLOW[1] == "Intro" and PHRASE_LABELS_MIDLOW[9] == "Chorus"
    assert PHRASE_LABELS_MIDLOW[8] == "Bridge" and PHRASE_LABELS_MIDLOW[10] == "Outro"


def test_phrasen_aus_high_mood_mit_zeiten_aus_pqtz():
    times = _beatgrid(129)
    pssi = _Tag(SimpleNamespace(mood=1, end_beat=129, entries=[
        _entry(1, 1, 1), _entry(2, 33, 2), _entry(3, 65, 5), _entry(4, 97, 6)]))
    phrases = phrases_from_anlz(_Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=60.0)
    assert [p["label"] for p in phrases] == ["Intro", "Up", "Chorus", "Outro"]
    assert phrases[0]["start_s"] == pytest.approx(0.0)
    assert phrases[1]["start_s"] == pytest.approx(times[32])
    assert phrases[0]["end_s"] == pytest.approx(phrases[1]["start_s"])
    assert phrases[-1]["end_s"] == pytest.approx(times[128])  # end_beat → Zeit
    assert all(p["mood"] == 1 for p in phrases)
    assert phrases[2]["kind"] == 5


def test_unbekannter_kind_wird_als_unbekannt_beschriftet_nicht_verworfen():
    times = _beatgrid(65)
    pssi = _Tag(SimpleNamespace(mood=2, end_beat=65, entries=[_entry(1, 1, 1), _entry(2, 17, 11), _entry(3, 33, 10)]))
    phrases = phrases_from_anlz(_Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=40.0)
    assert phrases[1]["label"] == "Unbekannt(11)" and phrases[2]["label"] == "Outro"


def test_beat_ausserhalb_des_beatgrids_wird_geklemmt():
    times = _beatgrid(10)
    pssi = _Tag(SimpleNamespace(mood=1, end_beat=50, entries=[_entry(1, 1, 1), _entry(2, 40, 6)]))
    phrases = phrases_from_anlz(_Anlz({"PSSI": pssi}), _Anlz({"PQTZ": _Pqtz(times)}), duration=30.0)
    assert phrases[1]["start_s"] == pytest.approx(times[-1])
    assert phrases[1]["end_s"] == pytest.approx(30.0)


def test_ohne_pssi_oder_pqtz_leere_liste():
    assert phrases_from_anlz(_Anlz({}), _Anlz({}), duration=30.0) == []
    assert phrases_from_anlz(None, None, duration=30.0) == []


def test_phrase_grid_sind_die_phrasenstarts_plus_ende():
    phrases = [
        {"start_s": 0.0, "end_s": 15.0, "label": "Intro", "mood": 1, "kind": 1, "fill": 0},
        {"start_s": 15.0, "end_s": 30.0, "label": "Up", "mood": 1, "kind": 2, "fill": 0},
    ]
    assert phrase_grid_from_phrases(phrases) == [0.0, 15.0, 30.0]
    assert phrase_grid_from_phrases([]) == []
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: hpg_core.rekordbox_phrases`)

- [ ] **Step 3: Modul**

```python
"""Rekordbox-Phrasen (PSSI-Tag aus ANLZ0000.EXT) lesen.

Reine Funktionen ueber pyrekordbox-AnlzFile-Objekte (oder Objekte mit
derselben Oberflaeche `get_tag(key).content`). Zeiten kommen aus dem
Beatgrid (PQTZ, ANLZ0000.DAT): `entry.beat` ist ein 1-basierter Index in
die PQTZ-Beatliste (verifiziert 2026-08-21 an 699 von 2475 EXT-Dateien;
0-basiert passt nie; der erste Eintrag liegt in 677/2470 auf beatnum 2, 74× auf 3, 70× auf 4).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Mood 1 ("high"): Kinds in eigenen Daten {1,2,3,5,6}; Kind 1 ist in
# 2370/2370 Tracks der erste, Kind 6 in 2370/2370 der letzte Eintrag
# (Messung 2026-08-21 ueber alle 2475 EXT-Dateien).
PHRASE_LABELS_HIGH: dict[int, str] = {1: "Intro", 2: "Up", 3: "Down", 5: "Chorus", 6: "Outro"}
# Mood 2 ("mid") und 3 ("low"): 102 eigene Tracks — Kind 1 in 100/102 der
# erste, Kind 10 in 100/102 der letzte Eintrag (Intro/Outro belegt).
# Verse/Bridge/Chorus dazwischen folgen dem Beat-Link-Schema und sind aus
# eigenen Daten NICHT pruefbar.
PHRASE_LABELS_MIDLOW: dict[int, str] = {
    1: "Intro", 2: "Verse 1", 3: "Verse 2", 4: "Verse 3", 5: "Verse 4",
    6: "Verse 5", 7: "Verse 6", 8: "Bridge", 9: "Chorus", 10: "Outro",
}
MOOD_NAMES: dict[int, str] = {1: "high", 2: "mid", 3: "low"}


def phrase_label(mood: int, kind: int) -> str:
    table = PHRASE_LABELS_HIGH if mood == 1 else PHRASE_LABELS_MIDLOW
    return table.get(int(kind), f"Unbekannt({int(kind)})")


def _tag_content(anlz, key: str):
    if anlz is None:
        return None
    try:
        return anlz.get_tag(key)
    except Exception:
        return None


def _beat_time(times, beat: int) -> float | None:
    """Zeit des 1-basierten Beat-Index, an den Rand geklemmt."""
    n = len(times)
    if n == 0:
        return None
    idx = min(max(int(beat) - 1, 0), n - 1)
    return float(times[idx])


def phrases_from_anlz(ext_anlz, dat_anlz, duration: float) -> list[dict]:
    """PSSI (aus EXT) + PQTZ (aus DAT) → Phrasenliste mit Sekunden.

    Rueckgabe: [{start_s, end_s, label, mood, kind, fill}], zeitlich
    sortiert, Ende = Start der naechsten Phrase, letzte endet am
    `end_beat` (geklemmt auf `duration`). Leer, wenn ein Tag fehlt.
    """
    pssi = _tag_content(ext_anlz, "PSSI")
    pqtz = _tag_content(dat_anlz, "PQTZ")
    if pssi is None or pqtz is None:
        return []
    try:
        _, _, times = pqtz.get()
    except Exception as exc:
        logger.warning("PQTZ nicht lesbar: %s", exc)
        return []
    content = pssi.content
    mood = int(getattr(content, "mood", 0))
    entries = list(getattr(content, "entries", []) or [])
    if not entries or len(times) == 0:
        return []
    starts: list[tuple[float, int, int]] = []
    for e in entries:
        t = _beat_time(times, int(e.beat))
        if t is None:
            continue
        starts.append((t, int(e.kind), int(getattr(e, "fill", 0))))
    starts.sort(key=lambda s: s[0])
    end_time = _beat_time(times, int(getattr(content, "end_beat", 0)))
    if end_time is None or end_time <= starts[-1][0]:
        end_time = float(duration)
    end_time = min(float(end_time), float(duration)) if duration > 0 else float(end_time)
    phrases: list[dict] = []
    for i, (t, kind, fill) in enumerate(starts):
        nxt = starts[i + 1][0] if i + 1 < len(starts) else end_time
        phrases.append({
            "start_s": round(t, 3),
            "end_s": round(max(nxt, t), 3),
            "label": phrase_label(mood, kind),
            "mood": mood,
            "kind": kind,
            "fill": fill,
        })
    unknown = sorted({p["kind"] for p in phrases if p["label"].startswith("Unbekannt")})
    if unknown:
        logger.info("PSSI: unbekannte Phrasen-Kinds %s bei mood %d", unknown, mood)
    return phrases


def phrase_grid_from_phrases(phrases: list[dict]) -> list[float]:
    """Gitterpunkte: alle Phrasenstarts plus das Ende der letzten Phrase."""
    if not phrases:
        return []
    pts = [float(p["start_s"]) for p in phrases] + [float(phrases[-1]["end_s"])]
    out: list[float] = []
    for p in pts:
        if not out or p - out[-1] > 1e-6:
            out.append(round(p, 3))
    return out
```

- [ ] **Step 4: Run → PASS** `.\venv312\Scripts\python.exe -m pytest tests/test_rekordbox_phrases.py -q --no-cov`
- [ ] **Step 5: Commit** `git add hpg_core/rekordbox_phrases.py tests/test_rekordbox_phrases.py && git commit -m "feat(rekordbox): PSSI-Phrasenleser (reine Funktionen)"`

---

### Task 3: `RekordboxImporter.get_phrases` + ANLZ-Helfer

**Files:**
- Modify: `hpg_core/rekordbox_importer.py:395-463` (Helfer herausziehen), neue Methode danach
- Test: `tests/test_rekordbox_importer.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_rekordbox_importer.py — anhaengen
def test_get_phrases_liest_ext_und_dat_ueber_read_anlz_files(monkeypatch):
    from types import SimpleNamespace
    import numpy as np
    from hpg_core.rekordbox_importer import RekordboxImporter, RekordboxTrackData

    imp = RekordboxImporter.__new__(RekordboxImporter)
    imp.track_cache = {}
    imp.basename_cache = {}
    imp._ambiguous_paths = set()
    imp._downbeat_cache = {}
    imp._phrases_cache = {}
    data = RekordboxTrackData(bpm=128.0, duration=60.0, content_id="42")
    imp.get_track_data = lambda path: data
    imp.is_available = lambda: True

    class _Pq:
        def get(self):
            t = np.arange(129) * 0.46875
            return np.array([(i % 4) + 1 for i in range(129)]), np.full(129, 128.0), t

    class _File:
        def __init__(self, tags):
            self._tags = tags
        def get_tag(self, k):
            if k not in self._tags:
                raise KeyError(k)
            return self._tags[k]

    pssi = SimpleNamespace(content=SimpleNamespace(mood=1, end_beat=129, entries=[
        SimpleNamespace(index=1, beat=1, kind=1, k1=0, k2=0, k3=0, fill=0, beat_fill=0),
        SimpleNamespace(index=2, beat=65, kind=5, k1=1, k2=0, k3=0, fill=0, beat_fill=0),
    ]))
    files = {"X/ANLZ0000.DAT": _File({"PQTZ": _Pq()}), "X/ANLZ0000.EXT": _File({"PSSI": pssi})}
    imp.db = SimpleNamespace(read_anlz_files=lambda cid: files)

    phrases = imp.get_phrases("C:/irgendwo/track.mp3")
    assert [p["label"] for p in phrases] == ["Intro", "Chorus"]
    assert phrases[1]["start_s"] == pytest.approx(64 * 0.46875)
    # memoisiert
    imp.db = None
    assert imp.get_phrases("C:/irgendwo/track.mp3") == phrases
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: 'RekordboxImporter' object has no attribute 'get_phrases'`)

- [ ] **Step 3: Implementierung** — in `__init__` neben `self._downbeat_cache = {}` ergaenzen `self._phrases_cache: Dict[str, List[Dict]] = {}`. Den ANLZ-Leseblock aus `get_first_downbeat` in einen Helfer ziehen und dort aufrufen:

```python
    def _read_anlz_files(self, content_id: str) -> list:
        """Alle ANLZ-Dateien (DAT/EXT/2EX) eines Tracks, robust gegen die
        pyrekordbox-API (AUDIT-FIX RB-01 2026-07-24, hierher verschoben)."""
        anlz_files = []
        if self.db is None:
            return anlz_files
        for reader, args in (
            (getattr(self.db, "read_anlz_files", None), (content_id,)),
            (getattr(self.db, "read_anlz_file", None), (content_id, "DAT")),
        ):
            if reader is None:
                continue
            try:
                res = reader(*args)
            except Exception:
                continue
            if res is None:
                continue
            if isinstance(res, dict):
                anlz_files.extend(res.values())
            else:
                anlz_files.append(res)
            if anlz_files:
                break
        return anlz_files
```

In `get_first_downbeat` die Schleife durch `anlz_files = self._read_anlz_files(data.content_id)` ersetzen (Verhalten identisch). Neue Methode:

```python
    def get_phrases(self, file_path: str) -> List[Dict]:
        """Rekordbox-Phrasen (PSSI) eines Tracks in Sekunden, memoisiert.

        Leer, wenn kein Rekordbox-Eintrag, keine EXT-Datei oder kein PSSI-Tag.
        Zeiten stammen aus dem PQTZ-Beatgrid derselben ANLZ-Gruppe.
        """
        from .rekordbox_phrases import phrases_from_anlz

        data = self.get_track_data(file_path)
        if not data or not data.content_id or self.db is None:
            return []
        if data.content_id in self._phrases_cache:
            return self._phrases_cache[data.content_id]
        result: List[Dict] = []
        try:
            files = self._read_anlz_files(data.content_id)
            ext = next((f for f in files if _hat_tag(f, "PSSI")), None)
            dat = next((f for f in files if _hat_tag(f, "PQTZ")), None)
            result = phrases_from_anlz(ext, dat, float(data.duration or 0.0))
        except Exception as e:
            logger.warning(f"PSSI-Phrasen nicht lesbar fuer {file_path}: {e}")
        self._phrases_cache[data.content_id] = result
        return result
```

Modulfunktion (vor der Klasse):

```python
def _hat_tag(anlz_file, key: str) -> bool:
    try:
        anlz_file.get_tag(key)
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Run → PASS**; zusaetzlich `tests/test_rekordbox_importer.py` komplett gruen (Refactor von `get_first_downbeat`).
- [ ] **Step 5: Commit** `git commit -am "feat(rekordbox): get_phrases (PSSI) und gemeinsamer ANLZ-Helfer"`

---

### Task 4: Track-Felder + Cache-Version 34

**Files:**
- Modify: `hpg_core/models.py:289` (nach `lufs_sample_rate`)
- Modify: `hpg_core/caching.py:103,158`
- Tests: `tests/test_models.py`, `tests/test_caching.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_models.py — anhaengen
def test_track_hat_kandidaten_felder_mit_leeren_defaults():
    from hpg_core.models import Track
    t = Track(filePath="C:/x.mp3", fileName="x.mp3")
    assert t.phrases == [] and t.cue_points == [] and t.phrase_grid == []
    assert t.mix_in_candidates == [] and t.mix_out_candidates == []
```

```python
# tests/test_caching.py — anhaengen (2 Leerzeichen wie die Datei)
def test_cache_version_34_und_kandidatenfelder_sind_listenfelder():
  from hpg_core import caching
  assert caching.CACHE_VERSION == 34
  for name in ("phrases", "cue_points", "phrase_grid", "mix_in_candidates", "mix_out_candidates"):
    assert name in caching.TRACK_LIST_FIELDS


def test_kandidaten_ueberleben_roundtrip_und_nichtliste_wird_abgewiesen():
  from hpg_core.caching import CacheValidationError, dict_to_track, track_to_dict, validate_track_dict
  from hpg_core.models import Track
  t = Track(filePath="C:/x.mp3", fileName="x.mp3", duration=300.0)
  t.phrases = [{"start_s": 0.0, "end_s": 15.0, "label": "Intro", "mood": 1, "kind": 1, "fill": 0}]
  t.cue_points = [{"t": 30.0, "name": "", "typ": 0, "provenance": "leer"}]
  t.phrase_grid = [0.0, 15.0]
  t.mix_in_candidates = [{"t": 15.0, "schema": ["pssi_phrase"], "provenance": "rekordbox_pssi", "confidence": 1.0}]
  back = dict_to_track(track_to_dict(t))
  assert back.phrases == t.phrases and back.mix_in_candidates == t.mix_in_candidates
  assert back.phrase_grid == [0.0, 15.0]
  d = track_to_dict(t)
  d["mix_out_candidates"] = "kaputt"
  with pytest.raises(CacheValidationError):
    validate_track_dict(d)
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Felder** in `models.Track` nach `lufs_sample_rate: int = 0`:

```python
    # Mixpunkt-Kandidaten (Spec 2026-08-21 Abschnitt 1). Alles Listen von
    # Dicts/Floats, damit der Cache sie ohne Sonderfall serialisiert.
    phrases: list = field(default_factory=list)             # Rekordbox-PSSI-Phrasen
    cue_points: list = field(default_factory=list)          # Cues mit Provenienz
    phrase_grid: list = field(default_factory=list)         # Gitterpunkte (Sekunden)
    mix_in_candidates: list = field(default_factory=list)   # MixCandidate.to_dict()
    mix_out_candidates: list = field(default_factory=list)
```

`caching.py`: `CACHE_VERSION = 34` (Kommentar: "34: Kandidatenfelder, Cue-Heuristik entfernt"); `TRACK_LIST_FIELDS = {..., "phrases", "cue_points", "phrase_grid", "mix_in_candidates", "mix_out_candidates"}`.

- [ ] **Step 4: Run → PASS**; ganze `tests/test_caching.py`, `tests/test_models.py` gruen. Pruefen, dass kein Test `CACHE_VERSION == 33` hart prueft: `grep -rn "CACHE_VERSION" tests/` — Treffer anpassen.
- [ ] **Step 5: Commit** `git commit -am "feat(models,cache): Kandidatenfelder, CACHE_VERSION 34"`

---

### Task 5: `MixCandidate`, Cue-Normalisierung, Gitter-Quantisierung

**Files:**
- Create: `hpg_core/mix_candidates.py`
- Test: `tests/test_mix_candidates.py`

- [ ] **Step 1: Failing tests**

```python
"""Tests fuer Mixpunkt-Kandidaten: Datenmodell, Cues, Gitter, Gates."""
import pytest

from hpg_core.mix_candidates import (
    MixCandidate, normalize_cues, quantize_to_points, passes_track_gates,
)


def test_mixcandidate_roundtrip_dict():
    c = MixCandidate(t=30.0, schema=["benannter_cue"], provenance="rekordbox_manual", confidence=0.9)
    d = c.to_dict()
    assert d["t"] == 30.0 and d["schema"] == ["benannter_cue"]
    assert MixCandidate.from_dict(d) == c
    assert MixCandidate.from_dict({"t": 1.0}).schema == []


def test_normalize_cues_provenienz_und_dedupe():
    cues = [
        {"position": 30.0, "name": "MIX IN", "type": 0, "hot_cue_number": None, "color": None},
        {"position": 30.5, "name": None, "type": 0, "hot_cue_number": None, "color": None},
        {"position": 61.0, "name": "CUE(Auto)", "type": 0, "hot_cue_number": None, "color": None},
        {"position": 90.0, "name": "", "type": 1, "hot_cue_number": 1, "color": 3},
        {"position": None, "name": "X", "type": 0, "hot_cue_number": None, "color": None},
        {"position": -0.5, "name": "X", "type": 0, "hot_cue_number": None, "color": None},
    ]
    out = normalize_cues(cues)
    assert [c["t"] for c in out] == [30.0, 61.0, 90.0]          # 30.5 < 2 s → weg, ungueltige weg
    assert out[0]["provenance"] == "manual" and out[0]["name"] == "MIX IN"
    assert out[1]["provenance"] == "auto"
    assert out[2]["provenance"] == "leer" and out[2]["typ"] == 1
    assert normalize_cues(None) == [] and normalize_cues([]) == []


def test_quantize_to_points_ceil_floor_mit_toleranz():
    pts = [0.0, 15.0, 30.0, 45.0]
    assert quantize_to_points(15.03, pts, "ceil") == 15.0     # 30 ms drueber → bleibt (0.05 s Toleranz)
    assert quantize_to_points(15.2, pts, "ceil") == 30.0
    assert quantize_to_points(29.97, pts, "floor") == 30.0
    assert quantize_to_points(29.8, pts, "floor") == 15.0
    assert quantize_to_points(50.0, pts, "ceil") is None      # hinter dem letzten Punkt
    assert quantize_to_points(-1.0, pts, "floor") is None
    assert quantize_to_points(10.0, [], "ceil") is None


def test_track_gates_in_und_out():
    # intro_end 20, outro_start 280, duration 300, grid 15 → 2 Phrasen = 30
    assert passes_track_gates(20.0, "in", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(19.9, "in", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(275.0, "in", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)  # > dur-2grid
    assert passes_track_gates(280.0, "out", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(280.1, "out", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)
    assert not passes_track_gates(20.0, "out", intro_end=20.0, outro_start=280.0, duration=300.0, grid=15.0)   # < 2grid
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError`)

- [ ] **Step 3: Modul (erster Teil)**

```python
"""Mixpunkt-Kandidaten je Track (Spec 2026-08-21, Abschnitt 1).

Ein Kandidat ist ein Zeitpunkt auf dem Gitter plus lokale Messwerte im
Fenster +-1 Phrase. Quellen ("schema"): benannter Cue, Auto-Cue,
PSSI-Phrasengrenze, Sektionsgrenze, Energie-Neuheit, Analyzer-Mixpunkt.
Harte Gates (Intro/Outro-Guard, Coverage, Gitter, 2 Phrasen) entscheiden,
ob ein Kandidat ueberhaupt entsteht. Bewertung und Paarung: Teil 2.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field, fields

from .config import (
    CUE_DEDUPE_SEC, KANDIDATEN_MAX_JE_SEITE, KANDIDATEN_MIN_JE_SEITE,
)
from .models import QUANTIZE_TOLERANCE_SEC

logger = logging.getLogger(__name__)

# Identisch zu den bisherigen Mustern in analysis.py (Wortgrenzen; "INTRO"
# markiert den Intro-START und ist KEIN Mix-In).
CUE_IN_PATTERN = re.compile(r"\b(MIX[- ]?IN|IN|START)\b")
CUE_OUT_PATTERN = re.compile(r"\b(MIX[- ]?OUT|OUT|OUTRO|END)\b")

SCHEMA_PRIORITAET = (
    "benannter_cue", "pssi_phrase", "auto_cue", "analyzer", "sektion", "energie_neuheit",
)


@dataclass
class MixCandidate:
    """Ein Kandidat mit lokalen Messwerten. Alle Messwerte optional (None =
    nicht gemessen), damit fehlende Werte spaeter umverteilt und nie mit 0
    bestraft werden."""
    t: float
    schema: list = field(default_factory=list)
    provenance: str = ""
    confidence: float = 0.0
    # Struktur
    section_label: str = ""
    phrase_label: str = ""
    neuheit: float | None = None
    traegt_allein: bool | None = None
    # Rhythmus
    groove_pattern_lokal: list = field(default_factory=list)
    bass_pattern_lokal: list = field(default_factory=list)
    syncopation_lokal: float | None = None
    percussive_ratio_lokal: float | None = None
    # Bass
    sub_energy: float | None = None
    bass_punch: float | None = None
    bass_rms_dbfs: float | None = None
    kick_aktiv: bool | None = None
    # Harmonie
    camelot_lokal: str = ""
    key_confidence_lokal: float | None = None
    # Klangfarbe
    timbre_fingerprint_lokal: list = field(default_factory=list)
    brightness_lokal: int | None = None
    flatness_lokal: float | None = None
    avg_mids_lokal: float | None = None
    avg_highs_lokal: float | None = None
    # Energie / Lautheit
    energy_lokal: int | None = None
    energy_trend: str = ""
    lufs_lokal: float | None = None
    # Stimmung / Vocals
    mood: dict = field(default_factory=dict)
    vocal_aktiv_lokal: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MixCandidate":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def normalize_cues(cues: list | None) -> list[dict]:
    """Rekordbox-Cues → [{t, name, typ, hot_cue, provenance}], sortiert, dedupliziert
    (< CUE_DEDUPE_SEC), Provenienz: manual (benannt, nicht 'CUE(Auto)'),
    auto ('CUE(Auto)'), leer (kein Name)."""
    out: list[dict] = []
    for cue in cues or []:
        pos = cue.get("position")
        if pos is None:
            continue
        try:
            t = float(pos)
        except (TypeError, ValueError):
            continue
        if t < 0.0:
            continue
        name = (cue.get("name") or "").strip()
        if not name:
            prov = "leer"
        elif name.upper().startswith("CUE(AUTO)"):
            prov = "auto"
        else:
            prov = "manual"
        out.append({
            "t": round(t, 3), "name": name, "typ": cue.get("type"),
            "hot_cue": cue.get("hot_cue_number"), "provenance": prov,
        })
    out.sort(key=lambda c: c["t"])
    dedup: list[dict] = []
    for c in out:
        if dedup and c["t"] - dedup[-1]["t"] < CUE_DEDUPE_SEC:
            # benannter Cue gewinnt gegen unbenannten Zwilling
            if dedup[-1]["provenance"] != "manual" and c["provenance"] == "manual":
                dedup[-1] = c
            continue
        dedup.append(c)
    return dedup


def quantize_to_points(t: float, points: list[float], mode: str) -> float | None:
    """Auf eine Liste von Gitterpunkten quantisieren (PSSI-Gitter).

    ceil: kleinster Punkt >= t - Toleranz; floor: groesster Punkt <= t + Toleranz.
    None, wenn kein Punkt in der Richtung liegt."""
    if not points:
        return None
    tol = QUANTIZE_TOLERANCE_SEC
    if mode == "ceil":
        for p in points:
            if p >= t - tol:
                return float(p)
        return None
    for p in reversed(points):
        if p <= t + tol:
            return float(p)
    return None


def passes_track_gates(t: float, seite: str, *, intro_end: float, outro_start: float,
                       duration: float, grid: float) -> bool:
    """Track-seitige harte Gates (Spec Abschnitt 1): Intro/Outro-Guard und
    Platz fuer das Mindestfenster von 2 Phrasen zur jeweils anderen Seite."""
    if grid <= 0 or duration <= 0 or t < 0 or t > duration:
        return False
    eps = QUANTIZE_TOLERANCE_SEC
    if seite == "in":
        return t + eps >= intro_end and t <= duration - 2 * grid + eps
    if seite == "out":
        return t - eps <= outro_start and t >= 2 * grid - eps
    raise ValueError(f"seite muss 'in' oder 'out' sein, nicht {seite!r}")
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add hpg_core/mix_candidates.py tests/test_mix_candidates.py && git commit -m "feat(kandidaten): MixCandidate, Cue-Normalisierung, Gitter, Gates"`

---

### Task 6: Schemata erzeugen, dedupen, kappen (`collect_candidate_times`)

**Files:**
- Modify: `hpg_core/mix_candidates.py`
- Test: `tests/test_mix_candidates.py`

- [ ] **Step 1: Failing tests**

```python
from hpg_core.mix_candidates import collect_candidate_times


def _sections():
    return [
        {"label": "intro", "start_time": 0.0, "end_time": 30.0, "avg_energy": 30.0},
        {"label": "build", "start_time": 30.0, "end_time": 60.0, "avg_energy": 55.0},
        {"label": "drop", "start_time": 60.0, "end_time": 120.0, "avg_energy": 90.0},
        {"label": "breakdown", "start_time": 120.0, "end_time": 150.0, "avg_energy": 50.0},
        {"label": "drop", "start_time": 150.0, "end_time": 240.0, "avg_energy": 92.0},
        {"label": "outro", "start_time": 240.0, "end_time": 300.0, "avg_energy": 25.0},
    ]


def test_collect_candidate_times_alle_schemata_mit_pssi_gitter():
    grid = [float(x) for x in range(0, 301, 15)]          # 15 s = 8 Bars @ 128 BPM
    phrases = [{"start_s": s, "end_s": s + 15.0, "label": "Chorus" if s in (60.0, 150.0) else "Up",
                "mood": 1, "kind": 5 if s in (60.0, 150.0) else 2, "fill": 0} for s in grid[:-1]]
    cues = [{"t": 45.0, "name": "MIX IN", "typ": 0, "hot_cue": None, "provenance": "manual"},
            {"t": 25.0, "name": "START", "typ": 0, "hot_cue": None, "provenance": "manual"},   # im Intro (bis 30 s)
            {"t": 61.0, "name": "CUE(Auto)", "typ": 0, "hot_cue": None, "provenance": "auto"},
            {"t": 20.0, "name": "Drop 2", "typ": 0, "hot_cue": None, "provenance": "manual"},   # benannt, kein IN/OUT: Guard gilt
            {"t": 233.0, "name": "", "typ": 0, "hot_cue": None, "provenance": "leer"}]
    ins, outs = collect_candidate_times(
        seite_grid=grid, sections=_sections(), phrases=phrases, cues=cues,
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True,
    )
    t_in = {c.t: c for c in ins}
    assert 45.0 in t_in and "benannter_cue" in t_in[45.0].schema
    assert 75.0 in t_in and "auto_cue" in t_in[75.0].schema            # 61 ceil → 75
    assert 60.0 in t_in and {"analyzer", "pssi_phrase", "sektion", "energie_neuheit"} <= set(t_in[60.0].schema)
    assert 30.0 in t_in and "benannter_cue" in t_in[30.0].schema       # 25 s ceil → 30, schlaegt den Guard
    assert all(c.t >= 30.0 for c in ins)                                  # "Drop 2" @20 s: ceil → 30 (Guard), nicht 20
    assert "benannter_cue" in t_in[30.0].schema and t_in[30.0].provenance == "rekordbox_manual"
    t_out = {c.t: c for c in outs}
    assert 225.0 in t_out and "auto_cue" in t_out[225.0].schema          # 233 floor → 225
    assert 240.0 in t_out and "analyzer" in t_out[240.0].schema
    assert all(c.t <= 240.0 for c in outs)                                # Outro-Guard
    assert len(ins) <= 8 and len(outs) <= 8
    assert ins == sorted(ins, key=lambda c: c.t)
    assert t_in[45.0].provenance == "rekordbox_manual"
    assert t_in[60.0].phrase_label == "Chorus" and t_in[60.0].section_label == "drop"


def test_collect_candidate_times_ohne_pssi_nutzt_phrasenanker_gitter():
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=_sections(), phrases=[], cues=[],
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True, anchor=0.0,
    )
    assert any("analyzer" in c.schema for c in ins)
    assert all(abs((c.t / 15.0) - round(c.t / 15.0)) < 1e-6 for c in ins + outs)


def test_collect_candidate_times_outro_nicht_abgedeckt_keine_out_kandidaten():
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=_sections(), phrases=[], cues=[],
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=False, anchor=0.0,
    )
    assert outs == [] and ins


def test_unanalysed_sektion_liefert_keinen_kandidaten():
    secs = _sections()
    secs[3] = {"label": "unanalysed", "start_time": 120.0, "end_time": 150.0, "avg_energy": 0.0}
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=secs, phrases=[], cues=[{"t": 130.0, "name": "", "typ": 0, "hot_cue": None, "provenance": "leer"}],
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True, anchor=0.0,
    )
    assert all(not (120.0 <= c.t < 150.0) for c in ins + outs)


def test_kappung_auf_acht_mit_prioritaet():
    cues = [{"t": float(t), "name": "", "typ": 0, "hot_cue": None, "provenance": "leer"} for t in range(35, 230, 10)]
    ins, outs = collect_candidate_times(
        seite_grid=[], sections=_sections(), phrases=[], cues=cues,
        analyzer_in=60.0, analyzer_out=240.0, duration=300.0, grid_sec=15.0,
        intro_end=30.0, outro_start=240.0, outro_covered=True, anchor=0.0,
    )
    assert len(ins) == 8 and len(outs) == 8
    assert any("analyzer" in c.schema for c in ins)   # hoehere Prioritaet ueberlebt die Kappung
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementierung** (in `mix_candidates.py` ergaenzen)

```python
from .config import ENERGIE_NEUHEIT_MIN
from .models import quantize_to_grid

PROVENANCE_JE_SCHEMA = {
    "benannter_cue": "rekordbox_manual", "auto_cue": "rekordbox_auto",
    "pssi_phrase": "rekordbox_pssi", "analyzer": "hpg_analyzer",
    "sektion": "hpg_analyzer", "energie_neuheit": "hpg_analyzer",
}


def _quantize(t: float, seite: str, seite_grid: list[float], grid_sec: float, anchor: float) -> float | None:
    mode = "ceil" if seite == "in" else "floor"
    if seite_grid:
        return quantize_to_points(t, seite_grid, mode)
    return quantize_to_grid(t, grid_sec, anchor, mode)


def _section_at(sections: list[dict], t: float) -> dict | None:
    for i, s in enumerate(sections):
        start, end = s.get("start_time", 0.0), s.get("end_time", 0.0)
        last = i == len(sections) - 1
        if start <= t < end or (last and t == end):
            return s
    return None


def _phrase_at(phrases: list[dict], t: float) -> dict | None:
    for i, p in enumerate(phrases):
        last = i == len(phrases) - 1
        if p["start_s"] <= t < p["end_s"] or (last and t == p["end_s"]):
            return p
    return None


def _rohe_zeitpunkte(sections, phrases, cues, analyzer_in, analyzer_out) -> dict[str, list[tuple[float, str, bool]]]:
    """Je Seite: [(t_roh, schema, guard_frei)]. Benannte Cues mit IN/OUT-Muster
    gehen nur auf ihre Seite und sind guard_frei (Spec-Ausnahme); andere
    benannte Cues ("Drop 2") sind Schema benannter_cue auf beiden Seiten MIT
    Guard; Auto-/leere Cues Schema auto_cue. Uebrige Quellen auf beide Seiten."""
    beide: list[tuple[float, str, bool]] = []
    rohe = {"in": [], "out": []}
    for c in cues:
        name = (c.get("name") or "").upper()
        if c["provenance"] == "manual" and CUE_IN_PATTERN.search(name):
            rohe["in"].append((c["t"], "benannter_cue", True))
        elif c["provenance"] == "manual" and CUE_OUT_PATTERN.search(name):
            rohe["out"].append((c["t"], "benannter_cue", True))
        elif c["provenance"] == "manual":
            beide.append((c["t"], "benannter_cue", False))
        else:
            beide.append((c["t"], "auto_cue", False))
    for p in phrases:
        beide.append((float(p["start_s"]), "pssi_phrase", False))
    vorher = None
    for s in sections:
        if s.get("label") in ("intro", "outro", "unanalysed"):
            vorher = s
            continue
        beide.append((float(s.get("start_time", 0.0)), "sektion", False))
        if vorher is not None and abs(float(s.get("avg_energy", 0.0)) - float(vorher.get("avg_energy", 0.0))) >= ENERGIE_NEUHEIT_MIN:
            beide.append((float(s.get("start_time", 0.0)), "energie_neuheit", False))
        vorher = s
    if analyzer_in is not None and analyzer_in >= 0:
        rohe["in"].append((float(analyzer_in), "analyzer", False))
    if analyzer_out is not None and analyzer_out >= 0:
        rohe["out"].append((float(analyzer_out), "analyzer", False))
    rohe["in"].extend(beide)
    rohe["out"].extend(beide)
    return rohe


def collect_candidate_times(*, seite_grid: list[float], sections: list[dict], phrases: list[dict],
                            cues: list[dict], analyzer_in: float | None, analyzer_out: float | None,
                            duration: float, grid_sec: float, intro_end: float, outro_start: float,
                            outro_covered: bool, anchor: float = 0.0,
                            ) -> tuple[list[MixCandidate], list[MixCandidate]]:
    """Kandidaten-Zeitpunkte je Seite: quantisieren, Gates, Dedupe (gleicher
    Gitterpunkt → Schemata vereinigen), Kappung auf KANDIDATEN_MAX_JE_SEITE
    nach SCHEMA_PRIORITAET, dann zeitlich sortiert. Noch OHNE Messwerte."""
    rohe = _rohe_zeitpunkte(sections, phrases, cues, analyzer_in, analyzer_out)
    ergebnis: dict[str, list[MixCandidate]] = {}
    for seite in ("in", "out"):
        if seite == "out" and not outro_covered:
            ergebnis[seite] = []
            continue
        je_t: dict[float, MixCandidate] = {}
        for t_roh, schema, guard_frei in rohe[seite]:
            tq = _quantize(t_roh, seite, seite_grid, grid_sec, anchor)
            if tq is None:
                continue
            tq = round(float(tq), 3)
            # Spec-Ausnahme: ein benannter Cue mit MIX IN/IN/START bzw. OUT-
            # Muster ist eine bewusste Nutzerentscheidung und schlaegt den
            # Intro/Outro-Guard; nur Trackgrenzen gelten. Alle anderen: Gates.
            if guard_frei:
                gate_ok = 0.0 <= tq <= duration
            else:
                gate_ok = passes_track_gates(tq, seite, intro_end=intro_end, outro_start=outro_start,
                                             duration=duration, grid=grid_sec)
            if not gate_ok:
                continue
            sek = _section_at(sections, tq)
            if sek is not None and sek.get("label") == "unanalysed":
                continue
            if tq not in je_t:
                je_t[tq] = MixCandidate(t=tq)
            if schema not in je_t[tq].schema:
                je_t[tq].schema.append(schema)
        kandidaten = list(je_t.values())
        for k in kandidaten:
            k.schema.sort(key=SCHEMA_PRIORITAET.index)
            k.provenance = PROVENANCE_JE_SCHEMA[k.schema[0]]
            sek = _section_at(sections, k.t)
            k.section_label = sek.get("label", "") if sek else ""
            ph = _phrase_at(phrases, k.t)
            k.phrase_label = ph["label"] if ph else ""
        if len(kandidaten) > KANDIDATEN_MAX_JE_SEITE:
            kandidaten.sort(key=lambda k: (SCHEMA_PRIORITAET.index(k.schema[0]), -len(k.schema)))
            kandidaten = kandidaten[:KANDIDATEN_MAX_JE_SEITE]
        kandidaten.sort(key=lambda k: k.t)
        if 0 < len(kandidaten) < KANDIDATEN_MIN_JE_SEITE:
            logger.info("Nur %d %s-Kandidaten (Minimum %d) — Quellen reichen nicht",
                        len(kandidaten), seite, KANDIDATEN_MIN_JE_SEITE)
        ergebnis[seite] = kandidaten
    return ergebnis["in"], ergebnis["out"]
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git commit -am "feat(kandidaten): Schemata sammeln, quantisieren, dedupen, kappen"`

---

### Task 7: Lokale Messung `measure_candidate_window`

**Files:**
- Modify: `hpg_core/mix_candidates.py`
- Test: `tests/test_mix_candidates.py`

Messfenster: `[t - w, t + w]`, `w = grid_sec * KANDIDATEN_FENSTER_PHRASEN`. Audio wird **je Kandidat** per `librosa.load(file_path, sr=KANDIDATEN_AUDIO_SR, mono=True, offset, duration)` geladen (unabhaengig von Head-/Tail-Fenster der Strukturanalyse — das Tail-Audio wird dort nicht zurueckgegeben). LUFS getrennt mit `soundfile.read(file_path, start, stop)` in nativer Samplerate/Kanalzahl: **Short-Term-Lautheit** (3-s-Fenster `[t-1.5, t+1.5]`, BS.1771) via `pyloudnorm.Meter(sr, filter_class="DeMan").integrated_loudness` auf genau diesem Block — exakt die Spec ("lufs_lokal Short-Term, native Samplerate, Stereo").

- [ ] **Step 1: Failing tests (synthetisches Audio, in tmp_path als WAV)**

```python
import numpy as np
import soundfile as sf

from hpg_core.mix_candidates import measure_candidate_window


def _kick_track(tmp_path, bpm=128.0, sekunden=60.0, sr=22050, kick_ab=0.0, kick_bis=None):
    """Sinus-Kick (55 Hz, 120 ms) auf jeder Zaehlzeit + leises Rauschen; Kick nur in [kick_ab, kick_bis)."""
    n = int(sekunden * sr)
    y = 0.01 * np.random.default_rng(0).standard_normal(n)
    spb = 60.0 / bpm
    kick_bis = sekunden if kick_bis is None else kick_bis
    t_kick = np.arange(0, sekunden, spb)
    for tk in t_kick:
        if not (kick_ab <= tk < kick_bis):
            continue
        i0 = int(tk * sr); L = int(0.12 * sr)
        tt = np.arange(L) / sr
        y[i0:i0 + L] += 0.8 * np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 25)
    p = tmp_path / "kick.wav"
    sf.write(p, y.astype(np.float32), sr)
    return str(p)


def test_measure_window_liefert_alle_felder_und_kick_aktiv(tmp_path):
    path = _kick_track(tmp_path)
    c = MixCandidate(t=30.0, schema=["sektion"])
    m = measure_candidate_window(
        path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=1.0,
        grid_sec=15.0, duration=60.0, sections=[{"label": "drop", "start_time": 0.0, "end_time": 60.0, "avg_energy": 80.0}],
    )
    assert m is c
    assert len(c.bass_pattern_lokal) == 16 and len(c.groove_pattern_lokal) == 16
    assert c.kick_aktiv is True and c.bass_rms_dbfs is not None and c.bass_rms_dbfs > -35.0
    assert c.sub_energy is not None and c.bass_punch is not None
    assert c.syncopation_lokal is not None and 0.0 <= c.syncopation_lokal <= 1.0
    assert c.percussive_ratio_lokal is not None
    assert c.camelot_lokal != "" and c.key_confidence_lokal is not None
    assert len(c.timbre_fingerprint_lokal) > 0
    assert c.brightness_lokal is not None and c.flatness_lokal is not None
    assert c.avg_mids_lokal is not None and c.avg_highs_lokal is not None
    assert c.energy_lokal is not None and c.energy_trend in ("rising", "falling", "stable")
    assert c.lufs_lokal is not None and -70.0 < c.lufs_lokal < 0.0
    assert set(c.mood) == {"brightness", "flatness", "key_mode", "pssi_mood"}
    assert c.vocal_aktiv_lokal in (True, False)
    assert c.neuheit is not None and 0.0 <= c.neuheit <= 1.0
    assert c.traegt_allein is True


def test_measure_window_ohne_kick_nach_t_traegt_nicht_allein_und_neuheit_hoch(tmp_path):
    path = _kick_track(tmp_path, kick_ab=0.0, kick_bis=30.0)      # nach 30 s Stille
    c = MixCandidate(t=30.0, schema=["sektion"])
    measure_candidate_window(path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=1.0,
                             grid_sec=15.0, duration=60.0, sections=[])
    assert c.traegt_allein is False
    assert c.energy_trend == "falling"
    assert c.neuheit > 0.3


def test_measure_window_ohne_downbeat_keine_muster_aber_rest_gemessen(tmp_path):
    path = _kick_track(tmp_path)
    c = MixCandidate(t=30.0)
    measure_candidate_window(path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=0.0,
                             grid_sec=15.0, duration=60.0, sections=[])
    assert c.bass_pattern_lokal == [] and c.kick_aktiv is None
    assert c.lufs_lokal is not None and c.energy_lokal is not None


def test_measure_window_am_trackrand_klemmt_und_kurz_ist_kein_absturz(tmp_path):
    path = _kick_track(tmp_path, sekunden=20.0)
    c = MixCandidate(t=1.0)
    measure_candidate_window(path, c, bpm=128.0, first_downbeat=0.0, downbeat_confidence=1.0,
                             grid_sec=15.0, duration=20.0, sections=[])
    assert c.energy_lokal is not None
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementierung**

```python
import numpy as np

from .config import (
    ENERGIE_TREND_SCHWELLE, KANDIDATEN_AUDIO_SR, KANDIDATEN_FENSTER_PHRASEN,
    KICK_AKTIV_MIN_DBFS, KICK_AKTIV_ONBEAT_MIN,
)
from .groove import ON_BEAT_SLOTS, bass_kennwerte, extract_groove, syncopation_from_pattern
from .downbeat import DOWNBEAT_RELIABLE_MIN
from .models import CAMELOT_MAP

BASS_RMS_CUTOFF_HZ = 160.0   # wie die Downbeat-Low-Frequency-Onsets (<=160 Hz)


def _lade_fenster(file_path: str, start: float, ende: float, sr: int):
    import librosa
    y, _ = librosa.load(file_path, sr=sr, mono=True, offset=max(0.0, start),
                        duration=max(0.0, ende - max(0.0, start)))
    return y


LUFS_SHORT_TERM_SEC = 3.0   # BS.1771 Short-Term-Fenster


def _lufs_short_term(file_path: str, t: float, duration: float) -> float | None:
    """Short-Term-Lautheit (3-s-Block um t) in nativer Samplerate/Kanalzahl."""
    try:
        import soundfile as sf
        import pyloudnorm as pyln
        info = sf.info(file_path)
        halb = LUFS_SHORT_TERM_SEC / 2.0
        start = max(0.0, t - halb)
        ende = min(float(duration), t + halb) if duration > 0 else t + halb
        a = int(start * info.samplerate)
        b = int(ende * info.samplerate)
        if b - a < info.samplerate:
            return None
        data, sr = sf.read(file_path, start=a, stop=b, dtype="float64", always_2d=True)
        meter = pyln.Meter(sr, filter_class="DeMan")
        v = float(meter.integrated_loudness(data))
        if not np.isfinite(v) or v >= 0.0 or v < -70.0:
            return None
        return round(v, 2)
    except Exception as exc:
        logger.warning("LUFS short-term nicht messbar (%s @ %.1f s): %s", file_path, t, exc)
        return None


def _bass_rms_dbfs(y: np.ndarray, sr: int) -> float | None:
    from scipy.signal import butter, sosfiltfilt
    if y is None or len(y) < sr // 4:
        return None
    sos = butter(4, BASS_RMS_CUTOFF_HZ, btype="low", fs=sr, output="sos")
    low = sosfiltfilt(sos, np.asarray(y, dtype=float))
    rms = float(np.sqrt(np.mean(low ** 2)))
    if rms <= 0.0:
        return -120.0
    return round(20.0 * np.log10(rms), 2)


def _kick_aktiv(bass_pattern: list[float], bass_rms_dbfs: float | None) -> bool | None:
    if not bass_pattern or bass_rms_dbfs is None:
        return None
    onbeat = sum(bass_pattern[i] for i in ON_BEAT_SLOTS)
    return bool(bass_rms_dbfs >= KICK_AKTIV_MIN_DBFS and onbeat >= KICK_AKTIV_ONBEAT_MIN)


def _trend(e_vor: int, e_nach: int) -> str:
    d = e_nach - e_vor
    if d >= ENERGIE_TREND_SCHWELLE:
        return "rising"
    if d <= -ENERGIE_TREND_SCHWELLE:
        return "falling"
    return "stable"


def _cos_dist(a, b) -> float:
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(1.0 - float(np.dot(a, b) / (na * nb)), 0.0, 1.0))


def _neuheit(y_vor, y_nach, sr, fc_vor, fc_nach, e_vor, e_nach) -> float | None:
    """Mittel aus vier normierten Spruengen vor/nach t: Onset-Dichte,
    Lautheit (Energie 0-100 /100), Timbre (Kosinus-Distanz MFCC), Harmonie
    (Kosinus-Distanz Chroma). 0 = nichts passiert, 1 = maximaler Bruch."""
    import librosa
    from .analysis import generate_timbre_fingerprint
    if y_vor is None or y_nach is None or len(y_vor) < sr or len(y_nach) < sr:
        return None
    o_v = float(np.mean(librosa.onset.onset_strength(y=y_vor, sr=sr)))
    o_n = float(np.mean(librosa.onset.onset_strength(y=y_nach, sr=sr)))
    onset = abs(o_n - o_v) / max(o_n, o_v, 1e-9)
    laut = abs(e_nach - e_vor) / 100.0
    timbre = _cos_dist(generate_timbre_fingerprint(y_vor, sr, fc_vor), generate_timbre_fingerprint(y_nach, sr, fc_nach))
    harm = _cos_dist(np.mean(fc_vor.get_chroma(), axis=1), np.mean(fc_nach.get_chroma(), axis=1))
    return round(float(np.clip(np.mean([onset, laut, timbre, harm]), 0.0, 1.0)), 3)


def measure_candidate_window(file_path: str, cand: MixCandidate, *, bpm: float, first_downbeat: float,
                             downbeat_confidence: float, grid_sec: float, duration: float,
                             sections: list[dict], pssi_mood: int | None = None) -> MixCandidate:
    """Fuellt die lokalen Messwerte eines Kandidaten (Fenster +-1 Phrase).
    Fehler einzelner Messungen lassen das Feld auf None; die Analyse kippt nie."""
    from .analysis import (
        FeatureCache, analyze_frequency_bands, analyze_rhythm_complexity, calculate_brightness,
        calculate_energy, detect_vocal_instrumental, generate_timbre_fingerprint,
        get_key_with_confidence, key_confidence_score,
    )
    sr = KANDIDATEN_AUDIO_SR
    w = grid_sec * KANDIDATEN_FENSTER_PHRASEN
    start, ende = max(0.0, cand.t - w), min(duration, cand.t + w)
    try:
        y = _lade_fenster(file_path, start, ende, sr)
    except Exception as exc:
        logger.warning("Kandidatenfenster nicht ladbar (%s @ %.1f s): %s", file_path, cand.t, exc)
        return cand
    if y is None or len(y) < sr:
        return cand
    fc = FeatureCache(y, sr)
    split = int((cand.t - start) * sr)
    y_vor, y_nach = y[:split], y[split:]
    try:
        cand.energy_lokal = calculate_energy(y)
        e_vor = calculate_energy(y_vor) if len(y_vor) else cand.energy_lokal
        e_nach = calculate_energy(y_nach) if len(y_nach) else cand.energy_lokal
        cand.energy_trend = _trend(e_vor, e_nach)
    except Exception as exc:
        logger.warning("Energie lokal: %s", exc)
    try:
        b, m, h = analyze_frequency_bands(y, sr, fc)
        cand.avg_mids_lokal, cand.avg_highs_lokal = round(m, 3), round(h, 3)
        pr, flat = analyze_rhythm_complexity(y, sr, fc)
        cand.percussive_ratio_lokal, cand.flatness_lokal = round(pr, 4), round(flat, 4)
        cand.brightness_lokal = calculate_brightness(y, sr, fc)
        cand.timbre_fingerprint_lokal = generate_timbre_fingerprint(y, sr, fc)
        cand.vocal_aktiv_lokal = detect_vocal_instrumental(y, sr, fc) == "vocal"
    except Exception as exc:
        logger.warning("Klangfarbe lokal: %s", exc)
    cand.mood = {"pssi_mood": pssi_mood}   # bleibt auch bei Harmonie-Fehler erhalten
    try:
        chroma_vec = np.mean(fc.get_chroma(), axis=1)
        note, mode, strength, margin, n2, m2 = get_key_with_confidence(chroma_vec)
        cand.camelot_lokal = CAMELOT_MAP.get((note, mode), "")
        cand.key_confidence_lokal = round(key_confidence_score(strength, margin, note, mode, n2, m2), 3)
        cand.mood.update({"brightness": cand.brightness_lokal, "flatness": cand.flatness_lokal,
                          "key_mode": mode})
    except Exception as exc:
        logger.warning("Harmonie lokal: %s", exc)
    try:
        cand.bass_rms_dbfs = _bass_rms_dbfs(y, sr)
        sub, punch = bass_kennwerte(y, sr)
        cand.sub_energy, cand.bass_punch = round(sub, 4), round(punch, 4)
        if downbeat_confidence >= DOWNBEAT_RELIABLE_MIN and bpm > 0:
            g = extract_groove(y, sr, bpm, first_downbeat - start, feature_cache=fc)
            cand.groove_pattern_lokal = g.groove_pattern
            cand.bass_pattern_lokal = g.bass_pattern
            cand.syncopation_lokal = round(syncopation_from_pattern(g.bass_pattern or g.groove_pattern), 4)
            cand.kick_aktiv = _kick_aktiv(g.bass_pattern, cand.bass_rms_dbfs)
            # traegt_allein: Kick + Bass NACH t aktiv
            if len(y_nach) >= sr:
                g_n = extract_groove(y_nach, sr, bpm, first_downbeat - cand.t, feature_cache=None)
                cand.traegt_allein = _kick_aktiv(g_n.bass_pattern, _bass_rms_dbfs(y_nach, sr))
                if cand.traegt_allein is None:
                    cand.traegt_allein = False
    except Exception as exc:
        logger.warning("Bass/Groove lokal: %s", exc)
    try:
        fc_v = FeatureCache(y_vor, sr) if len(y_vor) >= sr else None
        fc_n = FeatureCache(y_nach, sr) if len(y_nach) >= sr else None
        if fc_v is not None and fc_n is not None:
            cand.neuheit = _neuheit(y_vor, y_nach, sr, fc_v, fc_n, e_vor, e_nach)
    except Exception as exc:
        logger.warning("Neuheit lokal: %s", exc)
    cand.lufs_lokal = _lufs_short_term(file_path, cand.t, duration)
    return cand
```

Hinweis: `extract_groove` liefert leere Muster, wenn das Konzentrations-Gate (`GROOVE_MIN_PEAK_RATIO`) nicht haelt — dann bleibt `kick_aktiv = None`; der Test mit synthetischem Kick haelt das Gate (reine On-Beat-Energie).

- [ ] **Step 4: Run → PASS** (`-p no:randomly` falls installiert; die Tests sind deterministisch durch `default_rng(0)`). Scheitert `camelot_lokal != ""` am Rauschen/Kick: das Testsignal um einen leisen A-Moll-Dreiklang (220/261.6/329.6 Hz, Amplitude 0.05) ergaenzen statt die Assertion zu lockern.
- [ ] **Step 5: Commit** `git commit -am "feat(kandidaten): lokale Messung je Kandidat (Rhythmus, Bass, Harmonie, Klangfarbe, Energie, LUFS, Neuheit)"`

---

**Abweichung bei der Umsetzung (Commit dfd7372, Entscheidung Koordinator):** Die
oben gezeigte `_neuheit`-Formel war blind fuer Lautheitsbrueche (Kick weg →
0.105). Umgesetzt wurde: `rhythmus` = |Δ Onset-Dichte/s| / max (onset_detect),
`laut` = clip(|Δ RMS dB| / NEUHEIT_LAUT_DB=20, 0, 1) (Startwert), `timbre` =
Kosinus-Distanz MFCC OHNE Koeffizient 0, `harm` = Chroma-Kosinus-Distanz;
Mittel der vier. Gemessen: Kick weg 0.597, durchgehender Kick 0.03. Tests
unveraendert. Rauschboden `rhythmus` ≈ 0.12 bei unveraendertem Signal bekannt.

### Task 8: `build_track_candidates` + Confidence

**Files:**
- Modify: `hpg_core/mix_candidates.py`
- Test: `tests/test_mix_candidates.py`

- [ ] **Step 1: Failing test**

```python
from hpg_core.mix_candidates import build_track_candidates, candidate_confidence


def test_candidate_confidence_formel():
    # Mittel aus: downbeat_confidence, Gitterqualitaet (1.0 PSSI / phrase_confidence), key_confidence_lokal, Coverage (1/0)
    assert candidate_confidence(downbeat_confidence=1.0, pssi_grid=True, phrase_confidence=0.1,
                                key_confidence_lokal=0.5, covered=True) == pytest.approx((1.0 + 1.0 + 0.5 + 1.0) / 4)
    assert candidate_confidence(downbeat_confidence=0.4, pssi_grid=False, phrase_confidence=0.2,
                                key_confidence_lokal=None, covered=False) == pytest.approx((0.4 + 0.2 + 0.0) / 3)


def test_build_track_candidates_end_to_end_synthetisch(tmp_path):
    path = _kick_track(tmp_path, sekunden=120.0)
    sections = [{"label": "intro", "start_time": 0.0, "end_time": 15.0, "avg_energy": 20.0},
                {"label": "drop", "start_time": 15.0, "end_time": 105.0, "avg_energy": 80.0},
                {"label": "outro", "start_time": 105.0, "end_time": 120.0, "avg_energy": 20.0}]
    ins, outs = build_track_candidates(
        path, bpm=128.0, duration=120.0, first_downbeat=0.0, downbeat_confidence=1.0,
        phrase_confidence=0.0, phrase_anchor=0.0, phrase_unit=8, sections=sections,
        phrases=[], cues=[], analyzer_in=30.0, analyzer_out=90.0, outro_covered=True,
    )
    assert ins and outs
    assert all(isinstance(c, dict) for c in ins + outs)           # Track-Felder sind Dicts
    assert all(c["t"] >= 15.0 for c in ins) and all(c["t"] <= 105.0 for c in outs)
    assert all(0.0 <= c["confidence"] <= 1.0 for c in ins + outs)
    assert any(c["lufs_lokal"] is not None for c in ins)
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementierung**

```python
from .config import METER
from .rekordbox_phrases import phrase_grid_from_phrases


def candidate_confidence(*, downbeat_confidence: float, pssi_grid: bool, phrase_confidence: float,
                         key_confidence_lokal: float | None, covered: bool) -> float:
    """Mittel der verfuegbaren Teilkonfidenzen (Spec: downbeat, phrase, key,
    Coverage). Das gleichgewichtete Mittel ist ein STARTWERT, nicht gemessen."""
    teile = [float(downbeat_confidence), 1.0 if pssi_grid else float(phrase_confidence),
             1.0 if covered else 0.0]
    if key_confidence_lokal is not None:
        teile.append(float(key_confidence_lokal))
    return round(float(np.clip(np.mean(teile), 0.0, 1.0)), 3)


def build_track_candidates(file_path: str, *, bpm: float, duration: float, first_downbeat: float,
                           downbeat_confidence: float, phrase_confidence: float, phrase_anchor: float,
                           phrase_unit: int, sections: list[dict], phrases: list[dict], cues: list[dict],
                           analyzer_in: float | None, analyzer_out: float | None, outro_covered: bool,
                           ) -> tuple[list[dict], list[dict]]:
    """Vollstaendige Kandidaten beider Seiten als Dict-Listen (fuer Track/Cache)."""
    from .dj_brain import _get_intro_end_from_sections, _get_outro_start_from_sections
    if bpm <= 0 or duration <= 0:
        return [], []
    grid_sec = (60.0 / bpm) * METER * (phrase_unit if phrase_unit > 0 else 8)
    seite_grid = phrase_grid_from_phrases(phrases)
    intro_end = _get_intro_end_from_sections(sections)
    outro_start = _get_outro_start_from_sections(sections, duration)
    ins, outs = collect_candidate_times(
        seite_grid=seite_grid, sections=sections, phrases=phrases, cues=cues,
        analyzer_in=analyzer_in, analyzer_out=analyzer_out, duration=duration, grid_sec=grid_sec,
        intro_end=intro_end, outro_start=outro_start, outro_covered=outro_covered, anchor=phrase_anchor,
    )
    covered_bis = duration if outro_covered else None
    for cand in ins + outs:
        measure_candidate_window(file_path, cand, bpm=bpm, first_downbeat=first_downbeat,
                                 downbeat_confidence=downbeat_confidence, grid_sec=grid_sec,
                                 duration=duration, sections=sections,
                                 pssi_mood=int(phrases[0]["mood"]) if phrases else None)
        sek = _section_at(sections, cand.t)
        covered = sek is not None and sek.get("label") != "unanalysed" and (covered_bis is None or cand.t <= covered_bis)
        cand.confidence = candidate_confidence(
            downbeat_confidence=downbeat_confidence, pssi_grid=bool(seite_grid),
            phrase_confidence=phrase_confidence, key_confidence_lokal=cand.key_confidence_lokal, covered=covered)
    return [c.to_dict() for c in ins], [c.to_dict() for c in outs]
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git commit -am "feat(kandidaten): build_track_candidates mit Confidence"`

---

### Task 9: Einbau in `analyze_track` — Rekordbox-Fast-Path

**Files:**
- Modify: `hpg_core/analysis.py` (Import-Block; Fast-Path Zeilen ~1655–1780 Cue-Block; Track-Konstruktor ~1924)
- Test: `tests/test_cue_intro_guard.py`, `tests/test_analyze_track.py`

- [ ] **Step 1: Failing test** (Integration mit gemocktem Importer; Muster wie bestehende Tests in `tests/test_analyze_track.py` — Fixture/Monkeypatch dort nachlesen und uebernehmen)

```python
def test_fast_path_fuellt_phrasen_cues_gitter_und_kandidaten(monkeypatch, tmp_path):
    """Rekordbox-Pfad: Track traegt phrases/cue_points/phrase_grid/mix_*_candidates,
    die Cue-Heuristik (2./letzter Cue) wird NICHT mehr angewendet."""
    # Aufbau wie die bestehenden Fast-Path-Tests dieser Datei (synthetische WAV
    # 120 s @ 128 BPM, gemockter RekordboxImporter mit bpm/duration/content_id,
    # get_first_downbeat -> 0.0, get_phrases -> zwei Phrasen, cue_points drei
    # unbenannte Cues bei 20/61/100 s). Dann:
    from hpg_core import analysis
    track = analysis.analyze_track(str(wav))
    assert track.phrases and track.phrase_grid
    assert [c["provenance"] for c in track.cue_points] == ["leer", "leer", "leer"]
    assert track.mix_in_candidates and track.mix_out_candidates
    assert all("t" in c and "schema" in c for c in track.mix_in_candidates)
    # Heuristik weg: Mix-In ist NICHT der 2. Cue (61 s), sondern der Analyzer-Wert
    assert abs(track.mix_in_point - 61.0) > 1.0 or "analyzer" in track.mix_in_candidates[0]["schema"]
```

(Die Hilfsfixtures der Datei verwenden; falls keine passt, eine Fixture `fast_path_env` dort anlegen, die `analysis.get_rekordbox_importer` per `monkeypatch.setattr` auf ein `SimpleNamespace` mit `get_track_data`, `get_track_signature`, `get_first_downbeat`, `get_phrases` setzt und den Cache auf `tmp_path` umbiegt wie `tests/test_caching.py::_cache_process_job`.)

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementierung**

Imports (oben bei den `.`-Imports):

```python
from .mix_candidates import build_track_candidates, normalize_cues, CUE_IN_PATTERN, CUE_OUT_PATTERN
```

Nach `anlz_downbeat = rekordbox_importer.get_first_downbeat(file_path)`:

```python
            phrases = rekordbox_importer.get_phrases(file_path) if hasattr(rekordbox_importer, "get_phrases") else []
            cue_points = normalize_cues(rekordbox_data.cue_points)
```

Cue-Block ersetzen (von `if rekordbox_data.cue_points:` bis vor `# Audio Feature Extensions`): nur noch **benannte** Cues als Override, `in_pattern`/`out_pattern` durch `CUE_IN_PATTERN`/`CUE_OUT_PATTERN`, Schleife ueber `cue_points` (`c["provenance"] == "manual"`, `c["name"].upper()`), **kein** Heuristik-Zweig, kein `cue_in_verwerfen`-Aufruf mehr (Guard greift nur fuer Heuristik; die Funktion bleibt fuer Tests bestehen, wird aber nicht mehr gerufen — im Kommentar festhalten), `min_fenster = 0.0`, Rest (`align_ai_mix_points`, Bars) unveraendert.

Nach dem Advanced-Analysis-Block (vor `track = Track(`, also NACH dem `except`-Zweig — deshalb der Guard `if not analysis_degraded`, sonst wuerden die im except gesetzten leeren Listen ueberschrieben):

```python
        if not analysis_degraded:
          try:
            mix_in_candidates, mix_out_candidates = build_track_candidates(
                file_path, bpm=rekordbox_data.bpm, duration=duration,
                first_downbeat=first_downbeat, downbeat_confidence=downbeat_confidence,
                phrase_confidence=phrase_confidence, phrase_anchor=phrase_anchor,
                phrase_unit=structure.phrase_unit, sections=section_dicts, phrases=phrases,
                cues=cue_points, analyzer_in=mix_in_point, analyzer_out=mix_out_point,
                outro_covered=outro_covered,
            )
          except Exception as e:
            logger.warning(f"Kandidaten fehlgeschlagen: {e}")
            mix_in_candidates, mix_out_candidates = [], []
          phrase_grid = phrase_grid_from_phrases(phrases)
```

(Einrueckung im echten Code mit 4 Leerzeichen je Ebene; `phrase_grid_from_phrases` oben bei den Imports: `from .rekordbox_phrases import phrase_grid_from_phrases`.)

Im degradierten Zweig (`except (sf.LibsndfileError, ...)`) setzen: `phrases = []`, `cue_points = []`, `phrase_grid = []`, `mix_in_candidates = mix_out_candidates = []`. Im `Track(...)`-Konstruktor ergaenzen: `phrases=phrases, cue_points=cue_points, phrase_grid=phrase_grid, mix_in_candidates=mix_in_candidates, mix_out_candidates=mix_out_candidates`.

`tests/test_cue_intro_guard.py` bleibt unveraendert: die Datei testet ausschliesslich `cue_in_verwerfen` direkt (Zeilen 20-113), kein Test dort laeuft ueber `analyze_track` (Waechter Tor 1 geprueft). `cue_in_verwerfen` bleibt im Code (ungenutzt im Produktivpfad; Kommentar im Cue-Block: "Heuristik entfernt 2026-08-21, Spec Abschnitt 1").

- [ ] **Step 4: Run** `tests/test_analyze_track.py tests/test_cue_intro_guard.py tests/test_analysis.py -q --no-cov` → PASS
- [ ] **Step 5: Commit** `git commit -am "feat(analysis): Kandidaten im Rekordbox-Pfad, Cue-Heuristik entfernt (Spec 2026-08-21)"`

---

### Task 10: Einbau in `analyze_track` — Voll-Pfad

**Files:**
- Modify: `hpg_core/analysis.py` (Voll-Pfad ab ~1996; Track-Konstruktor ~2308)
- Test: `tests/test_analyze_track.py`

- [ ] **Step 1: Failing test**

```python
def test_voll_pfad_ohne_rekordbox_hat_analyzer_kandidaten_ohne_phrasen(monkeypatch, tmp_path):
    # Importer liefert None (kein Rekordbox) — Aufbau wie bestehende Voll-Pfad-Tests.
    track = analysis.analyze_track(str(wav))
    assert track.phrases == [] and track.cue_points == [] and track.phrase_grid == []
    assert track.mix_in_candidates and all("analyzer" in c["schema"] or "sektion" in c["schema"]
                                           or "energie_neuheit" in c["schema"] for c in track.mix_in_candidates)
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementierung** — im Voll-Pfad nach der Mixpunkt-Berechnung und dem Advanced-Block denselben `build_track_candidates`-Aufruf wie Task 9 mit `phrases=[]`, `cues=[]`, `bpm=bpm` (Voll-Pfad-Variable), `phrase_unit=structure.phrase_unit`, Konstruktor um die fuenf Felder ergaenzen (`phrases=[]`, `cue_points=[]`, `phrase_grid=[]`).
- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git commit -am "feat(analysis): Kandidaten im Voll-Pfad"`

---

### Task 11: Messwerkzeug `tools/kandidaten_messen.py`

**Files:**
- Create: `tools/kandidaten_messen.py`
- Test: `tests/test_tools_kandidaten_messen.py` (nur Parser/Formatierung, kein Audio)

- [ ] **Step 1: Failing test**

```python
def test_zusammenfassung_zaehlt_schemata_und_leere_seiten():
    from tools.kandidaten_messen import zusammenfassung
    tracks = [
        {"fileName": "a", "duration": 300.0, "mix_in_candidates": [{"t": 30.0, "schema": ["analyzer", "sektion"]}],
         "mix_out_candidates": [], "phrases": [], "analyse_sekunden": 12.5},
        {"fileName": "b", "duration": 300.0, "mix_in_candidates": [{"t": 30.0, "schema": ["pssi_phrase"]}],
         "mix_out_candidates": [{"t": 250.0, "schema": ["auto_cue"]}], "phrases": [{"label": "Intro"}], "analyse_sekunden": 20.0},
    ]
    z = zusammenfassung(tracks)
    assert z["tracks"] == 2 and z["ohne_out"] == 1 and z["mit_pssi"] == 1
    assert z["schemata_in"]["analyzer"] == 1 and z["schemata_out"]["auto_cue"] == 1
    assert z["kandidaten_in_median"] == 1 and z["analyse_sekunden_median"] == pytest.approx(16.25)
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Werkzeug** (Parent-Pfad in `sys.path`, wie alle `tools/`):

```python
"""Kandidaten-Regressionsmessung: analysiert eine Trackliste (oder liest den
Cache) und berichtet Kandidatenzahl je Seite, Schemaverteilung, PSSI-Anteil,
Intro/Outro-Verletzungen und Analysezeit je Track. Aufruf:
  python tools/kandidaten_messen.py --liste tracks.txt [--json out.json]
  python tools/kandidaten_messen.py --cache
"""
import argparse, json, os, statistics, sys, time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def zusammenfassung(tracks: list[dict]) -> dict:
    n = len(tracks)
    sch_in, sch_out = Counter(), Counter()
    for t in tracks:
        for c in t.get("mix_in_candidates", []):
            sch_in.update(c.get("schema", []))
        for c in t.get("mix_out_candidates", []):
            sch_out.update(c.get("schema", []))
    med = lambda xs: statistics.median(xs) if xs else 0
    return {
        "tracks": n,
        "ohne_in": sum(1 for t in tracks if not t.get("mix_in_candidates")),
        "ohne_out": sum(1 for t in tracks if not t.get("mix_out_candidates")),
        "mit_pssi": sum(1 for t in tracks if t.get("phrases")),
        "kandidaten_in_median": med([len(t.get("mix_in_candidates", [])) for t in tracks]),
        "kandidaten_out_median": med([len(t.get("mix_out_candidates", [])) for t in tracks]),
        "schemata_in": dict(sch_in), "schemata_out": dict(sch_out),
        "analyse_sekunden_median": med([t["analyse_sekunden"] for t in tracks if "analyse_sekunden" in t]),
    }


def _verletzungen(track: dict) -> int:
    from hpg_core.dj_brain import _get_intro_end_from_sections, _get_outro_start_from_sections
    secs = track.get("sections", [])
    ie = _get_intro_end_from_sections(secs)
    os_ = _get_outro_start_from_sections(secs, float(track.get("duration", 0.0)))
    v = sum(1 for c in track.get("mix_in_candidates", []) if c["t"] < ie - 0.05)
    v += sum(1 for c in track.get("mix_out_candidates", []) if c["t"] > os_ + 0.05)
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--liste", help="Textdatei, ein Audiopfad je Zeile")
    ap.add_argument("--cache", action="store_true", help="alle Tracks aus dem Cache lesen")
    ap.add_argument("--json", help="Ergebnis als JSON schreiben")
    a = ap.parse_args()
    from hpg_core.caching import track_to_dict
    tracks: list[dict] = []
    if a.liste:
        from hpg_core.analysis import analyze_track
        for line in open(a.liste, encoding="utf-8"):
            p = line.strip()
            if not p:
                continue
            t0 = time.perf_counter()
            tr = analyze_track(p)
            dt = time.perf_counter() - t0
            if tr is None:
                continue
            d = track_to_dict(tr); d["analyse_sekunden"] = round(dt, 2); tracks.append(d)
    elif a.cache:
        from hpg_core import caching
        import sqlite3
        conn = sqlite3.connect(caching.CACHE_FILE)
        for (row,) in conn.execute("SELECT data FROM cache WHERE key <> 'version'"):
            tracks.append(json.loads(row))
    z = zusammenfassung(tracks)
    z["intro_outro_verletzungen"] = sum(_verletzungen(t) for t in tracks)
    print(json.dumps(z, indent=2, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"zusammenfassung": z, "tracks": tracks}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add tools/kandidaten_messen.py tests/test_tools_kandidaten_messen.py && git commit -m "tools: kandidaten_messen (Regression/Analysezeit)"`

---

### Task 12: Messung an echten Tracks, Doku, Waechter Tor 2, Commit

- [ ] **Step 1: Cache leeren ist NICHT noetig** — Version 34 legt eine neue DB `hpg_cache_v34.db` an. Liste der 231 analysierten Tracks aus der alten DB ziehen (Spalte heisst `filepath`, Metadaten-Zeile `key='version'` ausschliessen): `.\venv312\Scripts\python.exe -c "import os,sqlite3;c=sqlite3.connect(os.path.expandvars(r'%LOCALAPPDATA%\HPG\hpg_cache_v33.db'));print('\n'.join(r[0] for r in c.execute(\"SELECT filepath FROM cache WHERE key <> 'version'\")))"` (sqlite3-CLI ist nicht im PATH) → in den Scratchpad-Ordner der Session (`%TEMP%\claude\...\scratchpad\tracks231.txt`), NICHT ins Repo.
- [ ] **Step 2: Messen** `.\venv312\Scripts\python.exe tools/kandidaten_messen.py --liste <scratchpad>\tracks231.txt --json <scratchpad>\kandidaten_v34.json` (dauert: 231 Tracks × Analysezeit; laufen lassen, Zeit notieren). Pflicht-Ergebnisse ins Handoff: `intro_outro_verletzungen` (muss 0 sein), `ohne_in`/`ohne_out`, Median Kandidaten je Seite, Schemaverteilung, `mit_pssi` (erwartet nahe 231, da 2475 EXT-Dateien vorliegen), Analysezeit-Median (Vergleich: vorher ohne Kandidaten — einmal mit `HPG_CACHE_DIR` auf leeres Verzeichnis und auskommentiertem Kandidatenaufruf NICHT machen; stattdessen die Zeit je `build_track_candidates` in `analysis.py` per `logger.info` mitloggen und aus dem Log den Median ziehen).
- [ ] **Step 3: Volle Suite** `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q` — gruen inkl. Coverage-Gate 70.
- [ ] **Step 4: Doku**: `CLAUDE.md` (CACHE_VERSION 34, neue Module in der Baumliste), `.agents/skills/hpg-mixpoint-engineering/SKILL.md` + `.claude/...` (Abschnitt "Kandidaten-Design" → "Teil 1 gebaut: Felder, Module, Heuristik entfernt"; Regel "quantize_to_grid ist die einzige erlaubte Quantisierung" ergaenzen um `quantize_to_points` fuer das unregelmaessige PSSI-Gitter, gleiche ceil/floor-Toleranz), `.agents/skills/hpg-cache-persistence/SKILL.md` (Version 34), `.agents/skills/hpg-rekordbox/SKILL.md` (`get_phrases`, PSSI), Handoff `docs/HANDOFF-<Datum>-kandidaten-teil1.md` mit den Messzahlen aus Step 2.
- [ ] **Step 5: Waechter Tor 2** mit dem Gesamt-Diff gegen dieses Plan-Dokument; Auflagen einarbeiten.
- [ ] **Step 6: Commit + Push** `git add -A docs CLAUDE.md .agents && git commit -m "docs: Kandidaten Teil 1 gebaut — Messung, Skills, Handoff" && git push -u origin kandidaten-teil1` (`.claude/skills/` ist per .gitignore unversioniert — dort nur editieren, nicht stagen). Merge auf main danach ueber superpowers:finishing-a-development-branch (Nutzer: "am Ende alles auf main mergen").

---

## Self-Review (Spec Abschnitt 1 gegen Tasks)

| Spec-Punkt | Task |
|---|---|
| `phrases` aus PSSI | 2, 3, 9 |
| `phrase_grid` PSSI vor Analyzer | 2 (`phrase_grid_from_phrases`), 6 (`_quantize`), 8 |
| `cue_points` mit Provenienz, Heuristik entfaellt | 5 (`normalize_cues`), 9 |
| `mix_in/out_candidates` 3–8 | 6 (Kappung/Minimum-Log), 8 |
| Position: t, schema (6 Schemata inkl. `analyzer`, Nutzer-Entscheidung B), provenance, confidence | 6, 8 |
| Struktur: section_label, phrase_label, neuheit, traegt_allein | 6, 7 |
| Rhythmus: groove/bass_pattern_lokal, syncopation, percussive_ratio | 7 |
| Bass: sub_energy, bass_punch, bass_rms_dbfs, kick_aktiv | 7 |
| Harmonie: camelot_lokal, key_confidence_lokal | 7 |
| Klangfarbe: timbre, brightness, flatness, avg_mids/highs | 7 |
| Energie/Lautheit: energy_lokal, energy_trend, lufs_lokal (nativ, Stereo) | 7 |
| Stimmung (brightness/flatness/Dur-Moll), Vocals | 7 |
| Gates: Guard Punkt, unanalysed/Coverage, Gitter 0.05 s, 2 Phrasen | 5, 6 |
| Guard fuer die Blende, BPM ≤ 2, Pitch ≤ 4 % | **Paar-Ebene → Teil 2** (Spec Abschnitt 2 Schritt 1) |
| benannter Cue schlaegt Guard | 6 (`gate_ok` fuer `benannter_cue` nur Trackgrenzen) und 9 (Track-Override) |
| Beide Analysepfade, CACHE_VERSION 34 | 4, 9, 10 |
| Track.mix_*_point = Rang 1 | Teil 2/4 (in Teil 1 unveraendert: Analyzer + benannter Cue) |

Placeholder-Scan: keine TBD/TODO. Typen: `MixCandidate.schema: list[str]`, `cue_points`-Dicts mit Schluesseln `t, name, typ, hot_cue, provenance` durchgaengig (Tasks 5, 6, 9); `phrases`-Dicts `start_s, end_s, label, mood, kind, fill` (Tasks 2, 6, 8).

**Entscheidung Nutzer 2026-08-21: Option B** — `analyzer` ist das sechste Schema (Spec Abschnitt 1 entsprechend ergaenzt).

**Weitere Abweichungen von der Spec, benannt (Waechter Tor 1):** Cue-Dicts tragen zusaetzlich `hot_cue`, Phrasen-Dicts `kind`/`fill` (Rohdaten, keine Wirkung); `candidate_confidence` ist gleichgewichtetes Mittel = Startwert.
