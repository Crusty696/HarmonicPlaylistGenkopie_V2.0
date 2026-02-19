"""
DJ Brain - Genre-spezifische Mix-Logik fuer den Harmonic Playlist Generator.

Berechnet intelligente, genre-spezifische Mix-Punkte basierend auf:
- Track-Strukturanalyse (Intro/Build/Drop/Breakdown/Outro)
- Genre-spezifische DJ-Konventionen (Phrase-Laenge, EQ-Strategie, Transition-Technik)
- Genre-Kompatibilitaets-Matrix fuer Cross-Genre-Transitions

Basiert auf Research von Pioneer DJ, Club Ready DJ School, DJ Tech Tools u.a.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from .models import Track
from .config import METER


# === Genre Mix Profiles ===
# Basiert auf gaengigen DJ-Konventionen pro Genre

@dataclass
class GenreMixProfile:
  """Definiert genre-spezifische Mix-Parameter."""
  name: str
  intro_bars: tuple[int, int]      # (min, max) Bars fuer Intro-Laenge
  outro_bars: tuple[int, int]      # (min, max) Bars fuer Outro-Laenge
  transition_bars: tuple[int, int] # (min, max) empfohlener Overlap in Bars
  phrase_unit: int                  # Phrase-Einheit in Bars (8, 16, 32)
  eq_strategy: str                 # EQ-Empfehlung
  mix_technique: str               # Primaere Mix-Technik
  description: str                 # Kurze Genre-Beschreibung fuer UI

GENRE_MIX_PROFILES: dict[str, GenreMixProfile] = {
  "Psytrance": GenreMixProfile(
    name="Psytrance",
    intro_bars=(32, 64),
    outro_bars=(32, 64),
    transition_bars=(16, 32),
    phrase_unit=16,
    eq_strategy="Bass Swap an der Drop-Grenze",
    mix_technique="Langer Intro/Outro-Overlap mit Bass Swap",
    description="Psytrance: 16-Bar Phrasen, Bass Swap am Drop",
  ),
  "Tech House": GenreMixProfile(
    name="Tech House",
    intro_bars=(16, 32),
    outro_bars=(16, 32),
    transition_bars=(8, 16),
    phrase_unit=8,
    eq_strategy="Schneller Bass Swap, Hi-Hats laufen lassen",
    mix_technique="Enge Cuts, Loop-basiertes Mixen",
    description="Tech House: 8-Bar Phrasen, schnelle Cuts",
  ),
  "Progressive": GenreMixProfile(
    name="Progressive",
    intro_bars=(32, 64),
    outro_bars=(32, 64),
    transition_bars=(32, 64),
    phrase_unit=8,
    eq_strategy="Langsamer EQ-Blend ueber 32+ Bars",
    mix_technique="Langer Layer-Blend mit graduellem EQ-Shift",
    description="Progressive: 8-Bar Phrasen, lange Blends",
  ),
  "Melodic Techno": GenreMixProfile(
    name="Melodic Techno",
    intro_bars=(32, 64),
    outro_bars=(32, 64),
    transition_bars=(16, 32),
    phrase_unit=8,
    eq_strategy="Filter Ride, Bass vom Incoming cutten bis Breakdown",
    mix_technique="Filter Rides, Melodie-bewusstes Blending",
    description="Melodic Techno: 8-Bar Phrasen, Filter Rides",
  ),
  "Techno": GenreMixProfile(
    name="Techno",
    intro_bars=(16, 32),
    outro_bars=(16, 32),
    transition_bars=(8, 16),
    phrase_unit=8,
    eq_strategy="Harter Bass Swap, Mids kontrollieren",
    mix_technique="Schnelle Cuts, Loop-basiert, harte Uebergaenge",
    description="Techno: 8-Bar Phrasen, harte Cuts und Bass Swaps",
  ),
  "Deep House": GenreMixProfile(
    name="Deep House",
    intro_bars=(32, 64),
    outro_bars=(32, 64),
    transition_bars=(32, 64),
    phrase_unit=8,
    eq_strategy="Sanfter Bass-Blend ueber 32+ Bars, Mids smooth halten",
    mix_technique="Langer smooth Blend, Groove-Matching",
    description="Deep House: 8-Bar Phrasen, lange smoothe Blends",
  ),
  "Trance": GenreMixProfile(
    name="Trance",
    intro_bars=(32, 64),
    outro_bars=(32, 64),
    transition_bars=(16, 32),
    phrase_unit=16,
    eq_strategy="Bass Swap am Build, Melodie rein-filtern",
    mix_technique="Breakdown-basiertes Blending, Melodie-Layering",
    description="Trance: 16-Bar Phrasen, Breakdown-Blends",
  ),
  "Drum & Bass": GenreMixProfile(
    name="Drum & Bass",
    intro_bars=(16, 32),
    outro_bars=(16, 32),
    transition_bars=(8, 16),
    phrase_unit=8,
    eq_strategy="Schneller Bass Swap, Drums laufen lassen",
    mix_technique="Double Drop, schnelle Cuts, DJ Neumark style",
    description="DnB: 8-Bar Phrasen, schnelle Drops und Cuts",
  ),
  "Minimal": GenreMixProfile(
    name="Minimal",
    intro_bars=(32, 64),
    outro_bars=(32, 64),
    transition_bars=(32, 64),
    phrase_unit=8,
    eq_strategy="Subtiler Bass-Blend, Texturen langsam einblenden",
    mix_technique="Sehr langer Blend, hypnotische Uebergaenge",
    description="Minimal: 8-Bar Phrasen, hypnotische Blends",
  ),
}

# Default-Profil fuer unbekannte Genres
DEFAULT_MIX_PROFILE = GenreMixProfile(
  name="Default",
  intro_bars=(16, 32),
  outro_bars=(16, 32),
  transition_bars=(16, 32),
  phrase_unit=8,
  eq_strategy="Standard Bass Swap",
  mix_technique="Standard Intro/Outro-Blend",
  description="Standard-Mix (Genre unbekannt)",
)


# === Genre Compatibility Matrix ===
# Werte 0.0-1.0: Wie gut passen zwei Genres zusammen?
# Symmetrisch: (A, B) == (B, A)

GENRE_COMPATIBILITY: dict[tuple[str, str], float] = {
  # --- Selbst-Paare (1.0) ---
  ("Psytrance", "Psytrance"):           1.0,
  ("Tech House", "Tech House"):         1.0,
  ("Progressive", "Progressive"):       1.0,
  ("Melodic Techno", "Melodic Techno"): 1.0,
  ("Techno", "Techno"):                 1.0,
  ("Deep House", "Deep House"):         1.0,
  ("Trance", "Trance"):                 1.0,
  ("Drum & Bass", "Drum & Bass"):       1.0,
  ("Minimal", "Minimal"):               1.0,

  # --- Original 4-Genre Cross-Paare ---
  ("Psytrance", "Tech House"):          0.3,
  ("Psytrance", "Progressive"):         0.6,
  ("Psytrance", "Melodic Techno"):      0.4,
  ("Tech House", "Progressive"):        0.5,
  ("Tech House", "Melodic Techno"):     0.75,
  ("Progressive", "Melodic Techno"):    0.85,

  # --- Psytrance Cross-Paare (neu) ---
  ("Psytrance", "Techno"):              0.5,   # BPM-Overlap, aber unterschiedliche Stimmung
  ("Psytrance", "Deep House"):          0.15,  # Kaum kompatibel - Tempo + Stimmung
  ("Psytrance", "Trance"):              0.75,  # Verwandt, gemeinsame Wurzeln
  ("Psytrance", "Drum & Bass"):         0.25,  # Nur ueber Breakdowns, Tempo-Sprung
  ("Psytrance", "Minimal"):             0.2,   # Kaum kompatibel

  # --- Tech House Cross-Paare (neu) ---
  ("Tech House", "Techno"):             0.8,   # Nah verwandt, BPM-Overlap
  ("Tech House", "Deep House"):         0.7,   # Gleiche Wurzeln, Groove-verwandt
  ("Tech House", "Trance"):             0.35,  # Unterschiedliche Stimmung
  ("Tech House", "Drum & Bass"):        0.2,   # Grosser Tempo-Sprung
  ("Tech House", "Minimal"):            0.75,  # Verwandt, groove-basiert

  # --- Progressive Cross-Paare (neu) ---
  ("Progressive", "Techno"):            0.55,  # Moderater Match
  ("Progressive", "Deep House"):        0.65,  # Smooth Transitions moeglich
  ("Progressive", "Trance"):            0.8,   # Progressive Trance ist das Bindeglied
  ("Progressive", "Drum & Bass"):       0.2,   # Kaum kompatibel
  ("Progressive", "Minimal"):           0.6,   # Beide atmosphaerisch

  # --- Melodic Techno Cross-Paare (neu) ---
  ("Melodic Techno", "Techno"):         0.8,   # Nah verwandt
  ("Melodic Techno", "Deep House"):     0.65,  # Melodisch, smooth
  ("Melodic Techno", "Trance"):         0.7,   # Melodische Verwandtschaft
  ("Melodic Techno", "Drum & Bass"):    0.2,   # Kaum kompatibel
  ("Melodic Techno", "Minimal"):        0.6,   # Techno-Familie

  # --- Techno Cross-Paare (neu) ---
  ("Techno", "Deep House"):             0.4,   # Unterschiedliche Energie
  ("Techno", "Trance"):                 0.55,  # Tempo-Overlap, unterschiedliche Stimmung
  ("Techno", "Drum & Bass"):            0.35,  # Industrial DnB Bridge moeglich
  ("Techno", "Minimal"):                0.8,   # Verwandt, Techno-Familie

  # --- Deep House Cross-Paare (neu) ---
  ("Deep House", "Trance"):             0.3,   # Unterschiedliche Energie + Tempo
  ("Deep House", "Drum & Bass"):        0.1,   # Fast inkompatibel
  ("Deep House", "Minimal"):            0.65,  # Beide subtil, smooth

  # --- Trance Cross-Paare (neu) ---
  ("Trance", "Drum & Bass"):            0.3,   # Nur ueber Breakdowns
  ("Trance", "Minimal"):                0.35,  # Unterschiedliche Stimmung

  # --- Drum & Bass Cross-Paare (neu) ---
  ("Drum & Bass", "Minimal"):           0.15,  # Fast inkompatibel
}


def get_genre_compatibility(genre_a: str, genre_b: str) -> float:
  """
  Gibt die Kompatibilitaet zwischen zwei Genres zurueck (0.0-1.0).

  Die Matrix ist symmetrisch. Bei unbekannten Genres wird 0.5 zurueckgegeben.

  Args:
    genre_a: Erstes Genre
    genre_b: Zweites Genre

  Returns:
    Kompatibilitaets-Score 0.0-1.0
  """
  if not genre_a or not genre_b:
    return 0.5
  if genre_a == "Unknown" or genre_b == "Unknown":
    return 0.5

  # Direkt nachschauen
  score = GENRE_COMPATIBILITY.get((genre_a, genre_b))
  if score is not None:
    return score

  # Umgekehrt (symmetrisch)
  score = GENRE_COMPATIBILITY.get((genre_b, genre_a))
  if score is not None:
    return score

  # Unbekannte Kombination
  return 0.5


def get_mix_profile(genre: str) -> GenreMixProfile:
  """
  Gibt das Mix-Profil fuer ein Genre zurueck.

  Args:
    genre: Genre-Name (z.B. "Psytrance", "Tech House")

  Returns:
    GenreMixProfile fuer das Genre oder Default-Profil
  """
  return GENRE_MIX_PROFILES.get(genre, DEFAULT_MIX_PROFILE)


# === Mix-Punkt-Berechnung ===

def calculate_genre_aware_mix_points(
  sections: list[dict],
  bpm: float,
  duration: float,
  genre: str,
) -> tuple[float, float, int, int]:
  """
  Berechnet genre-spezifische Mix-In/Out-Punkte basierend auf Track-Struktur.

  Logik:
  - Mix-In: Ende des Intros (oder Anfang des ersten Build/Main)
  - Mix-Out: Anfang des Outros (oder Ende des letzten Drop/Main)
  - Quantisiert auf genre-spezifische Phrase-Grenzen

  Args:
    sections: Liste von Section-Dicts (aus TrackSection.to_dict())
    bpm: Track BPM
    duration: Track-Dauer in Sekunden
    genre: Erkanntes Genre

  Returns:
    (mix_in_point, mix_out_point, mix_in_bars, mix_out_bars)
  """
  if not sections or bpm <= 0 or duration <= 0:
    return 0.0, duration, 0, 0

  profile = get_mix_profile(genre)
  seconds_per_beat = 60.0 / bpm
  seconds_per_bar = seconds_per_beat * METER

  # --- Mix-In: Wo faengt der "Kern" des Tracks an? ---
  mix_in_time = _find_mix_in_point(sections, profile, seconds_per_bar)

  # --- Mix-Out: Wo faengt der Track an auszuklingen? ---
  mix_out_time = _find_mix_out_point(sections, profile, seconds_per_bar, duration)

  # Quantisiere auf 4-Bar-Grenzen (nicht phrase_unit!)
  # phrase_unit (8/16/32) ist fuer DJ-Empfehlungen richtig, aber fuer Mix-Points
  # zu grob -- 16 bars bei 143 BPM = 27s Raster, das macht alle Tracks identisch.
  # 4 Bars = 1 Pattern, musikalisch korrekt UND individuell pro Track.
  MIX_POINT_GRID_BARS = 4
  grid_seconds = seconds_per_bar * MIX_POINT_GRID_BARS
  if grid_seconds > 0:
    mix_in_time = round(mix_in_time / grid_seconds) * grid_seconds
    mix_out_time = round(mix_out_time / grid_seconds) * grid_seconds

  # Sicherheitsgrenzen
  mix_in_time = max(seconds_per_bar, min(mix_in_time, duration * 0.4))
  mix_out_time = min(duration - seconds_per_bar, max(mix_out_time, duration * 0.6))

  # Sicherstellen, dass Mix-Out nach Mix-In liegt
  if mix_out_time <= mix_in_time + seconds_per_bar * 4:
    mix_in_time = duration * 0.15
    mix_out_time = duration * 0.85

  # In Bars umrechnen
  mix_in_bars = int(round(mix_in_time / seconds_per_bar))
  mix_out_bars = int(round(mix_out_time / seconds_per_bar))

  return round(mix_in_time, 2), round(mix_out_time, 2), mix_in_bars, mix_out_bars


def _find_mix_in_point(
  sections: list[dict],
  profile: GenreMixProfile,
  seconds_per_bar: float,
) -> float:
  """
  Findet den optimalen Mix-In-Punkt basierend auf der individuellen Track-Struktur.

  Jeder Track hat eine einzigartige Struktur - der Mix-In-Punkt muss aus der
  tatsaechlichen Audio-Analyse kommen, nicht aus Genre-Defaults.

  Strategie:
  1. Ende aller zusammenhaengenden Intro-Sektionen (auch Multi-Section-Intros)
  2. Anfang der ersten Build/Drop-Sektion (NICHT "main" bei 0.0!)
  3. Energie-basierter Fallback: Erste Sektion mit ueberdurchschnittlicher Energie
  4. Letzter Fallback: Genre-Profil Intro-Bars als Schaetzung
  """
  # --- Strategie 1: Ende aller zusammenhaengenden Intro-Sektionen ---
  last_intro_idx = -1
  for i, section in enumerate(sections):
    if section.get("label", "main") == "intro":
      last_intro_idx = i
    else:
      # Sobald kein Intro mehr -> fertig
      if last_intro_idx >= 0:
        break

  if last_intro_idx >= 0:
    # Mix-In ist der Anfang der Section NACH dem letzten Intro
    if last_intro_idx + 1 < len(sections):
      mix_in = sections[last_intro_idx + 1].get("start_time", 0.0)
    else:
      mix_in = sections[last_intro_idx].get("end_time", 0.0)
    # Nur zurueckgeben wenn sinnvoll (nicht am Track-Anfang)
    if mix_in > seconds_per_bar * 2:
      return mix_in

  # --- Strategie 2: Erste Build/Drop-Sektion (NICHT die allererste "main"!) ---
  # Ueberspringe die erste Section wenn sie bei 0.0 startet und "main" ist,
  # denn das bedeutet nur "kein Intro erkannt", nicht "Mix-In bei 0:00"
  for section in sections:
    label = section.get("label", "main")
    start = section.get("start_time", 0.0)
    if label in ("build", "drop"):
      # Build/Drop hat immer einen klaren Strukturwechsel
      return start

  # --- Strategie 3: Energie-basierter Fallback ---
  # Finde den ersten signifikanten Energie-Anstieg im Track
  # Das ist der Punkt wo der Track "richtig losgeht"
  if len(sections) >= 2:
    energies = [s.get("avg_energy", 50.0) for s in sections]
    avg_energy = sum(energies) / len(energies)

    for i, section in enumerate(sections):
      energy = section.get("avg_energy", 50.0)
      start = section.get("start_time", 0.0)
      # Ueberspringe Sections am Anfang die bei 0.0 sind
      if start < seconds_per_bar * 2:
        continue
      # Erste Section mit ueberdurchschnittlicher Energie = Mix-In
      if energy >= avg_energy * 0.9:
        return start

  # --- Strategie 4: Genre-Profil als letzte Schaetzung ---
  # Auch hier individuell: Nutze den Mittelwert des Genre-typischen Intro-Bereichs
  avg_intro_bars = (profile.intro_bars[0] + profile.intro_bars[1]) / 2.0
  return avg_intro_bars * seconds_per_bar


def _find_mix_out_point(
  sections: list[dict],
  profile: GenreMixProfile,
  seconds_per_bar: float,
  duration: float,
) -> float:
  """
  Findet den optimalen Mix-Out-Punkt basierend auf der individuellen Track-Struktur.

  Strategie:
  1. Anfang der fruehesten zusammenhaengenden Outro-Sektionen
  2. Energie-basiert: Letzte Section mit hoher Energie -> deren Ende
  3. Letzter Fallback: Genre-Profil Outro-Position
  """
  # --- Strategie 1: Frueheste zusammenhaengende Outro-Section ---
  first_outro_idx = -1
  for i in range(len(sections) - 1, -1, -1):
    if sections[i].get("label", "main") == "outro":
      first_outro_idx = i
    else:
      if first_outro_idx >= 0:
        break

  if first_outro_idx >= 0:
    outro_start = sections[first_outro_idx].get("start_time", duration)
    # Nur zurueckgeben wenn sinnvoll (nicht zu nah am Ende)
    if outro_start < duration - seconds_per_bar * 2:
      return outro_start

  # --- Strategie 2: Ende der letzten energiereichen Section ---
  # Ueberspringe die allerletzte Section wenn sie das Track-Ende ist
  if len(sections) >= 2:
    energies = [s.get("avg_energy", 50.0) for s in sections]
    avg_energy = sum(energies) / len(energies)

    for section in reversed(sections):
      label = section.get("label", "main")
      energy = section.get("avg_energy", 50.0)
      end = section.get("end_time", duration)
      # Finde die letzte Section mit guter Energie (Drop/Main/Build)
      if label in ("drop", "main", "build", "breakdown") and energy >= avg_energy * 0.7:
        # Mix-Out am Ende dieser Section, nicht am Track-Ende
        if end < duration - seconds_per_bar:
          return end

  # --- Strategie 3: Genre-Profil Outro-Bars ---
  avg_outro_bars = (profile.outro_bars[0] + profile.outro_bars[1]) / 2.0
  return duration - (avg_outro_bars * seconds_per_bar)


# === DJ Empfehlungen ===

@dataclass
class DJRecommendation:
  """Erweiterte DJ-Empfehlung fuer einen Transition zwischen zwei Tracks."""
  # Genre-Kontext
  genre_pair: str          # z.B. "Psytrance -> Psytrance"
  genre_compatibility: float  # 0.0-1.0

  # Mix-Technik
  mix_technique: str       # z.B. "Long intro/outro overlap with bass swap"
  eq_advice: str           # z.B. "Bass swap at drop boundary"
  transition_bars: int     # Empfohlener Overlap in Bars

  # Struktur-Kontext
  outgoing_section: str    # z.B. "outro" - Sektion des ausgehenden Tracks am Mix-Out
  incoming_section: str    # z.B. "intro" - Sektion des eingehenden Tracks am Mix-In
  structure_note: str      # z.B. "Mix from outro into intro - ideal alignment"

  # Risiko-Bewertung
  risk_notes: list[str] = field(default_factory=list)  # z.B. ["BPM difference > 5"]


def generate_dj_recommendation(
  track_a: Track,
  track_b: Track,
) -> DJRecommendation:
  """
  Erzeugt eine erweiterte DJ-Empfehlung fuer die Transition von Track A nach Track B.

  Beruecksichtigt Genre, Sektionsstruktur, BPM-Differenz und Energie-Verlauf.

  Args:
    track_a: Ausgehender Track
    track_b: Eingehender Track

  Returns:
    DJRecommendation mit allen Mix-Details
  """
  genre_a = track_a.detected_genre or "Unknown"
  genre_b = track_b.detected_genre or "Unknown"

  # Genre-Kompatibilitaet
  compat = get_genre_compatibility(genre_a, genre_b)
  genre_pair = f"{genre_a} -> {genre_b}"

  # Mix-Profil bestimmen (verwende das Profil des eingehenden Tracks)
  profile_b = get_mix_profile(genre_b)
  profile_a = get_mix_profile(genre_a)

  # Transition-Laenge: Mittelwert aus beiden Profilen
  avg_transition_bars = int(
    (profile_a.transition_bars[0] + profile_a.transition_bars[1] +
     profile_b.transition_bars[0] + profile_b.transition_bars[1]) / 4.0
  )

  # Mix-Technik: Verwende die des eingehenden Tracks (der DJ passt sich an)
  mix_technique = profile_b.mix_technique
  eq_advice = profile_b.eq_strategy

  # Wenn Cross-Genre, spezifische Empfehlung
  if genre_a != genre_b and genre_a != "Unknown" and genre_b != "Unknown":
    mix_technique = _get_cross_genre_technique(genre_a, genre_b)
    eq_advice = _get_cross_genre_eq(genre_a, genre_b)

  # Struktur-Kontext
  outgoing_section = _get_section_at_mix_out(track_a)
  incoming_section = _get_section_at_mix_in(track_b)
  structure_note = _build_structure_note(outgoing_section, incoming_section)

  # Risiko-Bewertung
  risk_notes = _assess_transition_risks(track_a, track_b, compat)

  return DJRecommendation(
    genre_pair=genre_pair,
    genre_compatibility=round(compat, 2),
    mix_technique=mix_technique,
    eq_advice=eq_advice,
    transition_bars=avg_transition_bars,
    outgoing_section=outgoing_section,
    incoming_section=incoming_section,
    structure_note=structure_note,
    risk_notes=risk_notes,
  )


# === Hilfsfunktionen ===

def _get_section_at_mix_out(track: Track) -> str:
  """Findet die Sektion am Mix-Out-Punkt eines Tracks."""
  if not track.sections or track.mix_out_point <= 0:
    return "unknown"

  for section in track.sections:
    start = section.get("start_time", 0.0)
    end = section.get("end_time", 0.0)
    if start <= track.mix_out_point <= end:
      return section.get("label", "unknown")

  # Letzte Sektion als Fallback
  if track.sections:
    return track.sections[-1].get("label", "unknown")
  return "unknown"


def _get_section_at_mix_in(track: Track) -> str:
  """Findet die Sektion am Mix-In-Punkt eines Tracks."""
  if not track.sections or track.mix_in_point <= 0:
    return "unknown"

  for section in track.sections:
    start = section.get("start_time", 0.0)
    end = section.get("end_time", 0.0)
    if start <= track.mix_in_point <= end:
      return section.get("label", "unknown")

  # Erste Sektion als Fallback
  if track.sections:
    return track.sections[0].get("label", "unknown")
  return "unknown"


def _build_structure_note(outgoing: str, incoming: str) -> str:
  """Erzeugt einen menschenlesbaren Hinweis zur Struktur-Ausrichtung.

  Gibt leeren String zurueck wenn keine Strukturdaten vorhanden sind,
  damit die GUI keine nutzlose Meldung anzeigt.
  """
  if outgoing == "unknown" or incoming == "unknown":
    return ""  # Keine Struktur-Daten -> keine Anzeige
  if outgoing == "outro" and incoming == "intro":
    return "Ideal: Outro in Intro mixen"
  if outgoing == "outro" and incoming in ("build", "main"):
    return "Gut: Outro in aktiven Teil -- Energie anpassen"
  if outgoing == "breakdown" and incoming == "intro":
    return "Smooth: Breakdown in Intro -- sanft halten"
  if outgoing == "breakdown" and incoming in ("build", "drop"):
    return "Gut: Breakdown in Build/Drop -- Energie-Steigerung"
  if outgoing == "drop" and incoming == "intro":
    return "Riskant: Drop in Intro -- Energie-Einbruch"
  if outgoing == "drop" and incoming == "drop":
    return "Mutig: Drop-zu-Drop -- praezises Timing noetig"
  if outgoing == "main" and incoming == "intro":
    return "Standard: Hauptteil in Intro blenden"
  if outgoing == "build" and incoming == "intro":
    return "OK: Build in Intro -- Energie passt"
  return f"Struktur: {outgoing} -> {incoming}"


def _get_cross_genre_technique(genre_a: str, genre_b: str) -> str:
  """Empfiehlt eine Mix-Technik fuer Cross-Genre-Transitions."""
  pair = frozenset({genre_a, genre_b})

  # Original 4-Genre Kombinationen
  if pair == frozenset({"Psytrance", "Progressive"}):
    return "Gradual BPM transition, blend during breakdowns"
  if pair == frozenset({"Tech House", "Melodic Techno"}):
    return "Quick bass swap, match groove patterns"
  if pair == frozenset({"Progressive", "Melodic Techno"}):
    return "Long blend over 32 bars, filter ride"
  if pair == frozenset({"Psytrance", "Tech House"}):
    return "Difficult mix - use breakdown bridge, adjust BPM early"
  if pair == frozenset({"Psytrance", "Melodic Techno"}):
    return "Blend during breakdowns, gradual tempo shift"
  if pair == frozenset({"Tech House", "Progressive"}):
    return "Match groove, gradual filter blend"

  # Techno Kombinationen
  if pair == frozenset({"Techno", "Tech House"}):
    return "Quick bass swap, Groove-Match -- verwandte Genres"
  if pair == frozenset({"Techno", "Melodic Techno"}):
    return "Filter Ride auf Melodie, Bass swap am Breakdown"
  if pair == frozenset({"Techno", "Minimal"}):
    return "Langer Blend, Texturen langsam aufbauen/abbauen"
  if pair == frozenset({"Techno", "Psytrance"}):
    return "BPM matchen, Breakdown-Bridge nutzen"
  if pair == frozenset({"Techno", "Trance"}):
    return "Breakdown-Blend, BPM langsam angleichen"
  if pair == frozenset({"Techno", "Progressive"}):
    return "Filter-Blend, Energie langsam anpassen"

  # Deep House Kombinationen
  if pair == frozenset({"Deep House", "Tech House"}):
    return "Groove-Match, sanfter Bass-Blend ueber 32 Bars"
  if pair == frozenset({"Deep House", "Melodic Techno"}):
    return "Melodien layern, sanfter Uebergang"
  if pair == frozenset({"Deep House", "Progressive"}):
    return "Langer atmosphaerischer Blend"
  if pair == frozenset({"Deep House", "Minimal"}):
    return "Hypnotischer Blend, subtile Textur-Shifts"

  # Trance Kombinationen
  if pair == frozenset({"Trance", "Progressive"}):
    return "Breakdown-Blend, Progressive Trance als Bridge"
  if pair == frozenset({"Trance", "Psytrance"}):
    return "Verwandte Genres -- Breakdown-Overlap, BPM matchen"
  if pair == frozenset({"Trance", "Melodic Techno"}):
    return "Melodie-Layering, Filter Ride"

  # DnB Kombinationen
  if pair == frozenset({"Drum & Bass", "Techno"}):
    return "Half-Time DnB oder Tempo-Jump am Drop"
  if pair == frozenset({"Drum & Bass", "Trance"}):
    return "Breakdown-Bridge, harter Tempo-Wechsel"

  return "Standard cross-genre blend - match energy levels"


def _get_cross_genre_eq(genre_a: str, genre_b: str) -> str:
  """Empfiehlt eine EQ-Strategie fuer Cross-Genre-Transitions."""
  pair = frozenset({genre_a, genre_b})

  # Original 4-Genre Kombinationen
  if pair == frozenset({"Psytrance", "Progressive"}):
    return "Cut Psy bass early, blend progressive bass in slowly"
  if pair == frozenset({"Tech House", "Melodic Techno"}):
    return "Quick bass swap, watch mid frequencies for clashing melodies"
  if pair == frozenset({"Progressive", "Melodic Techno"}):
    return "Gradual bass crossfade, use filter on incoming"
  if pair == frozenset({"Psytrance", "Tech House"}):
    return "Full bass swap at phrase boundary, careful with mid clash"
  if pair == frozenset({"Psytrance", "Melodic Techno"}):
    return "Filter ride on incoming, swap bass at breakdown"
  if pair == frozenset({"Tech House", "Progressive"}):
    return "Gradual bass blend, keep hi-hats from tech house"

  # Techno Kombinationen
  if pair == frozenset({"Techno", "Tech House"}):
    return "Schneller Bass Swap, Hi-Hats matchen"
  if pair == frozenset({"Techno", "Melodic Techno"}):
    return "Filter auf Incoming-Melodie, Bass swap am Drop"
  if pair == frozenset({"Techno", "Minimal"}):
    return "Subtiler Bass-Blend, Texturen langsam einblenden"
  if pair == frozenset({"Techno", "Psytrance"}):
    return "Harter Bass Swap an Phrase-Grenze, Psy-Bass frueh cutten"
  if pair == frozenset({"Techno", "Trance"}):
    return "Bass Swap am Breakdown, Trance-Melodie filtern"
  if pair == frozenset({"Techno", "Progressive"}):
    return "Gradueller Bass-Blend, Techno-Kick langsam rausnehmen"

  # Deep House Kombinationen
  if pair == frozenset({"Deep House", "Tech House"}):
    return "Sanfter Bass-Blend, Groove matchen, Hi-Hats laufen lassen"
  if pair == frozenset({"Deep House", "Melodic Techno"}):
    return "Langer Bass-Crossfade, Mids sauber halten"
  if pair == frozenset({"Deep House", "Progressive"}):
    return "Sehr langer Bass-Blend, alles smooth halten"
  if pair == frozenset({"Deep House", "Minimal"}):
    return "Subtile EQ-Shifts, beide Basse blenden"

  # Trance Kombinationen
  if pair == frozenset({"Trance", "Progressive"}):
    return "Langer Blend, Trance-Bass im Breakdown cutten"
  if pair == frozenset({"Trance", "Psytrance"}):
    return "Bass Swap an der Phrase-Grenze, Energie matchen"
  if pair == frozenset({"Trance", "Melodic Techno"}):
    return "Melodie-Clash vermeiden, Bass swap, Mids filtern"

  # DnB Kombinationen
  if pair == frozenset({"Drum & Bass", "Techno"}):
    return "Harter Bass Swap, DnB-Sub frueh cutten"
  if pair == frozenset({"Drum & Bass", "Trance"}):
    return "Full Cut am Drop, keine Bass-Ueberlappung"

  return "Standard bass swap at phrase boundary"


def _assess_transition_risks(
  track_a: Track,
  track_b: Track,
  genre_compat: float,
) -> list[str]:
  """Bewertet Risiken einer Transition."""
  risks = []

  # BPM-Check
  bpm_diff = abs(track_a.bpm - track_b.bpm)
  if bpm_diff > 8:
    risks.append(f"Grosser BPM-Sprung ({bpm_diff:.1f}) -- Pitch-Anpassung noetig")
  elif bpm_diff > 4:
    risks.append(f"BPM-Differenz {bpm_diff:.1f} -- langsam angleichen")

  # Energie-Check
  energy_diff = abs(track_a.energy - track_b.energy)
  if energy_diff > 30:
    risks.append(f"Grosser Energie-Sprung ({energy_diff}) -- EQ-Uebergang nutzen")
  elif energy_diff > 15:
    risks.append(f"Deutlicher Energie-Shift ({energy_diff}) -- Transition aufbauen")

  # Genre-Kompatibilitaet
  if genre_compat < 0.4:
    risks.append("Geringe Genre-Kompatibilitaet -- Bridge-Track empfohlen")
  elif genre_compat < 0.6:
    risks.append("Maessige Genre-Kompatibilitaet -- im Breakdown/Intro mixen")

  # Key-Konflikt (nur wenn Camelot-Codes vorhanden)
  if track_a.camelotCode and track_b.camelotCode:
    if track_a.camelotCode != track_b.camelotCode:
      # Einfacher Check: Gleicher Nummer-Bereich?
      num_a = _extract_camelot_number(track_a.camelotCode)
      num_b = _extract_camelot_number(track_b.camelotCode)
      if num_a > 0 and num_b > 0:
        diff = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
        if diff > 2:
          risks.append(f"Tonart-Clash (Camelot-Distanz: {diff}) -- EQ/Filter nutzen")

  return risks


def _extract_camelot_number(code: str) -> int:
  """Extrahiert die Nummer aus einem Camelot-Code (z.B. '8A' -> 8)."""
  try:
    return int(code[:-1])
  except (ValueError, IndexError):
    return 0
