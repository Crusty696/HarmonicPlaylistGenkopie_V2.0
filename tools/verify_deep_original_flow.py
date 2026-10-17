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
    parser.add_argument('--reuse-track', type=Path, action='append', default=[],
        help='Expliziter Analyse-Snapshot; Herkunft wird getrennt von frischer Analyse ausgewiesen')
    parser.add_argument('sources', nargs='+', type=Path)
    args = parser.parse_args()
    paths = [path.resolve(strict=True) for path in args.sources]
    if len(paths) < 2 or len(set(paths)) != len(paths):
        raise ValueError('Mindestens zwei unterschiedliche Originaltracks erforderlich')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ['HPG_CACHE_FILE'] = str(root / 'analysis.db')
    if args.reuse_features:
        os.environ['HPG_FEATURE_REUSE_REPORT'] = str(args.reuse_features.resolve(strict=True))
    for flag in ('HPG_STEMS', 'HPG_EMBEDDINGS', 'HPG_NATIVE_PHRASE'):
        os.environ[flag] = '1'
    from hpg_core.parallel_analyzer import ParallelAnalyzer
    from hpg_core import caching
    from hpg_core.playlist import generate_playlist_result, compute_transition_recommendations
    from hpg_core.transition_renderer import TransitionClipSpec
    from hpg_core.render_selection import render_with_reserve
    import numpy as np
    import soundfile as sf
    reusable = {}
    for snapshot_path in args.reuse_track:
        snapshot_path = snapshot_path.resolve(strict=True)
        saved = json.loads(snapshot_path.read_text(encoding='utf-8'))
        source = str(Path(saved['filePath']).resolve(strict=True))
        old_report = json.loads((snapshot_path.parent/'report.json').read_text(encoding='utf-8'))
        identity = old_report['sources'][source]
        if (identity.get('unchanged') is not True
                or identity['before_sha256'] != identity['after_sha256']
                or digest(source) != identity['before_sha256']):
            raise ValueError('Analyse-Snapshot gehört nicht zur unveränderten Quelle')
        if source in reusable or Path(source) not in paths:
            raise ValueError('Analyse-Snapshot doppelt oder außerhalb des Auftrags')
        reusable[source] = (caching.dict_to_track(saved), str(snapshot_path))
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
            reused_track = reusable.get(str(path))
            result = ([reused_track[0]] if reused_track else
                analyzer.analyze_files([str(path)], cache_policy='fresh',
                    progress_callback=lambda current, total, message: print(message, flush=True)))
            row = dict(path=str(path), elapsed_s=time.monotonic()-started, returned=len(result))
            row['origin'] = dict(kind='snapshot', path=reused_track[1]) if reused_track else dict(kind='fresh')
            report['analyses'].append(row)
            if result:
                track = result[0]
                snapshot = caching.track_to_dict(track)
                (root / f'track-{index}.json').write_text(json.dumps(snapshot, indent=2,
                    ensure_ascii=False, allow_nan=False), encoding='utf-8')
                row.update(bpm=track.bpm, grid=track.beatgrid_status,
                           stems=track.stem_analysis, embedding_status=track.embedding_analysis.get('status'),
                           native_status=track.native_phrase_analysis.get('status'))
                # Zusatzmerkmale mit Status unavailable duerfen die gueltige
                # Basisanalyse nicht verwerfen. Direkter Readback prueft den
                # Cache, ohne ueber analyze_files sofort erneut Stem-Inferenz
                # anzustossen.
                if not reused_track:
                    key = caching.generate_cache_key(str(path), track.rekordbox_signature)
                    row['cache_written'] = caching.cache_track(key, track)
                    if row['cache_written']:
                        cached = caching.get_cached_track(key, file_path=str(path))
                        row['cache_reused'] = cached is not None
                        if cached is not None:
                            row['cache_feature_statuses'] = dict(
                                stems=cached.stem_analysis.get('status'),
                                embedding=cached.embedding_analysis.get('status'))
                tracks.append(track)
            save()
        if len(tracks) != len(paths):
            raise RuntimeError('Nicht alle Originaltracks analysiert')
        playlist = generate_playlist_result(tracks, 'Harmonic Flow')
        report['playlist'] = dict(order=[track.filePath for track in playlist.tracks],
                                 boundaries=[asdict(value) for value in playlist.boundaries],
                                 quality=playlist.quality_dict())
        recommendations = compute_transition_recommendations(list(playlist.tracks),
            scoring_context=playlist.scoring_context_dict())
        save()
        for index, recommendation in enumerate(recommendations):
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
                deadline = time.monotonic()+120.
                def checkpoint():
                    if time.monotonic() > deadline:
                        raise TimeoutError('Originaltrack-Renderreserve-Zeitlimit')
                selected = render_with_reserve(playlist, index, sources, checkpoint)
                playlist = selected.playlist
                data = selected.audio
                row['spec'] = asdict(selected.spec)
                row['rejected'] = list(selected.rejected)
                report['playlist'] = dict(order=[track.filePath for track in playlist.tracks],
                    boundaries=[asdict(value) for value in playlist.boundaries],
                    quality=playlist.quality_dict())
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
