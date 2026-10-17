"""Gemeinsame Provenienzlabels der Analyse-Reader."""

from pathlib import Path


_LOSSY_SOURCE_SUFFIXES = frozenset({'.mp3', '.mp4', '.m4a', '.aac', '.ogg', '.wma'})


def source_duration_tolerance(path, *, sample_rate=16000):
    """Gemeinsame Laengentoleranz fuer verlustbehaftete Decoderquellen."""
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError('Invalid source-duration sample rate')
    if Path(path).suffix.lower() in _LOSSY_SOURCE_SUFFIXES:
        return .1
    return 1 / sample_rate

NATIVE_BEAT_INPUT_CONVENTIONS = {
    'rekordbox-builtin-mp3': 'rekordbox-builtin-mp3-planar-float32',
    'rekordbox-builtin': 'rekordbox-builtin-planar-float32',
    'rekordbox-builtin-flac': 'rekordbox-builtin-flac-planar-float32',
    'rekordbox-builtin-mp4': 'rekordbox-builtin-mp4-planar-float32',
    'rekordbox-builtin-aac': 'rekordbox-builtin-aac-planar-float32',
    'rekordbox-mpg123': 'rekordbox-mpg123-planar-float32',
    'rekordbox-mpg123-soxr-hq': 'rekordbox-mpg123-soxr-hq-planar-float32',
    'rekordbox-mpg123-stream': 'rekordbox-mpg123-stream-planar-float32',
    'rekordbox-mpg123-soxr-hq-stream': 'rekordbox-mpg123-soxr-hq-stream-planar-float32',
    'hpg-libsndfile': 'hpg-libsndfile-planar-float32',
    'hpg-librosa': 'hpg-librosa-planar-float32',
    'hpg-libsndfile-soxr-hq-44100': 'hpg-libsndfile-soxr-hq-44100-planar-float32',
    'hpg-libsndfile-pcm16-44100': 'hpg-libsndfile-pcm16-44100-planar-float32',
    'hpg-libsndfile-mono-downmix-44100': 'hpg-libsndfile-mono-downmix-planar-float32',
    'hpg-librosa-mono-downmix-44100': 'hpg-librosa-mono-downmix-planar-float32',
    'hpg-audioread-pcm16-44100': 'hpg-audioread-pcm16-44100-planar-float32',
    'hpg-audioread-soxr-hq-44100': 'hpg-audioread-soxr-hq-44100-planar-float32',
    'hpg-audioread-mono-downmix-44100': 'hpg-audioread-mono-downmix-planar-float32',
}

# Der gemeinsame Validator und der Beat-Adapter teilen dieselbe Backendliste;
# ein neu zugelassener Reader kann so nicht still ohne Modellkonvention bleiben.
READER_BACKENDS = frozenset(NATIVE_BEAT_INPUT_CONVENTIONS)
_BACKEND_BY_CONVENTION = {
    convention: backend for backend, convention in NATIVE_BEAT_INPUT_CONVENTIONS.items()
}
LOSSY_READER_BACKENDS = READER_BACKENDS - frozenset({
    'rekordbox-builtin', 'rekordbox-builtin-flac',
})
SOURCE_BIT_DEPTH_REQUIRED_BACKENDS = frozenset({
    'rekordbox-builtin', 'rekordbox-builtin-flac',
})


def reader_duration_tolerance(backend, *, sample_rate=44100):
    """Format-aware tolerance between decoder frames and track metadata."""
    if (type(backend) is not str or backend not in READER_BACKENDS
            or type(sample_rate) is not int or sample_rate <= 0):
        raise ValueError('Unknown audio reader backend')
    return .1 if backend in LOSSY_READER_BACKENDS else 2 / sample_rate


def convention_duration_tolerance(convention):
    """Resolve source-duration tolerance from a persisted reader convention."""
    if type(convention) is not str:
        raise ValueError('Unknown audio reader convention')
    backend = _BACKEND_BY_CONVENTION.get(convention)
    if backend is None:
        raise ValueError('Unknown audio reader convention')
    return reader_duration_tolerance(backend)
