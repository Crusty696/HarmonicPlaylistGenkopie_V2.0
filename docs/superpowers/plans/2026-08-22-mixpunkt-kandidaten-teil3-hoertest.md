# Mixpunkt-Kandidaten Teil 3 (Hoertest: Kandidaten vergleichen) — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Hoertest bekommt einen Modus "Kandidaten": je Trackpaar werden alle `PairCandidate`s (Teil 2) als Clips gerendert, verdeckt je Paar auf einer Seite in zufaelliger (gespeicherter) Reihenfolge bewertet (Note 1–5 je Kandidat + Wahl "bester"), und `fit --modus kandidaten` schaetzt daraus Gewichte fuer Abschnitt 2 und eine Schema-Rangfolge je Genre nach `hpg_core/data/candidate_preferences.json` — mit Holdout nach Tracks und AUC/Trefferquote im Bericht. Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`, Abschnitt 3 (Z. 143–177).

**Architecture:** Erweiterung von `tools/rate_transitions.py` (Unterbefehle `prepare`/`fit` bekommen `--modus {einzel,kandidaten}`, Default `einzel` = heutiges Verhalten, unveraendert) und `tools/hoertest_server.py` (erkennt den Kandidatensatz automatisch an der Spalte `clip_id` in `bewertung.csv`; Seite je Paar, Note + "bester", Zeitstempel). Neues Modul `hpg_core/candidate_preferences.py` laedt `candidate_preferences.json` (mitgeliefert + Override `%LOCALAPPDATA%\HPG\`); `pair_candidates.score_pair` nimmt daraus die `kandidaten_*_weight`, sonst die Toleranzen. Statistik bleibt scipy-only (wie heute). Der Hoertest selbst (Menschen hoeren) wird in dieser Umsetzung **nicht** durchgefuehrt — Nutzer-Anweisung vom 2026-08-22 (`/goal`, Wortlaut): „Audio-Tests: Alle Aufgaben, die eine menschliche Hörprobe erfordern, überspringst du. Dokumentiere sie für mich auf einer finalen Checkliste und arbeite sofort am nächsten Punkt weiter." Werkzeuge werden mit synthetischen Daten getestet; die Checkliste steht in Task 5.

**Tech Stack:** Python 3.12 (`.\venv312\Scripts\python.exe`), numpy, scipy (`minimize`), Stdlib-HTTP-Server, pytest (`--no-cov`). Kein neuer Dependency.

**Auflagen:** genau so wie in der Spec, vollstaendig, keine Annahmen; jede Zahl gemessen oder als **Startwert** markiert. Waechter `hpg-waechter` an Tor 1 und Tor 2. Keine Rueckfragen an den Nutzer (100 % autonom); Entscheidungen hier festgehalten.

**Grundlagen (verifiziert 2026-08-22, `docs/superpowers/plans/2026-08-22-faktenblatt-kandidaten-teil3.md`, Branch `kandidaten-teil2`):**
- `rate_transitions.py`: CLI `main` :1048-1077 (`prepare` :1053-1066 mit `--anzahl/--out/--bpm-toleranz/--cache/--seed/--nur-genre`; `fit` :1068-1072 mit `--dir/--seed/--genre`), `sammle_kandidaten` :650-699, `rendere_paar` :772-842 (baut `TransitionClipSpec` direkt, `HOERTEST_TRANSITION_TYPE="pro_eq_swap"` :108, `PRE_ROLL_SEK/POST_ROLL_SEK=8.0` :122-123, Beatgrid-Felder :829-839), `crossfade_reserve` :213-243, `maximin_auswahl` :170, `befehl_prepare` :861-953 (`pair_id=f"{nummer:03d}"` :896; CSV-Spalten :926-932), `befehl_fit` :960-1041, `verbinde_bewertungen` :261-298, `fit_logistic` :396-402 (eigene L2-Logistik ueber `_fit_standardisiert` :383/`_standardisiere` :339), `bootstrap_intervalle` :405-442, `datenlage_urteil` :448-465, `leite_gewichte_ab` :468-501, `baue_ausgabe_json` :535-574, `lies_csv`/`schreibe_csv` :845-855, `lade_tracks_aus_cache` :580, `loese_genre_auf` :609; `MIN_EREIGNISSE_JE_MERKMAL=10` :147, `GUT_AB=4` :163, `STANDARD_SEED=20260820` :110.
- `hoertest_server.py`: `BEWERTUNG_SPALTEN` :35, `CLIP_NAME` :38 (`_k1` passt), `merge_bewertungen` :102-117, `lade_uebersicht` :119-165, `lade_track_infos` :168-193, `SEITE` :214-477, `HoertestHandler` :480-605 (GET `/`, `/noten`, `/daten`, `/clips/<name>`; POST `/note`), `main` :608-630. Kein Zufall/Seed, keine Seite je Paar.
- `hpg_core/data/` enthaelt nur `transition_tolerances.json`; `tolerances.py` (`_override_pfad` :23-29, `_merge` :32-41, `load_tolerances` :44-58, `get_tolerances` :61-66, `reset_cache` :86-89) ist die Vorlage fuer den neuen Lader.
- `pair_candidates.py`: `FAKTOREN` :41-42, `_gewichte(tol)` :329-330, `score_pair` :333-376 (Parameter `tolerances`), `build_pair_candidates` :506-540; `PairCandidate` :46-80 (`t_out/t_in`, `overlap_sec`, `blend_bars`, `teilwerte`, `flags`, `score`, `out_a.schema/provenance/confidence`, `in_b....`).
- `transition_renderer.TransitionClipSpec` :51-96 (`mix_out_sec, mix_in_sec, crossfade_sec` Sekunden), `render_transition_clip(spec, path)` :138.
- Einrueckung: `rate_transitions.py` 4, `hoertest_server.py` Python 4 / CSS+JS 2, `tests/test_rate_transitions.py` 4, `tests/test_hoertest_server.py` **2**, `pair_candidates.py` 4, neue Module/Tests 4.

**Entscheidungen an Stellen, die die Spec offen laesst (Waechter Tor 1 vorlegen):**
1. Modusschalter `--modus {einzel,kandidaten}` (Default `einzel`) statt neuer Unterbefehle; `einzel` bleibt byte-identisch zum heutigen Verhalten.
2. Server erkennt den Kandidatenmodus **automatisch** an der Spalte `clip_id` in `bewertung.csv` (Spec: "neuer Modus automatisch"); kein `--modus` am Server, kein Eingriff in `Start.bat` (liegt ausserhalb des Repos) — Checkliste: neue `hoertest_server.py` in den Mobil-Ordner kopieren.
3. Reihenfolge je Paar: `random.Random(seed_satz + int(pair_id))` mischt die `clip_id`s bei `prepare`; gespeichert in `reihenfolge.json` (`{pair_id: {"seed": int, "clips": [...]}}`) — "Seed je Paar gespeichert".
4. `bewertung.csv` (Kandidaten) Spalten `pair_id, clip_id, note, gewaehlt, zeit` (Spec). `gewaehlt` = `"1"` fuer genau einen Clip je Paar, sonst leer; `zeit` = ISO-8601 lokal beim letzten Schreiben des Clips. POST `/note` `{pair_id, clip_id, note|null}`, POST `/bester` `{pair_id, clip_id}` (setzt `gewaehlt` exklusiv).
5. `merkmale.csv` (Kandidaten): `pair_id, clip_id, clip, <10 Teilwerte>, score, schema_out, schema_in, schemata_out, schemata_in, blend_bars, t_out, t_in, provenance_out, provenance_in, confidence_out, confidence_in, crossfade_sek, bpm_relation, bpm_a, bpm_b, genre_a, genre_b, key_a, key_b, track_a, track_b`. `schemata_*` = alle Schemata des Kandidaten (`|`-getrennt, nach Dedupe vereinigt; `schema_*` = Hauptschema); `bpm/genre/key` sind Anzeige-Kontext (kein Score/Schema) — damit der Mobil-Server ohne Cache Tempo/Genre/Camelot zeigen kann (Waechter Tor 1, Auflage 12c). Teilwerte `None` → leere Zelle (s. 8). `score` steht in der CSV, wird aber **nie** angezeigt; `/daten` liefert ausschliesslich die in Task 3 genannten Felder.
6. Auswahl der Paare: wie heute (`sammle_kandidaten`, `--nur-genre`, Maximin ueber `NEUE_FAKTOREN`); `--anzahl` zaehlt **Paare**. Paare ohne `PairCandidate` (Gates) oder ohne renderbaren Clip werden uebersprungen (Reserve wie heute). Clip-Render je Kandidat: `TransitionClipSpec(mix_out_sec=pc.t_out, mix_in_sec=pc.t_in, crossfade_sec=pc.overlap_sec, ...)` mit denselben Beatgrid-Feldern wie `rendere_paar`; `crossfade_reserve` prueft Rest A/B; **zusaetzlich** faellt ein Kandidat mit `overlap_sec > MAX_TRANSITION_OVERLAP_SECONDS` (64 s, Renderer-Deckel `transition_renderer.py:154`) weg (ValueError), damit `crossfade_sek` in der CSV immer die wirklich gerenderte Blende ist (Auflage 6).
7. Zielgroesse 1 (Note): bestehende L2-Logistik (`fit_logistic`) ueber die Teilwerte; Kontrollvariablen entfallen (alle zehn sind Gegenstand). Zielgroesse 2 (Paarvergleich): **Bradley-Terry mit linearem Nutzen** als paarweise Zerlegung — je Paar mit genau einer Wahl entstehen `(Sieger − Verlierer)`-Differenzvektoren fuer jeden Verlierer; Fit ohne Achsenabschnitt durch Maximierung von `Σ log σ(β·d) − L2·|β|²` (`scipy.optimize.minimize`), **ohne gespiegelte Zeilen** (die Spiegelung wuerde die Likelihood verdoppeln und L2 halbieren — Auflage 8). Koeffizienten **unstandardisiert** auf der Teilwert-Skala [0,1] — Absicht: das Gewicht soll proportional zum Nutzen je Teilwert-Einheit sein, nicht je Standardabweichung.
8. Fehlende Teilwerte: eine Zeile mit leerem Merkmal faellt fuer beide Modelle heraus (keine Imputation — keine Annahme); der Bericht nennt die Zahl. Clips **ohne Note** bleiben fuer Zielgroesse 2 erhalten (`note=None`), nur Zielgroesse 1 filtert sie (Auflage 7). Aktive Merkmale = die zehn mit Streuung >= `MIN_KONTROLL_STREUUNG` (0.05) im Satz. **Identifizierbarkeit** (Auflage 1): ein Merkmal ist aus dem Paarvergleich nur schaetzbar, wenn es **innerhalb** der Paare streut; `bpm` und `genre` sind je Paar konstant (Differenz exakt 0), Harmonie/Energie oft kaum. Schwelle `PAAR_STREUUNG_MIN = 0.05` (Startwert) auf die Standardabweichung der Differenzen im Train. Nicht identifizierbare Merkmale behalten ihr Toleranz-Gewicht (`kandidaten_*_weight` aus `get_tolerances`); nur identifizierbare werden neu verteilt, Summe ueber alle zehn 1.0. Bericht weist je Merkmal "nicht identifizierbar" aus. So bleibt die Nutzer-Regel "ausnahmslos alles gewichtet" gewahrt.
9. Holdout nach **Tracks**: `random.Random(seed).shuffle(tracks)`, `HOLDOUT_ANTEIL = 0.30` (Startwert) der Tracks = Holdout; ein Clip gehoert zum Holdout, wenn Track A **oder** B im Holdout ist (≈ 1 − 0.7² ≈ 51 % der Clips — Bericht und Checkliste sagen das); beide Modelle werden nur auf dem Rest geschaetzt. Standardisierung fuer Zielgroesse 1 mit den **Train**-Kennzahlen (`_kennzahlen(X)`, `_standardisiere_mit(X, mittel, streuung)`, Auflage 4). Bericht: AUC (Rangstatistik) fuer Zielgroesse 1 auf Holdout, Trefferquote (Rang 1 des Modells == `gewaehlt`) fuer Zielgroesse 2 auf Holdout, dazu die Zufallsbasis `Mittel(1/Clips je Paar)`.
10. Uebernahme nach `hpg_core/data/candidate_preferences.json` **nur** wenn die reine Funktion `uebernahme_erlaubt(...) -> (bool, grund)` alles bejaht: (a) Datenlage-Gate Zielgroesse 1 (`datenlage_urteil`, 10 je Merkmal und Klasse, Train), (b) Datenlage-Gate Zielgroesse 2: Paare mit genau einer Wahl im Train >= `MIN_EREIGNISSE_JE_MERKMAL` × identifizierbare Merkmale (Auflage 2), (c) Holdout nicht leer mit beiden Klassen und >= 1 Paar mit Wahl, (d) Holdout-AUC > 0.5 **und** Holdout-Trefferquote > Zufallsbasis (Startregel — Spec: "sonst Werte nicht uebernehmen"), (e) mindestens ein identifizierbares Merkmal mit gesichert positivem Effekt. Sonst `<dir>/candidate_preferences_entwurf.json` + Grund.
11. Gewichte: fuer identifizierbare Merkmale die positive untere Bootstrap-Grenze (Bootstrap ueber **Paare** als Cluster, `BOOTSTRAP_ZIEHUNGEN`), proportional auf das Restbudget `1 − Σ(Toleranz-Gewichte der nicht identifizierbaren)`; identifizierbare ohne gesichert positiven Effekt 0. Schema-Rangfolge je Genre (Genre = `loese_genre_auf(Track A)` ueber Pfad→Track-Abgleich `lower()`, Cache-Ausfall → ""): Anteil "gewaehlt" an "angeboten" ueber **alle** Schemata des Kandidaten (`schemata_out|in`, Laplace +1/+2), absteigend; nur Genres mit >= `MIN_EREIGNISSE_JE_MERKMAL` Wahlen.
12. `candidate_preferences.json` Format: `{"_diagnose": {...}, "<Genre>": {"kandidaten_<faktor>_weight": ..., "schema_rang": [...]}}`. Lader `hpg_core/candidate_preferences.py` (mitgeliefert + Override `%LOCALAPPDATA%\HPG\candidate_preferences.json`, Env `HPG_CANDIDATE_PREFERENCES_FILE`). `pair_candidates.score_pair`: ein **explizit** uebergebenes `tolerances` gewinnt (Aufrufer will genau diese Gewichte, z. B. Werkzeuge/Tests); sonst Praeferenz vor `get_tolerances` (Auflage 5a). Tests koppeln sich per Autouse-Fixture in `tests/conftest.py` von der ausgelieferten JSON ab (Auflage 5b). `schema_rang` wird in Teil 4 benutzt.
13. Mobil: `prepare --modus kandidaten` schreibt zusaetzlich `LIESMICH-kandidaten.txt` in den Satzordner (Kopieranleitung, Server-Start, neuer Port-Vorschlag 8767); die `Start.bat` im Mobil-Ordner liegt ausserhalb des Repos → Checkliste.
14. Satz 1 (280 Einzelnoten) bleibt unberuehrt (Spec: "bleiben Satz 1"); `fit --modus einzel` liest ihn wie heute.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| Modify `tools/rate_transitions.py` | `--modus`, Konstanten/Spalten Kandidaten, `rendere_kandidat`, `befehl_prepare_kandidaten`, `reihenfolge.json`, `verbinde_bewertungen_kandidaten`, `paarvergleich_daten`, `fit_paarvergleich`, `auc`, `holdout_nach_tracks`, `schema_rangfolge`, `baue_candidate_preferences`, `befehl_fit_kandidaten` |
| Modify `tools/hoertest_server.py` | Moduserkennung, `lade_uebersicht_kandidaten`, `merge_kandidaten_bewertung`, Seite `SEITE_KANDIDATEN`, Routen `/daten` (beide Modi), `/note` (beide), `/bester`, `/reihenfolge` |
| Create `hpg_core/candidate_preferences.py` | `load_candidate_preferences()`, `kandidaten_gewichte(genre)`, `schema_rangfolge(genre)`, `reset_cache()`, Pfade |
| Create `hpg_core/data/candidate_preferences.json` | `{}` (leer, wie `transition_tolerances.json`) |
| Modify `hpg_core/pair_candidates.py` | `_gewichte(tol, genre)` mit Praeferenz-Vorrang |
| Tests | `tests/test_rate_transitions.py` (4 Leerzeichen, anhaengen), `tests/test_hoertest_server.py` (2 Leerzeichen, anhaengen), Create `tests/test_candidate_preferences.py` (4), `tests/test_pair_candidates.py` (anhaengen) |

---

### Task 0: Waechter Tor 1

- [ ] **Step 1:** Subagent `hpg-waechter` mit: Dateitabelle, die 14 Entscheidungen, Spec Abschnitt 3; ausdruecklich: (a) `einzel`-Pfad unveraendert (Bestandstests bleiben), (b) keine Hoerprobe in dieser Umsetzung, (c) Statistik scipy-only, (d) `candidate_preferences.json` greift nur in `pair_candidates._gewichte`. Auflagen vor Task 1 einarbeiten und hier nachtragen.

---

### Task 1: Lader `hpg_core/candidate_preferences.py` + leere Datei + Vorrang in `pair_candidates`

**Files:**
- Create: `hpg_core/candidate_preferences.py`, `hpg_core/data/candidate_preferences.json` (Inhalt `{}`)
- Modify: `hpg_core/pair_candidates.py` (`_gewichte`, `score_pair`)
- Test: `tests/test_candidate_preferences.py` (neu), `tests/test_pair_candidates.py` (anhaengen)

- [ ] **Step 1: Failing tests**

```python
# tests/test_candidate_preferences.py
"""Tests fuer den Lader der Kandidaten-Praeferenzen (Hoertest Teil 3)."""
import json

import pytest

from hpg_core import candidate_preferences as cp


@pytest.fixture(autouse=True)
def _frisch(monkeypatch, tmp_path):
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(tmp_path / "prefs.json"))
    cp.reset_cache()
    yield
    cp.reset_cache()


