# Mixpunkt-Kandidaten Teil 2 (Paarung und Bewertung) — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aus den Track-Kandidaten (`mix_out_candidates` von A, `mix_in_candidates` von B) entstehen je Paar bewertete, sortierte `PairCandidate`s (Zeitpunkt-Kombination × Blendenlaenge) mit harten Gates, lokalem Score aus allen Faktoren, Teilwerten und Begruendung. Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`, Abschnitt 2 (Z. 89–142).

**Architecture:** Neues Modul `hpg_core/pair_candidates.py` (reine Funktionen ueber `Track` + `MixCandidate`, kein Audio). Camelot-Tabelle wird als reine Funktion `camelot_relation_score` nach `models.py` herausgeloest (playlist ruft sie auf — Verhalten unveraendert, bestehende Tests schuetzen). Zehn neue Gewichte `kandidaten_*_weight` in `GENRE_TRANSITION_TOLERANCES` (Summe 1.0, per JSON ueberschreibbar). Teil 2 aendert **nicht** `Track.mix_in_point/mix_out_point`, `calculate_enhanced_compatibility`, GUI oder Export (das ist Teil 4, Spec Abschnitt 4).

**Tech Stack:** Python 3.12 (`.\venv312\Scripts\python.exe`), numpy nur indirekt, pytest (`--no-cov` fuer schnelle Laeufe). Kein neuer Dependency.

**Auflagen des Nutzers:** genau so wie in der Spec, vollstaendig, keine Annahmen; jede Zahl gemessen oder als **Startwert** markiert (Hoertest Teil 3 ersetzt sie). Waechter `hpg-waechter` an Tor 1 (dieses Vorhaben) und Tor 2 (Diff) vor dem Merge. Keine Rueckfragen an den Nutzer (Anweisung 2026-08-22: 100 % autonom) — Entscheidungen hier festgehalten und im Handoff benannt.

**Grundlagen (vorab verifiziert, `docs/superpowers/plans/2026-08-22-faktenblatt-kandidaten-teil2.md`, HEAD `f18815b`):**
- `MixCandidate` (`mix_candidates.py:46-93`) traegt alle `*_lokal`-Felder; `Track.mix_in_candidates/mix_out_candidates` sind Listen von `to_dict()`-Dicts (`models.py:295-296`).
- `effective_bpm_diff(bpm1, bpm2) -> (diff, rel)` (`models.py:123-152`), `seconds_per_bar(bpm)` (:75-82), `quantize_to_grid` (:45-72), `QUANTIZE_TOLERANCE_SEC = 0.05` (:42); `quantize_to_points` (`mix_candidates.py:134-153`); `Track.phrase_anchor` (Property :176-199), `Track.phrase_unit` (:259, Default 8, aus `GENRE_PHRASE_UNITS` gesetzt), `Track.phrase_grid` (:294).
- `_get_intro_end_from_sections(sections)` (`dj_brain.py:613-631`), `_get_outro_start_from_sections(sections, duration)` (:634-659), `get_genre_compatibility(a, b)` (:48-86, Unknown ×0.5), `get_mix_profile(genre).transition_bars` Tuple (:89-101; `genres.py:294`).
- `transition_features.py`: `cosine_similarity` (:44-53), `_spreize` (:56-68), `_normiert` (:71-75), `BASS_PATTERN_SHARE = 0.6` (:17), `DEFAULT_SUB_DELTA_MAX/PUNCH/GROOVE_SIM_FLOOR/BRIGHTNESS/FLATNESS` (:32-38), `MODE_SWITCH_PENALTY = 0.15` (:41). Importiert `dj_brain`, `models`, `tolerances` — **nicht** `playlist`.
- `playlist.py`: `combine_weighted(components, weights)` (:278-295, None → Umverteilung), `VOCAL_CLASH_PENALTY = 0.06` (:53), `_resolve_track_genre(track)` (:298-309), Energie-Formeln (:362-371), `_calculate_compatibility_inner` (:508-603). `playlist` importiert `transition_features` und `tolerances`; Teil 4 wird `playlist → pair_candidates` importieren, deshalb importiert `pair_candidates` aus `playlist` **nur lazy** in Funktionen.
- `genres._TOLERANCE_DEFAULTS` (:500-521), `_validate_genre_tables` prueft Summe der acht `*_weight` (:585-594). `tolerances.write_override` (:92-113) skaliert nur `alt_keys` (vier klassische Gewichte); neue Schluessel, die nicht in `gewichte` stehen, bleiben beim Laden aus den Defaults (`_merge` :32-41 aktualisiert nur gelieferte Schluessel).
- `analyze_frequency_bands` (`analysis.py:183-207`) liefert Band-Anteile in **Prozent (0–100, 1 Dezimale)** → `avg_mids_lokal`/`avg_highs_lokal` sind Prozentpunkte. `calculate_brightness` 0–100, `calculate_energy` 0–100.
- Einrueckung: `pair_candidates.py`, `models.py`, `playlist.py`, `config.py`, `tolerances.py`, Tests: 4 Leerzeichen; `genres.py` Tabellen 2 / Funktionen 4; `dj_brain.py` 2.

**Entscheidungen an Stellen, die die Spec offen laesst (Waechter Tor 1 vorlegen):**
1. Benannter IN/OUT-Cue schlaegt auch den **Blenden**-Guard auf Paar-Ebene — Spec Abschnitt 1 (Z. 70, 77): "Guard fuer Punkt **und** Blende … Ausnahme: benannter Cue (MIX IN / IN / START) schlaegt den Guard". **Nur** Cues mit `CUE_IN_PATTERN`/`CUE_OUT_PATTERN` und `provenance == "manual"` (wie Teil 1, `mix_candidates._rohe_zeitpunkte`); ein "Drop 2"-Cue hat Schema `benannter_cue`, aber **mit** Guard. `MixCandidate` traegt das Muster nicht, deshalb prueft `_guard_frei(track, cand, seite)` ueber `track.cue_points`: ein manueller Cue mit passendem Muster, dessen Quantisierung (`mix_candidates._quantize`, dieselbe wie in Teil 1) auf `cand.t` faellt. Dann gilt nur noch `out_a.t + overlap <= duration_a` bzw. `0 <= in_b.t <= duration_b` (Waechter Tor 1, Auflage 3).
2. Pitch-Bedarf = `diff / bpm_a` (im Tempo-Raum von A, wie `effective_bpm_diff`).
3. Eigene Gewichtsschluessel `kandidaten_*_weight` (zehn, Summe 1.0), damit die acht bestehenden Track-Gewichte von `calculate_enhanced_compatibility` unveraendert bleiben. Startwerte = Spec-Werte proportional um 2×0.06 gestaucht (Tabelle Task 2).
4. Harmonie-Gewicht × `min(key_confidence_lokal_a, key_confidence_lokal_b)` (Spec: "Gewicht × key_confidence_lokal"); fehlt einer, keine Skalierung; fehlt `camelot_lokal` einer Seite → Teilwert None (Umverteilung).
5. Halbe/doppelte Zeit: Penalty 0.85 **einmal** auf den Gesamtscore (nicht zusaetzlich in der Camelot-Tabelle), Blende `<= 16` Takte.
6. "Bass-Swap-Punkt Pflicht, sonst Abzug": im Paar-Score immer `KICK_KONFLIKT_ABZUG` auf den Bass-Teilwert **und** Flag `bass_swap_pflicht` (Teil 4 waehlt daraus den Uebergangstyp; dort entfaellt der Abzug bei Bass-Swap/EQ-Swap — nicht Teil 2).
7. `percussive_ratio_lokal` beide `< 0.3` → Flag `lange_blende_erlaubt` ohne Score-Effekt (Spec nennt keinen Abzug/Bonus).
8. Blendenlaenge nach Outro-Deckel mindestens `MIN_TRANSITION_BARS` (= 8, `config.py:14`; dieselbe Untergrenze wie `playlist._outro_overlap_limit` und `dj_brain._dynamic_transition_bars`) — darunter faellt die Kombination am Blenden-Gate (Waechter Tor 1, Auflage 4). Ergibt der Deckel fuer beide Genre-Laengen denselben Wert → ein `PairCandidate`.
9. Dedupe: gleiche Kombination = `|Δt_out| < grid_sec_a - QUANTIZE_TOLERANCE_SEC` **und** `|Δt_in| < grid_sec_b - QUANTIZE_TOLERANCE_SEC` **und** gleiches Hauptschema (`schema[0]`) auf beiden Seiten **und gleiche `blend_bars`** (Teil 1 rundet `t` auf 3 Dezimalen; ohne Toleranz wuerden genau eine Phrase entfernte Gitterpunkte verschmelzen; ohne `blend_bars` fiele die zweite Blendenlaenge weg — Waechter Tor 1, Auflagen 1+2).
10. Rang-Tiebreak bei gleichem Score: Schema-Prioritaet out, dann in, dann kuerzere Blende.
11. Neue Konstanten sind Startwerte; Einheiten aus dem Code (Prozentpunkte, dB, LUFS) — Tabelle Task 1.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| Create `hpg_core/pair_candidates.py` | `PairCandidate`, `pair_gate_reasons`, `blend_bars_options`, `score_pair` (Teilwerte + Flags + Score), `dedupe_and_cap`, `begruendung_aus_teilwerten`, `build_pair_candidates` |
| Modify `hpg_core/models.py` | `camelot_relation_score(code_a, code_b, *, harmonic_strictness=7, allow_experimental=True, penalty=1.0) -> int` (aus `playlist._calculate_compatibility_inner` herausgeloest) |
| Modify `hpg_core/playlist.py` | `_calculate_compatibility_inner` delegiert nach dem BPM-Gate an `camelot_relation_score` |
| Modify `hpg_core/genres.py` | zehn `kandidaten_*_weight` in `_TOLERANCE_DEFAULTS`, zweite Summenpruefung in `_validate_genre_tables` |
| Modify `hpg_core/config.py` | Paar-Konstanten (Gates, Startwerte) |
| Create `tools/paar_kandidaten_messen.py` | Regressionsmessung ueber gecachte Tracks: Paare im BPM-Gate, Gate-Ausfaelle, Kandidaten je Paar, Rang-1-Schemata |
| Tests | Create `tests/test_pair_candidates.py`, `tests/test_tools_paar_kandidaten_messen.py`; Ergaenzungen in `tests/test_config.py`, `tests/test_models.py`, `tests/test_genres.py` (falls vorhanden, sonst in `tests/test_pair_candidates.py`) |

---

### Task 0: Waechter Tor 1

- [ ] **Step 1: Vorhaben pruefen lassen**

