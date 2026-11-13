"""Build a fixed-length Harmonic Flow set using rendered, cue-consistent edges."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np
import soundfile as sf

from .candidate_path import _candidate_link_consistent, _check_cancel
from .playlist import _build_generation_result, _rank_fixed_boundaries, calculate_compatibility
from .playlist_results import TrackOccurrence
from .playlist_selection import _eligible_unique
from .transition_renderer import BeatSyncError, TransitionClipSpec, render_transition_clip


def generate_verified_set(tracks, length, tolerance, context, choices, cancel_check, history=None):
    pool = _eligible_unique(tracks)
    if len(pool) < length:
        raise ValueError(f"{len(pool)} analysierte Titel für {length} Plätze verfügbar.")
    run_id = uuid4().hex
    items = [TrackOccurrence(run_id=run_id, ordinal=i, track=t) for i, t in enumerate(pool)]
    ranked = {}
    verified = {}
    neighbours = {}
    rotation = (history or {}).get("last_exported", {})
    best = 0

    def result(path, edges):
        sequence = tuple(TrackOccurrence(run_id=run_id, ordinal=i, track=pool[k]) for i, k in enumerate(path))
        return _build_generation_result(
            run_id=run_id, mode="Harmonic Flow", occurrences=sequence,
            input_tracks=len(sequence), invalid_bpm_excluded=0, bpm_tolerance=tolerance,
            context=context, choice_snapshot=choices, cancel_check=cancel_check,
            ranked_boundaries=(tuple((c,) for c in edges),
                               tuple(ranked[a,b][1][0] for a,b in zip(path,path[1:])),
                               sum(ranked[a,b][2] for a,b in zip(path,path[1:]))),
        )

    def options(a, previous, visited):
        if a not in neighbours:
            neighbours[a] = sorted((i for i in range(len(pool)) if i != a),
                key=lambda i: (-calculate_compatibility(pool[a],pool[i],tolerance,**context),
                               rotation.get(pool[i].track_id,0),pool[i].track_id))
        for b in neighbours[a]:
            _check_cancel(cancel_check)
            if b in visited:
                continue
            if (a,b) not in ranked:
                ranked[a,b] = _rank_fixed_boundaries((items[a],items[b]),tolerance,context,choices,cancel_check)
            for c in ranked[a,b][0][0]:
                if previous and not _candidate_link_consistent(previous,c,pool[a]):
                    continue
                key = a,b,c.key
                if key not in verified:
                    plan = result([a,b],[c]).recommendations[0].plan
                    ok = False
                    if plan is not None:
                        try:
                            render_transition_clip(TransitionClipSpec.from_plan(plan,pool[a],pool[b]),str(clip))
                            audio,_ = sf.read(clip,dtype="float32",always_2d=True)
                            ok = bool(audio.size and np.isfinite(audio).all() and .01 < np.max(np.abs(audio)) <= 1.0001)
                        except BeatSyncError:
                            pass
                    verified[key] = ok
                if verified[key]:
                    yield b,c

    with TemporaryDirectory(prefix="hpg-verified-") as directory:
        clip = Path(directory)/"transition.wav"
        for seed in sorted(range(len(pool)),key=lambda i: (rotation.get(pool[i].track_id,0),abs(pool[i].bpm-126))):
            path,edges,visited = [seed],[],{seed}
            stack=[options(seed,None,visited)]
            while stack:
                _check_cancel(cancel_check)
                if len(path)==length:
                    final=result(path,edges)
                    if final.path_stats.planned != length-1:
                        raise RuntimeError("Geprüfte Übergangskette konnte nicht publiziert werden.")
                    return final
                step=next(stack[-1],None)
                if step is None:
                    stack.pop()
                    visited.remove(path.pop())
                    if edges:
                        edges.pop()
                    continue
                b,c=step
                path.append(b)
                edges.append(c)
                visited.add(b)
                best=max(best,len(path))
                stack.append(options(b,c,visited))
    raise ValueError(f"Keine vollständig geprüfte Kette mit {length} Titeln gefunden. Längste Kette: {best}.")
