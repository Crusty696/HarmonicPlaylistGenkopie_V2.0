"""
Camelot-Wheel Testdaten und Erwartungswerte.
Definiert alle harmonischen Regeln fuer DJ-Mixing Tests.
"""

# Alle 24 erwarteten Camelot-Zuordnungen
EXPECTED_CAMELOT_MAP = {
  # Minor Keys (A-Seite)
  ('A', 'Minor'): '8A',
  ('A#', 'Minor'): '3A',
  ('B', 'Minor'): '10A',
  ('C', 'Minor'): '5A',
  ('C#', 'Minor'): '12A',
  ('D', 'Minor'): '7A',
  ('D#', 'Minor'): '2A',
  ('E', 'Minor'): '9A',
  ('F', 'Minor'): '4A',
  ('F#', 'Minor'): '11A',
  ('G', 'Minor'): '6A',
  ('G#', 'Minor'): '1A',
  # Major Keys (B-Seite)
  ('C', 'Major'): '8B',
  ('C#', 'Major'): '3B',
  ('D', 'Major'): '10B',
  ('D#', 'Major'): '5B',
  ('E', 'Major'): '12B',
  ('F', 'Major'): '7B',
  ('F#', 'Major'): '2B',
  ('G', 'Major'): '9B',
  ('G#', 'Major'): '4B',
  ('A', 'Major'): '11B',
  ('A#', 'Major'): '6B',
  ('B', 'Major'): '1B',
}

# Erwartete Compatibility-Scores fuer Camelot-Regeln
# Format: (code1, code2, erwarteter_score, regel_name)
COMPATIBILITY_RULES = [
  # Same Key = 100
  ("8A", "8A", 100, "Same Key"),
  ("1B", "1B", 100, "Same Key"),

  # Relative Major/Minor = 90 (gleiche Nummer, anderer Buchstabe)
  ("8A", "8B", 90, "Relative Major/Minor"),
  ("5B", "5A", 90, "Relative Major/Minor"),

  # Adjacent Keys = 80 (+-1 im Rad, gleicher Buchstabe)
  ("8A", "9A", 80, "Adjacent +1"),
  ("8A", "7A", 80, "Adjacent -1"),
  ("8B", "9B", 80, "Adjacent +1 Major"),

  # Wraparound 12->1 = 80
  ("12A", "1A", 80, "Wraparound 12->1"),
  ("1A", "12A", 80, "Wraparound 1->12"),

  # Plus Four = 70 (gleicher Buchstabe, +4 Positionen)
  ("8A", "12A", 70, "Plus Four"),
  ("3B", "7B", 70, "Plus Four Major"),

  # Plus Seven = 65 (Quintenzirkel)
  ("8A", "3A", 65, "Plus Seven"),

  # Energy Boost Minor->Major = 85
  ("8A", "8B", 90, "Relative = Energy Boost implizit"),

  # Diagonal = 60 (anderer Buchstabe, +-1 Nummer)
  ("8A", "9B", 60, "Diagonal +1"),
  ("8A", "7B", 60, "Diagonal -1"),
]

# Inkompatible Kombinationen (sollten niedrigen Score liefern)
INCOMPATIBLE_PAIRS = [
  ("8A", "2B"),  # Weit entfernt
  ("1A", "7B"),  # Keine harmonische Beziehung
  ("3B", "9A"),  # Keine Regel greift
]

# BPM-Toleranz Testfaelle
BPM_TOLERANCE_CASES = [
  # (bpm1, bpm2, tolerance, should_be_compatible)
  (128.0, 128.0, 3.0, True),   # Gleich
  (126.0, 128.0, 3.0, True),   # Innerhalb
  (128.0, 132.0, 3.0, False),  # Ueber Toleranz
  (128.0, 131.0, 3.0, True),   # Exakt auf Toleranzgrenze (<=)
  (128.0, 130.9, 3.0, True),   # Knapp innerhalb
  (120.0, 128.0, 10.0, True),  # Grosse Toleranz
]


def get_related_key(base_key: str, relation: str) -> str:
  """Liefert einen harmonisch verwandten Key basierend auf der Beziehung.

  Args:
    base_key: Start-Camelot Key (z.B. "8A")
    relation: Beziehungstyp ("same", "energy_up", "energy_down", "relative")

  Returns:
    Verwandter Camelot Key
  """
  number = int(base_key[:-1])
  mode = base_key[-1]

  if relation == "same":
    return base_key

  elif relation == "energy_up":
    new_number = (number % 12) + 1
    return f"{new_number}{mode}"

  elif relation == "energy_down":
    new_number = ((number - 2) % 12) + 1
    return f"{new_number}{mode}"

  elif relation == "relative":
    new_mode = "B" if mode == "A" else "A"
    return f"{number}{new_mode}"

  else:
    raise ValueError(f"Unknown relation: {relation}")
