"""Zeitplanung aus den unveränderten aktiven Übergangsplänen."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional
from .models import Track
from .playlist_results import TransitionPlan

@dataclass
class SetTimeline:
    """Zeitplanung fuer ein DJ-Set."""

    total_duration_minutes: float  # Gesamtlaenge in Minuten
    target_duration_minutes: float  # Gewuenschte Laenge
    peak_position_minutes: float  # Peak-Zeitpunkt
    entries: list  # Liste von SetTimelineEntry dicts
    overflow_minutes: float  # Ueberschuss/Defizit in Minuten


@dataclass
class SetTimelineEntry:
    """Ein Track-Eintrag in der Set-Timeline."""

    track: Track
    start_time: float  # Start in Sekunden
    end_time: float  # Ende der hoerbaren Trackstrecke in Set-Sekunden
    playing_duration: float  # Effektive Spieldauer in Sekunden
    overlap_with_next: float  # Overlap in Sekunden zum naechsten Track
    is_peak: bool  # Ist dieser Track am Peak-Punkt?
    energy_phase: str  # "intro", "warmup", "build", "peak", "sustain", "cooldown"
    transition_planned: Optional[bool] = None  # True/False; letzter Track None


def _timeline_track_duration(track: Track, index: int) -> float:
    """Liefert eine echte, positive Trackdauer oder bricht sichtbar ab."""
    try:
        duration = float(track.duration)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Track {index + 1}: ungueltige Dauer") from exc
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError(f"Track {index + 1}: Dauer muss endlich und positiv sein")
    return duration


def _validated_timeline_plan(
    plan: TransitionPlan,
    edge_index: int,
    duration_a: float,
    duration_b: float,
) -> tuple[float, float, float]:
    """Validiert den unveraendert zu uebernehmenden Plan einer Kante."""
    edge = f"Kante {edge_index + 1}->{edge_index + 2}"
    try:
        mix_out = float(plan.mix_out_a)
        mix_in = float(plan.mix_in_b)
        overlap = float(plan.overlap)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{edge}: unvollstaendiger TransitionPlan") from exc

    if not all(math.isfinite(value) for value in (mix_out, mix_in, overlap)):
        raise ValueError(f"{edge}: TransitionPlan enthaelt nicht-endliche Werte")
    if overlap <= 0.0:
        raise ValueError(f"{edge}: Overlap muss positiv sein")
    if not (0.0 <= mix_out and mix_out + overlap <= duration_a):
        raise ValueError(f"{edge}: Mix-Out oder Overlap liegt ausserhalb von Track A")
    if not (0.0 <= mix_in and mix_in + overlap <= duration_b):
        raise ValueError(f"{edge}: Mix-In oder Overlap liegt ausserhalb von Track B")
    return mix_out, mix_in, overlap


def _calculate_timeline_entries(
    tracks: list[Track], default_overlap: float,
    transition_plans: Optional[list[TransitionPlan]] = None,
) -> tuple[list[SetTimelineEntry], float]:
    """Berechnet die Timeline ausschliesslich aus gueltigen Plaenen.

    Eine planlose Kante spielt den aktuellen Track bis zum echten Ende und
    hat keinen erfundenen Overlap. Planwerte bleiben exakt; ungueltige Plaene
    werden nicht geklemmt oder durch Analysewerte ersetzt.
    """
    del default_overlap  # Oeffentlicher Legacy-Parameter; kein Timing-Fallback.
    entries: list[SetTimelineEntry] = []
    current_time = 0.0
    n = len(tracks)
    durations = [
        _timeline_track_duration(track, i) for i, track in enumerate(tracks)
    ]
    plans: list[Optional[tuple[float, float, float]]] = [None] * max(0, n - 1)

    for edge_index in range(n - 1):
        plan = (
            transition_plans[edge_index]
            if transition_plans is not None and edge_index < len(transition_plans)
            else None
        )
        if plan is not None:
            plans[edge_index] = _validated_timeline_plan(
                plan, edge_index, durations[edge_index], durations[edge_index + 1]
            )

    for index in range(1, n - 1):
        incoming = plans[index - 1]
        outgoing = plans[index]
        if incoming is not None and outgoing is not None:
            incoming_mix_in = incoming[1]
            outgoing_mix_out = outgoing[0]
            if not incoming_mix_in < outgoing_mix_out:
                raise ValueError(
                    f"Track {index + 1}: eingehender Mix-In muss vor "
                    "ausgehendem Mix-Out liegen"
                )

    for i, track in enumerate(tracks):
        track_dur = durations[i]
        plan_in = plans[i - 1] if i > 0 else None
        plan_out = plans[i] if i < n - 1 else None
        mix_in = plan_in[1] if plan_in is not None else 0.0
        mix_out = plan_out[0] if plan_out is not None else track_dur

        if plan_out is not None:
            overlap = plan_out[2]
            playing_duration = mix_out - mix_in + overlap
            transition_planned: Optional[bool] = True
        else:
            overlap = 0.0
            playing_duration = track_dur - mix_in
            transition_planned = False if i < n - 1 else None

        end_time = current_time + playing_duration
        next_start = current_time + mix_out - mix_in

        entries.append(
            SetTimelineEntry(
                track=track,
                start_time=current_time,
                end_time=end_time,
                playing_duration=playing_duration,
                overlap_with_next=overlap,
                is_peak=False,  # Wird spaeter gesetzt
                energy_phase="build",  # Wird spaeter gesetzt
                transition_planned=transition_planned,
            )
        )

        current_time = next_start

    total = entries[-1].end_time if entries else 0.0
    return entries, total


def _identify_peak_track(
    entries: list[SetTimelineEntry], total_seconds: float, peak_position_pct: float
) -> int:
    """Findet den Index des Peak-Tracks."""
    if not entries:
        return 0

    peak_time = total_seconds * peak_position_pct
    best_peak_idx = 0
    best_peak_score = -1.0

    for i, entry in enumerate(entries):
        mid = (entry.start_time + entry.end_time) / 2.0
        # Score: Energie * (1 - Abstand zum Peak-Zeitpunkt)
        time_factor = 1.0 - min(abs(mid - peak_time) / max(total_seconds, 1.0), 1.0)
        energy_factor = entry.track.energy / 100.0
        score = energy_factor * 0.6 + time_factor * 0.4
        if score > best_peak_score:
            best_peak_score = score
            best_peak_idx = i

    entries[best_peak_idx].is_peak = True
    return best_peak_idx


def _assign_energy_phases(entries: list[SetTimelineEntry], best_peak_idx: int) -> None:
    """Weist jedem Track eine Energy-Phase zu."""
    n = len(entries)
    if n == 0:
        return

    peak_pos = best_peak_idx / max(n - 1, 1)
    for i, entry in enumerate(entries):
        relative_pos = i / max(n - 1, 1)
        if entry.is_peak:
            entry.energy_phase = "peak"
        elif i == 0:
            entry.energy_phase = "intro"
        elif i == n - 1:
            entry.energy_phase = "cooldown"
        elif relative_pos < peak_pos * 0.5:
            # L3-Fix: echte Warm-up-Phase — vorher lieferten beide Branches
            # "build" und der finale else-Zweig war unerreichbar
            entry.energy_phase = "warmup"
        elif relative_pos <= peak_pos:
            entry.energy_phase = "build"
        elif relative_pos <= peak_pos + 0.15:
            entry.energy_phase = "sustain"
        else:
            entry.energy_phase = "cooldown"


def compute_set_timeline(
    tracks: list[Track],
    target_minutes: float = 60.0,
    peak_position_pct: float = 0.65,
    default_overlap: float = 16.0,
    transition_plans: Optional[list[TransitionPlan]] = None,
) -> SetTimeline:
    """
    Berechnet eine zeitbasierte Timeline fuer ein DJ-Set.

    Jeder Track bekommt einen Start/Ende-Zeitpunkt. Gesamtlaenge = Summe
    der Stuecke Mix-In..Mix-Out (erster Track ab 0, letzter bis zum Ende),
    Geplante Eintraege ueberlappen um den Plan-Overlap; ungeplante Kanten
    spielen ohne erfundene Blende bis zum Trackende.
    Der Peak-Track wird identifiziert.

    Args:
      tracks: Sortierte Playlist
      target_minutes: Gewuenschte Set-Laenge in Minuten
      peak_position_pct: Peak-Position als Anteil (0.0-1.0, default 0.65)
      default_overlap: Oeffentlicher Legacy-Parameter; ohne Plan keine Blende

    Returns:
      SetTimeline mit allen Eintraegen
    """
    if not tracks:
        return SetTimeline(
            total_duration_minutes=0.0,
            target_duration_minutes=target_minutes,
            peak_position_minutes=0.0,
            entries=[],
            overflow_minutes=0.0,
        )

    peak_position_pct = max(0.1, min(0.9, peak_position_pct))

    entries, total_seconds = _calculate_timeline_entries(
        tracks, default_overlap, transition_plans
    )
    best_peak_idx = _identify_peak_track(entries, total_seconds, peak_position_pct)
    _assign_energy_phases(entries, best_peak_idx)

    total_minutes = total_seconds / 60.0
    peak_minutes = entries[best_peak_idx].start_time / 60.0 if entries else 0.0

    return SetTimeline(
        total_duration_minutes=total_minutes,
        target_duration_minutes=target_minutes,
        peak_position_minutes=peak_minutes,
        entries=entries,
        overflow_minutes=total_minutes - target_minutes,
    )


def get_set_timing_summary(timeline: SetTimeline) -> dict:
    """
    Erstellt eine menschenlesbare Zusammenfassung der Set-Timeline.

    Returns:
      Dict mit: total_time, target_time, overflow, peak_track, peak_time,
      phase_breakdown, track_count, avg_track_duration
    """
    if not timeline.entries:
        return {
            "total_time": "0:00",
            "target_time": f"{timeline.target_duration_minutes:.0f}:00",
            "overflow": "0:00",
            "overflow_seconds": 0.0,
            "peak_track": None,
            "peak_time": "0:00",
            "phase_breakdown": {},
            "track_count": 0,
            "avg_track_duration": 0.0,
        }

    total_sec = timeline.total_duration_minutes * 60
    target_sec = timeline.target_duration_minutes * 60
    overflow_sec = timeline.overflow_minutes * 60

    # Formatiere Zeiten
    def _fmt(seconds: float) -> str:
        sign = "-" if seconds < 0 else ""
        s = abs(seconds)
        m = int(s // 60)
        sec = int(s % 60)
        return f"{sign}{m}:{sec:02d}"

    # Peak-Track finden
    peak_entry = next((e for e in timeline.entries if e.is_peak), None)
    peak_track_name = peak_entry.track.title if peak_entry else "?"
    peak_time = _fmt(peak_entry.start_time) if peak_entry else "0:00"

    # Phasen-Breakdown
    phases: dict[str, int] = {}
    for entry in timeline.entries:
        phases[entry.energy_phase] = phases.get(entry.energy_phase, 0) + 1

    # Durchschnittliche Track-Dauer
    durations = [e.playing_duration for e in timeline.entries]
    avg_dur = sum(durations) / len(durations) if durations else 0

    return {
        "total_time": _fmt(total_sec),
        "target_time": _fmt(target_sec),
        "overflow": _fmt(overflow_sec),
        "overflow_seconds": overflow_sec,
        "peak_track": peak_track_name,
        "peak_time": peak_time,
        "phase_breakdown": phases,
        "track_count": len(timeline.entries),
        "avg_track_duration": avg_dur,
    }