Subagent `hpg-waechter` mit: Dateitabelle oben, die 11 Entscheidungen, Anlass Spec Abschnitt 2. Ausdruecklich nennen: (a) Refactor `camelot_relation_score` nach `models.py` — Verhalten identisch, `tests/test_compatibility.py` und `tests/test_scoring_contract.py` bleiben unveraendert; (b) neue Gewichtsschluessel statt Aenderung der bestehenden; (c) `tools/paar_kandidaten_messen.py` ist Werkzeug, kein Produktcode; (d) lazy Import von `playlist` in `pair_candidates`. Erwartung: DURCHGEWUNKEN oder MIT AUFLAGEN; Auflagen vor Task 1 einarbeiten und in diesem Dokument nachtragen.

---

### Task 1: Konstanten in `config.py`

**Files:**
- Modify: `hpg_core/config.py` (direkt nach `ENERGIE_NEUHEIT_MIN`, Z. ~86)
- Test: `tests/test_config.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_config.py — anhaengen
def test_paar_konstanten_vorhanden_und_plausibel():
    from hpg_core import config
    assert config.PAAR_BPM_MAX == 2.0
    assert config.PAAR_PITCH_MAX == 0.04
    assert config.PAAR_HALF_DOUBLE_MAX_BARS == 16
    assert config.PAAR_BPM_SKALA == 1.0
    assert config.PAAR_MAX_KOMBINATIONEN == 6
    assert config.LUFS_DELTA_MAX_DB == 3.0
    assert config.BASS_RMS_DELTA_MAX_DB == 7.0
    assert config.SYNCOPATION_DELTA_MAX == 0.3
    assert config.PERCUSSIVE_HOCH == 0.7
    assert config.PERCUSSIVE_NIEDRIG == 0.3
    assert config.PERCUSSIVE_ABZUG == 0.10
    assert config.KICK_KONFLIKT_ABZUG == 0.15
    assert config.MIDS_HIGHS_DELTA_MAX == 5.0
    assert config.PSSI_MOOD_ABZUG == 0.10
    assert config.ENERGIE_TREND_WIDERSPRUCH == 0.8
    assert config.STRUKTUR_LABEL_BONUS == 0.10
    assert 0.0 < config.PERCUSSIVE_NIEDRIG < config.PERCUSSIVE_HOCH < 1.0
```

- [ ] **Step 2: Run → FAIL** `.\venv312\Scripts\python.exe -m pytest tests/test_config.py -q --no-cov` → `AttributeError: ... PAAR_BPM_MAX`

- [ ] **Step 3: Konstanten**

```python
# === Paarung und Bewertung von Kandidaten (Spec 2026-08-21, Abschnitt 2) ===
# Harte Gates auf Paar-Ebene (Spec-Werte).
PAAR_BPM_MAX = 2.0                 # |BPM_A - BPM_B| effektiv (Half/Double erkannt)
# Pitch-Bedarf diff / BPM_A. Spec-Gate; unter PAAR_BPM_MAX ab 50 BPM rechnerisch
# nie aktiv (2/50 = 4 %) — bleibt als eigenstaendiges Gate, wie die Spec es nennt.
PAAR_PITCH_MAX = 0.04
PAAR_HALF_DOUBLE_MAX_BARS = 16     # kurzer Cut bei Half/Double
PAAR_MAX_KOMBINATIONEN = 6         # Zeitpunkt-Kombinationen je Paar (x 2 Blenden)
# Teilwerte. Spec-Werte: PAAR_BPM_SKALA, LUFS_DELTA_MAX_DB, PERCUSSIVE_HOCH/NIEDRIG.
# Alle uebrigen sind STARTWERTE, nicht gemessen — der Hoertest (Teil 3) ersetzt sie.
PAAR_BPM_SKALA = 1.0               # exp(-diff / Skala), Spec-Wert
# Lautheit: 0 dB -> 1.0, >= 3 dB -> 0 (Spec-Wert). Dieselbe 3-dB-Toleranz wie
# GAIN_DIFF_WARN_DB oben (Gain-Hinweis in dj_brain) — bei Aenderung beide pruefen.
LUFS_DELTA_MAX_DB = 3.0
# |delta bass_rms_dbfs| auf [0,1]. Gemessen 2026-08-22 an 231 Tracks / 3664
# Kandidaten: paarweise Differenz (BPM <= 2) Median 1.9 dB, p90 7.2 dB -> p90.
BASS_RMS_DELTA_MAX_DB = 7.0
# |delta syncopation_lokal| auf [0,1]. Gemessen 2026-08-22: paarweise Differenz
# Median 0.09, p90 0.28 -> p90.
SYNCOPATION_DELTA_MAX = 0.3
PERCUSSIVE_HOCH = 0.7              # beide darueber -> Abzug (Spec-Schwelle)
PERCUSSIVE_NIEDRIG = 0.3           # beide darunter -> lange Blende erlaubt (Spec)
PERCUSSIVE_ABZUG = 0.10            # STARTWERT
KICK_KONFLIKT_ABZUG = 0.15         # STARTWERT: beide kick_aktiv -> Bass-Swap-Pflicht, Abzug
# Mittel aus |delta avg_mids_lokal| und |delta avg_highs_lokal| in Prozentpunkten
# (analyze_frequency_bands). Gemessen 2026-08-22: Mids-Differenz Median 2.3 /
# p90 8.1, Hoehen Median 0.8 / p90 2.0 -> Mittel p90 ~ 5.
MIDS_HIGHS_DELTA_MAX = 5.0
PSSI_MOOD_ABZUG = 0.10             # STARTWERT: PSSI-mood beidseitig vorhanden und verschieden
ENERGIE_TREND_WIDERSPRUCH = 0.8    # STARTWERT: energy_trend von B widerspricht der Richtung
STRUKTUR_LABEL_BONUS = 0.10        # STARTWERT: Outro/Down -> Chorus/Drop
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add hpg_core/config.py tests/test_config.py && git commit -m "feat(config): Konstanten fuer Paar-Kandidaten (Gates, Startwerte)"`

---

### Task 2: Gewichte in `genres.py`

**Files:**
- Modify: `hpg_core/genres.py` (`_TOLERANCE_DEFAULTS` Z. ~500-521; `_validate_genre_tables` Z. ~585-594)
- Test: `tests/test_pair_candidates.py` (neu; weitere Tests kommen in Task 4–6 dazu)

- [ ] **Step 1: Failing test**

```python
"""Tests fuer Paarung und Bewertung von Mixpunkt-Kandidaten (Spec Abschnitt 2)."""
import math

import pytest

from hpg_core.genres import CANONICAL_GENRES, GENRE_TRANSITION_TOLERANCES

KANDIDATEN_GEWICHTE = (
    "kandidaten_harmonic_weight", "kandidaten_bpm_weight", "kandidaten_energy_weight",
    "kandidaten_genre_weight", "kandidaten_groove_weight", "kandidaten_bass_weight",
    "kandidaten_timbre_weight", "kandidaten_mood_weight", "kandidaten_loudness_weight",
    "kandidaten_structure_weight",
)


def test_kandidaten_gewichte_je_genre_summe_eins():
    for genre in CANONICAL_GENRES:
        w = GENRE_TRANSITION_TOLERANCES[genre]
        assert all(k in w for k in KANDIDATEN_GEWICHTE), genre
        assert math.isclose(sum(w[k] for k in KANDIDATEN_GEWICHTE), 1.0, abs_tol=1e-6), genre


def test_kandidaten_gewichte_startwerte():
    w = GENRE_TRANSITION_TOLERANCES["Psytrance"]
    assert w["kandidaten_groove_weight"] == pytest.approx(0.264)
    assert w["kandidaten_harmonic_weight"] == pytest.approx(0.140)
    assert w["kandidaten_loudness_weight"] == pytest.approx(0.060)
    assert w["kandidaten_structure_weight"] == pytest.approx(0.060)


def test_alte_gewichte_unveraendert():
    w = GENRE_TRANSITION_TOLERANCES["Psytrance"]
    assert w["groove_weight"] == pytest.approx(0.300)
    assert w["harmonic_weight"] == pytest.approx(0.160)
```

- [ ] **Step 2: Run → FAIL** `.\venv312\Scripts\python.exe -m pytest tests/test_pair_candidates.py -q --no-cov` → KeyError/assert

- [ ] **Step 3: Gewichte und Validierung**

In `_TOLERANCE_DEFAULTS` nach `"mood_weight": 0.050,` einfuegen (2 Leerzeichen, wie die Tabelle):

```python
  # Paar-Kandidaten (Spec 2026-08-21 Abschnitt 2): eigene Schluessel, damit die
  # acht Track-Gewichte oben unveraendert bleiben. STARTWERTE = Spec-Werte
  # (0.16/0.12/0.12/0.12/0.30/0.08/0.05/0.05) proportional um die zwei neuen
  # Gewichte Lautheit/Struktur (je 0.06) gestaucht, Summe exakt 1.0. Nicht
  # gemessen — der Hoertest (Teil 3) ersetzt sie.
  "kandidaten_harmonic_weight": 0.140,
  "kandidaten_bpm_weight": 0.106,
  "kandidaten_energy_weight": 0.106,
  "kandidaten_genre_weight": 0.106,
  "kandidaten_groove_weight": 0.264,
  "kandidaten_bass_weight": 0.070,
  "kandidaten_timbre_weight": 0.044,
  "kandidaten_mood_weight": 0.044,
  "kandidaten_loudness_weight": 0.060,
  "kandidaten_structure_weight": 0.060,
```

In `_validate_genre_tables` direkt nach der bestehenden Summenpruefung (innerhalb derselben `for genre, werte in GENRE_TRANSITION_TOLERANCES.items():`-Schleife, 4 Leerzeichen):

```python
        summe_k = sum(
            werte[k] for k in (
                "kandidaten_harmonic_weight", "kandidaten_bpm_weight",
                "kandidaten_energy_weight", "kandidaten_genre_weight",
                "kandidaten_groove_weight", "kandidaten_bass_weight",
                "kandidaten_timbre_weight", "kandidaten_mood_weight",
                "kandidaten_loudness_weight", "kandidaten_structure_weight",
            )
        )
        if abs(summe_k - 1.0) > 1e-6:
            problems.append(f"Kandidaten-Gewichte von {genre} summieren auf {summe_k}, nicht 1.0")
```

- [ ] **Step 4: Run → PASS**, dazu `.\venv312\Scripts\python.exe -m pytest tests/test_tolerances.py tests/test_genres.py -q --no-cov` (soweit vorhanden) gruen.
- [ ] **Step 5: Commit** `git add hpg_core/genres.py tests/test_pair_candidates.py && git commit -m "feat(genres): kandidaten_*_weight (10 Startgewichte, Summe 1.0) + Validierung"`

---

