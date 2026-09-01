"""
Tests fuer alle 10 Playlist-Sortierstrategien.
Prueft ob jede Strategie korrekt sortiert und keine Tracks verliert.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import Mock
import hpg_core.playlist as playlist_mod
from hpg_core.playlist import (
  calculate_enhanced_compatibility, generate_playlist, STRATEGIES,
  STRATEGY_ALIASES, _sort_context_flow, _sort_genre_flow,
  _sort_harmonic_flow, _sort_peak_time,
  _sort_energy_wave, _remove_track, ENERGY_WAVE_FENSTER,
  _process_dj_brain_recommendations,
)
from hpg_core.models import effective_bpm_diff
from tests.fixtures.track_factories import (
  make_track, make_house_track, make_dj_set,
)


@pytest.fixture
def mixed_set():
  """8 Tracks mit verschiedenen BPM, Keys und Energy."""
  return make_dj_set()


@pytest.fixture
def same_key_set():
  """4 Tracks mit gleichem Key aber unterschiedlichem BPM."""
  return [
    make_track(camelotCode="8A", bpm=120.0, energy=50, title="Low BPM"),
    make_track(camelotCode="8A", bpm=126.0, energy=60, title="Mid BPM"),
    make_track(camelotCode="8A", bpm=128.0, energy=75, title="House BPM"),
    make_track(camelotCode="8A", bpm=130.0, energy=85, title="High BPM"),
  ]


class TestAllStrategiesExist:
  """Alle 8 Strategien sind registriert (Merge 11 -> 8, 2026-07-17)."""

  def test_8_strategies_available(self):
    """Genau 8 Strategien in STRATEGIES (nach Enhanced/EJ-Merge)."""
    assert len(STRATEGIES) == 8

  @pytest.mark.parametrize("name", [
    "Harmonic Flow", "Warm-Up", "Cool-Down", "Peak-Time",
    "Energy Wave", "Genre Flow", "Consistent", "Context Flow",
  ])
  def test_strategy_registered(self, name):
    """Strategie ist in STRATEGIES registriert."""
    assert name in STRATEGIES, f"Strategie '{name}' fehlt"

  @pytest.mark.parametrize("old_name,new_name", [
    ("Harmonic Flow Enhanced", "Harmonic Flow"),
    ("Peak-Time Enhanced", "Peak-Time"),
    ("Emotional Journey", "Context Flow"),
  ])
  def test_alte_namen_als_alias(self, old_name, new_name):
    """Alte Strategie-Namen bleiben via STRATEGY_ALIASES gueltig."""
    assert STRATEGY_ALIASES[old_name] == new_name
    assert new_name in STRATEGIES

  @pytest.mark.parametrize("old_name", [
    "Harmonic Flow Enhanced", "Peak-Time Enhanced", "Emotional Journey",
  ])
  def test_alias_generiert_playlist(self, old_name):
    """generate_playlist akzeptiert alte Namen (Backward-Compat)."""
    tracks = make_dj_set()
    result = generate_playlist(tracks[:], old_name, bpm_tolerance=6.0)
    assert len(result) > 0


class TestStrategyBasicProperties:
  """Grundeigenschaften aller Strategien."""

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_no_crash_with_mixed_set(self, mixed_set, strategy):
    """Kein Crash mit gemischtem Set."""
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    assert isinstance(result, list)

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_output_not_empty(self, mixed_set, strategy):
    """Ergebnis ist nicht leer."""
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    assert len(result) > 0


  def test_genre_flow_nutzt_gemeinsame_genre_aufloesung(self, monkeypatch):
    tracks = [
      make_track(title="Fallback Psy", detected_genre=" unknown ", genre="Psytrance"),
      make_track(title="Detected Psy", detected_genre="Psytrance", genre="Techno"),
      make_track(title="Trance", detected_genre="Trance", genre="Trance"),
    ]
    monkeypatch.setattr(
      playlist_mod,
      "get_genre_compatibility",
      lambda _left, right: 1.0 if right == "Trance" else 0.0,
    )

    result = _sort_genre_flow(tracks, 2.0, genre_weight=1.0)

    assert {track.title for track in result[:2]} == {
      "Fallback Psy", "Detected Psy"
    }
    assert result[2].title == "Trance"

  def test_dj_brain_dispatch_nutzt_id3_genre_fallback(self, monkeypatch):
    current = make_track(detected_genre="Unknown", genre="Psytrance")
    upcoming = make_track(detected_genre="Unknown", genre="Trance")
    recommendation = SimpleNamespace(
      mix_technique="Blend",
      eq_advice="EQ",
      transition_bars=16,
      structure_note="",
      genre_pair="Psytrance -> Trance",
      risk_notes=[],
      bpm_advice="",
      key_advice="",
      energy_advice="",
      gain_advice="",
      overlap_seconds=0.0,
    )
    generate = Mock(return_value=recommendation)
    monkeypatch.setattr(playlist_mod, "generate_dj_recommendation", generate)

    result, _notes, _overlap = _process_dj_brain_recommendations(
      current, upcoming
    )

    assert result is recommendation
    generate.assert_called_once_with(current, upcoming)

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_no_duplicates(self, mixed_set, strategy):
    """Keine duplizierten Tracks."""
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    paths = [t.filePath for t in result]
    assert len(paths) == len(set(paths)), (
      f"Strategie '{strategy}': Duplikate gefunden"
    )

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_track_count_preserved_or_filtered(self, mixed_set, strategy):
    """Tracks werden nicht hinzugefuegt (nur gefiltert)."""
    input_count = len(mixed_set)
    result = generate_playlist(mixed_set[:], strategy, bpm_tolerance=6.0)
    assert len(result) <= input_count


class TestWarmUp:
  """Warm-Up: BPM aufsteigend."""

  def test_bpm_ascending(self, same_key_set):
    """BPM muss aufsteigend sortiert sein."""
    result = generate_playlist(same_key_set, "Warm-Up", bpm_tolerance=15.0)
    bpms = [t.bpm for t in result]
    for i in range(len(bpms) - 1):
      assert bpms[i] <= bpms[i + 1], (
        f"Nicht aufsteigend bei Index {i}: {bpms[i]} > {bpms[i + 1]}"
      )

  def test_first_track_lowest_bpm(self, same_key_set):
    """Erster Track hat niedrigsten BPM."""
    result = generate_playlist(same_key_set, "Warm-Up", bpm_tolerance=15.0)
    if len(result) >= 2:
      assert result[0].bpm <= result[1].bpm


class TestCoolDown:
  """Cool-Down: BPM absteigend."""

  def test_bpm_descending(self, same_key_set):
    """BPM muss absteigend sortiert sein."""
    result = generate_playlist(same_key_set, "Cool-Down", bpm_tolerance=15.0)
    bpms = [t.bpm for t in result]
    for i in range(len(bpms) - 1):
      assert bpms[i] >= bpms[i + 1], (
        f"Nicht absteigend bei Index {i}: {bpms[i]} < {bpms[i + 1]}"
      )

  def test_first_track_highest_bpm(self, same_key_set):
    """Erster Track hat hoechsten BPM."""
    result = generate_playlist(same_key_set, "Cool-Down", bpm_tolerance=15.0)
    if len(result) >= 2:
      assert result[0].bpm >= result[1].bpm


class TestHarmonicFlow:
  """Harmonic Flow: Nachbarkeys bevorzugen."""

  def test_compatible_transitions(self, mixed_set):
    """Aufeinanderfolgende Tracks sollten kompatibel sein."""
    from hpg_core.playlist import calculate_compatibility
    result = generate_playlist(mixed_set[:], "Harmonic Flow", bpm_tolerance=6.0)
    if len(result) >= 2:
      compat_count = 0
      for i in range(len(result) - 1):
        score = calculate_compatibility(result[i], result[i + 1], 6.0)
        if score > 0:
          compat_count += 1
      # Mindestens 50% der Uebergaenge sollten kompatibel sein
      ratio = compat_count / (len(result) - 1)
      assert ratio >= 0.3, f"Nur {ratio:.0%} kompatible Uebergaenge"


class TestPeakTime:
  """Peak-Time: Energie steigt, dann faellt."""

  def test_returns_valid_playlist(self, mixed_set):
    """Peak-Time gibt valide Playlist zurueck."""
    result = generate_playlist(mixed_set[:], "Peak-Time", bpm_tolerance=6.0)
    assert len(result) > 0


def _small_track(title, *, bpm=128.0, energy=50, camelot="8A", genre="Techno"):
  return make_track(
    filePath=f"/test/small-{title}.mp3",
    fileName=f"small-{title}.mp3",
    title=title,
    bpm=bpm,
    energy=energy,
    camelotCode=camelot,
    genre=genre,
    detected_genre=genre,
  )


class TestSmallPoolStrategyContracts:
  def test_context_flow_empty_pool_bleibt_gueltig(self):
    assert _sort_context_flow([], 2.0, energy_direction="Cool Down") == []

  @pytest.mark.parametrize(
    ("params", "expected"),
    [
      ({"harmonic_strictness": 10, "allow_experimental": False}, ["B", "A"]),
      ({"harmonic_strictness": 3, "allow_experimental": True}, ["A", "B"]),
    ],
  )
  def test_harmonic_flow_two_tracks_uses_full_objective_for_both_inputs(
    self, monkeypatch, params, expected
  ):
    a, b = _small_track("A"), _small_track("B")

    def objective(left, right, _tolerance, **kwargs):
      strict = kwargs["harmonic_strictness"] == 10
      experimental = kwargs["allow_experimental"] is True
      preferred = (left.title, right.title) == (
        ("B", "A") if strict and not experimental else ("A", "B")
      )
      return 90 if preferred else 10

    monkeypatch.setattr("hpg_core.playlist.calculate_transition_objective", objective)
    for pool in ([a, b], [b, a]):
      result = _sort_harmonic_flow(pool, 2.0, **params)
      assert [track.title for track in result] == expected

  @pytest.mark.parametrize(
    ("direction", "expected"),
    [
      ("Build Up", ["Low", "High"]),
      ("Cool Down", ["High", "Low"]),
      ("down", ["High", "Low"]),
    ],
  )
  def test_context_flow_two_tracks_honors_energy_direction_for_both_inputs(
    self, direction, expected
  ):
    low = _small_track("Low", energy=20)
    high = _small_track("High", energy=90)
    for pool in ([low, high], [high, low]):
      result = _sort_context_flow(pool, 2.0, energy_direction=direction)
      assert [track.title for track in result] == expected

  def test_context_flow_two_tracks_honors_maintain_and_harmonic_params(
    self, monkeypatch
  ):
    a, b = _small_track("A"), _small_track("B")

    def compatibility(left, right, _tolerance, **kwargs):
      preferred = (left.title, right.title) == (
        ("B", "A")
        if kwargs["harmonic_strictness"] == 10
        and kwargs["allow_experimental"] is False
        else ("A", "B")
      )
      return 90 if preferred else 10

    monkeypatch.setattr("hpg_core.playlist.calculate_compatibility", compatibility)
    for pool in ([a, b], [b, a]):
      strict = _sort_context_flow(
        pool, 2.0, energy_direction="Maintain",
        harmonic_strictness=10, allow_experimental=False,
      )
      loose = _sort_context_flow(
        pool, 2.0, energy_direction="Maintain",
        harmonic_strictness=3, allow_experimental=True,
      )
      assert [track.title for track in strict] == ["B", "A"]
      assert [track.title for track in loose] == ["A", "B"]

  def test_context_flow_two_tracks_honors_genre_weight(self, monkeypatch):
    a = _small_track("A", genre="Techno")
    b = _small_track("B", genre="Trance")
    monkeypatch.setattr(
      "hpg_core.playlist.calculate_compatibility",
      lambda left, right, *_args, **_kwargs:
        90 if (left.title, right.title) == ("A", "B") else 80,
    )
    monkeypatch.setattr(
      "hpg_core.playlist.get_genre_compatibility",
      lambda left, right:
        1.0 if (left, right) == ("Trance", "Techno") else 0.0,
    )

    no_genre = _sort_context_flow(
      [b, a], 2.0, energy_direction="Maintain",
      genre_mixing=True, genre_weight=0.0,
    )
    genre_first = _sort_context_flow(
      [a, b], 2.0, energy_direction="Maintain",
      genre_mixing=True, genre_weight=1.0,
    )

    assert [track.title for track in no_genre] == ["A", "B"]
    assert [track.title for track in genre_first] == ["B", "A"]

  def test_peak_time_three_tracks_honors_peak_position_for_both_inputs(
    self, monkeypatch
  ):
    tracks = [
      _small_track("Low", energy=10),
      _small_track("Mid", energy=50),
      _small_track("High", energy=90),
    ]
    monkeypatch.setattr(
      "hpg_core.playlist.calculate_transition_objective",
      lambda *_args, **_kwargs: 100,
    )

    for pool in (tracks, list(reversed(tracks))):
      early = _sort_peak_time(pool, 2.0, peak_position=40)
      late = _sort_peak_time(pool, 2.0, peak_position=80)
      assert [track.title for track in early].index("High") < [
        track.title for track in late
      ].index("High")

  def test_peak_time_three_tracks_honors_bpm_gate(self, monkeypatch):
    tracks = [
      _small_track("100", bpm=100.0),
      _small_track("101", bpm=101.0),
      _small_track("102", bpm=102.0),
    ]
    monkeypatch.setattr(
      "hpg_core.playlist.calculate_transition_objective",
      lambda left, right, tolerance, **_kwargs:
        50 if abs(left.bpm - right.bpm) <= tolerance else 0,
    )

    for pool in (tracks, list(reversed(tracks))):
      result = _sort_peak_time(pool, 1.1, peak_position=70)
      assert all(
        abs(left.bpm - right.bpm) <= 1.1
        for left, right in zip(result, result[1:])
      )

  def test_peak_time_harmonic_params_break_equal_curve_ties(self, monkeypatch):
    a, b = _small_track("A"), _small_track("B")

    def objective(left, right, _tolerance, **kwargs):
      preferred = (left.title, right.title) == (
        ("B", "A")
        if kwargs["harmonic_strictness"] == 10
        and kwargs["allow_experimental"] is False
        else ("A", "B")
      )
      return 90 if preferred else 10

    monkeypatch.setattr("hpg_core.playlist.calculate_transition_objective", objective)
    for pool in ([a, b], [b, a]):
      strict = _sort_peak_time(
        pool, 2.0, peak_position=70,
        harmonic_strictness=10, allow_experimental=False,
      )
      loose = _sort_peak_time(
        pool, 2.0, peak_position=70,
        harmonic_strictness=3, allow_experimental=True,
      )
      assert [track.title for track in strict] == ["B", "A"]
      assert [track.title for track in loose] == ["A", "B"]

  def test_genre_flow_two_tracks_honors_mixing_weight_and_harmony(self, monkeypatch):
    a = _small_track("A", genre="Techno")
    b = _small_track("B", genre="Trance")
    monkeypatch.setattr(
      "hpg_core.playlist.calculate_compatibility",
      lambda left, right, *_args, **kwargs:
        (90 if (left.title, right.title) == ("A", "B") else 80)
        if kwargs.get("harmonic_strictness", 7) >= 7
        else (70 if (left.title, right.title) == ("B", "A") else 60),
    )
    monkeypatch.setattr(
      "hpg_core.playlist.get_genre_compatibility",
      lambda left, right:
        1.0 if (left, right) == ("Trance", "Techno") else 0.0,
    )

    for pool in ([a, b], [b, a]):
      harmonic = _sort_genre_flow(
        pool, 2.0, genre_mixing=False,
        harmonic_strictness=10, allow_experimental=False,
      )
      transition_first = _sort_genre_flow(
        pool, 2.0, genre_mixing=True, genre_weight=0.0,
        harmonic_strictness=10, allow_experimental=False,
      )
      genre_first = _sort_genre_flow(
        pool, 2.0, genre_mixing=True, genre_weight=1.0,
        harmonic_strictness=10, allow_experimental=False,
      )
      assert [track.title for track in harmonic] == ["A", "B"]
      assert [track.title for track in transition_first] == ["A", "B"]
      assert [track.title for track in genre_first] == ["B", "A"]

  def test_genre_flow_mehrtrack_ohne_genre_mixing_delegiert_harmonic(self, monkeypatch):
    tracks = [
      _small_track("A", genre="Techno"),
      _small_track("B", genre="Trance"),
      _small_track("C", genre="House"),
    ]
    expected = list(reversed(tracks))
    calls = []
    cancel_check = lambda: None

    def harmonic(received_tracks, tolerance, **kwargs):
      calls.append((received_tracks, tolerance, kwargs))
      return expected

    monkeypatch.setattr("hpg_core.playlist._sort_harmonic_flow", harmonic)

    result = _sort_genre_flow(
      tracks,
      1.75,
      genre_mixing=False,
      genre_weight=1.0,
      harmonic_strictness=9,
      allow_experimental=False,
      cancel_check=cancel_check,
    )

    assert result is expected
    assert len(calls) == 1
    received_tracks, tolerance, kwargs = calls[0]
    assert received_tracks is tracks
    assert tolerance == 1.75
    assert kwargs == {
      "genre_mixing": False,
      "genre_weight": 1.0,
      "harmonic_strictness": 9,
      "allow_experimental": False,
      "cancel_check": cancel_check,
    }


class TestEdgeCases:
  """Edge Cases fuer alle Strategien."""

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_empty_input(self, strategy):
    """Leere Eingabe = leere Ausgabe."""
    result = generate_playlist([], strategy, bpm_tolerance=3.0)
    assert result == []

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_single_track(self, strategy):
    """Ein Track = ein Track zurueck."""
    tracks = [make_house_track()]
    result = generate_playlist(tracks, strategy, bpm_tolerance=3.0)
    assert result == tracks

  @pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
  def test_two_tracks(self, strategy):
    """Zwei Tracks = kein Crash."""
    tracks = [
      make_track(camelotCode="8A", bpm=128.0, energy=70),
      make_track(camelotCode="9A", bpm=128.0, energy=72),
    ]
    result = generate_playlist(tracks, strategy, bpm_tolerance=3.0)
    assert len(result) > 0

  def test_unknown_strategy_is_rejected(self, mixed_set):
    """Unbekannte Strategien duerfen nicht still anders ausgefuehrt werden."""
    with pytest.raises(ValueError, match="Playlist-Strategie"):
      generate_playlist(mixed_set[:], "NonExistent", bpm_tolerance=6.0)

  def test_tracks_without_camelot_code(self):
    """Fehlende lokale Kandidaten duerfen analysierte Tracks nicht entfernen."""
    tracks = [
      make_track(camelotCode="", bpm=128.0),
      make_track(camelotCode="8A", bpm=128.0),
    ]
    result = generate_playlist(tracks, "Harmonic Flow", bpm_tolerance=3.0)
    assert len(result) == 2

  def test_tracks_with_zero_bpm_filtered(self):
    """Tracks mit BPM 0 werden gefiltert."""
    tracks = [
      make_track(camelotCode="8A", bpm=0.0),
      make_track(camelotCode="8A", bpm=128.0),
    ]
    result = generate_playlist(tracks, "Harmonic Flow", bpm_tolerance=3.0)
    valid_bpms = [t.bpm for t in result if t.bpm > 0]
    assert len(valid_bpms) >= 1

  @pytest.mark.parametrize("invalid_bpm", [float("nan"), float("inf"), -float("inf")])
  def test_tracks_with_non_finite_bpm_filtered(self, invalid_bpm):
    invalid = make_track(camelotCode="8A", bpm=invalid_bpm)
    valid = make_track(camelotCode="8A", bpm=128.0, title="valid")

    result = generate_playlist([invalid, valid], "Harmonic Flow", bpm_tolerance=3.0)

    assert result == [valid]

  def test_all_invalid_bpms_return_empty_playlist(self):
    tracks = [
      make_track(camelotCode="8A", bpm=0.0),
      make_track(camelotCode="8A", bpm=float("nan")),
    ]

    assert generate_playlist(tracks, "Harmonic Flow", bpm_tolerance=3.0) == []

  @pytest.mark.parametrize("strategy", sorted(STRATEGIES))
  @pytest.mark.parametrize(
    "status", ["unknown", "mismatch", "unverifiable", "unsupported"]
  )
  def test_beatgrid_status_entfernt_tracks_nicht_aus_strategien(
    self, strategy, status, monkeypatch
  ):
    monkeypatch.setattr(
      "hpg_core.playlist.calculate_transition_objective",
      lambda *args, **kwargs: 100,
    )
    invalid = make_track(camelotCode="8A", bpm=128.0, title="invalid")
    invalid.analysis_mode = "full"
    invalid.beatgrid_source = "rekordbox"
    invalid.beatgrid_status = status
    valid = make_track(camelotCode="8A", bpm=128.0, title="valid")
    valid.analysis_mode = "full"
    valid.beatgrid_source = "audio"
    valid.beatgrid_status = "verified"

    result = generate_playlist([invalid, valid], strategy, bpm_tolerance=3.0)

    assert {track.title for track in result} == {"invalid", "valid"}

  def test_beatgrid_status_nullt_scoring_nicht(self, monkeypatch):
    first = make_track(camelotCode="8A", bpm=128.0, title="first")
    second = make_track(camelotCode="8A", bpm=128.0, title="second")
    for track in (first, second):
      track.analysis_mode = "full"
      track.beatgrid_source = "audio"
      track.beatgrid_status = "verified"
    second.beatgrid_status = "mismatch"

    monkeypatch.setattr(
      "hpg_core.playlist._kandidaten_fuer_paar",
      lambda *args, **kwargs: [type("K", (), {
        "score": 0.8,
        "teilwerte": {name: 0.8 for name in (
          "harmonic", "bpm", "energy", "genre", "groove", "bass",
          "timbre", "mood", "loudness", "structure",
        )},
        "to_dict": lambda self: {},
      })()],
    )
    metrics = calculate_enhanced_compatibility(first, second, bpm_tolerance=3.0)

    assert metrics.overall_score > 0.0

  def test_harmonic_flow_fallback_prefers_half_time(self, monkeypatch):
    """Fallback wählt Half-Time (effektive BPM-Differenz) statt roher Distanz.

    Strategien-Merge 2026-07-17: der Half/Double-bewusste Fallback wurde aus
    der Plain-Variante in die Lookahead-Implementierung portiert. Nach dem
    Start-Track (120) muss der 60-BPM-Track (effektive Diff 0 via Half-Time)
    vor dem 90-BPM-Track (Diff 30) kommen.
    """
    tracks = [
      make_track(camelotCode="8A", bpm=120.0, energy=60, title="A"),
      make_track(camelotCode="8A", bpm=60.0, energy=60, title="B"),
      make_track(camelotCode="8A", bpm=90.0, energy=60, title="C"),
    ]

    monkeypatch.setattr(
      "hpg_core.playlist.calculate_compatibility",
      lambda *args, **kwargs: 0,
    )

    result = _sort_harmonic_flow(tracks, bpm_tolerance=3.0)
    bpms = [t.bpm for t in result]
    # Half-Time-Partner (60/120) muessen direkt aufeinander folgen
    idx_120, idx_60 = bpms.index(120.0), bpms.index(60.0)
    assert abs(idx_120 - idx_60) == 1, f"Reihenfolge: {bpms}"


def test_strategy_config_filtert_gueltige_sichtbare_parameter():
  from hpg_core.playlist import StrategyConfig

  config = StrategyConfig.from_mapping(
    {"peak_position": 80, "genre_weight": 0.0}
  )

  assert config.peak_position == 80
  assert config.genre_weight == 0.0
  assert set(config.effective_kwargs("Peak-Time")) == {
    "peak_position", "harmonic_strictness", "allow_experimental"
  }


@pytest.mark.parametrize(
  "params",
  [
    {"peak_position": 999},
    {"genre_weight": -2},
  ],
)
def test_strategy_config_verwirft_statt_zu_clampen(params):
  from hpg_core.playlist import StrategyConfig

  with pytest.raises(ValueError, match="advanced_params"):
    StrategyConfig.from_mapping(params)


def test_strategy_config_verwirft_wirkungslosen_overlap_parameter():
  from hpg_core.playlist import StrategyConfig

  with pytest.raises(ValueError, match="unbekannte Schluessel.*overlap"):
    StrategyConfig.from_mapping({"overlap": 16})


class TestDuplicateTrackReferences:
  """Regression: dieselbe Track-Instanz mehrfach in der Eingabeliste.

  Audit 2026-08-14: In _sort_directional_bpm (Warm-Up/Cool-Down) passte der
  Guard ``len(remaining) > 1`` nicht zum Filter ``other is not candidate``.
  Standen zwei Referenzen auf DASSELBE Track-Objekt in derselben BPM-Gruppe,
  filterte der Generator alle Kandidaten heraus und ``max()`` lief auf einer
  leeren Sequenz -> ValueError mitten in der Generierung.
  """

  @pytest.fixture(autouse=True)
  def _lokale_kanten(self, monkeypatch):
    monkeypatch.setattr(
      "hpg_core.playlist.calculate_transition_objective",
      lambda *args, **kwargs: 100,
    )

  def test_remove_track_entfernt_nur_exakt_die_zielinstanz(self):
    first = make_track(filePath="C:/music/same.wav", title="First")
    target = make_track(filePath="C:/music/same.wav", title="Target")
    assert first == target
    assert first.track_id == target.track_id
    items = [first, target]

    _remove_track(items, target)

    assert len(items) == 1
    assert items[0] is first

  def test_remove_track_verwirft_keine_pfadgleiche_ersatzinstanz(self):
    existing = make_track(filePath="C:/music/same.wav", title="Existing")
    missing = make_track(filePath="C:/music/same.wav", title="Missing")
    items = [existing]

    with pytest.raises(ValueError, match="nicht in der Arbeitsliste"):
      _remove_track(items, missing)

    assert len(items) == 1
    assert items[0] is existing

  @pytest.mark.parametrize("strategy", sorted(STRATEGIES))
  def test_same_instance_three_times(self, strategy):
    """Dieselbe Instanz 3x, identische BPM -> kein Crash, nichts verloren."""
    track = make_track(camelotCode="8A", bpm=138.0, energy=70, title="Dupe")
    tracks = [track, track, track]
    result = generate_playlist(tracks, strategy, bpm_tolerance=3.0)
    assert len(result) == 3

  @pytest.mark.parametrize("strategy", sorted(STRATEGIES))
  def test_duplicate_plus_distinct_same_bpm(self, strategy):
    """Doppelte Instanz + fremder Track bei gleicher BPM."""
    dupe = make_track(camelotCode="8A", bpm=138.0, energy=70, title="Dupe")
    other = make_track(camelotCode="9A", bpm=138.0, energy=75, title="Other")
    result = generate_playlist([dupe, dupe, other], strategy, bpm_tolerance=3.0)
    assert len(result) == 3

  @pytest.mark.parametrize("strategy", sorted(STRATEGIES))
  def test_partially_duplicated_set(self, strategy):
    """Groesseres Set mit mehreren doppelten Instanzen."""
    base = make_dj_set()
    tracks = list(base) + list(base[:3])
    result = generate_playlist(tracks, strategy, bpm_tolerance=100.0)
    assert len(result) == len(tracks)


class TestEnergyWaveBpmNaehe:
  """Energy Wave beruecksichtigt seit 2026-08-20 die BPM-Naehe.

  Vorher sortierte die Strategie ausschliesslich nach `track.energy` und
  nahm `bpm_tolerance` entgegen, ohne sie zu benutzen: an einem Pool von 80
  Tracks mit 93-146 BPM waren dadurch 63 % der Nachbarpaare unmixbar. Vor
  dieser Klasse gab es KEINEN Test, der die Reihenfolge von Energy Wave
  geprueft haette — ein Rueckbau waere lautlos geblieben.
  """

  def _wellen_pool(self, anzahl=10):
    """Energie und BPM absichtlich gegenlaeufig: wer nur nach Energie
    sortiert, springt zwangslaeufig durch das ganze BPM-Feld.

    Jeder Track bekommt einen EIGENEN filePath — Track vergleicht sich ueber
    track_id (den Pfad), und die Fixture vergibt sonst fuer alle denselben.
    """
    return [
      make_track(
        camelotCode="8A",
        bpm=128.0 if i % 2 == 0 else 140.0,
        energy=(i + 1) * (100 // anzahl),
        title=f"T{i}",
        filePath=f"/test/wave_{i}.mp3",
      )
      for i in range(anzahl)
    ]

  def _mittlerer_bpm_sprung(self, ordnung):
    spruenge = [
      effective_bpm_diff(a.bpm, b.bpm)[0] for a, b in zip(ordnung, ordnung[1:])
    ]
    return sum(spruenge) / len(spruenge)

  def test_bpm_spruenge_werden_kleiner(self):
    """Der Kern der Aenderung.

    Die Schwelle ist so gesetzt, dass das ALTE Verhalten durchfaellt: mit
    Fenster 1 liegt der mittlere Sprung an diesem Pool bei 6,67, mit dem
    aktuellen Fenster bei 1,33. Eine grosszuegigere Schwelle (etwa 12) waere
    wirkungslos — sie bestuende auch bei reiner Energiesortierung.
    """
    ordnung = _sort_energy_wave(self._wellen_pool(), 3.0)
    assert self._mittlerer_bpm_sprung(ordnung) < 3.0

  def test_altes_verhalten_faellt_durch(self, monkeypatch):
    """Gegenprobe: mit Fenster 1 ist die Strategie wieder BPM-blind.

    Ohne diesen Test laesst sich nicht unterscheiden, ob die Schwelle oben
    die Aenderung misst oder ohnehin gilt.
    """
    import hpg_core.playlist as pl
    monkeypatch.setattr(pl, "ENERGY_WAVE_FENSTER", 1)
    ordnung = pl._sort_energy_wave(self._wellen_pool(), 3.0)
    assert self._mittlerer_bpm_sprung(ordnung) > 3.0

  def test_kein_track_geht_verloren(self):
    pool = self._wellen_pool()
    ordnung = _sort_energy_wave(list(pool), 3.0)
    assert len(ordnung) == len(pool)
    assert {t.title for t in ordnung} == {t.title for t in pool}

  def test_welle_beginnt_in_der_mitte(self):
    """Die Dramaturgie bleibt: Start bei mittlerer Energie, dann wachsende
    Ausschlaege. Wird das aufgegeben, ist es keine Welle mehr."""
    pool = self._wellen_pool()
    ordnung = _sort_energy_wave(list(pool), 3.0)
    energien = [t.energy for t in ordnung]
    start = energien[0]
    assert min(energien) < start < max(energien)
    # Der Abstand zur Startenergie waechst ueber die Position
    abstaende = [abs(e - start) for e in energien]
    erste_haelfte = sum(abstaende[: len(abstaende) // 2])
    zweite_haelfte = sum(abstaende[len(abstaende) // 2 :])
    assert zweite_haelfte > erste_haelfte

  def test_energie_alterniert(self):
    pool = self._wellen_pool()
    ordnung = _sort_energy_wave(list(pool), 3.0)
    energien = [t.energy for t in ordnung]
    richtungen = [
      1 if b > a else -1 for a, b in zip(energien, energien[1:])
    ]
    wechsel = sum(1 for a, b in zip(richtungen, richtungen[1:]) if a != b)
    # Bei alternierender Auswahl wechselt die Richtung fast jeden Schritt
    assert wechsel >= len(richtungen) - 3

  def test_fenster_ist_gesetzt_und_plausibel(self):
    """1 waere das alte Verhalten, sehr grosse Werte zerstoeren die Welle."""
    assert 2 <= ENERGY_WAVE_FENSTER <= 16

  def test_freie_wahl_wuerde_den_aufbau_zerstoeren(self, monkeypatch):
    """Der Grund fuer das Fenster, an einem Pool der gross genug ist.

    Die Welle soll vom Zentrum aus immer weiter ausschlagen. Gemessen als
    Korrelation zwischen Position und Abstand zur Startenergie. Bei freier
    Wahl ueber die ganze Seite bricht dieser Aufbau zusammen — genau
    deshalb ist ENERGY_WAVE_FENSTER begrenzt und nicht unendlich.
    """
    import hpg_core.playlist as pl

    def aufbau(fenster):
      monkeypatch.setattr(pl, "ENERGY_WAVE_FENSTER", fenster)
      ordnung = pl._sort_energy_wave(self._wellen_pool(anzahl=40), 3.0)
      energien = [float(t.energy) for t in ordnung]
      abstaende = [abs(e - energien[0]) for e in energien]
      n = len(abstaende)
      mittel_pos = (n - 1) / 2
      mittel_ab = sum(abstaende) / n
      zaehler = sum((i - mittel_pos) * (a - mittel_ab)
                    for i, a in enumerate(abstaende))
      nenner = (sum((i - mittel_pos) ** 2 for i in range(n)) ** 0.5
                * sum((a - mittel_ab) ** 2 for a in abstaende) ** 0.5)
      return zaehler / nenner if nenner else 0.0

    mit_fenster = aufbau(ENERGY_WAVE_FENSTER)
    frei = aufbau(10_000)
    assert mit_fenster > frei
    assert mit_fenster > 0.3

  def test_kurze_listen_unveraendert(self):
    zwei = [
      make_track(camelotCode="8A", bpm=128.0, energy=30, title="A"),
      make_track(camelotCode="8A", bpm=140.0, energy=70, title="B"),
    ]
    assert [t.title for t in _sort_energy_wave(zwei, 3.0)] == ["A", "B"]
    assert _sort_energy_wave([], 3.0) == []
