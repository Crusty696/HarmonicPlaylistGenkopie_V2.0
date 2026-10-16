"""Original-Snapshots über die normale Renderreserve prüfen, ohne Neuanalyse."""
import argparse
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.analysis.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ['HPG_CACHE_FILE'] = str(output/'isolated.db')
    os.environ['HPG_CANDIDATE_CHOICES_FILE'] = str(output/'choices.json')
    from hpg_core.ai_models.feature_reuse import digest
    from hpg_core.caching import dict_to_track
    from hpg_core.playlist import generate_playlist_result
    from hpg_core.render_selection import render_with_reserve
    import numpy as np
    import soundfile as sf
    report = json.loads((root/'report.json').read_text(encoding='utf8'))
    sources = []
    for path, identity in report['sources'].items():
        if digest(path) != identity['before_sha256']:
            raise ValueError('Originalquelle seit Analyse verändert')
        sources.append(dict(path=path, size_bytes=identity['size'], sha256=identity['before_sha256']))
    tracks = [dict_to_track(json.loads(path.read_text(encoding='utf8')))
              for path in sorted(root.glob('track-*.json'))]
    if len(tracks) != len(sources):
        raise ValueError('Analyse unvollständig')
    result = generate_playlist_result(tracks, 'Harmonic Flow', candidate_choice_snapshot={})
    rows = []
    for index in range(len(tracks)-1):
        started = time.monotonic()
        def checkpoint():
            if time.monotonic()-started > 120:
                raise TimeoutError('Renderreserve-Zeitlimit')
        row = dict(index=index)
        rows.append(row)
        try:
            selected = render_with_reserve(result, index, sources, checkpoint)
            result = selected.playlist
            samples, rate = sf.read(io.BytesIO(selected.audio), always_2d=True)
            row.update(status='rendered_ram', spec=asdict(selected.spec),
                       rejected=list(selected.rejected), bytes=len(selected.audio),
                       finite=bool(np.isfinite(samples).all()), peak=float(np.max(np.abs(samples))),
                       duration=len(samples)/rate)
        except Exception:
            row.update(status='error', error=traceback.format_exc())
        row['elapsed_s'] = time.monotonic()-started
        (output/'report.json').write_text(json.dumps(dict(analysis=str(root), renders=rows,
            order=[t.filePath for t in result.tracks]), indent=2), encoding='utf8')
    return int(any(row['status'] != 'rendered_ram' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