### Task 3: `camelot_relation_score` nach `models.py` herausloesen

**Files:**
- Modify: `hpg_core/models.py` (nach `get_camelot_components`, Z. ~120)
- Modify: `hpg_core/playlist.py` (`_calculate_compatibility_inner` Z. ~508-603)
- Test: `tests/test_models.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_models.py — anhaengen
def test_camelot_relation_score_tabelle():
    from hpg_core.models import camelot_relation_score as s
    assert s("8A", "8A") == 100
    assert s("8A", "8B") == 90      # Moll -> Dur
    assert s("8B", "8A") == 85      # Dur -> Moll
    assert s("8A", "9A") == 80
    assert s("8A", "7A") == 80
    assert s("8A", "10A") == 75     # +2, strictness 7 -> loose_factor 1.0
    assert s("8A", "12A") == 70     # +4 experimentell
    assert s("8A", "3A") == 65      # +7 experimentell
    assert s("8A", "12A", allow_experimental=False) == max(5, 15 - 7)
    assert s("8A", "9B") == 60      # diagonal
    assert s("8A", "2A") == 8       # Rest: (15 - 7) * 1.0
    assert s("8A", "8A", penalty=0.85) == 85
    assert s("", "8A") == 10
    assert s("XX", "8A", penalty=0.85) == 8
    assert s("8A", "10A", harmonic_strictness=10) == int(75 * 0.76)
```

- [ ] **Step 2: Run → FAIL** `ImportError: cannot import name 'camelot_relation_score'`

- [ ] **Step 3: Funktion in `models.py`** (nach `get_camelot_components`)

```python
def camelot_relation_score(
    code_a: str, code_b: str, *, harmonic_strictness: int = 7,
    allow_experimental: bool = True, penalty: float = 1.0,
) -> int:
    """Camelot-Punktetabelle fuer zwei Codes (Reihenfolge der Zweige bindend).

    Herausgeloest aus playlist._calculate_compatibility_inner (2026-08-22),
    damit die Paar-Bewertung der Kandidaten (camelot_lokal) dieselbe Tabelle
    nutzt. `penalty` ist der Half/Double-Faktor des Aufrufers (1.0 = direct).
    Fehlende/ungueltige Codes -> 10 * penalty.
    """
    if not code_a or not code_b:
        return int(10 * penalty)
    num1, letter1 = get_camelot_components(code_a)
    num2, letter2 = get_camelot_components(code_b)
    if num1 == 0 or num2 == 0:
        return int(10 * penalty)
    if num1 == num2 and letter1 == letter2:
        return int(100 * penalty)
    if num1 == num2 and letter1 != letter2:
        if letter1 == "A" and letter2 == "B":
            return int(90 * penalty)
        return int(85 * penalty)
    next_num_cw = (num1 % 12) + 1
    next_num_ccw = (num1 - 2 + 12) % 12 + 1
    if letter1 == letter2 and (num2 == next_num_cw or num2 == next_num_ccw):
        return int(80 * penalty)
    # Obergrenze 1.0 (AUDIT-FIX F03): lockere Techniken ueberholen nie den +-1.
    loose_factor = max(0.4, min(1.0, 1.0 - (harmonic_strictness - 7) * 0.08))
    plus_two_num = (num1 + 2 - 1) % 12 + 1
    if num2 == plus_two_num and letter1 == letter2:
        return int(75 * penalty * loose_factor)
    if allow_experimental:
        plus_four_num = (num1 + 4 - 1) % 12 + 1
        if num2 == plus_four_num and letter1 == letter2:
            return int(70 * penalty * loose_factor)
        plus_seven_num = (num1 + 7 - 1) % 12 + 1
        if num2 == plus_seven_num and letter1 == letter2:
            return int(65 * penalty * loose_factor)
    if letter1 != letter2 and (num2 == next_num_cw or num2 == next_num_ccw):
        return int(60 * penalty * loose_factor)
    return max(5, int((15 - harmonic_strictness) * penalty))
```

- [ ] **Step 4: `playlist._calculate_compatibility_inner` ersetzen** — Kopf (Docstring, `strictness`, `allow_experimental`, BPM-Gate) bleibt, alles ab `if not track1.camelotCode` wird zu:

```python
    penalty = BPM_HALF_DOUBLE_PENALTY if bpm_relation != "direct" else 1.0
    return camelot_relation_score(
        track1.camelotCode, track2.camelotCode,
        harmonic_strictness=strictness, allow_experimental=allow_experimental,
        penalty=penalty,
    )
```

Import in `playlist.py` ergaenzen: `from .models import camelot_relation_score` (neben den bestehenden `models`-Importen). `_get_camelot_components` bleibt in `playlist.py` importiert — `tests/test_compatibility.py:6,24-42` importiert es von dort (Waechter Tor 1, Auflage 5). **Einrueckung `tests/test_models.py`: 2 Leerzeichen** (Dateikonvention; den Testcode aus Step 1 entsprechend mit 2 Leerzeichen einruecken).

- [ ] **Step 5: Run → PASS** `.\venv312\Scripts\python.exe -m pytest tests/test_models.py tests/test_compatibility.py tests/test_scoring_contract.py tests/test_playlist*.py -q --no-cov` — alle gruen, **keine** Aenderung an diesen Bestandstests.
- [ ] **Step 6: Commit** `git add hpg_core/models.py hpg_core/playlist.py tests/test_models.py && git commit -m "refactor(models): camelot_relation_score als reine Funktion, playlist delegiert"`

---

### Task 4: `PairCandidate`, Gates, Blendenlaengen

**Files:**
- Create: `hpg_core/pair_candidates.py`
- Test: `tests/test_pair_candidates.py` (anhaengen)

- [ ] **Step 1: Failing tests**

```python
# tests/test_pair_candidates.py — anhaengen
from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import Track
from hpg_core.pair_candidates import (
    PairCandidate, blend_bars_options, pair_gate_reasons,
)


def _sections(duration=300.0, intro_end=60.0, outro_start=240.0):
    return [
        {"label": "intro", "start_time": 0.0, "end_time": intro_end, "avg_energy": 30},
        {"label": "main", "start_time": intro_end, "end_time": outro_start, "avg_energy": 70},
        {"label": "outro", "start_time": outro_start, "end_time": duration, "avg_energy": 30},
    ]


def _track(name="a.mp3", bpm=140.0, duration=300.0, genre="Psytrance", **kw) -> Track:
    t = Track(filePath=name, fileName=name)
    t.bpm = bpm
    t.duration = duration
    t.detected_genre = genre
    t.phrase_unit = 16
    t.first_downbeat = 0.0
    t.downbeat_confidence = 1.0
    t.sections = _sections(duration)
    t.outro_covered = True
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def _grid(bpm=140.0, phrase_unit=16):
    return (60.0 / bpm) * 4 * phrase_unit   # 27.428 s


def _out(t, **kw):
    c = MixCandidate(t=t, schema=["sektion"], section_label="main")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _in(t, **kw):
    return _out(t, **kw)


def test_gates_durchlass():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    out, inn = _out(round(6 * g, 3)), _in(round(3 * g, 3))   # 164.6 s, 82.3 s
    assert pair_gate_reasons(a, b, out, inn, blend_bars=16) == []


def test_gate_bpm_und_pitch():
    a, b = _track(bpm=140.0), _track("b.mp3", bpm=143.0)
    g = _grid()
    r = pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(3 * _grid(143.0), 3)), 16)
    assert "bpm" in r


def test_gate_half_double_erlaubt_mit_relation():
    a, b = _track(bpm=140.0), _track("b.mp3", bpm=70.0)
    g_a, g_b = _grid(140.0), _grid(70.0)
    r = pair_gate_reasons(a, b, _out(round(6 * g_a, 3)), _in(round(3 * g_b, 3)), 16)
    assert "bpm" not in r and "pitch" not in r


def test_gate_blende_im_outro_und_benannter_cue_ausnahme():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    spaet = _out(round(8 * g, 3))          # 219.4 s, 16 Takte = 27.4 s -> 246.9 > 240
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # "Drop 2" ist benannter_cue, aber KEIN IN/OUT-Muster -> Guard bleibt.
    spaet.schema = ["benannter_cue"]
    a.cue_points = [{"t": round(8 * g, 3), "name": "Drop 2", "typ": 0, "hot_cue": None, "provenance": "manual"}]
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # Manueller "MIX OUT"-Cue, der (floor, Teil-1-Quantisierung) auf denselben Gitterpunkt faellt -> guard-frei.
    a.cue_points = [{"t": round(8 * g, 3) + 0.4, "name": "MIX OUT", "typ": 0, "hot_cue": None, "provenance": "manual"}]
    assert "blende_im_outro" not in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)
    # Auto-Cue mit OUT im Namen zaehlt nicht (provenance auto).
    a.cue_points = [{"t": round(8 * g, 3), "name": "CUE(Auto) OUT", "typ": 0, "hot_cue": None, "provenance": "auto"}]
    assert "blende_im_outro" in pair_gate_reasons(a, b, spaet, _in(round(3 * g, 3)), 16)


def test_blend_bars_options_unter_min_transition_bars_entfaellt():
    a = _track()
    g = _grid()
    # 9 Phrasen = 246.9 s liegt nach dem Outro-Start 240 -> Deckel < 8 Takte -> keine Blende
    c = _out(round(8 * g + 6 * (60.0 / 140.0) * 4, 3))   # 229.7 s, bis 240 bleiben 10.3 s = 6 Takte
    assert blend_bars_options(a, c, "direct") == []


def test_gate_in_im_intro_coverage_gitter():
    a, b = _track(), _track("b.mp3")
    g = _grid()
    assert "in_im_intro" in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(1 * g, 3)), 16)
    assert "coverage" in pair_gate_reasons(
        a, b, _out(round(6 * g, 3), section_label="unanalysed"), _in(round(3 * g, 3)), 16)
    a.outro_covered = False
    assert "outro_covered" in pair_gate_reasons(a, b, _out(round(6 * g, 3)), _in(round(3 * g, 3)), 16)
    a.outro_covered = True
    assert "gitter_out" in pair_gate_reasons(a, b, _out(round(6 * g + 1.0, 3)), _in(round(3 * g, 3)), 16)


def test_gate_gitter_pssi():
    a, b = _track(), _track("b.mp3")
    a.phrase_grid = [0.0, 30.0, 61.0, 95.0, 130.0, 170.0, 200.0, 230.0]
    out = _out(170.0)
    assert "gitter_out" not in pair_gate_reasons(a, b, out, _in(round(3 * _grid(), 3)), 16)
    assert "gitter_out" in pair_gate_reasons(a, b, _out(171.0), _in(round(3 * _grid(), 3)), 16)


def test_blend_bars_options_deckel_und_half_double():
    a = _track()
    g = _grid()
    assert blend_bars_options(a, _out(round(6 * g, 3)), "direct") == [16, 32]
    # 219.4 s: bis Outro 240 bleiben 20.6 s = 12.0 Takte (1.714 s/Takt)
    assert blend_bars_options(a, _out(round(8 * g, 3)), "direct") == [12]
    assert blend_bars_options(a, _out(round(6 * g, 3)), "half") == [16]


def test_paircandidate_roundtrip():
    pc = PairCandidate(out_a=_out(10.0), in_b=_in(20.0), blend_bars=16, overlap_sec=27.4,
                       score=0.5, teilwerte={"bpm": 1.0}, flags={"half_double": False},
                       begruendung="x", rang=1, bpm_relation="direct")
    d = pc.to_dict()
    assert d["out_a"]["t"] == 10.0 and d["t_out"] == 10.0 and d["t_in"] == 20.0
    back = PairCandidate.from_dict(d)
    assert back.out_a.t == 10.0 and back.in_b.t == 20.0 and back.blend_bars == 16
```

