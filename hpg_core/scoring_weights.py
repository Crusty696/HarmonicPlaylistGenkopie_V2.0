"""
Intelligentes Scoring-System: DynamicWeightCalculator
Berechnet adaptiv die Gewichte für verschiedene Score-Komponenten
basierend auf musikalischem Kontext.
"""

from .scoring_context import PlaylistContext
import logging

logger = logging.getLogger(__name__)


class DynamicWeightCalculator:
  """Berechnet Gewichte basierend auf Playlist-Kontext."""

  # Basis-Gewichte (Standard, Phase-unabhängig)
  BASE_WEIGHTS = {
      'harmonic': 0.30,
      'bpm': 0.25,
      'energy': 0.25,
      'genre': 0.15,
      'structure': 0.05,
  }

  def calculate_weights(self, context: PlaylistContext, strategy: str = "HARMONIC_FLOW") -> dict[str, float]:
    """
    Berechnet angepasste Gewichte basierend auf Kontext und Strategie.

    Args:
      context: PlaylistContext mit Info über aktuelle Position, Trend, etc.
      strategy: Playlist-Strategie (z.B. "PEAK_TIME", "GENRE_FLOW")

    Returns:
      Dictionary mit Gewichten für ['harmonic', 'bpm', 'energy', 'genre', 'structure']
      Die Gewichte summieren sich zu 1.0
    """

    # Start mit Basis-Gewichten
    weights = dict(self.BASE_WEIGHTS)

    # === PHASE-SPEZIFISCHE ANPASSUNGEN ===
    phase = context.get_playlist_phase()

    if phase == "INTRO":
      # Am Anfang: Harmonic Flow ist König, Energie kann niedrig sein
      weights['harmonic'] = 0.50   # ↑ "Setz einen guten harmonischen Ton"
      weights['energy'] = 0.15     # ↓ "Energie muss nicht hoch sein"
      weights['bpm'] = 0.20
      weights['genre'] = 0.10
      weights['structure'] = 0.05

    elif phase == "BUILD_UP":
      # Beim Build-Up: Energie-Progression ist wichtig
      weights['energy'] = 0.40     # ↑ "Baue Spannung auf"
      weights['harmonic'] = 0.25   # ↓ "Weniger kritisch während Aufbau"
      weights['bpm'] = 0.20
      weights['genre'] = 0.10
      weights['structure'] = 0.05

    elif phase == "PEAK":
      # Am Peak: Energie konsistent halten, gute BPM-Übergänge
      weights['energy'] = 0.35     # ↑ "Halte die Spannung"
      weights['bpm'] = 0.30        # ↑ "Smooth Übergänge wichtig"
      weights['harmonic'] = 0.20   # ↓ "Sekundär beim Peak"
      weights['genre'] = 0.10
      weights['structure'] = 0.05

    elif phase == "OUTRO":
      # Am Outro: Sanfte Abfahrt, Harmonic wichtig für musikalische Auflösung
      weights['energy'] = 0.30     # "Energie runter fahren"
      weights['harmonic'] = 0.35   # ↑ "Musikalische Auflösung"
      weights['bpm'] = 0.20
      weights['genre'] = 0.10
      weights['structure'] = 0.05

    # === TREND-SPEZIFISCHE ANPASSUNGEN ===

    energy_trend = context.get_energy_trend()
    bpm_trend = context.get_bpm_trend()
    genre_streak = context.get_genre_streak()

    if energy_trend == "RISING":
      # Wenn Energie steigt: verstärke den Trend
      weights['energy'] *= 1.2      # "Mach weiter hoch!"
      weights['bpm'] *= 0.9         # BPM weniger wichtig

    elif energy_trend == "FALLING":
      # Wenn Energie fällt: sanft weiter runter
      weights['energy'] *= 1.1
      weights['harmonic'] *= 1.1    # "Musikalisch bleiben während Abstieg"

    elif energy_trend == "STABLE":
      # Wenn Energie stabil: könnte sich etwas ändern
      # Genre-Fatigue detektieren
      if genre_streak > 5:
        weights['genre'] = 0.05      # ↓ "Erlaube Genre-Wechsel"
        weights['energy'] *= 1.15    # ↑ "Verändere mit Energie"

    if bpm_trend == "ACCELERATING":
      # BPM beschleunigt sich: verstärke das
      weights['bpm'] *= 1.15
      weights['energy'] *= 1.1       # Energie folgt oft BPM

    elif bpm_trend == "DECELERATING":
      # BPM verlangsamt sich: sanfte Fortsetzung
      weights['bpm'] *= 1.05

    # === STRATEGIE-SPEZIFISCHE ANPASSUNGEN ===

    if strategy == "PEAK_TIME":
      # Peak Time: Energie ist König
      weights['energy'] = 0.45       # ↑ Energie dominiert
      weights['harmonic'] = 0.20
      weights['bpm'] = 0.20
      weights['genre'] = 0.10
      weights['structure'] = 0.05

    elif strategy == "GENRE_FLOW":
      # Genre Flow: Genre-Konsistenz priorisieren
      weights['genre'] = 0.35        # ↑ Genre zusammenhalten
      weights['harmonic'] = 0.35     # ↑ Aber harmonisch bleiben
      weights['energy'] = 0.15
      weights['bpm'] = 0.10
      weights['structure'] = 0.05

    elif strategy == "ENERGY_WAVE":
      # Energy Wave: Energie-Muster erzeugen
      weights['energy'] = 0.50       # ↑ Energie-Welle ist Fokus
      weights['harmonic'] = 0.15
      weights['bpm'] = 0.15
      weights['genre'] = 0.15
      weights['structure'] = 0.05

    elif strategy == "EMOTIONAL_JOURNEY":
      # Emotional Journey: Emotionale Kohärenz & Genre-Storytelling
      weights['harmonic'] = 0.40     # ↑ Emotionale Kohärenz
      weights['genre'] = 0.25        # ↑ Genre-Storytelling
      weights['energy'] = 0.20
      weights['bpm'] = 0.10
      weights['structure'] = 0.05

    elif strategy == "HARMONIC_CONSISTENT":
      # Strictest harmonic mixing
      weights['harmonic'] = 0.50     # ↑ Harmonic ist alles
      weights['bpm'] = 0.25
      weights['energy'] = 0.15
      weights['genre'] = 0.05
      weights['structure'] = 0.05

    elif strategy == "BPM_PROGRESSION":
      # BPM Progression: Tempo-Kurve
      weights['bpm'] = 0.40          # ↑ BPM ist Fokus
      weights['energy'] = 0.25
      weights['harmonic'] = 0.20
      weights['genre'] = 0.10
      weights['structure'] = 0.05

    elif strategy == "SMOOTH_CROSSFADE":
      # Smooth Crossfade: minimale Überraschungen
      weights['bpm'] = 0.35          # ↑ Smooth BPM
      weights['energy'] = 0.25
      weights['harmonic'] = 0.25
      weights['structure'] = 0.10    # ↑ Structure wichtig für Übergänge
      weights['genre'] = 0.05

    # === NORMALISIEREN (Summe = 1.0) ===
    total = sum(weights.values())
    if total > 0:
      weights = {k: v / total for k, v in weights.items()}
    else:
      weights = dict(self.BASE_WEIGHTS)

    return weights

  def log_weights(self, context: PlaylistContext, strategy: str) -> None:
    """Debug: Zeige die berechneten Gewichte."""
    weights = self.calculate_weights(context, strategy)
    logger.debug(
        f"Weights for phase={context.get_playlist_phase()}, "
        f"trend={context.get_energy_trend()}, "
        f"strategy={strategy}: {weights}"
    )