def test_ohne_datei_leer():
    assert cp.load_candidate_preferences() == {}
    assert cp.kandidaten_gewichte("Psytrance") is None
    assert cp.schema_rangfolge("Psytrance") == []


def test_override_wird_gelesen_und_validiert(tmp_path):
    gewichte = {f"kandidaten_{f}_weight": 0.1 for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure")}
    (tmp_path / "prefs.json").write_text(json.dumps({
        "_diagnose": {"quelle": "test"},
        "Psytrance": {**gewichte, "schema_rang": ["pssi_phrase", "auto_cue"]},
        "Unbekanntes Genre": {"kandidaten_bpm_weight": 1.0},
    }), encoding="utf-8")
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(gewichte)
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase", "auto_cue"]
    assert cp.kandidaten_gewichte("Unbekanntes Genre") is None   # nicht kanonisch -> ignoriert
    assert cp.kandidaten_gewichte("Techno") is None


def test_gewichte_mit_falscher_summe_werden_verworfen(tmp_path, caplog):
    (tmp_path / "prefs.json").write_text(json.dumps({
        "Psytrance": {"kandidaten_bpm_weight": 0.5, "kandidaten_groove_weight": 0.2}}), encoding="utf-8")
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") is None
```

```python
# tests/test_pair_candidates.py — anhaengen
def test_score_pair_nimmt_praeferenz_gewichte_vor_toleranzen(monkeypatch):
    from hpg_core import candidate_preferences as cp
    a, b = _track(), _track("b.mp3")
    out, inn = _voll(160.0, kick_aktiv=False), _voll(80.0, kick_aktiv=False, camelot_lokal="3A")
    s_default, _, _ = score_pair(a, b, out, inn, 16)
    nur_harmonie = {f"kandidaten_{f}_weight": (1.0 if f == "harmonic" else 0.0) for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure")}
    monkeypatch.setattr(cp, "kandidaten_gewichte", lambda genre: nur_harmonie)
    s_pref, _, _ = score_pair(a, b, out, inn, 16)
    assert s_pref == pytest.approx(0.65)          # 8A -> 3A = 65/100, nur Harmonie zaehlt
    assert s_pref != pytest.approx(s_default)
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: hpg_core.candidate_preferences`)

- [ ] **Step 3: Lader**

```python
"""Kandidaten-Praeferenzen aus dem Hoertest (Spec 2026-08-21, Abschnitt 3).

`fit --modus kandidaten` schreibt hpg_core/data/candidate_preferences.json:
je kanonischem Genre die zehn `kandidaten_*_weight` (Summe 1.0) fuer die
Paar-Bewertung (pair_candidates.score_pair) und `schema_rang` (Rangfolge der
Schemata, Teil 4). Aufbau wie tolerances.py: mitgelieferte Datei, dann
Override unter %LOCALAPPDATA%/HPG (oder HPG_CANDIDATE_PREFERENCES_FILE).
Fehlt alles, liefern die Funktionen None/[] und pair_candidates nimmt die
Toleranzen — es gibt keinen stillen Default.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .genres import CANONICAL_GENRES

logger = logging.getLogger(__name__)

GEWICHT_SCHLUESSEL = tuple(
    f"kandidaten_{f}_weight" for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood",
        "loudness", "structure",
    )
)
_MITGELIEFERT = Path(__file__).parent / "data" / "candidate_preferences.json"
_cache: dict | None = None


def _override_pfad() -> Path:
    env = os.environ.get("HPG_CANDIDATE_PREFERENCES_FILE")
    if env:
        return Path(env)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".hpg")
    return Path(basis) / "HPG" / "candidate_preferences.json"


def _lies(pfad: Path) -> dict:
    if not pfad.is_file():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("candidate_preferences nicht lesbar (%s): %s", pfad, exc)
        return {}
    return daten if isinstance(daten, dict) else {}


def _gueltige_gewichte(eintrag: dict) -> dict | None:
    """Alle zehn Schluessel vorhanden, numerisch, >= 0, Summe 1.0 (±1e-6)."""
    try:
        werte = {k: float(eintrag[k]) for k in GEWICHT_SCHLUESSEL}
    except (KeyError, TypeError, ValueError):
        return None
    if any(v < 0.0 for v in werte.values()) or abs(sum(werte.values()) - 1.0) > 1e-6:
        return None
    return werte


def load_candidate_preferences() -> dict:
    """Liefert {genre: {"gewichte": dict|None, "schema_rang": list}} fuer
    kanonische Genres; ungueltige Gewichte werden geloggt und verworfen."""
    global _cache
    if _cache is not None:
        return _cache
    roh: dict = {}
    for quelle in (_MITGELIEFERT, _override_pfad()):
        for genre, eintrag in _lies(quelle).items():
            if genre in CANONICAL_GENRES and isinstance(eintrag, dict):
                roh.setdefault(genre, {}).update(eintrag)
    ergebnis: dict = {}
    for genre, eintrag in roh.items():
        gewichte = _gueltige_gewichte(eintrag)
        if gewichte is None and any(k in eintrag for k in GEWICHT_SCHLUESSEL):
            logger.warning("candidate_preferences: Gewichte fuer %s ungueltig (Summe != 1.0 "
                           "oder Schluessel fehlen) — ignoriert", genre)
        rang = [s for s in eintrag.get("schema_rang", []) if isinstance(s, str)]
        ergebnis[genre] = {"gewichte": gewichte, "schema_rang": rang}
    _cache = ergebnis
    return ergebnis


def kandidaten_gewichte(genre: str) -> dict | None:
    return load_candidate_preferences().get(genre, {}).get("gewichte")


def schema_rangfolge(genre: str) -> list[str]:
    return list(load_candidate_preferences().get(genre, {}).get("schema_rang", []))


def reset_cache() -> None:
    global _cache
    _cache = None
```

`hpg_core/data/candidate_preferences.json`: Inhalt `{}`.

In `pair_candidates.py`: Import `from . import candidate_preferences` und

```python
def _gewichte(tol: dict, genre: str, explizit: bool) -> dict[str, float]:
    """Gewichtsquelle: ein explizit uebergebenes `tolerances` gewinnt immer;
    sonst schlagen Praeferenzen aus dem Hoertest (candidate_preferences.json)
    die geladenen Toleranzen; ohne Eintrag fuer das Genre gelten die
    kandidaten_*_weight der Toleranzen."""
    pref = None if explizit else candidate_preferences.kandidaten_gewichte(genre)
    quelle = pref if pref is not None else tol
    return {f: float(quelle.get(f"kandidaten_{f}_weight", 0.0)) for f in FAKTOREN}
```
und in `score_pair`: `gew = _gewichte(tol, genre_a, explizit=tolerances is not None)`.

Autouse-Fixture in `tests/conftest.py` (2 Leerzeichen), damit kein Test an der ausgelieferten `candidate_preferences.json` haengt:

```python
@pytest.fixture(autouse=True)
def _keine_kandidaten_praeferenzen(monkeypatch, tmp_path):
  """Kandidaten-Praeferenzen (Hoertest Teil 3) aus Tests heraushalten: weder die
  mitgelieferte noch eine Override-Datei darf das Scoring in Tests aendern."""
  from hpg_core import candidate_preferences as cp
  monkeypatch.setattr(cp, "_MITGELIEFERT", tmp_path / "keine_praeferenzen.json")
  monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(tmp_path / "kein_override.json"))
  cp.reset_cache()
  yield
  cp.reset_cache()
```
Der Test `test_override_wird_gelesen_und_validiert` schreibt seine Datei an den per Env gesetzten Pfad (`_frisch`-Fixture in `tests/test_candidate_preferences.py` setzt denselben Env-Schluessel erneut — bleibt gueltig).

- [ ] **Step 4: Run → PASS** (`tests/test_candidate_preferences.py`, `tests/test_pair_candidates.py`)
- [ ] **Step 5: Commit** `git add hpg_core/candidate_preferences.py hpg_core/data/candidate_preferences.json hpg_core/pair_candidates.py tests/test_candidate_preferences.py tests/test_pair_candidates.py && git commit -m "feat(praeferenzen): candidate_preferences-Lader, Vorrang in score_pair"`

---

### Task 2: `prepare --modus kandidaten` (Render je Kandidat, CSVs, Reihenfolge)

**Files:**
- Modify: `tools/rate_transitions.py`
- Test: `tests/test_rate_transitions.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_rate_transitions.py — anhaengen
import json
from types import SimpleNamespace

from tools.rate_transitions import (
    BEWERTUNG_KANDIDATEN_SPALTEN, MERKMALE_KANDIDATEN_SPALTEN, clip_id_fuer,
    kandidaten_zeilen, reihenfolge_fuer_paar,
)


def _pc(t_out, t_in, bars, score, teil=None, schema_out=("pssi_phrase",), schema_in=("auto_cue",)):
    from hpg_core.mix_candidates import MixCandidate
    from hpg_core.pair_candidates import PairCandidate
    o = MixCandidate(t=t_out, schema=list(schema_out), provenance="rekordbox_pssi", confidence=0.8)
    i = MixCandidate(t=t_in, schema=list(schema_in), provenance="rekordbox_auto", confidence=0.7)
    return PairCandidate(out_a=o, in_b=i, blend_bars=bars, overlap_sec=bars * 1.714, score=score,
                         teilwerte=teil or {"harmonic": 0.9, "bpm": 1.0, "loudness": None},
                         flags={}, begruendung="x", rang=1, bpm_relation="direct")


def test_clip_id_und_spalten():
    assert clip_id_fuer("007", 3) == "007_k3"
    assert BEWERTUNG_KANDIDATEN_SPALTEN == ("pair_id", "clip_id", "note", "gewaehlt", "zeit")
    assert MERKMALE_KANDIDATEN_SPALTEN[:3] == ("pair_id", "clip_id", "clip")
    assert "score" in MERKMALE_KANDIDATEN_SPALTEN and "t_out" in MERKMALE_KANDIDATEN_SPALTEN
    assert MERKMALE_KANDIDATEN_SPALTEN[-2:] == ("track_a", "track_b")


def test_kandidaten_zeilen_schreiben_teilwerte_und_leer_bei_none():
    a = SimpleNamespace(filePath="a.mp3")
    b = SimpleNamespace(filePath="b.mp3")
    bew, merk = kandidaten_zeilen("007", [_pc(160.0, 80.0, 16, 0.8)], a, b, clips=["clips/007_k1.wav"])
    assert bew == [{"pair_id": "007", "clip_id": "007_k1", "note": "", "gewaehlt": "", "zeit": ""}]
    m = merk[0]
    assert m["clip"] == "clips/007_k1.wav" and m["harmonic"] == 0.9 and m["loudness"] == ""
    assert m["schema_out"] == "pssi_phrase" and m["blend_bars"] == 16 and m["t_out"] == 160.0
    assert m["provenance_in"] == "rekordbox_auto" and m["confidence_out"] == 0.8
    assert m["crossfade_sek"] == pytest.approx(16 * 1.714, abs=0.01)


def test_reihenfolge_fuer_paar_deterministisch_und_vollstaendig():
    clips = ["007_k1", "007_k2", "007_k3", "007_k4"]
    r1 = reihenfolge_fuer_paar("007", clips, seed_satz=20260820)
    r2 = reihenfolge_fuer_paar("007", clips, seed_satz=20260820)
    assert r1 == r2 and sorted(r1["clips"]) == clips and r1["seed"] == 20260820 + 7
    assert reihenfolge_fuer_paar("008", clips, seed_satz=20260820)["seed"] == 20260828
```

- [ ] **Step 2: Run → FAIL** (ImportError)

- [ ] **Step 3: Implementierung in `rate_transitions.py`** (nach `ZUSATZ_SPALTEN`, Konstanten; Funktionen vor `befehl_prepare`)

```python
# --- Kandidatenmodus (Spec 2026-08-21 Abschnitt 3) ------------------------
from hpg_core.pair_candidates import FAKTOREN as KANDIDATEN_TEILWERTE, build_pair_candidates
BEWERTUNG_KANDIDATEN_SPALTEN: tuple[str, ...] = ("pair_id", "clip_id", "note", "gewaehlt", "zeit")
MERKMALE_KANDIDATEN_SPALTEN: tuple[str, ...] = (
    "pair_id", "clip_id", "clip", *KANDIDATEN_TEILWERTE, "score",
    "schema_out", "schema_in", "schemata_out", "schemata_in", "blend_bars", "t_out", "t_in",
    "provenance_out", "provenance_in", "confidence_out", "confidence_in",
    "crossfade_sek", "bpm_relation", "bpm_a", "bpm_b", "genre_a", "genre_b", "key_a", "key_b",
    "track_a", "track_b",
)
# Innerhalb-Paar-Streuung (Std der Sieger-Verlierer-Differenzen im Train), ab der
# ein Merkmal aus dem Paarvergleich identifizierbar ist. STARTWERT.
PAAR_STREUUNG_MIN = 0.05
# Holdout nach Tracks: Anteil der Tracks, deren Clips NICHT in die Schaetzung
# gehen. STARTWERT.
HOLDOUT_ANTEIL = 0.30


def clip_id_fuer(pair_id: str, n: int) -> str:
    return f"{pair_id}_k{n}"


def _hauptschema(cand) -> str:
    from hpg_core.mix_candidates import SCHEMA_PRIORITAET
    s = [x for x in (cand.schema or []) if x in SCHEMA_PRIORITAET]
    return min(s, key=SCHEMA_PRIORITAET.index) if s else ""


def kandidaten_zeilen(pair_id: str, paare, track_a, track_b, clips: list[str]) -> tuple[list[dict], list[dict]]:
    """Zeilen fuer bewertung.csv und merkmale.csv je PairCandidate (Index n ab 1).
    Teilwerte None -> leere Zelle (Fit: Zeile faellt fuer das Merkmal heraus).
    bpm/genre/key sind Anzeige-Kontext fuer den Server (kein Score, kein Schema)."""
    bewertung, merkmale = [], []
    for n, (pc, clip) in enumerate(zip(paare, clips), start=1):
        cid = clip_id_fuer(pair_id, n)
        bewertung.append({"pair_id": pair_id, "clip_id": cid, "note": "", "gewaehlt": "", "zeit": ""})
        zeile = {"pair_id": pair_id, "clip_id": cid, "clip": clip}
        for name in KANDIDATEN_TEILWERTE:
            wert = pc.teilwerte.get(name)
            zeile[name] = "" if wert is None else round(float(wert), 6)
        zeile.update({
            "score": round(float(pc.score), 6),
            "schema_out": _hauptschema(pc.out_a), "schema_in": _hauptschema(pc.in_b),
            "schemata_out": "|".join(pc.out_a.schema or []), "schemata_in": "|".join(pc.in_b.schema or []),
            "blend_bars": int(pc.blend_bars), "t_out": float(pc.t_out), "t_in": float(pc.t_in),
            "provenance_out": pc.out_a.provenance, "provenance_in": pc.in_b.provenance,
            "confidence_out": float(pc.out_a.confidence), "confidence_in": float(pc.in_b.confidence),
            "crossfade_sek": round(float(pc.overlap_sec), 2), "bpm_relation": pc.bpm_relation,
            "bpm_a": round(float(getattr(track_a, "bpm", 0.0) or 0.0), 1),
            "bpm_b": round(float(getattr(track_b, "bpm", 0.0) or 0.0), 1),
            "genre_a": loese_genre_auf(track_a), "genre_b": loese_genre_auf(track_b),
            "key_a": str(getattr(track_a, "camelotCode", "") or ""),
            "key_b": str(getattr(track_b, "camelotCode", "") or ""),
            "track_a": track_a.filePath, "track_b": track_b.filePath,
        })
        merkmale.append(zeile)
    return bewertung, merkmale
```
(Test `test_kandidaten_zeilen_...` oben baut `a`/`b` deshalb als `SimpleNamespace(filePath=..., bpm=140.0, camelotCode="8A", detected_genre="Psytrance", genre="Psytrance")`; `loese_genre_auf` liest `detected_genre`/`genre` per `getattr`.)

```python


def reihenfolge_fuer_paar(pair_id: str, clip_ids: list[str], seed_satz: int = STANDARD_SEED) -> dict:
    """Zufaellige, reproduzierbare Anzeige-Reihenfolge je Paar; der Seed wird
    mitgespeichert (reihenfolge.json)."""
    seed = int(seed_satz) + int("".join(ch for ch in pair_id if ch.isdigit()) or 0)
    clips = list(clip_ids)
    random.Random(seed).shuffle(clips)
    return {"seed": seed, "clips": clips}


def rendere_kandidat(a: Track, b: Track, pc, pair_id: str, n: int, clips_dir: Path) -> str:
    """Rendert einen PairCandidate-Clip (Zeitpunkte und Blende des Kandidaten,
    sonst identisch zu rendere_paar). Wirft ValueError, wenn die Blende nicht
    in die Restlaengen passt."""
    rest_a, rest_b = crossfade_reserve(float(pc.t_out), float(a.duration or 0.0),
                                       float(b.duration or 0.0), float(pc.t_in))
    if min(rest_a, rest_b) < float(pc.overlap_sec):
        raise ValueError(f"Blende {pc.overlap_sec:.1f} s passt nicht (Rest A {rest_a:.1f}, B {rest_b:.1f})")
    if float(pc.overlap_sec) > MAX_TRANSITION_OVERLAP_SECONDS:
        # Der Renderer klemmt still auf 64 s (transition_renderer.py:154); dann
        # stuende in merkmale.csv eine andere Blende als im Clip. Lieber weglassen.
        raise ValueError(f"Blende {pc.overlap_sec:.1f} s ueber Renderer-Deckel {MAX_TRANSITION_OVERLAP_SECONDS:.0f} s")
    spec = TransitionClipSpec(
        track_a_path=a.filePath, track_b_path=b.filePath,
        mix_out_sec=float(pc.t_out), mix_in_sec=float(pc.t_in), crossfade_sec=float(pc.overlap_sec),
        transition_type=HOERTEST_TRANSITION_TYPE, pre_roll_sec=PRE_ROLL_SEK, post_roll_sec=POST_ROLL_SEK,
        bpm_a=float(a.bpm or 120.0), bpm_b=float(b.bpm or 120.0),
        first_downbeat_a=float(getattr(a, "first_downbeat", 0.0) or 0.0),
        first_downbeat_b=float(getattr(b, "first_downbeat", 0.0) or 0.0),
        downbeat_reliable_a=getattr(a, "downbeat_confidence", 0.0) >= DOWNBEAT_RELIABLE_MIN,
        downbeat_reliable_b=getattr(b, "downbeat_confidence", 0.0) >= DOWNBEAT_RELIABLE_MIN,
        bar_phase_reliable_a=getattr(a, "downbeat_confidence", 0.0) == REFERENCE_BEATGRID_CONFIDENCE,
        bar_phase_reliable_b=getattr(b, "downbeat_confidence", 0.0) == REFERENCE_BEATGRID_CONFIDENCE,
    )
    ziel = clips_dir / f"{clip_id_fuer(pair_id, n)}.wav"
    render_transition_clip(spec, str(ziel))
    return f"clips/{clip_id_fuer(pair_id, n)}.wav"


LIESMICH_KANDIDATEN = """HPG Hoertest — Kandidatenmodus
Je Paar liegen mehrere Clips (<pair_id>_k<n>.wav): gleicher Uebergang, andere
Mixpunkte/Blende. Seite je Paar: jeden Clip mit 1–5 benoten UND den besten
waehlen. Alles wird sofort in bewertung.csv geschrieben (pair_id, clip_id,
note, gewaehlt, zeit). Anzeige bewusst ohne Score/Schema.

Start am PC:   python tools/hoertest_server.py --dir <dieser Ordner> --port 8767
Mobil: diesen Ordner samt hoertest_server.py (Repo tools/) in den Mobil-Ordner
kopieren; der Server erkennt den Kandidatenmodus selbst (Spalte clip_id).
Auswertung:    python tools/rate_transitions.py fit --modus kandidaten --dir <Ordner>
"""


def befehl_prepare_kandidaten(args: argparse.Namespace) -> int:
    out = Path(args.out)
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    tracks = lade_tracks_aus_cache(args.cache)
    print(f"Analysierte Tracks im Cache: {len(tracks)}")
    kandidaten = sammle_kandidaten(tracks, args.bpm_toleranz)
    if getattr(args, "nur_genre", None):
        kandidaten = filtere_nach_genre(kandidaten, args.nur_genre)
    print(f"Paare nach Gates: {len(kandidaten)}")
    if not kandidaten:
        print("Keine Paare — nichts zu rendern.")
        return 1
    vektoren = [[k["merkmale"][n] for n in NEUE_FAKTOREN] for k in kandidaten]
    reserve = maximin_auswahl(vektoren, args.anzahl * RESERVE_FAKTOR, seed=args.seed)
    bewertung_zeilen, merkmal_zeilen, reihenfolge = [], [], {}
    paare_fertig, uebersprungen = 0, 0
    for index in reserve:
        if paare_fertig >= args.anzahl:
            break
        k = kandidaten[index]
        a, b = k["track_a"], k["track_b"]
        pcs = build_pair_candidates(a, b)
        if not pcs:
            uebersprungen += 1
            continue
        pair_id = f"{paare_fertig + 1:03d}"
        print(f"[{paare_fertig + 1}/{args.anzahl}] Paar {pair_id}: {len(pcs)} Kandidaten ...", flush=True)
        gerendert, clips = [], []
        for n, pc in enumerate(pcs, start=1):
            try:
                clips.append(rendere_kandidat(a, b, pc, pair_id, n, clips_dir))
                gerendert.append(pc)
            except Exception as exc:  # noqa: BLE001 — ein defekter Clip darf den Lauf nicht abbrechen
                logger.warning("Kandidat %s_k%d uebersprungen: %s", pair_id, n, exc)
        if not gerendert:
            uebersprungen += 1
            continue
        bew, merk = kandidaten_zeilen(pair_id, gerendert, a, b, clips)
        bewertung_zeilen += bew
        merkmal_zeilen += merk
        reihenfolge[pair_id] = reihenfolge_fuer_paar(pair_id, [z["clip_id"] for z in bew], args.seed)
        paare_fertig += 1
    if not merkmal_zeilen:
        print("Kein einziger Kandidaten-Clip konnte gerendert werden.")
        return 1
    schreibe_csv(out / "bewertung.csv", BEWERTUNG_KANDIDATEN_SPALTEN, bewertung_zeilen)
    schreibe_csv(out / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmal_zeilen)
    (out / "reihenfolge.json").write_text(json.dumps(reihenfolge, indent=2), encoding="utf-8")
    (out / "LIESMICH-kandidaten.txt").write_text(LIESMICH_KANDIDATEN, encoding="utf-8")
    print(f"Paare: {paare_fertig}   Clips: {len(merkmal_zeilen)}   uebersprungen: {uebersprungen}")
    print(f"Jetzt bewerten: python tools/hoertest_server.py --dir {out} --port 8767")
    return 0
```

CLI: `prepare` und `fit` bekommen `--modus`, `choices=("einzel", "kandidaten")`, `default="einzel"`. `main` dispatcht heute ueber `set_defaults(funktion=...)` (:1065/:1072) — deshalb Wrapper `_prepare(args)` / `_fit(args)`, die nach `args.modus` an `befehl_prepare_kandidaten`/`befehl_prepare` bzw. `befehl_fit_kandidaten`/`befehl_fit` weiterreichen, und `set_defaults(funktion=_prepare)` / `set_defaults(funktion=_fit)`. Import oben: `from hpg_core.config import MAX_TRANSITION_OVERLAP_SECONDS`.

- [ ] **Step 4: Run → PASS** (`tests/test_rate_transitions.py`)
- [ ] **Step 5: Commit** `git add tools/rate_transitions.py tests/test_rate_transitions.py && git commit -m "feat(hoertest): prepare --modus kandidaten — Clips je PairCandidate, CSVs, reihenfolge.json"`

---

### Task 3: Server-Modus Kandidaten (`hoertest_server.py`)

**Files:**
- Modify: `tools/hoertest_server.py`
- Test: `tests/test_hoertest_server.py` (2 Leerzeichen)

- [ ] **Step 1: Failing tests**

```python
# tests/test_hoertest_server.py — anhaengen (2 Leerzeichen)
from tools.hoertest_server import (
  BEWERTUNG_KANDIDATEN_SPALTEN, ist_kandidatensatz, lade_uebersicht_kandidaten,
  merge_kandidaten_bewertung,
)


def test_ist_kandidatensatz_an_clip_id_spalte():
  assert ist_kandidatensatz([{"pair_id": "001", "clip_id": "001_k1", "note": "", "gewaehlt": "", "zeit": ""}])
  assert not ist_kandidatensatz([{"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""}])
  assert not ist_kandidatensatz([])


def test_merge_kandidaten_note_und_bester_exklusiv_mit_zeit():
  zeilen = [
    {"pair_id": "001", "clip_id": "001_k1", "note": "", "gewaehlt": "", "zeit": ""},
    {"pair_id": "001", "clip_id": "001_k2", "note": "", "gewaehlt": "1", "zeit": "alt"},
    {"pair_id": "002", "clip_id": "002_k1", "note": "", "gewaehlt": "", "zeit": ""},
  ]
  neu = merge_kandidaten_bewertung(zeilen, pair_id="001", clip_id="001_k1", note=4, zeit="2026-08-22T20:00:00")
  assert neu[0]["note"] == "4" and neu[0]["zeit"] == "2026-08-22T20:00:00"
  neu = merge_kandidaten_bewertung(neu, pair_id="001", clip_id="001_k1", bester=True, zeit="2026-08-22T20:01:00")
  assert neu[0]["gewaehlt"] == "1" and neu[1]["gewaehlt"] == ""    # exklusiv je Paar
  assert neu[2]["gewaehlt"] == "" and neu[1]["zeit"] == "alt"
  neu = merge_kandidaten_bewertung(neu, pair_id="001", clip_id="001_k1", note=None, zeit="t")
  assert neu[0]["note"] == ""


def test_lade_uebersicht_kandidaten_gruppiert_verdeckt_und_in_reihenfolge():
  merk = [
    {"pair_id": "001", "clip_id": "001_k1", "clip": "clips/001_k1.wav", "score": "0.9", "schema_out": "pssi_phrase",
     "crossfade_sek": "27.4", "track_a": "C:/x/a.mp3", "track_b": "C:/x/b.mp3", "harmonic": "0.9"},
    {"pair_id": "001", "clip_id": "001_k2", "clip": "clips/001_k2.wav", "score": "0.5", "schema_out": "sektion",
     "crossfade_sek": "54.9", "track_a": "C:/x/a.mp3", "track_b": "C:/x/b.mp3", "harmonic": "0.9"},
  ]
  bew = [
    {"pair_id": "001", "clip_id": "001_k1", "note": "", "gewaehlt": "", "zeit": ""},
    {"pair_id": "001", "clip_id": "001_k2", "note": "3", "gewaehlt": "1", "zeit": "t"},
  ]
  reihenfolge = {"001": {"seed": 1, "clips": ["001_k2", "001_k1"]}}
  infos = {"c:/x/a.mp3": {"bpm": 140.0, "genre": "Psytrance", "key": "8A"}}
  paare = lade_uebersicht_kandidaten(merk, bew, reihenfolge, infos)
  assert [p["pair_id"] for p in paare] == ["001"]
  p = paare[0]
  assert [c["clip_id"] for c in p["clips"]] == ["001_k2", "001_k1"]
  assert p["bpm_a"] == 140.0 and p["genre_a"] == "Psytrance" and p["key_a"] == "8A"
  c = p["clips"][0]
  assert c["note"] == "3" and c["gewaehlt"] == "1" and c["crossfade_sek"] == "54.9"
  assert "score" not in c and "schema_out" not in c and "harmonic" not in c
```

- [ ] **Step 2: Run → FAIL** (ImportError)

- [ ] **Step 3: Implementierung** — in `hoertest_server.py` nach `BEWERTUNG_SPALTEN`:

```python
# Kandidatenmodus (Spec 2026-08-21 Abschnitt 3): bewertung.csv traegt clip_id.
BEWERTUNG_KANDIDATEN_SPALTEN = ("pair_id", "clip_id", "note", "gewaehlt", "zeit")


def ist_kandidatensatz(bewertung_zeilen: list[dict]) -> bool:
    """Moduserkennung: ein Kandidatensatz hat die Spalte clip_id."""
    return bool(bewertung_zeilen) and "clip_id" in bewertung_zeilen[0]


def merge_kandidaten_bewertung(zeilen: list[dict], *, pair_id: str, clip_id: str,
                               note=None, bester: bool = False, zeit: str = "") -> list[dict]:
    """Traegt Note (None = loeschen) bzw. die exklusive Wahl 'bester' eines
    Clips ein; `zeit` wird nur auf dem beruehrten Clip gesetzt."""
    neu = []
    for z in zeilen:
        k = dict(z)
        if k.get("pair_id") == pair_id:
            if bester:
                k["gewaehlt"] = "1" if k.get("clip_id") == clip_id else ""
            if k.get("clip_id") == clip_id:
                if not bester:
                    k["note"] = "" if note in (None, "") else str(int(note))
                k["zeit"] = zeit
        neu.append(k)
    return neu


def lade_uebersicht_kandidaten(merkmale_zeilen, bewertung_zeilen, reihenfolge: dict,
                               infos: dict | None = None) -> list[dict]:
    """Gruppen je Paar, Clips in gespeicherter Reihenfolge, verdeckt: kein
    score, kein Schema, keine Teilwerte — nur Tempo/Genre/Camelot/Blende."""
    infos = infos or {}
    merk = {z["clip_id"]: z for z in merkmale_zeilen}
    gruppen: dict[str, dict] = {}
    for z in bewertung_zeilen:
        pid = str(z.get("pair_id", "")).strip()
        m = merk.get(z.get("clip_id"), {})
        if pid not in gruppen:
            pfad_a, pfad_b = str(m.get("track_a", "")), str(m.get("track_b", ""))
            ia, ib = infos.get(pfad_a.lower(), {}), infos.get(pfad_b.lower(), {})
            gruppen[pid] = {
                "pair_id": pid, "track_a": Path(pfad_a).name, "track_b": Path(pfad_b).name,
                "bpm_a": ia.get("bpm", ""), "bpm_b": ib.get("bpm", ""),
                "genre_a": ia.get("genre", ""), "genre_b": ib.get("genre", ""),
                "key_a": ia.get("key", ""), "key_b": ib.get("key", ""), "clips": [],
            }
        gruppen[pid]["clips"].append({
            "clip_id": z.get("clip_id", ""), "clip": str(m.get("clip", "")),
            "note": str(z.get("note", "")).strip(), "gewaehlt": str(z.get("gewaehlt", "")).strip(),
            "crossfade_sek": str(m.get("crossfade_sek", "")).strip(),
        })
    for pid, g in gruppen.items():
        folge = reihenfolge.get(pid, {}).get("clips")
        if folge:
            rang = {cid: i for i, cid in enumerate(folge)}
            g["clips"].sort(key=lambda c: rang.get(c["clip_id"], len(rang)))
    return list(gruppen.values())
```

`SEITE_KANDIDATEN` (neues HTML, gleicher Stil/CSS wie `SEITE`; JS: `/daten` liefert Paar-Gruppen; Anzeige **ein Paar je Seite** mit Kopf (pair_id, Tempo, Genre, Camelot, Fortschritt "Paar i von n"), je Clip Karte mit `<audio>`, Blendenbalken (`zeichneSpur` wie heute mit `crossfade_sek`), Notenknoepfe 1–5 (POST `/note` `{pair_id, clip_id, note}`), Knopf "bester" (POST `/bester` `{pair_id, clip_id}`, exklusiv markiert), Navigation "← Paar / Paar →" (Tasten `PageUp/PageDown`), Tasten 1–5 auf den aktiven Clip, Pfeile hoch/runter wechseln den Clip, Leertaste spielt; **keine** Score-/Schema-/Teilwert-Anzeige). Der vollstaendige HTML/JS-Text wird im Umsetzungsschritt aus `SEITE` abgeleitet (CSS kopieren; JS-Funktionen `zeichnePaar()`, `setzeNote()`, `setzeBester()`, `naechstesPaar()`); verbindlich sind die Routen und Nutzlasten oben.

Handler: `do_GET` `/` liefert `SEITE_KANDIDATEN`, wenn `ist_kandidatensatz(lies_csv(bewertung))`, sonst `SEITE`; `/daten` liefert im Kandidatenmodus `lade_uebersicht_kandidaten(merkmale, bewertung, self.reihenfolge, self.track_infos)` — **keine weiteren Felder** als die oben gezeigten (Verdeckung serverseitig; Waechter Tor 2 prueft das); `/reihenfolge` liefert `reihenfolge.json`; `do_POST` `/note` nimmt im Kandidatenmodus `{pair_id, clip_id, note|null}` und schreibt `merge_kandidaten_bewertung(..., zeit=datetime.now().isoformat(timespec="seconds"))` mit `BEWERTUNG_KANDIDATEN_SPALTEN`; `/bester` analog mit `bester=True`. `main` laedt `reihenfolge.json` (fehlt sie: `{}`), Port-Default bleibt 8765. `import datetime` (heute nicht importiert) ergaenzen. Mobil ohne Cache: `lade_uebersicht_kandidaten` nimmt `bpm_a/b, genre_a/b, key_a/b` aus `merkmale.csv`, wenn `infos` fuer den Pfad nichts liefert (Spalten aus Task 2) — Test: `infos={}` und Spalten in `merk` gesetzt → Kontext erscheint trotzdem.

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add tools/hoertest_server.py tests/test_hoertest_server.py && git commit -m "feat(hoertest-server): Kandidatenmodus — Seite je Paar, Note + bester, Zeitstempel, gespeicherte Reihenfolge"`

---

### Task 4: `fit --modus kandidaten` (zwei Zielgroessen, Holdout nach Tracks, AUC/Trefferquote, Praeferenz-JSON)

**Files:**
- Modify: `tools/rate_transitions.py`
- Test: `tests/test_rate_transitions.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_rate_transitions.py — anhaengen
import numpy as np

from pathlib import Path

from tools.rate_transitions import (
    _kennzahlen, _standardisiere_mit, auc, baue_candidate_preferences, bootstrap_paarvergleich,
    fit_paarvergleich, gewichte_aus_paarvergleich, holdout_nach_tracks, identifizierbare_merkmale,
    nur_mit_note, paarvergleich_daten, schema_rangfolge, trefferquote_paarvergleich,
    uebernahme_erlaubt, verbinde_bewertungen_kandidaten,
)


def _merk(pid, cid, ta, tb, **teil):
    z = {"pair_id": pid, "clip_id": cid, "track_a": ta, "track_b": tb, "schema_out": "pssi_phrase",
         "schema_in": "auto_cue"}
    z.update({k: ("" if v is None else v) for k, v in teil.items()})
    return z


def test_verbinde_bewertungen_kandidaten_liest_note_gewaehlt_und_verwirft_leere_merkmale():
    merk = [_merk("001", "001_k1", "a", "b", harmonic=0.9, groove=0.8),
            _merk("001", "001_k2", "a", "b", harmonic=0.2, groove=None),
            _merk("002", "002_k1", "a", "c", harmonic=0.5, groove=0.5)]
    bew = [{"pair_id": "001", "clip_id": "001_k1", "note": "5", "gewaehlt": "1", "zeit": "t"},
           {"pair_id": "001", "clip_id": "001_k2", "note": "2", "gewaehlt": "", "zeit": "t"},
           {"pair_id": "002", "clip_id": "002_k1", "note": "", "gewaehlt": "", "zeit": ""}]
    zeilen, ohne, verworfen = verbinde_bewertungen_kandidaten(merk, bew, merkmale=("harmonic", "groove"))
    # 001_k2: leeres Merkmal -> verworfen; 002_k1: ohne Note -> bleibt (note None) fuer den Paarvergleich
    assert [z["clip_id"] for z in zeilen] == ["001_k1", "002_k1"] and ohne == 1 and verworfen == 1
    assert zeilen[0]["note"] == 5 and zeilen[0]["bewertung"] == 5 and zeilen[0]["gewaehlt"] is True
    assert zeilen[0]["tracks"] == ("a", "b") and zeilen[1]["note"] is None
    assert [z["clip_id"] for z in nur_mit_note(zeilen)] == ["001_k1"]


def test_auc_rangstatistik():
    assert auc(np.array([1, 1, 0, 0]), np.array([0.9, 0.8, 0.2, 0.1])) == pytest.approx(1.0)
    assert auc(np.array([1, 0]), np.array([0.5, 0.5])) == pytest.approx(0.5)
    assert auc(np.array([1, 1]), np.array([0.5, 0.6])) is None


def test_holdout_nach_tracks_trennt_clips_deterministisch():
    zeilen = [{"tracks": ("a", "b")}, {"tracks": ("c", "d")}, {"tracks": ("a", "d")}, {"tracks": ("e", "f")}]
    train, hold = holdout_nach_tracks(zeilen, anteil=0.5, seed=1)
    assert len(train) + len(hold) == 4
    hold_tracks = {t for z in hold for t in z["tracks"]}
    assert all(not (set(z["tracks"]) & hold_tracks) for z in train)
    assert holdout_nach_tracks(zeilen, anteil=0.5, seed=1) == (train, hold)


def _synth_paare(n=60, seed=3):
    rng = np.random.default_rng(seed)
    zeilen = []
    for p in range(n):
        xs = rng.uniform(0, 1, size=(3, 3))
        nutzen = 3.0 * xs[:, 0] + 0.0 * xs[:, 1]
        sieger = int(np.argmax(nutzen))
        for k in range(3):
            zeilen.append({"pair_id": f"{p:03d}", "clip_id": f"{p:03d}_k{k+1}", "note": 3, "bewertung": 3,
                           "gewaehlt": k == sieger,
                           "merkmale": {"harmonic": xs[k, 0], "groove": xs[k, 1], "bpm": 0.9},  # bpm je Paar konstant
                           "tracks": (f"a{p}", f"b{p}"), "genre": "Psytrance",
                           "schema_out": "pssi_phrase", "schema_in": "auto_cue",
                           "schemata_out": ["pssi_phrase"], "schemata_in": ["auto_cue"]})
    return zeilen


def test_paarvergleich_findet_bekannte_praeferenz_und_identifizierbarkeit():
    zeilen = _synth_paare()
    X, gruppen = paarvergleich_daten(zeilen, ("harmonic", "groove", "bpm"))
    assert X.shape == (120, 3) and len(gruppen) == 120            # 60 Paare x 2 Verlierer, keine Spiegelung
    assert identifizierbare_merkmale(X, ("harmonic", "groove", "bpm")) == ["harmonic", "groove"]
    beta = fit_paarvergleich(X)
    assert beta[0] > 1.0 and abs(beta[1]) < beta[0] / 3 and beta[2] == pytest.approx(0.0, abs=1e-6)
    treffer, basis = trefferquote_paarvergleich(beta, zeilen, ("harmonic", "groove", "bpm"))
    assert treffer > 0.8 and basis == pytest.approx(1 / 3)


def test_bootstrap_paarvergleich_zieht_ueber_paare():
    zeilen = _synth_paare(n=20)
    X, gruppen = paarvergleich_daten(zeilen, ("harmonic", "groove"))
    iv = bootstrap_paarvergleich(X, gruppen, ziehungen=30, seed=1)
    assert len(iv) == 2 and iv[0][0] > 0.0                          # harmonic gesichert positiv
    assert bootstrap_paarvergleich(np.zeros((0, 2)), [], ziehungen=5) == [(0.0, 0.0), (0.0, 0.0)]


def test_gewichte_aus_paarvergleich_restbudget_und_leer():
    tol = {f"kandidaten_{f}_weight": w for f, w in zip(
        ("harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure"),
        (0.140, 0.106, 0.106, 0.106, 0.264, 0.070, 0.044, 0.044, 0.060, 0.060))}
    g = gewichte_aus_paarvergleich(("harmonic", "groove"), [(0.5, 2.0), (-0.1, 0.3)], ["harmonic", "groove"], tol)
    assert g["bpm"] == pytest.approx(0.106) and g["groove"] == 0.0       # nicht identifizierbar behaelt, ungesichert 0
    assert g["harmonic"] == pytest.approx(1.0 - (1.0 - 0.140 - 0.264))     # Restbudget komplett auf harmonic
    assert sum(g.values()) == pytest.approx(1.0)
    assert gewichte_aus_paarvergleich(("harmonic",), [(-0.2, 0.1)], ["harmonic"], tol) == {}


def test_uebernahme_erlaubt_gruende():
    ok, _ = uebernahme_erlaubt(belastbar_note=True, n_paare_train=40, n_identifizierbar=2, auc_holdout=0.7,
                               treffer_holdout=0.6, basis_holdout=0.33, gewichte={"harmonic": 1.0})
    assert ok
    assert not uebernahme_erlaubt(belastbar_note=False, n_paare_train=40, n_identifizierbar=2, auc_holdout=0.7,
                                  treffer_holdout=0.6, basis_holdout=0.33, gewichte={"harmonic": 1.0})[0]
    assert "zu wenige Paare" in uebernahme_erlaubt(belastbar_note=True, n_paare_train=5, n_identifizierbar=2,
                                                   auc_holdout=0.7, treffer_holdout=0.6, basis_holdout=0.33,
                                                   gewichte={"harmonic": 1.0})[1]
    assert "AUC" in uebernahme_erlaubt(belastbar_note=True, n_paare_train=40, n_identifizierbar=2, auc_holdout=0.5,
                                       treffer_holdout=0.6, basis_holdout=0.33, gewichte={"harmonic": 1.0})[1]
    assert "Trefferquote" in uebernahme_erlaubt(belastbar_note=True, n_paare_train=40, n_identifizierbar=2,
                                                auc_holdout=0.7, treffer_holdout=0.3, basis_holdout=0.33,
                                                gewichte={"harmonic": 1.0})[1]


def test_standardisiere_mit_train_kennzahlen():
    X = np.array([[0.0, 10.0], [2.0, 10.0]])
    m, s = _kennzahlen(X)
    assert list(m) == [1.0, 10.0] and list(s) == [1.0, 1.0]          # Streuung 0 -> 1
    assert _standardisiere_mit(np.array([[3.0, 12.0]]), m, s).tolist() == [[2.0, 2.0]]


def test_rendere_kandidat_verwirft_blende_ueber_deckel(monkeypatch):
    from tools import rate_transitions as rt
    pc = _pc(100.0, 60.0, 48, 0.5)                                    # 48 Takte * 1.714 = 82 s > 64
    a = SimpleNamespace(filePath="a.mp3", duration=400.0, bpm=140.0, first_downbeat=0.0, downbeat_confidence=1.0)
    b = SimpleNamespace(filePath="b.mp3", duration=400.0, bpm=140.0, first_downbeat=0.0, downbeat_confidence=1.0)
    monkeypatch.setattr(rt, "render_transition_clip", lambda spec, pfad: pfad)
    with pytest.raises(ValueError):
        rt.rendere_kandidat(a, b, pc, "001", 1, Path("."))


def test_schema_rangfolge_und_praeferenz_json():
    zeilen = [{"genre": "Psytrance", "gewaehlt": g, "schemata_out": [s], "schemata_in": ["auto_cue"]}
              for s, g in [("pssi_phrase", True), ("pssi_phrase", False), ("sektion", False), ("sektion", False)] * 5]
    rang = schema_rangfolge(zeilen, min_wahlen=5)
    assert rang["Psytrance"][0] == "pssi_phrase"
    prefs = baue_candidate_preferences({"harmonic": 0.7, "groove": 0.3}, rang, {"quelle": "test"})
    assert prefs["Psytrance"]["kandidaten_harmonic_weight"] == pytest.approx(0.7)
    assert sum(v for k, v in prefs["Psytrance"].items() if k.endswith("_weight")) == pytest.approx(1.0)
    assert prefs["Psytrance"]["schema_rang"][0] == "pssi_phrase" and "_diagnose" in prefs
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implementierung** (reine Logik, vor `befehl_fit`)

```python
def verbinde_bewertungen_kandidaten(merkmale_zeilen, bewertung_zeilen, merkmale=KANDIDATEN_TEILWERTE,
                                    genre_von=None) -> tuple[list[dict], int, int]:
    """Join ueber clip_id. Rueckgabe (Zeilen, ohne Note, verworfen). Verworfen =
    ungueltige Note oder ein leeres Merkmal (keine Imputation)."""
    noten = {str(z.get("clip_id", "")).strip(): z for z in bewertung_zeilen}
    zeilen, ohne, verworfen = [], 0, 0
    for roh in merkmale_zeilen:
        cid = str(roh.get("clip_id", "")).strip()
        b = noten.get(cid) or {}
        eintrag = str(b.get("note", "")).strip()
        try:
            werte = {n: float(roh[n]) for n in merkmale}
        except (KeyError, TypeError, ValueError):
            verworfen += 1            # leeres/ungueltiges Merkmal: fuer BEIDE Modelle raus
            continue
        note = None
        if eintrag:
            try:
                note = int(round(float(eintrag)))
            except (TypeError, ValueError):
                verworfen += 1
                continue
            if not BEWERTUNG_MIN <= note <= BEWERTUNG_MAX:
                verworfen += 1
                continue
        else:
            ohne += 1                 # ohne Note: bleibt fuer den Paarvergleich erhalten
        tracks = (str(roh.get("track_a", "")), str(roh.get("track_b", "")))
        zeilen.append({
            "pair_id": str(roh.get("pair_id", "")).strip(), "clip_id": cid,
            "note": note, "bewertung": note,   # "bewertung": Schluessel fuer zu_zielgroesse
            "gewaehlt": str(b.get("gewaehlt", "")).strip() == "1", "merkmale": werte, "tracks": tracks,
            "genre": genre_von(tracks[0]) if genre_von else "",
            "schema_out": roh.get("schema_out", ""), "schema_in": roh.get("schema_in", ""),
            "schemata_out": [s for s in str(roh.get("schemata_out", "")).split("|") if s],
            "schemata_in": [s for s in str(roh.get("schemata_in", "")).split("|") if s],
        })
    return zeilen, ohne, verworfen


def nur_mit_note(zeilen: list[dict]) -> list[dict]:
    """Zielgroesse 1 (Note) sieht nur benotete Clips; Zielgroesse 2 alle."""
    return [z for z in zeilen if z.get("note") is not None]


def _kennzahlen(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Spaltenmittel und -streuung (Streuung 0 -> 1), Grundlage fuer
    _standardisiere_mit — Holdout wird mit den TRAIN-Kennzahlen skaliert."""
    X = np.asarray(X, dtype=float)
    mittel = X.mean(axis=0)
    streuung = X.std(axis=0)
    streuung[streuung == 0.0] = 1.0
    return mittel, streuung


def _standardisiere_mit(X: np.ndarray, mittel: np.ndarray, streuung: np.ndarray) -> np.ndarray:
    return (np.asarray(X, dtype=float) - mittel) / streuung


def identifizierbare_merkmale(X_diff: np.ndarray, namen, schwelle: float = PAAR_STREUUNG_MIN) -> list[str]:
    """Merkmale, die INNERHALB der Paare streuen (Std der Sieger-Verlierer-
    Differenzen >= schwelle). bpm/genre sind je Paar konstant -> nie dabei."""
    if X_diff.size == 0:
        return []
    std = np.asarray(X_diff, dtype=float).std(axis=0)
    return [n for n, s in zip(namen, std) if s >= schwelle]


def uebernahme_erlaubt(*, belastbar_note: bool, n_paare_train: int, n_identifizierbar: int,
                       auc_holdout: float | None, treffer_holdout: float | None,
                       basis_holdout: float | None, gewichte: dict) -> tuple[bool, str]:
    """Entscheidung 10: alle Bedingungen muessen halten, sonst (False, Grund)."""
    if not belastbar_note:
        return False, "Datenlage Zielgroesse 1 nicht belastbar (10 je Merkmal und Klasse)"
    if n_identifizierbar == 0:
        return False, "kein Merkmal streut innerhalb der Paare (nicht identifizierbar)"
    if n_paare_train < MIN_EREIGNISSE_JE_MERKMAL * n_identifizierbar:
        return False, (f"zu wenige Paare mit Wahl im Train: {n_paare_train} < "
                       f"{MIN_EREIGNISSE_JE_MERKMAL * n_identifizierbar}")
    if auc_holdout is None or treffer_holdout is None or basis_holdout is None:
        return False, "Holdout leer oder ohne beide Klassen/ohne Paar mit Wahl"
    if not auc_holdout > 0.5:
        return False, f"Holdout-AUC {auc_holdout:.3f} nicht besser als Zufall"
    if not treffer_holdout > basis_holdout:
        return False, f"Holdout-Trefferquote {treffer_holdout:.3f} nicht ueber Zufallsbasis {basis_holdout:.3f}"
    if not any(v > 0.0 for v in gewichte.values()):
        return False, "kein identifizierbares Merkmal mit gesichert positivem Effekt"
    return True, "alle Bedingungen erfuellt"


def auc(y: np.ndarray, score: np.ndarray) -> float | None:
    """Flaeche unter der ROC-Kurve als Rangstatistik (Mann-Whitney); None,
    wenn eine Klasse fehlt."""
    y = np.asarray(y, dtype=float)
    pos, neg = score[y == 1.0], score[y == 0.0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    groesser = (pos[:, None] > neg[None, :]).sum()
    gleich = (pos[:, None] == neg[None, :]).sum()
    return float((groesser + 0.5 * gleich) / (len(pos) * len(neg)))


def holdout_nach_tracks(zeilen: list[dict], anteil: float = HOLDOUT_ANTEIL, seed: int = STANDARD_SEED):
    """Teilt nach TRACKS: ein Clip ist Holdout, wenn Track A oder B im
    Holdout-Trackanteil liegt. Deterministisch ueber seed."""
    tracks = sorted({t for z in zeilen for t in z["tracks"]})
    random.Random(seed).shuffle(tracks)
    n_hold = int(round(len(tracks) * anteil))
    hold = set(tracks[:n_hold])
    train = [z for z in zeilen if not (set(z["tracks"]) & hold)]
    holdout = [z for z in zeilen if set(z["tracks"]) & hold]
    return train, holdout


def paarvergleich_daten(zeilen: list[dict], merkmale) -> tuple[np.ndarray, list[str]]:
    """Differenzen Sieger - Verlierer je Paar mit genau einer Wahl (Bradley-
    Terry als paarweise Zerlegung: ein Vergleich je Verlierer, KEINE
    Spiegelung — die wuerde die Likelihood verdoppeln und L2 halbieren).
    Rueckgabe X_diff, Paar-Ids je Zeile (fuer den Cluster-Bootstrap)."""
    namen = list(merkmale)
    X, gruppen = [], []
    je_paar: dict[str, list[dict]] = {}
    for z in zeilen:
        je_paar.setdefault(z["pair_id"], []).append(z)
    for pid, clips in je_paar.items():
        sieger = [c for c in clips if c["gewaehlt"]]
        if len(sieger) != 1 or len(clips) < 2:
            continue
        s = np.array([sieger[0]["merkmale"][n] for n in namen], dtype=float)
        for c in clips:
            if c is sieger[0]:
                continue
            v = np.array([c["merkmale"][n] for n in namen], dtype=float)
            X.append(s - v)
            gruppen.append(pid)
    if not X:
        return np.zeros((0, len(namen))), []
    return np.vstack(X), gruppen


def fit_paarvergleich(X_diff: np.ndarray, l2: float = L2_STAERKE) -> np.ndarray:
    """Bradley-Terry mit linearem Nutzen, ohne Achsenabschnitt:
    maximiert sum log sigmoid(beta . d) - l2 * |beta|^2 ueber alle
    Sieger-Verlierer-Differenzen d. Koeffizienten bewusst UNSTANDARDISIERT
    (Teilwert-Skala [0,1]): das Gewicht soll dem Nutzen je Teilwert-Einheit
    entsprechen, nicht je Standardabweichung."""
    X = np.asarray(X_diff, dtype=float)
    if X.size == 0:
        return np.zeros(X.shape[1] if X.ndim == 2 else 0)

    def ziel(beta):
        z = X @ beta
        return float(np.sum(np.logaddexp(0.0, -z))) + l2 * float(beta @ beta)

    def grad(beta):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        return -(X.T @ (1.0 - p)) + 2.0 * l2 * beta

    res = minimize(ziel, np.zeros(X.shape[1]), jac=grad, method="L-BFGS-B")
    return np.asarray(res.x, dtype=float)


def bootstrap_paarvergleich(X_diff, gruppen, l2=L2_STAERKE, ziehungen=BOOTSTRAP_ZIEHUNGEN,
                            seed=STANDARD_SEED) -> list[tuple[float, float]]:
    """95-%-Bootstrap je Koeffizient, Ziehung ueber PAARE (Cluster), nicht
    ueber Einzelzeilen: die K-1 Vergleiche eines Paars sind korreliert."""
    ids = sorted(set(gruppen))
    if not ids:
        return [(0.0, 0.0)] * (X_diff.shape[1] if X_diff.ndim == 2 else 0)
    index_je_id = {pid: [i for i, g in enumerate(gruppen) if g == pid] for pid in ids}
    rng = random.Random(seed)
    stapel = []
    for _ in range(int(ziehungen)):
        zug = [i for pid in rng.choices(ids, k=len(ids)) for i in index_je_id[pid]]
        stapel.append(fit_paarvergleich(X_diff[zug], l2))
    s = np.vstack(stapel)
    return [(float(np.percentile(s[:, j], 2.5)), float(np.percentile(s[:, j], 97.5))) for j in range(s.shape[1])]


def trefferquote_paarvergleich(beta: np.ndarray, zeilen: list[dict], merkmale) -> tuple[float | None, float | None]:
    """Anteil Paare, deren gewaehlter Clip den hoechsten Modell-Nutzen hat;
    zweiter Wert = Zufallsbasis (Mittel von 1/Clips je Paar)."""
    namen = list(merkmale)
    je_paar: dict[str, list[dict]] = {}
    for z in zeilen:
        je_paar.setdefault(z["pair_id"], []).append(z)
    treffer, basis, n = 0, 0.0, 0
    for clips in je_paar.values():
        sieger = [c for c in clips if c["gewaehlt"]]
        if len(sieger) != 1 or len(clips) < 2:
            continue
        nutzen = [float(np.array([c["merkmale"][m] for m in namen]) @ beta) for c in clips]
        if clips[int(np.argmax(nutzen))] is sieger[0]:
            treffer += 1
        basis += 1.0 / len(clips)
        n += 1
    if n == 0:
        return None, None
    return treffer / n, basis / n


def gewichte_aus_paarvergleich(namen, intervalle, identifizierbar, toleranz_gewichte: dict) -> dict[str, float]:
    """Gewichte fuer alle zehn Faktoren (Schluessel = Faktorname), Summe 1.0:
    nicht identifizierbare behalten ihr Toleranz-Gewicht (kandidaten_*_weight);
    das Restbudget wird auf identifizierbare Merkmale nach positiver unterer
    Bootstrap-Grenze verteilt; identifizierbare ohne gesicherten positiven
    Effekt bekommen 0. Kein identifizierbares positiv -> {} (keine Uebernahme)."""
    fest = {n: float(toleranz_gewichte.get(f"kandidaten_{n}_weight", 0.0))
            for n in KANDIDATEN_TEILWERTE if n not in identifizierbar}
    roh = {n: (lo if lo > 0.0 and hi > 0.0 else 0.0)
           for n, (lo, hi) in zip(namen, intervalle) if n in identifizierbar}
    summe = sum(roh.values())
    if summe <= 0.0:
        return {}
    rest = max(0.0, 1.0 - sum(fest.values()))
    ergebnis = dict(fest)
    ergebnis.update({n: rest * v / summe for n, v in roh.items()})
    for n in KANDIDATEN_TEILWERTE:
        ergebnis.setdefault(n, 0.0)
    return ergebnis


def schema_rangfolge(zeilen: list[dict], min_wahlen: int = MIN_EREIGNISSE_JE_MERKMAL) -> dict[str, list[str]]:
    """Je Genre: Hauptschemata (Out- und In-Seite gemeinsam) nach Anteil
    'gewaehlt' an 'angeboten' (Laplace +1/+2), absteigend; nur Genres mit
    mindestens min_wahlen Wahlen."""
    from hpg_core.mix_candidates import SCHEMA_PRIORITAET
    angebot: dict[str, dict[str, int]] = {}
    wahl: dict[str, dict[str, int]] = {}
    wahlen_je_genre: dict[str, int] = {}
    for z in zeilen:
        g = z.get("genre") or ""
        for s in (z.get("schema_out"), z.get("schema_in")):
            if not s:
                continue
            angebot.setdefault(g, {}).setdefault(s, 0)
            angebot[g][s] += 1
            if z.get("gewaehlt"):
                wahl.setdefault(g, {}).setdefault(s, 0)
                wahl[g][s] += 1
        if z.get("gewaehlt"):
            wahlen_je_genre[g] = wahlen_je_genre.get(g, 0) + 1
    ergebnis = {}
    for g, schemata in angebot.items():
        if wahlen_je_genre.get(g, 0) < min_wahlen:
            continue
        quote = {s: (wahl.get(g, {}).get(s, 0) + 1) / (n + 2) for s, n in schemata.items()}
        ergebnis[g] = sorted(quote, key=lambda s: (-quote[s], SCHEMA_PRIORITAET.index(s) if s in SCHEMA_PRIORITAET else 99))
    return ergebnis


def baue_candidate_preferences(gewichte: dict[str, float], rangfolge: dict[str, list[str]], diagnose: dict) -> dict:
    """JSON fuer hpg_core/data/candidate_preferences.json: fehlende Faktoren 0,
    Summe exakt 1.0 (Rundungsrest auf den groessten), schema_rang je Genre."""
    block = {f"kandidaten_{f}_weight": round(float(gewichte.get(f, 0.0)), 6) for f in KANDIDATEN_TEILWERTE}
    differenz = 1.0 - sum(block.values())
    groesster = max(block, key=block.get)
    block[groesster] = round(block[groesster] + differenz, 9)
    ergebnis: dict = {"_diagnose": dict(diagnose)}
    for genre in CANONICAL_GENRES:
        ergebnis[genre] = dict(block)
        ergebnis[genre]["schema_rang"] = list(rangfolge.get(genre, []))
    return ergebnis
```

`befehl_fit_kandidaten(args)`: liest CSVs; `genre_von` = Pfad→Genre ueber `lade_tracks_aus_cache` + `loese_genre_auf` (Abgleich `lower()`, Cache-Ausfall → ""); `verbinde_bewertungen_kandidaten(...)`; aktive Merkmale = Teilwerte mit Streuung >= `MIN_KONTROLL_STREUUNG` im Satz; `holdout_nach_tracks(zeilen)` (Bericht: Anteil Holdout-Clips, ≈ 51 % bei 30 % Tracks); **Zielgroesse 1** auf `nur_mit_note(train)`: `zu_zielgroesse(..., aktive)` (liest `"bewertung"`) → `fit_logistic`, `datenlage_urteil`; AUC auf `nur_mit_note(holdout)` mit `m, s = _kennzahlen(X_train)`, `auc(y_hold, _standardisiere_mit(X_hold, m, s) @ beta[1:] + beta[0])`; **Zielgroesse 2** auf `train` (alle Clips): `X_diff, gruppen = paarvergleich_daten(train, aktive)`, `identifizierbar = identifizierbare_merkmale(X_diff, aktive)`, Fit/Bootstrap nur ueber die identifizierbaren Spalten, `trefferquote_paarvergleich` auf Holdout (mit beta = 0 fuer nicht identifizierbare); Gewichte `gewichte_aus_paarvergleich(identifizierbar, intervalle, identifizierbar, get_tolerances(CANONICAL_GENRES[0]))`; Rangfolge `schema_rangfolge(zeilen)`; `uebernahme_erlaubt(...)` → bei True `baue_candidate_preferences` nach `hpg_core/data/candidate_preferences.json` + `candidate_preferences.reset_cache()`, sonst `<dir>/candidate_preferences_entwurf.json` + Grund; Diagnose-Dict (n Clips/Paare Train+Holdout, ohne Note, verworfen, aktive, identifizierbar/nicht, Koeffizienten, Intervalle, AUC, Trefferquote, Basis, Grund); Bericht (Tabelle je Merkmal: Koeffizient, Intervall, identifizierbar ja/nein, Gewicht; AUC; Trefferquote vs. Basis; Rangfolge je Genre; Holdout-Anteil).

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add tools/rate_transitions.py tests/test_rate_transitions.py && git commit -m "feat(hoertest): fit --modus kandidaten — Note + Paarvergleich, Holdout nach Tracks, AUC/Trefferquote, candidate_preferences"`

---

### Task 5: Synthetischer Ende-zu-Ende-Lauf (ohne Menschen), Doku, Waechter Tor 2, Merge

- [ ] **Step 1: Werkzeuglauf `prepare --modus kandidaten`** mit `--anzahl 3 --out <scratchpad>\hoertest_kandidaten_probe` gegen den Cache (Tracks mit Kandidaten). Pflicht: Clips `<pair_id>_k<n>.wav` entstehen, `bewertung.csv`/`merkmale.csv`/`reihenfolge.json`/`LIESMICH-kandidaten.txt` vorhanden, Spalten wie Task 2. Zahlen (Paare, Clips je Paar, Renderzeit je Clip) ins Handoff.
- [ ] **Step 2: Server-Rauchtest** `python tools/hoertest_server.py --dir <probe> --port 8767` im Hintergrund, `GET /daten` liefert Gruppen mit Clips in `reihenfolge.json`-Reihenfolge, `POST /note` und `POST /bester` schreiben `bewertung.csv` (clip_id, note, gewaehlt, zeit); danach beenden. Keine Hoerprobe.
- [ ] **Step 3: `fit --modus kandidaten` auf synthetischen Noten**: Skript im Scratchpad fuellt `bewertung.csv` der Probe deterministisch (Note aus `score`-Spalte: >= Median 4 sonst 2, `gewaehlt` = hoechster Score je Paar) — **nur zum Funktionstest des Fits**; Ausgabe `candidate_preferences_entwurf.json` (Uebernahme-Gate greift bei 3 Paaren nicht) und Bericht mit AUC/Trefferquote. Ergebnisdatei NICHT nach `hpg_core/data/` uebernehmen.
- [ ] **Step 4: Volle Suite** `.\venv312\Scripts\python.exe -m pytest tests/ --tb=short -q` gruen inkl. Coverage-Gate.
- [ ] **Step 5: Doku**: `CLAUDE.md` (Baumliste: `candidate_preferences.py`, `data/candidate_preferences.json`), `.agents/skills/hpg-testing-verification/SKILL.md` + `.claude/...` (Hoertest Kandidatenmodus: Befehle, Dateien, Spalten), `.agents/skills/hpg-mixpoint-engineering/SKILL.md` (+`.claude`: Praeferenz-Vorrang in `score_pair`), Handoff `docs/HANDOFF-<Datum>-kandidaten-teil3.md` mit Zahlen aus Step 1–3 und **Checkliste Hoerproben** (siehe unten).
- [ ] **Step 6: Waechter Tor 2** mit dem Gesamt-Diff gegen dieses Dokument; Auflagen einarbeiten.
- [ ] **Step 7: Commit + Merge** auf `main` ueber superpowers:finishing-a-development-branch (Option 1), Push.

**Checkliste Hoerproben (Mensch, nicht durch den Agenten):**
1. `prepare --modus kandidaten --anzahl 40 --out %USERPROFILE%\Music\HPG-Hoertest-Kandidaten --nur-genre Psytrance` laufen lassen (Dauer: Clips je Paar × Renderzeit aus Step 1).
2. Satz in den Mobil-Ordner kopieren, aktuelle `tools/hoertest_server.py` dazu, Server mit `--port 8767` starten (Start.bat um dritten Server ergaenzen — liegt ausserhalb des Repos).
3. Je Paar alle Clips benoten **und** den besten waehlen; Ziel je Genre mindestens 10 Wahlen je Schema (`MIN_EREIGNISSE_JE_MERKMAL`) und 10 Ereignisse je Merkmal und Klasse.
4. `fit --modus kandidaten --dir <Satz>`; nur bei Uebernahme (Datei `hpg_core/data/candidate_preferences.json` geschrieben) wirken die Gewichte in `score_pair`; sonst Entwurf pruefen.
5. Nach Uebernahme: App-Lauf und Hoerprobe der Rang-1-Kandidaten (Teil 4).

---

## Self-Review (Spec Abschnitt 3 gegen Tasks)

| Spec-Punkt | Task |
|---|---|
| Prepare: Paare wie heute (BPM ≤ 2, overall ≥ 0.70, groove ≥ 0.5, Genre-Filter) | 2 (`sammle_kandidaten`, `filtere_nach_genre`) |
| je Paar alle PairCandidates (max 6×2) als Clip, `pro_eq_swap`, 8 s Vor-/Nachlauf, Pegelfix | 2 (`rendere_kandidat`) |
| Dateiname `<pair_id>_k<n>.wav` | 2 (`clip_id_fuer`) |
| `merkmale.csv` je Clip: alle Teilwerte + schema, blend_bars, t_out, t_in, provenance, confidence | 2 (`MERKMALE_KANDIDATEN_SPALTEN`) |
| Anzeige verdeckt: kein Score, kein Schema; nur Tempo, Genre, Camelot, Blendenbalken | 3 (`lade_uebersicht_kandidaten`, Seite) |
| Server: Seite je Paar, Reihenfolge zufaellig, Seed je Paar gespeichert | 2 (`reihenfolge.json`), 3 |
| Zwei Eingaben: Note 1–5 je Kandidat + "bester"; sofort in `bewertung.csv` (pair_id, clip_id, note, gewaehlt, zeit) | 3 |
| Fit: Zielgroesse 1 (logistisch, gut ≥ 4) | 4 (`fit_logistic`) |
| Fit: Zielgroesse 2 Paarvergleich (Bradley-Terry/konditionale Logistik, Differenzen) | 4 (`paarvergleich_daten`, `fit_paarvergleich`) |
| Datenlage-Gate 10 je Merkmal und Klasse | 4 (`datenlage_urteil`) |
| Ergebnis: Gewichte fuer Abschnitt 2 + Rangfolge je Genre → `candidate_preferences.json` | 1 (Lader/Vorrang), 4 (`baue_candidate_preferences`) |
| Holdout nach Tracks; AUC/Trefferquote; sonst nicht uebernehmen | 4 (`holdout_nach_tracks`, `auc`, `trefferquote_paarvergleich`, Gate) |
| Mobil: gleicher Mechanismus, neuer Modus automatisch | 3 (Moduserkennung), 2 (LIESMICH), Checkliste |
| 12 Clips je Paar → weniger Paare je Satz; Satz 1 bleibt | 2 (`--anzahl` = Paare), Entscheidung 14 |
| Hoerzeit-Engpass | Checkliste |

Placeholder-Scan: keine TBD/TODO. Typen: `verbinde_bewertungen_kandidaten -> (list[dict], int, int)`, `paarvergleich_daten -> (X, y, gruppen)`, `fit_paarvergleich -> np.ndarray`, `holdout_nach_tracks -> (train, holdout)`, `auc -> float|None`, `schema_rangfolge -> dict[str, list[str]]`, `baue_candidate_preferences -> dict`; Server `merge_kandidaten_bewertung(zeilen, *, pair_id, clip_id, note=None, bester=False, zeit="")`, `lade_uebersicht_kandidaten(merk, bew, reihenfolge, infos)`.