- [ ] **Step 2: Run → FAIL** `ModuleNotFoundError: hpg_core.pair_candidates`

- [ ] **Step 3: Modul anlegen** (Kopf + Datentyp + Gates + Blenden; Score-Teile folgen in Task 5/6)

```python
"""Paarung und Bewertung von Mixpunkt-Kandidaten (Spec 2026-08-21, Abschnitt 2).

Eingabe: Track A (`mix_out_candidates`), Track B (`mix_in_candidates`).
Ausgabe: sortierte `PairCandidate`s (Zeitpunkt-Kombination x Blendenlaenge)
mit Gates, Score aus allen Faktoren lokal an der Naht, Teilwerten, Flags und
Begruendung. Reine Funktionen, kein Audio. Teil 4 bindet das Ergebnis an
Scoring, GUI und Export an; hier wird nichts am Track veraendert.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields

from .config import (
    BASS_RMS_DELTA_MAX_DB, BPM_HALF_DOUBLE_PENALTY, ENERGIE_TREND_WIDERSPRUCH,
    KICK_KONFLIKT_ABZUG, LUFS_DELTA_MAX_DB, MIDS_HIGHS_DELTA_MAX, MIN_TRANSITION_BARS,
    PAAR_BPM_MAX, PAAR_BPM_SKALA, PAAR_HALF_DOUBLE_MAX_BARS, PAAR_MAX_KOMBINATIONEN,
    PAAR_PITCH_MAX, PERCUSSIVE_ABZUG, PERCUSSIVE_HOCH, PERCUSSIVE_NIEDRIG, PSSI_MOOD_ABZUG,
    STRUKTUR_LABEL_BONUS, SYNCOPATION_DELTA_MAX,
)
from .dj_brain import (
    _get_intro_end_from_sections, _get_outro_start_from_sections,
    get_genre_compatibility, get_mix_profile,
)
from .mix_candidates import (
    CUE_IN_PATTERN, CUE_OUT_PATTERN, SCHEMA_PRIORITAET, MixCandidate, _quantize,
    quantize_to_points,
)
from .models import (
    QUANTIZE_TOLERANCE_SEC, Track, camelot_relation_score, effective_bpm_diff,
    quantize_to_grid, seconds_per_bar,
)
from .tolerances import get_tolerances
from .transition_features import (
    BASS_PATTERN_SHARE, DEFAULT_BRIGHTNESS_DELTA_MAX, DEFAULT_FLATNESS_DELTA_MAX,
    DEFAULT_GROOVE_SIM_FLOOR, DEFAULT_PUNCH_DELTA_MAX, DEFAULT_SUB_DELTA_MAX,
    MODE_SWITCH_PENALTY, _normiert, _spreize, cosine_similarity,
)

# Reihenfolge der Faktoren = Reihenfolge in Teilwerten/Begruendung.
FAKTOREN = ("harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre",
            "mood", "loudness", "structure")
SCHEMA_RANG = {s: i for i, s in enumerate(SCHEMA_PRIORITAET)}


@dataclass
class PairCandidate:
    """Eine Kombination aus Mix-Out-Kandidat (A) und Mix-In-Kandidat (B) mit
    Blendenlaenge. Teilwerte je Faktor in [0,1] oder None (nicht messbar)."""
    out_a: MixCandidate
    in_b: MixCandidate
    blend_bars: int
    overlap_sec: float
    score: float = 0.0
    teilwerte: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    begruendung: str = ""
    rang: int = 0
    bpm_relation: str = "direct"

    @property
    def t_out(self) -> float:
        return self.out_a.t

    @property
    def t_in(self) -> float:
        return self.in_b.t

    def to_dict(self) -> dict:
        d = asdict(self)
        d["t_out"], d["t_in"] = self.t_out, self.t_in
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PairCandidate":
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in names}
        kw["out_a"] = MixCandidate.from_dict(kw["out_a"])
        kw["in_b"] = MixCandidate.from_dict(kw["in_b"])
        return cls(**kw)


def _genre(track: Track) -> str:
    # Lazy: playlist importiert (ab Teil 4) dieses Modul — kein Importzyklus.
    from .playlist import _resolve_track_genre
    return _resolve_track_genre(track)


def _grid_sec(track: Track) -> float:
    unit = int(track.phrase_unit) if track.phrase_unit else get_mix_profile(_genre(track)).phrase_unit
    return seconds_per_bar(track.bpm) * unit


def _guard_frei(track: Track, cand: MixCandidate, seite: str) -> bool:
    """Spec-Ausnahme (Abschnitt 1): nur ein MANUELLER Cue mit IN- bzw. OUT-Muster
    schlaegt den Guard. MixCandidate traegt das Muster nicht; deshalb wird ueber
    track.cue_points geprueft, ob ein solcher Cue — mit derselben Quantisierung
    wie in Teil 1 (mix_candidates._quantize) — auf cand.t faellt."""
    if "benannter_cue" not in (cand.schema or []):
        return False
    muster = CUE_IN_PATTERN if seite == "in" else CUE_OUT_PATTERN
    grid = _grid_sec(track)
    for cue in track.cue_points or []:
        if cue.get("provenance") != "manual":
            continue
        if not muster.search((cue.get("name") or "").upper()):
            continue
        q = _quantize(float(cue["t"]), seite, list(track.phrase_grid or []), grid, track.phrase_anchor)
        if q is not None and abs(round(float(q), 3) - cand.t) <= QUANTIZE_TOLERANCE_SEC:
            return True
    return False


def _auf_gitter(track: Track, t: float, seite: str) -> bool:
    """Punkt liegt (mit QUANTIZE_TOLERANCE_SEC) auf dem PSSI-Gitter bzw. dem
    Phrasenraster des Tracks."""
    if track.phrase_grid:
        q = quantize_to_points(t, list(track.phrase_grid), "floor" if seite == "out" else "ceil")
    else:
        grid = _grid_sec(track)
        if grid <= 0.0:
            return False
        q = quantize_to_grid(t, grid, track.phrase_anchor, "round")
    return q is not None and abs(q - t) <= QUANTIZE_TOLERANCE_SEC


def _outro_deckel(track_a: Track, out_a: MixCandidate) -> float:
    """Spaetestes Ende der Blende: Outro-Start; bei guard-freiem OUT-Cue das Trackende."""
    if _guard_frei(track_a, out_a, "out"):
        return float(track_a.duration)
    return _get_outro_start_from_sections(track_a.sections, float(track_a.duration))


def pair_gate_reasons(track_a: Track, track_b: Track, out_a: MixCandidate,
                      in_b: MixCandidate, blend_bars: int) -> list[str]:
    """Harte Gates auf Paar-Ebene (Spec Abschnitt 2, Schritt 1). Leere Liste =
    Kombination erlaubt; sonst die Gruende (stabil benannt, fuer Messung)."""
    reasons: list[str] = []
    diff, rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    if diff > PAAR_BPM_MAX:
        reasons.append("bpm")
    if track_a.bpm > 0 and diff / track_a.bpm > PAAR_PITCH_MAX:
        reasons.append("pitch")
    if out_a.section_label == "unanalysed" or in_b.section_label == "unanalysed":
        reasons.append("coverage")
    if not track_a.outro_covered:
        reasons.append("outro_covered")
    spb = seconds_per_bar(track_a.bpm)
    overlap = blend_bars * spb
    if out_a.t + overlap > _outro_deckel(track_a, out_a) + QUANTIZE_TOLERANCE_SEC:
        reasons.append("blende_im_outro")
    intro_end = _get_intro_end_from_sections(track_b.sections)
    if not _guard_frei(track_b, in_b, "in") and in_b.t < intro_end - QUANTIZE_TOLERANCE_SEC:
        reasons.append("in_im_intro")
    if in_b.t < 0.0 or in_b.t > float(track_b.duration):
        reasons.append("in_ausserhalb")
    if not _auf_gitter(track_a, out_a.t, "out"):
        reasons.append("gitter_out")
    if not _auf_gitter(track_b, in_b.t, "in"):
        reasons.append("gitter_in")
    return reasons


def blend_bars_options(track_a: Track, out_a: MixCandidate, bpm_relation: str) -> list[int]:
    """Beide Genre-Blendenlaengen (transition_bars), je durch den Outro-Deckel
    auf ganze Takte geklemmt; Half/Double hoechstens PAAR_HALF_DOUBLE_MAX_BARS;
    unter MIN_TRANSITION_BARS (Projekt-Untergrenze, wie playlist._outro_overlap_limit)
    entfaellt die Laenge. Doppelte Werte nach dem Deckel werden zusammengelegt."""
    kurz, lang = get_mix_profile(_genre(track_a)).transition_bars
    spb = seconds_per_bar(track_a.bpm)
    if spb <= 0.0:
        return []
    max_bars = int(math.floor((_outro_deckel(track_a, out_a) - out_a.t + QUANTIZE_TOLERANCE_SEC) / spb))
    out: list[int] = []
    for bars in (int(kurz), int(lang)):
        b = min(bars, max_bars)
        if bpm_relation != "direct":
            b = min(b, PAAR_HALF_DOUBLE_MAX_BARS)
        if b >= MIN_TRANSITION_BARS and b not in out:
            out.append(b)
    return out
```

- [ ] **Step 4: Run → PASS** `.\venv312\Scripts\python.exe -m pytest tests/test_pair_candidates.py -q --no-cov`
- [ ] **Step 5: Commit** `git add hpg_core/pair_candidates.py tests/test_pair_candidates.py && git commit -m "feat(paare): PairCandidate, Paar-Gates, Blendenlaengen (Spec Abschnitt 2, Schritt 1+3)"`

