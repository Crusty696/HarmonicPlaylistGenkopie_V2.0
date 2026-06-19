# Mix-Point Intro/Outro Guard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mix-In/Mix-Out Punkte duerfen nie in Intro- oder Outro-Sektionen liegen. Gilt fuer alle Genres ohne Ausnahme.

**Architecture:** Entferne `mix_in_at_intro_start` aus allen Genre-Profilen. Ueberarbeite `_find_mix_in_point()` und `_find_mix_out_point()` um sektionsbasiert den optimalen Punkt NACH Intro / VOR Outro zu finden. Sichere den generischen Pfad in `analysis.py` mit `ceil()`/`floor()` ab. Fuege Validierungs-Guard als letzte Sicherheitsstufe ein.

**Tech Stack:** Python 3.12, pytest, librosa, numpy

**Spec:** `docs/superpowers/specs/2026-03-11-mix-point-intro-outro-guard-design.md`

---

## Chunk 1: Hilfsfunktionen und Guard

### Task 1: Hilfsfunktionen `_get_intro_end_from_sections` und `_get_outro_start_from_sections`

**Files:**
- Modify: `hpg_core/dj_brain.py`
- Test: `tests/test_dj_brain.py`

- [ ] **Step 1: Schreibe fehlschlagende Tests fuer die neuen Hilfsfunktionen**

In `tests/test_dj_brain.py` am Ende anfuegen:

```python
class TestIntroOutroSectionHelpers:
  """Tests fuer _get_intro_end_from_sections und _get_outro_start_from_sections."""

  def test_intro_end_standard_track(self):
    """Standard-Track: Intro endet bei 60s."""
    from hpg_core.dj_brain import _get_intro_end_from_sections
    sections = _standard_sections()
    assert _get_intro_end_from_sections(sections) == 60.0

  def test_intro_end_multi_intro(self):
    """Multi-Intro: Zwei Intro-Sektionen hintereinander."""
    from hpg_core.dj_brain import _get_intro_end_from_sections
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0},
      {"label": "intro", "start_time": 30.0, "end_time": 60.0},
      {"label": "build", "start_time": 60.0, "end_time": 90.0},
    ]
    assert _get_intro_end_from_sections(sections) == 60.0

  def test_intro_end_no_intro(self):
    """Kein Intro: Gibt 0.0 zurueck."""
    from hpg_core.dj_brain import _get_intro_end_from_sections
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 90.0},
      {"label": "outro", "start_time": 90.0, "end_time": 120.0},
    ]
    assert _get_intro_end_from_sections(sections) == 0.0

  def test_intro_end_empty_sections(self):
    """Leere Sektionen: Gibt 0.0 zurueck."""
    from hpg_core.dj_brain import _get_intro_end_from_sections
    assert _get_intro_end_from_sections([]) == 0.0

  def test_outro_start_standard_track(self):
    """Standard-Track: Outro startet bei 360s."""
    from hpg_core.dj_brain import _get_outro_start_from_sections
    sections = _standard_sections()
    assert _get_outro_start_from_sections(sections, 420.0) == 360.0

  def test_outro_start_multi_outro(self):
    """Multi-Outro: Zwei Outro-Sektionen am Ende."""
    from hpg_core.dj_brain import _get_outro_start_from_sections
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 200.0},
      {"label": "outro", "start_time": 200.0, "end_time": 250.0},
      {"label": "outro", "start_time": 250.0, "end_time": 300.0},
    ]
    assert _get_outro_start_from_sections(sections, 300.0) == 200.0

  def test_outro_start_no_outro(self):
    """Kein Outro: Gibt duration zurueck."""
    from hpg_core.dj_brain import _get_outro_start_from_sections
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0},
      {"label": "drop", "start_time": 30.0, "end_time": 300.0},
    ]
    assert _get_outro_start_from_sections(sections, 300.0) == 300.0

  def test_outro_start_empty_sections(self):
    """Leere Sektionen: Gibt duration zurueck."""
    from hpg_core.dj_brain import _get_outro_start_from_sections
    assert _get_outro_start_from_sections([], 300.0) == 300.0
```

- [ ] **Step 2: Tests ausfuehren - muessen fehlschlagen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestIntroOutroSectionHelpers -v --no-header --tb=short -p no:cacheprovider"`
Expected: ImportError oder AttributeError (Funktionen existieren noch nicht)

- [ ] **Step 3: Implementiere die Hilfsfunktionen**

In `hpg_core/dj_brain.py` nach `_get_intro_end()` (Zeile ~577) einfuegen:

