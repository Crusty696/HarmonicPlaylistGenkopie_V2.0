"""
Genre Compatibility Matrix: Intelligente Cross-Genre Transitions

Definiert, wie "musikal kompatibel" verschiedene Genres zueinander sind.
Nicht binär (kompatibel/nicht), sondern ein Kompatibilitäts-Score 0.0-1.0.

Beispiele:
- House → Tech House: sehr kompatibel (0.95)
- House → Deep House: kompatibel (0.85)
- House → Techno: etwas kompatibel (0.65)
- House → Classical: nicht kompatibel (0.2)
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class GenreCompatibilityMatrix:
  """Bewertet die musikalische Kompatibilität zwischen zwei Genres."""

  # Kompatibilitäts-Scores zwischen Genres (symmetrisch)
  # 1.0 = perfekt kompatibel, 0.0 = völlig unkompatibel
  COMPATIBILITY = {
    # House Familie
    ('House', 'Deep House'): 0.95,
    ('House', 'Tech House'): 0.90,
    ('House', 'Garage House'): 0.85,
    ('House', 'Progressive House'): 0.88,
    ('Deep House', 'Tech House'): 0.85,
    ('Deep House', 'Progressive House'): 0.80,

    # Techno Familie
    ('Techno', 'Minimal Techno'): 0.92,
    ('Techno', 'Deep Techno'): 0.85,
    ('Techno', 'Tech House'): 0.75,

    # Trance Familie
    ('Trance', 'Progressive Trance'): 0.90,
    ('Trance', 'Psytrance'): 0.75,

    # Drum & Bass Familie
    ('Drum and Bass', 'Liquid Drum and Bass'): 0.85,
    ('Drum and Bass', 'Hard Drum and Bass'): 0.70,

    # Dubstep Familie
    ('Dubstep', 'Riddim Dubstep'): 0.85,
    ('Dubstep', 'Wobble Dubstep'): 0.80,

    # Cross-Genre Bridges
    ('House', 'Techno'): 0.70,          # DJ Classic
    ('House', 'Trance'): 0.60,          # Energy kompatibel
    ('House', 'Drum and Bass'): 0.45,   # Stark unterschiedlich
    ('Techno', 'Trance'): 0.65,         # Beide electronic
    ('Techno', 'Drum and Bass'): 0.50,  # Wenig Kompatibilität
    ('Trance', 'Drum and Bass'): 0.55,  # BPM kompatibel

    # Populäre / Dance / Electronic
    ('Electro', 'House'): 0.80,
    ('Electro', 'Techno'): 0.75,
    ('EDM', 'House'): 0.85,
    ('EDM', 'Trance'): 0.80,

    # Hip-Hop / Rap
    ('Hip-Hop', 'Trap'): 0.90,
    ('Hip-Hop', 'Dubstep'): 0.55,       # Trap hat Dubstep-Einfluss
    ('Trap', 'Dubstep'): 0.70,

    # Funk / Soul / Disco
    ('Funk', 'Disco'): 0.85,
    ('Funk', 'House'): 0.75,            # House hat Funk-Roots
    ('Disco', 'House'): 0.80,

    # Jazz / Soul
    ('Jazz', 'Soul'): 0.85,
    ('Soul', 'R&B'): 0.90,
    ('Jazz', 'R&B'): 0.65,

    # Rock / Metal
    ('Rock', 'Hard Rock'): 0.90,
    ('Rock', 'Metal'): 0.60,

    # Ambient / Experimental
    ('Ambient', 'Downtempo'): 0.85,
    ('Downtempo', 'Chillout'): 0.90,
  }

  @staticmethod
  def get_compatibility(genre1: str, genre2: str) -> float:
    """
    Berechnet Kompatibilität zwischen zwei Genres.

    Args:
      genre1: Erstes Genre
      genre2: Zweites Genre

    Returns:
      Score 0.0-1.0 (1.0 = perfekt kompatibel)
    """
    # Wenn gleich: perfekt kompatibel
    if genre1 and genre2 and genre1.lower() == genre2.lower():
      return 1.0

    # Wenn fehlend: neutral
    if not genre1 or not genre2:
      return 0.5

    # Normalisiere zu Lowercase für Vergleich
    g1 = genre1.lower()
    g2 = genre2.lower()

    # Suche im Dictionary (bidirektional)
    for (stored_g1, stored_g2), score in GenreCompatibilityMatrix.COMPATIBILITY.items():
      if (g1 == stored_g1.lower() and g2 == stored_g2.lower()) or \
         (g1 == stored_g2.lower() and g2 == stored_g1.lower()):
        return score

    # Heuristische Fallbacks basierend auf Genre-Kategorie
    if GenreCompatibilityMatrix._is_electronic(g1) and GenreCompatibilityMatrix._is_electronic(g2):
      return 0.65  # Electronic-Genres sind meist kompatibel

    if GenreCompatibilityMatrix._is_acoustic(g1) and GenreCompatibilityMatrix._is_acoustic(g2):
      return 0.70  # Acoustic-Genres sind meist kompatibel

    if GenreCompatibilityMatrix._is_electronic(g1) and GenreCompatibilityMatrix._is_acoustic(g2):
      return 0.35  # Electronic + Acoustic: schwierig

    # Fallback: unbekannte Genres
    return 0.5

  @staticmethod
  def _is_electronic(genre: str) -> bool:
    """Ist das Genre elektronisch?"""
    electronic_keywords = [
      'house', 'techno', 'trance', 'drum and bass', 'dnb', 'dubstep',
      'edm', 'electro', 'electronic', 'synth', 'ambient', 'downtempo'
    ]
    return any(keyword in genre.lower() for keyword in electronic_keywords)

  @staticmethod
  def _is_acoustic(genre: str) -> bool:
    """Ist das Genre akustisch/organisch?"""
    acoustic_keywords = [
      'jazz', 'soul', 'r&b', 'funk', 'disco', 'rock', 'folk',
      'classical', 'acoustic', 'guitar', 'blues'
    ]
    return any(keyword in genre.lower() for keyword in acoustic_keywords)

  @staticmethod
  def log_compatibility(genre1: str, genre2: str) -> None:
    """Debug: Zeige Kompatibilität."""
    score = GenreCompatibilityMatrix.get_compatibility(genre1, genre2)
    logger.debug(f"Genre compatibility {genre1} → {genre2}: {score:.2f}")
