"""
hpg_core/genres.py — Single Source of Truth fuer alles Genre-Wissen.

Audit-Refactoring 2026-07-17: vorher lagen 5 Genre-Tabellen verteilt in
genre_classifier (GENRE_PROFILES, ID3_GENRE_MAP), dj_brain (GENRE_MIX_PROFILES,
GENRE_COMPATIBILITY) und structure_analyzer (GENRE_PHRASE_UNITS) — ohne
Kopplung. Neues Genre in einer Tabelle vergessen = stiller Drift.

Jetzt: alle Tabellen hier, plus _validate_genre_tables() beim Import —
Inkonsistenzen schlagen sofort als ImportError auf statt still zu driften.

Die alten Module re-exportieren ihre Namen weiter (keine API-Brueche).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

# Die 9 kanonischen Genres der App (rein elektronische Musik)
CANONICAL_GENRES: tuple[str, ...] = (
    "Psytrance",
    "Tech House",
    "Progressive",
    "Melodic Techno",
    "Techno",
    "Deep House",
    "Trance",
    "Drum & Bass",
    "Minimal",
)


def resolve_track_genre(track: object) -> str:
    """Wirksames Track-Genre: Klassifikation vor ID3, sonst Unknown."""
    for attribute in ("detected_genre", "genre"):
        value = getattr(track, attribute, "") or ""
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value and value.casefold() != "unknown":
            return value
    return "Unknown"


@dataclass
class GenreProfile:
    """Defines characteristic audio features for a genre."""

    name: str
    bpm_range: tuple[float, float]
    bpm_center: float  # Most common BPM
    spectral_centroid_range: tuple[float, float]  # Hz
    onset_rate_range: tuple[float, float]  # events/sec
    spectral_flatness_range: tuple[float, float]  # 0-1
    rms_variance_range: tuple[float, float]  # normalized
    bass_ratio_range: tuple[float, float]  # 0-100


GENRE_PROFILES: dict[str, GenreProfile] = {
    "Psytrance": GenreProfile(
        name="Psytrance",
        bpm_range=(135, 150),
        bpm_center=142,
        # Psytrance is bright - acid synths, layered high-freq elements
        spectral_centroid_range=(2000, 4500),
        # Moderate onset rate - driving kick but less percussive variety
        onset_rate_range=(2.0, 5.0),
        # More tonal (acid bass, synth leads) = lower flatness
        spectral_flatness_range=(0.01, 0.08),
        # High energy variance (big drops and breakdowns)
        rms_variance_range=(0.15, 0.6),
        # High bass intensity (driving basslines)
        bass_ratio_range=(50, 90),
    ),
    "Tech House": GenreProfile(
        name="Tech House",
        bpm_range=(124, 135),
        bpm_center=128,
        # Mid-range brightness - groovy but not as bright as psytrance
        spectral_centroid_range=(1500, 3500),
        # High onset rate - lots of percussion, hats, shakers
        onset_rate_range=(3.5, 7.0),
        # More noise-like (percussion heavy) = higher flatness
        spectral_flatness_range=(0.04, 0.15),
        # Lower energy variance - consistent groove
        rms_variance_range=(0.05, 0.25),
        # Moderate bass - groove-focused, not bass-dominated
        bass_ratio_range=(35, 70),
    ),
    "Progressive": GenreProfile(
        name="Progressive",
        bpm_range=(120, 140),
        bpm_center=126,
        # Moderate brightness - layered pads, subtle melodies
        spectral_centroid_range=(1200, 3200),
        # Lower onset rate - less percussion, more atmosphere
        onset_rate_range=(1.5, 4.5),
        # Mixed tonal/noise content
        spectral_flatness_range=(0.03, 0.12),
        # Low-moderate variance - gradual energy changes
        rms_variance_range=(0.03, 0.20),
        # Moderate bass
        bass_ratio_range=(30, 65),
    ),
    "Melodic Techno": GenreProfile(
        name="Melodic Techno",
        bpm_range=(120, 130),
        bpm_center=125,
        # Moderate-high brightness - synth melodies, pads
        spectral_centroid_range=(1500, 3800),
        # Moderate onset rate - rhythmic but melodic
        onset_rate_range=(2.5, 5.5),
        # More tonal (melodies, chords) = lower flatness
        spectral_flatness_range=(0.02, 0.10),
        # Moderate variance - breakdowns and builds
        rms_variance_range=(0.08, 0.35),
        # Moderate bass - balanced with melodic content
        bass_ratio_range=(35, 70),
    ),
    "Techno": GenreProfile(
        name="Techno",
        bpm_range=(130, 150),
        bpm_center=138,
        # Moderate brightness - industrial, dark, raw sounds
        spectral_centroid_range=(1800, 4000),
        # High onset rate - relentless percussion, hats
        onset_rate_range=(3.5, 7.0),
        # Higher flatness - noise elements, industrial textures
        spectral_flatness_range=(0.05, 0.18),
        # Low-moderate variance - consistent driving energy
        rms_variance_range=(0.04, 0.22),
        # High bass - powerful kicks, sub bass
        bass_ratio_range=(50, 90),
    ),
    "Deep House": GenreProfile(
        name="Deep House",
        bpm_range=(118, 128),
        bpm_center=123,
        # Lower brightness - warm pads, smooth keys, filtered sounds
        spectral_centroid_range=(1000, 2800),
        # Moderate onset rate - laid-back groove
        onset_rate_range=(2.0, 4.5),
        # Mixed tonal/noise - warm chords with shuffled hats
        spectral_flatness_range=(0.03, 0.12),
        # Low variance - smooth, consistent energy
        rms_variance_range=(0.02, 0.15),
        # Moderate bass - deep but not overpowering
        bass_ratio_range=(30, 65),
    ),
    "Trance": GenreProfile(
        name="Trance",
        bpm_range=(128, 145),
        bpm_center=138,
        # High brightness - euphoric synths, supersaw leads, uplifting melodies
        spectral_centroid_range=(2200, 5000),
        # Moderate onset rate - arpeggios, plucks, but not percussion-heavy
        onset_rate_range=(2.0, 5.5),
        # Low flatness - very tonal (melodies, pads, supersaw)
        spectral_flatness_range=(0.01, 0.08),
        # High variance - big breakdowns, builds, drops
        rms_variance_range=(0.15, 0.55),
        # Moderate-high bass - solid kick, rolling bass
        bass_ratio_range=(40, 80),
    ),
    "Drum & Bass": GenreProfile(
        name="Drum & Bass",
        bpm_range=(160, 180),
        bpm_center=174,
        # Moderate-high brightness - fast snares, cymbals, reese bass harmonics
        spectral_centroid_range=(1800, 4200),
        # Very high onset rate - fast breakbeats, rapid-fire drums
        onset_rate_range=(5.0, 10.0),
        # Moderate flatness - mix of tonal bass and percussive noise
        spectral_flatness_range=(0.04, 0.15),
        # High variance - drops, breaks, switches
        rms_variance_range=(0.10, 0.50),
        # Very high bass - massive sub bass, reese bass
        bass_ratio_range=(60, 95),
    ),
    "Minimal": GenreProfile(
        name="Minimal",
        bpm_range=(120, 132),
        bpm_center=126,
        # Low brightness - sparse, filtered, subtle textures
        spectral_centroid_range=(800, 2500),
        # Low-moderate onset rate - sparse percussion, space
        onset_rate_range=(1.5, 4.0),
        # Moderate flatness - percussive clicks, subtle textures
        spectral_flatness_range=(0.03, 0.13),
        # Very low variance - hypnotic, repetitive, consistent
        rms_variance_range=(0.01, 0.12),
        # Moderate bass - subtle, deep, not overwhelming
        bass_ratio_range=(25, 60),
    ),
}


# === ID3 Genre Tag Matching ===

# Mapping of common ID3 genre tag strings to our target genres
ID3_GENRE_MAP: dict[str, str] = {
    # Psytrance variants
    "psytrance": "Psytrance",
    "psy trance": "Psytrance",
    "psy-trance": "Psytrance",
    "psychedelic trance": "Psytrance",
    "goa trance": "Psytrance",
    "goa": "Psytrance",
    "full on": "Psytrance",
    "full-on": "Psytrance",
    "dark psy": "Psytrance",
    "dark psytrance": "Psytrance",
    "forest": "Psytrance",
    "hi-tech": "Psytrance",
    "hitech": "Psytrance",
    # Tech House variants
    "tech house": "Tech House",
    "tech-house": "Tech House",
    "techhouse": "Tech House",
    "minimal tech house": "Tech House",
    "bass house": "Tech House",
    # Progressive variants
    "progressive": "Progressive",
    "progressive house": "Progressive",
    "progressive trance": "Progressive",
    "prog house": "Progressive",
    "prog trance": "Progressive",
    "prog": "Progressive",
    "deep progressive": "Progressive",
    # Melodic Techno variants
    "melodic techno": "Melodic Techno",
    "melodic house & techno": "Melodic Techno",
    "melodic house": "Melodic Techno",
    "melodic house/techno": "Melodic Techno",
    "indie dance": "Melodic Techno",
    # Audit-Fix 2026-07-17: Afro/Organic House teilen mit Melodic Techno nur
    # das BPM — Groove/Timbre liegen naeher an Deep House (Mix-Profil passt)
    "organic house": "Deep House",
    "afro house": "Deep House",
    # Techno variants
    "techno": "Techno",
    "hard techno": "Techno",
    "industrial techno": "Techno",
    "acid techno": "Techno",
    "detroit techno": "Techno",
    "peak time techno": "Techno",
    "peak time / driving": "Techno",
    "peak time / driving techno": "Techno",
    "raw techno": "Techno",
    "warehouse techno": "Techno",
    # Deep House variants
    "deep house": "Deep House",
    "deep-house": "Deep House",
    "deephouse": "Deep House",
    "soulful house": "Deep House",
    "lounge house": "Deep House",
    "deep tech": "Deep House",
    "chill house": "Deep House",
    "jazzy house": "Deep House",
    # Trance variants
    "trance": "Trance",
    "uplifting trance": "Trance",
    "vocal trance": "Trance",
    "epic trance": "Trance",
    "euphoric trance": "Trance",
    "dream trance": "Trance",
    "hard trance": "Trance",
    "classic trance": "Trance",
    "tech trance": "Trance",
    "eurotrance": "Trance",
    # Drum & Bass variants
    "drum & bass": "Drum & Bass",
    "drum and bass": "Drum & Bass",
    "drum&bass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "d&b": "Drum & Bass",
    "d'n'b": "Drum & Bass",
    "jungle": "Drum & Bass",
    "liquid dnb": "Drum & Bass",
    "liquid drum & bass": "Drum & Bass",
    "neurofunk": "Drum & Bass",
    "liquid funk": "Drum & Bass",
    "jump up": "Drum & Bass",
    # "breakbeat" (~130-140 BPM) ist KEIN DnB (~170) — Mapping entfernt,
    # Audio-Klassifikation entscheidet (Audit-Fix 2026-07-17)
    # Minimal variants
    "minimal": "Minimal",
    "minimal techno": "Minimal",
    "minimal house": "Minimal",
    "minimal tech": "Minimal",
    "micro house": "Minimal",
    "microhouse": "Minimal",
    "clicks & cuts": "Minimal",
    "glitch": "Minimal",
}


# === Genre Mix Profiles ===
# Basiert auf gaengigen DJ-Konventionen pro Genre

@dataclass
class GenreMixProfile:
  """Definiert genre-spezifische Mix-Parameter."""
  name: str
  outro_bars: tuple[int, int]      # (min, max) Bars fuer Outro-Laenge
  transition_bars: tuple[int, int] # (min, max) empfohlener Overlap in Bars
  phrase_unit: int                  # Phrase-Einheit in Bars (8, 16, 32)
  eq_strategy: str                 # EQ-Empfehlung
  mix_technique: str               # Primaere Mix-Technik
  description: str                 # Kurze Genre-Beschreibung fuer UI

GENRE_MIX_PROFILES: dict[str, GenreMixProfile] = {
  "Psytrance": GenreMixProfile(
    name="Psytrance",
    outro_bars=(32, 64),
    transition_bars=(16, 32),
    phrase_unit=16,
    eq_strategy="Bass Swap an der Drop-Grenze",
    mix_technique="Langer Intro/Outro-Overlap mit Bass Swap",
    description="Psytrance: 16-Bar Phrasen, Bass Swap am Drop",
  ),
  "Tech House": GenreMixProfile(
    name="Tech House",
    outro_bars=(16, 32),
    transition_bars=(8, 16),
    phrase_unit=8,
    eq_strategy="Schneller Bass Swap, Hi-Hats laufen lassen",
    mix_technique="Enge Cuts, Loop-basiertes Mixen",
    description="Tech House: 8-Bar Phrasen, schnelle Cuts",
  ),
  "Progressive": GenreMixProfile(
    name="Progressive",
    outro_bars=(32, 64),
    transition_bars=(32, 64),
    phrase_unit=8,
    eq_strategy="Langsamer EQ-Blend ueber 32+ Bars",
    mix_technique="Langer Layer-Blend mit graduellem EQ-Shift",
    description="Progressive: 8-Bar Phrasen, lange Blends",
  ),
  "Melodic Techno": GenreMixProfile(
    name="Melodic Techno",
    outro_bars=(32, 64),
    transition_bars=(16, 32),
    phrase_unit=8,
    eq_strategy="Filter Ride, Bass vom Incoming cutten bis Breakdown",
    mix_technique="Filter Rides, Melodie-bewusstes Blending",
    description="Melodic Techno: 8-Bar Phrasen, Filter Rides",
  ),
  "Techno": GenreMixProfile(
    name="Techno",
    outro_bars=(16, 32),
    transition_bars=(16, 32),
    phrase_unit=8,
    eq_strategy="Bass Swap auf Phrasengrenze: Lows schnell (2-4 Bars), Mids langsam (bis 16 Bars)",
    mix_technique="16-Bar Standard-Blend, 32 Bars fuer volle Layering-Blends",
    description="Techno: 8-Bar Phrasen, 16-32 Bar Blends mit hartem Bass Swap",
  ),
  "Deep House": GenreMixProfile(
    name="Deep House",
    outro_bars=(32, 64),
    transition_bars=(32, 64),
    phrase_unit=8,
    eq_strategy="Sanfter Bass-Blend ueber 32+ Bars, Mids smooth halten",
    mix_technique="Langer smooth Blend, Groove-Matching",
    description="Deep House: 8-Bar Phrasen, lange smoothe Blends",
  ),
  "Trance": GenreMixProfile(
    name="Trance",
    outro_bars=(32, 64),
    transition_bars=(32, 64),
    phrase_unit=16,
    eq_strategy="Bass Swap am Build, Melodie rein-filtern",
    mix_technique="Breakdown-basiertes Blending, Melodie-Layering",
    description="Trance: 16-Bar Phrasen, Breakdown-Blends",
  ),
  "Drum & Bass": GenreMixProfile(
    name="Drum & Bass",
    outro_bars=(16, 32),
    transition_bars=(8, 16),
    phrase_unit=8,
    eq_strategy="Schneller Bass Swap, Drums laufen lassen",
    mix_technique="Double Drop, schnelle Cuts, DJ Neumark style",
    description="DnB: 8-Bar Phrasen, schnelle Drops und Cuts",
  ),
  "Minimal": GenreMixProfile(
    name="Minimal",
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


# Case-insensitive Lookup-Varianten (ID3-Genres sind oft nicht normalisiert)
_GENRE_COMPATIBILITY_NORMALIZED = {
  (a.casefold(), b.casefold()): v for (a, b), v in GENRE_COMPATIBILITY.items()
}
_MIX_PROFILES_NORMALIZED = {k.casefold(): v for k, v in GENRE_MIX_PROFILES.items()}


# Uebergangs-Toleranzen je Genre (Spec 2026-08-19, Abschnitt 9).
# Die Gewichte summieren je Genre auf 1.0. Bis zur Kalibrierung aus dem
# Hoertest tragen alle Genres dieselben Startwerte.
#
# 2026-08-21: groove_weight 0.12 -> 0.30, verteilt aus harmonic (0.246 ->
# 0.16), bpm/energy (0.157 -> 0.12) und genre (0.14 -> 0.12). Anlass: der
# Nutzer hoert, dass die App Paare mit unpassendem Rhythmus waehlt; im
# Hoertest war groove der staerkste Trenner (Spearman +0.53, n=84). Gemessen
# an je einer Playlist aus 60 Psy- und 53 Progressive-Tracks (Harmonic Flow):
#   Psytrance   Bestand:       groove-Median 0.90, 9 Uebergaenge <0.7, 40/59 Camelot>=80
#               0.30 verteilt:               0.93, 4 Uebergaenge <0.7, 35/59
#   Progressive Bestand:                     0.89, 10 <0.7, 31/52
#               0.30 verteilt:               0.87,  7 <0.7, 33/52
#   Melodic Techno (nur 23 Tracks, n=22 Uebergaenge — nicht robust):
#               Bestand:                     0.86,  7 <0.7, 14/22, Harm-Med 80
#               0.30 verteilt:               0.90,  3 <0.7,  7/22, Harm-Med 70
#   Melodic Techno verliert damit die Haelfte der Camelot-Treffer. Das ist
#   der gewaehlte Tausch, und das Genre war im Hoertest die Problemgruppe
#   (36 Uebergaenge, keiner gut) — ob dort Tonart oder Rhythmus wichtiger
#   ist, muessen die Noten zeigen. Die Tabelle ist je Genre ein eigener
#   Dict; ein abweichender Eintrag braucht keine neue Mechanik.
# "0.30 allein aus harmonic" (harmonic 0.066) gewann bei groove staerker,
# kostete aber ein Drittel der guten Tonart-Uebergaenge (25/59 bzw. 23/52)
# — fuer ein Werkzeug namens Harmonic Playlist Generator nicht vertretbar.
# Startwert, kein bewiesener; die Hoertest-Noten ersetzen ihn.
_TOLERANCE_DEFAULTS = {
  "harmonic_weight": 0.160,
  "bpm_weight": 0.120,
  "energy_weight": 0.120,
  "genre_weight": 0.120,
  "groove_weight": 0.300,
  "bass_weight": 0.080,
  "timbre_weight": 0.050,
  "mood_weight": 0.050,
  # Gemessen an 276 Paaren aus 24 Tracks (2026-08-19): kein Paar faellt
  # unter 0,654 Groove-Aehnlichkeit. Der Boden spreizt den Faktor auf den
  # vollen Bereich, statt ihn zwischen 0,65 und 1,0 zu quetschen.
  "groove_sim_floor": 0.65,
  # 0,50 statt frueher 0,25: sub_energy ist seit c01e8f0 ein LEISTUNGS-
  # verhaeltnis (Magnitude quadriert), die Werte haben sich dadurch etwa
  # verdoppelt. Neu gemessen an 18 Tracks: Spanne 0,288 bis 0,790,
  # paarweiser Abstand Median 0,140 / p90 0,306 / max 0,502.
  # Dieser Tabellenwert schlaegt DEFAULT_SUB_DELTA_MAX in
  # transition_features.py — beide muessen zusammen gepflegt werden.
  "bass_delta_max": 0.50,
  "brightness_delta_max": 60.0,
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
}

GENRE_TRANSITION_TOLERANCES: dict[str, dict] = {
  genre: dict(_TOLERANCE_DEFAULTS) for genre in CANONICAL_GENRES
}


# === Konsistenz-Validierung (Drift-Schutz) ===

def _validate_genre_tables() -> None:
    """Prueft beim Import, dass alle Tabellen dieselben kanonischen Genres
    abdecken. Ein vergessenes Genre schlaegt sofort fehl statt still zu driften."""
    canonical = set(CANONICAL_GENRES)
    problems: list[str] = []

    if set(GENRE_PROFILES) != canonical:
        problems.append(
            f"GENRE_PROFILES != CANONICAL_GENRES: "
            f"fehlend={canonical - set(GENRE_PROFILES)}, extra={set(GENRE_PROFILES) - canonical}"
        )
    if set(GENRE_MIX_PROFILES) != canonical:
        problems.append(
            f"GENRE_MIX_PROFILES != CANONICAL_GENRES: "
            f"fehlend={canonical - set(GENRE_MIX_PROFILES)}, extra={set(GENRE_MIX_PROFILES) - canonical}"
        )

    compat_genres = {g for pair in GENRE_COMPATIBILITY for g in pair}
    if compat_genres != canonical:
        problems.append(
            f"GENRE_COMPATIBILITY-Genres != CANONICAL_GENRES: "
            f"fehlend={canonical - compat_genres}, extra={compat_genres - canonical}"
        )
    for genre in canonical:
        if GENRE_COMPATIBILITY.get((genre, genre)) != 1.0:
            problems.append(f"Selbst-Paar fehlt/!=1.0 in GENRE_COMPATIBILITY: {genre}")

    # Audit-Fix 2026-07-21: Cross-Paar-Vollstaendigkeit explizit pruefen.
    # Der fruehere Set-Vergleich (compat_genres != canonical) war durch die
    # Selbst-Paare IMMER trivial erfuellt und uebersah fehlende Cross-Paare —
    # get_genre_compatibility waere dann still auf 0.5 gedriftet.
    missing_pairs = [
        (a, b)
        for a, b in combinations(sorted(canonical), 2)
        if (a, b) not in GENRE_COMPATIBILITY and (b, a) not in GENRE_COMPATIBILITY
    ]
    if missing_pairs:
        problems.append(
            f"GENRE_COMPATIBILITY fehlende Cross-Paare ({len(missing_pairs)}): {missing_pairs}"
        )

    bad_id3_targets = set(ID3_GENRE_MAP.values()) - canonical
    if bad_id3_targets:
        problems.append(f"ID3_GENRE_MAP zielt auf unbekannte Genres: {bad_id3_targets}")

    for genre, profile in GENRE_MIX_PROFILES.items():
        if profile.phrase_unit not in (8, 16, 32):
            problems.append(f"Ungueltige phrase_unit fuer {genre}: {profile.phrase_unit}")

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

    if problems:
        raise ValueError("Genre-Tabellen inkonsistent:\n" + "\n".join(problems))


_validate_genre_tables()