```python
def _get_intro_end_from_sections(sections: list[dict]) -> float:
  """Ende aller zusammenhaengenden Intro-Sektionen am Track-Anfang.

  Gibt 0.0 zurueck wenn kein Intro erkannt wurde.
  """
  if not sections:
    return 0.0

  last_intro_end = 0.0
  for section in sections:
    if section.get("label", "main") == "intro":
      last_intro_end = section.get("end_time", section.get("start_time", 0.0))
    else:
      if last_intro_end > 0.0:
        break

  return last_intro_end


def _get_outro_start_from_sections(sections: list[dict], duration: float) -> float:
  """Start aller zusammenhaengenden Outro-Sektionen am Track-Ende.

  Gibt duration zurueck wenn kein Outro erkannt wurde.
  """
  if not sections:
    return duration

  # Von hinten nach vorne suchen
  first_outro_start = duration
  found_outro = False
  for section in reversed(sections):
    if section.get("label", "main") == "outro":
      first_outro_start = section.get("start_time", duration)
      found_outro = True
    else:
      if found_outro:
        break

  return first_outro_start if found_outro else duration
```

- [ ] **Step 4: Export ergaenzen**

Die neuen Funktionen muessen im Import in `tests/test_dj_brain.py` sichtbar sein. Fuege in `tests/test_dj_brain.py` Zeile 26 die neuen Imports hinzu:

```python
  _get_intro_end_from_sections,
  _get_outro_start_from_sections,
```

Und entferne die lokalen `from hpg_core.dj_brain import` Zeilen aus den einzelnen Testmethoden.

- [ ] **Step 5: Tests ausfuehren - muessen passen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestIntroOutroSectionHelpers -v --no-header --tb=short -p no:cacheprovider"`
Expected: 8 PASSED

- [ ] **Step 6: Commit**

```bash
git add hpg_core/dj_brain.py tests/test_dj_brain.py
git commit -m "feat: add _get_intro_end_from_sections and _get_outro_start_from_sections helpers"
```

---

### Task 2: `mix_in_at_intro_start` entfernen

**Files:**
- Modify: `hpg_core/dj_brain.py:38,50,111,301,614`
- Test: `tests/test_dj_brain.py`

- [ ] **Step 1: Schreibe Test der bestätigt dass mix_in_at_intro_start nicht mehr existiert**

In `tests/test_dj_brain.py` anfuegen:

```python
class TestMixInAtIntroStartRemoved:
  """Bestätigt dass mix_in_at_intro_start entfernt wurde."""

  def test_psytrance_no_mix_in_at_intro_start(self):
    """Psytrance hat kein mix_in_at_intro_start mehr."""
    p = GENRE_MIX_PROFILES["Psytrance"]
    assert not hasattr(p, "mix_in_at_intro_start")

  def test_trance_no_mix_in_at_intro_start(self):
    """Trance hat kein mix_in_at_intro_start mehr."""
    p = GENRE_MIX_PROFILES["Trance"]
    assert not hasattr(p, "mix_in_at_intro_start")

  def test_default_no_mix_in_at_intro_start(self):
    """Default-Profil hat kein mix_in_at_intro_start mehr."""
    assert not hasattr(DEFAULT_MIX_PROFILE, "mix_in_at_intro_start")
```

- [ ] **Step 2: Tests ausfuehren - muessen fehlschlagen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestMixInAtIntroStartRemoved -v --no-header --tb=short -p no:cacheprovider"`
Expected: FAIL (Attribute existiert noch)

- [ ] **Step 3: Entferne `mix_in_at_intro_start` aus dem Dataclass und allen Profilen**

In `hpg_core/dj_brain.py`:

1. **Zeile 35-38**: Entferne das Feld `mix_in_at_intro_start` aus `GenreMixProfile`
2. **Zeile 50**: Entferne `mix_in_at_intro_start=True` aus Psytrance-Profil
3. **Zeile 111**: Entferne `mix_in_at_intro_start=True` aus Trance-Profil
4. **Zeile 301**: Aendere `min_mix_in = 0.0 if profile.mix_in_at_intro_start else seconds_per_bar * 8` zu:
   ```python
   # Minimum Mix-In: nach dem Intro (wird spaeter durch Sektions-Guard garantiert)
   min_mix_in = seconds_per_bar * 8
   ```
5. **Zeile 614**: Aendere `if not profile_b.mix_in_at_intro_start:` Block in `calculate_paired_mix_points()`:
   ```python
   # Paired Mix Points fuer alle Genres berechnen (kein mix_in_at_intro_start mehr)
   ```
   Entferne den `if not profile_b.mix_in_at_intro_start: return ...` Early-Return.

- [ ] **Step 4: Tests ausfuehren - neue Tests muessen passen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestMixInAtIntroStartRemoved -v --no-header --tb=short -p no:cacheprovider"`
Expected: 3 PASSED

- [ ] **Step 5: Alle DJ Brain Tests ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py -v --no-header --tb=short -p no:cacheprovider"`
Expected: Einige Tests koennten fehlschlagen wenn sie `mix_in_at_intro_start` referenzieren. Diese werden in Step 6 repariert.

- [ ] **Step 6: Bestehende Tests reparieren die `mix_in_at_intro_start` referenzieren**

Suche in `tests/test_dj_brain.py` nach allen Referenzen auf `mix_in_at_intro_start` und entferne/ersetze sie. Typisch:
- Tests die `p.mix_in_at_intro_start == True` pruefen -> entfernen
- Tests die Mix-In bei 0.0 fuer Psytrance erwarten -> anpassen auf >= intro_end

