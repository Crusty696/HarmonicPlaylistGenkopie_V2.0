"""Portable HPG playlist results, including the actual transition plans."""
import json
import os
from dataclasses import fields
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import playlist_results as pr
from .models import Track
from .caching import track_to_dict, dict_to_track
from .pair_candidates import CandidateSnapshot

_TYPES = {cls.__name__: cls for cls in (
    pr.PlaylistGenerationResult, pr.TrackOccurrence, pr.BoundaryResult,
    pr.ImmutableMetricsSnapshot, pr.ImmutableRecommendationSnapshot,
    pr.TransitionPlan, pr.GraphStats, pr.PathStats, CandidateSnapshot,
)}
_SEQUENCES = {cls.__name__: cls for cls in (tuple, pr._FrozenMapping, pr._FrozenSequence)}


def save_result(path, result):
    tracks = {track.track_id: i for i, track in enumerate(result.tracks)}

    def encode(value):
        name = type(value).__name__
        if isinstance(value, Track):
            return {"track": tracks[value.track_id]}
        if name in _TYPES:
            return {"type": name, "fields": {f.name: encode(getattr(value, f.name)) for f in fields(value)}}
        if name in _SEQUENCES:
            return {"seq": name, "items": [encode(x) for x in value]}
        return value

    payload = {"version": 1, "tracks": [track_to_dict(t) for t in result.tracks], "result": encode(result)}
    with NamedTemporaryFile(dir=Path(path).parent, delete=False, mode="w", encoding="utf8") as f:
        try:
            json.dump(payload, f, ensure_ascii=False, allow_nan=False)
            f.close()
            os.replace(f.name, path)
        finally:
            f.close()
            Path(f.name).unlink(missing_ok=True)


def load_result(path):
    with open(path, encoding="utf8") as f:
        payload = json.load(f)
    if payload["version"] != 1:
        raise ValueError("Unbekannte HPG-Setversion")
    tracks = [dict_to_track(row) for row in payload["tracks"]]

    def decode(value):
        if not isinstance(value, dict):
            return value
        if "track" in value:
            return tracks[value["track"]]
        if "seq" in value:
            return _SEQUENCES[value["seq"]](decode(x) for x in value["items"])
        return _TYPES[value["type"]](**{k: decode(v) for k,v in value["fields"].items()})

    result = decode(payload["result"])
    if not isinstance(result, pr.PlaylistGenerationResult) or len(result.recommendations) != len(result.tracks)-1:
        raise ValueError("Unvollständiges HPG-Set")
    return result
