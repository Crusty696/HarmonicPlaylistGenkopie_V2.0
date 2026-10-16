"""Nur noch ungepruefte Mixkandidaten aus einem Originaltrack-Beleg rendern."""
from pathlib import Path
import sys
import os
import json
import io
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    os.environ['HPG_CACHE_FILE'] = str(root/'analysis.db')
    from hpg_core import caching
    from hpg_core.playlist import generate_playlist_result, rebuild_result_for_order
    from hpg_core.candidate_choices import schluessel
    from hpg_core.transition_renderer import TransitionClipSpec, BeatSyncError
    from hpg_core.hearing_playback import render_wav_bytes
    import numpy as np
    import soundfile as sf
    prior = json.loads((root/'report.json').read_text(encoding='utf-8'))
    tracks = [caching.dict_to_track(json.loads((root/f'track-{i}.json').read_text(encoding='utf-8'))) for i in range(2)]
    result = generate_playlist_result(tracks, 'Harmonic Flow')
    reverse = '--reverse' in sys.argv[2:]
    if reverse:
        result = rebuild_result_for_order(result, [o.occurrence_id for o in reversed(result.occurrences)])
    sources = [dict(path=p, size_bytes=s['size'], sha256=s['before_sha256']) for p,s in prior['sources'].items()]
    tried = set() if reverse else {(r['spec']['mix_out_sec'], r['spec']['mix_in_sec'], r['spec']['crossfade_sec']) for r in prior['renders']}
    rows = []
    output = root/('candidate-reverse.json' if reverse else 'candidate-delta.json')
    candidates = result.boundaries[0].snapshots
    if '--reserve' in sys.argv[2:]:
        # Nur Suchraum-Diagnose, kein Nachweis der normalen Produktauswahl.
        from hpg_core import pair_candidates
        if output.exists():
            for row in json.loads(output.read_text(encoding='utf-8')):
                s = row['spec']
                tried.add((s['mix_out_sec'],s['mix_in_sec'],s['crossfade_sec']))
        candidates = pair_candidates.rank_pair_candidates(*result.tracks, max_combinations=30)
        output = output.with_stem(output.stem+'-reserve')
    for candidate in candidates:
        if (candidate.t_out, candidate.t_in, candidate.overlap_sec) in tried:
            continue
        a,b = result.tracks
        choice = {schluessel(a.filePath,b.filePath): dict(t_out=candidate.t_out,
            t_in=candidate.t_in, blend_bars=candidate.blend_bars)}
        selected = rebuild_result_for_order(result, [o.occurrence_id for o in result.occurrences], choice)
        plan = selected.recommendations[0].plan
        spec = TransitionClipSpec.from_plan(plan, a, b)
        row = dict(rank=candidate.rang, choice=choice, spec=asdict(spec))
        rows.append(row)
        try:
            audio = render_wav_bytes(asdict(spec), sources)
            samples, sr = sf.read(io.BytesIO(audio), always_2d=True)
            row.update(status='rendered_ram', frames=len(samples), sr=sr,
                       finite=bool(np.isfinite(samples).all()), peak=float(np.max(np.abs(samples))))
        except BeatSyncError as error:
            row.update(status='beat_sync_rejected', error=str(error))
        output.write_text(json.dumps(rows, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in row.items() if k not in ('choice','spec')}), flush=True)
        if row['status'] == 'rendered_ram':
            return 0
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