- [ ] **Step 7: Alle DJ Brain Tests nochmal ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py -v --no-header --tb=short -p no:cacheprovider"`
Expected: Alle PASSED

- [ ] **Step 8: Commit**

```bash
git add hpg_core/dj_brain.py tests/test_dj_brain.py
git commit -m "refactor: remove mix_in_at_intro_start from all genre profiles"
```

---

## Chunk 2: Mix-Point-Logik ueberarbeiten

### Task 3: `_find_mix_in_point()` ueberarbeiten

**Files:**
- Modify: `hpg_core/dj_brain.py:317-376`
- Test: `tests/test_dj_brain.py`

- [ ] **Step 1: Schreibe fehlschlagende Tests**

In `tests/test_dj_brain.py` anfuegen:

```python
class TestMixInNeverInIntro:
  """Mix-In darf NIEMALS in einer Intro-Sektion liegen."""

  def test_standard_track_mix_in_after_intro(self):
    """Standard-Track: Mix-In >= 60s (Intro endet bei 60s)."""
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4  # seconds_per_bar
    mix_in = _find_mix_in_point(sections, profile, spb)
    assert mix_in >= 60.0, f"Mix-In {mix_in}s liegt im Intro (endet bei 60s)"

  def test_trance_track_mix_in_after_intro(self):
    """Trance: Mix-In nach Intro, nicht bei 0.0."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 53.0, "start_bar": 0, "end_bar": 32, "avg_energy": 20.0},
      {"label": "build", "start_time": 53.0, "end_time": 106.0, "start_bar": 32, "end_bar": 64, "avg_energy": 55.0},
      {"label": "drop", "start_time": 106.0, "end_time": 300.0, "start_bar": 64, "end_bar": 180, "avg_energy": 85.0},
      {"label": "outro", "start_time": 300.0, "end_time": 360.0, "start_bar": 180, "end_bar": 216, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Trance")
    spb = (60.0 / 138.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    assert mix_in >= 53.0, f"Mix-In {mix_in}s liegt im Intro (endet bei 53s)"

  def test_no_intro_track(self):
    """Track ohne Intro: Mix-In kann bei 0.0 sein."""
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 200.0, "start_bar": 0, "end_bar": 100, "avg_energy": 85.0},
      {"label": "outro", "start_time": 200.0, "end_time": 300.0, "start_bar": 100, "end_bar": 150, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Techno")
    spb = (60.0 / 130.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    assert mix_in >= 0.0  # Kein Intro = alles erlaubt
    assert mix_in < 200.0  # Aber nicht im Outro

  def test_multi_intro_mix_in_after_all(self):
    """Multi-Intro: Mix-In nach ALLEN Intro-Sektionen."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "start_bar": 0, "end_bar": 16, "avg_energy": 15.0},
      {"label": "intro", "start_time": 30.0, "end_time": 60.0, "start_bar": 16, "end_bar": 32, "avg_energy": 25.0},
      {"label": "build", "start_time": 60.0, "end_time": 90.0, "start_bar": 32, "end_bar": 48, "avg_energy": 55.0},
      {"label": "drop", "start_time": 90.0, "end_time": 250.0, "start_bar": 48, "end_bar": 133, "avg_energy": 85.0},
      {"label": "outro", "start_time": 250.0, "end_time": 300.0, "start_bar": 133, "end_bar": 160, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Deep House")
    spb = (60.0 / 124.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    assert mix_in >= 60.0, f"Mix-In {mix_in}s liegt im Intro (endet bei 60s)"

  def test_mix_in_prefers_build_over_drop(self):
    """Mix-In bevorzugt Build-Sektionen als Einstieg (energetisch sinnvoller)."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 60.0, "start_bar": 0, "end_bar": 32, "avg_energy": 20.0},
      {"label": "build", "start_time": 60.0, "end_time": 90.0, "start_bar": 32, "end_bar": 48, "avg_energy": 55.0},
      {"label": "drop", "start_time": 90.0, "end_time": 200.0, "start_bar": 48, "end_bar": 107, "avg_energy": 85.0},
      {"label": "outro", "start_time": 200.0, "end_time": 300.0, "start_bar": 107, "end_bar": 160, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Tech House")
    spb = (60.0 / 128.0) * 4
    mix_in = _find_mix_in_point(sections, profile, spb)
    # Sollte beim Build einsteigen (60s), nicht erst beim Drop (90s)
    assert 60.0 <= mix_in <= 90.0, f"Mix-In {mix_in}s nicht im Build-Bereich (60-90s)"
```

- [ ] **Step 2: Tests ausfuehren - muessen fehlschlagen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestMixInNeverInIntro -v --no-header --tb=short -p no:cacheprovider"`
Expected: Mindestens `test_standard_track_mix_in_after_intro` und `test_trance_track_mix_in_after_intro` schlagen fehl

- [ ] **Step 3: Implementiere die neue `_find_mix_in_point()`**

Ersetze `_find_mix_in_point()` in `hpg_core/dj_brain.py` (Zeilen 317-376) komplett:

