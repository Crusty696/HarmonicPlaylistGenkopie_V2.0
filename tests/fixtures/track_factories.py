"""
Track-Factory fuer schnelle Test-Erstellung.
Erzeugt vorkonfigurierte Track-Objekte mit DJ-realistischen Werten.
"""
import math

from hpg_core.models import Track, CAMELOT_MAP
from hpg_core.mix_candidates import MixCandidate


def _lokaler_kandidat(t: float, camelot: str, energy: int) -> MixCandidate:
  muster = [0.8 if index % 4 == 0 else 0.0 for index in range(16)]
  return MixCandidate(
    t=t, schema=["pssi_phrase"], section_label="main", phrase_label="Chorus",
    neuheit=0.7, traegt_allein=True, groove_pattern_lokal=muster,
    bass_pattern_lokal=muster, syncopation_lokal=0.2,
    percussive_ratio_lokal=0.5, sub_energy=0.5, bass_punch=2.0,
    bass_rms_dbfs=-20.0, kick_aktiv=False, camelot_lokal=camelot,
    key_confidence_lokal=0.9, timbre_fingerprint_lokal=[1.0, 0.5, 0.2],
    brightness_lokal=50, flatness_lokal=0.1, avg_mids_lokal=40.0,
    avg_highs_lokal=20.0, energy_lokal=energy, energy_trend="stable",
    lufs_lokal=-10.0,
    mood={"pssi_mood": 1, "brightness": 50, "flatness": 0.1,
          "key_mode": "Minor"},
    vocal_aktiv_lokal=False,
  )


