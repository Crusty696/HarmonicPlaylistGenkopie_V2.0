"""Konsistente Kandidatenkette ohne Abhängigkeit von GUI oder Strategien."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .models import Track, seconds_per_bar, QUANTIZE_TOLERANCE_SEC
from .dj_brain import effective_track_phrase_unit
from .playlist_results import TrackOccurrence



def _check_cancel(cancel_check) -> None:
    """Bricht kooperativ ab; Aufrufer publizieren dadurch kein Teilergebnis."""
    if cancel_check is not None and cancel_check():
        raise InterruptedError("Playlist-Generierung abgebrochen")


@dataclass(frozen=True, slots=True)
class _PathState:
    selections: tuple[Optional["CandidateSnapshot"], ...]
    consistencies: tuple[bool, ...]
    planned: int
    saved_honored: int
    score: float
    path_consistent_links: int
    state_key_sequence: tuple


def _path_order(state: _PathState) -> tuple:
    return (
        -state.planned,
        -state.saved_honored,
        -state.score,
        -state.path_consistent_links,
        state.state_key_sequence,
    )


def _snapshot_flag(snapshot: "CandidateSnapshot", name: str, default=False):
    return dict(snapshot.flags).get(name, default)


def _candidate_link_consistent(
    previous: "CandidateSnapshot", current: "CandidateSnapshot", middle: Track
) -> bool:
    grid = seconds_per_bar(middle.bpm) * effective_track_phrase_unit(middle)
    return (
        current.t_out
        >= previous.t_in + 2.0 * grid - QUANTIZE_TOLERANCE_SEC
    )


def _select_snapshot_path(
    candidates_by_boundary: tuple[tuple["CandidateSnapshot", ...], ...],
    occurrences: tuple[TrackOccurrence, ...],
    cancel_check=None,
) -> tuple[tuple[Optional["CandidateSnapshot"], ...], tuple[bool, ...], int, int, int]:
    """Begrenzter DP: hoechstens 12 Kandidaten plus UNGEPLANT je Kante."""
    if not candidates_by_boundary:
        return (), (), 0, 0, 0
    previous_states: dict[Optional[tuple], _PathState] = {}
    states_retained = 0
    link_checks = 0

    for index, snapshots in enumerate(candidates_by_boundary):
        _check_cancel(cancel_check)
        options: tuple[Optional["CandidateSnapshot"], ...] = (*snapshots[:12], None)
        current_states: dict[Optional[tuple], _PathState] = {}
        predecessors = tuple(previous_states.values()) or (
            _PathState((), (), 0, 0, 0.0, 0, ()),
        )
        for option in options:
            _check_cancel(cancel_check)
            best: Optional[_PathState] = None
            for predecessor in predecessors:
                _check_cancel(cancel_check)
                previous = predecessor.selections[-1] if predecessor.selections else None
                if option is None:
                    consistent = False
                    link_ok = False
                elif previous is None:
                    consistent = True
                    link_ok = False
                else:
                    link_checks += 1
                    link_ok = _candidate_link_consistent(
                        previous, option, occurrences[index].track
                    )
                    # Physisch unspielbare Kombinationen erzeugen keinen Zustand.
                    if not link_ok:
                        continue
                    consistent = link_ok
                planned = predecessor.planned + (option is not None)
                honored = predecessor.saved_honored + int(
                    option is not None
                    and bool(_snapshot_flag(option, "gespeicherte_wahl"))
                )
                score = predecessor.score + (option.score if option is not None else 0.0)
                path_links = predecessor.path_consistent_links + int(link_ok)
                state_key = (0, option.key) if option is not None else (1, ())
                candidate = _PathState(
                    selections=(*predecessor.selections, option),
                    consistencies=(*predecessor.consistencies, consistent),
                    planned=planned,
                    saved_honored=honored,
                    score=score,
                    path_consistent_links=path_links,
                    state_key_sequence=(*predecessor.state_key_sequence, state_key),
                )
                if best is None or _path_order(candidate) < _path_order(best):
                    best = candidate
            assert best is not None
            current_states[option.key if option is not None else None] = best
        states_retained += len(current_states)
        previous_states = current_states

    winner = min(previous_states.values(), key=_path_order)
    return (
        winner.selections,
        winner.consistencies,
        link_checks,
        winner.path_consistent_links,
        states_retained,
    )
