"""
DJ Brain - Genre-spezifische Mix-Logik fuer den Harmonic Playlist Generator.

Berechnet intelligente, genre-spezifische Mix-Punkte basierend auf:
- Track-Strukturanalyse (Intro/Build/Drop/Breakdown/Outro)
- Genre-spezifische DJ-Konventionen (Phrase-Laenge, EQ-Strategie, Transition-Technik)
- Genre-Kompatibilitaets-Matrix fuer Cross-Genre-Transitions

Basiert auf Research von Pioneer DJ, Club Ready DJ School, DJ Tech Tools u.a.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .config import (
  DEFAULT_BPM,
  DEFAULT_SECTION_ENERGY,
  GAIN_DIFF_SHOW_DB,
  GAIN_DIFF_WARN_DB,
  KEY_CONFIDENCE_UNCERTAIN,
  METER,
)
from .genres import (
  DEFAULT_MIX_PROFILE,
  GENRE_COMPATIBILITY,
  GENRE_MIX_PROFILES,
  GenreMixProfile,
  _GENRE_COMPATIBILITY_NORMALIZED,
  _MIX_PROFILES_NORMALIZED,
)
from .models import (
  Track,
  effective_bpm_diff,
  get_camelot_components,
  quantize_to_grid,
  seconds_to_bars,
)


# === Genre-Wissen ===
# Audit-Refactoring 2026-07-17: alle Genre-Tabellen leben zentral in genres.py
# (Single Source of Truth mit Import-Validierung). Hier re-exportiert, damit
# bestehende Importe (analysis, structure_analyzer, main, Tests) stabil bleiben.
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

  # Case-insensitiver Fallback: ID3-Genres kommen oft kleingeschrieben
  # ("tech house" statt "Tech House") -- sonst stiller 0.5-Fallback
  key = (genre_a.casefold(), genre_b.casefold())
  score = _GENRE_COMPATIBILITY_NORMALIZED.get(key)
  if score is None:
    score = _GENRE_COMPATIBILITY_NORMALIZED.get((key[1], key[0]))
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
  profile = GENRE_MIX_PROFILES.get(genre)
  if profile is None and genre:
    profile = _MIX_PROFILES_NORMALIZED.get(genre.casefold())
  return profile if profile is not None else DEFAULT_MIX_PROFILE


# === Mix-Punkt-Berechnung ===

def calculate_genre_aware_mix_points(
  sections: list[dict],
  bpm: float,
  duration: float,
  genre: str,
  anchor: float = 0.0,
  first_downbeat: float | None = None,
) -> tuple[float, float, int, int]:
  """
  Berechnet genre-spezifische Mix-In/Out-Punkte basierend auf Track-Struktur.

  Logik:
  - Mix-In: Sektion mit Substanz (Energie-Dichte-Check)
  - Mix-Out: Punkt, an dem der Track "ausduennt"
  - Quantisiert aufs Phrasen-Gitter fuer musikalisches Phrase-Alignment

  Args:
    anchor: Anker des Phrasen-Gitters in Sekunden (seit A1: phrase_anchor,
      vorher first_downbeat) — das Gitter liegt auf anchor + k*grid statt
      auf k*grid. 0.0 = bisheriges Verhalten (Raster ab t=0).
    first_downbeat: Takt-Anker in Sekunden (AUDIT-FIX R3, 2026-07-26) —
      bindet die min_mix_in-Untergrenze an den Track-ANFANG statt an den
      (ggf. spaeten) Phrasen-Anker. None = Fallback auf anchor
      (Alt-Verhalten fuer Aufrufer ohne Downbeat-Info).
  """
  # AUDIT-FIX Z1 (2026-08-14): Der Guard reichte die ungueltige duration
  # unveraendert als mix_out durch — bei duration=-5.0 kam (0.0, -5.0) heraus
  # und verletzte damit genau die Invariante 0 <= mix_in < mix_out, die er
  # schuetzen soll. Zusaetzlich griffen die Vergleiche bei NaN/inf gar nicht
  # (NaN-Vergleiche sind immer False), die Funktion lief ungebremst durch und
  # lieferte Mix-Punkte ohne jede Dauer-Begrenzung. Jetzt explizit auf
  # Endlichkeit pruefen und nie einen negativen/nicht-endlichen mix_out
  # zurueckgeben.
  if (
    not sections
    or not math.isfinite(bpm)
    or not math.isfinite(duration)
    or bpm <= 0
    or duration <= 0
  ):
    safe_duration = duration if math.isfinite(duration) and duration > 0 else 0.0
    return 0.0, safe_duration, 0, 0

  profile = get_mix_profile(genre)
  seconds_per_beat = 60.0 / bpm
  seconds_per_bar = seconds_per_beat * METER

  # --- Mix-In: Wo faengt der optimale Mix-Bereich an? ---
  mix_in_time = _find_mix_in_point(sections, profile, seconds_per_bar, anchor)

  # --- Mix-Out: Wo faengt der Track an auszuklingen? ---
  mix_out_time = _find_mix_out_point(sections, profile, seconds_per_bar, duration, anchor)

  # Genre-spezifisches Phrase-Gitter fuer musikalisches Phrase-Alignment
  # (Downbeat-Feature 2026-07-17: Gitter am ersten Downbeat verankert)
  grid_seconds = seconds_per_bar * profile.phrase_unit
  if grid_seconds > 0:
    mix_in_time = quantize_to_grid(mix_in_time, grid_seconds, anchor, "ceil")
    mix_out_time = quantize_to_grid(mix_out_time, grid_seconds, anchor, "floor")

  # Sicherheitsgrenzen -- sektions- und phrasenbasiert statt Prozent-Schema.
  # Ein DJ orientiert sich an Struktur-Grenzen (Intro-Ende, Outro-Start) und
  # Phrasenraster, nicht an festen 40%/60%-Positionen.
  intro_end = _get_intro_end_from_sections(sections)
  outro_start = _get_outro_start_from_sections(sections, duration)

  # AUDIT-FIX R3 (2026-07-26): Untergrenze an den TAKT-Anker (first_downbeat)
  # binden. anchor ist seit A1 der PHRASEN-Anker und kann bis zu
  # phrase_unit-1 Bars (~28 s bei 16-Bar-Phrasen) hinter dem ersten Downbeat
  # liegen — min_mix_in wanderte entsprechend nach hinten und kollabierte das
  # Mix-Fenster in den Notfall-Prozent-Pfad. Der Sinn der Grenze ("nicht in
  # die allererste Phrase mixen") haengt am Track-Anfang, nicht an der
  # Phrasen-Phase.
  base_anchor = first_downbeat if first_downbeat is not None else anchor
  min_mix_in = max(intro_end, base_anchor + grid_seconds)
  # Mix-Out AUF der Outro-Grenze ist DJ-Standard (Ausstieg wenn das Outro
  # beginnt) — floor-Quantisierung garantiert bereits mix_out <= outro_start
  max_mix_out = min(outro_start, duration - grid_seconds)
  min_window = grid_seconds * 2  # mind. 2 Phrasen nutzbares Mix-Fenster
  grid_epsilon = 1e-9  # Verhindert Doppel-Quantisierung durch Float-Rauschen

  if max_mix_out - min_mix_in >= min_window:
    mix_in_time = max(min_mix_in, min(mix_in_time, max_mix_out - min_window))
    mix_out_time = max(mix_in_time + min_window, min(mix_out_time, max_mix_out))
    # Konsolidierung 2026-07-17: Clamps koennen die Punkte vom Phrasen-Gitter
    # schieben — zurueck aufs Gitter quantisieren, solange die Grenzen halten
    # (reale DJ-Cues liegen auf Phrasengrenzen, arXiv 2407.06823)
    if grid_seconds > 0:
      aligned_out = quantize_to_grid(
        mix_out_time + grid_epsilon, grid_seconds, anchor, "floor"
      )
      if aligned_out - mix_in_time >= min_window:
        mix_out_time = aligned_out
      aligned_in = quantize_to_grid(
        mix_in_time - grid_epsilon, grid_seconds, anchor, "ceil"
      )
      if mix_out_time - aligned_in >= min_window:
        mix_in_time = aligned_in
  else:
    # Track zu kurz bzw. Sektionen zu eng: Notfall-Prozente als letzte Instanz
    mix_in_time = max(intro_end, duration * 0.15)
    mix_out_time = min(outro_start - seconds_per_bar, duration * 0.85)

  if mix_out_time <= mix_in_time:
    # M7-Fix: auch der Notfall-Fallback respektiert Intro/Outro-Grenzen,
    # reine Prozente nur als allerletzte Instanz
    mix_in_time = max(intro_end, duration * 0.15)
    mix_out_time = min(max(outro_start - seconds_per_bar, 0.0), duration * 0.85)
    if mix_out_time <= mix_in_time:
      mix_in_time = duration * 0.15
      mix_out_time = duration * 0.85

  # AUDIT-FIX N5 (2026-07-24): Auch die Notfall-Pfade liefern jetzt Werte auf
  # dem Phrasen-Gitter, wenn das ohne Fenster-Kollaps moeglich ist. Vorher
  # gingen reine Prozentwerte (duration*0.15/0.85) ungefiltert und off-grid
  # in Track.mix_in_point/mix_out_point.
  # AUDIT-FIX N5b (2026-08-14): Die Quantisierung wurde vorher nur auf dem
  # PHRASEN-Gitter versucht. Kollabiert das Fenster dort (kurze Tracks, enge
  # Sektionen), blieben die rohen Prozentwerte off-grid stehen — auf
  # synthetischen Kurztracks bis zu 12.6 s neben der Phrasengrenze. Analog zu
  # align_ai_mix_points wird jetzt das feinere Bar-Gitter als zweite Stufe
  # versucht; erst wenn auch das kein gueltiges Fenster liefert, bleibt der
  # Rohwert (Invariante 1 hat Vorrang vor Invariante 2).
  for candidate_grid in (grid_seconds, seconds_per_bar):
    if candidate_grid <= 0:
      continue
    q_in = quantize_to_grid(
      mix_in_time - grid_epsilon, candidate_grid, anchor, "ceil"
    )
    q_out = quantize_to_grid(
      mix_out_time + grid_epsilon, candidate_grid, anchor, "floor"
    )
    if 0.0 <= q_in < q_out <= duration:
      mix_in_time, mix_out_time = q_in, q_out
      break

  # In Bars umrechnen
  mix_in_bars = seconds_to_bars(mix_in_time, bpm)
  mix_out_bars = seconds_to_bars(mix_out_time, bpm)

  # Interne Vertragsschnittstelle: Quantisierte Werte bleiben ungerundet.
  # Anzeige-/Exportpfade runden erst an der jeweiligen Ausgabegrenze.
  return mix_in_time, mix_out_time, mix_in_bars, mix_out_bars


def _find_mix_in_point(
  sections: list[dict],
  profile: GenreMixProfile,
  seconds_per_bar: float,
  anchor: float = 0.0,
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
  all_energies = [s.get("avg_energy", DEFAULT_SECTION_ENERGY) for s in sections]
  avg_energy = sum(all_energies) / len(all_energies) if all_energies else DEFAULT_SECTION_ENERGY

  # --- Kandidaten: Sektionen nach Intro, nicht Outro ---
  # AUDIT-FIX E3 (2026-07-24): "unanalysed"-Pseudo-Sections (Coverage-Luecke
  # bei langen Tracks) sind keine gueltigen Mix-Kandidaten.
  candidates = [
    s for s in sections
    if s.get("start_time", 0.0) >= intro_end
    and s.get("label", "main") not in ("intro", "outro", "unanalysed")
  ]

  if not candidates:
    # Kein nutzbarer Bereich nach Intro gefunden
    phrase_seconds = seconds_per_bar * profile.phrase_unit
    if phrase_seconds > 0:
      return max(intro_end, quantize_to_grid(intro_end, phrase_seconds, anchor))
    return intro_end

  # AUDIT-FIX B4 (2026-07-24): Ein DJ startet den Mix-In frueh im Track.
  # Ohne Positionsterm gewann z. B. ein spaetes "build" bei 64 % der Laenge
  # gegen ein fruehes "main". Suchfenster: erste ~40 % des Track-Bereichs;
  # nur wenn dort nichts liegt, alle Kandidaten zulassen.
  track_end = max(s.get("end_time", 0.0) for s in sections)
  search_limit = max(intro_end, track_end * 0.40)
  early = [s for s in candidates if s.get("start_time", 0.0) <= search_limit]
  if early:
    candidates = early

  # --- Beste Sektion waehlen ---
  # Praeferenz fuer Mix-In: build > main > breakdown > drop;
  # bei gleichem Label gewinnt die FRUEHERE Section (Positionsterm),
  # Energie-Naehe nur noch als Tiebreak.
  label_priority = {"build": 0, "main": 1, "breakdown": 2, "drop": 3}

  best = min(candidates, key=lambda s: (
    label_priority.get(s.get("label", "main"), 99),
    s.get("start_time", 0.0),
    abs(s.get("avg_energy", DEFAULT_SECTION_ENERGY) - avg_energy * 0.75),
  ))

  mix_in = best.get("start_time", intro_end)

  # --- Quantisierung auf Phrasen-Grenze (ceil = NACH Intro), downbeat-verankert ---
  phrase_seconds = seconds_per_bar * profile.phrase_unit
  if phrase_seconds > 0:
    mix_in = quantize_to_grid(mix_in, phrase_seconds, anchor, "ceil")

  # --- Guard: NIEMALS vor Intro-Ende ---
  mix_in = max(mix_in, intro_end)

  return mix_in


def _find_mix_out_point(
  sections: list[dict],
  profile: GenreMixProfile,
  seconds_per_bar: float,
  duration: float,
  anchor: float = 0.0,
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
    avg_outro_bars = (profile.outro_bars[0] + profile.outro_bars[1]) / 2.0
    return duration - (avg_outro_bars * seconds_per_bar)

  # --- Outro-Start bestimmen ---
  outro_start = _get_outro_start_from_sections(sections, duration)

  # --- Kandidaten: Sektionen vor Outro, nicht Intro ---
  # AUDIT-FIX E3 (2026-07-24): "unanalysed" ausgeschlossen (siehe Mix-In).
  candidates = [
    s for s in sections
    if s.get("end_time", 0.0) <= outro_start
    and s.get("label", "main") not in ("intro", "outro", "unanalysed")
  ]

  if not candidates:
    # Kein nutzbarer Bereich vor Outro
    phrase_seconds = seconds_per_bar * profile.phrase_unit
    if phrase_seconds > 0:
      mix_out = quantize_to_grid(outro_start, phrase_seconds, anchor, "floor")
      return max(0.0, min(mix_out, outro_start))
    return outro_start

  # --- Letzte starke Sektion VOR Outro ---
  # AUDIT-FIX B5 (2026-07-24): Position ist jetzt das PRIMAERE Kriterium.
  # Vorher schlug das Label die Position: ein "main" bei 50 % gewann gegen
  # ein "breakdown" bei 85 % — der Mix-Out landete in der Track-Mitte.
  # Ein DJ steigt so spaet wie musikalisch sinnvoll aus; das Label
  # entscheidet nur noch bei (praktisch) gleicher Endzeit. Drops bleiben
  # als Ausstieg unattraktiv (Tiebreak-Prioritaet).
  label_priority = {"main": 0, "breakdown": 1, "build": 2, "drop": 3}
  best = min(candidates, key=lambda s: (
    -s.get("end_time", 0.0),
    label_priority.get(s.get("label", "main"), 99),
  ))

  # Normalerweise mix_out am Ende dieser Sektion
  mix_out = best.get("end_time", outro_start)

  # --- Quantisierung auf Phrasen-Grenze (floor = VOR Outro), downbeat-verankert ---
  phrase_seconds = seconds_per_bar * profile.phrase_unit
  if phrase_seconds > 0:
    mix_out = quantize_to_grid(mix_out, phrase_seconds, anchor, "floor")

  # --- Guard: STRIKT vor dem Outro-Start ---
  # AUDIT-FIX B5-Regression (2026-07-24): Seit die Position das Primaerkriterium
  # ist, kann die gewaehlte Sektion exakt am Outro-Start enden (z. B. letzter
  # Drop 240-360, Outro ab 360). floor lieferte dann 360 == outro_start und der
  # Uebergang reichte in das Outro hinein. Ein DJ steigt VOR dem Outro aus:
  # landet der Punkt auf/hinter der Outro-Grenze, eine Phrase zurueck (analog
  # calculate_paired_mix_points). Nur wenn ein echtes Outro existiert
  # (outro_start < duration).
  if outro_start < duration and mix_out >= outro_start and phrase_seconds > 0:
    mix_out = quantize_to_grid(outro_start - phrase_seconds, phrase_seconds, anchor, "floor")

  mix_out = min(mix_out, outro_start)

  # Wir wollen auch vermeiden, dass der Uebergang direkt im Drop liegt, wenn es Alternativen gibt
  return max(0.0, mix_out)


# === DJ Empfehlungen ===

@dataclass
class TransitionContext:
  """Kontextobjekt fuer Transition-Berechnungen, buendelt verwandte Parameter."""
  bpm_a: float
  bpm_b: float
  energy_a: float
  energy_b: float
  profile_a: GenreMixProfile
  profile_b: GenreMixProfile


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

  # NEU: Track-spezifische Empfehlungen (immer ausgefuellt, nie generisch)
  bpm_advice: str = ""        # Konkrete BPM/Pitching-Empfehlung
  key_advice: str = ""        # Camelot-basierte Tonart-Empfehlung
  energy_advice: str = ""     # Energie-Empfehlung basierend auf tatsaechlicher Differenz
  gain_advice: str = ""       # LUFS-basierte Gain-Angleichung (2026-07-17)
  transition_type: str = "smooth_blend"  # Transition-Typ (fuer Farben in UI)

  # Advanced Audio Alignment
  bass_match_advice: str = ""
  rhythm_advice: str = ""
  
  # Paarspezifische Mix-Punkte (ueberschreiben die gespeicherten Track-Werte)
  # -1.0 = nicht berechnet -> UI nutzt track.mix_out_point / track.mix_in_point
  adjusted_mix_out_a: float = -1.0   # Angepasster Mix-Out fuer Track A (Sekunden)
  adjusted_mix_in_b: float = -1.0    # Angepasster Mix-In fuer Track B (Sekunden)
  # Berechnete Overlap-Dauer des Uebergangs (Tail von A, begrenzt durch den
  # Rest von B). Hinweis: in der Playlist-Pipeline ist transition_bars die
  # autoritative Overlap-Quelle — playlist.compute_transition_recommendations
  # ueberschreibt overlap_seconds danach mit seconds_per_bar * transition_bars.
  overlap_seconds: float = 0.0


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

  # Transition-Laenge: Dynamisch basierend auf tatsaechlichem BPM/Energy-Delta
  ctx = TransitionContext(
    bpm_a=track_a.bpm,
    bpm_b=track_b.bpm,
    energy_a=float(track_a.energy),
    energy_b=float(track_b.energy),
    profile_a=profile_a,
    profile_b=profile_b,
  )
  transition_bars = _dynamic_transition_bars(ctx)

  # Mix-Technik: Verwende die des eingehenden Tracks (der DJ passt sich an)
  mix_technique = profile_b.mix_technique
  eq_advice = profile_b.eq_strategy

  # Wenn Cross-Genre, spezifische Empfehlung
  if genre_a != genre_b and genre_a != "Unknown" and genre_b != "Unknown":
    mix_technique = _get_cross_genre_technique(genre_a, genre_b)
    eq_advice = _get_cross_genre_eq(genre_a, genre_b)

  # Paarspezifische Mix-Punkte: Overlap zwischen Outro(A) und Intro(B) abstimmen
  adjusted_mix_out_a, adjusted_mix_in_b = calculate_paired_mix_points(track_a, track_b)
  overlap_seconds = max(0.0, track_a.duration - adjusted_mix_out_a)
  # AUDIT-FIX B3/M1 (2026-08-14): Der alte "M1-Deckel" war
  #   intro_window_b = _get_intro_end(track_b) - adjusted_mix_in_b
  # und sollte verhindern, dass der Crossfade ueber das Intro-Ende von B
  # hinauslaeuft. Seit der Intro-Guard in calculate_paired_mix_points den
  # Mix-In auf ceil(intro_end) legt, ist diese Differenz per Konstruktion
  # <= 0 — der Deckel griff auf 51 realen Paaren genau 1x (und auch nur im
  # Sonderfall "Track B ohne Intro-Sektion", der jetzt ebenfalls geschlossen
  # ist). Der tatsaechlich bindende Deckel ist der Rest von Track B nach dem
  # Mix-In: laenger als B noch spielt kann der Uebergang nicht sein.
  room_b = max(0.0, track_b.duration - adjusted_mix_in_b)
  overlap_seconds = min(overlap_seconds, room_b)

  # Struktur-Kontext auf Basis der wirklich empfohlenen paarspezifischen Punkte
  outgoing_section = _get_section_at_time(track_a, adjusted_mix_out_a, "out")
  incoming_section = _get_section_at_time(track_b, adjusted_mix_in_b, "in")
  structure_note = _build_structure_note(outgoing_section, incoming_section)


  # Risiko-Bewertung
  risk_notes = _assess_transition_risks(
    track_a, track_b, compat, adjusted_mix_out_a, adjusted_mix_in_b
  )
  
  # Texture Similarity (Phase 3)
  
  # Rhythm Advice
  pr_a = track_a.percussive_ratio
  pr_b = track_b.percussive_ratio
  rhythm_adv = ""
  if pr_a > 0.7 and pr_b > 0.7:
      rhythm_adv = "Beide Tracks sehr perkussiv - Vorsicht vor Rhythmus-Salat, kurzen Übergang wählen"
  elif pr_b < 0.3:
      rhythm_adv = "Incoming Track sehr tonal - ideal für lange Filter-Blends"

  # Konkrete Track-basierte Empfehlungen

  # Konkrete Track-basierte Empfehlungen (nutzen echte Mess-Werte)
  bpm_advice = _bpm_advice(track_a.bpm, track_b.bpm)
  key_advice = _key_advice(track_a.camelotCode, track_b.camelotCode)
  energy_advice = _energy_advice(float(track_a.energy), float(track_b.energy))
  gain_advice = _gain_advice(
    getattr(track_a, "lufs", 0.0), getattr(track_b, "lufs", 0.0)
  )

  return DJRecommendation(
    genre_pair=genre_pair,
    genre_compatibility=round(compat, 2),
    mix_technique=mix_technique,
    eq_advice=eq_advice,
    transition_bars=transition_bars,
    outgoing_section=outgoing_section,
    incoming_section=incoming_section,
    structure_note=structure_note,
    risk_notes=risk_notes,
    rhythm_advice=rhythm_adv,
    bpm_advice=bpm_advice,
    key_advice=key_advice,
    energy_advice=energy_advice,
    gain_advice=gain_advice,
    adjusted_mix_out_a=adjusted_mix_out_a,
    adjusted_mix_in_b=adjusted_mix_in_b,
    overlap_seconds=round(overlap_seconds, 2),
  )


# === Paarspezifische Mix-Punkt-Berechnung ===

def _get_intro_end(track: Track) -> float:
  """
  Gibt die Zeit zurueck, wo das Intro von Track endet.

  Scannt sections nach zusammenhaengenden Intro-Sections am Track-Anfang.
  Fallback: track.mix_in_point (bereits gespeicherter Wert aus Analyse).

  Beispiel:
    sections: [intro(0-53s), intro(53-106s), drop(106-...)]
    -> gibt 106.0 zurueck (Ende aller Intro-Sections)
  """
  if not track.sections:
    return track.mix_in_point if track.mix_in_point >= 0 else 0.0

  last_intro_end = 0.0
  for section in track.sections:
    label = section.get("label", "main")
    if label == "intro":
      # Akkumuliere Ende des Intros (auch Multi-Section Intros)
      last_intro_end = section.get("end_time", section.get("start_time", 0.0))
    else:
      # AUDIT-FIX B7 (2026-07-24): IMMER beim ersten Non-Intro abbrechen.
      # Vorher lief der Scan weiter, wenn die erste Section kein Intro war —
      # eine "intro"-Section aus dem Tail-Analysefenster konnte intro_end
      # dann ans Track-ENDE ziehen und alle Mix-Punkte mitreissen.
      break

  if last_intro_end > 0.0:
    return last_intro_end

  # Kein Intro erkannt -> gespeicherter mix_in_point als Schaetzung
  return track.mix_in_point if track.mix_in_point >= 0 else 0.0


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
      # AUDIT-FIX B7 (2026-07-24): nur den zusammenhaengenden Intro-Block ab
      # Index 0 auswerten — Tail-Fenster-"intro"-Sections duerfen intro_end
      # nicht ans Track-Ende ziehen.
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
      # AUDIT-FIX N1 (2026-07-24): IMMER bei der ersten Non-Outro-Section
      # abbrechen. Vorher lief der Rueckwaerts-Scan weiter, wenn der Track
      # nicht auf "outro" endete — und fand das "outro", das die Fenster-
      # Analyse am Ende des HEAD-Fensters vergeben hatte. Folge: outro_start
      # in der Track-Mitte, Mix-Out bei ~34 % der Laenge (reproduziert fuer
      # jeden Track > Head-Fensterlaenge). Nur der zusammenhaengende Block
      # am Track-ENDE zaehlt.
      break

  return first_outro_start if found_outro else duration


def calculate_paired_mix_points(
  track_a: Track,
  track_b: Track,
) -> tuple[float, float]:
  """
  Berechnet aufeinander abgestimmte Mix-Out (Track A) und Mix-In (Track B).

  Problem mit per-Track-Berechnung: Mix-In wird ohne Kenntnis des Partner-Tracks
  berechnet. Bei Psytrance zB: Mix-In = immer 0.0, egal ob Intro 30s oder 300s.

  Diese Funktion loest das: Overlap = min(intro_dauer_B, outro_dauer_A).

  ACHTUNG (AUDIT-FIX N3, 2026-08-14): Dieser Overlap steuert nur die
  A-SEITE. Mix-In B ergibt sich ausschliesslich aus dem Intro-Guard
  (Invariante 5: nie im Intro mixen) — die fruehere Rechnung
  "Mix-In B = intro_end - overlap" landete per Definition im Intro und
  wurde vom Guard in 50 von 51 realen Paaren sofort wieder ueberschrieben.

  Beispiel Psytrance (phrase_unit=16, ~1.68 s/Bar):
    Track A: Duration 420s, Outro ab 367s -> Outro-Dauer = 53s
    Track B: Intro bis 106s
    Overlap (A-Seite) = min(106, 53) = 53s
    -> Mix-Out A = max(367, 420 - 53) = 367s (unveraendert)
    -> Mix-In B  = ceil(106) auf die naechste 16-Bar-Phrasengrenze

  Kurzes Intro (Track B Intro = 26s, Track A Outro = 53s):
    Overlap (A-Seite) = min(26, 53) = 26s
    -> Mix-Out A = max(367, 420 - 26) = 394s  (spaeter als Original!)
    -> Mix-In B  = ceil(26) auf die naechste Phrasengrenze

  Args:
    track_a: Ausgehender Track (dessen Mix-Out angepasst wird)
    track_b: Eingehender Track (dessen Mix-In angepasst wird)

  Returns:
    (adjusted_mix_out_a, adjusted_mix_in_b) in Sekunden
  """
  # AUDIT-FIX N4 (2026-07-24): Guard fuer fehlgeschlagene Analysen — bei
  # duration <= 0 kollabiert die Overlap-Rechnung (Mix-Out hinter Track-Ende,
  # unquantisierte Rohwerte). Dann lieber die Track-Werte unveraendert lassen.
  if track_a.duration <= 0 or track_b.duration <= 0:
    return (
      round(max(track_a.mix_out_point, 0.0), 2),
      round(max(track_b.mix_in_point, 0.0), 2),
    )

  profile_b = get_mix_profile(track_b.detected_genre or "Unknown")

  # --- Intro-Dauer von Track B ---
  intro_end_b = _get_intro_end(track_b)  # Sekunden (absoluter Zeitpunkt)

  # --- Outro-Dauer von Track A ---
  outro_start_a = track_a.mix_out_point
  if outro_start_a <= 0:
    outro_start_a = track_a.duration * 0.8  # Fallback: letzte 20%
  outro_duration_a = max(0.0, track_a.duration - outro_start_a)

  # --- Minimaler Overlap: genre-spezifisch nach Startwert des Transition-Bereichs ---
  bpm_b = track_b.bpm if track_b.bpm > 0 else DEFAULT_BPM
  seconds_per_bar_b = (60.0 / bpm_b) * METER
  min_overlap_bars = max(8, int(profile_b.transition_bars[0]))
  min_overlap = seconds_per_bar_b * min_overlap_bars

  # --- Target Overlap: das Minimum beider Seiten (nicht mehr als das Kuerzere) ---
  target_overlap = max(min_overlap, min(intro_end_b, outro_duration_a))
  # M3-Fix: harte Obergrenze — min_overlap darf bei kurzen Intros/Outros den
  # Overlap nicht ueber die halbe Laenge eines der beiden Tracks ziehen
  target_overlap = min(target_overlap, track_a.duration * 0.5, track_b.duration * 0.5)

  # --- Track A Mix-Out: target_overlap Sekunden vor Track-Ende ---
  # target_overlap steuert AUSSCHLIESSLICH die A-Seite (siehe N3 unten).
  adjusted_mix_out_a = track_a.duration - target_overlap
  # Aber nicht frueher als das urspruenglich berechnete Mix-Out
  # (wir verschieben nur nach hinten, nie nach vorne -- das waere schlechter)
  adjusted_mix_out_a = max(outro_start_a, adjusted_mix_out_a)

  # --- Track B Mix-In: Intro-Guard ist die Autoritaet ---
  # AUDIT-FIX N3 (2026-08-14): Vorher stand hier
  #   adjusted_mix_in_b = max(0.0, intro_end_b - target_overlap)
  # und direkt danach ein Guard, der jeden Wert unterhalb des Intro-Endes
  # wieder auf ceil(intro_end) hochzog. Da target_overlap immer > 0 ist, lag
  # der Startwert per Definition VOR dem Intro-Ende — der Guard feuerte in
  # 50 von 51 realen Paaren und ueberschrieb das Ergebnis vollstaendig.
  # target_overlap war fuer Track B also rechnerisch tot und suggerierte eine
  # Wirkung, die es nie hatte. Invariante 5 (Mix-In nie im Intro) verlangt
  # ohnehin genau das Guard-Ergebnis, deshalb wird es jetzt direkt berechnet.
  # Der 51. Fall (Track B ohne Intro-Sektion) lief in den Sonderfall unten:
  # _get_intro_end faellt dort auf track_b.mix_in_point zurueck, und
  # (mix_in_point - target_overlap) schob den Mix-In faktisch an den
  # Track-Anfang (gemessen 85.7 s -> 3.4 s, mitten in den ersten Drop).
  intro_end_sections_b = _get_intro_end_from_sections(track_b.sections or [])
  phrase_seconds_b = seconds_per_bar_b * profile_b.phrase_unit
  anchor_b = getattr(track_b, "phrase_anchor", getattr(track_b, "first_downbeat", 0.0)) or 0.0  # A1
  if intro_end_sections_b > 0:
    # ceil auf naechste Phrasengrenze nach Intro-Ende (downbeat-verankert).
    # Invariante 2: PHRASEN-Gitter (seconds_per_bar * phrase_unit), nicht ein
    # einzelner Bar — sonst weicht der Punkt bei Trance/Psytrance
    # (phrase_unit=16) bis zu 15 Bars von der Phrasengrenze ab (H2-Fix).
    adjusted_mix_in_b = quantize_to_grid(
      intro_end_sections_b, phrase_seconds_b, anchor_b, "ceil"
    )
  else:
    # Kein Intro erkannt: der per-Track berechnete Mix-In ist der beste
    # verfuegbare Schaetzwert und wird nicht nach vorn verschoben.
    adjusted_mix_in_b = max(0.0, track_b.mix_in_point)

  # --- Guard: Mix-Out A NIEMALS im Outro ---
  profile_a = get_mix_profile(track_a.detected_genre or "Unknown")
  outro_start_sections_a = _get_outro_start_from_sections(
    track_a.sections or [], track_a.duration
  )
  bpm_a = track_a.bpm if track_a.bpm > 0 else DEFAULT_BPM
  seconds_per_bar_a = (60.0 / bpm_a) * METER
  phrase_seconds_a = seconds_per_bar_a * profile_a.phrase_unit
  if adjusted_mix_out_a >= outro_start_sections_a:
    # floor auf Phrasengrenze VOR dem Outro (Invariante 1, downbeat-verankert)
    anchor_a = getattr(track_a, "phrase_anchor", getattr(track_a, "first_downbeat", 0.0)) or 0.0  # A1
    if phrase_seconds_a > 0:
      adjusted_mix_out_a = quantize_to_grid(
        outro_start_sections_a, phrase_seconds_a, anchor_a, "floor"
      )
      # floor kann exakt auf outro_start landen -> eine Phrase zurueck, damit
      # der Mix-Out garantiert VOR dem Outro liegt
      if adjusted_mix_out_a >= outro_start_sections_a:
        adjusted_mix_out_a -= phrase_seconds_a
    else:
      adjusted_mix_out_a = outro_start_sections_a - seconds_per_bar_a

  # Sicherheitscheck: Mix-Out vor Track-Ende
  adjusted_mix_out_a = min(adjusted_mix_out_a, track_a.duration - seconds_per_bar_a)
  # M2-Fix: Lower-Bound — Outro-Guard kann den Wert sonst negativ/nahe 0
  # druecken; negativer Wert wuerde den Sentinel-Check (>= 0.0) fehlleiten
  adjusted_mix_out_a = max(adjusted_mix_out_a, seconds_per_bar_a)

  # AUDIT-FIX B1 (2026-07-24): Die Endwerte werden IMMER aufs Phrasen-Gitter
  # quantisiert (downbeat-verankert). Vorher quantisierten nur die
  # Intro-/Outro-Guards — im Regelfall (Punkt ausserhalb Intro/Outro) gingen
  # ROHE Subtraktionswerte zurueck, und genau diese ueberschreiben in
  # playlist.compute_transition_recommendations die sauber quantisierten
  # Track-Werte. Der real gerenderte Uebergang startete damit off-grid.
  # Konvention: Mix-Out floor (nie NACH dem musikalischen Ereignis),
  # Mix-In ceil (nie davor). Quantisierte Werte nur uebernehmen, wenn sie
  # die Sicherheitsgrenzen nicht verletzen.
  anchor_a = getattr(track_a, "phrase_anchor", getattr(track_a, "first_downbeat", 0.0)) or 0.0  # A1
  # AUDIT-FIX N3b (2026-08-14): Epsilon gegen Float-Rauschen. Ein Wert, der
  # bereits exakt auf dem Gitter liegt, darf durch ceil/floor nicht eine
  # ganze Phrase weit springen (bei Psytrance ~27 s) — dieselbe Konvention
  # wie in align_ai_mix_points und calculate_genre_aware_mix_points.
  grid_epsilon = 1e-9
  if phrase_seconds_a > 0:
    q_out = quantize_to_grid(
      adjusted_mix_out_a + grid_epsilon, phrase_seconds_a, anchor_a, "floor"
    )
    if seconds_per_bar_a <= q_out <= track_a.duration - seconds_per_bar_a:
      adjusted_mix_out_a = q_out
  if phrase_seconds_b > 0:
    q_in = quantize_to_grid(
      adjusted_mix_in_b - grid_epsilon, phrase_seconds_b, anchor_b, "ceil"
    )
    if 0.0 <= q_in < track_b.duration:
      adjusted_mix_in_b = q_in
    elif q_in >= track_b.duration:
      # Bei sehr kurzen Tracks kann die naechste Phrase hinter dem Ende liegen.
      # Der rohe Wert darf dann nicht als ungueltiger Off-Track-Mixpunkt
      # zurueckbleiben. Fallback: letzter gueltiger Takt, mindestens nach dem
      # erkannten Intro, sofern das Zeitfenster dies noch erlaubt.
      last_bar = max(0.0, track_b.duration - seconds_per_bar_b)
      adjusted_mix_in_b = max(last_bar, min(intro_end_sections_b, track_b.duration))
      adjusted_mix_in_b = min(adjusted_mix_in_b, track_b.duration - 1e-6)

  # Keine Rundung innerhalb der Quantisierungskette (R9/N15).
  return adjusted_mix_out_a, adjusted_mix_in_b


def align_ai_mix_points(
  mix_in: float,
  mix_out: float,
  bpm: float,
  duration: float,
  phrase_unit: int = 8,
  anchor: float = 0.0,
) -> tuple[float, float]:
  """
  Quantisiert extern gelieferte Mix-Punkte (z.B. vom LLM) aufs Phrasen-Gitter.

  DJ-Konvention: Mix-In auf die naechste Phrasengrenze NACH dem Vorschlag
  (ceil, landet hinter dem Intro), Mix-Out auf die Grenze DAVOR (floor,
  bleibt vor dem Outro). Kollabiert das Fenster dadurch, wird auf das
  feinere Bar-Gitter ausgewichen; ist auch das ungueltig, bleiben die
  Originalwerte erhalten (LLM-Intent > kaputte Quantisierung).

  Returns:
    (aligned_mix_in, aligned_mix_out) in Sekunden
  """
  if bpm <= 0 or duration <= 0 or not (0 <= mix_in < mix_out <= duration):
    return mix_in, mix_out

  seconds_per_bar = (60.0 / bpm) * METER
  unit = phrase_unit if phrase_unit > 0 else 8

  # Epsilon gegen Float-Rauschen: 30.000001s darf nicht eine volle Phrase
  # nach hinten springen
  eps = 1e-6
  for grid in (seconds_per_bar * unit, seconds_per_bar):
    # Downbeat-verankertes Gitter (anchor=0.0 = bisheriges Verhalten)
    aligned_in = quantize_to_grid(mix_in - eps, grid, anchor, "ceil")
    aligned_out = quantize_to_grid(mix_out + eps, grid, anchor, "floor")
    if 0 <= aligned_in < aligned_out <= duration:
      return aligned_in, aligned_out

  return mix_in, mix_out


# === Hilfsfunktionen ===

def section_dict_at_time(track: Track, time_seconds: float) -> dict | None:
  """Die Sektion, die einen Zeitpunkt enthaelt — oder None.

  Einzige Quelle fuer "welche Sektion liegt bei t". Wer die Sektion an der
  Nahtstelle braucht, nimmt diese Funktion und raet nicht ueber Labels:
  gemessen an 200 Tracks liegt der Mix-Out im Median 76 s VOR dem Outro,
  und die letzte Main/Drop-Sektion ist nur in 12 % der Faelle die, in der
  der Mix-Out wirklich sitzt.
  """
  if not track.sections or time_seconds < 0:
    return None
  for index, section in enumerate(track.sections):
    if not isinstance(section, dict):
      continue
    start = section.get("start_time", 0.0)
    end = section.get("end_time", 0.0)
    is_last = index == len(track.sections) - 1
    if start <= time_seconds < end or (is_last and time_seconds == end):
      return section
  return None


def _get_section_at_time(track: Track, time_seconds: float, fallback_edge: str) -> str:
  """Label der Sektion an einem beliebigen Mix-Zeitpunkt."""
  if not track.sections or time_seconds < 0:
    return "unknown"

  treffer = section_dict_at_time(track, time_seconds)
  if treffer is not None:
    return treffer.get("label", "unknown")

  if fallback_edge == "in":
    return track.sections[0].get("label", "unknown")
  return track.sections[-1].get("label", "unknown")


def _effective_bpm_diff(bpm_a: float, bpm_b: float) -> tuple[float, str]:
  """Kleinste musikalische BPM-Differenz inkl. Half/Double-Time.

  Delegiert an die zentrale Definition in models — die fruehere lokale Kopie
  ignorierte das BPM_HALF_DOUBLE_ENABLED-Flag (Audit-Fix 2026-07-17).
  """
  return effective_bpm_diff(bpm_a, bpm_b)


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


def _bpm_advice(bpm_a: float, bpm_b: float) -> str:
  """
  Gibt eine konkrete BPM/Pitching-Empfehlung basierend auf der tatsaechlichen Differenz.

  Keine generischen Phrasen -- immer die echten Zahlen nennen.
  Wird als Prefix "BPM: ..." in die Transition-Notes injiziert.
  """
  if bpm_a <= 0 or bpm_b <= 0:
    return ""

  diff = bpm_b - bpm_a
  abs_diff, relation = _effective_bpm_diff(bpm_a, bpm_b)
  pct = abs(diff / bpm_a) * 100  # Pitch-Prozent-Aenderung

  # Audit-Fix 2026-07-21: Half/Double-Beziehung UNABHAENGIG von der 2.0-Grenze
  # behandeln. Vorher fiel z.B. 140->73 (double, eff. Diff ~3 BPM) in die
  # rohen Prozent-Zweige und meldete unsinnige "52% runter pitchen" — jetzt
  # wird die effektive Abweichung genannt und auf Phrasen-Alignment verwiesen.
  if relation in ("half", "double"):
    if abs_diff < 0.3:
      return (
        f"{bpm_a:.1f} → {bpm_b:.1f} — Half/Double-Time kompatibel, "
        f"Downbeat exakt auf Phrase setzen"
      )
    eff_pct = abs_diff / bpm_a * 100
    return (
      f"{bpm_a:.1f} → {bpm_b:.1f} — Half/Double-Time (eff. {abs_diff:.1f} BPM, "
      f"~{eff_pct:.1f}% Fein-Pitch), Downbeat auf Phrase setzen"
    )

  if abs_diff < 0.3:
    return f"{bpm_a:.1f} → {bpm_b:.1f} — Match, kein Pitching noetig"
  elif abs_diff <= 2.0:
    direction = "runter" if diff < 0 else "rauf"
    return f"{bpm_a:.1f} → {bpm_b:.1f} (Diff {diff:+.1f}) — Pitch-Fader {pct:.1f}% {direction}"
  elif abs_diff <= 5.0:
    direction = "runter" if diff < 0 else "rauf"
    return (
      f"{bpm_a:.1f} → {bpm_b:.1f} (Diff {diff:+.1f})"
      f" — {pct:.1f}% {direction} pitchen, frueh beginnen"
    )
  elif abs_diff <= 10.0:
    return f"{bpm_a:.1f} → {bpm_b:.1f} (Diff {diff:+.1f}) — Tempo im Intro angleichen"
  else:
    return f"{bpm_a:.1f} → {bpm_b:.1f} (Diff {diff:+.1f}) — Breakdown-Bridge oder Cold Cut"


def _key_advice(code_a: str, code_b: str) -> str:
  """
  Gibt eine Camelot-basierte Tonart-Empfehlung.

  Camelot Wheel: 1-12A/B (kreisfoermig), harmonisch = Distanz 1 gleicher Buchstabe.
  Wird als Prefix "Key: ..." in die Transition-Notes injiziert.
  """
  code_a = code_a or ""
  code_b = code_b or ""
  if not code_a or not code_b:
    return ""

  num_a = _extract_camelot_number(code_a)
  num_b = _extract_camelot_number(code_b)
  if num_a <= 0 or num_b <= 0:
    return ""

  # Gleiche Tonart = perfekt
  if code_a == code_b:
    return f"{code_a} → {code_b} — Gleiche Tonart, perfekt harmonisch"

  letter_a = code_a[-1].upper() if len(code_a) >= 2 else ""
  letter_b = code_b[-1].upper() if len(code_b) >= 2 else ""

  # Camelot-Distanz: Kreis 1-12, kuerzester Weg
  dist = min(abs(num_a - num_b), 12 - abs(num_a - num_b))

  # Richtung auf dem Rad (+ = im Uhrzeigersinn)
  direct = (num_b - num_a) % 12
  direction = "+" if direct <= 6 else "-"

  # Gleiche Nummer, A/B-Wechsel = Dur/Moll (Relative Major/Minor)
  if num_a == num_b:
    return f"{code_a} → {code_b} — Dur/Moll-Wechsel, smooth energy shift"

  if dist == 1 and letter_a == letter_b:
    return f"{code_a} → {code_b} — 1 Schritt ({direction}), harmonisch blendbar"
  elif dist == 1:
    return f"{code_a} → {code_b} — 1 Schritt ({direction}) + Modus-Wechsel, energy mix"
  elif dist == 2:
    return f"{code_a} → {code_b} — Distanz {dist}, Filter-Ride empfohlen"
  elif dist == 3:
    return f"{code_a} → {code_b} — Distanz {dist}, dezenter Clash — kein Melodie-Overlap"
  elif dist in (4, 5) and letter_a == letter_b:
    # Konsistenz mit calculate_compatibility: +4 (Energy Mix) und +7 (Mood
    # Shift, Distanz 5) sind dort bewusst erlaubte Techniken, kein Clash
    return f"{code_a} → {code_b} — Distanz {dist}, experimentelle Technik (+4/+7) — Energie-/Mood-Shift, kurz blenden"
  else:
    return f"{code_a} → {code_b} — Distanz {dist}, Key-Clash — nur Bass Swap"


def _gain_advice(lufs_a: float, lufs_b: float) -> str:
  """LUFS-basierte Gain-Angleichung zwischen zwei Tracks (2026-07-17).

  0.0 = LUFS unbekannt (Alt-Cache/Messung fehlgeschlagen) -> kein Advice.
  Anzeige ab GAIN_DIFF_SHOW_DB (1 dB = JND), Richtungsangabe fuer den
  Trim/Gain-Regler des eingehenden Decks.
  """
  if lufs_a >= 0.0 or lufs_b >= 0.0:
    return ""
  diff = lufs_a - lufs_b  # positiv = Track B ist leiser
  if abs(diff) < GAIN_DIFF_SHOW_DB:
    return f"{lufs_a:.1f} → {lufs_b:.1f} LUFS — Pegel passt, kein Gain noetig"
  direction = "rauf" if diff > 0 else "runter"
  hint = " (deutlich — vor dem Mix angleichen!)" if abs(diff) >= GAIN_DIFF_WARN_DB else ""
  return (
    f"{lufs_a:.1f} → {lufs_b:.1f} LUFS — Track B Gain {abs(diff):.1f} dB "
    f"{direction}{hint}"
  )


def _energy_advice(energy_a: float, energy_b: float) -> str:
  """
  Gibt eine Energie-Empfehlung basierend auf den tatsaechlichen Track-Werten.

  Zeigt immer die echten Zahlen statt generischer Labels.
  Wird als Prefix "Energy: ..." in die Transition-Notes injiziert.
  """
  if energy_a <= 0 and energy_b <= 0:
    return ""

  diff = energy_b - energy_a
  abs_diff = abs(diff)

  if abs_diff <= 5:
    return (
      f"{energy_a:.0f} → {energy_b:.0f} (Diff {diff:+.0f})"
      f" — stabil, normaler Crossfade"
    )
  elif diff > 25:
    return (
      f"{energy_a:.0f} → {energy_b:.0f} (Diff {diff:+.0f})"
      f" — Push, Drop-Cut oder Build-Einstieg"
    )
  elif diff > 10:
    return (
      f"{energy_a:.0f} → {energy_b:.0f} (Diff {diff:+.0f})"
      f" — Aufbau, im Build einmixen"
    )
  elif diff < -25:
    return (
      f"{energy_a:.0f} → {energy_b:.0f} (Diff {diff:+.0f})"
      f" — Drop, Breakdown-Uebergang planen"
    )
  elif diff < -10:
    return (
      f"{energy_a:.0f} → {energy_b:.0f} (Diff {diff:+.0f})"
      f" — Abfall, im Outro ueberblenden"
    )
  else:
    return (
      f"{energy_a:.0f} → {energy_b:.0f} (Diff {diff:+.0f})"
      f" — leichter Shift, smooth moeglich"
    )


def _dynamic_transition_bars(ctx: TransitionContext) -> int:
  """
  Berechnet die optimale Transition-Laenge in Bars.

  Basiert auf dem Durchschnitt der Genre-Profile, passt sich aber
  an die tatsaechlichen BPM- und Energie-Differenzen an.
  Groessere Unterschiede = mehr Zeit zum Angleichen.
  """
  # Basis: Durchschnitt aus beiden Genre-Profilen
  base = int(
    (ctx.profile_a.transition_bars[0] + ctx.profile_a.transition_bars[1] +
     ctx.profile_b.transition_bars[0] + ctx.profile_b.transition_bars[1]) / 4.0
  )

  bpm_diff, bpm_relation = _effective_bpm_diff(ctx.bpm_a, ctx.bpm_b)
  energy_diff = abs(ctx.energy_a - ctx.energy_b)

  # Mehr Zeit fuer grosse Abweichungen
  if bpm_diff > 8:
    base += 8   # Viel Zeit zum Tempo-Angleichen
  elif bpm_diff > 4:
    base += 4

  if energy_diff > 25:
    base += 4   # Mehr Zeit fuer grossen Energie-Shift

  if bpm_relation in ("half", "double"):
    # Audit-Fix 2026-07-17: Half/Double-Uebergaenge werden als KURZER Cut auf
    # den Downbeat gefahren, nicht als langer Blend — langer Overlap legt
    # Kick auf Doppel-Kick. Vorher wurde hier faelschlich +4 addiert.
    base = min(base, 16)

  # Kuerzer wenn beides gut passt
  if bpm_diff < 1.0 and energy_diff < 10:
    base -= 4

  # Auf naechste 4-Bar-Grenze runden, Minimum 8 Bars
  base = max(8, round(base / 4) * 4)
  return base


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

  # Audit-Fix 2026-07-17: Fallback nutzt die Kompatibilitaets-Matrix statt
  # eines generischen Texts — schwer kompatible Paare (z.B. Psytrance/Deep
  # House 0.15) verdienen eine explizite Bridge-Warnung
  compat = get_genre_compatibility(genre_a, genre_b)
  if compat < 0.3:
    return "Schwierige Kombination -- Breakdown-Bridge oder Cold Cut, kein langer Blend"
  if compat < 0.6:
    return "Vorsichtiger Uebergang -- kurzer Blend am Phrasen-Ende, Energie angleichen"
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

  compat = get_genre_compatibility(genre_a, genre_b)
  if compat < 0.3:
    return "Bass von Track A komplett cutten BEVOR Track B einsetzt -- keine Ueberlappung"
  return "Standard bass swap at phrase boundary"


def _assess_transition_risks(
  track_a: Track,
  track_b: Track,
  genre_compat: float,
  mix_out_a: float | None = None,
  mix_in_b: float | None = None,
) -> list[str]:
  """Bewertet Risiken einer Transition.

  AUDIT-FIX N2 (2026-08-14): mix_out_a/mix_in_b sind die PAARSPEZIFISCHEN
  Mix-Punkte (adjusted_mix_out_a/adjusted_mix_in_b). Ohne sie bewertete der
  Bass-Kollisions-Check die gespeicherten Track-Punkte — also eine Stelle,
  die in diesem Uebergang gar nicht gemixt wird. Auf 51 realen Paaren kippte
  dadurch das Kollisions-Urteil in 2 Faellen und die Dominanz-Warnung in 9.
  None = Fallback auf die Track-Punkte (Alt-Aufrufer/Tests).
  """
  risks = []

  # BPM-Check mit Half/Double-Time-Erkennung
  # Audit-Fix 2026-07-21: Half/Double UNABHAENGIG von der 2.0-Grenze melden —
  # sonst blieb ein Half/Double-Uebergang mit eff. Diff 2-4 BPM voellig ohne Hinweis.
  bpm_diff, bpm_relation = _effective_bpm_diff(track_a.bpm, track_b.bpm)
  if bpm_relation in ("half", "double"):
    suffix = "" if bpm_diff <= 2.0 else f", eff. {bpm_diff:.1f} BPM angleichen"
    risks.append(
      f"Half/Double-Time ({track_a.bpm:.1f}↔{track_b.bpm:.1f}) -- exakt auf Phrase/Downbeat cutten{suffix}"
    )
  elif bpm_diff > 8:
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

  # Bass-Kollisions-Check (Phase 3)
  # Wir schauen uns die Bass-Energie der beteiligten Sektionen an
  # Section-Dicts koennen unvollstaendig sein -- fehlende Zeiten nie vergleichen
  def _section_covers(s: dict, t: float) -> bool:
    start, end = s.get('start_time'), s.get('end_time')
    return start is not None and end is not None and start <= t <= end

  # Sentinel-Regel (config.MIX_POINT_UNSET = -1.0): 0.0 ist ein gueltiger
  # Mix-Punkt, deshalb >= 0.0 und nicht > 0 pruefen.
  point_a = mix_out_a if mix_out_a is not None and mix_out_a >= 0.0 else track_a.mix_out_point
  point_b = mix_in_b if mix_in_b is not None and mix_in_b >= 0.0 else track_b.mix_in_point

  out_sec_data = next((s for s in track_a.sections if _section_covers(s, point_a)), {})
  in_sec_data = next((s for s in track_b.sections if _section_covers(s, point_b)), {})
  
  bass_a = out_sec_data.get('avg_bass', track_a.avg_bass)
  bass_b = in_sec_data.get('avg_bass', track_b.avg_bass)
  
  # Audit-Fix 2026-07-17: unabhaengige Checks — der alte elif-Zweig war bei
  # bass_a > 60 unerreichbar (bass_b > 80 impliziert bass_b > 60)
  if bass_a > 60 and bass_b > 60:
      risks.append(f"Bass-Kollision droht! (A:{bass_a:.0f}%, B:{bass_b:.0f}%) -- Bass von Track A hart cutten")
  if bass_b > 80:
      risks.append("Incoming Track hat sehr dominanten Bass -- Bass-Swap am Phrasen-Ende empfohlen")

  # Key-Confidence (2026-07-17): unsichere Tonart = Harmonik-Empfehlung
  # mit Vorsicht geniessen (0.0 = unbekannt/Alt-Cache -> keine Warnung)
  for label, tr in (("A", track_a), ("B", track_b)):
      kc = getattr(tr, "key_confidence", 0.0)
      if 0.0 < kc < KEY_CONFIDENCE_UNCERTAIN:
          risks.append(
              f"Key von Track {label} unsicher erkannt ({kc:.0%}) -- "
              f"Harmonik-Empfehlung pruefen, im Zweifel Bass Swap"
          )

  # Loudness (2026-07-17): grosser LUFS-Unterschied ohne Gain-Angleichung
  # zerstoert den Uebergang hoerbar
  lufs_a = getattr(track_a, "lufs", 0.0)
  lufs_b = getattr(track_b, "lufs", 0.0)
  if lufs_a < 0.0 and lufs_b < 0.0 and abs(lufs_a - lufs_b) >= GAIN_DIFF_WARN_DB:
      risks.append(
          f"Lautheits-Sprung {abs(lufs_a - lufs_b):.1f} dB "
          f"({lufs_a:.1f} vs {lufs_b:.1f} LUFS) -- Gain vor dem Mix angleichen"
      )

  # AUDIT-FIX D2-light (2026-07-26): Vocal-Clash — zwei Lead-Vocals
  # uebereinander sind einer der haeufigsten Mixfehler
  if (
      getattr(track_a, "vocal_instrumental", "unknown") == "vocal"
      and getattr(track_b, "vocal_instrumental", "unknown") == "vocal"
  ):
      risks.append(
          "Beide Tracks vocal-lastig -- Vocal-Ueberlappung vermeiden "
          "(Uebergang ueber instrumentale Passagen legen)"
      )

  return risks



def _calculate_texture_similarity(fp_a: list, fp_b: list) -> float:
    """Calculates cosine similarity between two MFCC fingerprints.

    Audit-Fix 2026-07-17: MFCC-0 (Gesamtlautheit) wird verworfen — er
    dominierte die Cosine-Similarity, sodass "Textur" faktisch Lautheit mass.
    """
    if not fp_a or not fp_b or len(fp_a) != len(fp_b):
        return 0.0

    a = np.array(fp_a)
    b = np.array(fp_b)
    if len(a) > 2:
        a = a[1:]
        b = b[1:]

    # Cosine Similarity
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    sim = dot / (norm_a * norm_b)
    return float(sim)


def _extract_camelot_number(code: str) -> int:
  """Extrahiert die Nummer aus einem Camelot-Code (z.B. '8A' -> 8).

  Delegiert an die zentrale Parsing-Definition in models (Audit 2026-07-17).
  """
  return get_camelot_components(code)[0]