```python
def _find_mix_in_point(
  sections: list[dict],
  profile: GenreMixProfile,
  seconds_per_bar: float,
) -> float:
  """
  ADAPTIVES MIX-IN: Sucht den musikalisch sinnvollsten Einstiegspunkt.

  REGEL: Mix-In NIEMALS in einer Intro-Sektion.

  Strategie:
  1. Bestimme Intro-Ende aus Sektionen
  2. Suche die beste Sektion nach dem Intro (bevorzugt: build > main > drop)
  3. Quantisiere auf Phrasen-Grenze
  """
  if not sections:
    return 0.0

  # --- Intro-Ende bestimmen ---
  intro_end = _get_intro_end_from_sections(sections)

  # --- Energetischen Kontext berechnen ---
  all_energies = [s.get("avg_energy", 50.0) for s in sections]
  avg_energy = sum(all_energies) / len(all_energies) if all_energies else 50.0

  # --- Kandidaten: Sektionen nach Intro, nicht Outro ---
  candidates = [
    s for s in sections
    if s.get("start_time", 0.0) >= intro_end
    and s.get("label", "main") not in ("intro", "outro")
  ]

  if not candidates:
    # Kein nutzbarer Bereich nach Intro gefunden
    # Fallback: direkt nach Intro-Ende, phrase-aligned
    phrase_seconds = seconds_per_bar * profile.phrase_unit
    if phrase_seconds > 0:
      return max(intro_end, round(intro_end / phrase_seconds) * phrase_seconds)
    return intro_end

  # --- Beste Sektion waehlen ---
  # Praeferenz-Reihenfolge fuer Mix-In:
  # 1. "build" (DJ steigt ein waehrend Energie aufgebaut wird)
  # 2. "main" (stabiler Bereich)
  # 3. "breakdown" (ruhiger Moment)
  # 4. "drop" (letzter Ausweg, aber energetisch hoch)
  label_priority = {"build": 0, "main": 1, "breakdown": 2, "drop": 3}

  best = min(candidates, key=lambda s: (
    label_priority.get(s.get("label", "main"), 99),
    abs(s.get("avg_energy", 50.0) - avg_energy * 0.7),  # Naehe zu 70% Durchschnittsenergie
  ))

  mix_in = best.get("start_time", intro_end)

  # --- Quantisierung auf Phrasen-Grenze ---
  phrase_seconds = seconds_per_bar * profile.phrase_unit
  if phrase_seconds > 0:
    mix_in = round(mix_in / phrase_seconds) * phrase_seconds

  # --- Guard: NIEMALS vor Intro-Ende ---
  mix_in = max(mix_in, intro_end)

  return mix_in
```