---

### Task 5: Teilwerte und Score (`score_pair`)

**Files:**
- Modify: `hpg_core/pair_candidates.py`
- Test: `tests/test_pair_candidates.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_pair_candidates.py — anhaengen
from hpg_core.pair_candidates import score_pair


def _voll(t, **kw):
    """Kandidat mit allen lokalen Messwerten gesetzt."""
    basis = dict(
        schema=["pssi_phrase"], section_label="main", phrase_label="Chorus",
        neuheit=0.6, traegt_allein=True,
        groove_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
        bass_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
        syncopation_lokal=0.2,
        percussive_ratio_lokal=0.5, sub_energy=0.5, bass_punch=2.0,
        bass_rms_dbfs=-20.0, kick_aktiv=True, camelot_lokal="8A",
        key_confidence_lokal=0.9, timbre_fingerprint_lokal=[1.0, 0.5, 0.2],
        brightness_lokal=50, flatness_lokal=0.1, avg_mids_lokal=40.0,
        avg_highs_lokal=20.0, energy_lokal=70, energy_trend="rising",
        lufs_lokal=-10.0, mood={"pssi_mood": 1, "brightness": 50, "flatness": 0.1,
                                "key_mode": "Minor"}, vocal_aktiv_lokal=False,
    )
    basis.update(kw)
    c = MixCandidate(t=t)
    for k, v in basis.items():
        setattr(c, k, v)
    return c


def test_score_identische_kandidaten_nahe_eins_und_alle_teilwerte():
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False)
    score, teil, flags = score_pair(a, b, out, inn, blend_bars=16, energy_direction="maintain")
    assert set(teil) == {"harmonic", "bpm", "energy", "genre", "groove", "bass",
                         "timbre", "mood", "loudness", "structure"}
    assert all(v is not None for v in teil.values())
    assert teil["bpm"] == pytest.approx(1.0)
    assert teil["loudness"] == pytest.approx(1.0)
    assert teil["harmonic"] == pytest.approx(1.0)
    assert score > 0.9
    assert flags["bass_swap_pflicht"] is False and flags["half_double"] is False


def test_score_kick_konflikt_flag_und_abzug():
    a, b = _track(), _track("b.mp3")
    s_ohne, t_ohne, _ = score_pair(a, b, _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False), 16)
    s_mit, t_mit, flags = score_pair(a, b, _voll(160.0), _voll(80.0), 16)
    assert flags["bass_swap_pflicht"] is True
    assert t_mit["bass"] == pytest.approx(t_ohne["bass"] - 0.15)
    assert s_mit < s_ohne


def test_score_lautheit_linear_bis_3db():
    a, b = _track(), _track("b.mp3")
    _, t1, _ = score_pair(a, b, _voll(160.0), _voll(80.0, lufs_lokal=-11.5), 16)
    _, t3, _ = score_pair(a, b, _voll(160.0), _voll(80.0, lufs_lokal=-14.0), 16)
    assert t1["loudness"] == pytest.approx(0.5)
    assert t3["loudness"] == pytest.approx(0.0)


def test_score_fehlende_werte_werden_umverteilt_nicht_null():
    a, b = _track(), _track("b.mp3")
    leer_out = MixCandidate(t=160.0, schema=["sektion"], section_label="main")
    leer_in = MixCandidate(t=80.0, schema=["sektion"], section_label="main")
    score, teil, _ = score_pair(a, b, leer_out, leer_in, 16)
    assert teil["harmonic"] is None and teil["loudness"] is None and teil["groove"] is None
    assert teil["bpm"] == pytest.approx(1.0) and teil["genre"] == pytest.approx(1.0)
    assert score == pytest.approx(1.0)      # nur bpm+genre verfuegbar, beide 1.0


def test_score_half_double_penalty_und_vocals():
    a, b = _track(bpm=140.0), _track("b.mp3", bpm=70.0)
    s_hd, _, flags = score_pair(a, b, _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False), 16)
    a2, b2 = _track(), _track("b.mp3")
    s_direct, _, _ = score_pair(a2, b2, _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False), 16)
    assert flags["half_double"] is True
    assert s_hd == pytest.approx(s_direct * 0.85)
    s_voc, _, _ = score_pair(a2, b2, _voll(160.0, kick_aktiv=False, vocal_aktiv_lokal=True),
                             _voll(80.0, kick_aktiv=False, vocal_aktiv_lokal=True), 16)
    assert s_voc == pytest.approx(s_direct - 0.06)


def test_score_harmonie_gewicht_skaliert_mit_key_confidence():
    a, b = _track(), _track("b.mp3")
    # 8A -> 3A = 65/100; mit hoher Confidence drueckt das den Score staerker als mit niedriger
    s_hoch, _, _ = score_pair(a, b, _voll(160.0, kick_aktiv=False),
                              _voll(80.0, kick_aktiv=False, camelot_lokal="3A"), 16)
    s_tief, _, _ = score_pair(a, b, _voll(160.0, kick_aktiv=False, key_confidence_lokal=0.1),
                              _voll(80.0, kick_aktiv=False, camelot_lokal="3A"), 16)
    assert s_tief > s_hoch


def test_score_energie_richtung_und_trend():
    a, b = _track(), _track("b.mp3")
    _, t_up, _ = score_pair(a, b, _voll(160.0, energy_lokal=40), _voll(80.0, energy_lokal=90, energy_trend="rising"), 16, energy_direction="up")
    _, t_w, _ = score_pair(a, b, _voll(160.0, energy_lokal=40), _voll(80.0, energy_lokal=90, energy_trend="falling"), 16, energy_direction="up")
    assert t_up["energy"] == pytest.approx(1.0)
    assert t_w["energy"] == pytest.approx(0.8)


def test_score_struktur_und_mood():
    a, b = _track(), _track("b.mp3")
    _, t1, _ = score_pair(a, b, _voll(160.0, section_label="outro", phrase_label="Outro"),
                          _voll(80.0, neuheit=1.0, traegt_allein=True, phrase_label="Chorus"), 16)
    assert t1["structure"] == pytest.approx(1.0)
    _, t2, _ = score_pair(a, b, _voll(160.0), _voll(80.0, mood={"pssi_mood": 2, "brightness": 50,
                                                                "flatness": 0.1, "key_mode": "Major"}), 16)
    assert t2["mood"] == pytest.approx(1.0 - 0.15 - 0.10)
```

- [ ] **Step 2: Run → FAIL** `ImportError: score_pair`

- [ ] **Step 3: Teilwerte + Score** (an `pair_candidates.py` anhaengen)

