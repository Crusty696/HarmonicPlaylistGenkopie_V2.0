"""Begrenzter Originaltrack-Ablauf; eigener Cache, Audio ausschliesslich im RAM."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import sys
import time
import traceback
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reuse-features', type=Path,
        help='Belegordner fuer unveraenderte Stems/Embeddings; kein erneuter Modelllauf')
    parser.add_argument('sources', nargs=2, type=Path)
    args = parser.parse_args()
    paths = [path.resolve(strict=True) for path in args.sources]
    if len(set(paths)) != 2:
        raise ValueError('Zwei unterschiedliche Originaltracks erforderlich')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ['HPG_CACHE_FILE'] = str(root / 'analysis.db')
    if args.reuse_features:
        os.environ['HPG_FEATURE_REUSE_REPORT'] = str(args.reuse_features.resolve(strict=True))
    for flag in ('HPG_STEMS', 'HPG_EMBEDDINGS', 'HPG_NATIVE_PHRASE'):
        os.environ[flag] = '1'
    from hpg_core.parallel_analyzer import ParallelAnalyzer
    from hpg_core import caching
    from hpg_core.ai_models.deep_features import transient_failure
    from hpg_core.playlist import generate_playlist_result, compute_transition_recommendations
    from hpg_core.transition_renderer import TransitionClipSpec
    from hpg_core.hearing_playback import render_wav_bytes
    import numpy as np
    import soundfile as sf
    report = dict(scope='Originalquellen, Produkt-API; keine GUI- oder musikalische Abnahme',
                  cache_version=caching.CACHE_VERSION, sources={}, analyses=[], renders=[])
    report['feature_reuse_report'] = os.environ.get('HPG_FEATURE_REUSE_REPORT')
    project = Path(__file__).resolve().parents[1]
    report['code_sha256'] = {str(path.relative_to(project)): digest(path)
                             for path in (project / 'hpg_core').rglob('*.py')}
    for path in paths:
        report['sources'][str(path)] = dict(before_sha256=digest(path), size=path.stat().st_size)
    def save():
        (root / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                   default=str), encoding='utf-8')
    save()
    tracks = []
    try:
        analyzer = ParallelAnalyzer(max_workers=1)
        for index, path in enumerate(paths):
            started = time.monotonic()
            result = analyzer.analyze_files([str(path)], cache_policy='fresh',
                progress_callback=lambda current, total, message: print(message, flush=True))
            row = dict(path=str(path), elapsed_s=time.monotonic()-started, returned=len(result))
            report['analyses'].append(row)
            if result:
                track = result[0]
                snapshot = caching.track_to_dict(track)
                (root / f'track-{index}.json').write_text(json.dumps(snapshot, indent=2,
                    ensure_ascii=False, allow_nan=False), encoding='utf-8')
                row.update(bpm=track.bpm, grid=track.beatgrid_status,
                           stems=track.stem_analysis, embedding_status=track.embedding_analysis.get('status'),
                           native_status=track.native_phrase_analysis.get('status'))
                # Fresh schreibt absichtlich keinen Cache. Den isolierten
                # Snapshot explizit persistieren, dann den echten Lesepfad pruefen.
                if not transient_failure(track):
                    key = caching.generate_cache_key(str(path), track.rekordbox_signature)
                    row['cache_written'] = caching.cache_track(key, track)
                    if row['cache_written']:
                        reused = analyzer.analyze_files([str(path)], cache_policy='reuse')
                        row['cache_reused'] = (len(reused) == 1 and
                            getattr(reused[0], 'analysis_origin', None) == 'cache')
                tracks.append(track)
            save()
        if len(tracks) != 2:
            raise RuntimeError('Nicht beide Originaltracks analysiert')
        playlist = generate_playlist_result(tracks, 'Harmonic Flow')
        report['playlist'] = dict(order=[track.filePath for track in playlist.tracks],
                                 boundaries=[asdict(value) for value in playlist.boundaries],
                                 quality=playlist.quality_dict())
        recommendations = compute_transition_recommendations(list(playlist.tracks),
            scoring_context=playlist.scoring_context_dict())
        save()
        for recommendation in recommendations:
            row = dict(candidate= recommendation.kandidat_aktiv, notes=recommendation.notes)
            report['renders'].append(row)
            if recommendation.plan is None or recommendation.kandidat_aktiv <= 0:
                row['status'] = 'blocked_no_active_candidate'
                continue
            spec = TransitionClipSpec.from_plan(recommendation.plan,
                recommendation.from_track, recommendation.to_track)
            row['spec'] = asdict(spec)
            try:
                sources = [dict(path=str(path), size_bytes=report['sources'][str(path)]['size'],
                                sha256=report['sources'][str(path)]['before_sha256']) for path in paths]
                data = render_wav_bytes(asdict(spec), sources)
                samples, rate = sf.read(io.BytesIO(data), always_2d=True)
                row.update(status='rendered_ram', frames=len(samples), sample_rate=rate,
                           finite=bool(np.isfinite(samples).all()), peak=float(np.max(np.abs(samples))))
            except Exception:
                row.update(status='error', error=traceback.format_exc())
            save()
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        for path in paths:
            row = report['sources'][str(path)]
            row['after_sha256'] = digest(path)
            row['unchanged'] = row['before_sha256'] == row['after_sha256']
        save()
    print(json.dumps(dict(report=str(root/'report.json'), error=report.get('error'),
                          renders=[row.get('status') for row in report['renders']])), flush=True)
    return int(bool(report.get('error')) or not report['renders'] or
               any(row.get('status') != 'rendered_ram' for row in report['renders']) or
               any(not row['unchanged'] for row in report['sources'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