- [ ] **Step 4: Tests ausfuehren - muessen passen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestMixInNeverInIntro -v --no-header --tb=short -p no:cacheprovider"`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add hpg_core/dj_brain.py tests/test_dj_brain.py
git commit -m "feat: _find_mix_in_point never returns a point in intro sections"
```

---

### Task 4: `_find_mix_out_point()` ueberarbeiten

**Files:**
- Modify: `hpg_core/dj_brain.py:379-401`
- Test: `tests/test_dj_brain.py`

- [ ] **Step 1: Schreibe fehlschlagende Tests**

In `tests/test_dj_brain.py` anfuegen:

```python
class TestMixOutNeverInOutro:
  """Mix-Out darf NIEMALS in einer Outro-Sektion liegen."""

  def test_standard_track_mix_out_before_outro(self):
    """Standard-Track: Mix-Out < 360s (Outro startet bei 360s)."""
    sections = _standard_sections()
    profile = get_mix_profile("Psytrance")
    spb = (60.0 / 140.0) * 4
    mix_out = _find_mix_out_point(sections, profile, spb, 420.0)
    assert mix_out < 360.0, f"Mix-Out {mix_out}s liegt im Outro (startet bei 360s)"

  def test_multi_outro_mix_out_before_first(self):
    """Multi-Outro: Mix-Out vor der ERSTEN Outro-Sektion."""
    sections = [
      {"label": "drop", "start_time": 0.0, "end_time": 200.0, "start_bar": 0, "end_bar": 100, "avg_energy": 85.0},
      {"label": "main", "start_time": 200.0, "end_time": 250.0, "start_bar": 100, "end_bar": 125, "avg_energy": 60.0},
      {"label": "outro", "start_time": 250.0, "end_time": 275.0, "start_bar": 125, "end_bar": 138, "avg_energy": 30.0},
      {"label": "outro", "start_time": 275.0, "end_time": 300.0, "start_bar": 138, "end_bar": 150, "avg_energy": 15.0},
    ]
    profile = get_mix_profile("Techno")
    spb = (60.0 / 130.0) * 4
    mix_out = _find_mix_out_point(sections, profile, spb, 300.0)
    assert mix_out < 250.0, f"Mix-Out {mix_out}s liegt im Outro (startet bei 250s)"

  def test_no_outro_track(self):
    """Track ohne Outro: Mix-Out basierend auf Genre-Profil."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "start_bar": 0, "end_bar": 16, "avg_energy": 20.0},
      {"label": "drop", "start_time": 30.0, "end_time": 300.0, "start_bar": 16, "end_bar": 160, "avg_energy": 85.0},
    ]
    profile = get_mix_profile("Drum & Bass")
    spb = (60.0 / 174.0) * 4
    mix_out = _find_mix_out_point(sections, profile, spb, 300.0)
    assert mix_out > 0.0
    assert mix_out <= 300.0

  def test_mix_out_at_end_of_last_strong_section(self):
    """Mix-Out soll am Ende der letzten starken Sektion vor Outro liegen."""
    sections = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "start_bar": 0, "end_bar": 16, "avg_energy": 20.0},
      {"label": "drop", "start_time": 30.0, "end_time": 200.0, "start_bar": 16, "end_bar": 107, "avg_energy": 85.0},
      {"label": "breakdown", "start_time": 200.0, "end_time": 240.0, "start_bar": 107, "end_bar": 128, "avg_energy": 40.0},
      {"label": "outro", "start_time": 240.0, "end_time": 300.0, "start_bar": 128, "end_bar": 160, "avg_energy": 20.0},
    ]
    profile = get_mix_profile("Progressive")
    spb = (60.0 / 128.0) * 4
    mix_out = _find_mix_out_point(sections, profile, spb, 300.0)
    # Sollte im Bereich der letzten Nicht-Outro-Sektion liegen (breakdown endet bei 240s)
    assert mix_out < 240.0, f"Mix-Out {mix_out}s im Outro-Bereich"
    assert mix_out > 30.0, f"Mix-Out {mix_out}s zu frueh"
```

- [ ] **Step 2: Tests ausfuehren - muessen fehlschlagen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestMixOutNeverInOutro -v --no-header --tb=short -p no:cacheprovider"`
Expected: Mindestens `test_standard_track_mix_out_before_outro` schlaegt fehl

- [ ] **Step 3: Implementiere die neue `_find_mix_out_point()`**

Ersetze `_find_mix_out_point()` in `hpg_core/dj_brain.py` (Zeilen 379-401) komplett:

```python
def _find_mix_out_point(
  sections: list[dict],
  profile: GenreMixProfile,
  seconds_per_bar: float,
  duration: float,
) -> float:
  """
  ADAPTIVES MIX-OUT: Findet den optimalen Ausstiegspunkt.

  REGEL: Mix-Out NIEMALS in einer Outro-Sektion.

  Strategie:
  1. Bestimme Outro-Start aus Sektionen
  2. Suche die letzte starke Sektion VOR dem Outro
  3. Setze Mix-Out an deren Ende, quantisiert auf Phrasen-Grenze
  """
  if not sections:
    # Fallback Genre-Profil
    avg_outro_bars = (profile.outro_bars[0] + profile.outro_bars[1]) / 2.0
    return duration - (avg_outro_bars * seconds_per_bar)

  # --- Outro-Start bestimmen ---
  outro_start = _get_outro_start_from_sections(sections, duration)

  # --- Kandidaten: Sektionen vor Outro, nicht Intro ---
  candidates = [
    s for s in sections
    if s.get("end_time", 0.0) <= outro_start
    and s.get("label", "main") not in ("intro", "outro")
  ]

  if not candidates:
    # Kein nutzbarer Bereich vor Outro
    phrase_seconds = seconds_per_bar * profile.phrase_unit
    if phrase_seconds > 0:
      mix_out = (outro_start // phrase_seconds) * phrase_seconds
      return max(0.0, min(mix_out, outro_start))
    return outro_start

  # --- Letzte starke Sektion VOR Outro waehlen ---
  # Das Ende der letzten "drop", "main", oder "breakdown" Sektion
  last_strong = candidates[-1]
  mix_out = last_strong.get("end_time", outro_start)

  # --- Quantisierung auf Phrasen-Grenze ---
  phrase_seconds = seconds_per_bar * profile.phrase_unit
  if phrase_seconds > 0:
    mix_out = (mix_out // phrase_seconds) * phrase_seconds

  # --- Guard: NIEMALS nach Outro-Start ---
  mix_out = min(mix_out, outro_start)

  # Sicherheit: nicht negativ
  return max(0.0, mix_out)
```

- [ ] **Step 4: Tests ausfuehren - muessen passen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestMixOutNeverInOutro -v --no-header --tb=short -p no:cacheprovider"`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add hpg_core/dj_brain.py tests/test_dj_brain.py
git commit -m "feat: _find_mix_out_point never returns a point in outro sections"
```

---

### Task 5: `calculate_genre_aware_mix_points()` Sicherheitsgrenzen anpassen

**Files:**
- Modify: `hpg_core/dj_brain.py:267-314`
- Test: `tests/test_dj_brain.py`

- [ ] **Step 1: Schreibe fehlschlagende Tests**

In `tests/test_dj_brain.py` anfuegen:

```python
class TestGenreAwareMixPointsGuard:
  """calculate_genre_aware_mix_points respektiert Intro/Outro-Grenzen."""

  @pytest.mark.parametrize("genre", [
    "Psytrance", "Trance", "Tech House", "Techno",
    "Deep House", "Progressive", "Melodic Techno",
    "Drum & Bass", "Minimal",
  ])
  def test_mix_in_after_intro_all_genres(self, genre):
    """Mix-In nach Intro fuer alle Genres."""
    sections = _standard_sections()  # Intro endet bei 60.0
    bpm = 140.0 if genre in ("Psytrance", "Trance") else 128.0
    mi, mo, _, _ = calculate_genre_aware_mix_points(sections, bpm, 420.0, genre)
    assert mi >= 60.0, f"{genre}: Mix-In {mi}s im Intro (endet bei 60s)"

  @pytest.mark.parametrize("genre", [
    "Psytrance", "Trance", "Tech House", "Techno",
    "Deep House", "Progressive", "Melodic Techno",
    "Drum & Bass", "Minimal",
  ])
  def test_mix_out_before_outro_all_genres(self, genre):
    """Mix-Out vor Outro fuer alle Genres."""
    sections = _standard_sections()  # Outro startet bei 360.0
    bpm = 140.0 if genre in ("Psytrance", "Trance") else 128.0
    mi, mo, _, _ = calculate_genre_aware_mix_points(sections, bpm, 420.0, genre)
    assert mo < 360.0, f"{genre}: Mix-Out {mo}s im Outro (startet bei 360s)"

  def test_different_structures_different_points(self):
    """Verschiedene Track-Strukturen erzeugen verschiedene Mix-Punkte."""
    # Track A: langes Intro, kurzes Outro
    sections_a = [
      {"label": "intro", "start_time": 0.0, "end_time": 90.0, "start_bar": 0, "end_bar": 48, "avg_energy": 20.0},
      {"label": "drop", "start_time": 90.0, "end_time": 380.0, "start_bar": 48, "end_bar": 203, "avg_energy": 85.0},
      {"label": "outro", "start_time": 380.0, "end_time": 420.0, "start_bar": 203, "end_bar": 224, "avg_energy": 20.0},
    ]
    # Track B: kurzes Intro, langes Outro
    sections_b = [
      {"label": "intro", "start_time": 0.0, "end_time": 30.0, "start_bar": 0, "end_bar": 16, "avg_energy": 20.0},
      {"label": "drop", "start_time": 30.0, "end_time": 300.0, "start_bar": 16, "end_bar": 160, "avg_energy": 85.0},
      {"label": "outro", "start_time": 300.0, "end_time": 420.0, "start_bar": 160, "end_bar": 224, "avg_energy": 20.0},
    ]
    mi_a, mo_a, _, _ = calculate_genre_aware_mix_points(sections_a, 140.0, 420.0, "Techno")
    mi_b, mo_b, _, _ = calculate_genre_aware_mix_points(sections_b, 140.0, 420.0, "Techno")
    # Mix-Punkte muessen verschieden sein, weil Struktur verschieden
    assert mi_a != mi_b or mo_a != mo_b, "Verschiedene Strukturen haben gleiche Mix-Punkte!"
```

- [ ] **Step 2: Tests ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestGenreAwareMixPointsGuard -v --no-header --tb=short -p no:cacheprovider"`

- [ ] **Step 3: Passe `calculate_genre_aware_mix_points()` an**

In `hpg_core/dj_brain.py` Zeilen 267-314 die Sicherheitsgrenzen aendern:

```python
  # Sicherheitsgrenzen -- intro/outro-aware
  intro_end = _get_intro_end_from_sections(sections)
  outro_start = _get_outro_start_from_sections(sections, duration)

  min_mix_in = max(intro_end, seconds_per_bar * 4)
  mix_in_time = max(min_mix_in, min(mix_in_time, duration * 0.4))
  mix_out_time = min(outro_start, duration - seconds_per_bar * 4, max(mix_out_time, duration * 0.6))
```

- [ ] **Step 4: Tests ausfuehren - muessen passen**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestGenreAwareMixPointsGuard -v --no-header --tb=short -p no:cacheprovider"`
Expected: Alle PASSED (18 parametrierte + 1 Struktur-Test)

- [ ] **Step 5: Commit**

```bash
git add hpg_core/dj_brain.py tests/test_dj_brain.py
git commit -m "feat: calculate_genre_aware_mix_points enforces intro/outro boundaries"
```

---

## Chunk 3: Generischer Pfad und Paired Mix Points

### Task 6: `analysis.py` generischen Pfad absichern

**Files:**
- Modify: `hpg_core/analysis.py:635-665`
- Test: `tests/test_mix_points.py`, `tests/test_mix_points_root.py`

- [ ] **Step 1: Schreibe fehlschlagende Tests**

In `tests/test_mix_points.py` anfuegen:

```python
class TestMixInAfterIntro:
  """Mix-In muss nach dem erkannten Intro-Ende liegen."""

  @pytest.mark.slow
  def test_mix_in_not_at_intro_boundary(self):
    """Mix-In soll NACH intro_end_time liegen, nicht genau drauf."""
    from tests.fixtures.audio_generators import generate_track_with_structure, DEFAULT_SR
    bpm = 128.0
    duration = 300.0
    # Deutliches Intro: leise 15%, dann laut
    y = generate_track_with_structure(bpm, duration, DEFAULT_SR, intro_ratio=0.15, outro_ratio=0.85)
    mi, mo, _, _ = analyze_structure_and_mix_points(y, DEFAULT_SR, duration, 70, bpm)
    # intro_end ~ 15% = 45s. Mix-In muss > 45s sein (naechste Phrase-Grenze)
    seconds_per_phrase = (60.0 / bpm) * 4 * 8
    assert mi > duration * 0.14, f"Mix-In {mi}s zu nah am Intro-Anfang"
```

- [ ] **Step 2: Tests ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_mix_points.py::TestMixInAfterIntro -v --no-header --tb=short -p no:cacheprovider"`

- [ ] **Step 3: Aendere `analysis.py` - ceil statt round fuer Mix-In**

In `hpg_core/analysis.py` Zeile 635:
```python
# Alt:
intro_phrase_count = round(intro_end_time / seconds_per_phrase)
# Neu:
from math import ceil
intro_phrase_count = ceil(intro_end_time / seconds_per_phrase)
```

In `hpg_core/analysis.py` Zeile 645-653 - Mix-Out eine Phrase VOR outro_start:
```python
outro_phrase_index = floor(outro_start_time / seconds_per_phrase)
if outro_phrase_index >= floor(total_phrases) - 1:
    outro_phrase_index = max(1, floor(total_phrases) - 4)
# Sicherheit: mindestens 1 Phrase vor Outro-Start
if outro_phrase_index * seconds_per_phrase >= outro_start_time:
    outro_phrase_index = max(1, outro_phrase_index - 1)
```

- [ ] **Step 4: Alle Mix-Point-Tests ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_mix_points.py tests/test_mix_points_root.py -v --no-header --tb=short -p no:cacheprovider"`
Expected: Alle PASSED

- [ ] **Step 5: Commit**

```bash
git add hpg_core/analysis.py tests/test_mix_points.py
git commit -m "fix: analysis.py uses ceil for mix-in to place after intro end"
```

---

### Task 7: `calculate_paired_mix_points()` bereinigen

**Files:**
- Modify: `hpg_core/dj_brain.py:579-649`
- Test: `tests/test_dj_brain.py`

- [ ] **Step 1: Schreibe Tests**

In `tests/test_dj_brain.py` anfuegen:

```python
class TestPairedMixPointsAllGenres:
  """calculate_paired_mix_points arbeitet fuer alle Genres."""

  def test_paired_points_for_techno(self):
    """Techno-Paar bekommt angepasste Mix-Punkte."""
    a = _make_track(genre="Techno", bpm=130.0, duration=300.0, mix_out=250.0,
                    sections=[
                      {"label": "intro", "start_time": 0.0, "end_time": 30.0},
                      {"label": "drop", "start_time": 30.0, "end_time": 250.0},
                      {"label": "outro", "start_time": 250.0, "end_time": 300.0},
                    ])
    b = _make_track(genre="Techno", bpm=130.0, duration=300.0, mix_in=30.0,
                    sections=[
                      {"label": "intro", "start_time": 0.0, "end_time": 30.0},
                      {"label": "drop", "start_time": 30.0, "end_time": 250.0},
                      {"label": "outro", "start_time": 250.0, "end_time": 300.0},
                    ])
    mo_a, mi_b = calculate_paired_mix_points(a, b)
    assert mo_a >= 0.0
    assert mi_b >= 0.0
    assert mo_a <= a.duration
    assert mi_b <= b.duration

  def test_paired_points_for_psytrance(self):
    """Psytrance-Paar bekommt auch angepasste Mix-Punkte (nicht mehr Sonderbehandlung)."""
    a = _make_track(genre="Psytrance", bpm=140.0, duration=420.0, mix_out=360.0,
                    sections=[
                      {"label": "intro", "start_time": 0.0, "end_time": 60.0},
                      {"label": "drop", "start_time": 60.0, "end_time": 360.0},
                      {"label": "outro", "start_time": 360.0, "end_time": 420.0},
                    ])
    b = _make_track(genre="Psytrance", bpm=140.0, duration=420.0, mix_in=60.0,
                    sections=[
                      {"label": "intro", "start_time": 0.0, "end_time": 60.0},
                      {"label": "drop", "start_time": 60.0, "end_time": 360.0},
                      {"label": "outro", "start_time": 360.0, "end_time": 420.0},
                    ])
    mo_a, mi_b = calculate_paired_mix_points(a, b)
    assert mo_a >= 0.0
    assert mi_b >= 0.0
```

- [ ] **Step 2: Entferne den Early-Return in `calculate_paired_mix_points()`**

In `hpg_core/dj_brain.py` Zeile 614:
```python
# Alt:
if not profile_b.mix_in_at_intro_start:
    return track_a.mix_out_point, track_b.mix_in_point
# Entfernen: Diese Zeilen komplett loeschen
```

- [ ] **Step 3: Tests ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestPairedMixPointsAllGenres -v --no-header --tb=short -p no:cacheprovider"`
Expected: 2 PASSED

- [ ] **Step 4: Alle Tests ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/ -v --no-header --tb=short -p no:cacheprovider -x"`
Expected: Alle PASSED (ggf. Anpassungen noetig an bestehenden Tests die auf altes Verhalten pruefen)

- [ ] **Step 5: Commit**

```bash
git add hpg_core/dj_brain.py tests/test_dj_brain.py
git commit -m "refactor: calculate_paired_mix_points works for all genres equally"
```

---

## Chunk 4: Integration und Abschluss

### Task 8: Vollstaendiger Integrationstest

**Files:**
- Test: `tests/test_dj_brain.py`

- [ ] **Step 1: Schreibe umfassenden Integrationstest**

In `tests/test_dj_brain.py` anfuegen:

```python
class TestMixPointIntegration:
  """Ende-zu-Ende Tests: DJ Brain + Mix-Punkte + Empfehlungen."""

  def test_full_recommendation_respects_intro_outro(self):
    """generate_dj_recommendation nutzt Mix-Punkte die nicht in Intro/Outro liegen."""
    a = _make_track(
      genre="Psytrance", bpm=140.0, duration=420.0,
      mix_in=60.0, mix_out=350.0,
      sections=_standard_sections(),
    )
    b = _make_track(
      genre="Trance", bpm=138.0, duration=360.0,
      mix_in=53.0, mix_out=300.0,
      sections=[
        {"label": "intro", "start_time": 0.0, "end_time": 53.0, "start_bar": 0, "end_bar": 32, "avg_energy": 20.0},
        {"label": "build", "start_time": 53.0, "end_time": 106.0, "start_bar": 32, "end_bar": 64, "avg_energy": 55.0},
        {"label": "drop", "start_time": 106.0, "end_time": 300.0, "start_bar": 64, "end_bar": 180, "avg_energy": 85.0},
        {"label": "outro", "start_time": 300.0, "end_time": 360.0, "start_bar": 180, "end_bar": 216, "avg_energy": 20.0},
      ],
    )
    rec = generate_dj_recommendation(a, b)
    # Mix-Punkte in der Empfehlung duerfen nicht im Intro/Outro liegen
    if rec.adjusted_mix_in_b >= 0:
      assert rec.adjusted_mix_in_b >= 53.0 or rec.adjusted_mix_in_b == 0.0, \
        f"Adjusted Mix-In B ({rec.adjusted_mix_in_b}s) im Intro (endet bei 53s)"
    if rec.adjusted_mix_out_a >= 0:
      assert rec.adjusted_mix_out_a < 420.0, \
        f"Adjusted Mix-Out A ({rec.adjusted_mix_out_a}s) ausserhalb Track A"

  @pytest.mark.parametrize("genre_pair", [
    ("Psytrance", "Psytrance"),
    ("Trance", "Trance"),
    ("Tech House", "Techno"),
    ("Deep House", "Progressive"),
    ("Drum & Bass", "Drum & Bass"),
  ])
  def test_recommendations_for_all_genre_pairs(self, genre_pair):
    """DJ Empfehlungen fuer verschiedene Genre-Paare funktionieren."""
    g_a, g_b = genre_pair
    bpm_a = 140.0 if g_a in ("Psytrance", "Trance") else 128.0
    bpm_b = 140.0 if g_b in ("Psytrance", "Trance") else 128.0
    a = _make_track(genre=g_a, bpm=bpm_a, sections=_standard_sections())
    b = _make_track(genre=g_b, bpm=bpm_b, sections=_standard_sections())
    rec = generate_dj_recommendation(a, b)
    assert rec.genre_pair
    assert rec.mix_technique
    assert rec.transition_bars > 0
```

- [ ] **Step 2: Tests ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_dj_brain.py::TestMixPointIntegration -v --no-header --tb=short -p no:cacheprovider"`
Expected: Alle PASSED

- [ ] **Step 3: VOLLSTAENDIGE Test-Suite ausfuehren**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/ --tb=short -q -p no:cacheprovider"`
Expected: Alle Tests passen. Kaputte Tests reparieren falls noetig.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dj_brain.py
git commit -m "test: add integration tests for mix point intro/outro guard"
```

---

### Task 9: Aufraeumen und finaler Commit

- [ ] **Step 1: Pruefe ob alle Referenzen auf `mix_in_at_intro_start` entfernt sind**

Run: `grep -rn "mix_in_at_intro_start" hpg_core/ tests/`
Expected: Keine Treffer

- [ ] **Step 2: Vollstaendige Test-Suite mit Coverage**

Run: `powershell -Command "Set-Location 'C:\Users\david\Dokumente\HarmonicPlaylistGenkopie_V2.0-main'; & 'C:\Users\david\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/ --tb=short -q --cov=hpg_core --cov-report=term-missing -p no:cacheprovider"`
Expected: Coverage >= 70%, alle Tests PASSED

- [ ] **Step 3: Finaler Commit falls Aufraeum-Aenderungen**

```bash
git add -A
git commit -m "chore: cleanup mix_in_at_intro_start references"
```