```python
def _beide(a, b) -> bool:
    return a is not None and b is not None


def _teil_harmonie(out_a: MixCandidate, in_b: MixCandidate, *, harmonic_strictness: int,
                   allow_experimental: bool) -> float | None:
    if not out_a.camelot_lokal or not in_b.camelot_lokal:
        return None
    return camelot_relation_score(
        out_a.camelot_lokal, in_b.camelot_lokal, harmonic_strictness=harmonic_strictness,
        allow_experimental=allow_experimental, penalty=1.0) / 100.0


def _teil_bpm(diff: float) -> float:
    return math.exp(-diff / PAAR_BPM_SKALA)


def _teil_energie(out_a: MixCandidate, in_b: MixCandidate, richtung: str | None) -> float | None:
    if not _beide(out_a.energy_lokal, in_b.energy_lokal):
        return None
    diff = float(in_b.energy_lokal) - float(out_a.energy_lokal)
    # Formeln wie playlist.calculate_enhanced_compatibility (Energie-Block).
    if richtung == "up":
        wert = min(1.0, max(0.0, diff) / 50.0)
    elif richtung == "down":
        wert = min(1.0, max(0.0, -diff) / 50.0)
    elif richtung == "maintain":
        wert = max(0.0, 1.0 - abs(diff) / 50.0)
    else:
        wert = max(0.0, 1.0 - abs(diff) / 100.0)
    trend = in_b.energy_trend or ""
    if (richtung == "up" and trend == "falling") or (richtung == "down" and trend == "rising"):
        wert *= ENERGIE_TREND_WIDERSPRUCH
    return wert


def _teil_groove(out_a: MixCandidate, in_b: MixCandidate, tol: dict, flags: dict) -> float | None:
    bass_sim = cosine_similarity(out_a.bass_pattern_lokal, in_b.bass_pattern_lokal)
    onset_sim = cosine_similarity(out_a.groove_pattern_lokal, in_b.groove_pattern_lokal)
    if bass_sim is None and onset_sim is None:
        return None
    if bass_sim is None:
        roh = onset_sim
    elif onset_sim is None:
        roh = bass_sim
    else:
        roh = BASS_PATTERN_SHARE * bass_sim + (1.0 - BASS_PATTERN_SHARE) * onset_sim
    wert = _spreize(roh, tol.get("groove_sim_floor", DEFAULT_GROOVE_SIM_FLOOR))
    if _beide(out_a.syncopation_lokal, in_b.syncopation_lokal):
        wert *= _normiert(in_b.syncopation_lokal - out_a.syncopation_lokal, SYNCOPATION_DELTA_MAX)
    pa, pb = out_a.percussive_ratio_lokal, in_b.percussive_ratio_lokal
    if _beide(pa, pb):
        if pa > PERCUSSIVE_HOCH and pb > PERCUSSIVE_HOCH:
            wert -= PERCUSSIVE_ABZUG
        flags["lange_blende_erlaubt"] = bool(pa < PERCUSSIVE_NIEDRIG and pb < PERCUSSIVE_NIEDRIG)
    return max(0.0, min(1.0, wert))


def _teil_bass(out_a: MixCandidate, in_b: MixCandidate, tol: dict, flags: dict) -> float | None:
    sub = (_normiert(in_b.sub_energy - out_a.sub_energy, tol.get("bass_delta_max", DEFAULT_SUB_DELTA_MAX))
           if _beide(out_a.sub_energy, in_b.sub_energy) else None)
    punch = (_normiert(in_b.bass_punch - out_a.bass_punch, DEFAULT_PUNCH_DELTA_MAX)
             if _beide(out_a.bass_punch, in_b.bass_punch) else None)
    if sub is None and punch is None:
        return None
    if sub is None:
        wert = punch
    elif punch is None:
        wert = sub
    else:
        wert = 0.6 * sub + 0.4 * punch
    if _beide(out_a.bass_rms_dbfs, in_b.bass_rms_dbfs):
        wert *= _normiert(in_b.bass_rms_dbfs - out_a.bass_rms_dbfs, BASS_RMS_DELTA_MAX_DB)
    konflikt = bool(out_a.kick_aktiv and in_b.kick_aktiv)
    flags["bass_swap_pflicht"] = konflikt
    if konflikt:
        wert -= KICK_KONFLIKT_ABZUG
    return max(0.0, min(1.0, wert))


def _teil_timbre(out_a: MixCandidate, in_b: MixCandidate) -> float | None:
    wert = cosine_similarity(out_a.timbre_fingerprint_lokal, in_b.timbre_fingerprint_lokal)
    if wert is None:
        return None
    deltas = []
    if _beide(out_a.avg_mids_lokal, in_b.avg_mids_lokal):
        deltas.append(abs(in_b.avg_mids_lokal - out_a.avg_mids_lokal))
    if _beide(out_a.avg_highs_lokal, in_b.avg_highs_lokal):
        deltas.append(abs(in_b.avg_highs_lokal - out_a.avg_highs_lokal))
    if deltas:
        wert *= _normiert(sum(deltas) / len(deltas), MIDS_HIGHS_DELTA_MAX)
    return max(0.0, min(1.0, wert))


def _teil_mood(out_a: MixCandidate, in_b: MixCandidate, tol: dict) -> float | None:
    ma, mb = out_a.mood or {}, in_b.mood or {}
    ha = ma.get("brightness", out_a.brightness_lokal)
    hb = mb.get("brightness", in_b.brightness_lokal)
    fa = ma.get("flatness", out_a.flatness_lokal)
    fb = mb.get("flatness", in_b.flatness_lokal)
    hell = _normiert(float(hb) - float(ha), tol.get("brightness_delta_max", DEFAULT_BRIGHTNESS_DELTA_MAX)) if _beide(ha, hb) else None
    flach = _normiert(float(fb) - float(fa), DEFAULT_FLATNESS_DELTA_MAX) if _beide(fa, fb) else None
    if hell is None and flach is None:
        return None
    if hell is None:
        wert = flach
    elif flach is None:
        wert = hell
    else:
        wert = 0.7 * hell + 0.3 * flach
    if ma.get("key_mode") and mb.get("key_mode") and ma["key_mode"] != mb["key_mode"]:
        wert -= MODE_SWITCH_PENALTY
    if ma.get("pssi_mood") is not None and mb.get("pssi_mood") is not None and ma["pssi_mood"] != mb["pssi_mood"]:
        wert -= PSSI_MOOD_ABZUG
    return max(0.0, min(1.0, wert))


def _teil_lautheit(out_a: MixCandidate, in_b: MixCandidate) -> float | None:
    if not _beide(out_a.lufs_lokal, in_b.lufs_lokal):
        return None
    return _normiert(in_b.lufs_lokal - out_a.lufs_lokal, LUFS_DELTA_MAX_DB)


_OUT_LABELS = {"outro", "breakdown", "Outro", "Down"}
_IN_LABELS = {"drop", "Chorus"}


def _teil_struktur(out_a: MixCandidate, in_b: MixCandidate) -> float | None:
    teile = []
    if in_b.neuheit is not None:
        teile.append(float(in_b.neuheit))
    if in_b.traegt_allein is not None:
        teile.append(1.0 if in_b.traegt_allein else 0.0)
    if not teile:
        return None
    wert = sum(teile) / len(teile)
    aus_out = out_a.section_label in _OUT_LABELS or out_a.phrase_label in _OUT_LABELS
    in_in = in_b.section_label in _IN_LABELS or in_b.phrase_label in _IN_LABELS
    if aus_out and in_in:
        wert += STRUKTUR_LABEL_BONUS
    return max(0.0, min(1.0, wert))


def _gewichte(tol: dict) -> dict[str, float]:
    return {f: float(tol.get(f"kandidaten_{f}_weight", 0.0)) for f in FAKTOREN}


def score_pair(track_a: Track, track_b: Track, out_a: MixCandidate, in_b: MixCandidate,
               blend_bars: int, *, energy_direction=None, harmonic_strictness: int = 7,
               allow_experimental: bool = True,
               tolerances: dict | None = None) -> tuple[float, dict, dict]:
    """Score einer Kombination aus allen Faktoren lokal an der Naht (Spec
    Abschnitt 2, Schritt 2). Liefert (score, teilwerte, flags). Fehlende
    Teilwerte (None) werden per combine_weighted umverteilt, nie mit 0 bewertet.
    Half/Double: Gesamtscore x BPM_HALF_DOUBLE_PENALTY. Vocals beidseitig: -0.06.
    `blend_bars` ist bewusst KEIN Score-Merkmal (Spec Abschnitt 1: Blendenlaenge
    als Qualitaetsmerkmal widerlegt, rho -0.08); es dient nur den Gates/Flags."""
    from .playlist import VOCAL_CLASH_PENALTY, combine_weighted   # lazy, s. _genre
    richtung = getattr(energy_direction, "value", energy_direction)
    genre_a, genre_b = _genre(track_a), _genre(track_b)
    tol = tolerances if tolerances is not None else get_tolerances(genre_a)
    diff, rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    flags = {"half_double": rel != "direct", "bass_swap_pflicht": False,
             "lange_blende_erlaubt": False,
             "benannter_cue": _guard_frei(track_a, out_a, "out") or _guard_frei(track_b, in_b, "in")}
    teil = {
        "harmonic": _teil_harmonie(out_a, in_b, harmonic_strictness=harmonic_strictness,
                                   allow_experimental=allow_experimental),
        "bpm": _teil_bpm(diff),
        "energy": _teil_energie(out_a, in_b, richtung),
        "genre": get_genre_compatibility(genre_a, genre_b),
        "groove": _teil_groove(out_a, in_b, tol, flags),
        "bass": _teil_bass(out_a, in_b, tol, flags),
        "timbre": _teil_timbre(out_a, in_b),
        "mood": _teil_mood(out_a, in_b, tol),
        "loudness": _teil_lautheit(out_a, in_b),
        "structure": _teil_struktur(out_a, in_b),
    }
    gew = _gewichte(tol)
    if teil["harmonic"] is not None and _beide(out_a.key_confidence_lokal, in_b.key_confidence_lokal):
        gew["harmonic"] *= max(0.0, min(1.0, min(out_a.key_confidence_lokal, in_b.key_confidence_lokal)))
    score = combine_weighted(teil, gew)
    if flags["half_double"]:
        score *= BPM_HALF_DOUBLE_PENALTY
    if out_a.vocal_aktiv_lokal and in_b.vocal_aktiv_lokal:
        score -= VOCAL_CLASH_PENALTY
    return max(0.0, min(1.0, score)), teil, flags
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add hpg_core/pair_candidates.py tests/test_pair_candidates.py && git commit -m "feat(paare): score_pair — alle Faktoren lokal an der Naht, Umverteilung, Flags"`

---

### Task 6: Dedupe/Kappung, Rang, Begruendung, `build_pair_candidates`

**Files:**
- Modify: `hpg_core/pair_candidates.py`
- Test: `tests/test_pair_candidates.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_pair_candidates.py — anhaengen
from hpg_core.pair_candidates import begruendung_aus_teilwerten, build_pair_candidates


def _track_mit_kandidaten(name, bpm=140.0, outs=(), ins=()):
    t = _track(name, bpm=bpm)
    t.mix_out_candidates = [c.to_dict() for c in outs]
    t.mix_in_candidates = [c.to_dict() for c in ins]
    return t


def test_build_liefert_sortierte_raenge_und_zwei_blenden():
    g = _grid()
    a = _track_mit_kandidaten("a.mp3", outs=[_voll(round(5 * g, 3), kick_aktiv=False),
                                             _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"])])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    res = build_pair_candidates(a, b)
    assert len(res) == 4                      # 2 Kombinationen x 2 Blenden
    assert [p.rang for p in res] == [1, 2, 3, 4]
    assert all(res[i].score >= res[i + 1].score for i in range(len(res) - 1))
    assert {p.blend_bars for p in res} == {16, 32}
    assert all(p.begruendung for p in res)
    assert all(p.overlap_sec == pytest.approx(p.blend_bars * (60.0 / 140.0) * 4) for p in res)


def test_build_gates_leer_bei_bpm():
    a = _track_mit_kandidaten("a.mp3", bpm=140.0, outs=[_voll(round(5 * _grid(), 3))])
    b = _track_mit_kandidaten("b.mp3", bpm=143.0, ins=[_voll(round(3 * _grid(143.0), 3))])
    assert build_pair_candidates(a, b) == []


def test_build_dedupe_und_kappung_mit_schema_garantie():
    g = _grid()
    outs = [_voll(round(k * g, 3), kick_aktiv=False) for k in (3, 4, 5, 6, 7)]       # 5 pssi
    outs.append(_voll(round(7 * g, 3), kick_aktiv=False, schema=["sektion"], neuheit=0.0, traegt_allein=False))
    ins = [_voll(round(k * g, 3), kick_aktiv=False) for k in (3, 4)]
    a = _track_mit_kandidaten("a.mp3", outs=outs)
    b = _track_mit_kandidaten("b.mp3", ins=ins)
    res = build_pair_candidates(a, b)
    kombis = {(p.t_out, p.t_in) for p in res}
    assert len(kombis) <= 6
    assert any("sektion" in p.out_a.schema for p in res)      # Schema-Garantie
    assert len(res) <= 12


def test_build_dedupe_fasst_nahe_gleiche_schemata_zusammen():
    g = _grid()
    o1 = _voll(round(5 * g, 3), kick_aktiv=False)
    o2 = _voll(round(5 * g + 2.0, 3), kick_aktiv=False)   # < 1 Phrase, gleiches Hauptschema
    a = _track_mit_kandidaten("a.mp3", outs=[o1, o2])
    a.phrase_grid = [0.0, round(5 * g, 3), round(5 * g + 2.0, 3), round(8 * g, 3)]
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    res = build_pair_candidates(a, b)
    assert len({(p.t_out, p.t_in) for p in res}) == 1


def test_build_dedupe_laesst_genau_eine_phrase_abstand_getrennt():
    g = _grid()
    # Teil 1 rundet auf 3 Dezimalen: round(4g)-round(3g) = 27.428 < 27.42857
    o1, o2 = _voll(round(3 * g, 3), kick_aktiv=False), _voll(round(4 * g, 3), kick_aktiv=False)
    a = _track_mit_kandidaten("a.mp3", outs=[o1, o2])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    res = build_pair_candidates(a, b)
    assert len({(p.t_out, p.t_in) for p in res}) == 2
    assert {p.blend_bars for p in res} == {16, 32}


def test_begruendung_aus_teilwerten_fester_text():
    txt = begruendung_aus_teilwerten(
        {"harmonic": 0.9, "bpm": 1.0, "groove": 0.6, "loudness": None},
        {"bass_swap_pflicht": True, "half_double": False, "lange_blende_erlaubt": False,
         "benannter_cue": False}, 16)
    assert "Harmonie stark" in txt and "Groove mittel" in txt and "Lautheit nicht messbar" in txt
    assert "Bass-Swap noetig" in txt and "16 Takte" in txt
```

