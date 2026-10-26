"""Begrenzter Readernachweis mit synthetischem Audio; keine Modellinferenz."""
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _probe(payload):
    import ctypes as ct
    import numpy as np
    from hpg_core.ai_models.native_phrase_worker import NativeImage
    from hpg_core.ai_models.native_audio_reader import NativeAudioReader, bind_reader_imports
    request = json.loads(payload)
    image = NativeImage()
    bind_reader_imports(image)
    if image.function(0x2998258, ct.c_int32)() != 0:
        raise RuntimeError('Native stream initialization failed')
    reader = NativeAudioReader(image, request['path'])
    if request.get('compare_full'):
        import soundfile as sf
        maximum = 0.
        with sf.SoundFile(request['path']) as expected:
            if expected.samplerate != 44100 or expected.channels != 2:
                raise ValueError('Full exact comparison requires stereo44100')
            for start in range(0, reader.frames, 512):
                count = min(512, reader.frames-start)
                left, right = reader.read(start, count)
                reference = expected.read(count, dtype='float32', always_2d=True)
                maximum = max(maximum, float(np.max(np.abs(np.column_stack((left,right))-reference))))
        return json.dumps(dict(metadata=reader.metadata(), maximum_error=maximum)).encode()
    left, right = reader.read(0, 512)
    # Seek und Dateiende ebenfalls lesen; Audio bleibt im Kindprozess.
    end_left, end_right = reader.read(reader.frames-512, 512)
    return json.dumps(dict(metadata=reader.metadata(), left=left.tolist(),
        right=right.tolist(), finite_end=bool(np.isfinite(end_left).all()
        and np.isfinite(end_right).all()))).encode()


def probe(payload):
    import traceback
    try:
        return _probe(payload)
    except Exception:
        return json.dumps(dict(error=traceback.format_exc())).encode()


def main():
    import numpy as np
    import soundfile as sf
    from hpg_core.ai_models.process_runtime import OwnedModelProcess
    directory = Path(tempfile.mkdtemp(prefix='hpg-reader-proof-'))
    report = []
    if '--original-full' in sys.argv:
        source = Path(sys.argv[sys.argv.index('--original-full')+1])
        with OwnedModelProcess('tools.verify_native_reader', 'probe', max_payload_bytes=1024*1024) as owner:
            result = json.loads(owner.call(json.dumps(dict(path=str(source), compare_full=True)).encode(), deadline=time.monotonic()+60))
        (directory/'report.json').write_text(json.dumps(result,indent=2))
        print(directory/'report.json'); print(json.dumps(result,indent=2))
        return 0 if result.get('maximum_error') == 0 else 1
    cases = [('wav', 44100, 2), ('aiff', 44100, 2), ('wav', 48000, 1)]
    if '--resample-only' in sys.argv:
        cases = cases[-1:]
    for extension, rate, channels in cases:
        source = directory / f'synthetic-{rate}-{channels}.{extension}'
        signal = (np.sin(np.arange(rate * 2) * (2*np.pi*440/rate))*.25)
        audio = signal if channels == 1 else np.column_stack((signal, -signal))
        sf.write(source, audio, rate, subtype='PCM_16')
        try:
            with OwnedModelProcess('tools.verify_native_reader', 'probe',
                    max_payload_bytes=1024*1024) as owner:
                result = json.loads(owner.call(json.dumps(dict(path=str(source))).encode(),
                                                deadline=time.monotonic()+30))
            if 'error' in result:
                raise RuntimeError(result['error'])
            if rate == 44100:
                expected = sf.read(source, frames=512, dtype='float32', always_2d=True)[0]
                error = float(np.max(np.abs(np.column_stack((result['left'], result['right']))-expected)))
                result['maximum_error'] = error
                if error > 1/32768:
                    raise ValueError(f'Native PCM mismatch: {error}')
            elif max(abs(x) for x in result['left']) < .1:
                raise ValueError('Resampled signal missing')
            result.pop('left'); result.pop('right')
            report.append(dict(source=source.name, status='ok', **result))
        except Exception as error:
            report.append(dict(source=source.name, status='failed', reason=str(error)))
            break
    target = directory / 'report.json'
    target.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(target)
    print(json.dumps(report, indent=2))
    return 0 if len(report) == len(cases) and all(x['status']=='ok' for x in report) else 1


if __name__ == '__main__':
    raise SystemExit(main())
