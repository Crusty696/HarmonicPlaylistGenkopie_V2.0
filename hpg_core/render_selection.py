"""Begrenzte Renderreserve mit gemeinsamem Playlist-Plan und RAM-Ergebnis.

Ein Erfolg liefert den gesamten neu aufgebauten Playlistzustand. Aufrufer
duerfen nicht nur das Audio uebernehmen und alte Mixpunkte anzeigen.
"""
from dataclasses import asdict, dataclass
from collections.abc import Mapping
import json

from .playlist import (PlaylistGenerationResult, rebuild_result_for_order,
                       _resolve_track_genre, _normalize_energy_direction)
from .pair_candidates import rank_pair_candidates, MAX_RESERVE_COMBINATIONS
from .candidate_choices import schluessel
from .transition_renderer import TransitionClipSpec, BeatSyncError
from .hearing_playback import render_wav_bytes, MAX_PLAYBACK_BYTES


@dataclass(frozen=True)
class RenderSelection:
    playlist: PlaylistGenerationResult
    boundary_index: int
    spec: TransitionClipSpec
    audio: bytes
    rejected: tuple[tuple[str, str], ...]


def render_with_reserve(result, index, sources, checkpoint, *, render=render_wav_bytes):
    """Nur BeatSyncError erlaubt eine Alternative; IO/Abbruch bleiben Fehler.

    Standardplan zuerst, danach maximal 30 qualifizierte Kombinationen.
    Kein Persistieren von Kandidatenwahlen, kein Audio auf Datentraeger.
    Der Aufrufer muss seinen Worker gegen veraenderte GUI-Zustaende binden.
    """
    if (not isinstance(result, PlaylistGenerationResult) or type(index) is not int
            or not 0 <= index < len(result.recommendations)
            or not callable(checkpoint) or not callable(render)):
        raise ValueError('Ungueltiger Renderreserve-Auftrag')
    sources = tuple(dict(source) for source in sources)
    checkpoint()
    a, b = result.tracks[index:index+2]
    context = result.scoring_context_dict()
    genre = _resolve_track_genre(a)
    def profile(name):
        values = context.get(name, {})
        return values.get(genre, values.get('Unknown', {})) if isinstance(values, Mapping) else None
    choices = result.candidate_choice_snapshot_dict()
    pair_key = schluessel(a.filePath, b.filePath)
    order = [item.occurrence_id for item in result.occurrences]
    tried, rejected = set(), []

    def attempt(candidate_result):
        checkpoint()
        plan = candidate_result.recommendations[index].plan
        if plan is None:
            return None
        spec = TransitionClipSpec.from_plan(plan, a, b)
        identity = json.dumps(asdict(spec), sort_keys=True, allow_nan=False)
        if identity in tried:
            return None
        tried.add(identity)
        try:
            audio = render(asdict(spec), sources)
        except BeatSyncError as error:
            rejected.append((identity, str(error)))
            checkpoint()
            return None
        checkpoint()
        if not isinstance(audio, bytes) or not 0 < len(audio) <= MAX_PLAYBACK_BYTES:
            raise ValueError('Ungueltige RAM-Ausgabe der Renderreserve')
        return RenderSelection(candidate_result, index, spec, audio, tuple(rejected))

    selected = attempt(result)
    if selected is not None:
        return selected
    candidates = rank_pair_candidates(a, b, bpm_tolerance=result.bpm_tolerance,
        energy_direction=_normalize_energy_direction(context.get('energy_direction')),
        harmonic_strictness=context.get('harmonic_strictness', 7),
        allow_experimental=context.get('allow_experimental', True),
        tolerances=profile('candidate_tolerances_by_genre'),
        schema_rang=profile('candidate_schema_ranks_by_genre'),
        wahl=choices.get(pair_key, {}), max_combinations=MAX_RESERVE_COMBINATIONS)
    for candidate in candidates:
        checkpoint()
        updated_choices = dict(choices)
        updated_choices[pair_key] = dict(t_out=candidate.t_out, t_in=candidate.t_in,
                                         blend_bars=candidate.blend_bars)
        updated = rebuild_result_for_order(result, order, updated_choices,
                                            cancel_check=checkpoint)
        plan = updated.recommendations[index].plan
        if (plan is None or abs(plan.mix_out_a-candidate.t_out) > 1e-9
                or abs(plan.mix_in_b-candidate.t_in) > 1e-9
                or abs(plan.overlap-candidate.overlap_sec) > 1e-9):
            continue  # Die spielbare Playlistkette hat Vorrang vor Einzelwahl.
        selected = attempt(updated)
        if selected is not None:
            return selected
    raise BeatSyncError(f'Kein synchron renderbarer Kandidat in der begrenzten Reserve ({len(tried)} Specs)')