- [ ] **Step 2: Run → FAIL** `ImportError: build_pair_candidates`

- [ ] **Step 3: Implementierung** (anhaengen)

```python
_FAKTOR_NAMEN = {
    "harmonic": "Harmonie", "bpm": "Tempo", "energy": "Energie", "genre": "Genre",
    "groove": "Groove", "bass": "Bass", "timbre": "Klangfarbe", "mood": "Stimmung",
    "loudness": "Lautheit", "structure": "Struktur",
}


def _stufe(wert: float | None) -> str:
    if wert is None:
        return "nicht messbar"
    if wert >= 0.8:
        return "stark"
    if wert >= 0.5:
        return "mittel"
    return "schwach"


def begruendung_aus_teilwerten(teilwerte: dict, flags: dict, blend_bars: int) -> str:
    """Begruendung ausschliesslich aus Teilwerten und Flags (kein freier Text)."""
    teile = [f"{_FAKTOR_NAMEN.get(k, k)} {_stufe(teilwerte.get(k))}" for k in FAKTOREN if k in teilwerte]
    if flags.get("bass_swap_pflicht"):
        teile.append("Bass-Swap noetig")
    if flags.get("half_double"):
        teile.append(f"Half/Double, Cut <= {PAAR_HALF_DOUBLE_MAX_BARS} Takte")
    if flags.get("lange_blende_erlaubt"):
        teile.append("lange Blende erlaubt")
    if flags.get("benannter_cue"):
        teile.append("benannter Cue")
    teile.append(f"Blende {blend_bars} Takte")
    return "; ".join(teile)


def _hauptschema(cand: MixCandidate) -> str:
    schemata = [s for s in (cand.schema or []) if s in SCHEMA_RANG]
    return min(schemata, key=SCHEMA_RANG.get) if schemata else ""


def _gleiche_kombination(p: PairCandidate, q: PairCandidate, grid_a: float, grid_b: float) -> bool:
    """Spec Schritt 4: |dt| < 1 Phrase und gleiches Schema. Toleranz abgezogen,
    weil Teil 1 t auf 3 Dezimalen rundet — sonst verschmelzen Gitterpunkte, die
    genau eine Phrase auseinanderliegen. Gleiche Blende, sonst fiele die zweite
    Blendenlaenge (identischer Score) als Duplikat weg."""
    return (p.blend_bars == q.blend_bars
            and abs(p.t_out - q.t_out) < grid_a - QUANTIZE_TOLERANCE_SEC
            and abs(p.t_in - q.t_in) < grid_b - QUANTIZE_TOLERANCE_SEC
            and _hauptschema(p.out_a) == _hauptschema(q.out_a)
            and _hauptschema(p.in_b) == _hauptschema(q.in_b))


def _sortschluessel(p: PairCandidate):
    return (-p.score, SCHEMA_RANG.get(_hauptschema(p.out_a), len(SCHEMA_RANG)),
            SCHEMA_RANG.get(_hauptschema(p.in_b), len(SCHEMA_RANG)), p.blend_bars)


def dedupe_and_cap(paare: list[PairCandidate], grid_a: float, grid_b: float,
                   schemata_vorhanden: set[str]) -> list[PairCandidate]:
    """Schritt 4: nahe Kombinationen gleichen Schemas zusammenlegen (bester Score
    bleibt, Schemata vereinigt), Kappung auf PAAR_MAX_KOMBINATIONEN Zeitpunkt-
    Kombinationen (je bis zu 2 Blenden), mindestens eine Kombination je
    vorhandenem Schema."""
    paare = sorted(paare, key=_sortschluessel)
    # Dedupe ueber Kombinationen (ohne Blende): Vertreter = bester Score.
    vertreter: list[PairCandidate] = []
    zuordnung: dict[int, PairCandidate] = {}
    for p in paare:
        ziel = next((v for v in vertreter if _gleiche_kombination(p, v, grid_a, grid_b)), None)
        if ziel is None:
            vertreter.append(p)
            zuordnung[id(p)] = p
        else:
            for s in p.out_a.schema:
                if s not in ziel.out_a.schema:
                    ziel.out_a.schema.append(s)
            for s in p.in_b.schema:
                if s not in ziel.in_b.schema:
                    ziel.in_b.schema.append(s)
            zuordnung[id(p)] = ziel
    kombis: list[tuple[float, float]] = []
    for v in vertreter:
        key = (v.t_out, v.t_in)
        if key not in kombis:
            kombis.append(key)
    gewaehlt = kombis[:PAAR_MAX_KOMBINATIONEN]

    def schemata_in(auswahl):
        s = set()
        for p in vertreter:
            if (p.t_out, p.t_in) in auswahl:
                s.update(p.out_a.schema)
                s.update(p.in_b.schema)
        return s

    # Schema-Garantie: fehlt ein vorhandenes Schema, ersetzt die beste Kombination
    # mit diesem Schema die schlechteste gewaehlte, deren Schemata anderweitig
    # vertreten bleiben.
    for schema in SCHEMA_PRIORITAET:
        if schema not in schemata_vorhanden or schema in schemata_in(gewaehlt):
            continue
        ersatz = next(((p.t_out, p.t_in) for p in vertreter
                       if schema in p.out_a.schema or schema in p.in_b.schema), None)
        if ersatz is None or ersatz in gewaehlt:
            continue
        if len(gewaehlt) < PAAR_MAX_KOMBINATIONEN:
            gewaehlt.append(ersatz)
            continue
        for k in reversed(gewaehlt):
            rest = [x for x in gewaehlt if x != k]
            verloren = schemata_in(gewaehlt) - schemata_in(rest + [ersatz])
            if not verloren:
                gewaehlt = rest + [ersatz]
                break
    # Dedupe-Opfer (zuordnung != p) sind raus. Je (Kombination, Blende) bleibt
    # der beste Vertreter; liegen zwei Vertreter verschiedener Hauptschemata auf
    # demselben Punkt, werden ihre Schemata vereinigt (kein Kandidat geht verloren).
    ergebnis = [p for p in paare if zuordnung[id(p)] is p and (p.t_out, p.t_in) in gewaehlt]
    je_punkt: dict[tuple[float, float, int], PairCandidate] = {}
    for p in sorted(ergebnis, key=_sortschluessel):
        k = (p.t_out, p.t_in, p.blend_bars)
        if k in je_punkt:
            ziel = je_punkt[k]
            for s in p.out_a.schema:
                if s not in ziel.out_a.schema:
                    ziel.out_a.schema.append(s)
            for s in p.in_b.schema:
                if s not in ziel.in_b.schema:
                    ziel.in_b.schema.append(s)
            continue
        je_punkt[k] = p
    return list(je_punkt.values())


def build_pair_candidates(track_a: Track, track_b: Track, *, energy_direction=None,
                          harmonic_strictness: int = 7, allow_experimental: bool = True,
                          tolerances: dict | None = None) -> list[PairCandidate]:
    """Schritte 1–5 der Spec: Gates, Score, Blendenlaengen, Dedupe/Kappung,
    Rang + Begruendung. Liefert [] wenn keine Kombination die Gates besteht."""
    outs = [MixCandidate.from_dict(d) if isinstance(d, dict) else d for d in (track_a.mix_out_candidates or [])]
    ins = [MixCandidate.from_dict(d) if isinstance(d, dict) else d for d in (track_b.mix_in_candidates or [])]
    if not outs or not ins:
        return []
    _, rel = effective_bpm_diff(track_a.bpm, track_b.bpm)
    spb = seconds_per_bar(track_a.bpm)
    schemata_vorhanden: set[str] = set()
    for c in outs + ins:
        schemata_vorhanden.update(c.schema or [])
    paare: list[PairCandidate] = []
    for o in outs:
        for i in ins:
            for bars in blend_bars_options(track_a, o, rel):
                if pair_gate_reasons(track_a, track_b, o, i, bars):
                    continue
                score, teil, flags = score_pair(
                    track_a, track_b, o, i, bars, energy_direction=energy_direction,
                    harmonic_strictness=harmonic_strictness,
                    allow_experimental=allow_experimental, tolerances=tolerances)
                paare.append(PairCandidate(
                    out_a=MixCandidate.from_dict(o.to_dict()), in_b=MixCandidate.from_dict(i.to_dict()),
                    blend_bars=bars, overlap_sec=bars * spb, score=score, teilwerte=teil,
                    flags=flags, begruendung=begruendung_aus_teilwerten(teil, flags, bars),
                    bpm_relation=rel))
    if not paare:
        return []
    final = dedupe_and_cap(paare, _grid_sec(track_a), _grid_sec(track_b), schemata_vorhanden)
    for rang, p in enumerate(final, start=1):
        p.rang = rang
    return final
```

- [ ] **Step 4: Run → PASS** `.\venv312\Scripts\python.exe -m pytest tests/test_pair_candidates.py -q --no-cov`
- [ ] **Step 5: Commit** `git add hpg_core/pair_candidates.py tests/test_pair_candidates.py && git commit -m "feat(paare): Dedupe/Kappung, Schema-Garantie, Rang, Begruendung, build_pair_candidates"`

---

### Task 7: Werkzeug `tools/paar_kandidaten_messen.py`

**Files:**
- Create: `tools/paar_kandidaten_messen.py`
- Test: `tests/test_tools_paar_kandidaten_messen.py`

- [ ] **Step 1: Failing test**

```python
"""Tests fuer tools/paar_kandidaten_messen.py (reine Zusammenfassung)."""
import importlib.util
import os
import sys

import pytest

_PFAD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "paar_kandidaten_messen.py")
spec = importlib.util.spec_from_file_location("paar_kandidaten_messen", _PFAD)
pkm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkm)


def test_zusammenfassung_zaehlt_paare_gates_und_raenge():
    ergebnisse = [
        {"paar": ("a", "b"), "anzahl": 4, "gate_gruende": {}, "rang1_schema_out": "pssi_phrase",
         "rang1_schema_in": "auto_cue", "rang1_score": 0.8, "blenden": [16, 32]},
        {"paar": ("a", "c"), "anzahl": 0, "gate_gruende": {"bpm": 3, "gitter_out": 1},
         "rang1_schema_out": "", "rang1_schema_in": "", "rang1_score": None, "blenden": []},
    ]
    z = pkm.zusammenfassung(ergebnisse)
    assert z["paare"] == 2 and z["paare_mit_kandidaten"] == 1
    assert z["gate_gruende"] == {"bpm": 3, "gitter_out": 1}
    assert z["rang1_schemata_out"] == {"pssi_phrase": 1}
    assert z["kandidaten_median"] == 4
    assert z["rang1_score_median"] == pytest.approx(0.8)
```