def make_track(**overrides) -> Track:
  """Erstellt einen Track mit sinnvollen DJ-Defaults.

  Alle Felder koennen ueberschrieben werden.

  Beispiel:
    track = make_track(bpm=128.0, camelotCode="8A", energy=75)
  """
  defaults = {
    "filePath": "/test/track.mp3",
    "fileName": "Test Artist - Test Track.mp3",
    "artist": "Test Artist",
    "title": "Test Track",
    "genre": "Tech House",
    "detected_genre": "Tech House",
    "duration": 300.0,  # 5 Minuten - Standard DJ-Track
    "bpm": 128.0,
    "keyNote": "A",
    "keyMode": "Minor",
    "camelotCode": "8A",
    "energy": 70,
    "bass_intensity": 60,
    "mix_in_point": 30.0,   # ~16 Bars bei 128 BPM
    "mix_out_point": 270.0,  # ~144 Bars bei 128 BPM
    "mix_in_bars": 16,
    "mix_out_bars": 144,
  }
  defaults.update(overrides)
  track = Track(**defaults)
  if (
    "mix_in_candidates" not in overrides and "mix_out_candidates" not in overrides
    and math.isfinite(float(track.bpm or 0.0))
    and float(track.bpm or 0.0) > 0.0
  ):
    grid = (60.0 / float(track.bpm)) * 4 * int(track.phrase_unit or 8)
    if "sections" not in overrides:
      track.sections = [
        {"label": "intro", "start_time": 0.0, "end_time": 2 * grid, "avg_energy": 30},
        {"label": "main", "start_time": 2 * grid, "end_time": 14 * grid, "avg_energy": track.energy},
        {"label": "outro", "start_time": 14 * grid, "end_time": track.duration, "avg_energy": 30},
      ]
    if "outro_covered" not in overrides:
      track.outro_covered = True
    if "analysis_coverage" not in overrides:
      track.analysis_coverage = [{"start": 0.0, "end": track.duration}]
    track.first_downbeat = 0.0
    track.downbeat_confidence = 1.0
    intro_end = max(
      (float(section.get("end_time", 0.0)) for section in track.sections
       if str(section.get("label", "")).lower() == "intro"),
      default=0.0,
    )
    in_multiple = max(4, int(intro_end // grid) + 1)
    track.mix_in_candidates = [
      _lokaler_kandidat(in_multiple * grid, track.camelotCode, track.energy)
    ]
    track.mix_out_candidates = [_lokaler_kandidat(10 * grid, track.camelotCode, track.energy)]
  return track


def make_house_track(**overrides) -> Track:
  """House Track: 124-128 BPM, hohe Energie."""
  defaults = {
    "genre": "House",
    "detected_genre": "Tech House",
    "bpm": 126.0,
    "energy": 75,
    "bass_intensity": 70,
  }
  defaults.update(overrides)
  return make_track(**defaults)


def make_techno_track(**overrides) -> Track:
  """Techno Track: 130-140 BPM, sehr hohe Energie."""
  defaults = {
    "genre": "Techno",
    "detected_genre": "Techno",
    "bpm": 135.0,
    "energy": 85,
    "bass_intensity": 80,
  }
  defaults.update(overrides)
  return make_track(**defaults)


def make_dnb_track(**overrides) -> Track:
  """Drum & Bass Track: 170-180 BPM."""
  defaults = {
    "genre": "Drum & Bass",
    "detected_genre": "Drum & Bass",
    "bpm": 174.0,
    "energy": 80,
    "bass_intensity": 85,
  }
  defaults.update(overrides)
  return make_track(**defaults)


def make_minimal_track(**overrides) -> Track:
  """Track mit minimalen Pflichtfeldern - Edge Case."""
  return Track(
    filePath=overrides.get("filePath", "/test/minimal.mp3"),
    fileName=overrides.get("fileName", "minimal.mp3"),
    **{k: v for k, v in overrides.items() if k not in ("filePath", "fileName")}
  )


def make_compatible_pair(
    base_key: str = "8A",
    relation: str = "energy_up",
    bpm_diff: float = 0.0
) -> tuple[Track, Track]:
  """Erzeugt zwei harmonisch kompatible Tracks fuer Transition-Tests.

  Args:
    base_key: Start-Camelot Key
    relation: Harmonische Beziehung ("energy_up", "energy_down", "same", "relative")
    bpm_diff: BPM-Differenz zwischen den Tracks

  Returns:
    (track_a, track_b) Tupel kompatibler Tracks
  """
  from tests.fixtures.camelot_test_data import get_related_key

  # Ersten Track erstellen
  track_a = make_track(camelotCode=base_key, bpm=128.0)

  # Related Key bestimmen
  target_key = get_related_key(base_key, relation)

  # Zweiten Track erstellen
  track_b = make_track(
    camelotCode=target_key,
    bpm=128.0 + bpm_diff
  )

  return track_a, track_b


def make_playlist_set(
    num_tracks: int = 8,
    base_bpm: float = 128.0,
    progression: str = "energy_boost"
) -> list[Track]:
  """Erzeugt ein kohärentes DJ-Set für Playlist-Tests.

  Args:
    num_tracks: Anzahl Tracks
    base_bpm: Start-BPM
    progression: Energie-Progression ("energy_boost", "wave", "plateau", "random")

  Returns:
    Liste von Tracks mit harmonischem Flow
  """
  import numpy as np

  # Camelot-Sequenz für harmonischen Flow
  camelot_sequence = ["8A", "8B", "9B", "9A", "10A", "10B", "11B", "11A"]

  # Energie-Kurve basierend auf Progression
  if progression == "energy_boost":
    energy_curve = np.linspace(0.6, 0.9, num_tracks)
  elif progression == "wave":
    energy_curve = 0.7 + 0.2 * np.sin(np.linspace(0, 2*np.pi, num_tracks))
  elif progression == "plateau":
    energy_curve = np.full(num_tracks, 0.85)
  else:  # random
    np.random.seed(42)
    energy_curve = np.random.uniform(0.6, 0.9, num_tracks)

  tracks = []
  for i in range(num_tracks):
    camelot = camelot_sequence[i % len(camelot_sequence)]
    bpm = base_bpm + (i * 0.5)  # Leichter BPM-Anstieg

    track = make_track(
      camelotCode=camelot,
      bpm=round(bpm, 1),
      energy=int(energy_curve[i] * 100),
      fileName=f"Track_{i+1:02d}.mp3",
      title=f"Track {i+1}"
    )
    tracks.append(track)

  return tracks


def make_dj_set(count: int = 8, base_bpm: float = 126.0,
                bpm_range: float = 4.0) -> list[Track]:
  """Erzeugt ein realistisches DJ-Set mit harmonisch kompatiblen Tracks.

  Args:
    count: Anzahl der Tracks
    base_bpm: Basis-BPM
    bpm_range: BPM-Variationsbreite

  Returns:
    Liste von Tracks mit aufsteigendem BPM und kompatiblen Keys
  """
  # Camelot-Wheel Nachbarn fuer harmonischen Flow
  camelot_sequence = ["8A", "8B", "9B", "9A", "10A", "10B", "11B", "11A",
                      "12A", "12B", "1B", "1A"]

  tracks = []
  for i in range(count):
    bpm = base_bpm + (bpm_range * i / max(count - 1, 1))
    camelot = camelot_sequence[i % len(camelot_sequence)]

    # Reverse-Lookup fuer keyNote/keyMode
    reverse_map = {v: k for k, v in CAMELOT_MAP.items()}
    key_note, key_mode = reverse_map.get(camelot, ("A", "Minor"))

    duration = 300.0 + i * 10  # Leicht variierende Laengen

    # Mix-Point Berechnung passend zum BPM
    spb = 60.0 / bpm * 4  # seconds per bar
    mix_in = round(spb * 16, 2)   # 16 Bars Intro
    mix_out = round(duration - spb * 16, 2)  # 16 Bars Outro

    track = make_track(
      filePath=f"/test/track_{i+1:02d}.mp3",
      fileName=f"DJ Artist {i+1} - Track {i+1}.mp3",
      artist=f"DJ Artist {i+1}",
      title=f"Track {i+1}",
      bpm=round(bpm, 1),
      keyNote=key_note,
      keyMode=key_mode,
      camelotCode=camelot,
      energy=60 + i * 3,  # Aufsteigende Energie
      bass_intensity=55 + i * 2,
      duration=duration,
      mix_in_point=mix_in,
      mix_out_point=mix_out,
      mix_in_bars=16,
      mix_out_bars=int(round(mix_out / spb)),
    )
    tracks.append(track)

  return tracks