- [ ] **Step 2: Run → FAIL** (Datei fehlt)

- [ ] **Step 3: Werkzeug**

```python
"""Paar-Kandidaten-Regressionsmessung: liest alle Tracks aus dem Cache, bildet
alle Paare innerhalb des BPM-Gates (PAAR_BPM_MAX) und berichtet je Paar die
Zahl der PairCandidates, Gate-Ausfaelle je Grund, Rang-1-Schemata und Scores.
Aufruf:
  python tools/paar_kandidaten_messen.py --cache [--json out.json] [--max-paare N]
"""
import argparse, itertools, json, os, sqlite3, statistics, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hpg_core.config import PAAR_BPM_MAX
from hpg_core.models import effective_bpm_diff


def zusammenfassung(ergebnisse: list[dict]) -> dict:
    med = lambda xs: statistics.median(xs) if xs else 0
    gruende = Counter()
    for e in ergebnisse:
        gruende.update(e.get("gate_gruende", {}))
    mit = [e for e in ergebnisse if e.get("anzahl", 0) > 0]
    return {
        "paare": len(ergebnisse),
        "paare_mit_kandidaten": len(mit),
        "kandidaten_median": med([e["anzahl"] for e in mit]),
        "gate_gruende": dict(gruende),
        "rang1_schemata_out": dict(Counter(e["rang1_schema_out"] for e in mit if e.get("rang1_schema_out"))),
        "rang1_schemata_in": dict(Counter(e["rang1_schema_in"] for e in mit if e.get("rang1_schema_in"))),
        "rang1_score_median": med([e["rang1_score"] for e in mit if e.get("rang1_score") is not None]),
        "blenden": dict(Counter(b for e in mit for b in e.get("blenden", []))),
    }


def _lade_tracks() -> list:
    from hpg_core import caching
    pfad = caching.CACHE_FILE
    if not os.path.exists(pfad):
        print(f"Cache-Datei nicht gefunden: {pfad}", file=sys.stderr)
        return []
    tracks = []
    conn = sqlite3.connect(pfad)
    try:
        for (row,) in conn.execute("SELECT data FROM cache WHERE key <> 'version'"):
            tracks.append(caching.dict_to_track(json.loads(row)))
    except sqlite3.OperationalError as exc:
        print(f"Cache nicht lesbar: {exc}", file=sys.stderr)
    finally:
        conn.close()
    return tracks


def _hauptschema(cand) -> str:
    from hpg_core.mix_candidates import SCHEMA_PRIORITAET
    s = [x for x in cand.schema if x in SCHEMA_PRIORITAET]
    return min(s, key=SCHEMA_PRIORITAET.index) if s else ""


def messe(tracks: list, max_paare: int | None = None) -> list[dict]:
    from hpg_core.mix_candidates import MixCandidate
    from hpg_core.pair_candidates import blend_bars_options, build_pair_candidates, pair_gate_reasons
    ergebnisse = []
    for a, b in itertools.permutations(tracks, 2):
        diff, rel = effective_bpm_diff(a.bpm, b.bpm)
        if diff > PAAR_BPM_MAX:
            continue
        gruende = Counter()
        outs = [MixCandidate.from_dict(d) for d in a.mix_out_candidates]
        ins = [MixCandidate.from_dict(d) for d in b.mix_in_candidates]
        for o in outs:
            for i in ins:
                for bars in blend_bars_options(a, o, rel):
                    for g in pair_gate_reasons(a, b, o, i, bars):
                        gruende[g] += 1
        res = build_pair_candidates(a, b)
        ergebnisse.append({
            "paar": (a.filePath, b.filePath), "anzahl": len(res), "gate_gruende": dict(gruende),
            "rang1_schema_out": _hauptschema(res[0].out_a) if res else "",
            "rang1_schema_in": _hauptschema(res[0].in_b) if res else "",
            "rang1_score": res[0].score if res else None,
            "blenden": [p.blend_bars for p in res],
        })
        if max_paare is not None and len(ergebnisse) >= max_paare:
            break
    return ergebnisse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="Tracks aus dem Cache lesen (Pflicht)")
    ap.add_argument("--json", help="Ergebnis als JSON schreiben")
    ap.add_argument("--max-paare", type=int, default=None)
    a = ap.parse_args()
    if not a.cache:
        ap.error("--cache angeben")
    tracks = _lade_tracks()
    if not tracks:
        return 1
    ergebnisse = messe(tracks, a.max_paare)
    z = zusammenfassung(ergebnisse)
    print(json.dumps(z, indent=2, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"zusammenfassung": z, "paare": ergebnisse}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Deserialisierer: `caching.dict_to_track` (`caching.py:351`, verifiziert 2026-08-22).

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add tools/paar_kandidaten_messen.py tests/test_tools_paar_kandidaten_messen.py && git commit -m "tools: paar_kandidaten_messen (Paare im BPM-Gate, Gate-Gruende, Rang-1-Schemata)"`

---

### Task 8: Messung, Doku, Waechter Tor 2, Merge

- [ ] **Step 1: Messung** `.\venv312\Scripts\python.exe tools/paar_kandidaten_messen.py --json-tracks <scratchpad>\kandidaten_v34.json --json <scratchpad>\paare_v34.json` — die 231 Tracks der Messung vom 2026-08-22 liegen als Track-Dicts in der `kandidaten_messen.py --json`-Ausgabe (`analyze_track` dort schreibt NICHT in den Cache; deshalb hat das Werkzeug neben `--cache` die Option `--json-tracks`, Umsetzung 2026-08-22). Pflichtzahlen: `paare`, `paare_mit_kandidaten`, `kandidaten_median`, `gate_gruende`, `rang1_schemata_out/in`, `rang1_score_median`, `blenden`.
- [ ] **Step 2: Volle Suite** `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q` — gruen inkl. Coverage-Gate 70.
- [ ] **Step 3: Doku**: `CLAUDE.md` (Baumliste: `pair_candidates.py`, `tools/paar_kandidaten_messen.py`), `.agents/skills/hpg-mixpoint-engineering/SKILL.md` + `.claude/...` (Abschnitt "Kandidaten Teil 2 (gebaut)": Gates, Faktoren, Gewichte, Flags, was Teil 4 bleibt), `.agents/skills/hpg-playlist-scoring/SKILL.md` (+ `.claude`): `camelot_relation_score` in `models.py`, `kandidaten_*_weight`; Handoff `docs/HANDOFF-<Datum>-kandidaten-teil2.md` mit den Messzahlen, den 11 Entscheidungen und diesen **offenen Folgeaufgaben fuer Teil 3/4** (Waechter Tor 1, Auflage 7 — nicht vergessen): (a) GUI-Regler `main.py:1562-1565` und Hoertest-Fit `tools/rate_transitions.py:513-530` schreiben nur die alten `*_weight` — `kandidaten_*_weight` muessen in Teil 3 (Fit) und Teil 4 (Regler "Lautheit") angebunden werden; (b) `KICK_KONFLIKT_ABZUG` entfaellt in Teil 4 bei Bass-Swap/EQ-Swap (Score wird uebergangstyp-abhaengig); (c) `blend_bars` ist kein Score-Merkmal (Docstring `score_pair`). Ausserdem: Pitch-Gate ist unter dem 2-BPM-Gate rechnerisch nie aktiv (Messung zeigt `pitch: 0`) — so im Handoff benennen.
- [ ] **Step 4: Waechter Tor 2** mit dem Gesamt-Diff gegen dieses Dokument; Auflagen einarbeiten.
- [ ] **Step 5: Commit + Merge** `git add -A docs CLAUDE.md .agents && git commit -m "docs: Kandidaten Teil 2 gebaut — Messung, Skills, Handoff"`; Merge auf `main` ueber superpowers:finishing-a-development-branch (Option 1), Push.

---

## Self-Review (Spec Abschnitt 2 gegen Tasks)

| Spec-Punkt | Task |
|---|---|
| BPM ≤ 2 effektiv, Half/Double Cut ≤ 16, Penalty 0.85 | 1, 4 (Gate/Blende), 5 (Penalty) |
| Pitch ≤ 4 % | 1, 4 |
| `out_A + overlap ≤ outro_start_A`, `in_B ≥ intro_end_B` | 4 |
| Coverage (`unanalysed`, `outro_covered`) | 4 |
| Ausnahme benannter IN/OUT-Cue (MIX IN/IN/START, OUT) schlaegt Punkt- und Blenden-Guard (Spec Abschnitt 1 Z. 77) | 4 (`_guard_frei`) |
| Blende mindestens `MIN_TRANSITION_BARS` (Projektkonstante) | 4 |
| Gitter (PSSI/Phrasen, 0.05 s) | 4 |
| Harmonie (Camelot lokal × key_confidence) | 3, 5 |
| BPM exp(−diff/1.0) | 1, 5 |
| Energie Richtung + `energy_trend` | 5 |
| Genre (Unknown ×0.5) | 5 |
| Groove 0.6/0.4, Syncopation-Delta, percussive > 0.7 Abzug / < 0.3 lange Blende | 1, 5 |
| Bass 0.6 sub + 0.4 punch, `bass_rms_dbfs`-Delta, nie zwei Kicks (Flag + Abzug) | 1, 5 |
| Klangfarbe cos + Mitten/Hoehen-Delta | 1, 5 |
| Stimmung brightness/flatness, Dur/Moll −0.15, PSSI-mood | 5 |
| Lautheit neu (0 dB → 1, ≥ 3 dB → 0) | 1, 5 |
| Struktur neu (neuheit, traegt_allein, Label-Paar) | 1, 5 |
| Vocals −0.06 additiv | 5 |
| Gewichte Startwerte, Summe 1.0, je Genre, JSON-Override, Umverteilung | 2, 5 |
| Blendenlaengen `transition_bars[0]/[1]`, Outro-Deckel, eigene PairCandidates | 4, 6 |
| Dedupe < 1 Phrase + gleiches Schema, max 6 × 2, je Schema ≥ 1 | 6 |
| Ausgabe Rang, Score, Teilwerte, Begruendung aus Teilwerten | 6 |
| Messung vor/nach | 7, 8 |

Placeholder-Scan: keine TBD/TODO. Typen: `score_pair -> (float, dict, dict)`, `pair_gate_reasons -> list[str]`, `blend_bars_options -> list[int]`, `build_pair_candidates -> list[PairCandidate]` durchgaengig; `PairCandidate.teilwerte` Schluessel = `FAKTOREN`; Flags `half_double`, `bass_swap_pflicht`, `lange_blende_erlaubt`, `benannter_cue`.
